from __future__ import annotations
"""
generate_covers.py — Batch-generate Cover Letter paragraphs for all pending jobs.

Uses the Anthropic Batch API (50% cost reduction) with prompt caching on the shared
system prompt (~90% input-token saving for jobs 2-N in the batch).

Candidate profile is loaded at startup from data/content/candidate_profile.json.
Fill that file first — see CONFIGURE_CHECKLIST.md for setup instructions.

Run:
    python3 scripts/generate_covers.py --keys app_7468,app_7469,...
    python3 scripts/generate_covers.py --keys app_7468 --dry-run
    python3 scripts/generate_covers.py --keys app_7468 --force
"""
import json, sys, time, os, re, argparse, subprocess
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
        print("  See CONFIGURE_CHECKLIST.md for setup instructions.")
        sys.exit(1)
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Failed to load candidate_profile.json — {e}")
        sys.exit(1)

_PROFILE = _load_profile()
_contact = _PROFILE.get("contact", {})
_prof    = _PROFILE.get("profile", {})
_exp     = _PROFILE.get("experience", [])

_CANDIDATE_NAME     = _contact.get("name", "the candidate")
_YEARS_EXP          = _prof.get("years_of_experience", 5)
_INDUSTRIES         = _prof.get("industry_history", {}).get("industries", [])
_EXCLUDED_TOOLS     = _prof.get("excluded_tools", {}).get("tools", [])
_PLATFORM_NOTES     = _prof.get("platform_notes", {}).get("notes", {})
_FRAMING_RULES      = _prof.get("framing_rules", {}).get("rules", [])
_INVESTMENT_SENT    = _prof.get("verbatim_sentences", {}).get("investment_sentence", "")


