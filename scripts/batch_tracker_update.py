from __future__ import annotations
"""
batch_tracker_update.py — Atomic multi-job tracker update.

Reads job_tracker.json ONCE, applies all N updates in a single pass, then
writes ONCE. Eliminates race conditions from multiple sequential writes.

Updates JSON format:
    {"updates": [{"id": "app_7467", "status": "Prep Complete",
                  "resume_path": "outputs/.../<YOUR_NAME>_CV.pdf",
                  "cover_letter_path": "outputs/.../<YOUR_NAME>_CoverLetter.pdf",
                  "date": "2026-08-10"}]}

Run:
    python3 scripts/batch_tracker_update.py --updates data/prep_tmp/tracker_updates.json
"""
import json, sys, argparse, datetime
from pathlib import Path

ROOT         = Path(__file__).parent.parent
TRACKER_PATH = ROOT / "data" / "job_tracker.json"

# These statuses are terminal — never overwrite with a prep status
TERMINAL_STATUSES = {
    "Withdrawn", "Rejected", "Applied", "Under Review",
    "Interview Scheduled", "Assessment", "Offer Received",
    "Referral", "Referred",
}


def main():
    parser = argparse.ArgumentParser(description="Atomic multi-job tracker update")
    parser.add_argument("--updates", required=True, help="Path to JSON file with update list")
    args = parser.parse_args()

    updates_path = Path(args.updates)
    if not updates_path.exists():
        print(f"ERROR: updates file not found: {updates_path}", file=sys.stderr)
        sys.exit(1)

    try:
        updates_data = json.loads(updates_path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON in updates file: {e}", file=sys.stderr)
        sys.exit(1)

    updates = updates_data.get("updates")
    if not isinstance(updates, list):
        print("ERROR: updates file must have top-level key 'updates' (list)", file=sys.stderr)
        sys.exit(1)

    if not updates:
        print("No updates to apply."); return

    # Build update index
    update_index: dict[str, dict] = {}
    for u in updates:
        uid = u.get("id", "").strip()
        if not uid:
            print(f"[WARN] Skipping update with missing 'id': {u}")
            continue
        update_index[uid] = u

    # Read tracker once
    if not TRACKER_PATH.exists():
        print(f"ERROR: {TRACKER_PATH} not found", file=sys.stderr)
        sys.exit(1)

    tracker = json.loads(TRACKER_PATH.read_text())
    applications = tracker.get("applications", [])

    applied_ids: set[str] = set()
    skipped_terminal: list[str] = []
    not_found_ids = set(update_index.keys())
    now_iso = datetime.date.today().isoformat()

    for app in applications:
        aid = app.get("id", "")
        if aid not in update_index:
            continue

        not_found_ids.discard(aid)
        u = update_index[aid]
        current_status = app.get("status", "")
        new_status = u.get("status", "")

        if current_status in TERMINAL_STATUSES:
            # Terminal: update paths only, skip status change
            skipped_terminal.append(f"{aid} ({current_status})")
            if u.get("resume_path"):
                app["resume_path"] = u["resume_path"]
            if u.get("cover_letter_path"):
                app["cover_letter_path"] = u["cover_letter_path"]
            print(f"[SKIP]  {aid}: terminal status '{current_status}' — paths updated only")
            applied_ids.add(aid)
            continue

        # Apply full update
        date_str = u.get("date", now_iso)
        prev_status = current_status

        if new_status:
            app["status"] = new_status
        if u.get("resume_path"):
            app["resume_path"] = u["resume_path"]
        if u.get("cover_letter_path"):
            app["cover_letter_path"] = u["cover_letter_path"]

        # Append to status_history
        if not isinstance(app.get("status_history"), list):
            app["status_history"] = []
        if new_status and new_status != prev_status:
            app["status_history"].append({
                "status": new_status,
                "date": date_str,
                "note": "prep complete — PDFs generated"
            })

        print(f"[OK]    {aid}: {prev_status} → {new_status}")
        applied_ids.add(aid)

    if not_found_ids:
        for nid in sorted(not_found_ids):
            print(f"[WARN]  {nid}: not found in job_tracker.json — skipped")

    # Write tracker once
    TRACKER_PATH.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))

    print(f"\nbatch_tracker_update: applied {len(applied_ids)} updates "
          f"({len(skipped_terminal)} terminal-status skips)")


if __name__ == "__main__":
    main()
