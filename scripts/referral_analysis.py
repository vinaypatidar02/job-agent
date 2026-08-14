#!/usr/bin/env python3
"""
referral_analysis.py — Full referral pipeline analysis.

Prints a comprehensive report of the referral journey:
  - Funnel: Reached-Out → Followup → Referred / Stale-Referral
  - Active referrals with days-in-status
  - Conversion rates and timing statistics
  - Per-market breakdown
  - Journey timelines per application (--verbose)

Usage:
  python3 scripts/referral_analysis.py
  python3 scripts/referral_analysis.py --verbose   # include full journey timelines
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT    = Path(__file__).parent.parent
TRACKER = ROOT / "data" / "job_tracker.json"

REFERRAL_STATUSES = {"Reached-Out", "Followup", "Referred", "Stale-Referral"}


def _parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _find_status_date(app: dict, target: str) -> date | None:
    """Return the first date an entry entered target status."""
    for h in app.get("status_history", []):
        if h.get("status") == target:
            d = _parse_date(h.get("timestamp") or h.get("date") or "")
            if d:
                return d
    return None


def _days_between(d0: date | None, d1: date | None) -> str:
    if d0 and d1:
        return str((d1 - d0).days)
    return "—"


def analyse() -> None:
    tracker = json.loads(TRACKER.read_text())
    today   = date.today()
    verbose = "--verbose" in sys.argv

    # Collect all entries that ever touched a referral status
    referral_entries = []
    for app in tracker["applications"]:
        statuses_seen = {h.get("status") for h in app.get("status_history", [])}
        statuses_seen.add(app.get("status", ""))
        if statuses_seen & REFERRAL_STATUSES:
            referral_entries.append(app)

    w = 76
    print(f"\n{'═' * w}")
    print(f"  Referral Pipeline Analysis — {today.isoformat()}")
    print(f"{'═' * w}")

    if not referral_entries:
        print("\n  No referral entries found yet.")
        print("  To start: after Prep Complete, change status to 'Reached-Out' in the")
        print("  Google Sheet, then run: python3 scripts/sheets_sync.py pull")
        print(f"\n{'═' * w}\n")
        return

    # ── Categorise by current status ─────────────────────────────────────────
    by_status: dict[str, list] = defaultdict(list)
    for app in referral_entries:
        by_status[app.get("status", "Unknown")].append(app)

    reached_out = by_status.get("Reached-Out", [])
    followup    = by_status.get("Followup", [])
    referred    = by_status.get("Referred", [])
    stale       = by_status.get("Stale-Referral", [])
    other       = [
        a for k, v in by_status.items()
        if k not in REFERRAL_STATUSES
        for a in v
    ]

    total        = len(referral_entries)
    active_cnt   = len(reached_out) + len(followup)
    conv_pct     = f"{len(referred)/total*100:.0f}%" if total else "—"
    stale_pct    = f"{len(stale)/total*100:.0f}%"    if total else "—"

    # ── Funnel summary ────────────────────────────────────────────────────────
    print(f"\n  Funnel Summary")
    print(f"  {'─' * 44}")
    print(f"  Total referral attempts:     {total}")
    print(f"  ├── Active (Reached-Out):    {len(reached_out)}")
    print(f"  ├── Active (Followup):       {len(followup)}")
    print(f"  ├── Advanced to pipeline:    {len(other)}  (Under Review / Interview / etc.)")
    print(f"  ├── Referred:        {len(referred)}  ({conv_pct} conversion)")
    print(f"  └── Stale-Referral:          {len(stale)}  ({stale_pct})")

    # ── Helper: days since Reached-Out ────────────────────────────────────────
    def _ro_date(app: dict) -> date | None:
        return _find_status_date(app, "Reached-Out")

    def _days_from_ro(app: dict) -> str:
        d = _ro_date(app)
        return str((today - d).days) if d else "—"

    # ── Active referrals ──────────────────────────────────────────────────────
    active_all = reached_out + followup
    if active_all:
        print(f"\n  Active Referrals ({len(active_all)})")
        hdr = f"  {'Company':<26} {'Role':<26} {'Status':<15} {'Days':>5}  {'Market':<6}  Notes"
        sep = f"  {'─'*26} {'─'*26} {'─'*15} {'─'*5}  {'─'*6}  {'─'*22}"
        print(hdr)
        print(sep)
        for a in sorted(active_all, key=lambda x: _ro_date(x) or date.min):
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<26} "
                  f"{a.get('status',''):<15} {_days_from_ro(a):>5}  "
                  f"{a.get('market','uk'):<6}  {notes}")

    # ── Referred ──────────────────────────────────────────────────────
    if referred:
        print(f"\n  Referred ({len(referred)})")
        print(f"  {'Company':<26} {'Role':<26} {'Days to Referred':>17}  {'Market':<6}  Notes")
        print(f"  {'─'*26} {'─'*26} {'─'*17}  {'─'*6}  {'─'*22}")
        for a in referred:
            d0    = _ro_date(a)
            d1    = _find_status_date(a, "Referred")
            days  = _days_between(d0, d1)
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<26} "
                  f"{days:>17}  {a.get('market','uk'):<6}  {notes}")

    # ── Advanced into normal pipeline ─────────────────────────────────────────
    if other:
        print(f"\n  Advanced to Pipeline ({len(other)})  — formerly Referred")
        print(f"  {'Company':<26} {'Role':<26} {'Current Status':<20}  {'Market':<6}  Notes")
        print(f"  {'─'*26} {'─'*26} {'─'*20}  {'─'*6}  {'─'*22}")
        for a in other:
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<26} "
                  f"{a.get('status',''):<20}  {a.get('market','uk'):<6}  {notes}")

    # ── Stale referrals ───────────────────────────────────────────────────────
    if stale:
        print(f"\n  Stale Referrals — no response in 7+ days ({len(stale)})")
        print(f"  {'Company':<26} {'Role':<26} {'Days Elapsed':>13}  {'Market':<6}  Notes")
        print(f"  {'─'*26} {'─'*26} {'─'*13}  {'─'*6}  {'─'*22}")
        for a in stale:
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<26} "
                  f"{_days_from_ro(a):>13}  {a.get('market','uk'):<6}  {notes}")

    # ── Timing statistics ──────────────────────────────────────────────────────
    referred_times = []
    for a in referred:
        d0 = _ro_date(a)
        d1 = _find_status_date(a, "Referred")
        if d0 and d1:
            referred_times.append((d1 - d0).days)

    stale_times = []
    for a in stale:
        d0 = _ro_date(a)
        d1 = _find_status_date(a, "Stale-Referral")
        if d0 and d1:
            stale_times.append((d1 - d0).days)

    if referred_times or stale_times:
        print(f"\n  Timing")
        print(f"  {'─' * 44}")
        if referred_times:
            avg_r = sum(referred_times) / len(referred_times)
            print(f"  Avg days to Referred:  {avg_r:.1f}d  "
                  f"(range: {min(referred_times)}–{max(referred_times)}d)")
        if stale_times:
            avg_s = sum(stale_times) / len(stale_times)
            print(f"  Avg days to Stale-Referral:    {avg_s:.1f}d  "
                  f"(range: {min(stale_times)}–{max(stale_times)}d)")

    # ── Per-market breakdown ───────────────────────────────────────────────────
    if total > 1:
        mkt_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for a in referral_entries:
            mkt = a.get("market", "uk")
            mkt_counts[mkt][a.get("status", "?")] += 1

        print(f"\n  By Market")
        print(f"  {'Market':<8} {'Reached-Out':>12} {'Followup':>9} {'Referred':>9} "
              f"{'Stale':>7} {'Other':>6}")
        print(f"  {'─'*8} {'─'*12} {'─'*9} {'─'*9} {'─'*7} {'─'*6}")
        for mkt in sorted(mkt_counts.keys()):
            mc  = mkt_counts[mkt]
            oth = sum(v for k, v in mc.items() if k not in REFERRAL_STATUSES)
            print(f"  {mkt:<8} {mc.get('Reached-Out',0):>12} {mc.get('Followup',0):>9} "
                  f"{mc.get('Referred',0):>9} {mc.get('Stale-Referral',0):>7} {oth:>6}")

    # ── Full journey timelines (--verbose) ─────────────────────────────────────
    if verbose:
        print(f"\n  Journey Timelines")
        print(f"  {'─' * 60}")
        for a in referral_entries:
            print(f"\n  {a.get('company','')} — {a.get('role','')}  "
                  f"[{a.get('market','uk')}]  (current: {a.get('status','')})")
            for h in a.get("status_history", []):
                ts   = (h.get("date") or (h.get("timestamp") or "")[:10] or "—")
                src  = h.get("source", "")[:20]
                note = (h.get("reason") or h.get("note") or "")[:35]
                print(f"    {ts}  {h.get('status',''):<25}  {src:<20}  {note}")

    print(f"\n{'═' * w}\n")


if __name__ == "__main__":
    analyse()
