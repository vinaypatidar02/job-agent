#!/usr/bin/env python3
"""
run_scout.py — Job Scout Runner
================================
Claude Code calls this script directly. Real CLI arguments — no ambiguity.

Usage:
  python3 scripts/run_scout.py                         # default: Apify, all configured markets
  python3 scripts/run_scout.py --dry-run               # print search list + cost estimate, no API calls
  python3 scripts/run_scout.py --max-jobs 50           # cap Apify per-URL results (default: 100)
  python3 scripts/run_scout.py --yes                   # skip confirmation prompt (for scripted runs)
  python3 scripts/run_scout.py --market uk             # UK market only
  python3 scripts/run_scout.py --market intl           # all non-UK markets
  python3 scripts/run_scout.py --market all            # every configured market
  python3 scripts/run_scout.py --market all --intl-age 7  # one-time: cover 7 days instead of 24h

Actor: curious_coder/linkedin-jobs-scraper ($0.001/job, see apify_cache.py for 24h cache)
  Single-keyword URLs with filter params (f_E=4,5, f_TPR=r86400).
  f_WT and f_JT params are patched at runtime by _open_job_type_filters to include
  remote and contract roles alongside permanent (always-on behaviour).

Cost:
  ~$0.001/job × max_jobs per URL. 8 URLs at 100 jobs = $0.80 max.
  Cache: 24h TTL — re-running same day costs $0.
"""

import sys, json, os, subprocess, time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

LOCK_FILE = ROOT / "data" / "pipeline" / ".scout_lock"

# ═══════════════════════════════════════════════════════════════
# USER CONFIGURATION — LinkedIn Job Search URLs
# ═══════════════════════════════════════════════════════════════
# Replace the placeholder entries below with your own LinkedIn searches.
#
# HOW TO BUILD YOUR SEARCH URL:
#   1. Go to linkedin.com/jobs and search for your target role + location
#   2. Apply filters: Experience Level (Mid-Senior, Director), Date Posted (Past 24h)
#   3. Copy the full URL from your browser — it will contain f_TPR=r86400 and other params
#
# KEY URL PARAMETERS:
#   keywords=YOUR+ROLE   → URL-encoded role title (e.g. "Lead+Software+Engineer")
#   geoId=XXXXXX         → LinkedIn location ID (see geoId reference below)
#   f_TPR=r86400         → Past 24 hours (86400 seconds); use r604800 for 7 days
#   f_E=4%2C5            → Experience level: Mid-Senior(4), Director(5) — keep both
#   f_JT=F               → Job type: Full-time only (patched at runtime to include Contract)
#
# GEOID REFERENCE (copy the matching geoId into your URL):
#   United Kingdom:      101165590
#   Netherlands:         102890719
#   Germany:             101282230
#   Sweden:              105117694
#   Denmark:             104514075
#   Ireland:             104738515
#   UAE:                 104305776
#   United States:       103644278
#   Canada:              101174742
#   Australia:           101452733
#   Singapore:           102454443
#   (Find others: search on linkedin.com/jobs, copy the geoId from the URL)
#
# FORMAT: ("Descriptive Label", "LinkedIn_URL", max_jobs_per_search)
# COST:   $0.001/job × max_jobs = max $0.10 per search at cap 100
#
# 3-TUPLE: (label, linkedin_search_url, per_url_max_jobs)
# ─────────────────────────────────────────────────────────────
# EXAMPLE — UK analytics searches (replace with YOUR role + location):
#   ("Lead Data Analyst UK",
#    "https://www.linkedin.com/jobs/search?keywords=Lead%20Data%20Analyst&location=United%20Kingdom&geoId=101165590&f_TPR=r86400&f_JT=F&f_E=4%2C5",
#    100),
# ─────────────────────────────────────────────────────────────
# Add one tuple per role title + market combination you want to search.
# More specific keywords = fewer but more targeted results.
# Broad keywords (e.g. "Manager") return high volume with more noise — tune to your profession.
# ═══════════════════════════════════════════════════════════════

