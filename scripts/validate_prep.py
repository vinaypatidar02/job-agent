#!/usr/bin/env python3
"""
validate_prep.py — Pre-render validation for resume + cover letter JSON.

Run BEFORE pdf_renderer.py to catch LLM-written field issues before they
reach the PDF. Exits 0 if all checks pass, 1 if any fail.

Usage:
  python3 scripts/validate_prep.py \
      --resume /tmp/final_resume_<job_id>.json \
      --cover  /tmp/final_cover_<job_id>.json \
      --jd     /tmp/jd_<job_id>.txt \
      --company "<Company Name>" \
      --role    "<Role Title>"

  --jd, --company and --role are optional but enable V4, V5 and V15 checks.

Config-driven checks (V1, V2, V7, V17) read from data/content/candidate_profile.json.
If a relevant field is empty in the profile, the check is silently skipped.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

PASSED = []
FAILED = []
WARNED = []


# ── Load candidate profile (for config-driven checks) ────────────────────────
def _load_profile() -> dict:
    profile_path = ROOT / "data" / "content" / "candidate_profile.json"
    if not profile_path.exists():
        return {}
    try:
        return json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

_PROFILE = _load_profile()
_prof    = _PROFILE.get("profile", {})


def _pass(label, detail=""):
    PASSED.append(label)
    suffix = f" ({detail})" if detail else ""
    print(f"  {label:<42} PASS{suffix}")


def _warn(label, detail=""):
    WARNED.append(label)
    suffix = f" ({detail})" if detail else ""
    print(f"  {label:<42} WARN{suffix}")


def _fail(label, reason, hint=""):
    FAILED.append(label)
    print(f"  {label:<42} FAIL")
    print(f"     ✗ {reason}")
    if hint:
        print(f"       → {hint}")


# ── V1 — Required portfolio tools in summary ─────────────────────────────────
# Configurable via candidate_profile.json → profile.required_portfolio_tools.tools
# If empty: check is skipped. Use for tools you've built real portfolio/AI work with.
# EXAMPLE: ["claude", "mcp", "anthropic"] → summary must mention Claude + one support word.
_V1_TOOLS = _prof.get("required_portfolio_tools", {}).get("tools", [])
# Split into anchor (first tool) + support set (rest) for AND-logic check
_V1_ANCHOR  = _V1_TOOLS[0].lower() if _V1_TOOLS else ""
_V1_SUPPORT = [t.lower() for t in _V1_TOOLS[1:]] if len(_V1_TOOLS) > 1 else []

def check_v1_ai_fluency(resume: dict):
    if not _V1_ANCHOR:
        _pass("V1 AI fluency sentence", "skipped (required_portfolio_tools not configured)")
        return
    summary = resume.get("summary", "").lower()
    if _V1_ANCHOR in summary and (not _V1_SUPPORT or any(kw in summary for kw in _V1_SUPPORT)):
        _pass("V1 AI fluency sentence")
    else:
        _fail(
            "V1 AI fluency sentence",
            f"Summary missing portfolio tool signal: needs '{_V1_ANCHOR}'"
            + (f" + at least one of {_V1_SUPPORT}" if _V1_SUPPORT else "") + ".",
            f"Configure in candidate_profile.json → profile.required_portfolio_tools"
        )


# ── V2 — Excluded tools not in expertise/skills/summary/cover ────────────────
# Configurable via candidate_profile.json → profile.excluded_tools.tools
# If empty: check is skipped. Use for tools you can't defend in interviews.
_V2_EXCLUDED_TOOLS = [t.lower() for t in _prof.get("excluded_tools", {}).get("tools", [])]

def check_v2_excluded_tools(resume: dict, cover: dict):
    if not _V2_EXCLUDED_TOOLS:
        _pass("V2 Excluded tools", "skipped (excluded_tools not configured)")
        return

    issues = []
    # Fields to scan (NOT work_history bullets — those show historical exposure accurately)
    expertise_str = " ".join(resume.get("core_expertise", [])).lower()
    skills_str    = " ".join(resume.get("skills", [])).lower()
    summary_str   = resume.get("summary", "").lower()
    cover_paras   = cover.get("paragraphs", [])

    for tool in _V2_EXCLUDED_TOOLS:
        if tool in expertise_str:
            issues.append(f"'{tool}' found in core_expertise. Remove — it may stay in work history bullets only.")
        if tool in skills_str:
            issues.append(f"'{tool}' found in skills. Remove — it may stay in work history bullets only.")
        if tool in summary_str:
            issues.append(f"'{tool}' found in resume summary. Remove — it may stay in work history bullets only.")
        for i, para in enumerate(cover_paras):
            if tool in para.lower():
                issues.append(
                    f"'{tool}' found in cover letter para {i+1}. "
                    f"Remove — it may stay in work history bullets only."
                )

    if issues:
        for issue in issues:
            _fail("V2 Excluded tools", issue)
    else:
        _pass("V2 Excluded tools", f"{len(EXCLUDED_TOOLS)} tools checked")


# ── V3 — Cover letter word count (350–450 per CLAUDE.md Section 5) ───────────
COVER_MIN = 350
COVER_MAX = 450

def check_v3_word_count(cover: dict):
    paras = cover.get("paragraphs", [])
    words = sum(len(p.split()) for p in paras)
    if COVER_MIN <= words <= COVER_MAX:
        _pass("V3 Cover word count", f"{words} words")
    elif words < COVER_MIN:
        _fail(
            "V3 Cover word count",
            f"Cover letter is {words} words (min {COVER_MIN}).",
            "Expand Para 4 to reach target."
        )
    else:
        _fail(
            "V3 Cover word count",
            f"Cover letter is {words} words (max {COVER_MAX}).",
            "Trim Para 3 first, then Para 4. Never trim Para 1 or Para 2."
        )


# ── V4 — Company name in cover letter Para 1 ─────────────────────────────────
def check_v4_company_name(cover: dict, company: str):
    if not company:
        _pass("V4 Company in Para 1", "skipped (no --company arg)")
        return
    import re as _re
    # Strip parenthetical qualifiers e.g. "(anonymised)", "(via Harnham)" before checking
    company_clean = _re.sub(r'\s*\([^)]*\)\s*', ' ', company).strip()
    paras = cover.get("paragraphs", [])
    para1 = paras[0].lower() if paras else ""
    if company_clean.lower() in para1 or company.lower() in para1:
        _pass("V4 Company in Para 1")
        return
    # For anonymous companies ("Unnamed ..."), check that the meaningful descriptor
    # (everything after "Unnamed") appears in Para 1 — cover letter can't literally
    # write "Unnamed" as a company name.
    if company_clean.lower().startswith("unnamed "):
        descriptor = company_clean[len("unnamed "):].strip()
        if descriptor.lower() in para1:
            _pass("V4 Company in Para 1", f"anonymous company — descriptor '{descriptor}' found")
            return
    _fail(
        "V4 Company in Para 1",
        f"'{company_clean}' not found in Para 1.",
        "Para 1 must name the company. Generic opener will hurt response rate."
    )


# ── V5 — MMM/attribution framing guard (JD-conditional) ─────────────────────
MMM_JD_SIGNALS = [
    "mmm", "media mix", "marketing mix", "attribution model",
    "multi-touch attribution", "mta"
]
MMM_CLAIM_PHRASES = [
    "delivered mmm", "built mmm", "mmm model", "attribution model experience",
    "direct experience with mmm"
]
MMM_SAFE_WORDS = ["adjacent", "upskill", "learning", "robyn", "meridian", "active study"]

def check_v5_mmm_framing(resume: dict, cover: dict, jd_text: str):
    if not jd_text:
        _pass("V5 MMM framing guard", "skipped (no --jd arg)")
        return

    jd_lower = jd_text.lower()
    if not any(sig in jd_lower for sig in MMM_JD_SIGNALS):
        _pass("V5 MMM framing guard", "JD does not mention MMM/attribution")
        return

    all_text = (resume.get("summary", "") + " " +
                " ".join(cover.get("paragraphs", []))).lower()

    for phrase in MMM_CLAIM_PHRASES:
        if phrase in all_text:
            _fail(
                "V5 MMM framing guard",
                f"JD mentions MMM/attribution and text contains claim phrase: '{phrase}'.",
                "Framing must be 'adjacent + upskilling' only. NEVER claim direct MMM delivery."
            )
            return

    if not any(safe in all_text for safe in MMM_SAFE_WORDS):
        _fail(
            "V5 MMM framing guard",
            "JD mentions MMM/attribution but no safe framing word found in summary or cover.",
            f"Add one of: {', '.join(MMM_SAFE_WORDS)} to show framing is 'adjacent + active study'."
        )
        return

    _pass("V5 MMM framing guard", "JD has MMM signal; safe framing present")


# ── V6 — No FILL_ME placeholders ─────────────────────────────────────────────
def check_v6_no_fill_me(resume: dict, cover: dict):
    resume_str = json.dumps(resume)
    cover_str  = json.dumps(cover)
    issues = []
    if "FILL_ME" in resume_str:
        issues.append("FILL_ME placeholder found in resume JSON. LLM step incomplete.")
    if "FILL_ME" in cover_str:
        issues.append("FILL_ME placeholder found in cover letter JSON. LLM step incomplete.")
    # Raw prompt text never replaced in summary
    summary = resume.get("summary", "")
    if "Write exactly" in summary or summary.strip().startswith("S1:"):
        issues.append("summary contains raw prompt instructions — LLM never filled it.")
    # Truncated bullets (agent appended '...' instead of rewriting)
    for job in resume.get("work_history", []):
        for bullet in job.get("bullets", []):
            if bullet.rstrip().endswith("...") or bullet.rstrip().endswith("…"):
                issues.append(
                    f"Truncated bullet in '{job.get('company', '')}': "
                    f"'{bullet[:80]}' — rewrite to ≤28 words, do not append '...'."
                )
    if issues:
        for issue in issues:
            _fail("V6 No FILL_ME placeholders", issue)
    else:
        _pass("V6 No FILL_ME placeholders")


# ── V7 — Canonical metrics preservation ──────────────────────────────────────
# Configurable via candidate_profile.json → profile.canonical_metrics.metrics
# If empty: check is skipped. Use for exact metric strings that must appear unchanged
# (prevents LLM from paraphrasing "40%" into "approximately 40%").
_CANONICAL_METRICS  = _prof.get("canonical_metrics", {}).get("metrics", [])
METRICS_MIN_PRESENT = 3   # distinct canonical metrics required across bullets+cover
METRICS_BULLETS_MIN = 4   # bullets that must each contain ≥1 canonical metric

def check_v7_metrics(resume: dict, cover: dict):
    if not _CANONICAL_METRICS:
        _pass("V7 Canonical metrics", "skipped (canonical_metrics not configured)")
        return

    # Scope: work_history bullets + cover paragraphs only.
    # Summary is positioning text (no raw % metrics expected there).
    all_bullets = [b for r in resume.get("work_history", []) for b in r.get("bullets", [])]
    combined    = (" ".join(all_bullets) + " " + " ".join(cover.get("paragraphs", []))).lower()

    present = [m for m in _CANONICAL_METRICS if m in combined]
    missing = [m for m in _CANONICAL_METRICS if m not in combined]

    # Sub-A: how many distinct bullets each contain ≥1 canonical metric
    metric_bullets = [b for b in all_bullets if any(m in b.lower() for m in _CANONICAL_METRICS)]
    bullet_count   = len(metric_bullets)

    n_min_present = min(METRICS_MIN_PRESENT, len(_CANONICAL_METRICS))
    n_min_bullets = min(METRICS_BULLETS_MIN, len(all_bullets))

    sub_a_pass = bullet_count >= n_min_bullets
    sub_b_pass = len(present) >= n_min_present

    if sub_a_pass and sub_b_pass:
        _pass("V7 Canonical metrics",
              f"{len(present)}/{len(_CANONICAL_METRICS)} distinct metrics · {bullet_count} metric-bearing bullets")
    else:
        reasons = []
        if not sub_b_pass:
            reasons.append(
                f"only {len(present)}/{len(_CANONICAL_METRICS)} distinct metrics "
                f"(need {n_min_present}); missing: {', '.join(missing)}"
            )
        if not sub_a_pass:
            reasons.append(
                f"only {bullet_count} bullets contain a canonical metric "
                f"(need {n_min_bullets})"
            )
        _fail("V7 Canonical metrics", "; ".join(reasons),
              f"Restore bullets with: {', '.join(_CANONICAL_METRICS)}")


# ── V8 — Agile/Jira signal (JD-conditional) ──────────────────────────────────
AGILE_JD_SIGNALS = [
    "agile", "scrum", "sprint", "jira", "kanban",
    "sprint planning", "sprint delivery", "agile delivery",
]
AGILE_RESUME_SIGNALS = ["jira", "confluence", "agile", "scrum", "sprint"]

def check_v8_agile_jira(resume: dict, jd_text: str):
    if not jd_text:
        _pass("V8 Agile/Jira signal", "skipped (no --jd arg)")
        return

    jd_lower = jd_text.lower()
    if not any(sig in jd_lower for sig in AGILE_JD_SIGNALS):
        _pass("V8 Agile/Jira signal", "JD does not mention Agile/Scrum")
        return

    # Scope: work_history bullets only.
    # Summary is positioning text — Agile/Jira is delivery evidence, not positioning.
    all_bullets = [b for r in resume.get("work_history", []) for b in r.get("bullets", [])]
    all_text = " ".join(all_bullets).lower()

    if any(sig in all_text for sig in AGILE_RESUME_SIGNALS):
        _pass("V8 Agile/Jira signal", "JD has Agile signal; Jira/Confluence present in bullets")
    else:
        _fail(
            "V8 Agile/Jira signal",
            "JD mentions Agile/Scrum/sprint but no Jira or Confluence signal in work history bullets.",
            "Check your work history bullets tagged [leadership] — ensure at least one Jira/Confluence "
            "bullet is selected, or add a clean Agile bullet to experience_bank.md."
        )


# ── V9 — Git/GitHub version control signal (JD-conditional) ─────────────────
GIT_JD_SIGNALS = [
    "version control", "git", "github", "code review", "peer review",
    "pull request", "collaborative development", "engineering best practices",
    "version-controlled", "code repository",
]
GIT_RESUME_SIGNALS = [
    "git", "github", "version control", "pull request", "code review", "peer review",
]

def check_v9_git_version_control(resume: dict, jd_text: str):
    if not jd_text:
        _pass("V9 Git/version control signal", "skipped (no --jd arg)")
        return

    jd_lower = jd_text.lower()
    if not any(sig in jd_lower for sig in GIT_JD_SIGNALS):
        _pass("V9 Git/version control signal", "JD does not mention version control/GitHub")
        return

    # Scope: work_history bullets + skills list + core_expertise.
    # Summary is positioning — Git belongs in the technical inventory (skills) or delivery bullets.
    all_bullets = [b for r in resume.get("work_history", []) for b in r.get("bullets", [])]
    skills_str = " ".join(resume.get("skills", []) + resume.get("core_expertise", []))
    all_text = (" ".join(all_bullets) + " " + skills_str).lower()

    if any(sig in all_text for sig in GIT_RESUME_SIGNALS):
        _pass("V9 Git/version control signal",
              "JD has Git/VC signal; Git/GitHub present in bullets/skills")
    else:
        _fail(
            "V9 Git/version control signal",
            "JD mentions version control/GitHub/code review but no Git signal found in "
            "bullets or skills list.",
            "Git / GitHub is always in CORE_SKILLS in auto_prep.py — if missing from the "
            "skills list, check that auto_prep.py was used to generate this resume JSON.",
        )


# ── V10 — Investment/hedge fund domain: Mutual Fund experience in summary or cover ──
INVESTMENT_JD_SIGNALS = [
    "hedge fund", "asset management", "investment management", "asset manager",
    "quant finance", "quantitative finance", "fund manager",
    "wealth management", "private equity", "investment bank",
    "portfolio management", "fixed income", "equities",
    "trading strategy", "financial services firm", "fund administration",
]
MUTUAL_FUND_SIGNALS = ["mutual fund", "fund investor", "portfolio management experience"]

def check_v10_investment_domain(resume: dict, cover: dict, jd_text: str):
    if not jd_text:
        _pass("V10 Investment domain MF check", "skipped (no --jd arg)")
        return

    jd_lower = jd_text.lower()
    if not any(sig in jd_lower for sig in INVESTMENT_JD_SIGNALS):
        _pass("V10 Investment domain MF check", "Not an investment-domain JD — skip")
        return

    summary    = resume.get("summary", "").lower()
    cover_text = " ".join(cover.get("paragraphs", [])).lower()
    combined   = summary + " " + cover_text

    if any(sig in combined for sig in MUTUAL_FUND_SIGNALS):
        _pass("V10 Investment domain MF check",
              "Investment JD detected; Mutual Fund experience present in summary/cover")
    else:
        _fail(
            "V10 Investment domain MF check",
            "Investment/finance domain JD detected but personal investment experience missing from "
            "resume summary and cover letter.",
            "STEP 3: add a closing sentence to summary about your personal investment experience. "
            "STEP 5: add 1-2 sentences in Para 3 about domain fluency matching the JD's investment focus."
        )


# ── V11 — Per-role proportional quantification check (Hard Fail) ─────────────
# Bank ratios derived from strict impact-only classification of experience_bank.md:
#   Only %, outcome deltas (from X to Y), and accuracy figures count.
#   Team headcounts, stage counts, component counts = descriptors, NOT impact.
#
# POPULATE THIS for your own employers after writing experience_bank.md.
# Format: "company_substr_lowercase": (impact_bullet_count, total_bullets_in_bank)
# Example: "acme_corp": (3, 8)   → 38% impact ratio → enforces ≥1 impact bullet per role
# Leave empty ({}) to skip V11 for all roles.
ROLE_BANK_RATIOS: dict[str, tuple[int, int]] = {}
IMPACT_RE = re.compile(r'\d+%|from \d+ to \d+|\d+x\b', re.IGNORECASE)


def _bank_ratio(company_name: str):
    key = re.sub(r'[^a-z ]', '', company_name.lower()).strip()
    for k, v in ROLE_BANK_RATIOS.items():
        if k in key or key in k:
            return v
    return None  # unknown company — skip


def check_v11_role_quantification(resume: dict):
    failures = []
    for role in resume.get("work_history", []):
        ratio_pair = _bank_ratio(role.get("company", ""))
        if ratio_pair is None:
            continue
        bank_q, bank_total = ratio_pair
        if bank_q == 0:
            continue  # No impact bullets in bank for this company — skip ratio check
        bullets = role.get("bullets", [])
        n = len(bullets)
        expected_min = max(1, round(n * bank_q / bank_total))
        actual = sum(1 for b in bullets if IMPACT_RE.search(b))
        if actual < expected_min:
            failures.append(
                f"{role.get('company')} / {role.get('role')}: "
                f"{actual}/{n} impact bullets (expected ≥{expected_min} "
                f"based on {bank_q}/{bank_total} bank ratio)"
            )
    if not failures:
        _pass("V11 Per-role quantification", "All roles meet proportional impact-bullet threshold")
    else:
        _fail("V11 Per-role quantification",
              "\n     ".join(failures),
              "Swap in at least one impact bullet (with %, delta, or outcome metric) per failing role")


# ── V12 — Anonymised company: placeholder text absent from Para 1 + recipient ──
_ANON_TRIGGERS = ("(anonymised)", "unnamed", "undisclosed", "confidential client")

def check_v12_anonymised_company(cover: dict, company: str):
    co_lower = company.lower()
    if not any(t in co_lower for t in _ANON_TRIGGERS):
        _pass("V12 Anonymised company rule", "Not an anonymised company — skip")
        return
    paras     = cover.get("paragraphs", [])
    para1     = paras[0] if paras else ""
    recipient = cover.get("recipient", "")
    issues    = []
    # Para 1: full tracker string (with parenthetical) must not appear verbatim
    if "(anonymised)" in para1.lower():
        issues.append("'(anonymised)' found verbatim in Para 1 — reads as a placeholder")
    # Recipient field: must not contain the raw tracker company string
    for t in _ANON_TRIGGERS:
        if t in recipient.lower():
            issues.append(
                f"recipient field contains '{t}' — use a clean descriptor "
                f"(e.g. 'Hiring Team') instead of the tracker company string"
            )
            break
    if issues:
        _fail(
            "V12 Anonymised company rule",
            " | ".join(issues),
            "Para 1: use a natural lowercase descriptor ('at a well-established UK fintech'). "
            "Recipient: set to 'Hiring Team' or a role-specific equivalent. "
            "See ANONYMISED COMPANY RULE in agents/application_prep.md."
        )
    else:
        _pass("V12 Anonymised company rule",
              "Anonymised company — placeholder correctly absent from Para 1 and recipient")


# ── V13 — British English spelling check ─────────────────────────────────────
_AM_SPELLINGS = [
    "optimization", "optimizations", "optimize", "optimized", "optimizing",
    "modeling", "behavioral", "prioritize", "prioritized", "prioritizing",
    "prioritization", "analyze", "analyzed", "analyzing",
    "organize", "organized", "utilize", "utilized", "visualize",
    "behavior", "realize", "emphasize", "summarize", "color",
]

def check_v13_british_english(resume: dict, cover: dict):
    all_text = (json.dumps(resume) + " " + json.dumps(cover)).lower()
    hits = [w for w in _AM_SPELLINGS if w in all_text]
    if hits:
        _warn("V13 British English", f"American spellings found: {hits} — check _enforce_british_english()")
    else:
        _pass("V13 British English", "No American spellings detected")


# ── V14 — Contact info present in cover letter ────────────────────────────────
def check_v14_contact_info(cover: dict):
    """The closing block renders name + phone + email from cover['contact'].
    A hand-edited JSON that drops or FILL_MEs these produces a letter the
    recruiter cannot reply to."""
    contact = cover.get("contact") or {}
    email = (contact.get("email") or "").strip()
    phone = (contact.get("phone") or "").strip()
    problems = []
    if not email or "fill_me" in email.lower() or "@" not in email:
        problems.append(f"email='{email or '(missing)'}'")
    if not phone or "fill_me" in phone.lower() or not any(c.isdigit() for c in phone):
        problems.append(f"phone='{phone or '(missing)'}'")
    if problems:
        _fail("V14 Contact info", f"Invalid cover contact: {', '.join(problems)}",
              "Restore contact dict from auto_prep CONTACT constant before rendering.")
    else:
        _pass("V14 Contact info")


# ── V15 — Role title named in cover letter Para 1 ────────────────────────────
_ROLE_STOPWORDS = {"the", "a", "an", "and", "or", "of", "for", "in", "at", "to", "-", "&"}

def check_v15_role_title(cover: dict, role: str):
    """CLAUDE.md rule: cover letter must name the role title in paragraph 1.
    Fuzzy check: at least 60% of the significant title words must appear in
    Para 1 (exact-phrase matching would false-fail on natural rephrasing like
    'the Analytics Manager position')."""
    if not role:
        _pass("V15 Role in Para 1", "skipped (no --role arg)")
        return
    import re as _re
    # Strip parenthetical qualifiers e.g. "(relocation to Munich)" before matching
    role_clean = _re.sub(r'\s*\([^)]*\)\s*', ' ', role).strip()
    words = [w for w in _re.sub(r'[^a-z0-9 ]', ' ', role_clean.lower()).split()
             if w not in _ROLE_STOPWORDS]
    if not words:
        _pass("V15 Role in Para 1", "skipped (no significant words in role)")
        return
    paras = cover.get("paragraphs", [])
    para1 = paras[0].lower() if paras else ""
    found = [w for w in words if w in para1]
    if len(found) / len(words) >= 0.6:
        _pass("V15 Role in Para 1", f"{len(found)}/{len(words)} title words found")
    else:
        _fail("V15 Role in Para 1",
              f"Only {len(found)}/{len(words)} words of '{role_clean}' appear in Para 1.",
              "Para 1 must name the role title (CLAUDE.md cover letter rule).")


# ── V19 — Values alignment check (cover-only, meta.json required) ────────────
def check_v19_values_alignment(cover: dict, meta_path: str):
    """EU market best practice: cover letter must contain a values-alignment sentence
    when the company's values page was successfully fetched during prep.

    Logic:
      1. meta.json not provided (--meta absent) → skip silently.
      2. values_fetch.attempted = false / not_attempted → FAIL (fetch was never tried).
      3. values_fetch.result = "failed" → PASS (accepted: page unreachable).
      4. values_fetch.result = "success" AND no value keyword found in cover → FAIL.
    """
    if not meta_path:
        _pass("V19 Values alignment", "skipped (no --meta arg)")
        return

    meta_file = Path(meta_path)
    if not meta_file.exists():
        _pass("V19 Values alignment", "skipped (meta.json not found)")
        return

    try:
        meta = json.loads(meta_file.read_text())
    except json.JSONDecodeError:
        _warn("V19 Values alignment", "meta.json is not valid JSON — skipping check")
        return

    vf = meta.get("values_fetch", {})
    attempted = vf.get("attempted", False)
    result    = vf.get("result", "not_attempted")
    values    = vf.get("values_found", [])

    if result == "skipped_no_company_domain":
        _pass("V19 Values alignment", "skipped — third-party ATS or no company domain in career_page_url")
        return

    if result == "failed":
        _pass("V19 Values alignment", "values page unreachable during prep — sentence correctly omitted")
        return

    if not attempted or result == "not_attempted":
        _fail(
            "V19 Values alignment",
            "Values fetch was never attempted during cover letter prep.",
            "Re-run cover letter generation — the skill must run the domain check and "
            "attempt to fetch company values before writing Para 3, then record the "
            "result in meta.json."
        )
        return

    # result = "success" — check cover letter references at least one value
    # Matching strategy: keyword-based (cover prose paraphrases values — exact strings won't match)
    #   1. Normalise value string: lowercase, "&" → "and"
    #   2. Extract significant keywords (4+ chars, skip stopwords)
    #   3. A value "matches" if ≥2 of its significant keywords appear in cover_text
    _STOPWORDS = {"with", "that", "this", "have", "from", "they", "their",
                  "what", "into", "more", "than", "each", "also", "your",
                  "make", "build", "love", "team", "push", "focus", "free",
                  "work", "feel", "when", "been", "will", "just", "very",
                  "and", "but", "for", "the", "are", "our", "who", "how"}
    cover_text = " ".join(cover.get("paragraphs", [])).lower()
    import re as _re

    def _keywords(value_str: str):
        normalised = value_str.lower().replace("&", "and")
        words = _re.findall(r"[a-z]+", normalised)
        # skip leading pronouns and short stopwords
        return [w for w in words if len(w) >= 4 and w not in _STOPWORDS]

    matched = []
    for v in values:
        kws = _keywords(v)
        hits = [kw for kw in kws if kw in cover_text]
        if len(hits) >= max(1, len(kws) // 2):  # ≥50% of significant keywords found
            matched.append(v)

    if matched:
        _pass("V19 Values alignment", f"value(s) referenced in cover: {matched}")
    else:
        _fail(
            "V19 Values alignment",
            f"Company values were fetched ({values}) but no values-alignment sentence "
            f"found in cover letter paragraphs.",
            "Add 1 sentence to Para 3 Part A: '[Company] values [X] — in my work at "
            "[Employer], I [specific action + metric that demonstrates X].'"
        )


# ── V16 — AI project framing leak ────────────────────────────────────────────
_AI_PROJECT_FORBIDDEN = [
    "job search", "job application", "resume tailoring", "cv tailoring",
    "cover letter automation", "job search automation", "application automation",
]

def check_v16_ai_project_framing(resume: dict, cover: dict):
    """CLAUDE.md rule: AI Engineering Project must NEVER be described using phrases
    that reveal its job-search application domain (summary S4 + cover letter)."""
    summary = (resume.get("summary") or "").lower()
    cover_text = " ".join(cover.get("paragraphs", [])).lower()
    hits = [p for p in _AI_PROJECT_FORBIDDEN if p in summary or p in cover_text]
    if hits:
        _fail("V16 AI project framing",
              f"Forbidden phrase(s) found: {hits}",
              "Rewrite using neutral framing: 'production agentic pipeline', "
              "'analytics workflow automation', etc. — never reveal the job-search domain.")
    else:
        _pass("V16 AI project framing", "No forbidden AI project domain phrases found")


# ── V17 — S1 industry restriction ────────────────────────────────────────────
# Configurable via candidate_profile.json → profile.industry_whitelist.industries
# If empty: check is skipped (all industries allowed).
# Use for industries you can honestly claim from your actual work history.
# EXAMPLE: ["ecommerce", "marketplace", "agri-tech", "automotive"]
_V17_ALLOWED_INDUSTRIES = [i.lower() for i in _prof.get("industry_whitelist", {}).get("industries", [])]

def check_v17_s1_industry(resume: dict):
    """Summary industries must come from the candidate's actual work history.
    Configurable via candidate_profile.json → profile.industry_whitelist.industries.
    If the list is empty, this check is skipped."""
    if not _V17_ALLOWED_INDUSTRIES:
        _pass("V17 S1 industry restriction", "skipped (industry_whitelist not configured)")
        return

    summary = (resume.get("summary") or "").lower()
    # Any industry-like word in the summary that does NOT appear in the whitelist is suspicious
    # Simple approach: flag if any "known risky" industry word appears that isn't in whitelist
    _COMMON_INDUSTRIES = [
        "fintech", "insurance", "saas", "travel", "banking", "healthcare",
        "pharma", "legal", "media", "gaming", "logistics", "construction",
    ]
    hits = [w for w in _COMMON_INDUSTRIES if w in summary and w not in _V17_ALLOWED_INDUSTRIES]
    if hits:
        _fail("V17 S1 industry restriction",
              f"Industry word(s) in summary not in your whitelist: {hits}",
              f"S1 must use only your actual industries: {', '.join(_V17_ALLOWED_INDUSTRIES)}. "
              "Configure in candidate_profile.json → profile.industry_whitelist.")
    else:
        _pass("V17 S1 industry restriction", "No non-whitelisted industry words in summary")


# ── V18 — Third-person pronoun in summary (Hard Fail) ────────────────────────
def check_v18_pronoun(resume: dict):
    """Resume summary must use implicit first-person — 'his'/'her' should not appear."""
    summary = resume.get("summary") or ""
    m = re.search(r'\b(his|her)\b', summary, re.IGNORECASE)
    if m:
        _fail("V18 Third-person pronoun in summary",
              f"Found '{m.group(0)}' — summary must not use 'his'/'her'.",
              "Rephrase: e.g. 'during his [Company] tenure' → 'during the [Company] tenure'.")
    else:
        _pass("V18 Third-person pronoun", "No 'his'/'her' in summary")


# ── V20 — Bullet word count (brevity guard) ───────────────────────────────────
def check_v20_bullet_length(resume: dict):
    """All bullets must be ≤30 words. FAIL >30, WARN 28–30."""
    long_bullets = []
    warn_bullets = []
    for role in resume.get("work_history", []):
        co = role.get("company", "?")
        for bullet in role.get("bullets", []):
            wc = len(bullet.split())
            if wc > 30:
                long_bullets.append(f"[{wc}w] {co}: {bullet[:70]}…")
            elif wc >= 28:
                warn_bullets.append(f"[{wc}w] {co}: {bullet[:70]}…")
    if long_bullets:
        _fail("V20 Bullet length",
              f"{len(long_bullets)} bullet(s) exceed 30 words:\n     " + "\n     ".join(long_bullets),
              "Apply RULE 1 shortening in application_prep.md §4b — preserve all numeric metrics.")
    elif warn_bullets:
        _warn("V20 Bullet length",
              f"{len(warn_bullets)} bullet(s) at 28–30 words (borderline):\n     " +
              "\n     ".join(warn_bullets))
    else:
        _pass("V20 Bullet length", "All bullets ≤28 words")


# ── V21 — JD skills coverage in resume skills section ─────────────────────────
# Default toolkit built from common skills across all professions.
# The pipeline dynamically adds skills from the JD + candidate profile core_skills.
_AUTHENTIC_TOOLKIT = [
    ("sql", ["sql"]),
    ("python", ["python"]),
    ("tableau", ["tableau"]),
    ("bigquery", ["bigquery", "big query"]),
    ("redshift", ["redshift"]),
    ("looker", ["looker"]),
    ("git", ["git", "github", "version control"]),
    ("claude code", ["claude code"]),
    ("anthropic api", ["anthropic api", "anthropic"]),
    ("xgboost", ["xgboost"]),
    ("experimentation", ["experimentation", "a/b test", "ab test", "experiment"]),
    ("crm analytics", ["crm"]),
    ("pricing", ["pricing"]),
    ("segmentation", ["segment"]),
]
# Extend toolkit with user's core skills from candidate_profile.json
_core_skills = _PROFILE.get("core_skills", {}).get("skills", [])
_existing_labels = {t[0] for t in _AUTHENTIC_TOOLKIT}
for _skill in _core_skills:
    _skill_lower = _skill.lower()
    if _skill_lower not in _existing_labels:
        _AUTHENTIC_TOOLKIT.append((_skill_lower, [_skill_lower]))

# Excluded tools: loaded from profile + hardcoded cross-domain blocklists
_V21_EXCLUDE = list(_V2_EXCLUDED_TOOLS) + ["sap", "german"]

def check_v21_jd_skills_coverage(resume: dict, jd_text: str):
    if not jd_text:
        _pass("V21 JD skills coverage", "skipped (no --jd arg)")
        return
    jd_lower = jd_text.lower()
    skills_text = " ".join(resume.get("skills", [])).lower()
    expertise_text = " ".join(resume.get("core_expertise", [])).lower()
    combined = skills_text + " " + expertise_text

    # skip excluded tools
    for excl in _V21_EXCLUDE:
        jd_lower = jd_lower.replace(excl, "")

    missing = []
    for skill_label, jd_terms in _AUTHENTIC_TOOLKIT:
        in_jd = any(t in jd_lower for t in jd_terms)
        if not in_jd:
            continue
        in_resume = any(t in combined for t in jd_terms + [skill_label])
        if not in_resume:
            missing.append(skill_label)

    if missing:
        _warn("V21 JD skills coverage",
              f"Authentic skills in JD but missing from skills section: {missing}\n"
              "     → auto_prep.py should have included these — check detect_conditional_skills()")
    else:
        _pass("V21 JD skills coverage", "All JD-mentioned authentic skills present in resume")


# ── V22 — Bullet claim integrity (refinement drift check) ─────────────────────
def check_v22_bullet_integrity(resume: dict, resume_path: str):
    """Compare final bullets against auto_resume originals to detect claim drift."""
    import re as _re

    # Derive auto_resume path from final_resume path
    p = Path(resume_path)
    stem = p.stem  # e.g. "final_resume_4417143181"
    job_id = stem.replace("final_resume_", "")
    if job_id == stem:  # no substitution = unusual filename — skip
        _pass("V22 Bullet integrity", "skipped (non-standard resume filename)")
        return
    auto_path = p.parent / f"auto_resume_{job_id}.json"
    if not auto_path.exists():
        _pass("V22 Bullet integrity", f"skipped (auto_resume_{job_id}.json not found)")
        return

    with open(auto_path) as f:
        auto_resume = json.load(f)

    def _extract_nums(text: str) -> set:
        return set(_re.findall(r'\b\d+(?:[.,]\d+)?%?\b', text))

    # Common sentence-start action verbs — capitalized only because they open the bullet.
    # Excluding these prevents false positives in named-entity comparison.
    _SENT_VERBS = {
        "Led", "Built", "Ran", "Designed", "Drove", "Delivered", "Established",
        "Represented", "Applied", "Validated", "Conducted", "Developed",
        "Introduced", "Created", "Managed", "Deployed", "Engineered", "Owned",
        "Instrumented", "Spearheaded", "Implemented", "Launched", "Executed",
        "Identified", "Produced", "Reduced", "Achieved", "Enabled", "Supported",
    }

    def _extract_named(text: str) -> set:
        # Capitalised mid-sentence words (skip first word — always capitalised) and known tech keywords.
        words = text.split()
        mid_caps = set(
            w.rstrip(".,;:") for w in words[1:]
            if len(w) >= 3 and w[0].isupper() and not w.isupper()
        ) - _SENT_VERBS
        tech = {"SQL", "Python", "Tableau", "BigQuery", "Redshift", "Looker",
                "XGBoost", "Jira", "Confluence", "Agile", "Scrum",
                "Claude", "Anthropic", "Airflow", "Firebase", "SAP",
                "MCP", "KPI", "GMV", "RPC", "ASP", "MOV", "AOV", "SLA"}
        return mid_caps | (tech & set(words))

    issues = []
    final_roles = {(r.get("company",""), r.get("role","")): r.get("bullets", [])
                   for r in resume.get("work_history", [])}
    auto_roles  = {(r.get("company",""), r.get("role","")): r.get("bullets", [])
                   for r in auto_resume.get("work_history", [])}

    for key, final_bullets in final_roles.items():
        orig_bullets = auto_roles.get(key, [])
        for i, fb in enumerate(final_bullets):
            # find best matching original by index (auto_prep preserves order)
            if i < len(orig_bullets):
                ob = orig_bullets[i]
            else:
                continue  # new bullet added — flag it
            ob_nums = _extract_nums(ob)
            fb_nums = _extract_nums(fb)
            # (a) metric preservation
            lost = ob_nums - fb_nums
            if lost:
                issues.append(f"Metric(s) dropped from {key[0]}/{key[1]} bullet {i+1}: {lost}")
            # (b) metric inflation
            added = fb_nums - ob_nums
            if added:
                issues.append(f"New metric(s) in {key[0]}/{key[1]} bullet {i+1}: {added} (not in original)")
            # (c) new named entities
            ob_named = _extract_named(ob)
            fb_named = _extract_named(fb)
            new_names = fb_named - ob_named
            if new_names:
                issues.append(f"New named entity in {key[0]}/{key[1]} bullet {i+1}: {new_names}")

    if issues:
        _warn("V22 Bullet integrity",
              f"{len(issues)} potential drift(s) detected:\n     " + "\n     ".join(issues[:5]))
    else:
        _pass("V22 Bullet integrity", "No metric drift or new named entities in refined bullets")


# ── V23 — Weak leading verb guard ─────────────────────────────────────────────
_WEAK_LEADING_VERBS = {
    "ran", "worked", "helped", "assisted", "participated", "handled",
    "was", "collaborated", "supported", "involved", "contributed",
    "did", "took", "got",
}

def check_v23_leading_verbs(resume: dict):
    """All bullets must start with a strong ownership/leadership verb.
    WARN if first word is in the weak-verb blocklist."""
    hits = []
    for role in resume.get("work_history", []):
        co = role.get("company", "?")
        for bullet in role.get("bullets", []):
            words = bullet.split()
            if not words:
                continue
            first = words[0].rstrip(".,;:").lower()
            if first in _WEAK_LEADING_VERBS:
                hits.append(f"{co}: {bullet[:75]}…")
    if hits:
        _warn("V23 Weak leading verb",
              f"{len(hits)} bullet(s) open with a weak verb:\n     " + "\n     ".join(hits) +
              "\n     Replace with strong ownership verbs: Led, Built, Designed, Engineered, "
              "Conducted, Drove, Delivered, Established, Developed, Introduced, Deployed, Owned.")
    else:
        _pass("V23 Weak leading verb", "All bullets open with strong ownership verbs")


# ── V_LEAD — Leadership bullet at position 0 for is_leadership=True roles ─────
# These are the exact [team-lead]-tagged bullet openings from experience_bank.md.
# Pass 6 in auto_prep.py guarantees bullets[0] is the team-lead bullet.
# If it isn't, Pass 6 failed to fire — catch it here before rendering.
#
# POPULATE THIS from your own experience_bank.md after tagging bullets [team-lead].
# Format: "company_substr_lowercase": ("opening phrase variant 1", "variant 2 after SHORTEN")
# Example: "acme_corp": ("led and mentored a team of", "led a team of")
# Leave empty ({}) to skip V_LEAD enforcement.
_TEAM_LEAD_BULLETS: dict[str, tuple] = {}


def check_v_lead(resume: dict):
    meta = resume.get("_auto_prep_meta", {})
    if not meta.get("is_leadership"):
        _pass("V_LEAD Leadership bullet order", "skipped (is_leadership=False)")
        return

    failures = []
    for role in resume.get("work_history", []):
        co = role.get("company", "").lower()
        for co_key, phrases in _TEAM_LEAD_BULLETS.items():
            if co_key not in co:
                continue
            bullets = role.get("bullets", [])
            if not bullets:
                failures.append(f"{role.get('company', '?')}: no bullets")
                break
            first = bullets[0].lower()
            if not any(p in first for p in phrases):
                failures.append(
                    f"{role.get('company', '?')}: bullets[0] is not the team-lead bullet "
                    f"(found: '{bullets[0][:70]}')"
                )
            break  # matched company — no need to check other keys

    if failures:
        _fail(
            "V_LEAD Leadership bullet order",
            "\n     ".join(failures),
            "Re-run auto_prep.py — Pass 6 must place [team-lead] bullet first. "
            "Check that [team-lead] tag exists in experience_bank.md for this company.",
        )
    else:
        _pass("V_LEAD Leadership bullet order", "team-lead bullet is bullets[0] in all leadership roles")


# ── V_ROLES — work_history role count + exact bullet counts (Hard Fail) ────────
# Set to the number of roles in your work_history, or None to skip the count check.
_EXPECTED_ROLES: int | None = None

# Exact bullet counts per role — keyed by (company_substr, role_substr_or_None), both lowercased.
# auto_prep.py max_bullets defines these; the LLM must not add or remove bullets.
# role_substr disambiguates same-company roles (e.g. two different roles at the same employer).
# List longer role substrings before shorter ones so they match first (e.g. "senior data analyst"
# before "data analyst").
#
# POPULATE THIS from your own max_bullets settings in auto_prep.py after your first prep run.
# Example: ("acme_corp", None, 5) → expects exactly 5 bullets for any Acme Corp role
# Leave empty ([]) to skip V_ROLES bullet count enforcement.
_EXACT_BULLET_COUNTS: list[tuple] = []


def _expected_bullets(company: str, role: str):
    co = company.lower()
    ro = role.lower()
    for co_key, role_key, count in _EXACT_BULLET_COUNTS:
        if co_key not in co:
            continue
        if role_key is None or role_key in ro:
            return count
    return None


# ── V24 — Role-type framing consistency ──────────────────────────────────────

_EOR_KEYWORDS   = ("eor", "deel", "remote.com")
_VISA_KEYWORDS  = ("visa", "sponsorship", "right to work", "relocat",
                   "kennismigrant", "blue card", "arbetstillstånd",
                   "pay limit scheme", "critical skills permit", "employment visa")


def check_v24_role_type_framing(resume: dict, cover: dict):
    rt = (resume.get("role_type") or cover.get("role_type") or "").lower()
    if not rt:
        _warn("V24 Role-type framing", "role_type absent — cannot validate framing")
        return

    # For contract_remote: cover must NOT mention visa/relocation; address must have EOR
    if rt == "contract_remote":
        cover_text = " ".join(cover.get("paragraphs", [])).lower()
        bad = [kw for kw in _VISA_KEYWORDS if kw in cover_text]
        if bad:
            _fail(
                "V24 Role-type framing (contract_remote)",
                f"Cover letter contains visa/relocation language: {bad}",
                "Para 4 must use EOR framing only (no visa/relocation). "
                "Check para4_instructions field in auto_cover JSON.",
            )
        else:
            _pass("V24 contract_remote — no visa/relocation language in cover")

        addr = (resume.get("contact", {}) or cover.get("contact", {})).get("address", "").lower()
        if not any(kw in addr for kw in _EOR_KEYWORDS):
            _fail(
                "V24 Role-type framing (contract_remote address)",
                f"Contact address does not contain EOR/Deel/Remote.com: {addr!r}",
                "auto_prep.py should set contact['address'] = _EOR_ADDRESS for contract roles.",
            )
        else:
            _pass("V24 contract_remote — EOR address present")

    # For non-contract_remote: cover must NOT contain EOR/Deel; address must NOT have EOR
    else:
        cover_text = " ".join(cover.get("paragraphs", [])).lower()
        bad_eor = [kw for kw in _EOR_KEYWORDS if kw in cover_text]
        if bad_eor:
            _warn(
                "V24 Role-type framing (non-EOR role has EOR language)",
                f"role_type={rt!r} but cover contains: {bad_eor}",
            )
        addr = (resume.get("contact", {}) or cover.get("contact", {})).get("address", "").lower()
        if any(kw in addr for kw in _EOR_KEYWORDS):
            _fail(
                "V24 Role-type framing (wrong address for non-contract_remote)",
                f"EOR address used for role_type={rt!r}: {addr!r}",
                "auto_prep.py should use _VISA_ADDRESS for non-EOR roles.",
            )
        else:
            _pass(f"V24 {rt} — standard address (no EOR)")


def check_vroles_count(resume: dict):
    """Enforce exact role count + bullet counts. Skipped if _EXPECTED_ROLES is None and
    _EXACT_BULLET_COUNTS is empty (default for fresh installs — populate after first prep run)."""
    wh = resume.get("work_history", [])
    n = len(wh)
    if _EXPECTED_ROLES is None and not _EXACT_BULLET_COUNTS:
        _pass("V_ROLES Work history count + bullet counts",
              "skipped — _EXPECTED_ROLES and _EXACT_BULLET_COUNTS not configured "
              "(populate in validate_prep.py after your first prep run)")
        return
    if _EXPECTED_ROLES is not None and n != _EXPECTED_ROLES:
        _fail(
            "V_ROLES Work history count",
            f"work_history has {n} roles — expected {_EXPECTED_ROLES}. "
            "All ROLE_METADATA entries must be present.",
            "NEVER drop roles or bullets to fix 2-page overflow — shorten bullet word "
            "count (≤28 words, RULE 1 in application_prep.md §4b) instead.",
        )
        return  # bullet count check meaningless if role count is wrong

    bullet_issues = []
    for role in wh:
        co       = role.get("company", "")
        ro       = role.get("role", "")
        expected = _expected_bullets(co, ro)
        if expected is None:
            continue  # unknown role — skip
        actual = len(role.get("bullets", []))
        if actual != expected:
            bullet_issues.append(
                f"{co} / {ro}: {actual} bullets (expected {expected})"
            )

    if bullet_issues:
        _fail(
            "V_ROLES Exact bullet counts",
            "\n     ".join(bullet_issues),
            "Each role must have its exact bullet count. Adjust bullet selection in STEP 3.",
        )
    else:
        _pass("V_ROLES Work history count + bullet counts",
              f"{n} roles · all bullet counts correct")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Pre-render prep validation")
    parser.add_argument("--resume",    required=True, help="Path to final resume JSON")
    parser.add_argument("--cover",     required=False, default="",
                        help="Path to final cover letter JSON (optional — cover checks skipped if absent)")
    parser.add_argument("--jd",        default="",    help="Path to JD text file (optional)")
    parser.add_argument("--company",   default="",    help="Company name (optional, for V4)")
    parser.add_argument("--role",      default="",    help="Role title (optional, for V15)")
    parser.add_argument("--meta",      default="",    help="Path to application meta.json (optional, for V19)")
    parser.add_argument("--skip-v10",  action="store_true",
                        help="Skip V10 investment domain check (use when JD is investment-adjacent "
                             "but MF hook correctly omitted due to framing judgement)")
    args = parser.parse_args()

    resume_path = Path(args.resume)
    has_cover   = bool(args.cover)
    cover_path  = Path(args.cover) if has_cover else None

    if not resume_path.exists():
        print(f"ERROR: resume file not found: {resume_path}")
        sys.exit(1)
    if has_cover and not cover_path.exists():
        print(f"ERROR: cover file not found: {cover_path}")
        sys.exit(1)

    try:
        resume = json.loads(resume_path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in resume: {e}")
        sys.exit(1)
    cover = {}
    if has_cover:
        try:
            cover = json.loads(cover_path.read_text())
        except json.JSONDecodeError as e:
            print(f"ERROR: invalid JSON in cover: {e}")
            sys.exit(1)

    jd_text = ""
    if args.jd and Path(args.jd).exists():
        jd_text = Path(args.jd).read_text()

    company = args.company.strip()

    if not has_cover:
        print(f"\n[validate_prep] Pre-render Validation (resume only — cover checks skipped)\n")
    else:
        print(f"\n[validate_prep] Pre-render Validation\n")
    check_v1_ai_fluency(resume)
    check_v2_excluded_tools(resume, cover)
    if has_cover:
        check_v3_word_count(cover)
        check_v4_company_name(cover, company)
    check_v5_mmm_framing(resume, cover, jd_text)
    check_v6_no_fill_me(resume, cover)
    check_v7_metrics(resume, cover)
    check_v8_agile_jira(resume, jd_text)
    check_v9_git_version_control(resume, jd_text)
    if has_cover:
        if args.skip_v10:
            _pass("V10 Investment domain MF check", "skipped via --skip-v10")
        else:
            check_v10_investment_domain(resume, cover, jd_text)
    check_v11_role_quantification(resume)
    if has_cover:
        check_v12_anonymised_company(cover, company)
    check_v13_british_english(resume, cover)
    if has_cover:
        check_v14_contact_info(cover)
        check_v15_role_title(cover, args.role)
        check_v16_ai_project_framing(resume, cover)
    check_v17_s1_industry(resume)
    check_v18_pronoun(resume)
    if has_cover:
        check_v19_values_alignment(cover, args.meta)
    check_v20_bullet_length(resume)
    check_v21_jd_skills_coverage(resume, jd_text)
    check_v22_bullet_integrity(resume, str(resume_path))
    check_v23_leading_verbs(resume)
    if has_cover:
        check_v24_role_type_framing(resume, cover)
    check_v_lead(resume)
    check_vroles_count(resume)

    total = len(PASSED) + len(FAILED) + len(WARNED)
    print()
    if not FAILED:
        warn_note = f", {len(WARNED)} warning(s)" if WARNED else ""
        print(f"  ✓ All {len(PASSED)} checks passed{warn_note} — safe to render PDFs")
    else:
        print(f"  ✗ {len(FAILED)} of {total} checks FAILED — fix before rendering")
    print()
    sys.exit(0 if not FAILED else 1)


if __name__ == "__main__":
    main()
