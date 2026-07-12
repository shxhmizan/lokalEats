"""LokalEats FastAPI app: dish recommendations for Perak, Malaysia."""
import os
import sqlite3
import sys

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import recommender as rec

DB_PATH = "lokaleats.db"

if not os.path.exists(DB_PATH):
    print("lokaleats.db not found — run seed_db.py first")
    sys.exit(1)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Load dish data + feature matrix once at startup and cache in memory.
_conn = get_conn()
DISH_DF = rec.load_data(_conn)
DISH_MATRIX, PRICE_STATS = rec.build_dish_matrix(DISH_DF)
_conn.close()

app = FastAPI(title="LokalEats API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Pydantic models ----------

class UserCreate(BaseModel):
    name: str
    budget_max: float
    spice_pref: int
    halal_only: bool
    cuisines: list[str] = []
    tags_pref: list[str] = []


class RatingCreate(BaseModel):
    user_id: int
    dish_id: str
    liked: bool


class ExplainRequest(BaseModel):
    user_id: int
    dish_id: str


class NlqRequest(BaseModel):
    user_id: int
    query: str


# ---------- Helpers ----------

def user_row_to_dict(row):
    return {
        "user_id": row["user_id"],
        "name": row["name"],
        "budget_max": row["budget_max"],
        "spice_pref": row["spice_pref"],
        "halal_only": bool(row["halal_only"]),
        "cuisines": row["cuisines"].split(",") if row["cuisines"] else [],
        "tags_pref": row["tags_pref"].split(",") if row["tags_pref"] else [],
    }


def _clean(value):
    """Convert pandas/numpy NaN to None so the JSON encoder never sees it."""
    if isinstance(value, float) and value != value:
        return None
    return value


def dish_row_to_dict(row):
    d = {
        "dish_id": row["dish_id"],
        "dish_name": row["dish_name"],
        "price_rm": row["price_rm"],
        "spice_level": int(row["spice_level"]),
        "halal": row["halal"],
        "tags": [t.strip() for t in str(row["tags"]).split(",") if t.strip()],
        "cuisine_profile": row["cuisine_profile"],
        "restaurant_name": row["restaurant_name"],
        "place_id": row["place_id"],
        "city": _clean(row["city"]),
        "district": row["district"],
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "restaurant_rating": _clean(row["restaurant_rating"]),
        "gmaps_url": _clean(row["gmaps_url"]),
    }
    if "score" in row:
        d["score"] = round(float(row["score"]), 4)
    return d


def get_user_or_404(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="user not found")
    return row


def get_liked_tags(conn, user_id):
    """Tags from dishes the user has liked, for the tag-overlap score component."""
    rows = conn.execute(
        "SELECT dish_id FROM ratings WHERE user_id = ? AND liked = 1", (user_id,)
    ).fetchall()
    if not rows:
        return None
    liked_ids = {r["dish_id"] for r in rows}
    tags = set()
    subset = DISH_DF[DISH_DF["dish_id"].isin(liked_ids)]
    for t in subset["tags"]:
        tags.update(x.strip() for x in str(t).split(","))
    return tags or None


# ---------- Routes ----------

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/users")
def create_user(user: UserCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO users (name, budget_max, spice_pref, halal_only, cuisines, tags_pref) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user.name,
            user.budget_max,
            user.spice_pref,
            int(user.halal_only),
            ",".join(user.cuisines),
            ",".join(user.tags_pref),
        ),
    )
    conn.commit()
    user_id = cur.lastrowid
    row = get_user_or_404(conn, user_id)
    result = user_row_to_dict(row)
    conn.close()
    return result


@app.get("/api/users/{user_id}")
def get_user(user_id: int):
    conn = get_conn()
    row = get_user_or_404(conn, user_id)
    result = user_row_to_dict(row)
    conn.close()
    return result


@app.get("/api/recommend")
def recommend_dishes(user_id: int, district: str | None = None,
                      lat: float | None = None, lng: float | None = None,
                      max_km: float | None = None, max_price: float | None = None,
                      k: int = 10):
    conn = get_conn()
    row = get_user_or_404(conn, user_id)
    user = user_row_to_dict(row)
    liked_tags = get_liked_tags(conn, user_id)
    conn.close()

    if max_price is not None:
        user["budget_max"] = max_price

    results = rec.recommend(
        DISH_DF, DISH_MATRIX, PRICE_STATS, user,
        district=district, lat=lat, lng=lng, max_km=max_km, k=k,
        liked_tags=liked_tags,
    )
    return [dish_row_to_dict(r) for _, r in results.iterrows()]


@app.get("/api/dishes/{dish_id}/similar")
def get_similar_dishes(dish_id: str, k: int = 5):
    if dish_id not in DISH_DF["dish_id"].values:
        raise HTTPException(status_code=404, detail="dish not found")
    results = rec.similar_dishes(DISH_DF, DISH_MATRIX, dish_id, k=k)
    return [dish_row_to_dict(r) for _, r in results.iterrows()]


