# Agent: job_scout
# Stage 4 — ACTIVE
#
# ============================================================
# LEARNING NOTE — Agent vs Skill
# ============================================================
# This agent orchestrates the full scrape-to-shortlist pipeline.
# It calls the Apify MCP tool, runs enrich_jobs.py, invokes the
# score_job skill for each result, writes to job_tracker.json,
# and syncs to Google Sheets. Skills do one thing; this agent
# coordinates many things in sequence.
# ============================================================

# ── PREREQUISITES ─────────────────────────────────────────────
# Before running, confirm:
#   - APIFY_TOKEN is set in .env
#   - data/job_tracker.json exists and is valid JSON
#   - Python venv is active (.venv/bin/activate)
#   - scripts/enrich_jobs.py and scripts/apify_cache.py are present

# ── STEP 1 — SCRAPE, ENRICH & SCORE (with cache) ─────────────
# Call scripts/run_scout.py directly — do NOT interpret --age or
# --expanded flags yourself. Pass them straight to the script.
#
# Mapping of user prompts → exact command to run:
#
#   "run scout"                → python3 scripts/run_scout.py --yes  (intl default: NL + DE + DK + IE; --yes skips stdin prompt)
#   "run scout --age 1"        → python3 scripts/run_scout.py --age 1
#   "run scout --age 7"        → python3 scripts/run_scout.py --age 7
#   "run scout --expanded"     → python3 scripts/run_scout.py --expanded
#   "run scout --age 1 --expanded" → python3 scripts/run_scout.py --age 1 --expanded
#   "run scout netherlands"    → python3 scripts/run_scout.py --market nl
#   "run scout sweden"         → python3 scripts/run_scout.py --market se
#   "run scout germany"        → python3 scripts/run_scout.py --market de
#   "run scout denmark"        → python3 scripts/run_scout.py --market dk
#   "run scout ireland"        → python3 scripts/run_scout.py --market ie
#   "run scout all markets"    → python3 scripts/run_scout.py --market all
#
# --market flag:  intl (default = NL + DE + DK + IE) | uk | nl | se | de | dk | ie | all
#   Selects which markets to scrape. Default is intl (NL + DE + DK + IE; DK/IE added 2026-07-24).
#   UK deprioritised 2026-07-24 — strict visa restrictions, low expected yield.
#   Cost breakdown per run (Apify, max slots × $0.001/job) — post 2026-07-24 DK/IE addition:
#     --market nl:   2 URLs (LDA 100 + LBA 75) = $0.175 max
#     --market de:   2 URLs (LDA 100 + LBA 75) = $0.175 max
#     --market dk:   2 URLs (LDA 100 + LBA 75) = $0.175 max
#     --market ie:   2 URLs (LDA 100 + LBA 75) = $0.175 max
#     --market intl: 8 URLs (NL+DE+DK+IE)      = $0.70 max
#     --market uk:   3 URLs (LDA/LBA/AM × 100) = $0.30 max
#     --market se:   3 URLs (LDA/LBA/AM × 100) = $0.30 max
#     --market all:  14 URLs                   = $1.30 max
#   Adzuna is free where supported (gb/nl only — API 404 for se/dk/ie, verified 2026-07-24).
#
# The script handles everything end-to-end:
#   - Argument parsing (age, expanded, market)
#   - Cache check + cost estimate printed before any Apify call
#   - Confirmation prompt (user types Y to proceed)
#   - CachedScraper.get_batch() per market with correct post_age_days
#   - Stamps market field ("uk"/"nl"/"se"/"de"/"dk"/"ie") on every scraped job
#   - Saves raw output to data/pipeline/raw_scrape_output.json
#   - Calls enrich_jobs.py automatically → data/pipeline/enriched_scrape_output.json
#   - Calls score_jobs.py automatically → data/pipeline/scored_jobs.json + data/auto_rejected.json
#
# DEFAULT behaviour (no flags): NL + DE + DK + IE (intl), past 24h (baked into LinkedIn URLs)
# Use --market all for UK + NL + SE + DE, --market uk for UK-only.
# NEVER default to expanded list or age values not explicitly passed.