def _build_system_prompt(profile: dict) -> str:
    """Build the cover letter system prompt dynamically from candidate_profile.json."""
    contact  = profile.get("contact", {})
    prof     = profile.get("profile", {})
    exp_list = profile.get("experience", [])

    name     = contact.get("name", "the candidate")
    years    = prof.get("years_of_experience", 5)
    industries = prof.get("industry_history", {}).get("industries", [])
    excluded   = prof.get("excluded_tools", {}).get("tools", [])
    platforms  = prof.get("platform_notes", {}).get("notes", {})
    framing    = prof.get("framing_rules", {}).get("rules", [])
    inv_sent   = prof.get("verbatim_sentences", {}).get("investment_sentence", "")

    # Build career summary from experience[]
    career_lines = []
    for i, role in enumerate(exp_list[:6], 1):
        company = role.get("company", "")
        r       = role.get("role", "")
        dates   = role.get("dates", "")
        focus   = role.get("focus_areas", "")
        career_lines.append(f"{i}. {r} @ {company} ({dates})")
        if focus:
            career_lines.append(f"   Key focus: {focus}")

    career_section = "\n".join(career_lines) if career_lines else "  (Add your experience to candidate_profile.json)"

    # Platform notes section
    platform_section = ""
    if platforms:
        lines = [f"  {company}: {note}" for company, note in platforms.items()]
        platform_section = (
            "\nDATA PLATFORMS — NEVER mix these up (wrong platform = credibility risk):\n"
            + "\n".join(lines)
        )

    # Excluded tools section
    excluded_section = ""
    if excluded:
        excluded_section = (
            f"\nRESTRICTED TOOLS — NEVER mention in cover letters (too stale to defend in interviews):\n"
            f"  {', '.join(excluded)}"
        )

    # Industries section
    industries_str = ", ".join(industries) if industries else "(fill in candidate_profile.json)"
    industries_section = f"\nINDUSTRIES — ONLY use these, never invent others:\n  {industries_str}"

    # Framing rules
    framing_section = ""
    if framing:
        framing_section = "\nSPECIAL FRAMING RULES (follow exactly):\n" + "\n".join(f"  - {r}" for r in framing)

    # Investment note
    investment_section = ""
    if inv_sent:
        investment_section = (
            "\nINVESTMENT DOMAIN (if is_investment=true in context):\n"
            f"  Para 3: add 1 sentence on personal investment domain fluency.\n"
            "  NEVER claim professional fund management or institutional investment experience."
        )

    # Para 1 opener examples — built from years and domain labels
    domain_data = profile.get("domains", {})
    primary_label   = domain_data.get("primary",   {}).get("label", "your primary domain")
    secondary_label = domain_data.get("secondary", {}).get("label", "your secondary domain")
    opener_examples = (
        f"[primary domain — {primary_label}] opener example:\n"
        f"  \"With {years}+ years in {primary_label} — [specific specialties] — "
        "I bring [value proposition matching the JD].\"\n\n"
        f"[secondary domain — {secondary_label}] opener example:\n"
        f"  \"With {years}+ years in {secondary_label} — [specific specialties] — "
        "I [value proposition].\"\n\n"
        "[leadership] opener example:\n"
        f"  \"With {years}+ years in [domain] leadership — building teams, leading transformations, "
        "and driving [key outcome] — I bring both the strategic perspective and hands-on delivery "
        "to lead a high-performing function.\""
    )

    return (
        f"You are writing targeted cover letter paragraphs for {name}'s job applications.\n"
        "Follow every rule below exactly. Output ONLY the JSON object specified — no preamble, no explanation.\n\n"
        "════════════════════════════════════════════════════════════════════════════════\n"
        f"CANDIDATE PROFILE — {name}\n"
        "════════════════════════════════════════════════════════════════════════════════\n"
        f"Total experience: {years}+ years.\n\n"
        f"CAREER SUMMARY (newest first):\n{career_section}"
        f"{platform_section}"
        f"{excluded_section}"
        f"{industries_section}"
        f"{framing_section}"
        f"{investment_section}\n\n"
        "════════════════════════════════════════════════════════════════════════════════\n"
        "COVER LETTER STRUCTURE — 4 paragraphs, TARGET 380–420 words total\n"
        "HARD LIMIT: 450 words maximum. The validator rejects any cover over 450 words.\n"
        "Count every word carefully. When in doubt, cut — concise is better than over-length.\n"
        "════════════════════════════════════════════════════════════════════════════════\n"
        "PARA 1 (Role excitement + company hook + alignment) — TARGET 85–105 words:\n"
        "  - Use the Para 1 template provided in the user message.\n"
        "  - Replace [COMPANY_HOOK: ...FILL_ME] with 1–2 sentences that:\n"
        "      (a) name the exact company and exact role title\n"
        "      (b) mention ONE specific thing about this company's mission, product, or unique position\n"
        "  - Do NOT use generic openers like \"I am writing to apply...\"\n"
        "  - Result: the full Para 1 text (opener + company hook as one seamless paragraph).\n\n"
        "PARA 2 (Most relevant experience mapped to JD, specific with metrics) — TARGET 120–135 words:\n"
        "  - Draw from the work history bullets provided — synthesise, do not copy verbatim.\n"
        "  - Focus on the 2–3 most relevant achievements with specific numbers. Stop at 3.\n"
        "  - Must reference actual employers and real metrics from the bullets.\n"
        "  - No fabrication. No new metrics not present in the bullets.\n"
        "  - Keep each sentence tight — one idea per sentence. No compound clauses stacked 3-deep.\n\n"
        "PARA 3 (Broader strategic value + AI closer) — TARGET 115–135 words:\n"
        "  - Draw from a DIFFERENT role/angle than Para 2 (breadth, not repetition).\n"
        "  - Maximum 3 substantive sentences BEFORE the AI closer.\n"
        "  - Include the mandatory AI closer sentence provided in the user message verbatim\n"
        "    at the end of Para 3. The AI closer is ~25 words — it counts toward this paragraph's budget.\n"
        "  - If is_investment=true: add 1 sentence (not 2) on personal investment domain fluency.\n"
        "  - If is_leadership=true: include a sentence on people management / team building.\n\n"
        "PARA 4 (Forward-looking — follow para4_instructions exactly) — TARGET 45–65 words:\n"
        "  MARKET-SPECIFIC VISA/RELOCATION SENTENCES (use the one matching the market):\n"
        "    uk  permanent_hybrid  : \"I am relocating to the UK and would require Skilled Worker Visa sponsorship to take up the role.\"\n"
        "    uk  permanent_remote  : (omit relocation/visa sentence entirely — adds friction for remote hire)\n"
        "    uk  contract_remote   : EOR framing: mention Deel/Remote.com availability + 6h UK overlap. NEVER mention visa.\n"
        "    uk  contract_hybrid   : standard visa sentence + brief contract/EOR note.\n"
        "    nl  (any permanent)   : \"I am pursuing relocation to the Netherlands and would require Kennismigrant sponsorship to take up the role.\"\n"
        "    de  (any permanent)   : \"I am pursuing relocation to Germany and would require EU Blue Card (Blaue Karte EU) sponsorship to take up the role.\"\n"
        "    se  (any permanent)   : \"I am pursuing relocation to Sweden and would require Arbetstillstånd sponsorship via Migrationsverket to take up the role.\"\n"
        "    dk  (any permanent)   : \"I am pursuing relocation to Denmark and would require Pay Limit Scheme (Beløbsordningen) support to take up the role.\"\n"
        "    ie  (any permanent)   : \"I am pursuing relocation to Ireland and would qualify for a Critical Skills Employment Permit to take up the role.\"\n"
        "    ae  (any permanent)   : \"I am pursuing relocation to Dubai, UAE and would require Employment Visa sponsorship to take up the role.\"\n"
        "  ALWAYS follow the para4_instructions field provided — it overrides any default above.\n\n"
        "INTEGRITY RULES:\n"
        "  - Never fabricate metrics, experience, tools, or company knowledge.\n"
        + (f"  - Never mention {', '.join(excluded)} in cover letters.\n" if excluded else "")
        + "  - Never use \"I am writing to apply\" or similar generic openers.\n"
        "  - British English always: organisation, optimisation, modelling, behaviour, prioritise, analyse, programme.\n"
        "  - Tone: confident, specific, warm — not stiff, not generic.\n"
        "  - Closing: do NOT write \"Kind regards\" or the name — that is added by the template.\n"
        "  - Do NOT repeat the same achievement in Para 2 and Para 3.\n"
        "  - WORD COUNT DISCIPLINE: Before finalising, mentally verify each paragraph is within its\n"
        "    target range. If Para 2 or Para 3 exceeds its target, cut the weakest sentence. The\n"
        "    combined total of all 4 paragraphs must be ≤450 words — this is non-negotiable.\n\n"
        "════════════════════════════════════════════════════════════════════════════════\n"
        "PARA 1 OPENERS — auto_prep.py has already selected the right one per domain.\n"
        "The user message provides the full Para 1 template including the opener.\n"
        "Your task: replace [COMPANY_HOOK: ...FILL_ME] with the company-specific hook.\n"
        "Reference openers (for calibration only — use the one in the user message):\n\n"
        f"{opener_examples}\n\n"
        "════════════════════════════════════════════════════════════════════════════════\n"
        "OUTPUT FORMAT — return ONLY this JSON, nothing else:\n"
        "{\"paragraphs\": [\"full para 1 text\", \"full para 2 text\", \"full para 3 text\", \"full para 4 text\"]}\n"
        "No preamble. No explanation. No markdown. Just the JSON object."
    )


