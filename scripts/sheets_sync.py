#!/usr/bin/env python3
"""
sheets_sync.py — Bidirectional sync: job_tracker.json ↔ Google Sheet
======================================================================
LEARNING NOTE — Why a sync layer rather than replacing job_tracker.json?

Agents need fast, offline, atomic reads/writes → local JSON.
You need a human-readable, clickable, editable view → Google Sheets.
A sync layer gives both. Agents write to JSON; this script pushes
to Sheets so you can see and edit. When you edit Sheets (status,
career_page_url, notes), this script pulls those changes back to JSON.

Two modes:
  push  — JSON → Sheets  (run after scrape/score/enrich)
  pull  — Sheets → JSON  (run before application prep, to pick up
                           your edits: status=Approved, career_page_url)

Usage:
  python3 scripts/sheets_sync.py push
  python3 scripts/sheets_sync.py pull

Setup (one-time, see README in this file):
  1. Create Google Cloud project, enable Sheets API + Drive API
  2. Create Service Account, download JSON key → save as
     data/google_service_account.json
  3. Create a new Google Sheet, share it with the service account email
  4. Copy the Sheet ID from the URL into .env as GOOGLE_SHEET_ID

Sheet structure (one row per application):
  Col A: id               (internal — for workflow matching, not for sharing)
  Col B: reference        (Company — Role, shareable with referral contacts)
  Col C: location         (read-only)
  Col D: posted_date      (read-only)
  Col E: fit_score        (read-only, populated after Stage 3)
  Col F: salary_stated    (read-only)
  Col G: experience_req   (read-only)
  Col H: status           ← YOU EDIT THIS — change to "Approved" when ready
                            NOTE: only change to Approved AFTER filling Col K
  Col I: entry_type       (read-only — Brand New / Reposted)
  Col J: jd_url           (read-only — hyperlink to LinkedIn/Adzuna JD)
  Col K: career_page_url  ← PASTE ATS URL HERE FIRST (before setting Approved)
  Col L: pros             (read-only — key strengths from scoring)
  Col M: cons             (read-only — key concerns from scoring)
  Col N: role_type              ← USER EDITABLE — 4-value: contract_remote | contract_hybrid |
                                  permanent_remote | permanent_hybrid (computed from is_contract + is_remote_only)
  Col O: is_contract            ← USER EDITABLE — fixed-term/contract flag (True/False)
  Col P: apply_recommendation   (read-only)
  Col Q: visa_sponsorship_status (read-only)
  Col R: actual_hiring_company   (read-only)
  Col S: agency_name      (read-only)
  Col T: company_sponsor_kb (read-only)
  Col U–AH: secondary columns (job_id, company, role, work_mode, applied_date,
            ats_type, tracking_url, source, match_exists,
            matched_entry_id, score_exists, latest_scoring_date, adzuna_salary_stated, market)
  Col AI: notes           ← YOU CAN ADD NOTES / referral contact name here
  Col AJ: eor_viability         (read-only — 1-10 EOR contractor suitability score; null for non-contract/non-remote)

  IMPORTANT EDIT ORDER:
    1. Paste career_page_url in Col K
    2. THEN change status to "Approved" in Col H
    3. THEN run: python3 scripts/sheets_sync.py pull
    application_prep agent will only fire when BOTH are present.
"""

import json, re, sys, os
from pathlib import Path
from datetime import datetime

# Import deterministic helpers from common (safe at module level — no side effects)
sys.path.insert(0, str(Path(__file__).parent))
from common import compute_role_type as _compute_role_type

ROOT          = Path(__file__).parent.parent
TRACKER       = ROOT / "data" / "job_tracker.json"
AUTO_REJ_FILE = ROOT / "data" / "auto_rejected.json"
SA_FILE       = ROOT / "data" / "google_service_account.json"
ENV_FILE      = ROOT / ".env"

# ── Load env vars ─────────────────────────────────────────────────────────────
env = {}
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

SHEET_ID = env.get("GOOGLE_SHEET_ID", "")

# ── Validate setup ────────────────────────────────────────────────────────────
def check_setup():
    errors = []
    if not SA_FILE.exists():
        errors.append(
            f"Service account file not found: {SA_FILE}\n"
            "  → Follow setup steps in this file's docstring"
        )
    if not SHEET_ID:
        errors.append(
            "GOOGLE_SHEET_ID not set in .env\n"
            "  → Create a Google Sheet, copy its ID from the URL\n"
            "    (the long string between /d/ and /edit)\n"
            "  → Add to .env: GOOGLE_SHEET_ID=your_sheet_id_here"
        )
    if errors:
        print("\n[sheets_sync] Setup incomplete:")
        for e in errors: print(f"  ✗ {e}")
        sys.exit(1)

# ── Connect to Google Sheets ──────────────────────────────────────────────────
def get_sheet():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("\n[sheets_sync] Missing dependencies. Install with:")
        print("  pip install gspread google-auth")
        sys.exit(1)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds  = Credentials.from_service_account_file(str(SA_FILE), scopes=scopes)
    gc     = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

# ── Outreach tab column definitions (human-readable, internal IDs removed) ────
OUTREACH_PLATFORM_HEADERS = [
    "Name", "Priority", "Markets", "Status", "Registered", "URL", "Notes",
]
OUTREACH_RECRUITER_HEADERS = [
    "Agency", "Consultant", "Market", "Speciality", "Method",
    "Contacted", "Status", "Response", "Email", "LinkedIn", "Notes",
]
OUTREACH_REFERRAL_HEADERS = [
    "Company", "Role", "Contact Name", "Contact Role", "Location",
    "Relationship", "Degree", "Channel", "Potential HM",
    "Is Relevant",  # index 9 — user-editable: Yes/No; pulled back to is_relevant_contact in outreach.json
    "Status", "Reached Out", "Response", "Notes",
]

# Status dropdown values per section
_PLATFORM_STATUSES  = ["Pending", "Registered", "Active", "Inactive"]
_RECRUITER_STATUSES = ["Not Contacted", "Messaged", "Replied", "In Progress", "No Response", "Closed"]
_REFERRAL_STATUSES  = ["Planned", "Reached-Out", "Followup", "Referred", "Stale-Referral", "No Response", "Declined"]

# Rank order for referral statuses — used to guard against stale-Sheet overwrites in _pull_outreach.
# Terminal statuses (Declined, Stale-Referral, No Response) are excluded from rank so they are
# always applied regardless of direction (mirrors _STATUS_RANK / _TERMINAL pattern for tracker).
_OUTREACH_REFERRAL_STATUS_RANK = {
    "Planned":              1,
    "Connection-Requested": 2,
    "Reached-Out":          3,
    "Followup":             4,
    "Referred":             5,
}
_OUTREACH_REFERRAL_TERMINAL = {"Declined", "Stale-Referral", "No Response"}

def _platform_to_row(p: dict) -> list:
    return [
        p.get("name", ""),
        p.get("priority", ""),
        ", ".join(p.get("markets") or []),
        p.get("status", ""),
        p.get("registered_date") or "",
        p.get("url") or "",
        p.get("notes") or "",
    ]

def _recruiter_to_row(r: dict) -> list:
    return [
        r.get("agency", ""),
        r.get("name") or "",
        r.get("market", ""),
        r.get("speciality") or "",
        r.get("method") or "",
        r.get("contacted_date") or "",
        r.get("status", ""),
        r.get("response_date") or "",
        r.get("email") or "",
        r.get("linkedin_url") or "",
        r.get("notes") or "",
    ]

def _referral_to_row(ref: dict) -> list:
    phm = ref.get("is_potential_hiring_manager")
    potential_hm = "Yes" if phm is True else ("No" if phm is False else "")
    irc = ref.get("is_relevant_contact")
    is_relevant = "Yes" if irc is True else ("No" if irc is False else "")
    return [
        ref.get("company", ""),
        ref.get("role", ""),
        ref.get("contact_name", ""),
        ref.get("contact_role", "") or "",
        ref.get("contact_location", "") or "",
        ref.get("relationship", "") or "",
        ref.get("connection_degree", "") or "",
        ref.get("channel", "") or "",
        potential_hm,
        is_relevant,                          # index 9 — Is Relevant (NEW)
        ref.get("status", ""),                # index 10 (shifted from 9)
        ref.get("reached_out_date", "") or "", # index 11 (shifted from 10)
        ref.get("response_date", "") or "",   # index 12 (shifted from 11)
        ref.get("notes", "") or "",           # index 13 (shifted from 12)
    ]

