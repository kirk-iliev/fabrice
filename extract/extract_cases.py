#!/usr/bin/env python3
"""
Extract UFO cases from Jacques Vallée's Passport to Magonia appendix.

The PDF is image-based (scanned), so we use:
  pdf2image  → convert pages to PIL images
  pytesseract → OCR with bounding-box layout to restore reading order
  custom parser → split mixed "date+location+description" lines

Output: extract/cases.json  +  content/cases/case-NNN.md (one per case)
"""

import os
import re
import json
import sys

PDF_PATH = os.path.join(os.path.dirname(__file__), "..", "JacquesValleePassporttoMagonia.pdf")
APPENDIX_START_PAGE = 190  # 1-indexed PDF page (cases 1-8 start before page 195)
APPENDIX_END_PAGE   = 378  # inclusive

OUTPUT_JSON  = os.path.join(os.path.dirname(__file__), "cases.json")
OUTPUT_DIR   = os.path.join(os.path.dirname(__file__), "..", "content", "cases")
OCR_CACHE    = os.path.join(os.path.dirname(__file__), "ocr_lines.txt")

MONTH_MAP = {
    "jan": ("01", "January"), "feb": ("02", "February"),
    "mar": ("03", "March"),   "apr": ("04", "April"),
    "may": ("05", "May"),     "jun": ("06", "June"),
    "jul": ("07", "July"),    "aug": ("08", "August"),
    "sep": ("09", "September"), "sept": ("09", "September"),
    "oct": ("10", "October"), "nov": ("11", "November"),
    "dec": ("12", "December"),
}

TIME_QUALIFIERS = {"night", "dawn", "dusk", "evening", "early", "morning", "afternoon"}

# Matches "Oct. 4,1965" / "Sept. 11,1964" / "Nov., 1964" / "Mar., 1945" / "1897" etc.
DATE_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?[,]?\s+(\d{1,2}[,.]?\s*\d{4}|\d{4}|\d{1,2}[,.]?\s*\d{4})",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"^(\d{4})\s+(.*)", re.DOTALL)
CASE_NUM_RE = re.compile(r"^\d{1,3}[,.]?$")

# Known OCR misreads of case number lines (confirmed from ocr_lines.txt inspection)
OCR_CASE_NUM_FIXES = {
    "SB":   513,   # 5→S, 1 dropped, 3→B
    "S15":  515,   # 5→S
    "53]":  531,   # 1→]
    "no":   130,   # 130→no (1→n, 30→o in bad scan)
}


# ---------------------------------------------------------------------------
# OCR helpers
# ---------------------------------------------------------------------------

def ocr_page_to_lines(img) -> list[str]:
    """
    OCR a PIL image using Tesseract word-level bounding boxes,
    then reconstruct lines sorted by vertical position.
    Returns a list of text lines in reading order.
    """
    import pytesseract

    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    words = []
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        conf = int(data["conf"][i])
        if txt and conf > 20:
            words.append({
                "text": txt,
                "top":  data["top"][i],
                "left": data["left"][i],
                "height": data["height"][i],
            })

    if not words:
        return []

    words.sort(key=lambda w: (w["top"], w["left"]))

    # Group words into lines by proximity of top-coordinate
    lines_raw = []
    current = [words[0]]
    for w in words[1:]:
        avg_h = sum(x["height"] for x in current) / len(current)
        if abs(w["top"] - current[0]["top"]) < avg_h * 0.7:
            current.append(w)
        else:
            lines_raw.append(current)
            current = [w]
    lines_raw.append(current)

    return [
        " ".join(x["text"] for x in sorted(ln, key=lambda x: x["left"]))
        for ln in lines_raw
    ]


def extract_all_lines() -> list[str]:
    """
    OCR all appendix pages and return a flat list of text lines.
    Results are cached in OCR_CACHE to avoid re-running OCR.
    """
    if os.path.exists(OCR_CACHE):
        print(f"  Using cached OCR text from {OCR_CACHE}")
        with open(OCR_CACHE, encoding="utf-8") as f:
            return [ln.rstrip("\n") for ln in f]

    from pdf2image import convert_from_path

    all_lines = []
    total = APPENDIX_END_PAGE - APPENDIX_START_PAGE + 1
    print(f"  OCR-ing {total} pages (this takes a few minutes)…")

    for page_num in range(APPENDIX_START_PAGE, APPENDIX_END_PAGE + 1):
        pct = (page_num - APPENDIX_START_PAGE + 1) / total * 100
        print(f"  page {page_num}/{APPENDIX_END_PAGE}  ({pct:.0f}%)", end="\r", flush=True)

        imgs = convert_from_path(PDF_PATH, first_page=page_num, last_page=page_num, dpi=200)
        if not imgs:
            continue
        page_lines = ocr_page_to_lines(imgs[0])
        all_lines.extend(page_lines)

    print()  # newline after progress

    with open(OCR_CACHE, "w", encoding="utf-8") as f:
        f.write("\n".join(all_lines))
    print(f"  Cached OCR text to {OCR_CACHE}")

    return all_lines


