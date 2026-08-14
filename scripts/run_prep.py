from __future__ import annotations
"""
run_prep.py — Master orchestration script for application prep.

Enforces parallel execution at the Python level (ThreadPoolExecutor) so prep
is always fast regardless of how Claude happens to call it. Claude calls this
script once with all job IDs — the script handles all phases.

Usage:
    python3 scripts/run_prep.py --keys app_7468,app_7469,...
    python3 scripts/run_prep.py --keys app_7468 --dry-run     (plan only, no API calls)
    python3 scripts/run_prep.py --keys app_7468 --skip-git    (skip git commit step)

Phases:
  1. Parallel: fetch_jd + auto_prep + eval_prep per job  (ThreadPoolExecutor, 6 workers)
  2. Sequential: generate_summaries.py --keys all --force  (batch API, Haiku)
  3. Sequential: generate_covers.py --keys all             (batch API, Sonnet + prompt cache)
  4a. Sequential: finalize_resumes.py --keys all           (mechanical, no LLM)
  4b. Parallel: validate_prep + render resume + render cover + write meta.json
  5. Sequential: batch_tracker_update + sheets_sync push + git commit
"""
import json, sys, os, re, argparse, subprocess, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent
PREP_TMP = ROOT / "data" / "prep_tmp"
READY_DIR = ROOT / "outputs" / "applications" / "ready"
TRACKER_PATH = ROOT / "data" / "job_tracker.json"

PYTHON = sys.executable

def _candidate_name_slug() -> str:
    """Load candidate name from profile and return 'FirstName_LastName' slug for filenames."""
    profile_path = ROOT / "data" / "content" / "candidate_profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        name = profile.get("contact", {}).get("name", "Candidate")
        parts = name.strip().split()
        return "_".join(parts) if parts else "Candidate"
    except Exception:
        return "Candidate"

def _cv_filename() -> str:
    return f"{_candidate_name_slug()}_CV.pdf"

def _cover_filename() -> str:
    return f"{_candidate_name_slug()}_CoverLetter.pdf"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: list[str], desc: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess. Print stderr on failure."""
    result = subprocess.run(cmd, capture_output=capture, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n[ERROR] {desc} failed (exit {result.returncode})")
        if capture and result.stderr:
            for line in result.stderr.strip().splitlines()[-8:]:
                print(f"  {line}")
    return result


def _load_tracker_jobs(target_keys: list[str]) -> dict[str, dict]:
    """Load job metadata from tracker for the target keys."""
    if not TRACKER_PATH.exists():
        print(f"ERROR: {TRACKER_PATH} not found", file=sys.stderr)
        sys.exit(1)
    tracker = json.loads(TRACKER_PATH.read_text())
    return {
        app["id"]: app
        for app in tracker.get("applications", [])
        if app.get("id") in target_keys
    }


def _slugify(s: str) -> str:
    """Convert a string to a safe folder name component."""
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "", s)
    return s[:30]


def _make_output_folder(job: dict) -> Path:
    company_slug = _slugify(job.get("company", "Unknown"))
    role_slug    = _slugify(job.get("role", "Role"))[:25]
    date_str     = datetime.date.today().strftime("%Y%m%d")
    folder = READY_DIR / f"{company_slug}_{role_slug}_{date_str}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1 — Per-job: fetch_jd + auto_prep + eval_prep (parallel)
# ─────────────────────────────────────────────────────────────────────────────

def _phase1_one_job(key: str, job: dict) -> tuple[str, bool, list[str]]:
    """Run fetch_jd → auto_prep → eval_prep for one job. Returns (key, success, warns)."""
    warns: list[str] = []
    jd_file = PREP_TMP / f"jd_{key}.txt"
    auto_resume_file = PREP_TMP / f"auto_resume_{key}.json"
    auto_cover_file  = PREP_TMP / f"auto_cover_{key}.json"

    company = job.get("company", "")
    role    = job.get("role", "")
    jd_url  = job.get("jd_url", "")

    # ── Step 1a: Fetch JD ─────────────────────────────────────────────────────
    if not jd_file.exists() or jd_file.stat().st_size < 50:
        result = subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "fetch_jd.py"),
             "--job_id", key,
             "--jd_url", jd_url or "",
             "--company", company,
             "--role", role],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        jd_text = ""
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    jd_text = data.get("description") or ""
                    break
                except json.JSONDecodeError:
                    pass

        if jd_text and len(jd_text) > 50:
            jd_file.write_text(jd_text, encoding="utf-8")
            print(f"  {key}: JD fetched ({len(jd_text)} chars)")
        else:
            warns.append(f"[WARN]  {key}: JD not fetched — auto_prep will use tracker metadata only")
            # Write minimal placeholder so auto_prep.py has a file to open
            jd_file.write_text(
                f"Company: {company}\nRole: {role}\nURL: {jd_url}\n"
                "(JD text unavailable — scored from tracker metadata)",
                encoding="utf-8"
            )

    # ── Step 1b: auto_prep ────────────────────────────────────────────────────
    if not auto_resume_file.exists() or not auto_cover_file.exists():
        result = _run(
            [PYTHON, str(ROOT / "scripts" / "auto_prep.py"),
             "--job_id", key,
             "--jd_file", str(jd_file),
             "--company", company],
            desc=f"{key} auto_prep"
        )
        if result.returncode != 0:
            return key, False, warns + [f"[FAIL] {key}: auto_prep.py failed"]

    # ── Step 1c: eval_prep ────────────────────────────────────────────────────
    result = subprocess.run(
        [PYTHON, str(ROOT / "scripts" / "eval_prep.py"),
         "--resume", str(auto_resume_file),
         "--cover",  str(auto_cover_file),
         "--jd",     str(jd_file)],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if result.returncode != 0:
        # Attempt ephemeral fixes (bullet reordering, non-breaking tweaks)
        result2 = subprocess.run(
            [PYTHON, str(ROOT / "scripts" / "eval_prep.py"),
             "--resume", str(auto_resume_file),
             "--cover",  str(auto_cover_file),
             "--jd",     str(jd_file),
             "--apply-ephemeral"],
            capture_output=True, text=True, cwd=str(ROOT)
        )
        if result2.returncode != 0:
            warns.append(f"[WARN]  {key}: eval_prep has unfixed issues — review before submitting")
    else:
        print(f"  {key}: eval_prep passed")

    return key, True, warns


def _run_phase1_parallel(keys: list[str], jobs: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Run Phase 1 in parallel. Returns (ok_keys, failed_keys)."""
    print(f"\n[Phase 1] Fetch JD + auto_prep + eval_prep — {len(keys)} jobs in parallel")
    ok_keys: list[str] = []
    failed_keys: list[str] = []
    all_warns: list[str] = []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_phase1_one_job, k, jobs.get(k, {})): k for k in keys}
        for future in as_completed(futures):
            key, ok, warns = future.result()
            all_warns.extend(warns)
            if ok:
                ok_keys.append(key)
            else:
                failed_keys.append(key)

    for w in all_warns:
        print(w)
    return ok_keys, failed_keys


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4b — Per-job: validate + render + meta.json (parallel)
# ─────────────────────────────────────────────────────────────────────────────

