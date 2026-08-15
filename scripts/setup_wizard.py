#!/usr/bin/env python3
"""
setup_wizard.py — Interactive setup for Claude-Workflow-Automation.

Guides you through the minimum configuration required to run your first scout.
Takes ~15 minutes. Advanced customisation is documented in GUIDE.md §6.

Usage:
    python3 scripts/setup_wizard.py
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

CYAN  = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED   = "\033[31m"
BOLD  = "\033[1m"
RESET = "\033[0m"

PROFILE_PATH        = ROOT / "data" / "content" / "candidate_profile.json"
EXPERIENCE_PATH     = ROOT / "data" / "content" / "experience_bank.md"
ENV_PATH            = ROOT / ".env"
ENV_EXAMPLE         = ROOT / ".env.example"
RUBRIC_PATH         = ROOT / "docs" / "fit-scoring-rubric.md"
CANDIDATE_PROFILE_DOC = ROOT / "docs" / "candidate-profile.md"
SEARCH_CONFIG_PATH  = ROOT / "data" / "content" / "search_config.json"

# ─────────────────────────────────────────────────────────────────────────────

def banner(text: str) -> None:
    width = 60
    print(f"\n{CYAN}{'─' * width}{RESET}")
    print(f"{BOLD}{text}{RESET}")
    print(f"{CYAN}{'─' * width}{RESET}\n")


def ask(prompt: str, default: str = "", required: bool = True) -> str:
    display = f"{prompt}"
    if default:
        display += f" [{default}]"
    display += ": "
    while True:
        val = input(display).strip()
        if not val and default:
            return default
        if val:
            return val
        if not required:
            return ""
        print(f"  {RED}This field is required.{RESET}")


def ask_list(prompt: str, example: str = "") -> list[str]:
    print(f"{prompt}")
    if example:
        print(f"  {YELLOW}Example: {example}{RESET}")
    print(f"  Enter one per line. Press Enter twice when done.")
    items = []
    while True:
        line = input("  > ").strip()
        if not line:
            if items:
                break
        else:
            items.append(line)
    return items


def ask_yn(prompt: str, default: bool = True) -> bool:
    yn = "Y/n" if default else "y/N"
    while True:
        val = input(f"{prompt} [{yn}]: ").strip().lower()
        if not val:
            return default
        if val in ("y", "yes"):
            return True
        if val in ("n", "no"):
            return False
        print(f"  {RED}Enter y or n.{RESET}")


def print_ok(msg: str) -> None:
    print(f"  {GREEN}✓ {msg}{RESET}")


def print_warn(msg: str) -> None:
    print(f"  {YELLOW}⚠ {msg}{RESET}")


# ─────────────────────────────────────────────────────────────────────────────

def load_existing_profile() -> dict:
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_profile(profile: dict) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    print_ok(f"Saved: {PROFILE_PATH.relative_to(ROOT)}")


# ─────────────────────────────────────────────────────────────────────────────

def step_welcome() -> None:
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════╗
║  Claude-Workflow-Automation — Setup Wizard               ║
║  Minimum config for your first scout run (~15 min)       ║
╚══════════════════════════════════════════════════════════╝{RESET}

This wizard configures the essentials. Everything can be tuned
later — see {CYAN}GUIDE.md §6{RESET} for the full customisation guide.

You will set up:
  1. Your contact details (name, email, phone, LinkedIn)
  2. Your target job titles and profession domain
  3. Your work experience (minimum 1 role)
  4. Your target markets and salary thresholds
  5. Your LinkedIn job search configuration
  6. Your job fit scoring rubric

Press Ctrl+C at any time to cancel without saving.
""")


def step_contact(profile: dict) -> dict:
    banner("Step 1 of 6 — Contact Details")
    print("These appear in your resume header and cover letter.\n")
    c = profile.get("contact", {})
    c["name"]     = ask("Full name",     c.get("name", ""))
    c["email"]    = ask("Email address", c.get("email", ""))
    c["phone"]    = ask("Phone (international format, e.g. +1 234 567 8900)", c.get("phone", ""))
    c["linkedin"] = ask("LinkedIn URL (e.g. linkedin.com/in/your-name)", c.get("linkedin", ""))
    c["address"]  = ask("City, Country (e.g. London, UK)", c.get("address", ""))

    print("\nVisa situation:")
    markets = ["uk", "nl", "de", "dk", "ie", "se", "ae"]
    print(f"  Available markets: {', '.join(markets)}")
    rtw_input = ask("Markets where you ALREADY have the right to work (comma-separated, or blank if none)", "", required=False)
    rtw = [m.strip() for m in rtw_input.split(",") if m.strip() in markets] if rtw_input else []
    profile["has_right_to_work"] = {"markets": rtw}

    if rtw:
        print_ok(f"Visa checks will be skipped for: {', '.join(rtw)}")

    profile["contact"] = c
    return profile


