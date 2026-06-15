"""
tools/l2_qa_redteam.py — L2 Playbook internal QA / red-team harness (Prompt 8).

Generates playbooks across the required demo profiles + adversarial edge cases and
runs automated safety/correctness/quality checks. Read-only on the engine; prints a
per-profile + global verdict and exits non-zero if any FAIL.

    python tools/l2_qa_redteam.py            # summary
    python tools/l2_qa_redteam.py --dump     # + rendered EN/FA/AR previews
"""
import os
import sys

import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_audit_engine import run_audit, audit_from_df
from bazar_playbook import generate_playbook, validate_playbook, render_playbook, render_rule_text

SAMPLES = {"GOOD": "good", "AVERAGE": "average", "PROBLEM": "behavior_problem"}

# Stricter-than-engine red-team token list (signal / advice / price language).
REDTEAM_TOKENS = ["buy", "sell", " long ", " short ", "entry signal", "price target",
                  "stop loss", "take profit", "guarant", "will profit", "profit guarantee",
                  "signal", "financial advice", "we recommend you trade", "leverage"]


# ── profile builders ─────────────────────────────────────────────────────────
def _df(rows):
    df = pd.DataFrame(rows)
    df["open_time"] = pd.to_datetime(df["open_time"])
    df["close_time"] = pd.to_datetime(df["close_time"])
    return df


def _trades(specs, with_balance=False):
    """specs: list of (session, symbol, pnl[, pnl_R]). Sequential timestamps."""
    rows = []
    t = pd.Timestamp("2026-01-05 09:00:00")
    bal = 10000.0
    for i, sp in enumerate(specs):
        sess, sym, pnl = sp[0], sp[1], sp[2]
        t += pd.Timedelta(hours=3)
        row = dict(trade_id=f"T{i:03d}", open_time=t, close_time=t + pd.Timedelta(minutes=30),
                   symbol=sym, side="BUY", session=sess, pnl=float(pnl))
        if len(sp) > 3:
            row["pnl_R"] = float(sp[3]); row["initial_risk_amount"] = 100.0
        if with_balance:
            row["balance_before"] = round(bal, 2); row["lot_or_size"] = 0.1
            bal += pnl
        rows.append(row)
    return _df(rows)


def profile_low_sample():
    df = _trades([("NY", "EURUSD", 20 if i % 2 else -15) for i in range(15)])
    return audit_from_df(df, "LOW_SAMPLE").to_dict()


def profile_all_wins():
    df = _trades([("NY", "EURUSD", 30 + i, 1.0) for i in range(60)])
    return audit_from_df(df, "ALL_WINS").to_dict()


def profile_scratch_heavy():
    specs = []
    for i in range(60):
        pnl = 0.0 if i % 3 == 0 else (40 if i % 2 else -35)
        specs.append(("NY", "EURUSD", pnl))
    return audit_from_df(_trades(specs), "SCRATCH_HEAVY").to_dict()


def profile_marginal_observation_heavy():
    # near-breakeven across 4 sessions / 3 symbols — patterns present but not significant
    sess = ["Asia", "London", "NY", "Overlap"]; syms = ["EURUSD", "XAUUSD", "NAS100"]
    specs = []
    for i in range(140):
        s = sess[i % 4]; sym = syms[i % 3]
        win = (i % 10) < 5
        pnl = (55 if win else -50)
        if s == "Asia":   # mildly worse, but noisy
            pnl = (45 if win else -55)
        specs.append((s, sym, pnl))
    return audit_from_df(_trades(specs), "OBS_HEAVY").to_dict()


def profile_extreme_toxic_session():
    # one session = 70% of trades, deeply negative; the rest positive
    specs = []
    for i in range(100):
        if i < 70:
            specs.append(("Asia", "EURUSD", -40 if (i % 5) else 20))   # mostly losing
        else:
            specs.append(("NY", "GBPJPY", 60 if (i % 4) else -20))     # mostly winning
    return audit_from_df(_trades(specs, with_balance=True), "EXTREME_TOXIC").to_dict()


