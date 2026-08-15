#!/usr/bin/env python3
"""
setup_wizard.py — Interactive setup for Claude-Workflow-Automation.

Guides you through the minimum configuration required to run your first scout.
Takes ~10 minutes. Advanced customisation is documented in GUIDE.md §6.

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

PROFILE_PATH   = ROOT / "data" / "content" / "candidate_profile.json"
EXPERIENCE_PATH = ROOT / "data" / "content" / "experience_bank.md"
ENV_PATH       = ROOT / ".env"
ENV_EXAMPLE    = ROOT / ".env.example"

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
║  Minimum config for your first scout run (~10 min)       ║
╚══════════════════════════════════════════════════════════╝{RESET}

This wizard configures the essentials. Everything can be tuned
later — see {CYAN}GUIDE.md §6{RESET} for the full customisation guide.

You will set up:
  1. Your contact details (name, email, phone, LinkedIn)
  2. Your target job titles and profession domain
  3. Your work experience (minimum 1 role)
  4. Your target markets and salary expectations
  5. Your LinkedIn search URLs for the job scout

Press Ctrl+C at any time to cancel without saving.
""")


def step_contact(profile: dict) -> dict:
    banner("Step 1 of 5 — Contact Details")
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
    banner("Step 2 of 5 — Profession & Target Roles")
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
            profile["profile"] = p
            return profile
    skills = ask_list("Top skills (1-8):", "SQL, Python, Tableau, BigQuery")
    profile["core_skills"] = {"skills": skills}

    profile["profile"] = p
    return profile


def step_experience(profile: dict) -> dict:
    banner("Step 3 of 5 — Work Experience")
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
    banner("Step 4 of 5 — Markets & Salary")
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

    # Salary
    print("\nSalary expectations (used to filter out below-threshold roles).")
    print(f"  {YELLOW}Enter your minimum acceptable salary for each market.{RESET}")
    print(f"  {YELLOW}This sets the gate in scripts/common.py — you'll update it there.{RESET}")
    print(f"  Example gates: UK £80k, NL €90k, DE €90k, UAE AED 360k\n")
    print(f"  {CYAN}Note: Update SALARY_THRESHOLDS in scripts/common.py after setup.{RESET}")
    print(f"  See GUIDE.md §6c for instructions.\n")

    return profile


def step_scout_urls(profile: dict) -> None:
    banner("Step 5 of 5 — LinkedIn Search URLs")
    markets = profile.get("_target_markets", ["uk"])
    geoid_map = {
        "uk": "101165590", "nl": "102890719", "de": "101282230",
        "dk": "104514075", "ie": "104738515", "se": "105117694", "ae": "104305776"
    }

    print("The scout runs LinkedIn searches via Apify ($0.001/job).")
    print("You need to create search URLs for your target roles.\n")
    print(f"{BOLD}How to build a LinkedIn search URL:{RESET}")
    print("  1. Go to https://www.linkedin.com/jobs")
    print("  2. Search for your target role + location")
    print("  3. Apply filters: Date Posted = Past 24 hours, Experience Level = Mid-Senior/Director")
    print("  4. Copy the URL from your browser\n")

    for market in markets:
        gid = geoid_map.get(market, "YOUR_GEO_ID")
        print(f"  {CYAN}Market: {market.upper()} — geoId = {gid}{RESET}")
        print(f"  Example URL: https://www.linkedin.com/jobs/search?keywords=YOUR+ROLE&geoId={gid}&f_TPR=r86400&f_E=4%2C5")

    target_roles = profile.get("profile", {}).get("target_roles", ["Your Role"])
    print(f"\nYour target roles: {', '.join(target_roles[:3])}")
    print(f"\n  {YELLOW}Add your search URLs in scripts/run_scout.py → SEARCHES_APIFY list.{RESET}")
    print(f"  See GUIDE.md §4 Step 5 for detailed instructions.")
    print(f"\n  Format: (\"Label\", \"LinkedIn_URL\", max_jobs)")
    print(f"  Example: (\"Your Role Title\", \"https://www.linkedin.com/jobs/search?...\", 100)")


def step_env() -> None:
    banner("Environment Variables (.env)")
    if ENV_PATH.exists():
        print_ok(".env already exists.")
        if ask_yn("View required variables?", False):
            _print_env_summary()
        return

    if not ENV_EXAMPLE.exists():
        print_warn(".env.example not found. Create .env manually (see GUIDE.md §4 Step 1).")
        return

    print("Copying .env.example → .env for you to fill in.\n")
    import shutil
    shutil.copy(ENV_EXAMPLE, ENV_PATH)
    print_ok("Created .env from .env.example")
    print(f"\n  {YELLOW}Required: open .env and fill in:{RESET}")
    _print_env_summary()


def _print_env_summary() -> None:
    print("""
  ANTHROPIC_API_KEY   — console.anthropic.com → API Keys
  APIFY_TOKEN         — console.apify.com → Settings → Integrations
  YAHOO_EMAIL         — your IMAP email address
  YAHOO_APP_PASSWORD  — generate at security.yahoo.com → App passwords
  GOOGLE_SHEET_ID     — from your Google Sheet URL (the long ID in the middle)
""")


def step_completion(profile: dict) -> None:
    banner("Setup Complete!")
    markets = profile.get("_target_markets", [])

    print(f"  {GREEN}✓ candidate_profile.json configured{RESET}")
    print(f"  {GREEN}✓ experience_bank.md template created{RESET}")

    print(f"""
{BOLD}What to do next:{RESET}

  1. {YELLOW}Fill in your .env{RESET}
     Open .env and add your API keys (see GUIDE.md §4 Step 1)

  2. {YELLOW}Fill in experience_bank.md{RESET}
     Replace the placeholder bullets with your real achievements
     (data/content/experience_bank.md)

  3. {YELLOW}Add LinkedIn search URLs{RESET}
     Open scripts/run_scout.py and fill in SEARCHES_APIFY
     (see GUIDE.md §4 Step 5 for how to build URLs)

  4. {YELLOW}Set salary thresholds{RESET}
     Open scripts/common.py and update SALARY_THRESHOLDS for your markets

  5. {YELLOW}Run the integrity check{RESET}
     python3 scripts/check_workflow.py

  6. {YELLOW}Dry run (no API cost){RESET}
     python3 scripts/run_scout.py --dry-run

  7. {YELLOW}First live scout{RESET}
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

        # Remove internal wizard field before saving
        profile.pop("_target_markets", None)

        save_profile(profile)
        step_scout_urls(profile)
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