@app.post("/api/rate")
def rate_dish(rating: RatingCreate):
    """Star (liked=true) or unstar (liked=false) a dish. Unstarring removes the row."""
    conn = get_conn()
    get_user_or_404(conn, rating.user_id)
    if rating.dish_id not in DISH_DF["dish_id"].values:
        conn.close()
        raise HTTPException(status_code=404, detail="dish not found")
    if rating.liked:
        conn.execute(
            "INSERT INTO ratings (user_id, dish_id, liked) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, dish_id) DO UPDATE SET liked = 1, "
            "created_at = CURRENT_TIMESTAMP",
            (rating.user_id, rating.dish_id),
        )
    else:
        conn.execute(
            "DELETE FROM ratings WHERE user_id = ? AND dish_id = ?",
            (rating.user_id, rating.dish_id),
        )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.get("/api/starred")
def get_starred(user_id: int):
    conn = get_conn()
    get_user_or_404(conn, user_id)
    rows = conn.execute(
        "SELECT dish_id FROM ratings WHERE user_id = ? AND liked = 1 "
        "ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()

    dish_ids = [r["dish_id"] for r in rows]
    if not dish_ids:
        return []
    order = {did: i for i, did in enumerate(dish_ids)}
    subset = DISH_DF[DISH_DF["dish_id"].isin(dish_ids)].copy()
    subset["_order"] = subset["dish_id"].map(order)
    subset = subset.sort_values("_order")
    return [dish_row_to_dict(r) for _, r in subset.iterrows()]


@app.get("/api/dishes")
def browse_dishes(search: str | None = None, district: str | None = None,
                   cuisine: str | None = None, halal: str | None = None,
                   max_price: float | None = None, k: int = 50):
    df = DISH_DF
    mask = df["dish_id"].notna()

    if search:
        s = search.lower()
        mask &= (
            df["dish_name"].str.lower().str.contains(s, na=False)
            | df["restaurant_name"].str.lower().str.contains(s, na=False)
        )
    if district:
        mask &= df["district"] == district
    if cuisine:
        mask &= df["cuisine_profile"] == cuisine
    if halal:
        mask &= df["halal"] == halal
    if max_price is not None:
        mask &= df["price_rm"] <= max_price

    results = df[mask].head(k)
    return [dish_row_to_dict(r) for _, r in results.iterrows()]


@app.get("/api/districts")
def list_districts():
    counts = DISH_DF["district"].value_counts().to_dict()
    return [{"district": d, "count": int(c)} for d, c in counts.items()]


@app.post("/api/explain")
def explain(req: ExplainRequest):
    import llm
    conn = get_conn()
    user_row = get_user_or_404(conn, req.user_id)
    user = user_row_to_dict(user_row)

    cached = conn.execute(
        "SELECT text FROM llm_cache WHERE dish_id = ? AND user_id = ?",
        (req.dish_id, req.user_id),
    ).fetchone()
    if cached:
        conn.close()
        return {"text": cached["text"]}

    dish_rows = DISH_DF[DISH_DF["dish_id"] == req.dish_id]
    if dish_rows.empty:
        conn.close()
        raise HTTPException(status_code=404, detail="dish not found")
    dish = dish_rows.iloc[0].to_dict()

    result = llm.explain(user, dish)
    if "error" not in result:
        conn.execute(
            "INSERT OR REPLACE INTO llm_cache (dish_id, user_id, text) VALUES (?, ?, ?)",
            (req.dish_id, req.user_id, result["text"]),
        )
        conn.commit()
    conn.close()
    return result


@app.post("/api/nlq")
def nlq(req: NlqRequest):
    import llm
    conn = get_conn()
    get_user_or_404(conn, req.user_id)
    conn.close()

    parsed = llm.parse_query(req.query)
    if "error" in parsed:
        return parsed

    conn = get_conn()
    row = get_user_or_404(conn, req.user_id)
    user = user_row_to_dict(row)
    liked_tags = get_liked_tags(conn, req.user_id)
    conn.close()

    if parsed.get("max_price") is not None:
        user["budget_max"] = parsed["max_price"]
    if parsed.get("spice_min") is not None:
        user["spice_pref"] = parsed["spice_min"]
    if parsed.get("halal_only"):
        user["halal_only"] = True
    if parsed.get("cuisine"):
        user["cuisines"] = list(set(user["cuisines"]) | {parsed["cuisine"]})
    if parsed.get("tags"):
        user["tags_pref"] = list(set(user["tags_pref"]) | set(parsed["tags"]))

    results = rec.recommend(
        DISH_DF, DISH_MATRIX, PRICE_STATS, user,
        district=parsed.get("district"), k=10, liked_tags=liked_tags,
    )
    return {
        "parsed_filters": parsed,
        "results": [dish_row_to_dict(r) for _, r in results.iterrows()],
    }


app.mount("/", StaticFiles(directory="static", html=True), name="static")
