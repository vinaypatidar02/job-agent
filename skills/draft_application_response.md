# Skill: draft_application_response
# Stage 4 — ACTIVE
#
# ============================================================
# PURPOSE
# ============================================================
# Handles three modes of application communication:
#   question — answer an application form question
#   email    — draft a formal recruiter outreach email
#   dm       — draft a short LinkedIn / platform message
#
# Content source: data/content/experience_bank.md (single source of truth for all claims).
# Style reference: data/content/application_qa_bank.md (tone and structure anchors).
# All answers grounded in real experience — nothing fabricated.
# All corrections during refinement update the Q&A bank for future drafts.
# Only the final approved answer is stored to data/application_qa_log.json.
# ============================================================

# ── INPUT ────────────────────────────────────────────────────
# Natural language reference — no job_id required:
#
#   company:         "Vio" | "GoodHabitz" | "Altum Consulting" etc.
#   role:            "Senior Data Analyst" (optional — disambiguates multi-entry companies)
#   question:        "<question text>"              (mode=question only)
#   recruiter_name:  "<name or null>"               (mode=email/dm)
#   recruiter_email: "<email or null>"              (mode=email only)
#   already_applied: true | false                   (mode=email/dm)
#   easy_apply:      true | false                   (mode=email)
#
# Mode is inferred from context if not stated:
#   Question text present  → mode=question
#   Recruiter email given  → mode=email
#   "message" / "DM" / "LinkedIn" in prompt → mode=dm


# ── STEP 0 — READ MESSAGE LOG (mode=dm/email, thread replies) ───────────
# Before drafting any reply or follow-up to a contact who has already been
# messaged, search data/referral_outreach_log.json for ALL prior messages
# to that contact (connection note, referral request, thread replies).
#
# Why: Without reading the log, drafts risk repeating things already said,
# misjudging the relationship stage, or over-explaining context the contact
# already knows (e.g. visa process to someone who has worked in that country
# for years).
#
# How: grep/filter by contact_name, read all entries in chronological order,
# then draft anchored in what has already been exchanged.
#
# Skip only when: the prompt explicitly states this is a first message
# (connection note or cold outreach with no prior exchange).


# ── STEP 1 — RESOLVE JOB REFERENCE ──────────────────────────
# Read data/job_tracker.json.
# Search for entries matching the company name (case-insensitive fuzzy match).
# If role also provided: narrow to matching role title.
#
# Outcomes:
#   Single match found → use it; extract company, role, job_id, market, location,
#                        notes, flags, visa_sponsorship_status, fit_score
#   Multiple matches   → list them and ask user to confirm which one before proceeding
#   No match           → ask user to check company name; do not proceed on a guess
#
# Log: "[qa] Resolved: [Company] / [Role] (job_id: <id>, market: <market>)"


# ── STEP 2 — LOAD JD TEXT ────────────────────────────────────
# Run: python3 scripts/fetch_jd.py --job_id <job_id>
#
# source = enriched | raw | apify_cache | adzuna_cache → use description field directly
# source = not_found → proceed with tracker metadata (company, role, location, notes, flags)
#                      note in output: "[qa] JD unavailable — using tracker metadata only"
#
# JD text is needed for company-specific detail in answers — particularly for
# motivation questions. Do not fabricate JD detail not in the text or tracker.


# ── STEP 3 — CLASSIFY QUESTION (mode=question only) ──────────
#
# | Category         | Trigger phrases                                                              |
# |------------------|------------------------------------------------------------------------------|
# | motivation       | "Why interested?", "Why this company?", "Why this role?"                     |
# | learning         | "Main learning", "Past year", "How have you grown?"                          |
# | comparable_role  | "Most relevant role", "Comparable experience", "Similar?"                    |
# | achievement      | "Key achievement", "Most proud of", "Biggest impact?"                        |
# | behavioral       | "Tell me about a time...", "How do you handle...", "Example"                 |
# | work_arrangement | "Are you open to remote?", "Timezone?", "Equipment?", "When can you start?", |
# |                  | "Are you willing to relocate?", "Work from home?", "Remote setup?"           |
#
# If question doesn't clearly fit one category, classify as behavioral and note.
# If multiple categories fit (e.g. "comparable role + key achievement"), draft both
# angles and present the most relevant one first.


