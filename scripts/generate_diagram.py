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
    from matplotlib.patches import FancyBboxPatch
except ImportError:
    print("matplotlib not installed — run: pip install matplotlib")
    sys.exit(1)


# ── Colours ───────────────────────────────────────────────────────────────────
DET   = "#4A90D9"    # blue  — deterministic / free
LLM   = "#E8760A"    # orange — LLM API cost
HUMAN = "#27AE60"    # green — human action
STORE = "#7F8C8D"    # grey  — storage / output
INPUT = "#8E44AD"    # purple — pipeline input
BG    = "#FAFAFA"
GROUP_SCOUT = "#D6EAF8"
GROUP_PREP  = "#FEF9E7"
TEXT_DARK   = "#1A1A2E"
TEXT_LIGHT  = "#FFFFFF"

# ── Canvas ────────────────────────────────────────────────────────────────────
FIG_W, FIG_H = 16, 30
X_MAX = 16
Y_MAX = 30

CX  = 8.0    # main column centre-x
BW  = 7.4    # standard node box width
BH  = 0.74   # standard node box height
GX  = 0.3    # group box left edge
GW  = 15.4   # group box width  (GX to GX+GW = 15.7)
GAP = 0.46   # gap between consecutive box edges
STEP = BH + GAP   # centre-to-centre vertical distance


# ── Drawing helpers ───────────────────────────────────────────────────────────

def _node(ax, x, y, w, h, label, sublabel, color,
          tc=TEXT_LIGHT, lfs=9.8, sfs=8.3):
    """Rounded rectangle with label + optional sublabel."""
    ax.add_patch(FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle="round,pad=0,rounding_size=0.20",
        linewidth=0, facecolor=color, zorder=3, clip_on=False,
    ))
    if sublabel:
        ax.text(x, y + h*0.17, label,
                ha="center", va="center", fontsize=lfs,
                color=tc, fontweight="bold", zorder=4, clip_on=False)
        ax.text(x, y - h*0.20, sublabel,
                ha="center", va="center", fontsize=sfs,
                color=tc, alpha=0.93, zorder=4, clip_on=False)
    else:
        ax.text(x, y, label,
                ha="center", va="center", fontsize=lfs,
                color=tc, fontweight="bold", zorder=4, clip_on=False)


def _arrow_down(ax, x, y_from, y_to, color="#606060"):
    ax.annotate("", xy=(x, y_to), xytext=(x, y_from),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.7, mutation_scale=15),
                zorder=2)


def _arrow_right(ax, x_from, x_to, y, label="", color="#C0392B"):
    ax.annotate("", xy=(x_to, y), xytext=(x_from, y),
                arrowprops=dict(arrowstyle="-|>", color=color,
                                lw=1.7, mutation_scale=15),
                zorder=2)
    if label:
        ax.text((x_from + x_to)/2, y + 0.22, label,
                ha="center", va="bottom", fontsize=8.2,
                color=color, style="italic", zorder=7, clip_on=False)


def _group(ax, y_bot, height, title, fill, border):
    ax.add_patch(FancyBboxPatch(
        (GX, y_bot), GW, height,
        boxstyle="round,pad=0,rounding_size=0.3",
        linewidth=1.8, edgecolor=border, facecolor=fill,
        zorder=1, alpha=0.50, clip_on=False,
    ))
    # Title sits ABOVE the group box border so it never collides with interior nodes
    ax.text(GX + GW/2, y_bot + height + 0.12, title,
            ha="center", va="bottom", fontsize=9.5,
            color=border, fontweight="bold", zorder=5, clip_on=False)


def _legend(ax, x, y, color, label):
    ax.add_patch(FancyBboxPatch(
        (x, y), 0.52, 0.32,
        boxstyle="round,pad=0,rounding_size=0.05",
        linewidth=0, facecolor=color, zorder=5, clip_on=False,
    ))
    ax.text(x + 0.70, y + 0.16, label,
            fontsize=8.8, va="center", color=TEXT_DARK,
            zorder=5, clip_on=False)


# ── Main diagram ──────────────────────────────────────────────────────────────

