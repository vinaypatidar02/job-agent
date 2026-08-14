# Agent: application_prep
# Stage 4 — ACTIVE
#
# ============================================================
# ARCHITECTURE NOTE — Deterministic parallel execution
# ============================================================
# All multi-job work is handled by run_prep.py (Python script).
# Claude's only job is:
#   (a) collect qualifying job IDs
#   (b) run: python3 scripts/run_prep.py --keys <id1>,<id2>,...
#   (c) review any WARNs or FAILs in the output
#
# Parallelism is enforced at the Python level (ThreadPoolExecutor)
# so it cannot regress regardless of how Claude calls it.
# ============================================================

# ── GIT SYNC + SHEET PULL — run FIRST before anything else ───────
# 1. Pull latest git state:
#      git pull
#    If pull has conflicts: git checkout --theirs data/job_tracker.json
# 2. Pull latest Sheet edits (career_page_url, status=Approved) into tracker:
#      python3 scripts/sheets_sync.py pull --tabs apps,archive
# This ensures the gate below sees all Sheet edits before checking which jobs to prep.
# ──────────────────────────────────────────────────────────────

# ── TRIPLE-CONDITION GATE (check before doing anything) ───────
# Collect all entries where ALL THREE are true:
#   1. status = "Approved"
#   2. career_page_url is not null and not empty
#   3. resume_path is null (prep not already done)
#
# EASY APPLY HANDLING:
#   If career_page_url = "EASY_APPLY" (sentinel value entered in Sheet):
#     → Include in run_prep.py run as normal
#     → run_prep.py writes is_easy_apply = true in meta.json automatically
#
# HACKAJOB PASSIVE HANDLING:
#   If career_page_url contains "hackajob.com" OR ats_type = "hackajob_passive":
#     → Include in run_prep.py run as normal
#     → run_prep.py writes is_hackajob_passive = true in meta.json automatically
#
# If status = "Approved" but career_page_url is null or empty:
#   Log: "SKIPPED [Company] / [Role] — career_page_url missing.
#         For ATS roles: paste URL in Sheet Col K then re-run pull.
#         For Easy Apply: enter 'EASY_APPLY' in Sheet Col K."
#   Do NOT process.
#
# If resume_path is already set:
#   Log: "SKIPPED [Company] / [Role] — already prepped at [resume_path]"
#   Do NOT re-process.
#
# If zero qualifying entries → log "Nothing to prep" and stop.

# ── STEP 1: RUN THE ORCHESTRATION SCRIPT ──────────────────────────────────────
# Collect all qualifying job IDs (e.g. app_7468,app_7469,app_7470).
# Run ONCE with all IDs:
#
#   python3 scripts/run_prep.py --keys <id1>,<id2>,...,<idN>
#
# This script runs all phases (1–5):
#   Phase 1 — Parallel: fetch_jd + auto_prep + eval_prep  (6 workers)
#   Phase 2 — Batched: generate_summaries.py             (Batch API, Haiku)
#   Phase 3 — Batched: generate_covers.py                (Batch API, Sonnet + prompt cache)
#   Phase 4a — Parallel: finalize_resumes.py             (mechanical, no LLM)
#   Phase 4b — Parallel: validate_prep + render PDFs + meta.json  (4 workers)
#   Phase 5 — Sequential: batch_tracker_update + sheets_sync push + git commit
#
# Wait for run_prep.py to exit before doing anything else.
# Do NOT run any phase scripts manually in parallel — that is already handled.
# ─────────────────────────────────────────────────────────────────────────────

# ── STEP 2: REVIEW FLAGGED OUTPUTS ───────────────────────────────────────────
# Read the summary printed by run_prep.py. For each flagged item:
#
#   [WARN] bullet >28w  (finalize_resumes.py RULE 1):
#     Open final_resume_<job_id>.json. Shorten only the flagged bullet
#     (preserve all metrics; strong verb). Re-run validate_prep.py for that job.
#     Re-render resume PDF: python3 scripts/pdf_renderer.py resume <final_resume> <pdf_out>
#
#   [WARN] weak leading verb  (finalize_resumes.py RULE 3):
#     Open final_resume_<job_id>.json. Replace the flagged bullet's first word.
#     Re-run validate_prep.py and re-render resume PDF.
#
#   [WARN] cover word count / FILL_ME  (generate_covers.py):
#     Open final_cover_<job_id>.json. Fix the issue.
#     Re-render cover PDF: python3 scripts/pdf_renderer.py cover <final_cover> <pdf_out>
#
#   [FAIL] validate_prep:
#     Open the specific resume/cover JSON. Fix all failing checks.
#     Re-render both PDFs. Then update tracker manually or via:
#       python3 scripts/batch_tracker_update.py --updates data/prep_tmp/tracker_updates.json
#
#   [WARN] eval_prep unfixed issues:
#     Review the affected auto_resume_<job_id>.json for bullet ordering.
#     Edit manually if needed — eval_prep D2/D3 issues require judgment.
#
# If zero WARNs and zero FAILs: prep is complete, no action needed.
# ─────────────────────────────────────────────────────────────────────────────

# ── COMPLETION SUMMARY (printed by run_prep.py) ───────────────────────────────
# ═══════════════════════════════════════
#  Application Prep — <date>
# ═══════════════════════════════════════
#  Processed:  X jobs
#  Failed:     Y jobs (if any)
#  PDFs in:    outputs/applications/ready/
# ═══════════════════════════════════════
