# Skill: draft_referral_message
# Stage 4 — ACTIVE
#
# ============================================================
# PURPOSE
# ============================================================
# Draft LinkedIn connection request notes and referral request messages
# for warm/cold outreach to contacts at target companies.
#
# Handles two outputs:
#   A. LinkedIn connection request note  (≤300 chars, hard limit)
#   B. Referral request message          (LinkedIn DM / InMail / email)
#
# Claude recommends which type to send based on relationship context,
# then drafts the message(s). Honesty rules 1–10 from
# draft_application_response.md apply in full — cross-referenced below.
# ============================================================

# ── INPUT ────────────────────────────────────────────────────
# Natural language — no rigid format required. Fields Claude uses:
#
#   id / job_id:        "app_247" or "4444772917"  ← PREFERRED — unambiguous lookup in tracker
#   company:            "LEGO Group"               ← alternative if id not provided
#   role:               "Analytics Manager"        ← optional; disambiguates multi-entry
#   contact_linkedin:   "linkedin.com/in/..."      ← if provided, Claude reads the profile
#                                                     and auto-fills name / role / location /
#                                                     connection_degree (see Step 1b)
#   contact_name:       "Priya Sharma"             ← auto-filled from profile if URL given
#   contact_role:       "Analytics Manager"        ← auto-filled from profile if URL given
#   contact_location:   "Copenhagen"               ← auto-filled from profile if URL given
#   connection_degree:  "1st" | "2nd" | "3rd" | "not connected"  ← auto-filled if URL given
#   contact_nationality:"Indian"                   ← always manual; triggers struggle narrative
#   relationship:       "[YOUR_ALUMNI_NETWORK] alumni" | "ex-[Company A]" | "ex-[Company B]" | "ex-[Company C]"
#                       | "[YOUR_ALUMNI_NETWORK] junior" | "mutual connection" | "cold"  ← always manual
#   channel:            "linkedin" | "email"       ← optional; default = linkedin
#   contact_type:       "employee" | "recruiter"  ← default "employee"
#                       employee  — internal employee who can trigger a referral bonus
#                       recruiter — agency recruiter who posted the job (gatekeeper, not referrer)
#   agency_name:        "Harnham"                  ← recruiter type only; the agency name
#                       (company may be unknown for agency-posted roles; agency_name goes here)
#                       CLASSIFICATION RULE (applied at Step 3b pre-flight):
#                         Type=recruiter + Agency BLANK  → internal HR/TA at the hiring company
#                                                           Apply §4 HR/Talent Acquisition rules.
#                         Type=recruiter + Agency FILLED → external recruiter at that agency
#                                                           Apply §4 Recruiter (external agency) rules.
#   is_potential_hiring_manager: true | false | auto (default = auto)
#                       auto  = Claude infers by comparing contact_role to JD "Reports To" field
#                               or by matching contact title to the role's functional department head.
#                               Triggers when the match is plausible but not certain.
#                       true  = user explicitly flags this contact as likely the hiring manager
#                       false = user explicitly disables this flag
#                       Effect: Connection note first (Type A), then Type B-HM DM after acceptance.
#                               NEVER InMail — always Connect path. See §4 B-HM and Scenario 1/2.
#                               Confirmed HM ask: "I'd welcome a fair chance to be considered on my merits."
#                               Inferred HM ask: "I'd appreciate a fair chance to be considered —
#                               and if I've reached the wrong person, I'd be genuinely grateful
#                               for a pointer in the right direction."
#                       Never state with confidence — always soft inference in the message.
#
# ── STANDARD CONTACT TABLE FORMAT ───────────────────────────
# Users typically provide contacts in this tabular format.
# Commonly filled fields first; conditional/optional fields last.
# Copy-paste template — leave blank fields empty (Claude uses defaults):
#
#   Field          Value
#   ─────────────────────────────────────
#   Job            app_XXXX  ← blank for C-General (no specific role in play)
#   Profile        https://www.linkedin.com/in/...
#   Relationship   cold | mutual | [YOUR_ALUMNI_NETWORK] alumni | ex-[Company A] | ex-[Company B] | ex-[Company C]
#   Nationality    Indian  ← only fill if confirmed Indian; leave blank otherwise
#   Channel        linkedin | email
#   Applied        yes | no  ← blank = auto-detect from tracker (Applied/Under Review/Interview = yes;
#                               Approved/Prep Complete/Referral-Planned = no). For is_relevant=yes
#                               contacts always "no" (framing defaults to "before applying"). N/A for
#                               C-General (no specific role — Claude infers from context).
#   Is Relevant    yes | no  ← can this contact bypass the ATS gate? leave blank = auto-detect
#                               Both field names accepted ("Relevant" and "Is Relevant" are aliases).
#                               Auto-detect: yes if Type=recruiter OR Potential HM=yes OR
#                               contact role contains TA/HR/People/Recruitment keywords
#   Potential HM   yes | no  ← leave blank for auto-detection
#   Type           employee | recruiter  ← leave blank for default (employee)
#   Agency         ← recruiter type only; blank = internal HR/TA at hiring company
#   Via            app_XXXX  ← optional; job that surfaced this contact when NOT applying for it
#                               Provides hook context (roles they cover) without implying application
#
# Job identifier: id/job_id is preferred (exact match in tracker "id" or "job_id" field).
# If not provided, fall back to company name fuzzy match, narrowed by role if given.
# With a LinkedIn URL, contact_name is no longer required upfront — Step 1b fills it.
# Only relationship always needs user input. Ask only when missing context materially
# changes the hook or message type.


# ── STEP 1 — RESOLVE JOB AND CONTACT ────────────────────────
# Read data/job_tracker.json.
# Lookup priority:
#   1. If user provided id / job_id: match against tracker "id" field (e.g. "app_247")
#      OR "job_id" field (e.g. LinkedIn numeric ID "4444772917") — exact match, no ambiguity.
#   2. Otherwise: fuzzy match on company name, narrow by role if provided.
# Extract: market, role, location, job_id, notes.
#
# Read data/outreach.json — check if contact already has an entry for this job.
# If yes, note existing status and avoid duplicate logging.
#
# Log: "[referral] Resolved: [Company] / [Role] (id: <app_id>, job_id: <job_id>, market: <market>)"


# ── STEP 1b — READ LINKEDIN PROFILE (if URL provided) ────────
# Only run this step if contact_linkedin URL was provided.
#
# Load browser tools (single ToolSearch call):
#   select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__tabs_create_mcp,
#          mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__read_page
#
# 1. Call tabs_context_mcp — check if LinkedIn is already open and user is logged in.
# 2. Create a new tab (tabs_create_mcp) and navigate to the profile URL.
# 3. Read the page (read_page). LinkedIn is JS-rendered — if the page returns a login
#    wall or near-empty content, stop and inform the user:
#      "LinkedIn profile couldn't be read — are you logged in to LinkedIn in Chrome?
#       Please share the contact's name, role, location, and connection degree manually."
#    Do NOT retry or loop.
# 4. If profile content is readable, extract:
#      contact_name        — full name from profile header
#      contact_role        — current job title + company (first position listed)
#      contact_location    — location shown on profile
#      connection_degree   — "1st", "2nd", or "3rd" (shown as badge when logged in)
#      is_potential_hiring_manager — auto-flag by comparing contact_role to JD "Reports To" field
#        Match logic (all approximate — never confident):
#          - Contact title contains or is close to the value in JD "Reports To" field
#          - Contact title is "Head of / Director of / VP" for the same function as the role
#        If match found: set is_potential_hiring_manager = true; note in pre-flight.
#        If no JD "Reports To" available: flag if contact is a senior function head (Head+).
#        Default false when in doubt — don't over-trigger.
# 5. Present extracted fields to user for confirmation before proceeding:
#      "[referral] Profile read — please confirm:
#        Name:       <extracted>
#        Role:       <extracted title> at <extracted company>
#        Location:   <extracted>
#        Connection: <1st/2nd/3rd>
#       Anything to correct? Also please share: relationship type (e.g. [YOUR_ALUMNI_NETWORK] alumni,
#       ex-[Company A], cold) and contact nationality if Indian."
# 6. Wait for user confirmation/corrections before proceeding to Step 2.
#
# Fields NOT available from LinkedIn profile — always ask user:
#   relationship        — the shared context (alumni, ex-colleague, cold)
#   contact_nationality — never infer from name; only use if user confirms "Indian"
#
# Log: "[referral] LinkedIn profile read: <name> / <role> / <location> / <degree>"
#   or "[referral] LinkedIn profile unreadable — manual input required"


# ── STEP 2 — LOAD JD TEXT ────────────────────────────────────
# Run: python3 scripts/fetch_jd.py --job_id <job_id>
# Use JD text for company-specific detail in the hook (why THIS company).
# If unavailable (source=not_found), use tracker metadata only.
# Log: "[referral] JD text loaded" or "[referral] JD unavailable — using tracker metadata"