# ---------------------------------------------------------------------------
# Line cleaning
# ---------------------------------------------------------------------------

HEADER_LINES = {"APPENDIX", "PASSPORT TO MAGONIA"}
PAGE_NUM_RE  = re.compile(r"^\d{3}$")  # book page numbers are 3-digit
# When bounding boxes merge header with page number on one line
MERGED_HEADER_RE = re.compile(
    r"^(APPENDIX\s+\d{3}|\d{3}\s+PASSPORT TO MAGONIA|PASSPORT TO MAGONIA\s+\d{3})$"
)


def clean_lines(lines: list[str]) -> list[str]:
    """Remove book page headers and page number lines.

    Headers appear in two forms:
      - Two separate lines: "APPENDIX" then "319"
      - One merged line:    "APPENDIX 319"  or  "320 PASSPORT TO MAGONIA"
    Page numbers adjacent to headers must be dropped; isolated 3-digit
    numbers that match valid case numbers (1-923) must be kept.
    """
    result = []
    skip_next_pagenum = False

    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Single-line merged header (e.g. "APPENDIX 319" or "320 PASSPORT TO MAGONIA")
        if MERGED_HEADER_RE.match(s):
            skip_next_pagenum = False
            continue
        if s in HEADER_LINES:
            skip_next_pagenum = True
            continue
        if skip_next_pagenum and PAGE_NUM_RE.match(s) and 181 <= int(s) <= 380:
            skip_next_pagenum = False
            continue
        skip_next_pagenum = False
        result.append(s)

    return result


# ---------------------------------------------------------------------------
# Case splitting
# ---------------------------------------------------------------------------

def _parse_case_num(line: str) -> int | None:
    """Return case number if line is a case boundary, else None."""
    s = line.strip()
    # Known OCR misreads
    if s in OCR_CASE_NUM_FIXES:
        return OCR_CASE_NUM_FIXES[s]
    # Digits with optional trailing punctuation (e.g. "725,")
    if CASE_NUM_RE.match(s):
        n = int(s.rstrip(",."))
        if 1 <= n <= 923:
            return n
    return None


def split_into_cases(lines: list[str]) -> list[dict]:
    """Identify case-number boundaries and return list of {number, lines}."""
    cases = []
    i = 0
    while i < len(lines):
        n = _parse_case_num(lines[i])
        if n is not None:
            block = []
            j = i + 1
            while j < len(lines):
                if _parse_case_num(lines[j]) is not None:
                    break
                block.append(lines[j])
                j += 1
            cases.append({"number": n, "lines": block})
            i = j
        else:
            i += 1
    return cases


# ---------------------------------------------------------------------------
# Date / location parsing
# ---------------------------------------------------------------------------

def parse_date(token: str) -> tuple[str, str]:
    """
    Parse a date token like "Oct. 4,1965" or "Nov., 1964" into
    (iso_date, display_date).
    """
    m = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+"
        r"(\d{1,2})[,.]?\s*(\d{4})",
        token, re.IGNORECASE,
    )
    if m:
        key = m.group(1).lower().rstrip(".")
        mnum, mname = MONTH_MAP.get(key, ("01", "Unknown"))
        day  = m.group(2).zfill(2)
        year = m.group(3)
        return f"{year}-{mnum}-{day}", f"{mname} {int(day)}, {year}"

    # Approximate: month + year only
    m2 = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+(\d{4})",
        token, re.IGNORECASE,
    )
    if m2:
        key = m2.group(1).lower().rstrip(".")
        mnum, mname = MONTH_MAP.get(key, ("01", "Unknown"))
        year = m2.group(2)
        return f"{year}-{mnum}", f"{mname} {year}"

    # Year only
    m3 = re.search(r"\b(1[89]\d{2}|20\d{2})\b", token)
    if m3:
        return m3.group(0), m3.group(0)

    return "", token.strip()


