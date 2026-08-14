#!/usr/bin/env python3
"""
score_jobs.py — Semantic job scorer using Claude API (Haiku)
============================================================
Two-pass architecture:
  Pass 1 (free, ~0ms): Python pre-filter using ONLY native LinkedIn/Apify
    metadata fields (poster-declared, reliable, no JD text interpretation).
    Rejection hierarchy (most objective first):
    1. posted_date      → reject if >30d old; track as Stale if >3d old
    2. work_type        → reject if LinkedIn marks as Remote-only
    3. job_type         → reject if LinkedIn marks as Contract/Part-time
    4. salary (native)  → reject only if LinkedIn-provided AND clearly below £80k
    5. location         → reject if outside Tier 1/2/3
    6. job_title        → hard-reject title list (last: lets other gates fire first)
    - Duplicate check   → jd_url exact match OR fuzzy company+role match
    Note: Visa sponsorship requires JD text reading → Pass 2 only.

  Pass 2 (~$0.027/run): Claude Haiku semantic scoring for jobs that survive
    Pass 1. Receives raw LinkedIn native fields + full JD description.
    Claude is authoritative for: salary extraction, visa sponsorship,
    work mode, contract detection, remote detection, agency post detection,
    ATS type identification. No heuristic pre-processed values are passed.

Usage:
  python3 scripts/score_jobs.py                   # default
  python3 scripts/score_jobs.py --model sonnet    # higher quality (more expensive)
  python3 scripts/score_jobs.py --no-prefilter    # skip Pass 1 (debug)
  python3 scripts/score_jobs.py --max-age 14      # reject postings older than 14 days
  python3 scripts/score_jobs.py --dry-run         # score but don't write to disk

Output:
  data/scored_jobs.json     — shortlisted + review jobs (input to tracker writer)
  data/auto_rejected.json   — updated with rejected jobs (persistent history)
"""

import json, re, sys, time
from collections import defaultdict
from pathlib import Path
from datetime import datetime, date
from typing import Optional
from urllib import request as _ureq, error as _uerr

# ── Sponsor register (UK Home Office / NL IND) ────────────────────────────────

ROOT              = Path(__file__).parent.parent
ENRICHED_PATH     = ROOT / "data" / "pipeline" / "enriched_scrape_output.json"
TRACKER_PATH      = ROOT / "data" / "job_tracker.json"
AUTO_REJ_PATH     = ROOT / "data" / "auto_rejected.json"
SCORED_PATH       = ROOT / "data" / "pipeline" / "scored_jobs.json"
ENV_FILE          = ROOT / ".env"
JD_TEXT_CACHE_PATH = ROOT / "data" / "jd_text_cache.json"

TODAY = date.today().isoformat()

# ── Shared utilities (single source: scripts/common.py) ──────────────────────
sys.path.insert(0, str(Path(__file__).parent))
from common import (
    load_env,
    extract_job_id_from_url as _extract_job_id_from_url,
    edit_distance as _edit_distance,
    normalize_company as _normalize_company,
    SALARY_THRESHOLDS as _COMMON_SALARY_THRESHOLDS,
    SALARY_THRESHOLDS_REMOTE as _COMMON_SALARY_THRESHOLDS_REMOTE,
    annualise_day_rate as _annualise_day_rate,
    compute_role_type as _compute_role_type,
    ROLE_TYPE_ENUM as _ROLE_TYPE_ENUM,
)

# ── Candidate profile — loaded from candidate_profile.json ───────────────────
def _load_profile() -> dict:
    p = ROOT / "data" / "content" / "candidate_profile.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

_PROFILE          = _load_profile()
_CANDIDATE_NAME   = _PROFILE.get("contact", {}).get("name", "the candidate")
_YEARS_EXP        = _PROFILE.get("profile", {}).get("years_of_experience", 5)
_TARGET_ROLES     = _PROFILE.get("profile", {}).get("target_roles", [])
_CORE_SKILLS_LIST = _PROFILE.get("core_skills", {}).get("skills", [])
_VERBATIM_SENTS   = _PROFILE.get("profile", {}).get("verbatim_sentences", {}).get("sentences", [])
_LANGUAGES        = _PROFILE.get("profile", {}).get("languages", ["English"])

# ── CLI args ──────────────────────────────────────────────────────────────────
_args = sys.argv[1:]
MODEL        = "claude-haiku-4-5-20251001"
NO_PREFILTER    = "--no-prefilter" in _args
DRY_RUN         = "--dry-run" in _args
BATCH_MODE      = "--no-batch" not in _args   # batch is default; pass --no-batch for sync
FORCE_STALE     = "--force-stale" in _args   # re-score stale entries as if fresh
# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Posting Age Thresholds
# Full documentation: CONFIGURE_CHECKLIST.md § score_jobs.py
# ═══════════════════════════════════════════════════════════════
MAX_AGE         = 30   # Hard-reject postings older than this (days). Not tracked.
STALE_AGE_DAYS  = 3    # Default stale threshold. Older = Stale status (tracked but not scored).

# Per-market stale thresholds. Raise for markets with less frequent new postings.
# EXAMPLE: {"uk": 3, "nl": 7, "de": 7, "dk": 7, "ie": 7, "ae": 7, "se": 7}
_STALE_DAYS_BY_MARKET = {"uk": 3, "nl": 7, "se": 7, "de": 7, "dk": 7, "ie": 7, "ae": 7}

def _get_stale_threshold(market: str) -> int:
    return _STALE_DAYS_BY_MARKET.get((market or "uk").lower(), STALE_AGE_DAYS)

if "--model" in _args:
    idx = _args.index("--model")
    MODEL = _args[idx+1] if idx+1 < len(_args) else MODEL
if "--max-age" in _args:
    idx = _args.index("--max-age")
    try: MAX_AGE = int(_args[idx+1])
    except (IndexError, ValueError):
        print("ERROR: --max-age requires a number, e.g. --max-age 7")
        sys.exit(1)
if FORCE_STALE:
    # Raise stale threshold so >3d manual jobs pass the age gate, and mark
    # the flag so _build_existing_pool excludes current Stale entries from dedup.
    STALE_AGE_DAYS = 30
    for _m in _STALE_DAYS_BY_MARKET:
        _STALE_DAYS_BY_MARKET[_m] = 30

# ── Standalone stale-sweep mode (no enriched data needed) ────────────────────
if "--recategorize-stale" in _args:
    _raw  = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {"applications": []}
    _apps = _raw.get("applications", [])
    _today = date.today()
    _today_str = _today.isoformat()
    _count = 0
    for _app in _apps:
        if _app.get("status") not in {"Shortlisted", "Review Needed"}:
            continue
        _pd = _app.get("posted_date") or ""
        _m  = re.match(r"(\d{4}-\d{2}-\d{2})", str(_pd))
        if not _m:
            continue
        try:
            _age = (_today - date.fromisoformat(_m.group(1))).days
        except ValueError:
            continue
        _thr2 = _get_stale_threshold(_app.get("market", "uk"))
        if _age <= _thr2:
            continue
        _old = _app["status"]
        _app["status"] = "Stale"
        _app.setdefault("status_history", []).append({
            "status": "Stale", "date": _today_str,
            "source": "score_jobs_stale_sweep",
            "reason": f"Retroactive: posting now {_age}d old (>{_thr2}d threshold)",
        })
        print(f"  [stale-sweep] {_app.get('company')} / {_app.get('role')} "
              f"({_old} → Stale, age={_age}d)")
        _count += 1
    if _count and not DRY_RUN:
        _raw["applications"] = _apps
        TRACKER_PATH.write_text(json.dumps(_raw, indent=2, ensure_ascii=False))
    print(f"\n[score_jobs] Stale sweep complete: {_count} entries updated.")
    sys.exit(0)

# ── Load data ─────────────────────────────────────────────────────────────────
if not ENRICHED_PATH.exists():
    print(f"ERROR: {ENRICHED_PATH} not found. Run python3 scripts/run_scout.py first.")
    sys.exit(1)

enriched    = json.loads(ENRICHED_PATH.read_text())
tracker_raw = json.loads(TRACKER_PATH.read_text()) if TRACKER_PATH.exists() else {"applications": []}
tracker     = tracker_raw.get("applications", [])

