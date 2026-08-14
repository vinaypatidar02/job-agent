# docs/candidate-profile.md — Candidate Profile Template
# Referenced by CLAUDE.md §2 via @docs/candidate-profile.md
# Fill in your details below. Claude reads this at session start.
# All fields marked [YOUR_...] must be replaced before going live.


[CONTEXT] Name: [YOUR_FULL_NAME]
[CONTEXT] Current location: [YOUR_CITY], [YOUR_COUNTRY]
[CONTEXT] Target markets: [LIST MARKETS — e.g. United Kingdom (Skilled Worker Visa), Netherlands (Kennismigrant)]
[CONTEXT] Visa: [DESCRIBE YOUR VISA SITUATION — e.g. "Requires Skilled Worker Visa sponsorship.
          Only apply to roles explicitly stating visa sponsorship is available, or where the
          company is a known sponsor." OR "EU citizen — right to work in all EU markets."]

[CONTEXT] has_right_to_work markets: [LIST MARKET CODES where you already have work authorisation,
          or "None — sponsorship required in all markets" — configure in candidate_profile.json]

[CONTEXT] Total experience: [X]+ years in [YOUR_PRIMARY_DOMAIN]

[CONTEXT] Career summary:
  [List your roles in reverse chronological order — most recent first]
  - [Role Title] @ [Company] ([Start Date] – [End Date])
    [2-3 sentence summary of scope and key achievements]
  - [Previous Role] @ [Company] ([Start Date] – [End Date])
    [2-3 sentence summary]
  [Continue for all relevant roles]

[CONTEXT] Core expertise areas (use these for JD matching):
  [List your core competencies — Claude uses these to match against JD requirements]
  Example (analytics): Product Analytics, Growth Analytics, Experimentation,
    Pricing & Commercial Optimisation, Customer Lifecycle Analytics,
    KPI Strategy, Analytics Transformation, Stakeholder Management

[CONTEXT] Technical stack:
  [List your technical skills — Claude includes these in Skills section matching]
  Example: SQL, Python, Tableau, BigQuery, AWS Redshift, Git/GitHub

[CONTEXT] Data platform per employer — NEVER mix these up (wrong platform = credibility risk):
  [Company A]:  [Platform — e.g. AWS (Redshift)]
  [Company B]:  [Platform — e.g. GCP (BigQuery)]
  [Add all employers with the data platform used in that role]

[CONTEXT] [COMPANY/PRODUCT IDENTITY] — used when drafting Q&A and cover letters:
  [Add any product descriptions or business model notes that must be precise]
  Example: "[Company B] is a used two-wheeler marketplace — NEVER 'used car' or 'used vehicle'."
  [These prevent credibility-damaging mistakes in answers and outreach]

[RULE] [EXCLUDED TOOLS — tools you cannot defend in interviews]:
  [List tools you used historically but are not confident defending today]
  NEVER mention these in Skills section, Core Expertise, Profile Summary, Cover Letters, or Q&A.
  ALLOWED: CV work history bullets (historical factual record).
  Configure formally in candidate_profile.json → profile.excluded_tools

[CONTEXT] Team leadership (use for Manager-level JDs):
  [Describe your people management experience with headcounts if applicable]
  Example: "[Company A]: managed team of 5 analysts. [Company B]: led team of 3 analysts."

[CONTEXT] [DOMAIN-SPECIFIC EXPERIENCE — add any additional context Claude should know]:
  [Add domain-specific framing rules, product knowledge, or expertise context]
  Example: "Personal investment experience: 7+ years active equity investor.
  Use when JD is: hedge fund, asset management, investment bank."

[CONTEXT] [INTERNATIONAL EXPERIENCE — if applicable]:
  [Describe any international relocation, onsite deployments, or cross-border work]
  Example: "Deployed onsite to [City, Country] for [X] months during [Y]-year tenure at [Company]."
  FRAMING: always anchor inside the longer tenure — never present as a standalone short job.
  Use when: relocation questions, "why should we consider you from abroad", international team experience.

[CONTEXT] Education: [Degree Title], [University Name], [Year] (GPA [X]/10 if relevant)

[CONTEXT] Certifications:
  [List certifications most relevant first]
  Example: "[Certification Name] — [Issuer] ([Year])"
