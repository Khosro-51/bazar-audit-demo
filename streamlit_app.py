"""
Bazar Audit — Public Demo v0
مطابق دستور مهندس ارشد:
  • DEMO_MODE = True  →  سه دکمه sample، بدون upload
  • DEMO_MODE = False →  upload CSV فعال (private beta)
"""
import json
import os
import sys
import pandas as pd
import streamlit as st

# ── Path Fix (Windows + Linux compatible) ────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# ── Config ────────────────────────────────────────────────────────────────────
DEMO_MODE = True   # True = Public Demo | False = Private Beta (CSV upload)

SAMPLE_FILES = {
    "good":    os.path.join(BASE_DIR, "sample_data", "bazar_sample_good_trader.csv"),
    "average": os.path.join(BASE_DIR, "sample_data", "bazar_sample_average_trader.csv"),
    "problem": os.path.join(BASE_DIR, "sample_data", "bazar_sample_behavior_problem_trader.csv"),
}

SAMPLE_LABELS = {
    "good":    ("✅ Good Trader",    "No critical issues detected. Keep tracking more data."),
    "average": ("⚠️ Average Trader", "Main issues: session toxicity, fast re-entry after losses, weak symbol selection."),
    "problem": ("🔴 Problem Trader", "First problem is not behavior. Core strategy is structurally below breakeven."),
}

REQUIRED_COLS    = {'open_time', 'close_time', 'symbol', 'side', 'pnl', 'session'}
RECOMMENDED_COLS = {
    'pnl_R', 'lot_or_size', 'commission', 'balance_before', 'balance_after',
    'initial_risk_amount', 'initial_sl', 'setup_tag', 'exit_reason',
    'mfe_R', 'mae_R', 'trade_index_in_day',
}
SEV_ICON  = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}

# ── Engine Import ─────────────────────────────────────────────────────────────
ENGINE_ERROR = None
try:
    from bazar_audit_engine import audit_from_df
except Exception as e:
    audit_from_df = None
    ENGINE_ERROR  = e

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bazar Audit",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS — Dark Premium Theme ──────────────────────────────────────────────────
st.markdown("""
<style>
  /* ── global ── */
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

  /* ── hero headline ── */
  .hero-title {
    font-size: 2.6rem; font-weight: 700; line-height: 1.2;
    background: linear-gradient(135deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
  }
  .hero-sub {
    font-size: 1.05rem; color: #94a3b8; margin-bottom: 1.5rem;
  }
  .disclaimer {
    font-size: 0.78rem; color: #64748b;
    border-left: 3px solid #334155; padding-left: 10px;
    margin-bottom: 1.5rem; line-height: 1.6;
  }

  /* ── sample picker cards ── */
  .sample-narrative {
    background: #1e293b; border-radius: 10px;
    padding: 14px 18px; margin-top: 6px;
    font-size: 0.88rem; color: #cbd5e1; line-height: 1.6;
    border-left: 4px solid #475569;
  }
  .sample-narrative.good    { border-color: #34d399; }
  .sample-narrative.average { border-color: #fbbf24; }
  .sample-narrative.problem { border-color: #f87171; }

  /* ── metric cards ── */
  div[data-testid="metric-container"] {
    background: #1e293b; border-radius: 10px;
    padding: 14px 16px; border: 1px solid #334155;
  }

  /* ── insight cards ── */
  .ins-card {
    border-radius: 10px; padding: 16px 20px;
    margin-bottom: 14px; border: 1px solid #334155;
    background: #1e293b;
  }
  .ins-card.HIGH   { border-left: 5px solid #f87171; }
  .ins-card.MEDIUM { border-left: 5px solid #fbbf24; }
  .ins-card.LOW    { border-left: 5px solid #34d399; }
  .ins-title { font-size: 1.05rem; font-weight: 600; margin-bottom: 4px; }
  .ins-body  { font-size: 0.9rem; color: #cbd5e1; line-height: 1.65; }
  .ins-action{
    font-size: 0.85rem; color: #60a5fa;
    border-left: 3px solid #60a5fa; padding-left: 10px;
    margin-top: 10px;
  }
  .ins-badge {
    display:inline-block; border-radius:4px; padding:2px 8px;
    font-size:0.72rem; font-weight:600; margin-right:6px;
    vertical-align:middle;
  }
  .badge-HIGH   { background:#7f1d1d; color:#fca5a5; }
  .badge-MEDIUM { background:#78350f; color:#fcd34d; }
  .badge-LOW    { background:#064e3b; color:#6ee7b7; }

  /* ── tabs ── */
  button[data-baseweb="tab"] { font-size: 0.9rem; }

  /* ── sidebar ── */
  section[data-testid="stSidebar"] { background: #0f172a; }
</style>
""", unsafe_allow_html=True)

