"""
Synthetic Statement Lab — controlled statements with KNOWN expected diagnoses.

These are the algorithm's golden datasets: each generator builds a deterministic
trade statement engineered to trigger (or NOT trigger) a specific L1 diagnosis,
with the corresponding expected L2 playbook contract. Used by
tests/test_synthetic_statement_lab.py. No LLM, no live data, no network.

Principle: synthetic controlled statements validate the algorithm;
trader feedback validates usability and trust (and comes later).
"""
import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "tools"))

SESS4 = ["Asia", "London", "NY", "Overlap"]


def _df(rows):
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"])
    df["close_time"] = pd.to_datetime(df["close_time"])
    return df


def _row(i, t, pnl, session="NY", symbol="EURUSD", dur=30, **extra):
    r = dict(trade_id=f"T{i:04d}", open_time=t, close_time=t + pd.Timedelta(minutes=dur),
             symbol=symbol, side="BUY", session=session, pnl=float(pnl))
    r.update(extra)
    return r


# ── 1. GOOD_TRADER_CLEAN ────────────────────────────────────────────────────
def gen_good_clean():
    # positive edge, single session/symbol, ~1.5 days apart → no intraday cliff buckets
    rng = np.random.default_rng(11)
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(120):
        t += pd.Timedelta(hours=36)
        win = rng.random() < 0.55
        rows.append(_row(i, t, 60.0 if win else -45.0))
    return _df(rows)


# ── 2. NOISE_TRADER_RANDOM ──────────────────────────────────────────────────
def gen_noise_random():
    from monte_carlo_validation import make_random_trader
    return make_random_trader(np.random.default_rng(7), 120)


# ── 3. SESSION_TOXICITY_CONFIRMED ───────────────────────────────────────────
def gen_session_toxicity():
    # iid win draws (seeded) so there is NO sequence/post-loss artifact — Asia is the
    # only engineered weakness.
    rng = np.random.default_rng(3)
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(160):
        t += pd.Timedelta(hours=5)
        s = SESS4[i % 4]
        win = rng.random() < (0.20 if s == "Asia" else 0.60)
        rows.append(_row(i, t, 60.0 if win else -60.0, session=s))
    return _df(rows)


# ── 4. SYMBOL_NO_EDGE_CONFIRMED ─────────────────────────────────────────────
def gen_symbol_no_edge():
    syms = ["EURUSD", "XAUUSD", "NAS100"]
    rng = np.random.default_rng(4)
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(150):
        t += pd.Timedelta(hours=5)
        sym = syms[i % 3]
        win = rng.random() < (0.20 if sym == "XAUUSD" else 0.60)
        rows.append(_row(i, t, 60.0 if win else -60.0, session="NY", symbol=sym))
    return _df(rows)


# ── 5. POST_LOSS_DECAY_CONFIRMED ────────────────────────────────────────────
def gen_post_loss_decay():
    # Markov: after a loss the next trade (entered within 60 min) usually loses.
    # p(win|prev win)=0.70, p(win|prev loss)=0.30 → stationary WR 0.5, symmetric payoff
    # → expectancy ≈ 0 (NO systemic), but a sharp post-loss drop (0.70 → 0.30).
    rng = np.random.default_rng(5)
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    prev_loss = False
    for i in range(160):
        t += pd.Timedelta(minutes=40)               # 40 min apart, 20 min dur → 20 min gap (<60)
        win = rng.random() < (0.30 if prev_loss else 0.70)
        pnl = 55.0 if win else -55.0
        rows.append(_row(i, t, pnl, dur=20))
        prev_loss = pnl < 0
    return _df(rows)


# ── 6. PAYOFF_IMBALANCE_CONFIRMED ───────────────────────────────────────────
def gen_payoff_imbalance():
    # small wins, big losses, ~73% WR → ratio 0.375 (HIGH), expectancy ≈ 0.
    # iid draws so no post-loss artifact; 1 trade/day so no cliff.
    rng = np.random.default_rng(6)
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(120):
        t += pd.Timedelta(hours=36)
        win = rng.random() < 0.73
        rows.append(_row(i, t, 30.0 if win else -80.0))
    return _df(rows)


# ── 7. TRADE_COUNT_CLIFF_CHRONOLOGICAL ──────────────────────────────────────
def gen_trade_count_cliff():
    # 30 days × 5 trades/day; chronologically, trades 1–2 win, 3–5 lose (cliff at #3).
    # A MISLEADING reversed supplied trade_index_in_day proves the engine derives it (D3).
    rows = []
    day = pd.Timestamp("2026-01-05 09:00:00")
    i = 0
    for d in range(30):
        base = day + pd.Timedelta(days=d)
        for k in range(5):
            t = base + pd.Timedelta(hours=k)        # chronological position = k+1
            win = k < 2
            rows.append(_row(i, t, 50.0 if win else -50.0, session="NY",
                             trade_index_in_day=5 - k))   # reversed/misleading on purpose
            i += 1
    return _df(rows)


# ── 8. WEAK_EVIDENCE_OBSERVATION_ONLY ───────────────────────────────────────
def gen_weak_observation():
    # payoff ratio 0.75 (in [0.70, 0.90) → LOW observation), expectancy ≈ 0, iid draws
    rng = np.random.default_rng(8)
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(120):
        t += pd.Timedelta(hours=36)
        win = rng.random() < 0.571                   # ~57% WR
        rows.append(_row(i, t, 75.0 if win else -100.0))
    return _df(rows)


# ── 9. DATA_GAP_LOW_SAMPLE ──────────────────────────────────────────────────
def gen_low_sample():
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    for i in range(15):
        t += pd.Timedelta(hours=36)
        rows.append(_row(i, t, 20.0 if i % 2 else -15.0))
    return _df(rows)


GENERATORS = {
    "GOOD_TRADER_CLEAN": gen_good_clean,
    "NOISE_TRADER_RANDOM": gen_noise_random,
    "SESSION_TOXICITY_CONFIRMED": gen_session_toxicity,
    "SYMBOL_NO_EDGE_CONFIRMED": gen_symbol_no_edge,
    "POST_LOSS_DECAY_CONFIRMED": gen_post_loss_decay,
    "PAYOFF_IMBALANCE_CONFIRMED": gen_payoff_imbalance,
    "TRADE_COUNT_CLIFF_CHRONOLOGICAL": gen_trade_count_cliff,
    "WEAK_EVIDENCE_OBSERVATION_ONLY": gen_weak_observation,
    "DATA_GAP_LOW_SAMPLE": gen_low_sample,
}


def diagnose():
    """Print L1 insights (id/severity/evidence) + L2 rules for every golden case."""
    from bazar_audit_engine import audit_from_df
    from bazar_playbook import generate_playbook
    for name, gen in GENERATORS.items():
        rep = audit_from_df(gen(), name).to_dict()
        ins = [(i["insight_id"], i["severity"],
                "obs" if (i["metric_snapshot"] or {}).get("observation") else "FIND")
               for i in rep["insights"]]
        pb = generate_playbook(rep).to_dict()
        rules = [(r["op"], r["target"], r["value"]) for r in pb["rules"]]
        print(f"\n{name}: n={rep['total_trades']} license={pb['license']}")
        print(f"  L1: {ins}")
        print(f"  L2: {rules}")


if __name__ == "__main__":
    diagnose()