auto_rej_raw = {"auto_rejected": []}
if AUTO_REJ_PATH.exists():
    try:
        auto_rej_raw = json.loads(AUTO_REJ_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        # Continuing with an empty pool would drop ~4k entries from the dedup
        # pool and mass re-score already-rejected jobs (real API cost).
        print(f"[score_jobs] FATAL: auto_rejected.json exists but cannot be read ({e}).")
        print(f"[score_jobs] Fix or restore the file before re-running (git checkout data/auto_rejected.json).")
        sys.exit(1)
auto_rejected = auto_rej_raw.get("auto_rejected", [])

# ── Auto-flush guard ──────────────────────────────────────────────────────────
# scored_jobs.json is OVERWRITTEN on every run. If it still has unprocessed
# entries from a previous run, auto-flush them via write_tracker.py now before
# they are lost. This prevents the silent data-loss / wasted re-score failure mode.
if SCORED_PATH.exists():
    try:
        _prev = json.loads(SCORED_PATH.read_text())
        _prev_jobs = _prev.get("jobs", []) if isinstance(_prev, dict) else _prev
        if _prev_jobs:
            print(f"[score_jobs] ⚠ scored_jobs.json has {len(_prev_jobs)} unprocessed entries "
                  f"— auto-flushing via write_tracker.py before overwrite ...")
            import subprocess as _sp
            _r = _sp.run(
                [sys.executable, str(ROOT / "scripts" / "write_tracker.py")],
                capture_output=False, text=True
            )
            if _r.returncode != 0:
                print(f"[score_jobs] ERROR: write_tracker.py failed (exit {_r.returncode}). "
                      f"Fix before re-running to avoid data loss.")
                sys.exit(1)
            print(f"[score_jobs] ✓ Auto-flush complete — proceeding with fresh scoring run.\n")
    except (json.JSONDecodeError, OSError):
        pass  # Unreadable file — safe to overwrite

print(f"\n[score_jobs] ─────────────────────────────────────────")
print(f"[score_jobs] Input:        {len(enriched)} enriched jobs")
print(f"[score_jobs] Tracker:      {len(tracker)} existing entries (duplicate check)")
print(f"[score_jobs] Auto-rejected:{len(auto_rejected)} historical rejects (duplicate check)")
print(f"[score_jobs] Model:        {MODEL}")
print(f"[score_jobs] Max age:      {MAX_AGE} days")
print(f"[score_jobs] Pre-filter:   {'disabled' if NO_PREFILTER else 'enabled (native fields only)'}")
print(f"[score_jobs] ─────────────────────────────────────────\n")

# ─────────────────────────────────────────────────────────────────────────────
# PASS 1 — Native LinkedIn metadata gates (no API cost, no JD text parsing)
# ─────────────────────────────────────────────────────────────────────────────

TIER1 = {
    "london",
    # Inner London areas LinkedIn sometimes reports without "London" in the string
    "hammersmith", "paddington", "farringdon", "acton", "tottenham", "twickenham",
}
TIER2 = {
    "manchester", "birmingham", "leeds", "reading", "milton keynes",
    "cambridge", "oxford", "leicester", "coventry", "nottingham", "northampton",
    # Manchester satellites (≤35 min)
    "salford", "warrington", "liverpool",
    # Leeds satellites (≤25 min)
    "bradford", "york",
    # Birmingham satellites (≤15 min)
    "solihull",
    # London commuter belt (≤35 min to London)
    "welwyn garden city", "st albans", "hatfield",
}
TIER3 = {
    "bristol", "brighton", "luton", "watford", "slough", "guildford",
    # London commuter belt (≤45 min)
    "woking", "newbury", "uxbridge", "hayes",
    # Midlands / North (strong employer presence)
    "derby", "sheffield", "cheltenham",
    # South coast
    "southampton",
}
# UK vague region strings — can't reject on location, pass to Claude for scoring.
# Must be exact or province-level (not specific-city + province combos).
_UK_COUNTRY_LEVEL = {"england", "united kingdom", "great britain", "england, united kingdom"}
# UK regions that contain Tier 1/2 cities — pass through; reject devolved nations explicitly.
_UK_REGIONS_WITH_TIERS = {"west yorkshire", "greater manchester", "west midlands"}
_UK_REJECT_NATIONS    = {"scotland", "wales", "northern ireland", "cymru"}
ALL_TIERS = TIER1 | TIER2 | TIER3

# ── NL / SE tier cities ───────────────────────────────────────────────────────
NL_TIER1 = {
    "amsterdam", "rotterdam", "den haag", "the hague", "utrecht",
    "randstad",    # LinkedIn region string covering the full Randstad cluster
    # Amsterdam metro (≤25 min)
    "amstelveen", "hoofddorp", "schiphol", "haarlem", "diemen",
    "zaandam", "weesp", "lijnden", "nieuw-vennep",
    # Rotterdam/Den Haag metro satellites (≤25 min)
    "schiedam", "zoetermeer", "maassluis", "dordrecht", "rijswijk",
    "delft", "nootdorp", "pijnacker", "barendrecht",
    # Between Hague and Amsterdam (Leiden corridor)
    "leiden", "oegstgeest",
    # Amsterdam commuter (≤40 min) — media/tech cluster
    "hilversum",
    # Utrecht commuter (≤35 min) — Wolters Kluwer, Unica
    "hoevelaken",
}
# NL vague region pass-throughs — province contains tier-1 city, or country-only.
_NL_TIER1_PROVINCES = {"south holland", "north holland"}  # contain Rotterdam/Den Haag and Amsterdam
_NL_COUNTRY_ONLY    = {"netherlands"}  # exact country string — no city info, pass to Claude
SE_TIER1 = {
    "stockholm", "gothenburg", "göteborg", "malmo", "malmö",
    "solna",     # Stockholm County, immediately north of Stockholm
    "mölndal",   # Adjacent to Gothenburg, same labour market
    # Malmö satellites (≤20 min)
    "lund", "burlöv", "burlövs",
    # Stockholm commuter city (40 min by train)
    "uppsala",
}
# SE vague region pass-throughs
_SE_PASSTHROUGH = {"sweden", "sverige", "västra götaland", "västra götalands"}
DE_TIER1 = {
    "berlin", "munich", "münchen", "frankfurt", "hamburg",
    "düsseldorf", "dusseldorf", "cologne", "köln", "koeln",
    # Frankfurt Rhine-Main satellites (≤25 min)
    "mainz", "wiesbaden", "kronberg", "schwalbach", "eschborn",
    # Düsseldorf/Ruhr metro (≤50 min)
    "essen", "duisburg", "dortmund", "bochum",
    # Cologne metro (≤25 min)
    "bonn", "leverkusen",
    # Munich satellites (≤60 min)
    "gilching", "nuremberg", "nürnberg",
    # Hamburg satellites (≤60 min)
    "bremen",
    # Berlin satellites (≤90 min)
    "leipzig",
    # Major regional hubs (Tier 3 — pass gate, Claude scores 4)
    "stuttgart", "ludwigsburg", "karlsruhe",
    "hannover",
}
# DE vague region pass-throughs — country-level only (German provinces too large to infer tier)
_DE_COUNTRY_ONLY = {"germany", "deutschland"}

# ── AE tier cities (added 2026-08-01) ────────────────────────────────────────
AE_TIER1 = {
    "dubai",
    # Dubai satellites / business districts (all score 10 in Claude)
    "jumeirah", "jebel ali", "deira", "bur dubai", "al barsha",
    "business bay", "downtown dubai", "dubai marina", "jlt",
    "jumeirah lake towers", "difc", "dubai internet city",
    "dubai media city", "tecom", "sheikh zayed road",
    # Dubai adjacent / UAE metro (score 6 in Claude)
    "sharjah", "ajman",
    # Second city — Abu Dhabi (score 8 in Claude)
    "abu dhabi", "abudhabi",
    # Abu Dhabi districts
    "al reem island", "masdar city", "adgm",
}
# AE country-only strings — exact match; non-tier cities are P1-rejected.
_AE_COUNTRY_ONLY = {"united arab emirates", "uae", "emirates"}

# ── Residency/location eligibility gate ──────────────────────────────────────
# Fires on ALL markets. If a JD explicitly states that applicants must already be
# living/residing in the EU, UK, or target country, the candidate cannot qualify
# regardless of visa sponsorship. One phrase match → P1-REJECT.
# Phrases are English-only; non-English JDs are already rejected by language gates.
_RESIDENCY_EXCLUSION_PHRASES = [
    # "living outside [geography]" — always candidate-specific, never about company location
    "living outside the european union",
    "living outside the eu",
    "living outside europe",
    "living outside the uk",
    "living outside the united kingdom",
    "living outside the netherlands",
    "living outside germany",
    "living outside sweden",
    "living outside denmark",
    "living outside ireland",
    "living outside the uae",
    "applicants living outside",   # safe catch-all: "applicants living outside [any country]"
    "candidates living outside",
    # "residing outside" variants
    "residing outside the eu",
    "residing outside the uk",
    "residing outside europe",
    "applicants residing outside",
    "candidates residing outside",
    # Direct "we don't / do not hire" + location
    "don't hire applicants living",
    "do not hire applicants living",
    "don't hire candidates living",
    "do not hire candidates living",
    "don't hire applicants outside",
    "do not hire applicants outside",
    "don't hire candidates outside",
    "do not hire candidates outside",
    # Must-be-currently-in (candidate residency pre-requirement)
    "must currently reside in",
    "must currently live in",
    "must already reside in",
    "must already live in",
    "must already be based in",
    # "Residents only" — explicit eligibility restriction
    "eu residents only",
    "uk residents only",
    "european residents only",
    "european union residents only",
    # Cannot / unable to consider outside applicants
    "cannot consider applicants from outside",
    "cannot consider candidates from outside",
    "unable to consider applicants from outside",
    "unable to consider candidates from outside",
    "not accept applications from outside",
    "cannot accept applications from outside",
    # Only accepting from [country] — explicit eligibility
    "only accepting applications from candidates",
    "only considering applications from candidates",
    "only considering candidates currently based",
    "only considering applicants currently based",
]

# Arabic language requirement phrases (explicit — gate fires on any match)
_ARABIC_PHRASES = [
    "arabic language required", "arabic is required", "arabic is a must",
    "fluent in arabic", "arabic fluency", "business arabic",
    "native arabic speaker", "arabic speaking", "arabic skills required",
    "arabic proficiency required", "must speak arabic",
    "bilingual in arabic", "arabic is mandatory",
]

# UAE visa denial keywords
_VISA_DENIAL_KW_AE = [
    # ── UAE national / residency requirement ────────────────────────────────
    "uae nationals only", "emirati national", "emirati nationals only",
    "must be a uae national", "nationals only",
    "gcc nationals only", "gcc national preferred",
    "must have uae residency", "must already have uae residency",
    "existing uae residency required", "must hold uae residency",
    # ── Right-to-work denial — AE ──────────────────────────────────────────
    "must have the right to work in the uae",
    "must have the right to work in uae",
    "right to work in uae required",
    "must be eligible to work in the uae without sponsorship",
    "must already have a valid uae work permit",
    "existing uae work permit required",
    # ── Sponsorship refusal ─────────────────────────────────────────────────
    "no visa sponsorship available",
    "we do not sponsor work visas",
    "unable to provide visa sponsorship",
    "no employment visa sponsorship",
    "we cannot sponsor",
    "unable to sponsor",
]

# ── DK / IE tier cities (added 2026-07-24) ───────────────────────────────────
DK_TIER1 = {
    "copenhagen", "københavn", "kobenhavn",
    # Copenhagen metro (≤25 min)
    "frederiksberg", "hellerup", "gentofte", "kongens lyngby", "lyngby",
    "ballerup", "søborg", "soborg", "glostrup", "brøndby", "brondby",
    "herlev", "valby", "ørestad", "orestad",
    # Second city (Claude scores 8)
    "aarhus", "århus",
}
# DK country-only strings — exact match (like NL/DE): "Odense, Denmark" must NOT
# pass through on the "denmark" substring; non-tier cities are P1-rejected.
_DK_COUNTRY_ONLY = {"denmark", "danmark"}
# Capital Region contains Copenhagen — substring pass-through (city may be a CPH satellite)
_DK_REGION_SUBSTR = {"region hovedstaden", "capital region"}
IE_TIER1 = {
    "dublin", "county dublin",
    # Dublin metro (≤30 min)
    "dún laoghaire", "dun laoghaire", "sandyford", "leopardstown",
    "blackrock", "swords", "citywest",
    # Regional hubs (Claude scores 8/6)
    "cork", "galway", "limerick",
}
# IE country-only strings — exact match (like NL/DE); Leinster contains Dublin
# so it stays a substring pass-through.
_IE_COUNTRY_ONLY  = {"ireland", "republic of ireland"}
_IE_REGION_SUBSTR = {"leinster"}
# Northern Ireland is UK (different visa) — must NOT pass the ie gate even though
# its location strings contain the substring "ireland".
_IE_REJECT = {"northern ireland", "belfast", "derry", "londonderry"}

# Minimum analytics relevance required before a stale posting is tracked.
# Stale jobs that don't contain any of these substrings are rejected outright —
# there's no value logging "Project Controls Consultant" as Stale.
# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Title Filters
# ═══════════════════════════════════════════════════════════════

# TARGET_TITLE_KEYWORDS: Minimum keywords for stale postings to be worth tracking.
# If a stale job title contains NONE of these, it's silently dropped (not tracked).
# EXAMPLES (analytics): {"analytic", "analyst", "data", "insight"}
# EXAMPLES (software):  {"engineer", "developer", "architect", "programmer"}
# EXAMPLES (finance):   {"finance", "financial", "fp&a", "treasury", "controller"}
# EXAMPLES (product mgmt): {"product", "growth", "platform", "strategy"}
ANALYTICS_TITLE_KW = {
    "analytic", "analyst", "data", "insight",
    "bi manager", "bi lead", "bi director", "decision scientist",
}

# TITLE_REJECT_CONTAINS: Always reject if job title contains any of these strings.
# Remove entries or clear the list to disable. Lower-case, substring match.
# EXAMPLES (analytics): ["engineer", "architect", "director", "data science", "governance"]
# EXAMPLES (software):  ["qa ", "scrum master", "project manager", "business analyst"]
# EXAMPLES (finance):   ["payroll", "accounts payable", "accounts receivable", "bookkeeper"]
TITLE_REJECT_CONTAINS = [
    # ── Broad keyword blocks (each subsumes several specific patterns) ────────
    "engineer",     # data/software/ML/cloud/platform/BI/AI-enablement engineers — not analytics leadership
                    # tradeoff: "Senior Analytics Engineer" (Tier 2 today) — not in target role list,
                    # below seniority target, Gate 6 catches analytics_engineering role_focus anyway
    "architect",    # solutions/data/cloud/analytics architects — not analytics leadership
    "director",     # Director-level roles — above target seniority per CLAUDE.md (VP+)
                    # tradeoff: UK bank "Associate Director" (sometimes Sr Manager equiv) — acceptable
    "governance",   # data/AI governance roles — always non-analytics
    "devops",       # DevOps Manager/Lead beyond "devops engineer"
    # ── Analyst role types that are never target roles ────────────────────────
    "site reliability",
    "hr analyst", "people analyst", "payroll analyst", "payroll manager",
    "paid social", "seo analyst", "seo manager", "digital marketing analyst",
    "cro specialist", "cro consultant", "financial analyst", "finance analyst",
    "bi developer", "etl developer",
    "data science", "scientist", "graduate analyst",
    # ── Non-analytics operational/strategy titles ─────────────────────────────
    "revenue operations manager", "revenue operations lead",    # RevOps = Salesforce/CRM ops
    "business operations manager", "business operations lead",  # BizOps without analytics
    "regional operations manager", "regional operations lead",  # Regional/field ops ≠ analytics (e.g. Uber)
    "product owner",                                            # PO = product management, not analytics leadership
    "project manager", "programme manager",                     # PM ≠ analytics lead; "Project Mgr - AI Enablement" false-fired at 15 pts
    "talent acquisition", "talent partner",                     # HR/recruiting
    "people operations", "people partner",                      # HR
    "commercial transformation",                                # Strategy consulting type
    # ── Accounting / finance domain ───────────────────────────────────────────
    "statutory reporting", "accounts payable", "accounts receivable",
    "financial accountant", "fp&a", "actuarial",
    # ── Supply chain / infrastructure ops ────────────────────────────────────
    "demand manager", "data center operations", "data centre operations",
    # ── Customer success / services ops ──────────────────────────────────────
    "customer success manager",
]

# ── Language detection gate (NL/SE only) ─────────────────────────────────────
# Phrases that indicate the JD requires native Dutch or Swedish proficiency.
# Gate fires when 2+ distinct phrases are found in the first 2,000 chars.
# Threshold of 2 avoids false positives from incidental single mentions.
_DUTCH_PHRASES = [
    "je beschikt over", "wij zoeken", "functie-eisen", "you must speak dutch",
    "dutch language required", "dutch is required", "native dutch", "dutch is a must",
    "beheers je", "in het nederlands", "nederlandstalig", "vloeiend nederlands",
    "dutch fluency", "je werkt", "je hebt",
]
_SWEDISH_PHRASES = [
    "vi söker", "du har", "arbetsuppgifter", "svenska krävs", "swedish is required",
    "swedish language required", "fluent in swedish", "flytande svenska",
    "kräver svenska", "du behärskar svenska", "svenska är ett krav",
]
_DANISH_PHRASES = [
    "vi søger", "du har erfaring", "arbejdsopgaver", "dansk påkrævet",
    "danish is required", "danish language required", "fluent in danish",
    "danish fluency", "flydende dansk", "danish is a must", "native danish",
    "vi tilbyder", "dine opgaver", "du er", "dansk er et krav",
    "behersker dansk", "på dansk",
]
# Title-level language words — unambiguous non-English words that only appear in
# Dutch/Swedish job titles. One match in the title is sufficient to reject (titles
# are short; a non-English word in a title is a strong signal the role requires fluency).
_DUTCH_TITLE_WORDS   = ["strategisch", "analist", "hoofd", "medewerker", "adviseur", "bedrijfsanalist"]
_SWEDISH_TITLE_WORDS = ["analytiker", "ansvarig", "ingenjör"]
# Danish title words — "analytiker" shared with Swedish (both Scandinavian); gates are
# per-market so no cross-fire. "chef" (Danish for manager/head) deliberately excluded —
# too ambiguous with English in compound titles.
_DANISH_TITLE_WORDS  = ["analytiker", "leder", "medarbejder", "chefkonsulent", "rådgiver",
                        "forretningsanalytiker"]

# ── German language detection ─────────────────────────────────────────────────
# Layer 1: explicit "German required" phrases (English JDs signalling German needed)
_GERMAN_PHRASES = [
    "german language required", "german is required", "german is a must",
    "fluent in german", "german fluency", "business german",
    "native german", "german speaking", "german skills required",
    "german skills preferred", "german is preferred", "advantage: german",
    "you speak german", "daily business in german",
    # proficiency/knowledge phrasing (Google-style, softer but still disqualifying)
    "proficiency in german", "german language proficiency", "german proficiency",
    "knowledge of german", "german language skills", "working knowledge of german",
    "german would be", "german is an advantage", "german is a plus",
    "german is beneficial", "preferred: german", "nice to have: german",
    "ability to speak german",
    # German-language phrases
    "deutsch ist erforderlich", "deutschkenntnisse", "gute deutschkenntnisse",
    "sehr gute deutschkenntnisse", "verhandlungssicheres deutsch",
    "muttersprachler", "fließend deutsch",
]
# Layer 2: common German function words — detects if JD is written IN German
_GERMAN_FUNCTION_WORDS = {
    "und", "oder", "nicht", "haben", "sein", "werden", "können",
    "müssen", "sollen", "wir", "das", "die", "der", "ein", "eine",
    "für", "mit", "von", "zur", "zum", "bei", "nach", "über",
    "als", "auch", "noch", "dann", "wenn", "aber", "doch",
}
# Layer 3: German title words — detects if JOB TITLE is written in German
_GERMAN_TITLE_WORDS = [
    "analytiker", "leiter", "referent", "sachbearbeiter",
    "kaufmännisch", "geschäfts", "vertrieb", "stellenleiter",
]

# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Market Brand Allowlist
# ═══════════════════════════════════════════════════════════════
# For restrictive markets where you ONLY want to apply to specific companies.
# Use a market code as key, set of allowed company names (lowercase) as value.
# Leave empty dict for a market to allow all companies in that market.
# EXAMPLE (Sweden whitelist): {"se": {"spotify", "klarna", "ikea", "h&m", "volvo"}}
# EXAMPLE (no restrictions):  {} (empty dict = all markets open)
_MARKET_BRAND_ALLOWLIST: dict[str, set] = {
    # Replace with your own allowlist, or leave empty:
    "se": {"spotify", "klarna", "volvo cars", "ericsson", "king", "epidemic sound", "scania"},
}
_SE_ALLOWED = _MARKET_BRAND_ALLOWLIST.get("se", set())  # backward-compat alias

# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Company Exceptions
# ═══════════════════════════════════════════════════════════════
# Companies that mislabel YOUR target roles as "Data Science" in titles.
# Their "Data Scientist" posts still go to Pass 2 scoring.
# EXAMPLE: {"company_a", "company_b"} — add any company that does this.
_ANALYTICS_NAMED_DS_COMPANIES: set[str] = set()

# Companies whose LinkedIn job_type = "temporary" is a false positive.
# They include policy text like "Temporary work from abroad" in every JD,
# but the roles are genuinely permanent.
# EXAMPLE: {"company_x"} — add companies where you see this issue.
_PERMANENT_DESPITE_JOB_TYPE: set[str] = set()

# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Company Type Blocklist
# ═══════════════════════════════════════════════════════════════
# Fast-reject companies whose structure always produces role types you don't want.
# Saves Pass 2 API cost (~$0.005/job). Conservative: only add if you are sure.
# EXAMPLES (non-consulting seekers): {"mckinsey", "bcg", "bain & company", "deloitte"}
# EXAMPLES (direct-hire only):       {"harnham", "michael page", "hays", "robert half"}
# Leave empty to allow all company types.
_CONSULTING_BLOCKLIST_SUBSTRINGS: set[str] = {
    "deloitte",
    "pwc", "pricewaterhousecoopers",
    "kpmg",
    "mckinsey",
    "boston consulting group",
    "roland berger",
    "oliver wyman",
    "bain & company", "bain and company",
    "kearney",
    "arthur d. little", "arthur d little",
}
# EY handled separately — "ey" is too short for a substring match (false-positives).
_EY_EXACT      = {"ey", "ey-parthenon"}
_EY_SUBSTRINGS = ("ernst & young", "ernst and young", "ernst&young")

def _is_mgmt_consulting_company(company_name: str) -> bool:
    co = company_name.lower().strip()
    if any(s in co for s in _CONSULTING_BLOCKLIST_SUBSTRINGS):
        return True
    if co in _EY_EXACT or any(p in co for p in _EY_SUBSTRINGS):
        return True
    return False

# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Primary Tooling Title Blocklist
# ═══════════════════════════════════════════════════════════════
# Auto-reject if job TITLE starts with any of these tool-first keywords.
# Use for roles where a specific tool IS the entire job (not just mentioned in JD).
# EXAMPLES (analytics): ["sap analyst", "sap bi analyst", "powerbi analyst", "tableau developer"]
# EXAMPLES (software):  ["cobol developer", "fortran programmer", "mainframe developer"]
# EXAMPLES (finance):   ["sap fi consultant", "oracle financials analyst"]
_SAP_PRIMARY_TITLE_KW = [
    "sap analyst", "sap data analyst", "sap bi analyst", "sap bi developer",
    "sap reporting analyst", "sap functional analyst", "sap hana analyst",
]

# ── classify_title import for Tier-4 Pass 1 gate ─────────────────────────────
# Reuses the deterministic title classifier from classify_title.py.
# Gate fires when pts == 5 (Tier 4 — non-senior, non-lead BA/DA roles).
# Wrapped in try/except so a missing file silently skips the gate.
try:
    import importlib.util as _ilu_ct
    _ct_spec = _ilu_ct.spec_from_file_location(
        "classify_title", Path(__file__).parent / "classify_title.py"
    )
    _ct_mod = _ilu_ct.module_from_spec(_ct_spec)
    _ct_spec.loader.exec_module(_ct_mod)
    _classify_title = _ct_mod.classify_title
except Exception:
    _classify_title = None  # safe fallback — gate skipped if import fails

# Pass 1 keyword gates — high-confidence, low false-positive phrases in JD description.
# These are unambiguous objective signals that don't require semantic interpretation.

_VISA_DENIAL_KW = [
    # ── Explicit sponsorship refusal ─────────────────────────────────────────
    "cannot sponsor",
    "unable to sponsor",
    "no visa sponsorship",
    "visa sponsorship is not available",
    "visa sponsorship is not provided",
    "sponsorship is not available",
    "sponsorship cannot be provided",
    "sponsorship will not be provided",
    "cannot provide visa sponsorship",
    "we cannot provide visa sponsorship",
    "we do not offer sponsorship",
    "we are unable to offer sponsorship",
    "we are unable to provide visa sponsorship",
    "we cannot offer sponsorship",
    "we are not in a position to sponsor",
    "unfortunately we are unable to sponsor",
    "no work visa sponsorship",
    "no sponsorship available",
    "sponsorship not available",
    "no relocation or visa sponsorship",
    "work permit sponsorship is not available",
    # ── Right-to-work denial phrases — UK ───────────────────────────────────
    "must have the right to work in the uk without sponsorship",
    "must already have the right to work in the uk",
    "must already hold the right to work",
    "applicants must have the right to work in the uk",
    "you must have the right to work in the uk",
    "candidates must have the right to work in the uk",
    "right to work in the uk is required",
    "right to work in the united kingdom is required",
    "must be eligible to work in the uk without",
    "existing right to work in the uk",
    "must have legal right to work in the uk",
    "must hold a valid right to work in the uk",
    "must hold the right to work in the uk",
    # ── LinkedIn checkbox-style fields ───────────────────────────────────────
    "authorized to work in the united kingdom",
    "authorised to work in the united kingdom",
    "authorized to work in the uk",
    "authorised to work in the uk",
    "authorization to work in the uk",
    "authorisation to work in the uk",
    "must be authorized to work in",
    "must be authorised to work in",
    # ── EU/EEA citizenship requirement — UK roles ────────────────────────────
    "eu/eea candidates only",
    "eu or eea candidates only",
    "eu/eea citizens only",
    "eu or eea citizens only",
    "must be an eu citizen",
    "must be an eu/eea citizen",
    "must hold eu citizenship",
    "eu citizenship required",
    "eu/eea citizenship required",
]

# Netherlands — phrases that unambiguously deny non-EU applicants or refuse sponsorship
_VISA_DENIAL_KW_NL = [
    # ── Right-to-work denial — NL ────────────────────────────────────────────
    "must have the right to work in the netherlands",
    "must already have the right to work in the netherlands",
    "existing right to work in the netherlands",
    "right to work in the netherlands is required",
    "must have legal right to work in the netherlands",
    "must have existing right to work in the netherlands",
    "must be eligible to work in the netherlands without",
    "eligible to work in the netherlands without a work permit",
    # ── Authorization to work — NL ───────────────────────────────────────────
    "must be authorized to work in the netherlands",
    "must be authorised to work in the netherlands",
    "authorized to work in the netherlands",
    "authorised to work in the netherlands",
    "dutch work authorization required",
    "dutch work authorisation required",
    "must have valid dutch work authorization",
    "must have valid dutch work authorisation",
    # ── EU/EEA citizenship requirement ──────────────────────────────────────
    "eu/eea candidates only",
    "eu or eea candidates only",
    "eu/eea citizens only",
    "eu or eea citizens only",
    "must be an eu citizen",
    "must be an eu/eea citizen",
    "must hold eu citizenship",
    "eu citizenship required",
    "eu/eea citizenship required",
    # ── Work permit refusal — NL ─────────────────────────────────────────────
    "no ind sponsorship",
    "cannot sponsor ind applications",
    "no sponsorship for highly skilled migrant",
    "no sponsorship for a highly skilled migrant permit",
    "cannot sponsor a highly skilled migrant permit",
    "cannot sponsor a work permit",
    "no work permit sponsorship",
    "we do not sponsor work permits",
    "we cannot sponsor a work permit",
    "no work permit support",
    "we are unable to support visa applications",
    "we cannot assist with work permit applications",
    "must have valid dutch residency",
    "must have dutch residency",
    # ── EU work authorization ────────────────────────────────────────────────
    "eu work permit required",
    "eu work permit is required",
    "must hold an eu work permit",
    "must have eu work authorization",
    "must have eu work authorisation",
]

# Sweden — phrases that unambiguously deny non-EU applicants or refuse sponsorship
_VISA_DENIAL_KW_SE = [
    # ── Right-to-work denial — SE ────────────────────────────────────────────
    "must have the right to work in sweden",
    "must already have the right to work in sweden",
    "existing right to work in sweden",
    "right to work in sweden is required",
    "must have legal right to work in sweden",
    "must be eligible to work in sweden without",
    "eligible to work in sweden without a work permit",
    # ── Authorization to work — SE ───────────────────────────────────────────
    "must be authorized to work in sweden",
    "must be authorised to work in sweden",
    "authorized to work in sweden",
    "authorised to work in sweden",
    "swedish work authorization required",
    "swedish work authorisation required",
    "must have valid swedish work authorization",
    "must have valid swedish work authorisation",
    # ── EU/EEA citizenship requirement ──────────────────────────────────────
    "eu/eea candidates only",
    "eu or eea candidates only",
    "eu/eea citizens only",
    "eu or eea citizens only",
    "must be an eu citizen",
    "must be an eu/eea citizen",
    "must hold eu citizenship",
    "eu citizenship required",
    "eu/eea citizenship required",
    # ── Work permit refusal — SE ─────────────────────────────────────────────
    "swedish work permit required",
    "must hold a valid swedish work permit",
    "must have a valid swedish work permit",
    "cannot sponsor arbetstillstånd",
    "cannot sponsor a work permit",
    "no work permit sponsorship",
    "we do not sponsor work permits",
    "we cannot sponsor a work permit",
    "no work permit support",
    "we are unable to support visa applications",
    "we cannot assist with work permit applications",
    "must have swedish residency",
    # ── EU work authorization ────────────────────────────────────────────────
    "eu work permit required",
    "eu work permit is required",
    "must hold an eu work permit",
    "must have eu work authorization",
    "must have eu work authorisation",
    "must have valid eu work authorization",
    "must have valid eu work authorisation",
]

# Germany — phrases that unambiguously deny sponsorship for non-EU applicants
_VISA_DENIAL_KW_DE = [
    # ── Right-to-work denial — DE ────────────────────────────────────────────
    "must have the right to work in germany",
    "right to work in germany without sponsorship",
    "must be authorized to work in germany",
    "must be authorised to work in germany",
    "unrestricted right to work in germany",
    "valid german work permit required",
    "must hold a valid german work permit",
    # ── EU/EEA citizenship requirement ──────────────────────────────────────
    "eu/eea candidates only",
    "eu citizenship required",
    "german citizenship required",
    "must hold eu passport",
    "must have eu work authorization",
    "must have eu work authorisation",
    # ── Blue Card / sponsorship refusal ─────────────────────────────────────
    "no visa sponsorship available",
    "we cannot sponsor",
    "unable to sponsor",
    # ── German-language denial phrases ──────────────────────────────────────
    "arbeitserlaubnis nicht möglich",
    "keine aufenthaltserlaubnis",
    "wir übernehmen keine visumkosten",
]

# Denmark — phrases that unambiguously deny sponsorship for non-EU applicants
_VISA_DENIAL_KW_DK = [
    # ── Right-to-work denial — DK ────────────────────────────────────────────
    "must have the right to work in denmark",
    "right to work in denmark without sponsorship",
    "existing right to work in denmark",
    "must be authorized to work in denmark",
    "must be authorised to work in denmark",
    "valid danish work permit required",
    "must hold a valid danish work permit",
    "must have danish residency",
    # ── EU/EEA/Nordic citizenship requirement ────────────────────────────────
    "eu/eea candidates only",
    "eu or eea citizens only",
    "eu/eea citizens only",
    "eu citizenship required",
    "eu/eea citizenship required",
    "danish citizenship required",
    "nordic citizens only",
    "must hold eu passport",
    "must have eu work authorization",
    "must have eu work authorisation",
    # ── Work permit / sponsorship refusal — DK ──────────────────────────────
    "no work permit sponsorship",
    "we do not sponsor work permits",
    "we cannot sponsor a work permit",
    "cannot sponsor a work permit",
    "we are unable to support visa applications",
    "we cannot assist with work permit applications",
    # ── Danish-language denial phrases ──────────────────────────────────────
    "skal have arbejdstilladelse",
    "kræver dansk arbejdstilladelse",
]

# Ireland — phrases that unambiguously deny sponsorship for non-EU applicants
_VISA_DENIAL_KW_IE = [
    # ── Right-to-work denial — IE ────────────────────────────────────────────
    "must have the right to work in ireland",
    "must already have the right to work in ireland",
    "existing right to work in ireland",
    "right to work in ireland is required",
    "must be eligible to work in ireland without",
    "eligible to work in ireland without sponsorship",
    "must be authorized to work in ireland",
    "must be authorised to work in ireland",
    "authorised to work in ireland",
    # ── Irish immigration stamp requirements (existing residency only) ──────
    "stamp 4 required",
    "stamp 4 visa holders only",
    "hold a stamp 4",
    "stamp 1g",
    # ── EU/EEA citizenship requirement ──────────────────────────────────────
    "eu/eea candidates only",
    "eu or eea citizens only",
    "eu/eea citizens only",
    "eu citizenship required",
    "eu/eea citizenship required",
    "must hold eu passport",
    "eu passport holders only",
    "must have eu work authorization",
    "must have eu work authorisation",
    # ── Employment permit / sponsorship refusal — IE ────────────────────────
    "no employment permit sponsorship",
    "we do not sponsor employment permits",
    "cannot sponsor an employment permit",
    "we are unable to sponsor",
    "unable to provide visa sponsorship",
    "no critical skills sponsorship",
]

_CONTRACT_KW = [
    "day rate",
    "day-rate",
    " ir35",        # leading space avoids matching e.g. "their35"
    "ir35 ",
    "ir35,",
    "ir35.",
    "inside ir35",
    "outside ir35",
    "fixed-term contract",
    "fixed term contract",
    " ftc ",        # fixed term contract abbreviation
    "(ftc)",
    "interim role",
    "interim position",
    "interim contract",
    "6-month contract",
    "12-month contract",
    "6 month contract",
    "12 month contract",
    "6month contract",
    "12month contract",
    "duration of the contract",
    "contract duration",
    "contract period of",
    "contract will be ",
    "this is a contract",
    "this role is a contract",
    "offered on a contract",
    "on a fixed term",
    "on a fixed-term",
]

_REMOTE_ONLY_KW = [
    "100% remote",
    "fully remote",
    "remote only",
    "remote-only",
    "permanently remote",
    "entirely remote",
    "all remote",
    "completely remote",
]


def _location_in_tiers(location_str: str, market: str = "uk") -> tuple[bool, str]:
    """Returns (passes, tier_name). Reads native LinkedIn location field."""
    loc = location_str.lower().strip()
    if market == "nl":
        for city in NL_TIER1:
            if city in loc: return True, "nl_tier1"
        # Province containing tier-1 cities (Rotterdam/Den Haag, Amsterdam)
        if any(p in loc for p in _NL_TIER1_PROVINCES): return True, "nl_province"
        # Country-only string: no city info — pass to Claude for scoring
        if loc in _NL_COUNTRY_ONLY: return True, "nl_country"
        return False, "outside"
    if market == "se":
        for city in SE_TIER1:
            if city in loc: return True, "se_tier1"
        # Country or Västra Götaland region (contains Gothenburg)
        if any(r in loc for r in _SE_PASSTHROUGH): return True, "se_region"
        return False, "outside"
    if market == "de":
        for city in DE_TIER1:
            if city in loc: return True, "de_tier1"
        # Country-only string — pass to Claude (Claude scores 0 for unknown city)
        if loc in _DE_COUNTRY_ONLY: return True, "de_country"
        return False, "outside"
    if market == "dk":
        for city in DK_TIER1:
            if city in loc: return True, "dk_tier1"
        # Country-only string (exact) — no city info, pass to Claude
        if loc in _DK_COUNTRY_ONLY: return True, "dk_country"
        # Capital Region (contains Copenhagen satellites) — pass to Claude
        if any(r in loc for r in _DK_REGION_SUBSTR): return True, "dk_region"
        return False, "outside"
    if market == "ie":
        # Northern Ireland is UK — reject BEFORE any "ireland" matching
        if any(n in loc for n in _IE_REJECT): return False, "northern_ireland"
        for city in IE_TIER1:
            if city in loc: return True, "ie_tier1"
        # Country-only string (exact) — no city info, pass to Claude
        if loc in _IE_COUNTRY_ONLY: return True, "ie_country"
        # Leinster (contains Dublin) — pass to Claude
        if any(r in loc for r in _IE_REGION_SUBSTR): return True, "ie_region"
        return False, "outside"
    if market == "ae":
        for city in AE_TIER1:
            if city in loc: return True, "ae_tier1"
        # Country-only string (exact) — no city info, pass to Claude
        if loc in _AE_COUNTRY_ONLY: return True, "ae_country"
        return False, "outside"
    # UK — check devolved nations first (always reject)
    if any(n in loc for n in _UK_REJECT_NATIONS): return False, "devolved_nation"
    for city in TIER1:
        if city in loc: return True, "tier1"
    for city in TIER2:
        if city in loc: return True, "tier2"
    for city in TIER3:
        if city in loc: return True, "tier3"
    # Exact country/England-level string — no city info, pass to Claude
    if loc in _UK_COUNTRY_LEVEL: return True, "uk_country"
    # Region string containing a Tier 1/2 city — pass to Claude
    if any(r in loc for r in _UK_REGIONS_WITH_TIERS): return True, "uk_region"
    return False, "outside"


def _posting_age_days(posted_date: str) -> Optional[int]:
    """Return how many days ago the job was posted, or None if unparseable."""
    if not posted_date:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(posted_date))
    if not m:
        return None
    try:
        return (date.today() - date.fromisoformat(m.group(1))).days
    except ValueError:
        return None


def _posting_too_old(posted_date: str) -> bool:
    """True if the posting is older than MAX_AGE days (hard-reject, don't track)."""
    age = _posting_age_days(posted_date)
    return age is not None and age > MAX_AGE


def _posting_is_stale(posted_date: str, threshold: int = STALE_AGE_DAYS) -> bool:
    """True if the posting is older than threshold days but within MAX_AGE (track as Stale)."""
    age = _posting_age_days(posted_date)
    return age is not None and threshold < age <= MAX_AGE


