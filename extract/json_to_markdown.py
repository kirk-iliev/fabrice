#!/usr/bin/env python3
"""
Regenerate markdown case files from cases.json without re-running PDF extraction.
Useful for adjusting formatting or tags without re-parsing the PDF.

Usage:
    python json_to_markdown.py [--json PATH] [--out DIR]
"""

import json
import os
import argparse


DEFAULT_JSON = os.path.join(os.path.dirname(__file__), "cases.json")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "content", "cases")


def case_to_markdown(case: dict) -> str:
    n = case["case_number"]
    num_str = str(n).zfill(3)
    location = case.get("location") or f"Case {n}"
    date = case.get("date") or "unknown"
    display = case.get("date_display") or "Unknown date"
    time = case.get("time", "")
    description = case.get("description", "")
    tags = case.get("tags", ["case"])
    source = case.get("source", "Passport to Magonia")

    title = f"Case {num_str} — {location}"
    tags_yaml = "[" + ", ".join(tags) + "]"
    heading = f"{location} — {display}"
    if time:
        heading += f" ({time})"

    return f"""---
title: "{title}"
date: {date}
location: "{location}"
tags: {tags_yaml}
source: Passport to Magonia
---

## {heading}

{description}

**Source:** {source}
**Case:** {n}
"""


def main():
    parser = argparse.ArgumentParser(description="Convert cases.json to markdown files.")
    parser.add_argument("--json", default=DEFAULT_JSON, help="Path to cases.json")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output directory for .md files")
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        cases = json.load(f)

    os.makedirs(args.out, exist_ok=True)

    for case in cases:
        num_str = str(case["case_number"]).zfill(3)
        path = os.path.join(args.out, f"case-{num_str}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(case_to_markdown(case))

    print(f"Written {len(cases)} markdown files to {args.out}/")


if __name__ == "__main__":
    main()
