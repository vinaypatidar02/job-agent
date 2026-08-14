from __future__ import annotations
"""
finalize_resumes.py — Mechanical resume finalization for all pending jobs.

No LLM calls. Removes _auto_prep_meta, runs RULE 1 (>28w bullets) and RULE 3
(weak leading verbs) checks, then writes final_resume_<job_id>.json.

Run:
    python3 scripts/finalize_resumes.py --keys app_7468,app_7469,...
"""
import json, sys, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent
PREP_TMP = ROOT / "data" / "prep_tmp"

# RULE 3 — blocked leading verbs (weak action words)
_BLOCKED_VERBS = {
    "ran", "worked", "helped", "assisted", "participated", "handled",
    "was", "collaborated", "supported", "involved", "contributed",
    "did", "took", "got",
}

_WARNS: list[str] = []  # collected across threads for final report


def _count_words(bullet: str) -> int:
    return len(bullet.split())


def _leading_verb(bullet: str) -> str:
    words = bullet.strip().split()
    return words[0].rstrip(",.:;").lower() if words else ""


def _finalize_one(key: str) -> tuple[str, bool, list[str]]:
    """Finalize a single job. Returns (key, success, warns)."""
    warns: list[str] = []
    resume_file = PREP_TMP / f"auto_resume_{key}.json"
    final_file  = PREP_TMP / f"final_resume_{key}.json"

    if not resume_file.exists():
        return key, False, [f"[MISSING] {key}: auto_resume file not found"]

    try:
        data = json.loads(resume_file.read_text())
    except Exception as e:
        return key, False, [f"[ERROR] {key}: failed to read auto_resume: {e}"]

    work_history = data.get("work_history", [])
    for role in work_history:
        company = role.get("company", "?")
        for bullet in role.get("bullets", []):
            # RULE 1: bullet length
            wc = _count_words(bullet)
            if wc > 28:
                short = bullet[:60] + "..."
                warns.append(f"[WARN]  {key}: {company}: bullet is {wc}w (>28) — '{short}'")

            # RULE 3: weak leading verb
            verb = _leading_verb(bullet)
            if verb in _BLOCKED_VERBS:
                short = bullet[:60] + "..."
                warns.append(f"[WARN]  {key}: {company}: weak verb '{verb}' — '{short}'")

    # Remove internal-only field before rendering
    data.pop("_auto_prep_meta", None)

    final_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    return key, True, warns


def main():
    parser = argparse.ArgumentParser(description="Mechanical resume finalization (no LLM)")
    parser.add_argument("--keys", required=True, help="Comma-separated list of app IDs")
    args = parser.parse_args()

    target_keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    print(f"\nfinalize_resumes: processing {len(target_keys)} jobs")

    succeeded = 0
    failed: list[str] = []
    all_warns: list[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_finalize_one, k): k for k in target_keys}
        for future in as_completed(futures):
            key, ok, warns = future.result()
            all_warns.extend(warns)
            if ok:
                print(f"[OK]    {key}: final_resume written")
                succeeded += 1
            else:
                for w in warns:
                    print(w)
                failed.append(key)

    for w in all_warns:
        print(w)

    print(f"\nfinalize_resumes: {succeeded} succeeded, {len(failed)} failed")
    if failed:
        print(f"  Failed: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