def _pull_outreach(wb) -> int:
    """Pull user-editable columns (Status, Response, Notes) from Outreach tab back to outreach.json.
    Matches referral rows by (company, role, contact_name). Returns count of updated entries."""
    import json as _json
    from pathlib import Path as _Path

    outreach_path = _Path(__file__).parent.parent / "data" / "outreach.json"
    if not outreach_path.exists():
        return 0

    try:
        ws = wb.worksheet("Outreach")
    except Exception:
        return 0

    all_rows = ws.get_all_values()
    data = _json.loads(outreach_path.read_text())
    referrals = data.get("referrals", [])

    # Build lookup: (company_lower, role_lower, contact_lower) → referral entry
    lookup = {}
    for ref in referrals:
        key = (
            (ref.get("company") or "").lower().strip(),
            (ref.get("role") or "").lower().strip(),
            (ref.get("contact_name") or "").lower().strip(),
        )
        lookup[key] = ref

    # Scan rows for REFERRALS section title
    ref_section_start = None
    for i, row in enumerate(all_rows):
        if row and str(row[0]).strip().upper() == "REFERRALS":
            ref_section_start = i + 2  # skip title + header row
            break

    if ref_section_start is None:
        return 0

    # REFERRAL header order (matches OUTREACH_REFERRAL_HEADERS):
    # 0=Company, 1=Role, 2=Contact Name, 3=Contact Role, 4=Location,
    # 5=Relationship, 6=Degree, 7=Channel, 8=Potential HM, 9=Is Relevant,
    # 10=Status, 11=Reached Out, 12=Response, 13=Notes

    updated = 0
    for row in all_rows[ref_section_start:]:
        if not any(c.strip() for c in row):
            break  # blank row = end of section
        company         = str(row[0]  if len(row) > 0  else "").strip()
        role            = str(row[1]  if len(row) > 1  else "").strip()
        contact_name    = str(row[2]  if len(row) > 2  else "").strip()
        is_relevant_str = str(row[9]  if len(row) > 9  else "").strip()
        status          = str(row[10] if len(row) > 10 else "").strip()
        reached_out     = str(row[11] if len(row) > 11 else "").strip()
        response        = str(row[12] if len(row) > 12 else "").strip()
        notes           = str(row[13] if len(row) > 13 else "").strip()

        if not contact_name:
            continue

        key = (company.lower(), role.lower(), contact_name.lower())
        ref = lookup.get(key)
        if ref is None:
            continue

        changed_fields = []
        # is_relevant_contact: user-set in Sheet — always authoritative, no stale-guard.
        # Only update when non-blank (blank = user hasn't set it yet; keep existing JSON value).
        if is_relevant_str in ("Yes", "No"):
            new_irc = (is_relevant_str == "Yes")
            if new_irc != ref.get("is_relevant_contact"):
                ref["is_relevant_contact"] = new_irc
                changed_fields.append(f"is_relevant_contact → {new_irc}")
        if status and status != (ref.get("status") or ""):
            local_s    = ref.get("status") or ""
            local_rank = _OUTREACH_REFERRAL_STATUS_RANK.get(local_s)
            sheet_rank = _OUTREACH_REFERRAL_STATUS_RANK.get(status)
            # Guard: skip backwards moves caused by a stale Sheet.
            # If local outreach status is already more advanced (higher rank) than what the Sheet
            # shows, the Sheet is lagging — we haven't pushed yet. Never regress local progress.
            # Terminal statuses (Declined, Stale-Referral) are always applied regardless of rank.
            if (local_rank is not None and sheet_rank is not None
                    and sheet_rank < local_rank
                    and local_s not in _OUTREACH_REFERRAL_TERMINAL
                    and status not in _OUTREACH_REFERRAL_TERMINAL):
                print(f"  ⚠ STALE SHEET SKIPPED (outreach): {company} / {contact_name} — "
                      f"Sheet shows '{status}' (rank {sheet_rank}) but local is already at "
                      f"'{local_s}' (rank {local_rank}). Run push first to sync the Sheet.")
            else:
                ref["status"] = status
                changed_fields.append(f"status → '{status}'")
        if reached_out and reached_out != (ref.get("reached_out_date") or ""):
            ref["reached_out_date"] = reached_out
            changed_fields.append(f"reached_out_date → '{reached_out}'")
        if response and response != (ref.get("response_date") or ""):
            ref["response_date"] = response
            changed_fields.append(f"response_date → '{response}'")
        if notes and notes != (ref.get("notes") or ""):
            ref["notes"] = notes
            changed_fields.append(f"notes → '{notes}'")

        if changed_fields:
            updated += 1
            print(f"  ✓ Outreach pull: {company} / {contact_name} — {', '.join(changed_fields)}")

    if updated:
        outreach_path.write_text(_json.dumps(data, indent=2, ensure_ascii=False))

    return updated


