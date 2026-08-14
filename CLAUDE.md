# CLAUDE.md — Job Application Automation Pipeline
# ⚠️ CONVERSION NOTICE — Read This First
# ════════════════════════════════════════════════════════════════
# This project was converted from a personal job search pipeline
# into a general-purpose open-source tool. Despite thorough
# generalisation, you may encounter residual analytics-specific
# phrasing or prior preferences.
#
# BEFORE GOING LIVE:
#   1. Complete every step in CONFIGURE_CHECKLIST.md
#   2. Run: python3 scripts/check_workflow.py
#   3. Dry run: python3 scripts/run_scout.py --dry-run
#   4. Review the first scout result manually before applying to any job
# ════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────
# 1. PROJECT IDENTITY
# ─────────────────────────────────────────────────────────────

[CONTEXT] This project automates your international job search using AI.
  It scrapes LinkedIn via Apify, scores jobs via Claude, generates tailored
  resumes and cover letters, tracks applications, and monitors email replies.

[CONTEXT] State is stored locally with Google Sheets as a human-readable sync layer.
  data/job_tracker.json         ← agent source of truth (fast, offline, atomic)
  Google Sheet (GOOGLE_SHEET_ID) ← human-readable mirror for viewing and editing
  outputs/applications/ready/   ← Prep Complete (awaiting submission)
  outputs/applications/done/    ← Applied, Withdrawn, Rejected, etc.

[CONTEXT] Sync workflow:
  After scrape/score: python3 scripts/sheets_sync.py push --tabs apps,archive
  Before app prep:    python3 scripts/sheets_sync.py pull --tabs apps,archive
  User editable columns in Sheet: status, career_page_url, notes
  All other columns are read-only — set by the workflow

[CONTEXT] Tab selection (--tabs flag):
    --tabs apps,archive      : Applications + Archive (scout, app prep, email tracker)
    --tabs apps,outreach     : Applications + Outreach (referral logging)
    --tabs apps,archive,outreach : All meaningful tabs
    (no --tabs flag)         : All tabs — full daily sync, first-time setup only
  Sheet tabs:
    Applications — active entries (Shortlisted, Review Needed, Approved, Prep Complete,
                   Applied, Under Review, Interview Scheduled, Assessment, Offer Received, Withdrawn)
    Archive      — inactive entries (Rejected, Auto-Rejected, Withdrawn, Stale)
  RE-ACTIVATION: change a Stale entry's status in Archive to "Shortlisted" or "Review Needed",
  then run pull → restores to active in job_tracker.json.

[CONTEXT] Email check — uses IMAP (Yahoo by default) via scripts/gmail_backfill.py.
  Configure IMAP_HOST in gmail_backfill.py USER CONFIG section (Yahoo/Gmail/Outlook).

  Translate user prompt → script arg, then run:
    "check email"                → python3 scripts/gmail_backfill.py --days 2
    "check email last N days"    → python3 scripts/gmail_backfill.py --days N
    "check email backfill"       → python3 scripts/gmail_backfill.py --days 35
    "retry unmatched emails"     → python3 scripts/gmail_backfill.py --retry-unmatched

[CONTEXT] Apify cache: scripts/apify_cache.py, 24h TTL, data/apify_cache/ (free re-run same day).
  CLI: python3 scripts/apify_cache.py status|clear

[RULE] EDIT ORDER IN GOOGLE SHEET — must be followed to avoid incomplete prep:
  Step 1: Paste the ATS career page URL into career_page_url column (Col K)
  Step 2: THEN change status to "Approved" (Col H)
  Step 3: THEN run: python3 scripts/sheets_sync.py pull --tabs apps,archive
  Reason: application_prep agent requires career_page_url before it will act.

[RULE] DUPLICATION PREVENTION in application_prep:
  Agent only processes entries where ALL THREE conditions are true:
    status = "Approved"
    career_page_url is not null
    resume_path is null (prep not already done)
  Running pull multiple times is safe — agent skips already-prepped jobs.


# ─────────────────────────────────────────────────────────────
# 2. CANDIDATE PROFILE
# ─────────────────────────────────────────────────────────────
@docs/candidate-profile.md


