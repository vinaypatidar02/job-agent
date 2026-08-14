# Skill: tailor_resume
# Stage 3 — LEGACY FALLBACK
#
# ============================================================
# NOTE: The main pipeline uses agents/application_prep.md +
# scripts/auto_prep.py instead of this skill directly.
# Use this skill only for ad-hoc one-off resume tailoring
# outside the standard application prep flow.
#
# Content source: data/content/experience_bank.md (not the PDF variants).
# The three PDF files (master_resume.pdf, product_resume.pdf,
# customer_resume.pdf) are reference documents — not pipeline
# inputs. Domain detection is done from JD text, not by reading
# a PDF. See auto_prep.py for the authoritative domain logic.
# ============================================================

# ── INPUT ────────────────────────────────────────────────────
# {
#   "job": <score_job.md output object>,
#   "jd_text": "<full job description text>"
# }

# ── STEP 1 — DETECT JD DOMAIN ────────────────────────────────
# Read the JD text and classify into one of the domains defined in
# candidate_profile.json → domains (see CONFIGURE_CHECKLIST.md § Step 2).
#
# Default domain examples (analytics profession):
#   product/growth/ecommerce/marketplace/SaaS → product domain
#   CRM/retention/lifecycle/customer/marketing → crm domain
#   commercial/pricing/operations             → pricing domain
#   BI/insights/reporting/general analytics   → bi domain
#   Ambiguous or thin JD                      → general domain (broad bullet pool)
#
# Update these classifications in candidate_profile.json → domains for your profession.
# Do NOT open or read any PDF file — the PDF variants are reference documents only.

# ── STEP 1b — READ EXPERIENCE BANK (PRIMARY CONTENT SOURCE) ──
# Read data/content/experience_bank.md using the Read tool.
# This file contains ALL bullet points across all roles, tagged by domain.
# Use it as the PRIMARY source of bullet content — it supersedes the PDF variant
# for bullet selection. The PDF variant signals which bullets were previously
# emphasised in that domain, but the bank is the full set to choose from.
#
# BULLET SELECTION RULES (apply after reading the bank):
#   1. ALWAYS INCLUDE — pinned/priority project entry (first role, all bullets, never trim)
#   2. ALWAYS INCLUDE — leadership bullets for Lead/Manager-level JDs
#      (e.g. "team of N at [Company B]", "team of M at [Company C]")
#   3. ALWAYS PRESERVE — all numeric metrics exactly as written in experience_bank.md
#   4. DOMAIN PRIORITY — prioritise bullets whose tags match the JD domain
#      (domain tags are defined in candidate_profile.json → resume_tags)
#   5. SUPPORTING EVIDENCE — include cross-domain bullets if space allows (shows breadth)
#   6. 2-PAGE LIMIT — if content overflows, trim lower-priority bullets from the
#      earliest role first, never drop a role entirely (keep ≥1 bullet per role minimum)
#   NOTE: Bullets marked <!-- ADD: --> are placeholders the user will fill in —
#   skip empty placeholder lines, include any real bullets the user has added

