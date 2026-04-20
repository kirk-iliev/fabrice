#!/usr/bin/env python3
"""
Regenerate all markdown case files from the canonical data/cases.json.

The canonical dataset (built by build_dataset.py) is the single source of truth.
This script is the only thing that writes into content/cases/ -- never hand-edit
those files.

Passport cases keep their country/region tag enrichment (inferred from the
parenthetical in the location string via fix_cases.infer_country_region).

Usage:
    python extract/json_to_markdown.py [--json PATH] [--out DIR]
"""

import json
import os
import argparse

# Reuse country inference from the existing fix script.
from fix_cases import infer_country_region

HERE = os.path.dirname(__file__)
DEFAULT_JSON = os.path.join(HERE, "..", "data", "cases.json")
DEFAULT_OUT = os.path.join(HERE, "..", "content", "cases")


def enriched_tags(case: dict) -> list[str]:
    """Tags derived from the LLM enrichment fields. Skips `unknown`/`none`."""
    out = []
    shape = case.get("shape")
    if shape and shape not in ("unknown", "other"):
        out.append(f"shape-{shape}")
    entities = case.get("entities")
    if entities and entities not in ("none", "unknown", "other"):
        out.append(f"entities-{entities}")
    interaction = case.get("interaction")
    if interaction and interaction not in ("none", "other"):
        out.append(interaction.replace("_", "-"))
    tod = case.get("time_of_day")
    if tod and tod != "unknown":
        out.append(f"time-{tod}")
    return out


def file_name(cid: str) -> str:
    """P001 -> case-001.md   W001 -> case-w001.md"""
    if cid.startswith("P"):
        return f"case-{cid[1:]}.md"
    return f"case-{cid.lower()}.md"


def render_passport(case: dict) -> str:
    cid = case["id"]
    num = cid[1:].lstrip("0") or "0"
    num_str = cid[1:]
    location = case["location"] or f"Case {num}"
    date_iso = case.get("date_iso") or ""
    display = case.get("date_display") or "Unknown date"
    time = case.get("time") or ""
    desc = case.get("description", "")
    tags = list(case.get("tags") or ["case"])

    country, region = infer_country_region(location)
    if country:
        country_tag = country.lower().replace(" ", "-")
        if country_tag not in tags:
            tags.append(country_tag)
    if region and region not in tags:
        tags.append(region)
    for t in enriched_tags(case):
        if t not in tags:
            tags.append(t)

    title = f"Case {num_str} — {location}"
    heading = f"{location} — {display}"
    if time:
        heading += f" ({time})"

    title_yaml = title.replace('"', '\\"')
    location_yaml = location.replace('"', '\\"')
    country_yaml = country.replace('"', '\\"')

    date_line = f"date: {date_iso}\n" if date_iso else ""
    country_line = f'country: "{country_yaml}"\n' if country else ""
    tags_yaml = "[" + ", ".join(tags) + "]"

    return (
        f"---\n"
        f'title: "{title_yaml}"\n'
        f"{date_line}"
        f'location: "{location_yaml}"\n'
        f"{country_line}"
        f"tags: {tags_yaml}\n"
        f"source: Passport to Magonia\n"
        f"---\n\n"
        f"## {heading}\n\n"
        f"{desc}\n\n"
        f"**Source:** Passport to Magonia  \n"
        f"**Case:** {num}\n"
    )


def render_wonders(case: dict) -> str:
    cid = case["id"]
    location = case["location"] or cid
    display = case.get("date_display") or "Unknown date"
    desc = case.get("description", "")
    tags = list(case.get("tags") or ["case"])
    for t in enriched_tags(case):
        if t not in tags:
            tags.append(t)
    short_title = case.get("title") or ""
    citation = case.get("source_citation") or ""

    # Reconstruct the "<CID> — <loc>: <title>" YAML title
    clean_title = f"{cid} — {location}"
    if short_title and short_title != f"{location} — {display}":
        clean_title += f": {short_title}"

    clean_title_yaml = clean_title.replace('"', '\\"')
    location_yaml = location.replace('"', '\\"')

    subheading = ""
    if short_title and short_title != f"{location} — {display}":
        subheading = f"### {short_title}\n\n"

    return (
        f"---\n"
        f'title: "{clean_title_yaml}"\n'
        f"date: {display}\n"
        f'location: "{location_yaml}"\n'
        f"tags: {json.dumps(tags)}\n"
        f"source: Wonders in the Sky\n"
        f"---\n\n"
        f"## {location} — {display}\n\n"
        f"{subheading}"
        f"{desc}\n\n"
        f"**Source:** {citation}\n"
        f"**Case:** {cid}\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=DEFAULT_JSON)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args()

    with open(args.json, encoding="utf-8") as f:
        cases = json.load(f)

    os.makedirs(args.out, exist_ok=True)

    for case in cases:
        if case["source_book"] == "Passport to Magonia":
            md = render_passport(case)
        else:
            md = render_wonders(case)
        path = os.path.join(args.out, file_name(case["id"]))
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)

    print(f"Wrote {len(cases)} markdown files to {args.out}/")


if __name__ == "__main__":
    main()
