# Setup Guide

This guide walks through the complete setup from zero to first scout run.
Complete each stage in order before moving to the next.

## Prerequisites

Before starting, verify you have:

| Requirement | Check | Notes |
|-------------|-------|-------|
| Python 3.10+ | `python3 --version` | Scripts use match statements and `X \| Y` union syntax |
| Node.js 16+ | `node --version` | Required for Claude Code MCP servers (Apify) |
| Claude Code Pro | subscribe at claude.ai/code | $20/month — required for interactive pipeline orchestration |
| Apify account | apify.com | Free tier includes $5/month credit — covers ~6 intl runs |
| Google Cloud account | console.cloud.google.com | Free tier sufficient for Sheets API service account |
| Email account | Yahoo / Gmail / Outlook | For IMAP email tracking — free |

---

## Stage 1: Clone and Install

```bash
git clone https://github.com/YOUR_USERNAME/Claude-Workflow-Automation-public.git
cd Claude-Workflow-Automation-public

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt
```

Expected output: all packages install without error. If you see a `pip` version warning, run
`pip install --upgrade pip` first.

---

## Stage 2: Create .env File

```bash
cp .env.example .env
```

Open `.env` and fill in each variable. Full instructions are in `.env.example` for each one.
Summary of what you need and where to get it:

| Variable | Where to get it |
|----------|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys → Create key |
| `APIFY_TOKEN` | console.apify.com → Settings → Integrations → API token |
| `APIFY_LINKEDIN_ACTOR` | Keep as `bebity/linkedin-jobs-scraper` (do not change) |
| `YAHOO_EMAIL` | Your Yahoo email address (or Gmail/Outlook — see IMAP section below) |
| `YAHOO_APP_PASSWORD` | security.yahoo.com → Account Security → App passwords → Generate |
| `GOOGLE_SHEET_ID` | From your Sheet URL: `docs.google.com/spreadsheets/d/[THIS_PART]/edit` |
| `GITHUB_TOKEN` | github.com/settings/tokens → Generate new token (repo scope only) |
| `GITHUB_REPO` | Your repository in `username/repo-name` format (for CI monitoring) |

**Security:** `.env` is in `.gitignore` and will never be committed. Never share this file.

### IMAP email provider

The pipeline defaults to Yahoo IMAP. To use Gmail or Outlook instead, edit the `IMAP_HOST`
setting in `scripts/gmail_backfill.py` USER CONFIG section:

```python
# Yahoo (default):
IMAP_HOST = "imap.mail.yahoo.com"   IMAP_PORT = 993

# Gmail (requires App Password — enable at myaccount.google.com/apppasswords):
IMAP_HOST = "imap.gmail.com"        IMAP_PORT = 993

# Outlook / Hotmail:
IMAP_HOST = "outlook.office365.com" IMAP_PORT = 993
```

Yahoo is recommended as the default — app password setup is straightforward and does not
require OAuth configuration.

---

## Stage 3: Set Up Google Sheets

Follow the detailed instructions in `templates/google_sheets_setup.md`.

Summary:
1. Create a new Google Spreadsheet and copy its ID into `GOOGLE_SHEET_ID` in `.env`
2. Create a GCP service account and download its JSON key
3. Rename the JSON key to `data/google_service_account.json`
4. Share the spreadsheet with the service account email address (Editor access)

The spreadsheet tabs and all 43 column headers are created automatically on the first
`sheets_sync.py push` run — you do not need to create them manually.

---

## Stage 4: Fill candidate_profile.json

```bash
# The file is already present with placeholder values
# Open it and fill in every field marked YOUR_...
nano data/content/candidate_profile.json
```

Follow CONFIGURE_CHECKLIST.md Step 2 for a field-by-field walkthrough. Key sections:

- `contact` — your name, email, phone, LinkedIn URL
- `experience` — your work history in reverse chronological order (each entry links to experience_bank.md)
- `domains` — define 2–3 domains with detection keywords for your profession
- `profile.target_roles` — your target job titles, most senior first
- `has_right_to_work.markets` — markets where you already have work authorisation (skip visa checks)

---

## Stage 5: Write experience_bank.md

This file is the single source of truth for all resume bullet content.
The pipeline selects from it — it never invents bullets not present here.

```bash
nano data/content/experience_bank.md
```

Format:
```markdown
## Company Name
**Your Job Title** | Month YYYY – Month YYYY

- [tag1] Action verb + context + metric. Example: "Reduced inventory holding from 40 to 25 days
  by building a dynamic pricing algorithm using Python and Redshift."
- [tag2] Another bullet — action + context + outcome.
```

Rules:
- Only include metrics you can verify and defend in an interview
- Tag each bullet with `[tag]` labels matching `resume_tags` in candidate_profile.json
- The `## Company Name` heading must exactly match the `bank_key` in candidate_profile.json

See CONFIGURE_CHECKLIST.md Step 3 and ANTI_HALLUCINATION.md for full guidance.

---

## Stage 6: Configure LinkedIn Search URLs

Open `scripts/run_scout.py` and find the `SEARCHES_APIFY` block near the top.
Replace the placeholder URLs with your own LinkedIn job search URLs.

How to build a search URL:
1. Go to linkedin.com/jobs and search for your target role in your target location
2. Apply filters: Experience Level (Senior / Manager), Date Posted (Past 24 hours)
3. Copy the full URL from your browser address bar
4. Paste it into the `SEARCHES_APIFY` list

