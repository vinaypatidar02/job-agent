# Configuration Checklist
# Complete every step before your first scout run.
# Cross off each box as you finish it.

---

## [ ] Step 0: READ THIS FIRST

This tool was converted from a personal project. Despite thorough generalisation,
you may find residual references to analytics roles or prior preferences.

- If you encounter anything personalised: edit it to match your situation.
- Validate before going live:
    1. python3 scripts/check_workflow.py
    2. python3 scripts/run_scout.py --dry-run
    3. Review the first scout result manually before applying to any job.

---

## [ ] Step 1: Fill .env

Copy `.env.example` to `.env` and fill every value:

```
cp .env.example .env
```

| Variable | Where to get it |
|----------|----------------|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys → Create key |
| `APIFY_TOKEN` | console.apify.com → Settings → Integrations → API token |
| `APIFY_LINKEDIN_ACTOR` | Keep as-is: `bebity/linkedin-jobs-scraper` |
| `YAHOO_EMAIL` | Your Yahoo email address (used for IMAP email tracking) |
| `YAHOO_APP_PASSWORD` | security.yahoo.com → Security → App passwords → Generate |
| `GOOGLE_SHEET_ID` | From your Sheet URL: `docs.google.com/spreadsheets/d/[COPY_THIS_PART]/edit` |
| `GITHUB_TOKEN` | github.com/settings/tokens → Generate new token → repo scope only |
| `GITHUB_REPO` | `YOUR_USERNAME/YOUR_REPO_NAME` — optional, for CI monitoring |

Notes:
- YAHOO_APP_PASSWORD requires 2-factor authentication enabled on your Yahoo account first.
- If you use Gmail instead of Yahoo: update `IMAP_HOST` in `scripts/gmail_backfill.py`
  to `imap.gmail.com` and set `YAHOO_EMAIL` / `YAHOO_APP_PASSWORD` to your Gmail address
  and a Gmail app password.
- Never commit `.env` — it is already in `.gitignore`.

---

## [ ] Step 2: Fill data/content/candidate_profile.json

This is the single configuration file the entire pipeline reads. Fill every field.

```
cp data/content/candidate_profile.json.example data/content/candidate_profile.json
```

Then open it and fill in:

### contact
- `name` — your full name (appears in resume header and cover letter)
- `email` — your professional email
- `phone` — your phone number
- `linkedin` — your LinkedIn profile URL (e.g. `linkedin.com/in/your-handle`)
- `github` — your GitHub profile URL (optional)
- `address` — your current city and country (e.g. `London, UK`)

### visa_addresses
Per-market address suffix shown in the resume header. Remove markets you are not targeting.
Format: `"uk": "Country | Seeking Skilled Worker Visa Sponsorship"`

### has_right_to_work
- `markets` — list of market codes where you already have work authorisation.
  Example: `["uk", "ie"]` means UK and Ireland skip all visa scoring.
  Leave as `[]` if you need sponsorship in every market.

### education
Array of degrees, most recent first.
- `degree`, `institution`, `dates`, `gpa` (omit `gpa` if not listing)

### certifications
Array of strings. Most relevant first.
Example: `"AWS Certified Solutions Architect — Amazon Web Services (2024)"`

### experience
Array of roles, reverse chronological order.
- `company` — exact company name
- `location` — city
- `role` — your job title
- `dates` — e.g. `"2023-07-present"` or `"2021-07-2023-07"`
- `bank_key` — MUST match the `## [Company Name]` heading in `experience_bank.md` exactly
- `pinned` — `true` if this role always appears regardless of domain
- `max_bullets` — maximum bullets to include from this role (e.g. `5`)
- `focus_areas` — keywords describing what you did (used for bullet selection)

### core_skills
- `skills` — ordered list of your top technical skills. These always appear in the Skills section.

### domains
Define 2–3 domains relevant to your profession. Each domain has:
- `label` — human-readable label (e.g. `"Product Engineering"`)
- `keywords` — JD keywords that indicate this domain (e.g. `["backend", "api", "microservices"]`)

The pipeline detects which domain a JD belongs to by matching these keywords.

### headline_by_domain
Your resume headline and subtitle per domain. Two variants per domain:
- `default` — standard IC/specialist version
- `leadership` — managerial/lead version (used when JD signals team leadership)

### resume_tags
- `tags` — list of tags you will use to label bullets in `experience_bank.md`.
  Example: `["product", "backend", "infrastructure", "leadership"]`