def step_profession(profile: dict) -> dict:
    banner("Step 2 of 6 — Profession & Target Roles")
    p = profile.get("profile", {})

    print("What roles are you targeting? List your ideal job titles.\n")
    existing_roles = p.get("target_roles", [])
    if existing_roles and existing_roles != ["Your Target Role 1", "Your Target Role 2"]:
        print(f"  Current: {existing_roles}")
        if not ask_yn("Keep existing roles?"):
            existing_roles = []
    if not existing_roles:
        existing_roles = ask_list(
            "Target job titles (list each title you'd accept):",
            "Analytics Manager, Lead Data Analyst, Head of Analytics"
        )

    p["target_roles"] = existing_roles
    p["years_of_experience"] = int(ask("Years of relevant experience", str(p.get("years_of_experience", 5))))

    print("\nWhat is your primary domain/profession? (Used in document framing)")
    print(f"  {YELLOW}Examples: Analytics, Software Engineering, Finance, Product Management{RESET}")
    domain_label = ask("Your domain", p.get("target_seniority", "").split(" —")[0] or "Analytics")
    p["target_seniority"] = f"Lead/Manager level — {p['years_of_experience']}+ years experience expected"

    # Build minimal domain keywords for domain detection
    print(f"\nEnter 5-10 keywords that describe jobs in your domain (for document tailoring).")
    print(f"  {YELLOW}Example (analytics): product analytics, experimentation, sql, kpi, dashboard{RESET}")
    print(f"  {YELLOW}Example (software):  microservices, api design, kubernetes, ci/cd, distributed systems{RESET}")
    existing_domains = {k: v for k, v in profile.get("domains", {}).items() if not k.startswith("_")}
    if existing_domains:
        print(f"  Current domains configured. Skip to keep them.")
        if ask_yn("Keep existing domain keywords?"):
            profile["profile"] = p
            return profile

    domain_keywords = ask_list(
        f"Keywords for your primary domain ({domain_label}):",
        "experimentation, sql, python, dashboard, kpi framework"
    )
    profile["domains"] = {
        "_doc": "Domain keywords for document tailoring. Fill each domain with JD vocabulary from your field.",
        "primary": {
            "label": domain_label,
            "keywords": domain_keywords
        },
        "general": {
            "label": "General",
            "keywords": []
        }
    }

    # Core skills
    print("\nList your top technical skills (appear in resume Skills section).")
    print(f"  {YELLOW}Example: SQL, Python, Tableau, BigQuery, Looker{RESET}")
    existing_skills = profile.get("core_skills", {}).get("skills", [])
    if existing_skills and "YOUR_SKILL" not in str(existing_skills):
        print(f"  Current: {existing_skills}")
        if ask_yn("Keep existing skills?"):
            # Still write title_classifier even when skipping skills re-entry
            profile["title_classifier"] = {
                "domain_keywords": domain_keywords if "domain_keywords" in dir() else existing_domains.get("primary", {}).get("keywords", []),
                "seniority_keywords": ["manager", "lead", "head", "principal", "director"]
            }
            profile["profile"] = p
            return profile
    skills = ask_list("Top skills (1-8):", "SQL, Python, Tableau, BigQuery")
    profile["core_skills"] = {"skills": skills}

    # Write title_classifier from collected domain keywords
    profile["title_classifier"] = {
        "domain_keywords": domain_keywords,
        "seniority_keywords": ["manager", "lead", "head", "principal", "director"]
    }

    profile["profile"] = p
    return profile


def step_experience(profile: dict) -> dict:
    banner("Step 3 of 6 — Work Experience")
    print("The pipeline selects resume bullets from experience_bank.md.")
    print("We'll create a starter template for you to fill in.\n")

    existing_exp = [
        e for e in profile.get("experience", [])
        if not e.get("company", "").startswith("Company")
    ]

    if existing_exp:
        print(f"  Found {len(existing_exp)} existing role(s). Adding a new role.")
    else:
        print("  Let's add your most recent role (you can add more in experience_bank.md).")

    add_exp = ask_yn("Add/confirm work experience now?", True)
    if not add_exp:
        print_warn("Skipped. Fill data/content/experience_bank.md and candidate_profile.json → experience manually.")
        return profile

    roles = list(existing_exp)
    print("\nMost recent role:")
    company = ask("Company name")
    role    = ask("Job title")
    dates   = ask("Dates (e.g. 2023-01–2024-12 or 2022-06–present)")
    city    = ask("City (optional)", "", required=False)

    bank_key = f"{company}"
    roles.insert(0, {
        "company":     company,
        "location":    city or "Remote",
        "role":        role,
        "dates":       dates,
        "bank_key":    bank_key,
        "pinned":      False,
        "max_bullets": 5,
        "focus_areas": "key achievements and responsibilities"
    })

    if ask_yn("Add another role?", False):
        company2 = ask("Company name")
        role2    = ask("Job title")
        dates2   = ask("Dates")
        city2    = ask("City (optional)", "", required=False)
        roles.append({
            "company":     company2,
            "location":    city2 or "Remote",
            "role":        role2,
            "dates":       dates2,
            "bank_key":    company2,
            "pinned":      False,
            "max_bullets": 4,
            "focus_areas": "key achievements and responsibilities"
        })

    profile["experience"] = roles

    # Write/append experience_bank.md
    _write_experience_bank(roles)
    return profile


