# docs/project-file-map.md — Project File Map
# Referenced by CLAUDE.md §8 via @docs/project-file-map.md


[CONTEXT] Project structure and file purposes:

  CLAUDE.md                         ← Session context — read first, always.
  mcp.json                          ← MCP server configs (Apify LinkedIn scraper)
  .env                              ← API keys (never commit — gitignored)
  .env.example                      ← Template for .env (safe to commit)
  requirements.txt                  ← Python dependencies

  docs/candidate-profile.md        ← YOUR candidate profile (imported by CLAUDE.md §2)
  docs/fit-scoring-rubric.md        ← YOUR scoring rubric (imported by CLAUDE.md §4)
  docs/project-file-map.md          ← This file (imported by CLAUDE.md §8)
  docs/market-onboarding-guide.md   ← Guide for adding a new market

  skills/score_job.md               ← Skill: score a JD against profile
  skills/tailor_resume.md           ← Skill: domain detection + resume bullet selection
  skills/draft_cover_letter.md      ← Skill: write targeted cover letter as PDF
  skills/draft_application_response.md ← Skill: answer application questions + recruiter emails/DMs
  skills/draft_referral_message.md  ← Skill: draft LinkedIn connection notes + referral messages
  skills/draft_eor_pitch.md         ← Skill: EOR pitch for contract_remote roles
  skills/inject_manual_jobs.md      ← Skill: inject manually-found jobs into pipeline

  agents/job_scout.md               ← Agent: scrape → deduplicate → score → shortlist
  agents/application_prep.md        ← Agent: tailor resume + cover letter (both PDFs)
  agents/tracker.md                 ← Agent: update job_tracker.json from emails
  agents/CLAUDE.md                  ← Hook orchestration + 5-step workflow guide

  hooks/on_job_approved.md          ← Hook: triggers application_prep
  hooks/on_email_received.md        ← Hook: triggers tracker status update

  data/job_tracker.json             ← Application pipeline state (source of truth)
  data/auto_rejected.json           ← Jobs rejected by score_jobs.py (key: "auto_rejected")
  data/unmatched_emails.json        ← Emails that couldn't be matched to applications
  data/outreach.json                ← Referral contact tracking
  data/referral_outreach_log.json   ← Log of all referral outreach messages (final versions)
  data/application_qa_log.json      ← Log of all Q&A answers + recruiter emails (final versions)
  data/processed_email_ids.json     ← Email IDs already processed (dedup for gmail_backfill)
  data/manual_jobs_input.json       ← Jobs to inject manually (edit then run inject_manual.py)
  data/jd_text_cache.json           ← Cache of fetched JD text (used by fetch_jd.py)

  data/content/candidate_profile.json  ← MASTER CONFIG: your profile + preferences
  data/content/experience_bank.md      ← ALL resume bullets (single source of truth)
  data/content/application_qa_bank.md  ← Q&A style anchors and pre-written snippets
  data/content/cover_letter_bank.md    ← Cover letter openers and domain hooks
  data/content/recruiter_outreach_template.md ← Outreach message structure

  data/sponsor_registers/           ← UK/NL sponsor register data (optional manual audit)
  data/apify_cache/                 ← Apify 24h result cache (auto-managed)
  data/prep_tmp/                    ← Temporary prep files (auto_resume_*.json, auto_cover_*.json)
  data/pipeline/                    ← Intermediate pipeline files (scored_jobs.json etc.)
  data/monitoring/                  ← Scout run monitoring logs

  scripts/run_scout.py              ← Scout entrypoint: Apify scrape per market
  scripts/score_jobs.py             ← Two-pass scoring: Pass 1 Python gates + Pass 2 Claude batch
  scripts/write_tracker.py          ← Writes scored jobs into job_tracker.json / auto_rejected.json
  scripts/enrich_jobs.py            ← Post-scrape enrichment: compensation, experience, work_mode, ATS URL
  scripts/auto_prep.py              ← Application prep: domain detection, bullet selection, resume + cover JSON
  scripts/generate_summaries.py     ← Batch-generate Profile Summaries (Haiku + Batch API)
  scripts/generate_covers.py        ← Batch-generate Cover Letter paragraphs (Sonnet + Batch API)
  scripts/finalize_cover.py         ← Merge LLM paragraphs into auto_cover template
  scripts/finalize_resumes.py       ← Finalise resume JSON from auto_prep + summaries output
  scripts/run_prep.py               ← Orchestrate full prep pipeline for specific job IDs
  scripts/validate_prep.py          ← Post-prep validation checks (V1–V23)
  scripts/pdf_renderer.py           ← Render resume + cover letter PDFs (ReportLab, A4)
  scripts/sheets_sync.py            ← Bidirectional sync: job_tracker.json ↔ Google Sheet
  scripts/organize_outputs.py       ← Moves folders between ready/ referral/ and done/
  scripts/gmail_backfill.py         ← Email tracking via IMAP (Yahoo/Gmail/Outlook)
  scripts/fetch_jd.py               ← Fetch full JD text (cache-first, then WebFetch fallback)
  scripts/apify_cache.py            ← Cache layer for Apify results (24h TTL, MD5 key)
  scripts/classify_title.py         ← Pass 1 title tier classifier
  scripts/inject_manual.py          ← Inject manually-found jobs into the pipeline
  scripts/check_workflow.py         ← Workflow integrity checks (run after any pipeline change)
  scripts/scout_analysis.py         ← Post-scout results analysis + keyword overlap matrix
  scripts/monitor_scout.py          ← Scout run monitoring + Apify budget tracking
  scripts/referral_tracker.py       ← Referral flow: auto-advance Reached-Out → Followup → Stale-Referral
  scripts/referral_analysis.py      ← Referral pipeline analysis: funnel, timing, per-market
  scripts/git_sync.py               ← Git pull/commit/push automation for pipeline data
  scripts/outreach.py               ← Outreach tab data management
  scripts/sponsor_register.py       ← Refresh UK/NL sponsor registers (optional manual audit)
  scripts/update_templates.py       ← Sync Templates tab in Google Sheet (run after template changes)
  scripts/batch_tracker_update.py   ← Batch status updates to job_tracker.json
  scripts/test_email_tracker.py     ← Email classifier test (no IMAP needed)
  scripts/common.py                 ← Shared constants (SALARY_THRESHOLDS, paths, market config)
  scripts/CLAUDE.md                 ← PDF layout spec + Google Sheet column reference

  .claude/settings.json             ← Claude Code hooks wiring (PostToolUse on job_tracker writes)
  .github/workflows/daily_scout.yml ← GitHub Actions: automated daily scout

  outputs/applications/ready/       ← Prep Complete, active referral steps — awaiting action
  outputs/applications/referral/    ← Referred, Stale-Referral — referral attempt concluded
  outputs/applications/done/        ← Applied, Withdrawn, Rejected, etc.

  templates/google_sheets_setup.md  ← Service account setup + sheet schema guide
