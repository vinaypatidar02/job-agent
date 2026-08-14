#!/usr/bin/env python3
"""
finalize_cover.py — Merge LLM-written paragraphs into the auto_cover template.

Usage:
    python3 scripts/finalize_cover.py \
        --job_id 4435310423 \
        --paragraphs data/prep_tmp/paragraphs_4435310423.json \
        [--output data/prep_tmp/final_cover_4435310423.json]

The --paragraphs file must be a JSON with exactly one key:
    {"paragraphs": ["para1 text", "para2 text", "para3 text", "para4 text"]}

Why this script exists:
    During application prep the agent writes 4 paragraph texts then builds a
    final cover letter JSON. If it constructs a new dict from scratch it silently
    drops the header fields (name, contact, title_lines, market, date, recipient,
    salutation, closing) that auto_prep.py pre-filled. This script makes that
    impossible: it loads the auto_cover template as the base and only replaces
    the paragraphs, so every header field is always present.

Output:
    Same structure as auto_cover_<job_id>.json but with:
      - paragraphs[] replaced by the 4 provided texts
      - _auto_prep_meta removed
    Ready for validate_prep.py and pdf_renderer.py.
"""

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PREP_TMP = BASE_DIR / "data" / "prep_tmp"


def main() -> None:
    p = argparse.ArgumentParser(description="Merge paragraphs into auto_cover template")
    p.add_argument("--job_id", required=True, help="Job ID (used to locate auto_cover template)")
    p.add_argument("--paragraphs", required=True, help='JSON file: {"paragraphs": ["p1","p2","p3","p4"]}')
    p.add_argument("--output", help="Output path (default: data/prep_tmp/final_cover_<job_id>.json)")
    args = p.parse_args()

    # ── Load template ─────────────────────────────────────────────────────────
    template_path = PREP_TMP / f"auto_cover_{args.job_id}.json"
    if not template_path.exists():
        print(f"[finalize_cover] ERROR: template not found: {template_path}", file=sys.stderr)
        print(f"  Run auto_prep.py first: python3 scripts/auto_prep.py --job_id {args.job_id} ...", file=sys.stderr)
        sys.exit(1)

    with open(template_path) as f:
        cover = json.load(f)

    # ── Load paragraphs ───────────────────────────────────────────────────────
    para_path = Path(args.paragraphs)
    if not para_path.exists():
        print(f"[finalize_cover] ERROR: paragraphs file not found: {para_path}", file=sys.stderr)
        sys.exit(1)

    with open(para_path) as f:
        para_data = json.load(f)

    paragraphs = para_data.get("paragraphs")
    if not isinstance(paragraphs, list) or len(paragraphs) != 4:
        print(f"[finalize_cover] ERROR: paragraphs file must have exactly 4 items, got {len(paragraphs) if isinstance(paragraphs, list) else type(paragraphs)}", file=sys.stderr)
        sys.exit(1)

    # ── Validate: no FILL_ME placeholders remain ──────────────────────────────
    issues = []
    for i, para in enumerate(paragraphs):
        if not isinstance(para, str) or not para.strip():
            issues.append(f"  Para {i+1}: empty or not a string")
        elif "FILL_ME" in para:
            issues.append(f"  Para {i+1}: contains FILL_ME placeholder — not fully written")
        elif "[COMPANY_HOOK:" in para:
            issues.append(f"  Para {i+1}: contains unfilled company hook placeholder")

    if issues:
        print("[finalize_cover] ERROR: paragraphs contain unfilled placeholders:", file=sys.stderr)
        for issue in issues:
            print(issue, file=sys.stderr)
        sys.exit(1)

    # ── Merge: replace paragraphs, strip internal-only fields ────────────────
    cover["paragraphs"] = paragraphs
    cover.pop("_auto_prep_meta", None)
    cover.pop("para4_instructions", None)  # deterministic instruction consumed — not for renderer

    # ── Write output ──────────────────────────────────────────────────────────
    output_path = Path(args.output) if args.output else PREP_TMP / f"final_cover_{args.job_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(cover, f, indent=2)

    total_words = sum(len(para.split()) for para in paragraphs)
    market = cover.get("market", "uk")
    print(f"[finalize_cover] ✓ {output_path}")
    print(f"  market={market}  date={cover.get('date','')}  words={total_words}")
    if total_words < 350:
        print(f"  WARN: {total_words} words — below 350 target (expand Para 4)", file=sys.stderr)
    elif total_words > 450:
        print(f"  WARN: {total_words} words — above 450 target (trim Para 3 Part A first)", file=sys.stderr)
    else:
        print(f"  ✓ word count in range (350–450)")


if __name__ == "__main__":
    main()