# ─────────────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT — built at startup from candidate_profile.json, then cached
# across all N batch requests (~90% input token saving)
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = _build_system_prompt(_PROFILE)


# ─────────────────────────────────────────────────────────────────────────────
# Batch API helpers (mirrors generate_summaries.py)
# ─────────────────────────────────────────────────────────────────────────────

def _submit_batch(batch_requests: list[dict], api_key: str) -> str:
    import urllib.request as _ureq
    headers = {**_BATCH_HEADERS, "x-api-key": api_key}
    payload = json.dumps({"requests": batch_requests}).encode()
    req = _ureq.Request(
        "https://api.anthropic.com/v1/messages/batches",
        data=payload, method="POST", headers=headers)
    with _ureq.urlopen(req, timeout=60) as r:
        batch = json.loads(r.read())
    return batch["id"]


def _poll_batch(batch_id: str, api_key: str) -> dict[str, str]:
    import urllib.request as _ureq
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


# ─────────────────────────────────────────────────────────────────────────────
# Per-job helpers
# ─────────────────────────────────────────────────────────────────────────────

def _needs_cover(key: str, force: bool) -> bool:
    if force:
        return True
    para_file = PREP_TMP / f"paragraphs_{key}.json"
    if not para_file.exists():
        return True
    try:
        data = json.loads(para_file.read_text())
        paras = data.get("paragraphs", [])
        return not (isinstance(paras, list) and len(paras) == 4
                    and all(isinstance(p, str) and p.strip() for p in paras))
    except Exception:
        return True


