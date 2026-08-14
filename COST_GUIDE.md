# Cost Guide

All costs involved in running this pipeline, from fixed subscriptions to per-run API usage.

---

## Fixed Monthly Subscriptions

| Service | Plan | Cost | Notes |
|---------|------|------|-------|
| Claude Code | Pro | $20/month | Required for interactive pipeline orchestration. Includes Sonnet 4.6 sessions. Does NOT cover API calls made by scripts. |
| Claude API | Pay-as-you-go | See below | Billed separately from the subscription. Used by score_jobs.py, generate_summaries.py, generate_covers.py. |
| Apify | Free tier | $0/month | Includes $5 free credit each month. Covers approximately 6–7 full international scout runs. After $5: $0.001/job. |
| Google Sheets API | Free | $0/month | Via service account. The free tier is more than sufficient. |
| Email (IMAP) | Free | $0/month | Yahoo, Gmail, or Outlook — no additional cost. |

### Claude Code Pro subscription

The $20/month Claude Code subscription covers your interactive Claude Code sessions:
planning, reviewing scout results, running application prep, drafting referral messages.

It does NOT cover API calls made by the pipeline scripts. Those are billed separately
to your Anthropic account via `ANTHROPIC_API_KEY`. Your scripts and your interactive
sessions draw from different budgets.

### Apify free credit

Apify includes $5 of free credit every month. With $0.001 per job scraped:

- 100 jobs per search × $0.001 = $0.10 per search
- A typical international run (7 searches) costs at most $0.70
- The $5 monthly credit covers approximately 7 full international runs at zero cost
- After the free credit is consumed, you pay $0.001 per job

The pipeline caches Apify results for 24 hours. If you re-run a scout on the same day,
the cached results are reused at zero cost.

---

## Variable Costs — Claude API (per scout run)

### Job Scout (score_jobs.py)

| Stage | Model | Mode | Cost per 50 jobs scored |
|-------|-------|------|------------------------|
| Pass 1 — Python rules | None | Free | $0.00 |
| Pass 2 — Claude scoring | Haiku 4.5 | Batch + prompt cache | ~$0.05–0.15 |
| **Total per scout run** | | | **~$0.05–0.25** |

Pass 1 (Python rules) filters 30–60% of jobs before Claude is called. You only pay
for Pass 2 on jobs that pass the free pre-filter.

### Application Prep (per application)

| Stage | Model | Mode | Cost |
|-------|-------|------|------|
| generate_summaries.py | Haiku 4.5 | Batch | ~$0.002 |
| generate_covers.py | Sonnet 4.6 | Batch + prompt cache | ~$0.05–0.10 |
| auto_prep.py / finalize / pdf_renderer | Python | Free | $0.00 |
| **Total per application** | | | **~$0.05–0.12** |

---

## Cost Optimisations (built in — never disable)

### 1. Apify 24h cache
Re-running a scout on the same day reuses the cached Apify results. Cost: $0.

### 2. Claude Batch API
All LLM calls in score_jobs.py, generate_summaries.py, and generate_covers.py use
the Anthropic Batch API. Batch pricing is 50% of real-time pricing.

### 3. Claude prompt caching
The same system prompt is sent to Claude for every job in a given market. After the
first request in a batch, the prompt is cached — subsequent requests save approximately
90% of input token costs. This is the largest cost saving in the pipeline.

### 4. Pass 1 Python rules
Before Claude is invoked at all, score_jobs.py applies free Python-based rules:
title rejection patterns, stale-posting age gates, language gates, salary pre-screens.
Depending on your configuration, 30–60% of scraped jobs are filtered here at zero cost.

---

## Practical Monthly Estimates

| Scenario | Scout Runs | Applications Prepped | Apify Cost | Claude API | Total API |
|----------|-----------|----------------------|-----------|-----------|-----------|
| Light (1 run/week, 3 apps/week) | 4 | 12 | $0.00* | ~$0.80 | ~$0.80/mo |
| Active (2 runs/week, 5 apps/week) | 8 | 20 | ~$1.40 | ~$2.00 | ~$3.40/mo |
| Heavy (daily scout, 10 apps/week) | 20 | 40 | ~$6.00 | ~$4.50 | ~$10.50/mo |

*Light scenario stays within the $5/month Apify free credit.

Add $20/month for the Claude Code Pro subscription to any scenario above.

---

## How to Reduce Costs

**Limit market scope**
```bash
python3 scripts/run_scout.py --market uk   # UK only, instead of intl
```

**Lower the jobs-per-search cap**

In `scripts/run_scout.py`, reduce the third element of each `SEARCHES_APIFY` tuple:
```python
("Senior Engineer", "https://linkedin.com/jobs/...", 50)  # was 100
```

**Tighten Pass 1 filters**

Add more patterns to `TITLE_REJECT_CONTAINS` and `COMPANY_TYPE_BLOCKLIST` in
`scripts/score_jobs.py`. More Pass 1 rejects = fewer Pass 2 Claude calls.

**Use Haiku for cover letters**

In `scripts/generate_covers.py`, change the model constant from `claude-sonnet-4-6`
to `claude-haiku-4-5-20251001`. Cover quality decreases but cost drops approximately 3x.

**Use dry-run before spending credits**

```bash
python3 scripts/run_scout.py --dry-run
```

Shows your search plan and cost estimate without calling any API.

---

## Cost Tracking

Monitor your actual spend:
- Anthropic API usage: console.anthropic.com → Usage
- Apify usage: console.apify.com → Billing
- Apify cache status: `python3 scripts/apify_cache.py status`
