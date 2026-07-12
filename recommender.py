"""Content-based dish recommender using cosine similarity.

Feature vector per dish (34 dims total):
  - cuisine_profile one-hot      (11 dims)
  - tags multi-hot                (18 dims)
  - price_rm min-max normalized   (1 dim)
  - spice_level / 3               (1 dim)
  - halal one-hot                 (3 dims)

Vectors are built once and cached in memory (see build_dish_matrix).
"""
import hashlib
import sqlite3

import numpy as np
import pandas as pd

DB_PATH = "lokaleats.db"

CUISINES = [
    "malay", "chinese", "tomyam", "seafood", "kopitiam", "cafe",
    "western", "indian", "burger", "bakery", "cendol",
]
TAGS = [
    "breakfast", "rice", "noodle", "soup", "seafood", "western",
    "dessert", "drink", "dinner", "lunch", "grilled", "fish", "burger",
    "salad", "healthy", "pastry", "snack", "side",
]
HALAL_VALUES = ["halal", "non-halal", "unknown"]

N_CUISINE = len(CUISINES)
N_TAGS = len(TAGS)
N_HALAL = len(HALAL_VALUES)
PRICE_IDX = N_CUISINE + N_TAGS
SPICE_IDX = PRICE_IDX + 1
HALAL_START = SPICE_IDX + 1
VEC_LEN = HALAL_START + N_HALAL

EARTH_RADIUS_KM = 6371.0


