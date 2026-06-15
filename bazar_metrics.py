import pandas as pd
import numpy as np


R_COVERAGE_MIN = 0.8            # share of rows that must carry usable R data
PROFIT_FACTOR_CEILING = 100.0   # no-loss sample: cap the (infinite) ratio so a flawless
PAYOFF_RATIO_CEILING  = 100.0   # record ranks at the TOP, not 0.0 (=worst). (audit C1)


def r_mode(df: pd.DataFrame) -> str:
    n = len(df)
    if n == 0:
        return 'pnl_only'
    if 'pnl_R' in df.columns and df['pnl_R'].notna().sum() > n * R_COVERAGE_MIN:
        return 'full'
    # B1 fix: require the SAME ≥80% coverage for 'computed' that 'full' requires.
    # Previously a single non-null initial_risk_amount flipped the whole dataset into
    # R-mode, so expectancy_R/avg_win_R were computed on a tiny subset while every
    # dollar metric used all rows. Count only rows where R is actually defined
    # (risk > 0) — matching _r_series.
    if 'initial_risk_amount' in df.columns and int((df['initial_risk_amount'] > 0).sum()) > n * R_COVERAGE_MIN:
        return 'computed'
    return 'pnl_only'


def _r_series(df: pd.DataFrame, mode: str):
    """سری R را برمی‌گرداند: مستقیم (full) یا محاسبه‌شده از initial_risk_amount (computed)."""
    if mode == 'full':
        return df['pnl_R']
    if mode == 'computed':
        risk = df['initial_risk_amount']
        return (df['pnl'] / risk).where(risk > 0)
    return None


def _ratio_or_ceiling(num_mag: float, den_mag: float, ceiling: float) -> float:
    """Magnitude ratio num/den, rounded to 3dp; if there is no denominator (no
    losses) but a positive numerator, return the finite ceiling instead of 0.0
    (audit C1). den_mag/num_mag are passed full-precision (audit C3)."""
    if den_mag != 0:
        return round(abs(num_mag / den_mag), 3)
    if num_mag > 0:
        return ceiling
    return 0.0


def compute_core_metrics(df: pd.DataFrame) -> dict:
    mode = r_mode(df)
    n    = len(df)
    wins   = df[df['pnl'] > 0]
    losses = df[df['pnl'] < 0]
    n_scratch = int((df['pnl'] == 0).sum())
    decided   = len(wins) + len(losses)

    # C2 fix: win_rate over DECIDED trades (win/loss), excluding scratches (pnl==0),
    # so it sits on the same basis as breakeven_wr (which is built from avg win/loss
    # magnitudes and inherently ignores scratches). Expectancy still uses ALL trades.
    win_rate = round(len(wins) / decided, 4) if decided > 0 else 0.0

    # C3 fix: keep full-precision means for the ratios; round only the reported $ values.
    avg_win_full  = wins['pnl'].mean()   if len(wins)   > 0 else 0.0
    avg_loss_full = losses['pnl'].mean() if len(losses) > 0 else 0.0  # negative
    avg_win  = round(avg_win_full,  2)
    avg_loss = round(avg_loss_full, 2)
    payoff_ratio = _ratio_or_ceiling(avg_win_full, avg_loss_full, PAYOFF_RATIO_CEILING)

    gross_profit = wins['pnl'].sum()
    gross_loss   = abs(losses['pnl'].sum())
    # C1 fix: no losses but positive profit → infinite PF; cap at a finite ceiling
    # so a flawless sample ranks at the top instead of 0.0 (= worst).
    profit_factor = _ratio_or_ceiling(gross_profit, -gross_loss, PROFIT_FACTOR_CEILING)
    no_loss_trades = bool(gross_loss == 0 and gross_profit > 0)

    expectancy_dollar = round(df['pnl'].mean(), 2)

    # R-based metrics — v1.1: برای هر دو حالت full و computed محاسبه می‌شود.
    # قبلاً 'computed' فقط یک برچسب بود و هیچ متریک R تولید نمی‌کرد (وعده بدون اجرا).
    expectancy_R = None
    avg_win_R    = None
    avg_loss_R   = None
    payoff_R     = None
    r_vals = _r_series(df, mode)
    if r_vals is not None:
        r_clean  = r_vals.dropna()
        r_wins   = r_clean[r_clean > 0]
        r_losses = r_clean[r_clean < 0]
        avg_win_R_full  = r_wins.mean()   if len(r_wins)   > 0 else 0.0
        avg_loss_R_full = r_losses.mean() if len(r_losses) > 0 else 0.0
        avg_win_R  = round(avg_win_R_full,  3)
        avg_loss_R = round(avg_loss_R_full, 3)
        payoff_R   = _ratio_or_ceiling(avg_win_R_full, avg_loss_R_full, PAYOFF_RATIO_CEILING)
        expectancy_R = round(r_clean.mean(), 3) if len(r_clean) > 0 else None

    # breakeven WR: losses / (wins + losses) in absolute dollar terms (full precision, C3)
    denom = abs(avg_win_full) + abs(avg_loss_full)
    breakeven_wr = round(abs(avg_loss_full) / denom, 4) if denom > 0 else 0.5

    return {
        "n":                 n,
        "win_rate":          win_rate,
        "avg_win_dollar":    avg_win,
        "avg_loss_dollar":   avg_loss,
        "payoff_ratio":      payoff_ratio,
        "profit_factor":     profit_factor,
        "expectancy_dollar": expectancy_dollar,
        "breakeven_wr":      breakeven_wr,
        "expectancy_R":      expectancy_R,
        "avg_win_R":         avg_win_R,
        "avg_loss_R":        avg_loss_R,
        "payoff_R":          payoff_R,
        "r_mode":            mode,
        "scratch_trades":    n_scratch,
        "no_loss_trades":    no_loss_trades,
    }
