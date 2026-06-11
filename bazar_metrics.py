import pandas as pd
import numpy as np


def r_mode(df: pd.DataFrame) -> str:
    if 'pnl_R' in df.columns and df['pnl_R'].notna().sum() > len(df) * 0.8:
        return 'full'
    if 'initial_risk_amount' in df.columns and df['initial_risk_amount'].notna().sum() > 0:
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


def compute_core_metrics(df: pd.DataFrame) -> dict:
    mode = r_mode(df)
    n    = len(df)
    wins   = df[df['pnl'] > 0]
    losses = df[df['pnl'] < 0]

    win_rate = round((df['pnl'] > 0).mean(), 4)
    avg_win  = round(wins['pnl'].mean(),  2) if len(wins)  > 0 else 0.0
    avg_loss = round(losses['pnl'].mean(), 2) if len(losses) > 0 else 0.0  # negative
    payoff_ratio = round(abs(avg_win / avg_loss), 3) if avg_loss != 0 else 0.0

    gross_profit = wins['pnl'].sum()
    gross_loss   = abs(losses['pnl'].sum())
    profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else 0.0

    expectancy_dollar = round(df['pnl'].mean(), 2)

    # R-based metrics — v1.1: برای هر دو حالت full و computed محاسبه می‌شود.
    # قبلاً 'computed' فقط یک برچسب بود و هیچ متریک R تولید نمی‌کرد (وعده بدون اجرا).
    expectancy_R = None
    avg_win_R    = None
    avg_loss_R   = None
    payoff_R     = None
    r_vals = _r_series(df, mode)
    if r_vals is not None:
        r_wins   = r_vals[r_vals > 0]
        r_losses = r_vals[r_vals < 0]
        avg_win_R  = round(r_wins.mean(),  3) if len(r_wins)   > 0 else 0.0
        avg_loss_R = round(r_losses.mean(), 3) if len(r_losses) > 0 else 0.0
        payoff_R   = round(abs(avg_win_R / avg_loss_R), 3) if avg_loss_R != 0 else 0.0
        expectancy_R = round(r_vals.mean(), 3)

    # breakeven WR: losses / (wins + losses) in absolute dollar terms
    breakeven_wr = round(abs(avg_loss) / (avg_win + abs(avg_loss)), 4) if (avg_win + abs(avg_loss)) > 0 else 0.5

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
    }