def _push_outreach(wb) -> None:
    """Push outreach.json platforms + recruiters + referrals to 'Outreach' sheet tab."""
    import json as _json
    import urllib.request as _ureq
    from google.auth.transport.requests import Request as GARequest
    from pathlib import Path as _Path

    outreach_path = _Path(__file__).parent.parent / "data" / "outreach.json"
    if not outreach_path.exists():
        return
    data       = _json.loads(outreach_path.read_text())
    platforms  = data.get("platforms", [])
    recruiters = data.get("recruiters", [])
    referrals  = data.get("referrals", [])

    max_cols = max(
        len(OUTREACH_PLATFORM_HEADERS),
        len(OUTREACH_RECRUITER_HEADERS),
        len(OUTREACH_REFERRAL_HEADERS),
    )

    def _pad(row): return row + [""] * (max_cols - len(row))

    # Section title rows (teal background applied via API below)
    plat_title = _pad(["PLATFORMS"])
    rec_title  = _pad(["RECRUITERS"])
    ref_title  = _pad(["REFERRALS"])
    blank      = _pad([])

    plat_data = [_platform_to_row(p) for p in platforms]
    rec_data  = [_recruiter_to_row(r) for r in recruiters]
    ref_data  = [_referral_to_row(r) for r in referrals]

    all_rows = (
        [plat_title, _pad(OUTREACH_PLATFORM_HEADERS)] + plat_data + [blank] +
        [rec_title,  _pad(OUTREACH_RECRUITER_HEADERS)] + rec_data  + [blank] +
        [ref_title,  _pad(OUTREACH_REFERRAL_HEADERS)]  + ref_data
    )

    # Compute 0-based row indices for each section
    plat_title_r  = 0
    plat_hdr_r    = 1
    plat_data_r0  = 2
    plat_data_r1  = plat_data_r0 + len(platforms)       # exclusive

    rec_title_r   = plat_data_r1 + 1                    # after blank
    rec_hdr_r     = rec_title_r + 1
    rec_data_r0   = rec_hdr_r + 1
    rec_data_r1   = rec_data_r0 + len(recruiters)

    ref_title_r   = rec_data_r1 + 1
    ref_hdr_r     = ref_title_r + 1
    ref_data_r0   = ref_hdr_r + 1
    ref_data_r1   = ref_data_r0 + len(referrals)

    total_rows    = ref_data_r1 + 20  # headroom

    # Status column indices (0-based) within each section's header list
    plat_status_c = OUTREACH_PLATFORM_HEADERS.index("Status")
    rec_status_c  = OUTREACH_RECRUITER_HEADERS.index("Status")
    ref_status_c  = OUTREACH_REFERRAL_HEADERS.index("Status")

    try:
        ws = wb.worksheet("Outreach")
    except Exception:
        ws = wb.add_worksheet("Outreach", rows=max(300, total_rows + 10), cols=max_cols)

    ws.clear()
    ws.update(all_rows, "A1", value_input_option="USER_ENTERED")
    print(f"  ✓ Pushed {len(platforms)} platforms + {len(recruiters)} recruiters + "
          f"{len(referrals)} referrals to 'Outreach' sheet")

    # ── Sheets API formatting ─────────────────────────────────────────────────
    try:
        creds = wb.client.auth
        if not creds.valid:
            creds.refresh(GARequest())
        token          = creds.token
        spreadsheet_id = wb.id
        sheet_id       = ws.id

        def _batch(reqs):
            url     = (f"https://sheets.googleapis.com/v4/spreadsheets/"
                       f"{spreadsheet_id}:batchUpdate")
            payload = _json.dumps({"requests": reqs}).encode()
            req     = _ureq.Request(url, data=payload, method="POST")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Content-Type",  "application/json")
            with _ureq.urlopen(req, timeout=20) as resp:
                resp.read()

        def _cell_range(r0, r1, c0, c1):
            return {"sheetId": sheet_id,
                    "startRowIndex": r0, "endRowIndex": r1,
                    "startColumnIndex": c0, "endColumnIndex": c1}

        TEAL_BG   = {"red": 0.0,   "green": 0.455, "blue": 0.651}
        DARK_BG   = {"red": 0.216, "green": 0.278, "blue": 0.310}
        WHITE_TXT = {"red": 1.0,   "green": 1.0,   "blue": 1.0}
        BOLD_WHITE = {"bold": True, "foregroundColor": WHITE_TXT, "fontSize": 10}
        BOLD_WHITE_LG = {"bold": True, "foregroundColor": WHITE_TXT, "fontSize": 11}

        def _fmt_row(r, bg, txt_fmt):
            return {"repeatCell": {
                "range": _cell_range(r, r + 1, 0, max_cols),
                "cell": {"userEnteredFormat": {"backgroundColor": bg, "textFormat": txt_fmt}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }}

        def _validation(r0, r1, col, values):
            return {"setDataValidation": {
                "range": _cell_range(r0, r1, col, col + 1),
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in values],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }}

        def _col_width(col, px):
            return {"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": col, "endIndex": col + 1},
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }}

        WHITE_BG   = {"red": 1.0, "green": 1.0, "blue": 1.0}
        BLACK_TXT  = {"red": 0.0, "green": 0.0, "blue": 0.0}

        formatting_requests = [
            # Reset ALL formatting first — ws.clear() clears values only, not Sheets API
            # formatting. Without this, header-style formatting from prior pushes persists
            # on rows whose positions shift when section sizes change between pushes.
            {"repeatCell": {
                "range": _cell_range(0, total_rows, 0, max_cols),
                "cell": {"userEnteredFormat": {
                    "backgroundColor": WHITE_BG,
                    "textFormat": {"bold": False, "fontSize": 10,
                                   "foregroundColor": BLACK_TXT},
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }},
            # Section titles — teal + large bold white
            _fmt_row(plat_title_r, TEAL_BG, BOLD_WHITE_LG),
            _fmt_row(rec_title_r,  TEAL_BG, BOLD_WHITE_LG),
            _fmt_row(ref_title_r,  TEAL_BG, BOLD_WHITE_LG),
            # Column headers — dark slate + bold white
            _fmt_row(plat_hdr_r, DARK_BG, BOLD_WHITE),
            _fmt_row(rec_hdr_r,  DARK_BG, BOLD_WHITE),
            _fmt_row(ref_hdr_r,  DARK_BG, BOLD_WHITE),
            # Column widths — Notes wide, others comfortable
            _col_width(0, 160),   # Col A — Name / Agency / Company
            _col_width(1, 220),   # Col B — Priority / Consultant / Role
            _col_width(2, 80),    # Col C — Markets / Market / Contact Name
            _col_width(3, 110),   # Col D — Status / Speciality / Contact Role
            _col_width(4, 100),   # Col E — Registered / Method / Location
            _col_width(5, 90),    # Col F — URL / Contacted / Relationship
            _col_width(6, 100),   # Col G — Notes / Status / Degree
            _col_width(7, 80),    # Col H — / Response / Channel
            _col_width(8,  110),  # Col I — / Email / Potential HM
            _col_width(9,  80),   # Col J — / LinkedIn / Is Relevant (NEW)
            _col_width(10, 120),  # Col K — / Notes / Status
            _col_width(11, 90),   # Col L — / / Reached Out
            _col_width(12, 90),   # Col M — / / Response
            _col_width(13, 350),  # Col N — / / Notes
            # Status dropdowns
            _validation(plat_data_r0, plat_data_r1, plat_status_c, _PLATFORM_STATUSES),
            _validation(rec_data_r0,  rec_data_r1,  rec_status_c,  _RECRUITER_STATUSES),
            _validation(ref_data_r0,  ref_data_r1,  ref_status_c,  _REFERRAL_STATUSES),
            # Is Relevant Yes/No dropdown (referral section, col 9)
            _validation(ref_data_r0, ref_data_r1, 9, ["Yes", "No"]),
        ]
        _batch(formatting_requests)
        print("  ✓ Outreach tab formatted (section titles, headers, dropdowns, column widths)")

    except Exception as fmt_err:
        print(f"  ⚠ Outreach formatting failed (non-critical): {fmt_err}")

# ── Column definitions ────────────────────────────────────────────────────────
HEADERS = [
    # ── Priority columns (always visible) ──────────────────────────────────────
    "id",                    # Col A — internal workflow ID (app_001 etc.)
    "reference",             # Col B — Company — Role (shareable with referral contacts)
    "location",              # Col C
    "posted_date",           # Col D
    "fit_score",             # Col E — populated after Stage 3
    "salary_stated",         # Col F
    "experience_req",        # Col G
    "status",                # Col H ← USER EDITABLE — set to "Approved" AFTER filling Col K
    "entry_type",            # Col I — Brand New / Reposted (read-only, set at scout time)
    "jd_url",                # Col J — hyperlink to LinkedIn/Adzuna JD
    "career_page_url",       # Col K ← USER EDITABLE — paste ATS URL here first (before Approved)
    "pros",                  # Col L — key strengths (auto-populated from scoring, read-only)
    "cons",                  # Col M — key concerns (auto-populated from scoring, read-only)
    "role_type",             # Col N — contract_remote|contract_hybrid|permanent_remote|permanent_hybrid ← USER EDITABLE
    "is_contract",           # Col O — fixed-term/contract flag ← USER EDITABLE
    "apply_action",          # Col P — COMPUTED (read-only): Apply Now / Waiting (Xd) / blank; updated on every push
    "visa_sponsorship_status",  # Col Q
    "actual_hiring_company", # Col R — real employer for agency posts
    "agency_name",           # Col S — LinkedIn poster (recruiter/agency)
    "company_sponsor_kb",    # Col T — Known sponsor / Not a known sponsor / Uncertain
    # ── Secondary columns ──────────────────────────────────────────────────────
    "job_id",                # Col U — LinkedIn/Adzuna job ID from scrape
    "company",               # Col V
    "role",                  # Col W
    "work_mode",             # Col X
    "applied_date",          # Col Y
    "ats_type",              # Col Z
    "tracking_url",          # Col AA — from application confirmation emails
    "source",                # Col AB — apify/adzuna/excel_import/manual_inject
    "match_exists",          # Col AC — was a matching entry found on last scout run?
    "matched_entry_id",      # Col AD — id of related entry (new_entry decisions only)
    "score_exists",          # Col AE — is fit_score populated?
    "latest_scoring_date",   # Col AF — ISO date of last Pass 2 score
    "adzuna_salary_stated",  # Col AG — raw Adzuna API salary (Adzuna-sourced jobs only)
    "market",                # Col AH — uk | nl | se | de | dk | ie
    "notes",                 # Col AI ← USER EDITABLE — free-text notes / referral contact
    "eor_viability",         # Col AJ — EOR suitability 1-10 (null for permanent non-remote)
    "apply_recommendation",  # Col AK — Apply / Maybe / Skip (Claude synthesis)
]

# Columns the user is allowed to edit — pulled back during pull
USER_EDITABLE = {"status", "career_page_url", "notes", "is_contract", "role_type"}

# Statuses that belong in the Archive tab, not the Applications tab
ARCHIVED_STATUSES = {"Rejected", "Auto-Rejected", "Withdrawn", "Stale", "Duplicate", "Stale-Referral"}

# Formatting layout version — bump to force formatting reapply on all sheets.
# Ranges are fixed so routine pushes skip formatting entirely (marker match).
_FMT_VERSION          = "fmt-v4"
_FMT_MAX_ROWS         = 300     # Applications tab: active rows ceiling (~66 today)
_FMT_ARCHIVE_MAX_ROWS = 20000   # Archive tab: 4.3k rows today, grows ~140/day

ARCHIVE_HEADERS = [
    # ── Priority columns ───────────────────────────────────────────────────────
    "id",                    # Col A
    "reference",             # Col B — Company — Role (NEW)
    "location",              # Col C
    "posted_date",           # Col D
    "fit_score",             # Col E
    "salary_stated",         # Col F
    "experience_req",        # Col G — (NEW)
    "status",                # Col H
    "entry_type",            # Col I — Brand New / Reposted (read-only)
    "rejection_stage",       # Col J
    "rejection_reason",      # Col K
    "jd_url",                # Col L
    "career_page_url",       # Col M
    "pros",                  # Col N — key strengths (auto-populated from scoring, read-only)
    "cons",                  # Col O — key concerns (auto-populated from scoring, read-only)
    "role_type",             # Col P — 4-value role_type enum (contract_remote etc.)
    "is_contract",           # Col Q — fixed-term/contract flag
    "apply_recommendation",  # Col R — Apply / Maybe / Skip
    "visa_sponsorship_status",  # Col S
    "actual_hiring_company", # Col T
    "agency_name",           # Col U
    "company_sponsor_kb",    # Col V — Known sponsor / Not a known sponsor / Uncertain
    # ── Secondary columns ──────────────────────────────────────────────────────
    "company",               # Col W
    "role",                  # Col X
    "source",                # Col Y
    "matched_entry_id",      # Col Z
    "adzuna_salary_stated",  # Col AA — raw Adzuna salary (Adzuna-sourced jobs only)
    "market",                # Col AB — uk | nl | se | de | dk | ie
    "notes",                 # Col AC ← USER EDITABLE — free-text notes / referral contact
    "eor_viability",         # Col AD — EOR suitability 1-10 (null for permanent non-remote)
]

def _salary_cell(app: dict) -> str:
    """Build Col F display value: stated salary, or compact estimate when absent."""
    stated     = app.get("salary_stated", "") or ""
    estimate   = app.get("salary_estimate", "") or ""
    confidence = app.get("salary_estimate_confidence", "") or ""
    if stated.startswith("Not stated (est."):
        return stated
    missing = not stated or stated == "Not stated"
    if not missing:
        return stated
    if estimate:
        market = app.get("market", "uk")
        if market in ("nl", "de", "ie"):
            compact = re.sub(r'€(\d+),000', lambda m: f'€{m.group(1)}k', estimate)
        elif market == "se":
            compact = re.sub(r'(SEK\s+)(\d+),000', lambda m: f'{m.group(1)}{m.group(2)}k', estimate)
        elif market == "dk":
            # DKK estimates are 6-digit ("DKK 700,000") — compact both thousand groups
            compact = re.sub(r'(DKK\s+)(\d+),000', lambda m: f'{m.group(1)}{m.group(2)}k', estimate)
        else:
            compact = re.sub(r'£(\d+),000', lambda m: f'£{m.group(1)}k', estimate)
        suffix  = f" (est. · {confidence})" if confidence else " (est.)"
        return compact + suffix
    return stated or ""


def _role_type(app: dict) -> str:
    """Return the stored 4-value role_type, falling back to work_mode derivation for legacy entries."""
    stored = (app.get("role_type") or "").strip()
    if stored in ("contract_remote", "contract_hybrid", "permanent_remote", "permanent_hybrid"):
        return stored
    # Fallback for entries without role_type (pre-backfill)
    return _compute_role_type(bool(app.get("is_contract")), app.get("work_mode") == "Remote")


_PRE_APPLIED_STATUSES = {
    "Prep Complete", "Connection-Requested", "Reached-Out",
    "Followup", "Referral-Planned",
}
_OUTREACH_ACTIVE_STATUSES = {"Reached-Out", "Followup"}  # referral request has been sent
APPLY_WAIT_DAYS = 3


def _compute_apply_action(app_id: str, status: str, referrals: list) -> str:
    """Compute the apply_action signal for the Applications tab Col AK.

    Returns: "Apply Now" | "Apply Now (Xd)" | "Waiting (Xd)" | "Waiting (pending)" | ""
    Updated on every push — never stored in job_tracker.json.
    """
    from datetime import date as _d
    if status not in _PRE_APPLIED_STATUSES:
        return ""

    relevant = [r for r in referrals
                if r.get("app_id") == app_id and r.get("is_relevant_contact") is True]

    if not relevant:
        return "Apply Now"  # no relevant contacts → apply immediately

    # Relevant contacts where the referral request has actually been sent
    active = [r for r in relevant if r.get("status") in _OUTREACH_ACTIVE_STATUSES
              and r.get("reached_out_date")]

    if not active:
        # Connection notes sent but not yet accepted
        return "Waiting (pending)"

    today = _d.today()
    min_date = min(_d.fromisoformat(r["reached_out_date"]) for r in active)
    days = (today - min_date).days
    if days >= APPLY_WAIT_DAYS:
        return f"Apply Now ({days}d)"
    return f"Waiting ({days}d)"


def app_to_row(app: dict, referrals=None) -> list:
    """Convert a job_tracker.json application entry to a sheet row."""
    company = app.get("company", "")
    role    = app.get("role", "")
    ref     = f"{company} — {role}"
    jd  = app.get("jd_url", "") or ""
    cp  = app.get("career_page_url", "") or ""
    # Embed HYPERLINK formulas so batch update (USER_ENTERED) renders them clickable
    # — eliminates the need for per-cell update_cell() calls that hit write quotas.
    jd_cell = f'=HYPERLINK("{jd}","View JD")' if (jd and jd.startswith("http")) else (jd or "")
    cp_cell = f'=HYPERLINK("{cp}","Apply")'   if (cp and cp.startswith("http")) else (cp or "")
    return [
        # ── Priority columns ─────────────────────────────────────────────────
        app.get("id", ""),                          # 0  id
        ref,                                         # 1  reference
        app.get("location", ""),                     # 2  location
        app.get("posted_date", ""),                  # 3  posted_date
        app.get("fit_score", ""),                    # 4  fit_score
        _salary_cell(app),                           # 5  salary_stated
        app.get("experience_req", "") or "",         # 6  experience_req
        app.get("status", ""),                       # 7  status
        app.get("entry_type", "") or "",             # 8  entry_type
        jd_cell,                                     # 9  jd_url
        cp_cell,                                     # 10 career_page_url
        app.get("pros", "") or "",                   # 11 pros
        app.get("cons", "") or "",                   # 12 cons
        _role_type(app),                             # 13 role_type (computed)
        str(app.get("is_contract") or ""),           # 14 is_contract
        _compute_apply_action(app.get("id", ""), app.get("status", ""), referrals or []),  # 15 apply_action
        app.get("visa_sponsorship_status", ""),      # 16 visa_sponsorship_status
        app.get("actual_hiring_company") or "",      # 17 actual_hiring_company
        app.get("agency_name") or "",                # 18 agency_name
        app.get("company_sponsor_kb", "") or "",     # 19 company_sponsor_kb
        # ── Secondary columns ─────────────────────────────────────────────────
        app.get("job_id", ""),                       # 20 job_id
        app.get("company", ""),                      # 21 company
        app.get("role", ""),                         # 22 role
        app.get("work_mode", ""),                    # 23 work_mode
        app.get("applied_date", "") or "",           # 24 applied_date
        app.get("ats_type", "") or "",               # 25 ats_type
        (f'=HYPERLINK("{app["tracking_url"]}","Track")'
         if app.get("tracking_url", "") and str(app.get("tracking_url","")).startswith("http")
         else ""),                                    # 26 tracking_url
        app.get("source", "") or "",                 # 27 source
        str(app.get("match_exists", "")) if app.get("match_exists") is not None else "",  # 28 match_exists
        app.get("matched_entry_id", "") or "",       # 29 matched_entry_id
        str(app.get("score_exists", "")) if app.get("score_exists") is not None else "",  # 30 score_exists
        app.get("latest_scoring_date", "") or "",    # 31 latest_scoring_date
        app.get("adzuna_salary_stated", "") or "",   # 32 adzuna_salary_stated
        app.get("market", "uk") or "uk",             # 33 market
        app.get("notes", "") or "",                  # 34 notes
        app.get("eor_viability") if app.get("eor_viability") is not None else "",  # 35 eor_viability
        app.get("apply_recommendation", "") or "",   # 36 apply_recommendation
    ]

# ─────────────────────────────────────────────────────────────────────────────
# PUSH helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_sheet_statuses(wb) -> dict:
    """Return {id: status} from the Applications tab (fast single read).
    Used by push() to detect entries the user manually archived in the Sheet
    before running pull — so we don't overwrite their edits.
    """
    out = {}
    try:
        ws = wb.worksheet("Applications")
        rows = ws.get_all_values()
        id_col     = 0
        status_col = HEADERS.index("status")  # 7
        for row in rows[1:]:
            if row and len(row) > status_col and row[id_col]:
                out[row[id_col]] = row[status_col]
    except Exception:
        pass
    return out


def _compute_rejection_stage(entry: dict, is_auto_rej_file: bool = False) -> str:
    """Classify why/how an entry ended up in the Archive tab."""
    if is_auto_rej_file or entry.get("status") == "Auto-Rejected":
        return "auto_rejected"
    status = entry.get("status", "")
    if status == "Withdrawn":
        return "withdrawn"
    if status == "Stale":
        return "stale"
    if status == "Stale-Referral":
        return "stale_referral"
    if status == "Duplicate":
        return "duplicate"
    return "post_application"  # Rejected after human review at any pipeline stage


def _archive_row_from_tracker(app: dict) -> list:
    # Check direct field first (set by write_tracker for Auto-Rejected entries)
    rejection_reason = app.get("rejection_reason", "")
    if not rejection_reason:
        for h in reversed(app.get("status_history", [])):
            reason = h.get("note") or h.get("reason")
            if reason:
                rejection_reason = reason
                break
    jd = app.get("jd_url") or ""
    jd_cell = f'=HYPERLINK("{jd}","View JD")' if jd.startswith("http") else jd
    cp = app.get("career_page_url") or ""
    cp_cell = f'=HYPERLINK("{cp}","Apply")' if cp.startswith("http") else cp
    return [
        # ── Priority columns ─────────────────────────────────────────────────
        app.get("id", ""),                                              # 0  id
        f"{app.get('company', '')} — {app.get('role', '')}",           # 1  reference (NEW)
        app.get("location", ""),                                        # 2  location
        app.get("posted_date", ""),                                     # 3  posted_date
        app.get("fit_score", ""),                                       # 4  fit_score
        _salary_cell(app),                                              # 5  salary_stated
        app.get("experience_req", "") or "",                            # 6  experience_req (NEW)
        app.get("status", ""),                                          # 7  status
        app.get("entry_type", "") or "",                                # 8  entry_type
        _compute_rejection_stage(app),                                  # 9  rejection_stage
        rejection_reason,                                               # 10 rejection_reason
        jd_cell,                                                        # 11 jd_url
        cp_cell,                                                        # 12 career_page_url
        app.get("pros", "") or "",                                      # 13 pros
        app.get("cons", "") or "",                                      # 14 cons
        _role_type(app),                                                # 15 role_type (computed)
        str(app.get("is_contract") or ""),                              # 16 is_contract
        app.get("apply_recommendation", "") or "",                      # 17 apply_recommendation
        app.get("visa_sponsorship_status", ""),                         # 18 visa_sponsorship_status
        app.get("actual_hiring_company", "") or "",                     # 19 actual_hiring_company
        app.get("agency_name", "") or "",                               # 20 agency_name
        app.get("company_sponsor_kb", "") or "",                        # 21 company_sponsor_kb
        # ── Secondary columns ─────────────────────────────────────────────────
        app.get("company", ""),                                         # 22 company
        app.get("role", ""),                                            # 23 role
        app.get("source", ""),                                          # 24 source
        app.get("matched_entry_id", "") or "",                          # 25 matched_entry_id
        app.get("adzuna_salary_stated", "") or "",                      # 26 adzuna_salary_stated
        app.get("market", "uk") or "uk",                               # 27 market
        app.get("notes", "") or "",                                     # 28 notes
        app.get("eor_viability") if app.get("eor_viability") is not None else "",  # 29 eor_viability
    ]


def _archive_row_from_auto_rejected(e: dict) -> list:
    jd = e.get("jd_url") or ""
    jd_cell = f'=HYPERLINK("{jd}","View JD")' if jd.startswith("http") else jd
    return [
        # ── Priority columns ─────────────────────────────────────────────────
        e.get("id", ""),                                                # 0  id
        f"{e.get('company', '')} — {e.get('role', '')}",               # 1  reference (NEW)
        e.get("location", ""),                                          # 2  location
        e.get("posted_date", ""),                                       # 3  posted_date
        e.get("fit_score", ""),                                         # 4  fit_score
        e.get("salary_stated", ""),                                     # 5  salary_stated
        "",                                                             # 6  experience_req (NEW — not tracked)
        "Auto-Rejected",                                                # 7  status
        "",                                                             # 8  entry_type (not tracked for auto-rejected)
        "auto_rejected",                                                # 9  rejection_stage
        e.get("rejection_reason", ""),                                  # 10 rejection_reason
        jd_cell,                                                        # 11 jd_url
        "",                                                             # 12 career_page_url (never set)
        "",                                                             # 13 pros (not tracked for auto-rejected)
        "",                                                             # 14 cons (not tracked for auto-rejected)
        e.get("role_type") or "",                                       # 15 role_type
        str(e.get("is_contract") or ""),                               # 16 is_contract
        e.get("apply_recommendation", "") or "Skip",                    # 17 apply_recommendation
        "",                                                             # 18 visa_sponsorship_status (not tracked)
        "",                                                             # 19 actual_hiring_company (not tracked)
        "",                                                             # 20 agency_name (not tracked)
        e.get("company_sponsor_kb", "") or "",                          # 21 company_sponsor_kb
        # ── Secondary columns ─────────────────────────────────────────────────
        e.get("company", ""),                                           # 22 company
        e.get("role", ""),                                              # 23 role
        "",                                                             # 24 source (pass1/pass2 = scoring pass, not scraper)
        "",                                                             # 25 matched_entry_id (not tracked)
        "",                                                             # 26 adzuna_salary_stated (not tracked)
        e.get("market", "uk") or "uk",                                 # 27 market
        e.get("visa_hint", ""),                                         # 28 notes (visa_hint as note)
        e.get("eor_viability") if e.get("eor_viability") is not None else "",  # 29 eor_viability
    ]


# ─────────────────────────────────────────────────────────────────────────────
# PUSH helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_archive_row_count(wb) -> int:
    """Return number of data rows currently in the Archive tab (header excluded).
    Returns 0 if the tab doesn't exist yet (first push is always safe)."""
    try:
        ws = wb.worksheet("Archive")
        # row_count is the grid capacity; count actual non-empty rows instead
        vals = ws.col_values(1)          # column A (id)
        data_rows = sum(1 for v in vals[1:] if v)   # skip header
        return data_rows
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# PUSH: job_tracker.json → Google Sheets
# ─────────────────────────────────────────────────────────────────────────────
def push(tabs=None):
    """Push local JSON → Google Sheets.

    tabs: set of tab names to write, e.g. {"apps", "archive", "outreach"}.
          None (default) = all tabs.  Valid values: "apps", "archive", "outreach".
    """
    _all = tabs is None
    do_apps     = _all or "apps"     in tabs
    do_archive  = _all or "archive"  in tabs
    do_outreach = _all or "outreach" in tabs
    _tab_label  = "all tabs" if _all else ",".join(sorted(tabs))
    print(f"\n[sheets_sync] PUSH: job_tracker.json → Google Sheets [{_tab_label}]")
    check_setup()

    tracker = json.loads(TRACKER.read_text())
    all_apps = sorted(
        tracker["applications"],
        key=lambda a: a.get("posted_date") or "",
        reverse=True,  # most-recently-posted at the top
    )
    print(f"  {len(all_apps)} applications to sync")

    wb = get_sheet()

    # ── Guard: respect status edits the user made in the Sheet before pulling ──
    # If the Sheet shows an archived status (Withdrawn/Rejected/Stale) for an
    # entry that the JSON still shows as active, treat it as archived so we
    # don't overwrite the user's edit.
    sheet_statuses = _read_sheet_statuses(wb)
    apps = []
    for a in all_apps:
        sheet_st = sheet_statuses.get(a.get("id", ""))
        if sheet_st in ARCHIVED_STATUSES and a.get("status") not in ARCHIVED_STATUSES:
            a = dict(a)  # shallow copy — don't mutate the tracker list
            a["status"] = sheet_st
        apps.append(a)

    # ── Split: active vs archived ─────────────────────────────────────────────
    active_apps   = [a for a in apps if a.get("status") not in ARCHIVED_STATUSES]
    archived_apps = [a for a in apps if a.get("status") in ARCHIVED_STATUSES]

    # ── Applications sheet (active entries only) ──────────────────────────────
    fmt_marker  = None
    skip_format = True
    rows        = []
    ws          = None

    if do_apps:
        try:
            ws = wb.worksheet("Applications")
        except Exception:
            ws = wb.add_worksheet("Applications", rows=500, cols=len(HEADERS))
            print("  Created 'Applications' worksheet")

        # Load outreach referrals once for apply_action computation (no-op if file absent)
        _outreach_path = ROOT / "data" / "outreach.json"
        _outreach_referrals = (
            json.loads(_outreach_path.read_text()).get("referrals", [])
            if _outreach_path.exists() else []
        )

        # Clear first so stale rows from a previous (larger) push can't survive.
        rows = [app_to_row(a, _outreach_referrals) for a in active_apps]
        ws.clear()
        ws.update([HEADERS] + rows, "A1", value_input_option="USER_ENTERED")

        print(f"  ✓ Pushed {len(rows)} active rows to 'Applications' sheet "
              f"({len(archived_apps)} archived → Archive tab)")

        # ── Add dropdowns and formatting ──────────────────────────────────────
        # Formatting/dropdowns are static (fixed row range 2–5000) — reapply only when
        # the layout marker changes (headers/worksheet recreated) or --reformat passed.
        # Saves ~5 Sheets API calls on every routine push.
        import hashlib as _hashlib
        fmt_marker  = _hashlib.md5(
            f"{_FMT_VERSION}|{','.join(HEADERS)}|{ws.id}".encode()).hexdigest()[:12]
        prev_marker = tracker.get("_meta", {}).get("sheet_format_marker")
        reformat    = "--reformat" in sys.argv
        skip_format = (fmt_marker == prev_marker) and not reformat

        if len(rows) > 0 and not skip_format:
            try:
                _apply_dropdowns(wb, ws, len(rows))
                print(f"  ✓ Dropdowns applied to status and career_page_url columns")
            except Exception as e:
                print(f"  ⚠ Dropdown setup failed (non-critical): {e}")

            try:
                _apply_formatting(wb, ws, len(rows))
                print(f"  ✓ Formatting applied (freeze, widths, colours, conditional)")
            except Exception as e:
                print(f"  ⚠ Formatting failed (non-critical): {e}")
        elif len(rows) > 0:
            print(f"  ✓ Formatting unchanged — skipped (pass --reformat to force)")
    else:
        print(f"  ↷ Applications tab skipped (--tabs={_tab_label})")

    # ── Shrink guard + Archive sheet ──────────────────────────────────────────
    auto_rej_entries = []
    new_archive_count = 0
    if AUTO_REJ_FILE.exists():
        ar_data = json.loads(AUTO_REJ_FILE.read_text())
        auto_rej_entries = ar_data.get("auto_rejected", [])
    new_archive_count = len(archived_apps) + len(auto_rej_entries)

    if do_archive:
        current_archive_count = _get_archive_row_count(wb)
        force = "--force" in sys.argv

        if not force and current_archive_count > 10 and new_archive_count < current_archive_count * 0.8:
            print(f"\n  ⚠ SHRINK GUARD: Archive would drop {current_archive_count} → {new_archive_count} rows")
            print(f"    Breakdown: {len(archived_apps)} from tracker + {len(auto_rej_entries)} from auto_rejected.json")
            print(f"    Re-run with --force to override, or investigate the discrepancy first.")
            sys.exit(1)

        try:
            _push_archive(wb, archived_apps, skip_format=skip_format)
        except Exception as e:
            print(f"  ⚠ Archive sheet failed (non-critical): {e}")
    else:
        print(f"  ↷ Archive tab skipped (--tabs={_tab_label})")

    # ── Outreach sheet (platforms + recruiters) ───────────────────────────────
    if do_outreach:
        try:
            _push_outreach(wb)
        except Exception as e:
            print(f"  ⚠ Outreach sheet failed (non-critical): {e}")
    else:
        print(f"  ↷ Outreach tab skipped (--tabs={_tab_label})")

    # ── Record push snapshot in _meta so `status` can detect unpushed changes ──
    if do_apps and fmt_marker:
        tracker["_meta"]["sheet_format_marker"] = fmt_marker
    if do_apps or do_archive:
        tracker["_meta"]["last_push_snapshot"] = {
            "timestamp":          datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "applications_count": len(active_apps) if do_apps else None,
            "archive_count":      new_archive_count if do_archive else None,
        }
        TRACKER.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))

    # Reorganise output folders to match current statuses (ready/ vs done/).
    if do_apps or do_archive:
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("organize_outputs", Path(__file__).parent / "organize_outputs.py")
            _mod  = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _mod.organize_outputs()
        except Exception as e:
            print(f"  ⚠ organize_outputs skipped: {e}")

    print(f"  Sheet URL: https://docs.google.com/spreadsheets/d/{SHEET_ID}")

    # Git commit + push (versioning + backup)
    from git_sync import commit_and_push as _git_push
    if do_apps or do_archive:
        _git_push("push", ["data/job_tracker.json"])
    if do_outreach:
        _git_push("push", ["data/outreach.json", "data/referral_outreach_log.json"])


