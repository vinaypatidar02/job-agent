#!/usr/bin/env python3
"""
apify_cache.py — Cache layer for Apify LinkedIn scrape results
==============================================================
Actor: curious_coder/linkedin-jobs-scraper ($1.00 / 1,000 results)
Input: pre-filtered LinkedIn search URL (experience, job type, work mode,
       time filter all baked in — no keyword/location params needed)

Cache key: MD5(url)[:16] + today's date — same URL same day = free re-run.
Time filter (f_TPR=r86400 = past 24h) is embedded in the URL itself.

Default max jobs: 100 per URL. Override with --max-jobs N in run_scout.py.

CLI:
  python3 scripts/apify_cache.py status      ← show cache contents
  python3 scripts/apify_cache.py clear       ← delete all cache files
  python3 scripts/apify_cache.py clear --old ← delete only stale entries
"""

import json, sys, re, time, hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from urllib import request, error

ROOT          = Path(__file__).parent.parent
CACHE_DIR     = ROOT / "data" / "apify_cache"
MONITOR_DIR   = ROOT / "data" / "monitoring"
ENV_FILE      = ROOT / ".env"

CACHE_TTL        = 24   # hours — same URL same day hits cache
DEFAULT_MAX_JOBS = 100  # per URL; override via --max-jobs N in run_scout.py

ACTOR    = "curious_coder~linkedin-jobs-scraper"
API_BASE = "https://api.apify.com/v2"

# ATS domains for apply_url_hint extraction
ATS_DOMAINS = (
    "greenhouse.io", "lever.co", "workday.com", "ashbyhq.com",
    "smartrecruiters.com", "icims.com", "taleo.net", "bamboohr.com",
    "jobvite.com", "recruitee.com", "personio.com", "teamtailor.com",
    "hackajob.com",
)

# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — Title Blocklist
# Titles containing any of these strings are rejected before Pass 1 scoring.
# Use for titles that are 100% certain to be irrelevant to YOUR role.
# This saves Pass 2 Claude API cost — only block if you are sure.
# EXAMPLES (analytics): "data engineer", "data scientist", "data architect", "governance"
# EXAMPLES (software):  "qa engineer", "scrum master", "project manager", "business analyst"
# EXAMPLES (finance):   "tax specialist", "payroll", "accounts payable", "bookkeeper"
# Add your own below. Lower-case strings, substring match on title.
# ═══════════════════════════════════════════════════════════════
_TITLE_BLOCKLIST: set[str] = {
    # Add titles that are definitively NOT your target roles.
    # Example entries (analytics defaults — replace with your profession's noise):
    "data scientist", "data science",
    "data engineer",
    "database manager", "database administrator",
    "data platform engineer",
    "data architect", "data governance",
    "data architecture",
    "governance",
    "servicenow",
    "dynamics",
    "netsuite",
    "project controls",
    "commercial finance",
    "actuarial",
    "regulatory reporting",
    "vessel",
    "game analyst",
}

def _title_is_blocked(title: str) -> bool:
    t = title.lower()
    return any(bad in t for bad in _TITLE_BLOCKLIST)

# Per-label extra blocklist — applied after global blocklist for specific search keyword labels.
# Use when a particular keyword search attracts noise not blocked globally.
# Space-prefix on values prevents blocking hybrid titles (e.g. " product owner" won't block "Analytics Product Owner").
# EXAMPLE: {"Lead Business Analyst": {" product owner", "scrum master", "salesforce developer"}}
_PER_LABEL_BLOCKLIST: dict[str, set[str]] = {
    # Add per-keyword noise patterns here if specific searches return irrelevant titles.
}

def _title_is_blocked_for_label(title: str, label: str) -> bool:
    extra = _PER_LABEL_BLOCKLIST.get(label, set())
    t = " " + title.lower()  # space-prefix for phrase-boundary matching
    return any(bad in t for bad in extra)

CACHE_DIR.mkdir(parents=True, exist_ok=True)
MONITOR_DIR.mkdir(parents=True, exist_ok=True)