# ── STEP 3 — RECOMMENDATION ──────────────────────────────────
# APPLY AFTER REFERRAL, NOT BEFORE — always outreach first to preserve the contact's
# referral bonus eligibility. Many companies only award referral bonuses when the
# referral is submitted before the candidate's application is in the system.
# Framing: "I wanted to reach out before applying — would you be open to referring me?"
#
# Apply this table to decide connection note vs referral request:
#
# | Situation                                          | Recommendation                                      |
# |----------------------------------------------------|-----------------------------------------------------|
# | is_potential_hiring_manager = true, any degree     | Connection note first (type A) + B-HM DM after     |
# |                                                    | acceptance. Never use InMail — always Connect path. |
# | contact_type = employee, 1st degree, warm           | Direct referral request (type B)                    |
# | contact_type = employee, 1st degree, cold + senior | Post-acceptance international DM (type B-INTL)      |
# |                                                    | Cold senior contacts need explicit context on why   |
# |                                                    | reaching out directly — B-INTL provides this.       |
# | contact_type = employee, alumni / ex-colleague     | Direct referral request — shared bond overrides     |
# | contact_type = employee, [YOUR_ALUMNI_NETWORK] junior            | Direct referral request — seniority signals warmth  |
# | contact_type = employee, 2nd+ / cold               | Connection note first (type A) + follow-up (type B-INTL if cold+senior, else B) |
# | contact_type = employee, no LinkedIn, have email   | Referral request via email (type B)                 |
# | contact_type = recruiter, 1st degree / prior       | Direct recruiter outreach (type C)                  |
# | contact_type = recruiter, 2nd+ / no prior contact  | Connection note first (type A) + follow-up (type C) |
#
# "Connection request first" → draft BOTH A and C/B in sequence, clearly labelled.
#
# NOTE: contact_type = recruiter changes the ask entirely — see Message Type C below.
# The "outreach before applying" framing still applies: reaching out first establishes
# warm context before a formal ATS application appears.
#
# State recommendation in 1–2 sentences before drafting:
#   "I'd recommend a direct referral request — you share [YOUR_ALUMNI_NETWORK] alumni status,
#    which overrides connection degree and gives you a warm opener."


# ── STEP 3b — PRE-FLIGHT CHECK (MANDATORY GATE BEFORE DRAFTING) ──
# STOP. Before writing a single word, complete this pre-flight table.
# The fields require reading the Consolidated Rules sections to answer
# correctly — filling the table IS the proof of reading.
#
# Steps:
#   1. Read ## Consolidated Rules §1 (always applies to all drafts).
#   2. Identify contact function → read the relevant §2/§3/§4 sections.
#   3. Scan skills/draft_referral_learnings.md for any recent entries not yet in Consolidated Rules.
#   4. Log the completed pre-flight table before proceeding to STEP 4:
#
#   [referral] Pre-flight:
#     Contact function : [YOUR_DOMAIN] / product / HR/TA / recruiter / ops / engineering / other
#     Ask framing      : same-function / different-function / HR-uncertainty / potential-HM
#     Connection type  : 1st / mutual-2nd / cold / no-Connect-flag-to-user
#     Potential HM     : yes (auto | user-flagged) | no — if yes, use Type B-HM ask
#     Target role tier : Lead/Manager | Senior  ← determines Option A credential format (§2 rule)
#     Applied status   : yes | no | auto-detect  ← from Applied field or tracker status lookup (§6)
#     Message type     : connection note / referral request / DM after acceptance / recruiter outreach
#     Sections applied : e.g. §1, §3 (different-function), §4 (HR/TA), §4 (potential HM)
#
# A draft without this log is invalid. If the table is vague or missing,
# treat it as a skipped step and restart from STEP 3b.


# ── STEP 4 — DRAFT MESSAGE(S) ────────────────────────────────

# ── A. LinkedIn connection request note (≤300 chars) ─────────
# - Hook specific to the relationship — 1 sentence
# - One genuine reason for connecting to *this* person — 1 sentence
# - No explicit ask (referral ask comes in the follow-up message)
# - Count characters precisely — LinkedIn enforces this strictly
# - Output format: show text + char count, e.g. "Draft (247/300 chars):"


# ── B. Referral request message — employee (120–200 words) ──────────────
# Structure:
#
#   Hi [Name],
#
#   [HOOK — 1–2 sentences, relationship-specific]
#
#   [SITUATION — 2–3 sentences, where relevant:
#    Why European market, why now, why this company specifically.
#    Only include struggle narrative when contact_nationality = Indian
#    AND contact is in a European role (see Hook strategy below).]
#
#   [FIT — 1–2 sentences, metric-backed. One credibility signal, not a CV dump.]
#
#   [ASK — low-friction, specific:
#    "I wanted to reach out before applying for the [Role] — would you be
#     open to referring me through [Company]'s internal process or forwarding
#     my CV to the right team?"
#    Never ask for a job — ask for a referral, a forward, or a conversation.]
#
#   Best,
#   [YOUR_NAME]
#
# If contact_location differs from role location:
#   Acknowledge briefly: "I know you're in [their city] — hope the reach
#   across to [role city] isn't a stretch for this one."


# ── B-INTL. Post-acceptance DM — international candidate, ambiguous HM (150–170 words) ──
# Use when ALL of these are true:
#   - Connection was just accepted (now 1st degree)
#   - Contact is cold (no prior relationship)
#   - Contact is senior and may or may not be the hiring manager
#   - you need visa sponsorship for this market
#
# This format is stronger than standard Type B for cold senior contacts because it is
# transparent about WHY outreach is going to people in the business (not HR/portal) —
# which international candidates almost always need to explain. The honesty about the
# international candidate challenge disarms defensiveness and reframes the ask as
# reasonable rather than presumptuous.
#
# Structure:
#
#   Hi [Name],
#
#   [THANKS — 1 sentence. Never "hope this finds you well."]
#
#   [CONTEXT — 1 sentence: role + why this specific person.]
#
#   [VISA/CHALLENGE — 2–3 sentences: based in [YOUR_CURRENT_COUNTRY], need
#    sponsorship, honest reason for reaching out to people in the business
#    rather than standard application route — international candidates tend
#    to get filtered by HR before the profile is reviewed.]
#
#   [FIT — 2–3 sentences: "having gone through the JD carefully, I genuinely
#    believe I'm a strong fit" + most relevant experience + one metric/signal
#    that maps to the role specifically.]
#
#   [DUAL-PATH ASK — covers both HM and non-HM cases:
#    "Two things would help me: do you know if [Company] sponsors visas for
#     international candidates? And if you're involved in or close to the
#     hiring decision — or can point me to someone who is — I'd really
#     appreciate either a conversation or an introduction. Not asking you
#     to vouch for me, just to open a door."]
#
#   [CLOSE — 1 sentence: "Appreciate your time." or "No obligation either way."]
#
#   Appreciate your time.
#
#   Best,
#   [YOUR_NAME]
#
# Key constraints:
#   - NEVER say "I believe you are the hiring manager" — always HM-agnostic ask
#   - Fit claim must be JD-specific — "having gone through the JD carefully" is the anchor
#   - Visa question first in the dual ask — intelligence-gathering before the intro ask
#   - No obligation close is mandatory — reduces pressure on a cold senior contact
#   - 150–170 words. Do not pad.
#   - Use market-appropriate visa name in the visa/challenge paragraph


# ── B-HM. Potential hiring manager DM (100–150 words) ───────
# Use when is_potential_hiring_manager = true. The contact may or may not own the hire —
# the message must cover both cases without leaning on either with confidence.
# DO NOT call them the hiring manager directly — keep it a soft inference.
#
# Structure:
#
#   Hi [Name],
#
#   [HOOK — 1 sentence: their specific role/function at [Company] — not the JD mandate.]
#
#   [FIT SIGNAL — 2–3 sentences: most relevant experience, one metric, scope match.
#    Tight — this is a senior contact who reads quickly.]
#
#   [FAIR CHANCE HOOK — always include for B-HM contacts:
#    "I know being international adds a layer of complexity — not asking for special treatment,
#     just to be considered on the merits of the profile if the role budget allows for it."]
#
#   [DUAL-PATH ASK — two sub-variants depending on whether HM is confirmed or inferred:
#
#    Variant A — Confirmed HM (Potential HM=yes, Is Relevant=yes, user-verified from posting):
#    "If you're open to putting in a word, I'd welcome a fair chance to be considered on my merits."
#    Single-path ask — no dual-path needed because the contact is definitively the HM.
#
#    Variant B — Inferred HM (Potential HM=yes, Is Relevant=blank, auto-detected):
#    "I'm reaching out because your role as [their title] at [Company] suggests you may be
#     connected to this area — if the [Role] sits within your team, I'd appreciate a fair chance
#     to be considered. And if I've reached the wrong person, I'd be genuinely grateful for a
#     pointer in the right direction."
#    Dual-path — covers both outcomes gracefully without leaning on either with confidence.
#
#    — Never say "I believe you are the hiring manager" — always "suggests you may be connected"
#    — Replace "brief conversation" with "fair chance to be considered on my merits"]
#
#   [VISA LINE — mandatory:
#    "I am based in [YOUR_CITY], [YOUR_COUNTRY], and am actively seeking roles in [country]
#     under [visa]. I am fully prepared to relocate upon receiving an offer."]
#
#   Best,
#   [YOUR_NAME]
#
# Tone: direct and peer-level, but with genuine epistemic humility on the HM assumption.
# No struggle narrative for senior contacts regardless of nationality — mismatched register.
# No "would you refer me" ask — wrong framing for a potential hiring manager.
# Word count: 100–150. Err shorter — senior contacts reward concision.