def profile_systemic_with_strength():
    # hand-built audit: systemic finding + a POSITIVE session in all_sessions
    def ins(iid, sev, obs, snap, conf="HIGH", n=80):
        s = dict(snap); s["observation"] = obs
        return {"insight_id": iid, "severity": sev, "confidence": conf, "sample_size": n,
                "metric_snapshot": s, "message": "", "recommended_action": "",
                "title_fa": "", "body_fa": ""}
    sys_snap = {"win_rate": 0.35, "breakeven_win_rate": 0.55, "profit_factor": 0.7,
                "expectancy_R": -0.2, "gap_to_breakeven_pct": 20.0}
    sess_snap = {"worst_session": {"session": "Asia", "trades": 20, "win_rate": 0.2, "avg_pnl": -30.0},
                 "all_sessions": [{"session": "Asia", "trades": 20, "win_rate": 0.2, "avg_pnl": -30.0},
                                  {"session": "London", "trades": 40, "win_rate": 0.62, "avg_pnl": 28.0}],
                 "counterfactual": {"current_pf": 0.7, "pf_without_segment": 0.95,
                                    "current_net_pnl": -200, "net_pnl_without_segment": 100},
                 "p_value": 0.2}
    return {"trader_id": "SYS_STRENGTH", "total_trades": 120, "sample_size_ok": True,
            "r_mode": "full", "core_metrics": {"win_rate": 0.35, "breakeven_wr": 0.55,
            "profit_factor": 0.7, "payoff_ratio": 0.8, "expectancy_dollar": -10.0, "expectancy_R": -0.2},
            "insights": [ins("SYSTEMIC_UNDERPERFORMANCE", "HIGH", False, sys_snap),
                         ins("SESSION_TOXICITY", "LOW", True, sess_snap, conf="LOW", n=20)],
            "warnings": []}


PROFILES = {
    "GOOD": lambda: run_audit(os.path.join(BASE_DIR, "sample_data", "bazar_sample_good_trader.csv"), "GOOD").to_dict(),
    "AVERAGE": lambda: run_audit(os.path.join(BASE_DIR, "sample_data", "bazar_sample_average_trader.csv"), "AVERAGE").to_dict(),
    "PROBLEM": lambda: run_audit(os.path.join(BASE_DIR, "sample_data", "bazar_sample_behavior_problem_trader.csv"), "PROBLEM").to_dict(),
    "LOW_SAMPLE": profile_low_sample,
    "OBS_HEAVY_MARGINAL": profile_marginal_observation_heavy,
    "ALL_WINS": profile_all_wins,
    "SCRATCH_HEAVY": profile_scratch_heavy,
    "EXTREME_TOXIC_SESSION": profile_extreme_toxic_session,
    "SYSTEMIC_WITH_STRENGTH": profile_systemic_with_strength,
}


# ── checks (return list of (level, msg); level in PASS/WARN/FAIL) ──────────────
def _affected(rules):
    return sum(int((r.get("params") or {}).get("trades") or 0)
               for r in rules if r["op"] in ("remove", "limit") and r["target"] in ("session", "symbol"))


