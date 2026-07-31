#!/usrIdentifier/bin/env python3
import json
import os
import re
from bs4 import BeautifulSoup

# Import the link resolution helper module
from link_resolver import load_cache, resolve_link

HTML_FILE_PATH = 'patreon_archive.html' 
OUTPUT_JSON = 'posts.json'

# Let it pull from the terminal environment variable or set your key here
API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")

# --- REGIONAL LOOKUPS ---
KNOWN_WATERBODIES = {
    "Caney Fork River": [r"\bcaney fork\b", r"\bcaney\b"],
    "Center Hill Lake": [r"\bcenter hill\b"],
    "Old Hickory Lake": [r"\bold hickory\b"],
    "Percy Priest Lake": [r"\bpercy priest\b", r"\bpriest\b"],
    "Cumberland River": [r"\bcumberland river\b", r"\bcumberland\b"],
    "Duck River": [r"\bduck river\b"],
    "Harpeth River": [r"\bharpeth\b"],
    "Stones River": [r"\bstones river\b"],
    "Dale Hollow Lake": [r"\bdale hollow\b"],
    "Cordell Hull Lake": [r"\bcordell hull\b"],
    "Rock Island State Park": [r"\brock island\b"],
    "Collins River": [r"\bcollins river\b"],
    "Barren Fork River": [r"\bbarren fork\b"]
}

KNOWN_SPECIES = {
    "Brown Trout": [r"\bbrown trout\b", r"\bbrowns\b"],
    "Rainbow Trout": [r"\brainbow trout\b", r"\brainbows\b"],
    "Trout": [r"\btrout\b"],
    "Largemouth Bass": [r"\blargemouth\b", r"\blargemouth bass\b"],
    "Smallmouth Bass": [r"\bsmallmouth\b", r"\bsmallies\b", r"\bsmallie\b", r"\bbronzeback\b"],
    "Striped Bass / Striper": [r"\bstriped bass\b", r"\bstriper\b", r"\bstripers\b", r"\bhybrid bass\b"],
    "Walleye": [r"\bwalleye\b", r"\bwalleyes\b"],
    "Rock Bass": [r"\brock bass\b", r"\bgoggle eye\b", r"\bgoggle-eye\b"],
    "Musky": [r"\bmusky\b", r"\bmuskellunge\b"],
    "Crappie": [r"\bcrappie\b", r"\bslabs\b"],
    "Bluegill / Sunfish": [r"\bbluegill\b", r"\bsunfish\b", r"\bpanfish\b"]
}


def extract_metadata(text):
    text_lower = text.lower()
    
    # Detect Waterbody
    detected_waterbody = None
    for official_name, patterns in KNOWN_WATERBODIES.items():
        if any(re.search(pat, text_lower) for pat in patterns):
            detected_waterbody = official_name
            break

    # Detect Species
    detected_species = set()
    for official_species, patterns in KNOWN_SPECIES.items():
        if any(re.search(pat, text_lower) for pat in patterns):
            detected_species.add(official_species)
            
    if "Brown Trout" in detected_species or "Rainbow Trout" in detected_species:
        detected_species.discard("Trout")

    return detected_waterbody, sorted(list(detected_species))


def get_local_images(post_id):
    """Checks assets/images/post_X folder for existing images."""
    possible_paths = [
        os.path.join('assets', 'images', post_id),
        os.path.join('public', 'assets', 'images', post_id)
    ]
    
    found_images = []
    for path in possible_paths:
        if os.path.exists(path):
            files = sorted(os.listdir(path))
            for f in files:
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    clean_path = os.path.join('assets', 'images', post_id, f).replace('\\', '/')
                    found_images.append(clean_path)
            if found_images:
                break
                
    return found_images


