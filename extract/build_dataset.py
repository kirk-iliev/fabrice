#!/usr/bin/env python3
"""
Merge raw extracted sources into the canonical dataset at data/cases.json.

Inputs  : extract/cases.json (Passport to Magonia), extract/wonders_cases.json
Output  : data/cases.json  -- single source of truth, unified schema

The unified schema per case:

    id                  "P001" | "W001"
    source_book         "Passport to Magonia" | "Wonders in the Sky"
    title               short title (derived if absent)
    location_raw        original string as extracted
    location            lightly cleaned place name
    lat, lon            null   (filled later by geocoder)
    location_precision  null   (filled later by geocoder)
    date_display        human-readable
    date_iso            "1868-07", "-2637", etc. | null
    date_precision      "day"|"month"|"year"|"decade"|"century"|"circa"|null
    year_sort           int | null    (for sliders / sorting)
    time                "HHMM" | ""
    description         prose
    category            "CE1"|"CE2"|"CE3"|null  (Passport taxonomy only)
    shape               null  (filled later by LLM enrichment pass)
    entities            null
    interaction         null
    time_of_day         null
    source_citation     original citation text when available
    tags                list[str] (derived)
"""

import json
import os
import re

HERE = os.path.dirname(__file__)
PASSPORT_IN = os.path.join(HERE, "cases.json")
WONDERS_IN = os.path.join(HERE, "wonders_cases.json")
OUT = os.path.join(HERE, "..", "data", "cases.json")

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def clean_location(raw: str) -> str:
    """Strip common leakage artifacts from location strings."""
    if not raw:
        return ""
    s = raw.strip()
    # Passport sometimes has a leading year: "1877 Aldershot (Great Britain)"
    s = re.sub(r"^\d{3,4}\s+", "", s)
    return s.strip()


# Matches "PlaceName (Region)" or "PlaceName {Region)" (common OCR artifact).
# Captures the whole phrase so we can normalize braces on output.
_LOC_IN_DESC = re.compile(r"([A-Z][A-Za-z][^,.()\[\]{}]{1,60}[\s][\(\{]([^)}]{2,60})[\)}])")


def extract_location_from_description(desc: str) -> str:
    """
    For Passport cases whose `location` field is blank, the OCR usually
    stranded the location at the start of the description, e.g.:
        "April 12,1897 Nilwood (Illinois), On the property..."
    This pulls the first 'Town (Region)' pattern out of the first ~200 chars.
    """
    if not desc:
        return ""
    head = desc[:250]
    m = _LOC_IN_DESC.search(head)
    if m:
        whole = m.group(1).replace("{", "(").strip().rstrip(",")
        return whole
    # Fallback: description starts with "(Region)." -- use just the region.
    m = re.match(r"^\s*\(([^)]{2,40})\)", head)
    if m:
        return m.group(1).strip()
    return ""


def parse_passport_date(date_str: str):
    """Passport `date` is mostly ISO-ish: YYYY, YYYY-MM, YYYY-MM-DD."""
    if not date_str:
        return None, None, None
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?$", date_str)
    if not m:
        return date_str, None, None
    y, mo, d = m.groups()
    year = int(y)
    if d:
        return f"{y}-{mo}-{d}", "day", year
    if mo:
        return f"{y}-{mo}", "month", year
    return y, "year", year


