import json
import re
import time
from pathlib import Path

# --- 1. EXPANDED CANONICAL DICTIONARIES ---
WATERBODY_MAP = {
    # Caney Fork & Tributaries
    "caney fork": "Caney Fork River",
    "caney": "Caney Fork River",
    "smith fork": "Smith Fork Creek",
    "collins river": "Collins River",
    "barren fork": "Barren Fork River",
    
    # Stones River & Priest
    "stones river": "Stones River",
    "west fork stones": "West Fork Stones River",
    "west fork": "West Fork Stones River",
    "percy priest": "Percy Priest Lake",
    "priest": "Percy Priest Lake",
    "priest lake": "Percy Priest Lake",
    
    # Upper Cumberland / Center Hill / Old Hickory
    "center hill": "Center Hill Lake",
    "center hill lake": "Center Hill Lake",
    "old hickory": "Old Hickory Lake",
    "old hickory lake": "Old Hickory Lake",
    "cordell hull": "Cordell Hull Lake",
    
    # Other Middle TN Waters
    "buffalo river": "Buffalo River",
    "woods reservoir": "Woods Reservoir",
    "piney river": "Piney River",
    "duck river": "Duck River",
    "harpeth": "Harpeth River",
    "harpeth river": "Harpeth River",
    "cumberland river": "Cumberland River",
    "cumberland": "Cumberland River",
    "obey river": "Obey River",
    "dale hollow": "Dale Hollow Lake",
    "rock island": "Rock Island State Park"
}

SPECIES_MAP = {
    "rainbow trout": "Trout (Rainbow)",
    "brown trout": "Trout (Brown)",
    "trout": "Trout",
    "smallmouth": "Smallmouth Bass",
    "smallmouth bass": "Smallmouth Bass",
    "smallie": "Smallmouth Bass",
    "largemouth": "Largemouth Bass",
    "largemouth bass": "Largemouth Bass",
    "bass": "Bass",
    "striped bass": "Striped Bass",
    "striper": "Striped Bass",
    "stripers": "Striped Bass",
    "hybrid": "Hybrid Bass",
    "hybrid bass": "Hybrid Bass",
    "hybrids": "Hybrid Bass",
    "walleye": "Walleye",
    "crappie": "Crappie",
    "muskie": "Muskie",
    "musky": "Muskie",
    "bluegill": "Bluegill",
    "rock bass": "Rock Bass",
    "goggle eye": "Rock Bass",
    "catfish": "Catfish",
    "gar": "Gar",
    "carp": "Carp",
    "drum": "Drum"
}

ACCESS_RAMPS_KEYWORDS = [
    "Betty's Island", "Bettys Island", "Kirby Road", "Stone Wall", "Stonewall",
    "Buffalo Valley", "Long Branch", "Rocket Park", "VFW", "VFW Boat Ramp", 
    "Jefferson Springs", "The Steps", "Seven Points", "Pinewood", "Thompson Lane", 
    "Nice Mill", "Cookeville Boat Dock", "Sligo", "Ragland Bottoms", "Great Falls",
    "Gallatin Marina"
]

def extract_all_text_from_post(post_obj):
    """Recursively combines all text/string values from the post object."""
    combined_text = []
    if isinstance(post_obj, dict):
        for key, val in post_obj.items():
            if isinstance(val, str):
                combined_text.append(val)
            elif isinstance(val, (dict, list)):
                combined_text.append(extract_all_text_from_post(val))
    elif isinstance(post_obj, list):
        for item in post_obj:
            combined_text.append(extract_all_text_from_post(item))
    return " ".join(combined_text)

def extract_and_standardize(text):
    text_lower = text.lower()
    
    # Extract Waterbodies
    waterbodies = set()
    for kw, canonical in WATERBODY_MAP.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
            waterbodies.add(canonical)

    # Extract Species
    species = set()
    for kw, canonical in SPECIES_MAP.items():
        if re.search(r'\b' + re.escape(kw) + r'\b', text_lower):
            species.add(canonical)

    # Extract Access Ramps
    ramps = set()
    for ramp in ACCESS_RAMPS_KEYWORDS:
        if re.search(r'\b' + re.escape(ramp.lower()) + r'\b', text_lower):
            ramps.add(ramp)

    return {
        "waterbodies": list(waterbodies),
        "species": list(species),
        "access_ramps": list(ramps)
    }

def run_tagging_test():
    SCRIPT_DIR = Path(__file__).resolve().parent
    input_file = SCRIPT_DIR / "posts.json"
    output_file = SCRIPT_DIR / "tagged_posts.json"

    print("=" * 70)
    print("STARTING ROBUST TAGGING TEST RUN")
    print("=" * 70 + "\n")

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            posts = json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Could not find 'posts.json' at {input_file}")
        return

    print(f"Loaded {len(posts)} posts from {input_file.name}\n")
    
    # Debug: Print sample post key structure
    if len(posts) > 0:
        print(f"Sample Post Keys: {list(posts[0].keys())}\n" + "-" * 70)

    processed_posts = []
    total_posts = len(posts)
    passed_count = 0
    flagged_count = 0

    for idx, post in enumerate(posts, start=1):
        post_id = post.get("id", post.get("title", f"Post #{idx}"))
        
        # Extract ALL string data across the post JSON object
        full_post_text = extract_all_text_from_post(post)

        # Extraction
        tags = extract_and_standardize(full_post_text)
        post["detected_metadata"] = tags

        print(f"[{idx}/{total_posts}] Processing: {post_id}")
        print(f"  ├─ Extracted Character Length: {len(full_post_text)}")
        print(f"  ├─ Waterbodies : {tags['waterbodies'] if tags['waterbodies'] else '❌ NONE DETECTED'}")
        print(f"  ├─ Species     : {tags['species'] if tags['species'] else '❌ NONE DETECTED'}")
        print(f"  └─ Access/Ramps: {tags['access_ramps']}")

        # Validation logic
        if not tags["waterbodies"] or not tags["species"]:
            print("  ⚠️  [STATUS]: FLAGGED - Missing required primary tags!")
            flagged_count += 1
        else:
            print("  ✅ [STATUS]: PASSED - Fully tagged.")
            passed_count += 1

        print("-" * 70)
        processed_posts.append(post)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(processed_posts, f, indent=2)

    print("\n" + "=" * 70)
    print("TEST RUN COMPLETE")
    print(f"Total Processed     : {total_posts}")
    print(f"Successfully Tagged : {passed_count}")
    print(f"Flagged for Review : {flagged_count}")
    print(f"Saved results to    : {output_file.name}")
    print("=" * 70)

if __name__ == "__main__":
    run_tagging_test()