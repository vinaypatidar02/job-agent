# CONFIGURATION.md — Full Parameter Reference

Complete reference for every configurable parameter in the pipeline.
For a step-by-step setup guide, see GUIDE.md §4.

---

## 1. .env Variables

Create `.env` from `.env.example`: `cp .env.example .env`

| Variable | Required | Where to Get | Description |
|----------|----------|-------------|-------------|
| `ANTHROPIC_API_KEY` | Yes | console.anthropic.com → API Keys | Used by score_jobs.py, generate_covers.py, generate_summaries.py. Separate billing from Claude Code subscription. |
| `APIFY_TOKEN` | Yes | console.apify.com → Settings → Integrations | Authenticates the LinkedIn Jobs Scraper actor. $5/month free credit on free tier. |
| `APIFY_LINKEDIN_ACTOR` | Yes | Keep as-is | Default: `bebity/linkedin-jobs-scraper`. Change only if you switch actors. |
| `YAHOO_EMAIL` | Yes | Your Yahoo email address | Used by gmail_backfill.py for IMAP login. Also works with Gmail/Outlook — see IMAP section below. |
| `YAHOO_APP_PASSWORD` | Yes | security.yahoo.com → Security → App Passwords → Generate | App-specific password — NOT your main password. Required even with 2FA enabled. |
| `GOOGLE_SHEET_ID` | Yes | From Sheet URL: `docs.google.com/spreadsheets/d/[ID]/edit` | The ID portion of your Google Sheets URL. |
| `GITHUB_TOKEN` | Yes (for git_sync.py) | github.com/settings/tokens → Generate new token (classic) → repo scope | Used by git_sync.py to push pipeline data. Optional if you push manually. |
| `GITHUB_REPO` | No | Your repo: `username/repo-name` | Used by monitor_scout.py to show CI run status. Leave blank to disable CI monitoring. |

### IMAP provider configuration (gmail_backfill.py)

```python
# Edit in scripts/gmail_backfill.py USER CONFIG section:
# Yahoo (default):  IMAP_HOST = "imap.mail.yahoo.com"     IMAP_PORT = 993
# Gmail:            IMAP_HOST = "imap.gmail.com"           IMAP_PORT = 993
# Outlook:          IMAP_HOST = "outlook.office365.com"    IMAP_PORT = 993
```

Yahoo is recommended: simplest app password flow, no OAuth complexity.
Gmail requires enabling IMAP in Gmail settings and generating an App Password (not your Google password).

---

## 2. candidate_profile.json — Field Reference

File location: `data/content/candidate_profile.json`
This is the single file you fill once to configure the entire pipeline.

### contact

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Your full name — appears in PDF header, email sign-offs |
| `email` | string | Yes | Professional email — appears in resume and cover letter |
| `phone` | string | Yes | Phone number — appears in resume contact block |
| `linkedin` | string | Yes | LinkedIn profile URL (linkedin.com/in/your-id) |
| `github` | string | No | GitHub profile URL — include if relevant to your field |
| `address` | string | Yes | "City, Country" — your current location |
| `eor_address` | string | No | Address override for EOR contract roles (e.g. "City, Country | Remote (EOR-ready: Deel / Remote.com)") |

### visa_addresses

Dictionary mapping market codes to address suffix strings. The suffix appears in the resume address line for that market.

```json
"visa_addresses": {
  "uk": "[YOUR_COUNTRY] | Seeking Skilled Worker Visa Sponsorship",
  "nl": "[YOUR_COUNTRY] | Seeking Kennismigrant Sponsorship",
  "de": "[YOUR_COUNTRY] | Seeking EU Blue Card Sponsorship"
}
```

Remove markets you are not targeting. Leave empty `{}` if you have right to work everywhere.

### has_right_to_work

```json
"has_right_to_work": {
  "markets": ["uk", "ie"]
}
```

List market codes where you already have work authorisation. Those markets skip all visa checks — visa_score is auto-set to 5 and para4_instructions omit the visa sentence.

### education

Array of education objects, most recent first.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `degree` | string | Yes | Full degree title: "B.Tech Computer Science" |
| `institution` | string | Yes | University name |
| `dates` | string | Yes | "YYYY – YYYY" |
| `gpa` | string | No | "X.X/10" — omit field if not listing |

### certifications

Array of strings. Most relevant first. Format: `"Certification Name — Issuer (YYYY)"`.

### experience

