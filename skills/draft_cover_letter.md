# Skill: draft_cover_letter
# Stage 3 — ACTIVE
#
# ============================================================
# LEARNING NOTE — Skills that call other skills
# ============================================================
# This skill consumes the OUTPUT of tailor_resume.md (the
# tailored resume JSON) plus the JD text. It does NOT re-read
# the base resume PDFs — it works from what tailor_resume
# already selected and prioritised. This avoids duplication
# of work and keeps the cover letter consistent with the resume.
# ============================================================

# ── INPUT ────────────────────────────────────────────────────
# {
#   "job": <score_job.md output object>,
#   "jd_text": "<full job description text>",
#   "tailored_resume": <tailor_resume.md output JSON>,
#   "today": "<YYYY-MM-DD>",
#   "market": "uk" | "nl" | "se" | "de" | "dk" | "ie",   ← determines date-city and Para 4 relocation sentence
#   "work_mode": "Remote" | "Hybrid" | "On-site" | "Unknown",  ← optional; triggers remote framing
#   "is_remote_only": true | false                              ← optional; confirmed remote-only flag
# }

# ── STEP 0 — READ COVER LETTER BANK & ANCHOR TO RESUME ───────
# Read data/content/cover_letter_bank.md using the Read tool BEFORE writing anything.
#
#   Step 0a: Read data/content/cover_letter_bank.md
#
#   Step 0b: Para 2 source — CV work_history bullets from tailored_resume (NOT bank narratives).
#     → Read all work_history bullets from tailored_resume
#     → Rank bullets by: (1) hard quantified metrics, (2) JD keyword overlap
#     → Pick 2-3 highest-impact, most JD-relevant bullets as Para 2 anchors
#     → Synthesize into flowing 120-150 word challenge→action→result narrative
#     → Use cover_letter_bank.md Section 1 as STYLE REFERENCE ONLY — tone and structure;
#       do NOT copy bank text; synthesize fresh from the actual CV bullets
#     → Always include at least one specific metric verbatim. Never fabricate.
#
#   Step 0c: Para 3 source — remaining CV bullets (NOT bank Section 2 themes).
#     → Take remaining work_history bullets NOT anchored in Para 2
#     → If JD-relevant bullets exist covering a different thematic angle from Para 2
#       (e.g. leadership, pricing breadth, experimentation depth), synthesize ~50-60 words
#     → Always close Para 3 with the AI closer sentence (~25-30 words, mandatory):
#       "Beyond this, I bring current hands-on AI engineering capability — having built
#        a production-grade end-to-end agentic automation system using Claude Code, MCP
#        servers, and the Anthropic API, fully operational in production."
#     → Skip the secondary breadth only if no remaining bullets have JD relevance;
#       the AI closer is NEVER skipped
#
#   Step 0d: Para 1 opener (Section 3 of bank):
#     → Match by JD domain (domain-level positioning — not company-specific)
#     → Append a fresh company-specific hook after the opener
#
#   Para 4: always written fresh — never from the bank
#
# RULES:
#   - NEVER change any metric (40%, 30%, 85%, 70/30, 7%, 35%, 37%, 95%)
#   - NEVER fabricate any experience, metric, or company fact
#   - NEVER copy bank Section 1 narratives verbatim into Para 2 — synthesize from CV

