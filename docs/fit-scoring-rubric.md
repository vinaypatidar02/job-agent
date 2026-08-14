# docs/fit-scoring-rubric.md — Fit Scoring Rubric Template
# Referenced by CLAUDE.md §4 via @docs/fit-scoring-rubric.md
# Fill in YOUR career criteria. Claude reads this during Pass 2 scoring.
# Replace all [YOUR_...] placeholders with values specific to your profession.
#
# After editing: run python3 scripts/check_workflow.py to verify.


[CONTEXT] Fit scoring is on a 0–100 scale. Breakdown:

  ROLE TITLE MATCH           (0–20 points)
  ─────────────────────────────────────────
  [Fill in your target titles. Be specific — list ALL title variants you are qualified for.]

    20 = Tier 1 — Your most senior target titles:
         [YOUR_TIER1_TITLE_1], [YOUR_TIER1_TITLE_2], [YOUR_TIER1_TITLE_3]
         Include all seniority variants (Manager, Lead, Head, Principal, Director-equivalent).
         EXAMPLE (analytics): Analytics Manager, Lead Data Analyst, Head of Analytics,
           Lead Business Analyst, Growth Analytics Lead, Data & AI Manager
         EXAMPLE (software):  Staff Engineer, Engineering Manager, Principal Engineer,
           Head of Engineering, VP Engineering (if reachable)
         EXAMPLE (finance):   Finance Director, Head of FP&A, VP Finance, CFO (small companies)

    15 = Tier 2 — Strong senior adjacent titles:
         [YOUR_TIER2_TITLE_1], [YOUR_TIER2_TITLE_2]
         EXAMPLE (analytics): Senior Business Analyst, BI Manager, Senior Analytics Engineer
         EXAMPLE (software):  Senior Software Engineer, Tech Lead, Engineering Manager (smaller scope)
         EXAMPLE (finance):   Senior Financial Analyst, Finance Manager, Risk Manager

    10 = Tier 3 — Acceptable senior IC or specialist titles:
         [YOUR_TIER3_TITLE]
         EXAMPLE: Senior Data Analyst, Senior Developer, Senior Financial Analyst

     5 = Tier 4 — Below target; only if company or market is exceptional:
         [YOUR_TIER4_TITLE]
         EXAMPLE: Business Analyst, Software Engineer (non-senior), Financial Analyst

     0 = Unrelated title

  Human review queue priority within Review Needed (60–74):
    Sort by title tier (Tier 1 first), then fit_score within same tier.

  DOMAIN MATCH               (0–25 points)
  ─────────────────────────────────────────
  [Define the industries and company types you most want to work in.]

    25 = Your primary domains (where you have most experience and interest):
         [YOUR_PRIMARY_DOMAIN_1], [YOUR_PRIMARY_DOMAIN_2]
         EXAMPLE (analytics): Product-led tech, fintech, ecommerce, marketplace, SaaS
         EXAMPLE (software):  Consumer apps, developer tools, infrastructure platforms
         EXAMPLE (finance):   Asset management, investment banking, fintech, trading firms

    15 = Your secondary domains (acceptable, not ideal):
         [YOUR_SECONDARY_DOMAIN]
         EXAMPLE: Enterprise software, B2B SaaS, logistics tech, healthtech

     5 = Tertiary or less preferred:
         [YOUR_TERTIARY_DOMAIN]
         EXAMPLE: Traditional enterprise, non-tech companies, government adjacent

     0 = Unrelated domain (manufacturing, public sector, etc.)

  NOTE: If [YOUR_NON_PREFERRED_COMPANY_TYPE], only shortlist if score ≥ 88 overall AND
        company is well-known. [Configure this threshold in score_jobs.py USER CONFIG.]

  SKILLS MATCH               (0–25 points)
  ─────────────────────────────────────────
  [List your core technical skills. Score based on overlap with these in the JD.]

  Score based on overlap with: [YOUR_SKILL_1], [YOUR_SKILL_2], [YOUR_SKILL_3],
    [YOUR_SKILL_4], [YOUR_SKILL_5], [YOUR_SKILL_6], [YOUR_SKILL_7]

  EXAMPLE (analytics): SQL, Python, Tableau, BigQuery, Redshift, Looker,
    experimentation / A/B testing, CRM analytics, pricing, Anthropic API / Claude Code
  EXAMPLE (software):  Python/Go/Java, Kubernetes, AWS/GCP, distributed systems,
    microservices, CI/CD, PostgreSQL, system design
  EXAMPLE (finance):   Excel/VBA, Python, SQL, Bloomberg, financial modelling,
    DCF analysis, risk management, regulatory reporting

    25 = 7+ skills match
    15 = 4–6 skills match
     5 = 1–3 skills match

  SENIORITY MATCH            (0–15 points)
  ─────────────────────────────────────────
    15 = Your target level: [YOUR_TARGET_SENIORITY]
         EXAMPLE: Lead/Manager level — 5–10 years experience expected
    10 = Slightly senior (Director-adjacent) but reachable
     5 = Slightly junior but interesting scope or growth company
     0 = Clear mismatch (entry-level or C-suite / VP+ beyond reach)

  LOCATION                   (0–10 points)
  ─────────────────────────────────────────
  [Configure your preferred cities per market. Be specific — this drives daily decisions.]

  UK locations:
    10 = [YOUR_UK_TIER1_CITIES] — primary hubs
         EXAMPLE: London
     8 = [YOUR_UK_TIER2_CITIES] — strong secondaries
         EXAMPLE: Manchester, Birmingham
     6 = [YOUR_UK_TIER3_CITIES] — acceptable secondaries
         EXAMPLE: Leeds, Reading, Cambridge, Oxford, Leicester
     0 = Other UK cities or outside all tiers

  NL locations:
    10 = Amsterdam metro (Amstelveen, Hoofddorp, Schiphol, Haarlem, Diemen)
     8 = Rotterdam, The Hague, Utrecht + immediate metro
     6 = Leiden, Hilversum
     0 = Outside NL Tier 1

  DE locations:
    10 = Berlin
     8 = Munich, Frankfurt, Hamburg
     6 = Düsseldorf, Cologne, Bonn + Rhine-Main / Ruhr metro
     4 = Stuttgart, Hannover, Nuremberg, Karlsruhe, Leipzig, Bremen
     0 = Outside DE Tier 1

  DK locations:
    10 = Copenhagen metro (Frederiksberg, Hellerup, Gentofte, Ballerup, Brøndby)
     8 = Aarhus
     0 = Outside DK Tier 1

  IE locations:
    10 = Dublin metro (Dún Laoghaire, Sandyford, Leopardstown, Swords, Citywest)
     8 = Cork
     6 = Galway, Limerick
     0 = Outside IE Tier 1

  SE locations:
    10 = Stockholm
     8 = Gothenburg, Malmö
     0 = Outside SE Tier 1

  AE locations:
    10 = Dubai (DIFC, Business Bay, JLT, Dubai Internet City, Media City)
     8 = Abu Dhabi (ADGM, Masdar City)
     6 = Sharjah, Ajman
     0 = Outside AE Tier 1

  Remote override: if is_remote_only = true → location_score = 10 for ALL locations.

  VISA SPONSORSHIP           (0–5 points, or -10)
  ─────────────────────────────────────────
  [Note: markets in has_right_to_work skip this check — visa_score auto-set to 5]

     5 = Explicitly confirmed in JD ("visa sponsorship available", "we sponsor visas")
     0 = No mention — flag "Sponsorship Unconfirmed", do NOT reject
   -10 = Explicitly states no sponsorship → TOTAL SCORE becomes 0, status = "Auto-Rejected"


[RULE] Auto-shortlist if score ≥ 75 AND visa is not rejected.
[RULE] Flag for human review if score 60–74.
[RULE] Auto-reject if score < 60 OR visa sponsorship explicitly denied.
[RULE] Auto-reject Tier 4 titles: [YOUR_TIER4_ALWAYS_REJECT_TITLES] — below your experience level.
       Configure in score_jobs.py TITLE_REJECT_CONTAINS and classify_title.py _TIER4.
[RULE] Auto-reject [YOUR_PRIMARY_TOOLING_BLOCKLIST] primary roles: reject if your domain's
       irrelevant primary tool is the core requirement of the title.
       Configure in score_jobs.py TOOLING_PRIMARY_TITLE_BLOCKLIST.
