#!/usr/bin/env python3
"""
Slim data/cases.json into content/cases-geo.json — the payload the globe
page fetches in the browser.

We drop the long description and other server-side fields to keep the
browser download small. The globe only needs enough to render a dot and
link out to the per-case wiki page.
"""

import json
import os

from fix_cases import infer_country_region

HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "..", "data", "cases.json")
DST = os.path.join(HERE, "..", "content", "cases-geo.json")


def slug(cid: str) -> str:
    """Match json_to_markdown.file_name: P001 -> case-001, W001 -> case-w001"""
    return f"case-{cid[1:]}" if cid.startswith("P") else f"case-{cid.lower()}"


def main():
    with open(SRC, encoding="utf-8") as f:
        cases = json.load(f)

    geo = []
    for c in cases:
        if c.get("lat") is None:
            continue
        country, _ = infer_country_region(c.get("location") or "")
        geo.append({
            "id": c["id"],
            "slug": slug(c["id"]),
            "title": c.get("title") or "",
            "location": c.get("location") or "",
            "country": country or None,
            "lat": c["lat"],
            "lon": c["lon"],
            "precision": c.get("location_precision"),
            "year": c.get("year_sort"),
            "date_display": c.get("date_display") or "",
            "source_book": c.get("source_book"),
            "category": c.get("category"),
            "shape": c.get("shape"),
            "entities": c.get("entities"),
            "interaction": c.get("interaction"),
            "time_of_day": c.get("time_of_day"),
        })

    with open(DST, "w", encoding="utf-8") as f:
        json.dump(geo, f, separators=(",", ":"), ensure_ascii=False)

    kb = os.path.getsize(DST) // 1024
    print(f"Wrote {len(geo)} points to {DST} ({kb} KB)")


if __name__ == "__main__":
    main()
