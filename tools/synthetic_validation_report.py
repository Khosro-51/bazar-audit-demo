"""
tools/synthetic_validation_report.py — L1→L2 synthetic golden-dataset validation.

Runs every controlled statement in tests/synthetic_lab.py through the deterministic
L1 audit engine and the L2 playbook compiler, compares the ACTUAL output to the
case's EXPECTED semantic contract, and writes a pass/fail report to
reports/synthetic_validation_<YYYYMMDD>.md.

Principle: synthetic controlled statements validate the algorithm; trader feedback
validates usability/trust and comes later. No LLM, no live data, no network.

    python tools/synthetic_validation_report.py            # write report, exit 0/1
    python tools/synthetic_validation_report.py --print     # also print to stdout
"""
import os
import sys
from datetime import datetime, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for p in (BASE_DIR, os.path.join(BASE_DIR, "tests"), os.path.join(BASE_DIR, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

from bazar_audit_engine import audit_from_df            # noqa: E402
from bazar_playbook import generate_playbook, validate_playbook, render_playbook, OPS  # noqa: E402
from synthetic_lab import GENERATORS                    # noqa: E402

FORBIDDEN_PHRASES = ["buy", "sell", " long ", " short ", "entry price", "stop loss",
                     "take profit", "signal", "price target", "profit guarantee",
                     "financial advice", "leverage", "guaranteed"]

# Expected semantic contract per case. Keys (all optional):
#   expect_findings   : insight_ids that MUST be findings (observation == False)
#   forbid_findings   : insight_ids that must NOT be findings
#   no_med_high       : True → no MEDIUM/HIGH insight at all (clean / noise)
#   forbidden_l2_verbs: ops that must NOT appear anywhere in the playbook
#   require_rules     : list of dicts {op:set|None, target, value:any|None, source:str|None}
#   firm_only_on      : {target: {allowed values}} → any remove/limit on `target`
#                       must hit an allowed value (no cross-contamination)
#   l2_track_only     : True → every rule op is 'track'
#   license           : expected playbook license
EXPECT = {
    "GOOD_TRADER_CLEAN": dict(
        desc="Positive edge, single session/symbol, no intraday clustering.",
        no_med_high=True, forbidden_l2_verbs={"remove", "limit"}),
    "NOISE_TRADER_RANDOM": dict(
        desc="Pure noise (zero edge), sizes/sessions independent of outcome.",
        no_med_high=True, forbidden_l2_verbs={"remove", "limit"}),
    "SESSION_TOXICITY_CONFIRMED": dict(
        desc="One session (Asia) clearly negative; others fine.",
        expect_findings={"SESSION_TOXICITY"},
        require_rules=[{"op": {"limit", "remove"}, "target": "session", "value": "Asia",
                        "source": "SESSION_TOXICITY"}],
        firm_only_on={"session": {"Asia"}}),
    "SYMBOL_NO_EDGE_CONFIRMED": dict(
        desc="One traded symbol (XAUUSD) no-edge; others fine.",
        expect_findings={"SYMBOL_NO_EDGE"},
        require_rules=[{"op": {"limit", "paper_trade", "remove"}, "target": "symbol",
                        "value": "XAUUSD", "source": "SYMBOL_NO_EDGE"}],
        firm_only_on={"symbol": {"XAUUSD"}}),
    "POST_LOSS_DECAY_CONFIRMED": dict(
        desc="Win rate collapses right after a loss (fast re-entry); no systemic.",
        expect_findings={"POST_LOSS_DECAY"}, forbid_findings={"SYSTEMIC_UNDERPERFORMANCE"},
        require_rules=[{"op": {"test", "track"}, "target": "post_loss_review", "value": None}]),
    "PAYOFF_IMBALANCE_CONFIRMED": dict(
        desc="Small wins, big losses (payoff ratio ~0.4); expectancy ~0.",
        expect_findings={"PAYOFF_IMBALANCE"},
        require_rules=[{"op": {"test", "track"}, "target": "exit", "value": None}],
        forbid_payoff_firm=True),
    "TRADE_COUNT_CLIFF_CHRONOLOGICAL": dict(
        desc="WR drops after trade #3/day; supplied index is misleading (D3).",
        expect_findings={"TRADE_COUNT_CLIFF"},
        require_rules=[{"op": {"limit"}, "target": "trade_count", "value": 2}]),
    "WEAK_EVIDENCE_OBSERVATION_ONLY": dict(
        desc="Payoff ratio in the soft band → LOW observation, not a finding.",
        forbid_findings={"PAYOFF_IMBALANCE"}, forbidden_l2_verbs={"remove", "limit"},
        require_rules=[{"op": {"track"}, "target": "exit", "value": None}]),
    "DATA_GAP_LOW_SAMPLE": dict(
        desc="n=15 (<30) → data-collection only.",
        expect_findings={"SAMPLE_SIZE_INSUFFICIENT"}, license="data_collection_plan",
        l2_track_only=True),
    "MIXED_MULTI_LEAK_TRADER": dict(
        desc="Two independent leaks (toxic session + no-edge symbol); overall edge intact.",
        expect_findings={"SESSION_TOXICITY", "SYMBOL_NO_EDGE"},
        forbid_findings={"SYSTEMIC_UNDERPERFORMANCE"},
        require_rules=[
            {"op": {"limit", "remove"}, "target": "session", "value": "Asia",
             "source": "SESSION_TOXICITY"},
            {"op": {"limit", "paper_trade", "remove"}, "target": "symbol", "value": "XAUUSD",
             "source": "SYMBOL_NO_EDGE"}],
        firm_only_on={"session": {"Asia"}, "symbol": {"XAUUSD"}}),
}


def _run(name):
    audit = audit_from_df(GENERATORS[name](), name).to_dict()
    pb = generate_playbook(audit).to_dict()
    return audit, pb


def _findings(audit):
    return {i["insight_id"] for i in audit["insights"]
            if not (i["metric_snapshot"] or {}).get("observation")
            and not i["insight_id"].startswith("SAMPLE_SIZE")}


def _check(name, audit, pb):
    """Return (passed: bool, checks: list[(label, ok, detail)])."""
    exp = EXPECT[name]
    insights = audit["insights"]
    finds = _findings(audit)
    rules = pb["rules"]
    checks = []

    # contract validity (legal ops + every rule sourced + no forbidden token)
    try:
        validate_playbook(pb)
        checks.append(("playbook validates (legal ops, sourced, clean)", True, ""))
    except Exception as e:
        checks.append(("playbook validates", False, str(e)))
    checks.append(("every rule has source", all(r.get("source") for r in rules),
                   ""))
    checks.append(("every op in locked verb set", all(r["op"] in OPS for r in rules), ""))

    if exp.get("no_med_high"):
        bad = [i["insight_id"] for i in insights if i["severity"] in ("MEDIUM", "HIGH")
               and not (i["metric_snapshot"] or {}).get("observation")]
        checks.append(("no MEDIUM/HIGH false finding", not bad, ",".join(bad)))

    for fid in exp.get("expect_findings", set()):
        if fid.startswith("SAMPLE_SIZE"):
            ok = any(i["insight_id"] == fid for i in insights)
        else:
            ok = fid in finds
        checks.append((f"L1 finding present: {fid}", ok, ""))

    for fid in exp.get("forbid_findings", set()):
        checks.append((f"L1 NOT a finding: {fid}", fid not in finds, ""))

    for fv in exp.get("forbidden_l2_verbs", set()):
        present = [f"{r['op']} {r['target']}={r['value']}" for r in rules if r["op"] == fv]
        checks.append((f"no '{fv}' rule", not present, "; ".join(present)))

    if exp.get("forbid_payoff_firm"):
        bad = [r for r in rules if r.get("source") == "PAYOFF_IMBALANCE"
               and r["op"] in ("remove", "limit")]
        checks.append(("payoff did not fabricate firm remove/limit", not bad, ""))

    for req in exp.get("require_rules", []):
        def _m(r):
            if req.get("op") and r["op"] not in req["op"]:
                return False
            if req.get("target") and r["target"] != req["target"]:
                return False
            if req.get("value") is not None and r["value"] != req["value"]:
                return False
            if req.get("source") and r.get("source") != req["source"]:
                return False
            return True
        ok = any(_m(r) for r in rules)
        label = (f"L2 rule {sorted(req.get('op', []))} on {req.get('target')}"
                 f"={req.get('value')}" + (f" (src {req['source']})" if req.get("source") else ""))
        checks.append((label, ok, ""))

    for target, allowed in exp.get("firm_only_on", {}).items():
        bad = [r["value"] for r in rules if r["op"] in ("remove", "limit")
               and r["target"] == target and r["value"] not in allowed]
        checks.append((f"firm {target} rules only on {sorted(allowed)}", not bad,
                       ",".join(map(str, bad))))

    if exp.get("l2_track_only"):
        bad = [r["op"] for r in rules if r["op"] != "track"]
        checks.append(("L2 is track-only", not bad, ",".join(bad)))

    if exp.get("license"):
        checks.append((f"license == {exp['license']}", pb["license"] == exp["license"],
                       pb["license"]))

    # forbidden language across all rendered languages
    lang_bad = []
    for lang in ("en", "fa", "ar"):
        t = render_playbook(pb, lang).lower()
        lang_bad += [f"{lang}:{ph.strip()}" for ph in FORBIDDEN_PHRASES if ph in t]
    checks.append(("no forbidden language (en/fa/ar)", not lang_bad, "; ".join(lang_bad)))

    return all(ok for _, ok, _ in checks), checks


def build():
    lines = []
    P = lines.append
    P("# Synthetic Statement Lab — L1→L2 Validation Report\n")
    P(f"**Date:** {datetime.now(timezone.utc).date()} · **Cases:** {len(GENERATORS)} · "
      "**Gate:** internal algorithm validation (not trader feedback).\n")
    P("> Trader feedback validates usability and trust. Synthetic controlled statements "
      "validate the algorithm.\n")
    P("Each case is a deterministic controlled statement with a known expected diagnosis. "
      "A case PASSES when its actual L1 insights, evidence class, and L2 rule verbs match "
      "the expected semantic contract, every rule is sourced to an `insight_id`, and no "
      "forbidden (buy/sell/price/signal/advice) language appears in any language.\n")

    all_pass = True
    summary = []
    detail = []
    for name in GENERATORS:
        audit, pb = _run(name)
        ok, checks = _check(name, audit, pb)
        all_pass &= ok
        exp = EXPECT.get(name, {})
        n = audit["total_trades"]
        l1 = [f"{i['insight_id']}/{i['severity']}/"
              f"{'obs' if (i['metric_snapshot'] or {}).get('observation') else 'FIND'}"
              for i in audit["insights"]]
        l2 = [f"{r['op']} {r['target']}={r['value']}" for r in pb["rules"]]
        summary.append((name, n, "✅ PASS" if ok else "❌ FAIL"))

        detail.append(f"\n## {name} — {'✅ PASS' if ok else '❌ FAIL'}\n")
        detail.append(f"*{exp.get('desc', '')}*  · n={n} · license=`{pb['license']}`\n")
        detail.append(f"- **Input:** `tests/synthetic_lab.py::"
                      f"{GENERATORS[name].__name__}()` (deterministic, seeded)")
        detail.append(f"- **Actual L1:** {', '.join(l1) or '—'}")
        detail.append(f"- **Actual L2:** {', '.join(l2) or '—'}")
        if exp.get("expect_findings"):
            detail.append(f"- **Expected findings:** {', '.join(sorted(exp['expect_findings']))}")
        if exp.get("forbidden_l2_verbs"):
            detail.append(f"- **Forbidden L2 verbs:** {', '.join(sorted(exp['forbidden_l2_verbs']))}")
        detail.append("- **Checks:**")
        for label, cok, det in checks:
            detail.append(f"    - {'✅' if cok else '❌'} {label}"
                          + (f" — `{det}`" if det and not cok else ""))

    P("## Summary\n")
    P("| # | Case | Trades | Result |")
    P("|---|------|--------|--------|")
    for idx, (name, n, res) in enumerate(summary, 1):
        P(f"| {idx} | {name} | {n} | {res} |")
    P(f"\n**Overall: {'✅ ALL PASS' if all_pass else '❌ FAILURES PRESENT'}** "
      f"({sum(1 for _, _, r in summary if 'PASS' in r)}/{len(summary)} cases pass)\n")
    P("\n---")
    lines += detail
    return all_pass, "\n".join(lines)


def main():
    all_pass, md = build()
    out = os.path.join(BASE_DIR, "reports",
                       f"synthetic_validation_{datetime.now(timezone.utc):%Y%m%d}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(md + "\n")
    rel = os.path.relpath(out, BASE_DIR)
    print(f"wrote {rel}  ->  {'ALL PASS' if all_pass else 'FAILURES PRESENT'}")
    if "--print" in sys.argv:
        print("\n" + md)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