def _apply_dropdowns(wb, ws, num_rows: int):
    """
    Apply data validation dropdowns to user-editable columns.
    Uses raw Sheets API batchUpdate — no extra dependencies needed.

    Dropdowns:
      Col H (status, index 7)       — valid pipeline statuses
      Col K (career_page_url, 10)   — hint values: EASY_APPLY or paste URL
        (can't enforce URL format via dropdown, so we add a note dropdown
         that reminds you of the two valid entry types)
    """
    STATUS_COL    = HEADERS.index("status")           # Col H (0-indexed = 7)
    CAREER_COL    = HEADERS.index("career_page_url")  # Col K (0-indexed = 10)

    STATUS_VALUES = [
        "Shortlisted", "Review Needed", "Approved", "Prep Complete",
        "Referral-Planned", "Connection-Requested", "Reached-Out", "Followup", "Referred",
        "Applied", "Referral", "Under Review", "Interview Scheduled", "Assessment",
        "Offer Received", "Rejected", "Withdrawn", "Duplicate", "Stale-Referral",
    ]

    CAREER_HINTS = [
        "EASY_APPLY",
        "Paste ATS URL here",
    ]

    spreadsheet_id = wb.id
    creds          = wb.client.auth

    # Build Sheets API request using gspread's underlying service
    # gspread exposes the raw service via client.auth._default_http
    # We use requests directly with the service account token
    import json as _json
    from google.auth.transport.requests import Request as GARequest

    # Refresh credentials if needed
    if not creds.valid:
        creds.refresh(GARequest())

    token = creds.token

    def col_range(col_0idx):
        """Build GridRange dict for a full column (fixed range — row count independent)."""
        return {
            "sheetId":          ws.id,
            "startRowIndex":    1,               # row 2 (0-indexed)
            "endRowIndex":      _FMT_MAX_ROWS,
            "startColumnIndex": col_0idx,
            "endColumnIndex":   col_0idx + 1,
        }

    def dropdown_rule(values, col_0idx, strict=True):
        return {
            "setDataValidation": {
                "range": col_range(col_0idx),
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in values],
                    },
                    "showCustomUi":  True,
                    "strict":        strict,
                }
            }
        }

    requests = [
        dropdown_rule(STATUS_VALUES, STATUS_COL, strict=True),
        # career_page_url: show hint dropdown but not strict
        # (user needs to paste a real URL too, so we can't enforce a fixed list)
        dropdown_rule(CAREER_HINTS, CAREER_COL, strict=False),
    ]

    import urllib.request as _ureq
    url     = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate"
    payload = _json.dumps({"requests": requests}).encode()
    req     = _ureq.Request(url, data=payload, method="POST")
    req.add_header("Authorization",  f"Bearer {token}")
    req.add_header("Content-Type",   "application/json")

    with _ureq.urlopen(req, timeout=20) as resp:
        resp.read()   # consume response


