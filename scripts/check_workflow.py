#!/usr/bin/env python3
"""
check_workflow.py — Full pipeline integrity check.

Run after ANY enhancement to scripts, agents, skills, hooks, or CLAUDE.md:
  python3 scripts/check_workflow.py          # all 8 checks
  python3 scripts/check_workflow.py --quick  # C1–C6 only (no subprocess, <2s)

Exit 0 if all checks pass, 1 if any fail.
"""

import json
import py_compile
import re
import subprocess
import sys
from pathlib import Path

ROOT   = Path(__file__).parent.parent
QUICK  = "--quick" in sys.argv
PASSED = []
FAILED = []


def _pass(label, detail=""):
    PASSED.append(label)
    suffix = f" ({detail})" if detail else ""
    print(f"  {label:<42} PASS{suffix}")


def _fail(label, reason, hint=""):
    FAILED.append(label)
    print(f"  {label:<42} FAIL")
    print(f"     ✗ {reason}")
    if hint:
        print(f"       → {hint}")


# ─────────────────────────────────────────────────────────────────────────────
# C1 — Required files exist
# ─────────────────────────────────────────────────────────────────────────────
def check_c1_files():
    required = [
        # data files — note: data/resumes/*.pdf are personal reference docs, not pipeline inputs
        # The pipeline generates fresh PDFs from experience_bank.md + candidate_profile.json
        "data/content/candidate_profile.json",
        "data/job_tracker.json",
        "data/auto_rejected.json",
        "data/content/experience_bank.md",
        "data/content/cover_letter_bank.md",
        "data/processed_email_ids.json",
        "data/outreach.json",
        # scripts
        "scripts/apify_cache.py",
        "scripts/auto_prep.py",
        "scripts/enrich_jobs.py",
        "scripts/validate_prep.py",
        "scripts/fetch_jd.py",
        "scripts/gmail_backfill.py",
        "scripts/pdf_renderer.py",
        "scripts/run_scout.py",
        "scripts/score_jobs.py",
        "scripts/sheets_sync.py",
        "scripts/test_email_tracker.py",
        "scripts/outreach.py",
        "scripts/referral_tracker.py",
        "scripts/referral_analysis.py",
        # parallel prep pipeline (added 2026-08-10)
        "scripts/generate_covers.py",
        "scripts/finalize_resumes.py",
        "scripts/batch_tracker_update.py",
        "scripts/run_prep.py",
        # agents / skills / hooks
        "agents/job_scout.md",
        "agents/application_prep.md",
        "agents/tracker.md",
        "skills/score_job.md",
        "skills/tailor_resume.md",
        "skills/draft_cover_letter.md",
        "hooks/on_job_approved.md",
        "hooks/on_email_received.md",
        # root
        "CLAUDE.md",
        "mcp.json",
        ".claude/settings.json",
    ]
    # .env is gitignored — users create it from .env.example. Warn only.
    setup_files = [".env"]
    missing = [p for p in required if not (ROOT / p).exists()]
    missing_setup = [p for p in setup_files if not (ROOT / p).exists()]
    if missing:
        _fail("C1 Required files", f"{len(missing)} missing: {', '.join(missing[:3])}{'...' if len(missing) > 3 else ''}",
              "Ensure all pipeline files are present before running")
    elif missing_setup:
        _fail("C1 Required files", f"{len(missing_setup)} setup file(s) not found: {', '.join(missing_setup)}",
              "Copy .env.example → .env and fill in your API keys (see GUIDE.md §4 Step 2)")
    else:
        _pass("C1 Required files", f"{len(required) + len(setup_files)}/{len(required) + len(setup_files)}")


# ─────────────────────────────────────────────────────────────────────────────
# C2 — Python syntax (compile check)
# ─────────────────────────────────────────────────────────────────────────────
def check_c2_syntax():
    scripts = sorted((ROOT / "scripts").glob("*.py"))
    errors = []
    for path in scripts:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{path.name}: {e}")
    if errors:
        for e in errors:
            _fail("C2 Python syntax", e, "Fix syntax error before any other work")
    else:
        _pass("C2 Python syntax", f"{len(scripts)}/{len(scripts)} scripts")