def recategorize_stale_entries() -> int:
    """
    Retroactively update existing 'Shortlisted'/'Review Needed' tracker entries to
    'Stale' if their posted_date is now older than STALE_AGE_DAYS. Called at the
    start of every score run so the tracker stays current between scout runs.
    Returns count of entries updated.
    """
    updated = 0
    for app in tracker:
        if app.get("status") not in {"Shortlisted", "Review Needed"}:
            continue
        age = _posting_age_days(app.get("posted_date") or "")
        _thr = _get_stale_threshold(app.get("market", "uk"))
        if age is None or age <= _thr:
            continue
        old_status = app["status"]
        app["status"] = "Stale"
        app.setdefault("status_history", []).append({
            "status": "Stale",
            "date":   TODAY,
            "source": "score_jobs_stale_sweep",
            "reason": f"Retroactive: posting now {age}d old (>{_thr}d threshold)",
        })
        print(f"  [stale-sweep] {app.get('company')} / {app.get('role')} "
              f"({old_status} → Stale, age={age}d)")
        updated += 1
    if updated and not DRY_RUN:
        tracker_raw["applications"] = tracker
        TRACKER_PATH.write_text(json.dumps(tracker_raw, indent=2, ensure_ascii=False))
    return updated


_SALARY_HEADER_RE = re.compile(
    r'^(?:salary|pay|compensation|remuneration|package|annual\s+salary|total\s+compensation|reward)'
    r'(?:\s+(?:range|package|information))?\s*:\s*(.+)',
    re.IGNORECASE | re.MULTILINE
)


def _extract_salary_hint_from_description(desc: str) -> Optional[str]:
    """
    Find an explicitly labelled salary line (e.g. 'Salary: From £53k+') in the
    first 2000 chars of the description where structured headers always appear.
    Returns the extracted value string, or None if not found.
    """
    import html as _html
    clean = _html.unescape(desc[:2000])
    m = _SALARY_HEADER_RE.search(clean)
    if m:
        return m.group(1).strip()
    return None


def _parse_native_salary(native_str: str) -> Optional[tuple[int, int]]:
    """
    Parse LinkedIn's native salary field only.
    Handles: '75K GBP/yr - 90K GBP/yr' and '£75,000 - £90,000/year'.
    Returns (lower, upper) in GBP integers, or None if unparseable.
    Only used for Pass 1 hard-fail gate — Claude is authoritative for salary_stated.
    """
    if not native_str:
        return None
    has_k = bool(re.search(r'\d\s*[kK]\b', native_str))
    mult = 1000 if has_k else 1

    def _parse_num(s: str) -> Optional[int]:
        try:
            return int(float(s.replace(',', '').replace('k', '').replace('K', ''))) * mult
        except (ValueError, OverflowError):
            return None

    # Pattern A: currency-code suffix range "75K GBP/yr - 90K GBP/yr"
    m = re.search(
        r'(\d[\d,\.]+)\s*[kK]?\s*(?:GBP)[^\d\-–]*[\-–]\s*(\d[\d,\.]+)',
        native_str, re.IGNORECASE
    )
    if m:
        lo, hi = _parse_num(m.group(1)), _parse_num(m.group(2))
        if lo and hi:
            return lo, hi

    # Pattern B: symbol-prefix range "£75,000 - £90,000" or "£75k–£90k"
    m = re.search(
        r'(?:£|\$|€)\s*(\d[\d,\.]+)\s*[kK]?\s*(?:/\s*(?:yr|year|annum))?\s*[\-–]\s*(?:£|\$|€)?\s*(\d[\d,\.]+)',
        native_str, re.IGNORECASE
    )
    if m:
        lo, hi = _parse_num(m.group(1)), _parse_num(m.group(2))
        if lo and hi:
            return lo, hi

    return None


# ── Matching & dedup (new deterministic logic) ────────────────────────────────

KNOWN_AGENCIES = {
    "hackajob", "harnham", "robert walters", "michael page", "lorien",
    "burns sheehan", "glocomms", "la fosse", "data idols", "vma group",
    "sf technology", "w talent", "dune advisors", "salt",
    "oliver james", "paragon alpha", "selby jennings", "mason frank",
    "nigel frank", "marks sattin", "phaidon international", "harvey nash",
}

REPOST_GAP_DAYS   = 21   # days between old and new posting → genuine repost
TERMINAL_STATUSES = {"Rejected", "Withdrawn", "Stale", "Auto-Rejected", "Duplicate"}


# _extract_job_id_from_url, _edit_distance, _normalize_company come from
# scripts/common.py (imported at top) — single source of truth.

def _normalize_role(role: str) -> str:
    """Strip LinkedIn title noise before fuzzy matching.
    Handles suffixes like 'BI Lead at TrueLayer' → 'BI Lead'.
    """
    import re as _re
    if not role:
        return role
    # Strip " at [Company]" suffix injected by Jack/Jill and similar recruiters
    return _re.sub(r'\s+at\s+\S.*$', '', role, flags=_re.IGNORECASE).strip()


def _field_matches(a: str, b: str) -> bool:
    """True if two strings match within 3 character edits (case-insensitive)."""
    return bool(a and b and _edit_distance(a, b) <= 3)


def _role_matches(a: str, b: str) -> bool:
    """Role-aware fuzzy match: normalises 'at [Company]' suffixes first."""
    return _field_matches(_normalize_role(a), _normalize_role(b))


def _extract_hiring_company_hint(job: dict) -> Optional[str]:
    """
    If the posting company is a known agency, try to extract the real employer
    from the description. Returns the hiring company name or None.
    Note: scraped descriptions often have no whitespace between words (HTML strip
    artifact), so patterns use optional spaces not required spaces.
    """
    company = (job.get("company_name") or "").lower()
    if not any(re.search(r'\b' + re.escape(ag) + r'\b', company) for ag in KNOWN_AGENCIES):
        return None
    desc = job.get("description") or ""
    m = re.search(r"collaborating\s*with\s*([A-Z][\w\s&\-]+?)\s*to\s*connect", desc, re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r"on behalf of\s*([A-Z][\w\s&\-,]+?)[\.,]", desc, re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r"join\s*us\s*at\s*([A-Z][\w\s&\-]+?)\s+as\s+(?:a|an|the)\b", desc, re.IGNORECASE)
    if m: return m.group(1).strip()
    m = re.search(r"partnering\s*with\s*([A-Z][\w\s&\-]+?)\s+to\s+\w+", desc, re.IGNORECASE)
    if m: return m.group(1).strip()
    return None


def _scoring_date_proxy(entry: dict) -> Optional[str]:
    """Compute latest_scoring_date for entries that don't have it stored."""
    if entry.get("latest_scoring_date"):
        return entry["latest_scoring_date"]
    if entry.get("fit_score") is None:
        return None
    if entry.get("source") == "excel_import":
        return "2026-06-18"   # import date as proxy for all excel-imported scored entries
    for h in (entry.get("status_history") or []):
        d = h.get("date") or ""
        if d and len(d) >= 10:
            return d[:10]
    return None


def _build_existing_pool() -> list:
    """Build unified pool of tracker + auto_rejected entries for match checking."""
    pool = []
    for e in tracker:
        # --force-stale: exclude Stale entries so they can be re-scored fresh
        if FORCE_STALE and e.get("status") == "Stale":
            continue
        _jd_url = (e.get("jd_url") or "").strip()
        pool.append({
            "id":                  e.get("id"),
            "company":             (e.get("company") or "").lower().strip(),
            "role":                (e.get("role") or "").lower().strip(),
            "jd_url":              _jd_url,
            "job_id":              e.get("job_id") or _extract_job_id_from_url(_jd_url),
            "status":              e.get("status", ""),
            "posted_date":         (e.get("posted_date") or "")[:10],
            "fit_score":           e.get("fit_score"),
            "score_exists":        e.get("score_exists", e.get("fit_score") is not None),
            "latest_scoring_date": _scoring_date_proxy(e),
            "market":              e.get("market", "uk") or "uk",
        })
    for e in auto_rejected:
        _jd_url = (e.get("jd_url") or "").strip()
        pool.append({
            "id":                  e.get("id"),
            "company":             (e.get("company") or "").lower().strip(),
            "role":                (e.get("role") or "").lower().strip(),
            "jd_url":              _jd_url,
            "job_id":              e.get("job_id") or _extract_job_id_from_url(_jd_url),
            "status":              "Auto-Rejected",
            "posted_date":         (e.get("posted_date") or "")[:10],
            "fit_score":           e.get("fit_score"),
            "score_exists":        e.get("fit_score") is not None,
            "latest_scoring_date": (e.get("scout_run_date") or "")[:10] or None,
            "market":              e.get("market", "uk") or "uk",
        })
    # Checkpoint: jobs scored in a failed run today (not yet in tracker)
    checkpoint_path = ROOT / "data" / "pipeline" / "scoring_checkpoint.json"
    if checkpoint_path.exists():
        try:
            for e in json.loads(checkpoint_path.read_text()):
                if e.get("date") != TODAY:
                    continue  # previous-day checkpoint — ignore for today's run
                _jd_url = (e.get("jd_url") or "").strip()
                pool.append({
                    "id":                  f"ckpt:{_jd_url[:30]}",
                    "company":             (e.get("company") or "").lower().strip(),
                    "role":                (e.get("role") or "").lower().strip(),
                    "jd_url":              _jd_url,
                    "job_id":              e.get("job_id") or _extract_job_id_from_url(_jd_url),
                    "status":              "checkpoint",
                    "posted_date":         "",
                    "fit_score":           None,
                    "score_exists":        False,
                    "latest_scoring_date": TODAY,
                    "market":              e.get("market", "uk") or "uk",
                })
        except Exception:
            pass
    return pool


# Built once at module load — shared across all jobs in this batch
_EXISTING_POOL: list = _build_existing_pool()


def _find_match(job: dict) -> dict:
    """
    Determines the relationship between a scraped job and existing tracker/auto_rejected.

    Returns:
      decision:       "dedup" | "update_in_place" | "new_entry" | "no_match"
      matched_entry:  the best-matching pool entry dict, or None
      matched_id:     matched entry's id string, or None

    Decision tree:
      1. jd_url exact match → dedup
      2. company/hiring_co + role match (≤3 char edit distance each), gap ≤ 1 day → dedup
      3. match, gap 2–21 days → update_in_place
      4. match, gap > 21 days, terminal status → new_entry (old entry kept)
      5. match, gap > 21 days, active/unknown status → update_in_place
      6. no match → no_match
      Unknown gap (missing dates) → update_in_place (safe default)
    """
    jd_url     = (job.get("job_url") or job.get("url") or "").strip()
    company    = (job.get("company_name") or "").lower().strip()
    title      = (job.get("job_title") or "").lower().strip()
    new_posted = (job.get("posted_date") or job.get("postedDate") or "")[:10]

    is_agency  = any(re.search(r'\b' + re.escape(ag) + r'\b', company) for ag in KNOWN_AGENCIES)
    hiring_co  = _extract_hiring_company_hint(job)

    incoming_market = (job.get("market") or "uk").lower()

    # Signal 0: (job_id, market) match → always dedup (URL tracking params differ, job is same).
    # Market qualifier guards against job_id collisions across markets/sources.
    # Prefer the native job_id field (Apify/Adzuna) over URL extraction.
    incoming_job_id = str(job.get("job_id") or "").strip() or _extract_job_id_from_url(jd_url)
    if incoming_job_id:
        for e in _EXISTING_POOL:
            if (e.get("job_id") and str(e["job_id"]) == incoming_job_id
                    and incoming_market == (e.get("market") or "uk").lower()):
                print(f"    [match] job_id {incoming_job_id} ({incoming_market}) → dedup ({e['id']}/{e['status']})")
                return {"decision": "dedup", "matched_entry": e, "matched_id": e["id"]}

    # Signal 1: jd_url exact match → always dedup
    if jd_url:
        for e in _EXISTING_POOL:
            if e["jd_url"] and jd_url == e["jd_url"]:
                print(f"    [match] jd_url exact → dedup ({e['id']}/{e['status']})")
                return {"decision": "dedup", "matched_entry": e, "matched_id": e["id"]}

    # Signal 2: company/hiring_co + role (≤3 char edit distance each)
    # For agencies with no identifiable client, match on the agency name + role directly
    # (Harnham self-postings, hackajob, etc.) — gap check prevents false positives.
    match_co = hiring_co.lower().strip() if (is_agency and hiring_co) else company

    match_co_norm   = _normalize_company(match_co)
    candidates = [
        e for e in _EXISTING_POOL
        if _field_matches(match_co_norm, _normalize_company(e["company"])) and _role_matches(title, e["role"])
        # Different markets = different job listings (same company can post in UK and NL/SE)
        and (not incoming_market or not e.get("market") or incoming_market == e.get("market", "uk"))
    ]
    if not candidates:
        return {"decision": "no_match", "matched_entry": None, "matched_id": None}

    # Among multiple matches use the one with latest posted_date
    best        = max(candidates, key=lambda e: e["posted_date"])
    best_posted = best["posted_date"]

    gap_days: Optional[int] = None
    if new_posted and best_posted:
        try:
            gap_days = (date.fromisoformat(new_posted) - date.fromisoformat(best_posted)).days
        except ValueError:
            pass

    if gap_days is not None and abs(gap_days) <= 1:
        print(f"    [match] {match_co}+role, gap={gap_days}d → dedup ({best['id']})")
        return {"decision": "dedup", "matched_entry": best, "matched_id": best["id"]}

    existing_status = best["status"]

    if gap_days is not None and gap_days > REPOST_GAP_DAYS and existing_status in TERMINAL_STATUSES:
        print(f"    [match] {match_co}+role, gap={gap_days}d>{REPOST_GAP_DAYS}, "
              f"terminal → new_entry (supersedes {best['id']})")
        return {"decision": "new_entry", "matched_entry": best, "matched_id": best["id"]}

    if gap_days is None and existing_status in TERMINAL_STATUSES:
        print(f"    [match] {match_co}+role, gap unknown, terminal → new_entry "
              f"(supersedes {best['id']}/{existing_status})")
        return {"decision": "new_entry", "matched_entry": best, "matched_id": best["id"]}

    reason = (f"gap={gap_days}d" if gap_days is not None else "gap unknown")
    print(f"    [match] {match_co}+role, {reason} → update_in_place ({best['id']}/{existing_status})")
    return {"decision": "update_in_place", "matched_entry": best, "matched_id": best["id"]}


def _reconstruct_result_from_entry(entry: dict) -> dict:
    """Build a minimal score result dict from an existing tracker entry for score reuse."""
    score  = entry.get("fit_score") or 0
    action = "shortlist" if score >= 75 else "review" if score >= 60 else "reject"
    return {
        "action":                     action,
        "fit_score":                  entry.get("fit_score"),
        "fit_score_breakdown":        entry.get("fit_score_breakdown"),
        "visa_sponsorship_status":    entry.get("visa_sponsorship_status", "Unconfirmed"),
        "salary_stated":              entry.get("salary_stated"),
        "salary_estimate":            entry.get("salary_estimate"),
        "salary_estimate_confidence": entry.get("salary_estimate_confidence"),
        "salary_gate":                ("passed" if entry.get("salary_meets_threshold") is True
                                       else "tbc"  if entry.get("salary_meets_threshold") is None
                                       else "failed"),
        "work_mode":                  entry.get("work_mode"),
        "experience_req":             entry.get("experience_req"),
        "ats_type_from_jd":           entry.get("ats_type"),
        "is_agency_post":             entry.get("is_agency_post", False),
        "actual_hiring_company":      entry.get("actual_hiring_company"),
        "is_contract":                entry.get("is_contract", False),
        "is_remote_only":             entry.get("is_remote_only", False),
        "is_investment_domain":       entry.get("is_investment_domain", False),
        "is_sap_primary":             entry.get("is_sap_primary", False),
        "apply_recommendation":       entry.get("apply_recommendation"),
        "company_sponsor_kb":         entry.get("company_sponsor_kb", "Uncertain"),
        "pros":                       entry.get("pros", []),
        "cons":                       entry.get("cons", []),
        "flags":                      entry.get("flags", []),
        "_score_reused_from":         entry.get("id"),
        "role_type":                  (entry.get("role_type") or _compute_role_type(
                                          bool(entry.get("is_contract", False)),
                                          bool(entry.get("is_remote_only", False))
                                      )),
    }


