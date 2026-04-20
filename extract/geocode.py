#!/usr/bin/env python3
"""
Geocode every case in data/cases.json via OpenStreetMap's Nominatim.

- 1 req/sec rate limit (Nominatim ToS).
- Responses cached to data/geocache.json so re-runs are free and the
  script is fully resumable after Ctrl-C.
- For each case, we try the cleaned location string first; if that fails,
  we strip the parenthetical (e.g. "Copiago (Chile)" -> "Copiago").
- Precision is classified from Nominatim's `addresstype`.

Usage:
    python extract/geocode.py                 # geocode everything missing
    python extract/geocode.py --limit 30      # first 30 uncached cases only
    python extract/geocode.py --force         # re-query even cached entries
"""

import argparse
import json
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(__file__)
CASES_PATH = os.path.join(HERE, "..", "data", "cases.json")
CACHE_PATH = os.path.join(HERE, "..", "data", "geocache.json")

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "fabrice-ufo-dataset/0.1 (https://github.com/kirk-iliev/fabrice)"
RATE_LIMIT_SEC = 1.1  # be polite, Nominatim asks for 1 req/sec max

PRECISION_MAP = {
    # exact
    "house": "exact", "building": "exact", "amenity": "exact", "leisure": "exact",
    "shop": "exact", "tourism": "exact", "historic": "exact", "railway": "exact",
    # city-ish
    "city": "city", "town": "city", "village": "city", "hamlet": "city",
    "suburb": "city", "neighbourhood": "city", "locality": "city", "municipality": "city",
    "postcode": "city", "quarter": "city", "isolated_dwelling": "city",
    # region-ish
    "state": "region", "county": "region", "region": "region", "province": "region",
    "state_district": "region", "district": "region", "island": "region",
    # broad
    "country": "vague", "continent": "vague", "sea": "vague", "ocean": "vague",
    "waterway": "vague", "natural": "vague",
}

# Only skip cases where there's no geographic anchor at all. Strings like
# "France, exact location unknown" still have a country -- the candidate
# generator strips the "location unknown" clause and queries "France".
UNGEOCODABLE_PATTERNS = [
    r"^unknown$", r"^at sea$", r"^in the sky", r"^sky over",
]


def is_ungeocodable(s: str) -> bool:
    low = s.lower().strip()
    if not low:
        return True
    return any(re.search(p, low) for p in UNGEOCODABLE_PATTERNS)


def query_candidates(location: str):
    """Generate successively broader queries to try."""
    s = (location or "").strip()
    if not s:
        return []

    candidates = [s]

    # Wonders style: "China: Feathered guests from the sky" -- strip title
    if ":" in s:
        before_colon = s.split(":", 1)[0].strip()
        if before_colon:
            candidates.append(before_colon)
            s_for_further = before_colon  # use this for further cleaning below
        else:
            s_for_further = s
    else:
        s_for_further = s

    # "France, exact location unknown"  ->  "France"
    cleaned = re.sub(
        r",?\s*(exact\s+)?location\s+unknown.*$", "", s_for_further, flags=re.I
    ).strip().rstrip(",")
    if cleaned and cleaned != s_for_further:
        candidates.append(cleaned)
        s_for_further = cleaned

    # Passport style: "Copiago (Chile)"  ->  "Copiago, Chile"
    m = re.match(r"^(.+?)\s*\(([^)]+)\)\s*$", s_for_further)
    if m:
        head, paren = m.group(1).strip(), m.group(2).strip()
        candidates.append(f"{head}, {paren}")
        candidates.append(head)
        candidates.append(paren)

    # Drop prefixes like "Near ", "At "
    stripped = re.sub(r"^(near|at|over|above|in)\s+", "", s_for_further, flags=re.I)
    if stripped != s_for_further:
        candidates.append(stripped)

    # Comma-segment fallbacks. For "Amiterno, 70 Roman miles NE of Rome, Italy"
    # the first ("Amiterno") and last ("Italy") are both useful anchors.
    parts = [p.strip() for p in s_for_further.split(",") if p.strip()]
    if len(parts) >= 2:
        candidates.append(parts[0])
        candidates.append(parts[-1])
        candidates.append(f"{parts[0]}, {parts[-1]}")

    # Title mashed into location without punctuation, e.g.
    # "Trans-Rhenan Germany: Iron Globes" -> colon strip handled above,
    # but "Targoviste, Wallachia, Romania Hovering object" has no colon.
    # Last word of last part is often a country.
    if parts:
        last_tokens = parts[-1].split()
        if len(last_tokens) >= 2:
            candidates.append(last_tokens[-1])            # "object" (bad)
            candidates.append(" ".join(last_tokens[:-1])) # "Romania Hovering" (still noisy)
            # If first word of last part is capitalized (likely the real place),
            # try just that: "Romania Hovering" -> "Romania"
            candidates.append(last_tokens[0])

    seen = set()
    out = []
    for c in candidates:
        if c and c not in seen and len(c) > 1:
            seen.add(c)
            out.append(c)
    return out


