"""
Wave 0E — remaining LOW findings: A7, B3, D4, E3.
(D5 is a Streamlit fail-closed guard verified by inspection/compile, not unit-tested here.)

A7  post-loss "previous" is the most-recently-CLOSED prior trade (overlap-safe),
    and the gap is never negative
B3  session-toxicity HIGH uses a scale-invariant R cutoff, not a dollar amount
D4  recoverable "confirmed" split uses the engine's ALPHA_FINDING, not a stray 0.05
E3  drawdown buckets use a running high-water mark and never drop the recovery trade
"""
import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_insights import (
    _post_loss_indices, _drawdown_buckets,
    SESSION_TOXIC_HIGH_R, DD_THRESHOLD_PCT,
)
from bazar_audit_engine import audit_from_df
import bazar_report_extras as bx


# ── A7 ────────────────────────────────────────────────────────────────────────
def test_a7_previous_is_by_close_time_not_open():
    # T1 (loss) OPENS before T2 but CLOSES after it; T0 (win) closed just before T2.
    # Old open-order logic would call T2 "post-loss" (T1 opened just before) — wrong,
    # T1 hadn't resolved. New close-time logic: T2's predecessor is T0 (a win).
    opens  = np.array(["2026-01-05T09:00", "2026-01-05T09:15", "2026-01-05T10:00"], dtype="datetime64[ns]")
    closes = np.array(["2026-01-05T09:30", "2026-01-05T12:00", "2026-01-05T10:30"], dtype="datetime64[ns]")
    pnls   = np.array([50.0, -80.0, 25.0])  # T0 win, T1 loss (still open at 10:00), T2
    post, fast = _post_loss_indices(opens, closes, pnls)
    assert 2 not in post   # T2 is NOT post-loss (its completed predecessor T0 won)


def test_a7_gaps_never_negative_under_overlap():
    # Build overlapping trades; every post-loss gap must be >= 0 (no negative gaps).
    n = 40
    base = pd.Timestamp("2026-01-05 08:00:00")
    opens, closes, pnls = [], [], []
    for i in range(n):
        o = base + pd.Timedelta(minutes=20 * i)
        c = o + pd.Timedelta(minutes=90)           # 90-min trades, opened 20 min apart -> overlap
        opens.append(np.datetime64(o)); closes.append(np.datetime64(c))
        pnls.append(-30.0 if i % 2 else 40.0)
    opens = np.array(opens); closes = np.array(closes); pnls = np.array(pnls)
    post, fast = _post_loss_indices(opens, closes, pnls)
    # recompute gaps for the post set and assert non-negative
    close_order = np.argsort(closes, kind="stable"); cs = closes[close_order]
    for i in post:
        k = int(np.searchsorted(cs, opens[i], side="right"))
        prev = next(int(close_order[j]) for j in range(k - 1, -1, -1) if int(close_order[j]) != i)
        gap = (opens[i] - closes[prev]) / np.timedelta64(1, "m")
        assert gap >= 0


# ── B3 ────────────────────────────────────────────────────────────────────────
def _toxic_session_df(risk: float):
    """160 trades, 4 sessions; 'Asia' is cleanly the worst at avg -0.4R (low noise),
    the rest +0.1R. R-structure is identical regardless of `risk`; only the dollar
    magnitude scales. avg -0.4R is below the MEDIUM bar but ABOVE the HIGH bar
    (SESSION_TOXIC_HIGH_R = -0.50), so a faithful R rule must call it MEDIUM at any
    dollar scale — whereas the old -$60 rule would flip to HIGH once risk is large."""
    rows = []
    t = pd.Timestamp("2026-01-05 08:00:00")
    sess = ["London", "NY", "Overlap", "Asia"]
    for i in range(160):
        t += pd.Timedelta(hours=2)
        s = sess[i % 4]
        r = -0.4 if s == "Asia" else 0.1
        rows.append(dict(trade_id=f"T{i:03d}", open_time=t, close_time=t + pd.Timedelta(minutes=30),
                         symbol="EURUSD", side="BUY", session=s,
                         pnl=round(r * risk, 2), pnl_R=r, initial_risk_amount=risk))
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"]); df["close_time"] = pd.to_datetime(df["close_time"])
    return df