# ─────────────────────────────────────────────────────────────
# 3. JOB SEARCH PREFERENCES
# ─────────────────────────────────────────────────────────────

[CONTEXT] Target roles — configure in docs/candidate-profile.md:
  List your target titles in priority order (most senior first).
  The scoring rubric in Section 4 maps title patterns to point values.
  Examples by profession:
    Analytics: Analytics Manager, Lead Data Analyst, Head of Analytics
    Software:  Staff Engineer, Engineering Manager, Principal Engineer
    Finance:   Head of FP&A, Finance Director, VP Finance

[RULE] Salary threshold — configure in CLAUDE.md §3 and score_jobs.py USER CONFIG:
  Set YOUR_SALARY_THRESHOLD to the minimum annual salary you will accept.
  Salary gate rules:
    - Upper end > threshold → SHORTLIST (even if lower end is below)
    - Both ends < threshold → DO NOT shortlist
    - Not stated → Claude estimates; salary_gate = "tbc" — never auto-reject on estimate

[RULE] Remote-only and contract roles are accepted at 80% of the salary gate.
  is_remote_only and is_contract are informational flags — not hard blockers.
  Configure SALARY_THRESHOLDS_REMOTE in scripts/common.py.

[CONTEXT] Target locations — configure per market:
  Define your preferred cities by tier (Tier 1 = primary hub, etc.).
  Location scoring (0–10) is defined in docs/fit-scoring-rubric.md.
  Configure city tier lists at the top of scripts/score_jobs.py (CITY_TIERS dict).

[CONTEXT] Supported markets:
  UK  (--market uk):  United Kingdom — Skilled Worker Visa sponsorship required
  NL  (--market nl):  Netherlands — Kennismigrant / Highly Skilled Migrant permit
  DE  (--market de):  Germany — EU Blue Card (Blaue Karte EU)
  DK  (--market dk):  Denmark — Pay Limit Scheme (Beløbsordningen)
  IE  (--market ie):  Ireland — Critical Skills Employment Permit (CSEP)
  SE  (--market se):  Sweden — Arbetstillstånd via Migrationsverket
  AE  (--market ae):  UAE — Employment Visa / Work Permit (employer-sponsored)

  Usage: python3 scripts/run_scout.py --market uk|nl|se|de|dk|ie|ae|intl|all
  Verify current default market in run_scout.py before running (check the script).

[CONTEXT] has_right_to_work — configure in data/content/candidate_profile.json:
  If you already have work authorisation in a market, add its code to has_right_to_work.markets.
  Example: {"markets": ["uk", "ie"]} means UK + IE skip all visa checks.
  Markets not in this list require sponsorship assessment from JD text.

[CONTEXT] Industry preference — configure in CLAUDE.md §3:
  STRONGLY PREFERRED: [YOUR_PRIMARY_INDUSTRIES] — product-led companies
  ACCEPTABLE: Non-product companies only at exceptional fit score (≥ 88)
  AVOID: Pure staffing agencies, body-shopping roles

[RULE] Visa sponsorship: check JD text for explicit sponsorship statements.
  If unknown, flag as "Sponsorship Unconfirmed" rather than rejecting.
  (Markets in has_right_to_work skip this check — visa_score auto-set to 5.)

[DEFAULT] When in doubt on fit, flag for human review rather than auto-reject.


# ─────────────────────────────────────────────────────────────
# 4. FIT SCORING RUBRIC
# ─────────────────────────────────────────────────────────────
@docs/fit-scoring-rubric.md


# ─────────────────────────────────────────────────────────────
# 5. RESUME & COVER LETTER RULES
# ─────────────────────────────────────────────────────────────

[RULE] Never fabricate experience, metrics, or skills.
       Only restructure, reorder, and rephrase what exists
       in data/content/experience_bank.md — the single source of truth.

[RULE] Do not change any numbers or metrics from experience_bank.md.
       These are real figures from real outcomes.

[DEFAULT] Experience bank: data/content/experience_bank.md — all resume bullets.
  Domain detection and bullet selection handled by auto_prep.py based on JD analysis.
  Tag bullets with [tag] labels matching the resume_tags in candidate_profile.json.

