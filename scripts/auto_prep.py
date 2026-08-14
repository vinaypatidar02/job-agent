#!/usr/bin/env python3
"""
auto_prep.py — Mechanical pre-fill for the job prep step.

Applies all deterministic rules from experience_bank.md and cover_letter_bank.md
before the LLM runs. The LLM then only needs to write:
  - summary (4 sentences, JD-specific)
  - Para 1 company hook (1-2 sentences naming company + role)
  - Para 4 (70 words, company mission + call to action)

Usage:
  python3 scripts/auto_prep.py --job_id <id> --jd_file <path/to/jd.txt>
  python3 scripts/auto_prep.py --job_id <id> --jd_file <path> --domain product
  python3 scripts/auto_prep.py --job_id <id> --jd_file <path> --company "Acme Ltd"

Outputs written to data/prep_tmp/:
  data/prep_tmp/auto_resume_<job_id>.json  — full resume JSON; summary = "FILL_ME"
  data/prep_tmp/auto_cover_<job_id>.json   — cover JSON; paragraphs[0] ends with hook placeholder,
                                             paragraphs[3] = "FILL_ME"
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

BASE_DIR = Path(__file__).parent.parent

sys.path.insert(0, str(Path(__file__).parent))
from common import compute_role_type as _compute_role_type
from common import enforce_british_english as _enforce_british_english


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE PROFILE — loaded from data/content/candidate_profile.json
# Edit that file (not this script) to update your personal info and profession config.
# ─────────────────────────────────────────────────────────────────────────────

def _load_profile() -> dict:
    profile_path = BASE_DIR / "data" / "content" / "candidate_profile.json"
    if not profile_path.exists():
        raise FileNotFoundError(
            f"candidate_profile.json not found at {profile_path}\n"
            "Fill in data/content/candidate_profile.json with your details before running."
        )
    return json.loads(profile_path.read_text(encoding="utf-8"))

_PROFILE = _load_profile()

# ─────────────────────────────────────────────────────────────────────────────
# STATIC PROFILE DATA — loaded from candidate_profile.json
# ─────────────────────────────────────────────────────────────────────────────

CONTACT        = _PROFILE["contact"]
_VISA_ADDRESS  = {k: v for k, v in _PROFILE.get("visa_addresses", {}).items()
                  if not k.startswith("_")}
_EOR_ADDRESS   = _PROFILE["contact"].get(
    "eor_address",
    f"{_PROFILE['contact'].get('address', 'Remote')} | Remote (EOR-ready: Deel / Remote.com)"
)
EDUCATION      = _PROFILE.get("education", [])
CERTIFICATIONS = _PROFILE.get("certifications", [])
ROLE_METADATA  = _PROFILE.get("experience", [])

# Markets where user already has right to work — skip visa framing for these
_RIGHT_TO_WORK_MARKETS = set(_PROFILE.get("has_right_to_work", {}).get("markets", []))


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
# USER CONFIGURATION — Domain Detection Keywords
# These keywords detect which work domain a JD belongs to.
# The defaults below are tuned for analytics/data roles.
# For other professions, replace with your field's domain vocabulary.
# EXAMPLES (software eng): "primary": ["microservices", "api design", "distributed"]
# EXAMPLES (finance):      "primary": ["financial planning", "budgeting", "fp&a"]
# Edit candidate_profile.json → domains to add/remove domains and keywords.
# ═══════════════════════════════════════════════════════════════════════════════

DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "product": [
        "product analytics", "growth analytics", "experimentation", "a/b test",
        "ecommerce", "conversion", "saas", "funnel", "activation", "marketplace",
        "user behaviour", "user behavior", "feature adoption", "product metrics",
        "retention", "engagement", "dau", "mau",
        "growth analyst", "growth manager", "growth team", "growth metrics",
        "growth optimisation", "growth optimization", "growth hacking",
    ],
    "crm": [
        "crm", "lifecycle", "propensity", "segmentation", "campaign analytics",
        "customer analytics", "churn", "reactivation", "loyalty", "customer growth",
        "customer journey", "lifecycle management", "lifecycle analytics", "lapsed",
        "customer retention",
    ],
    "pricing": [
        "pricing", "commercial analytics", "procurement", "margin analysis",
        "inventory optimisation", "p&l", "revenue analytics", "financial modelling",
        "commercial strategy", "revenue operations",
    ],
    "marketing": [
        "marketing mix model", "marketing mix modelling", "media mix model",
        "mmm", "attribution model", "attribution modelling", "multi-touch attribution",
        "mta", "marketing measurement", "media planning analytics",
        "channel attribution", "marketing analytics", "media analytics",
        "marketing spend", "media spend", "spend optimisation", "budget allocation",
        "paid media", "marketing roi", "marketing effectiveness",
    ],
    "bi": [
        "business intelligence", "bi ", "kpi framework", "kpi strategy",
        "self-serve analytics", "data visualisation", "data visualization",
        "semantic layer", "certified metrics", "data literacy", "dashboard",
        "reporting infrastructure", "data governance",
        "business analyst", "business analysis", "business requirements",
        "requirements gathering", "stakeholder management", "process mapping",
        "analytics transformation", "ai transformation", "agentic ai",
        "generative ai", "digital transformation", "ai business analyst",
    ],
}

LEADERSHIP_KEYWORDS: list[str] = [
    "people management", "manage a team", "managing a team", "line manage",
    "build a team", "head of analytics", "head of data", "mentoring analyst",
    "people manager", "team of analyst", "lead a team", "leadership of",
    "manage analyst", "direct reports", "line reports", "reporting to you",
    "lead, coach", "coach and develop", "leading a team", "building a team",
    "team of data scientist", "team of analyst", "grow a team",
]


INVESTMENT_KEYWORDS: list[str] = [
    "hedge fund", "asset management", "investment management", "asset manager",
    "quant finance", "quantitative finance", "fund manager",
    "wealth management", "private equity", "investment bank",
    "portfolio management", "fixed income", "equities",
    "trading strategy", "financial services firm", "fund administration",
]


def detect_domain(jd: str) -> str:
    jd_lower = jd.lower()
    scores: dict[str, int] = {d: 0 for d in DOMAIN_KEYWORDS}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for kw in keywords if kw in jd_lower)
    top = max(scores, key=scores.get)
    if scores[top] == 0:
        print("[auto_prep] ⚠ WARNING: No domain keywords matched in JD — "
              "defaulting to 'general'. Pass --domain to override.")
        return "general"
    return top


def is_leadership_jd(jd: str) -> bool:
    jd_lower = jd.lower()
    return any(kw in jd_lower for kw in LEADERSHIP_KEYWORDS)


def is_investment_jd_fallback(jd: str) -> bool:
    """Keyword fallback for investment domain — used when tracker flag is absent."""
    jd_lower = jd.lower()
    return any(kw in jd_lower for kw in INVESTMENT_KEYWORDS)


# ─────────────────────────────────────────────────────────────────────────────
# EXPERTISE SELECTION — loaded from candidate_profile.json → expertise
# Edit candidate_profile.json to change what appears in Core Expertise section.
# ─────────────────────────────────────────────────────────────────────────────

_EXPERTISE_CONFIG  = _PROFILE.get("expertise", {})
PINNED_EXPERTISE   = _EXPERTISE_CONFIG.get("pinned", [])
LEADERSHIP_EXPERTISE = _EXPERTISE_CONFIG.get("leadership", ["Team Leadership", "Strategic Decision-Making"])

def _build_domain_expertise() -> dict:
    primary   = _EXPERTISE_CONFIG.get("primary", [])
    secondary = _EXPERTISE_CONFIG.get("secondary", [])
    return {domain: {"primary": primary, "secondary": secondary}
            for domain in list(DOMAIN_KEYWORDS.keys()) + ["general"]}

DOMAIN_EXPERTISE = _build_domain_expertise()


def select_expertise(domain: str, is_leadership: bool) -> list[str]:
    pools = DOMAIN_EXPERTISE.get(domain, DOMAIN_EXPERTISE["bi"])
    selected: list[str] = list(pools["primary"])

    if is_leadership:
        for item in LEADERSHIP_EXPERTISE:
            if item not in selected:
                selected.append(item)

    # Fill with secondary up to 8 domain items (leaving room for 2 pinned)
    for item in pools["secondary"]:
        if len(selected) >= 8:
            break
        if item not in selected:
            selected.append(item)

    for item in PINNED_EXPERTISE:
        if item not in selected:
            selected.append(item)

    return selected[:10]


# ─────────────────────────────────────────────────────────────────────────────
# SKILLS SELECTION  (STEP 1c rules)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# SKILLS + TAGS — loaded from candidate_profile.json
# ─────────────────────────────────────────────────────────────────────────────

CORE_SKILLS        = _PROFILE.get("core_skills", {}).get("skills", [])
PINNED_SKILLS      = []  # Add any always-pinned skills to core_skills in candidate_profile.json
ALL_ANALYTICS_TAGS = set(_PROFILE.get("resume_tags", {}).get("tags", []))

CONDITIONAL_SKILLS: dict[str, list[str]] = {
    "XGBoost": [
        "ml model", "machine learning", "classification", "prediction model",
        "xgboost", "gradient boosting",
    ],
    "Prompt Engineering": [
        "llm", "genai", "generative ai", "prompt", "language model",
        "ai tool", "large language", "natural language",
    ],
    "MCP Servers": [
        "mcp", "agentic", "workflow automation", "ai tooling", "orchestration",
    ],
}
EXCLUDED_MENTIONS = _PROFILE.get("profile", {}).get("excluded_tools", {}).get("tools", [])
# Tools in excluded_tools are blocked from Skills, Core Expertise, Profile Summary, Cover Letter.
# They CAN appear in work_history bullets (historical factual record).


def detect_conditional_skills(jd: str) -> list[str]:
    jd_lower = jd.lower()
    return [s for s, kws in CONDITIONAL_SKILLS.items() if any(kw in jd_lower for kw in kws)]


def select_skills(conditional: list[str]) -> list[str]:
    return CORE_SKILLS + conditional + PINNED_SKILLS


# ─────────────────────────────────────────────────────────────────────────────
# TITLE LINES — built from candidate_profile.json → headline_by_domain
# Edit candidate_profile.json to change the headline shown under your name.
# ─────────────────────────────────────────────────────────────────────────────

_HEADLINE_CONFIG = _PROFILE.get("headline_by_domain", {})

def _build_title_lines() -> dict:
    result = {}
    for domain, variants in _HEADLINE_CONFIG.items():
        if domain.startswith("_"):
            continue
        default    = variants.get("default", ["YOUR TITLE", "Your Specialties"])
        leadership = variants.get("leadership", default)
        result[(domain, False)] = default
        result[(domain, True)]  = leadership
    if not result:
        result[("general", False)] = ["Professional", "Domain · Strategy"]
        result[("general", True)]  = ["Lead Professional", "Domain · Leadership"]
    return result

TITLE_LINES = _build_title_lines()

def _build_contract_title_lines() -> dict:
    result = {}
    for domain, variants in _HEADLINE_CONFIG.items():
        if domain.startswith("_"):
            continue
        base = variants.get("default", ["Consultant", "Domain · Remote EOR"])
        title    = base[0].replace("Lead ", "Interim ").replace(" Manager", " Consultant")
        subtitle = (base[1] if len(base) > 1 else "Domain") + " · Remote EOR"
        result[domain] = [title, subtitle]
    return result

CONTRACT_TITLE_LINES = _build_contract_title_lines()

_PARA4_INSTRUCTIONS: dict[str, str] = {
    "contract_remote": (
        "EOR FRAMING — MANDATORY. Para 4 must state: (1) immediate availability as "
        "remote contractor via EOR (Deel or Remote.com), zero compliance overhead for "
        "the hiring company; (2) 6+ daily hours UK/CET overlap; (3) one JD-specific "
        "excitement sentence about this company or role; (4) call to action. "
        "NEVER mention visa sponsorship, relocation, or right to work."
    ),
    "contract_hybrid": (
        "HYBRID CONTRACT. Para 4 uses standard market relocation + visa sentence "
        "for this market. May briefly note contract/EOR flexibility as an aside. "
        "Keep standard visa framing — do not lead with EOR."
    ),
    "permanent_remote": (
        "PERMANENT REMOTE. Para 4: aspirational personal intent to relocate + "
        "market-appropriate visa sentence (framed as personal aspiration, not "
        "employer obligation). Add one sentence on remote-first working style "
        "and timezone alignment."
    ),
    "permanent_hybrid": (
        "PERMANENT HYBRID — STANDARD. Para 4: market-specific relocation intent "
        "sentence + visa sentence. Existing behaviour unchanged."
    ),
}


def select_title_lines(domain: str, is_leadership: bool) -> list[str]:
    return TITLE_LINES.get((domain, is_leadership), TITLE_LINES[("product", False)])


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY PROMPT BUILDER — built from candidate_profile.json
# ─────────────────────────────────────────────────────────────────────────────

def _build_summary_prompt(is_leadership: bool, is_investment: bool) -> str:
    _p = _PROFILE.get("profile", {})
    years = _p.get("years_of_experience", 5)
    industries = _p.get("industry_history", {}).get("industries", ["YOUR_INDUSTRY_1", "YOUR_INDUSTRY_2"])
    industry_str = ", ".join(industries) if industries else "YOUR_INDUSTRY_1, YOUR_INDUSTRY_2"
    framing_rules = _p.get("framing_rules", {}).get("rules", [])
    framing_note = (" Additional framing rules: " + "; ".join(framing_rules)) if framing_rules else ""

    verbatim_cfg = _p.get("verbatim_sentences", {})
    verbatim_list = verbatim_cfg.get("sentences", [])
    investment_sentence = verbatim_cfg.get("investment_sentence", "")

    leadership_s2s3 = (
        "S2: [One sentence on a domain strength from work history — no % metrics]\n"
        "S3: [One sentence on team leadership — led and mentored cross-functional teams, "
        "building capability in core tools and stakeholder delivery. No % metrics]\n"
    )
    ic_s2s3 = "S2-S3: [Two sentences on domain strengths — no % metrics]\n"

    sentences = (
        f"S1: [Role + {years}+ years + 2-3 industries STRICTLY from your actual employer sectors: "
        f"{industry_str}. Do NOT mirror the target company's industry or claim industries you have not worked in. "
        f"If applicable, include international onsite experience as a deployment within a longer tenure — "
        f"never as a standalone stint. No third-person pronouns (his/he/him) — use 'a' or 'the' instead. "
        f"No metrics]{framing_note}\n"
        + (leadership_s2s3 if is_leadership else ic_s2s3)
    )

    if verbatim_list:
        for i, s in enumerate(verbatim_list, start=4):
            sentences += f"S{i} (verbatim): '{s}'\n"
    if is_investment and investment_sentence:
        sentences += f"S_investment (verbatim, append only for investment JDs): '{investment_sentence}'\n"

    sentence_count = 4 + len(verbatim_list) + (1 if is_investment and investment_sentence else 0)
    word_target = "≤90w (4-sentence)" if sentence_count <= 4 else f"≤{70 + sentence_count * 15}w ({sentence_count}-sentence)"

    return (
        f"Write exactly {sentence_count} sentences "
        f"({'5 if is_investment and investment_sentence exists' if is_investment and investment_sentence else str(sentence_count)}):\n"
        + sentences
        + f"Target: {word_target}. FILL_ME"
    )


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIENCE BANK PARSING
# ─────────────────────────────────────────────────────────────────────────────

# Bullet tags that map to each detected domain (for scoring)
DOMAIN_BULLET_TAGS: dict[str, set[str]] = {
    "product":    {"product", "growth", "experimentation"},
    "marketing":  {"experimentation", "CRM", "growth"},
    "crm":        {"CRM", "growth", "product"},
    "pricing":    {"pricing", "bi"},
    "bi":         {"bi", "data-eng"},
    "general":    {"product", "growth", "CRM", "pricing", "experimentation", "leadership"},
}

# JD keyword clusters → bullet tag to inject into domain_tags at runtime.
# When any pattern is found in the JD, the corresponding bullet tag is added to domain_tags
# so bullets carrying that tag enter the primary scoring pool instead of the diversity pool.
# [leadership] excluded — handled separately via is_leadership flag.
JD_TAG_AUGMENTATION: list[tuple[list[str], str]] = [

    # ── [experimentation] ──────────────────────────────────────────────────────
    ([
        "experiment", "experimentation", "experimental design",
        "a/b test", "ab test", "split test", "multivariate test", "mvt",
        "incrementalit", "causal inference", "causal analysis", "causal model",
        "hypothesis test", "hypothesis-driven",
        "statistical significan", "statistical rigour", "statistical rigor",
        "control group", "treatment group", "holdout group",
        "test and learn", "test & learn", "lift test", "lift measurement",
        "randomised controlled", "randomized controlled", "rct",
        "bayesian test", "bayesian analysis",
        "propensity score matching", "difference-in-difference",
        "marketing mix model", "media mix model", "mmm",
        "marketing measurement", "attribution model", "attribution modelling",
        "measurement framework", "test framework", "experiment platform",
        "mta", "multi touch attribution", "multi-touch attribution",
    ], "experimentation"),

    # ── [CRM] ──────────────────────────────────────────────────────────────────
    ([
        "crm", "customer relationship management",
        "lifecycle", "customer lifecycle", "lifecycle analytics",
        "customer retention", "retention analytics",
        "churn", "churn prediction", "churn model",
        "segmentation", "customer segment", "audience segment",
        "propensit",
        "reactivat", "win-back", "winback", "lapsed customer",
        "loyalty", "loyalty programme", "loyalty program",
        "customer journey", "journey analytics",
        "campaign analytics", "campaign performance", "campaign optimis",
        "customer lifetime value", "clv", "ltv",
        "customer health score", "health score",
        "customer intelligence", "customer insight",
        "customer engagement", "subscriber analytics",
        "email marketing analytics", "marketing automation",
        "customer behaviour analytics", "customer behavior analytics",
    ], "CRM"),

    # ── [growth] ───────────────────────────────────────────────────────────────
    ([
        "growth analytics", "growth analysis", "growth hacking", "growth marketing",
        "growth team", "growth squad", "growth metrics", "growth kpi",
        "acquisition funnel", "user acquisition", "customer acquisition",
        "activation", "user activation", "onboarding analytics",
        "conversion", "conversion rate", "conversion optimis",
        "funnel analysis", "funnel optimis", "funnel performance",
        "dau", "mau", "wau", "daily active user", "monthly active user",
        "north star metric", "north star",
        "product-led growth", "plg",
        "feature adoption", "feature usage",
        "engagement metric", "user engagement",
        "payback period", "marketplace growth",
        "viral", "virality", "referral programme",
    ], "growth"),

    # ── [product] ──────────────────────────────────────────────────────────────
    ([
        "product analytics", "product analysis", "product metrics", "product kpi",
        "user behaviour", "user behavior", "user journey", "user experience analytic",
        "product intelligence", "product performance",
        "ecommerce analytics", "marketplace analytics",
        "app analytics", "mobile analytics",
        "product funnel", "product roadmap analytic",
        "ux analytics", "cx analytics",
        "digital product", "product strategy analytic",
        "product team", "product manager", "product owner",
        "self-serve product",
    ], "product"),

    # ── [pricing] ──────────────────────────────────────────────────────────────
    ([
        "pricing", "price analytics", "pricing analytics", "pricing strategy",
        "dynamic pricing", "algorithmic pricing",
        "commercial analytics", "commercial analysis", "commercial modelling",
        "commercial strategy", "commercial decisions",
        "margin", "margin analysis", "margin analytics",
        "p&l", "profit and loss",
        "revenue optimis", "revenue optimiz", "revenue analytics",
        "procurement", "procurement analytics",
        "financial modelling", "financial model", "financial analysis",
        "inventory optimis", "inventory management",
        "price elasticit", "price sensitivity",
        "yield management", "yield analytics",
        "monetisat", "monetizat",
        "unit economics", "cac", "cost per acquisition",
        "go-to-market analytic",
    ], "pricing"),

    # ── [ai] ───────────────────────────────────────────────────────────────────
    ([
        "machine learning", "ml model", "ml pipeline",
        "predictive model", "predictive analytics", "predictive analytic",
        "data science", "data scientist",
        "statistical model", "statistical modelling",
        "xgboost", "gradient boosting", "random forest",
        "classification model", "regression model", "clustering model",
        "nlp", "natural language processing",
        "llm", "large language model",
        "generative ai", "genai", "gen ai",
        "deep learning", "neural network",
        "forecast", "time series model",
        "recommendation system", "recommender system",
        "anomaly detection",
        "feature engineering",
        "model deployment", "model serving",
        "mlops", "ml ops",
        "supervised learning", "unsupervised learning",
        "bayesian model",
        "ai/ml", "ai & ml",
        "langchain", "openai", "anthropic",
        "prompt engineering", "agentic", "llm workflow",
    ], "ai"),

    # ── [bi] ───────────────────────────────────────────────────────────────────
    ([
        "business intelligence", " bi ", "bi/",
        "dashboard", "dashboarding", "data visualis", "data visualiz", "data viz",
        "tableau", "power bi", "looker", "qlik",
        "reporting", "data reporting", "business reporting",
        "kpi", "key performance indicator", "kpi framework", "kpi strategy",
        "self-serve analytics", "self-service analytics",
        "data literacy", "certified metrics", "semantic layer",
        "stakeholder reporting", "insight delivery", "insight generation",
        "analytics infrastructure", "analytics platform",
        "single source of truth", "ssot",
        "reporting layer", "analytics enablement", "analytics governance",
        "data product",
    ], "bi"),

    # ── [data-eng] ─────────────────────────────────────────────────────────────
    ([
        "data engineering", "data pipeline", "data pipelines",
        "etl", "elt", "data transformation",
        "dbt", "data build tool",
        "data warehouse", "data warehousing", "data lakehouse", "data lake",
        "data model", "data modelling", "data modeling",
        "data architecture", "analytics architecture",
        "bigquery", "redshift", "snowflake",
        "data platform", "modern data stack",
        "apache airflow", "workflow orchestration",
        "data quality", "data governance", "data infrastructure",
        "apache spark", "spark",
        "cloud data platform", "cloud data",
        "advanced sql", "complex sql", "sql optimis",
    ], "data-eng"),
]


def _augment_domain_tags(base_tags: set, jd_text: str) -> set:
    """Expand domain_tags with JD-signal-derived tags so JD-relevant bullets
    enter the primary scoring pool rather than being relegated to the diversity pool."""
    if not jd_text:
        return base_tags
    augmented = set(base_tags)
    jd_lower = jd_text.lower()
    for patterns, tag in JD_TAG_AUGMENTATION:
        if tag not in augmented and any(p in jd_lower for p in patterns):
            augmented.add(tag)
    return augmented


def parse_bullet_line(line: str) -> Optional[Tuple[set, str]]:
    """Parse '- [tag1] [tag2] bullet text' → (tags, text). Returns None if not a bullet."""
    line = line.strip()
    if not line.startswith("- ["):
        return None
    body = line[2:].strip()   # strip leading "- "
    tags: set[str] = set()
    while body.startswith("["):
        close = body.find("]")
        if close < 0:
            break
        tag = body[1:close]
        if re.match(r"^[\w-]+$", tag):
            tags.add(tag)
        body = body[close + 1:].strip()
    if not body:
        return None
    return tags, body


def mentions_excluded(text: str) -> bool:
    t = text.lower()
    return any(e in t for e in EXCLUDED_MENTIONS)


IMPACT_RE_AUTO = re.compile(r'\d+%|from \d+ to \d+|\d+x\b', re.IGNORECASE)

# ── Bullet text transforms applied at prep time ───────────────────────────────
# Add entries here to shorten long bullets from your experience_bank.md at render time.
# Format: {"exact original bullet text": "shortened version"}
# These are applied AFTER bullet selection but BEFORE JSON output.
# Useful when a bullet is important but too long for a 2-page resume.
# Excluded-tool replacement: replace bullets mentioning excluded tools with clean versions.
# Leave all three empty dicts if not needed.

# Exact bullet replacement for excluded-tool sentences (old → clean version)
_EXCLUDED_TOOL_OLD: str = ""   # Set to the exact bullet text mentioning an excluded tool
_EXCLUDED_TOOL_NEW: str = ""   # Set to the cleaned replacement bullet text

# Exact bullet to drop (e.g. an outdated workflow bullet you always remove)
_DROP_BULLET: str = ""

# Replacement bullet to add when _DROP_BULLET is removed (leave "" to just drop)
_DROP_BULLET_REPLACEMENT: str = ""

_BULLET_SHORTEN: dict[str, str] = {
    # Add your own entries if any bullets from experience_bank.md are too long.
    # EXAMPLE: "Led a comprehensive analysis of the product funnel covering all seven stages...": "Led funnel analysis across all product stages — identifying key drop-off points and informing OKR prioritisation.",
}


def _apply_bullet_transforms(bullets: list[str]) -> list[str]:
    """Apply post-selection bullet transforms: excluded-tool replacement, drop bullet, SHORTEN."""
    result = []
    drop_removed = False
    for b in bullets:
        if _DROP_BULLET and b == _DROP_BULLET:
            drop_removed = True
            continue
        if _EXCLUDED_TOOL_OLD and _EXCLUDED_TOOL_NEW and b == _EXCLUDED_TOOL_OLD:
            result.append(_EXCLUDED_TOOL_NEW)
            continue
        result.append(_BULLET_SHORTEN.get(b, b))
    if drop_removed and _DROP_BULLET_REPLACEMENT and _DROP_BULLET_REPLACEMENT not in result:
        result.append(_DROP_BULLET_REPLACEMENT)
    return result


# Impact floor per role — ensures proportional representation of impact bullets.
# Format: {bank_key_lowercase: (impact_bullets_in_bank, total_bullets_in_bank)}
# Derive from your own experience_bank.md bullet counts.
# If a key is missing, no floor is enforced (all bullets scored by domain relevance).
# EXAMPLE: {"acme corp": (3, 8), "startup ltd": (2, 5)}
ROLE_IMPACT_FLOOR: dict[str, tuple[int, int]] = {}


def score_bullet(tags: set, domain_tags: set, is_leadership: bool) -> int:
    s = len(tags & domain_tags)
    if is_leadership and "leadership" in tags:
        s += 4
    return s


def parse_experience_bank(path: Path) -> dict[str, list[dict]]:
    """Returns {bank_key: [{tags, text}, ...]} for each role section."""
    content = path.read_text(encoding="utf-8")
    # Split on role section headings
    parts = re.split(r"\n## ", "\n" + content)
    result: dict[str, list[dict]] = {}

    for part in parts[1:]:
        lines = part.split("\n")
        header = lines[0].strip()

        matched_key: Optional[str] = None
        for meta in ROLE_METADATA:
            if meta["bank_key"] in header:
                matched_key = meta["bank_key"]
                break
        if not matched_key:
            continue

        bullets = []
        for line in lines[1:]:
            parsed = parse_bullet_line(line)
            if parsed:
                tags, text = parsed
                bullets.append({"tags": tags, "text": text})

        result[matched_key] = bullets

    return result


def select_bullets_for_role(
    bank_bullets: list[dict],
    max_n: int,
    domain_tags: set,
    is_leadership: bool,
    pinned: bool = False,
    jd_text: str = "",
    company_key: str = "",
) -> tuple[list[str], list[dict]]:
    """Returns (selected_bullets, score_export).
    score_export is a list of all non-excluded bullets with their scores,
    sorted descending, for use by eval_prep.py D2 check.
    """
    if pinned:
        texts = [b["text"] for b in bank_bullets]
        return texts, []

    # JD keyword positions: word → fraction of JD length at first occurrence (0.0=start, 1.0=end)
    # Early-JD keywords (must-have requirements) score 3×; mid 2×; late (nice-to-haves) 1×.
    jd_len = len(jd_text) if jd_text else 1
    jd_word_pos: dict[str, float] = {}
    if jd_text:
        for _m in re.finditer(r'\b[a-z]{5,}\b', jd_text.lower()):
            if _m.group() not in jd_word_pos:
                jd_word_pos[_m.group()] = _m.start() / jd_len

    def _jd_pos_score(text: str) -> int:
        """Positional JD keyword score: early-JD keywords score 3, mid 2, late 1."""
        t = text.lower()
        total = 0
        for word, pos_frac in jd_word_pos.items():
            if word in t:
                total += 3 if pos_frac < 0.33 else (2 if pos_frac < 0.67 else 1)
        return total

    domain_pool: list[tuple] = []   # domain score >= 1
    other_pool:  list[tuple] = []   # domain score == 0

    for b in bank_bullets:
        s = score_bullet(b["tags"], domain_tags, is_leadership)
        pure_s = len(b["tags"] & domain_tags)
        kw = _jd_pos_score(b["text"])
        if pure_s >= 1:
            domain_pool.append((s, kw, b["text"], b["tags"]))
        else:
            gen_s = len(b["tags"] & ALL_ANALYTICS_TAGS)
            if is_leadership and "leadership" in b["tags"]:
                gen_s += 2
            other_pool.append((gen_s, kw, b["text"], b["tags"]))

    # Primary: pure domain tag count — ensures higher-augmentation bullets always rank above
    # lower-tag bullets regardless of JD keyword overlap (generic bullets accumulate many
    # common early-JD words and would otherwise distort the ranking).
    # Secondary: jd_pos_score — within the same tag tier, earlier JD requirements win.
    # Tertiary: total score (leadership bonus) — tiebreaker only.
    domain_pool.sort(key=lambda x: (len(x[3] & domain_tags), x[1], x[0]), reverse=True)
    # Diversity: combined gen_s + jd_pos_score + metric presence (+1 if bullet contains a
    # canonical CV metric: 40%, 30%, 85%, 70%, 35%) — ensures XGBoost (85%) beats Airflow
    # (no metric) when both compete for the same diversity slot at equal gen_s + jd_pos_score.
    _CANONICAL_METRICS = {"40%", "30%", "85%", "70%", "35%"}
    other_pool.sort(
        key=lambda x: x[0] + x[1] + (1 if any(m in x[2] for m in _CANONICAL_METRICS) else 0),
        reverse=True,
    )

    diversity_n = max_n // 2
    primary_n   = max_n - diversity_n

    # Pass 1 — primary (domain-relevant); track as (text, score) tuples
    primary_scored = [(t, s) for s, _, t, _ in domain_pool[:primary_n]]

    # Pass 2 — diversity (breadth); expands if primary ran short
    actual_div = diversity_n + (primary_n - len(primary_scored))
    diversity_scored = [(t, gen_s) for gen_s, _, t, _ in other_pool[:actual_div]]

    # Pass 3 — fill any remaining gap from leftover domain pool
    all_selected = {t for t, _ in primary_scored + diversity_scored}
    for s, _, t, _ in domain_pool[primary_n:]:
        if len(primary_scored) + len(diversity_scored) >= max_n:
            break
        if t not in all_selected:
            diversity_scored.append((t, s))
            all_selected.add(t)

    selected_scored: list[tuple[str, int]] = primary_scored + diversity_scored

    # Pass 4 — Impact floor: ensure proportional representation of impact bullets
    ck = company_key.lower().strip()
    floor_pair = ROLE_IMPACT_FLOOR.get(ck)
    if floor_pair and floor_pair[0] > 0:
        bank_q, bank_total = floor_pair
        n = len(selected_scored)
        expected_impact = max(1, round(n * bank_q / bank_total))
        actual_impact   = sum(1 for t, _ in selected_scored if IMPACT_RE_AUTO.search(t))

        if actual_impact < expected_impact:
            sel_texts = {t for t, _ in selected_scored}
            # Highest-scoring unselected impact bullets (descending)
            remaining_impact = sorted(
                [b for b in bank_bullets
                 if b["text"] not in sel_texts and IMPACT_RE_AUTO.search(b["text"])],
                key=lambda b: score_bullet(b["tags"], domain_tags, is_leadership),
                reverse=True,
            )
            # Lowest-scoring non-impact selected bullets (ascending by score)
            non_impact = sorted(
                [(t, s) for t, s in selected_scored if not IMPACT_RE_AUTO.search(t)],
                key=lambda x: x[1],
            )
            for cand, victim in zip(remaining_impact, non_impact):
                if actual_impact >= expected_impact:
                    break
                selected_scored.remove(victim)
                selected_scored.append(
                    (cand["text"], score_bullet(cand["tags"], domain_tags, is_leadership))
                )
                actual_impact += 1

    # Pass 5 — JD top-down ordering: re-sort selected bullets within each role section.
    # Primary key: stored domain relevance score (x[1]) — preserves tag-count ordering.
    # Secondary key: jd_pos_score — within the same relevance tier, mirrors JD priority order
    # so the bullet addressing the JD's earliest requirement appears first in the section.
    if jd_word_pos:
        selected_scored.sort(key=lambda x: (x[1], _jd_pos_score(x[0])), reverse=True)
    selected = [t for t, _ in selected_scored]

    # Pass 6 — Team-leadership guarantee: for is_leadership JDs, ensure the [team-lead]-
    # tagged bullet for this role is (a) included and (b) placed first.
    # Tag-based: [team-lead] is set on the specific people-management bullets in
    # experience_bank.md. This is stable regardless of bullet text rewording.
    # Other [leadership]-tagged bullets (architecture migrations, Agile process changes)
    # do NOT carry [team-lead] so they cannot displace the team-leadership bullet.
    if is_leadership:
        tags_by_text = {b["text"]: b["tags"] for b in bank_bullets}
        lead_idx = next(
            (i for i, t in enumerate(selected) if "team-lead" in tags_by_text.get(t, set())),
            None,
        )
        if lead_idx is not None and lead_idx != 0:
            # Present but not first — move to front
            selected = [selected[lead_idx]] + selected[:lead_idx] + selected[lead_idx + 1:]
        elif lead_idx is None:
            # Not selected — find the [team-lead] bullet from bank and inject it
            mgmt_candidates = [b for b in bank_bullets if "team-lead" in b.get("tags", set())]
            if mgmt_candidates and selected:
                best_lead = max(
                    mgmt_candidates,
                    key=lambda b: score_bullet(b["tags"], domain_tags, True),
                )
                if best_lead["text"] not in set(selected):
                    # Replace the last selected bullet (lowest priority) with the team-lead bullet
                    selected[-1] = best_lead["text"]
                # Always put it first
                selected = [best_lead["text"]] + [t for t in selected if t != best_lead["text"]]

    selected_set = set(selected)

    # Build score_export for eval_prep.py D2 check — use pure domain score (no leadership bonus)
    # so D2 checks domain relevance ordering, not inflated leadership totals.
    score_export = []
    for b in bank_bullets:
        score_export.append({
            "score":    len(b["tags"] & domain_tags),
            "text":     b["text"],
            "tags":     sorted(b["tags"]),
            "selected": b["text"] in selected_set,
        })
    score_export.sort(key=lambda x: x["score"], reverse=True)

    return selected, score_export


def build_work_history(
    bank: dict[str, list[dict]], domain: str, is_leadership: bool, jd_text: str = ""
) -> tuple[list[dict], str, dict, list[str]]:
    """Returns (work_history, primary_company, bullet_scores_map, jd_keywords).
    bullet_scores_map: {bank_key: [{score, text, tags, selected}]} for eval_prep.py D2.
    jd_keywords: sorted list of 5+ char JD words used as tiebreakers in bullet selection.
    """
    domain_tags = DOMAIN_BULLET_TAGS.get(domain, {"product", "growth"})
    domain_tags = _augment_domain_tags(domain_tags, jd_text)
    if is_leadership:
        domain_tags = domain_tags | {"leadership"}  # leadership bullets rank top for mgr/lead JDs
    work_history = []
    primary_score = -1
    # Default to first non-pinned company in ROLE_METADATA
    _first_non_pinned = next((m["company"] for m in ROLE_METADATA if not m.get("pinned", False)), "")
    primary_company = _first_non_pinned.split("/")[0].strip().lower() if _first_non_pinned else ""
    bullet_scores_map: dict[str, list[dict]] = {}

    # Compute jd_keywords (mirrors select_bullets_for_role tiebreaker logic)
    jd_words = (
        {w.lower() for w in re.findall(r'\b[a-z]{5,}\b', jd_text.lower())}
        if jd_text else set()
    )

    for meta in ROLE_METADATA:
        key = meta["bank_key"]
        bank_bullets = bank.get(key, [])
        pinned = meta.get("pinned", False)

        bullets, score_export = select_bullets_for_role(
            bank_bullets, meta["max_bullets"], domain_tags, is_leadership, pinned,
            jd_text=jd_text,
            company_key=key,
        )
        if not bullets:
            bullets = [f"[Add bullets for {meta['company']} to experience_bank.md]"]

        if not pinned and score_export:
            bullet_scores_map[key] = score_export

        # Track which non-pinned role has the strongest first bullet
        if not pinned and bullets and bank_bullets:
            for b in bank_bullets:
                if b["text"] == bullets[0]:
                    top_s = score_bullet(b["tags"], domain_tags, is_leadership)
                    if top_s > primary_score:
                        primary_score = top_s
                        primary_company = meta["company"].split("/")[0].strip().lower()
                    break

        bullets = _apply_bullet_transforms(bullets)

        entry = {
            "company": meta["company"],
            "location": meta["location"],
            "role": meta["role"],
            "dates": meta["dates"],
            "bullets": bullets,
        }
        if meta.get("featured_link"):
            entry["featured_link"] = meta["featured_link"]
        if meta.get("focus_areas"):
            entry["focus_areas"] = meta["focus_areas"]
        work_history.append(entry)

    return work_history, primary_company, bullet_scores_map, sorted(jd_words)


# ─────────────────────────────────────────────────────────────────────────────
# COVER LETTER BANK PARSING
# ─────────────────────────────────────────────────────────────────────────────



def _extract_narrative_from_lines(lines: list[str]) -> str:
    """Collect paragraph text up to next heading or comment marker."""
    paras = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<!--") or stripped.startswith("##") or stripped.startswith("# ─"):
            break
        if stripped == "" and current:
            paras.append(" ".join(current))
            current = []
        elif stripped:
            current.append(stripped)
    if current:
        paras.append(" ".join(current))
    return " ".join(paras).strip()


def parse_cover_letter_bank(path: Path) -> dict[str, dict[str, str]]:
    """Returns {"section1": {...}, "section2": {...}, "section3": {...}}."""
    content = path.read_text(encoding="utf-8")

    # Locate the three section boundaries
    s1 = re.search(r"# ─+\n# SECTION 1", content)
    s2 = re.search(r"# ─+\n# SECTION 2", content)
    s3 = re.search(r"# ─+\n# SECTION 3", content)

    if not (s1 and s2 and s3):
        print("[auto_prep] WARNING: Could not parse cover_letter_bank.md — sections missing",
              file=sys.stderr)
        return {"section1": {}, "section2": {}, "section3": {}}

    s1_text = content[s1.start(): s2.start()]
    s2_text = content[s2.start(): s3.start()]
    s3_text = content[s3.start():]

    return {
        "section1": _parse_section1(s1_text),
        "section2": _parse_section2(s2_text),
        "section3": _parse_section3(s3_text),
    }


def _parse_section1(text: str) -> dict[str, str]:
    """Parse Para 2 narratives. Keys: '<company>_<tag>' and '<company>'."""
    result: dict[str, str] = {}
    parts = re.split(r"\n## ", text)
    for part in parts[1:]:
        lines = part.split("\n")
        header = lines[0].strip()
        # "Company: Acme Corp | [growth][experimentation][crm] Campaign SOT ..."
        m = re.match(r"Company:\s*(\w+)\s*\|", header)
        if not m:
            continue
        company = m.group(1).lower()
        tags = {t.lower() for t in re.findall(r"\[(\w[\w-]*)\]", header)}
        narrative = _extract_narrative_from_lines(lines[1:])
        if not narrative:
            continue
        for tag in tags:
            result.setdefault(f"{company}_{tag}", narrative)
        result.setdefault(company, narrative)
    return result


def _parse_section2(text: str) -> dict[str, str]:
    """Parse Para 3 themes. Keys: 'theme_<tag>'."""
    result: dict[str, str] = {}
    parts = re.split(r"\n## ", text)
    for part in parts[1:]:
        lines = part.split("\n")
        header = lines[0].strip()
        tags = {t.lower() for t in re.findall(r"\[(\w[\w-]*)\]", header)}
        narrative = _extract_narrative_from_lines(lines[1:])
        if not narrative:
            continue
        for tag in tags:
            result.setdefault(f"theme_{tag}", narrative)
    return result


def _parse_section3(text: str) -> dict[str, str]:
    """Parse Para 1 openers. Keys: domain name from primary tag."""
    result: dict[str, str] = {}
    parts = re.split(r"\n## ", text)
    for part in parts[1:]:
        lines = part.split("\n")
        header = lines[0].strip()
        tags = {t.lower() for t in re.findall(r"\[(\w[\w-]*)\]", header)}
        opener = _extract_narrative_from_lines(lines[1:])
        if not opener:
            continue
        for tag in tags:
            result[tag] = opener
    return result




def select_para1_opener(s3: dict[str, str], domain: str) -> str:
    return (
        s3.get(domain)
        or s3.get("product")
        or next(iter(s3.values()), "[Para 1 opener — write fresh]")
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Mechanical pre-fill for job prep step")
    parser.add_argument("--job_id", required=True, help="Job tracker ID (e.g. app_042)")
    parser.add_argument("--jd_file", required=True, help="Path to file containing JD text")
    parser.add_argument("--domain", default=None,
                        help="Override domain detection: product|crm|pricing|bi|general")
    parser.add_argument("--company", default=None,
                        help="Company display name for cover letter recipient line")
    args = parser.parse_args()

    jd_path = Path(args.jd_file)
    if not jd_path.exists():
        print(f"[auto_prep] ERROR: JD file not found: {jd_path}", file=sys.stderr)
        sys.exit(1)
    jd_text = jd_path.read_text(encoding="utf-8")

    # ── Domain analysis ───────────────────────────────────────────────────────
    # Primary signal: Pass-2 role_focus from tracker (semantic, Claude-assigned).
    # Fallback: keyword-based detect_domain (fast but less accurate).
    # --domain flag always wins over both.
    _ROLE_FOCUS_TO_DOMAIN = {
        "product_analytics":    "product",
        "marketing_analytics":  "marketing",
        "crm_analytics":        "crm",
        "commercial_analytics": "pricing",   # default; overridden by marketing keyword signal below
        "market_pricing":       "pricing",
        "bi_reporting":         "bi",
        # mixed / analytics_engineering / ai_engineering / etc → keyword fallback
    }
    _tracker_role_focus = None
    if args.job_id and not args.domain:
        try:
            _t = json.load(open(BASE_DIR / "data" / "job_tracker.json"))
            for _a in _t.get("applications", []):
                if _a.get("id") == args.job_id or str(_a.get("job_id", "")) == args.job_id:
                    _tracker_role_focus = _a.get("role_focus")
                    break
        except Exception:
            pass

    if args.domain:
        domain = args.domain
    elif _tracker_role_focus == "commercial_analytics":
        # commercial_analytics is ambiguous — MMM/marketing roles get this bucket from Pass 2
        # until re-scored with the new marketing_analytics value. Check keyword detection:
        # if JD contains specific marketing-measurement signals, prefer marketing over pricing.
        kw_domain = detect_domain(jd_text)
        if kw_domain == "marketing":
            domain = "marketing"
            print(f"[auto_prep] commercial_analytics overridden by marketing keyword signal → marketing")
        else:
            domain = "pricing"
            print(f"[auto_prep] domain from Pass-2 role_focus (commercial_analytics) → pricing")
    elif _tracker_role_focus and _tracker_role_focus in _ROLE_FOCUS_TO_DOMAIN:
        domain = _ROLE_FOCUS_TO_DOMAIN[_tracker_role_focus]
        print(f"[auto_prep] domain from Pass-2 role_focus ({_tracker_role_focus}) → {domain}")
    else:
        domain = detect_domain(jd_text)
        if _tracker_role_focus:
            print(f"[auto_prep] role_focus={_tracker_role_focus!r} not mapped — keyword domain: {domain}")

    is_leadership = is_leadership_jd(jd_text)
    conditional = detect_conditional_skills(jd_text)

    print(f"[auto_prep] job_id={args.job_id}  domain={domain}  "
          f"leadership={is_leadership}  conditional_skills={conditional}")

    # ── Load banks ────────────────────────────────────────────────────────────
    exp_bank_path = BASE_DIR / "data" / "content" / "experience_bank.md"
    cl_bank_path  = BASE_DIR / "data" / "content" / "cover_letter_bank.md"

    if not exp_bank_path.exists():
        print(f"[auto_prep] ERROR: {exp_bank_path} not found", file=sys.stderr)
        sys.exit(1)
    if not cl_bank_path.exists():
        print(f"[auto_prep] ERROR: {cl_bank_path} not found", file=sys.stderr)
        sys.exit(1)

    exp_bank = parse_experience_bank(exp_bank_path)
    cl_bank  = parse_cover_letter_bank(cl_bank_path)

    # ── Build components ──────────────────────────────────────────────────────
    work_history, primary_company, bullet_scores_map, jd_keywords = build_work_history(
        exp_bank, domain, is_leadership, jd_text=jd_text
    )
    expertise    = select_expertise(domain, is_leadership)
    skills       = select_skills(conditional)
    title_lines  = select_title_lines(domain, is_leadership)

    para1_opener = select_para1_opener(cl_bank["section3"], domain)
    para2        = "FILL_ME"   # LLM synthesizes from work_history bullets in STEP 5
    para3        = "FILL_ME"   # LLM synthesizes secondary breadth + AI closer in STEP 5

    # Sanitise company label for use in the cover letter recipient line.
    # Agency/anonymised postings carry verbose tracker strings like
    # "Unnamed fintech scale-up (client of WeDo recruitment)" that must
    # never appear verbatim as a salutation — use "Hiring Team" instead.
    _ANON_PATTERNS = ("unnamed", "(anonymised)", "undisclosed", "confidential client", "client of")
    _raw_company = args.company or "Company"
    _co_lower = _raw_company.lower()
    if any(p in _co_lower for p in _ANON_PATTERNS):
        company_label = "Hiring Team"
        print(f"[auto_prep] anonymised/agency company detected — recipient set to 'Hiring Team'")
    else:
        company_label = _raw_company

    # Derive city from job tracker entry (first segment of location field)
    # LinkedIn often returns verbose variants — normalise to clean city names
    _CITY_NORM_UK = {
        "greater london":     "London",
        "london area":        "London",
        "greater manchester": "Manchester",
        "west midlands":      "Birmingham",
        "west yorkshire":     "Leeds",
    }
    _CITY_NORM_NL = {
        "amsterdam":          "Amsterdam",
        "amsterdam area":     "Amsterdam",
        "amsterdam-centrum":  "Amsterdam",
        "noord-holland":      "Amsterdam",
        "amsterdam metropolitan area": "Amsterdam",
        "rotterdam":          "Rotterdam",
        "rotterdam-centrum":  "Rotterdam",
        "south holland":      "Rotterdam",
        "the hague":          "The Hague",
        "den haag":           "The Hague",
        "den haag centrum":   "The Hague",
        "utrecht":            "Utrecht",
        "utrecht-centrum":    "Utrecht",
        "haarlem":            "Haarlem",
        "amstelveen":         "Amstelveen",
        "hoofddorp":          "Hoofddorp",
        "diemen":             "Diemen",
        "leiden":             "Leiden",
        "hilversum":          "Hilversum",
        "eindhoven":          "Eindhoven",
    }
    _CITY_NORM_SE = {
        "stockholm":  "Stockholm",
        "gothenburg": "Gothenburg",
        "göteborg":   "Gothenburg",
        "malmö":      "Malmö",
        "malmo":      "Malmö",
    }
    _CITY_NORM_DE = {
        "berlin":       "Berlin",
        "munich":       "Munich",
        "münchen":      "Munich",
        "frankfurt":    "Frankfurt",
        "hamburg":      "Hamburg",
        "düsseldorf":   "Düsseldorf",
        "dusseldorf":   "Düsseldorf",
        "cologne":      "Cologne",
        "köln":         "Cologne",
        "koeln":        "Cologne",
        "bonn":         "Bonn",
        "stuttgart":    "Stuttgart",
        "hannover":     "Hannover",
        "nürnberg":     "Nuremberg",
        "nuremberg":    "Nuremberg",
        "nuernberg":    "Nuremberg",
        "karlsruhe":    "Karlsruhe",
        "leipzig":      "Leipzig",
        "bremen":       "Bremen",
        "essen":        "Essen",
        "dortmund":     "Dortmund",
        "duisburg":     "Duisburg",
        "mainz":        "Mainz",
        "wiesbaden":    "Wiesbaden",
        "eschborn":     "Eschborn",
        "leverkusen":   "Leverkusen",
        "gilching":     "Gilching",
    }
    _CITY_NORM_DK = {
        "copenhagen":                 "Copenhagen",
        "københavn":                  "Copenhagen",
        "kobenhavn":                  "Copenhagen",
        "copenhagen area":            "Copenhagen",
        "greater copenhagen":         "Copenhagen",
        "capital region":             "Copenhagen",
        "capital region of denmark":  "Copenhagen",
        "region hovedstaden":         "Copenhagen",
        "frederiksberg":              "Copenhagen",
        "aarhus":                     "Aarhus",
        "århus":                      "Aarhus",
    }
    _CITY_NORM_IE = {
        "dublin":            "Dublin",
        "dublin area":       "Dublin",
        "greater dublin":    "Dublin",
        "county dublin":     "Dublin",
        "dún laoghaire":     "Dublin",
        "dun laoghaire":     "Dublin",
        "sandyford":         "Dublin",
        "leopardstown":      "Dublin",
        "cork":              "Cork",
        "galway":            "Galway",
        "limerick":          "Limerick",
    }
    _CITY_NORM_AE = {
        "dubai":                    "Dubai",
        "dubai area":               "Dubai",
        "dubai, united arab emirates": "Dubai",
        "dubai, uae":               "Dubai",
        "dubai metropolitan area":  "Dubai",
        "difc":                     "Dubai",
        "dubai internet city":      "Dubai",
        "dubai media city":         "Dubai",
        "business bay":             "Dubai",
        "jumeirah lake towers":     "Dubai",
        "jlt":                      "Dubai",
        "sheikh zayed road":        "Dubai",
        "jebel ali":                "Dubai",
        "abu dhabi":                "Abu Dhabi",
        "abudhabi":                 "Abu Dhabi",
        "abu dhabi, united arab emirates": "Abu Dhabi",
        "sharjah":                  "Sharjah",
        "ajman":                    "Ajman",
        "united arab emirates":     "Dubai",
        "uae":                      "Dubai",
    }
    _CITY_DEFAULTS = {"uk": "London", "nl": "Amsterdam", "se": "Stockholm", "de": "Berlin",
                      "dk": "Copenhagen", "ie": "Dublin", "ae": "Dubai"}
    market = "uk"
    city   = "London"
    is_investment  = False
    is_remote_only = False
    is_contract    = False
    role_type      = "permanent_hybrid"
    eor_viability  = None
    work_mode      = "Unknown"
    try:
        with open(BASE_DIR / "data" / "job_tracker.json") as _f:
            _tracker = json.load(_f)
        _found = False
        for _app in _tracker.get("applications", []):
            if _app.get("id") == args.job_id or str(_app.get("job_id", "")) == args.job_id:
                _found = True
                market = _app.get("market", "uk")
                _loc = _app.get("location", "")
                # Cover date line uses the JOB's own city (normalised), all markets.
                # Anchor city (_CITY_DEFAULTS) is the fallback only when location is empty.
                if _loc:
                    _raw = _loc.split(",")[0].strip().lower()
                    _norm = (_CITY_NORM_UK if market == "uk"
                             else _CITY_NORM_NL if market == "nl"
                             else _CITY_NORM_SE if market == "se"
                             else _CITY_NORM_DE if market == "de"
                             else _CITY_NORM_DK if market == "dk"
                             else _CITY_NORM_IE if market == "ie"
                             else _CITY_NORM_AE if market == "ae"
                             else _CITY_NORM_UK)
                    city = _norm.get(_raw, _raw.title() if _raw else _CITY_DEFAULTS.get(market, "London"))
                else:
                    city = _CITY_DEFAULTS[market]
                # Read investment flag from tracker; fall back to keyword check.
                # tracker True → confirmed, trust it. tracker False or absent → always check JD
                # text (matches validate_prep V10 which always checks JD text regardless).
                tracker_flag = _app.get("is_investment_domain")
                if tracker_flag:
                    is_investment = True
                else:
                    is_investment = is_investment_jd_fallback(jd_text)
                # Work arrangement and contract flags.
                is_remote_only = bool(_app.get("is_remote_only"))
                is_contract    = bool(_app.get("is_contract"))
                work_mode      = _app.get("work_mode") or "Unknown"
                eor_viability  = _app.get("eor_viability")
                role_type      = (
                    _app.get("role_type")
                    or _compute_role_type(is_contract, is_remote_only)
                )
                break
        if not _found:
            # job_id not in tracker (manually-added) — use keyword fallback
            is_investment = is_investment_jd_fallback(jd_text)
    except Exception:
        is_investment = is_investment_jd_fallback(jd_text)

    if is_investment:
        print("[auto_prep] investment domain detected — S5 MF hook will be added to summary")
    today = datetime.date.today().strftime("%Y-%m-%d")

    # Contract roles use EOR address and contract-specific title lines.
    _is_contract_role = role_type in ("contract_remote", "contract_hybrid")
    contact = dict(CONTACT)
    if _is_contract_role:
        contact["address"] = _EOR_ADDRESS
    elif market in _RIGHT_TO_WORK_MARKETS:
        # User already has work authorisation in this market — no visa framing needed.
        contact["address"] = CONTACT.get("address", "")
    else:
        contact["address"] = _VISA_ADDRESS.get(market, CONTACT.get("address", ""))
    if _is_contract_role:
        title_lines = CONTRACT_TITLE_LINES.get(domain, CONTRACT_TITLE_LINES["general"])
        print(f"[auto_prep] role_type={role_type} → EOR address + CONTRACT_TITLE_LINES")
    else:
        print(f"[auto_prep] role_type={role_type}")

    bullet_counts = ", ".join(
        f"{r['company'].split('/')[0].strip()[:8]}:{len(r['bullets'])}"
        for r in work_history
    )
    print(f"[auto_prep] primary_company={primary_company}  bullets=[{bullet_counts}]")
    print(f"[auto_prep] expertise ({len(expertise)}): {expertise}")
    print(f"[auto_prep] skills: {skills}")

    # ── Resume JSON ───────────────────────────────────────────────────────────
    resume_json: dict = {
        "name": CONTACT.get("name", "YOUR FULL NAME"),
        "title_lines": title_lines,
        "contact": contact,
        "core_expertise": expertise,
        "skills": skills,
        "summary": _build_summary_prompt(is_leadership, is_investment),
        "work_history": work_history,
        "education": EDUCATION,
        "certifications": CERTIFICATIONS,
        "role_type":   role_type,
        "is_contract": is_contract,
        "_auto_prep_meta": {
            "domain": domain,
            "is_leadership": is_leadership,
            "is_investment": is_investment,
            "is_contract": is_contract,
            "role_type": role_type,
            "eor_viability": eor_viability,
            "primary_company": primary_company,
            "conditional_skills": conditional,
            "bullet_scores": bullet_scores_map,
            "jd_keywords": jd_keywords,
        },
    }

    # ── Cover letter JSON ─────────────────────────────────────────────────────
    hook_placeholder = (
        "[COMPANY_HOOK: 1-2 sentences — name the company + exact role title + "
        "one specific thing about the company's mission/product. FILL_ME]"
    )
    cover_json: dict = {
        "name": CONTACT.get("name", "YOUR FULL NAME"),
        "title_lines": title_lines,
        "contact": contact,
        "core_expertise": [],
        "skills": [],
        "date": f"{city}, {today}",
        "market": market,
        "work_mode": work_mode,
        "is_remote_only": is_remote_only,
        "is_contract": is_contract,
        "role_type": role_type,
        "eor_viability": eor_viability,
        "para4_instructions": _PARA4_INSTRUCTIONS[role_type],
        "recipient": company_label if company_label == "Hiring Team" else f"{company_label} Hiring Team",
        "salutation": "Dear Hiring Team,",
        "paragraphs": [
            para1_opener + " " + hook_placeholder,
            para2,
            para3,
            "FILL_ME",
        ],
        "closing": "Kind regards,",
        "_auto_prep_meta": {
            "domain": domain,
            "is_leadership": is_leadership,
            "is_investment": is_investment,
            "is_contract": is_contract,
            "role_type": role_type,
            "eor_viability": eor_viability,
            "primary_company": primary_company,
            "para1_source": "cover_letter_bank Section 3",
            "para2_source": "CV work_history bullets — LLM-synthesized (impactful + JD-relevant)",
            "para3_source": "CV work_history bullets — secondary breadth + mandatory AI closer",
            "ai_closer": (
                # Drawn from profile.verbatim_sentences.sentences[0] if set; else generic.
                _PROFILE.get("profile", {}).get("verbatim_sentences", {}).get("sentences", [""])[0]
                or "[YOUR_AI_CLOSER — e.g. 'I bring current hands-on AI automation capability, "
                "having built a production agentic pipeline using [YOUR_TOOLS].' "
                "Set profile.verbatim_sentences.sentences[0] in candidate_profile.json]"
            ),
        },
    }

    # ── Write outputs (with British English enforcement) ──────────────────────
    prep_tmp = BASE_DIR / "data" / "prep_tmp"
    prep_tmp.mkdir(parents=True, exist_ok=True)
    out_resume = prep_tmp / f"auto_resume_{args.job_id}.json"
    out_cover  = prep_tmp / f"auto_cover_{args.job_id}.json"

    # Apply British English substitution to all generated text before writing.
    # JSON string pass is safe — only affects string values, not JSON structure.
    _resume_str = _enforce_british_english(json.dumps(resume_json, indent=2, ensure_ascii=False))
    _cover_str  = _enforce_british_english(json.dumps(cover_json, indent=2, ensure_ascii=False))

    out_resume.write_text(_resume_str, encoding="utf-8")
    out_cover.write_text(_cover_str, encoding="utf-8")

    print(f"[auto_prep] ✓ Resume pre-fill → {out_resume}")
    print(f"[auto_prep] ✓ Cover pre-fill  → {out_cover}")
    print("[auto_prep] LLM tasks: fill 'summary' (4 sentences), "
          "replace '[COMPANY_HOOK: ... FILL_ME]' in paragraphs[0], "
          "synthesize paragraphs[1] (Para 2, 120-150w from CV bullets + JD relevance), "
          "synthesize paragraphs[2] (Para 3, 80-100w: secondary breadth + ai_closer), "
          "write paragraphs[3] (Para 4, ~70 words). "
          "Remove _auto_prep_meta before rendering.")


if __name__ == "__main__":
    main()
