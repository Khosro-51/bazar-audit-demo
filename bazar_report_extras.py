"""
bazar_report_extras.py — v2.1 psychological conversion layer
Four elements added to the downloadable HTML report:
  1. Bazar Score (0-100) — memorable single metric
  2. Recoverable-money card — counterfactual loss aversion
  3. Journey progress bar — Zeigarnik / path incompletion
  4. Level-2 CTA — click tracked in access_log (no fake scarcity)
"""
from __future__ import annotations
import math


# ── 1. BAZAR SCORE ────────────────────────────────────────────────────────────

def bazar_score(result: dict) -> int:
    """
    Composite 0-100 score from engine metrics.
    Lower = more problems to fix (motivates improvement).
    Formula:
      pf_score   (40 pts): PF 0→1.5 mapped linearly, capped at 40
      wr_score   (25 pts): WR vs breakeven WR gap (-20pp→+20pp)
      discipline (20 pts): penalise HIGH findings, reward no HIGH
      cliff_pen  (15 pts): deduct if TRADE_COUNT_CLIFF is HIGH/MEDIUM
    """
    cm = result.get("core_metrics", {})
    insights = result.get("insights", [])

    pf = cm.get("profit_factor", 0) or 0
    wr = cm.get("win_rate", 0) or 0
    bwr = cm.get("breakeven_wr", 0.5) or 0.5

    # pf score: 0 at PF=0, 40 at PF>=1.5
    pf_score = min(40, max(0, (pf / 1.5) * 40))

    # wr score: 25 at wr == bwr+0.20, 0 at wr == bwr-0.20
    wr_gap = wr - bwr  # -0.20 → +0.20 typical range
    wr_score = min(25, max(0, ((wr_gap + 0.20) / 0.40) * 25))

    # discipline: start 20, -7 per HIGH finding, -3 per MEDIUM finding
    disc = 20
    for ins in insights:
        sev = ins.get("severity", "")
        obs = (ins.get("metric_snapshot") or {}).get("observation", False)
        if obs:
            continue  # observations don't penalise
        if sev == "HIGH":
            disc -= 7
        elif sev == "MEDIUM":
            disc -= 3
    disc = max(0, disc)

    # cliff penalty: -10 if TRADE_COUNT_CLIFF is MEDIUM/HIGH
    cliff_pen = 0
    for ins in insights:
        if ins.get("insight_id") == "TRADE_COUNT_CLIFF":
            if ins.get("severity") in ("MEDIUM", "HIGH"):
                cliff_pen = 10
    cliff_score = 15 - cliff_pen

    raw = pf_score + wr_score + disc + cliff_score
    return max(0, min(100, round(raw)))


def score_label(score: int, lang: str) -> str:
    """Human label for the score band."""
    bands = {
        "en": [
            (80, "Strong"),
            (60, "Developing"),
            (40, "Needs Work"),
            (0,  "Critical"),
        ],
        "fa": [
            (80, "قوی"),
            (60, "در حال رشد"),
            (40, "نیاز به بهبود"),
            (0,  "بحرانی"),
        ],
        "ar": [
            (80, "قوي"),
            (60, "في تطور"),
            (40, "يحتاج عمل"),
            (0,  "حرج"),
        ],
    }
    for threshold, label in bands.get(lang, bands["en"]):
        if score >= threshold:
            return label
    return ""


def score_color(score: int) -> str:
    if score >= 60:
        return "#00E5A0"
    if score >= 40:
        return "#FFB020"
    return "#FF4757"


def bazar_score_html(result: dict, lang: str) -> str:
    score = bazar_score(result)
    color = score_color(score)
    label = score_label(score, lang)
    pct = score  # for arc fill

    titles = {"en": "Bazar Score", "fa": "نمره بازار", "ar": "نقاط بازار"}
    subs   = {
        "en": "Composite trading health (0–100)",
        "fa": "سلامت کلی معاملات (۰–۱۰۰)",
        "ar": "صحة التداول الشاملة (٠–١٠٠)",
    }
    title = titles.get(lang, titles["en"])
    sub   = subs.get(lang, subs["en"])

    # SVG arc
    r = 54
    circ = 2 * math.pi * r
    dash = circ * score / 100
    gap  = circ - dash

    return f"""
<div class="bz-score-block">
  <div class="bz-score-title">{title}</div>
  <div class="bz-score-ring">
    <svg width="140" height="140" viewBox="0 0 140 140">
      <circle cx="70" cy="70" r="{r}" fill="none" stroke="#1C2530" stroke-width="12"/>
      <circle cx="70" cy="70" r="{r}" fill="none" stroke="{color}" stroke-width="12"
              stroke-dasharray="{dash:.1f} {gap:.1f}"
              stroke-dashoffset="{circ/4:.1f}"
              stroke-linecap="round"/>
    </svg>
    <div class="bz-score-num" style="color:{color}">{score}</div>
  </div>
  <div class="bz-score-label" style="color:{color}">{label}</div>
  <div class="bz-score-sub">{sub}</div>
</div>"""