# ── C. Recruiter outreach message — specific role (100–150 words) ────────────
# Use when contact_type = recruiter AND a specific role is in play.
# The recruiter is the gatekeeper — the ask is to be put forward to their client,
# not to trigger an internal referral bonus.
# DISTINCT from Type C-General (no specific role) — see below.
#
# SUBJECT LINE — required for InMail and email; not applicable for regular LinkedIn DMs:
#   Format: "[Role Title] — Interested in Being Considered"
#   Example: "Lead AI Business Analyst — Interested in Being Considered"
#   Keep it clean — role + intent. Do NOT pack in credentials (reads like keyword spam).
#   Always draft the subject alongside the message body for these channels.
#   Log subject in referral_outreach_log.json as "subject" field (null for DMs).
#
# Connection note (≤300 chars) — full 300 chars for all recruiter contacts:
#   Structure: role → brief fit signal (2 employers + domains) → market/visa → closing ask
#   Template — Lead/Manager target (~299 chars):
#     "Hi [Name], I came across the [Role] you're covering — a strong match for my background.
#     [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2]). Targeting [country] under
#     [visa], ready to relocate. Would love to be put forward."
#   Template — Senior target (~272 chars):
#     "Hi [Name], I came across the [Role] you're covering — a strong match. [years_of_experience]+
#     years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2]).
#     Targeting [country] under [visa], ready to relocate. Would love to be put forward."
#
# DM structure (sent after connection accepted):
#
#   [Subject: Role Title — Interested in Being Considered]   ← InMail / email only
#
#   Hi [Name],
#
#   [HOOK — 1 sentence: the role itself or the recruiter's speciality.
#    NOT "I saw your profile."
#    If prior recruiter interaction in outreach.json recruiters[]:
#      "We spoke briefly about a [domain] role you were covering at [agency]..."
#    Otherwise: lead with role/domain fit. If employer is unknown, hook on the
#    role function rather than the company.]
#
#   [FIT SIGNAL — 2–3 sentences: most relevant experience anchor, one metric,
#    domain match to the role/sector. Tight — recruiters scan quickly.]
#
#   [RELOCATION — always include for international markets:
#    "Based in [YOUR_CITY] — actively targeting [country] under [visa],
#     fully prepared to relocate on receiving an offer."]
#
#   [FAIR CHANCE HOOK — always include for external recruiter contacts:
#    "I know being international adds a layer of complexity. I'm not asking for
#     special treatment — just a fair look at the profile before geography becomes
#     the deciding factor, if the role budget allows for it."]
#
#   [ASK — direct, dual ask: this role + radar for future. NEVER "would you refer me" — wrong framing.
#    NEVER "hiring team" — recruiter submits to their client, not an internal team.
#    "I'd love to be put forward for this one — and regardless of how it goes, I'd be keen to
#     stay on your radar for other [YOUR_DOMAIN] leadership openings you cover. Happy to share my
#     CV across if that helps."
#    Dual ask rationale: pitching for this role AND asking for radar placement — one DM, two
#    outcomes. Increases value to the recruiter (not just a one-off submission request).]
#
#   Best,
#   [YOUR_NAME]
#
# Hook strategy for contact_type = recruiter:
#   - Recruiter specialises in [YOUR_DOMAIN] → closing note hook: "Keen to be on your radar"
#   - Recruiter is a generalist → closing note hook: standard put-forward ask
#   - Struggle narrative: still applies if recruiter is Indian/South Asian AND
#     based in European context (same three conditions as type B)
# If contact_location differs from role location: same acknowledgement as type B.
#
# Market visa variables (use consistently across all recruiter and HR/TA messages):
#   UK  → "the UK under Skilled Worker Visa"
#   NL  → "NL under Kennismigrant"
#   DE  → "Germany under EU Blue Card"
#   DK  → "Denmark under Pay Limit Scheme"
#   IE  → "Ireland under Critical Skills Employment Permit"
#   AE  → "UAE" — omit fair chance hook (UAE is international-first market; employment
#           visa is standard employer process, not a candidate burden to explain)


# ── C-General. Recruiter outreach — no specific role (general market outreach) ──────
# Use when contact_type = recruiter AND no specific role is in play.
# Goal: get on the recruiter's radar for future [YOUR_DOMAIN] leadership openings.
# DISTINCT from Type C — there is no role to reference, no client to submit to.
# Ask: "be on your radar" — not "put me forward" (no specific role/client exists).
#
# Connection note (≤300 chars) — full 300 chars (C-General always uses Lead/Manager credential):
#   Template (~280 chars):
#     "Hi [Name], I came across your profile exploring [YOUR_DOMAIN] leadership roles in [country].
#     [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B]; product,
#     growth, and commercial analytics. Targeting [country] under [visa]. Keen to be on your
#     radar for the right opening."
#   Note: omit "same space" closing hook — recruiter does not do analytics.
#         omit "inside a company" — they are at an agency, not the hiring company.
#         "Keen to be on your radar" is the confirmed correct close for this type.
#
# DM structure (sent after connection accepted):
#
#   Hi [Name],
#
#   [HOOK — 1 sentence: came across profile exploring [YOUR_DOMAIN] leadership roles in [country].
#    Do NOT reference a specific role — this is general market outreach.]
#
#   [FIT SIGNAL — 2 sentences: [years_of_experience]+ years, employers, domains. Tight.]
#
#   [RELOCATION:
#    "Based in [YOUR_CITY] — actively targeting [country] under [visa],
#     fully prepared to relocate on receiving an offer."]
#
#   [FAIR CHANCE HOOK:
#    "I know being international adds a layer of complexity. I'm not asking for
#     special treatment — just a fair look at the profile before geography becomes
#     the deciding factor, if the role budget allows for it."]
#
#   [ASK — radar ask, no specific client:
#    "If you're placing [YOUR_ROLE_2] or [YOUR_ROLE_1] roles in [country], I'd love
#     to be on your radar. Happy to send my CV across if that's helpful."]
#
#   Best,
#   [YOUR_NAME]
#
# Role-type neutral — do NOT assume contract vs permanent. No specific role is referenced
# so no role-type assumption is possible or appropriate.
# AE market: omit fair chance hook (UAE is international-first — employment visa is standard).


# ── HOOK STRATEGY ────────────────────────────────────────────
# The opening hook must be relationship-specific. Generic openers
# ("Hi, I came across your profile...") are ignored.
#
# | Relationship / Type       | Hook angle                                                           |
# |---------------------------|----------------------------------------------------------------------|
# | [YOUR_ALUMNI_NETWORK] alumni            | "[YOUR_ALUMNI_NETWORK] batch of [year] here..." — instant shared recognition.      |
# |                           | Mention campus / department if known.                                |
# | [YOUR_ALUMNI_NETWORK] junior            | Frame as a senior reaching out — flatters without being sycophantic. |
# | Ex-[Company A]               | "We crossed paths at [Company A]..." or "We overlapped at [Company] —  |
# | Ex-[Company B] / [Company C]      | [team/project context if known]."                                    |
# | Cold / mutual / 2nd       | Lead with the company or role itself — something genuinely specific. |
# | (employee)                | Never open with "I saw your profile." or "I came across your name." |
# |                           | NEVER mention mutual connections by name — reads hollow.             |
# | Recruiter, prior contact  | "We spoke briefly about a [domain] role at [agency]..." — callback   |
# |                           | creates instant continuity and proves you're selective, not mass-DM. |
# | Recruiter, no prior       | Lead with the role/domain fit, not the company (may be unknown).     |
# |                           | "I came across the [role title] you're covering — it's a strong      |
# |                           | match for what I do." — role first, you second.                      |
#
# STRUGGLE NARRATIVE — use ONLY when ALL three are true:
#   1. contact_nationality = "Indian" (explicitly confirmed by user — do not assume from name)
#   2. Message type is referral request (not connection note — too long for 300 chars)
#   3. Contact is in a European role (the journey is relatable, not hypothetical)
#
# Frame: "[years_of_experience] years building [YOUR_DOMAIN] practices at product-first companies — [Company A],
# [Company B] — and the drive to apply that in a European context has only grown. [Company]
# is one of the specific places I have been watching." — Honest, not desperate. Specific,
# not generic.
#
# DO NOT use the struggle narrative with non-Indian contacts — it may read as over-sharing
# or simply won't resonate. If nationality is unknown, skip it and lead with company/role.


# ── TONE RULES ───────────────────────────────────────────────
# Target: conversational-professional.
# Think: warm LinkedIn DM from someone you met once at a conference.
# NOT: stiff cover letter formality ("I hope this message finds you well")
# NOT: over-casual opener ("Hey!" / "Hope you're doing well!")
# LENGTH: Lean short. Connection note hard cap 300 chars. Referral message
#         start at 120–160 words. Add one specific detail if it feels thin.
#         Never pad. Sweet spot will emerge through iteration.


# ── STEP 4b — SAMPLE COMPARISON (MANDATORY BEFORE SHOWING DRAFT) ──────────
# After drafting and before displaying the message to the user:
#
# 1. Identify the matching scenario from §8 Scenario Samples below (read it now if not yet read).
#    Mapping:
#      Confirmed HM (Potential HM=yes, Is Relevant=yes)     → Scenario 1
#      Inferred HM  (Potential HM=yes, Is Relevant=blank)   → Scenario 2
#      Employee warm (alumni / ex-colleague)                 → Scenario 3
#      Employee cold senior (B-INTL)                         → Scenario 4
#      HR/TA is_relevant=yes                                 → Scenario 5
#      HR/TA is_relevant=no or unknown                       → Scenario 6
#      External recruiter, specific role                     → Scenario 7
#      External recruiter, no specific role                  → Scenario 8
#
# 2. Compare the draft against the scenario sample, checking each element:
#      a. Opening hook — relationship-specific? (alumni / cold / recruiter hook format)
#      b. Credential format — Option A applied wherever credentials appear?
#         (HM connection notes, recruiter connection notes, HR/TA is_relevant=yes notes, all DMs)
#         SKIP for minimal cold employee connection notes (Scenarios 3/4) — no credentials there.
#         Lead/Manager: "[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A]... and [YOUR_ROLE_2] at [Company B]..."
#         Senior:       "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A]... and [Company B]..."
#      c. Key structural phrases — present and correctly worded?
#         Fair chance hook (standard): "not asking for special treatment, just to be considered on the merits..."
#         Fair chance hook (ATS variant, Scenario 3 only): "having my profile reach the hiring manager directly..."
#         Scenario 1 ask: "I'd welcome a fair chance to be considered on my merits."
#         Scenario 2 ask: "I'd appreciate a fair chance to be considered. And if I've reached the wrong person,
#                          I'd be genuinely grateful for a pointer in the right direction."
#         Scenario 5 ask: "Would you be happy to put me forward for consideration?"
#         Scenario 6 ask: "Would you be able to point me to the right person handling this role,
#                          or put me forward if it falls within your remit?"
#         Scenario 7 ask: dual ask — "I'd love to be put forward for this one — and regardless of how it goes,
#                          I'd be keen to stay on your radar..."
#         Scenario 8 ask: "I'd love to be on your radar. Happy to send my CV across if that's helpful."
#      d. Closing hook — correct for contact function? (Option 1 / Option 2 / HR/TA / Type-C specific)
#      e. Pipe characters — removed from display? (§1 rule)
#      f. Word / character count — within range for message type?
#
# 3. In the response to the user, flag deviations BEFORE showing the draft:
#      Format: "[!] DEVIATION [element]: expected — [sample wording]; got — [draft wording]"
#      Example: "[!] DEVIATION [fair chance ask]: expected — 'I'd welcome a fair chance to be
#                considered on my merits.' / got — 'I'd love a brief conversation.'"
#    If no deviations: write one line "✓ Scenario [N] sample — no deviations." then show draft.
#
# NOTE: [JD-FIT], [Name], [Company], [Role], [country], [visa], [their title] are live-fill
# placeholders. Variation here is EXPECTED and NOT a deviation. Only flag structural,
# phrasal, or format deviations against the sample.