def draw() -> Path:
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, X_MAX)
    ax.set_ylim(0, Y_MAX)
    ax.axis("off")

    HH = BH / 2   # half box height

    # ── Title ─────────────────────────────────────────────────────────────────
    ax.text(CX, 29.50, "job-agent Pipeline Architecture",
            ha="center", va="center", fontsize=15.5,
            fontweight="bold", color=TEXT_DARK, clip_on=False)

    # ─────────────────── INPUT ────────────────────────────────────────────────
    y_input = 28.60
    _node(ax, CX, y_input, BW, BH,
          "LinkedIn Search URLs",
          "search_config.json  ·  Configured by setup_wizard.py Step 5",
          INPUT)

    # ─────────────────── SCOUT GROUP ──────────────────────────────────────────
    # Extra gap before first scout node creates room for the group title above the box
    SCOUT_TITLE_GAP = 0.70
    y = y_input - STEP - SCOUT_TITLE_GAP

    _arrow_down(ax, CX, y_input - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Apify LinkedIn Scraper",
          "[DET]  $0.001/job  ·  24-hour cache (free re-run same day)",
          DET)
    y_apify = y

    y -= STEP
    _arrow_down(ax, CX, y_apify - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Pass 1 Gates",
          "[DET]  Age · Title · Language · Blocklist · Dedup  ·  Free",
          DET)
    y_p1 = y

    # Side arrow → auto_rejected
    side_x_start = CX + BW/2
    side_x_end   = 14.05
    _arrow_right(ax, side_x_start, side_x_end - 0.95, y_p1, label="rejected")
    _node(ax, side_x_end, y_p1, 1.90, BH,
          "auto_rejected", ".json", STORE,
          tc=TEXT_LIGHT, lfs=8.5, sfs=8.0)

    y -= STEP
    _arrow_down(ax, CX, y_p1 - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Enrichment",
          "[DET]  Salary parse · Work mode detection · ATS URL extraction  ·  Free",
          DET)
    y_enrich = y

    y -= STEP
    _arrow_down(ax, CX, y_enrich - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Pass 2 — Claude Scoring",
          "[LLM — Haiku Batch]  ~$0.002–$0.005/job  ·  50% off real-time price",
          LLM)
    y_p2 = y

    SCORE_H = 0.84
    y -= STEP - BH/2 + SCORE_H/2
    _arrow_down(ax, CX, y_p2 - HH, y + SCORE_H/2)
    _node(ax, CX, y, BW, SCORE_H,
          "Score ≥ 75 → Shortlisted     |     60–74 → Review Needed",
          "< 60 or visa denied → auto_rejected.json",
          STORE, tc=TEXT_LIGHT, lfs=9.2, sfs=8.4)
    y_score = y
    SCORE_HH = SCORE_H / 2

    # Draw scout group behind all its nodes
    scout_top    = y_input - HH - 0.20   # just below input node bottom
    scout_bottom = y_score - SCORE_HH - 0.35
    _group(ax, scout_bottom, scout_top - scout_bottom,
           "Job Discovery — daily or on demand", GROUP_SCOUT, DET)

    # ─────────────────── SHEET → HUMAN → PULL ─────────────────────────────────
    y = y_score - SCORE_HH - GAP - HH
    _arrow_down(ax, CX, y_score - SCORE_HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Google Sheets Dashboard",
          "[DET]  sheets_sync.py push  ·  Free",
          DET)
    y_sheet = y

    y -= STEP
    _arrow_down(ax, CX, y_sheet - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "You: Review  →  Approve  →  Paste ATS URL",
          "Col H = Approved  ·  Col K = ATS URL  ·  (fill URL before setting Approved)",
          HUMAN)
    y_human = y

    y -= STEP
    _arrow_down(ax, CX, y_human - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Pull from Sheet",
          "[DET]  sheets_sync.py pull  ·  Syncs approvals and ATS URLs to local JSON",
          DET)
    y_pull = y

    # ─────────────────── APPLICATION PREP GROUP ───────────────────────────────
    prep_nodes = [
        ("Domain Detection",
         "[DET]  Keyword match vs candidate_profile.json → domains  ·  Free",    DET),
        ("Bullet Selection",
         "[DET]  Tag filter from experience_bank.md  ·  Free",                   DET),
        ("Profile Summary",
         "[LLM — Haiku Batch]  ~$0.002/app  ·  50% off real-time price",         LLM),
        ("Cover Letter",
         "[LLM — Sonnet Batch]  ~$0.05–$0.10/app  ·  50% off real-time price",   LLM),
        ("Validation V1–V23",
         "[DET]  Pre-render checks — blocks PDF on any FAIL  ·  Free",            DET),
        ("PDF Render",
         "[DET]  reportlab A4  ·  [YourName]_CV.pdf + CoverLetter.pdf  ·  Free", DET),
    ]

    # Pre-calculate y_pdf so prep_bottom is explicit (avoids straddle on boundary)
    y_pdf_calc  = y_pull - len(prep_nodes) * STEP
    prep_top    = y_pull - HH - 0.20       # just below pull node bottom
    prep_bottom = y_pdf_calc - HH - 0.50   # explicit 0.50 gap below last prep node
    _group(ax, prep_bottom, prep_top - prep_bottom,
           "Application Prep — per approved job", GROUP_PREP, "#C47A1A")

    y = y_pull - STEP
    y_prev = y_pull
    for label, sub, color in prep_nodes:
        _arrow_down(ax, CX, y_prev - HH, y + HH)
        _node(ax, CX, y, BW, BH, label, sub, color)
        y_prev = y
        y -= STEP
    y_pdf = y_prev   # last prep node (equals y_pdf_calc)

    # ─────────────────── OUTPUTS → APPLY → EMAIL → STATUS ────────────────────
    # Extra gap so outputs/ready/ sits clearly below the Application Prep group
    y = y_pdf - STEP - 0.45
    _arrow_down(ax, CX, y_pdf - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "outputs/ready/  ·  CV.pdf + CoverLetter.pdf",
          "[Company]_[Role]_[Date]/  ·  Open career_page_url from meta.json to apply",
          STORE, tc=TEXT_LIGHT)
    y_ready = y

    y -= STEP
    _arrow_down(ax, CX, y_ready - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "You: Apply via ATS Form",
          "Open career_page_url · Upload CV.pdf and CoverLetter.pdf",
          HUMAN)
    y_apply = y

    y -= STEP
    _arrow_down(ax, CX, y_apply - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Email Check",
          "[LLM — Haiku]  gmail_backfill.py  ·  ~$0.001/email  ·  50% off real-time",
          LLM)
    y_email = y

    y -= STEP
    _arrow_down(ax, CX, y_email - HH, y + HH)
    _node(ax, CX, y, BW, BH,
          "Status Update",
          "[DET]  job_tracker.json → Sheet  ·  Applied → Offer / Rejected",
          DET, lfs=9.5, sfs=7.8)
    y_status = y

    # ─────────────────── LEGEND ───────────────────────────────────────────────
    ly = max(0.55, y_status - BH/2 - 1.25)   # safe gap below last node
    ax.text(GX + 0.05, ly + 0.60, "Legend",
            fontsize=9.5, fontweight="bold", color=TEXT_DARK,
            clip_on=False)
    col_gap = (GW - 0.5) / 2.5
    items = [
        (GX + 0.05,          ly,        DET,   "[DET] Deterministic — no API cost"),
        (GX + 0.05 + col_gap, ly,       LLM,   "[LLM] Claude API — inference cost noted"),
        (GX + 0.05 + col_gap*2, ly,     HUMAN, "Human action required"),
        (GX + 0.05,          ly - 0.50, STORE, "Storage / output"),
        (GX + 0.05 + col_gap, ly - 0.50, INPUT, "Pipeline input"),
    ]
    for ix, iy, color, label in items:
        _legend(ax, ix, iy, color, label)

    # ─────────────────── Save ─────────────────────────────────────────────────
    out = ROOT / "docs" / "images" / "pipeline.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print(f"Saved: {out}  (y_status={y_status:.2f}  legend_y={ly:.2f})")
    return out


if __name__ == "__main__":
    draw()