# ─────────────────────────────────────────────────────────────────────────────
# C3 — job_tracker.json schema
# ─────────────────────────────────────────────────────────────────────────────
def check_c3_tracker():
    path = ROOT / "data" / "job_tracker.json"
    if not path.exists():
        _fail("C3 job_tracker schema", "File missing — C1 should have caught this")
        return
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        _fail("C3 job_tracker schema", f"Invalid JSON: {e}", "Fix JSON syntax in job_tracker.json")
        return

    issues = []

    # Top-level structure
    if "_meta" not in data:
        issues.append("missing '_meta' key")
    if "applications" not in data:
        issues.append("missing 'applications' key")
    if issues:
        _fail("C3 job_tracker schema", "; ".join(issues))
        return

    meta  = data.get("_meta", {})
    apps  = data.get("applications", [])
    valid = set(meta.get("valid_statuses", []))

    if not valid:
        issues.append("_meta.valid_statuses is empty")

    # Per-entry checks
    seen_ids   = set()
    bad_status = []
    missing_fields = []
    dup_ids    = []

    for a in apps:
        for field in ("id", "company", "role", "status"):
            if not a.get(field):
                missing_fields.append(f"{a.get('id','?')}.{field}")
        aid = a.get("id", "")
        if aid in seen_ids:
            dup_ids.append(aid)
        seen_ids.add(aid)
        st = a.get("status", "")
        if valid and st and st not in valid:
            bad_status.append(f"{a.get('id','?')}: '{st}'")

    if missing_fields:
        issues.append(f"{len(missing_fields)} entries missing required fields: {', '.join(missing_fields[:3])}{'...' if len(missing_fields)>3 else ''}")
    if bad_status:
        issues.append(f"{len(bad_status)} invalid status values: {', '.join(bad_status[:3])}{'...' if len(bad_status)>3 else ''}")
    if dup_ids:
        issues.append(f"duplicate IDs: {', '.join(dup_ids[:3])}")

    if issues:
        for issue in issues:
            _fail("C3 job_tracker schema", issue)
    else:
        _pass("C3 job_tracker schema", f"{len(apps)} entries, all valid")


# ─────────────────────────────────────────────────────────────────────────────
# C4 — auto_rejected.json schema (key must be "auto_rejected", not "jobs")
# ─────────────────────────────────────────────────────────────────────────────
def check_c4_auto_rejected():
    path = ROOT / "data" / "auto_rejected.json"
    if not path.exists():
        _fail("C4 auto_rejected schema", "File missing")
        return
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        _fail("C4 auto_rejected schema", f"Invalid JSON: {e}")
        return

    if not isinstance(data, dict) or "auto_rejected" not in data:
        top_keys = list(data.keys())[:4] if isinstance(data, dict) else type(data).__name__
        _fail("C4 auto_rejected schema",
              f"Top-level key must be 'auto_rejected', found: {top_keys}",
              "Fix: wrap entries under {\"auto_rejected\": [...]} — wrong key caused today's incident")
        return

    entries = data["auto_rejected"]
    bad = [e.get("id", "?") for e in entries if not e.get("company") or not e.get("role")]
    if bad:
        _fail("C4 auto_rejected schema", f"{len(bad)} entries missing company/role: {bad[:3]}")
    else:
        _pass("C4 auto_rejected schema", f"{len(entries)} entries, correct key")


# ─────────────────────────────────────────────────────────────────────────────
# C5 — Sheets sync consistency
# ─────────────────────────────────────────────────────────────────────────────
def check_c5_sheets_sync():
    issues = []

    # 5a — ARCHIVED_STATUSES in sheets_sync.py must match tracker valid_statuses
    sync_src = (ROOT / "scripts" / "sheets_sync.py").read_text()
    m = re.search(r'ARCHIVED_STATUSES\s*=\s*\{([^}]+)\}', sync_src)
    if not m:
        issues.append("ARCHIVED_STATUSES constant not found in sheets_sync.py")
    else:
        raw = m.group(1)
        archived_in_code = {s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()}
        tracker_path = ROOT / "data" / "job_tracker.json"
        if tracker_path.exists():
            meta = json.loads(tracker_path.read_text()).get("_meta", {})
            valid = set(meta.get("valid_statuses", []))
            not_in_valid = archived_in_code - valid
            if not_in_valid:
                issues.append(
                    f"ARCHIVED_STATUSES values not in valid_statuses: {not_in_valid} "
                    f"— add them to _meta.valid_statuses"
                )

    # 5b — last_push_snapshot must exist (push was run at least once)
    # null is allowed for fresh installs — only fail if key is entirely absent
    tracker_path = ROOT / "data" / "job_tracker.json"
    if tracker_path.exists():
        meta = json.loads(tracker_path.read_text()).get("_meta", {})
        snap = meta.get("last_push_snapshot", "MISSING")
        if snap == "MISSING":
            issues.append("_meta.last_push_snapshot key absent — run: python3 scripts/sheets_sync.py push")

    if issues:
        for issue in issues:
            _fail("C5 Sheets sync consistency", issue)
    else:
        _pass("C5 Sheets sync consistency")


