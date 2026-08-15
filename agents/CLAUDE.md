# agents/CLAUDE.md — Extended context for the agents/ directory
# Loaded automatically when Claude works with files in agents/.
# Root CLAUDE.md is always loaded first; this file extends it.

# ─────────────────────────────────────────────────────────────
# HOOKS & ORCHESTRATION — wiring details
# ─────────────────────────────────────────────────────────────

# Hook 1 — on_job_approved (PostToolUse on Write)
#   Trigger: any write to data/job_tracker.json
#   Condition: entry where status=Approved AND career_page_url
#              not null AND resume_path is null
#   Action: invoke application_prep agent (with user confirmation)
#   File: hooks/on_job_approved.md
#   Wired: .claude/settings.json → PostToolUse → Write matcher
#
# Hook 2 — on_email_received (conceptual — NOT wired as a settings.json hook)
#   Trigger: user types "check email" / "run tracker" / similar
#   Action: IMAP fetch → classify → invoke tracker agent
#          → label processed → push to Sheets
#   File: hooks/on_email_received.md
#   NOT wired: UserPromptSubmit hooks are deliberately not used (they fire on
#   every message regardless of matcher — see .claude/settings.json "_learning").
#   Natural-language triggers ("check email", "run scout") are handled by
#   Claude reading CLAUDE.md and the agent files directly.

# ─────────────────────────────────────────────────────────────
# SPONSOR REGISTER — refresh commands (optional manual audit)
# ─────────────────────────────────────────────────────────────
#   python3 scripts/sponsor_register.py refresh-uk   # UK Home Office Licensed Sponsors CSV
#   python3 scripts/sponsor_register.py refresh-nl   # NL IND Recognised Sponsors register
#   python3 scripts/sponsor_register.py status       # show file ages and record counts
#
# Sponsorship is assessed from JD text only (visa_sponsorship_status in Pass 2).
# Register files at data/sponsor_registers/ are available for manual audit only.
# Markets using candidate-driven permits (DE EU Blue Card) don't require a register.
# If you have right to work in a market: add it to has_right_to_work.markets in
# candidate_profile.json — visa checks are skipped for those markets entirely.

[CONTEXT] GitHub Actions scout — set up via .github/workflows/daily_scout.yml
  Schedule: Disabled by default — uncomment the cron line to enable.
  Trigger:  Actions tab → Run workflow (manual trigger always available)
  Markets:  Configure --market flag in the "Run scout pipeline" step
  Pipeline: git pull → sheets_sync pull → clear old caches → run_scout → write_tracker
            → sheets_sync push → scout_analysis → git commit + push
  Secrets:  All API keys stored as GitHub Actions repository secrets
            (Settings → Secrets and variables → Actions)
  Required secrets: ANTHROPIC_API_KEY, APIFY_TOKEN, IMAP_EMAIL, IMAP_APP_PASSWORD,
                    GOOGLE_SHEET_ID, GOOGLE_SA_JSON, GIT_USER_EMAIL, GIT_USER_NAME
  Optional secrets: GITHUB_REPO (format: username/repo — for CI monitoring only)

[RULE] CREDENTIAL ROTATION — when any API key changes, update BOTH:
  1. Local .env file
  2. GitHub Actions secret (repo Settings → Secrets → update value)

# ─────────────────────────────────────────────────────────────
# FULL END-TO-END WORKFLOW (all stages combined)
# ─────────────────────────────────────────────────────────────

#   1. DISCOVER (on-demand via Claude Code)
#      Say "run scout" in Claude Code (or specify a market)
#      Or run directly:
#        python3 scripts/run_scout.py                     (default market — verify in run_scout.py)
#        python3 scripts/run_scout.py --market uk         (United Kingdom)
#        python3 scripts/run_scout.py --market nl         (Netherlands)
#        python3 scripts/run_scout.py --market de         (Germany)
#        python3 scripts/run_scout.py --market dk         (Denmark)
#        python3 scripts/run_scout.py --market ie         (Ireland)
#        python3 scripts/run_scout.py --market ae         (UAE)
#        python3 scripts/run_scout.py --market se         (Sweden)
#        python3 scripts/run_scout.py --market intl       (all international markets)
#        python3 scripts/run_scout.py --market all        (every market)
#      → Claude reads agents/job_scout.md and runs the scout pipeline directly
#        (no UserPromptSubmit hook — natural-language trigger)
#      → Scrapes LinkedIn (Apify) → enriches → scores → deduplicates
#      → Stamps market field on every job → writes to job_tracker.json
#      → Pushes to Google Sheet
#
#   2. REVIEW (manual, ~5 min)
#      Open Google Sheet
#      → Review shortlisted jobs (fit score, salary, location, work mode)
#      → For each job you want to apply to:
#          a. Paste ATS career page URL into Col K (career_page_url)
#          b. Change status to "Approved" in Col H
#      → Run: python3 scripts/sheets_sync.py pull --tabs apps,archive
#
#   3. PREPARE (semi-automated)
#      sheets_sync.py pull writes job_tracker.json
#      → on_job_approved hook fires (PostToolUse)
#      → Detects Approved + career_page_url + resume_path=null
#      → Confirms with you, then invokes application_prep agent
#      → Tailors resume → renders PDF → writes cover letter PDF
#      → Updates tracker → pushes to Sheet
#
#   4. APPLY (manual, ~5-10 min per application)
#      Open career_page_url in browser
#      Review tailored resume PDF from outputs/applications/
#      Fill and submit the ATS form
#      (Claude in Chrome can assist with form filling)
#
#   5. TRACK (automated, on demand)
#      Say: "check email" or "check email last N days" in Claude Code
#      → Claude runs: python3 scripts/gmail_backfill.py --days N
#      → Connects to your IMAP inbox (configured via IMAP_EMAIL + IMAP_APP_PASSWORD in .env)
#      → Classifies each email via Claude API → fuzzy-matches to tracker
#      → Status updates flow: Applied → Under Review → Interview → Offer/Rejected
#      → Pushes to Google Sheet automatically

# ─────────────────────────────────────────────────────────────
# CONTRACT & REMOTE ROLES — role_type + para4_instructions
# ─────────────────────────────────────────────────────────────
# Every scout run captures BOTH permanent/hybrid AND remote/contract roles
# (no filtering at any stage — Gates 8/9 are enrichment signals only).
#
# role_type — 4-value enum (computed deterministically by auto_prep.py / write_tracker.py):
#   "contract_remote"   → EOR framing — candidate engages via Deel/Remote.com; no visa needed
#   "contract_hybrid"   → standard visa framing + contract note
#   "permanent_remote"  → aspirational relocation framing; remote readiness primary
#   "permanent_hybrid"  → existing default (standard visa + relocation framing)
#
# para4_instructions — set by auto_prep.py per role_type; written to auto_cover JSON:
#   - contract_remote: EOR framing mandate (no visa/relocation)
#   - other types: standard market relocation + visa sentence
#   - finalize_cover.py strips this field from final_cover JSON before rendering
#   - LLM reads it and follows it exactly — never infers role_type from context
#
# eor_viability — integer 1–10 (null for permanent non-remote roles):
#   Set by Claude Pass 2. Included in meta.json for contract/remote entries.
#
# is_contract + role_type are user-editable in Sheet (Col O + Col N).
# sheets_sync.py pull reads both back; if is_contract changes, role_type recomputes.
#
# EOR pitch skill: "draft EOR pitch [job_id]" (only for contract_remote roles)
#   File: skills/draft_eor_pitch.md
