"""
generate_summaries.py — Batch-generate Profile Summaries for ready/ CVs that still have
the raw LLM instruction template in their auto_resume JSON summary field.

Run: python3 scripts/generate_summaries.py
     python3 scripts/generate_summaries.py --dry-run     (show which apps need summaries)
     python3 scripts/generate_summaries.py --force       (regenerate even if summary exists)
     python3 scripts/generate_summaries.py --keys app_7089,4449383323  (specific apps only)

Candidate profile is loaded at startup from data/content/candidate_profile.json.
Fill that file first — see CONFIGURE_CHECKLIST.md for setup instructions.
"""
import json, sys, time, os, re, argparse
import urllib.request as _ureq
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import enforce_british_english as _enforce_british_english

ROOT = Path(__file__).parent.parent
PREP_TMP = ROOT / "data" / "prep_tmp"

_BATCH_HEADERS = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta":    "message-batches-2024-09-24,prompt-caching-2024-07-31",
    "content-type":      "application/json",
}

# ── Load candidate profile ────────────────────────────────────────────────────
def _load_profile() -> dict:
    profile_path = ROOT / "data" / "content" / "candidate_profile.json"
    if not profile_path.exists():
        print("ERROR: data/content/candidate_profile.json not found.")
        print("  Run: cp data/content/candidate_profile.json.example data/content/candidate_profile.json")
        print("  Then fill in your details. See CONFIGURE_CHECKLIST.md.")
        sys.exit(1)
    try:
        raw = profile_path.read_text(encoding="utf-8")
        return json.loads(raw)
    except Exception as e:
        print(f"ERROR: Failed to load candidate_profile.json — {e}")
        sys.exit(1)

_PROFILE = _load_profile()
_contact = _PROFILE.get("contact", {})
_prof = _PROFILE.get("profile", {})
_domains = _PROFILE.get("domains", {})

_CANDIDATE_NAME = _contact.get("name", "the candidate")
_YEARS_EXP      = _prof.get("years_of_experience", 5)
_INDUSTRIES     = _prof.get("industry_history", {}).get("industries", [])
_VERBATIM_SENTS = _prof.get("verbatim_sentences", {}).get("sentences", [])
_INVESTMENT_SENT = _prof.get("verbatim_sentences", {}).get("investment_sentence", "")
_FRAMING_RULES  = _prof.get("framing_rules", {}).get("rules", [])

# Build the system prompt dynamically — no hardcoded personal data
SYSTEM_PROMPT = (
    f"You are writing concise professional profile summaries for {_CANDIDATE_NAME}'s CV.\n"
    "Follow the instructions exactly. Output ONLY the summary text — no labels, no preamble, no quotes.\n"
    "Use British English (organisation, optimisation, modelling, behaviour, etc.)."
)

def _build_bullets_context(work_history: list[dict]) -> str:
    lines = []
    for role in work_history:
        company = role.get("company", "")
        role_title = role.get("role", "")
        bullets = role.get("bullets", [])
        if bullets:
            lines.append(f"{role_title} @ {company}:")
            for b in bullets[:4]:  # bullets[0] is team-lead after Pass 6 for leadership roles
                lines.append(f"  • {b}")
    return "\n".join(lines)


def _domain_flavour_label(domain: str) -> str:
    """Map domain key to a human-readable description for S2 framing guidance."""
    # Build from candidate_profile.json domains first; fall back to domain key itself
    domain_data = _domains.get(domain, {})
    label = domain_data.get("label", "")
    if label and "YOUR" not in label:
        return label
    # Fallback: derive from domain key
    return {
        "primary":   "your primary domain expertise",
        "secondary": "your secondary domain expertise",
        "general":   "your core professional expertise",
    }.get(domain, f"{domain} domain expertise")