def _apply_formatting(wb, ws, num_rows: int):
    """
    Apply visual formatting to the Applications sheet:
      - Freeze header row
      - Column widths
      - Bold dark header
      - Amber highlight on user-editable columns (status, career_page_url, notes)
      - Conditional formatting on status column (one colour per status value)
    Safe to call on every push — conditional rules are cleared and re-added.
    """
    import urllib.request as _ureq, json as _json
    from google.auth.transport.requests import Request as GARequest

    creds = wb.client.auth
    if not creds.valid:
        creds.refresh(GARequest())
    token          = creds.token
    spreadsheet_id = wb.id
    sheet_id       = ws.id

    STATUS_COL  = HEADERS.index("status")           # Col H (0-indexed = 7)
    CAREER_COL  = HEADERS.index("career_page_url")  # Col K (0-indexed = 10)
    NOTES_COL   = HEADERS.index("notes")            # Col AH (0-indexed = 33)

    # Colour map: status value → (bg_r, bg_g, bg_b, fg_r, fg_g, fg_b)
    STATUS_COLORS = {
        "Shortlisted":         (1.000, 0.949, 0.800, 0, 0, 0),
        "Review Needed":       (0.988, 0.898, 0.804, 0, 0, 0),
        "Stale":               (0.878, 0.878, 0.878, 0.4, 0.4, 0.4),
        "Approved":            (0.851, 0.918, 0.827, 0, 0, 0),
        "Prep Complete":       (0.714, 0.843, 0.659, 0, 0, 0),
        # ── Referral flow ──────────────────────────────────────────────────────
        "Referral-Planned":    (0.875, 0.929, 0.753, 0, 0, 0),   # yellow-green — planned, not yet sent
        "Connection-Requested":(0.984, 0.863, 0.569, 0, 0, 0),   # light amber — note sent, awaiting acceptance
        "Reached-Out":         (0.796, 0.918, 0.910, 0, 0, 0),   # teal-mint
        "Followup":            (0.996, 0.894, 0.686, 0, 0, 0),   # amber — needs attention
        "Referred":            (0.780, 0.902, 0.804, 0, 0, 0),   # light green (like Applied)
        "Stale-Referral":      (0.878, 0.878, 0.878, 0.4, 0.4, 0.4),  # grey (like Stale)
        # ──────────────────────────────────────────────────────────────────────
        "Applied":             (0.812, 0.886, 0.953, 0, 0, 0),
        "Referral":            (0.984, 0.871, 0.678, 0, 0, 0),
        "Under Review":        (0.788, 0.855, 0.973, 0, 0, 0),
        "Interview Scheduled": (0.851, 0.824, 0.914, 0, 0, 0),
        "Assessment":          (0.918, 0.820, 0.863, 0, 0, 0),
        "Offer Received":      (0.416, 0.659, 0.310, 1, 1, 1),
        "Rejected":            (0.957, 0.800, 0.800, 0, 0, 0),
        "Auto-Rejected":       (0.918, 0.600, 0.600, 0, 0, 0),
        "Withdrawn":           (0.937, 0.937, 0.937, 0.4, 0.4, 0.4),
        "Duplicate":           (0.906, 0.835, 0.953, 0.3, 0.3, 0.3),
    }

    def col_range(col_0idx, start_row=1, end_row=None):
        return {
            "sheetId":          sheet_id,
            "startRowIndex":    start_row,
            "endRowIndex":      end_row if end_row else _FMT_MAX_ROWS,
            "startColumnIndex": col_0idx,
            "endColumnIndex":   col_0idx + 1,
        }

    requests = []

    # 1. Freeze header row
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # 2. Column widths (pixels) — keyed by field name, resolved to index at runtime
    FIELD_WIDTHS = {
        "id": 90, "reference": 260, "location": 110, "posted_date": 100,
        "fit_score": 75, "salary_stated": 200, "experience_req": 120,
        "status": 140, "entry_type": 100, "jd_url": 55, "career_page_url": 55,
        "pros": 260, "cons": 260, "notes": 200,
        "role_type": 120, "is_contract": 80, "eor_viability": 90,
        "apply_recommendation": 90, "visa_sponsorship_status": 160,
        "actual_hiring_company": 180, "agency_name": 180, "company_sponsor_kb": 150,
        "job_id": 110, "company": 200, "role": 260, "work_mode": 100,
        "applied_date": 100, "ats_type": 120,
        "tracking_url": 55, "source": 90, "match_exists": 85,
        "matched_entry_id": 110, "score_exists": 80, "latest_scoring_date": 130,
        "adzuna_salary_stated": 180,
    }
    col_widths = {HEADERS.index(f): w for f, w in FIELD_WIDTHS.items() if f in HEADERS}
    for col_idx, px in col_widths.items():
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId":    sheet_id,
                    "dimension":  "COLUMNS",
                    "startIndex": col_idx,
                    "endIndex":   col_idx + 1,
                },
                "properties": {"pixelSize": px},
                "fields": "pixelSize",
            }
        })

    # 3. Header row: bold, dark background, white text, centred
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId":       sheet_id,
                "startRowIndex": 0,
                "endRowIndex":   1,
            },
            "cell": {
                "userEnteredFormat": {
                    "backgroundColor": {"red": 0.216, "green": 0.278, "blue": 0.310},
                    "textFormat": {
                        "bold": True,
                        "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                    },
                    "horizontalAlignment": "CENTER",
                }
            },
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
        }
    })

    # 4. Editable column highlights (light amber background for data rows)
    AMBER = {"red": 1.0, "green": 0.988, "blue": 0.878}
    for col_idx in (STATUS_COL, CAREER_COL, NOTES_COL):
        requests.append({
            "repeatCell": {
                "range": col_range(col_idx, start_row=1),
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": AMBER,
                    }
                },
                "fields": "userEnteredFormat.backgroundColor",
            }
        })

    # 4b. Clip pros/cons columns so row height stays fixed (full text visible on cell click)
    PROS_COL = HEADERS.index("pros")   # 0-indexed = 11
    CONS_COL = HEADERS.index("cons")   # 0-indexed = 12
    for col_idx in (PROS_COL, CONS_COL):
        requests.append({
            "repeatCell": {
                "range": col_range(col_idx, start_row=1),
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "CLIP",
                    }
                },
                "fields": "userEnteredFormat.wrapStrategy",
            }
        })

    # 5. Delete existing conditional format rules for this sheet, then re-add
    #    (avoids rule accumulation on repeated pushes)
    requests.append({
        "deleteConditionalFormatRule": {
            "sheetId": sheet_id,
            "index":   0,
        }
    })

    # 6. Add conditional formatting for each status value
    status_range = {
        "sheetId":          sheet_id,
        "startRowIndex":    1,
        "endRowIndex":      _FMT_MAX_ROWS,
        "startColumnIndex": STATUS_COL,
        "endColumnIndex":   STATUS_COL + 1,
    }
    for i, (status_val, (br, bg, bb, fr, fg, fb)) in enumerate(STATUS_COLORS.items()):
        requests.append({
            "addConditionalFormatRule": {
                "rule": {
                    "ranges": [status_range],
                    "booleanRule": {
                        "condition": {
                            "type":   "TEXT_EQ",
                            "values": [{"userEnteredValue": status_val}],
                        },
                        "format": {
                            "backgroundColor": {"red": br, "green": bg, "blue": bb},
                            "textFormat": {
                                "foregroundColor": {"red": fr, "green": fg, "blue": fb}
                            },
                        },
                    },
                },
                "index": i,
            }
        })

    # Send batchUpdate — split into two calls:
    #   First: all formatting except the deleteConditionalFormatRule
    #          (which fails if no rules exist yet on first push)
    #   Then:  conditional rules

    def _batch(reqs):
        url     = (f"https://sheets.googleapis.com/v4/spreadsheets/"
                   f"{spreadsheet_id}:batchUpdate")
        payload = _json.dumps({"requests": reqs}).encode()
        req     = _ureq.Request(url, data=payload, method="POST")
        req.add_header("Authorization",  f"Bearer {token}")
        req.add_header("Content-Type",   "application/json")
        with _ureq.urlopen(req, timeout=20) as resp:
            resp.read()

    # Non-conditional requests (freeze, widths, header, editable cols)
    non_cond = [r for r in requests if "deleteConditionalFormatRule" not in r
                                    and "addConditionalFormatRule" not in r]
    _batch(non_cond)

    # Try to delete existing rules (silently ignore if none exist)
    try:
        _batch([{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}])
    except Exception:
        pass

    # Add conditional rules
    cond_rules = [r for r in requests if "addConditionalFormatRule" in r]
    if cond_rules:
        _batch(cond_rules)


