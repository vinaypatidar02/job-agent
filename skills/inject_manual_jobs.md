# Skill: inject_manual_jobs
# Stage 2 — ACTIVE
#
# ============================================================
# PURPOSE
# ============================================================
# Inject manually-found LinkedIn jobs into the scoring pipeline.
# Supports a minimal input format: just a job URL (no description required).
# Claude fetches the full JD via Chrome browser automation, then runs the
# complete pipeline: inject → enrich → score → write → pull → push.
#
# Trigger phrase: "inject manual jobs" (or "inject jobs", "inject manual")
#
# VALIDATED 2026-08-05: Browser fetch confirmed working against Raylo job
# 4432667000 — 7,559 chars extracted, matches known JD.
# ============================================================

# ── INPUT FORMAT ─────────────────────────────────────────────
# User provides job details conversationally — no file editing required:
#
# MINIMAL (description auto-fetched via browser):
#   "inject this job: https://www.linkedin.com/jobs/view/4429589502/"
#   "inject this job: https://... — market: de"
#
# FULL (no browser fetch needed):
#   "inject this job: Head of Analytics at Spotify, Stockholm, permanent — [paste JD text]"
#
# Optional overrides the user can mention:
#   market, posted_date, is_contract, is_remote_only
#
# Step 0 reads whatever the user provided, builds the entry, and writes it to
# data/manual_jobs_input.json internally — the user never sees the JSON format.
# ============================================================

# ── STEP 0 — Build entry from user input ─────────────────────
# Parse what the user provided (URL and/or job details).
# Build a JSON entry in the appropriate format (minimal or full).
# Write to data/manual_jobs_input.json (read first, append, write back).
# Log: "[inject] Entry added: [Company] [Title] — proceeding to fetch/score"

# ── STEP 1 — Read and parse input file ───────────────────────
# Read data/manual_jobs_input.json.
# Strip lines starting with // (comment lines) using regex.
# Parse remaining JSON.
# Identify minimal entries: job_url present but description absent or empty/whitespace.
# Log count: "[inject] X minimal entries need browser fetch, Y full entries ready"

# ── STEP 2 — Fetch minimal entries via browser ────────────────
# Skip this step entirely if all entries have descriptions.
#
# IMPORTANT: LinkedIn is a JS-rendered SPA. The "About the job" section
# is initially collapsed. Exact fetch sequence (validated 2026-08-05):
#
# Load ALL required browser tools in a SINGLE ToolSearch call:
#   select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,
#          mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,
#          mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__tabs_close_mcp
#
# For each minimal entry:
#
#   1. VERIFY LOGIN: Call tabs_context_mcp. Check existing tabs for a LinkedIn tab.
#      If no LinkedIn session visible: warn user they must be logged into LinkedIn
#      in Chrome browser, then stop.
#
#   2. CREATE TAB: Call tabs_create_mcp to open a fresh tab.
#      Navigate to the job_url.
#
#   3. WAIT: computer wait action, duration=3 — LinkedIn SPA needs time to hydrate.
#
#   4. SCROLL: computer scroll down 500px (coordinate [590, 400], direction=down,
#      scroll_amount=5) — triggers intersection-observer lazy loading of the
#      "About the job" section.
#
#   5. SCREENSHOT: computer screenshot — verify the page loaded.
#      Check screenshot for:
#        - Login wall ("Sign in", "Join now"): log FAILED, close tab, skip URL.
#        - "About the job" heading visible: proceed.
#        - "About the job" not visible (page error/empty): log FAILED, close tab, skip URL.
#
#   6. CLICK "… more": The description is truncated. A "… more" link appears at the
#      bottom of the visible text. Click it using computer left_click at the approximate
#      coordinates visible in the screenshot.
#      Typical position: x≈290, y≈345 after scrolling. Confirm from screenshot.
#
#   7. EXTRACT via get_page_text + WRITE CACHE IMMEDIATELY:
#
#      Call get_page_text on the tab. This returns the full rendered page text.
#
#      Parse the text:
#        job_title:    First h1 or title line (LinkedIn sets page title as "Role | Company | LinkedIn")
#        company_name: Second segment of page title, or prominent company name near top
#        location:     Line after company name (e.g. "Amsterdam, North Holland, Netherlands · X days ago")
#        work_mode:    Look for "Hybrid" / "Remote" / "On-site" pill text near top
#        job_type:     Look for "Full-time" / "Contract" / "Part-time" near top
#        posted_raw:   "X days ago" / "X weeks ago" / "X months ago" → convert to YYYY-MM-DD
#        description:  Everything between "About the job" heading and "Set alert for similar jobs"
#
#      Market derivation from location text:
#        Netherlands / Amsterdam / Rotterdam / Utrecht / etc. → "nl"
#        Germany / Berlin / Munich / Frankfurt / Hamburg → "de"
#        Denmark / Copenhagen → "dk"
#        Ireland / Dublin → "ie"
#        UAE / Dubai → "ae"
#        Sweden / Stockholm → "se"
#        United Kingdom / London / Manchester / etc. → "uk"
#        Default → "uk"
#
#      IMMEDIATELY AFTER extracting — write to data/jd_text_cache.json:
#        1. git pull (ensure local is up to date)
#        2. Read current data/jd_text_cache.json
#        3. Add entry keyed by job_id (as string):
#           {description, company, role, location, job_type, work_mode, posted_date, market}
#        4. Write back — do NOT batch across multiple jobs
#      This prevents data loss if the session ends or context is compacted mid-run.
#
#   8. CLOSE TAB: tabs_close_mcp.
#
#   9. LOG:
#      Success: "[inject] Fetched: <job_title> @ <company_name> (<location>) — <N> chars"
#      Failure: "[inject] FAILED: <url> — <reason>. Add description manually."

