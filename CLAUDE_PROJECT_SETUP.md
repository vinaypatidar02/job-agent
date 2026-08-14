# CLAUDE_PROJECT_SETUP.md — Claude Code Setup Guide

This guide walks through setting up Claude Code to run this pipeline interactively.
Complete SETUP.md first (Python environment, .env, candidate_profile.json, experience_bank.md).

---

## 1. Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
claude --version    # verify install
```

Also available as:
- Desktop app (Mac/Windows): download from claude.ai/code
- VS Code extension: search "Claude Code" in the Extensions panel
- JetBrains plugin: available in the JetBrains Marketplace

---

## 2. Subscribe to Claude Code Pro

- Go to claude.ai/code and subscribe to the Pro plan ($20/month)
- The Pro subscription covers your interactive Claude Code sessions (planning, reviewing, manual prep)
- It does NOT cover Claude API calls made by scripts — those are billed separately via ANTHROPIC_API_KEY to your Anthropic account balance

---

## 3. Sign in

```bash
claude login
# Opens a browser authentication page — complete the sign-in flow
```

---

## 4. Open the project

```bash
cd /path/to/Claude-Workflow-Automation-public
claude
```

Claude Code reads `CLAUDE.md` automatically at startup. The full pipeline context — candidate profile, scoring rubric, file map, behavioural rules — is loaded into the session without any manual prompting.

---

## 5. Verify MCP server (Apify)

The `mcp.json` file is already configured. It reads `APIFY_TOKEN` from your `.env` file automatically via `${APIFY_TOKEN}`.

```json
{
  "mcpServers": {
    "apify": {
      "command": "npx",
      "args": ["-y", "@apify/actors-mcp-server", "--actors", "bebity/linkedin-jobs-scraper"],
      "env": {
        "APIFY_TOKEN": "${APIFY_TOKEN}"
      }
    }
  }
}
```

Verify the MCP server loaded: in Claude Code, type `/mcp` — `apify` should appear in the list with status `connected`.

If MCP does not load:
- Confirm `APIFY_TOKEN` is set in `.env`
- Confirm Node.js 16+ is installed: `node --version`
- Try restarting Claude Code

---

## 6. Verify hooks

The `on_job_approved` hook is wired in `.claude/settings.json`. It fires after every write to `job_tracker.json` and checks whether any newly-written entries have status `Approved`.

```bash
cat .claude/settings.json
```

Expected output includes a `PostToolUse` hook entry matching writes to `job_tracker.json` that runs `hooks/on_job_approved.md`.

When working correctly: after you run `sheets_sync.py pull` and a job transitions to `Approved`, Claude Code automatically detects it and offers to start application prep for that job.

---

## 7. Run the integrity check

```bash
python3 scripts/check_workflow.py
```

All checks must pass before running your first scout. Common failures and fixes are in SETUP.md Troubleshooting.

---

## 8. GitHub Actions (optional — daily automated scouts)

The `.github/workflows/daily_scout.yml` file can run the scout on a cron schedule without opening Claude Code manually.

### Required GitHub Secrets

Go to your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |
| `APIFY_TOKEN` | Your Apify API token |
| `GOOGLE_SHEET_ID` | Your Google Sheet ID |
| `GOOGLE_SA_JSON` | Full JSON contents of `data/google_service_account.json` |
| `GIT_USER_EMAIL` | Your git commit email address |
| `GIT_USER_NAME` | Your git username |

### Configure schedule and market

Edit `.github/workflows/daily_scout.yml`:

```yaml
on:
  schedule:
    - cron: '0 8 * * 1-5'   # 8am UTC, Monday–Friday — adjust to your preferred time
```

```yaml
- name: Run scout
  run: python3 scripts/run_scout.py --market intl --yes   # change market as needed
```

The workflow commits updated `data/job_tracker.json` and `data/auto_rejected.json` back to the repo after each run, so your local copy stays in sync via `git pull`.

---

## 9. Daily session workflow

```
Morning:
  cd project && claude                                         # open Claude Code

  "check email"                                                # classify overnight replies
  "run scout intl" or "run scout uk"                          # discover new jobs
  Review Google Sheet — add ATS URLs, set status to Approved
  "pull from sheet"                                            # bring approvals into tracker
  "run application prep"                                       # generate resume + cover letter
  Apply via ATS / draft outreach message

  "sync to sheet"                                              # push status updates
```

---

## 10. How CLAUDE.md context loading works

Claude Code reads `CLAUDE.md` at session start and keeps it in context throughout the session. The file imports two additional files via `@docs/...` syntax:

```
CLAUDE.md §2 → @docs/candidate-profile.md     (your career profile — who you are)
CLAUDE.md §4 → @docs/fit-scoring-rubric.md    (how to score jobs — what you want)
CLAUDE.md §8 → @docs/project-file-map.md      (where files live — pipeline structure)
```

This means you can update your candidate profile, scoring rubric, or file map independently without editing the root `CLAUDE.md`.

Skill files (`skills/*.md`) and agent files (`agents/*.md`) are loaded on demand — Claude reads them when a skill or agent is invoked. They do not need to be in context at session start.

---

## 11. Updating CLAUDE.md for your profession

Edit these sections to reflect your job search (not the defaults):

| Section | What to fill |
|---------|-------------|
| §2 — Candidate Profile | Your name, location, visa situation, career summary, technical stack |
| §3 — Job Search Preferences | Target roles, salary threshold, preferred cities, industry preferences |
| §4 — Fit Scoring Rubric | (edit docs/fit-scoring-rubric.md) Title tiers, domain scoring, skills list |

Leave sections §5–§13 as-is — they contain pipeline rules that apply regardless of profession.