# ── INSTRUCTIONS ─────────────────────────────────────────────
# Write a 4-paragraph cover letter (350–450 words) following the
# eBay sample format from CLAUDE.md Section 5.
#
# PARAGRAPH 1 — Role excitement + company alignment + summary (80–100 words)
#   - Start with the matching Para 1 opener from Section 3 of the bank (domain-matched)
#   - Append a fresh, company-specific hook: name the company + exact role title +
#     something specific about the company (product, culture, mission — do not fabricate)
#   FORBIDDEN: "I am writing to apply", "I am excited to apply for this role",
#              any generic opener not naming the specific company
#
# PARAGRAPH 2 — Most relevant experience mapped to JD (120–150 words)
#   - Source: work_history bullets from tailored_resume (selected in Step 0b above)
#   - Synthesize the 2-3 highest-impact, most JD-relevant bullets into flowing prose
#   - Structure: challenge → action → result
#   - Always include at least one specific metric verbatim
#   - Do NOT copy from cover_letter_bank.md Section 1 — synthesize fresh from CV bullets
#   - Use Section 1 only as a style reference for tone and narrative flow
#
# PARAGRAPH 3 — Broader strategic value + AI closer (80–100 words total)
#   Part A — Secondary breadth (~50-60 words, conditional):
#     - Source: remaining work_history bullets NOT anchored in Para 2
#     - Select bullets with a different thematic angle from Para 2
#       (e.g. leadership, pricing, experimentation if Para 2 was CRM/growth)
#     - Synthesize into ~50-60 words showing career breadth
#     - Skip Part A only if no remaining bullets have meaningful JD relevance
#   Part B — AI closer (~25-30 words, ALWAYS mandatory, always last):
#     - "Beyond this, I bring current hands-on AI engineering capability — having built
#        a production-grade end-to-end agentic automation system using Claude Code, MCP
#        servers, and the Anthropic API, fully operational in production."
#     - NEVER omit — it is a mandatory differentiator in every application
#   - If JD mentions MMM/attribution → add in Part A: "strong incrementally foundation
#     + active MMM/MTA study (Robyn, Meridian)" as a single sentence; never fabricate delivery
#
#   Values alignment (ALL markets — every cover letter):
#     BEFORE writing Para 3 — determine whether to fetch values:
#
#       STEP A — Domain check (gate):
#         Extract the domain from career_page_url in the job input.
#         KNOWN THIRD-PARTY ATS DOMAINS (skip fetch if career_page_url matches):
#           greenhouse.io, lever.co, workday.com, myworkdayjobs.com, ashbyhq.com,
#           workable.com, smartrecruiters.com, taleo.net, icims.com, jobvite.com,
#           recruitee.com, bamboohr.com, teamtailor.com, linkedin.com
#         Also skip if:
#           - career_page_url is empty/null (no URL provided)
#           - is_easy_apply = true (LinkedIn Easy Apply — no company domain)
#           - The URL domain does not contain the company name or a recognisable brand
#             subdomain (e.g. "jobs.sonos.com" is fine; "jobs.lever.co/sonos" is not)
#         If skip condition is met: write to meta.json:
#           { "attempted": false, "result": "skipped_no_company_domain", "values_found": [] }
#         Then proceed to Para 3 WITHOUT a values-alignment sentence. Do not guess.
#
#       STEP B — Fetch (only if domain check passes):
#         WebFetch <company-domain>/careers, /about, /values, or /culture — one attempt only.
#         Use the company's OWN domain derived from career_page_url (not a web search).
#         Write to meta.json:
#           { "attempted": true, "result": "success" | "failed",
#             "values_found": ["value1", "value2", ...] }
#         If fetch fails: result="failed", values_found=[] → skip sentence, proceed without.
#
#     THEN in Para 3 Part A (only when values_fetch.result = "success"):
#       1. Select the 1–2 company values most strongly evidenced by the candidate's work history.
#       2. Weave ONE values-alignment sentence into Part A (~20 words):
#            "[Company] values [X] — in my work at [Employer], I [specific action + metric]."
#       3. Draw from the FULL work history (all employers in experience_bank.md) —
#          pick the employer and bullet that best demonstrates the specific value.
#       4. Do NOT fabricate company values — only use what is verifiably stated on their site.
#
#   GOVERNANCE / CAPABILITY-BUILDING SIGNAL (ALL markets — trigger: JD contains ANY of):
#     "center of excellence", "CoE", "data governance", "data literacy",
#     "data democratization", "analytics capability", "data maturity",
#     "AI workflow integration", "analytics pods", "cross-functional pods":
#
#     Include ONE sentence (~20 words) in Part A framing the candidate as a structure-builder.
#     Draw from experience_bank.md — pick the employer with the strongest team leadership
#     and capability-building bullets that overlap with the JD signal.
#     Pick whichever has stronger JD keyword overlap.
#     Example framing (do NOT copy verbatim — synthesize from actual bullets):
#       "I've built analytics capability from the ground up — structuring cross-functional
#        pods, embedding data literacy across operations, and developing high-impact analysts."
#     NEVER fabricate formal CoE programmes, governance frameworks, or org initiatives
#     not grounded in experience_bank.md bullets.
#     Placement: after values-alignment sentence (if present), before the AI closer.
#     The AI closer (Part B) remains ALWAYS last — never displaced by this sentence.
#
# PARAGRAPH 4 — Determined by role_type (read para4_instructions field)
# ─────────────────────────────────────────────────────────────────────────────
# When auto_prep.py output (auto_cover_<id>.json) is available, the cover JSON
# contains a `para4_instructions` field. READ IT and follow those instructions
# exactly for Para 4. Do NOT infer the role type from context — the field is
# authoritative and was set deterministically by auto_prep.py from role_type.
#
# When cover JSON is NOT available (manual / standalone use):
#   - Always written fresh — never from the bank
#   - What specifically excites you about THIS company's mission or product
#   - 1 concrete thing you would want to work on or improve
#   - Professional closing + invitation to discuss
#   - Do not be generic — reference something real about the company
#   - For contract_remote: EOR framing (see _PARA4_INSTRUCTIONS in auto_prep.py)
#   - For permanent roles: market-specific relocation + visa sentence (see below)
#
# ── REMOTE-ONLY / PERMANENT_REMOTE ROLES ──────────────────────────────────────
# (role_type=permanent_remote — work_mode="Remote" OR is_remote_only=true)
# Remote companies do NOT expect the candidate to relocate — frame around remote
# readiness, NOT around visa/relocation logistics as a company obligation.
#
# Para 3 — add one subtle sentence (Part A or before the AI closer):
#   "I am fully set up to contribute remotely from day one, with experience
#    working across distributed teams spanning multiple time zones."
#
# Para 4 — add as an aspirational close (after the CTA, not the main focus):
#   For EU markets (nl/de/dk/ie/se): express personal desire to relocate and
#   pursue the relevant permit independently — keep it aspirational, not transactional.
#   Example: "I am also personally keen to relocate to [country] in the future and
#   would pursue the [EU Blue Card / Kennismigrant / Pay Limit Scheme / CSEP] route
#   independently when the opportunity arises."
#   For UK: omit the relocation sentence for remote roles (the Skilled Worker Visa
#   requires employer sponsorship at point of employment — mentioning it adds friction
#   where the company is not expecting to sponsor).
#
# ── CONTRACT_REMOTE ROLES (role_type=contract_remote) ─────────────────────────
# Para 4 MUST use EOR framing (from para4_instructions field):
#   (1) Immediate availability as remote contractor via EOR (Deel or Remote.com)
#   (2) 6+ daily hours UK/CET overlap
#   (3) One JD-specific company excitement sentence
#   (4) Call to action
# NEVER mention visa sponsorship, relocation, or right to work in Para 4.
# ─────────────────────────────────────────────────────────────────────────────
#
# CLOSING FORMAT:
#   "Kind regards,"
#   [blank line]
#   "[YOUR_NAME]"
#   "[YOUR_PHONE]"
#   "[YOUR_EMAIL]"
#   (use contact info from candidate_profile.json → contact)