SEARCHES_APIFY = [
    # ── YOUR MARKET 1 (e.g. United Kingdom) ──────────────────────────────────────
    # Replace these placeholder entries with your actual role + location searches:
    ("YOUR ROLE TITLE 1",
     "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE+HERE&location=YOUR+LOCATION&geoId=YOUR_GEO_ID&f_TPR=r86400&f_JT=F&f_E=4%2C5",
     100),
    ("YOUR ROLE TITLE 2",
     "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE+2+HERE&location=YOUR+LOCATION&geoId=YOUR_GEO_ID&f_TPR=r86400&f_JT=F&f_E=4%2C5",
     100),
    # Add more entries here — each costs max $0.10 at 100 jobs cap
]

DEFAULT_APIFY_MAX_JOBS = 100  # fallback when using 2-tuple searches; per-URL caps above take precedence

# ── Additional market search lists ───────────────────────────────────────────
# Add per-market lists below if you're searching multiple countries.
# Each list follows the same 3-tuple format: (label, linkedin_url, max_jobs)
# Built-in support for markets: uk, nl, se, de, dk, ie, ae (see --market flag)
# Add a new list and wire it into _build_apify_searches() if targeting other markets.

# ── NL — Netherlands ──────────────────────────────────────────────────────────
# geoId 102890719 = Netherlands. Scoring gate: NL_TIER1 in score_jobs.py.
SEARCHES_APIFY_NL = [
    # ("NL Your Role 1",
    #  "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=Netherlands&geoId=102890719&f_TPR=r86400&f_JT=F&f_E=4%2C5",
    #  100),
]

# ── SE — Sweden ───────────────────────────────────────────────────────────────
# geoId 105117694 = Sweden. Scoring gate: SE_TIER1 in score_jobs.py.
# NOTE: SE market uses a brand allowlist (MARKET_BRAND_ALLOWLIST in score_jobs.py).
SEARCHES_APIFY_SE = [
    # ("SE Your Role 1",
    #  "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=Sweden&geoId=105117694&f_TPR=r86400&f_JT=F&f_E=4%2C5",
    #  100),
]

# ── DE — Germany ──────────────────────────────────────────────────────────────
# geoId 101282230 = Germany. Scoring gate: DE_TIER1 in score_jobs.py.
SEARCHES_APIFY_DE = [
    # ("DE Your Role 1",
    #  "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=Germany&geoId=101282230&f_TPR=r86400&f_JT=F&f_E=4%2C5",
    #  100),
]

# ── DK — Denmark ──────────────────────────────────────────────────────────────
# geoId 104514075 = Denmark. Scoring gate: _DK_TIER1 in score_jobs.py.
SEARCHES_APIFY_DK = [
    # ("DK Your Role 1",
    #  "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=Denmark&geoId=104514075&f_TPR=r86400&f_JT=F&f_E=4%2C5",
    #  100),
]

# ── IE — Ireland ──────────────────────────────────────────────────────────────
# geoId 104738515 = Ireland. Scoring gate: _IE_TIER1 in score_jobs.py.
# NOTE: Northern Ireland (Belfast) is UK, not Ireland — score_jobs rejects it in ie gate.
SEARCHES_APIFY_IE = [
    # ("IE Your Role 1",
    #  "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=Ireland&geoId=104738515&f_TPR=r86400&f_JT=F&f_E=4%2C5",
    #  100),
]

# ── AE — United Arab Emirates ─────────────────────────────────────────────────
# geoId 104305776 = UAE. Scoring gate: AE_TIER1 in score_jobs.py.
SEARCHES_APIFY_AE = [
    # ("AE Your Role 1",
    #  "https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&location=United%20Arab%20Emirates&geoId=104305776&f_TPR=r86400&f_JT=F&f_E=4%2C5",
    #  100),
]


# ── Parse arguments ───────────────────────────────────────────────────────────
args              = sys.argv[1:]
yes               = "--yes" in args
dry_run           = "--dry-run" in args
max_jobs          = DEFAULT_APIFY_MAX_JOBS  # per URL; overridden by --max-jobs N
max_jobs_explicit = False
age               = None     # None = use URL default; only used if --intl-age is passed

if "--age" in args:
    idx = args.index("--age")
    try:
        age = int(args[idx + 1])
    except (IndexError, ValueError):
        print("ERROR: --age requires a number, e.g. --age 1")
        sys.exit(1)