def _build_work_history_context(work_history: list[dict]) -> str:
    lines = []
    for role in work_history:
        company = role.get("company", "")
        role_title = role.get("role", "")
        bullets = role.get("bullets", [])
        if bullets:
            lines.append(f"\n{role_title} @ {company}:")
            for b in bullets:
                lines.append(f"  • {b}")
    return "\n".join(lines)


def _build_user_message(key: str, resume_data: dict, cover_data: dict, jd_text: str) -> str:
    meta = resume_data.get("_auto_prep_meta", {})
    cover_meta = cover_data.get("_auto_prep_meta", {})

    company = cover_data.get("recipient", "").replace(" Hiring Team", "").strip()
    market = cover_data.get("market", "uk")
    role_type = cover_data.get("role_type", "permanent_hybrid")
    domain = meta.get("domain") or cover_meta.get("domain", "product")
    is_investment = meta.get("is_investment", False) or cover_meta.get("is_investment", False)
    is_leadership = meta.get("is_leadership", False) or cover_meta.get("is_leadership", False)

    # Para 1 template from auto_cover (has [COMPANY_HOOK: FILL_ME] placeholder)
    paragraphs = cover_data.get("paragraphs", [])
    para1_template = paragraphs[0] if paragraphs else ""

    # Mandatory AI closer from _auto_prep_meta
    ai_closer = cover_meta.get("ai_closer", (
        "Beyond this, I bring current hands-on AI engineering capability — having built a "
        "production-grade end-to-end agentic automation system using Claude Code, MCP servers, "
        "and the Anthropic API, fully operational in production."
    ))

    para4_instructions = cover_data.get("para4_instructions", "")

    work_history_ctx = _build_work_history_context(resume_data.get("work_history", []))

    jd_section = jd_text.strip() if jd_text.strip() else "(JD not available — use tracker metadata)"

    return (
        f"Company: {company}  Market: {market}  Domain: {domain}\n"
        f"is_investment: {is_investment}  is_leadership: {is_leadership}  role_type: {role_type}\n"
        f"Date line in cover: {cover_data.get('date', '')}\n\n"
        f"PARA 4 INSTRUCTIONS (follow exactly):\n{para4_instructions}\n\n"
        f"PARA 1 TEMPLATE (complete this — replace [COMPANY_HOOK: ...FILL_ME] with 1–2 company-specific sentences):\n"
        f"{para1_template}\n\n"
        f"MANDATORY AI CLOSER (append verbatim at end of Para 3):\n{ai_closer}\n\n"
        f"JD TEXT:\n{jd_section}\n\n"
        f"WORK HISTORY BULLETS (source for Para 2 and Para 3 — do not fabricate):\n{work_history_ctx}\n\n"
        "Write the 4 paragraphs now. Output ONLY: {\"paragraphs\": [\"p1\", \"p2\", \"p3\", \"p4\"]}"
    )


def _postprocess_cover(raw: str, key: str, cover_data: dict) -> list[str] | None:
    """Parse LLM output, validate, enforce British English. Returns paragraphs list or None on failure."""
    raw = raw.strip()
    # Strip any markdown code fences the LLM may have wrapped it in
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[ERROR] {key}: LLM output is not valid JSON: {e}")
        print(f"  Raw (first 300): {raw[:300]}")
        return None

    paras = parsed.get("paragraphs")
    if not isinstance(paras, list) or len(paras) != 4:
        print(f"[ERROR] {key}: expected 4 paragraphs, got {len(paras) if isinstance(paras, list) else type(paras)}")
        return None

    ok = True
    for i, p in enumerate(paras):
        if not isinstance(p, str) or not p.strip():
            print(f"[ERROR] {key}: Para {i+1} is empty or not a string")
            ok = False
        elif "FILL_ME" in p:
            print(f"[WARN]  {key}: Para {i+1} contains FILL_ME placeholder — check output")
        elif "[COMPANY_HOOK:" in p:
            print(f"[WARN]  {key}: Para {i+1} has unfilled company hook — check output")

    if not ok:
        return None

    # British English enforcement
    paras = [_enforce_british_english(p) for p in paras]

    # Word count check
    total_words = sum(len(p.split()) for p in paras)
    if total_words < 350:
        print(f"[WARN]  {key}: cover letter {total_words} words — below 350 target")
    elif total_words > 450:
        print(f"[WARN]  {key}: cover letter {total_words} words — above 450 target")

    return paras