# ── OUTPUT ───────────────────────────────────────────────────
# Return a JSON object ready to pass to scripts/pdf_renderer.py:
# {
#   "name": "[candidate name from candidate_profile.json → contact.name]",
#   "title_lines": <same as tailored_resume.title_lines>,
#   "contact": <same as tailored_resume.contact>,
#   "core_expertise": [],   ← empty for cover letter sidebar
#   "skills": [],           ← empty for cover letter sidebar
#   "date": "<City>, <today YYYY-MM-DD>",
#           where City = job's own city (normalised); fallback: Amsterdam (NL), Stockholm (SE), Berlin (DE), Copenhagen (DK), Dublin (IE), London (UK)
#   "recipient": "<Company Name> Hiring Team",
#   "salutation": "Dear Hiring Team,",
#   "paragraphs": [
#     "<paragraph 1 text>",
#     "<paragraph 2 text>",
#     "<paragraph 3 text>",
#     "<paragraph 4 text>"
#   ],
#   "closing": "Kind regards,"
# }

# ── MARKET-SPECIFIC ADJUSTMENTS ─────────────────────────────
# Apply ONLY when market ≠ "uk". Read the market field from the input.
#
# ALL non-UK markets — relocation de-risking (add alongside the permit sentence):
#   If you have prior international relocation experience, reference it here.
#   One clause or short sentence, woven naturally into Para 4. Example:
#   "Having previously relocated internationally for [duration] with [Company],
#    I am confident settling into a new market quickly."
#   This converts "relocation risk" into "proven relocator".
#   FRAMING RULE: always anchor any overseas stint inside the longer employer tenure —
#   never present it as a standalone short job.
#   Draw from experience_bank.md — use only verified facts about your relocation.
#
# DATE LINE (all markets): the JOB's own city + date, e.g. "Utrecht, YYYY-MM-DD"
#   for a Utrecht job. Anchor city (NL=Amsterdam, SE=Stockholm, DE=Berlin,
#   DK=Copenhagen, IE=Dublin, UK=London) is the fallback ONLY when the job
#   location is unknown. auto_prep.py derives this automatically from the
#   tracker location field.
#
# NL (market="nl"):
#   Date line: job city, e.g. "Amsterdam, YYYY-MM-DD" / "Utrecht, YYYY-MM-DD"
#   Para 4:    Add one sentence after the forward-looking content (before closing):
#     "I am actively pursuing a Dutch Highly Skilled Migrant (kennismigrant) permit
#      and am excited to relocate to Amsterdam — this role meets the IND eligibility
#      criteria." (Adjust naturally to fit Para 4 flow, ~25 words)
#   Tone:      Dutch market values directness — outcome-first sentences.
#              Avoid overly deferential phrasing ("I would be honoured to...").
#   Spelling:  UK English throughout (organisation, optimisation, behaviour).
#
# SE (market="se"):
#   Date line: job city, e.g. "Stockholm, YYYY-MM-DD" / "Gothenburg, YYYY-MM-DD"
#   Para 4:    Add one sentence after the forward-looking content (before closing):
#     "I am committed to relocating to Stockholm and plan to apply for a Swedish
#      work permit (arbetstillstånd) — the role meets the ILO salary requirements
#      for permit eligibility." (Adjust naturally to fit Para 4 flow, ~25 words)
#   Tone:      Swedish companies value collaborative achievement — where Para 2/3
#              reference leadership bullets, frame as "leading a team to achieve X"
#              rather than just "led a team". Consensus-building resonates.
#   Spelling:  UK English throughout.
#
# DE (market="de"):
#   Date line: job city, e.g. "Berlin, YYYY-MM-DD" / "Munich, YYYY-MM-DD"
#   Para 4:    Add one sentence after the forward-looking content (before closing):
#     "I am prepared to relocate to Berlin and would apply for an EU Blue Card
#      (Blaue Karte EU) upon receiving a formal offer — my [YOUR_DEGREE] and
#      this role's seniority tier meet the permit eligibility criteria."
#     (Replace [YOUR_DEGREE] with your actual degree from candidate_profile.json → education[0])
#     (~30 words, adjust naturally to Para 4 flow)
#   Tone:      German corporate culture values precision and directness. Outcome
#              statements should be specific and metric-grounded. Avoid effusive
#              or overly warm phrasing ("I would be honoured to...").
#   Spelling:  UK English throughout.
#
# DK (market="dk"):
#   Date line: job city, e.g. "Copenhagen, YYYY-MM-DD" / "Aarhus, YYYY-MM-DD"
#   Para 4:    Add one sentence after the forward-looking content (before closing):
#     "I am committed to relocating to Copenhagen and would apply for a Danish work
#      and residence permit under the Pay Limit Scheme upon receiving an offer —
#      this role's salary level meets the scheme's eligibility threshold."
#     (~30 words, adjust naturally to Para 4 flow; use the job's own city.)
#   NEVER mention the EU Blue Card for Denmark — Denmark opted out of the scheme.
#   Tone:      Danish workplaces value informality with substance — direct,
#              low-hierarchy phrasing; lead with outcomes, skip formal flourishes.
#   Spelling:  UK English throughout.
#
# IE (market="ie"):
#   Date line: job city, e.g. "Dublin, YYYY-MM-DD" / "Cork, YYYY-MM-DD"
#   Para 4:    Add one sentence after the forward-looking content (before closing):
#     "I am excited to relocate to Dublin and would apply for a Critical Skills
#      Employment Permit — analytics roles are on Ireland's Critical Skills
#      Occupations List and this role meets the eligibility criteria."
#     (~28 words, adjust naturally to Para 4 flow; use the job's own city.)
#   Tone:      Irish business culture blends warmth with pragmatism — the standard
#              confident-warm register works; no adjustment needed.
#   Spelling:  UK English throughout.
#
# AE (market="ae"):
#   Date line: job city, e.g. "Dubai, YYYY-MM-DD" / "Abu Dhabi, YYYY-MM-DD"
#   Para 4:    Add one sentence after the forward-looking content (before closing):
#     "I am committed to relocating to Dubai and would complete the UAE employment
#      visa process promptly upon receiving an offer — I am familiar with the
#      requirements and ready to proceed without delay."
#     (~28 words, adjust naturally to Para 4 flow; use the job's own city.)
#   NOTE: The UAE employment visa is employer-sponsored — framing should be that
#     the candidate is ready and willing; never imply a candidate-driven path.
#   Tone:      UAE business culture values directness and efficiency — outcome-first
#              phrasing. Lead with value delivery, close with practical readiness.
#   Spelling:  UK English throughout.
#
# AE CONSTRAINTS: For NL/SE/DE/DK/IE markets: NEVER reference "UK" as a target country.
#   For AE: NEVER reference "UK Skilled Worker Visa", "EU Blue Card", "kennismigrant",
#   or any non-UAE permit. Use "UAE employment visa" / "UAE work permit" only.