def _build_prompt(data: dict, jd_text: str = "") -> str:
    meta = data.get("_auto_prep_meta", {})
    title_lines = data.get("title_lines", ["Senior Professional"])
    title = title_lines[0] if title_lines else "Senior Professional"
    is_leadership = meta.get("is_leadership", False)
    domain = meta.get("domain", "general")
    bullets_ctx = _build_bullets_context(data.get("work_history", []))

    domain_flavour = _domain_flavour_label(domain)
    years = _YEARS_EXP
    industries_str = ", ".join(_INDUSTRIES[:3]) if _INDUSTRIES else "your target industries"
    framing_str = "\n".join(f"- {r}" for r in _FRAMING_RULES) if _FRAMING_RULES else ""

    if is_leadership:
        s2_s3_rules = (
            "- S2: One sentence on the domain strength most relevant to the JD excerpt — "
            "drawn from the work history below. No % metrics. British English.\n"
            "- S3: One sentence on team leadership — reference leading and mentoring a team, "
            "building capability, and enabling data-driven delivery. "
            "Draw from the team-lead bullet (first bullet per company in context). "
            "No % metrics. British English."
        )
    else:
        s2_s3_rules = (
            "- S2: One sentence on the domain strength most relevant to the JD excerpt — "
            "drawn from the work history below. No % metrics. British English.\n"
            "- S3: One sentence on a second, different domain strength that complements S2 — "
            "drawn from the work history. No % metrics. British English."
        )

    jd_section = ""
    if jd_text.strip():
        jd_section = (
            f"\nFull JD — use this to decide which of {_CANDIDATE_NAME.split()[0]}'s "
            "experiences to highlight in S2/S3. "
            "Draw from work history only; do NOT mirror the JD's company industry or copy JD vocabulary:\n"
            f"{jd_text}\n"
        )

    framing_section = ""
    if framing_str:
        framing_section = f"\nSpecial framing rules (follow exactly):\n{framing_str}\n"

    return (
        f"Write exactly 3 sentences for {_CANDIDATE_NAME}'s Profile Summary "
        f"(S1, S2, S3 only — additional sentences are appended by the system).\n\n"
        f"Title to use for S1: \"{title}\"\n"
        f"Domain flavour (use as inspiration for S2 framing, not verbatim): {domain_flavour}\n"
        f"is_leadership: {is_leadership}\n"
        f"{jd_section}"
        f"{framing_section}"
        "Rules:\n"
        f"- S1: Start with \"{title} with {years}+ years across [{industries_str}].\" "
        "Keep all numerals as digits. No pronouns (he/his/him), no % metrics.\n"
        f"{s2_s3_rules}\n"
        f"- Do NOT mirror the target company's industry — stick to {industries_str}.\n"
        "- Output ONLY the 3 sentences as plain text. No labels, no bullet points.\n\n"
        "Work history context (bullets[0] per company is the highest-priority bullet):\n"
        f"{bullets_ctx}"
    )


def _postprocess_summary(s1_s3: str, is_investment: bool, key: str) -> str:
    """Apply British English, validate, then append configured verbatim sentences."""
    text = _enforce_british_english(s1_s3.strip())

    # Ensure S1-S3 block ends with a period so appended sentences attach cleanly
    if text and not text[-1] in '.!?':
        text += '.'

    # Sentence count check
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if len(sentences) != 3:
        print(f"[WARN] {key}: expected 3 sentences from LLM, got {len(sentences)}")

    # Truncation check: last sentence must end with terminal punctuation
    last = sentences[-1] if sentences else ""
    if last and last[-1] not in '.!?':
        print(f"[WARN] {key}: S3 appears truncated (no terminal punctuation) — check max_tokens")

    # Pronoun check (summaries should be in first person or title, not third person)
    if re.search(r'\b(he|his|him)\b', text, re.IGNORECASE):
        print(f"[WARN] {key}: third-person pronoun (he/his/him) found in S1-S3")

    # % metric check (S1-S3 should have none — metrics go in bullets, not summary)
    if '%' in text:
        print(f"[WARN] {key}: percentage metric found in S1-S3 — check output")

    # Append configured verbatim sentences from candidate_profile.json
    parts = [text] + list(_VERBATIM_SENTS)
    if is_investment and _INVESTMENT_SENT:
        parts.append(_INVESTMENT_SENT)
    return " ".join(parts)


def _needs_summary(data: dict, force: bool) -> bool:
    summary = data.get("summary", "")
    if force:
        return True
    return (
        "Write exactly" in summary
        or summary.strip().startswith("S1:")
        or "FILL_ME" in summary
        or not summary.strip()
    )


