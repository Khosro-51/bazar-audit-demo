"""
Acceptance + statistical-honesty tests — Phase 2 (v2.0).
معیارهای جدید طبق حکم مهندس: GOOD بدون finding کاذب، AVERAGE ممکن است observation شود،
PROBLEM باید finding ساختاری قوی بدهد، و Monte Carlo دائمی <10%.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_audit_engine import run_audit, audit_from_df


PATHS = {
    "GOOD": os.path.join(BASE_DIR, "sample_data", "bazar_sample_good_trader.csv"),
    "AVERAGE": os.path.join(BASE_DIR, "sample_data", "bazar_sample_average_trader.csv"),
    "PROBLEM": os.path.join(BASE_DIR, "sample_data", "bazar_sample_behavior_problem_trader.csv"),
}


def _ids(report):
    return [i.insight_id for i in report.insights]


def _schema_ok(report):
    for ins in report.insights:
        assert ins.severity.value in ("LOW", "MEDIUM", "HIGH")
        assert ins.confidence.value in ("LOW", "MEDIUM", "HIGH")
        assert ins.message and ins.recommended_action and ins.body_fa
        json.dumps(ins.to_dict(), ensure_ascii=False)


def test_good_no_false_findings():
    r = run_audit(PATHS["GOOD"], "GOOD")
    _schema_ok(r)
    assert _ids(r) == ["SAMPLE_SIZE_LIMITED"]
    assert all(i.severity.value == "LOW" for i in r.insights)


def test_average_observations():
    r = run_audit(PATHS["AVERAGE"], "AVERAGE")
    _schema_ok(r)
    ids = _ids(r)
    # سشن و نماد باید حضور داشته باشند (به‌عنوان finding یا observation)
    assert "SESSION_TOXICITY" in ids
    assert "SYMBOL_NO_EDGE" in ids
    assert "SYSTEMIC_UNDERPERFORMANCE" not in ids
    # هر MEDIUM/HIGH باید p-value معنادار داشته باشد (نه ادعای بی‌مدرک)
    for i in r.insights:
        if i.insight_id in ("SESSION_TOXICITY", "SYMBOL_NO_EDGE") and i.severity.value in ("MEDIUM", "HIGH"):
            assert (i.metric_snapshot or {}).get("p_value", 1.0) < 0.05


def test_problem_systemic_first_and_strong():
    r = run_audit(PATHS["PROBLEM"], "PROBLEM")
    _schema_ok(r)
    non_sample = [i for i in r.insights if "SAMPLE" not in i.insight_id]
    assert non_sample and non_sample[0].insight_id == "SYSTEMIC_UNDERPERFORMANCE"
    assert non_sample[0].severity.value == "HIGH"
    ids = _ids(r)
    for req in ("SESSION_TOXICITY", "TRADE_COUNT_CLIFF", "PAYOFF_IMBALANCE", "SYMBOL_NO_EDGE"):
        assert req in ids


def test_problem_json_contract_first_non_sample_insight():
    r = run_audit(PATHS["PROBLEM"], "PROBLEM")
    non_sample = [i for i in r.insights if "SAMPLE" not in i.insight_id]
    first = non_sample[0].to_dict()
    for key in ("insight_id", "severity", "confidence", "sample_size",
                "metric_snapshot", "message", "recommended_action", "title_fa", "body_fa"):
        assert key in first
    assert first["insight_id"] == "SYSTEMIC_UNDERPERFORMANCE"


# ── v1.2 regression: borderline / counterfactual / confidence guard ──────────

def _make_borderline_df(n=60):
    rows = []
    t = pd.Timestamp('2026-01-05 09:00:00')
    for i in range(n):
        win = (i % 20) < 9
        t += pd.Timedelta(hours=3)
        rows.append(dict(
            trade_id=f'T{i:03d}', open_time=t, close_time=t + pd.Timedelta(minutes=30),
            symbol='EURUSD', side='BUY',
            pnl=127.0 if win else -114.0,
            pnl_R=1.1 if win else -1.0,
            session=['London', 'NY', 'Asia', 'Overlap'][i % 4],
        ))
    return pd.DataFrame(rows)


def test_borderline_edge_below_breakeven():
    rep = audit_from_df(_make_borderline_df(), 'BORDERLINE')
    ids = [i.insight_id for i in rep.insights]
    assert "EDGE_BELOW_BREAKEVEN" in ids, f"got {ids}"
    assert "SYSTEMIC_UNDERPERFORMANCE" not in ids
    # v2.0: expectancy در محدوده نویز → observation LOW (نه MEDIUM بی‌مدرک)
    ins = next(i for i in rep.insights if i.insight_id == "EDGE_BELOW_BREAKEVEN")
    assert ins.severity.value in ("LOW", "MEDIUM")
    if ins.severity.value == "MEDIUM":
        assert (ins.metric_snapshot or {}).get("observation") is False


def test_session_counterfactual_fields():
    r = run_audit(PATHS["AVERAGE"], "AVERAGE")
    st_ins = next(i for i in r.insights if i.insight_id == "SESSION_TOXICITY")
    cf = st_ins.metric_snapshot.get("counterfactual")
    assert cf is not None
    for key in ("current_pf", "pf_without_segment", "current_net_pnl", "net_pnl_without_segment"):
        assert key in cf
    assert "impact_pct" not in st_ins.metric_snapshot
    assert "p_value" in st_ins.metric_snapshot


def test_small_segment_confidence_guard():
    r = run_audit(PATHS["AVERAGE"], "AVERAGE")
    for ins in r.insights:
        if ins.insight_id in ("SESSION_TOXICITY", "SYMBOL_NO_EDGE") and ins.sample_size < 20:
            assert ins.confidence.value == "LOW"


# ── Phase 2 (v2.0): تست دائمی Monte Carlo — قلب صداقت آماری ─────────────────

_SES = ['Asia', 'London', 'Overlap', 'NY']
_SYM = ['EURUSD', 'NAS100', 'XAUUSD', 'GBPJPY']


def _random_trader(rng, n=120):
    rows = []
    t = pd.Timestamp('2026-01-05 08:00:00')
    for i in range(n):
        t += pd.Timedelta(minutes=int(rng.integers(30, 600)))
        r = float(rng.normal(0, 1.0))
        rows.append(dict(
            trade_id=f'T{i}', open_time=t, close_time=t + pd.Timedelta(minutes=30),
            symbol=_SYM[int(rng.integers(0, 4))], side='BUY',
            pnl=round(r * 100, 2), pnl_R=round(r, 2),
            session=_SES[int(rng.integers(0, 4))], initial_risk_amount=100.0))
    return pd.DataFrame(rows)


def test_monte_carlo_false_finding_rate_below_10pct():
    """تریدر کاملاً تصادفی نباید finding (MEDIUM/HIGH) بگیرد — سقف ۱۰٪.
    seed ثابت → قطعی. اگر کسی آستانه‌ها را شل کرد، این تست یقه‌اش را می‌گیرد."""
    rng = np.random.default_rng(2026)
    N = 40
    flagged = 0
    for k in range(N):
        rep = audit_from_df(_random_trader(rng), f'MC{k}')
        if any(i.severity.value in ("MEDIUM", "HIGH")
               for i in rep.insights if "SAMPLE" not in i.insight_id):
            flagged += 1
    assert flagged / N <= 0.10, f"false finding rate = {flagged}/{N}"