def _phase4b_one_job(key: str, job: dict) -> tuple[str, bool, str | None, list[str]]:
    """Validate, render PDFs, write meta.json. Returns (key, success, folder_str, warns)."""
    warns: list[str] = []
    final_resume_file = PREP_TMP / f"final_resume_{key}.json"
    final_cover_file  = PREP_TMP / f"final_cover_{key}.json"
    jd_file           = PREP_TMP / f"jd_{key}.txt"

    company = job.get("company", "Unknown")
    role    = job.get("role", "Role")

    if not final_resume_file.exists():
        return key, False, None, [f"[FAIL] {key}: final_resume not found"]
    if not final_cover_file.exists():
        return key, False, None, [f"[FAIL] {key}: final_cover not found"]

    # ── validate_prep ─────────────────────────────────────────────────────────
    result = subprocess.run(
        [PYTHON, str(ROOT / "scripts" / "validate_prep.py"),
         "--resume", str(final_resume_file),
         "--cover",  str(final_cover_file),
         "--jd",     str(jd_file) if jd_file.exists() else "",
         "--company", company,
         "--role", role],
        capture_output=True, text=True, cwd=str(ROOT)
    )
    if result.returncode != 0:
        # Extract FAIL lines for the summary
        for line in (result.stdout + result.stderr).splitlines():
            if "FAIL" in line or "ERROR" in line:
                warns.append(f"[FAIL]  {key}: validate_prep: {line.strip()}")
        return key, False, None, warns

    # ── Build output folder ────────────────────────────────────────────────────
    folder = _make_output_folder(job)
    cv_path    = folder / _cv_filename()
    cover_path = folder / _cover_filename()

    # ── Render resume PDF ─────────────────────────────────────────────────────
    result = _run(
        [PYTHON, str(ROOT / "scripts" / "pdf_renderer.py"),
         "resume", str(final_resume_file), str(cv_path)],
        desc=f"{key} resume PDF"
    )
    if result.returncode != 0:
        return key, False, None, warns + [f"[FAIL] {key}: resume PDF render failed"]

    # ── Render cover PDF ──────────────────────────────────────────────────────
    result = _run(
        [PYTHON, str(ROOT / "scripts" / "pdf_renderer.py"),
         "cover", str(final_cover_file), str(cover_path)],
        desc=f"{key} cover PDF"
    )
    if result.returncode != 0:
        return key, False, None, warns + [f"[FAIL] {key}: cover PDF render failed"]

    # ── Write meta.json ───────────────────────────────────────────────────────
    meta = {
        "company":          company,
        "role":             role,
        "job_id":           key,
        "jd_url":           job.get("jd_url", ""),
        "career_page_url":  job.get("career_page_url", ""),
        "ats_type":         job.get("ats_type", ""),
        "fit_score":        job.get("fit_score"),
        "resume_variant":   _get_domain(key),
        "prep_date":        datetime.date.today().isoformat(),
        "notes":            job.get("notes"),
    }
    is_hackajob = (
        "hackajob" in (job.get("career_page_url") or "").lower()
        or job.get("ats_type") == "hackajob_passive"
    )
    if is_hackajob:
        meta["is_hackajob_passive"] = True

    (folder / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"  {key}: PDFs + meta.json → {folder.name}/")

    return key, True, str(folder), warns


