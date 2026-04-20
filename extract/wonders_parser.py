#!/usr/bin/env python3
import re
import json
import os

RAW_TEXT_PATH = "extract/wonders_raw.txt"
OUTPUT_JSON = "extract/wonders_cases.json"
OUTPUT_DIR = "content/cases"

# Regex for "Date, Location" heading
prefix = r"(?:(?:About|Before|After|Circa|Since|Spring|Summer|Fall|Winter|Autumn|Early|Late|Mid)\s+)?"
day = r"(?:\d{1,2}\s+)?"
month = r"(?:(?:January|February|March|April|May|June|July|August|September|October|November|December|[A-Za-z]+)\s+)?"
year = r"(?:\d{1,4})(?:\s*BC)?(?:–\d{1,4}(?:\s*BC)?)?"

DATE_LOC_RE = re.compile(f"^({prefix}{day}{month}{year}),\\s+(.*)$", re.IGNORECASE)

def extract_location_tags(location_str):
    tags = []
    # Strip anything after a colon, dash, or em-dash to remove trailing descriptions
    location_str = re.split(r'[:\-—]', location_str)[0]
    
    # Split by comma to get geographic levels (e.g., City, Region, Country)
    parts = [p.strip() for p in location_str.split(',')]
    for part in parts:
        # Clean up prefixes
        part = re.sub(r'^(near|outside|above|over|around|between|the)\s+', '', part, flags=re.IGNORECASE)
        # Remove anything in parentheses like '(Istanbul)'
        part = re.sub(r'\(.*?\)', '', part).strip()
        
        # Split on common OCR miss-merges
        part = re.split(r'\s+(apparition|hovering|flying|disk|intruder|watering|object|meteor|light|wonders|a\s|circles|angel|three|unexplained)', part, flags=re.IGNORECASE)[0]
        
        # Filter out common "unknown" phrases and months
        months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
        if part.lower() in ["location unknown", "exact location unknown", "unknown location", "unknown", "somewhere", "unspecified", "students", "with a message", "melted metal"] + months:
            continue
            
        if part:
            # Lowercase, replace non-alphanumeric with hyphens
            tag = re.sub(r'[^a-z0-9]+', '-', part.lower()).strip('-')
            
            # Reject tags that contain numbers (likely dates/pages)
            if any(char.isdigit() for char in tag):
                continue
            
            # Robustness heuristic: A geographic tag shouldn't be a full sentence.
            # Reject if it has more than 2 hyphens (3 words) or is longer than 25 chars.
            if tag and tag.count('-') < 3 and len(tag) <= 25 and tag not in tags:
                tags.append(tag)
    return tags

def parse_wonders():
    if not os.path.exists(RAW_TEXT_PATH):
        print(f"Error: {RAW_TEXT_PATH} not found.")
        return

    with open(RAW_TEXT_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    cases = []
    current_case = None
    collecting = None # 'description' or 'source'

    case_count = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        # Skip "Syntax Warning" and page numbers (lines that are just digits)
        if line.startswith("Syntax Warning") or line.isdigit():
            continue

        # Look for a new case heading
        match = DATE_LOC_RE.match(line)
        if match:
            # Save previous case
            if current_case:
                cases.append(current_case)

            case_count += 1
            date_str = match.group(1)
            location = match.group(2)
            
            # The next line is usually the title
            title = ""
            if i + 1 < len(lines):
                title = lines[i+1].strip()

            base_tags = ["case", "wonders-in-the-sky"]
            location_tags = extract_location_tags(location)
            
            current_case = {
                "case_number": f"W{str(case_count).zfill(3)}",
                "date_display": date_str,
                "location": location,
                "title": title,
                "description": "",
                "source": "",
                "tags": base_tags + location_tags
            }
            collecting = "description"
            continue

        if current_case:
            # If we see "Source:", switch to collecting source
            if line.startswith("Source:"):
                current_case["source"] = line.replace("Source:", "").strip()
                collecting = "source"
            elif collecting == "description":
                # Skip if it's the title (already captured)
                if line == current_case["title"]:
                    continue
                if current_case["description"]:
                    current_case["description"] += " " + line
                else:
                    current_case["description"] = line
            elif collecting == "source":
                current_case["source"] += " " + line

    # Add last case
    if current_case:
        cases.append(current_case)

    # Save to JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    print(f"Successfully parsed {len(cases)} cases into {OUTPUT_JSON}")

def generate_markdown():
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        cases = json.load(f)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for case in cases:
        path = os.path.join(OUTPUT_DIR, f"case-{case['case_number'].lower()}.md")
        
        # Clean up title for YAML
        clean_title = f"{case['case_number']} — {case['location']}"
        if case['title']:
            clean_title += f": {case['title']}"
            
        clean_title = clean_title.replace('"', '\\"')
        clean_loc = case['location'].replace('"', '\\"')
        
        content = f"""---
title: "{clean_title}"
date: {case['date_display']}
location: "{clean_loc}"
tags: {json.dumps(case['tags'])}
source: Wonders in the Sky
---

## {case['location']} — {case['date_display']}

### {case['title']}

{case['description']}

**Source:** {case['source']}
**Case:** {case['case_number']}
"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Generated {len(cases)} markdown files in {OUTPUT_DIR}")

if __name__ == "__main__":
    parse_wonders()
    generate_markdown()
