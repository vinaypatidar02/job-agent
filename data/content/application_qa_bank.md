# data/content/application_qa_bank.md — Application Q&A Bank
# ════════════════════════════════════════════════════════════════
# Style anchors and pre-written snippets for application question answers.
# The draft_application_response skill reads this file before answering.
# This file provides TONE and STRUCTURE reference — not verbatim answers.
#
# HONESTY RULES (non-negotiable):
#   - Never claim experience not in experience_bank.md
#   - Never alter metrics (percentages, team sizes, dates)
#   - Never claim domain knowledge not grounded in your work history
#   - If experience is analogical (not a direct match), say so explicitly
#     BAD: "maps directly onto that experience"
#     GOOD: "the skills are transferable — [explain the mapping]"
#   - Never mention tools you cannot defend in an interview
#     (configured in candidate_profile.json → profile.excluded_tools)
#   - AI project: use neutral technical terms only — never reveal application domain
#     USE: "document generation", "data ingestion", "event-driven email processing"
#     NOT: "resume tailoring", "job search automation", "cover letter generation"
#
# CANONICAL METRICS (never alter these — they are real):
#   [List your real metrics here — examples:]
#   [YOUR_METRIC_1] — e.g. "40% improvement in conversion"
#   [YOUR_METRIC_2] — e.g. "30% reduction in cost"
#   [YOUR_METRIC_3] — e.g. "85% prediction accuracy"
#   These must match exactly what is in experience_bank.md.
#   Configure formally in candidate_profile.json → profile.canonical_metrics
# ════════════════════════════════════════════════════════════════


# ── SECTION 1: Motivation / Why This Company ──────────────────
# Style: specific, genuine, not generic. Always name the company.
# 150–250 words. Structure:
#   1. What specifically attracted you (product, mission, data maturity stage)
#   2. Why your experience is a genuine match (not "maps directly")
#   3. What you would want to work on first

# [Add your own pre-written motivation snippets here by domain]
# Example domain: product analytics
# "[Company] is building [X]. What drew me to this role is [specific product challenge
#  or data maturity signal from their site/JD]..."
# NOTE: Do not copy this example verbatim — synthesize fresh from the JD for each application.


# ── SECTION 2: Learning / Past Year ──────────────────────────
# Style: specific technical learning, framed as career impact.
# 200–280 words. Structure:
#   1. What you built or learned (be specific about the system/skill)
#   2. How you approached it (decision points, what was hard)
#   3. Career impact: how it changed how you work / what you can now do

# [Add your key learning narrative here]
# Example framing for AI pipeline:
# "The biggest learning this year has been building a production-grade agentic system
#  from scratch — a multi-stage pipeline covering data ingestion, LLM-based classification
#  with explicit scoring rubrics, domain-aware document generation, and automated event
#  processing. What surprised me most was..."
# IMPORTANT: Do not mention job search / resume tailoring / cover letters as the domain.


# ── SECTION 3: Comparable Role / Most Relevant Experience ──────
# Style: challenge → action → result. Honest about domain differences.
# 200–300 words.
# Lead with your most relevant role for the JD. Use precise labels.
# Always acknowledge domain difference honestly if present.

# [Add your comparable role narrative by JD domain]
# Example: [Company B] role for supply/ops/commercial JDs
# Example: [Company A] role for growth/CRM/experimentation JDs


# ── SECTION 4: Behavioural / STAR ────────────────────────────
# Style: Situation → Task → Action → Result. 150–200 words.
# Draw from experience_bank.md. Do not fabricate.
# Have 3-4 prepared STAR examples covering:
#   - Stakeholder influence / conflicting priorities
#   - Working with ambiguous or incomplete data
#   - Leading a team through a difficult delivery
#   - Delivering insight that changed a decision

# [Add your STAR examples here]


# ── SECTION 5: Work Arrangement ──────────────────────────────
# Key anchors (always grounded in facts — update to match your situation):
#
#   Remote readiness: "Fully set up to work remotely from day one; experienced with
#     async collaboration across time zones."
#   Timezone: "[YOUR TIMEZONE]. Can overlap [TARGET MARKET] business hours.
#     Flexible on early morning / late evening for team standups."
#   Equipment: "Own machine available from day one; happy to use company device once provided."
#   Start date: "Can start remotely within [X weeks]; relocation to follow once permit
#     approved (typically 2-3 months)."
#   Relocation intent: "I am actively pursuing a [VISA TYPE] and am excited to relocate
#     to [CITY] — this role meets the eligibility criteria."
#
#   FRAMING RULE: For remote roles — do NOT frame visa/permit as a company obligation.
#   Remote readiness is the primary message; relocation is a personal aspiration.


# ── SECTION 6: Why Are You Leaving / Why Now ─────────────────
# Style: forward-looking, honest, not negative about current employer.
# 80–120 words.
# Frame as: what you are moving towards, not what you are leaving behind.

# [Add your "why leaving" narrative here]