intl_age_days = None   # when set, overrides Apify f_TPR for this run only
if "--intl-age" in args:
    idx = args.index("--intl-age")
    try:
        intl_age_days = int(args[idx + 1])
    except (IndexError, ValueError):
        print("ERROR: --intl-age requires a number of days, e.g. --intl-age 7")
        sys.exit(1)

if "--max-jobs" in args:
    idx = args.index("--max-jobs")
    try:
        max_jobs = int(args[idx + 1])
        max_jobs_explicit = True
        if max_jobs < 1 or max_jobs > 300:
            print("ERROR: --max-jobs must be between 1 and 300")
            sys.exit(1)
    except (IndexError, ValueError):
        print("ERROR: --max-jobs requires a number, e.g. --max-jobs 15")
        sys.exit(1)

market = "intl"  # default: NL + DE + DK + IE + AE (add UK to SEARCHES_APIFY and set market=all for UK)
if "--market" in args:
    idx = args.index("--market")
    try:
        market = args[idx + 1]
        if market not in ("uk", "nl", "se", "de", "dk", "ie", "ae", "all", "intl"):
            print(f"ERROR: --market must be uk, nl, se, de, dk, ie, ae, intl, or all (got '{market}')")
            sys.exit(1)
    except IndexError:
        print("ERROR: --market requires a value: uk, nl, se, de, dk, ie, ae, intl, or all")
        sys.exit(1)


# ── --intl-age: patch market-specific Apify URLs to use a longer time window ─
# Only active when --intl-age N is passed (e.g. first run covering 7 days).
# Default URLs use f_TPR=r86400 (24h). This extends the window without editing URLs.
import re as _re_tpr
if intl_age_days:
    _intl_tpr = f"f_TPR=r{intl_age_days * 86400}"
    def _patch_tpr(searches):
        return [(l, _re_tpr.sub(r'f_TPR=r\d+', _intl_tpr, u), m) for l, u, m in searches]
    SEARCHES_APIFY_NL = _patch_tpr(SEARCHES_APIFY_NL)
    SEARCHES_APIFY_SE = _patch_tpr(SEARCHES_APIFY_SE)
    SEARCHES_APIFY_DE = _patch_tpr(SEARCHES_APIFY_DE)
    SEARCHES_APIFY_DK = _patch_tpr(SEARCHES_APIFY_DK)
    SEARCHES_APIFY_IE = _patch_tpr(SEARCHES_APIFY_IE)
    SEARCHES_APIFY_AE = _patch_tpr(SEARCHES_APIFY_AE)


# Always-on: remove work-type gate (f_WT) and broaden job type to include contract (f_JT=F → F,C).
# Lets remote-only and fixed-term contract roles reach the pipeline alongside permanent roles.
import re as _re_jt
def _open_job_type_filters(searches):
    """Strip f_WT param and add contract type (C) to f_JT for every LinkedIn search URL."""
    def _fix(u):
        u = _re_jt.sub(r'&f_WT=[^&]*', '', u)         # remove work-type filter
        u = _re_jt.sub(r'(f_JT=F)(?=&|$)', r'\1%2CC', u)  # full-time + contract
        return u
    return [(lbl, _fix(url), mx) for lbl, url, mx in searches]

SEARCHES_APIFY    = _open_job_type_filters(SEARCHES_APIFY)
SEARCHES_APIFY_NL = _open_job_type_filters(SEARCHES_APIFY_NL)
SEARCHES_APIFY_SE = _open_job_type_filters(SEARCHES_APIFY_SE)
SEARCHES_APIFY_DE = _open_job_type_filters(SEARCHES_APIFY_DE)
SEARCHES_APIFY_DK = _open_job_type_filters(SEARCHES_APIFY_DK)
SEARCHES_APIFY_IE = _open_job_type_filters(SEARCHES_APIFY_IE)
SEARCHES_APIFY_AE = _open_job_type_filters(SEARCHES_APIFY_AE)