# ── STEP 1c — SELECT CORE EXPERTISE & SKILLS ─────────────────
# Apply these rules BEFORE writing the output JSON. Do not leave either field
# to free-form judgment — select from the defined pools in candidate_profile.json.
#
# ── CORE EXPERTISE ────────────────────────────────────────────
# Always produce 8–10 items. Lead with domain-primary items, end with pinned.
#
# PINNED (always include, appear last in the list):
#   — Use the pinned expertise items from candidate_profile.json → profile.target_roles
#     or the user-designated pinned expertise in their profile.
#
# DOMAIN-PRIORITISED (pick from pools in candidate_profile.json → domains):
#   For each detected JD domain, read the expertise items listed under that domain.
#   Primary domain: pick all primary expertise items.
#   Secondary domain (if mixed JD): add 2–3 items from the secondary domain.
#
#   Example pattern (analytics profession — adapt for your domains):
#     Product / growth JD → Product Analytics, Growth Analytics, Experimentation
#     CRM / lifecycle JD  → CRM Analytics, Customer Lifecycle Analytics, Retention Analytics
#     Commercial JD       → Pricing & Commercial Optimisation, Analytics Transformation
#     BI / insights JD    → KPI Strategy & Business Intelligence, Analytics Transformation
#
#   Leadership emphasis (Lead/Manager-level JD, any domain):
#     ALWAYS ADD if not already in primary: Stakeholder Management, Strategic Decision-Making
#
#   GOVERNANCE / CAPABILITY-BUILDING JDs (trigger — JD contains ANY of):
#     "center of excellence", "CoE", "data governance", "data literacy",
#     "data democratization", "[YOUR_DOMAIN] capability", "data maturity",
#     "[YOUR_DOMAIN] transformation", "data culture", "data enablement",
#     "AI workflow integration", "analytics pods", "cross-functional pods"
#
#     Add 1–2 most relevant to the expertise list (do NOT exceed 10 total including pinned):
#       "[YOUR_DOMAIN] Capability Building"
#       "Data Governance & Literacy"
#       "[YOUR_DOMAIN] Transformation"
#
# ── SKILLS ────────────────────────────────────────────────────
# Compose the skills list from candidate_profile.json → core_skills + conditional tools:
#
#   CORE — always include: items in candidate_profile.json → core_skills.skills
#
#   CONDITIONAL — include only if JD explicitly mentions the associated keywords:
#     (define these in candidate_profile.json for your own tool stack)
#
#   PINNED — always include, always at end of list:
#     Items marked "pinned" in candidate_profile.json
#
#   NOT IN POOL — never list tools you cannot defend in an interview:
#     items in candidate_profile.json → profile.excluded_tools
#
#   NEVER add tools outside your profile (fabricating tools is disqualifying)

# ── STEP 2 — EXTRACT JD KEYWORDS ─────────────────────────────
# From the JD text, identify:
#   a. Technical skills explicitly mentioned
#   b. Domain keywords
#   c. Seniority signals (lead, manager, head of, cross-functional etc.)
#   d. Industry context
#   e. Specific tools or platforms named
# These keywords will be used to prioritise and rephrase bullet points.

# ── STEP 3 — TAILOR BULLET POINTS ────────────────────────────
# For each role in the base resume:
#   - Move bullets that match JD keywords to the TOP of that role
#   - Rephrase bullets to align terminology with the JD where natural
#     Only change the label of an existing concept — never add ideas or metrics not in the original bullet
#   - Preserve ALL original metrics exactly as written in experience_bank.md
#   - Do NOT fabricate any experience, metric, or skill
#   - Do NOT remove bullets — only reorder and rephrase
#
# SPECIAL FRAMING RULES (update with your own from candidate_profile.json):
#
#   Portfolio project / AI fluency — surface for tech/product JDs:
#     Draw the framing from experience_bank.md pinned project bullets.
#
#   Agile / delivery framework — if JD mentions Agile, Scrum, sprint, delivery:
#     Surface any Agile/project-management bullets from experience_bank.md.
#
#   Team leadership — if JD mentions managing/mentoring/people mgmt:
#     Lead with team sizes from your work history bullets.
#
#   MMM / attribution / advanced analytics — if JD mentions these:
#     NEVER claim delivery experience you don't have. Frame as foundation + active study.

# ── STEP 4 — SUMMARY LINE ────────────────────────────────────
# Rewrite the resume summary (top paragraph) to:
#   - Open with your seniority level — NOT the job posting title.
#     Use the same label as title_lines Line 1 (from candidate_profile.json → headline_by_domain).
#     This is especially important when applying to Tier 2 roles: the summary must still
#     open at Lead/Manager level, not Senior IC level.
#   - RULE (S1): Industries mentioned must come from YOUR actual employer sectors
#     (candidate_profile.json → profile.industry_history). DO NOT use the target company's industry.
#   - S2-S3: describe 1-2 of your actual domain strengths using the work_history
#     bullets already in the resume — do NOT copy JD phrases verbatim.
#     RULE: no phrase in S2-S3 may be lifted word-for-word from the JD.
#   - Keep to 3-4 sentences max
#   - Do not change seniority level or fabricate experience
#   - ALWAYS close with any mandatory differentiator sentences configured in
#     candidate_profile.json → profile.verbatim_sentences

# ── STEP 5 — PROFESSION LINE ─────────────────────────────────
# Generate exactly 2 title_lines for the sidebar under the name.
# These are YOUR professional identity — they must NOT mirror the job posting title
# and must NOT include company- or role-specific language from the JD.
#
#   Line 1: Seniority descriptor — choose from candidate_profile.json → headline_by_domain
#     Max 30 characters. NEVER use the job title from the posting.
#     Use only titles you have genuinely held or that accurately represent your seniority.
#
#   Line 2: 2–3 of your strongest specialties for this JD domain, " · " separated.
#     Max 32 characters. Pick from candidate_profile.json → domains expertise items.
#
#   FORBIDDEN:
#     ✗ Echoing the job title verbatim
#     ✗ Adding company-specific nouns (marketplace, gaming, SaaS, digital)
#     ✗ Lines longer than 32 characters

