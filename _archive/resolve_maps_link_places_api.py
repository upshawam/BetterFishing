#!/usr/bin/env python3
"""
Resolve a share.google (Google Maps short link) to lat/lng coordinates
using the official Google Places API.

Two steps:
  1. Follow the share.google redirect with `requests` (a plain HTTP request,
     no page rendering) to recover the place name Google resolved it to
     (e.g. "VFW Boat Ramp"). This step doesn't touch Maps' JS-rendered UI,
     so it doesn't trip Google's bot detection.
  2. Send that name to the official Places API (Text Search), which returns
     real coordinates, a place_id, and a formatted address. This replaces
     any scraping of Maps pages, which Google actively blocks.

Setup:
    pip install requests
    Get an API key from Google Cloud Console with "Places API" enabled:
    https://console.cloud.google.com/apis/library/places-backend.googleapis.com

Usage:
    export GOOGLE_PLACES_API_KEY="your-key-here"
    python resolve_maps_link_places_api.py "https://share.google/MQW19lpSBxzDHNxkQ"

    # or pass the key directly:
    python resolve_maps_link_places_api.py "<link>" --key YOUR_KEY
"""

import argparse
import os
import re
import sys
from urllib.parse import urlparse, parse_qs

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# In case the share link resolves straight to a maps URL with coordinates
# already in it (happens for direct "place" shares) — no API call needed then.
URL_COORD_PATTERNS = [
    r"@(-?\d+\.\d+),(-?\d+\.\d+)",
    r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
]


def _try_extract_coords_from_url(url):
    for pattern in URL_COORD_PATTERNS:
        match = re.search(pattern, url)
        if match:
            lat, lng = match.groups()
            return float(lat), float(lng)
    return None, None


def resolve_place_name(short_url: str):
    """
    Follow the short link and return (place_name, final_url).
    place_name is None if we couldn't find one (and coords may already
    be available directly from the URL — check separately).
    """
    resp = requests.get(short_url, headers=HEADERS, allow_redirects=True, timeout=15)
    final_url = resp.url

    parsed = urlparse(final_url)
    query_params = parse_qs(parsed.query)

    place_name = None
    if "q" in query_params:
        place_name = query_params["q"][0]

    return place_name, final_url


def lookup_coordinates(place_name: str, api_key: str):
    """
    Use the Places API Text Search endpoint to resolve a place name to
    coordinates. Returns the first (best) match as a dict, or None.
    """
    endpoint = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": place_name, "key": api_key}

    resp = requests.get(endpoint, params=params, timeout=15)
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        return None

    top = data["results"][0]
    location = top["geometry"]["location"]
    return {
        "name": top.get("name"),
        "address": top.get("formatted_address"),
        "lat": location["lat"],
        "lng": location["lng"],
        "place_id": top.get("place_id"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="share.google link")
    parser.add_argument("--key", help="Google Places API key "
                         "(defaults to GOOGLE_PLACES_API_KEY env var)")
    args = parser.parse_args()

    short_url = args.url or input("Enter share.google link: ").strip()
    api_key = args.key or os.environ.get("GOOGLE_PLACES_API_KEY")

    if not api_key:
        print("No API key found. Pass --key YOUR_KEY or set "
              "GOOGLE_PLACES_API_KEY.", file=sys.stderr)
        sys.exit(1)

    place_name, final_url = resolve_place_name(short_url)
    print(f"Resolved to: {final_url}")

    # Some share links resolve straight to a maps URL with coordinates
    # already baked in — no API call needed in that case.
    lat, lng = _try_extract_coords_from_url(final_url)
    if lat is not None:
        print(f"Coordinates (from URL): {lat}, {lng}")
        return

    if not place_name:
        print("Couldn't find a place name in the resolved URL either.")
        sys.exit(1)

    print(f"Place name: {place_name}")

    result = lookup_coordinates(place_name, api_key)
    if result is None:
        print(f"Places API found no match for '{place_name}'.")
        sys.exit(1)

    print(f"Matched: {result['name']} — {result['address']}")
    print(f"Coordinates: {result['lat']}, {result['lng']}")
    print(f"Google Maps: https://www.google.com/maps?q={result['lat']},{result['lng']}")


if __name__ == "__main__":
    main()