# ── INTERNATIONAL EXPERIENCE (all modes) ──────────
# If you have international work experience (relocation, onsite deployment at a foreign office,
# or cross-cultural team leadership), document it in experience_bank.md and reference it here.
# Source bullets: experience_bank.md — use the most relevant role with cross-border scope.
#
# USE IT when the question/message touches: relocation readiness, international
# or cross-cultural experience, adaptability, working with distributed teams,
# "why should we consider a candidate from abroad", or recruiter
# outreach where establishing proven-relocator status adds credibility.
#
# FRAMING RULES (adapt to your own experience):
#   - Anchor inside the longer tenure (e.g. "deployed onsite for X months during my Y-year
#     tenure with [Company]") — never as a standalone short job.
#   - Frame as employer trust + successful adaptation: visa, relocation, and
#     delivery in an unfamiliar market, embedded with local stakeholders.
#   - For relocation questions: this is the primary evidence — lead with it,
#     then the permit route (kennismigrant / EU Blue Card / Pay Limit Scheme /
#     Critical Skills Employment Permit — match the job's market).
#   - Never inflate: use exact tenure and city from experience_bank.md only.

# ── STEP 4 — DRAFT ANSWER ────────────────────────────────────

# ── motivation (150–250 words) ────────────────────────────
# 1. Lead with what is genuinely compelling about THIS company — use JD text or
#    tracker notes/flags for specific detail. Never fabricate or use generic praise.
# 2. Acknowledge domain match honestly: if experience is analogical not direct, say so.
#    BAD: "maps directly onto that experience"
#    GOOD: "the analytical skills are transferable — [explain why]"
# 3. Reference the specific role mandate from JD (not just the company name).
# 4. If relevant: mention agentic pipeline fit (see AI framing rules in STEP 5).
# 5. Close with market-appropriate relocating sentence (STEP 5 Rule 2).
#
# Style reference: data/content/application_qa_bank.md SECTION 1

# ── learning (200–280 words) ──────────────────────────────
# Draw from the FULL agentic pipeline — all 5 stages in sequence:
#   Stage 1: Multi-source data scraping with caching and deduplication
#   Stage 2: Two-pass LLM-based scoring with explicit rubrics and hard override logic
#   Stage 3: Domain-aware document generation with structured JSON-to-PDF rendering
#   Stage 4: Structured email classification for automated status tracking
#   Stage 5: Bidirectional Google Sheets sync
#
# Frame the learning as:
#   - Systems thinking: each stage produces structured output consumed by the next
#   - Decision auditability: making scoring/override logic explicit and testable
#   - LLM evaluation discipline: evaluating outputs critically, building validation layers
#
# Connect to career impact: now bridges domain logic and AI tooling; can evaluate
# LLM outputs critically; builds validation layers that catch errors before decisions.
#
# FORBIDDEN in this answer (see STEP 5 Rule 3):
#   resume, cover letter, job search, job application, resume tailoring, job search automation
# USE INSTEAD:
#   document generation, data ingestion, event-driven email processing,
#   structured JSON-to-PDF rendering
#
# Style reference: data/content/application_qa_bank.md SECTION 2

# ── comparable_role (200–300 words) ──────────────────────
# Lead with your most relevant role for the JD domain.
# Draw from experience_bank.md — pick the role with the strongest JD keyword overlap.
#
# Always use precise labels for each company/product (document in candidate_profile.json):
#   - Platform per employer (e.g. AWS/Redshift, GCP/BigQuery) — never mix up
#   - Business type (exact product/market description from experience_bank.md)
#   - Connecting key or unique methodology that shows cross-domain thinking
#
# Key metrics: use ONLY verbatim metrics from experience_bank.md — never alter percentages.
# Document your canonical metrics in candidate_profile.json → profile.canonical_metrics
#
# Always acknowledge domain difference honestly if present.
# Style reference: data/content/application_qa_bank.md SECTION 3

# ── achievement (100–150 words) ───────────────────────────
# Select from experience_bank.md — highest-metric bullet most relevant to JD domain.
# Structure: challenge → action → result.
# Include exact metric verbatim from experience_bank.md.
# Do NOT alter percentages.

# ── behavioral (150–200 words) ────────────────────────────
# STAR format: Situation → Task → Action → Result.
# Draw from experience_bank.md — do not fabricate.
# Style reference: data/content/application_qa_bank.md SECTION 4

