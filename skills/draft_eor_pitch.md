# Skill: draft_eor_pitch
# Stage 4 — ACTIVE
#
# ============================================================
# PURPOSE
# ============================================================
# Draft outreach for contract_remote roles where the candidate
# pitches as a zero-overhead remote contractor via EOR
# (Employer of Record: Deel or Remote.com).
#
# Two outputs:
#   A. LinkedIn Connection Note  (≤300 chars, hard limit)
#   B. Short Cover Email         (≤150 words; Subject + body)
#      — for agency recruiter / TA / hiring manager direct outreach
#
# Trigger: "draft EOR pitch [job_id]"
# Exit with warning if role_type ≠ "contract_remote".
# ============================================================

# ── STEP 0 — GUARD ───────────────────────────────────────────
# Read data/job_tracker.json.
# Find entry by job_id (or app_id / company / role if no job_id given).
# Check role_type field.
#
#   If role_type ≠ "contract_remote":
#     Print: "[draft_eor_pitch] ⚠ Skipped — role_type={role_type} is not contract_remote.
#             EOR pitch only applies to fully remote contract roles."
#     Stop. Do not draft anything.
#
#   If role_type = "contract_remote": proceed.
#
# Fields to extract from tracker entry:
#   company, role, fit_score, eor_viability, location, market, salary_stated

# ── STEP 1 — CONTEXT ─────────────────────────────────────────
# Log the entry details for the user:
#   "[draft_eor_pitch] contract_remote: [Company] / [Role]
#    fit_score=[X]  eor_viability=[Y]  salary=[Z]  location=[L]"
#
# If eor_viability ≤ 4:
#   Print a soft warning:
#   "[draft_eor_pitch] ⚠ eor_viability={eor_viability} — low EOR suitability
#    (mandatory onsite or regulated entity flagged in JD). Pitch may not land well.
#    Proceed? (Y/n)"
#   Wait for confirmation before drafting.

# ── STEP 2 — DRAFT CONNECTION NOTE (Type A) ──────────────────
# ≤300 chars HARD LIMIT. Count precisely.
#
# Structure:
#   [SENIORITY HOOK — 1 sentence: [YOUR_YEARS]+ years + domain + relevant to this company]
#   [ZERO-COMPLIANCE PITCH — 1 sentence: available as remote contractor via EOR]
#   [CALL TO CONNECT — closing hook from draft_referral_message.md §closing hooks]
#
# EOR pitch phrasing (adapt to char count — do not exceed 300):
#   "Available as a remote contractor via EOR (Deel/Remote.com) — zero compliance
#    overhead on [Company]'s end."
#
# Closing hook options (pick whichever fits char budget):
#   "Always good to have a conversation with someone working in the same space
#    before applying."     ← for domain-matched contacts
#   "Always good to know someone inside a company before applying."
#                          ← for non-domain contacts
#
# Output format:
#   Draft (NNN/300 chars):
#   [message text]

# ── STEP 3 — DRAFT COVER EMAIL (Type B) ──────────────────────
# ≤150 words. Subject line + body. For TA / recruiter / hiring manager.
#
# Subject: "Senior Analytics Contractor — [Company] | Immediate Availability via EOR"
#   Adapt if you know the recruiter handles this role specifically:
#   "Re: [Role title] at [Company] — Senior Analytics Contractor, EOR"
#
# Body structure (5 short sections, 120–150 words total):
#
#   Hi [Name / Hiring Team],
#
#   [INTRO — 1 sentence: [YOUR_YEARS]+ years in [YOUR_DOMAIN] at product-led companies
#    ([YOUR_INDUSTRY_1], [YOUR_INDUSTRY_2]). Keep to actual industries from candidate_profile.json only.]
#
#   [FIT — 1-2 sentences: one specific signal from the JD + one metric from
#    the most relevant work_history bullet. NEVER fabricate.]
#
#   [EOR ARRANGEMENT — 1-2 sentences:
#    "I engage as a fully remote contractor via an Employer of Record (Deel or
#     Remote.com) — zero compliance or employment law overhead on your side.
#     6+ hours daily UK/CET overlap guaranteed."]
#
#   [AVAILABILITY — 1 sentence: "Available immediately or within two weeks."]
#
#   [CTA — 1 sentence: "Happy to share my CV or jump on a call — let me know."]
#
#   Best,
#   [YOUR_NAME]
#   [YOUR_PHONE]  |  [YOUR_EMAIL]
#   (use contact info from candidate_profile.json → contact)
#
# Word count: show total words before asking for confirmation.

# ── STEP 4 — REFINEMENT LOOP ─────────────────────────────────
# Display both drafts and wait for user response. Do NOT log yet.
#
# If user requests revision: apply and redisplay.
# User signals final by: "good", "use this", "send", "done", or moving on.

# ── STEP 5 — LOG (on confirmation) ───────────────────────────
# Append to data/referral_outreach_log.json (same format as draft_referral_message.md):
# {
#   "logged_date":      "YYYY-MM-DD",
#   "company":          "<company>",
#   "role":             "<role>",
#   "job_id":           "<job_id>",
#   "contact_name":     "<name or 'Hiring Team'>",
#   "contact_role":     "<recruiter/TA/hiring manager or null>",
#   "contact_location": null,
#   "relationship":     "cold",
#   "connection_degree": null,
#   "channel":          "linkedin | email",
#   "contact_type":     "recruiter | employee",
#   "agency_name":      null,
#   "subject":          "<email subject or null for connection note>",
#   "message_type":     "eor_pitch_connection | eor_pitch_email",
#   "message_text":     "<final confirmed message text>",
#   "char_count":       <int>,
#   "refinement_notes": null,
#   "outcome":          null
# }
# Create file with {"_meta": {...}, "messages": []} if absent.
#
# Log: "[eor_pitch] Saved: [Company] / [Role] → [message_type]"

# ── CONSTRAINTS ───────────────────────────────────────────────
# NEVER use if role_type ≠ "contract_remote".
# NEVER mention visa, sponsorship, relocation, or right to work.
# NEVER exceed 300 chars for connection note — count precisely.
# NEVER exceed 150 words for cover email.
# NEVER fabricate metrics, industries, or company facts.
# ALWAYS use British English spellings.
# ALWAYS draw experience claims from experience_bank.md.
# NEVER reveal the AI pipeline application domain (use neutral terms:
#   "data ingestion", "document generation", "automated status tracking").
# NEVER write a real phone number — use "+91-XXXXXXXXXX".