def _run_finalize_cover(key: str) -> bool:
    """Call finalize_cover.py to merge paragraphs into auto_cover template."""
    para_file = PREP_TMP / f"paragraphs_{key}.json"
    final_file = PREP_TMP / f"final_cover_{key}.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "finalize_cover.py"),
         "--job_id", key,
         "--paragraphs", str(para_file),
         "--output", str(final_file)],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"[ERROR] {key}: finalize_cover.py failed")
        if result.stderr:
            print(f"  {result.stderr.strip()[:300]}")
        return False
    return True


def _load_api_key() -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
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
    return api_key


def main():
    parser = argparse.ArgumentParser(description="Batch-generate cover letter paragraphs")
    parser.add_argument("--keys", required=True, help="Comma-separated list of app IDs to process")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without API calls")
    parser.add_argument("--force", action="store_true", help="Regenerate even if paragraphs exist")
    args = parser.parse_args()

    api_key = _load_api_key()
    if not api_key and not args.dry_run:
        print("ERROR: ANTHROPIC_API_KEY not set"); sys.exit(1)

    target_keys = [k.strip() for k in args.keys.split(",") if k.strip()]

    # Collect jobs needing cover letters
    pending: list[tuple[str, dict, dict, str]] = []  # (key, resume_data, cover_data, jd_text)
    for key in target_keys:
        resume_file = PREP_TMP / f"auto_resume_{key}.json"
        cover_file  = PREP_TMP / f"auto_cover_{key}.json"

        if not resume_file.exists():
            print(f"[MISSING] {key}: auto_resume file not found — run auto_prep.py first")
            continue
        if not cover_file.exists():
            print(f"[MISSING] {key}: auto_cover file not found — run auto_prep.py first")
            continue

        if not _needs_cover(key, args.force):
            print(f"[SKIP]    {key}: paragraphs already generated")
            continue

        resume_data = json.loads(resume_file.read_text())
        cover_data  = json.loads(cover_file.read_text())

        jd_file = PREP_TMP / f"jd_{key}.txt"
        jd_text = ""
        if jd_file.exists():
            try:
                jd_text = jd_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        pending.append((key, resume_data, cover_data, jd_text))

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Cover letters to generate: {len(pending)}")
    if args.dry_run or not pending:
        for key, _, cover_data, _ in pending:
            company = cover_data.get("recipient", "?")
            print(f"  {key}: {company}")
        return

    # Build batch requests — one per job
    batch_requests = []
    for key, resume_data, cover_data, jd_text in pending:
        user_msg = _build_user_message(key, resume_data, cover_data, jd_text)
        batch_requests.append({
            "custom_id": key,
            "params": {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1024,
                "system": [{"type": "text", "text": SYSTEM_PROMPT,
                             "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": user_msg}],
            },
        })

    print(f"Submitting batch of {len(batch_requests)} requests (Sonnet + prompt cache)...")
    batch_id = _submit_batch(batch_requests, api_key)
    print(f"Batch ID: {batch_id}")

    results = _poll_batch(batch_id, api_key)
    print(f"\nResults received: {len(results)}/{len(batch_requests)}")

    # Post-process results
    succeeded = 0
    failed_keys = []
    for key, resume_data, cover_data, _ in pending:
        raw = results.get(key)
        if not raw:
            print(f"[FAIL]  {key}: no result in batch response")
            failed_keys.append(key)
            continue

        paras = _postprocess_cover(raw, key, cover_data)
        if paras is None:
            failed_keys.append(key)
            continue

        # Write paragraphs file
        para_file = PREP_TMP / f"paragraphs_{key}.json"
        para_file.write_text(json.dumps({"paragraphs": paras}, indent=2, ensure_ascii=False))
        print(f"[OK]    {key}: {len(' '.join(paras).split())} words, paragraphs saved")

        # Merge into final_cover via finalize_cover.py
        if not _run_finalize_cover(key):
            failed_keys.append(key)
            continue

        succeeded += 1

    print(f"\nCover letters: {succeeded} succeeded, {len(failed_keys)} failed")
    if failed_keys:
        print(f"  Failed: {', '.join(failed_keys)}")
    if not succeeded:
        sys.exit(1)


if __name__ == "__main__":
    main()