### profile (sub-fields)
- `years_of_experience` — integer (e.g. `8`)
- `target_roles` — list of exact target job titles you are pursuing
- `target_seniority` — description (e.g. `"Lead/Manager — 5-10 years experience expected"`)
- `required_portfolio_tools.tools` — tools that must appear in Skills section (V1 check). Leave `[]` to skip.
- `excluded_tools.tools` — tools you cannot defend in interviews. Blocked from Skills/Summary. Leave `[]` to skip.
- `canonical_metrics.metrics` — exact metric strings that must appear verbatim (V7 check). Leave `[]` to skip.
- `industry_whitelist.industries` — industries you can honestly claim. Leave `[]` to allow all.
- `verbatim_sentences.sentences` — sentences always appended to every Profile Summary (S4, S5, etc.).
- `verbatim_sentences.investment_sentence` — appended only when JD is finance/investment domain. Leave `""` to skip.
- `industry_history.industries` — 2–3 industries you have worked in (used in S1 framing).
- `platform_notes.notes` — per-employer data platform rules. Format: `{"Company A": "AWS (Redshift)"}`. Prevents credibility-risk mix-ups.
- `framing_rules.rules` — special framing instructions per employer or period. Applied in cover letter generation.

---

## [ ] Step 3: Write data/content/experience_bank.md

This is the ONLY source of resume bullet content. The pipeline cannot invent bullets.

### Format

```markdown
## Company Name
Role Title | Start Date – End Date

• [tag] Action verb + context + specific outcome with metric.
• [tag] Action verb + context + specific outcome with metric.
• [tag] Action verb + context — broader contribution or methodology note.
```

### Rules

- `## Company Name` MUST match `bank_key` in `candidate_profile.json experience[]` exactly.
- Tags must match entries in `resume_tags`. Use `[tag]` format: `[product]`, `[leadership]`, `[backend]`.
- Bullets follow: Action verb + context + metric. Example: "Reduced deployment time by 40% by introducing automated CI/CD pipelines across 3 teams."
- Only include metrics you can verify and defend in an interview. Never fabricate.
- `max_bullets` in candidate_profile.json controls how many bullets auto_prep.py selects per role.
- Order bullets within a role: highest-impact first.
- Include all bullets you ever want to appear — auto_prep.py selects the best subset per JD.

### Worked example (replace with your own)

```markdown
## Acme Corp
Senior Software Engineer | 2022-03 – 2024-06

• [backend] Redesigned the order processing service to handle 3x traffic, reducing p99 latency from 800ms to 120ms.
• [leadership] Mentored 4 junior engineers over 18 months; 3 were promoted to mid-level.
• [infrastructure] Migrated 12 microservices from on-prem to AWS ECS, cutting infrastructure cost by 35%.
• [product] Shipped the self-serve billing portal (React + Stripe), reducing support tickets by 22%.
```

---

## [ ] Step 4: Write data/content/cover_letter_bank.md

Optional but recommended. Provides style anchors and domain-specific opening hooks
that the cover letter generator uses as reference.

Leave this file empty if you prefer Claude to generate everything from the JD and your
experience_bank.md. The pipeline will not fail if the file is empty.

When you do fill it:
- Section 1: Strong Para 2 narrative examples (style reference only — not copied verbatim)
- Section 2: Secondary theme examples for Para 3 (leadership, breadth, methodology)
- Section 3: Domain-matched Para 1 openers (one per domain you defined in candidate_profile.json)

---

## [ ] Step 5: Configure LinkedIn search URLs

Open `scripts/run_scout.py` and fill in `SEARCHES_APIFY`:

```python
SEARCHES_APIFY = [
    ("Your Role Title 1",
     "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=YOUR+LOCATION&geoId=YOUR_GEO_ID&f_TPR=r86400&f_JT=F&f_E=4%2C5",
     100),
    # Add more searches — each costs at most $0.10 (100 jobs × $0.001)
]
```

How to build your URL:
1. Go to linkedin.com/jobs and search for your target role + location.
2. Apply filters: Date Posted = Past 24h, Experience Level = Senior/Manager.
3. Copy the full URL from your browser address bar.
4. Paste it as the second element of the tuple.

Key URL parameters:
- `f_TPR=r86400` — Past 24 hours (86400 seconds)
- `f_E=4%2C5` — Mid-Senior (4) and Director (5) experience levels
- `f_JT=F` — Full-time only (remove to include contract)
- `geoId=101165590` — United Kingdom (see CONFIGURATION.md for all market geoIds)