def pass1_filter(job: dict) -> tuple[str, str]:
    """
    Returns (result, reason) where result is "pass", "reject", or "stale".
    Uses ONLY native LinkedIn/Apify metadata fields — no JD description parsing.
      "pass"   → send to Pass 2 (Claude API)
      "reject" → P1-REJECT, add to auto_rejected (hard cutoff)
      "stale"  → add to tracker as status=Stale, skip Claude API

    Rejection hierarchy (most objective gate first):
      1. Posting too old (>30d)  — hardest cut, no JD read needed
      2. Remote-only             — role-type gate, native LinkedIn field
      3. Contract/non-permanent  — role-type gate, native LinkedIn field
      4. Salary below £80k       — only when stated; Pass 2 handles TBC cases
      5. Location outside tiers  — native LinkedIn field
      6. Title hard-reject       — last: lets other gates fire first, Pass 2 can still see edge cases
    Note: "No Visa Sponsorship (stated)" requires JD text reading → Pass 2 only (not in Pass 1).
    """
    market = job.get("market", "uk")
    title  = (job.get("job_title") or "").lower()
    posted = job.get("posted_date") or job.get("postedDate") or ""

    # 1. Posting age (from LinkedIn posted_date — poster-declared)
    #    >MAX_AGE days → hard reject (not worth tracking at all)
    #    >STALE_AGE_DAYS days → Stale ONLY if title is analytics-relevant;
    #                           otherwise reject (no value logging off-topic stale jobs)
    if _posting_too_old(posted):
        return "reject", f"Posting too old (posted {posted}, >{MAX_AGE}d)"
    _stale_thr = _get_stale_threshold(market)
    if _posting_is_stale(posted, _stale_thr):
        if any(kw in title for kw in ANALYTICS_TITLE_KW):
            return "stale", f"Posting is stale (posted {posted}, >{_stale_thr}d old)"
        return "reject", f"Stale + non-analytics title (posted {posted}, >{_stale_thr}d old)"

    # 2. Work type (from LinkedIn structured fields — poster-declared)
    # Detect remote/contract signals for salary gate adjustment; no longer hard-reject.
    # Remote and contract roles are now accepted at 80% of market salary threshold.
    _WORK_TYPE_FIELDS = ["work_type", "workType", "workplace_type", "workplaceType", "workMode"]
    _REMOTE_BOOL_FIELDS = ["remote_allowed", "remoteAllowed", "is_remote", "isRemote"]
    native_work_type = next(
        (str(job.get(f)) for f in _WORK_TYPE_FIELDS if job.get(f) is not None and job.get(f) != ""),
        ""
    ).lower()
    remote_bool = any(job.get(f) is True for f in _REMOTE_BOOL_FIELDS)
    _is_remote_signal = (remote_bool
                         or (native_work_type and "remote" in native_work_type and "hybrid" not in native_work_type)
                         or bool(job.get("remote_hint") and not native_work_type))

    # 3. Job type (from LinkedIn job_type field — poster-declared)
    # Part-time is still rejected; contract/temporary/freelance pass through to Claude scoring.
    native_job_type = (job.get("job_type") or job.get("jobType") or "").lower()
    if native_job_type and "part-time" in native_job_type:
        return "reject", f"Part-time role (LinkedIn native job_type: '{native_job_type}')"
    _co_lower = (job.get("company_name") or "").lower()
    _is_contract_signal = bool(
        native_job_type
        and any(t in native_job_type for t in ["contract", "temporary", "freelance"])
        and not any(co in _co_lower for co in _PERMANENT_DESPITE_JOB_TYPE)
    )

    # 4. Native salary hard-fail (from LinkedIn salary card field — poster-declared)
    # Only fires for UK market: NL/SE salaries are in EUR/SEK and can't be compared to £80k.
    # Remote or contract signals → use 80% threshold.
    native_salary = job.get("salary") or ""
    if market == "uk" and native_salary:
        # Day-rate annualisation (catches "£450/day" before _parse_native_salary which only handles annual).
        # Day-rate always uses the remote/contract threshold (80%) since contract implies flexibility.
        _day_annual = _annualise_day_rate(native_salary)
        if _day_annual is not None:
            _thr = _COMMON_SALARY_THRESHOLDS_REMOTE["uk"]  # 80% — day rate = contract
            if _day_annual < _thr:
                return "reject", (
                    f"Day rate below threshold: '{native_salary}' → "
                    f"£{_day_annual:,.0f}/yr < £{_thr:,} (80% gate for contracts)"
                )
            native_salary = ""  # skip _parse_native_salary double-check for same string
        parsed = _parse_native_salary(native_salary)
        if parsed:
            lo, hi = parsed
            _thr = (_COMMON_SALARY_THRESHOLDS_REMOTE["uk"] if (_is_remote_signal or _is_contract_signal)
                    else _COMMON_SALARY_THRESHOLDS["uk"])
            if hi < _thr and lo < _thr:
                return "reject", f"Salary below £{_thr//1000}k threshold (LinkedIn native: '{native_salary}')"

    # 5. Location (from LinkedIn location field — poster-declared)
    location = job.get("location") or job.get("jobLocation") or ""
    in_tier, _ = _location_in_tiers(location, market)
    if not in_tier:
        return "reject", f"Location '{location}' outside acceptable tiers (market={market})"

    # 5b. SE brand whitelist — only 7 companies permitted; all others auto-reject.
    if market == "se":
        _co_raw = (job.get("actual_hiring_company") or job.get("company_name") or "").lower()
        if not any(allowed in _co_raw for allowed in _SE_ALLOWED):
            return "reject", f"SE whitelist: '{job.get('company_name')}' not in approved brand list"

    # 5d. Language gate (NL/SE/DE/DK) — Dutch/Swedish/German/Danish-only roles are hard disqualifiers.
    # Three checks: (a) job title — 1 unambiguous word is enough (titles are short);
    #               (b) description — 2+ distinct requirement phrases;
    #               (c) NL/SE/DE — JD text written in the local language (function word count).
    #
    # German explicit phrase check fires on ALL markets (not just DE).
    # A UK or NL role requiring German fluency is equally disqualifying.
    _desc_all = (job.get("description") or "")[:3000].lower()
    if any(ph in _desc_all for ph in _GERMAN_PHRASES):
        return "reject", f"German language skills required — role not English-first (market={market})"

    if market in ("nl", "se", "de"):
        # DE language gate — three independent checks (mirroring NL/SE pattern)
        if market == "de":
            _title_de = (job.get("job_title") or "").lower()
            _desc_de  = _desc_all  # reuse already-lowercased slice
            # (a) German title words
            if any(w in _title_de for w in _GERMAN_TITLE_WORDS):
                return "reject", f"Job title written in German: '{job.get('job_title')}'"
            # (b) JD text written in German (function word count)
            _de_words = set(re.findall(r'\b[a-zäöüß]{2,}\b', _desc_de))
            _de_hits  = len(_de_words & _GERMAN_FUNCTION_WORDS)
            if _de_hits >= 6:
                return "reject", (
                    f"JD text written in German ({_de_hits} German function words detected) "
                    "— likely requires German proficiency"
                )
            # Explicit phrase check already fired above (all-market gate)

    # Language gate (NL/SE/DK) — Dutch/Swedish/Danish-only roles are hard disqualifiers.
    # Three checks: (a) job title — 1 unambiguous word is enough (titles are short);
    #               (b) description — 2+ distinct requirement phrases;
    #               (c) JD text written in the local language (function word count).
    # IE has no language gate — English-speaking market (only the all-market German
    # phrase check above applies).
    if market in ("nl", "se", "dk"):
        _lang_phrases = (_DUTCH_PHRASES if market == "nl"
                         else _SWEDISH_PHRASES if market == "se" else _DANISH_PHRASES)
        _lang_label   = ("Dutch" if market == "nl"
                         else "Swedish" if market == "se" else "Danish")
        # (a) Title-level check
        _title_words = (_DUTCH_TITLE_WORDS if market == "nl"
                        else _SWEDISH_TITLE_WORDS if market == "se" else _DANISH_TITLE_WORDS)
        _title_text  = (job.get("job_title") or "").lower()
        _title_hits  = sum(1 for w in _title_words if re.search(r'\b' + w + r'\b', _title_text))
        if _title_hits >= 1:
            return "reject", (
                f"Job title contains {_lang_label} language indicator "
                f"— likely requires native {_lang_label} proficiency"
            )
        # (b) Description-level requirement phrases check
        _desc_lang    = (job.get("description") or "")[:2000].lower()
        _lang_hits    = sum(1 for p in _lang_phrases if p in _desc_lang)
        if _lang_hits >= 2:
            return "reject", f"Role requires {_lang_label} language proficiency (found {_lang_hits} signal phrases)"
        # (c) NL only — detect JD text written in Dutch
        # A JD written entirely in Dutch implies Dutch proficiency even if not stated explicitly.
        # Threshold: 8+ distinct Dutch function words in first 3,000 chars.
        if market == "nl":
            _DUTCH_FUNCTION_WORDS = {
                "van", "de", "het", "een", "voor", "met", "zijn", "worden",
                "die", "dat", "ook", "maar", "als", "niet", "naar", "bij",
                "door", "over", "kan", "wordt", "geen", "hun", "zich", "nog",
                "heeft", "deze", "wij", "je", "jij",
            }
            _desc_jd   = (job.get("description") or "")[:3000].lower()
            _jd_words  = set(re.findall(r'\b[a-z]{2,}\b', _desc_jd))
            _dutch_hits = len(_jd_words & _DUTCH_FUNCTION_WORDS)
            if _dutch_hits >= 8:
                return "reject", (
                    f"JD text written in Dutch ({_dutch_hits} Dutch function words detected) "
                    "— likely requires Dutch proficiency"
                )
        elif market == "se":
            # (c) SE — detect JD text written in Swedish (parallel to NL check above).
            # Uses ASCII-safe Swedish function words that never appear in English JDs.
            _SWEDISH_FUNCTION_WORDS = {
                "och", "att", "inte", "ska", "ett", "vad", "hur", "alla",
                "kan", "har", "bli", "din", "vill", "det", "med",
            }
            _desc_se   = (job.get("description") or "")[:3000].lower()
            _se_words  = set(re.findall(r'\b[a-z]{2,}\b', _desc_se))
            _se_hits   = len(_se_words & _SWEDISH_FUNCTION_WORDS)
            if _se_hits >= 6:
                return "reject", (
                    f"JD text written in Swedish ({_se_hits} Swedish function words detected) "
                    "— likely requires Swedish proficiency"
                )
        elif market == "dk":
            # (c) DK — detect JD text written in Danish (parallel to NL/SE checks above).
            # Danish function words that never appear in English JDs; regex includes
            # æ/ø/å so words like "på" and "være" are captured.
            _DANISH_FUNCTION_WORDS = {
                "og", "ikke", "være", "til", "af", "på", "som", "eller",
                "vores", "hos", "skal", "kan", "har", "vil", "med", "dine",
            }
            _desc_dk   = (job.get("description") or "")[:3000].lower()
            _dk_words  = set(re.findall(r'\b[a-zæøå]{2,}\b', _desc_dk))
            _dk_hits   = len(_dk_words & _DANISH_FUNCTION_WORDS)
            if _dk_hits >= 6:
                return "reject", (
                    f"JD text written in Danish ({_dk_hits} Danish function words detected) "
                    "— likely requires Danish proficiency"
                )

    # AE language gate — check if Arabic proficiency is explicitly required.
    # Arabic function-word detection not used (Arabic is Unicode script — regex won't match).
    # Phrase-based check only: any single phrase is sufficient to reject.
    if market == "ae":
        _desc_ae = (job.get("description") or "")[:2000].lower()
        for _ph in _ARABIC_PHRASES:
            if _ph in _desc_ae:
                return "reject", f"Role requires Arabic language proficiency: '{_ph}'"

    # 5e. Residency gate (ALL markets) — auto-reject if JD explicitly states that applicants
    # must already be living/residing in the EU, UK, or target country.
    # One phrase match is sufficient. Scans first 3,000 chars (covers any upfront disclaimer).
    _desc_res = (job.get("description") or "")[:3000].lower()
    for _ph in _RESIDENCY_EXCLUSION_PHRASES:
        if _ph in _desc_res:
            return "reject", f"Residency gate: JD excludes applicants not already in country (matched: '{_ph}')"

    # 6. Hard-reject titles (from LinkedIn job_title field — poster-declared)
    # Last gate: lets age/remote/contract/salary/location fire first.
    # Pass 2 (Claude) is the final arbiter for borderline titles that pass all gates above.
    company_lower = (job.get("company_name") or "").lower()
    for bad in TITLE_REJECT_CONTAINS:
        if bad == "data science" and any(co in company_lower for co in _ANALYTICS_NAMED_DS_COMPANIES):
            continue   # Deliveroo names analytics roles as "Data Science" — pass to Claude
        if bad == "director" and "associate" in title:
            continue   # "Associate Director" = Senior Manager equiv in UK/EU firms — pass to Claude
        if bad in title:
            return "reject", f"Title contains '{bad}'"

    # 6a. Junior Tier-4 title gate (non-senior, non-lead analyst roles)
    # Uses classify_title.py deterministic classifier (pts==5 → Tier 4).
    # Saves the ~$0.027 Claude API call for clearly sub-target titles.
    # Tier 3+ (Senior DA, Senior BA, etc.) still pass to Claude for full scoring.
    # Stale jobs return early at gate 1 and never reach this gate.
    if _classify_title is not None:
        _tier_pts, _tier_reason = _classify_title(title)
        if _tier_pts == 5:
            return "reject", (
                f"Junior Tier-4 title (non-senior/non-lead analyst): "
                f"'{job.get('job_title', '')}' — {_tier_reason}"
            )

    # 6b. SAP-primary title gate (title-level only — clear tooling-first signal)
    # Only blocks when SAP is the defining technology in the title itself.
    # JD-level SAP-primary detection is handled by Claude in Pass 2.
    for _sap_kw in _SAP_PRIMARY_TITLE_KW:
        if _sap_kw in title:
            return "reject", f"SAP-primary title: '{job.get('job_title', '')}'"

    # 6c. Non-analytics "Business Partner" titles — deterministic Pass 1 gate.
    # "Commercial Business Partner", "HR Business Partner", "Sales Business Partner" etc.
    # are not analytics roles. Only block when NO analytics/data keyword qualifies the title.
    # Examples that pass: "Analytics Business Partner", "Data & Insights Business Partner"
    if "business partner" in title:
        _analytics_qualifiers = {"analytic", "data", "insight", "reporting", "intelligence"}
        if not any(q in title for q in _analytics_qualifiers):
            return "reject", f"Non-analytics Business Partner title: '{job.get('job_title', '')}'"

    # 6d. Known management consulting firm gate (company-level, P1)
    # Pure management consulting + Big 4 firms are always management_consulting role_focus
    # in Pass 2 and rejected by Gate 6. Blocking here saves the Claude API call.
    # Tech consulting firms (Accenture, Capgemini, Infosys) still pass to Claude —
    # they sometimes post genuine analytics delivery roles.
    if _is_mgmt_consulting_company(job.get("company_name") or ""):
        return "reject", (
            f"Known management consulting firm (always management_consulting role_focus "
            f"→ Gate 6 rejected in Pass 2): '{job.get('company_name')}'"
        )

    # 7. Visa denial keywords (description — high-confidence explicit phrases only)
    # Shorter phrases like "right to work in the uk" alone are NOT included — a direct
    # employer could say that while still intending to sponsor. Only structurally
    # unambiguous denial phrases are listed.
    if market == "nl":
        _visa_kws = _VISA_DENIAL_KW + _VISA_DENIAL_KW_NL
    elif market == "se":
        _visa_kws = _VISA_DENIAL_KW + _VISA_DENIAL_KW_SE
    elif market == "de":
        _visa_kws = _VISA_DENIAL_KW + _VISA_DENIAL_KW_DE
    elif market == "dk":
        _visa_kws = _VISA_DENIAL_KW + _VISA_DENIAL_KW_DK
    elif market == "ie":
        _visa_kws = _VISA_DENIAL_KW + _VISA_DENIAL_KW_IE
    elif market == "ae":
        _visa_kws = _VISA_DENIAL_KW + _VISA_DENIAL_KW_AE
    else:
        _visa_kws = _VISA_DENIAL_KW
    desc_lower = (job.get("description") or "").lower()
    for kw in _visa_kws:
        if kw in desc_lower:
            return "reject", f"Visa denial keyword in JD: '{kw}'"

    # 8. Contract/IR35/day-rate keywords (description — enrichment, not rejection)
    # Keywords set _is_contract_signal; Pass 2 (Claude) detects is_contract independently.
    desc_contract = (job.get("description") or "")[:1000].lower()
    for kw in _CONTRACT_KW:
        if kw in desc_contract:
            _is_contract_signal = True   # enrichment signal only — do not reject
            break

    # 9. Remote-only keywords (description — enrichment, not rejection)
    # High-confidence phrases only — vaguer phrasing ("distributed team") caught by Pass 2.
    desc_remote = (job.get("description") or "")[:800].lower()
    for kw in _REMOTE_ONLY_KW:
        if kw in desc_remote:
            _is_remote_signal = True   # enrichment signal only — do not reject
            break

    return "pass", ""


# ─────────────────────────────────────────────────────────────────────────────
# PASS 2 — Claude API semantic scoring
# ─────────────────────────────────────────────────────────────────────────────

def _build_score_system() -> str:
    _name   = _CANDIDATE_NAME
    _yrs    = _YEARS_EXP
    _titles = ", ".join(_TARGET_ROLES) if _TARGET_ROLES else "Lead/Manager/Head-level roles in your target profession"
    _skills = ", ".join(_CORE_SKILLS_LIST) if _CORE_SKILLS_LIST else "YOUR_SKILL_1, YOUR_SKILL_2, YOUR_SKILL_3"
    _exp_lines = []
    for e in _PROFILE.get("experience", []):
        _exp_lines.append(f"{e.get('company','')} ({e.get('role','')} — {e.get('focus_areas','key work')})")
    _exp_str = "; ".join(_exp_lines) if _exp_lines else "[Fill experience in candidate_profile.json]"
    _lang_str = ", ".join(_LANGUAGES) if _LANGUAGES else "English"
    _ai_note = ""
    if _VERBATIM_SENTS:
        _ai_note = (
            f"\n  → Skills: The candidate's AI engineering portfolio (see verbatim sentences in "
            f"candidate_profile.json) is DIRECTLY relevant — count these as skills match.\n"
            "    Award 15 pts (4-6 skills) if AI tooling aligns; 25 pts (7+) if AI + core skills also match."
        )
    return (
        f"You are a job fit scorer for {_name}, a professional with {_yrs}+ years of experience"
        " seeking roles (visa sponsorship may be required).\n\n"
        "CANDIDATE PROFILE:\n"
        f"- Target titles: {_titles}\n"
        f"- Key experience: {_exp_str}\n"
        f"- Core skills: {_skills}\n"
        "- Employment type: Set is_contract=true"
    )