def _get_domain(key: str) -> str:
    """Read domain from auto_resume _auto_prep_meta (may have been removed by finalize_resumes)."""
    # Try auto_resume first (still has _auto_prep_meta)
    auto_file = PREP_TMP / f"auto_resume_{key}.json"
    if auto_file.exists():
        try:
            d = json.loads(auto_file.read_text())
            meta = d.get("_auto_prep_meta", {})
            if meta.get("domain"):
                return meta["domain"]
        except Exception:
            pass
    return "general"


def _run_phase4b_parallel(
    keys: list[str], jobs: dict[str, dict]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Returns ([(key, folder_path), ...], failed_keys)."""
    print(f"\n[Phase 4b] Validate + render PDFs + meta.json — {len(keys)} jobs in parallel")
    ok_with_folders: list[tuple[str, str]] = []
    failed_keys: list[str] = []
    all_warns: list[str] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_phase4b_one_job, k, jobs.get(k, {})): k for k in keys}
        for future in as_completed(futures):
            key, ok, folder, warns = future.result()
            all_warns.extend(warns)
            if ok and folder:
                ok_with_folders.append((key, folder))
            else:
                failed_keys.append(key)

    for w in all_warns:
        print(w)
    return ok_with_folders, failed_keys


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Master application prep orchestrator")
    parser.add_argument("--keys", required=True, help="Comma-separated list of app IDs")
    parser.add_argument("--dry-run", action="store_true", help="Print plan, no API calls")
    parser.add_argument("--skip-git", action="store_true", help="Skip git commit step")
    args = parser.parse_args()

    target_keys = [k.strip() for k in args.keys.split(",") if k.strip()]
    if not target_keys:
        print("ERROR: --keys is empty"); sys.exit(1)

    PREP_TMP.mkdir(parents=True, exist_ok=True)
    READY_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f" run_prep.py — {len(target_keys)} jobs")
    print(f" Keys: {', '.join(target_keys)}")
    print(f"{'='*60}")

    # Load tracker metadata once
    jobs = _load_tracker_jobs(target_keys)
    missing = [k for k in target_keys if k not in jobs]
    if missing:
        print(f"[WARN] These keys were not found in tracker: {', '.join(missing)}")

    if args.dry_run:
        print("\n[DRY RUN] Phase plan:")
        for k in target_keys:
            j = jobs.get(k, {})
            print(f"  {k}: {j.get('company','?')} — {j.get('role','?')}")
        print("\nNo API calls made. Remove --dry-run to execute.")
        return

    # ── Phase 1 ───────────────────────────────────────────────────────────────
    p1_keys = [k for k in target_keys if k in jobs]
    p1_ok, p1_failed = _run_phase1_parallel(p1_keys, jobs)
    if p1_failed:
        print(f"[ERROR] Phase 1 failed for: {', '.join(p1_failed)} — aborting those jobs")

    if not p1_ok:
        print("ERROR: All jobs failed Phase 1 — aborting"); sys.exit(1)

    keys_csv = ",".join(p1_ok)

    # ── Phase 2 — Batch summaries ─────────────────────────────────────────────
    print(f"\n[Phase 2] Batch summaries — {len(p1_ok)} jobs")
    r2 = _run(
        [PYTHON, str(ROOT / "scripts" / "generate_summaries.py"), "--keys", keys_csv, "--force"],
        desc="generate_summaries"
    )
    if r2.returncode != 0:
        print("ERROR: generate_summaries.py failed — cannot proceed"); sys.exit(1)
    if r2.stdout:
        print(r2.stdout.strip())

    # ── Phase 3 — Batch cover letters ─────────────────────────────────────────
    print(f"\n[Phase 3] Batch cover letters (Sonnet + prompt cache) — {len(p1_ok)} jobs")
    r3 = _run(
        [PYTHON, str(ROOT / "scripts" / "generate_covers.py"), "--keys", keys_csv],
        desc="generate_covers"
    )
    if r3.returncode != 0:
        print("ERROR: generate_covers.py failed — cannot proceed"); sys.exit(1)
    if r3.stdout:
        print(r3.stdout.strip())

    # ── Phase 4a — Finalize resumes ───────────────────────────────────────────
    print(f"\n[Phase 4a] Finalize resumes (mechanical) — {len(p1_ok)} jobs")
    r4a = _run(
        [PYTHON, str(ROOT / "scripts" / "finalize_resumes.py"), "--keys", keys_csv],
        desc="finalize_resumes"
    )
    if r4a.returncode != 0:
        print("ERROR: finalize_resumes.py failed"); sys.exit(1)
    if r4a.stdout:
        print(r4a.stdout.strip())

    # ── Phase 4b — Parallel validate + render + meta ──────────────────────────
    p4b_ok_folders, p4b_failed = _run_phase4b_parallel(p1_ok, jobs)
    if p4b_failed:
        print(f"[ERROR] Phase 4b failed for: {', '.join(p4b_failed)}")

    if not p4b_ok_folders:
        print("ERROR: All jobs failed Phase 4b — nothing to commit"); sys.exit(1)

    # ── Phase 5 — Atomic tracker update + sheets sync + git ──────────────────
    print(f"\n[Phase 5] Tracker update + sheets sync + git commit")
    today_str = datetime.date.today().isoformat()

    # Build tracker_updates.json
    updates = []
    for key, folder in p4b_ok_folders:
        folder_path = Path(folder)
        updates.append({
            "id":                key,
            "status":            "Prep Complete",
            "resume_path":       str(folder_path / _cv_filename()),
            "cover_letter_path": str(folder_path / _cover_filename()),
            "date":              today_str,
        })

    updates_file = PREP_TMP / "tracker_updates.json"
    updates_file.write_text(json.dumps({"updates": updates}, indent=2))

    r5a = _run(
        [PYTHON, str(ROOT / "scripts" / "batch_tracker_update.py"),
         "--updates", str(updates_file)],
        desc="batch_tracker_update"
    )
    if r5a.returncode != 0:
        print("ERROR: batch_tracker_update.py failed"); sys.exit(1)
    if r5a.stdout:
        print(r5a.stdout.strip())

    # sheets_sync pull first, then push
    print("  sheets_sync pull...")
    r_pull = _run(
        [PYTHON, str(ROOT / "scripts" / "sheets_sync.py"), "pull", "--tabs", "apps,archive"],
        desc="sheets_sync pull"
    )
    if r_pull.returncode != 0:
        print("[WARN] sheets_sync pull failed — push skipped (check Sheet manually)")
    else:
        print("  sheets_sync push...")
        r_push = _run(
            [PYTHON, str(ROOT / "scripts" / "sheets_sync.py"), "push", "--tabs", "apps,archive"],
            desc="sheets_sync push"
        )
        if r_push.returncode != 0:
            print("[WARN] sheets_sync push failed — check Sheet manually")

    # Git commit
    if not args.skip_git:
        commit_msg = f"local: prep {today_str} ({len(p4b_ok_folders)} jobs)"
        subprocess.run(["git", "add", "data/job_tracker.json",
                        "outputs/applications/ready/"],
                       cwd=str(ROOT), capture_output=True)
        r_git = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(ROOT), capture_output=True, text=True
        )
        if r_git.returncode == 0:
            print(f"  git commit: {commit_msg}")
        else:
            print("[WARN] git commit failed (nothing staged?)")

    # ── Final summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f" Application Prep — {today_str}")
    print(f"{'='*60}")
    print(f" Processed:  {len(p4b_ok_folders)} jobs")
    if p1_failed or p4b_failed:
        all_failed = list(set(p1_failed + p4b_failed))
        print(f" Failed:     {len(all_failed)} jobs ({', '.join(all_failed)})")
    print(f" PDFs in:    outputs/applications/ready/")
    print(f"{'='*60}")

    if p1_failed or p4b_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