def run_checks(name, audit, pb):
    issues = []
    rules = pb["rules"]
    total = audit.get("total_trades", 0)

    # C1 forbidden language (rendered en/fa/ar + json text)
    blob = " ".join([pb.get("hypothesis", "")] + pb.get("limitations", [])
                    + pb.get("tracking_requirements", [])
                    + [render_rule_text(r, lg) for r in rules for lg in ("en", "fa", "ar")]).lower()
    hits = [tok.strip() for tok in REDTEAM_TOKENS if tok in blob]
    issues.append(("FAIL" if hits else "PASS", f"forbidden-language: {hits or 'none'}"))

    # C2 no firm action from observation/data_gap
    bad = [r for r in rules if r["op"] in ("remove", "limit") and r["evidence"]["status"] != "finding"]
    issues.append(("FAIL" if bad else "PASS",
                   f"firm-rule-from-non-finding: {[r['source'] for r in bad] or 'none'}"))

    # C3 contradictions: same (target,value) both kept and restricted
    keys_keep = {(r["target"], str(r["value"])) for r in rules if r["op"] == "keep"}
    keys_restrict = {(r["target"], str(r["value"])) for r in rules if r["op"] in ("remove", "limit", "paper_trade")}
    contra = keys_keep & keys_restrict
    issues.append(("FAIL" if contra else "PASS", f"keep-vs-restrict contradiction: {contra or 'none'}"))

    # C3b clarity: keep rule coexisting with a core paper_trade (mixed message)
    has_core_paper = any(r["op"] == "paper_trade" and r["target"] == "strategy_core" for r in rules)
    has_keep = any(r["op"] == "keep" for r in rules)
    if has_core_paper and has_keep:
        issues.append(("WARN", "keep rule present alongside core paper_trade (mixed message)"))

    # C4 over-restriction must carry a warning
    aff = _affected(rules)
    share = (aff / total) if total else 0
    if share > 0.40:
        warned = any(("more than" in x or "minimum-disruption" in x or "Conservative" in x
                      or "fewer than 30" in x or ">40" in x or "soften" in x.lower()) for x in pb["limitations"])
        issues.append(("PASS" if warned else "FAIL",
                       f"over-restriction {share:.0%} of trades {'(warned)' if warned else '(NO warning!)'}"))
    else:
        issues.append(("PASS", f"restriction share {share:.0%}"))

    # C5 clear 30-trade protocol
    nc = pb["next_cycle"]
    ok5 = nc.get("min_trades") == 30 and nc.get("success_metrics", {}).get("metrics") is not None \
        and nc.get("failure_conditions")
    issues.append(("PASS" if ok5 else "FAIL", "30-trade protocol present" if ok5 else "protocol incomplete"))

    # C6 success/failure engine-sourced + uncertainty band
    sm = nc.get("success_metrics", {})
    ok6 = sm.get("computed_by") == "engine" and sm.get("with_uncertainty_band") is True
    issues.append(("PASS" if ok6 else "FAIL", "criteria engine-sourced + uncertainty band"))

    # C7 validates
    try:
        validate_playbook(pb); issues.append(("PASS", "validate_playbook"))
    except Exception as e:
        issues.append(("FAIL", f"validate_playbook raised: {e}"))

    # C8 determinism
    pb2 = generate_playbook(audit).to_dict()
    issues.append(("PASS" if pb2 == pb else "FAIL", "deterministic regeneration"))

    # C9 license correctness
    exp = "data_collection_plan" if (not audit.get("sample_size_ok") or total < 30) else "playbook_candidate"
    issues.append(("PASS" if pb["license"] == exp else "FAIL",
                   f"license={pb['license']} (expected {exp})"))

    return issues


def main(dump=False):
    overall_fail = 0
    overall_warn = 0
    for name, build in PROFILES.items():
        audit = build()
        pb = generate_playbook(audit).to_dict()
        issues = run_checks(name, audit, pb)
        fails = [m for lv, m in issues if lv == "FAIL"]
        warns = [m for lv, m in issues if lv == "WARN"]
        overall_fail += len(fails); overall_warn += len(warns)
        tag = "FAIL" if fails else ("WARN" if warns else "PASS")
        print(f"\n=== {name} [{tag}] license={pb['license']} rules={len(pb['rules'])} "
              f"conf={pb['confidence']} ===")
        for lv, m in issues:
            if lv != "PASS":
                print(f"   [{lv}] {m}")
        if dump:
            print("   --- EN preview ---")
            print("   " + render_playbook(pb, "en").replace("\n", "\n   ")[:1200])
    print(f"\n==== GLOBAL: {overall_fail} FAIL, {overall_warn} WARN ====")
    return overall_fail


if __name__ == "__main__":
    raise SystemExit(1 if main(dump="--dump" in sys.argv) else 0)