# ── STEP 5 — APPLY HONESTY RULES (ALL MODES) ────────────────
# Rules 1–10 from draft_application_response.md apply in full.
# Key referral-specific additions:
#
# RULE R1 — Relationship accuracy
#   NEVER imply a closer relationship than stated.
#   "We worked together" is only valid if user confirmed it.
#   "Crossed paths" is safer when overlap is uncertain.
#
# RULE R2 — Calibrate the ask to warmth
#   Cold / 3rd degree: do NOT ask for a referral — ask for a conversation or profile share.
#   Warm (alumni / ex-colleague): asking for a CV forward is appropriate.
#   Never ask for a job directly.
#
# RULE R3 — Contact details
#   Only use information the user explicitly provided.
#   Do not infer title / team / background beyond what was stated.
#
# RULE R4 — Relocating framing (same as draft_application_response RULE 2)
#   "I am based in [YOUR_CITY], [YOUR_COUNTRY], and am actively seeking roles in [country]
#    under [visa]. I am fully prepared to relocate upon receiving an offer."
#   Visa per market: uk → Skilled Worker Visa | nl → Kennismigrant |
#   de → EU Blue Card | se → Arbetstillstånd | dk → Pay Limit Scheme |
#   ie → Critical Skills Employment Permit
#
# RULE R5 — Phone number placeholder
#   NEVER write a real phone number. Use "+91-XXXXXXXXXX" if needed.
#
# RULE R6 — AI project (same as draft_application_response RULE 3)
#   NEVER reveal the application domain. Use: document generation,
#   data ingestion, automated status tracking, structured JSON-to-PDF rendering.
#
# RULE R7 — LinkedIn char limit
#   Connection note MUST be ≤300 chars. Count carefully. Show count.
#
# RULE R8 — British English (same as draft_application_response RULE 10)
#   optimisation / modelling / organised / analyse — not US spellings.
#
# RULE R9 — Recruiter-specific ask framing (contact_type = recruiter ONLY)
#   NEVER use "would you refer me" with a recruiter — that is the employee referral ask.
#   The recruiter's role is to screen and submit candidates, not to trigger a bonus.
#   Use instead: "put me forward", "submit me as a candidate", "share my CV with your client".
#   NEVER "share my CV with the team" — external recruiter submits to their client, not an internal team.
#   The framing shifts from "referral favour" to "candidate submission".


# ── STEP 5b — FOLLOW-UP REPLIES ──────────────────────────────
# When drafting a reply to a contact's response (not an initial outreach):
#   1. Read data/referral_outreach_log.json — find the prior message(s) sent to this contact.
#      MANDATORY — the contact's reply is shaped by what was sent; replying without reading
#      the prior message produces misaligned drafts.
#   2. Read the contact's reply carefully — identify what they understood vs what was intended.
#   3. Correct any misreading before making the next ask.
#   4. Keep follow-ups shorter than the original — engagement is established, get to the point.
#
# CONTEXT INFERENCE — when user references "this job", "the JD", "this contact" etc.
# without specifying an ID, always infer from the most recent active conversation thread
# (the contact/job being discussed), NOT the last job_id looked up in a different context.
# When in doubt, state the inferred company + contact name before acting.


# ── STEP 6 — REFINEMENT LOOP ─────────────────────────────────
# Display draft and wait for user response. Do NOT log yet.
#
# If user requests revision:
#   1. Apply it and redisplay
#   2. Note what changed and why (informs Learnings update)
#   3. Carry forward within session — don't require same correction twice
#
# User signals final by: "good", "use this", "send", "done", or moving on.


# ── STEP 7 — LOG AND UPDATE STATUS (on confirmation) ─────────
# 1. Update data/outreach.json referrals[]:
#      Add or update contact entry with:
#        status:              set per message type (see below)
#        contact_name:        <name>
#        contact_role:        <role>
#        contact_location:    <location>
#        relationship:        <type>
#        connection_degree:   <degree>
#        channel:             <linkedin | email>
#        contact_type:        <employee | recruiter>
#        agency_name:         <agency name, or null if employee>
#        reached_out_date:    <today's date>   ← ALWAYS set at Step 7 (same as logged_date)
#                             Exception: if user says "draft for later / I'll send tomorrow"
#                             → keep null, add TODO note in notes field, run Step 7b when sent.
#
#      Status and reached_out_date per message type confirmed:
#        connection_note (Type A)               → status = "Connection-Requested",  reached_out_date = today
#        referral_request (Type B / B-HM)       → status = "Reached-Out",           reached_out_date = today
#        recruiter_outreach (Type C)             → status = "Reached-Out",           reached_out_date = today
#        inmail (§1 InMail exception)            → status = "Reached-Out",           reached_out_date = today
#
#      If BOTH connection_note AND referral_request are confirmed in the same session
#      (e.g. user sends the note and the DM draft together):
#        → Set status = "Reached-Out" (the higher status wins), reached_out_date = today
#
# 2. Set job tracker status per message type (if not already at a later stage):
#      connection_note  → "Connection-Requested" (if currently Planned or Referral-Planned)
#      referral/inmail  → "Reached-Out"          (if currently Connection-Requested or earlier)
#    (Read tracker → find entry → if status is Prep Complete, set to Referral-Planned
#     → append to status_history[] → write back)
#
# 3. Append to data/referral_outreach_log.json:
#    {
#      "logged_date":      "YYYY-MM-DD",
#      "company":          "<company>",
#      "role":             "<role>",
#      "job_id":           "<job_id>",
#      "contact_name":     "<name>",
#      "contact_role":     "<contact_role>",
#      "contact_location": "<contact_location>",
#      "relationship":     "<relationship>",
#      "connection_degree":"<degree>",
#      "channel":          "<channel>",
#      "contact_type":     "<employee | recruiter>",
#      "agency_name":      "<agency name or null>",
#      "subject":          "<subject line or null — required for InMail/email, null for DMs>",
#      "message_type":     "connection_note | referral_request | recruiter_outreach",
#      "message_text":     "<final confirmed message text>",
#      "char_count":       <int>,
#      "refinement_notes": "<what changed across drafts, or null>",
#      "outcome":          null
#    }
#    Create file with {"_meta": {...}, "messages": []} if absent.
#
# 4. If a non-obvious pattern emerged during drafting, update the
#    ## Learnings section at the bottom of this skill file (append only).
#    Format: "- YYYY-MM-DD [relationship / company type, market]: <observation>"
#    Only confirmed final messages trigger Learnings updates — not draft iterations.
#
# 5. Run: python3 scripts/sheets_sync.py push --tabs apps,outreach
#    (sync status and outreach.json referrals — including reached_out_date — to Sheet)
#
# Log: "[referral] Saved: [Company] / [Role] → [contact_name] → [message_type]"
# Log: "[referral] Status → [new status] | reached_out_date = [date]"
# Log: "[referral] Google Sheet synced"


# ── STEP 7b — CONFIRM SENT (prior-session messages) ──────────
# Use when user says "I sent those connection requests" for messages drafted in an earlier session.
# The draft_referral_message skill already created outreach.json entries (Step 7) but left
# reached_out_date null because the sending was deferred. This step patches that.
#
# 1. Read data/outreach.json — find entries matching (company, contact_name) for reported contacts.
# 2. For each: set reached_out_date = today (or user-specified date if they say "I sent it yesterday").
# 3. Advance status if needed: connection_note sent → "Connection-Requested"; referral sent → "Reached-Out".
# 4. Write back outreach.json.
# 5. Run: python3 scripts/sheets_sync.py push --tabs apps,outreach
#
# Log: "[referral] Step 7b: reached_out_date set for N entries → sheets_sync pushed"
#
# Shortcut — if drift is discovered after the fact across multiple contacts, run:
#   python3 scripts/sync_outreach_dates.py --dry-run    ← preview
#   python3 scripts/sync_outreach_dates.py              ← apply + push
# This script auto-backfills from referral_outreach_log.json (using earliest logged_date per contact).


# ── OUTPUT ───────────────────────────────────────────────────
# 1. Recommendation (1–2 sentences) + message type(s) to draft
# 2. Drafted message(s) — clearly labelled (Step 1: connection note / Step 2: referral)
#    MANDATORY: Remove ALL pipe characters before displaying — user copies directly into LinkedIn.
#    Show character count for connection notes: "Draft (247/300 chars):"
# 3. After confirmation:
#    "[referral] 1 entry logged → data/referral_outreach_log.json"
#    "[referral] Status → Referral-Planned | outreach.json updated"


# ── ROLE TYPE (contract_remote) ──────────────────────────────
# When the target job has role_type = "contract_remote":
#   - Omit visa/sponsorship references from the referral message and connection note.
#   - If the contact asks about work arrangement or sponsorship, briefly note EOR:
#     "I can engage as a remote contractor via EOR — zero overhead on [Company]'s side."
#   - Hook strategy and LinkedIn note length/format are UNCHANGED.
# For permanent roles: existing framing unchanged (relocation + visa as appropriate).