[DEFAULT] Resume format: scripts/pdf_renderer.py (reportlab, single-column, A4).
  Full layout spec (fonts, colours, pixel measurements) in scripts/CLAUDE.md.
  File naming: [YOUR_NAME]_CV.pdf

[DEFAULT] Resume length: Maximum 2 pages.

[DEFAULT] Bullet point style: Action verb + context + metric.
          Example: "Led experimentation programme across 3 product
          verticals, improving conversion by 18%."

[DEFAULT] Cover letter format:
  Header:    Same two-column layout as resume (name + title left, contact right)
  Opening:   City + date (e.g. "London, 2026-06-17"); then "[Company] Hiring Team"
  Salutation: "Dear Hiring Team,"
  Structure: 4 paragraphs:
    Para 1: Role excitement + why this company specifically + alignment summary
    Para 2: Most relevant experience mapped to JD (specific, with metrics)
    Para 3: Broader strategic value — additional experiences that reinforce fit
    Para 4: Forward-looking — company mission + call to action (+ visa sentence for intl markets)
  Closing:   "Kind regards," + Name + Phone + Email
  Tone:      Confident, specific, warm — not generic, not stiff
  Length:    350–450 words

[RULE] Cover letter must name the company and role title in paragraph 1.
       No generic openers like "I am writing to apply for..."

[RULE] Cover letter: PDF only. File: [YOUR_NAME]_CoverLetter.pdf.
       Same reportlab styling as resume.

[CONTEXT] Cover letter market adjustments:
  Date line uses the JOB's own city in ALL markets.
  Anchor city is the fallback ONLY when the location field is empty.
  NL: Para 4 adds kennismigrant relocation sentence.
  SE: Para 4 adds arbetstillstånd relocation sentence.
  DE: Para 4 adds EU Blue Card relocation sentence.
  DK: Para 4 adds Pay Limit Scheme sentence (NEVER EU Blue Card — Denmark opted out).
  IE: Para 4 adds Critical Skills Employment Permit sentence.
  AE: Para 4 adds UAE Employment Visa sentence.

[RULE] All generated resume and cover letter text must use British English spellings.
  American spellings (optimization, modeling, behavioral, prioritize, analyze, organize,
  utilize, visualize) must never appear in final PDFs.


# ─────────────────────────────────────────────────────────────
# 6. APPLICATION TRACKING
# ─────────────────────────────────────────────────────────────

[CONTEXT] Tracker file: data/job_tracker.json
          This is the single source of truth for all applications.

[CONTEXT] Valid status values and what triggers each:
  "Shortlisted"          → Job scored ≥ 75, awaiting human approval
  "Review Needed"        → Job scored 60–74, flagged for human review
  "Auto-Rejected"        → Rejected by scoring rules. Terminal — goes to Archive on push.
  "Stale"                → Job posted > stale window when scored; tracked but not scored
  "Approved"             → Human approved AND career_page_url filled. BOTH required.
  "Prep Complete"        → Resume + cover letter generated and saved
  "Referral-Planned"     → Contacts identified; outreach message drafted but not sent
  "Connection-Requested" → LinkedIn connection note sent; waiting for acceptance
  "Reached-Out"          → Referral request (or recruiter outreach) sent
  "Followup"             → Auto-set by referral_tracker.py on day 4 (3+ days since Reached-Out)
  "Referred"             → Contact referred the application; application submitted
  "Stale-Referral"       → Auto-set by referral_tracker.py on day 8 — no response received
  "Applied"              → Application submitted, confirmation received
  "Under Review"         → Recruiter/ATS confirmed active review
  "Interview Scheduled"  → Interview invite received
  "Assessment"           → Take-home task or online test received
  "Offer Received"       → Offer email received
  "Rejected"             → Rejection email received OR manually set
  "Withdrawn"            → Candidate chose to withdraw (always manually set)
  "Duplicate"            → Manually set for re-posts/near-duplicates

[RULE] "Rejected" and "Withdrawn" are terminal — automation never overwrites them once set.

[RULE] DUPLICATE PREVENTION — Check ALL signals before adding:
    1. (job_id, market) exact match — HIGHEST priority
    2. jd_url exact match
    3. Fuzzy match: same company + role title (within edit distance 2)
    4. Same recruiter + role title word overlap ≥ 2 words

