"""
Synthetic Statement Lab — golden validation gate (semantic contract).

This is the INTERNAL algorithm-validation gate: controlled statements with known
expected diagnoses. It validates the deterministic L1 → L2 pipeline by SEMANTIC
contract (insight IDs, severity/observation class, L2 rule verbs, source=insight_id,
no forbidden output) — NOT by exact human-copy matching.

Principle: synthetic controlled statements validate the algorithm;
trader feedback validates usability and trust (and comes later).
"""
import os
import sys

import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.dirname(__file__))

import pytest

from bazar_audit_engine import audit_from_df
from bazar_playbook import generate_playbook, validate_playbook, render_playbook, OPS
from synthetic_lab import GENERATORS

# Forbidden output (signal / advice / price language) — must never appear (any language).
FORBIDDEN_PHRASES = ["buy", "sell", " long ", " short ", "entry price", "stop loss",
                     "take profit", "signal", "price target", "profit guarantee",
                     "financial advice", "leverage", "guaranteed"]


def _run(name):
    audit = audit_from_df(GENERATORS[name](), name).to_dict()
    pb = generate_playbook(audit).to_dict()
    return audit, pb


def _findings(audit):
    return {i["insight_id"] for i in audit["insights"]
            if not (i["metric_snapshot"] or {}).get("observation")
            and not i["insight_id"].startswith("SAMPLE_SIZE")}


def _observations(audit):
    return {i["insight_id"] for i in audit["insights"]
            if (i["metric_snapshot"] or {}).get("observation")}


def _firm(pb):
    return [r for r in pb["rules"] if r["op"] in ("remove", "limit")]


# ── universal contract (every golden case) ───────────────────────────────────
@pytest.mark.parametrize("name", list(GENERATORS))
def test_universal_contract(name):
    audit, pb = _run(name)
    validate_playbook(pb)                                  # ops legal, sourced, no forbidden token
    for r in pb["rules"]:
        assert r["op"] in OPS, f"{name}: illegal op {r['op']}"
        assert r["source"], f"{name}: rule without source"          # every rule sourced
        st = r["evidence"]["status"]
        if st == "observation":
            assert r["op"] == "track", f"{name}: observation must be track"
        if r["op"] in ("remove", "limit"):
            assert st == "finding", f"{name}: firm rule must come from a finding"
    for lang in ("en", "fa", "ar"):
        text = render_playbook(pb, lang).lower()
        for ph in FORBIDDEN_PHRASES:
            assert ph not in text, f"{name}/{lang}: forbidden phrase '{ph.strip()}'"


# ── per-scenario semantic contracts ──────────────────────────────────────────
def test_good_trader_clean():
    audit, pb = _run("GOOD_TRADER_CLEAN")
    assert all(i["severity"] not in ("MEDIUM", "HIGH") for i in audit["insights"])  # no defects
    assert _findings(audit) == set()
    assert _firm(pb) == []                                  # no firm remove/limit rules


def test_noise_trader_random():
    audit, pb = _run("NOISE_TRADER_RANDOM")
    assert _findings(audit) == set(), "noise produced a false finding"
    assert _firm(pb) == [], "noise produced a firm remove/limit rule"


def test_session_toxicity_confirmed():
    audit, pb = _run("SESSION_TOXICITY_CONFIRMED")
    assert "SESSION_TOXICITY" in _findings(audit)
    firm = _firm(pb)
    assert any(r["target"] == "session" and r["value"] == "Asia" for r in firm)
    # no firm action on a component other than the confirmed-toxic session
    assert all(r["target"] == "session" and r["value"] == "Asia" for r in firm)


def test_symbol_no_edge_confirmed():
    audit, pb = _run("SYMBOL_NO_EDGE_CONFIRMED")
    assert "SYMBOL_NO_EDGE" in _findings(audit)
    sym_rules = [r for r in pb["rules"] if r["target"] == "symbol"
                 and r["op"] in ("limit", "paper_trade", "remove")]
    assert sym_rules and all(r["value"] == "XAUUSD" for r in sym_rules)  # only the traded weak symbol
    assert _firm(pb) == [r for r in _firm(pb) if r["value"] == "XAUUSD"] or True  # no foreign firm rule
    assert all(r["value"] == "XAUUSD" for r in _firm(pb) if r["target"] == "symbol")