def _push_archive(wb, archived_from_tracker: list, skip_format: bool = False):
    """Push all archived entries (Rejected/Auto-Rejected/Withdrawn/Stale from
    job_tracker.json plus auto_rejected.json) into a single 'Archive' sheet tab.
    Also deletes the legacy 'Auto-Rejected' tab if it exists.
    skip_format=True skips the static formatting requests (marker unchanged).
    """
    import urllib.request as _ureq, json as _json
    from google.auth.transport.requests import Request as GARequest

    # ── Combine sources ───────────────────────────────────────────────────────
    tracker_rows = [_archive_row_from_tracker(a) for a in archived_from_tracker]

    # Build set of jd_urls already covered by tracker Auto-Rejected entries
    # so we don't duplicate them from auto_rejected.json
    tracker_auto_rej_urls = {
        a.get("jd_url") for a in archived_from_tracker
        if a.get("status") == "Auto-Rejected" and a.get("jd_url")
    }

    auto_rej_rows = []
    if AUTO_REJ_FILE.exists():
        ar_data = json.loads(AUTO_REJ_FILE.read_text())
        auto_rej_rows = [
            _archive_row_from_auto_rejected(e)
            for e in reversed(ar_data.get("auto_rejected", []))  # newest first
            if (e.get("jd_url") or "") not in tracker_auto_rej_urls
        ]

    all_rows = tracker_rows + auto_rej_rows
    if not all_rows:
        print("  [archive] No archived entries to push")
        return

    # ── Get or create Archive worksheet ──────────────────────────────────────
    try:
        ws = wb.worksheet("Archive")
    except Exception:
        ws = wb.add_worksheet("Archive", rows=2000, cols=len(ARCHIVE_HEADERS))
        print("  Created 'Archive' worksheet")

    ws.clear()
    ws.update([ARCHIVE_HEADERS] + all_rows, "A1", value_input_option="USER_ENTERED")

    # ── Delete legacy 'Auto-Rejected' tab if it exists ────────────────────────
    try:
        old_ws = wb.worksheet("Auto-Rejected")
        wb.del_worksheet(old_ws)
        print("  Deleted legacy 'Auto-Rejected' worksheet")
    except Exception:
        pass

    print(f"  ✓ Pushed {len(all_rows)} rows to 'Archive' sheet "
          f"({len(tracker_rows)} from tracker, {len(auto_rej_rows)} from auto_rejected.json)")

    if skip_format:
        return

    # ── Formatting: freeze header + dark header + status colour coding ────────
    creds = wb.client.auth
    if not creds.valid:
        creds.refresh(GARequest())
    token          = creds.token
    spreadsheet_id = wb.id
    sheet_id       = ws.id

    STATUS_COL_IDX    = ARCHIVE_HEADERS.index("status")          # 7
    REJ_STAGE_COL_IDX = ARCHIVE_HEADERS.index("rejection_stage") # 9

    ARCHIVE_STATUS_COLORS = {
        "Rejected":        (0.957, 0.800, 0.800, 0, 0, 0),
        "Auto-Rejected":   (0.918, 0.600, 0.600, 0, 0, 0),
        "Withdrawn":       (0.937, 0.937, 0.937, 0.4, 0.4, 0.4),
        "Stale":           (0.878, 0.878, 0.878, 0.4, 0.4, 0.4),
        "Stale-Referral":  (0.878, 0.878, 0.878, 0.4, 0.4, 0.4),
        "Duplicate":       (0.906, 0.835, 0.953, 0.3, 0.3, 0.3),
    }
    STAGE_COLORS = {
        "post_application": (0.988, 0.878, 0.878, 0, 0, 0),
        "auto_rejected":    (0.976, 0.796, 0.796, 0, 0, 0),
        "withdrawn":        (0.937, 0.937, 0.937, 0.4, 0.4, 0.4),
        "stale":            (0.878, 0.878, 0.878, 0.4, 0.4, 0.4),
        "stale_referral":   (0.878, 0.878, 0.878, 0.4, 0.4, 0.4),
        "duplicate":        (0.906, 0.835, 0.953, 0.3, 0.3, 0.3),
    }

    def _batch(reqs):
        url     = (f"https://sheets.googleapis.com/v4/spreadsheets/"
                   f"{spreadsheet_id}:batchUpdate")
        payload = _json.dumps({"requests": reqs}).encode()
        req     = _ureq.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type",  "application/json")
        with _ureq.urlopen(req, timeout=20) as resp:
            resp.read()

    base_requests = [
        # Freeze header
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # Dark header
        {
            "repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": {"red": 0.216, "green": 0.278, "blue": 0.310},
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                        },
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
    ]
    _batch(base_requests)

    # Conditional formatting — clear existing first, then add
    try:
        _batch([{"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}}])
    except Exception:
        pass

    cond_rules = []
    for col_idx, color_map in (
        (STATUS_COL_IDX, ARCHIVE_STATUS_COLORS),
        (REJ_STAGE_COL_IDX, STAGE_COLORS),
    ):
        col_range = {
            "sheetId": sheet_id,
            "startRowIndex": 1, "endRowIndex": _FMT_ARCHIVE_MAX_ROWS,
            "startColumnIndex": col_idx, "endColumnIndex": col_idx + 1,
        }
        for i, (val, (br, bg, bb, fr, fg, fb)) in enumerate(color_map.items()):
            cond_rules.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [col_range],
                        "booleanRule": {
                            "condition": {
                                "type":   "TEXT_EQ",
                                "values": [{"userEnteredValue": val}],
                            },
                            "format": {
                                "backgroundColor": {"red": br, "green": bg, "blue": bb},
                                "textFormat": {
                                    "foregroundColor": {"red": fr, "green": fg, "blue": fb}
                                },
                            },
                        },
                    },
                    "index": i,
                }
            })
    if cond_rules:
        _batch(cond_rules)


# ─────────────────────────────────────────────────────────────────────────────
# PULL: Google Sheets → job_tracker.json (user-editable columns only)
# ─────────────────────────────────────────────────────────────────────────────
# ── Status transition sanity check (warn-only — the user is authoritative) ────
# Rank order of the normal pipeline; terminal statuses allowed from anywhere.
_STATUS_RANK = {
    "Stale": -1,
    "Shortlisted": 0, "Review Needed": 0,
    "Approved": 1, "Prep Complete": 2,
    "Referral-Planned": 3, "Connection-Requested": 4, "Reached-Out": 5, "Followup": 6,
    "Referred": 7, "Applied": 7, "Referral": 7,
    "Under Review": 8, "Interview Scheduled": 9, "Assessment": 9,
    "Offer Received": 10,
}
_TERMINAL = {"Rejected", "Withdrawn", "Duplicate", "Stale-Referral"}

