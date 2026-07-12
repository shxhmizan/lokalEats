"""Loads perak_restaurant.csv and dishes.csv into lokaleats.db (SQLite).

Idempotent: drops and recreates all tables on every run.
"""
import sqlite3
import pandas as pd

DB_PATH = "lokaleats.db"

SCHEMA = """
CREATE TABLE restaurants (
  place_id TEXT PRIMARY KEY, name TEXT, category TEXT, address TEXT,
  city TEXT, district TEXT, latitude REAL, longitude REAL, phone TEXT,
  price_range TEXT, rating REAL, reviews_count INTEGER, gmaps_url TEXT
);
CREATE TABLE dishes (
  dish_id TEXT PRIMARY KEY, dish_name TEXT, price_rm REAL,
  spice_level INTEGER, halal TEXT, tags TEXT, cuisine_profile TEXT,
  place_id TEXT REFERENCES restaurants(place_id)
);
CREATE TABLE users (
  user_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
  budget_max REAL, spice_pref INTEGER, halal_only INTEGER,
  cuisines TEXT,
  tags_pref TEXT
);
CREATE TABLE ratings (
  user_id INTEGER, dish_id TEXT, liked INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, dish_id)
);
CREATE TABLE llm_cache (
  dish_id TEXT, user_id INTEGER, text TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (dish_id, user_id)
);
"""


def main():
    restaurants = pd.read_csv("perak_restaurant.csv")
    dishes = pd.read_csv("dishes.csv")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for table in ("dishes", "ratings", "llm_cache", "users", "restaurants"):
        cur.execute(f"DROP TABLE IF EXISTS {table}")
    cur.executescript(SCHEMA)

    r = restaurants[[
        "place_id", "name", "category", "address", "city", "district",
        "latitude", "longitude", "phone", "price_range", "rating",
        "reviews_count", "gmaps_url",
    ]].copy()
    r.to_sql("restaurants", conn, if_exists="append", index=False)

    d = dishes[[
        "dish_id", "dish_name", "price_rm", "spice_level", "halal",
        "tags", "cuisine_profile", "place_id",
    ]].copy()
    d.to_sql("dishes", conn, if_exists="append", index=False)

    conn.commit()

    n_restaurants = cur.execute("SELECT COUNT(*) FROM restaurants").fetchone()[0]
    n_dishes = cur.execute("SELECT COUNT(*) FROM dishes").fetchone()[0]
    print(f"Loaded {n_restaurants} restaurants, {n_dishes} dishes into {DB_PATH}")

    conn.close()


if __name__ == "__main__":
    main()