# ─────────────────────────────────────────────────────────────────────────────
# C6 — settings.json integrity
# ─────────────────────────────────────────────────────────────────────────────
def check_c6_settings():
    path = ROOT / ".claude" / "settings.json"
    if not path.exists():
        _fail("C6 settings.json", "File missing")
        return
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        _fail("C6 settings.json", f"Invalid JSON: {e}", "Fix JSON syntax in .claude/settings.json")
        return

    issues = []
    hooks = data.get("hooks", {})
    if "PostToolUse" not in hooks:
        issues.append("hooks.PostToolUse missing")
    else:
        for entry in hooks["PostToolUse"]:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if "job_tracker.json" in cmd and not (ROOT / "data" / "job_tracker.json").exists():
                    issues.append("hook references data/job_tracker.json which does not exist")

    if issues:
        for issue in issues:
            _fail("C6 settings.json", issue)
    else:
        _pass("C6 settings.json")


# ─────────────────────────────────────────────────────────────────────────────
# C7 — pdf_renderer self-test  (skipped with --quick)
# ─────────────────────────────────────────────────────────────────────────────
def check_c7_pdf_renderer():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "pdf_renderer.py"), "test"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if result.returncode != 0:
        _fail("C7 pdf_renderer self-test",
              result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "non-zero exit",
              "Check reportlab install: pip install reportlab")
    else:
        _pass("C7 pdf_renderer self-test")


# ─────────────────────────────────────────────────────────────────────────────
# C8 — email tracker dry run  (skipped with --quick)
# ─────────────────────────────────────────────────────────────────────────────
def check_c8_email_tracker():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_email_tracker.py"), "--dry"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if result.returncode != 0:
        _fail("C8 email tracker dry run",
              result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "non-zero exit",
              "Check data/job_tracker.json is readable and well-formed")
    else:
        _pass("C8 email tracker dry run")


# ─────────────────────────────────────────────────────────────────────────────
# C9 — Python 3.9 annotation compatibility (PEP 604 unions need __future__)
# py_compile (C2) never evaluates annotations, so `-> X | None` on a module-level
# def crashes at import time on Python 3.9 without `from __future__ import
# annotations`. This killed monitor_scout.py silently for weeks (fixed 2026-07-12).
# ─────────────────────────────────────────────────────────────────────────────
def check_c9_annotations():
    import ast

    def _has_union(node) -> bool:
        for sub in ast.walk(node):
            if isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr):
                return True
        return False

    offenders = []
    for path in sorted((ROOT / "scripts").glob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue  # C2 owns syntax errors
        has_future = any(
            isinstance(n, ast.ImportFrom) and n.module == "__future__"
            and any(a.name == "annotations" for a in n.names)
            for n in tree.body
        )
        if has_future:
            continue
        for node in ast.walk(tree):
            anns = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                anns = [a.annotation for a in node.args.args + node.args.kwonlyargs
                        if a.annotation] + ([node.returns] if node.returns else [])
            elif isinstance(node, ast.AnnAssign) and node.annotation:
                anns = [node.annotation]
            if any(_has_union(a) for a in anns):
                offenders.append(path.name)
                break

    if offenders:
        _fail("C9 Py3.9 annotations",
              f"PEP 604 unions without __future__ import: {', '.join(offenders)}",
              "Add 'from __future__ import annotations' after the module docstring")
    else:
        _pass("C9 Py3.9 annotations")


# ─────────────────────────────────────────────────────────────────────────────
# C10 — Outreach tracker file integrity
# ─────────────────────────────────────────────────────────────────────────────
def check_c10_outreach():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "outreach.py"), "--dry-run"],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if result.returncode != 0:
        _fail("C10 outreach tracker",
              result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "non-zero exit",
              "Check data/outreach.json has 'platforms', 'recruiters', '_meta' keys")
    else:
        _pass("C10 outreach tracker", result.stdout.strip())