# ── 2. RECOVERABLE MONEY CARD ─────────────────────────────────────────────────

def recoverable_card_html(insights: list, lang: str) -> str:
    """
    Extract counterfactual deltas from SESSION_TOXICITY and SYMBOL_NO_EDGE.
    Show total 'recoverable' dollars from removing losing segments.
    Strictly based on engine counterfactual numbers — no invented values.
    """
    items = []
    for ins in insights:
        snap = ins.get("metric_snapshot") or {}
        cf = snap.get("counterfactual") or {}
        if not cf:
            continue
        cur = cf.get("current_net_pnl")
        without = cf.get("net_pnl_without_segment")
        if cur is None or without is None:
            continue
        delta = without - cur
        if delta <= 0:
            continue
        seg_key = ins.get("insight_id", "")
        if seg_key == "SESSION_TOXICITY":
            worst = snap.get("worst_session", {})
            seg_name = worst.get("session", "")
        elif seg_key == "SYMBOL_NO_EDGE":
            worst = snap.get("worst_symbol", {})
            seg_name = worst.get("symbol", "")
        else:
            seg_name = seg_key
        items.append((seg_name, delta))

    if not items:
        return ""

    total = sum(d for _, d in items)

    titles = {
        "en": "Recoverable from Past Data",
        "fa": "قابل بازیابی از داده گذشته",
        "ar": "قابل الاسترداد من البيانات السابقة",
    }
    notes = {
        "en": "Based on your actual trades — retrospective, not a promise.",
        "fa": "بر اساس معاملات واقعی شما — گذشته‌نگر، نه وعده.",
        "ar": "بناءً على صفقاتك الفعلية — استرجاعي، وليس وعداً.",
    }
    rows_html = ""
    for seg, delta in items:
        rows_html += f'<div class="bz-cf-row"><span>{seg}</span><span class="bz-cf-num">+{delta:,.0f}$</span></div>\n'

    return f"""
<div class="bz-recover-block">
  <div class="bz-recover-title">{titles.get(lang, titles["en"])}</div>
  <div class="bz-recover-total">+{total:,.0f}$</div>
  {rows_html}
  <div class="bz-recover-note">{notes.get(lang, notes["en"])}</div>
</div>"""


# ── 3. JOURNEY BAR ────────────────────────────────────────────────────────────

def journey_bar_html(lang: str) -> str:
    labels = {
        "en": ["Audit ✓", "Playbook", "Mentor"],
        "fa": ["آدیت ✓", "پلی‌بوک", "منتور"],
        "ar": ["التدقيق ✓", "دليل اللعب", "المرشد"],
    }
    heads  = {
        "en": "Your Journey",
        "fa": "مسیر شما",
        "ar": "رحلتك",
    }
    steps = labels.get(lang, labels["en"])
    head  = heads.get(lang, heads["en"])
    items_html = ""
    for i, step in enumerate(steps):
        active = "bz-step-done" if i == 0 else "bz-step-locked"
        lock   = "" if i == 0 else "🔒 "
        items_html += f'<div class="bz-step {active}">{lock}{step}</div>'
        if i < len(steps) - 1:
            items_html += '<div class="bz-step-arrow">→</div>'

    return f"""
<div class="bz-journey-block">
  <div class="bz-journey-head">{head}</div>
  <div class="bz-journey-steps">{items_html}</div>
</div>"""


# ── 4. LEVEL-2 CTA ────────────────────────────────────────────────────────────