def _write_experience_bank(roles: list[dict]) -> None:
    if EXPERIENCE_PATH.exists():
        existing = EXPERIENCE_PATH.read_text(encoding="utf-8")
        added = []
        for r in roles:
            key = r["bank_key"]
            if f"## {key}" not in existing:
                added.append(r)
        if added:
            with EXPERIENCE_PATH.open("a", encoding="utf-8") as f:
                for r in added:
                    f.write(_experience_bank_section(r))
            print_ok(f"Appended {len(added)} section(s) to experience_bank.md")
        else:
            print_ok("experience_bank.md already has entries for these roles.")
    else:
        with EXPERIENCE_PATH.open("w", encoding="utf-8") as f:
            f.write(_experience_bank_header())
            for r in roles:
                f.write(_experience_bank_section(r))
        print_ok(f"Created: {EXPERIENCE_PATH.relative_to(ROOT)}")

    print(f"\n  {YELLOW}Next: open experience_bank.md and fill in real bullet points.{RESET}")
    print(f"  Format: • [tag] Action verb + context + metric")
    print(f"  Example: • [product] Led experimentation programme across 3 verticals, improving conversion by 18%.")


def _experience_bank_header() -> str:
    return """# experience_bank.md — Resume Bullet Points

## HOW TO USE
# Each ## heading is a "bank_key" — it must match the bank_key in candidate_profile.json.
# Tag each bullet with [tag] so the pipeline can select relevant bullets per JD domain.
# Format: • [tag] Action verb + context + specific metric
# Rules:
#   - Only include metrics you can verify and defend in an interview
#   - Never fabricate achievements — the pipeline selects from here, never invents
#   - Aim for 6-10 bullets per role (pipeline selects the most relevant per JD)
#
# Example tags: [product] [analytics] [leadership] [data] [engineering] [commercial]
# Use tags that match the domain keywords you configured in candidate_profile.json → domains

"""


def _experience_bank_section(r: dict) -> str:
    return f"""## {r["bank_key"]}
{r["role"]} | {r["dates"]}

• [tag] REPLACE: Action verb + context + metric (e.g. Led X initiative, resulting in Y% improvement)
• [tag] REPLACE: Action verb + context + metric
• [tag] REPLACE: Action verb + context + metric

"""


def step_markets(profile: dict) -> dict:
    banner("Step 4 of 6 — Markets & Salary Thresholds")
    print("Which markets are you targeting? This determines which LinkedIn searches to run.\n")

    market_info = {
        "uk": "United Kingdom (Skilled Worker Visa sponsorship required)",
        "nl": "Netherlands (Kennismigrant sponsorship required)",
        "de": "Germany (EU Blue Card sponsorship required)",
        "dk": "Denmark (Pay Limit Scheme sponsorship required)",
        "ie": "Ireland (Critical Skills Permit sponsorship required)",
        "se": "Sweden (Arbetstillstånd, whitelist brands only)",
        "ae": "UAE / Dubai (Employment Visa sponsorship required)",
    }
    rtw = set(profile.get("has_right_to_work", {}).get("markets", []))

    print("Available markets:")
    for code, desc in market_info.items():
        note = f" {GREEN}[already have right to work]{RESET}" if code in rtw else ""
        print(f"  {code:4s} — {desc}{note}")

    selected_input = ask("\nEnter markets to target (comma-separated)", "uk,nl,de")
    selected = [m.strip() for m in selected_input.split(",") if m.strip() in market_info]
    if not selected:
        selected = ["uk"]
        print_warn("Defaulting to UK only.")

    profile["_target_markets"] = selected

    # Visa addresses
    visa_defaults = {
        "uk": "Seeking Skilled Worker Visa Sponsorship",
        "nl": "Seeking Kennismigrant Sponsorship",
        "de": "Seeking EU Blue Card Sponsorship",
        "dk": "Seeking Pay Limit Scheme Sponsorship",
        "ie": "Seeking Critical Skills Employment Permit",
        "se": "Seeking Arbetstillstånd Sponsorship",
        "ae": "Seeking UAE Employment Visa Sponsorship",
    }
    country = profile["contact"].get("address", "").split(",")[-1].strip() or "Your Country"
    visa_addresses = {}
    for m in selected:
        if m not in rtw:
            visa_addresses[m] = f"{country} | {visa_defaults[m]}"
    profile["visa_addresses"] = visa_addresses
    print_ok(f"Targeting: {', '.join(selected)}")

    # Salary thresholds — interactive per market
    MARKET_DEFAULTS = {
        "uk": (80_000, "GBP £"),
        "nl": (90_000, "EUR €"),
        "de": (90_000, "EUR €"),
        "dk": (700_000, "DKK kr"),
        "ie": (90_000, "EUR €"),
        "se": (800_000, "SEK kr"),
        "ae": (360_000, "AED"),
    }

    print(f"\n{BOLD}Minimum annual salary thresholds{RESET}")
    print("Jobs below your threshold are auto-rejected. Remote/contract roles are screened at 80% of this gate.")
    print(f"  {YELLOW}Press Enter to accept the suggested default for each market.{RESET}\n")

    thresholds: dict = {}
    for market in selected:
        default, currency_symbol = MARKET_DEFAULTS.get(market, (50_000, ""))
        print(f"  {market.upper()} — Minimum annual salary ({currency_symbol})?")
        print(f"  Suggested default: {currency_symbol}{default:,}")
        val = ask(f"  Enter amount or press Enter for default", str(default), required=False)
        threshold = int(val) if val.isdigit() else default
        thresholds[market] = threshold

    profile["salary_thresholds"] = {
        "_doc": "Annual salary gate per market in local currency. 80% applied automatically for remote/contract roles.",
        **thresholds
    }
    print_ok("Salary thresholds set. Remote/contract roles screened at 80% of each gate.")

    return profile


