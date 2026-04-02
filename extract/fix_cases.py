#!/usr/bin/env python3
"""
Post-process cases.json to fix OCR errors and duplicates, then regenerate markdown.

Known issues:
1. Exact-duplicate pages in OCR output (cases 374-384, 922-923 appear twice)
2. Case number leading digits dropped by OCR:
   - 93  (1954 date) → 193    93  (1952 date) = real
   - 94  (1954 date) → 194    94  (1952 date) = real
   - 107 (1965 date) → 707   107  (1952 date) = real
   - 198 (1966 date) → 798   198  (1954 date) = real
   - 716 (1966 date) → 776   716  (1965 date) = real
   - 718 (1966 date) → 778   718  (1965 date) = real
3. Full month names (July, June, August) not parsed by date regex
"""

import json
import os
import re
import sys

CASES_JSON = os.path.join(os.path.dirname(__file__), "cases.json")
OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), "..", "content", "cases")

MONTH_MAP = {
    "jan": ("01", "January"), "january": ("01", "January"),
    "feb": ("02", "February"), "february": ("02", "February"),
    "mar": ("03", "March"),    "march": ("03", "March"),
    "apr": ("04", "April"),    "april": ("04", "April"),
    "may": ("05", "May"),
    "jun": ("06", "June"),     "june": ("06", "June"),
    "jul": ("07", "July"),     "july": ("07", "July"),
    "aug": ("08", "August"),   "august": ("08", "August"),
    "sep": ("09", "September"), "sept": ("09", "September"), "september": ("09", "September"),
    "oct": ("10", "October"),  "october": ("10", "October"),
    "nov": ("11", "November"), "november": ("11", "November"),
    "dec": ("12", "December"), "december": ("12", "December"),
}

DATE_FULL_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?[,]?\s+"
    r"(\d{1,2})[,.]?\s*(\d{4})",
    re.IGNORECASE,
)

DATE_APPROX_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?[,]?\s+(\d{4})",
    re.IGNORECASE,
)

# Map: (wrong_case_num, date_year_min, date_year_max) → correct_case_num
REMAP = {
    (93,  1954, 1954): 193,
    (94,  1954, 1954): 194,
    (107, 1965, 1965): 707,
    (198, 1966, 1966): 798,
    (716, 1966, 1966): 776,
    (718, 1966, 1966): 778,
    (34,  1908, 1908): 34,  # Keep as 34 — investigate separately
}

# Cases 374-384 and 922-923 are exact duplicates from double-scanned PDF pages
DEDUP_KEEP_FIRST = {374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 384, 922, 923}


def repair_date(case: dict) -> dict:
    """Re-parse date if it's empty but description/location contains a date."""
    if case["date"]:
        return case

    # Try to extract date from location field (common parsing artifact)
    text = case.get("location", "") + " " + case.get("description", "")

    m = DATE_FULL_RE.search(text)
    if m:
        key = m.group(1).lower().rstrip(".")
        mnum, mname = MONTH_MAP.get(key, ("01", "Unknown"))
        day = m.group(2).zfill(2)
        year = m.group(3)
        case["date"] = f"{year}-{mnum}-{day}"
        case["date_display"] = f"{mname} {int(day)}, {year}"
        # Try to fix the location (strip the date from it)
        loc = case["location"]
        clean_loc = DATE_FULL_RE.sub("", loc).strip().lstrip(",. ")
        if clean_loc:
            case["location"] = clean_loc
        return case

    m2 = DATE_APPROX_RE.search(text)
    if m2:
        key = m2.group(1).lower().rstrip(".")
        mnum, mname = MONTH_MAP.get(key, ("01", "Unknown"))
        year = m2.group(2)
        case["date"] = f"{year}-{mnum}"
        case["date_display"] = f"{mname} {year}"
        loc = case["location"]
        clean_loc = DATE_APPROX_RE.sub("", loc).strip().lstrip(",. ")
        if clean_loc:
            case["location"] = clean_loc
        return case

    return case


