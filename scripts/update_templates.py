#!/usr/bin/env python3
"""
Update the Templates tab in the Google Sheet tracker.
Run whenever the contact table template or any other template changes.

Usage:
    python3 scripts/update_templates.py
"""

import sys
sys.path.insert(0, '.')
from scripts.sheets_sync import get_sheet


TEMPLATES = [
    # ── REFERRAL CONTACT ─────────────────────────────────────────
    ['REFERRAL CONTACT', '', ''],
    ['Field',        'Value', 'Options / Notes'],
    ['Job',          '', 'app_XXXX — blank for general recruiter outreach (Type C-General)'],
    ['Profile',      '', 'LinkedIn URL — auto-fills name, role, location, connection degree'],
    ['Relationship', '', 'cold | mutual | [YOUR_ALUMNI_NETWORK] alumni | ex-[Company A] | ex-[Company B] | [YOUR_ALUMNI_NETWORK] junior'],
    ['Nationality',  '', 'Indian — only if confirmed; leave blank (triggers struggle narrative)'],
    ['Channel',      '', 'linkedin / email'],
    ['Applied',      '', 'yes / no — blank = auto-detect from tracker (Applied/Under Review/Interview = yes; Approved/Prep Complete etc. = no). For is_relevant=yes contacts always "no". N/A for C-General.'],
    ['Is Relevant',  '', 'yes / no — blank = auto-detect (yes if recruiter / HM / TA keywords in role)'],
    ['Potential HM', '', 'yes / no — blank = auto-detect'],
    ['Type',         '', 'employee (default) / recruiter'],
    ['Agency',       '', 'Recruiter only — blank = internal HR/TA at hiring company'],
    ['Via',          '', 'Optional — app_XXXX that surfaced this contact when NOT applying for it'],
    ['', '', ''],
    ['', '', ''],

    # ── STATUS UPDATE ─────────────────────────────────────────────
    ['STATUS UPDATE', '', ''],
    ['Field',    'Value', 'Options / Notes'],
    ['Contact',  '', 'Contact name'],
    ['Job',      '', 'app_XXXX'],
    ['Status',   '', 'Connection-Requested / Reached-Out / Referred / No Response / Declined'],
    ['Date',     '', 'YYYY-MM-DD  (leave blank = today)'],
    ['Note',     '', "Optional context (e.g. 'accepted connection, sent referral request')"],
    ['', '', ''],
    ['', '', ''],

    # ── HOW TO USE ────────────────────────────────────────────────
    ['HOW TO USE', '', ''],
    ['1', 'Fill in the Value column for the template you need', ''],
    ['2', 'Copy the filled rows (Col A + Col B)', ''],
    ['3', 'Paste into chat — Claude reads the Field | Value format', ''],
]


def main():
    wb   = get_sheet()
    tmpl = wb.worksheet('Templates')
    rng  = f'A1:C{len(TEMPLATES)}'
    tmpl.update(rng, TEMPLATES)
    print(f'[update_templates] Templates tab updated — {len(TEMPLATES)} rows written')


if __name__ == '__main__':
    main()
