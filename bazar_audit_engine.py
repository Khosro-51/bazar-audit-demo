"""
Bazar Audit Engine v1
ترتیب اجرا: Data Quality → Core Metrics → Strategic → Behavioral → Edge Attribution
"""
import json
import pandas as pd
import sys
sys.path.insert(0, '/home/claude/bazar_v1')

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
    "SESSION_TOXICITY":          3,
    "TRADE_COUNT_CLIFF":         4,
    "PAYOFF_IMBALANCE":          5,
    "SYMBOL_NO_EDGE":            6,
    "DRAWDOWN_RECOVERY_SIZING":  7,
    "POST_LOSS_DECAY":           8,
    "POST_LOSS_FAST_REENTRY":    9,
}


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['open_time', 'close_time'])
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df.sort_values('open_time').reset_index(drop=True)


def run_audit(path: str, trader_id: str = 'trader') -> AuditReport:
    df   = load(path)
    mode = r_mode(df)
    report = AuditReport(trader_id=trader_id, total_trades=len(df),
                         sample_size_ok=True, r_mode=mode)

    # ── Data Quality ────────────────────────────────────────────────
    ok, size_ins = insight_sample_size(df)
    if size_ins:
        report.insights.append(size_ins)
    if not ok:
        report.sample_size_ok = False
        return report

    if mode == 'pnl_only':
        report.warnings.append(
            "pnl_R not found. R-based insights are disabled. "
            "Add 'initial_risk_amount' or 'pnl_R' column for full analysis.")

    # ── Core Metrics ─────────────────────────────────────────────────
    metrics = compute_core_metrics(df)
    report.core_metrics = metrics

    # ── Strategic Layer (اول) ────────────────────────────────────────
    for fn in [insight_systemic]:
        ins = fn(df, metrics)
        if ins: report.insights.append(ins)

    # ── Behavioral + Edge Layer ──────────────────────────────────────
    for fn in [
        insight_session_toxicity,
        insight_trade_count_cliff,
        insight_post_loss_decay,
        insight_drawdown_recovery,
        insight_payoff_imbalance,
        insight_symbol_edge,
    ]:
        ins = fn(df, metrics)
        if ins: report.insights.append(ins)

    # ── Priority Sort ────────────────────────────────────────────────
    report.insights.sort(key=lambda x: PRIORITY.get(x.insight_id, 99))

    return report


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


def audit_from_df(df: pd.DataFrame, trader_id: str = 'trader') -> AuditReport:
    """Wrapper: df مستقیم می‌گیرد برای استفاده در UI"""
    # اطمینان از datetime بودن ستون‌های زمانی
    for col in ['open_time', 'close_time']:
        if col in df.columns and not pd.api.types.is_datetime64_any_dtype(df[col]):
            df = df.copy()
            df[col] = pd.to_datetime(df[col], errors='coerce')
    df = df.sort_values('open_time').reset_index(drop=True)
    mode = r_mode(df)
    report = AuditReport(trader_id=trader_id, total_trades=len(df),
                         sample_size_ok=True, r_mode=mode)

    ok, size_ins = insight_sample_size(df)
    if size_ins:
        report.insights.append(size_ins)
    if not ok:
        report.sample_size_ok = False
        return report

    if mode == 'pnl_only':
        report.warnings.append(
            "pnl_R not found. R-based insights are disabled. "
            "Add 'initial_risk_amount' or 'pnl_R' column for full analysis.")

    metrics = compute_core_metrics(df)
    report.core_metrics = metrics

    for fn in [insight_systemic]:
        ins = fn(df, metrics)
        if ins: report.insights.append(ins)

    for fn in [insight_session_toxicity, insight_trade_count_cliff,
               insight_post_loss_decay, insight_drawdown_recovery,
               insight_payoff_imbalance, insight_symbol_edge]:
        ins = fn(df, metrics)
        if ins: report.insights.append(ins)

    report.insights.sort(key=lambda x: PRIORITY.get(x.insight_id, 99))
    return report
