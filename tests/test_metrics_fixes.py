"""
Wave 0C — metric-correctness fixes: B1, B2, C1, C2, C3.

B1  computed R-mode requires >=80% risk coverage (not a single non-null row)
B2  the edge/systemic significance test uses the R series of the engine's mode
    (full OR computed) via _significance_series — schema no longer gates it
C1  a no-loss (profitable) sample yields a high PF/payoff (ceiling), never 0.0
C2  win_rate is computed over decided trades (scratches excluded), consistent
    with breakeven_wr
C3  payoff_ratio / breakeven_wr are computed from full-precision means, not the
    2-dp rounded display values
"""
import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_metrics import (
    r_mode, compute_core_metrics, _r_series,
    PROFIT_FACTOR_CEILING, PAYOFF_RATIO_CEILING,
)
from bazar_insights import _significance_series
from bazar_audit_engine import audit_from_df


def _mk(rows):
    df = pd.DataFrame(rows)
    for c in ("open_time", "close_time"):
        df[c] = pd.to_datetime(df[c])
    return df


def _trades(n, pnl_fn, **extra):
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(n):
        t += pd.Timedelta(hours=2)
        row = dict(trade_id=f"T{i:03d}", open_time=t, close_time=t + pd.Timedelta(minutes=30),
                   symbol="EURUSD", side="BUY", session=["London", "NY", "Asia", "Overlap"][i % 4],
                   pnl=pnl_fn(i))
        for k, v in extra.items():
            row[k] = v(i) if callable(v) else v
        rows.append(row)
    return _mk(rows)


# ── B1 ────────────────────────────────────────────────────────────────────────
def test_b1_sparse_risk_is_not_computed_mode():
    # 100 trades, only 1 with a usable initial_risk_amount -> must NOT be 'computed'
    df = _trades(100, lambda i: 50.0 if i % 2 else -40.0,
                 initial_risk_amount=lambda i: 100.0 if i == 0 else np.nan)
    assert "pnl_R" not in df.columns
    assert r_mode(df) == "pnl_only"
    m = compute_core_metrics(df)
    assert m["expectancy_R"] is None  # no R metrics fabricated from 1 row


def test_b1_full_coverage_is_computed_mode():
    df = _trades(100, lambda i: 50.0 if i % 2 else -40.0, initial_risk_amount=100.0)
    assert r_mode(df) == "computed"
    m = compute_core_metrics(df)
    assert m["expectancy_R"] is not None  # R metrics now genuinely populated


# ── B2 ──────────────────────────────────────────────────────────────────────
def test_b2_significance_series_uses_computed_R_not_schema():
    # computed mode, NO pnl_R column -> the edge test series is the computed R series,
    # not the dollar fallback and not empty (pre-fix this path was column-gated off).
    df = _trades(60, lambda i: 50.0 if i % 2 else -40.0, initial_risk_amount=100.0)
    assert "pnl_R" not in df.columns
    s = _significance_series(df, r_mode(df))
    expected = (df["pnl"] / 100.0)
    assert len(s) == len(df)
    assert np.allclose(sorted(s.tolist()), sorted(expected.tolist()))


def test_b2_allnan_pnl_r_falls_back_to_dollars():
    df = _trades(60, lambda i: 50.0 if i % 2 else -40.0)
    df["pnl_R"] = np.nan
    s = _significance_series(df, r_mode(df))  # r_mode -> pnl_only
    assert np.allclose(sorted(s.tolist()), sorted(df["pnl"].dropna().tolist()))


def test_b2_full_computed_edge_parity():
    # Same underlying data encoded two ways must produce the SAME systemic verdict.
    pnl = lambda i: 90.0 if (i % 100) < 48 else -100.0   # marginal, slightly negative
    full = _trades(120, pnl, pnl_R=lambda i: 0.9 if (i % 100) < 48 else -1.0,
                   initial_risk_amount=100.0)
    computed = _trades(120, pnl, initial_risk_amount=100.0)  # no pnl_R column
    assert r_mode(full) == "full" and r_mode(computed) == "computed"

    def verdict(df):
        return sorted((i.insight_id, i.severity.value) for i in audit_from_df(df, "X").insights
                      if i.insight_id in ("EDGE_BELOW_BREAKEVEN", "SYSTEMIC_UNDERPERFORMANCE"))
    assert verdict(full) == verdict(computed)


# ── C1 ──────────────────────────────────────────────────────────────────────
def test_c1_no_loss_trader_not_scored_worst():
    df = _trades(40, lambda i: 100.0 + i, pnl_R=1.0, initial_risk_amount=100.0)  # all wins
    m = compute_core_metrics(df)
    assert m["no_loss_trades"] is True
    assert m["profit_factor"] == PROFIT_FACTOR_CEILING   # not 0.0
    assert m["payoff_ratio"] == PAYOFF_RATIO_CEILING     # not 0.0
    assert m["profit_factor"] > 1.0 and m["payoff_ratio"] > 1.0


def test_c1_all_losses_still_zero():
    df = _trades(40, lambda i: -50.0 - i)  # all losses
    m = compute_core_metrics(df)
    assert m["profit_factor"] == 0.0
    assert m["no_loss_trades"] is False


# ── C2 ──────────────────────────────────────────────────────────────────────
def test_c2_winrate_excludes_scratches():
    # 10 wins, 10 losses, 20 scratches -> win_rate should be 10/20 = 0.5 (decided),
    # NOT 10/40 = 0.25 (old behavior that counted scratches in the denominator).
    def pnl(i):
        if i < 10:
            return 100.0
        if i < 20:
            return -100.0
        return 0.0
    df = _trades(40, pnl)
    m = compute_core_metrics(df)
    assert m["scratch_trades"] == 20
    assert m["win_rate"] == 0.5
    # win_rate is now on the same basis as breakeven_wr (both ignore scratches)
    assert abs(m["win_rate"] - m["breakeven_wr"]) < 1e-9  # symmetric 100/-100 -> bwr 0.5


# ── C3 ──────────────────────────────────────────────────────────────────────
def test_c3_ratios_use_full_precision():
    # avg_win 100.0049, avg_loss -33.337 -> full-precision payoff rounds to 3.000,
    # but computing from the 2-dp display values (100.00 / 33.34) rounds to 2.999.
    df = _trades(40, lambda i: 100.0049 if i % 2 == 0 else -33.337)
    m = compute_core_metrics(df)
    aw_full, al_full = 100.0049, 33.337
    from_full    = round(aw_full / al_full, 3)
    from_rounded = round(round(aw_full, 2) / round(al_full, 2), 3)
    assert from_full != from_rounded                 # the two approaches really differ here
    assert m["payoff_ratio"] == from_full            # engine uses full precision
    assert m["payoff_ratio"] != from_rounded