# ── Load searches from config file (overrides hardcoded lists above) ──────────
def _load_searches_from_config() -> dict[str, list]:
    """Load search entries from data/content/search_config.json.
    Returns dict mapping market_code → list of (label, url, max_jobs) tuples.
    When non-empty, overrides the hardcoded SEARCHES_APIFY* lists above.
    """
    _GEO_IDS = {
        "uk": "101165590", "nl": "102890719", "de": "101282230",
        "se": "105117694", "dk": "104514075", "ie": "104738515", "ae": "104305776",
    }
    _TIME_WINDOW_MAP = {"r86400": "r86400", "r604800": "r604800", "r2592000": "r2592000"}
    path = ROOT / "data" / "content" / "search_config.json"
    if not path.exists():
        return {}
    try:
        config = json.loads(path.read_text())
        result: dict[str, list] = {}
        for entry in config.get("searches", []):
            if entry.get("_comment"):
                continue  # skip template placeholder entries
            market = entry.get("market", "uk")
            keywords = entry.get("keywords", "").replace(" ", "+")
            if not keywords or keywords == "Your+Role+Title":
                continue  # skip unfilled placeholder entries
            geo = _GEO_IDS.get(market, "101165590")
            jt = "F%2CC" if entry.get("include_contract") else "F"
            tw = _TIME_WINDOW_MAP.get(entry.get("time_window", "r86400"), "r86400")
            url = (f"https://www.linkedin.com/jobs/search"
                   f"?keywords={keywords}&geoId={geo}"
                   f"&f_TPR={tw}&f_JT={jt}&f_E=4%2C5")
            result.setdefault(market, []).append(
                (entry.get("label", keywords), url, int(entry.get("max_jobs", 100)))
            )
        return result
    except Exception as e:
        print(f"[run_scout] Warning: could not load search_config.json: {e}")
        return {}


_config_searches = _load_searches_from_config()
if _config_searches:
    # Override hardcoded SEARCHES_APIFY* lists with config file entries
    SEARCHES_APIFY    = _config_searches.get("uk", SEARCHES_APIFY)
    SEARCHES_APIFY_NL = _config_searches.get("nl", SEARCHES_APIFY_NL)
    SEARCHES_APIFY_SE = _config_searches.get("se", SEARCHES_APIFY_SE)
    SEARCHES_APIFY_DE = _config_searches.get("de", SEARCHES_APIFY_DE)
    SEARCHES_APIFY_DK = _config_searches.get("dk", SEARCHES_APIFY_DK)
    SEARCHES_APIFY_IE = _config_searches.get("ie", SEARCHES_APIFY_IE)
    SEARCHES_APIFY_AE = _config_searches.get("ae", SEARCHES_APIFY_AE)
    print(f"[run_scout] Loaded {sum(len(v) for v in _config_searches.values())} searches from search_config.json")

# UK subset for intl runs (first 2 entries of SEARCHES_APIFY).
# Adjust the slice if your SEARCHES_APIFY includes more/fewer UK keywords.
SEARCHES_APIFY_UK_INTL = SEARCHES_APIFY[:2]


def _tagged(searches, mkt):
    """Add market tag as 4th element to 3-tuple search entries."""
    return [(t[0], t[1], t[2], mkt) for t in searches]


def _build_apify_searches(mkt):
    out = []
    if mkt in ("uk", "all"):         out += _tagged(SEARCHES_APIFY, "uk")
    if mkt in ("intl",):             out += _tagged(SEARCHES_APIFY_UK_INTL, "uk")
    if mkt in ("nl", "all", "intl"): out += _tagged(SEARCHES_APIFY_NL, "nl")
    if mkt in ("se", "all"):         out += _tagged(SEARCHES_APIFY_SE, "se")
    if mkt in ("de", "all", "intl"): out += _tagged(SEARCHES_APIFY_DE, "de")
    if mkt in ("dk", "all", "intl"): out += _tagged(SEARCHES_APIFY_DK, "dk")
    if mkt in ("ie", "all", "intl"): out += _tagged(SEARCHES_APIFY_IE, "ie")
    if mkt in ("ae", "all", "intl"): out += _tagged(SEARCHES_APIFY_AE, "ae")
    return out


apify_searches_tagged = _build_apify_searches(market)
apify_searches = [(t[0], t[1], t[2]) for t in apify_searches_tagged]