# _SCORE_SYSTEM_STATIC — generic scoring rules with no personal data.
# SCORE_SYSTEM = _build_score_system() + "\n" + _SCORE_SYSTEM_STATIC (assigned after closing """)
_SCORE_SYSTEM_STATIC = """
- Employment type: Set is_contract=true (informational flag only — do NOT set action=reject) if the JD mentions: day rate, IR35, inside/outside IR35, fixed-term contract, FTC, interim, 6/12-month contract, contractor, "duration of the contract will be X months", "contract duration", "contract period of", or any phrasing indicating a time-limited/fixed-term engagement. If uncertain default is_contract=false. NOTE: "Temporary work from abroad policy" or "work from abroad temporarily" is NOT a contract indicator — it describes a remote-work flexibility benefit. Do NOT set is_contract=true based on this phrase alone.
- Work arrangement: Set is_remote_only=true (informational flag only — do NOT set action=reject) if the role is fully remote / 100% remote with no office requirement. Hybrid = false. Scoring continues normally regardless of these flags.
SCORING RUBRIC (0-100):
  Role title match   (0-20):
    20 = Manager, Lead, Head, or Principal exact match:
         Analytics Manager / Data Analytics Manager / AI Analytics Manager /
         Product Analytics Manager / Growth Analytics Manager,
         Analytics Lead / AI Analytics Lead / Analytics Transformation Lead or Manager,
         Lead Business Analyst / Lead Product Analyst / Lead Data Analyst,
         Senior Analytics Lead / Growth Analytics Lead or Manager,
         Head of Data / Head of Analytics / Head of Data & Analytics,
         Insights Lead / Insights Manager (analytics-heavy), Data & AI Lead or Manager,
         Principal Data Analyst or Principal Analytics role
    15 = Senior non-Lead analytics role OR senior AI Enablement practitioner:
         Senior Business Analyst / Senior Analytics Engineer /
         Senior Performance Analyst / Senior Product Analyst /
         Senior Insights Analyst / BI Manager / BI Product Lead / BI Lead /
         Business Intelligence Manager / Business Intelligence Lead / Head of Business Intelligence /
         AI Enablement Specialist / AI & Automation Specialist /
         Forward Deployed AI Accelerator / AI Practice Lead /
         ANY title where the JD primary work is enabling AI workflows org-wide
         (use JD content to confirm — not just the title alone)
    10 = Senior Data Analyst specifically
     5 = Business Analyst or Data Analyst (non-senior, non-lead)
     0 = Unrelated title (Data Engineer, Data Scientist, Software Engineer, etc.)
  Domain match       (0-25): 25=product/growth/ecommerce/marketplace/fintech, 15=other tech, 5=consulting, 0=unrelated
  Skills match       (0-25): 25=7+ skills overlap, 15=4-6, 5=1-3, 0=none
  Seniority          (0-15): 15=Lead/Manager 5-10yr expected, 10=slightly senior, 5=slightly junior, 0=mismatch
  Location           (0-10): 10=London, 8=Manchester/Birmingham (incl. Salford/Liverpool/Warrington/Solihull), 6=other Tier2 (Leeds/Reading/Cambridge/Oxford/Coventry/Leicester/Nottingham/MK/Northampton/Bradford/York/Welwyn Garden City/St Albans/Hatfield), 0=Tier3 (Bristol/Brighton/Luton/Watford/Slough/Guildford/Woking/Newbury/Derby/Sheffield/Cheltenham/Southampton) or outside tiers
  Visa sponsorship   (-10/0/3/5): 5=confirmed, 3=large company (likely on UKVI sponsor register), 0=unconfirmed/unknown, -10=explicitly denied

=== AI ENABLEMENT ROLES — special scoring guidance ===
For roles where primary work is enabling AI workflows, practices, or tooling org-wide
(not traditional analytics delivery or data engineering):
  → role_focus: use "mixed" — NOT "insights_strategy" (they have technical requirements)
    and NOT "analytics_engineering" (they don't build data pipelines/dbt models)
  → Skills: Count the candidate's AI portfolio (from candidate_profile.json verbatim_sentences)
    as DIRECTLY relevant — award 15 pts (4-6 skills) if AI tooling aligns; 25 pts (7+) if AI + core skills also match. (informational flag only — do NOT set action=reject) if the JD mentions: day rate, IR35, inside/outside IR35, fixed-term contract, FTC, interim, 6/12-month contract, contractor, "duration of the contract will be X months", "contract duration", "contract period of", or any phrasing indicating a time-limited/fixed-term engagement. If uncertain default is_contract=false. NOTE: "Temporary work from abroad policy" or "work from abroad temporarily" is NOT a contract indicator — it describes a remote-work flexibility benefit. Do NOT set is_contract=true based on this phrase alone.
- Work arrangement: Set is_remote_only=true (informational flag only — do NOT set action=reject) if the role is fully remote / 100% remote with no office requirement. Hybrid = false. Scoring continues normally regardless of these flags.

SCORING RUBRIC (0-100):
  Role title match   (0-20):
    20 = Manager, Lead, Head, or Principal exact match:
         Analytics Manager / Data Analytics Manager / AI Analytics Manager /
         Product Analytics Manager / Growth Analytics Manager,
         Analytics Lead / AI Analytics Lead / Analytics Transformation Lead or Manager,
         Lead Business Analyst / Lead Product Analyst / Lead Data Analyst,
         Senior Analytics Lead / Growth Analytics Lead or Manager,
         Head of Data / Head of Analytics / Head of Data & Analytics,
         Insights Lead / Insights Manager (analytics-heavy), Data & AI Lead or Manager,
         Principal Data Analyst or Principal Analytics role
    15 = Senior non-Lead analytics role OR senior AI Enablement practitioner:
         Senior Business Analyst / Senior Analytics Engineer /
         Senior Performance Analyst / Senior Product Analyst /
         Senior Insights Analyst / BI Manager / BI Product Lead / BI Lead /
         Business Intelligence Manager / Business Intelligence Lead / Head of Business Intelligence /
         AI Enablement Specialist / AI & Automation Specialist /
         Forward Deployed AI Accelerator / AI Practice Lead /
         ANY title where the JD primary work is enabling AI workflows org-wide
         (use JD content to confirm — not just the title alone)
    10 = Senior Data Analyst specifically
     5 = Business Analyst or Data Analyst (non-senior, non-lead)
     0 = Unrelated title (Data Engineer, Data Scientist, Software Engineer, etc.)
  Domain match       (0-25): 25=product/growth/ecommerce/marketplace/fintech, 15=other tech, 5=consulting, 0=unrelated
  Skills match       (0-25): 25=7+ skills overlap, 15=4-6, 5=1-3, 0=none
  Seniority          (0-15): 15=Lead/Manager 5-10yr expected, 10=slightly senior, 5=slightly junior, 0=mismatch
  Location           (0-10): 10=London, 8=Manchester/Birmingham (incl. Salford/Liverpool/Warrington/Solihull), 6=other Tier2 (Leeds/Reading/Cambridge/Oxford/Coventry/Leicester/Nottingham/MK/Northampton/Bradford/York/Welwyn Garden City/St Albans/Hatfield), 0=Tier3 (Bristol/Brighton/Luton/Watford/Slough/Guildford/Woking/Newbury/Derby/Sheffield/Cheltenham/Southampton) or outside tiers
  Visa sponsorship   (-10/0/3/5): 5=confirmed, 3=large company (likely on UKVI sponsor register), 0=unconfirmed/unknown, -10=explicitly denied

=== AI ENABLEMENT ROLES — special scoring guidance ===
For roles where primary work is enabling AI workflows, practices, or tooling org-wide
(not traditional analytics delivery or data engineering):
  → role_focus: use "mixed" — NOT "insights_strategy" (they have technical requirements)
    and NOT "analytics_engineering" (they don't build data pipelines/dbt models)
  → Skills: Count the candidate's AI/automation portfolio (see verbatim_sentences in
    candidate_profile.json) as DIRECTLY relevant — these are hands-on engineering skills.
    Award 15 pts (4-6 skills) if AI tooling aligns; 25 pts (7+) if AI + core skills also match.
  → Domain: score the company's domain normally (fintech = 25, etc.)
  → Seniority: 10 pts if JD shows cross-functional scope or org-level impact; 5 pts if unclear

=== VISA SPONSORSHIP — YOU ARE AUTHORITATIVE ===
You receive no pre-screened visa hint. Read the full job description AND the raw job metadata.
Use judgment to assess whether this employer will sponsor a UK Skilled Worker Visa for a
candidate relocating from outside the UK. You are detecting INTENT, not matching exact phrases.

Set visa_sponsorship_status = "Rejected" (score -10, action = reject) if the JD or posting
contains ANY language whose INTENT is that the candidate must already hold the right to work
in the UK independently. This includes — but is not limited to:
  - Explicit no-sponsorship statements ("we cannot sponsor", "no visa sponsorship available",
    "unable to provide visa sponsorship", "sponsorship is not available")
  - Right-to-work requirements ("must have the right to work in the UK",
    "must be eligible to work in the UK", "applicants must have the right to work without
    sponsorship", "you must already have the right to work")
  - LinkedIn "Requirements added by job poster" checkbox fields, e.g.:
    "Authorized to work in United Kingdom" / "Authorised to work in United Kingdom"
    These appear as brief bullet-point labels at the bottom of the JD, not as full
    sentences. Treat them as explicit denial signals regardless of their terse style.
  IMPORTANT: Do NOT infer visa denial from the posting company being an agency or recruiter.
  If an agency post has an anonymised or unknown client, set visa_sponsorship_status = "Unconfirmed" —
  the actual hiring company (not the agency) would sponsor, and you cannot assess their intent
  without knowing who they are. Only set Rejected if the JD text EXPLICITLY denies sponsorship.

  Apply "Rejected" ONLY when the denial is stated in plain language in the JD text itself,
  not inferred from the company type, phrasing about commute, or availability requirements.

Return Confirmed ONLY if the JD explicitly and unambiguously states the company WILL provide
sponsorship (e.g. "certificate of sponsorship", "we will sponsor your visa",
"we are a licensed UK sponsor", "visa sponsorship is available").
Return Unconfirmed if the JD does not address sponsorship at all.

=== COMPANY SIZE AS SPONSORSHIP PROXY ===
When visa_sponsorship_status would be Unconfirmed (JD silent on sponsorship):
SET visa_sponsorship = 3 if company is any of: FTSE 100/250 listed firms,
well-known global tech/fintech companies (Series C+, recognisable brand),
major UK/global banks, large UK retailers or broadcasters, Big 4/top-tier consultancies,
or any multinational clearly operating at UK scale (1,000+ UK employees, global offices).
These are almost universally on the UK Home Office Skilled Worker sponsor register.
KEEP visa_sponsorship = 0 if company is: early-stage startup (<Series B, <100 employees),
niche agency/boutique recruiter, or a company you have no knowledge of.
ALWAYS apply Rejected (-10) if ANY denial phrase appears, regardless of company size.

=== SALARY EXTRACTION ===
Find salary from ANY available source — in order of priority:
  1. Raw job metadata fields (check ALL fields in "Raw Apify Job Data" block below — look for
     any field whose name or value contains salary/compensation/pay/remuneration data, e.g.
     salary, salaryRange, salary_text, salaryText, compensationOnEmploymentTypes, pay, etc.)
  2. Job Description body text (extract stated range or figure)
  3. If absent in both: generate an estimate (see below)

Extract ONLY compensation for this specific role — NOT company revenue, ARR, funding, bonuses,
equity valuations, or any other business metrics.

SALARY RANGE RULE: When salary is a RANGE (e.g. "€90,000–€120,000", "£75k–£95k"):
  → Check ONLY the UPPER end of the range against the threshold
  → Upper end > threshold → salary_gate = "passed" (even if lower end is below threshold)
  → Only set salary_gate = "failed" if BOTH ends are clearly below threshold
  Example: "€90k–€120k" with NL threshold €90k → upper €120k > €90k → salary_gate = "passed"
  Example: "£70k–£78k" with UK threshold £80k → upper £78k < £80k → salary_gate = "failed"

Salary gate: passed if upper end >= threshold; failed if both ends clearly below threshold;
tbc if indeterminate.

If salary is not stated in metadata OR job description body:
  → For UK: estimate in GBP. London adds 10–15% over other UK cities. Use 2025–2026 UK
    analytics market rates. Set salary_stated = "Not stated (est. £X–Y)". Round to nearest £5,000.
    For NL/SE: see Market Context section below for estimation currency and format.
  → ALWAYS set salary_gate = "tbc" when using an estimate — NEVER set salary_gate = "failed"
    for an estimated salary. Only reject on clearly stated (non-estimated) below-threshold pay.
  → Set salary_estimate and salary_estimate_confidence fields accordingly.

=== AGENCY POST DETECTION ===
Set is_agency_post=true if the posting company is a recruiter/staffing agency posting on behalf of another employer.
Signals: "on behalf of", "collaborating with [Company]", "our client", "recruiting for", "connecting you with".
Extract actual_hiring_company as the real employer name if identifiable. Set null if the client is anonymised.
If is_agency_post=true and actual_hiring_company is known, use the REAL company for location and domain scoring.

=== ATS IDENTIFICATION ===
Set ats_type_from_jd to the ATS platform identified from URLs or platform references in the JD.
If both Workday and Lever appear, prefer the one nearest to "apply" language.
Return unknown if no clear platform signal. Do not invent ATS URLs.

=== ACTIONS ===
shortlist — fit_score >= 75 AND visa_sponsorship_status != Rejected AND salary_gate != failed
review    — fit_score 60-74 OR (>=75 but has notable flags)
reject    — fit_score < 60 OR visa_sponsorship_status=Rejected OR salary_gate=failed
NOTE: is_remote_only and is_contract are informational flags only — they do NOT trigger reject.

IMPORTANT: Return ONLY valid JSON — no markdown, no explanation, nothing else.

JSON schema:
{
  "action": "shortlist|review|reject",
  "fit_score": <int 0-100>,
  "fit_score_breakdown": {
    "role_title": <0-20>,
    "domain": <0-25>,
    "skills": <0-25>,
    "seniority": <0-15>,
    "location": <0-10>,
    "visa_sponsorship": <-10|0|3|5>
  },
  "visa_sponsorship_status": "Confirmed|Rejected|Unconfirmed",
  "sponsorship_notes": "<one sentence explaining the sponsorship assessment and reasoning>",
  "salary_stated": "<display string or 'Not stated'>",
  "salary_gate": "passed|failed|tbc",
  "salary_estimate": "<market-currency range e.g. £80,000–£110,000 (UK) or €90,000–€120,000 (NL) or SEK 800,000–1,000,000 (SE)>" or null,
  "salary_estimate_confidence": "low|medium|high" or null,
  "work_mode": "Remote|Hybrid|On-site|Unknown",
  "is_remote_only": <boolean>,
  "is_contract": <boolean>,
  "is_agency_post": <boolean>,
  "actual_hiring_company": "<string or null>",
  "ats_type_from_jd": "greenhouse|lever|workday|ashby|smartrecruiters|icims|bamboohr|teamtailor|screenloop|unknown",
  "is_investment_domain": <boolean>,
  "is_sap_primary": <boolean>,
  "requires_non_english_language": <boolean>,
  "apply_recommendation": "Apply|Maybe|Skip",
  "company_sponsor_kb": "Known sponsor|Not a known sponsor|Uncertain",
  "experience_req": "<extracted string or null>",
  "pros": ["<key strength or positive match — specific, one line each>"],
  "cons": ["<key concern, risk, or caveat — specific, one line each>"],
  "rejection_reason": "<one sentence>" or null,
  "role_focus": "product_analytics|marketing_analytics|commercial_analytics|market_pricing|crm_analytics|bi_reporting|analytics_engineering|ai_engineering|credit_risk|management_consulting|insights_strategy|mixed",
  "eor_viability": <int 1-10 or null>
}

pros: 3–6 bullet points covering genuine strengths for THIS specific role and candidate.
Focus on: title/seniority alignment, domain fit (product/growth/ecommerce), skills overlap
(SQL/Python/Tableau/experimentation), company quality, location, AI/analytics relevance.
Be specific — e.g. "Analytics Manager title is an exact seniority match" not "good title match".

cons: 2–5 bullet points covering real concerns, risks, or caveats for THIS role.
Focus on: skills gaps, domain mismatch, visa uncertainty, travel demands, seniority mismatch,
salary unknown, weak domain fit, consulting/services context. If no major concerns, list
1–2 minor caveats. Be honest — do not omit genuine risks.

Do NOT use generic phrases ("strong candidate", "good match", "relevant experience").
Each point must be specific to this job and this candidate's profile.

experience_req: Extract the years-of-experience requirement as explicitly stated anywhere in
the JD text. Match any phrasing that specifies a number of years — e.g. "5 years working in",
"a minimum of 3 years", "ideally 6+ years", "X years' experience", "X–Y years within analytics",
"proven track record of X years", "you will have X years' hands-on" — not just the canonical
"X years of experience" pattern. Normalise to a compact display string: "5+ years",
"5–7 years", "minimum 3 years". Return null ONLY if no years figure appears anywhere in the
JD. Do NOT estimate or infer — only return what is explicitly written in the JD text.

is_investment_domain: true if the EMPLOYER is an investment firm (hedge fund, asset manager,
PE firm, investment bank, quant fund, wealth manager). Judge by industry/sector in JD, not
just keywords. false if the company merely SERVES financial clients (e.g. fintech data
platform for asset managers = false; quant analyst role at a hedge fund = true).

=== LANGUAGE REQUIREMENT ===
The candidate's working languages are configured in candidate_profile.json → profile.languages. Set requires_non_english_language=true if the JD
indicates that ANY non-English language (German, Dutch, French, Swedish, Spanish, etc.)
is required or operationally expected for the role — in meetings, written communication,
client interaction, or stated as a requirement/preference in the skills/requirements section.
Apply broadly: even "preferred" or "would be an advantage" counts as true when it appears
in a requirements list or skills section. This overrides fit_score entirely — a role
requiring any non-English language must be rejected regardless of how strong the match is.
Set false ONLY when the mention is clearly aspirational with no operational expectation
(e.g. mentioned in a company culture paragraph, not in the requirements or skills section).

=== SAP-PRIMARY ROLES ===
If SAP (SAP Analytics Cloud, SAP BW/4HANA, SAP BusinessObjects, SAP HANA) is the PRIMARY
analytics environment the role operates in — not merely one tool mentioned among many — set
action=reject and rejection_reason="SAP-primary role: not aligned with candidate's SQL/Python/
Tableau/BigQuery analytics stack." SAP mentioned incidentally does NOT trigger this.
Set is_sap_primary=true in this case, false otherwise.

=== ROLE FOCUS CLASSIFICATION ===
Classify the PRIMARY nature of this role. Choose exactly one:
  "product_analytics"     — product/growth/experimentation/conversion/marketplace analytics
  "marketing_analytics"   — PRIMARY work is marketing measurement: Marketing Mix Modelling (MMM),
                            media mix, channel attribution (MTA/Shapley), incrementality testing
                            as the CORE deliverable (not a supporting technique), marketing spend
                            optimisation, media planning analytics. Role is owned by a marketing
                            or growth team, not a product team. Distinct from product_analytics
                            (which is product/feature/funnel focused) and commercial_analytics
                            (which is revenue/pricing/P&L focused). Key signal: role title or JD
                            explicitly names MMM, media mix, attribution modelling, or marketing
                            measurement as the primary output.
  "commercial_analytics"  — analytics/modelling IS the primary output: pricing models, revenue
                            analytics, commercial strategy supported by data science/SQL/Python
  "market_pricing"        — the job IS pricing: rate-setting, tariff management, market price
                            decisions, energy/utility/telecom pricing strategy. Analytics is a
                            supporting tool, not the primary deliverable. Distinct from
                            commercial_analytics where data science/modelling is the main output.
  "crm_analytics"         — customer lifecycle/CRM/segmentation/retention analytics
  "bi_reporting"          — PRIMARY output is dashboards/reports/BI tooling delivery.
                            TIE-BREAKER: if the role is IC-level (not manager/lead), the JD
                            does not mention experimentation/A/B testing/incrementality, AND the
                            primary tool is a BI platform (Tableau/Power BI/Looker/Qlik/MicroStrategy),
                            classify as "bi_reporting" — not "mixed". Do NOT default to "mixed"
                            for ambiguous BI-heavy IC analyst roles.
  "analytics_engineering" — dbt/data modelling/data pipeline/analytics platform engineering
  "ai_engineering"        — AI/ML infrastructure/platform roles: MLOps, model deployment,
                            AI platform architecture. Output = AI systems, NOT analytics insights.
                            Use when role BUILDS AI tools; NOT when role USES AI for analytics.
  "credit_risk"           — PRIMARY work is credit risk strategy, underwriting, or risk scoring.
                            Only when credit/risk modelling IS the job. Commercial analytics with
                            incidental risk exposure = "commercial_analytics", not "credit_risk".
  "management_consulting" — client-facing consulting. Known consulting firms (BCG, McKinsey,
                            Bain, Oliver Wyman, Roland Berger, Booz Allen, Big-4 advisory arms:
                            Deloitte, PwC, EY, KPMG, Accenture Strategy) regardless of title.
                            ALSO: any role whose TITLE contains "Consultant" or "Consulting"
                            at a non-product company (client-facing advisory work).
                            EXCEPTION: internal analytics role at a product company where
                            "Consultant" is a seniority label → prefer "mixed".
  "insights_strategy"     — essential skills list has NO hands-on technical analytics tools
                            (SQL, Python, Tableau, BigQuery etc.) AND deliverables are strategy
                            decks, market research, or qualitative insights. Key test: does the
                            required skills section mention ANY analytics tool? YES → not this.
                            When uncertain, prefer "mixed".
  "mixed"                 — analytics strategy primary; BI or consulting present but not dominant

Distinctions: Head of Analytics who owns BI = "mixed"; BI Manager 80% Tableau = "bi_reporting";
Lead BA at McKinsey = "management_consulting". PREFER "mixed" when uncertain.

=== APPLY RECOMMENDATION ===
Independent of the action field. Provide a personal recommendation for the candidate:

Apply  — fit_score >= 75 AND visa_sponsorship_status != Rejected AND salary_gate != failed
         AND fit_score_breakdown.domain >= 20 (product/tech/ecommerce/fintech)
         AND fit_score_breakdown.seniority >= 10 AND no major red flags.

Maybe  — fit_score 60-74, OR score >= 75 but with notable caveats: consulting/services domain
         (domain_score <= 10), seniority_score = 5, salary_gate = tbc for unknown company,
         or visa_sponsorship_status = Unconfirmed for an early-stage/unknown company.

Skip   — fit_score < 60, OR visa_sponsorship_status = Rejected, OR salary_gate = failed,
         OR is_sap_primary = true, OR Tier-4 title (role_title = 5 in fit_score_breakdown).
         NOTE: is_remote_only and is_contract alone do NOT trigger Skip — they are informational.

=== COMPANY VISA SPONSOR KNOWLEDGE BASE ===
SEPARATE from visa_sponsorship_status (which reads JD text). Uses your training knowledge
(cutoff August 2025). Base on the ACTUAL HIRING COMPANY (use actual_hiring_company if
is_agency_post=true; if actual_hiring_company is null, return "Uncertain").

"Known sponsor" — ONLY when highly confident as of training data: FTSE 100/250,
  major global tech (Google, Meta, Amazon, Microsoft, Apple, Salesforce, Adobe, Spotify),
  Big 4 / top consulting (Deloitte, KPMG, PwC, EY, Accenture, McKinsey, BCG, Bain),
  major UK/global banks (Barclays, HSBC, Lloyds, NatWest, Goldman Sachs, JPMorgan),
  major UK fintechs with large UK headcount (Wise, Revolut, Monzo, Checkout.com),
  large UK retailers / broadcasters (Tesco, Sainsbury's, M&S, Sky, BT, Virgin, BBC).

"Not a known sponsor" — ONLY when certain the company does not/cannot sponsor. Very rare.

"Uncertain" — DEFAULT. Use for early-stage startups, Series A/B, niche agencies, any company
  where confidence is low, or companies founded/rebranded after 2023. PREFER Uncertain.

=== CONTRACT / REMOTE / EOR HANDLING ===

VISA FOR CONTRACTS: If is_contract=true, the candidate can engage via Employer of Record
(EOR: Deel or Remote.com) — no employer visa sponsorship required.
Set visa_sponsorship_status="EOR" and visa_score=5 for such roles.
EXCEPTION: if JD explicitly states "no overseas contractors", "must have right to work in UK
as employee", or is explicitly inside-IR35 with employing firm as the legal employer
→ set visa_sponsorship_status="Rejected", visa_score=-10.

LOCATION FOR REMOTE: If is_remote_only=true OR work_mode="Remote", score location=10
regardless of the job's city (remote = timezone-agnostic; India aligns with UK/CET hours).

DAY RATES: If salary is stated as a day rate (e.g. "£450/day", "£400 per day"), annualise:
rate × 220 working days. Compare against the 80% market threshold.
Example: £450/day × 220 = £99,000 > UK £64,000 remote gate → salary_gate="passed".

EOR VIABILITY: Add JSON field "eor_viability" (integer 1–10, or null for permanent non-remote):
  8–10: async-friendly, startup/scale-up, senior IC scope, fully remote, no mandatory onsite
  5–7:  hybrid, mid-size, some office expectation, or mixed remote
  1–4:  mandatory onsite, regulated entity requiring employee status, "no contractors" language
Set eor_viability=null when is_contract=false AND work_mode != "Remote"."""

SCORE_SYSTEM = _build_score_system() + "\n" + _SCORE_SYSTEM_STATIC


_MARKET_ADDONS = {
    "nl": """
=== MARKET CONTEXT: Netherlands ===
Location (0-10): 10=Amsterdam (incl. Amstelveen/Hoofddorp/Schiphol/Haarlem/Diemen/Zaandam/Weesp), 8=Rotterdam/The Hague/Utrecht (incl. Schiedam/Delft/Rijswijk/Zoetermeer/Maassluis/Dordrecht/Nootdorp), 6=Leiden/Hilversum/Hoevelaken, 0=outside NL Tier 1.
Visa: kennismigrant or EU Blue Card. Reject if JD has explicit EU/NL work-right requirement.
CRITICAL: Do NOT use "UK Skilled Worker Visa" or any UK visa language for this role.
  All visa/sponsorship notes must reference kennismigrant or EU Blue Card only.
Salary threshold: €90,000 (not £80k). Show in EUR. Use salary_gate="tbc" if not stated.
SALARY RANGE: check UPPER end only — upper > €90,000 → salary_gate = "passed".
MONTHLY SALARY: If salary is stated per month (e.g. "€6,500/month", "€7,100 gross/month",
  "per maand"), convert to annual by multiplying × 12 ONLY. Do NOT add estimated bonuses or
  allowances. Compare the annual figure to €90,000. Example: €7,100/month × 12 = €85,200 <
  €90,000 → salary_gate = "failed". Do NOT set salary_gate="passed" for monthly salaries
  below this annual equivalent.
Salary estimation (if unstated): estimate in EUR. Use 2025–2026 Netherlands analytics market
  rates. Set salary_stated = "Not stated (est. €X–Y)" e.g. "Not stated (est. €90,000–€110,000)".
  Round to nearest €5,000.
Sponsor KB (NL): Use your training knowledge. Apply company_sponsor_kb = "Known sponsor" (3 pts)
  for companies highly likely to have IND kennismigrant registration: AEX/AMX index-listed
  companies, major global tech/fintech with large NL offices (e.g. ASML, Booking.com, Adyen,
  ING, ABN AMRO, Philips, Shell, Unilever — as examples of the category, not an exhaustive list),
  and any multinational operating at Netherlands scale (500+ NL employees, global offices).
  Apply "Uncertain" for early-stage startups, small/niche firms, or companies you have low
  confidence about. Use your full training knowledge — do not restrict to named companies only.
""",
    "se": """
=== MARKET CONTEXT: Sweden ===
Location (0-10): 10=Stockholm, 8=Gothenburg/Malmö, 0=outside SE Tier 1.
Visa: Swedish arbetstillstånd (Migrationsverket). Reject if JD has explicit EU/SE work-right requirement.
CRITICAL: Do NOT use "UK Skilled Worker Visa" or any UK visa language for this role.
  All visa/sponsorship notes must reference arbetstillstånd or Migrationsverket only.
Salary threshold: SEK 800,000 (not £80k). Show in SEK. Use salary_gate="tbc" if not stated.
SALARY RANGE: check UPPER end only — upper > SEK 800,000 → salary_gate = "passed".
MONTHLY SALARY: If salary is stated per month (e.g. "SEK 65,000/month"), convert to annual
  by multiplying × 12 ONLY. Example: SEK 65,000/month × 12 = SEK 780,000 < SEK 800,000 →
  salary_gate = "failed". Do NOT add estimated bonuses or allowances.
Salary estimation (if unstated): estimate in SEK. Use 2025–2026 Sweden analytics market rates.
  Set salary_stated = "Not stated (est. SEK X–Y)" e.g. "Not stated (est. SEK 750,000–950,000)".
  Round to nearest SEK 25,000.
Sponsor KB (SE): Use your training knowledge. Apply company_sponsor_kb = "Known sponsor" (3 pts)
  for companies highly likely to have Migrationsverket arbetstillstånd approval: OMX Stockholm-listed
  companies, major global tech/fintech with large SE offices (e.g. Spotify, Klarna, Ericsson,
  Volvo, IKEA, H&M, Nordea — as examples of the category, not an exhaustive list), and any
  multinational operating at Sweden scale (500+ SE employees, global offices).
  Apply "Uncertain" for early-stage startups, small/niche firms, or companies you have low
  confidence about. Use your full training knowledge — do not restrict to named companies only.
""",
    "de": """
=== MARKET CONTEXT: Germany ===
Location (0-10): 10=Berlin, 8=Munich/Frankfurt/Hamburg, 6=Düsseldorf/Cologne/Bonn (incl. Essen/Duisburg/Dortmund/Leverkusen/Mainz/Wiesbaden/Eschborn), 4=Stuttgart/Hannover/Nuremberg/Karlsruhe/Leipzig/Bremen, 0=outside DE tiers.
Visa: EU Blue Card (Blaue Karte EU) — candidate-driven. No employer sponsor licence required.
  Candidate applies to Ausländerbehörde after receiving a job offer. Employer simply hires.
CRITICAL: Do NOT use "UK Skilled Worker Visa" or any UK visa language for this role.
  All visa/sponsorship notes must reference EU Blue Card / Blaue Karte EU only.
  Set company_sponsor_kb = "Known sponsor" (3 pts) for DAX-listed companies (SAP, Siemens,
  Deutsche Bank, BMW, Volkswagen, Allianz, Bayer, BASF, Adidas, Merck) and global tech with
  DE HQ or large DE presence (Zalando, Delivery Hero, HelloFresh, N26, Celonis, Personio).
  Apply "Uncertain" for early-stage startups, small firms, or unknown companies.
Salary threshold: €90,000 (not £80k). Show in EUR. Use salary_gate="tbc" if not stated.
SALARY RANGE: check UPPER end only — upper > €90,000 → salary_gate = "passed".
MONTHLY SALARY: If salary is stated per month, convert to annual by multiplying × 12 ONLY.
  Do NOT add estimated bonuses or allowances. Compare to €90,000.
Salary estimation (if unstated): estimate in EUR. Use 2025–2026 Germany analytics market rates.
  Berlin/Munich add ~10-15% premium. Set salary_stated = "Not stated (est. €X–Y)"
  e.g. "Not stated (est. €85,000–€110,000)". Round to nearest €5,000.
CRITICAL — Language gate: if JD implies or states German language required for daily ops →
  set action=reject and rejection_reason="German language required — role not English-first".
  Only pass JDs where English is the stated or implied working language.
""",
    "dk": """
=== MARKET CONTEXT: Denmark ===
Location (0-10): 10=Copenhagen (incl. Frederiksberg/Hellerup/Gentofte/Kongens Lyngby/Ballerup/Søborg/Glostrup/Brøndby/Herlev/Valby/Ørestad), 8=Aarhus, 0=outside DK Tier 1.
Visa: Danish Pay Limit Scheme (Beløbsordningen) work and residence permit — salary-threshold
  based (~DKK 514,000/yr minimum; any role passing our DKK 700,000 gate clears it). Employer
  supports the application; SIRI-certified employers can use the Fast-track scheme. Denmark
  is NOT part of the EU Blue Card scheme (Danish opt-out) — never mention Blue Card for DK roles.
CRITICAL: Do NOT use "UK Skilled Worker Visa" or any UK visa language for this role.
  All visa/sponsorship notes must reference the Pay Limit Scheme (Beløbsordningen) only.
  Reject if JD has explicit EU/EEA/Nordic/DK work-right requirement.
Salary threshold: DKK 700,000 (not £80k). Show in DKK. Use salary_gate="tbc" if not stated.
SALARY RANGE: check UPPER end only — upper > DKK 700,000 → salary_gate = "passed".
MONTHLY SALARY: Danish salaries are commonly stated per month (e.g. "DKK 60,000/month",
  "kr. 58.000 om måneden"). Convert to annual by multiplying × 12 ONLY. Do NOT add pension
  contributions or bonuses. Example: DKK 55,000/month × 12 = DKK 660,000 < DKK 700,000 →
  salary_gate = "failed".
Salary estimation (if unstated): estimate in DKK. Use 2025–2026 Denmark analytics market
  rates. Copenhagen adds ~10-15% premium. Set salary_stated = "Not stated (est. DKK X–Y)"
  e.g. "Not stated (est. DKK 650,000–DKK 800,000)". Round to nearest DKK 25,000.
Sponsor KB (DK): Use your training knowledge. Apply company_sponsor_kb = "Known sponsor" (3 pts)
  for companies highly likely to be SIRI Fast-track certified or routinely hiring international
  talent: C25/OMX Copenhagen-listed companies, major global tech/pharma with large DK offices
  (e.g. Novo Nordisk, Maersk, Vestas, Danske Bank, LEGO, Carlsberg, Novonesis, Trustpilot,
  Unity, Zendesk — as examples of the category, not an exhaustive list), and any multinational
  operating at Denmark scale (500+ DK employees, global offices).
  Apply "Uncertain" for early-stage startups, small/niche firms, or companies you have low
  confidence about. Use your full training knowledge — do not restrict to named companies only.
CRITICAL — Language gate: if JD implies or states Danish language required for daily ops →
  set action=reject and rejection_reason="Danish language required — role not English-first".
  Only pass JDs where English is the stated or implied working language.
""",
    "ie": """
=== MARKET CONTEXT: Ireland ===
Location (0-10): 10=Dublin (incl. Dún Laoghaire/Sandyford/Leopardstown/Blackrock/Swords/Citywest), 8=Cork, 6=Galway/Limerick, 0=outside IE Tier 1.
IMPORTANT: Northern Ireland (Belfast/Derry) is the UK, NOT Ireland — score 0 and reject
  (different immigration system; this pipeline treats only the Republic of Ireland as IE).
Visa: Critical Skills Employment Permit (CSEP) — analytics/ICT roles are on Ireland's
  Critical Skills Occupations List; any role passing our €90,000 gate is far above the CSEP
  salary thresholds. Employer and candidate jointly apply; no labour market needs test for
  critical skills roles. Reject if JD has explicit EU/EEA work-right or Stamp 4 requirement.
CRITICAL: Do NOT use "UK Skilled Worker Visa" or any UK visa language for this role.
  All visa/sponsorship notes must reference the Critical Skills Employment Permit only.
Salary threshold: €90,000 (not £80k). Show in EUR. Use salary_gate="tbc" if not stated.
SALARY RANGE: check UPPER end only — upper > €90,000 → salary_gate = "passed".
MONTHLY SALARY: If salary is stated per month, convert to annual by multiplying × 12 ONLY.
  Do NOT add estimated bonuses or allowances. Compare to €90,000.
Salary estimation (if unstated): estimate in EUR. Use 2025–2026 Ireland analytics market
  rates. Dublin adds ~10-15% premium; US tech EMEA HQs pay well above local market.
  Set salary_stated = "Not stated (est. €X–Y)" e.g. "Not stated (est. €85,000–€105,000)".
  Round to nearest €5,000.
Sponsor KB (IE): Use your training knowledge. Apply company_sponsor_kb = "Known sponsor" (3 pts)
  for companies that routinely sponsor Critical Skills Employment Permits: US tech/fintech
  EMEA headquarters in Dublin (e.g. Google, Meta, Stripe, LinkedIn, Microsoft, Amazon,
  Salesforce, HubSpot, Intercom — as examples of the category, not an exhaustive list),
  ISEQ-listed Irish plcs (Ryanair, AIB, Bank of Ireland, Kerry Group, CRH, Flutter), and any
  multinational operating at Ireland scale (500+ IE employees, global offices).
  Apply "Uncertain" for early-stage startups, small/niche firms, or companies you have low
  confidence about. Use your full training knowledge — do not restrict to named companies only.
No language gate — Ireland is English-speaking.
""",
    "ae": """
=== MARKET CONTEXT: United Arab Emirates ===
Location (0-10): 10=Dubai (incl. DIFC/Dubai Internet City/Dubai Media City/Jumeirah/Business Bay/JLT/Sheikh Zayed Road/Jebel Ali), 8=Abu Dhabi (incl. ADGM/Masdar City/Al Reem Island), 6=Sharjah/Ajman, 0=outside AE Tier 1.
Visa: UAE Employment Visa / Work Permit — employer-sponsored. Employer applies to MOHRE for
  work permit; candidate then obtains UAE residence visa. No candidate-driven standalone path.
CRITICAL: Do NOT use "UK Skilled Worker Visa", "EU Blue Card", "kennismigrant", or any non-UAE
  visa language. All visa/sponsorship notes must reference UAE Employment Visa / Work Permit only.
Salary threshold: AED 360,000/year (not £80k). Show in AED. Use salary_gate="tbc" if not stated.
  NOTE: UAE salaries are TAX-FREE — AED 360,000 gross = AED 360,000 net purchasing power.
SALARY RANGE: check UPPER end only — upper > AED 360,000 → salary_gate = "passed".
MONTHLY SALARY: UAE salaries are commonly stated per month (e.g. "AED 30,000/month",
  "AED 35,000 per month"). Convert to annual by multiplying × 12 ONLY. Do NOT add housing
  allowance, flight tickets, or other benefits — base salary only.
  Example: AED 28,000/month × 12 = AED 336,000 < AED 360,000 → salary_gate = "failed".
  Example: AED 32,000/month × 12 = AED 384,000 > AED 360,000 → salary_gate = "passed".
Salary estimation (if unstated): estimate in AED. Use 2025–2026 UAE analytics market rates.
  Dubai adds ~15-20% premium over other emirates. Set salary_stated = "Not stated (est. AED X–Y)"
  e.g. "Not stated (est. AED 350,000–AED 480,000)". Round to nearest AED 10,000.
Sponsor KB (AE): Use your training knowledge. Apply company_sponsor_kb = "Known sponsor" (3 pts)
  for companies with established UAE presence that routinely hire international talent: major
  global tech/fintech with UAE offices (e.g. Amazon, Google, Microsoft, Meta, Salesforce,
  Careem, noon, Deliveroo — as examples of the category, not an exhaustive list), UAE
  flagship employers (Emirates Group, Etisalat/e&, du, DP World, ADNOC, Emaar, DAMAC), and
  any multinational with 200+ UAE employees. Apply "Uncertain" for early-stage startups, small
  firms, or companies you have low confidence about. Use your full training knowledge.
Language gate (AE): If JD explicitly states Arabic language is required/preferred for
  daily work operations → set action=reject and rejection_reason="Arabic language required".
  Most international company roles in UAE use English — only reject on explicit Arabic requirement.
No EU citizenship or residency requirement ever applies to UAE — no such gates exist.
""",
}


