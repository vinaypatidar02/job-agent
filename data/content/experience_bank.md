# data/content/experience_bank.md — Experience Bank
# ════════════════════════════════════════════════════════════════
# This is the SINGLE SOURCE OF TRUTH for all resume bullet points.
# auto_prep.py selects bullets from this file — it cannot invent content.
# Nothing enters a resume that is not first written and verified here.
#
# CRITICAL RULES:
#   - Only include metrics you can VERIFY and DEFEND in an interview
#   - Never fabricate or estimate — every number must be real
#   - Bullet format: • [tag] Action verb + context + metric
#   - Tags must match resume_tags in candidate_profile.json
#   - Section headers (## Company Name) must EXACTLY match bank_key in candidate_profile.json
#
# BULLET FORMAT:
#   • [tag] Led experimentation programme across 3 product verticals,
#            improving conversion by 18%.
#   • [tag] Built end-to-end pricing model reducing inventory holding
#            from 40 to 25 days.
#
# TAGS:
#   Tags are how auto_prep.py selects domain-relevant bullets.
#   Define your tags in candidate_profile.json → resume_tags.
#   A bullet can have multiple tags: • [tag1][tag2] Bullet text
#   Example tags (analytics domain):
#     [product]    → product analytics / A-B testing / funnels
#     [crm]        → CRM / lifecycle / retention / segmentation
#     [pricing]    → pricing / commercial / revenue optimisation
#     [leadership] → team management / capability building
#     [data]       → data infrastructure / tooling / platform
#   Example tags (software domain):
#     [backend]    → server-side / API / microservices
#     [platform]   → infrastructure / devops / reliability
#     [leadership] → team management / hiring / mentoring
#
# SECTION HEADER FORMAT:
#   ## [EXACT COMPANY NAME matching bank_key in candidate_profile.json]
#   [Role Title] | [Start Date] – [End Date]
#   [Location] (optional)
#
# AFTER WRITING: run python3 scripts/check_workflow.py to validate
# ════════════════════════════════════════════════════════════════


## [Company A Name]
[Your Most Recent Role Title] | [Month YYYY] – Present
[City, Country] (optional)

• [tag] [Action verb] [what you did] [context] [result/metric — real, verifiable].
• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].

[Add more bullets as needed. auto_prep.py selects based on max_bullets and JD domain.]


## [Company B Name]
[Previous Role Title] | [Month YYYY] – [Month YYYY]
[City, Country] (optional)

• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].


## [Company C Name]
[Earlier Role Title] | [Month YYYY] – [Month YYYY]
[City, Country] (optional)

• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].
• [tag] [Action verb] [what you did] [context] [result/metric].


# ════════════════════════════════════════════════════════════════
# WORKED EXAMPLE (analytics domain — replace with your content)
# ════════════════════════════════════════════════════════════════
# ## Acme Corp
# Senior Analytics Manager | Jan 2023 – Present
#
# • [product][leadership] Led a team of 5 analysts delivering product analytics
#    across checkout, search, and recommendations — supporting 12M monthly active users.
# • [product] Designed and shipped A/B testing framework reducing experiment
#    cycle time by 40%, enabling 3x more experiments per quarter.
# • [crm] Built propensity model targeting 30% of user base, capturing 70% of
#    high-intent customers and cutting marketing spend by 35%.
# • [leadership] Introduced weekly data review cadence with 4 product squads,
#    improving data-driven decision coverage from 30% to 85% of roadmap items.
# • [data] Migrated 150+ legacy dashboards from Excel to Tableau, reducing
#    reporting time from 3 days to same-day.
#
# ## Previous Company
# Data Analyst | Jun 2020 – Dec 2022
#
# • [product] Developed XGBoost delivery prediction model achieving 85% accuracy,
#    reducing late deliveries by 7%.
# • [data] Built SQL-based data pipeline automating daily KPI reporting for
#    operations team (12 hours/week saved).
# ════════════════════════════════════════════════════════════════