# ── CONSTRAINTS ──────────────────────────────────────────────
# NEVER imply a closer relationship than stated.
# NEVER ask for a job — only ask for a referral, a forward, or a conversation.
# NEVER use struggle narrative unless contact_nationality = Indian (confirmed).
# NEVER write a real phone number.
# NEVER reveal the AI pipeline application domain.
# NEVER use stiff formal openers ("I hope this message finds you well").
# ALWAYS count LinkedIn connection note characters precisely (≤300 hard limit).
# ALWAYS use British English spellings.
# ALWAYS draw experience claims from experience_bank.md.
# ALWAYS store only the final confirmed message to the outreach log.


## Consolidated Rules

<!-- Thematic grouping of all confirmed rules. Read relevant sections via pre-flight check. -->
<!-- New learnings: append to ## Learnings (Raw) below; promote here when confirmed. -->


### §1 Formatting & Mechanics (all messages — always read)

- **Always remove pipe characters before displaying any draft** — the user copies directly
  into LinkedIn. Pipe (|) characters break copy-paste. Strip from ALL message types and ALL
  scenarios before presenting to user: connection notes, referral requests, recruiter outreach,
  follow-up replies. This is a display rule — the underlying templates may use pipes for layout,
  but every draft shown to user must have them removed.
- **No "|" pipe character** in any draft text — disables copy-paste from screen. Applies to
  connection notes, referral requests, recruiter outreach, and follow-up replies.
- **Always assume Connect is available** — never flag "no Connect button visible" or suggest
  InMail as a fallback based on browser reads or profile inspection. Only reconsider if the
  user explicitly states Connect is not available for a specific contact.
- **Never use InMail** — always use the Connect path (free), including for potential HMs.
  InMail is no longer an option. Always send connection note first, then DM after acceptance.
  This applies even when is_potential_hiring_manager = true — Type B-HM DM goes after acceptance.
  (See also §4 B-HM for full HM DM rules.)
- **British English spellings** throughout (optimised, modelling, behavioural, prioritise, etc.)
- **No overconfident phrases** — avoid "that's exactly", "exactly the path", "directly in line".
  Softer alternatives: "which is the role I'm applying for", "the kind of mandate I've been
  building towards", "it's an area I've been building in hands-on."
- **Exact role name in the ask** — never "the role" generically.
- **"The right team"** — never just "team" in the ask.
- **Outreach before applying** — preserves the contact's referral bonus eligibility. Many
  companies only award the bonus when the referral is submitted before the application enters
  the ATS. Frame as: "I wanted to reach out before applying." (See also §6 Applied flag
  resolution rules for when "already applied" framing overrides this for is_relevant=no contacts.)
- **outreach.json entries** — always include company and role fields directly in each referral
  entry; sheets_sync reads them directly. Never rely on app_id lookup. Set at creation time.
- **reached_out_date is mandatory at Step 7** — always set to today's date when writing to
  outreach.json in Step 7. NEVER write `null` unless the user explicitly says the message will be
  sent later ("I'll send tomorrow"). The `null → set later` pattern is the root cause of the
  recurring "Reached Out" column gap in the Sheet. If you're in Step 7, the message has just been
  confirmed — today is the date. Use Step 7b to patch deferred sends from prior sessions.


### §2 Connection Notes (Type A — ≤300 chars)

- **No signature** — LinkedIn shows your name and photo; recipient already knows who sent it.
  Salutation ("Hi [Name],") stays — personalises and distinguishes from a generic blast.
- **Keep hook different from referral request** — contact reads both sequentially; same hook
  kills momentum. Connection note: role + why you're reaching out to THIS person.
  Referral request: the deeper hook (JD mandate, their vantage point, your fit).
- **HM and recruiter contacts — use the full 300 chars**: signal intent AND brief credentials
  in the note itself. The note does double duty — even if they never accept or reply, they
  have received the key message. Structure: role → brief fit signal (2 employers + domains)
  → reason for connecting. Use ~270–295 chars.
  Use "exploring" not "applying" — outreach precedes application; "applying" is inaccurate
  and sounds transactional. "exploring" keeps tone open and non-presumptuous.
  Regular employees (non-HM, non-recruiter) stay minimal — long cold notes read as a pitch
  to someone who is a voucher, not a decision-maker.
- **Option A credential format (mandatory pre-flight — check target role tier first):**
  Role-adaptive credentials in all DMs and in HM/recruiter connection notes:
  - **Lead/Manager target role** → title-forward format:
    "[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and
     [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2])"
  - **Senior target role** → employer-domain format:
    "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B]
     ([YOUR_DOMAIN_2])"
  NEVER use "8+ years in [YOUR_DOMAIN] leadership" as a blanket phrase — the first ~3.5 years were
  IC/Senior roles at earlier employers. The title-forward format (Lead/Manager version)
  signals seniority through actual titles, not a leadership claim over the full career.
  This rule applies globally across all message types and all 8 contact scenarios.
- **Closing hook by contact function:**
  - Option 1 (non-data internal employee: ops, engineering, product, growth, finance):
    "Always good to know someone inside a company before applying."
  - Option 2 ([YOUR_DOMAIN] / similar-role internal employee):
    "Always good to have a conversation with someone working in the same space before applying."
  - Option HR/TA (internal HR, TA, People, Talent — any is_relevant value):
    "Always good to know someone on the talent team before applying."
    Use this instead of Option 1 for all HR/TA contacts — more precise than "inside a company."
  - External recruiter: NEVER Option 1 or 2. Use role-specific close:
    Type C → "Would love to be put forward."
    Type C-General → "Keen to be on your radar for the right opening."
  - Rule: [YOUR_DOMAIN] → Option 2 | HR/TA → Option HR/TA | other internal → Option 1 | external recruiter → type-specific close.
- **Never map the contact's exact career journey** — "BCG Bangalore, HEC Paris, now LEGO" reads
  like profile stalking. Reference the broad transition generically: "noticed you made the move
  from [Your Country] to [Target Country]." Country-to-country, not country-to-city
  ("[Country A] to [City B]") — the asymmetry looks odd.
- **"Similar transition" > "exactly the path I'm working towards"** — the latter implies a single
  destination, which isn't true when targeting multiple European markets.
- **Hometown personal link** — if contact studied at a university in your city, mention it
  factually: "Spotted [their alma mater] on your profile — I'm from [your city] originally." Never make an
  emotional claim ("has a special place for me"). Let the receiver draw the warmth; don't state it.
- **Senior contacts** — subtle peer recognition: one clause, no adjectives ("fewer still end up
  somewhere like LEGO"). Implies the destination is noteworthy without flattery. Never map career.
- **HR / TA contacts (Connect-only)** — format depends on is_relevant_contact:
  - `is_relevant_contact = yes` (contact owns this hire): use the **full 300 chars** with credentials.
    Structure: role → brief fit signal (2 employers + domains + market/visa) → talent-team closing hook.
    Template — Lead/Manager target (~293 chars):
    "Hi [Name], I came across the [Role] at [Company] — a strong match. [years_of_experience]+ years
    in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([domain_A]) and [YOUR_ROLE_2] at [Company B]
    ([domain_B]); targeting [country] under [visa].
    Always good to know someone on the talent team before applying."
  Template — Senior target (~275 chars):
    "Hi [Name], I came across the [Role] at [Company] — a strong match. [years_of_experience]+ years
    in [YOUR_DOMAIN] — [Company A] ([domain_A]) and [Company B] ([domain_B]);
    targeting [country] under [visa]. Always good to know someone on the talent team before applying."
  - `is_relevant_contact = no / unknown`: use **soft intent only**, ≤220 chars, NO credentials.
    Template (~151 chars): "Hi [Name], I came across the [Role] at [Company] and wanted to connect
    before applying. Always good to know someone on the talent team before applying."
  Close HR/TA notes with "talent team" hook — more precise than "inside a company" (Option 1).
  "Inside a company" is reserved for non-HR internal employee contacts. Never open with "Wanted
  to reach out before submitting through the portal" — the closing hook signals this naturally.

- **External recruiter contacts** — always full 300 chars regardless of is_relevant_contact:
  - Type C, Lead/Manager target (~299 chars): "Hi [Name], I came across the [Role] you're covering —
    a strong match for my background. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A]
    ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2]).
    Targeting [country] under [visa], ready to relocate. Would love to be put forward."
  - Type C, Senior target (~272 chars): "Hi [Name], I came across the [Role] you're covering —
    a strong match. [years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and
    [Company B] ([YOUR_DOMAIN_2]). Targeting [country] under [visa], ready to relocate.
    Would love to be put forward."
  - Type C-General (~280 chars, always Lead/Manager): "Hi [Name], I came across your profile
    exploring [YOUR_DOMAIN] leadership roles in [country]. [years_of_experience]+ years in [YOUR_DOMAIN] —
    [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B]; [YOUR_DOMAIN_1] and [YOUR_DOMAIN_2].
    Targeting [country] under [visa]. Keen to be on your radar for the right opening."
  Note: NEVER use Option 1 ("inside a company") — recruiter is at an agency, not the hiring company.
        NEVER use Option 2 ("same space") — recruiter does not do analytics.
        Use "Would love to be put forward" (Type C) or "Keen to be on your radar" (C-General).


### §3 Referral Request (Type B — 120–200 words)

- **Salutation + signature** ("Hi [Name]," and "Best, [YOUR_NAME]") — both required.
- **Lead with contact's position** at the company — not the role description. "Given your time in
  [Function] at [Company]..." — the receiver needs context on why YOU are reaching out to THEM
  before they care about the role. Opening with role description feels out of context.
- **No "follow up" framing** — even when this IS the second message. "Thanks for connecting.
  I wanted to follow up on..." reads as a sales chase. Open with the deeper hook (JD mandate,
  their vantage point, or the company). The connection note established context — build on it
  without naming it.