[RULE] Never delete an entry from job_tracker.json.
       Only update status and append to status_history[].

[CONTEXT] Output folder convention:
  outputs/applications/ready/[Company]_[RoleShortName]_[YYYYMMDD]/
  outputs/applications/referral/[Company]_[RoleShortName]_[YYYYMMDD]/
  outputs/applications/done/[Company]_[RoleShortName]_[YYYYMMDD]/
  Each folder contains:
    ├── [YOUR_NAME]_CV.pdf
    ├── [YOUR_NAME]_CoverLetter.pdf
    └── meta.json


# ─────────────────────────────────────────────────────────────
# 7. EMAIL STATUS MAPPING
# ─────────────────────────────────────────────────────────────

[CONTEXT] Email classification uses Claude API. Reference patterns:

  KEYWORDS                              → STATUS UPDATE
  ─────────────────────────────────────────────────────
  "application received" /
  "thank you for applying"              → "Applied"
  "under review" / "shortlisted"        → "Under Review"
  "invite you to interview"             → "Interview Scheduled"
  "online assessment" / "take-home"     → "Assessment"
  "pleased to offer" / "formal offer"   → "Offer Received"
  "unfortunately" / "not moving forward" → "Rejected"

[RULE] Match email using BOTH: (1) company (sender domain / name in body) AND
       (2) role keywords. Both must align for a confident match.

[RULE] If no match found, log to data/unmatched_emails.json for manual review.

[RULE] Always append to status_history[], never overwrite it.


# ─────────────────────────────────────────────────────────────
# 8. PROJECT FILE MAP
# ─────────────────────────────────────────────────────────────
@docs/project-file-map.md


# ─────────────────────────────────────────────────────────────
# 10. GLOBAL BEHAVIOURAL RULES
# ─────────────────────────────────────────────────────────────

[RULE] Always read CLAUDE.md before starting any task in this project.

[RULE] SCRIPT DEFAULTS — never assume defaults from CLAUDE.md or memory. Before running any
       script with user-configurable behaviour (run_scout.py, sheets_sync.py, etc.), read the
       script to find current defaults. Confirm with user before proceeding.

[RULE] Always read the relevant skill file before executing a skill.

[RULE] OUTREACH DRAFTING TRIGGER — when the user provides a contact table in the standard
  format, ALWAYS read BOTH of these files before drafting:
    skills/draft_referral_message.md
    skills/draft_referral_learnings.md
  The contact table IS the trigger. No exceptions.

[RULE] Never modify data/content/experience_bank.md bullets mid-session without user confirmation.
       experience_bank.md is the single source of truth — changes affect all future applications.

[RULE] Never modify a completed application folder's resume.pdf.
       If re-tailoring is needed, create a new dated folder.

[RULE] When writing to job_tracker.json, read the current file first,
       merge the update, then write back. Never overwrite blindly.

[RULE] PIPELINE ANALYSIS — always read BOTH files:
         data/job_tracker.json   — active + terminal pipeline entries
         data/auto_rejected.json — jobs rejected before tracker entry
       Total = tracker entries + auto_rejected entries. Reading only tracker gives WRONG totals.

[RULE] Log all actions to the terminal — transparency over brevity.

[RULE] SCORED JOBS MUST BE WRITTEN BEFORE RE-SCORING:
       score_jobs.py overwrites scored_jobs.json on every run. Mandatory sequence:
         score_jobs.py → write_tracker.py → (only then: score_jobs.py again if needed)

[RULE] CACHING AND BATCHING ARE NON-NEGOTIABLE DEFAULTS:
  Apify cache (24h TTL):       run_scout.py always checks apify_cache before calling Apify.
                                Never call apify_cache.py clear before a scout run.
  Anthropic batching:          score_jobs.py runs batch mode by default (BATCH_MODE=True).
                                Never pass --no-batch. Batch costs 50% of real-time.
  Anthropic prompt caching:    cache_control: ephemeral on all system prompts.
                                ~90% input token saving on repeated market runs.
  All three must be active on every scout run. Do not suggest workarounds.

[RULE] If uncertain (borderline fit score, ambiguous visa), ask for human input rather than assuming.