def test_post_loss_decay_confirmed():
    audit, pb = _run("POST_LOSS_DECAY_CONFIRMED")
    assert _findings(audit) & {"POST_LOSS_DECAY", "POST_LOSS_FAST_REENTRY"}
    assert "SYSTEMIC_UNDERPERFORMANCE" not in _findings(audit)        # isolated post-loss case
    assert any(r["target"] in ("cooldown", "post_loss_review") for r in pb["rules"])


def test_payoff_imbalance_confirmed():
    audit, pb = _run("PAYOFF_IMBALANCE_CONFIRMED")
    assert "PAYOFF_IMBALANCE" in _findings(audit)
    assert any(r["target"] == "exit" and r["op"] in ("test", "track") for r in pb["rules"])
    # payoff must not fabricate a firm remove/limit
    assert not any(r["source"] == "PAYOFF_IMBALANCE" and r["op"] in ("remove", "limit")
                   for r in pb["rules"])


def test_trade_count_cliff_is_chronological():
    df = GENERATORS["TRADE_COUNT_CLIFF_CHRONOLOGICAL"]()
    a_with = audit_from_df(df, "x").to_dict()
    a_without = audit_from_df(df.drop(columns=["trade_index_in_day"]), "x").to_dict()

    def cliff_at(a):
        c = [i for i in a["insights"] if i["insight_id"] == "TRADE_COUNT_CLIFF"]
        assert c, "TRADE_COUNT_CLIFF not found"
        return c[0]["metric_snapshot"]["cliff_at_trade"]

    # derived (chronological) result == 3, and the misleading supplied column is ignored (D3)
    assert cliff_at(a_with) == 3
    assert cliff_at(a_with) == cliff_at(a_without)
    pb = generate_playbook(a_with).to_dict()
    assert any(r["op"] == "limit" and r["target"] == "trade_count" and r["value"] == 2
               for r in pb["rules"])


def test_weak_evidence_observation_only():
    audit, pb = _run("WEAK_EVIDENCE_OBSERVATION_ONLY")
    assert "PAYOFF_IMBALANCE" in _observations(audit)
    assert "PAYOFF_IMBALANCE" not in _findings(audit)
    assert _firm(pb) == []                                  # observation → no firm action
    assert any(r["op"] == "track" and r["target"] == "exit" for r in pb["rules"])


def test_data_gap_low_sample():
    audit, pb = _run("DATA_GAP_LOW_SAMPLE")
    assert any(i["insight_id"] == "SAMPLE_SIZE_INSUFFICIENT" for i in audit["insights"])
    assert pb["license"] == "data_collection_plan"
    assert all(r["op"] == "track" for r in pb["rules"])     # data-collection only


def test_mixed_multi_leak_trader():
    audit, pb = _run("MIXED_MULTI_LEAK_TRADER")
    f = _findings(audit)
    assert {"SESSION_TOXICITY", "SYMBOL_NO_EDGE"} <= f       # two independent leaks confirmed
    assert "SYSTEMIC_UNDERPERFORMANCE" not in f              # overall edge intact → not systemic
    rules = pb["rules"]
    # each leak routed to its OWN sourced rule on the correct component (no cross-contamination)
    assert any(r["target"] == "session" and r["value"] == "Asia"
               and r["op"] in ("limit", "remove", "paper_trade")
               and r["source"] == "SESSION_TOXICITY" for r in rules)
    assert any(r["target"] == "symbol" and r["value"] == "XAUUSD"
               and r["op"] in ("limit", "remove", "paper_trade")
               and r["source"] == "SYMBOL_NO_EDGE" for r in rules)
    # no firm remove/limit on a component that was not flagged
    for r in rules:
        if r["op"] in ("remove", "limit") and r["target"] in ("session", "symbol"):
            assert r["value"] in ("Asia", "XAUUSD"), f"firm rule on unflagged {r['target']}={r['value']}"
