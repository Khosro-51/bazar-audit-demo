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
    ids = _ids(r)
    assert "SAMPLE_SIZE_LIMITED" in ids
    # GOOD must produce no false FINDINGS (MEDIUM/HIGH). Observations (LOW) are
    # allowed — e.g. after the D3 fix (Wave 0D) trade_index_in_day is derived
    # deterministically from open_time, which surfaces a non-significant cliff
    # OBSERVATION (p≈0.20) on this profile. That is honest, not a false finding.
    findings = [i for i in r.insights
                if i.insight_id != "SAMPLE_SIZE_LIMITED"
                and i.severity.value in ("MEDIUM", "HIGH")]
    assert findings == [], f"unexpected findings: {[i.insight_id for i in findings]}"
    for i in r.insights:
        if i.insight_id != "SAMPLE_SIZE_LIMITED":
            assert i.severity.value == "LOW"
            assert (i.metric_snapshot or {}).get("observation") is True


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
    for req in ("SESSION_TOXICITY", "PAYOFF_IMBALANCE", "SYMBOL_NO_EDGE"):
        assert req in ids
    # D3 (Wave 0D): trade_index_in_day is now derived deterministically from
    # open_time. The PROBLEM fixture's supplied index was inconsistent with its
    # timestamps (its first chronological trade carried index 5) and was the only
    # reason a cliff appeared; under faithful derivation it does not. If a cliff
    # is reported at all it must be evidence-gated (LOW observation), never a
    # MEDIUM/HIGH false finding.
    cliff = next((i for i in r.insights if i.insight_id == "TRADE_COUNT_CLIFF"), None)
    if cliff is not None:
        assert cliff.severity.value == "LOW"


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
# Wave 0I (audit B4): two-tier validation, both sharing tools.monte_carlo_validation
# as the single source of truth.
#   * Fast tier (below)  — runs in ordinary `pytest`; modest N, both criteria.
#   * Release tier        — @pytest.mark.release, large N; DESELECTED by default
#                           (pytest.ini addopts `-m "not release"`). Run before a
#                           deploy with `pytest -m release` or
#                           `python tools/monte_carlo_validation.py 1000`.
import pytest

sys.path.insert(0, os.path.join(BASE_DIR, "tools"))
from monte_carlo_validation import false_finding_rates, MED_HIGH_MAX, HIGH_ONLY_MAX


def _assert_fp_rates(res, mh_max=MED_HIGH_MAX, ho_max=HIGH_ONLY_MAX):
    mh = res["false_positive_rate_med_high"]
    ho = res["false_positive_rate_high_only"]
    assert mh < mh_max, f"med_high false-finding rate {mh} >= {mh_max}: {res}"
    assert ho < ho_max, f"high_only false-finding rate {ho} >= {ho_max}: {res}"


# Fast-tier COARSE thresholds. At N=100 the true ~5% rate has seed-dependent
# sampling noise up to ~12%, so a strict 10% bound would false-fail on noise. The
# fast tier therefore uses a coarse ceiling that won't trip on noise but DOES catch
# gross regressions (e.g., a significance gate removed → rate jumps to 30%+). The
# authoritative 10%/10% gate is the release tier (large N), where 10% is meaningful.
FAST_MED_HIGH_MAX  = 0.20
FAST_HIGH_ONLY_MAX = 0.15


def test_monte_carlo_false_finding_rate_fast():
    """Fast coarse tripwire (runs in every `pytest`; ~4s, deterministic)."""
    _assert_fp_rates(false_finding_rates(n_traders=100, seed=2026),
                     mh_max=FAST_MED_HIGH_MAX, ho_max=FAST_HIGH_ONLY_MAX)


@pytest.mark.release
def test_monte_carlo_false_finding_rate_release():
    """Authoritative pre-release gate: med_high < 10% AND high_only < 10% at N=1000.
    Deselected by default (pytest.ini); run with `pytest -m release` or
    `python tools/monte_carlo_validation.py 1000`."""
    _assert_fp_rates(false_finding_rates(n_traders=1000, seed=42))