# ── work_arrangement (80–150 words) ───────────────────────
# Use SECTION 5 of application_qa_bank.md for pre-written phrasing anchors.
# Adapt to the specific question (timezone / equipment / start date / relocation).
#
# Key anchors (always grounded in facts — never fabricate):
#   Remote readiness:  Fully set up to work remotely from day one; experienced
#                      with async, distributed collaboration across time zones.
#   Timezone:          IST (UTC+5:30). Can overlap CET/CEST business hours (offset
#                      is 6.5h ahead). Flexible on early morning / late evening
#                      for team meetings or standups.
#   Equipment:         Own machine available from day one; happy to use company
#                      device once provided / shipped.
#   Start date:        Can start remotely within [X weeks notice period]; relocation
#                      to follow once permit approved (typically 2–3 months).
#   Relocation intent (EU markets):
#                      Express personal desire to relocate to [country] and pursue
#                      the relevant permit (EU Blue Card / Kennismigrant / Pay Limit
#                      Scheme / CSEP) independently — aspirational, not a request for
#                      company sponsorship logistics. Keep subtle and forward-looking.
#
# FRAMING RULE: For remote roles — remote companies do NOT expect the candidate to
# relocate. Do NOT frame the visa/permit as something the company must handle.
# Remote readiness is the primary message; relocation is a personal aspiration, mentioned briefly.

# ── ROLE TYPE FRAMING (read role_type from tracker / job context) ──────────
# When role_type = "contract_remote":
#   - Visa / right-to-work questions:
#     "I am available as a remote contractor via an Employer of Record (Deel or
#      Remote.com). The EOR entity is the legal employer in my country of residence,
#      so no work permit or right-to-work in [country] is required from your side."
#   - Start date: "Immediately, or within two weeks."
#   - Work arrangement: "Fully remote from India, with 6+ hours daily overlap with
#     UK/CET business hours — I can flex to align with your team's core hours."
#   - NEVER mention visa sponsorship, relocation, or right-to-work as the company's obligation.
#
# When role_type = "permanent_hybrid" | "permanent_remote" | "contract_hybrid":
#   - Existing permanent-role framing unchanged (see work_arrangement section above).
# ─────────────────────────────────────────────────────────────────────────────

# ── email (mode=email) ────────────────────────────────────
# See STEP 6 for full email structure rules.
# Body: 3–4 short paragraphs. Reference company + role specifically.

# ── dm (mode=dm) ─────────────────────────────────────────
# 80–120 words. Punchy, professional, not stiff.
# Name the role. One key fit point. Relocating sentence. CTA.

# ── HIRING MANAGER cold DM (mode = hiring_manager_dm) ────────────────────────
# Trigger: "Draft hiring manager cold DM [company] [role/focus]"
# Target:  Directors of Data / CDOs / VPs of Analytics — INTERNAL hiring managers
#          NOT for: HR/P&C, external recruiters, peer contacts (use dm mode for those)
#
# Hook source:
#   - job_id given → read tracker entry + run fetch_jd.py; derive company hook
#     from JD text (what they are building, their known challenge, their data stage)
#   - no job_id → use Claude's knowledge of the company; FLAG output with:
#     "[MANUAL REVIEW: hook is from Claude knowledge — verify before sending]"
#
# Structure (120–160 words total, plain text):
#   Sentence 1 — Company hook (1 sentence):
#     What they are working on that caught attention — their product direction,
#     a public initiative, a known data maturity challenge. Specific, not generic.
#     Never fabricate; if unsure, flag for manual review.
#
#   3 impact bullets (action-noun format, real metrics from experience_bank.md):
#     • Scaled Data Impact:         [verb + what + metric linking data to commercial growth]
#     • Delivered Commercial Value: [verb + what + financial/efficiency outcome + metric]
#     • Future-Proofed Teams:       [verb + governance/capability-building + outcome]
#     Each bullet: ~1 sentence. Use verbatim metrics — never alter percentages.
#
#   Closing (2 sentences):
#     Express interest in connecting briefly + soft CTA (not a CV push, not a job ask).
#     Example: "If you're thinking about scaling your analytics capabilities this year,
#     I'd welcome a brief exchange. Happy to share more context if useful."
#
# Tone:   Peer-to-peer — as a senior practitioner to another. Not a cover letter pitch.
# NEVER:  "I am writing to apply", offer CV in first message, mention visa/sponsorship.
#
# Email subject line (when reaching out via email rather than DM):
#   "[YOUR_SENIORITY_LABEL] ([YOUR_YEARS]+ Yrs) – [value prop tied to company context]"
#   Example: "Senior Analytics Leader (8+ Yrs) – Scaling Decision-Grade Analytics at [Company]"
#   (Adapt YOUR_SENIORITY_LABEL from candidate_profile.json → profile.target_roles[0])
#
# Log: Save final approved version to data/referral_outreach_log.json under
#      outreach_type = "hiring_manager_cold_dm".
# Step 0 (read log) and Step 1 (resolve job reference) apply to this mode too.