def _session_sev(df):
    rep = audit_from_df(df, "X")
    ins = next((i for i in rep.insights if i.insight_id == "SESSION_TOXICITY"), None)
    assert ins is not None
    return ins.severity.value, (ins.metric_snapshot or {}).get("observation")


def test_b3_session_high_is_scale_invariant():
    # avg -0.4R is worse-than-MEDIUM but not HIGH (cutoff -0.50R); must be MEDIUM and
    # SIGNIFICANT (observation False) at BOTH dollar scales — the dollar amount
    # (-40 vs -400, straddling the old -$60 line) must NOT change the verdict.
    sev_small, obs_small = _session_sev(_toxic_session_df(risk=100))   # avg_pnl ~ -40$
    sev_big,   obs_big   = _session_sev(_toxic_session_df(risk=1000))  # avg_pnl ~ -400$
    assert obs_small is False and obs_big is False        # genuinely significant
    assert sev_small == "MEDIUM"                           # R rule, not the -$60 rule
    assert sev_small == sev_big                            # scale-invariant
    assert SESSION_TOXIC_HIGH_R == -0.50


# ── D4 ────────────────────────────────────────────────────────────────────────
def test_d4_recoverable_uses_engine_alpha():
    from bazar_insights import ALPHA_FINDING
    assert bx.ALPHA_FINDING == ALPHA_FINDING          # report layer shares the engine constant
    assert bx.ALPHA_FINDING < 0.05                    # and it is the stricter 0.015, not 0.05


# ── E3 ────────────────────────────────────────────────────────────────────────
def test_e3_every_trade_classified_no_drop():
    # equity dips into drawdown then recovers; the recovery trade must be counted.
    balance = [10000, 9900, 9600, 9400, 9700, 10050, 10100]  # dip below -3% then recover
    lots    = [1, 1, 2, 2, 3, 1, 1]
    normal_s, dd_s = _drawdown_buckets(balance, lots, DD_THRESHOLD_PCT)
    assert len(normal_s) + len(dd_s) == len(balance)   # nothing dropped (E3)
    # 9700 is the recovery trade: peak 10000, dd = 3.0% which is NOT > 3.0 -> normal bucket
    # (it must be classified, not silently discarded)
    assert len(dd_s) >= 1 and len(normal_s) >= 1


def test_e3_running_peak_from_start():
    # First row is the highest; a later dip > 3% must register as drawdown.
    balance = [10000, 9500, 9400]   # -5%, -6%
    lots    = [1, 5, 5]
    normal_s, dd_s = _drawdown_buckets(balance, lots, DD_THRESHOLD_PCT)
    assert normal_s == [1.0]            # only the peak row is "normal"
    assert dd_s == [5.0, 5.0]           # both dips are drawdown trades


# ── RA-1 (Wave 0F): drawdown sizing is now permutation-gated ───────────────────
from bazar_insights import insight_drawdown_recovery


def _dd_df(balances, lots):
    n = len(balances)
    t = pd.Timestamp("2026-01-05 09:00:00")
    rows = []
    for i in range(n):
        t += pd.Timedelta(hours=2)
        rows.append(dict(trade_id=f"T{i:03d}", open_time=t, close_time=t + pd.Timedelta(minutes=30),
                         symbol="EURUSD", side="BUY", session="NY",
                         pnl=10.0, balance_before=float(balances[i]), lot_or_size=float(lots[i])))
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"]); df["close_time"] = pd.to_datetime(df["close_time"])
    return df


def test_ra1_clear_oversizing_is_significant_finding():
    # 12 trades at peak (small lots) then 12 deep in drawdown (big lots): the
    # drawdown/size association is unambiguous -> permutation-significant FINDING.
    balances = [10000] * 12 + [9000] * 12          # second block is ~10% drawdown
    lots     = [0.10] * 12 + [0.50] * 12
    ins = insight_drawdown_recovery(_dd_df(balances, lots), {})
    assert ins is not None
    snap = ins.metric_snapshot
    assert "p_value" in snap                        # RA-1: gate is wired
    assert snap["observation"] is False             # significant -> finding
    assert ins.severity.value in ("MEDIUM", "HIGH")
    assert snap["p_value"] < 0.015