def nominatim_search(query: str):
    params = {"q": query, "format": "json", "limit": "1", "addressdetails": "1"}
    url = NOMINATIM_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data[0] if data else None


def classify_precision(hit: dict) -> str:
    atype = hit.get("addresstype") or hit.get("type") or ""
    return PRECISION_MAP.get(atype.lower(), "vague")


def geocode_one(location: str, cache: dict) -> dict | None:
    """Return cached or freshly-fetched hit dict, or None."""
    if is_ungeocodable(location):
        return None

    queries = query_candidates(location)
    for q in queries:
        if q in cache:
            entry = cache[q]
            if entry is not None:
                return entry
            continue  # cached miss, try next candidate

        time.sleep(RATE_LIMIT_SEC)
        try:
            hit = nominatim_search(q)
        except Exception as e:
            print(f"  ! error on {q!r}: {e}")
            hit = None

        if hit:
            compact = {
                "lat": float(hit["lat"]),
                "lon": float(hit["lon"]),
                "precision": classify_precision(hit),
                "matched_query": q,
                "display_name": hit.get("display_name", ""),
            }
            cache[q] = compact
            save_cache(cache)
            return compact
        else:
            cache[q] = None
            save_cache(cache)

    return None


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Cap on cases to process")
    ap.add_argument("--force", action="store_true", help="Re-query even cases with lat already set")
    args = ap.parse_args()

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    cache = load_cache()

    targets = [c for c in cases if args.force or c.get("lat") is None]
    if args.limit:
        targets = targets[: args.limit]

    print(f"Geocoding {len(targets)} / {len(cases)} cases (cache entries: {len(cache)})")

    hits = misses = ungeo = 0
    for i, c in enumerate(targets, 1):
        loc = c.get("location") or ""
        if is_ungeocodable(loc):
            ungeo += 1
            continue

        result = geocode_one(loc, cache)
        if result:
            c["lat"] = result["lat"]
            c["lon"] = result["lon"]
            c["location_precision"] = result["precision"]
            hits += 1
        else:
            misses += 1

        if i % 25 == 0:
            print(f"  [{i}/{len(targets)}] hits={hits} misses={misses} ungeo={ungeo}")
            # Periodic persistence so a crash doesn't lose progress
            with open(CASES_PATH, "w", encoding="utf-8") as f:
                json.dump(cases, f, indent=2, ensure_ascii=False)

    with open(CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)

    total = len(cases)
    resolved = sum(1 for c in cases if c.get("lat") is not None)
    print()
    print(f"Session: hits={hits} misses={misses} ungeocodable={ungeo}")
    print(f"Overall: {resolved}/{total} cases have coordinates "
          f"({100*resolved/total:.1f}%)")


if __name__ == "__main__":
    main()