# ── STEP 3 — Merge and write enriched entries ─────────────────
# For each successfully fetched entry:
#   - Merge extracted fields (from get_page_text parse + cache) into the entry dict.
#   - User-supplied fields (market, posted_date, is_contract etc.) OVERRIDE extracted values.
#   - IMPORTANT: Always include location and market explicitly so inject_manual.py does
#     not fall back to market="uk" for non-UK jobs. Missing location → wrong market →
#     location gate rejection. Never leave location empty in the output entry.
#   - If description is still empty after fetch attempt: skip that entry.
# Write the complete list (all entries, including unchanged full-form entries) back
# to data/manual_jobs_input.json preserving the original comment header.
#
# NOTE: Write the ACTIVE (non-commented) entries only — preserve commented examples as-is.
# Simplest approach: read raw text, strip comment lines for parsing, then rebuild the file
# by writing the enriched active entries as uncommented JSON within the [ ] array.

# ── STEP 4 — Run injection pipeline ──────────────────────────
# Run sequentially:
#   python3 scripts/inject_manual.py
#   python3 scripts/enrich_jobs.py
#   python3 scripts/score_jobs.py
#   python3 scripts/write_tracker.py
#   python3 scripts/sheets_sync.py pull --tabs apps,archive
#   python3 scripts/sheets_sync.py push --tabs apps,archive
#   python3 scripts/scout_analysis.py

# ── STEP 5 — Report ──────────────────────────────────────────
# Show a brief summary table:
#   - How many browser-fetched (with description char count per entry)
#   - How many full-form (description already present)
#   - How many failed fetch (with URL)
#   - Scoring results: shortlisted / review needed / auto-rejected
#   - Scout analysis output (from scout_analysis.py)

# ── ERROR HANDLING ────────────────────────────────────────────
# Login wall detected    → stop, tell user to log into LinkedIn in Chrome, then retry
# Empty page / timeout   → skip that URL, continue with others
# No description after
#   fetch attempt        → skip that entry (inject_manual.py guard catches any that slip through)
# Job already in tracker → inject_manual.py dedup skips silently; show in summary
# Browser tools missing  → load via ToolSearch before proceeding (single call, all tools)