# ─────────────────────────────────────────────────────────────────────────────
# C11 — Market key consistency across per-market config dicts
# A half-added market (e.g. present in run_scout but missing a salary threshold)
# fails silently at runtime — this check catches it statically.
# ─────────────────────────────────────────────────────────────────────────────
def check_c11_markets():
    problems = []
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from common import SALARY_THRESHOLDS
        expected = set(SALARY_THRESHOLDS.keys())

        # score_jobs.py — regex-scan (importing it executes CLI arg parsing)
        sj = (ROOT / "scripts" / "score_jobs.py").read_text()
        m = re.search(r"_STALE_DAYS_BY_MARKET = \{([^}]*)\}", sj)
        stale_keys = set(re.findall(r'"(\w+)"(?=\s*:)', m.group(1))) if m else set()
        if stale_keys != expected:
            problems.append(f"_STALE_DAYS_BY_MARKET keys {sorted(stale_keys)} != {sorted(expected)}")
        addon_keys = set(re.findall(r'=== MARKET CONTEXT: \w+ ===', sj))
        # every non-uk market needs a Pass 2 addon (uk is the base prompt)
        for mkt, label in [("nl", "Netherlands"), ("se", "Sweden"), ("de", "Germany"),
                           ("dk", "Denmark"), ("ie", "Ireland"),
                           ("ae", "United Arab Emirates")]:
            if mkt in expected and f"=== MARKET CONTEXT: {label} ===" not in sj:
                problems.append(f"_MARKET_ADDONS missing '{mkt}' ({label}) block in score_jobs.py")
        # salary-estimate cfg: each market needs a '"<mkt>": {' entry near "currency_char"
        cfg_block = sj[sj.find("_market_cfg = {"):sj.find("_market_cfg = {") + 3000]
        cfg_keys = set(re.findall(r'"(\w{2})": \{', cfg_block))
        if not expected.issubset(cfg_keys):
            problems.append(f"_market_cfg keys {sorted(cfg_keys)} missing {sorted(expected - cfg_keys)}")

        # auto_prep.py — anchor city fallback dict
        ap = (ROOT / "scripts" / "auto_prep.py").read_text()
        m = re.search(r"_CITY_DEFAULTS = \{([^}]*)\}", ap)
        city_keys = set(re.findall(r'"(\w+)"(?=\s*:)', m.group(1))) if m else set()
        if city_keys != expected:
            problems.append(f"auto_prep _CITY_DEFAULTS keys {sorted(city_keys)} != {sorted(expected)}")

        # run_scout.py — CLI validation tuple must accept every market
        rs = (ROOT / "scripts" / "run_scout.py").read_text()
        for mkt in expected:
            if f'"{mkt}"' not in rs:
                problems.append(f"run_scout.py has no reference to market '{mkt}'")
    except Exception as e:
        problems.append(f"check crashed: {e}")

    if problems:
        _fail("C11 market key consistency", "; ".join(problems),
              "Add the missing market keys — see CLAUDE.md §3 market blocks")
    else:
        _pass("C11 market key consistency", f"{len(expected)} markets: {', '.join(sorted(expected))}")


# ─────────────────────────────────────────────────────────────────────────────
# C13 — Outreach ↔ Tracker status sync
# Detects mismatches where outreach.json referrals[] shows a higher status than
# the corresponding job_tracker.json entry — tracker wasn't updated after outreach.
# Catches cases like app_389 (outreach Reached-Out, tracker still Approved).
# ─────────────────────────────────────────────────────────────────────────────
def check_c13_outreach_tracker_sync():
    STATUS_RANK = {
        "Shortlisted": 1, "Review Needed": 1, "Auto-Rejected": 1, "Stale": 1,
        "Approved": 2,
        "Prep Complete": 3,
        "Referral-Planned": 4,
        "Connection-Requested": 5,
        "Reached-Out": 6,
        "Followup": 6,
        "Referred": 7,
        "Stale-Referral": 8,
        "Applied": 9, "Referral": 9,
        "Under Review": 10,
        "Interview Scheduled": 11, "Assessment": 11,
        "Offer Received": 12,
        "Rejected": 13, "Withdrawn": 13, "Duplicate": 13,
    }
    REQUIRED_TRACKER_RANK = {
        "Connection-Requested": STATUS_RANK["Connection-Requested"],
        "Reached-Out":          STATUS_RANK["Reached-Out"],
        "Followup":             STATUS_RANK["Reached-Out"],
        "Referred":             STATUS_RANK["Referred"],
        "Stale-Referral":       STATUS_RANK["Stale-Referral"],
    }

    outreach_path = ROOT / "data" / "outreach.json"
    tracker_path  = ROOT / "data" / "job_tracker.json"
    if not outreach_path.exists() or not tracker_path.exists():
        _fail("C13 Outreach↔Tracker sync", "data/outreach.json or data/job_tracker.json missing")
        return

    outreach = json.loads(outreach_path.read_text())
    tracker  = json.loads(tracker_path.read_text())

    tracker_status = {
        app["id"]: app.get("status", "")
        for app in tracker.get("applications", [])
        if isinstance(app, dict) and app.get("id")
    }

    mismatches = []
    checked = 0
    for ref in outreach.get("referrals", []):
        outreach_st = ref.get("status", "")
        if outreach_st not in REQUIRED_TRACKER_RANK:
            continue
        checked += 1
        app_id = ref.get("app_id")
        if not app_id:
            continue
        tracker_st    = tracker_status.get(app_id, "")
        required_rank = REQUIRED_TRACKER_RANK[outreach_st]
        actual_rank   = STATUS_RANK.get(tracker_st, 0)
        if actual_rank < required_rank:
            mismatches.append(
                f"{app_id} ({ref.get('company','?')} / {ref.get('contact_name','?')}): "
                f"outreach={outreach_st}, tracker={tracker_st or 'MISSING'}"
            )

    if mismatches:
        for m in mismatches:
            _fail("C13 Outreach↔Tracker sync", m,
                  "Advance tracker status to match outreach, then run sheets_sync pull+push")
    else:
        _pass("C13 Outreach↔Tracker sync", f"{checked} referral entries consistent")


