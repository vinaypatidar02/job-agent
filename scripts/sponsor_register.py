#!/usr/bin/env python3
"""
sponsor_register.py — UK Home Office & NL IND sponsor register cache

Downloads and caches:
  UK: Home Office Register of Licensed Sponsors (Workers)
      → data/sponsor_registers/uk_sponsors.csv
  NL: IND Recognised Sponsors register
      → data/sponsor_registers/nl_sponsors.txt

Usage:
  python3 scripts/sponsor_register.py refresh-uk
  python3 scripts/sponsor_register.py refresh-nl
  python3 scripts/sponsor_register.py status

Imported by score_jobs.py — must never hard-crash on missing files.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import urllib.request as _ureq
from datetime import date, datetime
from pathlib import Path
from typing import Optional

ROOT        = Path(__file__).parent.parent
_DATA_DIR   = ROOT / "data" / "sponsor_registers"
UK_CSV_PATH = _DATA_DIR / "uk_sponsors.csv"
NL_TXT_PATH = _DATA_DIR / "nl_sponsors.txt"


def _ensure_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────────────────────

def refresh_uk() -> None:
    """Download the Home Office Licensed Sponsors (Workers) CSV."""
    _ensure_dir()

    # Step 1 — fetch the publications page to find the current CSV download URL
    page_url = (
        "https://www.gov.uk/government/publications/"
        "register-of-licensed-sponsors-workers"
    )
    print(f"[sponsor_register] Fetching UK page: {page_url}")
    try:
        req = _ureq.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[sponsor_register] ERROR fetching UK page: {e}")
        return

    # Extract CSV URL from the attachment links in the page
    csv_url = None
    for pattern in [
        r'href="(https://assets\.publishing\.service\.gov\.uk[^"]+\.csv)"',
        r'href="(/government/uploads/[^"]+\.csv)"',
        r'"url"\s*:\s*"(https://[^"]+register-of-licensed-sponsors[^"]+\.csv)"',
    ]:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            csv_url = m.group(1)
            if csv_url.startswith("/"):
                csv_url = "https://www.gov.uk" + csv_url
            break

    if not csv_url:
        # Fallback: direct known URL pattern
        csv_url = (
            "https://assets.publishing.service.gov.uk/media/"
            "register-of-licensed-sponsors-workers.csv"
        )
        print(f"[sponsor_register] WARNING: could not parse CSV URL from page, "
              f"trying fallback: {csv_url}")

    print(f"[sponsor_register] Downloading UK register: {csv_url}")
    try:
        req2 = _ureq.Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req2, timeout=60) as resp2:
            data = resp2.read()
        UK_CSV_PATH.write_bytes(data)
        lines = data.count(b"\n")
        print(f"[sponsor_register] UK register saved: {UK_CSV_PATH} ({lines:,} lines)")
    except Exception as e:
        print(f"[sponsor_register] ERROR downloading UK CSV: {e}")


def refresh_nl() -> None:
    """Download the IND Recognised Sponsors register."""
    _ensure_dir()

    # IND Work register sub-page — contains the HTML table with sponsor names
    # (Parent page at /public-register-recognised-sponsors just links to sub-pages)
    page_url = "https://ind.nl/en/public-register-recognised-sponsors/public-register-work"
    print(f"[sponsor_register] Fetching NL IND page: {page_url}")
    try:
        req = _ureq.Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[sponsor_register] ERROR fetching NL page: {e}")
        html = ""

    # Try to find a direct download link (CSV or Excel)
    dl_url = None
    for pattern in [
        r'href="(https://[^"]+recognized-sponsors[^"]*\.(csv|xlsx?))"',
        r'href="(https://[^"]+ind\.nl[^"]+\.(csv|xlsx?))"',
        r'href="(/[^"]+register[^"]*\.(csv|xlsx?))"',
    ]:
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            dl_url = m.group(1)
            if dl_url.startswith("/"):
                dl_url = "https://ind.nl" + dl_url
            break

    if dl_url:
        print(f"[sponsor_register] Downloading NL register: {dl_url}")
        try:
            req2 = _ureq.Request(dl_url, headers={"User-Agent": "Mozilla/5.0"})
            with _ureq.urlopen(req2, timeout=60) as resp2:
                data = resp2.read()
            # Store raw content (plain text or CSV)
            NL_TXT_PATH.write_bytes(data)
            print(f"[sponsor_register] NL register saved: {NL_TXT_PATH} ({len(data):,} bytes)")
            return
        except Exception as e:
            print(f"[sponsor_register] ERROR downloading NL file: {e}")

    # Fallback: parse company names from the HTML table on the page
    # IND work register uses: <th scope="row">Company Name</th>
    if html:
        print("[sponsor_register] Parsing NL company names from HTML table...")
        import html as _html_mod
        names = re.findall(r'<th scope="row">([^<]+)</th>', html)
        if names:
            # Deduplicate while preserving order
            seen: set = set()
            unique_names = []
            for n in names:
                n_clean = n.strip()
                if n_clean.lower() not in seen:
                    seen.add(n_clean.lower())
                    unique_names.append(n_clean)
            # Decode HTML entities (e.g. &amp; → &)
            unique_names = [_html_mod.unescape(n) for n in unique_names]
            NL_TXT_PATH.write_text("\n".join(unique_names), encoding="utf-8")
            print(f"[sponsor_register] NL register (HTML-parsed): "
                  f"{len(unique_names)} companies → {NL_TXT_PATH}")
        else:
            print("[sponsor_register] WARNING: could not extract NL company names from HTML. "
                  "The IND page structure may have changed. "
                  "Manually download from https://ind.nl/en/public-register-recognised-sponsors/public-register-work "
                  "and save as data/sponsor_registers/nl_sponsors.txt (one name per line).")
    else:
        print("[sponsor_register] WARNING: NL page fetch failed and no fallback available.")


# ─────────────────────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────────────────────

def load_uk() -> list | None:
    """
    Load UK sponsor names from the cached CSV.
    Returns list of lowercase company names, or None if file absent.
    """
    if not UK_CSV_PATH.exists():
        return None
    try:
        names = []
        with open(UK_CSV_PATH, newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for row in reader:
                if row:
                    # First column is typically the organisation name
                    name = row[0].strip()
                    if name and name.lower() != "organisation name":
                        names.append(name.lower())
        return names if names else None
    except Exception as e:
        print(f"[sponsor_register] WARNING: could not load UK register: {e}")
        return None


def load_nl() -> list | None:
    """
    Load NL sponsor names from the cached file (plain text, one per line, or CSV-ish).
    Returns list of lowercase company names, or None if file absent.
    """
    if not NL_TXT_PATH.exists():
        return None
    try:
        content = NL_TXT_PATH.read_text(encoding="utf-8", errors="replace")
        names = []
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                # Strip CSV quoting if present
                name = line.strip('"').strip("'").strip(",").strip()
                if name:
                    names.append(name.lower())
        return names if names else None
    except Exception as e:
        print(f"[sponsor_register] WARNING: could not load NL register: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# LOOKUP
# ─────────────────────────────────────────────────────────────

_CORP_STRIP = re.compile(
    r'\s*\b(plc|ltd|limited|inc|corp|corporation|group|holdings|llc|gmbh|bv|ab|sa|nv|'
    r'co\.|co|the|uk|nl|europe|international|global)\b\.?\s*$',
    re.IGNORECASE,
)

_TLD_BRAND = re.compile(r'\b(\w{4,}\.(?:com|org|net|io|ai|nl|de|uk|eu))\b', re.IGNORECASE)

# NL alias map: LinkedIn company name (exact) → token that appears in the register entry.
# Used when _normalise() cannot bridge the name gap (e.g. "The HEINEKEN Company" ≠ "Heineken Nederland B.V.").
# Aliases must be verified against data/sponsor_registers/nl_sponsors.txt before adding.
# Key: exact LinkedIn company_name string (case-sensitive as it appears in scrape output).
# Value: token that is a substring of the normalised register entry.
_NL_ALIASES: dict[str, str] = {
    "The HEINEKEN Company":                 "heineken",
    "Accenture the Netherlands":            "accenture",
    "Randstad Nederland":                   "randstad",
    "Alibaba Cloud":                        "alibaba",
    "Basic-Fit":                            "basic fit",
    "Bausch + Lomb NL":                     "bausch",
    "Biscuit International Netherlands":    "biscuit international",
    "ERIKS Netherlands":                    "eriks",
    "Experis Nederland":                    "experis",
    "Grant Thornton Netherlands":           "grant thornton",
    "HADDAD BRANDS EUROPE":                 "haddad",
    "Hillebrand Gori - A company of DHL":   "hillebrand",
    "Hot ITem Conclusion":                  "conclusion",
    "Hyundai GLOVIS Europe":                "hyundai",
    "Johnson & Johnson Innovative Medicine":"johnson",
    "Johnson & Johnson MedTech":            "johnson",
    "Mediq Nederland":                      "mediq",
    "OLIVER | The Brandtech Group":         "oliver",
    "Odido Nederland":                      "odido",
    "Rituals (B Corp™)":               "rituals",
    "Stater Nederland B.V.":               "stater",
    "Tony's Chocolonely":                   "tony",
    "Arval BNP Paribas Group":              "arval",
    "AS Watson Benelux":                    "watson",
    "dsm-firmenich":                        "dsm",
    "dsm-Firmenich":                        "dsm",
    "DSM-firmenich":                        "dsm",
}


def _normalise(name: str) -> str:
    """Strip suffixes and lowercase for fuzzy matching."""
    name = name.strip().lower()
    # Iteratively strip trailing corp suffixes (e.g. "Foo Ltd Group" → "Foo")
    for _ in range(3):
        stripped = _CORP_STRIP.sub("", name).strip()
        if stripped == name:
            break
        name = stripped
    return name


def lookup_uk(company: str, registry: list) -> bool:
    """
    Return True if company appears on the UK sponsor register.
    Partial, case-insensitive match: 'Deloitte' matches 'Deloitte LLP'.
    """
    if not company or not registry:
        return False
    needle = _normalise(company)
    if len(needle) < 3:
        return False
    for entry in registry:
        entry_norm = _normalise(entry)
        if needle in entry_norm or entry_norm in needle:
            return True
    return False


def lookup_nl(company: str, registry: list) -> bool:
    """
    Return True if company appears on the NL IND recognised sponsors register.

    Three-tier matching (all additive, zero regression risk):
      1. Primary: partial substring match after suffix-stripping (original logic).
      2. Alias map: curated LinkedIn-name → register token for known name-form gaps
         (e.g. "The HEINEKEN Company" → "heineken" → matches "Heineken Nederland B.V.").
      3. TLD-brand: extract ".com"-style brand token for compound names like
         "Just Eat Takeaway.com" → "takeaway.com" → matches "Takeaway.com Group B.V.".
    """
    if not company or not registry:
        return False
    needle = _normalise(company)
    if len(needle) < 3:
        return False

    # Tier 2: alias map (exact LinkedIn company_name key, case-sensitive).
    alias_token = _NL_ALIASES.get(company)

    # Tier 3: TLD-brand fallback (compound names like "Just Eat Takeaway.com").
    tld_brand = None
    m = _TLD_BRAND.search(company)
    if m:
        candidate = m.group(1).lower()
        if candidate != needle:
            tld_brand = candidate

    for entry in registry:
        entry_norm = _normalise(entry)
        # Tier 1: original substring logic
        if needle in entry_norm or entry_norm in needle:
            return True
        # Tier 2: alias token in normalised register entry
        if alias_token and alias_token in entry_norm:
            return True
        # Tier 3: TLD brand token in normalised register entry
        if tld_brand and (tld_brand in entry_norm or entry_norm in tld_brand):
            return True
    return False


# ─────────────────────────────────────────────────────────────
# METADATA
# ─────────────────────────────────────────────────────────────

def get_age_days(market: str) -> int:
    """Return age in days of the cached register file, or 9999 if absent."""
    path = UK_CSV_PATH if market == "uk" else NL_TXT_PATH
    if not path.exists():
        return 9999
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
        return (date.today() - mtime).days
    except Exception:
        return 9999


def status() -> None:
    """Print age and record count for each cached register."""
    for market, path, loader in [
        ("uk", UK_CSV_PATH, load_uk),
        ("nl", NL_TXT_PATH, load_nl),
    ]:
        if path.exists():
            age = get_age_days(market)
            names = loader() or []
            size_kb = path.stat().st_size // 1024
            print(f"[sponsor_register] {market.upper()}: {len(names):,} companies, "
                  f"{age}d old, {size_kb}kB → {path}")
        else:
            print(f"[sponsor_register] {market.upper()}: NOT DOWNLOADED")
            print(f"  Fix: python3 scripts/sponsor_register.py refresh-{market}")


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "refresh-uk":
        refresh_uk()
    elif cmd == "refresh-nl":
        refresh_nl()
    elif cmd == "status":
        status()
    else:
        print(f"Usage: python3 scripts/sponsor_register.py refresh-uk|refresh-nl|status")
        sys.exit(1)