def parse_wonders_date(display: str):
    """
    Wonders `date_display` is freeform: "675", "Circa 2637 BC",
    "Spring 1870", "12 March 849", "849 AD", etc.
    Return (date_iso, date_precision, year_sort).
    """
    if not display:
        return None, None, None
    s = display.strip()
    low = s.lower()

    is_circa = any(tok in low for tok in ("circa", "ca.", "c.", "around", "approximately"))
    is_bc = bool(re.search(r"\bb\.?c\.?\b", low))

    # Day-month-year: "12 March 849" or "March 12, 849"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{1,4})", s)
    if m and m.group(2).lower() in MONTHS:
        day = int(m.group(1))
        mo = MONTHS[m.group(2).lower()]
        year = int(m.group(3))
        if is_bc:
            year = -year
        return f"{year:04d}-{mo:02d}-{day:02d}", ("circa" if is_circa else "day"), year

    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{1,4})", s)
    if m and m.group(1).lower() in MONTHS:
        mo = MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3))
        if is_bc:
            year = -year
        return f"{year:04d}-{mo:02d}-{day:02d}", ("circa" if is_circa else "day"), year

    # Month + year: "May 698", "Spring 1870" (season treated as year precision)
    m = re.search(r"([A-Za-z]+)\s+(\d{1,4})", s)
    if m and m.group(1).lower() in MONTHS:
        mo = MONTHS[m.group(1).lower()]
        year = int(m.group(2))
        if is_bc:
            year = -year
        return f"{year:04d}-{mo:02d}", ("circa" if is_circa else "month"), year

    # Just year: "675", "2637 BC", "675 AD"
    m = re.search(r"(\d{1,4})", s)
    if m:
        year = int(m.group(1))
        if is_bc:
            year = -year
        iso = f"{year:04d}" if year >= 0 else f"-{abs(year):04d}"
        return iso, ("circa" if is_circa else "year"), year

    return None, None, None


def derive_category(tags: list) -> str | None:
    for cat in ("CE3", "CE2", "CE1"):
        if cat in tags:
            return cat
    return None


def derive_title(location: str, date_display: str, existing: str | None = None) -> str:
    if existing:
        return existing
    return f"{location} — {date_display}" if location and date_display else (location or date_display or "")


def normalize_passport(case: dict) -> dict:
    n = case["case_number"]
    cid = f"P{n:03d}"
    loc_raw = case.get("location", "") or ""
    loc = clean_location(loc_raw)
    if not loc:
        # OCR fallback: pull "Town (Region)" out of the description prefix.
        loc = extract_location_from_description(case.get("description", "") or "")
        loc_raw = loc_raw or loc
    date_iso, date_prec, year_sort = parse_passport_date(case.get("date", ""))
    tags = case.get("tags", []) or []
    return {
        "id": cid,
        "source_book": "Passport to Magonia",
        "title": derive_title(loc, case.get("date_display", "")),
        "location_raw": loc_raw,
        "location": loc,
        "lat": None,
        "lon": None,
        "location_precision": None,
        "date_display": case.get("date_display", "") or "",
        "date_iso": date_iso,
        "date_precision": date_prec,
        "year_sort": year_sort,
        "time": case.get("time", "") or "",
        "description": case.get("description", "") or "",
        "category": derive_category(tags),
        "shape": None,
        "entities": None,
        "interaction": None,
        "time_of_day": None,
        "source_citation": None,   # Passport cites inline in description
        "tags": tags,
    }


def normalize_wonders(case: dict) -> dict:
    cid = case["case_number"]   # already "W001"
    loc_raw = case.get("location", "") or ""
    loc = clean_location(loc_raw)
    display = case.get("date_display", "") or ""
    date_iso, date_prec, year_sort = parse_wonders_date(display)
    return {
        "id": cid,
        "source_book": "Wonders in the Sky",
        "title": derive_title(loc, display, case.get("title")),
        "location_raw": loc_raw,
        "location": loc,
        "lat": None,
        "lon": None,
        "location_precision": None,
        "date_display": display,
        "date_iso": date_iso,
        "date_precision": date_prec,
        "year_sort": year_sort,
        "time": "",
        "description": case.get("description", "") or "",
        "category": None,
        "shape": None,
        "entities": None,
        "interaction": None,
        "time_of_day": None,
        "source_citation": case.get("source") or None,
        "tags": case.get("tags", []) or [],
    }


def main():
    with open(PASSPORT_IN, encoding="utf-8") as f:
        passport = json.load(f)
    with open(WONDERS_IN, encoding="utf-8") as f:
        wonders = json.load(f)

    merged = [normalize_wonders(c) for c in wonders] + [normalize_passport(c) for c in passport]
    # Sort by year_sort (None at end), then id
    merged.sort(key=lambda c: (c["year_sort"] is None, c["year_sort"] or 0, c["id"]))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    unresolved_dates = sum(1 for c in merged if c["year_sort"] is None)
    print(f"Wrote {len(merged)} cases to {OUT}")
    print(f"  Passport: {len(passport)}   Wonders: {len(wonders)}")
    print(f"  Unresolved year_sort: {unresolved_dates}")


if __name__ == "__main__":
    main()