# ─────────────────────────────────────────────────────────────────────────────
# C12 — Referral flow consistency
# Ensures the referral statuses are registered everywhere they need to be.
# ─────────────────────────────────────────────────────────────────────────────
def check_c12_referral_flow():
    REFERRAL_STATUSES = {"Referral-Planned", "Connection-Requested", "Reached-Out", "Followup", "Referred", "Stale-Referral"}
    problems = []

    # job_tracker.json valid_statuses must contain all 5
    tracker_path = ROOT / "data" / "job_tracker.json"
    if tracker_path.exists():
        meta = json.loads(tracker_path.read_text()).get("_meta", {})
        valid = set(meta.get("valid_statuses", []))
        missing = REFERRAL_STATUSES - valid
        if missing:
            problems.append(f"_meta.valid_statuses missing: {sorted(missing)}")

    # sheets_sync.py: ARCHIVED_STATUSES must contain Stale-Referral
    sync_src = (ROOT / "scripts" / "sheets_sync.py").read_text()
    if "Stale-Referral" not in sync_src:
        problems.append("sheets_sync.py has no reference to 'Stale-Referral'")
    m = re.search(r'ARCHIVED_STATUSES\s*=\s*\{([^}]+)\}', sync_src)
    if m:
        raw = m.group(1)
        archived = {s.strip().strip('"').strip("'") for s in raw.split(",") if s.strip()}
        if "Stale-Referral" not in archived:
            problems.append("ARCHIVED_STATUSES does not include 'Stale-Referral'")

    # organize_outputs.py: must reference REFERRAL_DIR and REFERRAL_STATUSES
    org_src = (ROOT / "scripts" / "organize_outputs.py").read_text()
    if "REFERRAL_DIR" not in org_src:
        problems.append("organize_outputs.py missing REFERRAL_DIR")
    if "REFERRAL_STATUSES" not in org_src:
        problems.append("organize_outputs.py missing REFERRAL_STATUSES")

    # outreach.json: must have "referrals" key
    outreach_path = ROOT / "data" / "outreach.json"
    if outreach_path.exists():
        outreach = json.loads(outreach_path.read_text())
        if "referrals" not in outreach:
            problems.append("data/outreach.json missing 'referrals' key")
    else:
        problems.append("data/outreach.json not found")

    if problems:
        for p in problems:
            _fail("C12 Referral flow", p, "Referral statuses must be registered in all 4 places")
    else:
        _pass("C12 Referral flow", f"{len(REFERRAL_STATUSES)} statuses (incl. Referral-Planned), Outreach tab wired")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    mode = "QUICK (C1–C6, C9–C13)" if QUICK else "FULL (C1–C13)"
    print(f"\n[check_workflow] Workflow Integrity Check — {mode}\n")

    check_c1_files()
    check_c2_syntax()
    check_c3_tracker()
    check_c4_auto_rejected()
    check_c5_sheets_sync()
    check_c6_settings()
    check_c9_annotations()
    check_c10_outreach()
    check_c11_markets()
    check_c12_referral_flow()
    check_c13_outreach_tracker_sync()

    if not QUICK:
        check_c7_pdf_renderer()
        check_c8_email_tracker()

    total = len(PASSED) + len(FAILED)
    print()
    if not FAILED:
        print(f"  ✓ All {total} checks passed — workflow is intact")
    else:
        print(f"  ✗ {len(FAILED)} of {total} checks FAILED — resolve before closing this task")
    print()
    sys.exit(0 if not FAILED else 1)


if __name__ == "__main__":
    main()