# ── STEP 2 — WRITE SHORTLISTED/REVIEW/STALE TO TRACKER ───────
# Run: python3 scripts/write_tracker.py
#
# This script handles all tracker writes from scored_jobs.json:
#   - Reads data/pipeline/scored_jobs.json (Shortlisted + Review Needed + Stale entries)
#   - Deduplicates by (job_id, market) first, then jd_url exact match
#     (score_jobs.py already ran all complex fuzzy / stale-exception /
#     agency-URL dedup — do NOT re-implement dedup here or you risk
#     blocking valid fresh reposts)
#   - Assigns next sequential app_<NNN> IDs
#   - Writes all three status types to job_tracker.json
#   - Safe to run twice — duplicate (job_id, market) / jd_urls are skipped on second run
#
# NEVER write ad-hoc Python to do this step — the stale+fresh repost
# exception is subtle and the script already handles it correctly.
#
# Log: "[write_tracker] Wrote X entries to job_tracker.json"

# ── STEP 2.5 — SCOUT QUALITY EVALUATION ──────────────────────
# Run: python3 scripts/eval_scout.py
#
# Runs SC1–SC4 (zero API) + SC-S1 (1 Haiku call, ~$0.003).
# Skip semantic: python3 scripts/eval_scout.py --skip-semantic
#
#   IF exit code 0: log "✓ Scout eval passed" and proceed to STEP 3.
#
#   IF exit code 1 or 2 (issues found):
#
#     PART A — Fix this run (automatic, no approval needed):
#       python3 scripts/eval_scout.py --apply-ephemeral
#       Log what was patched (demoted entries, updated apply_recommendation, etc.)
#
#     PART B — Fix the root cause (one issue at a time, with approval):
#       For each issue that carries a systemic_fix in the report:
#         1. Show a one-line summary:
#              "Root cause fix — <file>: <what changes>"
#         2. Ask: "Apply this fix to prevent recurrence? (Y/n)"
#         3. If Y: use the Edit tool to make the exact change described.
#            If N: note it and move to the next issue.
#         4. After applying: run python3 scripts/check_workflow.py --quick
#            to confirm the pipeline is still intact.
#
#     Proceed to STEP 3 after both parts are done.
#
# HIGH vs MEDIUM/LOW only affects urgency of root-cause framing in the report —
# both follow the same two-part flow above. No blocking difference.

# ── STEP 3 — SYNC TO GOOGLE SHEETS ───────────────────────────
# Run: python3 scripts/sheets_sync.py push --tabs apps,archive
# This updates the Google Sheet with all new shortlisted entries
# so you can review, edit status, and paste career_page_url.
# Log: "[scout] Google Sheet updated"
# NOTE: This MUST run after Step 2 (tracker write) — not before.

# ── STEP 4 — SUMMARY ─────────────────────────────────────────
# Print a clean summary:
#   ═══════════════════════════════════════
#    Job Scout Run — <date>
#   ═══════════════════════════════════════
#    Raw scraped:     X
#    After enrichment: X
#    Shortlisted:     X  ← added to tracker + sheet
#    For review:      X  ← added to tracker + sheet
#    Auto-rejected:   X  ← logged only
#    Duplicates:      X  ← skipped
#   ───────────────────────────────────────
#    Next step: open Google Sheet, review shortlisted jobs,
#    paste career_page_url, set status → Approved,
#    then run: python3 scripts/sheets_sync.py pull --tabs apps,archive
#   ═══════════════════════════════════════

# ── ERROR HANDLING ────────────────────────────────────────────
# If Apify call fails → log error + HTTP code, abort gracefully
# If enrich_jobs.py fails → log error, abort (do not score raw data)
# If score_job returns unexpected shape → log + skip that job, continue
# If job_tracker.json write fails → log error, do not exit silently
