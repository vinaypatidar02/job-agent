# TOOL_COMMANDS.md — Complete Command Reference

All daily-use commands organised by pipeline stage. Run all commands from the project root directory.

---

## Scout — Discover Jobs

```bash
# Dry run (see search list + cost estimate, no API calls)
python3 scripts/run_scout.py --dry-run

# Run scout for specific markets
python3 scripts/run_scout.py --market uk       # United Kingdom
python3 scripts/run_scout.py --market nl       # Netherlands
python3 scripts/run_scout.py --market de       # Germany
python3 scripts/run_scout.py --market dk       # Denmark
python3 scripts/run_scout.py --market ie       # Ireland
python3 scripts/run_scout.py --market ae       # UAE
python3 scripts/run_scout.py --market se       # Sweden
python3 scripts/run_scout.py --market intl     # All non-UK markets (NL+DE+DK+IE+AE+SE)
python3 scripts/run_scout.py --market all      # Every configured market
python3 scripts/run_scout.py --yes             # Skip confirmation prompt (non-interactive)

# Write scored results to tracker (always run after run_scout.py)
python3 scripts/write_tracker.py

# Sync tracker to Google Sheet
python3 scripts/sheets_sync.py push --tabs apps,archive      # Applications + Archive (default)
python3 scripts/sheets_sync.py push --tabs apps,outreach     # Applications + Referral Outreach
python3 scripts/sheets_sync.py push                          # All tabs — first-time setup only (slow)

# Post-scout keyword analysis (run after every scout)
python3 scripts/scout_analysis.py
```

---

## Review and Approve — Google Sheet to Local

```
Workflow:
  1. Open Google Sheet
  2. Paste ATS career page URL into Col K (career_page_url) for each job to approve
  3. Set status to "Approved" in Col H
  4. Run pull to bring edits into job_tracker.json
```

```bash
python3 scripts/sheets_sync.py pull --tabs apps,archive
```

---

## Application Prep — Generate Resume and Cover Letter

```bash
# Run prep for all Approved jobs (recommended — use Claude Code natural language)
# In Claude Code: "run application prep"

# Run directly by app_id (for specific jobs)
python3 scripts/run_prep.py --keys app_001,app_002,app_003

# Auto prep (domain detection + bullet selection + JSON output — runs before generate_*)
python3 scripts/auto_prep.py

# Enrich jobs (salary parse, work_mode, ATS URL — runs after scout before scoring)
python3 scripts/enrich_jobs.py

# Generate profile summaries (Haiku batch — runs after auto_prep.py)
python3 scripts/generate_summaries.py
python3 scripts/generate_summaries.py --dry-run     # preview which apps need summaries
python3 scripts/generate_summaries.py --force       # regenerate even if already filled
python3 scripts/generate_summaries.py --keys app_001,app_002   # specific apps only

# Generate cover letter paragraphs (Sonnet batch — runs after auto_prep.py)
python3 scripts/generate_covers.py

# Merge LLM cover letter paragraphs into final structured JSON
python3 scripts/finalize_cover.py

# Merge LLM resume sections into final structured JSON
python3 scripts/finalize_resumes.py

# Validate prep output before PDF render
python3 scripts/validate_prep.py --job_id app_001

# Test PDF renderer layout (no app data needed)
python3 scripts/pdf_renderer.py test
```

---

## Email Tracking — Classify Employer Replies

```bash
python3 scripts/gmail_backfill.py                    # check last 2 days (default)
python3 scripts/gmail_backfill.py --days 7           # check last 7 days
python3 scripts/gmail_backfill.py --days 35          # full backfill (all recent email)
python3 scripts/gmail_backfill.py --retry-unmatched  # retry emails in unmatched_emails.json
python3 scripts/gmail_backfill.py --dry              # classify only, no writes to tracker
```

---

## Referral Tracking — Manage Outreach Pipeline

```bash
python3 scripts/referral_tracker.py                  # auto-advance statuses (day 4 → Followup, day 8 → Stale-Referral)
python3 scripts/referral_tracker.py --dry-run        # preview advances without writing
python3 scripts/referral_tracker.py status           # show all active referrals
python3 scripts/referral_tracker.py --push           # advance + sync to Sheet in one step
python3 scripts/referral_analysis.py                 # full funnel stats and pipeline summary
python3 scripts/referral_analysis.py --verbose       # timeline view (per-referral journey)
```

---

## Sync and Maintenance