- **Ask framing by contact function:**
  - **All employee contacts (same function or different)**: forward first, refer second.
    Forwarding to the hiring manager is lower friction for any contact — no portal, no job
    code, no formal vouching required. Same-function contacts may know the referral system,
    but forward-first still gets more action. Only go refer-first if the contact has
    explicitly used the referral system before or mentioned the bonus.
    → "Having my CV reach the hiring manager for the [Role] directly gives the best chance of
    my profile being considered — would you be open to forwarding it to the right team, or
    referring me through [Company]'s internal process if that's easier?"
  - **HR/TA contacts**: uncertainty ask — they may not own this specific role.
    → "Would you be able to point me to the right person on the hiring side for this role,
    or share my CV if it falls within your remit?"
- **Drop "Honestly" prefix** — adds hedging tone that undermines confidence.
- **Keep reasoning clause** in the forward-first version ("gives the best chance of my profile
  being considered") — makes the ask actionable, not just a favour request.
- **JD-FIT instruction** — whenever a DM template says "[why this company]" or "[company/JD detail]",
  replace with 1–2 sentences that map the role's core requirements directly to your experience.
  Source: JD text (loaded in Step 2) + data/content/experience_bank.md. Always truthful — never
  fabricated. Do NOT write generic statements like "I've long admired [Company]'s approach to
  data." Map specific JD requirements to specific experience and metrics.
- **Fair chance hook — warm employee (ATS variant)**: include in Type B DMs for warm contacts
  (alumni, ex-colleagues, [YOUR_ALUMNI_NETWORK]) where the ask is to forward CV to the hiring manager:
  "I know being international adds a layer of complexity — having my profile reach the hiring
  manager directly gives the best chance of being considered before the ATS filter kicks in."
  This framing is appropriate when the contact can forward internally (warm relationship =
  their forward bypasses the ATS stage). Use the standard fair chance hook for all other contexts.
- **Junior framing gate** — NEVER apply junior framing unless user explicitly states the contact
  is junior or lower in the hierarchy than the role applied for. Never infer from title alone.


### §4 Contact-Type Rules

#### HR / Talent Acquisition
- **Verify location first** — check LinkedIn profile location against the role location before
  drafting. Large tech companies spread HR across offices (JetBrains HR in Munich for a Berlin
  role). A city mismatch lowers response likelihood and means they likely don't own this hire.
  Record discrepancy in outreach.json: contact_location = "Munich, Germany (role is Berlin)".
- **Always use Connect** → connection note (see §2 for format by is_relevant) + full pitch DM after acceptance.
- **Connection note length by is_relevant_contact:**
  - `is_relevant_contact = yes` → full 300 chars with credentials (see §2 HR/TA rule)
  - `is_relevant_contact = no / unknown` → soft intent ≤220 chars, no credentials
- **Ask framing depends on is_relevant_contact:**
  - `is_relevant_contact = yes` (contact owns this hire — they ARE the process):
    Use **direct ask**: "Would you be happy to put me forward for consideration?"
    No sharing, no pointing — they own the hire. Add fair chance hook before the ask.
    NEVER "share my CV with the hiring manager" — they are the hiring-side contact; asking
    them to share with someone else implies they are not the decision-maker, which is wrong
    when is_relevant = yes.
  - `is_relevant_contact = no / unknown` (contact may not own this specific hire):
    Use **pointer ask**: "Would you be able to point me to the right person handling this role,
    or put me forward if it falls within your remit?"
    Include fair chance hook before the ask: "I know being international adds a layer of complexity —
    not asking for special treatment, just to be considered on the merits of the profile if the role
    budget allows for it. Would you be able to point me to the right person..."
- **Applied variant framing** (from Applied field or tracker auto-detect — see §6):
  - is_relevant=yes → always "before applying" / "before going through the portal" (Applied ignored)
  - is_relevant=no + Applied=yes → "I've already applied through the portal — wanted to reach out directly as well"
  - is_relevant=no + Applied=no/blank → auto-detect from tracker (see §6)
- **Full pitch structure** (DM after acceptance): direct intent opener ("before going
  through the portal") + 3-line background + relocation line + fair chance hook (is_relevant=yes
  only) + ask. 100–130 words.

#### Recruiter (external agency)
**Gate: only applies when Agency field is filled.** If Type=recruiter AND Agency is blank →
the contact is an internal HR/TA at the hiring company — apply §4 HR/Talent Acquisition rules instead.

- **Always use Connect** → connection note first (type A) + Type C or C-General after acceptance.
  - Specific role in play → Type C. No specific role → Type C-General.
- **Always draft a subject line** for email outreach: "[Role Title] — Interested in Being
  Considered." No credential keywords — reads like spam. LinkedIn DMs have no subject field.
  Log as "subject" field in referral_outreach_log.json.
- **Self-directed AI work framing**: "it's an area I've been building in hands-on, not just
  following from a distance" — not "directly in line with what I've been doing."
- **Ask framing**: NEVER "hiring team" — recruiter submits to their client, not an internal team.
  - Specific role (Type C) — dual ask: "I'd love to be put forward for this one — and regardless
    of how it goes, I'd be keen to stay on your radar for other [YOUR_DOMAIN] leadership openings you
    cover. Happy to share my CV across if that helps."
  - General outreach (C-General): "I'd love to be on your radar. Happy to send my CV across if that's helpful."
- **Fair chance hook**: always include — recruiter decides whether to submit; geography is the
  most common filter at this stage.

#### Potential Hiring Manager (Type B-HM)
- **Trigger**: contact title matches or is functionally close to the JD "Reports To" field,
  or contact is a senior function head (Head of, Director, VP) for the role's domain.
  Auto-detected in Step 1b; can be overridden by user with `is_potential_hiring_manager: true/false`.
- **Never state with confidence** — always soft inference: "your role as [title] at [Company]
  suggests you may be connected to this area" — never "I believe you're the hiring manager."
- **Fair chance hook** — always include in B-HM DMs before the ask:
  "I know being international adds a layer of complexity — not asking for special treatment,
   just to be considered on the merits of the profile if the role budget allows for it."
- **Fair chance ask — two sub-variants:**
  - **Confirmed HM** (Potential HM=yes, Is Relevant=yes, user-verified from posting):
    "If you're open to putting in a word, I'd welcome a fair chance to be considered on my merits."
    Single-path ask — contact is definitively the HM; no dual-path needed.
  - **Inferred HM** (Potential HM=yes, Is Relevant=blank, auto-detected):
    "I'm reaching out because your role as [their title] at [Company] suggests you may be
     connected to this area — if the [Role] sits within your team, I'd appreciate a fair chance
     to be considered. And if I've reached the wrong person, I'd be genuinely grateful for a
     pointer in the right direction."
    Dual-path — covers both outcomes without leaning on either with confidence.
  NEVER use "brief conversation" in the B-HM ask — replaced with "fair chance to be considered."
- **No referral ask** — wrong framing for a potential hiring manager. The ask is a conversation
  or a direction, not an internal referral bonus trigger.
- **No struggle narrative** — mismatched register for a senior/leadership contact regardless of
  contact nationality. Keep tone peer-level and concise.
- **Word count**: 100–150. Shorter is better — senior contacts reward concision.
- **Connection note first, then B-HM DM after acceptance** — always use the Connect path.
  Log message_type = "referral_request" for the B-HM DM (same as other employee DMs).

#### Cold senior contacts — post-acceptance DM (Type B-INTL)
- **Trigger**: cold 1st-degree contact (accepted connection), senior role, you need visa sponsorship.
- **Use Type B-INTL** — not standard Type B. The international candidate challenge needs to be
  named explicitly for cold senior contacts; standard referral framing assumes shared context.
- **Structure order**: Thanks → Role context → Visa/challenge (why reaching out in business, not via HR)
  → Fit (JD-specific) → Dual-path ask → No-obligation close.
- **Dual-path ask**: combines visa intelligence question + HM-agnostic intro/conversation ask.
  Both in one paragraph — do not split into separate messages.
- **Fit claim must be JD-anchored**: "having gone through the JD carefully" — never generic.
- **No obligation close is mandatory** for cold senior contacts: "No obligation either way" or
  "Appreciate your time" — releases pressure without weakening the ask.
- **Word count**: 150–170. Longer than B-HM because the challenge context requires 2–3 sentences.

#### Senior contacts (Head of, Director, VP)
- Subtle peer recognition — one clause, no adjectives: "not many get to lead data science and
  BI at a company scaling this fast." Peer recognition framing, not flattery.
- Never map their exact career journey. Reference role/destination generically.
- Applies in both connection note and referral request.

#### [YOUR_ALUMNI_NETWORK] alumni / junior contacts
- Opening: "[YOUR_ALUMNI_NETWORK] alum here — a few batches ahead of you." NOT "[YOUR_ALUMNI_NETWORK] senior reaching out"
  (arrogant; not how you address a junior naturally).
- Brief credibility only: years + known brand names ([Company A], [Company B]). No metrics parade
  (propensity model %, visit growth %). The shared bond + implied seniority does the work.


### §5 Thread / Conversation Rules

- **Salutation ("Hi [Name],") + signature ("Best, [YOUR_NAME]")**: only in (1) connection note and
  (2) the first formal DM after connection is accepted (the referral request).
- **All subsequent replies** in the same thread: NO salutation, NO signature. LinkedIn threads
  carry context; repeating them reads as copy-paste, not conversation.


### §7 Contact Response Handling  ← MANDATORY GATE

<!-- ⚠ MANDATORY — not optional reading. Run every time the user shares ANY contact reply. -->
<!-- Do NOT update status, draft a reply, or take any other action before completing R0–R3. -->

**Trigger**: user shares a contact's response — connection accepted, referral request reply,
InMail reply, DM reply, or any message from a contact linked to an active outreach entry.

**MANDATORY pre-action sequence (must complete BEFORE responding or updating anything):**

Step R0 — Read the original outreach message first.
  Run: grep referral_outreach_log.json for this contact + app_id.
  Read the exact message that was sent. You MUST know what was asked before you can
  interpret the reply. Classifying a response without reading the original is invalid.
  Log: "[response] Prior message: [message_type] sent [logged_date] — [1-line summary of ask]"
  Log: "[response] Contact reply: [verbatim or user-paraphrased]"

Step R1 — Identify the application
1. Read data/outreach.json → match contact_name to referrals[] → get app_id, company, role, current outreach status.
2. Read data/job_tracker.json → find app_id → note tracker status, visa_sponsorship_status, market.

**Step R2 — Classify the response (MANDATORY — log the verdict before any action)**

Read the response carefully against the original outreach message. Then output:
  "[response] Classification: [type] | Verdict: [Pursue / Terminal / Needs-Input]"

| Response signal | Classification | Verdict | Tracker action |
|---|---|---|---|
| "Happy to refer" / "I'll pass your CV" / explicit referral confirmation | **Referred** | Pursue | tracker → Referred; docs move ready/ → referral/ |
| "Sure, go ahead and apply" / positive but non-committing | **Positive-pending** | Pursue | no tracker change; update outreach response_notes |
| Contact accepted connection; no message yet | **Connected** | Pursue | outreach → Connection-Requested; send referral request next |
| Redirected to a named person ("speak to X") | **Redirect** | Pursue | outreach → Declined + redirect notes; identify named person; add/update their outreach entry → Connection-Requested or Reached-Out; no tracker change |
| "We don't sponsor visas" / "not open to international candidates" | **Visa-blocked** | Needs-Input | assess severity (Step R3) before acting |
| "Role has been filled" / "position on hold" / "not hiring right now" | **Role-dead** | Terminal | tracker → Withdrawn; rejection_stage = role_filled_or_hold |
| "I'm not in the right team" / "can't help" / no named redirect | **Declined** | Pursue-if-others | outreach entry → Declined; check if other contacts remain active; if none → Terminal |
| Connection declined (LinkedIn) | **Declined** | Pursue-if-others | outreach entry → Declined; check other contacts |

**Redirect rule**: when a contact names a specific person to contact, that person becomes
an active lead. Update the named person's outreach entry (or create one). Do not treat a
redirect as a dead end — it is an actionable handoff.

**Step R3 — Visa-blocked: assess severity before withdrawing**

| Who said it | Confidence | Action |
|---|---|---|
| HR / TA / hiring manager | HIGH | Withdrawn unless user wants to verify with HR directly |
| Peer employee (different team) | MEDIUM | Flag to user; suggest verifying with HR; don't auto-withdraw |
| JD already says visa_sponsorship_status = "Confirmed" | CONFLICT | Flag conflict; do NOT withdraw on peer intel alone |

**Step R4 — Update data files**

outreach.json referrals[] — the contact's entry:
  response_received: true
  response_date: today
  response_notes: 1-sentence summary (what they said + the outcome)
  status: Referred / Declined / unchanged (per classification above)

job_tracker.json — the application entry:
  status: Withdrawn / Referred / unchanged
  rejection_stage: "withdrawn" or "role_filled_or_hold" if applicable
  notes: append contact name + what they said + date
  status_history[]: append new entry with source = "contact_response"

**Step R5 — Sync**
  ALWAYS: python3 scripts/sheets_sync.py pull --tabs apps,outreach → then push --tabs apps,outreach
  (pull first — pick up any edits the user made in Sheet before push overwrites them)

**Key rule — one declined contact ≠ terminal**
Only mark the tracker Withdrawn if:
  a) The blocker is hard (visa explicitly denied, role filled, salary confirmed below threshold)
  b) ALL active contacts for the role have declined or gone silent, OR
  c) User explicitly decides not to pursue