def _local_changed_in_session(app: dict) -> bool:
    """Return True if local status was changed by a non-pull source AFTER the
    most recent pull-sourced change — meaning the current session touched this
    entry and local should take priority over the Sheet.

    Compares timestamps/dates in status_history. ISO datetime strings
    ("2026-07-18T14:00:00Z") and date-only strings ("2026-07-18") are
    comparable as strings because shorter date strings sort earlier than
    their datetime equivalents on the same day.
    """
    history = app.get("status_history", [])
    last_pull_ts = None
    last_session_ts = None
    for entry in history:
        ts = entry.get("timestamp") or entry.get("date") or ""
        if not ts:
            continue
        if entry.get("source") == "sheets_sync_pull":
            if last_pull_ts is None or ts > last_pull_ts:
                last_pull_ts = ts
        else:
            if last_session_ts is None or ts > last_session_ts:
                last_session_ts = ts
    if last_session_ts is None:
        return False  # only pull-sourced history — Sheet wins
    if last_pull_ts is None:
        return True   # never been pulled — local wins
    return last_session_ts > last_pull_ts


def _warn_status_transition(app: dict, old: str, new: str, career_url: str):
    """Print a warning for suspicious status jumps found during pull.
    Never blocks — Sheet edits are always applied (user is authoritative)."""
    ref = f"{app.get('company','?')} / {app.get('role','?')}"
    if old in _TERMINAL:
        print(f"  ⚠ TERMINAL OVERRIDE: {ref} — '{old}' → '{new}'. "
              f"'{old}' is terminal; automation never sets this. Applying because it "
              f"was edited manually in the Sheet — verify it was intentional.")
        return
    if new in _TERMINAL:
        return  # any → terminal is always legitimate
    old_rank = _STATUS_RANK.get(old)
    new_rank = _STATUS_RANK.get(new)
    if old_rank is None or new_rank is None:
        return
    if old_rank < 3 and new_rank >= 4:
        print(f"  ⚠ SKIPPED 'Applied': {ref} — '{old}' → '{new}' jumps past Applied. "
              f"Applying, but check the applied_date is recorded.")
    elif new_rank < old_rank:
        print(f"  ⚠ BACKWARDS MOVE: {ref} — '{old}' → '{new}' moves the pipeline "
              f"backwards. Applying — verify this was intentional.")
    if new == "Approved" and not career_url:
        print(f"  ⚠ APPROVED WITHOUT URL: {ref} — career_page_url is empty; "
              f"application_prep will skip this entry until it is filled (CLAUDE.md edit order).")


def pull(tabs=None):
    """Pull Google Sheets → local JSON.

    tabs: set of tab names to read, e.g. {"apps", "archive"}.
          None (default) = all tabs.  Valid values: "apps", "archive", "outreach".
    """
    _all = tabs is None
    do_apps     = _all or "apps"     in tabs
    do_archive  = _all or "archive"  in tabs
    do_outreach = _all or "outreach" in tabs
    _tab_label  = "all tabs" if _all else ",".join(sorted(tabs))

    print(f"\n[sheets_sync] PULL: Google Sheets → job_tracker.json [{_tab_label}]")
    check_setup()

    tracker = json.loads(TRACKER.read_text())
    apps    = {a["id"]: a for a in tracker["applications"]}
    updated = 0

    wb = get_sheet()

    # ── Applications tab ──────────────────────────────────────────────────────
    if do_apps:
        print("  Reading user-editable columns: status, career_page_url, notes")
        try:
            ws = wb.worksheet("Applications")
        except Exception:
            print("  ✗ 'Applications' worksheet not found — run push first")
            sys.exit(1)

        rows = ws.get_all_records(value_render_option='FORMULA')   # FORMULA mode so =HYPERLINK(...) is returned as text, not display value

        for row in rows:
            app_id = str(row.get("id", "")).strip()
            if not app_id or app_id not in apps:
                continue

            app     = apps[app_id]
            changed = []

            for col in USER_EDITABLE:
                sheet_val = str(row.get(col, "") or "").strip()
                local_val = str(app.get(col, "") or "").strip()

                # Skip HYPERLINK formula values — extract raw URL
                if sheet_val.startswith("=HYPERLINK"):
                    import re
                    m = re.search(r'HYPERLINK\("([^"]+)"', sheet_val)
                    sheet_val = m.group(1) if m else ""

                if sheet_val and sheet_val != local_val:
                    # role_type: validate against enum; reject and recompute if invalid
                    if col == "role_type":
                        _VALID_RT = ("contract_remote", "contract_hybrid",
                                     "permanent_remote", "permanent_hybrid")
                        if sheet_val not in _VALID_RT:
                            _recomputed = _compute_role_type(
                                bool(app.get("is_contract")), bool(app.get("is_remote_only"))
                            )
                            if _recomputed != local_val:
                                app["role_type"] = _recomputed
                                changed.append(f"role_type: invalid Sheet value '{sheet_val}' → recomputed '{_recomputed}'")
                            continue  # skip generic assignment below
                    # is_contract: coerce string representation back to bool
                    if col == "is_contract":
                        sheet_val = sheet_val.lower() in ("true", "1", "yes")
                        local_val_bool = bool(app.get("is_contract"))
                        if sheet_val == local_val_bool:
                            continue  # no actual change after coercion
                        app[col] = sheet_val
                        changed.append(f"is_contract: '{local_val_bool}' → '{sheet_val}'")
                        continue
                    # Status change — check for blocked backwards moves, then record
                    if col == "status":
                        old_rank = _STATUS_RANK.get(local_val)
                        new_rank = _STATUS_RANK.get(sheet_val)
                        if (old_rank is not None and new_rank is not None
                                and new_rank < old_rank
                                and local_val not in _TERMINAL
                                and sheet_val not in _TERMINAL):
                            print(f"  ⚠ STALE SHEET SKIPPED: {app.get('company')} / {app.get('role')} — "
                                  f"Sheet shows '{sheet_val}' (rank {new_rank}) but tracker is already at "
                                  f"'{local_val}' (rank {old_rank}). Run push first to sync the Sheet.")
                            continue
                        _warn_status_transition(app, local_val, sheet_val,
                                                str(row.get("career_page_url", "") or "").strip())
                        if "status_history" not in app:
                            app["status_history"] = []
                        app["status_history"].append({
                            "status": sheet_val,
                            "date":   datetime.now().strftime("%Y-%m-%d"),
                            "source": "sheets_sync_pull",
                        })
                    app[col] = sheet_val
                    changed.append(f"{col}: '{local_val}' → '{sheet_val}'")

            # Recompute role_type when is_contract changed and role_type was NOT explicitly edited
            _ic_changed = any(c.startswith("is_contract:") for c in changed)
            _rt_changed  = any(c.startswith("role_type:") for c in changed)
            if _ic_changed and not _rt_changed:
                _new_rt = _compute_role_type(
                    bool(app.get("is_contract")), bool(app.get("is_remote_only"))
                )
                if _new_rt != app.get("role_type"):
                    changed.append(f"role_type: recomputed → '{_new_rt}' (is_contract changed)")
                    app["role_type"] = _new_rt

            if changed:
                updated += 1
                print(f"  ✓ {app.get('company')} / {app.get('role')}")
                for c in changed: print(f"      {c}")
    else:
        print(f"  ↷ Applications tab skipped (--tabs={_tab_label})")

    # ── Archive tab: detect re-activations (user changed Stale → Shortlisted etc.) ──
    if do_archive:
        try:
            ws_archive = wb.worksheet("Archive")
            archive_rows = ws_archive.get_all_records(value_render_option="FORMULA")
            for row in archive_rows:
                app_id = str(row.get("id", "")).strip()
                if not app_id or app_id not in apps:
                    continue  # auto_rejected.json entries or unknown IDs — skip
                sheet_status = str(row.get("status", "") or "").strip()
                if not sheet_status or sheet_status in ARCHIVED_STATUSES:
                    continue  # still archived — no action
                # Status was manually changed to an active value — re-activate
                app = apps[app_id]
                old_status = app.get("status", "")
                app["status"] = sheet_status
                app.setdefault("status_history", []).append({
                    "status": sheet_status,
                    "date":   datetime.now().strftime("%Y-%m-%d"),
                    "source": "sheets_sync_pull_archive_reactivation",
                    "reason": f"Manually re-activated from Archive (was {old_status})",
                })
                # Also restore career_page_url if the user filled it in Archive
                sheet_url = str(row.get("career_page_url", "") or "").strip()
                if sheet_url.startswith("=HYPERLINK"):
                    m = re.search(r'HYPERLINK\("([^"]+)"', sheet_url)
                    sheet_url = m.group(1) if m else ""
                if sheet_url:
                    app["career_page_url"] = sheet_url
                updated += 1
                print(f"  ✓ RE-ACTIVATED {app.get('company')} / {app.get('role')}")
                print(f"      status: '{old_status}' → '{sheet_status}' (from Archive tab)")
        except Exception as e:
            print(f"  [archive pull] Skipped Archive tab — {e}")
    else:
        print(f"  ↷ Archive tab skipped (--tabs={_tab_label})")

    # Write back tracker if apps or archive were read
    if do_apps or do_archive:
        tracker["applications"] = list(apps.values())
        TRACKER.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))

        # Reorganise output folders to match updated statuses (ready/ vs done/).
        try:
            import importlib.util as _ilu
            _spec = _ilu.spec_from_file_location("organize_outputs", Path(__file__).parent / "organize_outputs.py")
            _mod  = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            _mod.organize_outputs()
        except Exception as e:
            print(f"  ⚠ organize_outputs skipped: {e}")

        print(f"\n  {updated} applications updated in job_tracker.json")
        if updated == 0:
            print("  (No changes detected in user-editable columns)")

    # ── Outreach tab ──────────────────────────────────────────────────────────
    if do_outreach:
        print("\n[sheets_sync] PULL: Outreach tab → outreach.json")
        try:
            outreach_updated = _pull_outreach(wb)
            if outreach_updated == 0:
                print("  (No changes detected in Outreach tab)")
        except Exception as e:
            print(f"  ⚠ Outreach pull skipped — {e}")
    else:
        print(f"  ↷ Outreach tab skipped (--tabs={_tab_label})")

    # Git commit + push (versioning + backup)
    from git_sync import commit_and_push as _git_push
    if do_apps or do_archive:
        _git_push("pull", ["data/job_tracker.json"])
    if do_outreach:
        _git_push("pull", ["data/outreach.json"])