def split_date_and_text(line: str) -> tuple[str, str]:
    """
    Given a line like "Sept. 11,1964 Ulysses (Oklahoma). Karen...",
    return ("Sept. 11,1964", "Ulysses (Oklahoma). Karen...").
    """
    m = re.match(
        r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?[,]?\s+"
        r"(?:\d{1,2}[,.]?\s*)?\d{4}[,.]?)\s*(.*)",
        line, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return line.strip(), ""


def extract_location(text: str) -> tuple[str, str]:
    """Split 'Location (State). Description text.' into (location, description)."""
    m = re.match(r"^([^.()][^.()]*(?:\([^)]+\))?)\.\s+(.+)", text, re.DOTALL)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", text.strip()


# ---------------------------------------------------------------------------
# Tag inference
# ---------------------------------------------------------------------------

def infer_tags(description: str, location: str) -> list[str]:
    tags = ["case"]
    c = (description + " " + location).lower()

    if any(w in c for w in {"creature", "being", "entity", "humanoid", "figure",
                             "dwarf", "occupant", "pilot", "alien",
                             "small man", "little man", "came out", "emerged",
                             "men", "beings"}):
        tags.append("humanoid")

    if any(w in c for w in {"land", "landed", "landing", "rested on",
                              "ground level", "on the road", "touched down",
                              "came to ground", "settled on"}):
        tags.append("landing")

    if any(w in c for w in {"trace", "burn", "scorched", "imprint",
                              "footprint", "crushed", "flattened",
                              "depression", "radioactiv", "calcin", "oily substance"}):
        tags.append("trace-evidence")

    if any(w in c for w in {"engine", "stall", "headlight", "radio",
                              "engine died", "lights went out", "car stopped",
                              "ignition", "electrical system"}):
        tags.append("vehicle-interference")

    if "humanoid" in tags:
        tags.append("CE3")
    elif "vehicle-interference" in tags or "trace-evidence" in tags or "landing" in tags:
        tags.append("CE2")
    else:
        tags.append("CE1")

    # dedupe
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t); out.append(t)
    return out


# ---------------------------------------------------------------------------
# Case processing
# ---------------------------------------------------------------------------

def process_case(raw: dict) -> dict:
    n     = raw["number"]
    lines = raw["lines"]

    if not lines:
        return {
            "case_number": n, "date": "", "date_display": "", "time": "",
            "location": "", "description": "No details recorded.",
            "source": "Passport to Magonia", "tags": ["case"],
        }

    # ---- First line: date (+ possibly start of description) ----
    first = lines[0]
    if DATE_RE.match(first):
        date_token, rest_of_first = split_date_and_text(first)
    else:
        date_token, rest_of_first = "", first

    iso_date, display_date = parse_date(date_token)

    # ---- Second line: may be time or qualifier ----
    time_str  = ""
    desc_parts = []
    if rest_of_first:
        desc_parts.append(rest_of_first)

    idx = 1
    if idx < len(lines):
        second = lines[idx]
        tm = TIME_RE.match(second)
        if tm:
            time_str = tm.group(1)
            rest = tm.group(2).strip()
            if rest:
                desc_parts.append(rest)
            idx += 1
        elif second.lower() in TIME_QUALIFIERS:
            time_str = second
            idx += 1

    # ---- Remaining lines: description continuation ----
    desc_parts.extend(lines[idx:])
    desc_text = " ".join(desc_parts).strip()

    location, description = extract_location(desc_text)
    if not location:
        description = desc_text

    tags = infer_tags(description, location)

    return {
        "case_number": n,
        "date":         iso_date,
        "date_display": display_date,
        "time":         time_str,
        "location":     location,
        "description":  description,
        "source":       "Passport to Magonia",
        "tags":         tags,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def case_to_markdown(case: dict) -> str:
    n        = case["case_number"]
    num_str  = str(n).zfill(3)
    location = case["location"] or f"Case {n}"
    date     = case["date"] or "unknown"
    display  = case["date_display"] or "Unknown date"
    time     = case.get("time", "")
    desc     = case["description"]
    tags     = case["tags"]

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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)

    print("Step 1/4  OCR extraction…")
    raw_lines = extract_all_lines()
    print(f"  Raw lines: {len(raw_lines)}")

    print("Step 2/4  Cleaning…")
    lines = clean_lines(raw_lines)
    print(f"  Clean lines: {len(lines)}")

    print("Step 3/4  Splitting & processing cases…")
    raw_cases = split_into_cases(lines)
    print(f"  Case blocks found: {len(raw_cases)}")
    cases = [process_case(r) for r in raw_cases]

    print(f"Step 4/4  Writing output…")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)
    print(f"  Saved {OUTPUT_JSON}")

    written = 0
    for case in cases:
        num_str = str(case["case_number"]).zfill(3)
        path    = os.path.join(OUTPUT_DIR, f"case-{num_str}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(case_to_markdown(case))
        written += 1

    print(f"  Written {written} markdown files to {OUTPUT_DIR}/")
    print("Done.")


if __name__ == "__main__":
    main()
