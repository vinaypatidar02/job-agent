# Skill: score_job
# Stage 3 — ACTIVE
#
# ============================================================
# LEARNING NOTE — What is a Skill file?
# ============================================================
# A skill is a self-contained prompt template invoked by agents.
# It receives structured input, does one job, returns structured
# output. It has no side effects — it does not write files or
# update the tracker. The calling agent handles that.
# ============================================================

# ── INPUT ────────────────────────────────────────────────────
# A single enriched job object from enrich_jobs.py output.
# Key fields (curious_coder/linkedin-jobs-scraper actor + enrichment):
#   job_title, company_name, location, job_url, job_id
#   salary (native, often empty), job_type, posted_date
#   description (full JD text)
#   compensation_extracted.display / .lower / .upper / .currency
#   experience_years.display / .min_yrs / .max_yrs
#   work_mode ("Remote" | "Hybrid (Xd/week)" | "On-site" | "Unknown")
#   ats_type, is_easy_apply, career_page_url (null unless in description)
#
# Jobs arrive pre-sorted newest-first from enrich_jobs.py.
# Process them in the order received — do not re-sort.

# ── INSTRUCTIONS ─────────────────────────────────────────────
# Step 1 — DUPLICATE CHECK — 3-signal check (before scoring, every time)
#   Read data/job_tracker.json. Check ALL three signals:
#     a. job_url exact match against any entry's jd_url
#     b. career_page_url exact match (if not null)
#     c. Fuzzy match: company_name + job_title within edit distance 2
#        against company + role fields of existing entries
#   If ANY signal matches → STOP. Return:
#     { "action": "skip", "reason": "duplicate",
#       "matched_id": "<existing id>", "matched_status": "<status>" }
#   Log: "DUPLICATE SKIPPED: [company] / [role] — already exists as [status]"
#
# Step 2 — SCORE the job using the rubric in CLAUDE.md Section 4.
#   Read each dimension carefully from the JD description text:
#
#   ROLE TITLE MATCH (0–20):
#     Compare job_title against target roles in CLAUDE.md Section 3.
#     20 = exact / near-exact match to listed target roles
#     10 = adjacent (Data Lead, Insights Manager, etc.)
#      0 = unrelated
#
#   DOMAIN MATCH (0–25):
#     Infer industry from company_name + description.
#     25 = product-led: tech, fintech, ecommerce, marketplace, SaaS
#     15 = other tech or data-heavy (media, logistics, healthtech)
#      5 = services / consulting / agency
#      0 = unrelated (manufacturing, public sector, etc.)
#     NOTE: If non-product company, only shortlist if score ≥ 88
#     overall AND company is well-known (FTSE 250 equivalent).
#
#   SKILLS MATCH (0–25):
#     Scan description for: SQL, Python, Tableau, BigQuery, Redshift,
#     Looker, Looker Studio, GA4, Firebase, Airflow, experimentation,
#     A/B testing, CRM analytics, pricing, segmentation, propensity.
#     25 = 7+ match  |  15 = 4–6 match  |  5 = 1–3 match
#
#   SENIORITY MATCH (0–15):
#     Use experience_years.min_yrs and description context.
#     15 = Lead/Manager level, 5–10 years expected
#     10 = slightly senior (Principal, Director-adjacent) but reachable
#      5 = slightly junior but interesting scope
#      0 = clear mismatch (entry-level or VP+)
#
#   LOCATION (0–10):
#     Match location field against CLAUDE.md Section 3 Tier list.
#     10 = London
#      8 = Manchester / Birmingham
#      6 = Leeds / Reading / Milton Keynes / Cambridge / Oxford /
#           Leicester / Coventry / Nottingham / Northampton / Salford /
#           Liverpool / Warrington / Solihull / Bradford / York /
#           Welwyn Garden City / St Albans / Hatfield
#      0 = Tier 3 (Bristol/Brighton/Luton/Watford/Slough/Guildford/Woking/
#           Newbury/Derby/Sheffield/Cheltenham/Southampton) — requires score ≥ 85
#           AND explicitly remote/hybrid; or outside all tiers → auto-reject
#     If work_mode = "Remote" AND location is UK → score 8 minimum.
#
#   VISA SPONSORSHIP (0–5, or -10):
#      5 = explicitly stated in JD ("visa sponsorship available" etc.)
#      3 = company is a known UK Skilled Worker sponsor
#          (check well-known companies: HSBC, Monzo, Wise, Google etc.)
#      0 = no mention → flag "Sponsorship Unconfirmed", do not reject
#    -10 = explicitly states no sponsorship → TOTAL SCORE becomes 0,
#          status = "Auto-Rejected", reason = "No visa sponsorship"
#
# Step 3 — SALARY GATE: check against your configured threshold (CLAUDE.md §3 / score_jobs.py USER CONFIG)
#   Use compensation_extracted if available, else native salary field.
#     - Upper end > [YOUR_SALARY_THRESHOLD] → salary gate PASSED (even if lower end is below)
#     - Both ends < [YOUR_SALARY_THRESHOLD] → salary gate FAILED → auto-reject
#     - Single figure < [YOUR_SALARY_THRESHOLD] → auto-reject
#     - Not stated / "Competitive" → flag "Salary TBC", do not reject
#
# Step 4 — DECIDE
#   TOTAL = sum of all 5 dimensions (visa can make total 0)
#   ≥ 75 AND visa not rejected AND salary gate passed/TBC → "Shortlisted"
#   60–74                                                 → "Review Needed"
#   < 60 OR visa rejected OR salary gate failed           → "Auto-Rejected"
#   Duplicate detected (Step 1)                           → "skip"

