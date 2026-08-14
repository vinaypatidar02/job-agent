#!/usr/bin/env python3
"""
outreach.py — Recruiter outreach + platform registration tracker

Commands:
  python3 scripts/outreach.py list                          # all platforms + recruiters
  python3 scripts/outreach.py list --type platforms
  python3 scripts/outreach.py list --type recruiters
  python3 scripts/outreach.py list --market nl              # filter recruiters by market
  python3 scripts/outreach.py list --status "Not Contacted" # filter by status

  python3 scripts/outreach.py add-platform "Name" --url URL --markets nl,de,uk --notes "..."
  python3 scripts/outreach.py add-recruiter "Name" "Agency" --market uk --method LinkedIn --email x@y.com --linkedin https://...

  python3 scripts/outreach.py update plt_001 --status Active --profile-url "https://..."
  python3 scripts/outreach.py update rec_001 --status Replied --note "Interested, wants CV"

  python3 scripts/outreach.py --dry-run                     # validate file only (for check_workflow)
"""

import json
import sys
import argparse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTREACH_PATH = ROOT / "data" / "outreach.json"
TODAY = date.today().isoformat()


def _load() -> dict:
    return json.loads(OUTREACH_PATH.read_text())


def _save(data: dict) -> None:
    data["_meta"]["last_updated"] = TODAY
    OUTREACH_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _next_id(items: list, prefix: str) -> str:
    nums = [int(x["id"][len(prefix):]) for x in items if x.get("id", "").startswith(prefix) and x["id"][len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1 if nums else 1):03d}"


# ── LIST ──────────────────────────────────────────────────────────────────────

def cmd_list(args):
    data = _load()
    show_type = args.type  # "platforms", "recruiters", or None (both)

    if show_type != "recruiters":
        platforms = data["platforms"]
        if args.status:
            platforms = [p for p in platforms if p["status"].lower() == args.status.lower()]
        print(f"\nPLATFORMS ({len(platforms)})")
        print("  " + "─" * 78)
        for p in platforms:
            markets = ",".join(p.get("markets") or [])
            profile = f"  profile: {p['profile_url']}" if p.get("profile_url") else ""
            reg = f"  registered: {p['registered_date']}" if p.get("registered_date") else ""
            status_tag = f"[{p['status']}]"
            print(f"  {p['id']}  {p['name']:<28} {status_tag:<14} {p.get('priority',''):<8} {markets}{profile}{reg}")
            if p.get("notes"):
                print(f"           {p['notes'][:90]}")
        print()

    if show_type != "platforms":
        recruiters = data["recruiters"]
        if args.market:
            recruiters = [r for r in recruiters if r.get("market") == args.market.lower()]
        if args.status:
            recruiters = [r for r in recruiters if r["status"].lower() == args.status.lower()]

        print(f"RECRUITERS ({len(recruiters)})")
        print("  " + "─" * 78)
        for r in recruiters:
            name_str = f" — {r['name']}" if r.get("name") else ""
            contacted = f"  contacted: {r['contacted_date']}" if r.get("contacted_date") else ""
            responded = f"  replied: {r['response_date']}" if r.get("response_date") else ""
            status_tag = f"[{r['status']}]"
            print(f"  {r['id']}  {r['agency']:<22} ({r.get('market','?')})  {status_tag:<18}{name_str}{contacted}{responded}")
            if r.get("notes"):
                print(f"           {r['notes'][:90]}")
        print()

    # Follow-up nudges — messaged but no reply in 7+ days
    if show_type != "platforms":
        pending = [
            r for r in data["recruiters"]
            if r["status"] == "Messaged" and r.get("contacted_date")
            and (date.fromisoformat(TODAY) - date.fromisoformat(r["contacted_date"])).days >= 7
        ]
        if pending:
            print(f"⚠  FOLLOW-UP DUE ({len(pending)} recruiter(s) messaged 7+ days ago, no reply):")
            for r in pending:
                days = (date.fromisoformat(TODAY) - date.fromisoformat(r["contacted_date"])).days
                print(f"   {r['id']}  {r['agency']} ({r.get('market','?')}) — {days}d ago")
            print()


# ── ADD PLATFORM ──────────────────────────────────────────────────────────────

def cmd_add_platform(args):
    data = _load()
    new_id = _next_id(data["platforms"], "plt_")
    entry = {
        "id": new_id,
        "name": args.name,
        "url": args.url or "",
        "markets": [m.strip() for m in (args.markets or "").split(",") if m.strip()],
        "priority": args.priority or "",
        "model": args.model or "",
        "registered_date": None,
        "status": "Pending",
        "profile_url": None,
        "notes": args.notes or "",
    }
    data["platforms"].append(entry)
    _save(data)
    print(f"  ✓ Added platform {new_id}: {args.name}")


# ── ADD RECRUITER ─────────────────────────────────────────────────────────────

