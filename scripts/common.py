#!/usr/bin/env python3
"""
common.py — Shared utilities for the job-automation pipeline.
==============================================================
Single source of truth for helpers that were previously copy-pasted across
score_jobs.py, write_tracker.py, eval_base.py, gmail_backfill.py,
inject_manual.py and inject_manual_jobs.py.

Import style (scripts all live in scripts/, which Python puts on sys.path
when a script is run directly):

    from common import load_env, extract_job_id_from_url

No side effects at import time — safe to import from anywhere.
"""

from __future__ import annotations  # PEP 604 unions on Python 3.9

import re
from pathlib import Path
from typing import Optional

ROOT     = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG — single-sourced pipeline thresholds
# ─────────────────────────────────────────────────────────────────────────────

# Minimum acceptable salary per market (annual, local currency).
# UK £80k / NL €90k / SE SEK 800k / DE €90k / DK DKK 700k / IE €90k / AE AED 360k —
# CLAUDE.md §3 is the policy source; this constant is the single enforcement point for code.
# DK/IE added 2026-07-24: DKK 700k ≈ €94k (aligns with NL/DE €90k, clears Pay Limit
# Scheme visa threshold ~DKK 514k); IE €90k matches NL/DE.
# AE added 2026-08-01: AED 360k ≈ £77k/€90k equivalent; tax-free so effective net
# purchasing power exceeds UK/EU thresholds at this level.
SALARY_THRESHOLDS = {"uk": 80_000, "nl": 90_000, "se": 800_000, "de": 90_000,
                     "dk": 700_000, "ie": 90_000, "ae": 360_000}

# 80% of each market threshold — applied when is_remote_only or is_contract is true.
# Remote/contract roles are geographically flexible and worth scoring at a reduced gate.
SALARY_THRESHOLDS_REMOTE = {k: int(v * 0.8) for k, v in SALARY_THRESHOLDS.items()}

DAY_RATE_ANNUAL_FACTOR = 220   # working days/year (used to annualise day-rate contracts)

ROLE_TYPE_ENUM = ("contract_remote", "contract_hybrid", "permanent_remote", "permanent_hybrid")


def compute_role_type(is_contract: bool, is_remote_only: bool) -> str:
    """Derive the 4-value role_type from two booleans (deterministic — no LLM)."""
    if is_contract and is_remote_only:
        return "contract_remote"
    if is_contract:
        return "contract_hybrid"
    if is_remote_only:
        return "permanent_remote"
    return "permanent_hybrid"


def annualise_day_rate(salary_str: str) -> "float | None":
    """Extract and annualise a day-rate salary string. Returns None if not a day rate."""
    m = re.search(r'([\d,]+)\s*/\s*day|per\s+day[^-\d]*([\d,]+)', salary_str, re.I)
    if not m:
        return None
    raw = (m.group(1) or m.group(2) or "").replace(",", "")
    return float(raw) * DAY_RATE_ANNUAL_FACTOR if raw else None


# ─────────────────────────────────────────────────────────────────────────────
# ENV LOADER
# ─────────────────────────────────────────────────────────────────────────────

def load_env(env_file: Path = ENV_FILE) -> dict:
    """Parse KEY=VALUE lines from .env (comments and blank lines ignored)."""
    env = {}
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# ─────────────────────────────────────────────────────────────────────────────
# JOB ID EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

_JOB_ID_RE = re.compile(r'[/-](\d{9,13})(?:[?/]|$)')


def extract_job_id_from_url(url: str) -> Optional[str]:
    """Extract the numeric LinkedIn job ID from a job URL path (9–13 digits).

    Handles both slugged (/jobs/view/role-at-co-4444555566) and bare
    (/jobs/view/4444555566) URL forms. Tracking params are ignored because the
    ID must be terminated by ?, / or end-of-string.
    """
    m = _JOB_ID_RE.search(url or "")
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# FUZZY MATCHING
# ─────────────────────────────────────────────────────────────────────────────

def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance, case-insensitive. Returns 99 if length diff > 3
    (early exit — a distance that large always fails the ≤2/≤3 match thresholds
    used across the pipeline)."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 3:
        return 99
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(dp[j], dp[j - 1], prev)
            prev = temp
    return dp[n]