A single "can't help" reply does NOT kill the application — other contacts may still respond.


### §6 Situational Rules

- **Apply framing — before vs already applied**: Check the Applied field (contact table) AND
  tracker status before drafting any DM. Contact notes (Type A) are always unaffected — no
  before/after framing in 300-char connection notes.

  **Applied field resolution rules (in priority order):**
  ```
  1. is_relevant=yes contacts → ALWAYS "before applying" framing regardless of Applied field.
     Rationale: these contacts own the hire; outreach-before-apply preserves their referral
     bonus eligibility. The Applied field value is ignored for these contacts.

  2. is_relevant=no + Applied=yes (explicit) → "already applied" framing:
     "I've already applied through the portal — wanted to reach out directly as well."

  3. is_relevant=no + Applied=no (explicit) → "before applying" framing:
     "I wanted to reach out before applying."

  4. is_relevant=no + Applied=blank → auto-detect from tracker status:
     Applied / Under Review / Interview Scheduled / Assessment → "already applied" framing
     Approved / Prep Complete / Referral-Planned / Connection-Requested → "before applying"

  5. C-General (no specific role) → Claude infers from context. No specific role was
     applied for, so the before/after framing does not apply in the standard sense.
     Focus on general market positioning and being on the radar.
  ```

  Step 7 (Log): always write `is_relevant_contact` and resolved Applied status to the outreach.json
  entry. Use the `Relevant` field from the contact table if provided; otherwise auto-detect from
  contact_type + is_potential_hiring_manager + TA/HR/People/Recruitment keywords in contact_role.

- **Contact redirected to a dead end** (e.g. "contact the hiring manager" but none listed in JD):
  acknowledge their advice as valid, explain the constraint, then pivot.
  Opener: "With that in mind, I was hoping you might be open to..." — flows naturally from the
  acknowledged constraint. Canonical ask ("Would you be open to...") is for cold/direct first asks.
- **Insider intel question**: adding a question alongside the ask ("curious whether the role would
  be open to someone making the move from [Your Country] to [Target Country]") gives the contact
  two things to respond to — easier to reply even if unsure about the referral. Use country-to-country
  framing, not "international candidate."
- **Positive response follow-up**: keep it very short (1–2 sentences). Two confirmed patterns:
  1. Humble qualifier: "of course only if you find it worth your time" — releases obligation.
  2. Pre-emptive thanks: "else I am anyway very much thankful for the referral" — removes
     transactional feel. Use both together to lower pressure while making the concrete ask.


### §8 Scenario Samples

<!-- Reference samples for all 8 contact scenarios — exact confirmed text from session review. -->
<!-- Read in STEP 4b — compare every draft against the matching scenario sample. -->
<!-- Placeholders: [Name] [Company] [Role] [their title] [country] [visa] -->
<!-- Option A credential in DMs — ALWAYS includes team size for [Company B] where applicable:     -->
<!--   Lead/Manager: "[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) -->
<!--                  and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N)" -->
<!--   Senior:       "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and       -->
<!--                  [Company B] ([YOUR_DOMAIN_2])"  ← no "team of N"                                       -->
<!-- Connection notes use abbreviated em-dash grouping (no "team of N") to save chars.          -->
<!-- JD-FIT = mandatory instruction in Scenarios 3 and 4 only — see those samples.              -->
<!-- AE market (all scenarios): omit fair chance hook — UAE employment visa is standard process. -->


#### Scenario 1 — Confirmed HM (Potential HM=yes, Is Relevant=yes)
<!-- Contact is verified HM from job posting. Full credentials. No closing hook (preserves space). -->
<!-- Applied flag: always "before applying" — is_relevant=yes, Applied field ignored. See §6 rule 1. -->

**Connection note — Lead/Manager target (~282 chars):**

Hi [Name], I came across the [Role] at [Company] and wanted to reach out to you directly before applying. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B] — product, growth, and commercial analytics; targeting [country] under [visa]. Would love to connect.

*Senior target: replace credential with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2])"*

**DM — after acceptance (~110 words):**

Hi [Name],

I came across the [Role] at [Company] and wanted to reach out before going through the portal.

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity — not asking for special treatment, just to be considered on the merits of the profile if the role budget allows for it.

If you're open to putting in a word, I'd welcome a fair chance to be considered on my merits.

Best,
[YOUR_NAME]

*Senior target: replace credential line with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2]). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer."*
*Applied flag: NOT applicable. is_relevant=yes always forces "before applying" — Applied field is ignored. See §6 rule 1.*


---

#### Scenario 2 — Inferred HM (Potential HM=yes, Is Relevant=blank, auto-detected)
<!-- HM auto-inferred from contact title. is_relevant not confirmed. Dual-path fair chance ask. -->
<!-- Applied flag: always "before applying" — Potential HM=yes → is_relevant auto-yes. See §6 rule 1. -->

**Connection note — Lead/Manager target (~280 chars):**

Hi [Name], I came across the [Role] at [Company] — as [their title], you may be connected to this area. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B] — product, growth, and commercial analytics; targeting [country] under [visa]. Would love to connect.

*Senior target: replace credential with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2])"*

**DM — after acceptance (~120 words):**

Hi [Name],

I came across the [Role] at [Company] — your role as [their title] suggests you may be connected to this area.

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity — not asking for special treatment, just to be considered on the merits of the profile if the role budget allows for it.

If the [Role] sits within your team, I'd appreciate a fair chance to be considered — and if I've reached the wrong person, I'd be genuinely grateful for a pointer in the right direction.

Best,
[YOUR_NAME]

*Senior target: same credential swap as Scenario 1 DM.*
*Applied flag: NOT applicable. Potential HM=yes → is_relevant auto-detected as yes → always "before applying". Applied field ignored. See §6 rule 1.*


---

