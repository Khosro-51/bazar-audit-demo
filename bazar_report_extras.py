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

# D4 fix: use the engine's single significance constant instead of a stray 0.05.
# A finding is only "confirmed" when the engine judged it significant
# (observation is False ⇔ p < ALPHA_FINDING), so the threshold must match.
try:
    from bazar_insights import ALPHA_FINDING
except Exception:  # keep this module importable standalone
    ALPHA_FINDING = 0.015


# ── 1. BAZAR SCORE ────────────────────────────────────────────────────────────
# D2 fix: the single source of truth for the Bazar Score is
# streamlit_app.compute_bazar_score(). The previous duplicate formula that lived
# here (PF/WR/discipline/cliff) diverged from the app's documented formula
# (Edge/Consistency/Discipline/Data) and produced a different number in the
# downloadable report than the one the product describes. It was removed; the
# canonical score is now computed by the caller and passed into bazar_score_html().


def score_label(score: int, lang: str, exp_r: float = 0.0) -> str:
    """Human label for the score band. If exp_r<0 and score in 60-79, flag as inconclusive."""
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
    inc_suffix = {"en": " — inconclusive sample", "fa": " — شواهد ناکافی", "ar": " — عينة غير حاسمة"}
    for threshold, label in bands.get(lang, bands["en"]):
        if score >= threshold:
            # if negative expectancy but score in 'Developing' band, add qualifier
            if exp_r < 0 and 60 <= score < 80:
                return label + inc_suffix.get(lang, inc_suffix["en"])
            return label
    return ""


def score_color(score: int) -> str:
    if score >= 60:
        return "#00E5A0"
    if score >= 40:
        return "#FFB020"
    return "#FF4757"


def bazar_score_html(result: dict, lang: str, score: int) -> str:
    # `score` is the canonical Bazar Score, computed once by the caller
    # (streamlit_app.compute_bazar_score) and passed in — see D2 fix above.
    exp_r = (result.get("core_metrics") or {}).get("expectancy_R", 0) or 0
    # if expectancy is negative, cap color at amber regardless of score
    color = score_color(score) if exp_r >= 0 else ("#FFB020" if score >= 40 else "#FF4757")
    label = score_label(score, lang, exp_r)
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
    # split by evidence: confirmed (significant per the engine, not obs) vs watchlist
    confirmed_items = []
    watch_items = []
    for seg, delta in items:
        # find the matching insight to check p_value and observation
        p_val = None
        is_obs = True
        for ins in insights:
            snap2 = ins.get("metric_snapshot") or {}
            seg_key = ins.get("insight_id", "")
            ws = snap2.get("worst_session") or snap2.get("worst_symbol") or {}
            seg_name2 = ws.get("session") or ws.get("symbol") or ""
            if seg_name2 == seg:
                p_val  = snap2.get("p_value")
                is_obs = bool(snap2.get("observation", True))
                break
        if not is_obs and p_val is not None and p_val < ALPHA_FINDING:
            confirmed_items.append((seg, delta))
        else:
            watch_items.append((seg, delta, p_val))

    parts = []

    if confirmed_items:
        total_c = sum(d for _, d in confirmed_items)
        rows_c = "".join(f'<div class="bz-cf-row"><span>{s}</span><span class="bz-cf-num">+{d:,.0f}$</span></div>' for s,d in confirmed_items)
        ctitles = {"en":"Confirmed Recoverable","fa":"بازیابی تأییدشده","ar":"قابل استرداد مؤكد"}
        cnotes  = {"en":"Statistically confirmed — retrospective, not a guarantee.","fa":"تأیید آماری — گذشته‌نگر، نه تضمین.","ar":"مؤكد إحصائيًا — استرجاعي وليس ضمانا."}
        parts.append(f'<div class="bz-recover-block"><div class="bz-recover-title">{ctitles.get(lang,ctitles["en"])}</div><div class="bz-recover-total">+{total_c:,.0f}$</div>{rows_c}<div class="bz-recover-note">{cnotes.get(lang,cnotes["en"])}</div></div>')
    else:
        msgs = {"en":"No statistically confirmed recoverable drag yet. Keep logging trades.","fa":"هنوز هیچ زیانی تأییدشده‌ای وجود ندارد. به ثبت معاملات ادامه دهید.","ar":"لا مؤكد إحصائيًا حتى الآن."}
        parts.append(f'<div class="bz-recover-block bz-recover-neutral"><div class="bz-recover-note" style="font-size:13px">{msgs.get(lang,msgs["en"])}</div></div>')

    if watch_items:
        wtitles = {"en":"Watchlist Drag (unconfirmed)","fa":"زیان مشاهده‌شده (تأییدنشده)","ar":"خسائر ملاحظة (غير مؤكدة)"}
        wnotes  = {"en":"Historical what-if only. Not confirmed improvement opportunities.","fa":"فقط اعداد فرضی گذشته. فرصت بهبود تأیید نشده.","ar":"أرقام افتراضية تاريخية فقط."}
        wrows = "".join(
            f'<div class="bz-cf-row"><span>{s}</span><span class="bz-watch-num">~+{d:,.0f}$</span>{(" <span class=bz-watch-p>(p="+f"{p:.2f})</span>") if p is not None else ""}</div>'
            for s,d,p in watch_items
        )
        parts.append(f'<div class="bz-watch-block"><div class="bz-recover-title">{wtitles.get(lang,wtitles["en"])}</div>{wrows}<div class="bz-recover-note">{wnotes.get(lang,wnotes["en"])}</div></div>')

    return "\n".join(parts)