# ── Monitoring — URL health recording ────────────────────────────────────────
def _market_from_label(label: str) -> str:
    if label.startswith("NL "):
        return "nl"
    if label.startswith("SE "):
        return "se"
    if label.startswith("DE "):
        return "de"
    if label.startswith("DK "):
        return "dk"
    if label.startswith("IE "):
        return "ie"
    return "uk"

import threading
_URL_HEALTH_LOCK = threading.Lock()  # url_health.json is read-modify-write; get_batch is parallel

def _record_url_health(label: str, url: str, run_id: str, items: int, usd: float,
                       session_id: str = ""):
    with _URL_HEALTH_LOCK:
        _record_url_health_unlocked(label, url, run_id, items, usd, session_id)

def _record_url_health_unlocked(label: str, url: str, run_id: str, items: int, usd: float,
                                session_id: str = ""):
    path = MONITOR_DIR / "url_health.json"
    records = []
    if path.exists():
        try:
            records = json.loads(path.read_text())
        except Exception:
            pass
    records.append({
        "date":       date.today().isoformat(),
        "keyword":    label,
        "market":     _market_from_label(label),
        "run_id":     run_id,
        "session_id": session_id,
        "items":      items,
        "usd":        round(usd, 4),
    })
    path.write_text(json.dumps(records, indent=2))

# ── Auth ──────────────────────────────────────────────────────────────────────
def load_token() -> Optional[str]:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None

# ── Cache key: URL hash + today's date ───────────────────────────────────────
def _url_cache_key(label: str, url: str) -> str:
    url_hash = hashlib.md5(url.encode()).hexdigest()[:16]
    today    = date.today().isoformat()
    return f"{url_hash}_{today}"

def _cache_path(label: str, url: str) -> Path:
    return CACHE_DIR / f"{_url_cache_key(label, url)}.json"

# ── Cache read / write ────────────────────────────────────────────────────────
def read_cache(label: str, url: str) -> Optional[list]:
    path = _cache_path(label, url)
    if not path.exists():
        return None
    try:
        cached    = json.loads(path.read_text())
        fetched   = datetime.fromisoformat(cached["fetched_at"])
        if fetched.date() < datetime.now().date():
            print(f"  [cache] STALE  {label} (from {fetched.date()}) — re-scraping")
            return None
        print(f"  [cache] HIT    {label} (fetched {fetched.strftime('%H:%M')}, {cached.get('count',0)} jobs)")
        return cached["results"]
    except Exception:
        return None

def write_cache(label: str, url: str, results: list, max_jobs: int = None):
    path = _cache_path(label, url)
    payload = {
        "label":         label,
        "url":           url,
        "fetched_at":    datetime.now().isoformat(),
        "ttl_hours":     CACHE_TTL,
        "count":         len(results),
        "requested_max": max_jobs,
        "results":       results,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"  [cache] WRITE  {label} → {len(results)} jobs cached")

# ── Field normalization ───────────────────────────────────────────────────────
def _strip_html(html_str: str) -> str:
    return re.sub(r"<[^>]+>", " ", html_str or "").strip()