# ── OUTPUT ───────────────────────────────────────────────────
# Return a JSON object ready to pass to scripts/pdf_renderer.py.
# All personal values come from candidate_profile.json — do NOT hardcode them here.
# {
#   "name": "<contact.name from candidate_profile.json>",
#   "title_lines": ["<Line 1>", "<Line 2>"],
#   "contact": {
#     "email":    "<contact.email from candidate_profile.json>",
#     "phone":    "<contact.phone from candidate_profile.json>",
#     "address":  "<contact.address from candidate_profile.json>",
#     "linkedin": "<contact.linkedin from candidate_profile.json>"
#   },
#   "core_expertise": [<8–10 items — apply STEP 1c domain priority table>],
#   "skills": [<core + conditional (if JD-triggered) + pinned — apply STEP 1c pool rules>],
#   "summary": "<tailored summary paragraph>",
#   "work_history": [
#     {
#       "company": "<name from experience_bank.md>",
#       "location": "<location>",
#       "role": "<role title>",
#       "dates": "<YYYY-MM-YYYY-MM>",   ← pdf_renderer converts to "Apr 2025 – Mar 2026"
#       "bullets": ["<bullet 1>", ...]  ← JD-relevant bullets first
#     }, ...
#   ],
#   "education": [<from candidate_profile.json → education>],
#   "certifications": [<from candidate_profile.json → certifications — priority order>]
# }
# NOTE: List certifications in the order defined in candidate_profile.json.

# ── ROLE TYPE FRAMING (contract vs permanent — read role_type from input JSON) ─
# When auto_prep.py output includes `role_type` and `is_contract` fields, apply:
#
#   contract_remote / contract_hybrid:
#     - title_lines are pre-set by auto_prep.py to CONTRACT_TITLE_LINES — PRESERVE them.
#       Do NOT override with standard TITLE_LINES.
#     - Profile summary S1: replace any visa/sponsorship mention with EOR availability.
#       Example: "…available as a remote contractor via EOR | UK/CET timezone-aligned."
#       Do NOT add EOR/contractor framing to S2–S4 or to any work_history bullet.
#     - S2–S4 (domain strengths, AI closer): unchanged regardless of role_type.
#     - contact.address will contain the EOR address set by auto_prep.py — preserve it.
#
#   permanent_remote / permanent_hybrid:
#     - Use standard TITLE_LINES (from auto_prep.py — they will already be correct).
#     - S1: standard framing (no EOR mentions).
#     - No changes from normal processing.
#
#   Do NOT add EOR/contractor language to skills, core_expertise, or work_history bullets.

# ── CONSTRAINTS ───────────────────────────────────────────────
# NEVER change any metric from experience_bank.md.
# NEVER add a skill or tool not in candidate_profile.json → core_skills.
# NEVER remove a role from work history — only reorder bullets within roles.
# NEVER claim direct delivery experience for frameworks or tools not in your history.
# Keep resume to 2 pages maximum when rendered — trim lower-priority
# bullets from the oldest role if content overflows.
#
# AI PROJECT FRAMING RULE (if applicable to your profile):
# NEVER use terms that reveal the application domain of any portfolio project:
# Use neutral technical terms only:
#   "data ingestion" (not "scraping job listings")
#   "document generation" (not "resume tailoring")
#   "event-driven email processing" (not "email tracking")
# The project's value is the engineering capability — not its specific domain.

# ── PINNED RULES — PORTFOLIO PROJECT & SIDEBAR ───────────────
#
# RULE A — Pinned project entry (if configured in candidate_profile.json → experience):
#   The entry marked pinned: true is ALWAYS included as the first work_history entry.
#   Never omit, compress, or move it lower — it is a mandatory differentiator.
#   All its bullets from experience_bank.md are included without trimming.
#
# RULE B — Sidebar pinned items (NEVER drop to make room for other items):
#   core_expertise must ALWAYS include the items marked pinned in candidate_profile.json
#   skills list must ALWAYS include the items marked pinned in candidate_profile.json