Array of role objects in reverse chronological order (most recent first).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `company` | string | Yes | Company name |
| `location` | string | Yes | City where role is based |
| `role` | string | Yes | Your job title |
| `dates` | string | Yes | "YYYY-MM-present" or "YYYY-MM–YYYY-MM" |
| `bank_key` | string | Yes | Must match the `## [heading]` in experience_bank.md exactly |
| `pinned` | bool | No | If true, always include this role regardless of domain |
| `max_bullets` | int | Yes | Maximum bullets to include from experience_bank.md |
| `focus_areas` | string | No | JD domain keywords to guide bullet selection |

### core_skills

```json
"core_skills": {
  "skills": ["Python", "SQL", "Tool A", "Tool B"]
}
```

Always included in the Skills section. List in priority order.

### domains

Dictionary of domain objects. auto_prep.py detects the JD domain from these keywords and selects matching bullets and headlines.

```json
"domains": {
  "primary": {
    "label": "Backend Engineering",
    "keywords": ["backend", "api", "microservices", "distributed"]
  },
  "secondary": {
    "label": "Platform / Infrastructure",
    "keywords": ["kubernetes", "devops", "ci/cd", "infrastructure"]
  },
  "general": {
    "label": "General",
    "keywords": []
  }
}
```

Add or remove domain keys freely — use any names that match your profession.

### headline_by_domain

Resume headline and subtitle per domain. Maps domain keys (above) to headline variants.

```json
"headline_by_domain": {
  "primary": {
    "default": ["Senior Software Engineer", "Backend · APIs · Distributed Systems"],
    "leadership": ["Engineering Manager", "Backend · Leadership · Scale"]
  }
}
```

`default` = IC roles. `leadership` = manager/lead roles. auto_prep.py picks based on `is_leadership` flag from JD scoring.

### resume_tags

```json
"resume_tags": {
  "tags": ["backend", "platform", "leadership", "data"]
}
```