def _submit_batch(batch_requests: list[dict], api_key: str) -> str:
    headers = {**_BATCH_HEADERS, "x-api-key": api_key}
    payload = json.dumps({"requests": batch_requests}).encode()
    req = _ureq.Request(
        "https://api.anthropic.com/v1/messages/batches",
        data=payload, method="POST", headers=headers)
    with _ureq.urlopen(req, timeout=60) as r:
        batch = json.loads(r.read())
    return batch["id"]


def _poll_batch(batch_id: str, api_key: str) -> dict[str, str]:
    headers = {**_BATCH_HEADERS, "x-api-key": api_key}
    poll_start = time.time()
    while True:
        req = _ureq.Request(
            f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
            headers=headers)
        with _ureq.urlopen(req, timeout=30) as r:
            status = json.loads(r.read())
        counts = status.get("request_counts", {})
        print(f"  Batch {batch_id}: {status['processing_status']} — "
              f"succeeded={counts.get('succeeded', 0)} errored={counts.get('errored', 0)} "
              f"processing={counts.get('processing', 0)}")
        if status["processing_status"] == "ended":
            break
        elapsed = time.time() - poll_start
        if elapsed < 120:    time.sleep(15)
        elif elapsed < 600:  time.sleep(30)
        else:                time.sleep(60)

    req2 = _ureq.Request(
        f"https://api.anthropic.com/v1/messages/batches/{batch_id}/results",
        headers=headers)
    with _ureq.urlopen(req2, timeout=60) as r:
        raw = r.read().decode()

    results: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cid = rec["custom_id"]
        if rec["result"]["type"] == "succeeded":
            results[cid] = rec["result"]["message"]["content"][0]["text"].strip()
        else:
            print(f"[ERROR] {cid}: {rec['result']}")
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Regenerate even if summary exists")
    parser.add_argument("--keys", help="Comma-separated list of specific app keys to process")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not api_key:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        except ImportError:
            env_file = ROOT / ".env"
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                        api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set"); sys.exit(1)

    target_keys = set(args.keys.split(",")) if args.keys else None
    # Derive keys dynamically from all auto_resume_*.json files in prep_tmp
    all_keys = sorted(
        f.stem.replace("auto_resume_", "")
        for f in PREP_TMP.glob("auto_resume_*.json")
    )
    job_keys = [k for k in all_keys if target_keys is None or k in target_keys]

    # Collect jobs needing summaries
    pending: list[tuple[str, dict, Path]] = []
    for key in job_keys:
        f = PREP_TMP / f"auto_resume_{key}.json"
        if not f.exists():
            print(f"[MISSING] {key}: auto_resume file not found")
            continue
        data = json.loads(f.read_text())
        if _needs_summary(data, args.force):
            pending.append((key, data, f))
        else:
            if args.dry_run:
                print(f"[SKIP]    {key}: summary already filled")

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Summaries to generate: {len(pending)}")
    if args.dry_run or not pending:
        for key, _, _ in pending:
            print(f"  {key}")
        return

    # Build batch requests (load JD excerpt per job)
    batch_requests = []
    for key, data, _ in pending:
        jd_file = PREP_TMP / f"jd_{key}.txt"
        jd_text = ""
        if jd_file.exists():
            try:
                jd_text = jd_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass
        prompt = _build_prompt(data, jd_text)
        batch_requests.append({
            "custom_id": key,
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 240,  # 3 sentences (~180 tokens); S4/S5 appended programmatically
                "system": [{"type": "text", "text": SYSTEM_PROMPT,
                             "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": prompt}],
            },
        })

    print(f"Submitting batch of {len(batch_requests)} requests...")
    batch_id = _submit_batch(batch_requests, api_key)
    print(f"Batch ID: {batch_id}")

    # Poll until complete
    results = _poll_batch(batch_id, api_key)
    print(f"\nResults received: {len(results)}/{len(batch_requests)}")

    # Update auto_resume JSONs with post-processed summaries
    updated = 0
    for key, data, f in pending:
        raw_s1_s3 = results.get(key)
        if not raw_s1_s3:
            print(f"[FAIL]  {key}: no result in batch response")
            continue
        meta = data.get("_auto_prep_meta", {})
        summary = _postprocess_summary(
            raw_s1_s3,
            is_investment=meta.get("is_investment", False),
            key=key,
        )
        data["summary"] = summary
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"[OK]    {key}: {summary[:90]}...")
        updated += 1

    print(f"\nUpdated {updated}/{len(pending)} auto_resume files.")
    if updated == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