def cmd_add_recruiter(args):
    data = _load()
    new_id = _next_id(data["recruiters"], "rec_")
    entry = {
        "id": new_id,
        "name": args.name or None,
        "agency": args.agency,
        "market": (args.market or "uk").lower(),
        "speciality": args.speciality or "",
        "email": args.email or None,
        "linkedin_url": args.linkedin or None,
        "contacted_date": None,
        "method": args.method or None,
        "status": "Not Contacted",
        "status_history": [],
        "response_date": None,
        "notes": args.notes or "",
    }
    data["recruiters"].append(entry)
    _save(data)
    print(f"  ✓ Added recruiter {new_id}: {args.name or '(unnamed)'} @ {args.agency}")


# ── UPDATE ────────────────────────────────────────────────────────────────────

def cmd_update(args):
    data = _load()
    entry_id = args.id.lower()

    # Find in platforms or recruiters
    target = next((p for p in data["platforms"] if p["id"] == entry_id), None)
    kind = "platform"
    if not target:
        target = next((r for r in data["recruiters"] if r["id"] == entry_id), None)
        kind = "recruiter"
    if not target:
        print(f"  ✗ No entry found with id '{entry_id}'")
        sys.exit(1)

    if args.status:
        valid = data["_meta"]["platform_statuses" if kind == "platform" else "recruiter_statuses"]
        if args.status not in valid:
            print(f"  ✗ Invalid status '{args.status}'. Valid: {valid}")
            sys.exit(1)
        old_status = target["status"]
        target["status"] = args.status
        if kind == "recruiter":
            target.setdefault("status_history", []).append({
                "status": args.status, "date": TODAY, "from": old_status
            })
        # Auto-set dates
        if kind == "recruiter" and args.status == "Messaged" and not target.get("contacted_date"):
            target["contacted_date"] = TODAY
        if kind == "recruiter" and args.status in ("Replied", "In Progress") and not target.get("response_date"):
            target["response_date"] = TODAY
        if kind == "platform" and args.status == "Registered" and not target.get("registered_date"):
            target["registered_date"] = TODAY
        if kind == "platform" and args.status == "Active" and not target.get("registered_date"):
            target["registered_date"] = TODAY

    if args.profile_url and kind == "platform":
        target["profile_url"] = args.profile_url
    if args.name and kind == "recruiter":
        target["name"] = args.name
    if args.email and kind == "recruiter":
        target["email"] = args.email
    if args.linkedin and kind == "recruiter":
        target["linkedin_url"] = args.linkedin
    if args.method and kind == "recruiter":
        target["method"] = args.method
    if args.note:
        existing = target.get("notes") or ""
        target["notes"] = f"{existing} | {TODAY}: {args.note}".lstrip(" | ")

    _save(data)
    print(f"  ✓ Updated {kind} {entry_id}: {target.get('name') or target.get('agency') or target.get('name')} → {target['status']}")


# ── DRY RUN ───────────────────────────────────────────────────────────────────

def cmd_dry_run():
    data = _load()
    assert "platforms" in data, "missing 'platforms' key"
    assert "recruiters" in data, "missing 'recruiters' key"
    assert "_meta" in data, "missing '_meta' key"
    assert "platform_statuses" in data["_meta"]
    assert "recruiter_statuses" in data["_meta"]
    print(f"  outreach.json OK — {len(data['platforms'])} platforms, {len(data['recruiters'])} recruiters")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Recruiter outreach + platform tracker")
    parser.add_argument("--dry-run", action="store_true", help="Validate file and exit (for check_workflow)")

    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list")
    p_list.add_argument("--type", choices=["platforms", "recruiters"])
    p_list.add_argument("--market")
    p_list.add_argument("--status")

    p_plat = sub.add_parser("add-platform")
    p_plat.add_argument("name")
    p_plat.add_argument("--url")
    p_plat.add_argument("--markets")
    p_plat.add_argument("--priority")
    p_plat.add_argument("--model")
    p_plat.add_argument("--notes")

    p_rec = sub.add_parser("add-recruiter")
    p_rec.add_argument("name", nargs="?")
    p_rec.add_argument("agency")
    p_rec.add_argument("--market", default="uk")
    p_rec.add_argument("--speciality")
    p_rec.add_argument("--email")
    p_rec.add_argument("--linkedin")
    p_rec.add_argument("--method")
    p_rec.add_argument("--notes")

    p_upd = sub.add_parser("update")
    p_upd.add_argument("id")
    p_upd.add_argument("--status")
    p_upd.add_argument("--profile-url")
    p_upd.add_argument("--name")
    p_upd.add_argument("--email")
    p_upd.add_argument("--linkedin")
    p_upd.add_argument("--method")
    p_upd.add_argument("--note")

    args = parser.parse_args()

    if args.dry_run:
        cmd_dry_run()
        return

    if args.command == "list" or args.command is None:
        if args.command is None:
            args.type = None
            args.market = None
            args.status = None
        cmd_list(args)
    elif args.command == "add-platform":
        cmd_add_platform(args)
    elif args.command == "add-recruiter":
        cmd_add_recruiter(args)
    elif args.command == "update":
        cmd_update(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
