"""OpenRouter LLM calls: explaining recommendations and parsing natural-language queries.

The LLM never selects dishes -- recommender.py's cosine-similarity engine does that.
This module only (a) explains a dish pick in one casual sentence, and (b) turns a
free-text query into a filter JSON that main.py then feeds into recommender.recommend().

If OPENROUTER_API_KEY is not set, both explain() and parse_query() return
{"error": "llm_disabled"} so the rest of the app keeps working without a key.
"""
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "google/gemini-2.5-flash-lite"
TIMEOUT_SECS = 15


def _call_openrouter(messages, temperature, max_tokens):
    """POST to OpenRouter chat completions, one retry on failure. Raises on final failure."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    last_err = None
    for _ in range(2):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT_SECS)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            last_err = e
    raise last_err


def _strip_json_fences(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def explain(user, dish):
    """Return {"text": "..."} with one casual BM/English sentence, or {"error": ...}."""
    if not API_KEY:
        return {"error": "llm_disabled"}

    prompt = (
        "You are a friendly Malaysian food buddy. Given a user's preferences and a "
        "recommended dish, write ONE short sentence explaining why it's a good pick. "
        "Use a casual Malaysian tone mixing English and Bahasa Malaysia (Manglish/rojak "
        "style), like: \"Sedap ni — spicy tomyam under RM12, memang match your budget\". "
        "Keep it under 25 words. Do not use quotation marks in your reply.\n\n"
        f"User preferences: budget max RM{user['budget_max']}, spice preference "
        f"{user['spice_pref']}/3, halal only: {user['halal_only']}, "
        f"favourite cuisines: {', '.join(user['cuisines']) or 'none specified'}.\n"
        f"Dish: {dish['dish_name']} from {dish['restaurant_name']}, price RM{dish['price_rm']}, "
        f"spice level {dish['spice_level']}/3, halal status: {dish['halal']}, "
        f"cuisine: {dish['cuisine_profile']}, tags: {dish['tags']}."
    )

    try:
        text = _call_openrouter(
            [{"role": "user", "content": prompt}], temperature=0.7, max_tokens=60
        )
        return {"text": text.strip()}
    except Exception as e:
        return {"error": f"llm_request_failed: {e}"}


def parse_query(query):
    """Parse a free-text query (BM/English) into a strict filter JSON dict.

    Returns keys: max_price, spice_min, district, cuisine, tags, halal_only.
    On failure returns {"error": ...}.
    """
    if not API_KEY:
        return {"error": "llm_disabled"}

    prompt = (
        "Convert the following food search query (may be in Bahasa Malaysia, English, "
        "or mixed) into STRICT JSON with exactly these keys: "
        '"max_price" (number or null), "spice_min" (integer 0-3 or null), '
        '"district" (one of: Kinta, Manjung, Larut Matang & Selama, Hilir Perak, '
        "Batang Padang, Kampar, Kerian, Kuala Kangsar, Hulu Perak, Muallim, or null), "
        '"cuisine" (one of: malay, chinese, tomyam, seafood, kopitiam, cafe, western, '
        'indian, burger, bakery, cendol, or null), "tags" (array of strings from: '
        "breakfast, rice, noodle, soup, seafood, western, dessert, drink, dinner, lunch, "
        'grilled, fish, burger, salad, healthy, pastry, snack, side), "halal_only" '
        "(boolean).\n"
        "Respond with ONLY the JSON object, no markdown fences, no explanation.\n\n"
        f"Query: {query}"
    )

    try:
        text = _call_openrouter(
            [{"role": "user", "content": prompt}], temperature=0.2, max_tokens=200
        )
        text = _strip_json_fences(text)
        parsed = json.loads(text)
        return {
            "max_price": parsed.get("max_price"),
            "spice_min": parsed.get("spice_min"),
            "district": parsed.get("district"),
            "cuisine": parsed.get("cuisine"),
            "tags": parsed.get("tags") or [],
            "halal_only": bool(parsed.get("halal_only")),
        }
    except json.JSONDecodeError:
        return {"error": "llm_parse_failed"}
    except Exception as e:
        return {"error": f"llm_request_failed: {e}"}
