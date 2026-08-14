#!/usr/bin/env python3
"""
referral_tracker.py — Advance referral statuses based on days elapsed.

Automatic advancement rules (relative to first Reached-Out date):
  Reached-Out → Followup        day 4+ (3+ full days since Reached-Out)
  Reached-Out → Stale-Referral  day 8+ (7+ full days, if Followup was skipped)
  Followup    → Stale-Referral  day 8+ (7+ full days since original Reached-Out)

Usage:
  python3 scripts/referral_tracker.py            # advance + show status
  python3 scripts/referral_tracker.py --dry-run  # preview without writing
  python3 scripts/referral_tracker.py status     # show active referrals only (no advance)
  python3 scripts/referral_tracker.py --push     # advance + push to Sheet after writing

Intended to be run daily, or before reviewing the Google Sheet.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT    = Path(__file__).parent.parent
TRACKER = ROOT / "data" / "job_tracker.json"

REFERRAL_ACTIVE = {"Reached-Out", "Followup"}
FOLLOWUP_DAYS   = 3   # advance Reached-Out → Followup after this many days
STALE_DAYS      = 7   # advance Reached-Out / Followup → Stale-Referral after this many days


def _parse_date(s: str) -> date | None:
    """Parse ISO date string (YYYY-MM-DD or datetime) → date. Returns None on failure."""
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _find_reached_out_date(app: dict) -> date | None:
    """Return the date the entry first entered Reached-Out status."""
    for entry in app.get("status_history", []):
        if entry.get("status") == "Reached-Out":
            ts = entry.get("timestamp") or entry.get("date") or ""
            d = _parse_date(ts)
            if d:
                return d
    return None


def _find_status_date(app: dict, target_status: str) -> date | None:
    """Return the date the entry first entered target_status."""
    for entry in app.get("status_history", []):
        if entry.get("status") == target_status:
            ts = entry.get("timestamp") or entry.get("date") or ""
            d = _parse_date(ts)
            if d:
                return d
    return None


def advance_statuses(dry_run: bool = False) -> list[dict]:
    """
    Advance Reached-Out / Followup entries based on days elapsed since Reached-Out.
    Returns list of changes made.
    """
    tracker = json.loads(TRACKER.read_text())
    today   = date.today()
    changes = []

    for app in tracker["applications"]:
        status = app.get("status", "")
        if status not in REFERRAL_ACTIVE:
            continue

        reached_out_date = _find_reached_out_date(app)
        if not reached_out_date:
            print(f"  ⚠ {app.get('company')} / {app.get('role')}: "
                  f"status={status} but no Reached-Out date in history — skipping")
            continue

        days_elapsed = (today - reached_out_date).days

        new_status = None
        if days_elapsed >= STALE_DAYS:
            new_status = "Stale-Referral"
        elif days_elapsed >= FOLLOWUP_DAYS and status == "Reached-Out":
            new_status = "Followup"

        if not new_status:
            continue

        changes.append({
            "id":         app["id"],
            "company":    app.get("company", ""),
            "role":       app.get("role", ""),
            "old_status": status,
            "new_status": new_status,
            "days":       days_elapsed,
        })

        if not dry_run:
            app["status"] = new_status
            app.setdefault("status_history", []).append({
                "status": new_status,
                "date":   today.isoformat(),
                "source": "referral_tracker",
                "reason": f"Auto-advanced from {status} after {days_elapsed} days since Reached-Out",
            })

    if not dry_run and changes:
        TRACKER.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))

    return changes


def show_status() -> None:
    """Print current referral pipeline state."""
    tracker = json.loads(TRACKER.read_text())
    today   = date.today()

    all_referral = {"Reached-Out", "Followup", "Referred", "Stale-Referral"}
    entries = [a for a in tracker["applications"] if a.get("status") in all_referral]

    print(f"\n[referral_tracker] Referral Pipeline — {today.isoformat()}")
    print(f"  {'─' * 72}")

    if not entries:
        print("  No referral-tracked entries yet.\n")
        print("  To start: change status to 'Reached-Out' in the Sheet after prep,")
        print("  then run: python3 scripts/sheets_sync.py pull --tabs apps,archive,outreach\n")
        return

    active    = [a for a in entries if a.get("status") in ("Reached-Out", "Followup")]
    converted = [a for a in entries if a.get("status") == "Referred"]
    stale     = [a for a in entries if a.get("status") == "Stale-Referral"]

    def _days_since_ro(app: dict) -> str:
        d = _find_reached_out_date(app)
        return str((today - d).days) if d else "-"

    def _days_to(app: dict, status: str) -> str:
        d0 = _find_reached_out_date(app)
        d1 = _find_status_date(app, status)
        if d0 and d1:
            return str((d1 - d0).days)
        return "-"

    if active:
        print(f"\n  Active Referrals ({len(active)})")
        print(f"  {'Company':<26} {'Role':<28} {'Status':<15} {'Days':>5}  Notes")
        print(f"  {'─'*26} {'─'*28} {'─'*15} {'─'*5}  {'─'*22}")
        for a in sorted(active, key=lambda x: _find_reached_out_date(x) or date.min):
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<28} "
                  f"{a.get('status',''):<15} {_days_since_ro(a):>5}  {notes}")

    if converted:
        print(f"\n  Referred ({len(converted)})")
        print(f"  {'Company':<26} {'Role':<28} {'Days to Referred':>17}  {'Market':<6}  Notes")
        print(f"  {'─'*26} {'─'*28} {'─'*17}  {'─'*6}  {'─'*22}")
        for a in converted:
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<28} "
                  f"{_days_to(a, 'Referred'):>17}  {a.get('market','uk'):<6}  {notes}")

    if stale:
        print(f"\n  Stale Referrals — no response after 7+ days ({len(stale)})")
        print(f"  {'Company':<26} {'Role':<28} {'Days Elapsed':>13}  Notes")
        print(f"  {'─'*26} {'─'*28} {'─'*13}  {'─'*22}")
        for a in stale:
            notes = (a.get("notes") or "")[:22]
            print(f"  {a.get('company',''):<26} {a.get('role',''):<28} "
                  f"{_days_since_ro(a):>13}  {notes}")

    total = len(entries)
    conv_pct  = f"{len(converted)/total*100:.0f}%" if total else "—"
    stale_pct = f"{len(stale)/total*100:.0f}%"     if total else "—"
    print(f"\n  Totals: {len(active)} active | {len(converted)} referred ({conv_pct}) | "
          f"{len(stale)} stale ({stale_pct})")
    print()


def main() -> None:
    dry_run     = "--dry-run" in sys.argv
    push        = "--push" in sys.argv
    status_only = "status" in sys.argv

    if status_only:
        show_status()
        return

    if dry_run:
        print("[referral_tracker] DRY RUN — no changes will be written\n")

    changes = advance_statuses(dry_run=dry_run)

    if changes:
        print(f"[referral_tracker] {'Would advance' if dry_run else 'Advanced'} "
              f"{len(changes)} entries:")
        for c in changes:
            print(f"  {c['company']} / {c['role']}: "
                  f"{c['old_status']} → {c['new_status']}  ({c['days']}d since Reached-Out)")
    else:
        print("[referral_tracker] No status advances needed today.")

    show_status()

    if push and not dry_run and changes:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "sheets_sync.py"), "push",
             "--tabs", "apps,archive,outreach"],
            cwd=str(ROOT),
        )
        if result.returncode == 0:
            print("[referral_tracker] Pushed updated statuses to Google Sheet.")
        else:
            print("[referral_tracker] ⚠ Sheet push failed — "
                  "run manually: python3 scripts/sheets_sync.py push --tabs apps,archive,outreach")


if __name__ == "__main__":
    main()