apify_max_jobs = max_jobs

# ── Display header ────────────────────────────────────────────────────────────
apify_slots   = sum(t[2] if len(t) == 3 else apify_max_jobs for t in apify_searches)

markets_str = "NL + DE + DK + IE + AE (+ UK intl subset)" if market == "intl" else (
    "UK + NL + SE + DE + DK + IE + AE" if market == "all" else market.upper())
print(f"\n[scout] ──────────────────────────────────────────")
print(f"[scout] Markets:     {markets_str}")
print(f"[scout] Source:      Apify (LinkedIn, curious_coder/linkedin-jobs-scraper)")
if intl_age_days:
    print(f"[scout] Window:      UK=24h | other markets={intl_age_days}d (--intl-age override)")
else:
    print(f"[scout] Window:      past 24h all markets (f_TPR=r86400 in URL)")
print(f"[scout] Searches:    {len(apify_searches)} LinkedIn URLs")
for entry in apify_searches:
    label = entry[0]; per_max = entry[2] if len(entry) == 3 else apify_max_jobs
    print(f"[scout]              {label:<35} max {per_max} jobs")
est_max = apify_slots * 0.001
print(f"[scout] Est. cost:   ~${est_max:.2f} max ({apify_slots} total slots × $0.001/job)")
print(f"[scout] ──────────────────────────────────────────\n")

# ── Cache status check ────────────────────────────────────────────────────────
from scripts.apify_cache import CachedScraper, read_cache as read_apify_cache

cache_hits = sum(1 for e in apify_searches_tagged
                 if read_apify_cache(e[0], e[1]) is not None)
live_calls = len(apify_searches_tagged) - cache_hits
if live_calls == 0:
    print(f"[scout] All results from Apify cache — $0.00 cost")
else:
    live_slots = sum(t[2] for t in apify_searches_tagged
                     if read_apify_cache(t[0], t[1]) is None)
    est_live = live_slots * 0.001
    print(f"[scout] Cache: {cache_hits}/{len(apify_searches_tagged)} cached → {live_calls} live call(s)")
    print(f"[scout] Est. cost: ~${est_live:.2f} max ({live_calls} URLs, {live_slots} slots × $0.001/job)")

# ── Dry run — print search list and exit ──────────────────────────────────────
if dry_run:
    print(f"\n[scout] Apify searches ({len(apify_searches)}) — per-URL caps:")
    for entry in apify_searches:
        label, url = entry[0], entry[1]
        per_max = entry[2] if len(entry) == 3 else apify_max_jobs
        print(f"  • {label:<35} max {per_max} jobs  (curious_coder actor, $0.001/job)")
        print(f"    {url[:90]}{'...' if len(url) > 90 else ''}")
    print(f"\n[scout] --dry-run: exiting without making any API calls.")
    sys.exit(0)

if yes:
    print("\n[scout] --yes flag set — skipping confirmation prompt")
else:
    confirm = input("\nProceed? [Y/n]: ").strip().lower()
    if confirm not in ("", "y", "yes"):
        print("[scout] Aborted.")
        sys.exit(0)

# ── Concurrent run prevention ─────────────────────────────────────────────────
def _acquire_lock():
    """Return True if lock acquired; False if another run is actively in progress."""
    if LOCK_FILE.exists():
        try:
            info  = json.loads(LOCK_FILE.read_text())
            pid   = info.get("pid", 0)
            age_h = (time.time() - LOCK_FILE.stat().st_mtime) / 3600
            try:
                os.kill(pid, 0)   # signal 0 = existence check only
                alive = True
            except (ProcessLookupError, PermissionError):
                alive = False
            if alive and age_h < 2:
                print(f"[scout] Another run is in progress "
                      f"(PID {pid}, started {info.get('started_at', '?')}). Exiting.")
                return False
            print(f"[scout] WARNING: stale lock found "
                  f"(PID {pid}, {age_h:.1f}h old, process {'alive' if alive else 'dead'}). "
                  f"Overriding.")
        except Exception:
            pass   # corrupt/unreadable lock file — overwrite
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(json.dumps({
        "pid": os.getpid(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }))
    return True

if not _acquire_lock():
    sys.exit(0)
import atexit
atexit.register(lambda: LOCK_FILE.unlink(missing_ok=True))

# ── Pull latest Sheet edits into tracker before scraping ─────────────────────
print("\n[scout] Pulling latest Sheet edits...")
_pull = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "sheets_sync.py"), "pull",
     "--tabs", "apps,archive"],
    cwd=ROOT
)
if _pull.returncode != 0:
    print("[scout] ⚠ sheets_sync pull failed — proceeding with local tracker")

