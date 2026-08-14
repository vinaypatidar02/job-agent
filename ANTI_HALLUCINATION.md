# Anti-Hallucination Design

This document explains how the pipeline prevents LLM fabrication and how to configure
the validation layer for your own profile.

---

## The Experience Bank Philosophy

The pipeline's primary anti-hallucination mechanism is `data/content/experience_bank.md`.

`auto_prep.py` selects resume bullets ONLY from this file. It cannot invent content.
The LLM is given a bounded set of pre-written bullets and asked to select and reorder them
for the target JD — not to create new ones.

This means: **if it is not in experience_bank.md, it will not appear in the resume.**

Consequences:
- No bullet appears in a resume that was not first written and verified by you.
- Metrics (percentages, team sizes, timelines) are preserved verbatim — never rounded or paraphrased.
- The LLM's role in resume generation is selection and ordering, not authorship.
- Cover letter generation draws from the selected bullets, not from general knowledge of your career.

### Writing a good experience_bank.md

- Use `action verb + context + metric` for every bullet.
- Include all bullets you ever want to appear — the pipeline selects the best subset per JD.
- Order bullets within a role by impact (highest first).
- Only include metrics you can verify and defend in an interview.
- Tag bullets with `[tag]` labels so the pipeline can match them to JD domains.

---

## Validation Checks (V1–V23)

`validate_prep.py` runs all checks before every PDF render. Hard failures block rendering.

| Check | What it verifies | Config source | Failure type |
|-------|-----------------|---------------|-------------|
| V1 | Required portfolio tools appear in Skills section | `profile.required_portfolio_tools.tools` | FAIL |
| V2 | Excluded tools do NOT appear outside work history bullets | `profile.excluded_tools.tools` | FAIL |
| V3 | Bullet count per role does not exceed max_bullets | `experience[].max_bullets` | FAIL |
| V4 | No FILL_ME placeholders remain in any field | automatic | FAIL |
| V5 | No unresolved [COMPANY_HOOK: ...] template in cover letter | automatic | FAIL |
| V6 | Resume content fits within 2 pages (estimated) | automatic | WARN |
| V7 | Canonical metrics appear verbatim — not rounded or paraphrased | `profile.canonical_metrics.metrics` | FAIL |
| V8 | Work history bullets traceable to experience_bank.md (spot check) | automatic | WARN |
| V9 | No third-person pronouns (he / his / him) in Profile Summary | automatic | WARN |
| V10 | Finance/investment domain: personal investment sentence placed correctly | `profile.verbatim_sentences.investment_sentence` | WARN |
| V11 | Profile Summary has exactly 3 LLM-generated sentences before verbatim appends | automatic | WARN |
| V12 | S3 ends with terminal punctuation (not truncated) | automatic | WARN |
| V13 | British English spellings used — no American variants | automatic | WARN |
| V14 | Each bullet is 28 words or fewer | automatic | WARN |
| V15 | Cover letter is 350–450 words | automatic | WARN |
| V16 | Company name appears in cover letter Para 1 | automatic | FAIL |
| V17 | Only industries in industry_whitelist are claimed | `profile.industry_whitelist.industries` | WARN |
| V18 | No third-person pronouns in cover letter body | automatic | WARN |
| V19 | AI project tense is "have built... fully operational" (not "currently building") | automatic | WARN |
| V20 | Excluded tools not mentioned in cover letter or Q&A | `profile.excluded_tools.tools` | WARN |
| V21 | Only real tools (from core_skills or experience_bank.md) appear in Skills section | automatic | WARN |
| V22 | Cover letter Para 4 uses the correct visa/permit name for the target market | automatic | WARN |
| V23 | PDF metadata (title, author, creator) read from candidate_profile.json — not hardcoded | automatic | WARN |

**FAIL** — rendering is blocked until the issue is fixed.
**WARN** — flagged to the user but rendering proceeds.

---

## How to Configure Validation

Most checks are automatic and require no configuration. Config-driven checks read
from `data/content/candidate_profile.json`:

```json
"profile": {
  "required_portfolio_tools": {
    "tools": ["Python", "SQL"]
  },
  "excluded_tools": {
    "tools": ["Tool X", "Tool Y"]
  },
  "canonical_metrics": {
    "metrics": ["40%", "3x throughput improvement"]
  },
  "industry_whitelist": {
    "industries": ["ecommerce", "fintech", "marketplace"]
  }
}
```

Leave any list empty (`[]`) to skip that check. This is the safe default for new users —
all checks are safe to skip until you have defined your own profile constraints.

### required_portfolio_tools (V1)

List tools you have built public or portfolio work with. If a JD requires Tool A and
you have it in required_portfolio_tools, the pipeline verifies it appears in the Skills
section of the generated resume. Prevents a skills mismatch between your resume and the JD.

### excluded_tools (V2 + V20)

List tools you have used historically but cannot defend in an interview. These are blocked
from appearing in the Skills section, Profile Summary, and cover letter — but are still
allowed in `experience_bank.md` work history bullets (as historical facts).

Example: a tool used in an early role that you are no longer current on.

### canonical_metrics (V7)

Exact metric strings that must appear unchanged in the final output. If a metric is
configured here and the LLM paraphrases it (e.g. "approximately 40%"), V7 flags it.

Only configure metrics that are precisely stated figures from real outcomes.

### industry_whitelist (V17)

Industries you can honestly claim in answers and cover letters. V17 soft-warns if a
generated output claims an industry not in this list.

Leave empty to allow all industries — useful if your background spans many sectors.

---

## How LLM Outputs Are Staged Before Writing

No LLM output goes directly to a file the user uploads. Every output passes through
a staging and validation layer first:

```
score_jobs.py          → scored_jobs.json           (reviewed, then write_tracker.py)
auto_prep.py           → data/prep_tmp/auto_resume_*.json
generate_summaries.py  → updates auto_resume_*.json  (replaces instruction placeholder)
generate_covers.py     → data/prep_tmp/auto_cover_*.json
finalize_resumes.py    → data/prep_tmp/final_resume_*.json
finalize_cover.py      → data/prep_tmp/final_cover_*.json
validate_prep.py       → runs V1–V23 — FAIL blocks next step
pdf_renderer.py        → outputs/applications/ready/[folder]/[YOUR_NAME]_CV.pdf
                       → outputs/applications/ready/[folder]/[YOUR_NAME]_CoverLetter.pdf
```

The PDF is the last step. By the time it is rendered, the content has been:
1. Selected from experience_bank.md (not invented)
2. Staged to a JSON intermediate file
3. Checked by validate_prep.py
4. Confirmed readable by finalize scripts

---

## British English Enforcement

All generated text uses British English spellings throughout. American spellings are
blocked before rendering:

| American | British |
|----------|---------|
| optimization | optimisation |
| modeling | modelling |
| behavioral | behavioural |
| prioritize | prioritise |
| analyze | analyse |
| organize | organise |
| utilize | utilise |
| visualize | visualise |

`scripts/common.py` provides `enforce_british_english()`. This function is called
by `auto_prep.py`, `generate_summaries.py`, and `generate_covers.py` before any
content is written to the intermediate JSON files.

V13 in validate_prep.py soft-warns if any American spellings are found in the final output.
