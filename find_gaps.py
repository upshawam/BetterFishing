#!/usr/bin/env python3
import json
import os

INPUT_JSON = 'posts.json'

def find_missing_data(posts):
    missing_waterbody = []
    missing_species = []
    missing_map_resolution = []
    no_maps_at_all = []

    for post in posts:
        post_id = post.get('post_id', 'N/A')
        title = post.get('title', 'Untitled')
        url = post.get('url', '')
        metadata = post.get('detected_metadata', {})
        
        waterbody = metadata.get('waterbody')
        species = metadata.get('species', [])
        map_links = post.get('map_links', [])
        resolved_locations = post.get('resolved_locations', [])

        # 1. Missing Waterbody
        if not waterbody:
            missing_waterbody.append((post_id, title))

        # 2. Missing Species
        if not species:
            missing_species.append((post_id, title))

        # 3. Has Map Links, but failed to resolve coordinates for at least one
        unresolved_links = [
            loc.get('original_url') 
            for loc in resolved_locations 
            if loc.get('lat') is None or loc.get('lng') is None
        ]
        if unresolved_links:
            missing_map_resolution.append((post_id, title, unresolved_links))

        # 4. No Map Links captured at all
        if not map_links:
            no_maps_at_all.append((post_id, title))

    return {
        "waterbody": missing_waterbody,
        "species": missing_species,
        "unresolved_maps": missing_map_resolution,
        "no_maps": no_maps_at_all
    }


def print_report(gaps, total_posts):
    print("=" * 60)
    print("           DATA GAP ANALYSIS REPORT           ")
    print("=" * 60)
    print(f" Total Posts Analyzed: {total_posts}\n")

    # --- 1. MISSING WATERBODY ---
    print(f"🌊 MISSING WATERBODY ({len(gaps['waterbody'])} posts)")
    print("-" * 60)
    if gaps['waterbody']:
        for pid, title in gaps['waterbody']:
            print(f" • [{pid}] {title}")
    else:
        print(" 🎉 None! All posts have a waterbody assigned.")
    print("\n")

    # --- 2. MISSING SPECIES ---
    print(f"🐟 MISSING SPECIES ({len(gaps['species'])} posts)")
    print("-" * 60)
    if gaps['species']:
        for pid, title in gaps['species']:
            print(f" • [{pid}] {title}")
    else:
        print(" 🎉 None! All posts have species assigned.")
    print("\n")

    # --- 3. UNRESOLVED MAP COORDINATES ---
    print(f"⚠️  HAS MAP LINKS BUT FAILED TO RESOLVE ({len(gaps['unresolved_maps'])} posts)")
    print("-" * 60)
    if gaps['unresolved_maps']:
        for pid, title, links in gaps['unresolved_maps']:
            print(f" • [{pid}] {title}")
            for link in links:
                print(f"      └─ Failed Link: {link}")
    else:
        print(" 🎉 None! Every map link was successfully converted to coordinates.")
    print("\n")

    # --- 4. NO MAP LINKS AT ALL ---
    print(f"🗺️  NO MAP LINKS CAPTURED ({len(gaps['no_maps'])} posts)")
    print("-" * 60)
    if gaps['no_maps']:
        for pid, title in gaps['no_maps']:
            print(f" • [{pid}] {title}")
    else:
        print(" 🎉 None! Every post has at least one map link.")
    print("=" * 60)


if __name__ == '__main__':
    if not os.path.exists(INPUT_JSON):
        print(f"❌ Error: Could not find '{INPUT_JSON}'. Please run archive_historical2.py first.")
    else:
        with open(INPUT_JSON, 'r', encoding='utf-8') as f:
            posts = json.load(f)
        
        gaps = find_missing_data(posts)
        print_report(gaps, len(posts))