import json
import re
import urllib.parse
from pathlib import Path
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

geolocator = Nominatim(user_agent="tn_fishing_map_extractor_v3")
session = requests.Session()

def unshorten_share_link(short_url):
    """Tracks the real redirect target of share.google links."""
    try:
        # Use allow_redirects=False to catch the raw 301/302 Location header before CAPTCHA
        res = session.get(short_url, headers=HEADERS, allow_redirects=False, timeout=6)
        if res.status_code in (301, 302, 303, 307, 308) and 'Location' in res.headers:
            redirect_url = res.headers['Location']
            # Follow one more step if it goes to another redirect
            if "share.google" in redirect_url or "maps.app.goo.gl" in redirect_url:
                res2 = session.get(redirect_url, headers=HEADERS, allow_redirects=False, timeout=6)
                if 'Location' in res2.headers:
                    return res2.headers['Location']
            return redirect_url
    except Exception:
        pass
    return short_url

def extract_place_from_text_context(post_text, target_url):
    """Extracts place names sitting directly next to or above the URL in the post content."""
    if not post_text:
        return None
        
    lines = post_text.split('\n')
    for idx, line in enumerate(lines):
        if target_url in line:
            # 1. Check same line before URL
            before_url = line.split(target_url)[0].strip()
            clean_before = re.sub(r'[\.\-\:\,]+$', '', before_url).strip()
            if len(clean_before) > 3 and not clean_before.startswith("http"):
                return clean_before
            
            # 2. Check previous line if same line had no useful name
            if idx > 0:
                prev_line = lines[idx-1].strip()
                clean_prev = re.sub(r'[\.\-\:\,]+$', '', prev_line).strip()
                if len(clean_prev) > 3 and not clean_prev.startswith("http"):
                    parts = re.split(r'[\.\,\!\?]', clean_prev)
                    return parts[-1].strip() if parts[-1].strip() else clean_prev
                    
    return None

def resolve_coords(original_url, post_text=""):
    """Resolves coordinates via URL redirect, regex pattern, context text extraction, or Geocoding."""
    # 1. Resolve raw redirect URL
    expanded = unshorten_share_link(original_url)

    # 2. Direct Lat/Lng regex on expanded URL
    match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', expanded)
    if match:
        return float(match.group(1)), float(match.group(2)), "Direct URL (@lat,lng)", expanded

    match = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', expanded)
    if match:
        return float(match.group(1)), float(match.group(2)), "Direct URL (!3d!4d)", expanded

    # 3. Extract place parameter from URL (q=)
    parsed = urllib.parse.urlparse(expanded)
    params = urllib.parse.parse_qs(parsed.query)
    place_name = params.get('q', [None])[0]

    # 4. Fallback: Context Extraction from Post Text
    if not place_name or place_name.startswith("http"):
        place_name = extract_place_from_text_context(post_text, original_url)

    # 5. Geocode Place Name
    if place_name:
        clean_place = re.sub(r'(?i)^(at|ending at|starting at|near)\s+', '', place_name)
        try:
            search_query = f"{clean_place}, Tennessee, USA"
            location = geolocator.geocode(search_query, timeout=5)
            if location:
                return location.latitude, location.longitude, f"Geocoded Context: {clean_place}", expanded
        except (GeocoderTimedOut, GeocoderServiceError):
            pass

    return None, None, "Unresolved", expanded

def process_map_links():
    SCRIPT_DIR = Path(__file__).resolve().parent
    input_file = SCRIPT_DIR / "posts.json"
    output_file = SCRIPT_DIR / "posts_with_pins.json"

    if not input_file.exists():
        print(f"[ERROR] Could not find {input_file.name}")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        posts = json.load(f)

    print("=" * 70)
    print("STARTING REDIRECT & CONTEXTUAL PIN EXTRACTION")
    print("=" * 70 + "\n")

    total_pins = 0

    for idx, post in enumerate(posts, start=1):
        post_id = post.get("id", post.get("title", f"Post #{idx}"))
        map_links = post.get("map_links", [])
        post_text = post.get("content_raw", "") or post.get("content_markdown", "")

        if not map_links:
            post["explicit_pins"] = []
            continue

        print(f"[{idx}/{len(posts)}] Processing: {post_id} ({len(map_links)} links)")

        resolved_pins = []
        for link_idx, url in enumerate(map_links, start=1):
            lat, lng, method, expanded = resolve_coords(url, post_text)

            if lat and lng:
                pin_data = {
                    "pin_id": f"{post_id}_pin_{link_idx}",
                    "original_url": url,
                    "expanded_url": expanded,
                    "lat": lat,
                    "lng": lng,
                    "method": method
                }
                resolved_pins.append(pin_data)
                total_pins += 1
                print(f"  ├─ Pin #{link_idx}: ✅ ({lat:.4f}, {lng:.4f}) [{method}]")
            else:
                print(f"  ├─ Pin #{link_idx}: ❌ Could not resolve | {url}")

        post["explicit_pins"] = resolved_pins
        print("-" * 70)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2)

    print("\n" + "=" * 70)
    print("MAP PIN RESOLUTION COMPLETE")
    print(f"Total Posts Processed  : {len(posts)}")
    print(f"Total Resolved Map Pins: {total_pins}")
    print(f"Saved results to       : {output_file.name}")
    print("=" * 70)

if __name__ == "__main__":
    process_map_links()