def _build_system_prompt(market: str = "uk") -> str:
    """Return market-appropriate system prompt for Claude scoring."""
    _intros = {
        "nl": "seeking Netherlands roles (kennismigrant or EU Blue Card sponsorship required)",
        "se": "seeking Sweden roles (Swedish arbetstillstånd/work permit sponsorship required)",
        "de": "seeking Germany roles (EU Blue Card / Blaue Karte EU — candidate-driven, no employer sponsor licence required)",
        "dk": "seeking Denmark roles (Danish Pay Limit Scheme / Beløbsordningen work permit — salary-threshold based, employer-supported)",
        "ie": "seeking Ireland roles (Critical Skills Employment Permit sponsorship required)",
        "ae": "seeking UAE roles (UAE Employment Visa / Work Permit sponsorship required — employer-sponsored)",
    }
    base = SCORE_SYSTEM
    if market in _intros:
        base = base.replace(
            "seeking UK roles (Skilled Worker Visa sponsorship required)",
            _intros[market],
            1,
        )
    addon = _MARKET_ADDONS.get(market, "")
    return base + addon if addon else base


def _build_user_prompt(job: dict) -> str:
    import html as _html_mod
    exp_display = (job.get("experience_years") or {}).get("display") or "Not specified"
    desc        = _html_mod.unescape((job.get("description") or "")[:10000])

    # Deterministic pre-extraction of salary from description header lines.
    # Avoids relying on Claude to find "Salary: £X" buried in prose.
    salary_hint = _extract_salary_hint_from_description(job.get("description") or "")
    salary_hint_str = salary_hint if salary_hint else "Not found by pre-scan"

    # Pass ALL non-description raw Apify fields to Claude so it can find salary,
    # work_mode, and other signals regardless of which field names Apify used.
    # Description is included separately below to avoid duplication.
    _SKIP = {"description", "descriptionHtml", "jd_text"}
    raw_meta = {k: v for k, v in job.items() if k not in _SKIP and v is not None}
    raw_meta_str = json.dumps(raw_meta, indent=2)[:2500]  # cap to stay within token budget

    _source = job.get("_source", "")
    _linkedin_salary = job.get("salary") if _source != "adzuna" else "Not available"
    _adzuna_salary   = job.get("salary") if _source == "adzuna"  else "Not available"

    return f"""Score this job for {_CANDIDATE_NAME}:

Market: {job.get("market", "uk").upper()}
Company: {job.get("company_name", "Unknown")}
Title: {job.get("job_title", "Unknown")}
Location: {job.get("location", "Unknown")}
Posted: {job.get("posted_date") or job.get("postedDate") or "Unknown"}
Experience Required (extracted from JD): {exp_display}
LinkedIn URL: {job.get("job_url") or job.get("url") or ""}
LinkedIn/Apify structured salary: {_linkedin_salary or "Not available"}
Adzuna structured salary: {_adzuna_salary or "Not available"}
Salary extracted from description header: {salary_hint_str}

Raw Job Data (all structured fields — use to find salary, work_mode, etc.):
{raw_meta_str}

Job Description:
{desc}"""


# Accumulates real token counts across all API calls this run (no caller changes needed)
_api_usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0,
              "cache_read_tokens": 0, "cache_write_tokens": 0}


def call_claude_api(system: str, user_prompt: str, model: str, api_key: str) -> str:
    payload = json.dumps({
        "model":      model,
        "max_tokens": 1500,
        "system":     [{"type": "text", "text": system,
                        "cache_control": {"type": "ephemeral"}}],
        "messages":   [{"role": "user", "content": user_prompt}],
    }).encode()

    req = _ureq.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload, method="POST"
    )
    req.add_header("x-api-key",           api_key)
    req.add_header("anthropic-version",   "2023-06-01")
    req.add_header("anthropic-beta",      "prompt-caching-2024-07-31")
    req.add_header("content-type",        "application/json")

    with _ureq.urlopen(req, timeout=45) as resp:
        result = json.loads(resp.read())

    usage = result.get("usage", {})
    _api_usage["input_tokens"]       += usage.get("input_tokens", 0)
    _api_usage["output_tokens"]      += usage.get("output_tokens", 0)
    _api_usage["cache_read_tokens"]  += usage.get("cache_read_input_tokens", 0)
    _api_usage["cache_write_tokens"] += usage.get("cache_creation_input_tokens", 0)
    _api_usage["calls"]              += 1

    return result["content"][0]["text"]


_BATCH_HEADERS = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta":    "message-batches-2024-09-24,prompt-caching-2024-07-31",
    "content-type":      "application/json",
}
_BATCH_STATE_PATH = ROOT / "data" / "pipeline" / "batch_state.json"


def _poll_batch(batch_id: str, api_key: str) -> dict[str, dict]:
    """Poll an existing batch until done (max 240 min), return {custom_id: message}."""
    headers = {**_BATCH_HEADERS, "x-api-key": api_key}
    deadline   = time.time() + 240 * 60
    poll_start = time.time()
    last_status = "in_progress"
    while time.time() < deadline:
        req = _ureq.Request(
            f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
            headers=headers)
        # Retry up to 3 times on transient network errors before giving up
        for _attempt in range(3):
            try:
                with _ureq.urlopen(req, timeout=30) as r:
                    status = json.loads(r.read())
                break
            except Exception as _net_err:
                if _attempt == 2:
                    raise
                print(f"[score_jobs] Network error polling batch (attempt {_attempt+1}/3) — "
                      f"retrying in 30s ({_net_err})")
                time.sleep(30)
        last_status = status["processing_status"]
        counts = status.get("request_counts", {})
        print(f"[score_jobs] Batch {batch_id}: {last_status} — "
              f"success={counts.get('succeeded',0)} error={counts.get('errored',0)} "
              f"processing={counts.get('processing',0)}")
        if last_status == "ended":
            break
        # O4: adaptive backoff — poll fast early (quick batches), slow down as time passes
        elapsed = time.time() - poll_start
        if elapsed < 120:    time.sleep(15)   # <2 min: 15s
        elif elapsed < 600:  time.sleep(30)   # 2–10 min: 30s
        else:                time.sleep(60)   # >10 min: 60s
    else:
        print("[score_jobs] WARNING: batch poll ceiling (240 min) reached")
        if last_status != "ended":
            raise RuntimeError(
                f"Batch {batch_id} still {last_status} after 240 min. "
                "Re-run score_jobs.py to resume polling, or delete "
                "data/pipeline/batch_state_<market>.json to force a new batch for that market."
            )

    req2 = _ureq.Request(
        f"https://api.anthropic.com/v1/messages/batches/{batch_id}/results",
        headers=headers)
    with _ureq.urlopen(req2, timeout=60) as r:
        raw = r.read().decode()

    results = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        cid = rec["custom_id"]
        results[cid] = rec["result"]["message"] if rec["result"]["type"] == "succeeded" else None
    return results




def _check_batch_completed(batch_id: str, api_key: str) -> bool:
    """Return True if Anthropic reports this batch as ended with all requests succeeded."""
    try:
        headers = {**_BATCH_HEADERS, "x-api-key": api_key}
        req = _ureq.Request(
            f"https://api.anthropic.com/v1/messages/batches/{batch_id}",
            headers=headers)
        with _ureq.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        counts = data.get("request_counts", {})
        return (data.get("processing_status") == "ended"
                and counts.get("succeeded", 0) > 0
                and counts.get("processing", 0) == 0)
    except Exception:
        return False


def _get_or_submit_batch_id(requests_payload: list, api_key: str,
                            state_path: Path = _BATCH_STATE_PATH) -> str:
    """Return today's batch_id (resuming or submitting). Does NOT poll — call _poll_batch separately."""
    if state_path.exists():
        try:
            saved = json.loads(state_path.read_text())
            if saved.get("date") == TODAY:
                batch_id = saved["batch_id"]
                if saved.get("status") == "done":
                    print(f"[score_jobs] {state_path.name}: already done today — re-fetching results")
                    return batch_id
                if saved.get("status") in ("polling", "cancelled"):
                    if _check_batch_completed(batch_id, api_key):
                        print(f"[score_jobs] Batch {batch_id} completed on Anthropic side — will fetch")
                    else:
                        print(f"[score_jobs] Resuming batch {batch_id} from {state_path.name}")
                    return batch_id
        except Exception as e:
            print(f"[score_jobs] Warning: could not read {state_path.name} ({e}), submitting new batch")

    # Submit new batch
    headers = {**_BATCH_HEADERS, "x-api-key": api_key}
    payload = json.dumps({"requests": requests_payload}).encode()
    req = _ureq.Request(
        "https://api.anthropic.com/v1/messages/batches",
        data=payload, method="POST", headers=headers)
    with _ureq.urlopen(req, timeout=60) as r:
        batch = json.loads(r.read())
    batch_id = batch["id"]
    mkt_tag = state_path.stem.replace("batch_state_", "").upper()
    print(f"[score_jobs] {mkt_tag} batch submitted: {batch_id} ({len(requests_payload)} requests)")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"date": TODAY, "batch_id": batch_id, "status": "polling"}))
    return batch_id


def _load_or_submit_batch(requests_payload: list, api_key: str,
                          state_path: Path = _BATCH_STATE_PATH) -> dict[str, dict]:
    """Submit (or resume) batch then poll to completion. Used in non-parallel fallback."""
    batch_id = _get_or_submit_batch_id(requests_payload, api_key, state_path=state_path)
    try:
        results = _poll_batch(batch_id, api_key)
    except Exception:
        state_path.write_text(json.dumps(
            {"date": TODAY, "batch_id": batch_id, "status": "polling"}))
        raise
    state_path.write_text(json.dumps(
        {"date": TODAY, "batch_id": batch_id, "status": "done"}))
    return results


def _accumulate_batch_usage(message: dict) -> None:
    usage = message.get("usage", {})
    _api_usage["input_tokens"]       += usage.get("input_tokens", 0)
    _api_usage["output_tokens"]      += usage.get("output_tokens", 0)
    _api_usage["cache_read_tokens"]  += usage.get("cache_read_input_tokens", 0)
    _api_usage["cache_write_tokens"] += usage.get("cache_creation_input_tokens", 0)
    _api_usage["calls"]              += 1


def parse_score_response(raw: str) -> Optional[dict]:
    """Extract JSON from Claude response even if there's surrounding text."""
    raw = raw.strip()
    try: return json.loads(raw)
    except ValueError: pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try: return json.loads(m.group(0))
        except ValueError: pass
    return None