# ── Engine health check ───────────────────────────────────────────────────────
if ENGINE_ERROR or audit_from_df is None:
    st.error("⚠️ Engine import failed.")
    st.exception(ENGINE_ERROR)
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Bazar Audit")
    st.markdown("**v0 — Public Demo**")
    st.divider()
    st.markdown("""
**بفهم سود و ضرر معاملاتت واقعاً از کجا می‌آید.**

Bazar سیگنال خرید و فروش نمی‌دهد.  
Bazar عملکرد، ریسک و ساختار تصمیم‌گیری تریدر را تحلیل می‌کند.
""")
    st.divider()
    if DEMO_MODE:
        st.info("🔒 **Demo Mode**\n\nUpload CSV در private beta فعال می‌شود.")
    else:
        st.markdown("**ستون‌های اجباری:**")
        st.code(", ".join(sorted(REQUIRED_COLS)))
        st.markdown("**ستون‌های پیشنهادی:**")
        st.code(", ".join(sorted(RECOMMENDED_COLS)))
    st.divider()
    st.caption("Bazar does not provide buy/sell signals.\nIt analyzes trading behavior and strategy performance.")


# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown('<div class="hero-title">Bazar Audit</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-sub">Discover what really drives your trading performance.</div>',
    unsafe_allow_html=True
)
st.markdown("""
<div class="disclaimer">
Bazar does not provide buy/sell signals or financial advice.<br>
It analyzes trading performance, risk behavior, and strategy structure.
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  DEMO MODE: sample picker
# ─────────────────────────────────────────────────────────────────────────────
if DEMO_MODE:
    st.subheader("یک تریدر نمونه را انتخاب کن")
    st.caption("سه پروفایل واقع‌گرایانه — ببین Bazar چطور فکر می‌کند.")

    col_g, col_a, col_p = st.columns(3)
    chosen = None

    with col_g:
        label, narrative = SAMPLE_LABELS["good"]
        if st.button(label, use_container_width=True, key="btn_good"):
            chosen = "good"
        st.markdown(f'<div class="sample-narrative good">{narrative}</div>', unsafe_allow_html=True)

    with col_a:
        label, narrative = SAMPLE_LABELS["average"]
        if st.button(label, use_container_width=True, key="btn_average"):
            chosen = "average"
        st.markdown(f'<div class="sample-narrative average">{narrative}</div>', unsafe_allow_html=True)

    with col_p:
        label, narrative = SAMPLE_LABELS["problem"]
        if st.button(label, use_container_width=True, key="btn_problem"):
            chosen = "problem"
        st.markdown(f'<div class="sample-narrative problem">{narrative}</div>', unsafe_allow_html=True)

    st.divider()
    st.caption("📌 Upload your own trading history — coming soon for private beta.")

    if "active_sample" not in st.session_state:
        st.session_state.active_sample = None
    if chosen:
        st.session_state.active_sample = chosen

    if st.session_state.active_sample is None:
        st.info("👆 یکی از پروفایل‌های بالا را انتخاب کن تا Audit Report ساخته شود.")
        st.stop()

    key     = st.session_state.active_sample
    csv_path = SAMPLE_FILES[key]
    trader_id = key.upper() + "_TRADER"

    try:
        df = pd.read_csv(csv_path, parse_dates=['open_time', 'close_time'])
        df = df.sort_values('open_time').reset_index(drop=True)
    except Exception as e:
        st.error(f"خطا در بارگذاری فایل نمونه: {e}")
        st.stop()

# ─────────────────────────────────────────────────────────────────────────────
#  PRIVATE BETA MODE: CSV upload
# ─────────────────────────────────────────────────────────────────────────────
else:
    uploaded = st.file_uploader(
        "فایل CSV معاملاتت را آپلود کن",
        type=["csv"],
        help="MT5 export یا هر فرمت CSV با ستون‌های استاندارد"
    )
    if uploaded is None:
        with st.expander("نمونه فرمت CSV"):
            sample = pd.DataFrame([{
                "trade_id": "T001", "open_time": "2024-01-05 09:00:00",
                "close_time": "2024-01-05 09:45:00", "symbol": "EURUSD",
                "side": "BUY", "pnl": 120.5, "pnl_R": 1.2,
                "session": "London", "lot_or_size": 0.1,
            }])
            st.dataframe(sample)
        st.stop()

    try:
        df = pd.read_csv(uploaded, parse_dates=['open_time', 'close_time'])
        df = df.sort_values('open_time').reset_index(drop=True)
    except Exception as e:
        st.error("CSV قابل خواندن نیست.")
        st.exception(e)
        st.stop()

    missing_req = sorted(REQUIRED_COLS - set(df.columns))
    if missing_req:
        st.error(f"ستون‌های اجباری وجود ندارند: `{', '.join(missing_req)}`")
        st.stop()

    missing_rec = sorted(RECOMMENDED_COLS - set(df.columns))
    if missing_rec:
        with st.expander("⚠️ هشدار کیفیت داده"):
            st.warning(f"ستون‌های پیشنهادی موجود نیستند: `{', '.join(missing_rec)}`")

    trader_id = uploaded.name.replace('.csv', '')


# ── Run Engine ────────────────────────────────────────────────────────────────
with st.spinner("در حال تحلیل..."):
    try:
        report = audit_from_df(df, trader_id=trader_id)
        result = report.to_dict()
    except Exception as e:
        st.error("Engine خطا داد.")
        st.exception(e)
        st.stop()

insights = result.get("insights", [])
metrics  = result.get("core_metrics", {})


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_report, tab_data, tab_json = st.tabs(["📋 Audit Report", "📁 Data", "🔧 JSON"])


# ════════════════════════════════════════════════════════════════════════════
with tab_report:

    # ── Narrative banner per sample ──────────────────────────────────────────
    if DEMO_MODE:
        key = st.session_state.active_sample
        _, narrative = SAMPLE_LABELS[key]
        color_map = {"good": "#34d399", "average": "#fbbf24", "problem": "#f87171"}
        st.markdown(f"""
        <div style="background:#1e293b;border-left:5px solid {color_map[key]};
                    border-radius:8px;padding:14px 20px;margin-bottom:18px;
                    font-size:0.95rem;color:#e2e8f0;">
            <strong>Bazar says:</strong> {narrative}
        </div>
        """, unsafe_allow_html=True)

    # ── Health Summary Cards ─────────────────────────────────────────────────
    st.subheader("Trading Health Summary")

    high_n   = sum(1 for i in insights if i.get("severity") == "HIGH")
    medium_n = sum(1 for i in insights if i.get("severity") == "MEDIUM")
    low_n    = sum(1 for i in insights if i.get("severity") == "LOW")
    wr       = metrics.get("win_rate", 0)
    pf       = metrics.get("profit_factor", 0)
    exp_r    = metrics.get("expectancy_R")
    exp_d    = metrics.get("expectancy_dollar", 0)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Trades",           f"{report.total_trades}")
    c2.metric("🔴 High Issues",   f"{high_n}")
    c3.metric("🟠 Medium Issues", f"{medium_n}")
    c4.metric("Win Rate",         f"{wr*100:.1f}%" if wr else "N/A")
    c5.metric("Profit Factor",    f"{pf:.2f}" if pf else "N/A")
    c6.metric("Expectancy",
              f"{exp_r:.2f}R" if exp_r is not None else f"{exp_d:.1f}$")

    if result.get("warnings"):
        for w in result["warnings"]:
            st.warning(w)

    st.divider()

    # ── Insights ─────────────────────────────────────────────────────────────
    if not insights:
        st.success("✅ هیچ مشکل قابل توجهی شناسایی نشد.")
    else:
        st.subheader(f"Insights — {len(insights)} مورد")
        for ins in insights:
            sev    = ins.get("severity", "LOW")
            iid    = ins.get("insight_id", "")
            title  = ins.get("title_fa") or iid
            body   = ins.get("body_fa") or ins.get("message", "")
            action = ins.get("recommended_action", "")
            conf   = ins.get("confidence", "")
            n      = ins.get("sample_size", "")
            snap   = ins.get("metric_snapshot", {})
            icon   = SEV_ICON.get(sev, "⚪")

            st.markdown(f"""
            <div class="ins-card {sev}">
              <div class="ins-title">
                {icon}&nbsp;{title}
                <span class="ins-badge badge-{sev}">{sev}</span>
                <span style="font-size:0.72rem;color:#64748b;">{iid} | conf:{conf} | n={n}</span>
              </div>
              <div class="ins-body">{body}</div>
              {'<div class="ins-action">→ ' + action + '</div>' if action else ''}
            </div>
            """, unsafe_allow_html=True)

            if snap:
                with st.expander("Metric Snapshot"):
                    num_items = {k: v for k, v in snap.items()
                                 if isinstance(v, (int, float)) and not isinstance(v, bool)}
                    if num_items:
                        cols = st.columns(min(len(num_items), 4))
                        for i, (k, v) in enumerate(num_items.items()):
                            cols[i % 4].metric(k, f"{v:.3f}" if isinstance(v, float) else str(v))
                    complex_items = {k: v for k, v in snap.items()
                                     if not isinstance(v, (int, float, type(None))) or isinstance(v, bool)}
                    if complex_items:
                        st.json(complex_items)

# ════════════════════════════════════════════════════════════════════════════
with tab_data:
    st.subheader("Trade Data")

    col_f, col_i = st.columns([2, 1])
    with col_f:
        if 'symbol' in df.columns:
            symbols = ['All'] + sorted(df['symbol'].unique().tolist())
            sel_sym = st.selectbox("فیلتر نماد", symbols)
        else:
            sel_sym = 'All'
    with col_i:
        st.metric("Total Rows", len(df))
        st.metric("Columns",    len(df.columns))

    display_df = df if sel_sym == 'All' else df[df['symbol'] == sel_sym]
    st.dataframe(display_df, use_container_width=True, height=400)

    st.divider()
    st.subheader("Column Info")
    col_info_df = pd.DataFrame({
        "column":   list(df.columns),
        "non_null": [int(df[c].notna().sum()) for c in df.columns],
        "dtype":    [str(df[c].dtype)         for c in df.columns],
        "sample":   [str(df[c].iloc[0]) if len(df) > 0 else "" for c in df.columns],
    })
    st.dataframe(col_info_df, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
with tab_json:
    st.subheader("Engine Output — Raw JSON")
    st.json(result)
    st.download_button(
        label="⬇️ Download Audit JSON",
        data=json.dumps(result, ensure_ascii=False, indent=2, default=str),
        file_name=f"bazar_audit_{trader_id}.json",
        mime="application/json",
    )
