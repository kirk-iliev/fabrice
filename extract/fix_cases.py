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

# ---------------------------------------------------------------------------
# Geography lookup tables
# ---------------------------------------------------------------------------

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
    # territories / DC
    "district of columbia", "puerto rico", "guam",
}

# Maps the parenthetical in a location string to (country, region)
# Keys are lowercase; matched against the extracted parenthetical token.
COUNTRY_MAP = {
    # North America
    "united states": ("United States", "north-america"),
    "usa":           ("United States", "north-america"),
    "canada":        ("Canada",        "north-america"),
    "mexico":        ("Mexico",        "north-america"),
    # Central / Caribbean
    "cuba":          ("Cuba",          "central-america-caribbean"),
    "venezuela":     ("Venezuela",     "south-america"),
    "brazil":        ("Brazil",        "south-america"),
    "argentina":     ("Argentina",     "south-america"),
    "chile":         ("Chile",         "south-america"),
    "peru":          ("Peru",          "south-america"),
    "colombia":      ("Colombia",      "south-america"),
    "bolivia":       ("Bolivia",       "south-america"),
    "uruguay":       ("Uruguay",       "south-america"),
    # Europe
    "france":        ("France",        "europe"),
    "great britain": ("Great Britain", "europe"),
    "england":       ("Great Britain", "europe"),
    "united kingdom":("Great Britain", "europe"),
    "scotland":      ("Great Britain", "europe"),
    "wales":         ("Great Britain", "europe"),
    "ireland":       ("Ireland",       "europe"),
    "germany":       ("Germany",       "europe"),
    "west germany":  ("Germany",       "europe"),
    "east germany":  ("Germany",       "europe"),
    "italy":         ("Italy",         "europe"),
    "spain":         ("Spain",         "europe"),
    "portugal":      ("Portugal",      "europe"),
    "netherlands":   ("Netherlands",   "europe"),
    "belgium":       ("Belgium",       "europe"),
    "switzerland":   ("Switzerland",   "europe"),
    "austria":       ("Austria",       "europe"),
    "sweden":        ("Sweden",        "europe"),
    "norway":        ("Norway",        "europe"),
    "denmark":       ("Denmark",       "europe"),
    "finland":       ("Finland",       "europe"),
    "greece":        ("Greece",        "europe"),
    "yugoslavia":    ("Yugoslavia",    "europe"),
    "hungary":       ("Hungary",       "europe"),
    "czechoslovakia":("Czechoslovakia","europe"),
    "poland":        ("Poland",        "europe"),
    "romania":       ("Romania",       "europe"),
    "bulgaria":      ("Bulgaria",      "europe"),
    "ussr":          ("USSR",          "europe"),
    "soviet union":  ("USSR",          "europe"),
    "russia":        ("Russia",        "europe"),
    "gulf of guinea":("Atlantic Ocean","africa"),
    "coast of delaware": ("United States", "north-america"),
    "aleutian islands":  ("United States", "north-america"),
    "persian gulf":  ("Persian Gulf",  "middle-east"),
    # Middle East / Africa
    "turkey":        ("Turkey",        "middle-east"),
    "iran":          ("Iran",          "middle-east"),
    "iraq":          ("Iraq",          "middle-east"),
    "israel":        ("Israel",        "middle-east"),
    "egypt":         ("Egypt",         "africa"),
    "south africa":  ("South Africa",  "africa"),
    "nigeria":       ("Nigeria",       "africa"),
    # Asia / Pacific
    "japan":         ("Japan",         "asia"),
    "china":         ("China",         "asia"),
    "india":         ("India",         "asia"),
    "pakistan":      ("Pakistan",      "asia"),
    "australia":     ("Australia",     "oceania"),
    "new zealand":   ("New Zealand",   "oceania"),
    "philippines":   ("Philippines",   "asia"),
    "indonesia":     ("Indonesia",     "asia"),
    "vietnam":       ("Vietnam",       "asia"),
    "korea":         ("Korea",         "asia"),
    # Africa
    "morocco":       ("Morocco",       "africa"),
    "algeria":       ("Algeria",       "africa"),
    "libya":         ("Libya",         "africa"),
    "mozambique":    ("Mozambique",    "africa"),
    "zambia":        ("Zambia",        "africa"),
    "gabon":         ("Gabon",         "africa"),
    "rhodesia":      ("Rhodesia",      "africa"),
    "tunisia":       ("Tunisia",       "africa"),
    # Middle East
    "lebanon":       ("Lebanon",       "middle-east"),
    "jordan":        ("Jordan",        "middle-east"),
    "persia":        ("Iran",          "middle-east"),
    "saudi arabia":  ("Saudi Arabia",  "middle-east"),
    # Asia / Pacific
    "annam":         ("Vietnam",       "asia"),
    "new guinea":    ("Papua New Guinea", "oceania"),
    "fiji islands":  ("Fiji",          "oceania"),
    "fiji":          ("Fiji",          "oceania"),
    # Europe (islands/regions)
    "sardinia":      ("Italy",         "europe"),
    "sicily":        ("Italy",         "europe"),
    "swiss alps":    ("Switzerland",   "europe"),
    "eire":          ("Ireland",       "europe"),
    # Americas
    "san salvador":  ("El Salvador",   "central-america-caribbean"),
    "paraguay":      ("Paraguay",      "south-america"),
    "tierra del fuego": ("Argentina",  "south-america"),
    # Canada regions
    "nova scotia":   ("Canada",        "north-america"),
    "labrador":      ("Canada",        "north-america"),
    "newfoundland":  ("Canada",        "north-america"),
    "ontario":       ("Canada",        "north-america"),
    "quebec":        ("Canada",        "north-america"),
    "british columbia": ("Canada",     "north-america"),
    "alberta":       ("Canada",        "north-america"),
    "manitoba":      ("Canada",        "north-america"),
    "azores":        ("Portugal",      "europe"),
    # Catch-all ocean
    "atlantic ocean":("Atlantic Ocean","oceania"),
    "pacific ocean": ("Pacific Ocean", "oceania"),
}