#### Scenario 3 — Employee warm (alumni / ex-colleague / [YOUR_ALUMNI_NETWORK])
<!-- Warm relationship overrides connection degree. Data contact → Option 2 hook. Non-data → Option 1. -->
<!-- ATS variant fair chance hook — forward-to-HM framing. JD-FIT is MANDATORY in this DM. -->
<!-- Applied flag: auto-detect from tracker (§6 rules 2–4). -->

**Connection note — [YOUR_DOMAIN] contact (~228 chars, [YOUR_ALUMNI_NETWORK] hook):**

Hi [Name], [YOUR_ALUMNI_NETWORK] alum here — a few batches ahead. Noticed you are at [Company] while exploring [YOUR_DOMAIN] leadership roles in [country]. Always good to have a conversation with someone working in the same space before applying.

*Ex-colleague variant (~201 chars):*

Hi [Name], we overlapped at [previous company] — I was on the [YOUR_DOMAIN] side. Noticed you are at [Company] now. Always good to have a conversation with someone working in the same space before applying.

**Connection note — non-data contact (~194 chars, [YOUR_ALUMNI_NETWORK] hook):**

Hi [Name], [YOUR_ALUMNI_NETWORK] alum here — a few batches ahead. Noticed you are at [Company] while exploring [YOUR_DOMAIN] leadership roles in [country]. Always good to know someone inside a company before applying.

*Ex-colleague variant (~167 chars):*

Hi [Name], we overlapped at [previous company] — I was on the [YOUR_DOMAIN] side. Noticed you are at [Company] now. Always good to know someone inside a company before applying.

**DM — after acceptance / direct for 1st degree warm (~145 words):**

Hi [Name],

[Relationship hook — [YOUR_ALUMNI_NETWORK] / ex-[Company A] / ex-[Company B] etc. One sentence, specific.]

I've been exploring [YOUR_DOMAIN] leadership roles in [country] and came across the [Role] at [Company]. [JD-FIT — 1–2 sentences mapping the role's core requirements directly to your experience, drawn from JD text + experience_bank.md. E.g. "The focus on experimentation and product analytics maps directly to my work at [Company A] — incrementality testing across grocery and CRM, driving 40% visit growth." Always truthful, never fabricated.]

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity — having my profile reach the hiring manager directly gives the best chance of being considered before the ATS filter kicks in.

I wanted to reach out before applying — would you be open to forwarding my CV to the right person, or referring me through [Company]'s internal process if that's easier?

Best,
[YOUR_NAME]

*Senior target: replace credential line with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2]). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer."*
*Already applied variant: replace ask with "I've already applied for the [Role] — would you be open to forwarding my CV directly to the hiring manager, or putting in a word through [Company]'s internal process if that's easier?" (opening + JD-FIT + credential unchanged)*


---

#### Scenario 4 — Employee cold senior (Type B-INTL)
<!-- Cold connection, senior contact, visa sponsorship needed. Minimal connection note. -->
<!-- JD-FIT is MANDATORY and lives inside the [JD-FIT] block in the DM (after visa/challenge). -->
<!-- Applied flag: auto-detect from tracker for DM framing. Connection note unaffected. -->

**Connection note — [YOUR_DOMAIN] contact (~178 chars):**

Hi [Name], I came across the [Role] at [Company] while exploring [YOUR_DOMAIN] leadership opportunities in [country]. Always good to have a conversation with someone working in the same space before applying.

**Connection note — non-data contact (~175 chars):**

Hi [Name], I came across the [Role] at [Company] while exploring [YOUR_DOMAIN] leadership opportunities in [country]. Always good to know someone inside a company before applying.

**DM — after acceptance (~160 words, B-INTL format):**

Hi [Name],

Thanks for connecting.

I came across the [Role] at [Company] — having gone through the JD carefully, I genuinely believe I'm a strong fit.

I'm based in [YOUR_CITY] and need [visa] sponsorship to work in [country]. The reason I'm reaching out to people in the business directly — rather than through the standard application — is that international candidates often get filtered before the profile is reviewed by anyone who can assess actual fit.

[JD-FIT — 2–3 sentences: map the role's core requirements to your specific experience. Lead/Manager: lead with "[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N)" + one metric specific to this role. Senior: use domain-only credential. Always drawn from experience_bank.md — never fabricated.]

Two things would help: do you know if [Company] sponsors visas for international candidates? And if you're involved in or close to the hiring decision — or can point me to someone who is — I'd appreciate a fair chance to be reviewed. Not asking you to vouch for me, just to open a door.

No obligation either way.

Best,
[YOUR_NAME]

*Senior target: use domain-only credential inside the [JD-FIT] block.*
*Already applied variant: replace "The reason I'm reaching out to people in the business directly — rather than through the standard application —" with "I recently applied for the [Role] and wanted to reach out directly as well —" (rest identical)*


---

#### Scenario 5 — HR/TA is_relevant=yes
<!-- Contact owns this hire. Full 300 chars with credentials + talent-team hook. Direct ask. -->
<!-- Applied flag: always "before applying" — is_relevant=yes, Applied field ignored. See §6 rule 1. -->

**Connection note — Lead/Manager target (~287 chars):**

Hi [Name], I came across the [Role] at [Company] — a strong match. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B] — product, growth, and commercial analytics; targeting [country] under [visa]. Always good to know someone on the talent team before applying.

*Senior target: replace credential with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2])"*

**DM — after acceptance (~110 words):**

Hi [Name],

I wanted to reach out before going through the portal for the [Role] at [Company].

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity — not asking for special treatment, just to be considered on the merits of the profile if the role budget allows for it.

Would you be happy to put me forward for consideration?

Best,
[YOUR_NAME]

*Senior target: same credential swap as Scenario 1 DM.*
*Applied flag: NOT applicable. is_relevant=yes always forces "before applying" — Applied field ignored. See §6 rule 1.*


---

#### Scenario 6 — HR/TA is_relevant=no or unknown
<!-- Contact may not own this hire. Credentials NOW included in connection note (confirmed rule). -->
<!-- Fair chance hook in DM. Pointer ask. Applied flag: auto-detect from tracker. -->

**Connection note — Lead/Manager target (~275 chars):**

Hi [Name], I came across the [Role] at [Company] and wanted to reach out before applying. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B] — product, growth, and commercial analytics. Always good to know someone on the talent team before applying.

*Senior target (~272 chars): replace credential with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2])"*

**DM — after acceptance (~115 words):**

Hi [Name],

I wanted to reach out about the [Role] at [Company].

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity — not asking for special treatment, just to be considered on the merits of the profile if the role budget allows for it.

Would you be able to point me to the right person handling this role, or put me forward if it falls within your remit?

Best,
[YOUR_NAME]

*Senior target: same credential swap as Scenario 1 DM.*
*Already applied variant: replace opener with "I recently applied for the [Role] at [Company] and wanted to reach out." (rest identical)*


---

#### Scenario 7 — External recruiter, specific role (Type C)
<!-- Full 300 chars connection note. Fair chance hook. Dual ask: this role + radar for future. -->
<!-- Applied flag: not applicable — recruiter context, framing is about being put forward. -->

**Connection note — Lead/Manager target (~291 chars):**

Hi [Name], I came across the [Role] you're covering — a strong match for my background. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B] — product, growth, and commercial analytics. Targeting [country] under [visa], ready to relocate. Would love to be put forward.

*Senior target (~286 chars): replace credential with "[years_of_experience]+ years in [YOUR_DOMAIN] — [Company A] ([YOUR_DOMAIN_1]) and [Company B] ([YOUR_DOMAIN_2])"*

**DM — after acceptance (~120 words):**

Hi [Name],

I came across the [Role] you're covering — it's a strong match for what I do.

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity. I'm not asking for special treatment — just a fair look at the profile before geography becomes the deciding factor, if the role budget allows for it.

I'd love to be put forward for this one — and regardless of how it goes, I'd be keen to stay on your radar for other [YOUR_DOMAIN] leadership openings you cover. Happy to share my CV across if that helps.

Best,
[YOUR_NAME]

*Senior target: same credential swap as Scenario 1 DM.*


---

#### Scenario 8 — External recruiter, no specific role (Type C-General)
<!-- General market outreach. Always Lead/Manager credential. No Applied flag (no specific role). -->

**Connection note — always Lead/Manager credential (~280 chars):**

Hi [Name], I came across your profile exploring [YOUR_DOMAIN] leadership roles in [country]. [years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] and [YOUR_ROLE_2] at [Company B]; product, growth, and commercial analytics. Targeting [country] under [visa]. Keen to be on your radar for the right opening.

**DM — after acceptance (~115 words):**

Hi [Name],

I came across your profile exploring [YOUR_DOMAIN] leadership roles in [country] — the roles you cover are a strong match for my background.

[years_of_experience]+ years in [YOUR_DOMAIN] — [YOUR_ROLE_1] at [Company A] ([YOUR_DOMAIN_1]) and [YOUR_ROLE_2] at [Company B] ([YOUR_DOMAIN_2], team of N). Based in [YOUR_CITY] — actively targeting [country] under [visa], fully prepared to relocate on receiving an offer.

I know being international adds a layer of complexity. I'm not asking for special treatment — just a fair look at the profile before geography becomes the deciding factor, if the role budget allows for it.

If you're placing [YOUR_ROLE_2] or [YOUR_ROLE_1] roles in [country], I'd love to be on your radar. Happy to send my CV across if that's helpful.

Best,
[YOUR_NAME]

*C-General always uses Lead/Manager credential — no Senior variant applies. General market outreach defaults to senior positioning regardless of the specific role being contacted about.*


---

## Learnings (Raw)

# Full learnings moved to skills/draft_referral_learnings.md (2026-08-08)
# to reduce skill file size. Load that file when reviewing patterns or
# scanning for recent learnings before drafting (Step 3 pre-flight).
# To add a new learning: append to skills/draft_referral_learnings.md, NOT here.
# To promote to Consolidated Rules: copy the entry to §1 above.