def get_year(case: dict) -> int:
    d = case.get("date", "")
    m = re.search(r"\b(\d{4})\b", d)
    return int(m.group(1)) if m else 0


def case_to_markdown(case: dict) -> str:
    n        = case["case_number"]
    num_str  = str(n).zfill(3)
    location = case["location"] or f"Case {n}"
    date     = case["date"] or "unknown"
    display  = case.get("date_display") or "Unknown date"
    time     = case.get("time", "")
    desc     = case.get("description", "")
    tags     = case.get("tags", ["case"])

    title     = f"Case {num_str} — {location}"
    tags_yaml = "[" + ", ".join(tags) + "]"
    heading   = f"{location} — {display}"
    if time:
        heading += f" ({time})"

    return (
        f'---\n'
        f'title: "{title}"\n'
        f'date: {date}\n'
        f'location: "{location}"\n'
        f'tags: {tags_yaml}\n'
        f'source: Passport to Magonia\n'
        f'---\n\n'
        f'## {heading}\n\n'
        f'{desc}\n\n'
        f'**Source:** Passport to Magonia  \n'
        f'**Case:** {n}\n'
    )


def main():
    with open(CASES_JSON, encoding="utf-8") as f:
        cases = json.load(f)

    # ---- Step 1: Repair dates using full month names ----
    cases = [repair_date(c) for c in cases]

    # ---- Step 2: Group by case number ----
    from collections import defaultdict
    by_num = defaultdict(list)
    for c in cases:
        by_num[c["case_number"]].append(c)

    fixed = {}

    for n, entries in by_num.items():
        if len(entries) == 1:
            fixed[n] = entries[0]
            continue

        # Multiple entries for same case number
        if n in DEDUP_KEEP_FIRST:
            # Exact duplicates — keep the one with more complete data
            best = max(entries, key=lambda c: len(c.get("description", "")))
            fixed[n] = best
            continue

        # Different content — use year to determine which is the "real" case n
        # Real case n should have a date that's plausible given its position
        # in the sequence (cases are chronological)
        entries.sort(key=get_year)
        year_first = get_year(entries[0])
        year_second = get_year(entries[1])

        # Check remapping table
        for (wrong_n, yr_min, yr_max), correct_n in REMAP.items():
            if wrong_n == n:
                for e in entries:
                    yr = get_year(e)
                    if yr_min <= yr <= yr_max:
                        e["case_number"] = correct_n
                        fixed[correct_n] = e
                    else:
                        fixed[n] = e  # Keep as real case n

        if n not in fixed:
            # Default: keep first (lowest year = earlier date = real case)
            fixed[n] = entries[0]
            # If second entry was remapped, set it
            if len(entries) > 1 and entries[1]["case_number"] not in fixed:
                second_n = entries[1]["case_number"]
                fixed[second_n] = entries[1]

    # ---- Step 3: Sort by case number ----
    sorted_cases = [fixed[n] for n in sorted(fixed.keys())]

    # ---- Step 4: Save updated JSON ----
    with open(CASES_JSON, "w", encoding="utf-8") as f:
        json.dump(sorted_cases, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(sorted_cases)} cases to {CASES_JSON}")

    # ---- Step 5: Regenerate all markdown files ----
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    # Remove old files
    for fn in os.listdir(OUTPUT_DIR):
        if fn.startswith("case-") and fn.endswith(".md"):
            os.remove(os.path.join(OUTPUT_DIR, fn))

    written = 0
    for case in sorted_cases:
        num_str = str(case["case_number"]).zfill(3)
        path    = os.path.join(OUTPUT_DIR, f"case-{num_str}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(case_to_markdown(case))
        written += 1

    print(f"Written {written} markdown files to {OUTPUT_DIR}/")

    # ---- Report remaining gaps ----
    present = set(c["case_number"] for c in sorted_cases)
    missing = [n for n in range(1, 924) if n not in present]
    if missing:
        print(f"Still missing ({len(missing)}): {missing}")
    else:
        print("All 923 cases present!")


if __name__ == "__main__":
    main()