# ── Load credentials ──────────────────────────────────────────────────────────
apify_token = None
try:
    from scripts.apify_cache import load_token
    apify_token = load_token()
except Exception:
    pass

def _make_apify():
    return CachedScraper(token=apify_token)

# ── Run scrape ────────────────────────────────────────────────────────────────
def _scrape_apify_all_markets(scraper, tagged, max_j):
    """Run Apify for all markets in parallel, stamp market on each job, return combined list."""
    from concurrent.futures import ThreadPoolExecutor, as_completed as _ac

    def _fetch_market(mkt_tag):
        mkt_list = [(t[0], t[1], t[2]) for t in tagged if t[3] == mkt_tag]
        print(f"[scout] Apify [{mkt_tag.upper()}]: {len(mkt_list)} URL(s)...")
        mkt_jobs = scraper.get_batch(mkt_list, max_jobs=max_j)
        for j in mkt_jobs:
            j["market"] = mkt_tag
        print(f"[scout] Apify [{mkt_tag.upper()}]: {len(mkt_jobs)} jobs")
        return mkt_jobs

    markets = sorted(set(t[3] for t in tagged))
    all_jobs = []
    with ThreadPoolExecutor(max_workers=len(markets)) as pool:
        futures = {pool.submit(_fetch_market, mkt): mkt for mkt in markets}
        for f in _ac(futures):
            all_jobs.extend(f.result())
    return all_jobs

# ── Pre-run Apify budget snapshot (for cost delta in monitoring) ──────────────
def _write_pre_run_apify_snapshot():
    try:
        from urllib import request as _req2
        token = apify_token
        if not token:
            return
        req = _req2.Request(
            f"https://api.apify.com/v2/users/me/usage/monthly?token={token}",
            headers={"Content-Type": "application/json"},
        )
        with _req2.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        services = d["data"]["monthlyServiceUsage"]
        used = sum(v.get("amountAfterVolumeDiscountUsd", 0) for v in services.values())
        snap_path = ROOT / "data" / "monitoring" / "pre_run_snapshot.json"
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.write_text(json.dumps({
            "timestamp":            datetime.now().isoformat(timespec="seconds"),
            "apify_used_usd_before": round(used, 4),
        }))
        print(f"[scout] Pre-run Apify snapshot: ${used:.4f} used this cycle")
    except Exception as e:
        print(f"[scout] Pre-run snapshot skipped: {e}")

_write_pre_run_apify_snapshot()

# ── Sponsor register staleness check (warn-only; score_jobs enforces absence) ──
def _warn_stale_registers(active_markets: set):
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from sponsor_register import get_age_days
        for mkt in ("uk", "nl"):
            if mkt not in active_markets:
                continue
            age = get_age_days(mkt)
            if age >= 9999:
                print(f"[scout] ⚠ {mkt.upper()} sponsor register MISSING — all {mkt.upper()} jobs "
                      f"will be skipped. Fix: python3 scripts/sponsor_register.py refresh-{mkt}")
            elif age > 14:
                print(f"[scout] ⚠ {mkt.upper()} sponsor register is {age} days old — refresh "
                      f"recommended: python3 scripts/sponsor_register.py refresh-{mkt}")
    except Exception as e:
        print(f"[scout] Register age check skipped: {e}")

_active_markets = ({"uk", "nl", "se", "de", "dk", "ie", "ae"} if market == "all"
                   else {"nl", "de", "dk", "ie", "ae", "uk"} if market == "intl"
                   else {market})
_warn_stale_registers(_active_markets)

