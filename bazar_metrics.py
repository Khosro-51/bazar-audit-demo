import pandas as pd
import numpy as np


def r_mode(df: pd.DataFrame) -> str:
    if 'pnl_R' in df.columns and df['pnl_R'].notna().sum() > len(df) * 0.8:
        return 'full'
    if 'initial_risk_amount' in df.columns and df['initial_risk_amount'].notna().sum() > 0:
        return 'computed'
    return 'pnl_only'


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

    # R-based metrics
    expectancy_R = None
    avg_win_R    = None
    avg_loss_R   = None
    payoff_R     = None
    if mode == 'full':
        r_wins   = df[df['pnl_R'] > 0]['pnl_R']
        r_losses = df[df['pnl_R'] < 0]['pnl_R']
        avg_win_R  = round(r_wins.mean(),  3) if len(r_wins)   > 0 else 0.0
        avg_loss_R = round(r_losses.mean(), 3) if len(r_losses) > 0 else 0.0
        payoff_R   = round(abs(avg_win_R / avg_loss_R), 3) if avg_loss_R != 0 else 0.0
        expectancy_R = round(df['pnl_R'].mean(), 3)

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