Tags used to label bullets in experience_bank.md. A bullet tagged `[backend]` will be selected when domain = "primary" (if "backend" is in that domain's keywords).

**Field interdependency**: `resume_tags` → `domains` → `experience_bank.md` must be consistent:
- Tags listed in `resume_tags.tags` must appear as `[tag]` prefixes in experience_bank.md bullets
- A domain's `keywords` determine which tags get selected for that domain (e.g. if domain "primary" has keyword "backend", bullets tagged `[backend]` are favoured)
- Tags in experience_bank.md that are not in `resume_tags.tags` are still selectable as generic bullets

### profile

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `years_of_experience` | int | Yes | Total years — used in S1 profile summary |
| `target_roles` | array | Yes | List of target job titles — used in scoring prompt |
| `target_seniority` | string | Yes | Seniority description — used in scoring prompt |
| `industry_history.industries` | array | Yes | Industries you have worked in — used in S1 framing |
| `verbatim_sentences.sentences` | array | No | Sentences always appended to every profile summary |
| `verbatim_sentences.investment_sentence` | string | No | Finance-domain closing sentence — only appended when JD is finance-domain |
| `platform_notes.notes` | object | No | Per-employer data platform mapping. Used in cover letter SYSTEM_PROMPT. |
| `framing_rules.rules` | array | No | Special framing instructions for generate_covers.py SYSTEM_PROMPT |
| `required_portfolio_tools.tools` | array | No | V1 check: tools that must appear in Skills. Leave [] to skip. |
| `excluded_tools.tools` | array | No | V2 check: tools blocked from Skills/Summary/Cover. Leave [] to skip. |
| `canonical_metrics.metrics` | array | No | V7 check: exact metric strings that must appear unchanged. Leave [] to skip. |
| `industry_whitelist.industries` | array | No | V17 check: industries you can honestly claim. Leave [] to allow all. |

---

## 3. experience_bank.md Format

File location: `data/content/experience_bank.md`

```markdown
## Company Name
Role Title | Start Date – End Date

• [tag] Action verb + context + metric. Max 28 words per bullet.
• [tag] Another bullet. Only include what you can defend in an interview.
• [tag] Metrics must be exact — never rounded or paraphrased.
```

Rules:
- `## Company Name` must match `bank_key` in candidate_profile.json `experience[]` exactly
- Tags must match `resume_tags` in candidate_profile.json
- `max_bullets` per role is set in candidate_profile.json `experience[].max_bullets`
- This file is the only source of resume bullet content — auto_prep.py cannot invent bullets
- Metrics (percentages, team sizes, timeframes) are preserved verbatim by validate_prep.py V7

---

## 4. CLAUDE.md Customisation

| Section | What to edit | What to keep |
|---------|-------------|-------------|
| §2 — Candidate Profile | Everything (or edit docs/candidate-profile.md which §2 imports) | — |
| §3 — Job Search Preferences | Target roles, salary threshold, city tiers, industry preferences | Visa market names |
| §4 — Fit Scoring Rubric | (edit docs/fit-scoring-rubric.md which §4 imports) | Scoring thresholds (≥75, 60-74, <60) |
| §5–§13 | Leave as-is | Pipeline rules apply to any profession |

---

## 5. LinkedIn URL Builder

Build search URLs at linkedin.com/jobs, then copy the full URL to `SEARCHES_APIFY` in `scripts/run_scout.py`.

Key URL parameters:

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `f_TPR` | `r86400` | Past 24 hours (86400 seconds) |
| `f_TPR` | `r604800` | Past 7 days |
| `f_E` | `4` | Mid-Senior level |
| `f_E` | `5` | Director level |
| `f_E` | `4%2C5` | Mid-Senior AND Director (URL-encoded comma) |
| `f_JT` | `F` | Full-time |
| `f_JT` | `C` | Contract |
| `f_JT` | `F%2CC` | Full-time AND Contract |
| `geoId` | see table | Geographic region |

geoId values by market:

| Market | geoId |
|--------|-------|
| United Kingdom | 101165590 |
| Netherlands | 102890719 |
| Germany | 101282230 |
| Sweden | 105117694 |
| Denmark | 104514075 |
| Ireland | 104738515 |
| UAE | 104305776 |

Example search entry in run_scout.py:
```python
SEARCHES_APIFY = [
    ("Head of Analytics",
     "https://www.linkedin.com/jobs/search?keywords=Head+of+Analytics&geoId=101165590&f_TPR=r86400&f_E=4%2C5&f_JT=F",
     100),  # max 100 jobs — costs max $0.10
]
```

---

## 6. score_jobs.py USER CONFIG

All configurable blocks are in the `USER CONFIGURATION` section at the top of `scripts/score_jobs.py`.

| Config Block | Default | Purpose |
|-------------|---------|---------|
| `MAX_AGE` | 30 days | Hard-reject postings older than this — not tracked |
| `STALE_AGE_DAYS` | 3 days | Default stale threshold — older postings tracked as Stale, not scored |
| `_STALE_DAYS_BY_MARKET` | `{"uk": 3, "nl": 7, ...}` | Per-market stale override |
| `TITLE_REJECT_CONTAINS` | `[]` | Always-reject title substrings. Example: `["junior", "intern", "qa engineer"]` |
| `TARGET_TITLE_KEYWORDS` | set | Keywords required in stale posting titles. Example: `{"engineer", "developer", "architect"}` |
| `TOOLING_PRIMARY_TITLE_BLOCKLIST` | `[]` | Reject if title is primarily an irrelevant tool. Example: `["cobol developer", "mainframe"]` |
| `REJECT_REMOTE_ONLY_FLAG` | `False` | If True, reject jobs LinkedIn marks as Remote Only |
| `REJECT_CONTRACT_ROLES` | `False` | If True, reject jobs LinkedIn marks as Contract |
| `REJECT_PART_TIME` | `True` | If True, reject part-time jobs (default True for most job seekers) |
| `COMPANY_TYPE_BLOCKLIST` | `set()` | Company names (lowercase) to fast-reject. Example: `{"mckinsey", "deloitte"}` |
| `MARKET_BRAND_ALLOWLIST` | `{}` | Per-market brand whitelist. Example: `{"se": {"Spotify", "Klarna"}}` |
| `ANALYTICS_NAMED_DS_COMPANIES` | `set()` | Companies that mislabel analytics roles as "Data Science" — still scored |
| `PERMANENT_DESPITE_JOB_TYPE` | `set()` | Companies that mislabel permanent roles as temporary — treated as permanent |

---

## 7. classify_title.py — Profession Configuration

The title tier classifier uses regex patterns to score job titles into Tiers 1–5.
Default patterns are tuned for analytics/data roles.

To configure for a different profession, edit the patterns in `scripts/classify_title.py`:

```python
# Current default (analytics/data):
_HAS_ANALYTICS = re.compile(
    r'\b(analytics|analyst|insights?|intelligence|growth|commercial|'
    r'performance|behavioural?|behavioral|reporting|crm)\b'
)
_HAS_LEAD_MGR = re.compile(r'\b(manager|lead|head|principal)\b')

# Software Engineering example:
_HAS_ANALYTICS = re.compile(r'\b(engineer|developer|programmer|architect|devops|platform)\b')
_HAS_LEAD_MGR = re.compile(r'\b(manager|lead|head|principal|staff|distinguished|fellow)\b')

# Finance / FP&A example:
_HAS_ANALYTICS = re.compile(r'\b(finance|financial|accounting|treasury|fp&a|risk|compliance)\b')
_HAS_LEAD_MGR = re.compile(r'\b(manager|controller|head|director|vp|partner)\b')

# Product Management example:
_HAS_ANALYTICS = re.compile(r'\b(product|growth|platform|strategy|portfolio)\b')
_HAS_LEAD_MGR = re.compile(r'\b(director|head|senior|principal|group|general)\b')
```

Also update `_TIER2` and `_TIER4` lists to match your profession's title ladder.
Run `python3 scripts/classify_title.py` (no args) to run the built-in verification suite after changes.

---

## 8. Markets Reference

| Market | Code | Visa Type | Salary Gate | Key Cities | geoId | Adzuna |
|--------|------|-----------|-------------|-----------|-------|--------|
| UK | uk | Skilled Worker Visa | Configure in common.py | London, Manchester, Birmingham | 101165590 | Supported |
| Netherlands | nl | Kennismigrant | Configure in common.py | Amsterdam, Rotterdam, Utrecht | 102890719 | Supported |
| Germany | de | EU Blue Card | Configure in common.py | Berlin, Munich, Frankfurt, Hamburg | 101282230 | Supported |
| Denmark | dk | Pay Limit Scheme | Configure in common.py | Copenhagen, Aarhus | 104514075 | Not supported (Apify only) |
| Ireland | ie | Critical Skills Employment Permit | Configure in common.py | Dublin, Cork, Galway | 104738515 | Not supported (Apify only) |
| Sweden | se | Arbetstillstånd | Configure in common.py | Stockholm, Gothenburg, Malmö | 105117694 | Not supported |
| UAE | ae | UAE Employment Visa | Configure in common.py | Dubai, Abu Dhabi, Sharjah | 104305776 | Not supported (Apify only) |

Note: This public version uses Apify only — Adzuna is excluded. The `--source adzuna` flag is not available.

---

## 9. Google Sheets Column Reference

Key user-editable columns (all others are read-only — set by the pipeline):

| Column | Field | Editable | Notes |
|--------|-------|----------|-------|
| H | status | Yes | Change to "Approved" to trigger prep. Valid values in CLAUDE.md §6. |
| K | career_page_url | Yes | ATS URL — must be filled BEFORE setting status to Approved |
| AI | notes | Yes | Free-text notes visible to Claude during prep |

Column schema is created automatically by `sheets_sync.py push` on first run.
You do not need to manually create column headers — the script handles all sheet setup.

---

## 10. Salary Thresholds

Set in `scripts/common.py`:

```python
SALARY_THRESHOLDS = {
    "uk": 80000,    # GBP
    "nl": 90000,    # EUR
    "de": 90000,    # EUR
    "dk": 700000,   # DKK
    "ie": 90000,    # EUR
    "se": 800000,   # SEK
    "ae": 360000,   # AED
}

SALARY_THRESHOLDS_REMOTE = {k: int(v * 0.8) for k, v in SALARY_THRESHOLDS.items()}
```

`SALARY_THRESHOLDS_REMOTE` (80% of market threshold) applies to remote-only and contract roles.

Day-rate annualisation: `day_rate × 220 = annual_equivalent`
The factor 220 is `DAY_RATE_ANNUAL_FACTOR` in common.py.

---

## 11. Fit Scoring Thresholds

| Score Range | Action |
|-------------|--------|
| ≥ 75 AND visa not rejected | Auto-shortlist |
| 60–74 | Flag for human review (Review Needed) |
| < 60 OR visa rejected | Auto-reject |

Thresholds are set in `score_jobs.py`:
```python
SHORTLIST_THRESHOLD = 75
REVIEW_THRESHOLD    = 60
```

Adjust these if you want a broader or narrower review funnel.
Point allocations per dimension are in `docs/fit-scoring-rubric.md`.