# ── Skip scrape+enrich if today's enriched output already exists ──────────────
# This lets score_jobs.py re-run without re-scraping Apify after a crash.
# Guard: also require today's Apify cache files to exist — the enriched file's
# mtime alone is unreliable because inject_manual.py and enrich_jobs.py can
# update it without making an Apify call (causing a false skip).
_enriched_path = ROOT / "data" / "pipeline" / "enriched_scrape_output.json"
_today_str = datetime.now().date().isoformat()
_apify_cache_dir = ROOT / "data" / "apify_cache"
_apify_ran_today = any(
    f.suffix == ".json" and f.stem.endswith(_today_str)
    for f in _apify_cache_dir.iterdir()
) if _apify_cache_dir.exists() else False
_skip_to_scoring = (
    _enriched_path.exists()
    and datetime.fromtimestamp(_enriched_path.stat().st_mtime).date().isoformat() == _today_str
    and _apify_ran_today
)

if _skip_to_scoring:
    print(f"\n[scout] Enriched data from today already exists (Apify ran today) — skipping scrape + enrich.")
    print(f"[scout] Resuming from scoring step (no extra Apify cost).")
else:
    try:
        results = _scrape_apify_all_markets(_make_apify(), apify_searches_tagged, apify_max_jobs)
        print(f"\n[scout] Apify total: {len(results)} unique jobs across all markets")
    except RuntimeError as e:
        print(f"\n[scout] ERROR: Apify run failed — {e}")
        print(f"[scout]   Check APIFY_TOKEN in .env and console.apify.com")
        sys.exit(1)

    # ── Save raw output ───────────────────────────────────────────────────────────
    raw_path = ROOT / "data" / "pipeline" / "raw_scrape_output.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\n[scout] Saved {len(results)} raw jobs → {raw_path}")

    # ── Run enrichment ────────────────────────────────────────────────────────────
    print(f"\n[scout] Running enrichment...")
    enrich = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "enrich_jobs.py")],
        cwd=ROOT
    )
    if enrich.returncode != 0:
        print("[scout] ERROR: enrich_jobs.py failed — aborting")
        sys.exit(1)
    print(f"[scout] Enriched output → data/pipeline/enriched_scrape_output.json")

# ── Run scoring ───────────────────────────────────────────────────────────────
print(f"\n[scout] Running scorer...")
score_cmd = [sys.executable, str(ROOT / "scripts" / "score_jobs.py")]
score = subprocess.run(score_cmd, cwd=ROOT)
if score.returncode != 0:
    print("[scout] ERROR: score_jobs.py failed — aborting")
    sys.exit(1)

# ── Write scored entries to tracker ──────────────────────────────────────────
print(f"\n[scout] Writing scored jobs to tracker...")
_wt = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "write_tracker.py")],
    cwd=ROOT
)
if _wt.returncode != 0:
    print("[scout] ⚠ write_tracker.py failed — check output above")

# ── Push tracker to Google Sheet ─────────────────────────────────────────────
print(f"\n[scout] Syncing tracker to Google Sheet...")
_push = subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "sheets_sync.py"), "push",
     "--tabs", "apps,archive"],
    cwd=ROOT
)
if _push.returncode != 0:
    print("[scout] ⚠ sheets_sync push failed")

print(f"\n[scout] Running post-run analysis...")
subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "scout_analysis.py")],
    cwd=ROOT
)

print(f"\n[scout] Scout complete.")

# ── Monitoring ─────────────────────────────────────────────────────────────
triggered_by = "github_actions" if os.environ.get("GITHUB_ACTIONS") else "local_manual"
subprocess.run(
    [sys.executable, str(ROOT / "scripts" / "monitor_scout.py"),
     "--triggered-by", triggered_by],
    cwd=ROOT
)

# ── Git commit + push (versioning + backup) ──────────────────────────────
print(f"\n[scout] Committing pipeline outputs to git...")
from git_sync import commit_and_push as _git_push
_git_push("scout", [
    "data/job_tracker.json",
    "data/auto_rejected.json",
    "data/processed_email_ids.json",
    "data/unmatched_emails.json",
    "data/jd_text_cache.json",
    "data/reinject_jobs.json",
    "data/monitoring/",
    "data/pipeline/",
])