def load_data(conn=None):
    """Load dishes joined with restaurant info as a DataFrame."""
    own_conn = conn is None
    if own_conn:
        conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT d.dish_id, d.dish_name, d.price_rm, d.spice_level, d.halal,
               d.tags, d.cuisine_profile, d.place_id,
               r.name AS restaurant_name, r.city, r.district,
               r.latitude, r.longitude, r.rating AS restaurant_rating,
               r.gmaps_url, r.price_range AS restaurant_price_range
        FROM dishes d
        JOIN restaurants r ON d.place_id = r.place_id
    """
    df = pd.read_sql_query(query, conn)
    if own_conn:
        conn.close()
    return df


def build_dish_matrix(df):
    """Build the (n_dishes, VEC_LEN) feature matrix for all dishes."""
    n = len(df)
    matrix = np.zeros((n, VEC_LEN), dtype=np.float64)

    cuisine_idx = {c: i for i, c in enumerate(CUISINES)}
    tag_idx = {t: i for i, t in enumerate(TAGS)}
    halal_idx = {h: i for i, h in enumerate(HALAL_VALUES)}

    price_min = df["price_rm"].min()
    price_max = df["price_rm"].max()
    price_range = (price_max - price_min) or 1.0

    for row_i, row in enumerate(df.itertuples(index=False)):
        c = cuisine_idx.get(row.cuisine_profile)
        if c is not None:
            matrix[row_i, c] = 1.0

        for tag in str(row.tags).split(","):
            tag = tag.strip()
            t = tag_idx.get(tag)
            if t is not None:
                matrix[row_i, N_CUISINE + t] = 1.0

        matrix[row_i, PRICE_IDX] = (row.price_rm - price_min) / price_range
        matrix[row_i, SPICE_IDX] = row.spice_level / 3.0

        h = halal_idx.get(row.halal)
        if h is not None:
            matrix[row_i, HALAL_START + h] = 1.0

    return matrix, {"price_min": price_min, "price_max": price_max, "price_range": price_range}


def build_user_vector(user, price_stats):
    """Build a feature vector for a user from their stored preferences.

    user: dict with budget_max, spice_pref, halal_only, cuisines (list), tags_pref (list)
    """
    vec = np.zeros(VEC_LEN, dtype=np.float64)

    for cuisine in user.get("cuisines") or []:
        if cuisine in CUISINES:
            vec[CUISINES.index(cuisine)] = 1.0

    for tag in user.get("tags_pref") or []:
        if tag in TAGS:
            vec[N_CUISINE + TAGS.index(tag)] = 1.0

    # Users like dishes comfortably under budget: target price = 0.6 * budget_max
    target_price = 0.6 * user["budget_max"]
    vec[PRICE_IDX] = (target_price - price_stats["price_min"]) / price_stats["price_range"]
    vec[PRICE_IDX] = np.clip(vec[PRICE_IDX], 0.0, 1.0)

    vec[SPICE_IDX] = user["spice_pref"] / 3.0

    if user.get("halal_only"):
        vec[HALAL_START + HALAL_VALUES.index("halal")] = 1.0
    else:
        # no strong halal preference signal -> leave halal dims at 0
        pass

    return vec


def cosine_similarity_matrix(matrix, vec):
    """Cosine similarity between every row of matrix and vec."""
    matrix_norm = np.linalg.norm(matrix, axis=1)
    vec_norm = np.linalg.norm(vec)
    denom = matrix_norm * vec_norm
    denom[denom == 0] = 1e-9
    return (matrix @ vec) / denom


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def _tie_breaker(dish_id):
    """Small deterministic noise in [0, 1e-6) from a hash of dish_id."""
    h = hashlib.md5(dish_id.encode()).hexdigest()
    return (int(h[:8], 16) % 1_000_000) / 1_000_000 * 1e-6


def recommend(df, matrix, price_stats, user, district=None, lat=None, lng=None,
              max_km=None, k=10, liked_tags=None):
    """Return top-k recommended dishes for a user as a DataFrame with a 'score' column.

    Hard filters (applied before scoring, never ranked away):
      - price_rm <= budget_max
      - halal_only -> halal == 'halal' only (excludes 'unknown')
      - optional district filter
      - optional max distance from (lat, lng)
    """
    mask = df["price_rm"] <= user["budget_max"]

    if user.get("halal_only"):
        mask &= df["halal"] == "halal"

    if district:
        mask &= df["district"] == district

    if lat is not None and lng is not None and max_km is not None:
        dist = haversine_km(lat, lng, df["latitude"].values, df["longitude"].values)
        mask &= dist <= max_km

    idx = np.where(mask.values)[0]
    if len(idx) == 0:
        return df.iloc[0:0].assign(score=[])

    sub_df = df.iloc[idx].reset_index(drop=True)
    sub_matrix = matrix[idx]

    user_vec = build_user_vector(user, price_stats)
    sims = cosine_similarity_matrix(sub_matrix, user_vec)

    ratings_filled = sub_df["restaurant_rating"].fillna(3.5).values / 5.0

    if liked_tags:
        tag_overlap = np.zeros(len(sub_df))
        for i, tags in enumerate(sub_df["tags"]):
            dish_tags = {t.strip() for t in str(tags).split(",")}
            if dish_tags:
                tag_overlap[i] = len(dish_tags & liked_tags) / len(dish_tags)
        score = 0.7 * sims + 0.2 * ratings_filled + 0.1 * tag_overlap
    else:
        # redistribute the 0.1 liked-tag weight when the user has no likes yet
        score = 0.8 * sims + 0.2 * ratings_filled

    tie_noise = np.array([_tie_breaker(did) for did in sub_df["dish_id"]])
    score = score + tie_noise

    sub_df = sub_df.assign(score=score)
    return sub_df.sort_values("score", ascending=False).head(k).reset_index(drop=True)


def similar_dishes(df, matrix, dish_id, k=5):
    """Nearest neighbors of a dish vector, excluding same-restaurant duplicates
    of the identical dish_name and the dish itself."""
    match = df.index[df["dish_id"] == dish_id]
    if len(match) == 0:
        return df.iloc[0:0].assign(score=[])
    src_i = match[0]
    src_vec = matrix[src_i]
    src_name = df.iloc[src_i]["dish_name"]

    sims = cosine_similarity_matrix(matrix, src_vec)

    exclude = (df["dish_id"] == dish_id) | (df["dish_name"] == src_name)
    sims = np.where(exclude.values, -np.inf, sims)

    top_idx = np.argsort(sims)[::-1][:k]
    result = df.iloc[top_idx].copy()
    result["score"] = sims[top_idx]
    return result.reset_index(drop=True)


if __name__ == "__main__":
    df = load_data()
    matrix, price_stats = build_dish_matrix(df)
    print(f"Loaded {len(df)} dishes, feature matrix shape {matrix.shape}")

    test_user = {
        "budget_max": 15.0,
        "spice_pref": 2,
        "halal_only": True,
        "cuisines": ["tomyam", "seafood"],
        "tags_pref": ["soup", "spicy" if False else "seafood"],
    }

    top10 = recommend(df, matrix, price_stats, test_user, k=10)
    print("\nTop 10 recommendations for test user (tomyam/seafood, halal, budget RM15, spice 2):")
    cols = ["dish_id", "dish_name", "restaurant_name", "district", "price_rm",
            "spice_level", "halal", "cuisine_profile", "score"]
    print(top10[cols].to_string(index=False))

    print("\nSimilar dishes to the top result:")
    sims = similar_dishes(df, matrix, top10.iloc[0]["dish_id"], k=5)
    print(sims[["dish_id", "dish_name", "restaurant_name", "score"]].to_string(index=False))