# ── STEP 5 — APPLY HONESTY RULES (ALL MODES) ────────────────
# These rules override everything. Check every draft before displaying.

# RULE 1 — Domain match honesty
#   If experience is analogical (not a direct sector match), say so explicitly.
#   BAD: "maps directly onto that experience"
#   GOOD: "the analytical skills are transferable" + explain the mapping

# RULE 2 — Relocating framing
#   NEVER: "in the process of relocating" / "currently relocating"
#   CORRECT pattern: "I am based in [YOUR_CITY, YOUR_COUNTRY], and am actively seeking roles
#   in [country] under [visa]. [City] is a preferred destination and I am fully
#   prepared to relocate upon receiving an offer."
#   (Update [YOUR_CITY, YOUR_COUNTRY] from candidate_profile.json → contact.address)
#   Visa per market:
#     uk → Skilled Worker Visa sponsorship
#     nl → Kennismigrant permit
#     de → EU Blue Card
#     se → Arbetstillstånd permit
#     dk → Danish work and residence permit under the Pay Limit Scheme
#          (Beløbsordningen) — NEVER "EU Blue Card" (Denmark opted out)
#     ie → Critical Skills Employment Permit
#     ae → UAE Employment Visa / Work Permit (employer-sponsored) — NEVER "EU Blue Card"

# RULE 3 — AI project framing (application domain must never be revealed)
#   FORBIDDEN: resume, cover letter, job search, job application, resume tailoring,
#              job search automation, CV generation
#   USE: document generation, data ingestion, event-driven email processing,
#        structured JSON-to-PDF rendering, automated status tracking

# RULE 4 — Metrics are fixed (never alter)
#   Your canonical metrics are configured in candidate_profile.json → profile.canonical_metrics
#   These are real figures from real outcomes. Rounding or paraphrasing is not permitted.
#   Always draw from experience_bank.md — never invent or adjust any percentage.

# RULE 5 — Company/product identity (per employer)
#   ALWAYS use the precise product label and business description for each company.
#   Document in candidate_profile.json → experience[].focus_areas + platform_notes.
#   The key risk: wrong business type or wrong data platform = credibility loss in interviews.
#   Cross-check experience_bank.md bullets for exact labels before using in answers.

# RULE 6 — Data platforms per employer (never mix up)
#   Each employer uses a specific data platform — document in candidate_profile.json → profile.platform_notes.
#   Example format: {"Company A": "AWS (Redshift)", "Company B": "GCP (BigQuery)"}
#   Wrong platform = credibility risk in a technical interview.
#   Always verify platform against experience_bank.md before citing in any answer.

# RULE 7 — Skills exclusion
#   NEVER mention Google Analytics, Firebase, or Apache Airflow in any answer,
#   email, or outreach message.
#   These may appear in experience_bank.md role bullets (historical factual use)
#   but must never appear in Q&A answers, emails, or DMs.

# RULE 8 — AI pipeline tense
#   ALWAYS: "have built... fully operational in production"
#   NEVER: "currently building", "am building", "in progress"
#   The pipeline is live and shipped.

# RULE 9 — MMM / MTA (if applicable to your domain)
#   Never claim delivered MMM or MTA models unless they are in your experience_bank.md.
#   Frame as: practical adjacent experience (cite the actual role and outcome) + active self-study.

# RULE 10 — British English
#   Use British spellings throughout.
#   optimisation / modelling / behavioural / prioritise / analyse / organise
#   NEVER: optimization / modeling / behavioral / prioritize / analyze / organize


# ── STEP 6 — EMAIL STRUCTURE (mode=email only) ───────────────