# ── CONTRACT / EOR SCORING RULES ─────────────────────────────
# If is_contract=true (detected from job_type="contract" or JD keywords):
#   - visa_sponsorship_status = "EOR" (candidate engages via Employer of Record;
#     no employer visa sponsorship needed)
#   - visa_score = 5 (same as Confirmed)
#   - EXCEPTION: if JD explicitly states "no overseas contractors", "must have
#     right to work as employee", or "IR35 inside [firm employees only]" →
#     visa_sponsorship_status = "Rejected", visa_score = -10
#
# If is_remote_only=true OR work_mode="Remote":
#   - location_score = 10 for ALL job locations (remote is timezone-agnostic;
#     your location aligns with target market business hours)
#
# role_type = compute from is_contract × is_remote_only:
#   is_contract=true  + is_remote_only=true   → "contract_remote"
#   is_contract=true  + is_remote_only=false  → "contract_hybrid"
#   is_contract=false + is_remote_only=true   → "permanent_remote"
#   is_contract=false + is_remote_only=false  → "permanent_hybrid"
#
# eor_viability (integer 1–10, null for permanent non-remote roles):
#   8–10: async-friendly, startup/scale-up, senior IC scope, no mandatory onsite
#   5–7:  hybrid, mid-size, some office expectation
#   1–4:  mandatory onsite, regulated entity requiring employee status,
#         "no contractors" language
#   Set eor_viability=null for permanent_hybrid roles.

# ── OUTPUT ───────────────────────────────────────────────────
# Return a JSON object with this exact shape:
# {
#   "action": "shortlist" | "review" | "reject" | "skip",
#   "job_id": "<from input>",
#   "company": "<company_name>",
#   "role": "<job_title>",
#   "location": "<location>",
#   "jd_url": "<job_url>",
#   "fit_score": <0–100 integer>,
#   "fit_score_breakdown": {
#     "role_title": <0–20>,
#     "domain": <0–25>,
#     "skills": <0–25>,
#     "seniority": <0–15>,
#     "location": <0–10>,
#     "visa_sponsorship": <-10–5>
#   },
#   "visa_sponsorship_status": "Confirmed" | "EOR" | "Unconfirmed" | "Rejected",
#   "salary_stated": "<compensation_extracted.display or native salary or 'Not stated'>",
#   "salary_gate": "passed" | "failed" | "tbc",
#   "salary_meets_threshold": true | false | null,
#   "work_mode": "<from enrichment>",
#   "is_contract": <bool>,
#   "is_remote_only": <bool>,
#   "role_type": "contract_remote" | "contract_hybrid" | "permanent_remote" | "permanent_hybrid",
#   "eor_viability": <1–10 integer or null>,
#   "experience_req": "<experience_years.display>",
#   "ats_type": "<from enrichment>",
#   "is_easy_apply": <bool>,
#   "career_page_url": "<from enrichment or null>",
#   "posted_date": "<from input>",
#   "rejection_reason": "<if rejected: brief reason>" | null,
#   "flags": ["Salary TBC", "Sponsorship Unconfirmed", ...]
# }

# NOTE: After the calling agent writes to job_tracker.json,
# it must run: python3 scripts/sheets_sync.py push --tabs apps,archive
# This skill does not do that directly — the agent does.

# ── CONSTRAINTS ───────────────────────────────────────────────
# NEVER shortlist a job where visa sponsorship is explicitly denied.
# NEVER shortlist a job outside the accepted location tiers.
# NEVER skip the duplicate check — run it for every single job.
# NEVER fabricate or assume skills not mentioned in the JD.
# When in doubt between "shortlist" and "review", choose "review".
# Always include reasoning in fit_score_breakdown, not just numbers.