# ── 3. EQUITY CURVE ───────────────────────────────────────────────────────────────────

def equity_curve_html(result: dict, lang: str) -> str:
    """
    Inline SVG equity curve (cumulative PnL over trade number).
    Annotates session/symbol from trade_meta if available.
    Observations get markers only; confirmed findings could get a dashed counterfactual line.
    """
    pnl_series = result.get("pnl_series") or []
    trade_meta = result.get("trade_meta") or []
    if len(pnl_series) < 2:
        return ""

    # cumulative pnl
    cum = []
    total = 0.0
    for p in pnl_series:
        total += p
        cum.append(total)

    n       = len(cum)
    W, H    = 660, 220
    PAD_L, PAD_R, PAD_T, PAD_B = 52, 16, 16, 36
    chart_w = W - PAD_L - PAD_R
    chart_h = H - PAD_T - PAD_B

    y_min = min(cum)
    y_max = max(cum)
    y_range = y_max - y_min if y_max != y_min else 1

    def cx(i):  return PAD_L + (i / (n - 1)) * chart_w
    def cy(v):  return PAD_T + chart_h - ((v - y_min) / y_range) * chart_h

    # get toxic segment names from insights
    watch_sessions = set()
    watch_symbols  = set()
    for ins in result.get("insights", []):
        snap = ins.get("metric_snapshot") or {}
        sid  = ins.get("insight_id", "")
        if sid == "SESSION_TOXICITY":
            ws = (snap.get("worst_session") or {}).get("session", "")
            if ws: watch_sessions.add(ws)
        elif sid == "SYMBOL_NO_EDGE":
            ws = (snap.get("worst_symbol") or {}).get("symbol", "")
            if ws: watch_symbols.add(ws)

    # zero line
    zero_y = cy(0)
    zero_line = f'<line x1="{PAD_L}" y1="{zero_y:.1f}" x2="{W-PAD_R}" y2="{zero_y:.1f}" stroke="#2d3748" stroke-width="1" stroke-dasharray="4 3"/>'

    # main polyline
    pts = " ".join(f"{cx(i):.1f},{cy(v):.1f}" for i, v in enumerate(cum))
    line = f'<polyline points="{pts}" fill="none" stroke="#00E5A0" stroke-width="2" stroke-linejoin="round"/>'

    # shaded area under curve
    area_pts  = f"{PAD_L:.1f},{cy(0):.1f} " + pts + f" {cx(n-1):.1f},{cy(0):.1f}"
    area      = f'<polygon points="{area_pts}" fill="#00E5A0" fill-opacity="0.07"/>'

    # watchlist markers (small triangles for weak sessions/symbols)
    markers = ""
    for i, meta in enumerate(trade_meta[:n]):
        sess = meta.get("session", "")
        sym  = meta.get("symbol", "")
        if sess in watch_sessions or sym in watch_symbols:
            mx, my = cx(i), cy(cum[i])
            markers += f'<circle cx="{mx:.1f}" cy="{my:.1f}" r="3" fill="#FFB020" fill-opacity="0.7" title="{sess}/{sym}"/>'

    # y-axis labels (3 ticks)
    y_labels = ""
    for frac in [0, 0.5, 1.0]:
        val = y_min + frac * y_range
        yp  = cy(val)
        y_labels += f'<text x="{PAD_L-6}" y="{yp+4:.1f}" text-anchor="end" font-size="9" fill="#586069">{val:+,.0f}</text>'
        y_labels += f'<line x1="{PAD_L-3}" y1="{yp:.1f}" x2="{PAD_L}" y2="{yp:.1f}" stroke="#586069" stroke-width="1"/>'

    # x-axis labels
    x_labels = ""
    for frac in [0, 0.25, 0.5, 0.75, 1.0]:
        idx = int(frac * (n - 1))
        xp  = cx(idx)
        x_labels += f'<text x="{xp:.1f}" y="{H-PAD_B+14}" text-anchor="middle" font-size="9" fill="#586069">#{idx+1}</text>'

    # axis lines
    axes = (f'<line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{H-PAD_B}" stroke="#2d3748" stroke-width="1"/>'
            f'<line x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}" stroke="#2d3748" stroke-width="1"/>')

    # legend
    titles = {"en": "Cumulative P&L", "fa": "سود و زیان تجمیعی", "ar": "الربح والخسارة التراكمي"}
    subs   = {
        "en": "🟡 = watchlist segment (unconfirmed)",
        "fa": "🟡 = سگمنت تحت نظر (تأییدنشده)",
        "ar": "🟡 = شريحة مراقبة (غير مؤكدة)",
    }
    title = titles.get(lang, titles["en"])
    sub   = (subs.get(lang, subs["en"]) if (watch_sessions or watch_symbols) else "")

    svg = f"""
<div class="bz-equity-block">
  <div class="bz-recover-title">{title}</div>
  <svg width="100%" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" style="max-width:{W}px">
    {zero_line}
    {axes}
    {area}
    {line}
    {markers}
    {y_labels}
    {x_labels}
  </svg>
  {('<div class="bz-equity-sub">' + sub + '</div>') if sub else ''}
</div>"""
    return svg


# ── 4. JOURNEY BAR ────────────────────────────────────────────────────────────

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
.bz-recover-neutral{border-left-color:#586069;}
.bz-recover-neutral .bz-recover-note{color:#8892a4;font-size:13px;font-style:normal;}
.bz-watch-block{background:#0D1117;border:1px solid #1C2530;border-left:3px solid #586069;border-radius:8px;padding:18px 20px;margin:12px 0;}
.bz-watch-num{color:#8892a4;font-family:'JetBrains Mono',monospace;}
.bz-watch-p{color:#586069;font-size:11px;margin-left:6px;}

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

/* ── Equity curve ── */
.bz-equity-block{background:#0D1117;border:1px solid #1C2530;border-radius:8px;padding:16px 20px;margin:20px 0;overflow:hidden;}
.act-obs{font-size:13px;color:#8892a4;border-inline-start:2px solid #586069;padding-inline-start:10px;margin-top:10px;font-style:italic;}
.bz-equity-sub{font-size:11px;color:#586069;margin-top:6px;}
"""