def _update_imap_config(host: str, port: int) -> None:
    """Update IMAP_HOST and IMAP_PORT in gmail_backfill.py."""
    script_path = ROOT / "scripts" / "gmail_backfill.py"
    if not script_path.exists():
        print_warn("gmail_backfill.py not found — update IMAP_HOST manually.")
        return
    content = script_path.read_text(encoding="utf-8")
    content = re.sub(r'^IMAP_HOST\s*=\s*".*?"', f'IMAP_HOST = "{host}"', content, flags=re.MULTILINE)
    content = re.sub(r'^IMAP_PORT\s*=\s*\d+', f'IMAP_PORT = {port}', content, flags=re.MULTILINE)
    script_path.write_text(content, encoding="utf-8")
    print_ok(f"Updated gmail_backfill.py: IMAP_HOST = {host}, IMAP_PORT = {port}")


def step_scout_urls(profile: dict) -> None:
    banner("Step 5 of 6 — LinkedIn Job Search Configuration")
    markets = profile.get("_target_markets", ["uk"])

    print(f"""
{BOLD}How LinkedIn filters work:{RESET}
  {GREEN}✅ Keywords{RESET}           — always works
  {GREEN}✅ Location / Market{RESET}  — always works
  {GREEN}✅ Experience level{RESET}   — works reliably (wizard always selects Mid-Senior + Director)
  {GREEN}✅ Date posted{RESET}        — works; choose from: Past 24 hours / Past week / Past month
                       LinkedIn does NOT support custom date ranges
  {YELLOW}⚠️  Job type{RESET}          — partially reliable; employers sometimes miscategorise roles
  {YELLOW}⚠️  Work arrangement{RESET}  — unreliable (Remote/Hybrid labels inconsistent);
                       pipeline re-detects this from job description text
""")

    # Check if search_config.json already exists with non-placeholder content
    if SEARCH_CONFIG_PATH.exists():
        try:
            existing_config = json.loads(SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))
            existing_searches = [
                s for s in existing_config.get("searches", [])
                if "YOUR_ROLE" not in s.get("keywords", "YOUR_ROLE")
            ]
            if existing_searches:
                print_ok(f"search_config.json already has {len(existing_searches)} configured search(es).")
                for s in existing_searches:
                    print(f"    • {s.get('label', s.get('keywords', '?'))}")
                if not ask_yn("Re-configure searches (overwrites existing)?", False):
                    return
        except (json.JSONDecodeError, KeyError):
            pass

    geo_ids = {
        "uk": "101165590", "nl": "102890719", "de": "101282230",
        "se": "105117694", "dk": "104514075", "ie": "104738515", "ae": "104305776"
    }

    target_roles = profile.get("profile", {}).get("target_roles", ["Your Role"])
    print(f"Your target roles: {', '.join(target_roles[:3])}")
    print(f"Your target markets: {', '.join(m.upper() for m in markets)}\n")
    print(f"Add one search entry per role-market combination. Each search costs $0.001/job fetched.")
    print(f"  {YELLOW}Tip: start with 2-3 searches across 1-2 markets, then expand once you've validated results.{RESET}\n")

    searches = []
    while True:
        print(f"\n{BOLD}Search entry {len(searches) + 1}:{RESET}")

        # Keywords
        keyword_default = target_roles[0] if target_roles else "Your Role"
        keywords = ask(f"Job title keywords to search", keyword_default)

        # Market
        print(f"  Available markets: {', '.join(markets)}")
        market_choice = ask(f"Market for this search", markets[0] if markets else "uk")
        if market_choice not in markets:
            print_warn(f"'{market_choice}' not in your configured markets. Adding anyway.")

        # Time window
        print("  Date posted filter:")
        print("    1. Past 24 hours (recommended — freshest jobs, lowest stale rate)")
        print("    2. Past week (7 days — more volume, some older posts)")
        print("    3. Past month (highest volume, most stale posts)")
        tw_choice = ask("  Choose (1/2/3)", "1")
        tw_map = {"1": "r86400", "2": "r604800", "3": "r2592000"}
        time_window = tw_map.get(tw_choice, "r86400")

        # Contract
        include_contract = ask_yn("  Include contract roles in results?", False)

        # Max jobs
        max_jobs_raw = ask("  Max jobs to fetch (cost: $0.001/job)", "100")
        try:
            max_jobs = int(max_jobs_raw)
        except ValueError:
            max_jobs = 100

        # Build preview URL
        geo = geo_ids.get(market_choice, "101165590")
        jt = "F%2CC" if include_contract else "F"
        url = (
            f"https://www.linkedin.com/jobs/search"
            f"?keywords={keywords.replace(' ', '+')}"
            f"&geoId={geo}&f_TPR={time_window}&f_JT={jt}&f_E=4%2C5"
        )
        label = f"{keywords} — {market_choice.upper()}"
        print(f"\n  Preview URL: {CYAN}{url[:100]}{'...' if len(url) > 100 else ''}{RESET}")

        searches.append({
            "label": label,
            "market": market_choice,
            "keywords": keywords,
            "time_window": time_window,
            "include_contract": include_contract,
            "max_jobs": max_jobs
        })
        print_ok(f"Added: {label}")

        if not ask_yn("Add another search?", len(searches) < 2):
            break

    # Write search_config.json
    SEARCH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config_data = {
        "_doc": "Job search configuration. Managed by setup_wizard.py. run_scout.py reads from this file.",
        "_time_windows": {
            "r86400": "Past 24 hours",
            "r604800": "Past week (7 days)",
            "r2592000": "Past month"
        },
        "searches": searches
    }
    SEARCH_CONFIG_PATH.write_text(json.dumps(config_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print_ok(f"Saved {len(searches)} search(es) to data/content/search_config.json")
    print(f"  {YELLOW}Tip: Edit this file directly to add more searches without re-running the wizard.{RESET}")


def step_env() -> None:
    banner("Environment Variables (.env)")
    if ENV_PATH.exists():
        print_ok(".env already exists.")
        if ask_yn("View required variables?", False):
            _print_env_summary()
    else:
        if not ENV_EXAMPLE.exists():
            print_warn(".env.example not found. Create .env manually (see GUIDE.md §4 Step 1).")
        else:
            print("Copying .env.example → .env for you to fill in.\n")
            import shutil
            shutil.copy(ENV_EXAMPLE, ENV_PATH)
            print_ok("Created .env from .env.example")
            print(f"\n  {YELLOW}Required: open .env and fill in:{RESET}")
            _print_env_summary()

    # Email provider selection
    print(f"\n{BOLD}Email provider for application tracking:{RESET}")
    print("  The pipeline checks your inbox for interview/rejection emails.")
    print("  1. Yahoo   (recommended — simple App Password setup)")
    print("  2. Gmail   (requires Gmail IMAP enabled + App Password)")
    print("  3. Outlook")
    print("  4. Other   (you'll provide hostname)")
    provider_choice = ask("Choose your email provider (1/2/3/4)", "1")

    imap_configs = {
        "1": ("imap.mail.yahoo.com", 993),
        "2": ("imap.gmail.com", 993),
        "3": ("outlook.office365.com", 993),
    }

    if provider_choice in imap_configs:
        imap_host, imap_port = imap_configs[provider_choice]
        if provider_choice == "1":
            print_ok("Yahoo IMAP — default config (no file change needed)")
        else:
            _update_imap_config(imap_host, imap_port)
    elif provider_choice == "4":
        imap_host = ask("IMAP hostname (e.g. mail.yourprovider.com)")
        imap_port_raw = ask("IMAP port", "993")
        try:
            imap_port = int(imap_port_raw)
        except ValueError:
            imap_port = 993
        _update_imap_config(imap_host, imap_port)
    else:
        print_warn("Unrecognised choice — defaulting to Yahoo. Update gmail_backfill.py manually if needed.")


def _print_env_summary() -> None:
    print("""
  ANTHROPIC_API_KEY   — console.anthropic.com → API Keys
  APIFY_TOKEN         — console.apify.com → Settings → Integrations
  YAHOO_EMAIL         — your IMAP email address
  YAHOO_APP_PASSWORD  — generate at security.yahoo.com → App passwords
  GOOGLE_SHEET_ID     — from your Google Sheet URL (the long ID in the middle)
""")


def step_rubric(profile: dict) -> dict:
    banner("Step 6 of 6 — Scoring Rubric")
    print("Claude uses this rubric to score job fit on a 0-100 scale.")
    print("Answer a few questions and we'll generate docs/fit-scoring-rubric.md for you.\n")
    print(f"  {YELLOW}You can always edit the generated file directly afterwards.{RESET}\n")

    # Check if already configured
    if RUBRIC_PATH.exists():
        content = RUBRIC_PATH.read_text(encoding="utf-8")
        if "[YOUR_TIER1_TITLE_1]" not in content:
            print_ok("fit-scoring-rubric.md already configured.")
            if not ask_yn("Re-generate (overwrites existing)?", False):
                return profile

    target_roles = profile.get("profile", {}).get("target_roles", [])

    # Title tiers
    print(f"{BOLD}Job Title Scoring (0-20 points){RESET}")
    print("How well does a job title match? We score in tiers.\n")

    print("Tier 1 (20 pts) — Primary target titles. You'd definitely apply.")
    tier1 = ask_list(
        "Primary target titles:",
        ", ".join(target_roles[:3]) if target_roles else "Analytics Manager, Data Analytics Lead"
    )

    print("\nTier 2 (15 pts) — Senior titles you'd also apply to (adjacent, slightly lower priority).")
    tier2 = ask_list("Senior adjacent titles:", "Senior Business Analyst, BI Manager")

    print("\nTier 3 (10 pts) — One level down. Only if the role is very interesting.")
    tier3_raw = ask("Single title (e.g. 'Senior Data Analyst')", "Senior Data Analyst")

    print("\nTier 4 (5 pts) — Borderline titles. Pipeline auto-rejects these by default.")
    tier4 = ask_list("Borderline titles:", "Business Analyst, Data Analyst")

    print("\nAuto-reject title patterns — always rejected (leave blank if none):")
    always_reject = ask("Title patterns to always reject (e.g. 'Junior, Intern, Graduate')", "", required=False)

    # Domain match
    print(f"\n{BOLD}Industry / Domain Scoring (0-25 points){RESET}")
    print("What types of companies or industries are you most interested in?\n")

    print("Primary domain (25 pts) — company types or industries you strongly prefer:")
    primary_domains = ask_list(
        "Primary industries/company types:",
        "product-led tech, fintech, ecommerce, SaaS, marketplace"
    )

    print("\nSecondary domain (15 pts) — acceptable industries:")
    secondary_domain = ask("Secondary industry (one description):", "financial services, media")

    print("\nNon-preferred (requires ≥88 score + well-known company):")
    non_preferred = ask("Non-preferred company types:", "staffing agency, outsourcing, body-shopping")

    print("\nPrimary tooling blocklist — auto-reject if this tool IS the entire job title:")
    tooling_block = ask("Tool name(s) in title to reject (e.g. 'SAP, Salesforce, Cobol')", "", required=False)

    # Skills
    print(f"\n{BOLD}Skills Scoring (0-25 points){RESET}")
    skills_raw = profile.get("core_skills", {}).get("skills", [])
    if skills_raw:
        print(f"  Current skills from your profile: {', '.join(skills_raw[:6])}")
        use_existing = ask_yn("Use these for skills scoring?", True)
    else:
        use_existing = False
    if use_existing:
        scoring_skills = skills_raw[:7]
    else:
        scoring_skills = ask_list("Top 7 skills for job matching:", "SQL, Python, Tableau, BigQuery")

    # Seniority
    print(f"\n{BOLD}Seniority Match (0-15 points){RESET}")
    years_exp = profile.get("profile", {}).get("years_of_experience", 5)
    seniority_desc = ask(
        "Describe your target seniority level:",
        f"Lead/Manager level — {years_exp}+ years experience expected"
    )

    # UK cities (only if UK is a target market)
    selected_markets = profile.get("_target_markets", [])
    uk_tier1 = uk_tier2 = uk_tier3 = ""
    if "uk" in selected_markets:
        print(f"\n{BOLD}UK Location Scoring (0-10 points){RESET}")
        print("Which UK cities/regions do you prefer?\n")
        uk_tier1 = ask("Tier 1 cities (10 pts, comma-separated):", "London")
        uk_tier2 = ask("Tier 2 cities (8 pts, comma-separated):", "Manchester, Birmingham")
        uk_tier3 = ask("Tier 3 cities (6 pts, comma-separated):", "Leeds, Reading, Cambridge, Oxford")

    _write_fit_scoring_rubric(
        rubric_path=RUBRIC_PATH,
        tier1=tier1, tier2=tier2, tier3=tier3_raw, tier4=tier4,
        always_reject=always_reject,
        primary_domains=primary_domains, secondary_domain=secondary_domain,
        non_preferred=non_preferred, tooling_block=tooling_block,
        skills=scoring_skills, seniority_desc=seniority_desc,
        uk_tier1=uk_tier1, uk_tier2=uk_tier2, uk_tier3=uk_tier3,
    )
    print_ok("Generated docs/fit-scoring-rubric.md")
    print(f"  {YELLOW}Review and adjust it — this directly affects which jobs get shortlisted.{RESET}")
    return profile


def _write_fit_scoring_rubric(
    rubric_path: Path,
    tier1: list, tier2: list, tier3: str, tier4: list,
    always_reject: str,
    primary_domains: list, secondary_domain: str,
    non_preferred: str, tooling_block: str,
    skills: list, seniority_desc: str,
    uk_tier1: str, uk_tier2: str, uk_tier3: str
) -> None:
    t1_str = " / ".join(tier1) if tier1 else "[YOUR_TIER1_TITLES]"
    t2_str = " / ".join(tier2) if tier2 else "[YOUR_TIER2_TITLES]"
    skill_lines = "\n    ".join(s for s in (skills + ["[add more skills]"])[:7])
    primary_domain_str = ", ".join(primary_domains) if primary_domains else "[YOUR_PRIMARY_DOMAINS]"
    reject_line = (
        f"    Auto-reject: {always_reject}"
        if always_reject
        else "    [No always-reject title patterns configured]"
    )
    tooling_line = (
        f"    Auto-reject if title is primarily: {tooling_block}"
        if tooling_block
        else "    [No tooling blocklist configured]"
    )

    uk_loc_block = ""
    if uk_tier1:
        uk_loc_block = f"""
    UK:  10 = {uk_tier1}
          8 = {uk_tier2 or 'Manchester, Birmingham'}
          6 = {uk_tier3 or 'Leeds, Reading, Cambridge'}
          0 = locations not listed above or outside UK"""

    content = f"""# docs/fit-scoring-rubric.md — Job Fit Scoring Rubric
# Generated by setup_wizard.py — edit to tune scoring for your profession.
# Claude reads this at session start via CLAUDE.md §4 import.
# Score range: 0–100. Auto-shortlist ≥75. Review Needed 60–74. Auto-reject <60.


[CONTEXT] Fit scoring is on a 0–100 scale. Breakdown:

  ROLE TITLE MATCH           (0–20 points)
    20 = Tier 1 — exact match for primary targets:
         {t1_str}
    15 = Tier 2 — senior adjacent titles:
         {t2_str}
    10 = Tier 3 — one level down:
         {tier3 or '[YOUR_TIER3_TITLE]'}
     5 = Tier 4 — borderline (pipeline may auto-reject):
         {" / ".join(tier4) if tier4 else "[YOUR_TIER4_TITLES]"}
     0 = Unrelated title
{reject_line}

  Human review queue priority within Review Needed (60–74):
    Sort by title tier (Tier 1 first), then fit_score within same tier.

  DOMAIN MATCH               (0–25 points)
    25 = {primary_domain_str}
    15 = {secondary_domain or '[YOUR_SECONDARY_DOMAIN]'}
     5 = {non_preferred or '[OTHER_INDUSTRIES]'}
     0 = Unrelated domain
    Note: {non_preferred or 'Non-preferred company types'} only if role score ≥ 88 AND well-known company.
{tooling_line}

  SKILLS MATCH               (0–25 points)
    Score based on overlap with:
    {skill_lines}
    25 = 7+ skills match
    15 = 4–6 skills match
     5 = 1–3 skills match

  SENIORITY MATCH            (0–15 points)
    15 = {seniority_desc}
    10 = Slightly senior (Director-adjacent) but reachable
     5 = Slightly junior but interesting scope
     0 = Clear mismatch (junior IC or VP+)

  LOCATION                   (0–10 points) — market-dependent:{uk_loc_block}
    NL:  10 = Amsterdam metro | 8 = Rotterdam/The Hague/Utrecht | 6 = Leiden/Hilversum | 0 = outside
    DE:  10 = Berlin | 8 = Munich/Frankfurt/Hamburg | 6 = Cologne/Düsseldorf | 4 = other DE cities | 0 = outside
    DK:  10 = Copenhagen metro | 8 = Aarhus | 0 = outside
    IE:  10 = Dublin metro | 8 = Cork | 6 = Galway/Limerick | 0 = outside
    SE:  10 = Stockholm | 8 = Gothenburg/Malmö | 0 = outside
    AE:  10 = Dubai | 8 = Abu Dhabi | 6 = Sharjah/Ajman | 0 = outside

  VISA SPONSORSHIP           (0–5 points)
    5  = JD explicitly confirms sponsorship available
    0  = JD silent on sponsorship (flag, do not reject)
   -10 = JD explicitly states no sponsorship → auto-reject
    Note: has_right_to_work markets auto-score 5 (no check needed)

[RULE] Auto-shortlist if score ≥ 75 AND visa is not rejected.
[RULE] Flag for human review if score 60–74.
[RULE] Auto-reject if score < 60 OR visa sponsorship explicitly denied.
"""
    rubric_path.parent.mkdir(parents=True, exist_ok=True)
    rubric_path.write_text(content, encoding="utf-8")


def _generate_claude_profile(profile: dict) -> None:
    """Generate docs/candidate-profile.md from candidate_profile.json.
    This is what Claude reads at session start for context about the candidate.
    """
    c = profile.get("contact", {})
    p = profile.get("profile", {})
    exp = profile.get("experience", [])
    skills = profile.get("core_skills", {}).get("skills", [])
    domains = {k: v for k, v in profile.get("domains", {}).items() if not k.startswith("_")}
    rtw = profile.get("has_right_to_work", {}).get("markets", [])
    visa_addrs = {k: v for k, v in profile.get("visa_addresses", {}).items() if not k.startswith("_")}

    name = c.get("name", "[YOUR_FULL_NAME]")
    location = c.get("address", "[YOUR_CITY, YOUR_COUNTRY]")
    years = p.get("years_of_experience", 0)
    target_roles = p.get("target_roles", [])
    seniority = p.get("target_seniority", "")
    industries = p.get("industry_history", {}).get("industries", [])

    # Build primary domain label
    primary_domain = next(
        (v.get("label", "your field") for k, v in domains.items() if k not in ("_doc", "general") and isinstance(v, dict)),
        "your field"
    )

    # Market/visa context
    if rtw:
        sponsorship_markets = [k for k in visa_addrs if k not in rtw]
        visa_note = f"Has right to work in: {', '.join(m.upper() for m in rtw)}."
        if sponsorship_markets:
            visa_note += f" Seeking sponsorship in: {', '.join(m.upper() for m in sponsorship_markets)}."
    elif visa_addrs:
        visa_note = "Requires visa sponsorship in all target markets. Only apply to roles explicitly stating visa sponsorship is available."
    else:
        visa_note = "Right to work status: configure in candidate_profile.json → has_right_to_work."

    # Experience bullets
    exp_lines = [
        f"  - {e.get('role', 'Your Role')} @ {e.get('company', 'Company')} ({e.get('dates', 'dates')})"
        for e in exp
    ]

    # Salary thresholds
    salary_thresholds = {k: v for k, v in profile.get("salary_thresholds", {}).items() if not k.startswith("_")}
    if salary_thresholds:
        salary_lines = "\n".join(f"  {k.upper()}: {v:,}" for k, v in salary_thresholds.items())
    else:
        salary_lines = "  [Configure in candidate_profile.json → salary_thresholds]"

    all_markets = list(visa_addrs.keys()) if visa_addrs else (rtw if rtw else [])
    markets_str = ", ".join(m.upper() for m in all_markets) if all_markets else "[Configure target markets]"

    content = f"""# docs/candidate-profile.md — Candidate Profile
# Generated by setup_wizard.py from candidate_profile.json.
# Re-run wizard to update, or edit this file directly.
# Claude reads this at session start via CLAUDE.md §2 import.


[CONTEXT] Name: {name}
[CONTEXT] Current location: {location}
[CONTEXT] Target markets: {markets_str}
[CONTEXT] Visa: {visa_note}

[CONTEXT] Total experience: {years}+ years in {primary_domain}

[CONTEXT] Career summary (reverse chronological):
{chr(10).join(exp_lines) if exp_lines else "  [Add your roles in candidate_profile.json → experience]"}

[CONTEXT] Target roles:
  {', '.join(target_roles) if target_roles else "[Configure in candidate_profile.json → profile.target_roles]"}

[CONTEXT] Target seniority: {seniority}

[CONTEXT] Core expertise areas (use these for JD matching):
  {', '.join(skills) if skills else "[Configure in candidate_profile.json → core_skills.skills]"}

[CONTEXT] Minimum salary thresholds (annual, local currency):
{salary_lines}

[CONTEXT] Industries worked in:
  {', '.join(industries) if industries else "[Configure in candidate_profile.json → profile.industry_history.industries]"}

[CONTEXT] Technical stack:
  {', '.join(skills) if skills else "[Configure in candidate_profile.json → core_skills.skills]"}

[CONTEXT] Data platform notes:
  [Configure in candidate_profile.json → profile.platform_notes to prevent tool mix-ups in cover letters]

[RULE] Excluded tools (cannot defend in interviews):
  [Configure in candidate_profile.json → profile.excluded_tools — blocked from Skills, Summary, and Cover Letters]

[CONTEXT] Team leadership:
  [Note team sizes in experience_bank.md bullets and candidate_profile.json → experience]
"""
    CANDIDATE_PROFILE_DOC.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_PROFILE_DOC.write_text(content, encoding="utf-8")
    print_ok("Generated docs/candidate-profile.md (Claude reads this at session start)")


def step_completion(profile: dict) -> None:
    banner("Setup Complete!")
    markets = profile.get("_target_markets", [])

    print(f"  {GREEN}✓ candidate_profile.json configured{RESET}")
    print(f"  {GREEN}✓ experience_bank.md template created{RESET}")
    print(f"  {GREEN}✓ search_config.json configured{RESET}")
    print(f"  {GREEN}✓ fit-scoring-rubric.md generated{RESET}")
    print(f"  {GREEN}✓ candidate-profile.md generated for Claude context{RESET}")

    print(f"""
{BOLD}What to do next:{RESET}

  1. {YELLOW}Fill in your .env{RESET}
     Open .env and add your API keys (see GUIDE.md §4 Step 1)

  2. {YELLOW}Fill in experience_bank.md{RESET}
     Replace the placeholder bullets with your real achievements
     (data/content/experience_bank.md)

  3. {YELLOW}Review docs/fit-scoring-rubric.md{RESET}
     This controls which jobs get shortlisted vs rejected.
     Adjust title tiers, domain scores, and skills to tune accuracy.

  4. {YELLOW}Run the integrity check{RESET}
     python3 scripts/check_workflow.py

  5. {YELLOW}Dry run (no API cost){RESET}
     python3 scripts/run_scout.py --dry-run

  6. {YELLOW}First live scout{RESET}
     python3 scripts/run_scout.py --market {markets[0] if markets else 'uk'} --yes

{BOLD}Want to customise further?{RESET}
  See {CYAN}GUIDE.md §6{RESET} for:
  • Scoring weights and thresholds
  • Adding/removing job title filters
  • Company blocklists and brand allowlists
  • Adding validation checks (V24+)
  • Swapping Claude models (Haiku vs Sonnet tradeoffs)
  • Configuring the referral outreach workflow
""")


def main() -> None:
    step_welcome()

    try:
        profile = load_existing_profile()

        # Strip template placeholders so we start fresh
        if profile.get("contact", {}).get("name") in ("YOUR FULL NAME", ""):
            profile = {}

        step_env()
        profile = step_contact(profile)
        profile = step_profession(profile)
        profile = step_experience(profile)
        profile = step_markets(profile)

        # Save here so _target_markets is persisted for step_rubric's UK city questions
        save_profile(profile)

        step_scout_urls(profile)
        profile = step_rubric(profile)

        # Remove internal wizard field before final save
        profile.pop("_target_markets", None)
        save_profile(profile)

        _generate_claude_profile(profile)
        step_completion(profile)

    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Setup cancelled — no changes saved.{RESET}\n")
        sys.exit(0)
    except Exception as e:
        print(f"\n{RED}Error: {e}{RESET}")
        print("Check your inputs and try again, or fill candidate_profile.json manually.")
        sys.exit(1)


if __name__ == "__main__":
    main()
