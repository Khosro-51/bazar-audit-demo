"""
Bazar Audit Engine v1.1
ترتیب اجرا: Data Quality → Core Metrics → Strategic → Behavioral → Edge Attribution

تغییرات v1.1:
- حذف sys.path هاردکد (/home/claude/...) — مسیر نسبی و قابل حمل شد.
- run_audit و audit_from_df ادغام شدند؛ یک هسته واحد (audit_from_df) وجود دارد.
- اعتبارسنجی ستون‌های ضروری داخل خود موتور انجام می‌شود (نه فقط در UI).
"""
import os
import sys

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_schema import AuditReport, Severity
from bazar_metrics import compute_core_metrics, r_mode
from bazar_insights import (
    insight_sample_size,
    insight_systemic,
    insight_session_toxicity,
    insight_trade_count_cliff,
    insight_post_loss_decay,
    insight_drawdown_recovery,
    insight_payoff_imbalance,
    insight_symbol_edge,
)

REQUIRED_COLS = {'open_time', 'close_time', 'symbol', 'side', 'pnl', 'session'}

# اولویت نمایش insights
PRIORITY = {
    "SAMPLE_SIZE_INSUFFICIENT":  0,
    "SAMPLE_SIZE_LIMITED":       1,
    "SYSTEMIC_UNDERPERFORMANCE": 2,
    "EDGE_BELOW_BREAKEVEN":      2,
    "SESSION_TOXICITY":          3,
    "TRADE_COUNT_CLIFF":         4,
    "PAYOFF_IMBALANCE":          5,
    "SYMBOL_NO_EDGE":            6,
    "DRAWDOWN_RECOVERY_SIZING":  7,
    "POST_LOSS_DECAY":           8,
    "POST_LOSS_FAST_REENTRY":    9,
}

# لایه‌ها — ترتیب اجرا اهمیت دارد
STRATEGIC_INSIGHTS = [insight_systemic]
BEHAVIORAL_INSIGHTS = [
    insight_session_toxicity,
    insight_trade_count_cliff,
    insight_post_loss_decay,
    insight_drawdown_recovery,
    insight_payoff_imbalance,
    insight_symbol_edge,
]

R_WARNING = (
    "pnl_R not found. R-based insights are disabled. "
    "Add 'initial_risk_amount' or 'pnl_R' column for full analysis.")


def validate_columns(df: pd.DataFrame) -> None:
    """ستون‌های ضروری را بررسی می‌کند؛ در صورت نبود، ValueError با پیام واضح."""
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def audit_from_df(df: pd.DataFrame, trader_id: str = 'trader') -> AuditReport:
    """هسته واحد audit — هم CSV و هم DataFrame مستقیم (UI) از همین مسیر می‌گذرند."""
    validate_columns(df)

    df = df.copy()
    for col in ('open_time', 'close_time'):
        if not pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = pd.to_datetime(df[col], errors='coerce')

    # RA-4: drop rows whose timestamps failed to parse (NaT). Left in, they corrupt
    # sequencing (post-loss/close-time ordering), the per-day trade index (cliff),
    # and the 3D map — and pandas sorts NaT to the end rather than excluding them.
    # Remove them once, up front, and surface how many were dropped.
    _bad_ts = df['open_time'].isna() | df['close_time'].isna()
    n_bad_ts = int(_bad_ts.sum())
    if n_bad_ts:
        df = df[~_bad_ts]
    # RA-7 / D3: stable sort so tied open_times get a deterministic order (and hence
    # a deterministic derived trade_index_in_day) across pandas versions.
    df = df.sort_values('open_time', kind='stable').reset_index(drop=True)

    mode = r_mode(df)
    report = AuditReport(trader_id=trader_id, total_trades=len(df),
                         sample_size_ok=True, r_mode=mode)
    if n_bad_ts:
        report.warnings.append(
            f"{n_bad_ts} trade(s) had unparseable open/close timestamps and were excluded from the analysis.")

    # ── Data Quality ────────────────────────────────────────────────
    ok, size_ins = insight_sample_size(df)
    if size_ins:
        report.insights.append(size_ins)
    if not ok:
        report.sample_size_ok = False
        return report

    if mode == 'pnl_only':
        report.warnings.append(R_WARNING)

    # ── Core Metrics ─────────────────────────────────────────────────
    metrics = compute_core_metrics(df)
    report.core_metrics = metrics

    # ── Strategic Layer (اول) → Behavioral + Edge Layer ─────────────
    for fn in STRATEGIC_INSIGHTS + BEHAVIORAL_INSIGHTS:
        ins = fn(df, metrics)
        if ins:
            report.insights.append(ins)

    # ── Priority Sort ────────────────────────────────────────────────
    report.insights.sort(key=lambda x: PRIORITY.get(x.insight_id, 99))
    return report


def run_audit(path: str, trader_id: str = 'trader') -> AuditReport:
    """CSV را بارگذاری و به هسته واحد audit می‌سپارد."""
    df = pd.read_csv(path, parse_dates=['open_time', 'close_time'])
    return audit_from_df(df, trader_id=trader_id)


def load(path: str) -> pd.DataFrame:
    """(backward-compatible) بارگذاری و اعتبارسنجی CSV."""
    df = pd.read_csv(path, parse_dates=['open_time', 'close_time'])
    validate_columns(df)
    return df.sort_values('open_time', kind='stable').reset_index(drop=True)


def print_report(report: AuditReport):
    SEV_ICON = {"HIGH": "🔴", "MEDIUM": "⚠️", "LOW": "ℹ️"}
    print(f"\n{'='*62}")
    print(f"  BAZAR AUDIT — {report.trader_id}  ({report.total_trades} trades | R: {report.r_mode})")
    print(f"{'='*62}")

    m = report.core_metrics
    if m:
        print(f"  WR: {round(m['win_rate']*100,1)}%  |  "
              f"PF: {m['profit_factor']}  |  "
              f"Payoff: {m['payoff_ratio']}  |  "
              f"Exp$: {m['expectancy_dollar']}")
        if m.get('expectancy_R') is not None:
            print(f"  Exp(R): {m['expectancy_R']}  |  AvgWin: {m['avg_win_R']}R  |  AvgLoss: {m['avg_loss_R']}R")

    if report.warnings:
        print()
        for w in report.warnings:
            print(f"  ⚠️  {w}")

    print()
    if not report.insights:
        print("  ✅  No significant issues detected.")
    else:
        for ins in report.insights:
            icon = SEV_ICON.get(ins.severity.value, "•")
            conf_tag = f"[conf:{ins.confidence.value}]"
            print(f"{icon}  {ins.insight_id}  {conf_tag}  n={ins.sample_size}")
            print(f"    {ins.body_fa}")
            print(f"    → {ins.recommended_action}")
            print()

    high = sum(1 for i in report.insights if i.severity == Severity.HIGH)
    med  = sum(1 for i in report.insights if i.severity == Severity.MEDIUM)
    low  = sum(1 for i in report.insights if i.severity == Severity.LOW)
    print(f"{'─'*62}")
    print(f"  HIGH: {high}  MEDIUM: {med}  LOW: {low}")
    print(f"{'='*62}\n")
