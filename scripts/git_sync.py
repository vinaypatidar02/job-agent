"""
git_sync.py — shared helper for committing and pushing pipeline outputs to git.

Usage:
    from git_sync import commit_and_push
    commit_and_push("scout", ["data/job_tracker.json", "data/monitoring/"])
"""
import subprocess
import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent


def commit_and_push(label: str, files: list[str]) -> bool:
    """
    Stage `files`, commit with a standard message, and push.

    label   — short tag used in the commit message, e.g. "scout", "email", "pull"
    files   — list of paths relative to ROOT (files or directories)
    Returns True if anything was committed, False if nothing changed.
    Non-fatal: prints a warning on failure instead of raising.
    """
    today = datetime.date.today().isoformat()

    result = subprocess.run(
        ["git", "add"] + files,
        cwd=ROOT, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[git_sync] ⚠ git add failed: {result.stderr.strip()}")
        return False

    # Stage tracked-but-modified files (e.g. scripts, skills)
    # -u only touches files already known to git — never picks up .env or secrets
    subprocess.run(["git", "add", "-u"], cwd=ROOT, capture_output=True, text=True)

    # Stage new/untracked batch state files by explicit pattern — avoids accidentally
    # committing future debug dumps or large intermediates not yet in .gitignore
    batch_files = sorted((ROOT / "data" / "pipeline").glob("batch_state*.json"))
    if batch_files:
        subprocess.run(
            ["git", "add"] + [str(f) for f in batch_files],
            cwd=ROOT, capture_output=True, text=True
        )

    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=ROOT
    )
    if diff.returncode == 0:
        print(f"[git_sync] Nothing to commit — all files already up to date.")
        return False

    commit = subprocess.run(
        ["git", "commit", "-m", f"{label}: {today}"],
        cwd=ROOT, capture_output=True, text=True
    )
    if commit.returncode != 0:
        print(f"[git_sync] ⚠ git commit failed: {commit.stderr.strip()}")
        return False

    push = subprocess.run(
        ["git", "push"], cwd=ROOT, capture_output=True, text=True
    )
    if push.returncode != 0:
        print(f"[git_sync] ⚠ git push failed: {push.stderr.strip()}")
        print(f"[git_sync]   Run 'git push' manually to sync.")
        return False

    print(f"[git_sync] ✓ Committed and pushed ({label}: {today})")
    return True