[RULE] After any enhancement to scripts, agents, skills, hooks, or CLAUDE.md:
       run python3 scripts/check_workflow.py. Fix failures before done.

[CONTEXT] Sponsor check: Assessed ONLY from JD text via visa_sponsorship_status in Pass 2:
    "Rejected"     → JD explicitly denies sponsorship → auto-reject (-10 score)
    "Confirmed"    → JD explicitly confirms sponsorship → +5 score
    "Unconfirmed"  → JD silent on sponsorship → 0 pts, human reviews
  Exception: markets in has_right_to_work skip this check entirely.

[RULE] German language gate (ALL markets): auto-reject in Pass 1 if JD contains explicit
  German language requirement phrases — regardless of market.

[RULE] Non-[YOUR_DOMAIN] Business Partner title gate: configure in score_jobs.py USER CONFIG.
  Auto-reject if title contains "business partner" without a domain qualifier.
  Customize the qualifier list to your profession in TITLE_REJECT_CONTAINS.


# ─────────────────────────────────────────────────────────────
# 12. HOOKS & ORCHESTRATION (Stage 5)
# ─────────────────────────────────────────────────────────────
[CONTEXT] Hook wiring, GitHub Actions config, and full 5-step workflow guide in agents/CLAUDE.md.

[RULE] CREDENTIAL ROTATION — when any API key changes, update BOTH:
  1. Local .env file
  2. GitHub Actions secret (repo Settings → Secrets → update value)

[RULE] Always run sheets_sync.py push after any agent modifies job_tracker.json.

[RULE] NEVER run sheets_sync.py push without running pull first in the same session.
       push overwrites Sheet contents from local JSON — any unsaved Sheet edits
       (Approved status, career_page_url) will be lost if pull hasn't captured them first.
       Sequence: pull → (verify) → push. No exceptions.

[RULE] Always run sheets_sync.py pull before application prep to pick up Sheet edits.


# ─────────────────────────────────────────────────────────────
# 13. CONTRACT & REMOTE ROLES — EOR STRATEGY
# ─────────────────────────────────────────────────────────────

[CONTEXT] Every scout run captures BOTH permanent/hybrid AND remote/contract roles.
  No filtering at any stage — Gates 8/9 in score_jobs.py are enrichment signals, not hard rejects.

[CONTEXT] role_type — 4-value internal field:
  "contract_remote"   → EOR framing — Deel/Remote.com; no employer visa sponsorship needed
  "contract_hybrid"   → standard visa framing + contract note; hybrid attendance required
  "permanent_remote"  → aspirational relocation framing; remote readiness primary
  "permanent_hybrid"  → default (permanent + hybrid office attendance)

[CONTEXT] eor_viability — integer 1–10 (null for permanent non-remote roles):
  8–10: async-friendly, startup/scale-up, senior IC scope, no mandatory onsite
  5–7:  hybrid, mid-size, some office expectation
  1–4:  mandatory onsite, regulated entity, "no contractors" language

[RULE] Contract/EOR visa scoring: if is_contract=true → visa_sponsorship_status="EOR", visa_score=5.
  Exception: if JD explicitly blocks overseas contractors → visa_sponsorship_status="Rejected".

[RULE] Remote location scoring: if is_remote_only=true → location_score=10 for ALL locations.

[RULE] Day-rate salary annualisation: day_rate × 220 = annual equivalent.
  Gate compared against SALARY_THRESHOLDS_REMOTE (80% of market threshold).

[CONTEXT] EOR pitch skill: "draft EOR pitch [job_id]" (only for role_type=contract_remote roles).
  File: skills/draft_eor_pitch.md.


# ─────────────────────────────────────────────────────────────
# 11. MCP SERVER CONFIGURATION — see scripts/CLAUDE.md
# ─────────────────────────────────────────────────────────────
[CONTEXT] Apify actor: bebity/linkedin-jobs-scraper ($0.001/job, 24h cache in data/apify_cache/).
  Email: Yahoo IMAP via gmail_backfill.py (configure YAHOO_EMAIL + YAHOO_APP_PASSWORD in .env).
  Full MCP config details in scripts/CLAUDE.md.