def _parse_posted_at(raw: str) -> str:
    """Convert curious_coder postedAt ('2 days ago', ISO date, etc.) → YYYY-MM-DD."""
    if not raw:
        return date.today().isoformat()
    raw = raw.strip()
    # Already ISO date
    if re.match(r"\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    # Relative: "3 hours ago", "1 day ago", "2 weeks ago"
    m = re.search(r"(\d+)\s*(hour|day|week|month)", raw.lower())
    if m:
        n, unit = int(m.group(1)), m.group(2)
        delta = {"hour": 0, "day": n, "week": n * 7, "month": n * 30}[unit]
        return (date.today() - timedelta(days=delta)).isoformat()
    return date.today().isoformat()

def _parse_salary(salary_info) -> str:
    """Normalise salaryInfo (list or str) → human-readable string."""
    if not salary_info:
        return ""
    if isinstance(salary_info, list):
        parts = [str(x).strip() for x in salary_info if x]
        result = " – ".join(parts) if parts else ""
    else:
        result = str(salary_info).strip()
    # Sanitize: digitless strings (e.g. "K – K", "$ – $") are malformed — return empty
    if result and not any(c.isdigit() for c in result):
        return ""
    return result

def _normalize(item: dict) -> dict:
    """Map curious_coder output fields → pipeline-standard field names."""
    description_text = (
        item.get("descriptionText")
        or _strip_html(item.get("descriptionHtml", ""))
    )
    apply_url = item.get("applyUrl", "") or ""
    apply_url_hint = apply_url if any(d in apply_url for d in ATS_DOMAINS) else ""

    return {
        "job_url":         item.get("link", ""),
        "job_title":       item.get("title", ""),
        "company_name":    item.get("companyName", ""),
        "location":        item.get("location", ""),
        "description":     description_text,
        "posted_date":     _parse_posted_at(item.get("postedAt", "")),
        "salary":          _parse_salary(item.get("salaryInfo")),
        "job_id":          str(item.get("id", "")),
        "job_type":        item.get("employmentType", ""),
        "work_type":       item.get("workplaceType", ""),
        "seniority_level": item.get("seniorityLevel", ""),
        "apply_url_hint":  apply_url_hint,
        "_source":         "apify",
    }

# ── Apify API call ────────────────────────────────────────────────────────────
def call_apify_url(url: str, max_jobs: int = DEFAULT_MAX_JOBS,
                   token: str = None, meta: dict = None) -> list:
    """
    Call curious_coder/linkedin-jobs-scraper with a pre-filtered LinkedIn URL.
    Polls until run completes, returns normalised list of job dicts.
    Cost: $1.00 / 1,000 results ($0.001/job).
    meta: optional dict populated with run_id/run_usd/items — thread-safe channel
    for URL health recording (function attributes are kept for compat but are
    unreliable when get_batch fetches URLs in parallel).
    """
    if not token:
        token = load_token()
    if not token:
        raise ValueError("APIFY_TOKEN not found in .env")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    def api(method, path, body=None):
        # Retry transient failures with backoff. GETs are idempotent → retry on any
        # network error or 5xx. POSTs (run start) are billed — retry ONLY on
        # connection-level URLError (request never reached Apify), never on a
        # response error, to avoid starting duplicate paid runs.
        endpoint = f"{API_BASE}{path}"
        data = json.dumps(body).encode() if body else None
        last_err = None
        for attempt in range(3):
            if attempt:
                wait = 2 ** attempt  # 2s, 4s
                print(f"  [apify] Transient error, retry {attempt}/2 in {wait}s: {last_err}")
                time.sleep(wait)
            req = request.Request(endpoint, data=data, headers=headers, method=method)
            try:
                with request.urlopen(req, timeout=60) as r:
                    return json.loads(r.read())
            except error.HTTPError as e:
                if method == "GET" and e.code >= 500:
                    last_err = f"HTTP {e.code}"
                    continue
                raise
            except error.URLError as e:
                last_err = e.reason
                continue
        raise RuntimeError(f"Apify API {method} {path} failed after 3 attempts: {last_err}")

    clamped = max(10, max_jobs)  # actor requires count >= 10
    actor_input = {"urls": [url], "count": clamped}  # plain strings, not objects
    print(f"  [apify] Starting run: {ACTOR} (max {clamped} jobs)")

    try:
        run    = api("POST", f"/acts/{ACTOR}/runs", actor_input)
        run_id = run["data"]["id"]
        print(f"  [apify] Run ID: {run_id}")
    except error.HTTPError as e:
        raise RuntimeError(f"Apify run start failed: HTTP {e.code} — {e.read().decode()[:200]}")

    # Poll for completion (max ~8 min)
    for attempt in range(96):
        time.sleep(5)
        try:
            status_resp = api("GET", f"/actor-runs/{run_id}")
            status      = status_resp["data"]["status"]
        except Exception as e:
            print(f"  [apify] Poll error (attempt {attempt+1}): {e}")
            continue
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run {run_id} ended with status: {status}")

    dataset_id  = status_resp["data"]["defaultDatasetId"]
    run_usd     = status_resp["data"].get("usageTotalUsd", 0) or 0
    items_resp  = api("GET", f"/datasets/{dataset_id}/items?format=json&clean=true")
    items = items_resp.get("items", items_resp) if isinstance(items_resp, dict) else items_resp
    print(f"  [apify] Fetched {len(items)} raw items (${run_usd:.4f})")

    normalised = [_normalize(item) for item in items if item.get("link") or item.get("title")]
    print(f"  [apify] Normalised → {len(normalised)} jobs")

    # Record URL health (live calls only — cache hits are excluded)
    # Label is not available here; CachedScraper.get() owns the label.
    # Store metadata on the function object so callers can read it.
    call_apify_url._last_run_id  = run_id
    call_apify_url._last_run_usd = run_usd
    call_apify_url._last_items   = len(items)
    if meta is not None:
        meta.update({"run_id": run_id, "run_usd": run_usd, "items": len(items)})

    # Retry once if 0 results — handles transient LinkedIn/Apify interruptions.
    # Only this URL is retried; other keywords are unaffected.
    if not normalised:
        print(f"  [apify] ⚠  0 results — retrying once (same URL, same count)")
        try:
            run2    = api("POST", f"/acts/{ACTOR}/runs", actor_input)
            run_id2 = run2["data"]["id"]
            print(f"  [apify] Retry run ID: {run_id2}")
        except error.HTTPError as e:
            print(f"  [apify] Retry start failed: HTTP {e.code} — treating as genuine zero")
            return normalised

        status2 = "UNKNOWN"
        status_resp2 = {}
        for attempt in range(96):
            time.sleep(5)
            try:
                status_resp2 = api("GET", f"/actor-runs/{run_id2}")
                status2      = status_resp2["data"]["status"]
            except Exception as e:
                print(f"  [apify] Retry poll error (attempt {attempt+1}): {e}")
                continue
            if status2 in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                break

        if status2 != "SUCCEEDED":
            print(f"  [apify] Retry run ended with status: {status2} — treating as genuine zero")
            return normalised

        dataset_id2 = status_resp2["data"]["defaultDatasetId"]
        items_resp2 = api("GET", f"/datasets/{dataset_id2}/items?format=json&clean=true")
        items2      = items_resp2.get("items", items_resp2) if isinstance(items_resp2, dict) else items_resp2
        print(f"  [apify] Retry fetched {len(items2)} raw items")
        normalised  = [_normalize(i) for i in items2 if i.get("link") or i.get("title")]
        print(f"  [apify] Retry normalised → {len(normalised)} jobs")

    return normalised

# ── CachedScraper — main interface ────────────────────────────────────────────
class CachedScraper:
    """
    URL-based LinkedIn job scraper using curious_coder actor.

    Usage:
        scraper = CachedScraper(token=token)
        results = scraper.get_batch(SEARCHES_APIFY, max_jobs=100)

    SEARCHES_APIFY format: [(label, url), ...]
    """
    def __init__(self, token: str = None):
        self.token = token or load_token()
        self.stats = {"cache_hits": 0, "apify_calls": 0, "total_jobs": 0}
        # Unique ID for this scout invocation — stamps url_health records so
        # monitor_scout can isolate THIS run's cost from earlier same-day runs.
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def get(self, label: str, url: str, max_jobs: int = DEFAULT_MAX_JOBS) -> list:
        cached = read_cache(label, url)
        if cached is not None:
            self.stats["cache_hits"] += 1
            self.stats["total_jobs"] += len(cached)
            return cached
        self.stats["apify_calls"] += 1
        meta: dict = {}
        results = call_apify_url(url, max_jobs, self.token, meta=meta)
        write_cache(label, url, results, max_jobs)
        self.stats["total_jobs"] += len(results)
        # Record URL health for live calls (not cache hits)
        try:
            _record_url_health(
                label,
                url,
                meta.get("run_id", ""),
                meta.get("items", len(results)),
                meta.get("run_usd", len(results) * 0.001),
                session_id=self.session_id,
            )
        except Exception:
            pass  # monitoring is non-critical
        return results

    def get_batch(self, searches: list, max_jobs: int = DEFAULT_MAX_JOBS) -> list:
        """
        Run multiple URL-based searches, deduplicating by job_url.
        searches: [(label, url), ...] 2-tuples  OR
                  [(label, url, per_url_max), ...] 3-tuples (per-URL cap overrides max_jobs)
        max_jobs: fallback cap per URL when 2-tuples are used (default 100)
        """
        # Normalise entries to (label, url, entry_max)
        norm = []
        for entry in searches:
            if len(entry) == 3:
                label, url, entry_max = entry
                entry_max = min(entry_max, max_jobs)  # CLI --max-jobs overrides when lower
            else:
                label, url = entry
                entry_max = max_jobs
            norm.append((label, url, entry_max))

        # Fetch all URLs in parallel — each Apify run polls for minutes, so this
        # cuts scout wall-time ~4×. Results are processed in original order below
        # so dedup stays deterministic. Cache hits return instantly either way.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(norm)))) as pool:
            fetched = list(pool.map(lambda e: self.get(e[0], e[1], e[2]), norm))

        seen_urls = set()
        combined  = []
        blocked   = 0
        for (label, url, entry_max), results in zip(norm, fetched):
            if len(results) >= entry_max:
                print(f"  ⚠  [{label}] Hit cap ({len(results)}/{entry_max}) — some jobs may be unseen")
            for pos, job in enumerate(results, 1):
                job["scrape_position"] = pos
                job["search_keyword"]  = label
            for job in results:
                if (_title_is_blocked(job.get("job_title", ""))
                        or _title_is_blocked_for_label(job.get("job_title", ""), label)):
                    blocked += 1
                    continue
                job_url = job.get("job_url", "")
                if job_url and job_url in seen_urls:
                    continue
                if job_url:
                    seen_urls.add(job_url)
                combined.append(job)

        print(f"\n  [apify] Batch complete:")
        print(f"    Cache hits:   {self.stats['cache_hits']}")
        print(f"    Apify calls:  {self.stats['apify_calls']}")
        print(f"    Title-blocked: {blocked} non-target roles removed")
        print(f"    Total unique: {len(combined)} jobs")
        return combined

    def summary(self) -> dict:
        return self.stats

# ── CLI ───────────────────────────────────────────────────────────────────────
def cli_status():
    files = sorted(CACHE_DIR.glob("*.json"))
    if not files:
        print("\n  Cache is empty.\n")
        return
    print(f"\n  {'File':<45} {'Label':<30} {'Jobs':>5} {'Age':>8} {'Status'}")
    print(f"  {'-'*100}")
    for f in files:
        try:
            d         = json.loads(f.read_text())
            fetched_dt = datetime.fromisoformat(d["fetched_at"])
            age        = (datetime.now() - fetched_dt).total_seconds() / 3600
            status     = "✓ fresh" if fetched_dt.date() >= datetime.now().date() else "✗ stale"
            label      = d.get("label") or d.get("keyword", "?")
            print(f"  {f.name:<45} {label:<30} {d.get('count',0):>5} {age:>6.1f}h {status}")
        except Exception as e:
            print(f"  {f.name:<45} ERROR: {e}")
    print()

def cli_clear(old_only=False):
    files   = list(CACHE_DIR.glob("*.json"))
    removed = 0
    for f in files:
        if old_only:
            try:
                d            = json.loads(f.read_text())
                fetched_date = datetime.fromisoformat(d["fetched_at"]).date()
                if fetched_date >= datetime.now().date():   # today → keep
                    continue
            except Exception:
                pass
        f.unlink()
        removed += 1
    label = "stale" if old_only else "all"
    print(f"\n  Removed {removed} {label} cache files.\n")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "status"
    if mode == "status":
        cli_status()
        print(f"  Actor:       {ACTOR}")
        print(f"  Pricing:     $1.00 / 1,000 results ($0.001/job)")
        print(f"  Default cap: {DEFAULT_MAX_JOBS} jobs/URL\n")
    elif mode == "clear":
        cli_clear(old_only="--old" in sys.argv)
    else:
        print(__doc__)