```bash
# Sheet sync
python3 scripts/sheets_sync.py push --tabs apps,archive      # push after any tracker change
python3 scripts/sheets_sync.py pull --tabs apps,archive      # pull before app prep

# Git sync (commit pipeline data to GitHub)
python3 scripts/git_sync.py

# Workflow integrity check (run after any pipeline change)
python3 scripts/check_workflow.py
python3 scripts/check_workflow.py --quick    # skip integration tests (faster)

# Apify cache
python3 scripts/apify_cache.py status        # show all cached searches and their ages
python3 scripts/apify_cache.py clear         # clear cache — only on explicit user instruction

# Budget and CI monitoring
python3 scripts/monitor_scout.py             # Apify credit usage + GitHub Actions CI status

# Sponsor register (manual audit — not required for scoring)
python3 scripts/sponsor_register.py refresh-uk
python3 scripts/sponsor_register.py status

# Outreach tracker (recruiter contacts + job platforms)
python3 scripts/outreach.py list                              # show all platforms + recruiters
python3 scripts/outreach.py list --type platforms            # platforms only
python3 scripts/outreach.py list --type recruiters           # recruiters only
python3 scripts/outreach.py list --market nl                 # filter recruiters by market

# Templates tab (update after any contact table format change)
python3 scripts/update_templates.py                          # regenerate Sheet Templates tab
```

---

## Manual Job Injection

```bash
# Step 1: populate data/manual_jobs_input.json with the job details
# Step 2: run the injector
python3 scripts/inject_manual.py

# Or in Claude Code: "inject manual job" (triggers the inject_manual_jobs skill)
```

---

## Diagnostics and Audit Tools

```bash
# Title tier classification (audit existing titles)
python3 scripts/classify_title.py "Head of Analytics"   # single title
python3 scripts/classify_title.py --batch                # stdin, one title per line
python3 scripts/classify_title.py                        # run built-in verification suite

# Test email classifier (no IMAP required)
python3 scripts/test_email_tracker.py

# Scout analysis
python3 scripts/scout_analysis.py                        # keyword overlap matrix + market breakdown
```

---

## Claude Code Natural Language Triggers

When Claude Code is open in this project, these natural language phrases trigger the corresponding scripts or skills:

| Phrase | Action |
|--------|--------|
| "run scout" | `python3 scripts/run_scout.py --yes` |
| "run scout [market]" | `python3 scripts/run_scout.py --market [market] --yes` |
| "run application prep" | `application_prep` agent (all Approved jobs) |
| "check email" | `python3 scripts/gmail_backfill.py --days 2` |
| "check email last N days" | `python3 scripts/gmail_backfill.py --days N` |
| "check email backfill" | `python3 scripts/gmail_backfill.py --days 35` |
| "retry unmatched emails" | `python3 scripts/gmail_backfill.py --retry-unmatched` |
| "run referral tracker" | `python3 scripts/referral_tracker.py --push` |
| "sync to sheet" | `python3 scripts/sheets_sync.py push --tabs apps,archive` |
| "pull from sheet" | `python3 scripts/sheets_sync.py pull --tabs apps,archive` |
| "score [job_id]" | `score_job` skill |
| "draft cover letter [job_id]" | `draft_cover_letter` skill |
| "draft referral message" | `draft_referral_message` skill (provide contact table) |
| "draft EOR pitch [job_id]" | `draft_eor_pitch` skill (contract_remote roles only) |
| "inject manual job" | `inject_manual_jobs` skill |
| "show outreach / list recruiters" | `python3 scripts/outreach.py list` |
| "update templates tab" | `python3 scripts/update_templates.py` |

---

## Daily Session Sequence

```
Morning:
  1. python3 scripts/gmail_backfill.py                         # check overnight replies
  2. python3 scripts/sheets_sync.py push --tabs apps,archive   # push any status updates
  3. python3 scripts/run_scout.py --market intl --yes          # discover new jobs
  4. python3 scripts/write_tracker.py                          # write scored results
  5. python3 scripts/scout_analysis.py                         # review results + keyword overlap
  6. python3 scripts/sheets_sync.py push --tabs apps,archive   # publish to Sheet

Approval cycle (after reviewing Sheet):
  6. python3 scripts/sheets_sync.py pull --tabs apps,archive   # pull approvals + ATS URLs
  7. [In Claude Code] "run application prep"                    # generate documents

Referral (weekly):
  8. python3 scripts/referral_tracker.py --push                # advance + sync
  9. python3 scripts/referral_analysis.py                      # review funnel
```
