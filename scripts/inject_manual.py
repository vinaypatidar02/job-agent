#!/usr/bin/env python3
"""
inject_manual.py — Inject manually-sourced jobs into the raw scrape output pipeline
=====================================================================================
Reads data/manual_jobs_input.json, stamps market and _source fields,
and appends new jobs to data/pipeline/raw_scrape_output.json (deduped by job_url).

After running this script, re-run enrich_jobs.py and score_jobs.py.
Jobs already in job_tracker.json will be deduped by score_jobs.py's
_EXISTING_POOL check — only the manual jobs not yet in the tracker will
be scored with Claude API calls.

Usage:
  python3 scripts/inject_manual.py                    # inject all manual jobs
  python3 scripts/inject_manual.py --dry-run          # show what would be injected
"""

import json, re, sys
from pathlib import Path

ROOT          = Path(__file__).parent.parent
MANUAL_PATH   = ROOT / "data" / "manual_jobs_input.json"
RAW_PATH      = ROOT / "data" / "pipeline" / "raw_scrape_output.json"

DRY_RUN = "--dry-run" in sys.argv

# ── Market derivation from location string ────────────────────────────────────

_NL_SIGNALS = {"netherlands", "amsterdam", "rotterdam", "den haag", "the hague", "utrecht"}
_SE_SIGNALS = {"sweden", "stockholm", "gothenburg", "göteborg", "malmo", "malmö"}
_DE_SIGNALS = {
    "germany", "deutschland", "berlin", "munich", "münchen",
    "frankfurt", "hamburg", "düsseldorf", "cologne", "köln",
}
_DK_SIGNALS = {"denmark", "danmark", "copenhagen", "københavn", "aarhus", "århus"}
_IE_SIGNALS = {"ireland", "dublin", "cork", "galway", "limerick"}
# Northern Ireland is UK — checked before IE signals ("ireland" is a substring)
_NI_SIGNALS = {"northern ireland", "belfast", "derry", "londonderry"}

def _derive_market(location: str) -> str:
    loc = (location or "").lower()
    if any(s in loc for s in _NL_SIGNALS):
        return "nl"
    if any(s in loc for s in _SE_SIGNALS):
        return "se"
    if any(s in loc for s in _DE_SIGNALS):
        return "de"
    if any(s in loc for s in _DK_SIGNALS):
        return "dk"
    if any(s in loc for s in _NI_SIGNALS):
        return "uk"
    if any(s in loc for s in _IE_SIGNALS):
        return "ie"
    return "uk"


# ── Load inputs ───────────────────────────────────────────────────────────────

if not MANUAL_PATH.exists():
    print(f"[inject] No manual jobs file found at {MANUAL_PATH} — nothing to inject.")
    sys.exit(0)

_raw = MANUAL_PATH.read_text()
_cleaned = re.sub(r'(?m)^\s*//[^\n]*\n?', '', _raw)
manual_jobs = json.loads(_cleaned)
if not manual_jobs:
    print("[inject] manual_jobs_input.json is empty — nothing to inject.")
    sys.exit(0)

print(f"[inject] Loaded {len(manual_jobs)} manual job(s) from {MANUAL_PATH.name}")

# ── Load existing raw output (if present) ────────────────────────────────────

existing_jobs = []
if RAW_PATH.exists():
    existing_jobs = json.loads(RAW_PATH.read_text())
    print(f"[inject] Existing raw_scrape_output.json: {len(existing_jobs)} job(s)")
else:
    print(f"[inject] raw_scrape_output.json not found — will create from manual jobs only")

existing_urls = {
    (j.get("job_url") or j.get("url") or "").strip()
    for j in existing_jobs
    if j.get("job_url") or j.get("url")
}


sys.path.insert(0, str(Path(__file__).parent))
from common import (
    extract_job_id_from_url as _job_id_from_url,
    compute_role_type as _compute_role_type,
    ROLE_TYPE_ENUM as _ROLE_TYPE_ENUM,
)


