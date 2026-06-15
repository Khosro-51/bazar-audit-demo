"""
L2-core tests (Prompt 7 / spec §12). Deterministic Playbook Engine — no LLM.

Covers: determinism, verb-set + source enforcement, evidence discipline
(finding→firm / observation→track / gap→collect), the "no firm rule from noise"
honesty guard, conflict resolver, systemic override, keep rules, low-sample Data
Collection Protocol, schema/validation, forbidden-language scan, number provenance.
"""
import os
import sys

import numpy as np
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "tools"))

from bazar_audit_engine import run_audit, audit_from_df
from bazar_playbook import (
    generate_playbook, validate_playbook, render_playbook, render_rule_text,
    PlaybookValidationError, OPS, LICENSE_CANDIDATE, LICENSE_DATA_COLLECTION,
)
from monte_carlo_validation import make_random_trader

PATHS = {k: os.path.join(BASE_DIR, "sample_data", f"bazar_sample_{v}_trader.csv")
         for k, v in (("GOOD", "good"), ("AVERAGE", "average"), ("PROBLEM", "behavior_problem"))}


def _ins(iid, severity, observation, snap, conf="HIGH", n=50):
    s = dict(snap); s["observation"] = observation
    return {"insight_id": iid, "severity": severity, "confidence": conf, "sample_size": n,
            "metric_snapshot": s, "message": "", "recommended_action": "",
            "title_fa": "", "body_fa": ""}


def _audit(insights, total=60, ok=True, cm=None):
    return {"trader_id": "X", "total_trades": total, "sample_size_ok": ok,
            "r_mode": "pnl_only", "core_metrics": cm or {"win_rate": 0.4, "breakeven_wr": 0.5,
            "profit_factor": 0.8, "payoff_ratio": 0.8, "expectancy_dollar": -5.0,
            "expectancy_R": -0.05}, "insights": insights, "warnings": []}


# ── determinism + schema/validation ─────────────────────────────────────────────
def test_determinism_and_validates():
    a = run_audit(PATHS["AVERAGE"], "AVERAGE")
    p1 = generate_playbook(a.to_dict()).to_dict()
    p2 = generate_playbook(a.to_dict()).to_dict()
    assert p1 == p2                       # pure function, no clock/RNG
    validate_playbook(p1)                 # contract holds on real output
    assert p1["generated_at"] is None     # caller stamps time, not the engine


def test_all_samples_validate_and_render():
    for name, path in PATHS.items():
        pb = generate_playbook(run_audit(path, name).to_dict()).to_dict()
        validate_playbook(pb)
        for lang in ("en", "fa", "ar"):
            txt = render_playbook(pb, lang)
            assert isinstance(txt, str) and len(txt) > 0


# ── verb-set + source enforcement ───────────────────────────────────────────────
def test_validation_rejects_illegal_op_and_missing_source():
    pb = generate_playbook(run_audit(PATHS["PROBLEM"], "PROBLEM").to_dict()).to_dict()
    assert all(r["op"] in OPS for r in pb["rules"])
    assert all(r["source"] for r in pb["rules"])
    bad = {"license": LICENSE_CANDIDATE, "rules": [{"op": "add", "source": "x"}]}
    try:
        validate_playbook(bad); assert False, "should reject op 'add'"
    except PlaybookValidationError:
        pass
    bad2 = {"license": LICENSE_CANDIDATE, "rules": [{"op": "limit", "source": ""}]}
    try:
        validate_playbook(bad2); assert False, "should reject missing source"
    except PlaybookValidationError:
        pass


# ── evidence discipline (the core honesty invariant) ─────────────────────────────
def test_evidence_discipline_across_samples():
    for name, path in PATHS.items():
        pb = generate_playbook(run_audit(path, name).to_dict()).to_dict()
        for r in pb["rules"]:
            st = r["evidence"]["status"]
            if st == "observation":
                assert r["op"] == "track", f"{name}: observation must be track, got {r['op']}"
            if st == "data_gap":
                assert r["op"] == "track"
            if r["op"] in ("remove", "limit"):
                assert st == "finding", f"{name}: firm rule must come from a finding"


# ── no firm rule from noise (L2 Monte-Carlo honesty analog, spec §12.4) ──────────
def test_no_firm_rule_fabricated_from_noise():
    rng = np.random.default_rng(2026)
    N = 40
    with_firm = 0
    for k in range(N):
        rep = audit_from_df(make_random_trader(rng, 120), f"MC{k}").to_dict()
        finding_ids = {i["insight_id"] for i in rep["insights"]
                       if not (i["metric_snapshot"] or {}).get("observation")
                       and not i["insight_id"].startswith("SAMPLE_SIZE")}
        pb = generate_playbook(rep).to_dict()
        firm = [r for r in pb["rules"] if r["op"] in ("remove", "limit", "paper_trade")]
        if firm:
            with_firm += 1
        for r in firm:
            if r["source"].startswith("engine:"):   # keep/setup strengths, not finding-derived
                continue
            assert r["source"] in finding_ids, (
                f"L2 fabricated a firm rule with no L1 finding: {r['source']}")
    assert with_firm / N <= 0.20, f"firm-rule rate on noise = {with_firm}/{N}"