# ── BRITISH ENGLISH RULE (all markets) ────────────────────────
# All generated text must use British English spellings throughout.
# Correct forms: optimisation, modelling, behavioural, prioritise, analyse,
#   organise, utilise, visualise, standardise, centralise.
# American variants (optimization, modeling, behavioral, prioritize, analyze,
#   organize, utilize, visualize) must NEVER appear in any cover letter.

# ── CONSTRAINTS ───────────────────────────────────────────────
# NEVER open with a generic sentence. Company name must appear in sentence 1.
# NEVER fabricate company facts — only reference what is verifiably known.
# NEVER claim direct MMM/MTA delivery experience.
# NEVER use the same opening verb/phrase as another cover letter — vary them.
# Use UK English spelling throughout (organisation, optimisation, behaviour).
# For NL/SE/DE/DK/IE/AE markets: NEVER reference "UK" as a target country, "right to work in
#   the UK", "Skilled Worker Visa", or any UK-market context. Each market uses ONLY its own
#   permit language: NL=kennismigrant, SE=arbetstillstånd, DE=EU Blue Card,
#   DK=Pay Limit Scheme (never Blue Card), IE=Critical Skills Employment Permit,
#   AE=UAE Employment Visa / Work Permit (never EU Blue Card or kennismigrant).
#
# AI PROJECT FRAMING RULE:
# NEVER use terms that reveal the application domain of the AI Engineering Project:
# no "job application", "job search", "resume tailoring", "cover letter", or
# "job search automation". Use neutral technical terms only:
#   "data ingestion" (not "scraping job listings")
#   "document generation" (not "resume tailoring")
#   "event-driven email processing" (not "email tracking")
# The project's value is the agentic engineering capability — not its specific domain.
#
# WORD LIMIT: 350–450 words across all 4 paragraphs combined. Count before outputting.
#   True constraint is 1 page — 350-450 is a calibrated proxy from the eBay sample (~420 words).
#   If over 450: trim Para 3 Part A first (secondary breadth), then Para 4. Never trim Para 2 or Para 1.
#   If under 350: expand Para 4 (the company-specific closing paragraph).
#   Remove filler phrases ("I am confident that", "I would be delighted to", etc.).
#   Every sentence must carry new information — no repetition of points already in the
#   resume summary.
