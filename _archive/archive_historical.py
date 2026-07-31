import os
import re
import json
import time
import random
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.sync_api import sync_playwright

# Configuration
PATREON_URL = "https://www.patreon.com/cw/BetterDaysFishing/posts"
DATA_DIR = Path("data")
ASSETS_DIR = Path("assets/images")
POSTS_JSON_PATH = DATA_DIR / "posts.json"
SESSION_STATE_PATH = "session_state.json"

# Ensure output directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def download_image(url, save_path):
    """Downloads an image from a URL to a local file path."""
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(response.content)
            return True
    except Exception as e:
        print(f"   [!] Failed to download image {url}: {e}")
    return False


def extract_map_links(text, html_soup):
    """Extracts raw Google Maps, short links, or share links from text and hrefs."""
    links = set()
    
    # Check all anchor tags
    for a in html_soup.find_all('a', href=True):
        href = a['href']
        if any(domain in href for domain in ['maps.google.com', 'maps.app.goo.gl', 'share.google', 'goo.gl/maps']):
            links.add(href)
            
    # Regex fallback for plain text map URLs
    map_regex = r'(https?://(?:maps\.app\.goo\.gl|share\.google|maps\.google\.com)[^\s"]+)'
    found_in_text = re.findall(map_regex, text)
    for link in found_in_text:
        links.add(link)
        
    return list(links)


def expand_all_content(page):
    """Clicks all 'Show More', 'Read More', or comment expander buttons on the page."""
    print("[-] Expanding collapsed text and comments...")
    
    # Expand post text toggles
    expand_selectors = [
        'button:has-text("Show more")',
        'button:has-text("Read more")',
        'button:has-text("See more")',
        '[data-tag="post-card-expand-button"]'
    ]
    
    for selector in expand_selectors:
        buttons = page.locator(selector).all()
        for btn in buttons:
            try:
                if btn.is_visible():
                    btn.click(timeout=1000)
                    time.sleep(0.3)
            except Exception:
                pass

    # Expand comment threads
    comment_selectors = [
        'button:has-text("View comments")',
        'button:has-text("Show replies")',
        'button:has-text("View more comments")'
    ]
    
    for selector in comment_selectors:
        buttons = page.locator(selector).all()
        for btn in buttons:
            try:
                if btn.is_visible():
                    btn.click(timeout=1000)
                    time.sleep(0.3)
            except Exception:
                pass


def load_all_posts(page):
    """Scrolls down and repeatedly clicks 'Load More' until all posts are loaded."""
    print("[-] Loading feed and scrolling for historical posts...")
    previous_height = 0
    no_change_count = 0
    
    while True:
        # Scroll to bottom
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(random.uniform(2.0, 3.5))
        
        # Check for 'Load More' or 'Show More' feed buttons
        load_more = page.locator('button:has-text("Load more"), button:has-text("Show more posts")')
        if load_more.count() > 0 and load_more.first.is_visible():
            try:
                load_more.first.click()
                print("   [+] Clicked 'Load More' button...")
                time.sleep(random.uniform(2.0, 4.0))
            except Exception:
                pass
                
        # Detect height changes to break loop when all content is loaded
        current_height = page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            no_change_count += 1
            if no_change_count >= 3:  # End of page reached
                print("[+] Reached end of Patreon feed.")
                break
        else:
            no_change_count = 0
            previous_height = current_height