# OCR misreads of US state names
US_STATES_OCR = {
    "lowa":     "iowa",
    "ilinois":  "illinois",
    "ihlinois": "illinois",
    "ihinois":  "illinois",
    "illinols": "illinois",
}


def infer_country_region(location: str) -> tuple[str, str]:
    """
    Given a location string like 'Lufkin (Texas)' or 'Scutari (Turkey)',
    return (country, region) or ("", "") if unknown.
    """
    if not location:
        return "", ""

    # Extract parenthetical: "Foo (Bar)" → "Bar"
    m = re.search(r"\(([^)]+)\)", location)
    paren = m.group(1).strip() if m else location.strip()
    key = paren.lower()

    # Fix known OCR misreads of state names before lookup
    key = US_STATES_OCR.get(key, key)

    # US state check
    if key in US_STATES:
        return "United States", "north-america"

    # Direct country map lookup
    if key in COUNTRY_MAP:
        return COUNTRY_MAP[key]

    # Multi-word fallback: try progressively shorter suffixes of the location
    # e.g. "near Foo, South Africa" → try "south africa"
    words = key.split()
    for length in range(len(words), 0, -1):
        candidate = " ".join(words[-length:])
        if candidate in COUNTRY_MAP:
            return COUNTRY_MAP[candidate]

    # Comma fallback: "Pennsylvania, exact location unknown" → try first token
    first_token = key.split(",")[0].strip()
    if first_token != key:
        first_token = US_STATES_OCR.get(first_token, first_token)
        if first_token in US_STATES:
            return "United States", "north-america"
        if first_token in COUNTRY_MAP:
            return COUNTRY_MAP[first_token]

    return "", ""

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
    (34,  1945, 1945): 54,   # OCR read "54" as "34"; real case 34 is 1908
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

    # Last resort: year-only (e.g. "1908 Coast of Delaware" where year is in location)
    m3 = re.search(r'\b(1[89]\d{2}|20\d{2})\b', text)
    if m3:
        case["date"] = m3.group(1)
        case["date_display"] = m3.group(1)

    return case


def get_year(case: dict) -> int:
    d = case.get("date", "")
    m = re.search(r"\b(\d{4})\b", d)
    return int(m.group(1)) if m else 0


def case_to_markdown(case: dict) -> str:
    n        = case["case_number"]
    num_str  = str(n).zfill(3)
    location = case["location"] or f"Case {n}"
    date     = case["date"] or ""
    display  = case.get("date_display") or "Unknown date"
    time     = case.get("time", "")
    desc     = case.get("description", "")
    tags     = list(case.get("tags", ["case"]))

    country, region = infer_country_region(location)

    # Add country and region tags (avoid duplicates)
    if country:
        country_tag = country.lower().replace(" ", "-")
        if country_tag not in tags:
            tags.append(country_tag)
    if region and region not in tags:
        tags.append(region)

    title     = f"Case {num_str} — {location}"
    tags_yaml = "[" + ", ".join(tags) + "]"
    heading   = f"{location} — {display}"
    if time:
        heading += f" ({time})"

    # Escape double quotes in YAML string fields to prevent parse errors
    title_yaml    = title.replace('"', '\\"')
    location_yaml = location.replace('"', '\\"')
    country_yaml  = country.replace('"', '\\"')

    # Only emit date field when we have a real date — omitting it prevents
    # Quartz from falling back to file-modification time (today's date)
    date_line    = f'date: {date}\n' if date else ''
    country_line = f'country: "{country_yaml}"\n' if country else ''

    return (
        f'---\n'
        f'title: "{title_yaml}"\n'
        f'{date_line}'
        f'location: "{location_yaml}"\n'
        f'{country_line}'
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
            e = entries[0]
            yr = get_year(e)
            # Apply REMAP even for single-entry case numbers (e.g. only the
            # mislabelled version was found, with no real duplicate)
            remapped = False
            for (wrong_n, yr_min, yr_max), correct_n in REMAP.items():
                if wrong_n == n and yr_min <= yr <= yr_max and correct_n != n:
                    e["case_number"] = correct_n
                    fixed[correct_n] = e
                    remapped = True
                    break
            if not remapped:
                fixed[n] = e
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
