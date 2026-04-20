#!/usr/bin/env python3
"""
LLM enrichment pass: extract structured features (shape, entities, interaction,
time_of_day) from each case description using Claude Haiku 4.5.

- Uses prompt caching: the schema + instructions are cached, so only the
  case description is charged as fresh input per call.
- Uses tool-use for guaranteed JSON output.
- Resumable: skips cases that already have `shape` populated.
- Saves progress every 20 cases.

Usage:
    python extract/enrich.py                  # enrich all cases missing features
    python extract/enrich.py --limit 10       # first 10 uncached cases (dry-run friendly)
    python extract/enrich.py --force          # re-run even on already-enriched cases
"""

import argparse
import json
import os
import sys
import time

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

if not os.getenv("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY not set (expected in extract/.env)", file=sys.stderr)
    sys.exit(1)

MODEL = "claude-haiku-4-5-20251001"
CASES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "cases.json")

client = Anthropic()

# ---- Schema ---------------------------------------------------------------

SHAPES = ["disk", "sphere", "cylinder", "triangle", "rectangle", "cigar",
          "light", "fireball", "cloud", "cross", "multiple", "other", "unknown"]
ENTITIES = ["none", "humanoid", "animal_form", "multiple_types", "other", "unknown"]
INTERACTIONS = ["none", "abduction", "trace_evidence", "vehicle_interference",
                "physical_contact", "communication", "injury_or_burn",
                "animal_reaction", "other"]
TIME_OF_DAY = ["dawn", "morning", "day", "afternoon", "dusk", "night", "unknown"]

TOOL = {
    "name": "record_extraction",
    "description": "Record the structured features extracted from one UFO case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "shape": {
                "type": "string", "enum": SHAPES,
                "description": "Primary shape of the reported object.",
            },
            "entities": {
                "type": "string", "enum": ENTITIES,
                "description": "Were non-witness entities/occupants described?",
            },
            "interaction": {
                "type": "string", "enum": INTERACTIONS,
                "description": "Most significant interaction type.",
            },
            "time_of_day": {
                "type": "string", "enum": TIME_OF_DAY,
                "description": "When the event occurred. `unknown` if not stated.",
            },
        },
        "required": ["shape", "entities", "interaction", "time_of_day"],
    },
}

SYSTEM_PROMPT = f"""You extract structured features from historical UFO case reports by \
Jacques Vallée (from *Passport to Magonia* and *Wonders in the Sky*).

For each case description you read, call the `record_extraction` tool exactly once \
with these fields:

- shape: the PRIMARY shape of the observed object. Use `light` when it was just \
a luminous point with no clear form. Use `fireball` for bright moving lights with \
a flame-like or burning quality. Use `multiple` when several distinct objects of \
different shapes were reported together. `unknown` only if no shape information is \
given at all.
- entities: whether non-witness beings were part of the account. `humanoid` = \
human-like figure(s), possibly in suits. `animal_form` = creature-like. \
`multiple_types` = more than one kind of entity. `none` if no entity described.
- interaction: the MOST SIGNIFICANT kind of interaction described. Pick from: \
`trace_evidence` (marks on ground, burned grass), `vehicle_interference` (car, \
radio, compass affected), `physical_contact` (witnesses touched or struck), \
`communication` (verbal or telepathic exchange), `abduction`, `injury_or_burn`, \
`animal_reaction` (dogs bark, cattle flee), `none`, or `other`.
- time_of_day: when the event happened. Use `unknown` if the source doesn't say.

Be decisive. If a case is ambiguous, choose the best-fit enum rather than `unknown` \
unless the text truly gives no clue. Valid enums only.
"""


# ---- Main loop ------------------------------------------------------------

def enrich_one(case: dict) -> dict | None:
    text = f"""Case {case['id']} ({case.get('source_book', '?')})
Location: {case.get('location', 'unknown')}
Date: {case.get('date_display', 'unknown')}

Description:
{case.get('description', '')}"""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=200,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        tools=[TOOL],
        tool_choice={"type": "tool", "name": "record_extraction"},
        messages=[{"role": "user", "content": text}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "record_extraction":
            return dict(block.input)
    return None


def save(cases):
    tmp = CASES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2, ensure_ascii=False)
    os.replace(tmp, CASES_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with open(CASES_PATH, encoding="utf-8") as f:
        cases = json.load(f)

    targets = [c for c in cases if args.force or c.get("shape") is None]
    if args.limit:
        targets = targets[: args.limit]

    print(f"Enriching {len(targets)} / {len(cases)} cases with {MODEL}")
    print()

    total_in_cached = total_in_fresh = total_out = 0
    t0 = time.time()
    errors = 0

    for i, c in enumerate(targets, 1):
        try:
            result = enrich_one(c)
        except Exception as e:
            print(f"  ! {c['id']} error: {e}")
            errors += 1
            time.sleep(2)
            continue

        if result:
            c["shape"] = result["shape"]
            c["entities"] = result["entities"]
            c["interaction"] = result["interaction"]
            c["time_of_day"] = result["time_of_day"]

        if i % 20 == 0:
            save(cases)
            elapsed = time.time() - t0
            rate = i / elapsed
            eta = (len(targets) - i) / rate
            print(f"  [{i}/{len(targets)}]  {rate:.1f}/s  "
                  f"ETA {eta/60:.1f} min  errors={errors}")

    save(cases)
    elapsed = time.time() - t0
    print()
    print(f"Done. Processed {len(targets)} cases in {elapsed/60:.1f} min. "
          f"Errors: {errors}")


if __name__ == "__main__":
    main()