# Subject line:
#   "[Role Title] application — [YOUR_NAME]"
#   (use name from candidate_profile.json → contact.name)

# Salutation:
#   Named recruiter: "Hi [Name],"   ← always "Hi", never "Dear" — even in email
#   Unnamed:         "Hi [Company] Team,"

# Opening paragraph (if already applied via LinkedIn / Easy Apply):
#   "I have just submitted my application for the [Role] position at [Company] via
#    LinkedIn and wanted to follow up directly as well."

# Body (2–3 short paragraphs):
#   Para 1: Genuine interest in company + specific role mandate (from JD or tracker notes)
#   Para 2: Most relevant experience mapped to the role — specific, with metric
#   Para 3: Relocating sentence (market-appropriate, RULE 2 pattern)

# Closing line (Easy Apply — documents on LinkedIn):
#   "My CV and cover letter are attached to the LinkedIn application; I am happy to
#    provide them separately should that be more convenient."

# Sign-off:
#   "Kind regards,
#    [YOUR_NAME]
#    [YOUR_PHONE] | [YOUR_EMAIL]"
#   (use contact info from candidate_profile.json → contact)
#
#   IMPORTANT: Always output phone as placeholder if real phone is not configured — never fabricate.

# Tone: Formal throughout. No contractions. No casual phrasing.


# ── STEP 6.5 — REFINEMENT LOOP (before storing) ─────────────
# After displaying the draft, wait for user response.
# Do NOT log to application_qa_log.json yet.
#
# If user requests a refinement:
#   1. Apply it and display updated answer
#   2. Classify the correction type:
#        honesty  — overstated match, wrong relocating framing, wrong visa name
#        content  — missing context (e.g. forgot key product detail), wrong platform
#        tone     — too casual, not formal enough, wrong length
#        framing  — AI project tense wrong, prohibited term used
#        style    — approved email pattern not followed
#   3. Update data/content/application_qa_bank.md — amend the relevant snippet
#      so the bank reflects the corrected version for future drafts
#   4. If the correction reveals a missing rule (not already in STEP 5):
#        Surface to user: "[skill] Suggested new rule: <rule summary>. Add to skill file? (Y/n)"
#        Write to skill file ONLY on explicit Y — never auto-add
#        NOTE: User may later instruct auto-approval — until then, always ask first
#   5. Carry corrections forward within this session automatically — do not require
#      the user to repeat the same correction for a different question
#
# User signals answer is final by:
#   Explicit: "final", "good", "done", "use this", "perfect", or similar
#   Implicit: moving on to a new question or task


# ── STEP 7 — STORE TO Q&A LOG (final answer only) ────────────
# Read data/application_qa_log.json.
# Create file with {"log": []} if absent.
# Append:
# {
#   "company":    "<company>",
#   "role":       "<role>",
#   "job_id":     "<job_id>",
#   "market":     "<market>",
#   "date":       "YYYY-MM-DD",
#   "type":       "application_question" | "recruiter_email" | "recruiter_dm",
#   "question":   "<question text for application_question>
#                  OR <recruiter call-to-action prompt that triggered the email/DM>",  // ALL types
#   "recipient":  "<name or email>",       // type=recruiter_email/dm only
#   "subject":    "<subject>",             // type=recruiter_email only
#   "content":    "<full final answer or email body>"
# }
# Write back.
# Log: "[qa_log] Stored [type] for [Company] / [Role] → data/application_qa_log.json"


# ── OUTPUT ───────────────────────────────────────────────────
# 1. Display full drafted answer / email / DM to user
# 2. After final confirmation:
#    "[qa_log] 1 entry appended → data/application_qa_log.json"


# ── CONSTRAINTS ──────────────────────────────────────────────
# NEVER fabricate experience, metrics, or skills.
# NEVER modify metrics from experience_bank.md.
# NEVER mention: Google Analytics, Firebase, Apache Airflow (outside role bullets).
# NEVER reveal the application domain of the AI project.
# NEVER say "in the process of relocating".
# NEVER assign a wrong data platform to an employer.
# NEVER write a real phone number — always use the placeholder format from candidate_profile.json.
# ALWAYS draw from experience_bank.md for claims about work experience.
# ALWAYS use British English spellings.
# ALWAYS store only the final version to the Q&A log, never drafts.
