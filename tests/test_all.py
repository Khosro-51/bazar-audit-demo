"""
Regression tests for the Bazar Audit public demo acceptance criteria.
"""
import json
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_audit_engine import run_audit


PATHS = {
    "GOOD": os.path.join(BASE_DIR, "sample_data", "bazar_sample_good_trader.csv"),
    "AVERAGE": os.path.join(BASE_DIR, "sample_data", "bazar_sample_average_trader.csv"),
    "PROBLEM": os.path.join(BASE_DIR, "sample_data", "bazar_sample_behavior_problem_trader.csv"),
}

CRITERIA = {
    "GOOD": {
        "exact_ids": ["SAMPLE_SIZE_LIMITED"],
        "max_high": 0,
        "max_medium": 0,
        "systemic_inactive": True,
        "required_active": [],
    },
    "AVERAGE": {
        "exact_ids": ["SESSION_TOXICITY", "SYMBOL_NO_EDGE", "POST_LOSS_FAST_REENTRY"],
        "systemic_inactive": True,
        "required_active": ["SESSION_TOXICITY", "SYMBOL_NO_EDGE", "POST_LOSS_FAST_REENTRY"],
    },
    "PROBLEM": {
        "exact_ids": [
            "SYSTEMIC_UNDERPERFORMANCE",
            "SESSION_TOXICITY",
            "TRADE_COUNT_CLIFF",
            "PAYOFF_IMBALANCE",
            "SYMBOL_NO_EDGE",
        ],
        "systemic_first": True,
        "required_active": ["SYSTEMIC_UNDERPERFORMANCE", "SESSION_TOXICITY"],
    },
}


def _failures_for_report(name, report):
    ids = [i.insight_id for i in report.insights]
    cr = CRITERIA[name]
    failures = []

    for ins in report.insights:
        if ins.severity.value not in ("LOW", "MEDIUM", "HIGH"):
            failures.append(f"BAD SEVERITY: {ins.insight_id}")
        if ins.confidence.value not in ("LOW", "MEDIUM", "HIGH"):
            failures.append(f"BAD CONFIDENCE: {ins.insight_id}")
        if not ins.message:
            failures.append(f"MISSING MESSAGE: {ins.insight_id}")
        if not ins.recommended_action:
            failures.append(f"MISSING ACTION: {ins.insight_id}")
        if not ins.body_fa:
            failures.append(f"MISSING BODY_FA: {ins.insight_id}")

    if "max_high" in cr:
        high_count = sum(1 for i in report.insights if i.severity.value == "HIGH")
        if high_count > cr["max_high"]:
            failures.append(f"{name} has {high_count} HIGH insights (expected {cr['max_high']})")

    if "max_medium" in cr:
        medium_count = sum(1 for i in report.insights if i.severity.value == "MEDIUM")
        if medium_count > cr["max_medium"]:
            failures.append(f"{name} has {medium_count} MEDIUM insights (expected {cr['max_medium']})")

    if "exact_ids" in cr and ids != cr["exact_ids"]:
        failures.append(f"{name} insight order mismatch: got {ids}, expected {cr['exact_ids']}")

    if cr.get("systemic_inactive") and "SYSTEMIC_UNDERPERFORMANCE" in ids:
        failures.append("SYSTEMIC_UNDERPERFORMANCE should be INACTIVE")

    for req in cr.get("required_active", []):
        if req not in ids:
            failures.append(f"{req} should be ACTIVE but missing")

    if cr.get("systemic_first"):
        non_sample = [i for i in report.insights if "SAMPLE" not in i.insight_id]
        first = non_sample[0].insight_id if non_sample else "NONE"
        if first != "SYSTEMIC_UNDERPERFORMANCE":
            failures.append(f"SYSTEMIC should be first but got: {first}")

    if cr.get("at_least_one_post_loss"):
        post_loss_ids = [i for i in ids if "POST_LOSS" in i]
        if not post_loss_ids:
            failures.append("No POST_LOSS insight found")

    return failures


def test_acceptance_criteria():
    for name, path in PATHS.items():
        assert os.path.exists(path), f"Missing sample dataset: {path}"
        report = run_audit(path, trader_id=name)
        failures = _failures_for_report(name, report)
        assert not failures, f"{name} acceptance failures: {failures}"


def test_problem_json_contract_first_non_sample_insight():
    report = run_audit(PATHS["PROBLEM"], "PROBLEM")
    non_sample = [i for i in report.insights if "SAMPLE" not in i.insight_id]

    assert non_sample, "PROBLEM report should include at least one non-sample insight"
    first = non_sample[0].to_dict()

    for key in (
        "insight_id",
        "severity",
        "confidence",
        "sample_size",
        "metric_snapshot",
        "message",
        "recommended_action",
        "title_fa",
        "body_fa",
    ):
        assert key in first

    assert first["insight_id"] == "SYSTEMIC_UNDERPERFORMANCE"
    json.dumps(first, ensure_ascii=False)


# ── v1.2: تست‌های پچ‌های ENGINEERING_NOTES ─────────────────────────────────
import pandas as pd


def _make_borderline_df(n=60):
    """تریدر مرزی: WR=45٪، PF≈0.91، expectancy_R≈-0.055 — باید EDGE_BELOW_BREAKEVEN بگیرد."""
    rows = []
    t = pd.Timestamp('2026-01-05 09:00:00')
    for i in range(n):
        win = (i % 20) < 9   # 45% win rate
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
    from bazar_audit_engine import audit_from_df
    rep = audit_from_df(_make_borderline_df(), 'BORDERLINE')
    ids = [i.insight_id for i in rep.insights]
    assert "EDGE_BELOW_BREAKEVEN" in ids, f"got {ids}"
    assert "SYSTEMIC_UNDERPERFORMANCE" not in ids
    ins = next(i for i in rep.insights if i.insight_id == "EDGE_BELOW_BREAKEVEN")
    assert ins.severity.value == "MEDIUM"


def test_session_counterfactual_replaces_impact_pct():
    report = run_audit(PATHS["AVERAGE"], "AVERAGE")
    st_ins = next(i for i in report.insights if i.insight_id == "SESSION_TOXICITY")
    cf = st_ins.metric_snapshot.get("counterfactual")
    assert cf is not None
    for key in ("current_pf", "pf_without_segment", "current_net_pnl", "net_pnl_without_segment"):
        assert key in cf
    assert "impact_pct" not in st_ins.metric_snapshot


def test_small_segment_confidence_guard():
    """سگمنت با n<20 نباید confidence بالاتر از LOW بگیرد."""
    report = run_audit(PATHS["AVERAGE"], "AVERAGE")
    for ins in report.insights:
        if ins.insight_id in ("SESSION_TOXICITY", "SYMBOL_NO_EDGE") and ins.sample_size < 20:
            assert ins.confidence.value == "LOW", (
                f"{ins.insight_id} n={ins.sample_size} got {ins.confidence.value}")
