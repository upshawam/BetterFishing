import json
import re
from pathlib import Path
import urllib.request
import urllib.error

# --- CONFIGURATION ---
# Change this to any model you have pulled in Ollama (e.g., 'llama3', 'llama3.2', 'mistral', 'gemma2')
OLLAMA_MODEL = "qwen3:8b"
OLLAMA_URL = "http://localhost:11434/api/generate"

def call_ollama(prompt):
    """Sends a prompt directly to the local Ollama HTTP API."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json"  # Enforces structured JSON response from Ollama
    }
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        OLLAMA_URL, 
        data=data, 
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            return json.loads(res_json.get("response", "{}"))
    except urllib.error.URLError:
        print("\n❌ ERROR: Could not connect to Ollama.")
        print("   Make sure Ollama is running in the background (`ollama serve` or open the Ollama app).")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"\n⚠️ Warning: Model response was not valid JSON: {e}")
        return {"waterbodies": [], "species": [], "access_ramps": []}

def extract_text(post_obj):
    """Helper to pull full raw text from post dictionary."""
    combined = []
    if isinstance(post_obj, dict):
        for k, v in post_obj.items():
            if k == "detected_metadata":
                continue # Skip existing regex output
            if isinstance(v, str):
                combined.append(v)
            elif isinstance(v, (dict, list)):
                combined.append(extract_text(v))
    elif isinstance(post_obj, list):
        for item in post_obj:
            combined.append(extract_text(item))
    return " ".join(combined)

def run_ollama_audit():
    SCRIPT_DIR = Path(__file__).resolve().parent
    input_file = SCRIPT_DIR / "tagged_posts.json"
    diff_report_file = SCRIPT_DIR / "audit_diff_report.json"

    if not input_file.exists():
        print(f"[ERROR] Could not find {input_file.name}. Run tag_posts.py first!")
        return

    with open(input_file, "r", encoding="utf-8") as f:
        posts = json.load(f)

    print("=" * 75)
    print(f"STARTING OLLAMA SEMANTIC AUDIT (Using model: '{OLLAMA_MODEL}')")
    print("=" * 75 + "\n")

    audit_results = []
    discrepancy_count = 0

    prompt_template = """
    You are an expert Middle Tennessee fishing guide and metadata auditor.
    Analyze the following fishing trip report and extract:
    1. Primary waterbodies fished or specifically referenced.
    2. Fish species targetted or caught.
    3. Access ramps, dams, or specific landmarks mentioned.

    Return ONLY a JSON object with this EXACT structure:
    {{
      "waterbodies": ["Waterbody Name"],
      "species": ["Species Name"],
      "access_ramps": ["Ramp Name"]
    }}

    TRIP REPORT TEXT:
    {text}
    """

    for idx, post in enumerate(posts, start=1):
        post_id = post.get("id", post.get("title", f"Post #{idx}"))
        regex_metadata = post.get("detected_metadata", {})
        post_text = extract_text(post)

        print(f"[{idx}/{len(posts)}] Reading context for: {post_id} ...")

        # 1. Get Ollama's semantic tags
        formatted_prompt = prompt_template.format(text=post_text[:3000]) # Cap length if posts are huge
        ollama_metadata = call_ollama(formatted_prompt)

        # Ensure keys exist
        o_waters = set(ollama_metadata.get("waterbodies", []))
        o_species = set(ollama_metadata.get("species", []))
        
        r_waters = set(regex_metadata.get("waterbodies", []))
        r_species = set(regex_metadata.get("species", []))

        # 2. Find what regex missed that Ollama caught
        missed_waters = list(o_waters - r_waters)
        missed_species = list(o_species - r_species)

        has_discrepancy = bool(missed_waters or missed_species)

        print(f"  ├─ Regex Tags : Waters: {list(r_waters)} | Species: {list(r_species)}")
        print(f"  ├─ Ollama Tags: Waters: {list(o_waters)} | Species: {list(o_species)}")

        if has_discrepancy:
            discrepancy_count += 1
            print("  ⚠️  DISCREPANCY DETECTED:")
            if missed_waters:
                print(f"     └─ Waters Regex Missed : {missed_waters}")
            if missed_species:
                print(f"     └─ Species Regex Missed: {missed_species}")
        else:
            print("  ✅ FULL MATCH: Regex captured all context.")

        print("-" * 75)

        audit_results.append({
            "post_id": post_id,
            "regex_tags": regex_metadata,
            "ollama_tags": ollama_metadata,
            "missed_by_regex": {
                "waterbodies": missed_waters,
                "species": missed_species
            },
            "has_discrepancy": has_discrepancy
        })

    # Save summary report
    with open(diff_report_file, "w", encoding="utf-8") as f:
        json.dump(audit_results, f, indent=2)

    print("\n" + "=" * 75)
    print("OLLAMA AUDIT COMPLETE")
    print(f"Total Posts Audited      : {len(posts)}")
    print(f"Discrepancies / Misses   : {discrepancy_count}")
    print(f"Saved Diff Report to     : {diff_report_file.name}")
    print("=" * 75)

if __name__ == "__main__":
    run_ollama_audit()