Repeat for each market you are targeting, using the per-market `SEARCHES_APIFY_NL`,
`SEARCHES_APIFY_DE`, etc. dicts already in the file.

---

## [ ] Step 6: Configure your scoring rubric

Open `docs/fit-scoring-rubric.md` and fill in every `[YOUR_...]` placeholder:

- `[YOUR_TIER1_TITLES]` — your most senior target job titles (20 points)
- `[YOUR_TIER2_TITLES]` — strong senior-adjacent titles (15 points)
- `[YOUR_PRIMARY_DOMAIN]` — industry/company types where you do your best work (25 points)
- `[YOUR_SKILLS]` — your top technical skills for the skills match dimension (25 points)
- `[YOUR_TARGET_SENIORITY]` — the seniority level you are targeting (15 points)
- `[YOUR_TIER1_CITIES]` — primary target cities (10 points)
- `[YOUR_SALARY_THRESHOLD]` — minimum annual salary you will accept

Also update CLAUDE.md §3 with your target roles and salary threshold.

---

## [ ] Step 7: Configure target roles and preferences in CLAUDE.md

Open `CLAUDE.md` and update §3 (JOB SEARCH PREFERENCES):

- List your target job titles in priority order (most senior first)
- Set your salary threshold and the currency for each market
- Set your preferred city tiers per market
- Configure your industry preferences (strongly preferred / acceptable / avoid)

---

## [ ] Step 8: Configure score_jobs.py filters

Open `scripts/score_jobs.py` and fill in the USER CONFIGURATION block at the top:

| Config | What to fill |
|--------|-------------|
| `TITLE_REJECT_CONTAINS` | Patterns for job titles you never want. Example: `["junior", "intern", "graduate"]` |
| `TARGET_TITLE_KEYWORDS` | Keywords that qualify a stale posting as worth tracking. Example: `{"engineer", "developer"}` |
| `TOOLING_PRIMARY_TITLE_BLOCKLIST` | Titles whose primary tool is irrelevant to you. Example: `["cobol developer"]` |
| `COMPANY_TYPE_BLOCKLIST` | Company name substrings to fast-reject. Example: `{"mckinsey", "bain"}` |
| `MARKET_BRAND_ALLOWLIST` | Per-market brand allowlist. Leave `{}` unless a market needs restricting. |
| `REJECT_REMOTE_ONLY_FLAG` | `True` to reject remote-only roles. Default: `False`. |
| `REJECT_CONTRACT_ROLES` | `True` to reject contract roles. Default: `False`. |
| `REJECT_PART_TIME` | `True` to reject part-time roles. Default: `True`. |

---

## [ ] Step 9: Update classify_title.py (only if your profession is NOT analytics/data)

If you are NOT targeting analytics or data roles, update `scripts/classify_title.py`:

Open the USER CONFIGURATION block at the top of the file.
Update `_HAS_ANALYTICS` (the domain keyword pattern) and `_TIER2` / `_TIER4` lists.

Examples are provided in the file for: Software Engineering, Finance/FP&A, Product Management.

If you are targeting analytics/data roles, leave this file unchanged.

---

## [ ] Step 10: Set up Google Sheets

Follow the step-by-step guide in `templates/google_sheets_setup.md`.

Summary:
1. Create a new blank Google Spreadsheet.
2. Copy the spreadsheet ID from the URL into `GOOGLE_SHEET_ID` in `.env`.
3. Create a Google Cloud service account and download the JSON key.
4. Rename the downloaded file to `data/google_service_account.json`.
5. Share the spreadsheet with the service account's email address (Editor access).
6. Run `python3 scripts/sheets_sync.py push` — this creates all column headers automatically.

Note: You do NOT need to manually create column headers. The first `push` sets up the
entire sheet schema (43 columns across Applications and Archive tabs).

---

## [ ] Step 11: Run the integrity check

```bash
python3 scripts/check_workflow.py
```

All checks must pass before your first scout run. Fix any failures before continuing.
Common failures and fixes are listed in SETUP.md Appendix.

---

## [ ] Step 12: First dry run

```bash
python3 scripts/run_scout.py --dry-run
```

Expected output: your search list and cost estimate. No API calls are made.
Verify the search titles, URLs, and job counts look correct.

When you are ready to run for real:

```bash
python3 scripts/run_scout.py --market uk --yes
```

Then review the results in your Google Sheet before approving any job for prep.