# ── conflict resolver: >40% / <30 remaining → remove downgraded to limit ─────────
def test_conflict_resolver_downgrades_large_removal():
    snap = {"worst_session": {"session": "Asia", "trades": 50, "win_rate": 0.2, "avg_pnl": -30.0},
            "all_sessions": [{"session": "Asia", "trades": 50, "win_rate": 0.2, "avg_pnl": -30.0},
                             {"session": "NY", "trades": 10, "win_rate": 0.6, "avg_pnl": 20.0}],
            "counterfactual": {"current_pf": 0.8, "pf_without_segment": 1.3,
                               "current_net_pnl": -100, "net_pnl_without_segment": 400},
            "p_value": 0.001}
    a = _audit([_ins("SESSION_TOXICITY", "HIGH", False, snap)], total=60)
    pb = generate_playbook(a).to_dict()
    sess = [r for r in pb["rules"] if r["target"] == "session"][0]
    assert sess["op"] == "limit"                      # remove(50/60) would leave <30 → softened
    assert any("Conservative" in x or "fewer than 30" in x for x in pb["limitations"])


def test_conflict_resolver_allows_low_collateral_remove():
    snap = {"worst_session": {"session": "Asia", "trades": 8, "win_rate": 0.2, "avg_pnl": -30.0},
            "all_sessions": [{"session": "Asia", "trades": 8, "win_rate": 0.2, "avg_pnl": -30.0},
                             {"session": "NY", "trades": 92, "win_rate": 0.6, "avg_pnl": 20.0}],
            "counterfactual": {"current_pf": 0.8, "pf_without_segment": 1.3,
                               "current_net_pnl": -100, "net_pnl_without_segment": 400},
            "p_value": 0.001}
    a = _audit([_ins("SESSION_TOXICITY", "HIGH", False, snap)], total=100)
    pb = generate_playbook(a).to_dict()
    sess = [r for r in pb["rules"] if r["target"] == "session"][0]
    assert sess["op"] == "remove"                     # 8/100 removed, 92 remain → remove permitted


# ── systemic override: behavioral firm demoted to track, core leads ──────────────
def test_systemic_override_demotes_behavioral():
    sys_snap = {"win_rate": 0.3, "breakeven_win_rate": 0.55, "profit_factor": 0.7,
                "expectancy_R": -0.2, "gap_to_breakeven_pct": 25.0}
    sess_snap = {"worst_session": {"session": "Asia", "trades": 10, "win_rate": 0.2, "avg_pnl": -30.0},
                 "all_sessions": [{"session": "Asia", "trades": 10, "win_rate": 0.2, "avg_pnl": -30.0}],
                 "counterfactual": {"current_pf": 0.7, "pf_without_segment": 0.9,
                                    "current_net_pnl": -100, "net_pnl_without_segment": 50},
                 "p_value": 0.001}
    a = _audit([_ins("SYSTEMIC_UNDERPERFORMANCE", "HIGH", False, sys_snap),
                _ins("SESSION_TOXICITY", "HIGH", False, sess_snap)], total=100)
    pb = generate_playbook(a).to_dict()
    assert any(r["op"] == "paper_trade" and r["target"] == "strategy_core" for r in pb["rules"])
    sess = [r for r in pb["rules"] if r["target"] == "session"][0]
    assert sess["op"] == "track"          # demoted — don't trim sessions to fix a no-edge core


