"""
Generate a coloured pipeline architecture diagram → docs/images/pipeline.png
Run: python3 scripts/generate_diagram.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
except ImportError:
    print("matplotlib not installed — run: pip install matplotlib")
    sys.exit(1)


# ── Colour palette ────────────────────────────────────────────────────────────
DET   = "#4A90D9"    # blue  — deterministic / free
LLM   = "#E8760A"    # orange — LLM / API cost
HUMAN = "#27AE60"    # green — human decision
STORE = "#7F8C8D"    # grey  — storage / output
INPUT = "#8E44AD"    # purple — pipeline input
BG    = "#FAFAFA"    # near-white background
GROUP_SCOUT = "#EBF5FB"   # light blue group box
GROUP_PREP  = "#FEF9E7"   # light amber group box

TEXT_DARK  = "#1A1A2E"    # dark text on light boxes
TEXT_LIGHT = "#FFFFFF"    # white text on dark boxes

FIG_W, FIG_H = 13, 21


def _box(ax, x, y, w, h, label, sublabel, color, text_color=TEXT_LIGHT, radius=0.25, fontsize=9):
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=0,
        facecolor=color,
        zorder=3,
    )
    ax.add_patch(box)
    if sublabel:
        ax.text(x, y + 0.12, label, ha="center", va="center",
                fontsize=fontsize, color=text_color, fontweight="bold", zorder=4)
        ax.text(x, y - 0.18, sublabel, ha="center", va="center",
                fontsize=7.5, color=text_color, alpha=0.88, zorder=4)
    else:
        ax.text(x, y, label, ha="center", va="center",
                fontsize=fontsize, color=text_color, fontweight="bold", zorder=4)


def _arrow(ax, x1, y1, x2, y2, label="", color="#444"):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>", color=color,
            lw=1.5, mutation_scale=14,
        ),
        zorder=2,
    )
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(mx + 0.08, my, label, fontsize=7.5, color=color,
                ha="left", va="center", style="italic", zorder=4)


def _group_box(ax, x, y, w, h, title, color, title_color):
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0,rounding_size=0.3",
        linewidth=1.5, edgecolor=title_color, facecolor=color,
        zorder=1, alpha=0.5,
    )
    ax.add_patch(rect)
    ax.text(x + 0.25, y + h - 0.28, title,
            fontsize=8.5, color=title_color, fontweight="bold",
            ha="left", va="top", zorder=2)


def _legend_item(ax, x, y, color, label):
    box = FancyBboxPatch((x, y), 0.45, 0.28,
                         boxstyle="round,pad=0,rounding_size=0.05",
                         linewidth=0, facecolor=color, zorder=4)
    ax.add_patch(box)
    ax.text(x + 0.6, y + 0.14, label, fontsize=8, va="center", color=TEXT_DARK, zorder=4)


def draw() -> Path:
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 21)
    ax.axis("off")

    BW = 4.8   # box width (standard)
    BH = 0.65  # box height (standard)
    CX = 6.5   # centre x of main column

    # ── Title ────────────────────────────────────────────────────────────────
    ax.text(CX, 20.55, "job-agent Pipeline Architecture",
            ha="center", va="center", fontsize=14, fontweight="bold", color=TEXT_DARK)

    # ── Input ────────────────────────────────────────────────────────────────
    _box(ax, CX, 19.85, BW, BH,
         "LinkedIn Search URLs", "search_config.json  ·  setup_wizard.py Step 5",
         INPUT)

    _arrow(ax, CX, 19.52, CX, 19.12)

    # ── SCOUT group ──────────────────────────────────────────────────────────
    _group_box(ax, 1.3, 12.85, 10.4, 6.55, "Job Discovery — daily or on demand",
               GROUP_SCOUT, DET)

    _box(ax, CX, 18.85, BW, BH,
         "Apify LinkedIn Scraper", "[DET]  $0.001/job  ·  24h cache (free re-run)",
         DET)

    _arrow(ax, CX, 18.52, CX, 18.12)

    _box(ax, CX, 17.85, BW, BH,
         "Pass 1 Gates", "[DET]  Age · Title · Language · Dedup  ·  Free",
         DET)

    # Side reject arrow
    _arrow(ax, 8.9, 17.85, 11.0, 17.85, label="rejected", color="#C0392B")
    _box(ax, 11.65, 17.85, 1.65, BH,
         "auto_rejected", ".json", STORE, text_color=TEXT_LIGHT, fontsize=8)

    _arrow(ax, CX, 17.52, CX, 17.12)

    _box(ax, CX, 16.85, BW, BH,
         "Enrichment", "[DET]  Salary parse · Work mode · ATS URL  ·  Free",
         DET)

    _arrow(ax, CX, 16.52, CX, 16.12)

    _box(ax, CX, 15.85, BW, BH,
         "Pass 2 — Claude Scoring", "[LLM — Haiku Batch]  ~$0.002–0.005/job  ·  50% off",
         LLM)

    _arrow(ax, CX, 15.52, CX, 15.12)

    # ── Score routing ─────────────────────────────────────────────────────────
    _box(ax, CX, 14.85, BW, BH,
         "Score ≥ 75 → Shortlisted      60–74 → Review Needed",
         "< 60 or visa denied → auto_rejected.json",
         STORE, text_color=TEXT_LIGHT, fontsize=8.5)

    _arrow(ax, CX, 14.52, CX, 14.12)

    # ── Sheets → Human → Pull ────────────────────────────────────────────────
    _box(ax, CX, 13.85, BW, BH,
         "Google Sheets Dashboard", "[DET]  sheets_sync.py push  ·  Free",
         DET)

    _arrow(ax, CX, 13.52, CX, 13.12)

    _box(ax, CX, 12.85, BW, BH,
         "You: Review  →  Approve  →  Paste ATS URL",
         "Col H = Approved  ·  Col K = ATS URL",
         HUMAN)

    _arrow(ax, CX, 12.52, CX, 12.12)

    _box(ax, CX, 11.85, BW, BH,
         "Pull from Sheet", "[DET]  sheets_sync.py pull  ·  Syncs approvals + URLs",
         DET)

    _arrow(ax, CX, 11.52, CX, 11.12)

    # ── APPLICATION PREP group ────────────────────────────────────────────────
    _group_box(ax, 1.3, 5.35, 10.4, 6.05, "Application Prep — per approved job",
               GROUP_PREP, "#D4A017")

    PBHALF = 0.38
    items = [
        (10.85, "Domain Detection",    "[DET]  Keyword match vs candidate_profile.json",  DET),
        (10.15, "Bullet Selection",    "[DET]  Tag filter from experience_bank.md",        DET),
        (9.45,  "Profile Summary",     "[LLM — Haiku Batch]  ~$0.002/app",                LLM),
        (8.75,  "Cover Letter",        "[LLM — Sonnet Batch]  ~$0.05–0.10/app",           LLM),
        (8.05,  "Validation V1–V23",   "[DET]  Blocks PDF render on FAIL",                DET),
        (7.35,  "PDF Render",          "[DET]  reportlab  ·  CV.pdf + CoverLetter.pdf",   DET),
    ]
    for i, (y, label, sub, color) in enumerate(items):
        _box(ax, CX, y, BW, BH, label, sub, color)
        if i < len(items) - 1:
            _arrow(ax, CX, y - PBHALF, CX, items[i + 1][0] + PBHALF)

    _arrow(ax, CX, 7.35 - PBHALF, CX, 6.0)

    # ── Output + Apply ────────────────────────────────────────────────────────
    _box(ax, CX, 5.65, BW, BH,
         "outputs/ready/  ·  CV.pdf + CoverLetter.pdf",
         "[Company]_[Role]_[Date]/",
         STORE, text_color=TEXT_LIGHT)

    _arrow(ax, CX, 5.32, CX, 4.92)

    _box(ax, CX, 4.65, BW, BH,
         "You: Apply via ATS Form",
         "Open career_page_url from meta.json",
         HUMAN)

    _arrow(ax, CX, 4.32, CX, 3.92)

    _box(ax, CX, 3.65, BW, BH,
         "Email Check", "[LLM — Haiku]  gmail_backfill.py  ·  ~$0.001/email",
         LLM)

    _arrow(ax, CX, 3.32, CX, 2.92)

    _box(ax, CX, 2.65, BW, BH,
         "Status Update", "[DET]  job_tracker.json → Sheet  ·  Applied → Under Review → Offer/Rejected",
         DET, fontsize=8.2)

    # ── Legend ────────────────────────────────────────────────────────────────
    lx, ly = 1.45, 1.35
    ax.text(lx, ly + 0.42, "Legend", fontsize=8.5, fontweight="bold", color=TEXT_DARK)
    _legend_item(ax, lx,       ly,       DET,   "[DET] Deterministic — no API cost")
    _legend_item(ax, lx + 3.5, ly,       LLM,   "[LLM] Claude API — inference cost noted")
    _legend_item(ax, lx + 7.0, ly,       HUMAN, "Human action required")
    _legend_item(ax, lx,       ly - 0.38, STORE, "Storage / output")
    _legend_item(ax, lx + 3.5, ly - 0.38, INPUT, "Pipeline input")

    # ── Save ─────────────────────────────────────────────────────────────────
    out = ROOT / "docs" / "images" / "pipeline.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved: {out}")
    return out


if __name__ == "__main__":
    draw()