def _apply_hard_overrides(r: dict, job: Optional[dict] = None) -> dict:
    """Enforce critical scoring gates in code regardless of what Claude returned."""
    changed = []

    # Propagate market from job into result so downstream helpers (e.g.
    # _canonical_rejection_reason) can read it from r without needing job.
    # Claude's response JSON never includes a market field.
    if job is not None and "market" not in r:
        r["market"] = (job.get("market") or "uk").lower()

    # Gate 1: Visa denial is non-negotiable
    if r.get("visa_sponsorship_status") == "Rejected" and r.get("action") != "reject":
        r["action"] = "reject"
        r.setdefault("flags", []).append("OVERRIDE: visa_sponsorship=Rejected forces reject")
        changed.append("visa_sponsorship=Rejected → action=reject")

    # Gate 1b: Visa "Confirmed" without JD evidence — downgrade to Unconfirmed.
    # Claude leaks world knowledge for large known sponsors (Tesco, Barclays, Emirates etc.),
    # setting "Confirmed" even when the JD is entirely silent on sponsorship. Per CLAUDE.md,
    # "Confirmed" requires explicit JD text. If none of the market-specific or generic
    # sponsorship keywords appear in the JD, override to Unconfirmed and strip the +5 pts
    # so downstream Gates 3/4 re-evaluate action on the corrected score.
    # Applies to ALL markets (uk, nl, de, dk, ie, ae, se).
    _VISA_CONFIRM_KEYWORDS = {
        # Generic English phrases (all markets) — fired when company explicitly supports immigration.
        # Non-English terms (blaue karte, arbetstillstånd etc.) are kept as a safety net but will
        # rarely fire in practice because non-English JDs are auto-rejected before reaching Pass 2.
        "visa", "sponsor", "sponsorship", "skilled worker", "right to work",
        "work permit", "immigration", "work authoris", "relocation support",
        "global mobility", "residence permit",
        # UK — Skilled Worker Visa / UKVI / Home Office
        "certificate of sponsorship", "cos", "ukvi", "tier 2", "sponsor licence",
        "home office", "indefinite leave", "skilled worker visa",
        # NL — Kennismigrant / 30% Ruling (Dutch companies mention 30% ruling alongside sponsorship)
        "kennismigrant", "highly skilled migrant", "30% ruling",
        # NL + DE — EU Blue Card (English name for both markets' permit scheme)
        "blue card", "eu blue card",
        # DE — Blaue Karte EU (German terms — safety net; unlikely in qualifying English JD)
        "blaue karte", "niederlassungserlaubnis",
        # SE — Arbetstillstånd (Swedish term — safety net; unlikely in qualifying English JD)
        "arbetstillstånd", "work authorization",
        # DK — Pay Limit Scheme / SIRI fast-track (Danish immigration authority)
        "pay limit scheme", "beløbsordningen", "siri", "fast-track scheme",
        # IE — Critical Skills Employment Permit / Irish work permit stamps
        "critical skills", "employment permit", "csep", "stamp 1",
        # AE — UAE Employment Visa / Work Permit
        "employment visa", "residence visa", "mohre", "work visa",
    }
    if r.get("visa_sponsorship_status") == "Confirmed" and job is not None:
        _jd_lower = (job.get("description") or "").lower()
        if not any(kw in _jd_lower for kw in _VISA_CONFIRM_KEYWORDS):
            r["visa_sponsorship_status"] = "Unconfirmed"
            _bd = r.get("fit_score_breakdown") or {}
            _visa_pts = _bd.get("visa_sponsorship", 0)
            if _visa_pts > 0:
                _bd["visa_sponsorship"] = 0
                r["fit_score_breakdown"] = _bd
                r["fit_score"] = r.get("fit_score", 0) - _visa_pts
            r.setdefault("flags", []).append(
                "OVERRIDE: visa=Confirmed but no JD keyword evidence → Unconfirmed"
            )
            changed.append("visa_sponsorship: Confirmed→Unconfirmed (no JD evidence)")

    # Gate 2: Salary clearly below £80k — only when explicitly stated, never on Claude's estimate.
    # CLAUDE.md rule: "No salary stated → do not disqualify, flag as Salary TBC"
    # "Not stated (est. £X–Y)" is an estimate — treat as TBC, not explicit.
    _salary_stated = r.get("salary_stated") or ""
    _salary_is_explicit = (
        bool(_salary_stated)
        and _salary_stated not in ("", "Not stated", "Not provided")
        and not _salary_stated.startswith("Not stated (est.")
    )
    # Salary sanity: if the highest parsed number in salary_stated >= market threshold,
    # the upper bound of the range passes — override any Claude salary_gate=failed.
    # Prevents false rejections when Claude checks lower end of a range instead of upper.
    # Market-aware thresholds: UK £80k, NL €90k, SE SEK 800k, DE €90k, DK DKK 700k, IE €90k.
    _SALARY_THRESHOLDS = _COMMON_SALARY_THRESHOLDS  # single source: scripts/common.py
    # Remote/contract roles use 80% salary threshold (SALARY_THRESHOLDS_REMOTE).
    _is_remote_contract = r.get("is_remote_only") or r.get("is_contract")
    _thr_dict   = _COMMON_SALARY_THRESHOLDS_REMOTE if _is_remote_contract else _COMMON_SALARY_THRESHOLDS
    _market_thr = _thr_dict.get(r.get("market", "uk"), 80_000)
    # Pre-parse salary numbers once — reused by Gate 2b and Gate 2 sanity check.
    _sal_nums_raw = re.findall(r"\d[\d,]*", _salary_stated.replace(",", "")) if _salary_is_explicit else []
    _sal_nums = []
    for n in _sal_nums_raw:
        try: _sal_nums.append(int(n))
        except ValueError: pass

    # Gate 2b: Monthly salary annualization (NL/SE).
    # Claude may compare monthly figures raw against the annual threshold — this gate
    # overrides salary_gate regardless of what Claude returned, using ×12 only.
    if _salary_is_explicit and "month" in _salary_stated.lower():
        _sal_nums_monthly = [n for n in _sal_nums if 500 < n < 100_000]
        if _sal_nums_monthly:
            _monthly_upper = max(_sal_nums_monthly)
            _annual_equiv  = _monthly_upper * 12
            if _annual_equiv < _market_thr:
                r["salary_gate"] = "failed"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: monthly {_monthly_upper:,}/mo × 12 = {_annual_equiv:,} "
                    f"< {_market_thr:,} threshold → salary_gate=failed")
                changed.append(f"monthly {_monthly_upper:,} × 12 = {_annual_equiv:,} < {_market_thr:,} → failed")
                # Scrub stale salary-passes language from pros — now invalid after downgrade.
                _pros_val = r.get("pros")
                if _pros_val:
                    def _is_salary_pass_bullet(ln: str) -> bool:
                        lo = ln.lower()
                        return (any(c in lo for c in ["salary", "£", "€", "sek", "dkk"])
                                and any(w in lo for w in ["meets", "exceeds", "above", "passes", "sufficient"])
                                and "threshold" in lo)
                    if isinstance(_pros_val, list):
                        r["pros"] = [p for p in _pros_val if not _is_salary_pass_bullet(p)]
                    else:
                        r["pros"] = "\n".join(
                            ln for ln in _pros_val.split("\n") if not _is_salary_pass_bullet(ln)
                        ).strip()
            elif _annual_equiv >= _market_thr and r.get("salary_gate") != "passed":
                r["salary_gate"] = "passed"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: monthly {_monthly_upper:,}/mo × 12 = {_annual_equiv:,} "
                    f">= {_market_thr:,} threshold → salary_gate=passed")
                changed.append(f"monthly {_monthly_upper:,} × 12 = {_annual_equiv:,} >= {_market_thr:,} → passed")

    # Gate 2c: Day-rate annualisation (contract roles).
    # Claude may set salary_gate incorrectly for "£450/day" (comparing raw daily figure to threshold).
    # Contract roles always use the 80% remote threshold — no strict visa requirement.
    if _salary_is_explicit and re.search(r'/\s*day\b|per\s+day', _salary_stated, re.I):
        _day_annual = _annualise_day_rate(_salary_stated)
        if _day_annual is not None:
            _thr_day = _COMMON_SALARY_THRESHOLDS_REMOTE.get(r.get("market", "uk"), 64_000)
            if _day_annual < _thr_day:
                r["salary_gate"] = "failed"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: day rate annualised {_day_annual:,.0f}/yr "
                    f"< {_thr_day:,} (80% gate) → salary_gate=failed")
                changed.append(f"day rate {_day_annual:,.0f}/yr < {_thr_day:,} → failed")
            elif _day_annual >= _thr_day and r.get("salary_gate") != "passed":
                r["salary_gate"] = "passed"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: day rate annualised {_day_annual:,.0f}/yr "
                    f">= {_thr_day:,} (80% gate) → salary_gate=passed")
                changed.append(f"day rate {_day_annual:,.0f}/yr >= {_thr_day:,} → passed")

    if r.get("salary_gate") == "failed" and _salary_is_explicit:
        if _sal_nums:
            _upper = max(_sal_nums)
            if _upper < 1000:
                _upper *= 1000   # K notation: 89 → 89000
            if _upper >= _market_thr:
                r["salary_gate"] = "passed"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: salary upper bound {_upper:,} >= {_market_thr:,} threshold — gate passed (was failed)")
                changed.append(f"salary upper {_upper:,} >= {_market_thr:,} → gate passed")
                # Scrub stale salary-gate-failed bullets from cons — Claude wrote them
                # before the override ran; leaving them in creates a false hard-blocker signal.
                # cons may be a list (fresh Claude output) or a string (reconstructed entry).
                _cons_val = r.get("cons")
                if _cons_val:
                    def _is_salary_fail_bullet(ln: str) -> bool:
                        lo = ln.lower()
                        return (("salary_gate" in lo and "fail" in lo)
                                or ("falls below" in lo and "threshold" in lo
                                    and any(c in ln for c in ["€", "£", "SEK", "DKK", "salary"])))
                    if isinstance(_cons_val, list):
                        r["cons"] = [ln for ln in _cons_val if not _is_salary_fail_bullet(ln)]
                    else:
                        r["cons"] = "\n".join(
                            ln for ln in _cons_val.split("\n") if not _is_salary_fail_bullet(ln)
                        ).strip()
    # Gate 2 reverse sanity: if salary is explicitly stated and max parsed number is below
    # threshold, force salary_gate=failed even if Claude returned "passed".
    # Catches the case where Claude is confused by qualifiers like "(DOE)" and passes a
    # clearly-below-threshold range (e.g. £55k–£70k). Complement to the upgrade path above.
    if _salary_is_explicit and _sal_nums:
        _upper_check = max(_sal_nums)
        if _upper_check < 1000:
            _upper_check *= 1000   # K notation: 70 → 70000
        if _upper_check < _market_thr and r.get("salary_gate") != "failed":
            r["salary_gate"] = "failed"
            r.setdefault("flags", []).append(
                f"OVERRIDE: stated salary upper {_upper_check:,} < {_market_thr:,} "
                f"threshold — gate downgraded to failed (Claude said passed)")
            changed.append(f"salary upper {_upper_check:,} < {_market_thr:,} → gate failed (corrected)")
            # Scrub stale salary-passes language from pros — now invalid after downgrade.
            _pros_val = r.get("pros")
            if _pros_val:
                def _is_salary_pass_bullet(ln: str) -> bool:  # noqa: F811
                    lo = ln.lower()
                    return (any(c in lo for c in ["salary", "£", "€", "sek"])
                            and any(w in lo for w in ["meets", "exceeds", "above", "passes", "sufficient"])
                            and "threshold" in lo)
                if isinstance(_pros_val, list):
                    r["pros"] = [p for p in _pros_val if not _is_salary_pass_bullet(p)]
                else:
                    r["pros"] = "\n".join(
                        ln for ln in _pros_val.split("\n") if not _is_salary_pass_bullet(ln)
                    ).strip()
    if (r.get("salary_gate") == "failed"
            and _salary_is_explicit
            and r.get("action") != "reject"):
        r["action"] = "reject"
        r.setdefault("flags", []).append("OVERRIDE: salary_gate=failed (stated) forces reject")
        changed.append("salary_gate=failed (stated) → action=reject")

    # Gate 3: Score < 60 must always be reject
    if r.get("fit_score", 100) < 60 and r.get("action") != "reject":
        r["action"] = "reject"
        r.setdefault("flags", []).append("OVERRIDE: fit_score<60 forces reject")
        changed.append(f"fit_score={r['fit_score']}<60 → action=reject")

    # Gate 4: Score ≥ 75 with no blockers must be shortlist (not review)
    if (r.get("fit_score", 0) >= 75
            and r.get("action") == "review"
            and r.get("visa_sponsorship_status") != "Rejected"
            and r.get("salary_gate") != "failed"):
        r["action"] = "shortlist"
        r.setdefault("flags", []).append("OVERRIDE: fit_score≥75 with no blockers → shortlist")
        changed.append(f"fit_score={r['fit_score']}≥75, no blockers → shortlist")

    # Gate 5: Correct action when Claude rejected for salary/visa that our overrides cleared.
    # If action is still "reject" but no hard blocker actually applies, upgrade to review/shortlist.
    if (r.get("action") == "reject"
            and r.get("visa_sponsorship_status") != "Rejected"
            and r.get("salary_gate") != "failed"
            and r.get("fit_score", 0) >= 60):
        new_action = "shortlist" if r.get("fit_score", 0) >= 75 else "review"
        r["action"] = new_action
        r.setdefault("flags", []).append(
            f"OVERRIDE: no hard blockers after gate fixes → upgraded to {new_action}")
        changed.append(f"no hard blockers remain → {new_action}")
        # Clear stale rejection_reason — job upgraded to {new_action}; it was set
        # before blockers were cleared, so it no longer reflects the final assessment.
        r["rejection_reason"] = None

    # Gate 5b: Non-English language requirement — role requires a language the candidate
    # does not speak. Authoritative semantic check (Claude read the full JD). Overrides fit_score.
    if r.get("requires_non_english_language"):
        if r.get("action") != "reject":
            r["action"] = "reject"
            r.setdefault("flags", []).append("OVERRIDE: requires_non_english_language=true → reject")
            r["rejection_reason"] = (r.get("rejection_reason")
                or "Role requires non-English language proficiency")
            changed.append("requires_non_english_language=true → reject")

    # Gate 6: Role focus filter — block purely BI, analytics-engineering, or consulting roles
    role_focus = r.get("role_focus", "")
    domain_pts = (r.get("fit_score_breakdown") or {}).get("domain", 0)
    fit        = r.get("fit_score", 0)

    if role_focus == "analytics_engineering":
        if r.get("action") != "reject":
            r["action"] = "reject"
            r.setdefault("flags", []).append("OVERRIDE: role_focus=analytics_engineering → reject")
            r["rejection_reason"] = (r.get("rejection_reason")
                or "Analytics engineering/data modelling role — not aligned with analytics leadership profile")
            changed.append("role_focus=analytics_engineering → reject")

    elif role_focus == "ai_engineering":
        if r.get("action") != "reject":
            r["action"] = "reject"
            r.setdefault("flags", []).append("OVERRIDE: role_focus=ai_engineering → reject")
            r["rejection_reason"] = (r.get("rejection_reason")
                or "AI/ML engineering/infrastructure role — not aligned with analytics leadership profile")
            changed.append("role_focus=ai_engineering → reject")

    elif role_focus == "credit_risk":
        if r.get("action") != "reject":
            r["action"] = "reject"
            r.setdefault("flags", []).append("OVERRIDE: role_focus=credit_risk → reject")
            r["rejection_reason"] = (r.get("rejection_reason")
                or "Credit/risk strategy role — primary output is risk modelling, not analytics leadership")
            changed.append("role_focus=credit_risk → reject")

    elif role_focus == "bi_reporting":
        _title_lo = (job.get("job_title") or "").lower() if job else ""
        if "risk" in _title_lo:
            if r.get("action") != "reject":
                r["action"] = "reject"
                r.setdefault("flags", []).append("OVERRIDE: bi_reporting + risk title → reject")
                r["rejection_reason"] = (r.get("rejection_reason")
                    or "Risk reporting role — BI-flavoured risk function, not analytics leadership")
                changed.append("role_focus=bi_reporting, risk title → reject")
        elif domain_pts < 20:
            if r.get("action") != "reject":
                r["action"] = "reject"
                r.setdefault("flags", []).append(
                    "OVERRIDE: role_focus=bi_reporting + domain<20 → reject")
                r["rejection_reason"] = (r.get("rejection_reason")
                    or "Purely BI/reporting role — primary output is dashboards, not analytics strategy")
                changed.append("role_focus=bi_reporting, domain<20 → reject")
        else:
            if r.get("action") == "shortlist":
                r["action"] = "review"
                r.setdefault("flags", []).append(
                    "OVERRIDE: role_focus=bi_reporting at product/tech company → shortlist→review")
                changed.append("role_focus=bi_reporting, domain≥20 → review (not shortlist)")

    elif role_focus == "management_consulting":
        if fit < 88:
            if r.get("action") != "reject":
                r["action"] = "reject"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: role_focus=management_consulting + fit={fit}<88 → reject")
                r["rejection_reason"] = (r.get("rejection_reason")
                    or f"Consulting/advisory role — fit_score {fit} below the ≥88 threshold (CLAUDE.md)")
                changed.append(f"role_focus=management_consulting, fit={fit}<88 → reject")
        else:
            if r.get("action") == "shortlist":
                r["action"] = "review"
                r.setdefault("flags", []).append(
                    f"OVERRIDE: role_focus=management_consulting, fit={fit}≥88 → review (human judgment)")
                changed.append(f"role_focus=management_consulting, fit={fit}≥88 → review")

    elif role_focus == "market_pricing":
        if r.get("action") == "shortlist":
            r["action"] = "review"
            r.setdefault("flags", []).append(
                "OVERRIDE: role_focus=market_pricing → shortlist→review (pricing function, not analytics)")
            changed.append("role_focus=market_pricing → review (not shortlist)")

    elif role_focus == "insights_strategy":
        if r.get("action") != "reject":
            r["action"] = "reject"
            r.setdefault("flags", []).append("OVERRIDE: role_focus=insights_strategy → reject")
            r["rejection_reason"] = (r.get("rejection_reason")
                or "Insights/strategy role — primary output is qualitative insights or "
                   "operational management with no hands-on analytics tooling required")
            changed.append("role_focus=insights_strategy → reject")

    elif role_focus == "mixed" and job is not None:
        # If no analytics tooling OR analytical methodology signals appear anywhere in the JD,
        # Claude mislabelled it as 'mixed' when it should be 'insights_strategy'.
        # CLAUDE.md rule: "uncertain → prefer mixed" — override only when BOTH are absent:
        #   1. No specific tool names (SQL/Python/Tableau etc.)
        #   2. No broader analytical vocabulary (cohort/KPI/agentic/statistical etc.)
        # This prevents false positives on roles that have implicit technical requirements
        # (e.g. "BI experience", "agentic systems", "cohort decomposition") but don't
        # enumerate tool names in the essential skills list.
        _jd = (job.get("description") or "").lower()
        _TOOLING = {"sql", "python", "tableau", "looker", "bigquery", "redshift",
                    "power bi", "powerbi", "dbt", "spark", "databricks"}
        # Broader analytical signals that indicate hands-on technical work even without
        # specific tool names — any one of these blocks the insights_strategy override.
        _ANALYTICAL = {
            "cohort", "a/b test", "ab test", "experiment", "statistical",
            "regression", "segmentation", "attribution", "survival",
            "agentic", "genai", "gen ai", "gen-ai", "pipeline",
            "machine learning", "deep learning",
            "kpi", "decomposition", "modelling", "modeling",
            "dashboard", "quantitative", "business intelligence",
            "analytical framework", "analytics framework", "data model",
            "funnel", "bi ", "bi tool", "bi platform",
        }
        _has_tooling = any(t in _jd for t in _TOOLING)
        _has_analytical = any(t in _jd for t in _ANALYTICAL)
        if not _has_tooling and not _has_analytical:
            r["role_focus"] = "insights_strategy"
            if r.get("action") != "reject":
                r["action"] = "reject"
                r.setdefault("flags", []).append(
                    "OVERRIDE: role_focus=mixed + no analytics tooling or analytical vocab in JD "
                    "→ reclassified as insights_strategy → reject")
                r["rejection_reason"] = (r.get("rejection_reason")
                    or "Mixed classification but no SQL/Python/Tableau/Looker/BigQuery or "
                       "analytical methodology found in JD — reclassified as insights_strategy")
                changed.append("role_focus=mixed, no tooling or analytical vocab in JD → insights_strategy → reject")

    # Stamp role_type (deterministic — always overwrite any Claude value)
    r["role_type"] = _compute_role_type(
        bool(r.get("is_contract")), bool(r.get("is_remote_only"))
    )
    # Ensure eor_viability defaults to None when Claude omits it
    r.setdefault("eor_viability", None)

    if changed:
        print(f"    [override] Hard gates applied: {'; '.join(changed)}")
    return r


# Bare "not stated" patterns — no estimate was provided by Claude
_SALARY_BARE_MISSING = {"", "not stated", "not provided", "not disclosed",
                        "not available", "not specified"}


def _patch_missing_salary_estimate(score_result: dict, job: dict, key: str) -> dict:
    """
    Safety net: if Claude returned bare 'Not stated' (without an estimate), make a
    focused Haiku call to fill the gap. Only fires when Claude ignores the Pass 2
    salary estimation instruction — when Claude follows it correctly this is a no-op.
    Supports all markets (UK/GBP, NL/EUR, SE/SEK).
    """
    market = job.get("market", "uk")

    stated = (score_result.get("salary_stated") or "").strip().lower()
    needs_patch = (
        stated in _SALARY_BARE_MISSING
        or (stated.startswith("not stated") and "est." not in stated)
        or (stated.startswith("not provided") and "est." not in stated)
    )
    if not needs_patch:
        return score_result

    role     = job.get("job_title") or job.get("role") or "Unknown Role"
    company  = job.get("company_name") or job.get("company") or ""
    location = job.get("location") or "United Kingdom"

    _market_cfg = {
        "uk": {
            "label":         "UK",
            "currency":      "GBP",
            "example":       '{"salary_range": "£80,000–£110,000", "confidence": "medium"}',
            "currency_char": "£",
            "premium":       "London adds ~10-15% premium",
        },
        "nl": {
            "label":         "Netherlands",
            "currency":      "EUR",
            "example":       '{"salary_range": "€90,000–€110,000", "confidence": "medium"}',
            "currency_char": "€",
            "premium":       "Amsterdam adds ~10-15% premium",
        },
        "se": {
            "label":         "Sweden",
            "currency":      "SEK",
            "example":       '{"salary_range": "SEK 750,000–SEK 950,000", "confidence": "medium"}',
            "currency_char": "SEK",
            "premium":       "Stockholm adds ~10-15% premium",
        },
        "de": {
            "label":         "Germany",
            "currency":      "EUR",
            "example":       '{"salary_range": "€90,000–€115,000", "confidence": "medium"}',
            "currency_char": "€",
            "premium":       "Berlin/Munich add ~10% premium",
        },
        "dk": {
            "label":         "Denmark",
            "currency":      "DKK",
            "example":       '{"salary_range": "DKK 650,000–DKK 800,000", "confidence": "medium"}',
            "currency_char": "DKK",
            "premium":       "Copenhagen adds ~10-15% premium",
        },
        "ie": {
            "label":         "Ireland",
            "currency":      "EUR",
            "example":       '{"salary_range": "€85,000–€105,000", "confidence": "medium"}',
            "currency_char": "€",
            "premium":       "Dublin adds ~10-15% premium; US tech EMEA HQs pay above local market",
        },
        "ae": {
            "label":         "United Arab Emirates",
            "currency":      "AED",
            "example":       '{"salary_range": "AED 350,000–AED 480,000", "confidence": "medium"}',
            "currency_char": "AED",
            "premium":       "Dubai adds ~15-20% premium; salaries are tax-free",
        },
    }
    cfg = _market_cfg.get(market, _market_cfg["uk"])

    prompt = (
        f"Role: {role}\nCompany: {company}\nLocation: {location}\n\n"
        f"Estimate the annual {cfg['currency']} salary range for this role in the "
        f"{cfg['label']} analytics market (2025-2026). "
        f"Base your estimate on role title, seniority, company type, and location "
        f"({cfg['premium']}). "
        f"Return ONLY valid JSON with no extra text: {cfg['example']}"
    )
    try:
        payload = json.dumps({
            "model":      "claude-haiku-4-5-20251001",
            "max_tokens": 80,
            "messages":   [{"role": "user", "content": prompt}],
            "system":     f"You are a {cfg['label']} salary benchmarking assistant. Return only valid JSON.",
        }).encode()
        req = _ureq.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"Content-Type": "application/json",
                     "anthropic-version": "2023-06-01",
                     **({"x-api-key": key} if key else {})},
            method="POST",
        )
        with _ureq.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read())["content"][0]["text"].strip()
        raw = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(raw)
        rng  = parsed.get("salary_range", "")
        conf = parsed.get("confidence", "low")
        if rng and cfg["currency_char"] in rng:
            score_result["salary_stated"]              = f"Not stated (est. {rng})"
            score_result["salary_estimate"]            = rng
            score_result["salary_estimate_confidence"] = conf
            score_result.setdefault("salary_gate", "tbc")
            print(f"    [salary_patch] Estimated: {rng} (conf={conf})")
        else:
            print(f"    [salary_patch] Unexpected format '{rng}' — keeping bare Not stated")
            score_result.setdefault("salary_gate", "tbc")
    except Exception as e:
        print(f"    [salary_patch] Failed ({e}) — keeping bare Not stated, gate=tbc")
        score_result.setdefault("salary_gate", "tbc")
    return score_result


def _canonical_rejection_reason(r: dict) -> str:
    """
    Return the single most-significant rejection reason in confirmed hierarchy order.
    Called after all _apply_hard_overrides() gates so all flags are already set.
    Hierarchy: Visa Denied > Salary Failed > Score/Fit (Pass 2 semantic)
    is_remote_only and is_contract are informational flags — they no longer cause rejection.
    Always includes numeric fit score when the root cause is score-based.
    """
    market = r.get("market", "uk")
    if r.get("visa_sponsorship_status") == "Rejected":
        return "Visa sponsorship explicitly denied in job description"
    if (r.get("salary_gate") == "failed"
            and r.get("salary_stated") not in ("", "Not stated", "Not provided", None)):
        _thresholds = {"uk": "£80k", "nl": "€90k", "se": "SEK 800k", "de": "€90k"}
        thr = _thresholds.get(market, "£80k")
        return f"Salary below {thr} threshold (stated: {r.get('salary_stated', '')})"
    # Score-based: always surface both the number and Claude's semantic reason.
    claude_reason = r.get("rejection_reason") or "Domain/fit mismatch"
    return f"Fit score {r.get('fit_score', 0)}/100 — {claude_reason}"


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCORING LOOP
# ─────────────────────────────────────────────────────────────────────────────

env = load_env()
api_key = env.get("ANTHROPIC_API_KEY", "")
if not api_key and not DRY_RUN:
    print("ERROR: ANTHROPIC_API_KEY not found in .env")
    sys.exit(1)

# ── Retroactive stale sweep (runs before scoring new jobs) ───────────────────
_stale_swept = recategorize_stale_entries()
if _stale_swept:
    print(f"[score_jobs] Retroactive stale sweep: {_stale_swept} entries updated to Stale\n")

# Counters
pass1_rejected   = []
pass1_stale_jobs = []
pass2_scored     = []
skipped_dupes    = []
apify_upgrades   = []   # Apify-over-Adzuna data patches emitted to scored_jobs.json

# Per-job scoring checkpoint — written after each scored job so a mid-loop kill
# doesn't lose work. Loaded into _EXISTING_POOL so re-run dedup skips these jobs.
CHECKPOINT_PATH = ROOT / "data" / "pipeline" / "scoring_checkpoint.json"
_checkpoint: list = []
try:
    if CHECKPOINT_PATH.exists():
        for _ce in json.loads(CHECKPOINT_PATH.read_text()):
            if _ce.get("date") == TODAY:
                _checkpoint.append(_ce)
except Exception:
    pass

def _write_checkpoint(jd_url: str, job_id: str, company: str, title: str,
                      market: str = "uk") -> None:
    _checkpoint.append({"jd_url": jd_url, "job_id": job_id or "",
                        "company": company, "role": title, "date": TODAY,
                        "market": market or "uk"})
    try:
        CHECKPOINT_PATH.write_text(json.dumps(_checkpoint, indent=2))
    except Exception:
        pass


def _cache_jd_description(job_id: str, company: str, role: str, job: dict) -> None:
    """Persist JD description to jd_text_cache.json so fetch_jd.py finds it locally next time."""
    if not job_id:
        return
    description = (job.get("description") or "").strip()
    if not description:
        return
    try:
        cache: dict = {}
        if JD_TEXT_CACHE_PATH.exists():
            try:
                cache = json.loads(JD_TEXT_CACHE_PATH.read_text())
            except Exception:
                pass
        if str(job_id) not in cache:  # don't overwrite existing entries
            cache[str(job_id)] = {
                "description": description,
                "company":     company,
                "role":        role,
                "source":      "score_jobs",
                "cached_at":   TODAY,
            }
            JD_TEXT_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    except Exception as e:
        print(f"  [warn] JD cache write failed for {job_id}: {e}")

p1_rejects   = 0
p1_stale     = 0
p1_passes    = 0
p2_shortlist = 0
p2_review    = 0
p2_reject    = 0
p2_error     = 0

# O5: pre-load today's checkpoint so we skip jobs already queued/scored in this run
_scored_today_ids: set = set()  # (job_id, market) tuples
if CHECKPOINT_PATH.exists():
    try:
        for _ce in json.loads(CHECKPOINT_PATH.read_text()):
            if _ce.get("date") == TODAY and _ce.get("job_id"):
                _scored_today_ids.add((_ce["job_id"], (_ce.get("market") or "uk").lower()))
    except Exception:
        pass
if _scored_today_ids:
    print(f"[score_jobs] O5: {len(_scored_today_ids)} jobs already scored today — will skip in main loop")

seen_urls_this_run    = set()
seen_co_role_this_run = set()
seen_job_ids_this_run = set()
# Batch queue: populated in BATCH_MODE, processed after main loop
_p2_batch_queue: list = []  # each: (job, system_prompt, user_prompt, match_decision, matched_id, company, title)