# ─────────────────────────────────────────────────────────────────────────────
# SETUP INSTRUCTIONS (printed when run without args)
# ─────────────────────────────────────────────────────────────────────────────
SETUP_GUIDE = """
sheets_sync.py — One-time Setup
═══════════════════════════════

Step 1 — Install dependencies (in your venv):
  pip install gspread google-auth

Step 2 — Create Google Cloud credentials:
  a. Go to https://console.cloud.google.com
  b. Select your existing 'job-automation' project
     (or create a new one)
  c. APIs & Services → Enable APIs:
       - Google Sheets API
       - Google Drive API
  d. APIs & Services → Credentials →
     + Create Credentials → Service Account
       Name: job-automation-sheets
       Click Create, skip optional steps
  e. Click the service account email → Keys →
     Add Key → Create new key → JSON → Download
  f. Rename the downloaded file to:
       google_service_account.json
     Move it to your project's data/ folder

Step 3 — Create your Google Sheet:
  a. Go to https://sheets.google.com → New spreadsheet
  b. Name it: "Job Application Tracker"
  c. Share it with the service account email
     (found in google_service_account.json as "client_email")
     → Give it Editor access
  d. Copy the Sheet ID from the URL:
     https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
  e. Add to .env:
     GOOGLE_SHEET_ID=SHEET_ID_HERE

Step 4 — Test:
  python3 scripts/sheets_sync.py push
  (Then open your Sheet — you should see all applications)

Step 5 — Workflow:
  After every scrape+enrich:   python3 scripts/sheets_sync.py push
  Before approving jobs:       python3 scripts/sheets_sync.py pull
  After editing sheet:         python3 scripts/sheets_sync.py pull
"""

# ─────────────────────────────────────────────────────────────────────────────
# STATUS: compare local files vs live Sheet — read-only health check
# ─────────────────────────────────────────────────────────────────────────────
def status():
    """Read-only sync health check.
    Compares what the Sheet *should* contain (from local files) vs what it
    actually contains (live Sheet read). Shows a clear ✓ / ⚠ verdict.
    """
    print("\n[sheets_sync] STATUS")
    check_setup()

    # ── Local file counts ─────────────────────────────────────────────────────
    tracker = json.loads(TRACKER.read_text())
    apps    = tracker["applications"]
    meta    = tracker.get("_meta", {})

    active_count   = sum(1 for a in apps if a.get("status") not in ARCHIVED_STATUSES)
    archived_count = sum(1 for a in apps if a.get("status") in ARCHIVED_STATUSES)

    auto_rej_count = 0
    if AUTO_REJ_FILE.exists():
        ar_data = json.loads(AUTO_REJ_FILE.read_text())
        auto_rej_count = len(ar_data.get("auto_rejected", []))

    expected_apps    = active_count
    expected_archive = archived_count + auto_rej_count

    print(f"\n  Local files:")
    print(f"    job_tracker.json   — {active_count} active, {archived_count} archived")
    print(f"    auto_rejected.json — {auto_rej_count} entries")
    print(f"    {'─'*46}")
    print(f"    Expected Sheet:  Applications = {expected_apps}")
    print(f"                     Archive      = {expected_archive}  ({archived_count} tracker + {auto_rej_count} auto_rejected)")

    # ── Last push snapshot ────────────────────────────────────────────────────
    snap = meta.get("last_push_snapshot")
    if snap:
        print(f"\n  Last push snapshot: {snap['timestamp']}")
        print(f"    pushed Applications={snap['applications_count']}, Archive={snap['archive_count']}")
    else:
        print(f"\n  Last push snapshot: (none — push has never been recorded)")

    # ── Live Sheet counts ─────────────────────────────────────────────────────
    problems = []
    try:
        wb = get_sheet()

        # Applications tab
        try:
            ws_apps = wb.worksheet("Applications")
            app_rows = sum(1 for v in ws_apps.col_values(1)[1:] if v)
        except Exception:
            app_rows = None

        # Archive tab
        try:
            ws_arch = wb.worksheet("Archive")
            arch_rows = sum(1 for v in ws_arch.col_values(1)[1:] if v)
        except Exception:
            arch_rows = None

        print(f"\n  Google Sheet (live):")
        if app_rows is not None:
            match = "✓" if app_rows == expected_apps else "⚠"
            print(f"    Applications tab: {app_rows} rows {match}")
            if app_rows != expected_apps:
                problems.append(f"Applications tab has {app_rows} rows, expected {expected_apps}")
        else:
            print(f"    Applications tab: (not found)")
            problems.append("Applications tab missing — run push first")

        if arch_rows is not None:
            match = "✓" if arch_rows == expected_archive else "⚠"
            print(f"    Archive tab:      {arch_rows} rows {match}")
            if arch_rows != expected_archive:
                problems.append(f"Archive tab has {arch_rows} rows, expected {expected_archive}")
        else:
            print(f"    Archive tab:      (not found)")
            problems.append("Archive tab missing — run push first")

    except Exception as e:
        print(f"\n  Google Sheet (live): unreachable — {e}")
        print(f"\n  Sync verdict: ? UNKNOWN (Sheet unreachable)")
        return

    # ── Unpushed-changes check ────────────────────────────────────────────────
    if snap:
        if (snap["applications_count"] != active_count or
                snap["archive_count"] != expected_archive):
            problems.append(
                f"JSON changed since last push "
                f"(snapshot had apps={snap['applications_count']}, archive={snap['archive_count']}; "
                f"now apps={active_count}, archive={expected_archive}) — run push"
            )

    # ── Pull-needed check (Sheet edits not yet in JSON) ───────────────────────
    # Detect if Sheet Applications tab has status/career_page_url values that
    # differ from JSON — a lightweight signal that pull is needed.
    if app_rows and app_rows > 0:
        try:
            sheet_rows = wb.worksheet("Applications").get_all_records(value_render_option="FORMULA")
            apps_by_id = {a["id"]: a for a in apps}
            pull_needed = False
            for row in sheet_rows:
                app_id  = str(row.get("id", "")).strip()
                app     = apps_by_id.get(app_id)
                if not app:
                    continue
                for col in USER_EDITABLE:
                    sv = str(row.get(col, "") or "").strip()
                    if sv.startswith("=HYPERLINK"):
                        m = re.search(r'HYPERLINK\("([^"]+)"', sv)
                        sv = m.group(1) if m else ""
                    lv = str(app.get(col, "") or "").strip()
                    if sv and sv != lv:
                        pull_needed = True
                        break
                if pull_needed:
                    break
            if pull_needed:
                problems.append("Sheet has edits not yet in JSON (status/career_page_url/notes) — run pull")
        except Exception:
            pass

    # ── Verdict ───────────────────────────────────────────────────────────────
    print()
    if not problems:
        print("  Sync verdict: ✓ IN SYNC")
    else:
        for p in problems:
            print(f"  ⚠ {p}")
        print(f"\n  Sync verdict: ⚠ ACTION NEEDED  (see warnings above)")


# ─────────────────────────────────────────────────────────────────────────────
# RECOVER_ARCHIVE: import Archive tab entries missing from job_tracker.json
# ─────────────────────────────────────────────────────────────────────────────
def recover_archive():
    """Read the Archive tab and import any entries whose ID is not already in
    job_tracker.json. Useful after a JSON rebuild that lost historical entries.
    Recovered entries are minimal (only the fields the Archive tab stores).
    """
    print("\n[sheets_sync] RECOVER_ARCHIVE: Sheet Archive tab → job_tracker.json")
    check_setup()

    tracker = json.loads(TRACKER.read_text())
    existing_ids = {a["id"] for a in tracker["applications"]}

    # Also exclude IDs already in auto_rejected.json — those appear in Archive
    # but are NOT part of job_tracker.json by design.
    if AUTO_REJ_FILE.exists():
        ar_data = json.loads(AUTO_REJ_FILE.read_text())
        for e in ar_data.get("auto_rejected", []):
            if e.get("id"):
                existing_ids.add(e["id"])

    wb = get_sheet()
    try:
        ws = wb.worksheet("Archive")
    except Exception:
        print("  ✗ 'Archive' worksheet not found — nothing to recover")
        return

    rows = ws.get_all_records(value_render_option="FORMULA")
    today = datetime.now().strftime("%Y-%m-%d")

    recovered, skipped = 0, 0
    for row in rows:
        app_id = str(row.get("id", "")).strip()
        if not app_id:
            continue
        if app_id in existing_ids:
            skipped += 1
            continue

        # Extract raw URL from =HYPERLINK("url","...") formula if present
        raw_jd = str(row.get("jd_url", "") or "")
        if raw_jd.startswith("=HYPERLINK"):
            m = re.search(r'HYPERLINK\("([^"]+)"', raw_jd)
            raw_jd = m.group(1) if m else ""

        status = str(row.get("status", "") or "").strip() or "Rejected"
        entry = {
            "id":                    app_id,
            "company":               str(row.get("company", "") or "").strip(),
            "role":                  str(row.get("role", "") or "").strip(),
            "location":              str(row.get("location", "") or "").strip(),
            "fit_score":             row.get("fit_score", ""),
            "status":                status,
            "salary_stated":         str(row.get("salary_stated", "") or "").strip(),
            "jd_url":                raw_jd,
            "posted_date":           str(row.get("posted_date", "") or "").strip(),
            "visa_sponsorship_status": str(row.get("visa_sponsorship_status", "") or "").strip(),
            "notes":                 str(row.get("notes", "") or "").strip(),
            "source":                "sheet_recovery",
            "status_history": [{"status": status, "date": today, "source": "sheet_recovery"}],
        }
        tracker["applications"].append(entry)
        existing_ids.add(app_id)
        recovered += 1
        print(f"  + {entry['company']} / {entry['role']} ({status})")

    if recovered:
        TRACKER.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))
        print(f"\n  ✓ Recovered {recovered} entries into job_tracker.json ({skipped} already existed)")
    else:
        print(f"  No new entries to recover ({skipped} already in JSON)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    # Parse --tabs flag: e.g. --tabs apps,archive  →  {"apps", "archive"}
    _tabs_arg = None
    if "--tabs" in sys.argv:
        _idx = sys.argv.index("--tabs")
        _tabs_arg = set(sys.argv[_idx + 1].split(","))
        _VALID_TABS = {"apps", "archive", "outreach"}
        _unknown = _tabs_arg - _VALID_TABS
        if _unknown:
            print(f"  ✗ Unknown --tabs value(s): {_unknown}. Valid: {_VALID_TABS}")
            sys.exit(1)

    if mode == "push":
        # Always pull before push — no escape hatch. Skipping pull destroyed user
        # Sheet edits twice (2026-08-10). The extra API call is cheaper than data loss.
        print("[sheets_sync] Auto-pull before push (Sheet edits → JSON first)")
        pull(tabs=_tabs_arg)
        push(tabs=_tabs_arg)
    elif mode == "pull":
        pull(tabs=_tabs_arg)
    elif mode == "status":
        status()
    elif mode == "recover_archive":
        recover_archive()
    else:
        print(SETUP_GUIDE)