def cta_block_html(lang: str, email: str = "") -> str:
    """
    Waitlist CTA for Level 2 (Playbook Engine).
    Click is not tracked here — tracking is done in streamlit_app.py via log_access.
    The button links back to the app with ?cta=l2 so the app can log the click.
    """
    titles = {
        "en": "Ready to build your Personal Playbook?",
        "fa": "آماده ساخت پلی‌بوک شخصی‌ات هستی؟",
        "ar": "هل أنت مستعد لبناء دليل اللعب الشخصي؟",
    }
    bodies = {
        "en": "Level 2 personalises your trading rules based on what your data actually proves — not guesses.",
        "fa": "سطح ۲ قوانین ترید تو را بر اساس آنچه داده‌ات واقعاً ثابت کرده شخصی‌سازی می‌کند — نه حدس.",
        "ar": "المستوى الثاني يخصص قواعد تداولك بناءً على ما يثبته بياناتك فعلاً — لا التخمينات.",
    }
    btns = {
        "en": "Join Waitlist for Level 2 →",
        "fa": "ثبت‌نام در لیست انتظار سطح ۲ ←",
        "ar": "الانضمام إلى قائمة الانتظار للمستوى الثاني ←",
    }

    return f"""
<div class="bz-cta-block">
  <div class="bz-cta-title">{titles.get(lang, titles["en"])}</div>
  <div class="bz-cta-body">{bodies.get(lang, bodies["en"])}</div>
  <a class="bz-cta-btn" href="?cta=l2" target="_blank">{btns.get(lang, btns["en"])}</a>
</div>"""


# ── EXTRA CSS (injected into _REPORT_CSS) ────────────────────────────────────

EXTRAS_CSS = """
/* ── Bazar Score ── */
.bz-score-block{text-align:center;padding:28px 0 20px;border-bottom:1px solid #1C2530;margin-bottom:24px;}
.bz-score-title{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#8892a4;margin-bottom:12px;}
.bz-score-ring{position:relative;display:inline-block;width:140px;height:140px;}
.bz-score-num{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:38px;font-weight:700;font-family:'JetBrains Mono',monospace;}
.bz-score-label{font-size:18px;font-weight:600;margin-top:8px;}
.bz-score-sub{font-size:11px;color:#8892a4;margin-top:4px;}

/* ── Recoverable card ── */
.bz-recover-block{background:#0D1117;border:1px solid #1C2530;border-left:3px solid #00E5A0;border-radius:8px;padding:18px 20px;margin:20px 0;}
.bz-recover-title{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8892a4;margin-bottom:8px;}
.bz-recover-total{font-size:32px;font-weight:700;color:#00E5A0;font-family:'JetBrains Mono',monospace;margin-bottom:10px;}
.bz-cf-row{display:flex;justify-content:space-between;font-size:13px;color:#c9d1d9;padding:3px 0;}
.bz-cf-num{color:#00E5A0;font-family:'JetBrains Mono',monospace;}
.bz-recover-note{font-size:11px;color:#586069;margin-top:10px;font-style:italic;}

/* ── Journey bar ── */
.bz-journey-block{margin:24px 0;text-align:center;}
.bz-journey-head{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8892a4;margin-bottom:10px;}
.bz-journey-steps{display:flex;justify-content:center;align-items:center;gap:8px;flex-wrap:wrap;}
.bz-step{padding:7px 16px;border-radius:20px;font-size:13px;font-weight:600;}
.bz-step-done{background:#00E5A0;color:#07090C;}
.bz-step-locked{background:#1C2530;color:#586069;border:1px dashed #2d3748;}
.bz-step-arrow{color:#586069;font-size:16px;}

/* ── Level-2 CTA ── */
.bz-cta-block{background:linear-gradient(135deg,#0D1117 0%,#0a1628 100%);border:1px solid #00E5A0;border-radius:10px;padding:24px;margin:28px 0 10px;text-align:center;}
.bz-cta-title{font-size:17px;font-weight:700;color:#e6edf3;margin-bottom:10px;}
.bz-cta-body{font-size:13px;color:#8892a4;margin-bottom:18px;line-height:1.6;}
.bz-cta-btn{display:inline-block;padding:11px 28px;background:#00E5A0;color:#07090C;font-weight:700;font-size:14px;border-radius:6px;text-decoration:none;letter-spacing:.03em;}
.bz-cta-btn:hover{background:#00c98a;}
"""