def parse_patreon_archive(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    post_cards = soup.find_all('div', attrs={'data-tag': 'post-card'})
    posts = []
    
    for idx, card in enumerate(post_cards):
        post_id = f"post_{idx + 1}"
        
        # 1. Extract Title & URL
        title_tag = card.find(attrs={'data-tag': 'post-title'})
        is_fallback_title = False
        if title_tag and title_tag.find('a'):
            title = title_tag.find('a').get_text(strip=True)
            post_url = title_tag.find('a').get('href', '')
        elif title_tag:
            title = title_tag.get_text(strip=True)
            post_url = ""
        else:
            title = f"Trip Report #{idx + 1}"
            post_url = ""
            is_fallback_title = True

        # 2. Extract Date & Month
        date_tag = card.find(attrs={'data-tag': 'post-published-at'})
        published_date = date_tag.get_text(strip=True) if date_tag else ""
        
        time_tag = card.find('time')
        if time_tag and time_tag.get('datetime'):
            published_date = time_tag['datetime']
            
        month_match = re.search(r'-(\d{2})-', published_date)
        month_str = month_match.group(1) if month_match else ""

        # 3. Extract Raw Body Content
        content_container = card.find('div', class_='patreon-post-content')
        content_raw = ""
        content_markdown = ""
        
        if content_container:
            paragraphs = [p.get_text(strip=True) for p in content_container.find_all('p') if p.get_text(strip=True)]
            content_raw = "\n".join(paragraphs)
            content_markdown = "\n\n".join(paragraphs)

        # 4. Extract Map Links (Updated to support maps.app.goo.gl)
        map_links = []
        for link in card.find_all('a', href=True):
            href = link['href']
            if any(k in href for k in ['share.google', 'maps.app.goo.gl', 'maps.google', 'google.com/maps', 'tva.com']):
                map_links.append(href)
        
        # Regex search inside raw text for shortened map links
        raw_google_links = re.findall(
            r'https://(?:share\.google|maps\.app\.goo\.gl)/[A-Za-z0-9_-]+', 
            content_raw
        )
        map_links.extend(raw_google_links)
        map_links = list(set(map_links))

        # 5. Extract Images (HTML search + Local Asset Folder Fallback)
        images = []
        for img in card.find_all('img'):
            src = img.get('src', '')
            if src and 'user' not in src and ('patreon-media' in src or 'assets/images' in src):
                images.append(src)
                
        if not images:
            images = get_local_images(post_id)

        # 6. Extract Comments (Targeting Patreon LineClamp + Profile Links)
        comments = []
        comment_elements = (
            card.find_all(attrs={'data-tag': 'comment-row'}) or 
            card.find_all('div', class_=re.compile(r'comment', re.I))
        )
        
        for c in comment_elements:
            author_tag = (
                c.select_one('span[class*="LineClamp-module__"]') or
                c.find(attrs={'data-tag': 'comment-author'}) or 
                c.find(attrs={'data-tag': 'commenter-name'}) or
                c.find('a', attrs={'data-tag': 'user-profile-link'})
            )
            
            if not author_tag:
                author_tag = (
                    c.find('a', href=re.compile(r'/user|\bprofile\b', re.I)) or 
                    c.find('strong') or 
                    c.find('h4')
                )
            
            author = author_tag.get_text(strip=True) if author_tag else "Anonymous"
            
            body_tag = (
                c.find(attrs={'data-tag': 'comment-body'}) or 
                c.find(attrs={'data-tag': 'comment-text'}) or
                c.find('p')
            )
            
            text = body_tag.get_text(strip=True) if body_tag else c.get_text(strip=True)
            author = re.sub(r'(AUTHOR|CREATOR|\s*·.*)', '', author, flags=re.I).strip()
            
            if text and text != author:
                comments.append({
                    "author": author if author else "Anonymous",
                    "text": text,
                    "date": ""
                })

        # 7. Extract Metadata
        full_text_search = f"{title}\n{content_raw}"
        waterbody, species = extract_metadata(full_text_search)

        post_data = {
            "post_id": post_id,
            "title": title,
            "published_date": published_date,
            "url": post_url,
            "content_raw": content_raw,
            "content_markdown": content_markdown,
            "images": images,
            "map_links": map_links,
            "resolved_locations": [], # Populated by link_resolver
            "comments": comments,
            "detected_metadata": {
                "waterbody": waterbody,
                "species": species,
                "month": month_str
            },
            "_flags": {
                "fallback_title": is_fallback_title
            }
        }
        
        posts.append(post_data)
        
    return posts


def print_scrape_dashboard(posts):
    total = len(posts)
    if total == 0:
        print("❌ No posts found to evaluate.")
        return

    titles_found = sum(1 for p in posts if not p.get('_flags', {}).get('fallback_title', False))
    images_found = sum(1 for p in posts if len(p.get('images', [])) > 0)
    total_images = sum(len(p.get('images', [])) for p in posts)
    maps_found = sum(1 for p in posts if len(p.get('map_links', [])) > 0)
    total_maps = sum(len(p.get('map_links', [])) for p in posts)
    coords_resolved = sum(1 for p in posts if any(loc.get('lat') is not None for loc in p.get('resolved_locations', [])))
    waterbodies_found = sum(1 for p in posts if p.get('detected_metadata', {}).get('waterbody'))
    species_found = sum(1 for p in posts if len(p.get('detected_metadata', {}).get('species', [])) > 0)

    print("\n" + "="*50)
    print("        PATREON SCRAPE SUMMARY DASHBOARD        ")
    print("="*50)
    print(f" Total Posts Scraped : {total}")
    print(f" Real Titles Captured: {titles_found}/{total} ({titles_found/total*100:.1f}%)")
    print(f" Posts with Images   : {images_found}/{total} ({images_found/total*100:.1f}%) | Total Images: {total_images}")
    print(f" Posts with Map Links: {maps_found}/{total} ({maps_found/total*100:.1f}%) | Total Links:  {total_maps}")
    print(f" Locations Resolved  : {coords_resolved}/{maps_found if maps_found else 1} mapped posts")
    print(f" Waterbodies Tagged  : {waterbodies_found}/{total} ({waterbodies_found/total*100:.1f}%)")
    print(f" Species Tagged      : {species_found}/{total} ({species_found/total*100:.1f}%)")
    print("="*50)

    # Misses Reporting
    misses = []
    for p in posts:
        reasons = []
        if p.get('_flags', {}).get('fallback_title', False):
            reasons.append("Missing Real Title")
        if len(p.get('images', [])) == 0:
            reasons.append("No Images")
        if len(p.get('map_links', [])) == 0:
            reasons.append("No Map Links")
        if not p.get('detected_metadata', {}).get('waterbody'):
            reasons.append("Unidentified Waterbody")

        if len(reasons) >= 3:
            misses.append((p.get('post_id', 'N/A'), p.get('title', '')[:40], ", ".join(reasons)))

    if misses:
        print("\n⚠️  POSSIBLE MISSES / LOW DATA POSTS (Top 10):")
        print("-" * 50)
        for pid, title, reason in misses[:10]:
            print(f" • [{pid}] {title:<40} -> {reason}")
        if len(misses) > 10:
            print(f" ... and {len(misses) - 10} more posts with missing attributes.")
    else:
        print("\n Pure clean run! No high-value data gaps detected across posts.")
    print("="*50 + "\n")


if __name__ == '__main__':
    target_file = HTML_FILE_PATH
    if not os.path.exists(target_file):
        html_files = [f for f in os.listdir('.') if f.endswith('.html') or f.endswith('.htm')]
        if html_files:
            target_file = html_files[0]

    if os.path.exists(target_file):
        with open(target_file, 'r', encoding='utf-8') as f:
            raw_html = f.read()
        
        parsed_posts = parse_patreon_archive(raw_html)
        
        # --- RESOLVE MAP LINKS TO COORDINATES ---
        print("\n📍 Resolving Map Links & Coordinates...")
        coord_cache = load_cache()
        
        for p in parsed_posts:
            resolved_locations = []
            for link in p.get("map_links", []):
                resolved = resolve_link(link, API_KEY, coord_cache)
                resolved_locations.append(resolved)
            
            p["resolved_locations"] = resolved_locations
        
        # 1. Print dashboard summary while _flags exist
        print_scrape_dashboard(parsed_posts)

        # 2. Strip temporary _flags before saving final JSON
        for p in parsed_posts:
            p.pop('_flags', None)
            
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(parsed_posts, f, indent=2, ensure_ascii=False)
            
        print(f"✅ Successfully exported structured posts & resolved locations to {OUTPUT_JSON}")
            
    else:
        print(f"Error: Could not find any HTML file in '{os.getcwd()}'.")