# ── keep rules from a data-supported strength ────────────────────────────────────
def test_f3_keep_demoted_under_systemic_core_paper_trade():
    # systemic finding + a positive session (→ would-be keep). Under a core paper_trade,
    # no `keep` must survive (mixed message); it becomes a 'track strongest area' note.
    sys_snap = {"win_rate": 0.35, "breakeven_win_rate": 0.55, "profit_factor": 0.7,
                "expectancy_R": -0.2, "gap_to_breakeven_pct": 20.0}
    sess_snap = {"worst_session": {"session": "Asia", "trades": 20, "win_rate": 0.2, "avg_pnl": -30.0},
                 "all_sessions": [{"session": "Asia", "trades": 20, "win_rate": 0.2, "avg_pnl": -30.0},
                                  {"session": "London", "trades": 40, "win_rate": 0.62, "avg_pnl": 28.0}],
                 "counterfactual": {"current_pf": 0.7, "pf_without_segment": 0.95,
                                    "current_net_pnl": -200, "net_pnl_without_segment": 100},
                 "p_value": 0.2}   # observation
    a = _audit([_ins("SYSTEMIC_UNDERPERFORMANCE", "HIGH", False, sys_snap),
                _ins("SESSION_TOXICITY", "LOW", True, sess_snap, conf="LOW", n=20)], total=120)
    pb = generate_playbook(a).to_dict()
    assert any(r["op"] == "paper_trade" and r["target"] == "strategy_core" for r in pb["rules"])
    assert not any(r["op"] == "keep" for r in pb["rules"]), "no keep should survive under core paper_trade"
    london = [r for r in pb["rules"] if str(r["value"]) == "London"]
    assert london and london[0]["op"] == "track"
    validate_playbook(pb)


def test_keep_rule_from_positive_segment():
    snap = {"worst_session": {"session": "Asia", "trades": 10, "win_rate": 0.2, "avg_pnl": -30.0},
            "all_sessions": [{"session": "Asia", "trades": 10, "win_rate": 0.2, "avg_pnl": -30.0},
                             {"session": "London", "trades": 40, "win_rate": 0.65, "avg_pnl": 25.0}],
            "counterfactual": {"current_pf": 0.9, "pf_without_segment": 1.2,
                               "current_net_pnl": 0, "net_pnl_without_segment": 300},
            "p_value": 0.2}    # observation (not significant)
    a = _audit([_ins("SESSION_TOXICITY", "LOW", True, snap, conf="LOW", n=10)], total=100)
    pb = generate_playbook(a).to_dict()
    keeps = [r for r in pb["rules"] if r["op"] == "keep"]
    assert any(r["value"] == "London" for r in keeps)
    assert all(r["source"] == "engine:strength" for r in keeps)


# ── low sample → Data Collection Protocol, no firm rules ─────────────────────────
def test_low_sample_data_collection_plan():
    a = _audit([_ins("SAMPLE_SIZE_INSUFFICIENT", "HIGH", False, {"trades": 12}, n=12)],
               total=12, ok=False)
    pb = generate_playbook(a).to_dict()
    assert pb["license"] == LICENSE_DATA_COLLECTION
    assert all(r["op"] in ("track",) for r in pb["rules"])
    assert "not strong enough" in pb["data_sufficiency"]["note"].lower()
    validate_playbook(pb)


# ── number provenance: rule evidence == source insight snapshot ──────────────────
# ── QA / red-team regressions (Wave 0L) ─────────────────────────────────────────
def test_qa_no_signal_or_advice_language():
    for name, path in PATHS.items():
        pb = generate_playbook(run_audit(path, name).to_dict()).to_dict()
        validate_playbook(pb)  # contract now forbids 'signal'
        for lang in ("en", "fa", "ar"):
            t = render_playbook(pb, lang).lower()
            for tok in ("signal", "buy ", "sell ", "price target", "take profit"):
                assert tok not in t, f"{name}/{lang}: forbidden '{tok}'"


def test_qa_over_restriction_limit_is_warned():
    # a MEDIUM session finding → `limit` (not remove) covering 50% of trades must
    # still carry an over-restriction warning (resolver previously warned only removes).
    snap = {"worst_session": {"session": "Asia", "trades": 50, "win_rate": 0.3, "avg_pnl": -20.0},
            "all_sessions": [{"session": "Asia", "trades": 50, "win_rate": 0.3, "avg_pnl": -20.0},
                             {"session": "NY", "trades": 50, "win_rate": 0.6, "avg_pnl": 15.0}],
            "counterfactual": {"current_pf": 0.9, "pf_without_segment": 1.2,
                               "current_net_pnl": -100, "net_pnl_without_segment": 200},
            "p_value": 0.01}
    a = _audit([_ins("SESSION_TOXICITY", "MEDIUM", False, snap)], total=100)
    pb = generate_playbook(a).to_dict()
    sess = [r for r in pb["rules"] if r["target"] == "session"][0]
    assert sess["op"] == "limit"
    assert any("more than 40%" in x for x in pb["limitations"]), pb["limitations"]


def test_number_provenance_counterfactual():
    a = run_audit(PATHS["AVERAGE"], "AVERAGE").to_dict()
    by_id = {i["insight_id"]: i for i in a["insights"]}
    pb = generate_playbook(a).to_dict()
    for r in pb["rules"]:
        cf = r["evidence"].get("counterfactual")
        if cf and r["source"] in by_id:
            assert cf == (by_id[r["source"]]["metric_snapshot"] or {}).get("counterfactual")