# Priority dedup key: (job_id, market) — URL tracking params make URL match unreliable
existing_job_id_market = set()
for j in existing_jobs:
    _jid = str(j.get("job_id") or "").strip() or _job_id_from_url(
        (j.get("job_url") or j.get("url") or "").strip())
    if _jid:
        existing_job_id_market.add((_jid, (j.get("market") or "uk").lower()))

# ── Prepare manual jobs for injection ────────────────────────────────────────

to_inject = []
skipped   = []

for job in manual_jobs:
    url = (job.get("jd_url") or job.get("job_url") or "").strip()
    market = (job.get("market") or _derive_market(job.get("location", ""))).lower()
    job_id = str(job.get("job_id") or "").strip() or _job_id_from_url(url)
    if job_id and (job_id, market) in existing_job_id_market:
        skipped.append(job.get("job_title", url) + " @ " + job.get("company_name", "?"))
        continue
    if url and url in existing_urls:
        skipped.append(job.get("job_title", url) + " @ " + job.get("company_name", "?"))
        continue

    # Guard: skip entries without a description — inject_manual_jobs skill auto-fetches these
    if not (job.get("description") or "").strip():
        print(f"  [SKIP] {job.get('job_title', url)}: no description — "
              f"run 'inject manual jobs' skill to auto-fetch from browser")
        continue

    # Normalize to pipeline-compatible dict (field names already match)
    _is_contract   = bool(job.get("is_contract", False))
    _is_remote     = bool(job.get("is_remote_only", False))
    # role_type: use explicit value if valid, else auto-derive from booleans
    _rt_explicit = (job.get("role_type") or "").strip()
    if _rt_explicit and _rt_explicit not in _ROLE_TYPE_ENUM:
        print(f"  [inject] WARNING: invalid role_type '{_rt_explicit}' for "
              f"{job.get('job_title')} — auto-deriving from is_contract/is_remote_only")
        _rt_explicit = ""
    _role_type = _rt_explicit or _compute_role_type(_is_contract, _is_remote)
    injected = {
        "job_title":    job.get("job_title", ""),
        "company_name": job.get("company_name", ""),
        "location":     job.get("location", ""),
        "salary":       job.get("salary", "Not stated"),
        "job_type":     job.get("job_type", "Full-time"),
        "posted_date":  job.get("posted_date", ""),
        "job_url":      url,
        "job_id":       job_id,
        "description":  job.get("description", ""),
        "_source":      "manual_inject",
        "market":       market,
        "is_contract":  _is_contract,
        "is_remote_only": _is_remote,
        "role_type":    _role_type,
        "eor_viability": job.get("eor_viability"),  # optional hint; score_jobs.py may override
    }
    to_inject.append(injected)
    # prevent intra-batch duplicates
    if job_id:
        existing_job_id_market.add((job_id, market))
    existing_urls.add(url)

# ── Summary ───────────────────────────────────────────────────────────────────

print(f"\n[inject] To inject: {len(to_inject)}")
for j in to_inject:
    mkt = j["market"].upper()
    print(f"  [{mkt}] {j['job_title']} @ {j['company_name']}  ({j['location']})")

if skipped:
    print(f"\n[inject] Already in raw output (skipped): {len(skipped)}")
    for s in skipped:
        print(f"  - {s}")

if not to_inject:
    print("\n[inject] Nothing new to inject — raw_scrape_output.json unchanged.")
    sys.exit(0)

if DRY_RUN:
    print("\n[inject] --dry-run: not writing. Re-run without --dry-run to apply.")
    sys.exit(0)

# ── Write merged output ───────────────────────────────────────────────────────

merged = existing_jobs + to_inject
RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
RAW_PATH.write_text(json.dumps(merged, indent=2, ensure_ascii=False))

print(f"\n[inject] Wrote {len(merged)} total jobs to {RAW_PATH}")
print(f"[inject] ({len(existing_jobs)} scraped + {len(to_inject)} injected manual)")
print(f"\n[inject] Next steps:")
print(f"  python3 scripts/enrich_jobs.py")
print(f"  python3 scripts/score_jobs.py")
print(f"  python3 scripts/write_tracker.py && python3 scripts/sheets_sync.py pull --tabs apps,archive && python3 scripts/sheets_sync.py push --tabs apps,archive")