def parse_posts(page_html):
    """Parses full DOM HTML using BeautifulSoup into structured JSON format."""
    soup = BeautifulSoup(page_html, 'html.parser')
    posts_data = []
    
    # Patreon post card containers
    post_cards = soup.find_all('div', {'data-tag': 'post-card'}) or soup.find_all('article')
    
    if not post_cards:
        # Fallback query if Patreon shifts dataset tags
        post_cards = soup.find_all('div', class_=re.compile(r'PostCard|postContainer'))

    print(f"[-] Found {len(post_cards)} posts to process.")

    for idx, card in enumerate(post_cards, start=1):
        try:
            # Post URL and ID
            title_elem = card.find('a', {'data-tag': 'post-title'}) or card.find('h1') or card.find('h2')
            post_url = title_elem['href'] if title_elem and title_elem.has_attr('href') else ""
            if post_url and not post_url.startswith("http"):
                post_url = f"https://www.patreon.com{post_url}"
                
            post_id_match = re.search(r'/posts/(?:[a-zA-Z0-9-]+-)?(\d+)', post_url)
            post_id = post_id_match.group(1) if post_id_match else f"post_{idx}"

            # Title
            title = title_elem.get_text(strip=True) if title_elem else f"Trip Report #{idx}"

            # Published Date
            date_elem = card.find('time') or card.find('a', {'data-tag': 'post-published-at'})
            published_date = date_elem['datetime'] if date_elem and date_elem.has_attr('datetime') else ""
            if not published_date and date_elem:
                published_date = date_elem.get_text(strip=True)

            # Content
            content_div = card.find('div', {'data-tag': 'post-content'}) or card
            content_raw = content_div.get_text(separator="\n", strip=True)
            content_markdown = md(str(content_div))

            # Map Links
            map_links = extract_map_links(content_raw, content_div)

            # Images
            image_paths = []
            img_tags = card.find_all('img')
            img_count = 1
            for img in img_tags:
                src = img.get('src', '')
                # Filter out profile photos or tiny icons
                if src and 'patreonusercontent.com' in src and not any(x in src for x in ['user_avatar', 'profile']):
                    img_filename = f"image_{img_count}.jpg"
                    local_path = ASSETS_DIR / post_id / img_filename
                    if download_image(src, local_path):
                        image_paths.append(str(local_path).replace("\\", "/"))
                        img_count += 1

            # Comments
            comments = []
            comment_threads = card.find_all('div', {'data-tag': 'comment-row'}) or card.find_all('div', class_=re.compile(r'comment'))
            for c in comment_threads:
                author_elem = c.find('a', class_=re.compile(r'author|user')) or c.find('span')
                text_elem = c.find('div', class_=re.compile(r'body|text')) or c
                
                author = author_elem.get_text(strip=True) if author_elem else "Anonymous"
                comment_text = text_elem.get_text(strip=True) if text_elem else ""
                
                if comment_text and author != title:
                    comments.append({
                        "author": author,
                        "text": comment_text,
                        "date": ""
                    })

            # ISO Month tag
            month_match = re.search(r'\d{4}-(\d{2})-\d{2}', published_date)
            month_str = month_match.group(1) if month_match else ""

            post_object = {
                "post_id": post_id,
                "title": title,
                "published_date": published_date,
                "url": post_url,
                "content_raw": content_raw,
                "content_markdown": content_markdown,
                "images": image_paths,
                "map_links": map_links,
                "comments": comments,
                "detected_metadata": {
                    "waterbody": None,
                    "species": [],
                    "month": month_str
                }
            }

            posts_data.append(post_object)
            print(f"[{idx}/{len(post_cards)}] Processed: '{title}' ({len(image_paths)} images, {len(map_links)} maps)")

        except Exception as e:
            print(f"[!] Error processing post #{idx}: {e}")

    return posts_data


def main():
    with sync_playwright() as p:
        # Launch real installed Google Chrome with automation bypass flags
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--start-maximized"
            ]
        )
        
        # Load session state if it exists
        if os.path.exists(SESSION_STATE_PATH):
            context = browser.new_context(storage_state=SESSION_STATE_PATH)
            print("[-] Loaded existing browser session state.")
        else:
            context = browser.new_context()

        page = context.new_page()
        page.goto(PATREON_URL)

        # Interactive Auth Prompt
        print("\n=======================================================")
        print("ACTION REQUIRED:")
        print("1. Log into your Patreon account in the opened Chrome window.")
        print("2. Ensure you have access to the subscriber feed.")
        print("3. Return here and press ENTER to start the scraper.")
        print("=======================================================\n")
        input("Press ENTER after logging in...")

        # Save session cookies for future reuse
        context.storage_state(path=SESSION_STATE_PATH)
        print("[-] Saved session state to session_state.json")

        # Scroll feed to bottom
        load_all_posts(page)

        # Expand text & comments
        expand_all_content(page)

        # Capture complete page HTML
        print("[-] Extracting DOM content...")
        full_html = page.content()

        # Parse posts
        posts = parse_posts(full_html)

        # Save JSON output
        with open(POSTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(posts, f, indent=2, ensure_ascii=False)

        print(f"\n[✔] SUCCESS: Archived {len(posts)} posts into '{POSTS_JSON_PATH}'")
        browser.close()


if __name__ == "__main__":
    main()