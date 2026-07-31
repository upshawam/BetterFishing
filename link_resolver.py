import json
import os
import re
from urllib.parse import urlparse, parse_qs
import requests

CACHE_FILE = 'resolved_coords_cache.json'
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
URL_COORD_PATTERNS = [
    r"@(-?\d+\.\d+),(-?\d+\.\d+)",
    r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
]


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_cache(cache):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _try_extract_coords_from_url(url):
    for pattern in URL_COORD_PATTERNS:
        match = re.search(pattern, url)
        if match:
            lat, lng = match.groups()
            return float(lat), float(lng)
    return None, None


def resolve_link(short_url: str, api_key: str, cache: dict) -> dict:
    """
    Resolves a shared map link using cache -> URL regex -> Places API (Text Search).
    """
    # 1. Check local cache first (Free & Instant)
    if short_url in cache:
        return cache[short_url]

    result_data = {
        "original_url": short_url,
        "resolved_url": short_url,
        "place_name": None,
        "address": None,
        "lat": None,
        "lng": None,
        "source": "failed"
    }

    try:
        # Follow redirect to get final destination URL
        resp = requests.get(short_url, headers=HEADERS, allow_redirects=True, timeout=10)
        final_url = resp.url
        result_data["resolved_url"] = final_url

        # Check if coordinates are embedded directly in the expanded URL
        lat, lng = _try_extract_coords_from_url(final_url)
        if lat is not None:
            result_data["lat"] = lat
            result_data["lng"] = lng
            result_data["source"] = "url_extract"
            cache[short_url] = result_data
            save_cache(cache)
            return result_data

        # Extract place name from query parameters
        parsed = urlparse(final_url)
        query_params = parse_qs(parsed.query)
        place_name = query_params.get("q", [None])[0]

        if not place_name or not api_key:
            cache[short_url] = result_data
            save_cache(cache)
            return result_data

        result_data["place_name"] = place_name

        # Append region bias if not specified to target local Tennessee waters/ramps
        search_query = place_name if any(term in place_name.upper() for term in ["TN", "TENNESSEE"]) else f"{place_name}, TN"

        # Places API Text Search call ($0.032 per request)
        endpoint = "https://maps.googleapis.com/maps/api/place/textsearch/json"
        api_resp = requests.get(endpoint, params={"query": search_query, "key": api_key}, timeout=10)
        api_data = api_resp.json()

        if api_data.get("status") in ["OVER_QUERY_LIMIT", "REQUEST_DENIED"]:
            print(f"⚠️ Google Cloud Limit/Denial: {api_data.get('error_message', 'Quota reached')}")
            return result_data

        if api_data.get("status") == "OK" and api_data.get("results"):
            top = api_data["results"][0]
            loc = top["geometry"]["location"]
            result_data["place_name"] = top.get("name", place_name)
            result_data["address"] = top.get("formatted_address")
            result_data["lat"] = loc["lat"]
            result_data["lng"] = loc["lng"]
            result_data["source"] = "places_api"

    except Exception as e:
        print(f"⚠️ Error resolving {short_url}: {e}")

    cache[short_url] = result_data
    save_cache(cache)
    return result_data