_CORP_SUFFIXES = re.compile(
    r'\s*\b(plc|ltd|limited|inc|corp|corporation|group|holdings|llc|gmbh|bv|ab|sa|nv)\b\.?\s*$',
    re.IGNORECASE,
)


def normalize_company(name: str) -> str:
    """Strip trailing corporate suffixes before fuzzy company name matching.
    'Kingfisher plc' → 'Kingfisher', 'Marks & Spencer Group' → 'Marks & Spencer'.
    """
    if not name:
        return name
    return _CORP_SUFFIXES.sub('', name).strip()


# ─────────────────────────────────────────────────────────────────────────────
# BRITISH ENGLISH ENFORCEMENT
# Single source of truth — imported by auto_prep.py and generate_summaries.py.
# ─────────────────────────────────────────────────────────────────────────────

_BE_MAP = [
    (r'\boptimizations\b', 'optimisations'),
    (r'\boptimization\b',  'optimisation'),
    (r'\boptimize\b',      'optimise'),
    (r'\boptimized\b',     'optimised'),
    (r'\boptimizing\b',    'optimising'),
    (r'\bmodeling\b',      'modelling'),
    (r'\bbehaviors\b',     'behaviours'),
    (r'\bbehavior\b',      'behaviour'),
    (r'\bbehavioral\b',    'behavioural'),
    (r'\bprioritizations\b', 'prioritisations'),
    (r'\bprioritization\b', 'prioritisation'),
    (r'\bprioritize\b',    'prioritise'),
    (r'\bprioritized\b',   'prioritised'),
    (r'\bprioritizing\b',  'prioritising'),
    (r'\banalyze\b',       'analyse'),
    (r'\banalyzed\b',      'analysed'),
    (r'\banalyzing\b',     'analysing'),
    (r'\borganize\b',      'organise'),
    (r'\borganized\b',     'organised'),
    (r'\borganizing\b',    'organising'),
    (r'\butilize\b',       'utilise'),
    (r'\butilized\b',      'utilised'),
    (r'\butilizing\b',     'utilising'),
    (r'\bvisualize\b',     'visualise'),
    (r'\bvisualized\b',    'visualised'),
    (r'\bvisualizing\b',   'visualising'),
    (r'\bstandardize\b',   'standardise'),
    (r'\bstandardized\b',  'standardised'),
    (r'\bstandardizing\b', 'standardising'),
    (r'\bcentralize\b',    'centralise'),
    (r'\bcentralized\b',   'centralised'),
    (r'\bcentralizing\b',  'centralising'),
    (r'\bcustomize\b',     'customise'),
    (r'\bcustomized\b',    'customised'),
    (r'\bcustomizing\b',   'customising'),
    (r'\brecognize\b',     'recognise'),
    (r'\brecognized\b',    'recognised'),
    (r'\brecognizing\b',   'recognising'),
    (r'\brealize\b',       'realise'),
    (r'\brealized\b',      'realised'),
    (r'\brealizing\b',     'realising'),
    (r'\bemphasize\b',     'emphasise'),
    (r'\bemphasized\b',    'emphasised'),
    (r'\bemphasizing\b',   'emphasising'),
    (r'\bsummarize\b',     'summarise'),
    (r'\bsummarized\b',    'summarised'),
    (r'\bsummarizing\b',   'summarising'),
    (r'\bcolors\b',        'colours'),
    (r'\bcolor\b',         'colour'),
    (r'\bmodeled\b',       'modelled'),
    (r'\bmodeler\b',       'modeller'),
    (r'\blabeled\b',       'labelled'),
    (r'\blabeling\b',      'labelling'),
]


def enforce_british_english(text: str) -> str:
    """Substitute American spellings with British equivalents (word-boundary safe).

    Preserves original casing: "Behavioral" → "Behavioural", "OPTIMIZE" → "OPTIMISE".
    """
    def _cased(replacement: str):
        def _sub(m: re.Match) -> str:
            orig = m.group(0)
            if orig.isupper():
                return replacement.upper()
            if orig[0].isupper():
                return replacement[0].upper() + replacement[1:]
            return replacement
        return _sub

    for pattern, replacement in _BE_MAP:
        text = re.sub(pattern, _cased(replacement), text, flags=re.IGNORECASE)
    return text
