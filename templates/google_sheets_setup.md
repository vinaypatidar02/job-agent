# templates/google_sheets_setup.md — Google Sheets Setup Guide
# ════════════════════════════════════════════════════════════════
# Complete guide to set up the Google Sheet that acts as the
# human-readable dashboard for your job application pipeline.
# ════════════════════════════════════════════════════════════════


## What the Sheet does

- Mirrors `data/job_tracker.json` in a human-readable format
- Lets you approve jobs, add ATS URLs, and add notes
- Changes sync back to the local tracker via `sheets_sync.py pull`
- Archive tab shows all rejected / stale jobs (separate from active pipeline)
- Outreach tab shows referral contacts (optional)

You do NOT need to manually create columns — sheets_sync.py creates all headers
automatically on first push.


## Step 1 — Create a Google Cloud Project and Enable Sheets API

1. Go to: console.cloud.google.com
2. Create a new project (e.g. "job-automation")
3. In the project, go to: APIs & Services → Library
4. Search for "Google Sheets API" and click Enable
5. Search for "Google Drive API" and click Enable


## Step 2 — Create a Service Account

1. Go to: APIs & Services → Credentials
2. Click "Create Credentials" → Service Account
3. Enter a name (e.g. "job-automation-sheets")
4. Click Create and Continue
5. Skip the optional role and user access steps
6. Click Done

The service account has an email address like:
`job-automation-sheets@your-project.iam.gserviceaccount.com`
**Copy this email — you will need it in Step 4.**


## Step 3 — Download the Service Account JSON Key

1. In Credentials, click on the service account you just created
2. Go to the "Keys" tab
3. Click "Add Key" → Create new key → JSON
4. Download the JSON file
5. Rename it to: `google_service_account.json`
6. Move it to: `data/google_service_account.json` in this project
7. Verify it is listed in `.gitignore` — **NEVER commit this file**


## Step 4 — Create the Google Sheet

1. Go to: sheets.google.com → Create new spreadsheet
2. Give it a name (e.g. "Job Application Pipeline")
3. Copy the Sheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/[THIS_IS_THE_SHEET_ID]/edit
   ```
4. Add `GOOGLE_SHEET_ID=[your-sheet-id]` to your `.env` file


## Step 5 — Share the Sheet with the Service Account

1. In the Google Sheet, click Share (top right)
2. Enter the service account email from Step 2
3. Give it "Editor" permission
4. Uncheck "Notify people" (the service account has no inbox)
5. Click Share


## Step 6 — First Push (creates all column headers)

```bash
python3 scripts/sheets_sync.py push
```

This creates all tabs (Applications, Archive, Outreach) and column headers automatically.
You do not need to set up any columns manually.

Expected output:
```
Pushing to Google Sheet...
Applications tab: 0 rows
Archive tab: 0 rows
Push complete.
```


## Sheet Structure

### Applications Tab (active jobs)

| Column | Key | User editable? | Notes |
|--------|-----|---------------|-------|
| A | app_id | No | Internal ID |
| B | company | No | Scraped |
| C | role | No | Scraped |
| D | location | No | Scraped |
| E | market | No | uk/nl/de/etc |
| F | fit_score | No | 0-100 |
| G | posted_date | No | |
| H | status | YES | Change here to approve/reject |
| I | rejection_reason | No | |
| J | flags | No | Salary TBC, Unconfirmed, etc |
| K | career_page_url | YES | Add ATS URL here before Approving |
| L | salary_stated | No | |
| M | salary_gate | No | passed/failed/tbc |
| N | role_type | YES | permanent_hybrid/contract_remote/etc |
| O | is_contract | YES | true/false |
| ... | [more columns] | No | See scripts/CLAUDE.md for full schema |
| AI | notes | YES | Free text notes |

**User-editable columns: H (status), K (career_page_url), N (role_type), O (is_contract), AI (notes)**

### Archive Tab

All inactive jobs: Rejected, Auto-Rejected, Withdrawn, Stale.

To re-activate a Stale job:
1. Change its status in Archive tab to "Shortlisted" or "Review Needed"
2. Run: `python3 scripts/sheets_sync.py pull --tabs apps,archive`
3. The job moves back to Applications tab in job_tracker.json

### Outreach Tab (optional)

Referral contacts and outreach tracking. Populated by referral workflow.


## Common Issues

**PermissionDenied error:**
The service account email was not added to the Sheet as Editor.
Go to Share → check the service account email is listed with Editor access.

**WORKSHEET_NOT_FOUND:**
The Sheet tabs don't exist yet. Run `push` without `--tabs` flag first to create them.

**Quota exceeded:**
Google Sheets API has a 100 requests/100 seconds limit per user.
The pipeline uses batching to stay well within this. If you hit limits, add a delay
between push/pull runs.

**Changes lost on push:**
Always run `pull` before `push` in the same session.
Push overwrites Sheet contents from local JSON — any Sheet edits since the last pull
(status changes, URLs added) will be lost.
