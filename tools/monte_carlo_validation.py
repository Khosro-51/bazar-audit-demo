"""
Bazar Audit — Monte Carlo False-Positive Validation
تریدرهای کاملاً تصادفی (بدون هیچ edge و بدون هیچ الگوی رفتاری) می‌سازد
و می‌سنجد موتور چند درصد از آنها را با insight رفتاری MEDIUM/HIGH متهم می‌کند.
نرخ ایده‌آل: نزدیک به نرخ خطای اسمی (۵-۱۰٪). نرخ بالا = موتور نویز را سیگنال می‌بیند.

اجرا:
    python tools/monte_carlo_validation.py 1000
"""
import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_audit_engine import audit_from_df

SESSIONS = ['Asia', 'London', 'Overlap', 'NY']
SYMBOLS  = ['EURUSD', 'NAS100', 'XAUUSD', 'GBPJPY']


def make_random_trader(rng: np.random.Generator, n_trades: int = 120) -> pd.DataFrame:
    """تریدر صفر-edge: pnl_R ~ N(0,1)، سشن و نماد تصادفی، بدون الگوی رفتاری.
    RA-1: balance_before + lot_or_size emitted so DRAWDOWN_RECOVERY_SIZING is
    exercised. Lot size is INDEPENDENT of the equity path (true null), so the
    drawdown finding should only fire at ~the test alpha (false positives)."""
    rows = []
    t = pd.Timestamp('2026-01-05 08:00:00')
    balance = 10000.0
    for i in range(n_trades):
        t = t + pd.Timedelta(minutes=int(rng.integers(30, 600)))
        open_t  = t
        close_t = open_t + pd.Timedelta(minutes=int(rng.integers(10, 120)))
        risk  = 100.0
        pnl_r = float(rng.normal(0.0, 1.0))
        pnl   = round(pnl_r * risk, 2)
        rows.append({
            'trade_id':  f'T{i:04d}',
            'open_time': open_t,
            'close_time': close_t,
            'symbol':  SYMBOLS[int(rng.integers(0, len(SYMBOLS)))],
            'side':    'BUY' if rng.random() < 0.5 else 'SELL',
            'pnl':     pnl,
            'pnl_R':   round(pnl_r, 2),
            'session': SESSIONS[int(rng.integers(0, len(SESSIONS)))],
            'initial_risk_amount': risk,
            'balance_before': round(balance, 2),
            'lot_or_size': round(float(rng.uniform(0.05, 0.30)), 2),  # independent of state
        })
        balance += pnl
    return pd.DataFrame(rows)


# Pass criteria (audit B4 / Wave 0I). A zero-edge, zero-behavior trader must not
# be flagged with a MEDIUM/HIGH finding more often than the nominal rate.
MED_HIGH_MAX  = 0.10
HIGH_ONLY_MAX = 0.10


def false_finding_rates(n_traders: int = 1000, n_trades: int = 120, seed: int = 42) -> dict:
    """Run `n_traders` zero-edge random traders through the engine and return the
    false-finding rates. Single source of truth shared by the CLI gate and the
    pytest tiers (fast + release). Deterministic for a fixed seed."""
    rng = np.random.default_rng(seed)
    flagged = 0
    high_flagged = 0
    id_counts = Counter()

    for k in range(n_traders):
        df  = make_random_trader(rng, n_trades)
        rep = audit_from_df(df, trader_id=f'MC_{k:04d}')
        behavioral = [i for i in rep.insights if 'SAMPLE' not in i.insight_id]
        med_high   = [i for i in behavioral if i.severity.value in ('MEDIUM', 'HIGH')]
        if med_high:
            flagged += 1
        if any(i.severity.value == 'HIGH' for i in behavioral):
            high_flagged += 1
        for i in med_high:
            id_counts[i.insight_id] += 1

    return {
        'n_traders': n_traders,
        'n_trades_each': n_trades,
        'seed': seed,
        'false_positive_rate_med_high': round(flagged / n_traders, 4),
        'false_positive_rate_high_only': round(high_flagged / n_traders, 4),
        'insight_id_counts': dict(id_counts.most_common()),
    }


def main(n_traders: int = 1000, n_trades: int = 120, seed: int = 42) -> dict:
    result = false_finding_rates(n_traders, n_trades, seed)
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    res = main(n_traders=n)
    # CI/pre-release gate: non-zero exit if either rate breaches its ceiling.
    mh, ho = res['false_positive_rate_med_high'], res['false_positive_rate_high_only']
    ok = mh < MED_HIGH_MAX and ho < HIGH_ONLY_MAX
    print(f"\nGATE: med_high {mh:.4f} < {MED_HIGH_MAX} and high_only {ho:.4f} < {HIGH_ONLY_MAX} -> "
          f"{'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