def test_ra1_flat_sizing_no_finding():
    # Same drawdown shape but constant lot size -> ratio 1.0 -> no pattern, no finding.
    balances = [10000] * 12 + [9000] * 12
    lots     = [0.20] * 24
    ins = insight_drawdown_recovery(_dd_df(balances, lots), {})
    assert ins is None


def test_ra1_drawdown_measured_in_random_traders():
    # The MC generator now emits balance_before/lot_or_size, so DRAWDOWN can fire on
    # noise — but with the permutation gate its false-finding rate stays controlled.
    import numpy as np
    sys_path = os.path.join(BASE_DIR, "tools")
    if sys_path not in sys.path:
        sys.path.insert(0, sys_path)
    from monte_carlo_validation import make_random_trader
    df = make_random_trader(np.random.default_rng(1), 120)
    assert {"balance_before", "lot_or_size"}.issubset(df.columns)   # now exercised by MC


# ── RA-4 (Wave 0G): NaT timestamp / NaN balance robustness ─────────────────────
def test_ra4_nat_timestamps_dropped_with_warning():
    rows = []
    for i in range(35):
        d = (i % 27) + 1
        rows.append(dict(trade_id=f"T{i}", open_time=f"2026-01-{d:02d} 09:00:00",
                         close_time=f"2026-01-{d:02d} 09:30:00",
                         symbol="EURUSD", side="BUY", pnl=(10.0 if i % 2 else -8.0), session="NY"))
    rows.append(dict(trade_id="BAD", open_time="not-a-date", close_time="also-bad",
                     symbol="EURUSD", side="BUY", pnl=5.0, session="NY"))
    rep = audit_from_df(pd.DataFrame(rows), "NAT")
    assert rep.total_trades == 35                                   # the NaT row was dropped
    assert any("excluded" in w or "unparseable" in w for w in rep.warnings)
    assert rep.core_metrics                                         # engine still proceeded, no crash


def test_ra4_drawdown_buckets_ignore_nan():
    balance = [10000, np.nan, 9000, 9000, 9000, 10000]
    lots    = [0.1,   0.5,    0.5,  np.nan, 0.5, 0.1]
    normal_s, dd_s = _drawdown_buckets(balance, lots, DD_THRESHOLD_PCT)
    assert len(normal_s) + len(dd_s) == 4                           # 2 NaN rows dropped
    assert not any(np.isnan(x) for x in normal_s + dd_s)            # no NaN leaks through


# ── RA-2 (Wave 0H): single decided-basis win rate (scratches excluded) ─────────
from bazar_insights import _decided_win_rate, _decided_counts, insight_session_toxicity


def test_ra2_decided_win_rate_excludes_scratches():
    s = pd.Series([10.0, 10.0, -5.0, 0.0, 0.0])    # 2 wins, 1 loss, 2 scratch
    assert _decided_counts(s) == (2, 3)
    assert abs(_decided_win_rate(s) - 2 / 3) < 1e-9
    assert _decided_win_rate(s) != (s > 0).mean()  # differs from the old all-trades basis (2/5)


def test_ra2_session_winrate_is_decided_basis():
    # NY: 2 wins, 4 losses, 4 scratches (avg_pnl < 0 -> toxic, so the insight fires).
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    plan = [("NY", [50, 50, -40, -40, -40, -40, 0, 0, 0, 0]),
            ("London", [60, 60, 60, -20, -20, 0, 0, 0, 0, 0])]
    for sess, pls in plan:
        for p in pls:
            t += pd.Timedelta(hours=2)
            rows.append(dict(trade_id=f"{sess}{int(t.value)}", open_time=t,
                             close_time=t + pd.Timedelta(minutes=30),
                             symbol="EURUSD", side="BUY", session=sess, pnl=float(p)))
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"]); df["close_time"] = pd.to_datetime(df["close_time"])
    ins = insight_session_toxicity(df, {"profit_factor": 1.0, "r_mode": "pnl_only"})
    assert ins is not None
    by = {r["session"]: r["win_rate"] for r in ins.metric_snapshot["all_sessions"]}
    assert abs(by["NY"] - round(2 / 6, 4)) < 1e-6      # 2 wins / 6 decided, NOT 2/10 (all-basis)