for i, job in enumerate(enriched):
    title       = job.get("job_title") or "Unknown"
    company     = job.get("company_name") or "Unknown"
    jd_url      = (job.get("job_url") or job.get("url") or "").strip()
    _job_market = (job.get("market") or "uk").lower()

    # ── Intra-batch dedup ─────────────────────────────────────────────────────
    co_role_key    = f"{_normalize_company(company.lower())}::{title.lower()}::{_job_market}"
    batch_job_id   = str(job.get("job_id") or "").strip() or _extract_job_id_from_url(jd_url)
    batch_id_key   = (batch_job_id, _job_market) if batch_job_id else None

    # O5: skip jobs already fully scored in a prior run today
    if batch_id_key and batch_id_key in _scored_today_ids:
        print(f"  — SKIP (already scored today) {company} / {title}")
        continue

    if batch_id_key and batch_id_key in seen_job_ids_this_run:
        print(f"  — SKIP (intra-batch dupe, job_id) {company} / {title}")
        skipped_dupes.append((job, {"id": "intra-batch", "status": "duplicate"}))
        continue
    if jd_url and jd_url in seen_urls_this_run:
        print(f"  — SKIP (intra-batch dupe) {company} / {title}")
        skipped_dupes.append((job, {"id": "intra-batch", "status": "duplicate"}))
        continue
    if co_role_key in seen_co_role_this_run:
        print(f"  — SKIP (intra-batch dupe) {company} / {title}")
        skipped_dupes.append((job, {"id": "intra-batch", "status": "duplicate"}))
        continue

    # ── Cross-run match check ─────────────────────────────────────────────────
    match_result   = _find_match(job)
    match_decision = match_result["decision"]
    matched_entry  = match_result["matched_entry"]
    matched_id     = match_result["matched_id"]

    # Attach match metadata to job dict — carried through to write_tracker.py
    job["_match_decision"] = match_decision
    job["_matched_id"]     = matched_id if match_decision in ("new_entry", "update_in_place") else None
    job["_match_exists"]   = matched_entry is not None
    job["_score_reused"]   = False

    # Apify-over-Adzuna upgrade: when Apify finds a job that matches an existing
    # Shortlisted/Review Needed entry, queue a data patch so write_tracker.py
    # can upgrade that entry's fields (jd_url → LinkedIn URL, career_page_url
    # from applyUrl, salary, etc.). Applies to both dedup and update_in_place.
    _queued_upgrade = False
    if (job.get("_source") == "apify"
            and matched_entry
            and matched_entry.get("status") in ("Shortlisted", "Review Needed")):
        apify_upgrades.append({
            "_matched_id":          matched_entry["id"],
            "_company":             company,
            "_role":                title,
            "jd_url":               jd_url,
            "salary_stated":        job.get("salary_stated") or "",
            "work_mode":            job.get("work_mode") or "",
            "experience_req":       (job.get("experience_years") or {}).get("display") or "",
            "ats_type":             job.get("ats_type") or "",
            "career_page_url_hint": job.get("career_page_url") or "",
        })
        _queued_upgrade = True

    if match_decision == "dedup":
        upgrade_note = " → Apify upgrade queued" if _queued_upgrade else ""
        print(f"  — SKIP (dedup/{matched_id}) {company} / {title}{upgrade_note}")
        skipped_dupes.append((job, matched_entry or {"id": "?", "status": "dedup"}))
        if jd_url: seen_urls_this_run.add(jd_url)
        seen_co_role_this_run.add(co_role_key)
        if batch_id_key: seen_job_ids_this_run.add(batch_id_key)
        _EXISTING_POOL.append({
            "id": f"intra:{i}", "company": company.lower().strip(),
            "role": title.lower().strip(), "jd_url": jd_url, "job_id": batch_job_id,
            "status": "intra-batch", "posted_date": (job.get("posted_date") or "")[:10],
            "fit_score": None, "score_exists": False,
            "latest_scoring_date": TODAY, "market": (job.get("market") or "uk").lower(),
        })
        continue

    if jd_url: seen_urls_this_run.add(jd_url)
    seen_co_role_this_run.add(co_role_key)
    if batch_id_key: seen_job_ids_this_run.add(batch_id_key)
    _EXISTING_POOL.append({
        "id": f"intra:{i}", "company": company.lower().strip(),
        "role": title.lower().strip(), "jd_url": jd_url, "job_id": batch_job_id,
        "status": "intra-batch", "posted_date": (job.get("posted_date") or "")[:10],
        "fit_score": None, "score_exists": False,
        "latest_scoring_date": TODAY, "market": (job.get("market") or "uk").lower(),
    })

    # ── Pass 1 ────────────────────────────────────────────────────────────────
    if not NO_PREFILTER:
        p1_result, reason = pass1_filter(job)
        if p1_result == "reject":
            p1_rejects += 1
            print(f"  ✗ P1-REJECT  {company} / {title} — {reason}")
            pass1_rejected.append((job, reason))
            continue
        elif p1_result == "stale":
            p1_stale += 1
            print(f"  ~ P1-STALE   {company} / {title} — {reason}")
            pass1_stale_jobs.append(job)
            continue

    p1_passes += 1

    # ── Re-scoring eligibility ────────────────────────────────────────────────
    if matched_entry and matched_entry.get("score_exists"):
        fit_sc = matched_entry.get("fit_score")
        print(f"  ↩ SCORE REUSED [{fit_sc}] {company} / {title}")
        full_entry = next((e for e in tracker if e.get("id") == matched_id), None)
        if full_entry:
            reused_result = _reconstruct_result_from_entry(full_entry)
            job["_score_reused"] = True
            pass2_scored.append((job, reused_result))
            continue
    # Removed: time-gated re-scoring (REPOST_GAP_DAYS = 21d threshold).
    # Old scores are always reused — no expiry.
    # if matched_entry and matched_entry.get("score_exists"):
    #     last_scored = matched_entry.get("latest_scoring_date")
    #     if last_scored:
    #         try:
    #             days_since = (date.fromisoformat(TODAY) - date.fromisoformat(last_scored)).days
    #             if days_since <= REPOST_GAP_DAYS:
    #                 fit_sc = matched_entry.get("fit_score")
    #                 print(f"  ↩ SCORE REUSED [{fit_sc}] {company} / {title} "
    #                       f"(scored {days_since}d ago, ≤{REPOST_GAP_DAYS}d threshold)")
    #                 full_entry = next((e for e in tracker if e.get("id") == matched_id), None)
    #                 if full_entry:
    #                     reused_result = _reconstruct_result_from_entry(full_entry)
    #                     job["_score_reused"] = True
    #                     pass2_scored.append((job, reused_result))
    #                     continue
    #         except ValueError:
    #             pass

    # ── Pass 2 — Claude API ───────────────────────────────────────────────────
    if DRY_RUN:
        print(f"  [dry-run] Would score: {company} / {title}")
        continue

    user_prompt   = _build_user_prompt(job)
    system_prompt = _build_system_prompt(job.get("market", "uk"))
    _cache_jd_description(batch_job_id, company, title, job)

    if BATCH_MODE:
        _p2_batch_queue.append((job, system_prompt, user_prompt, match_decision, matched_id, company, title))
        print(f"  [batch] Queued: {company} / {title}")
        continue

    try:
        raw = call_claude_api(system_prompt, user_prompt, MODEL, api_key)
        result = parse_score_response(raw)
        if not result:
            print(f"  ⚠ PARSE ERROR {company} / {title} — raw: {raw[:120]}")
            p2_error += 1
            continue

        # ── Post-score hard overrides ─────────────────────────────────────────
        # Critical gates enforced in code regardless of what Claude returned.
        result = _apply_hard_overrides(result, job)
        # Sync apply_recommendation to final action after all overrides (covers upgrades + downgrades).
        # reject→Skip | shortlist→Apply | review→Maybe. Ensures the field always matches action.
        _final_action = result.get("action")
        if _final_action == "reject":
            result["apply_recommendation"] = "Skip"
        elif _final_action == "shortlist":
            result["apply_recommendation"] = "Apply"
        elif _final_action == "review":
            result["apply_recommendation"] = "Maybe"
        # Salary patch: if Claude skipped the estimation instruction, fill it now.
        if not DRY_RUN:
            result = _patch_missing_salary_estimate(result, job, api_key)
        # Rewrite rejection_reason to the highest-hierarchy cause.
        # Runs after ALL override gates so every flag is already set.
        # Ensures the displayed reason always reflects the most significant signal,
        # not whichever gate happened to write rejection_reason first.
        if result.get("action") == "reject":
            result["rejection_reason"] = _canonical_rejection_reason(result)

        action = result.get("action", "reject")
        score  = result.get("fit_score", 0)
        visa   = result.get("visa_sponsorship_status", "Unconfirmed")
        sal_g  = result.get("salary_gate", "tbc")

        if action == "shortlist":
            p2_shortlist += 1
            tag = "✓ SHORTLIST"
        elif action == "review":
            p2_review += 1
            tag = "⚠ REVIEW   "
        else:
            p2_reject += 1
            tag = "✗ P2-REJECT"

        reason_str = f" — {result.get('rejection_reason')}" if result.get("rejection_reason") else ""
        agency_str = f" [via {company}→{result.get('actual_hiring_company')}]" if result.get("is_agency_post") and result.get("actual_hiring_company") else ""
        print(f"  {tag} [{score}] {company} / {title}{agency_str}{reason_str}")
        if result.get("flags"):
            print(f"            flags: {', '.join(result['flags'])}")

        pass2_scored.append((job, result))
        _write_checkpoint(jd_url, batch_job_id, company, title, _job_market)
        time.sleep(0.3)

    except _uerr.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  ⚠ API ERROR  {company} / {title} — HTTP {e.code}: {body}")
        p2_error += 1
        _write_checkpoint(jd_url, batch_job_id, company, title, _job_market)
    except Exception as e:
        print(f"  ⚠ ERROR      {company} / {title} — {e}")
        p2_error += 1
        _write_checkpoint(jd_url, batch_job_id, company, title, _job_market)


# ── Batch processing pass (BATCH_MODE only) ───────────────────────────────────
if BATCH_MODE and _p2_batch_queue and not DRY_RUN:
    print(f"\n[score_jobs] Processing {len(_p2_batch_queue)} queued jobs via Batch API ...")

    # Group by market so each batch has a single uniform system prompt —
    # maximises prompt cache hits (all requests in a batch share the same prefix).
    _market_groups: dict = defaultdict(list)
    for _qi, _qitem in enumerate(_p2_batch_queue):
        _qmkt = (_qitem[0].get("market") or "uk").lower()
        _market_groups[_qmkt].append((_qi, _qitem))

    # ── O1: Phase 1 — submit/resume all market batches (sequential, fast HTTP POSTs) ──
    _pending_batches: dict = {}  # market → (batch_id, state_path)
    for _mkt, _mitems in sorted(_market_groups.items()):
        _mkt_requests = [
            {"custom_id": f"job_{_qi:04d}",
             "params": {
                 "model":      MODEL,
                 "max_tokens": 1500,
                 "system":     [{"type": "text", "text": _msys,
                                 "cache_control": {"type": "ephemeral"}}],
                 "messages":   [{"role": "user", "content": _musr}],
             }}
            for _qi, (_mjob, _msys, _musr, *_) in _mitems
        ]
        _mkt_state = _BATCH_STATE_PATH.parent / f"batch_state_{_mkt}.json"
        _bid = _get_or_submit_batch_id(_mkt_requests, api_key, state_path=_mkt_state)
        _pending_batches[_mkt] = (_bid, _mkt_state)

    # ── O1: Phase 2 — poll all markets in parallel ──────────────────────────────
    from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed

    def _poll_market(args):
        mkt, bid, state_path = args
        print(f"[score_jobs] [{mkt.upper()}] Polling batch {bid}...")
        results = _poll_batch(bid, api_key)
        state_path.write_text(json.dumps({"date": TODAY, "batch_id": bid, "status": "done"}))
        print(f"[score_jobs] [{mkt.upper()}] Batch done — {len(results)} results")
        return results

    batch_results: dict = {}
    _n = len(_pending_batches)
    print(f"\n[score_jobs] Polling {_n} market batch(es) in parallel...")
    with ThreadPoolExecutor(max_workers=_n) as _pool:
        _futs = {_pool.submit(_poll_market, (mkt, bid, sp)): mkt
                 for mkt, (bid, sp) in _pending_batches.items()}
        for _f in _as_completed(_futs):
            _mkt = _futs[_f]
            try:
                batch_results.update(_f.result())
            except Exception as _pe:
                print(f"[score_jobs] ERROR polling {_mkt.upper()} batch: {_pe}")

    for i, (job, system_prompt, user_prompt, match_decision, matched_id, company, title) \
            in enumerate(_p2_batch_queue):
        cid = f"job_{i:04d}"
        result_msg = batch_results.get(cid)
        _batch_jd_url = (job.get("job_url") or job.get("url") or "").strip()
        _batch_job_id = str(job.get("job_id") or "").strip() or _extract_job_id_from_url(_batch_jd_url)
        _batch_market = (job.get("market") or "uk").lower()
        if result_msg is None:
            print(f"  ⚠ BATCH MISS {company} / {title} — no result (API error; will retry on re-run)")
            p2_error += 1
            # Do NOT checkpoint batch misses — the job must be re-queued on re-run.
            # Checkpointing here would cause O5 to skip it permanently for today.
            continue

        _accumulate_batch_usage(result_msg)
        raw_text = result_msg["content"][0]["text"]
        result = parse_score_response(raw_text)
        if not result:
            print(f"  ⚠ PARSE ERROR {company} / {title} — raw: {raw_text[:120]}")
            p2_error += 1
            # Do NOT checkpoint parse errors — re-run should retry the API call.
            continue

        result = _apply_hard_overrides(result, job)
        # Sync apply_recommendation to final action after all overrides (covers upgrades + downgrades).
        _final_action = result.get("action")
        if _final_action == "reject":
            result["apply_recommendation"] = "Skip"
        elif _final_action == "shortlist":
            result["apply_recommendation"] = "Apply"
        elif _final_action == "review":
            result["apply_recommendation"] = "Maybe"
        result = _patch_missing_salary_estimate(result, job, api_key)
        if result.get("action") == "reject":
            result["rejection_reason"] = _canonical_rejection_reason(result)

        action = result.get("action", "reject")
        score  = result.get("fit_score", 0)
        if action == "shortlist":
            p2_shortlist += 1
            tag = "✓ SHORTLIST"
        elif action == "review":
            p2_review += 1
            tag = "⚠ REVIEW   "
        else:
            p2_reject += 1
            tag = "✗ P2-REJECT"

        reason_str = f" — {result.get('rejection_reason')}" if result.get("rejection_reason") else ""
        agency_str = (f" [via {company}→{result.get('actual_hiring_company')}]"
                      if result.get("is_agency_post") and result.get("actual_hiring_company") else "")
        print(f"  {tag} [{score}] {company} / {title}{agency_str}{reason_str}")
        if result.get("flags"):
            print(f"            flags: {', '.join(result['flags'])}")
        pass2_scored.append((job, result))
        _write_checkpoint(_batch_jd_url, _batch_job_id, company, title, _batch_market)


# ─────────────────────────────────────────────────────────────────────────────
# WRITE OUTPUTS
# ─────────────────────────────────────────────────────────────────────────────

def _build_rejection_entry(job: dict, reason: str, score_result: Optional[dict], source: str) -> dict:
    has_score = score_result is not None and score_result.get("fit_score") is not None
    return {
        "id":                   f"rej_{len(auto_rejected) + 1:04d}",
        "job_id":               job.get("jobId") or job.get("job_id") or "",
        "company":              job.get("company_name") or "",
        "role":                 job.get("job_title") or "",
        "location":             job.get("location") or "",
        "jd_url":               job.get("job_url") or job.get("url") or "",
        "posted_date":          job.get("posted_date") or job.get("postedDate") or "",
        "fit_score":            score_result.get("fit_score") if score_result else None,
        "rejection_reason":     reason,
        "salary_stated":        score_result.get("salary_stated") if score_result else (job.get("salary") or ""),
        "visa_hint":            "n/a",
        "scout_run_date":       TODAY,
        "source":               source,
        "scraper_source":       job.get("_source", "apify"),
        "score_exists":         has_score,
        "latest_scoring_date":  TODAY if has_score else None,
        "role_focus":           score_result.get("role_focus", "") if score_result else "",
        "market":               job.get("market", "uk"),
        "role_type":            (_compute_role_type(
                                    bool(score_result.get("is_contract")) if score_result else bool(job.get("is_contract")),
                                    bool(score_result.get("is_remote_only")) if score_result else (job.get("work_mode") == "Remote")
                                )),
        "eor_viability":        score_result.get("eor_viability") if score_result else None,
    }


shortlisted_for_tracker = []
newly_rejected_entries  = []

for job, result in pass2_scored:
    action = result.get("action", "reject")

    # Heuristic fallback: augment is_agency_post for known agencies Claude may have missed.
    # Uses word-boundary match to avoid false positives (e.g. "saltus" != "salt").
    if not result.get("is_agency_post"):
        co_lower = (job.get("company_name") or "").lower().strip()
        if any(re.search(r'\b' + re.escape(ag) + r'\b', co_lower) for ag in KNOWN_AGENCIES):
            result["is_agency_post"] = True
            if not result.get("actual_hiring_company"):
                hint = _extract_hiring_company_hint(job)
                if hint:
                    result["actual_hiring_company"] = hint

    if action in ("shortlist", "review"):
        # Post-scoring dedup: if pre-scoring dedup returned no_match (because company_name
        # was an agency/board name not in KNOWN_AGENCIES), retry using actual_hiring_company
        # that Claude identified from the JD body.
        if (job.get("_match_decision") == "no_match"
                and result.get("is_agency_post")
                and result.get("actual_hiring_company")):
            _res_co    = result["actual_hiring_company"].lower().strip()
            _res_norm  = _normalize_company(_res_co)
            _title_lo  = (job.get("job_title") or "").lower().strip()
            _mkt       = (job.get("market") or "uk").lower()
            _post_cands = [
                e for e in _EXISTING_POOL
                if _field_matches(_res_norm, _normalize_company(e["company"]))
                and _role_matches(_title_lo, e["role"])
                and (not _mkt or not e.get("market") or _mkt == e.get("market", "uk"))
            ]
            if _post_cands:
                _best    = max(_post_cands, key=lambda e: e["posted_date"])
                _np      = (job.get("posted_date") or job.get("postedDate") or "")[:10]
                _gap: Optional[int] = None
                if _np and _best["posted_date"]:
                    try:
                        _gap = (date.fromisoformat(_np) - date.fromisoformat(_best["posted_date"])).days
                    except ValueError:
                        pass
                _ex_st = _best.get("status", "")
                if _gap is not None and _gap > REPOST_GAP_DAYS and _ex_st in TERMINAL_STATUSES:
                    _pdec = "new_entry"
                elif _gap is None and _ex_st in TERMINAL_STATUSES:
                    _pdec = "new_entry"
                else:
                    _pdec = "dedup"
                print(f"    [post-score dedup] {_res_co}+role, gap={_gap}d → {_pdec} "
                      f"({_best['id']}/{_ex_st})")
                if _pdec == "dedup":
                    skipped_dupes.append((job, _best))
                    continue
                job["_match_decision"] = _pdec
                job["_matched_id"]     = _best["id"]
                job["_match_exists"]   = True

        # Resolve ATS type: prefer Claude's semantic identification over heuristic URL match
        ats_from_claude = result.get("ats_type_from_jd") or "unknown"
        ats_final = ats_from_claude if ats_from_claude != "unknown" else (job.get("ats_type") or "unknown")

        # Resolve company: use actual_hiring_company if agency post
        display_company = (
            result.get("actual_hiring_company") or job.get("company_name") or ""
        ) if result.get("is_agency_post") else (job.get("company_name") or "")

        entry = {
            "job":    job,
            "score":  result,
            "status": "Shortlisted" if action == "shortlist" else "Review Needed",
            # Resolved fields for tracker writer convenience
            "_resolved_company":   display_company,
            "_resolved_ats_type":  ats_final,
            # Match metadata (for write_tracker.py routing)
            "_match_decision":     job.get("_match_decision", "no_match"),
            "_matched_id":         job.get("_matched_id"),
            "_match_exists":       job.get("_match_exists", False),
            "_score_reused":       job.get("_score_reused", False),
        }
        shortlisted_for_tracker.append(entry)
    else:
        reason = result.get("rejection_reason") or f"fit_score={result.get('fit_score',0)}"
        newly_rejected_entries.append(
            _build_rejection_entry(job, reason, result, "pass2")
        )

for job, reason in pass1_rejected:
    newly_rejected_entries.append(
        _build_rejection_entry(job, reason, None, "pass1")
    )

# Stale jobs: tracked in scored_jobs.json with status=Stale, no Claude score.
# They appear in the Google Sheet (grey row) so the user can see them but they
# don't clutter Shortlisted. A fresh repost of the same role bypasses dedup and
# gets scored normally.
for job in pass1_stale_jobs:
    shortlisted_for_tracker.append({
        "job":               job,
        "score":             None,
        "status":            "Stale",
        "_resolved_company":  job.get("company_name", ""),
        "_resolved_ats_type": job.get("ats_type") or "unknown",
        "_match_decision":    job.get("_match_decision", "no_match"),
        "_matched_id":        job.get("_matched_id"),
        "_match_exists":      job.get("_match_exists", False),
        "_score_reused":      False,
    })

if not DRY_RUN:
    scored_output = {
        "jobs":           shortlisted_for_tracker,
        "apify_upgrades": apify_upgrades,
        "_run_stats": {
            "input_jobs":   len(enriched),
            "duplicates":   len(skipped_dupes),
            "p1_rejected":  p1_rejects,
            "p1_stale":     p1_stale,
            "p1_passed":    p1_passes,
            "p2_shortlist": p2_shortlist,
            "p2_review":    p2_review,
            "p2_reject":    p2_reject,
            "p2_error":     p2_error,
            "run_date":     TODAY,
        },
    }
    SCORED_PATH.write_text(json.dumps(scored_output, indent=2, ensure_ascii=False))
    print(f"\n[score_jobs] Wrote {len(shortlisted_for_tracker)} jobs + "
          f"{len(apify_upgrades)} Apify upgrades → {SCORED_PATH.name}")

    existing_urls = {e.get("jd_url") for e in auto_rejected if e.get("jd_url")}
    fresh = [e for e in newly_rejected_entries if e.get("jd_url") not in existing_urls]
    auto_rejected.extend(fresh)
    for idx, entry in enumerate(auto_rejected, 1):
        entry["id"] = f"rej_{idx:04d}"
    AUTO_REJ_PATH.write_text(json.dumps({"auto_rejected": auto_rejected}, indent=2, ensure_ascii=False))
    print(f"[score_jobs] Appended {len(fresh)} new rejects → {AUTO_REJ_PATH.name}")

    # Prune checkpoint to today's entries only — prevents unbounded file growth.
    today_cp = [e for e in _checkpoint if e.get("date") == TODAY]
    CHECKPOINT_PATH.write_text(json.dumps(today_cp, indent=2))

# ── Summary ───────────────────────────────────────────────────────────────────
# Haiku 4.5: real-time $1.00/$5.00 per 1M in/out; batch $0.50/$2.50; cache read $0.10/$0.05
_IN_RATE  = 0.50 if BATCH_MODE else 1.00
_OUT_RATE = 2.50 if BATCH_MODE else 5.00
_CR_RATE  = 0.05 if BATCH_MODE else 0.10   # cache read
_CW_RATE  = 0.625 if BATCH_MODE else 1.25  # cache write

haiku_cost_usd = (
    _api_usage["input_tokens"]         * _IN_RATE
    + _api_usage["output_tokens"]      * _OUT_RATE
    + _api_usage["cache_read_tokens"]  * _CR_RATE
    + _api_usage["cache_write_tokens"] * _CW_RATE
) / 1_000_000

_mode_tag = "batch" if BATCH_MODE else "real-time"
print(f"""
[score_jobs] ══════════════════════════════════════════
  Input jobs:      {len(enriched)}
  Duplicates:      {len(skipped_dupes)} skipped
  Pass 1 rejected: {p1_rejects}  (native field gates — hard cutoff)
  Pass 1 stale:    {p1_stale}  (>{STALE_AGE_DAYS}d old → tracked as Stale)
  Pass 1 passed:   {p1_passes} → sent to Claude API ({_mode_tag})
  ─────────────────────────────────────────
  Shortlisted:     {p2_shortlist}
  For review:      {p2_review}
  API rejected:    {p2_reject}
  API errors:      {p2_error}
  ─────────────────────────────────────────
  API tokens:      {_api_usage["input_tokens"]:,} in / {_api_usage["output_tokens"]:,} out  ({_api_usage["calls"]} calls)
  Cache tokens:    {_api_usage["cache_read_tokens"]:,} read / {_api_usage["cache_write_tokens"]:,} write
  Actual cost:     ${haiku_cost_usd:.4f}
[score_jobs] ══════════════════════════════════════════

Next step: python3 scripts/write_tracker.py && python3 scripts/sheets_sync.py pull --tabs apps,archive && python3 scripts/sheets_sync.py push --tabs apps,archive
""")

# Write actual token counts to monitoring (only meaningful for real runs with API calls)
if not DRY_RUN and _api_usage["calls"] > 0:
    try:
        monitor_dir = ROOT / "data" / "monitoring"
        monitor_dir.mkdir(parents=True, exist_ok=True)
        scoring_path = monitor_dir / "scoring_run.json"
        records = json.loads(scoring_path.read_text()) if scoring_path.exists() else []
        records.append({
            "date":                TODAY,
            "timestamp":           datetime.now().isoformat(timespec="seconds"),
            "batch_mode":          BATCH_MODE,
            "jobs_p2":             _api_usage["calls"],
            "input_tokens":        _api_usage["input_tokens"],
            "output_tokens":       _api_usage["output_tokens"],
            "cache_read_tokens":   _api_usage["cache_read_tokens"],
            "cache_write_tokens":  _api_usage["cache_write_tokens"],
            "cost_usd":            round(haiku_cost_usd, 6),
            "model":               MODEL,
        })
        scoring_path.write_text(json.dumps(records, indent=2))
        print(f"[score_jobs] Monitoring → {scoring_path.name} (actual tokens logged)")
    except Exception as e:
        print(f"[score_jobs] Warning: could not write monitoring data: {e}")
