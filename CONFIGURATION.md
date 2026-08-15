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

The setup wizard Step 1 asks for your email provider and updates `gmail_backfill.py` automatically. To change provider after setup, re-run the wizard or edit the file directly:

```python
# Edit in scripts/gmail_backfill.py:
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

## 5. LinkedIn Search Configuration

Search configuration is stored in `data/content/search_config.json` and loaded automatically by `run_scout.py`. The setup wizard Step 5 builds entries interactively — no URL editing required.

**search_config.json format:**

```json
{
  "searches": [
    {
      "label": "Head of Analytics — UK",
      "market": "uk",
      "keywords": "Head of Analytics",
      "time_window": "r86400",
      "include_contract": false,
      "max_jobs": 100
    }
  ]
}
```

**Field reference:**

| Field | Values | Description |
|-------|--------|-------------|
| `label` | string | Display name (shown in logs and dry-run output) |
| `market` | uk, nl, de, se, dk, ie, ae | Target market — determines geoId automatically |
| `keywords` | string | Job title or keyword phrase |
| `time_window` | `r86400` / `r604800` / `r2592000` | Past 24 hours / Past week / Past month |
| `include_contract` | true / false | Include contract roles in results |
| `max_jobs` | integer | Cap per URL — cost is $0.001/job |

**LinkedIn filter reliability:**

| Filter | Reliability | Notes |
|--------|------------|-------|
| Keywords | ✅ Always works | Core search parameter |
| Location / Market | ✅ Always works | Driven by geoId |
| Experience level | ✅ Reliable | Wizard always selects Mid-Senior + Director |
| Date posted | ✅ Reliable | Only 3 options: Past 24h / Past week / Past month — custom ranges not supported |
| Job type (Full-time / Contract) | ⚠️ Partially reliable | Employers sometimes miscategorise; pipeline re-detects from JD text |
| Work arrangement (Remote / Hybrid) | ⚠️ Unreliable | Labels inconsistent; pipeline re-detects from JD text instead |

**geoId values (reference — filled automatically by wizard):**

| Market | geoId |
|--------|-------|
| United Kingdom | 101165590 |
| Netherlands | 102890719 |
| Germany | 101282230 |
| Sweden | 105117694 |
| Denmark | 104514075 |
| Ireland | 104738515 |
| UAE | 104305776 |

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

**Recommended approach — via candidate_profile.json:**

Add `title_classifier` to your config (the setup wizard Step 2 does this automatically):

```json
{
  "title_classifier": {
    "domain_keywords": ["engineer", "developer", "architect", "platform"],
    "seniority_keywords": ["manager", "lead", "head", "principal", "staff"]
  }
}
```

`classify_title.py` reads this at startup and builds the regex patterns dynamically. No Python editing required.

**Manual override** (advanced — only if you need fine-grained control):

Edit patterns directly in `scripts/classify_title.py`. Note that `candidate_profile.json` takes precedence when populated.

```python
# Software Engineering example:
_HAS_ANALYTICS = re.compile(r'\b(engineer|developer|programmer|architect|devops|platform)\b')
_HAS_LEAD_MGR  = re.compile(r'\b(manager|lead|head|principal|staff|distinguished|fellow)\b')

# Finance / FP&A example:
_HAS_ANALYTICS = re.compile(r'\b(finance|financial|accounting|treasury|fp&a|risk|compliance)\b')
_HAS_LEAD_MGR  = re.compile(r'\b(manager|controller|head|director|vp|partner)\b')

# Product Management example:
_HAS_ANALYTICS = re.compile(r'\b(product|growth|platform|strategy|portfolio)\b')
_HAS_LEAD_MGR  = re.compile(r'\b(director|head|senior|principal|group|general)\b')
```

Also update `_TIER2` and `_TIER4` lists to match your profession's title ladder.
Run `python3 scripts/classify_title.py` (no args) to run the built-in verification suite after changes.

---

## 8. Markets Reference

| Market | Code | Visa Type | Salary Gate | Key Cities | geoId | Adzuna |
|--------|------|-----------|-------------|-----------|-------|--------|
| UK | uk | Skilled Worker Visa | Set in candidate_profile.json | London, Manchester, Birmingham | 101165590 | Supported |
| Netherlands | nl | Kennismigrant | Set in candidate_profile.json | Amsterdam, Rotterdam, Utrecht | 102890719 | Supported |
| Germany | de | EU Blue Card | Set in candidate_profile.json | Berlin, Munich, Frankfurt, Hamburg | 101282230 | Supported |
| Denmark | dk | Pay Limit Scheme | Set in candidate_profile.json | Copenhagen, Aarhus | 104514075 | Not supported (Apify only) |
| Ireland | ie | Critical Skills Employment Permit | Set in candidate_profile.json | Dublin, Cork, Galway | 104738515 | Not supported (Apify only) |
| Sweden | se | Arbetstillstånd | Set in candidate_profile.json | Stockholm, Gothenburg, Malmö | 105117694 | Not supported |
| UAE | ae | UAE Employment Visa | Set in candidate_profile.json | Dubai, Abu Dhabi, Sharjah | 104305776 | Not supported (Apify only) |

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

Set in `data/content/candidate_profile.json → salary_thresholds`. The setup wizard Step 4 prompts for these interactively. No Python editing required.

```json
{
  "salary_thresholds": {
    "uk": 80000,
    "nl": 90000,
    "de": 90000,
    "dk": 700000,
    "ie": 90000,
    "se": 800000,
    "ae": 360000
  }
}
```

`common.py` reads from this file at startup. If the file is missing or the key is absent, built-in defaults are used (same values as above).

Remote/contract roles are automatically screened at 80% of the market threshold (`SALARY_THRESHOLDS_REMOTE`).

Day-rate annualisation: `day_rate × 220 = annual_equivalent`
The factor 220 is `DAY_RATE_ANNUAL_FACTOR` in `scripts/common.py`.

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