```python
SEARCHES_APIFY = [
    ("Your Role Title 1",
     "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=YOUR+CITY&geoId=YOUR_GEO_ID&f_TPR=r86400&f_E=4%2C5",
     100),   # max 100 jobs = max $0.10 per run
]
```

GeoId reference (common markets):
- UK: `101165590` | NL: `102890719` | DE: `101282230`
- SE: `105117694` | DK: `104514075` | IE: `104738515` | UAE: `104305776`

See CONFIGURATION.md for the full LinkedIn URL parameter reference.

---

## Stage 7: Configure Scoring Rubric

Two files define how jobs are scored:

**CLAUDE.md §3** — target roles, salary threshold, preferred locations per market.
Edit the placeholder values (`[YOUR_TARGET_ROLE_N]`, `[YOUR_SALARY_THRESHOLD]`, city tiers).

**docs/fit-scoring-rubric.md** — title tier mapping, domain scoring, skills matching.
Replace `[YOUR_TIER1_TITLE_N]`, `[YOUR_PRIMARY_DOMAIN]`, `[YOUR_SKILL_N]` with your
actual target titles, industries, and technical skills.

These two files together tell Claude Pass 2 how to evaluate every job it sees.

---

## Stage 8: Configure score_jobs.py Filters

Open `scripts/score_jobs.py` and find the `USER CONFIGURATION` block at the top.
Edit the Pass 1 filter blocks to match your profession:

- `TITLE_REJECT_CONTAINS` — titles you never want (e.g. "junior", "intern", "graduate")
- `TARGET_TITLE_KEYWORDS` — minimum domain keywords for stale postings
- `TOOLING_PRIMARY_TITLE_BLOCKLIST` — title-level tool blocklist (irrelevant tool-first roles)
- `COMPANY_TYPE_BLOCKLIST` — company types to fast-reject before Claude scoring
- `MARKET_BRAND_ALLOWLIST` — per-market brand whitelists (leave `{}` unless you need one)

Leave any block as its default empty value to disable that filter.

---

## Stage 9: Install Claude Code and Configure MCP

```bash
# Install Claude Code CLI globally
npm install -g @anthropic-ai/claude-code

# Verify install
claude --version

# Sign in with your Anthropic account
claude login

# Open the project in Claude Code
cd Claude-Workflow-Automation-public
claude
```

The `mcp.json` file is already configured and reads your `APIFY_TOKEN` from `.env` automatically.
Claude Code loads the Apify MCP server on startup. Verify it is active:

In Claude Code, type `/mcp` — the Apify actor (`bebity/linkedin-jobs-scraper`) should appear.

The `on_job_approved` hook is pre-wired in `.claude/settings.json`. It triggers application
prep automatically when jobs move to Approved status. No further configuration needed.

---

## Stage 10: First Run

Run the integrity check first — all checks must pass before your first scout:

```bash
python3 scripts/check_workflow.py
```

If any check fails, fix the underlying issue before continuing (do not skip checks).

Dry run (no API calls — just shows what would be searched):

```bash
python3 scripts/run_scout.py --dry-run
```

Expected output: a list of your configured searches with job caps and cost estimates.

First real scout run:

```bash
python3 scripts/run_scout.py --market uk --yes
python3 scripts/write_tracker.py
python3 scripts/sheets_sync.py push --tabs apps,archive
```

Expected: Apify scrapes LinkedIn, jobs are scored by Claude, results appear in Google Sheets.
The first `push` creates all tabs and column headers automatically.

Review jobs in the Sheet, approve any you want to apply for (set status to Approved and paste
the ATS URL in Col K), then pull and run prep:

```bash
python3 scripts/sheets_sync.py pull --tabs apps,archive
# In Claude Code: "run application prep"
```

---

## Troubleshooting

**Apify 401 Unauthorized**
`APIFY_TOKEN` is not set or has expired. Regenerate it at console.apify.com → Settings →
Integrations → API token, then update `.env`.

**Google Sheets PermissionDenied**
The spreadsheet has not been shared with the service account email address.
Open the sheet → Share → paste the service account email → set to Editor → Done.

**IMAP AUTH failed / LOGIN failed**
The app password is wrong or 2-factor authentication is not enabled.
For Yahoo: security.yahoo.com → Account Security → enable 2FA → generate a new App Password.
For Gmail: myaccount.google.com/apppasswords → generate a new App Password.

**check_workflow FAIL: required paths missing**
Run the command from the project root directory (`Claude-Workflow-Automation-public/`), not
from a subdirectory. The script uses relative paths from the project root.

**auto_prep.py KeyError 'contact'**
`candidate_profile.json` is missing one or more required top-level keys. Check that all
required sections (`contact`, `experience`, `domains`, `core_skills`, `profile`) are present
and contain valid JSON. Run `python3 -m json.tool data/content/candidate_profile.json` to
validate the JSON syntax.

**score_jobs.py returns no jobs**
The Apify cache returned a result set with zero qualifying jobs. This can happen if your
search URL returns no results or if Pass 1 filters are too aggressive. Run
`python3 scripts/apify_cache.py clear` to force a fresh Apify call on the next run. Check
your LinkedIn search URL returns results when you open it in a browser.

**sheets_sync WORKSHEET_NOT_FOUND**
The Sheet tabs do not exist yet. Run `python3 scripts/sheets_sync.py push` (without `--tabs`)
once to create all tabs, then use `--tabs` flags for subsequent runs.
