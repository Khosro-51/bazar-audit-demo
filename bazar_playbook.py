"""
bazar_playbook.py — L2 Personal Strategy Playbook Engine (L2-core, deterministic).

Implements docs/l2_playbook_engine_spec.md and the locked agreement in
BAZAR_L2_L3_AGENT_DESIGN.md §8. This is Line 2: **fully deterministic, no LLM,
no live market data, no engine changes**. It compiles an L1 audit result into a
Personal Strategy Playbook (Candidate v1) using a LOCKED verb set, where every
number traces to an engine insight snapshot and every rule carries a `source`.

Locked §15 decisions (this build):
  * `limit` is the default; `remove` only for a confirmed HIGH finding AND when the
    conflict resolver permits (collateral low).
  * If firm `remove` rules would drop >40% of historical trades → downgrade to `limit`.
  * If testable trades remaining after firm rules < 30 → Data Collection / Conservative
    Protocol instead of a full Playbook Candidate.
  * `keep` rules ship by default, only for existing data-supported components.
  * `setup_tag` rules only when user-supplied with coverage >= 70%; NO inferred
    clustering in L2-core.
  * en/fa/ar via a fixed glossary, English source of truth, no LLM.

The module has NO Streamlit/LLM dependency and is deterministic (no clocks/RNG):
`generated_at` is stamped by the caller, never here.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

SCHEMA_VERSION = "l2.v1"
MIN_CYCLE_TRADES = 30
REMOVE_TRADE_SHARE_MAX = 0.40   # firm removes above this share of trades → downgrade
VERDICT_STATES = ["improved", "worsened", "insufficient_evidence"]

# Locked verb set — the ONLY allowed ops, on EXISTING components only.
OPS = {"keep", "remove", "limit", "paper_trade", "track", "test"}
LICENSE_CANDIDATE = "playbook_candidate"
LICENSE_DATA_COLLECTION = "data_collection_plan"

# Tokens that must never appear in any rendered text (Forbidden Output Policy).
_FORBIDDEN_TOKENS = ("buy", "sell", "long ", "short ", "signal", "price target",
                     "stop loss level", "take profit", "guaranteed", "will profit",
                     "profit guarantee")


# ── data model ────────────────────────────────────────────────────────────────

@dataclass
class Evidence:
    status: str                      # finding | observation | data_gap | strength
    confidence: str = "LOW"          # LOW | MEDIUM | HIGH
    n: int = 0
    p_value: Optional[float] = None
    counterfactual: Optional[dict] = None

    def to_dict(self) -> dict:
        return {"status": self.status, "confidence": self.confidence, "n": self.n,
                "p_value": self.p_value, "counterfactual": self.counterfactual}


@dataclass
class PlaybookRule:
    op: str
    target: str
    value: Any
    source: str                      # engine insight_id | engine:strength
    evidence: Evidence
    rationale_key: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"op": self.op, "target": self.target, "value": self.value,
                "source": self.source, "evidence": self.evidence.to_dict(),
                "rationale_key": self.rationale_key, "params": self.params}


@dataclass
class PlaybookCycle:
    min_trades: int = MIN_CYCLE_TRADES
    success_metrics: dict = field(default_factory=dict)
    failure_conditions: dict = field(default_factory=dict)
    verdict_states: list = field(default_factory=lambda: list(VERDICT_STATES))

    def to_dict(self) -> dict:
        return {"min_trades": self.min_trades,
                "success_metrics": self.success_metrics,
                "failure_conditions": self.failure_conditions,
                "verdict_states": self.verdict_states}


@dataclass
class Playbook:
    playbook_id: str
    based_on_report_id: str
    license: str
    hypothesis: str
    data_sufficiency: dict
    rules: list                       # list[PlaybookRule]
    next_cycle: PlaybookCycle
    tracking_requirements: list
    confidence: str
    limitations: list
    schema_version: str = SCHEMA_VERSION
    generated_at: Optional[str] = None   # stamped by caller, NOT the pure engine

    def to_dict(self) -> dict:
        return {
            "playbook_id": self.playbook_id,
            "based_on_report_id": self.based_on_report_id,
            "schema_version": self.schema_version,
            "license": self.license,
            "generated_at": self.generated_at,
            "hypothesis": self.hypothesis,
            "data_sufficiency": self.data_sufficiency,
            "rules": [r.to_dict() for r in self.rules],
            "next_cycle": self.next_cycle.to_dict(),
            "tracking_requirements": self.tracking_requirements,
            "confidence": self.confidence,
            "limitations": self.limitations,
        }


# ── helpers ────────────────────────────────────────────────────────────────────

_CONF_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
_RANK_CONF = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}


def _conf_from_n(n: int) -> str:
    if n < 20:
        return "LOW"
    if n < 50:
        return "MEDIUM"
    return "HIGH"


def _cap(conf: str, ceiling: str) -> str:
    return _RANK_CONF[min(_CONF_RANK.get(conf, 0), _CONF_RANK.get(ceiling, 0))]


def _status_of(ins: dict) -> str:
    if str(ins.get("insight_id", "")).startswith("SAMPLE_SIZE"):
        return "data_gap"
    return "observation" if (ins.get("metric_snapshot") or {}).get("observation") else "finding"


def _ev(ins: dict, status: str, snap: dict) -> Evidence:
    return Evidence(status=status,
                    confidence=str(ins.get("confidence", "LOW")),
                    n=int(ins.get("sample_size", 0) or 0),
                    p_value=snap.get("p_value"),
                    counterfactual=snap.get("counterfactual"))


# ── core: insight → rules ───────────────────────────────────────────────────────

def _rules_from_insight(ins: dict) -> list:
    """Map one L1 insight to zero+ tentative playbook rules (§6). Tentative `remove`
    is only proposed for HIGH segment findings; the conflict resolver decides later."""
    iid = ins.get("insight_id", "")
    snap = ins.get("metric_snapshot") or {}
    status = _status_of(ins)
    sev = str(ins.get("severity", "LOW"))
    out = []

    if iid == "SYSTEMIC_UNDERPERFORMANCE" and status == "finding":
        out.append(PlaybookRule("paper_trade", "strategy_core", "until_edge_proven", iid,
                                _ev(ins, status, snap), "paper_trade_core",
                                {"wr": snap.get("win_rate"), "bwr": snap.get("breakeven_win_rate"),
                                 "pf": snap.get("profit_factor")}))
        out.append(PlaybookRule("track", "edge", "net_after_costs", iid,
                                _ev(ins, status, snap), "track_costs", {}))

    elif iid == "EDGE_BELOW_BREAKEVEN":
        out.append(PlaybookRule("track", "costs", "spread_commission", iid,
                                _ev(ins, status, snap), "track_costs",
                                {"gap": snap.get("gap_to_breakeven_pct")}))

    elif iid == "SESSION_TOXICITY":
        w = snap.get("worst_session") or {}
        name = w.get("session", "")
        if status == "finding":
            op = "remove" if sev == "HIGH" else "limit"   # tentative; resolver may downgrade
            out.append(PlaybookRule(op, "session", name, iid, _ev(ins, status, snap),
                                    f"{op}_session",
                                    {"session": name, "trades": w.get("trades"),
                                     "avg_pnl": w.get("avg_pnl"), "p": snap.get("p_value")}))
        else:
            out.append(PlaybookRule("track", "session", name, iid, _ev(ins, status, snap),
                                    "track_segment",
                                    {"kind": "session", "name": name, "p": snap.get("p_value")}))

    elif iid == "SYMBOL_NO_EDGE":
        w = snap.get("worst_symbol") or {}
        name = w.get("symbol", "")
        if status == "finding":
            op = "remove" if sev == "HIGH" else "paper_trade"   # tentative
            out.append(PlaybookRule(op, "symbol", name, iid, _ev(ins, status, snap),
                                    f"{op}_symbol",
                                    {"symbol": name, "trades": w.get("trades"),
                                     "total_pnl": w.get("total_pnl"), "p": snap.get("p_value")}))
        else:
            out.append(PlaybookRule("track", "symbol", name, iid, _ev(ins, status, snap),
                                    "track_segment",
                                    {"kind": "symbol", "name": name, "p": snap.get("p_value")}))

    elif iid == "TRADE_COUNT_CLIFF":
        cliff = snap.get("cliff_at_trade")
        cap = (cliff - 1) if isinstance(cliff, int) else None
        if status == "finding":
            out.append(PlaybookRule("limit", "trade_count", cap, iid, _ev(ins, status, snap),
                                    "limit_trade_count",
                                    {"cap": cap, "cliff": cliff, "drop": snap.get("drop_pct")}))
        else:
            out.append(PlaybookRule("track", "trade_count", "sequence_per_day", iid,
                                    _ev(ins, status, snap), "track_segment",
                                    {"kind": "trade_count", "name": f"#{cliff}",
                                     "p": snap.get("p_value")}))

    elif iid == "POST_LOSS_FAST_REENTRY" and status == "finding":
        out.append(PlaybookRule("limit", "cooldown", 60, iid, _ev(ins, status, snap),
                                "limit_cooldown",
                                {"minutes": 60, "fast_wr": snap.get("fast_wr"),
                                 "n": snap.get("n_fast")}))

    elif iid == "POST_LOSS_DECAY" and status == "finding":
        out.append(PlaybookRule("test", "post_loss_review", "structured_review", iid,
                                _ev(ins, status, snap), "test_post_loss",
                                {"drop": snap.get("wr_drop_pct"), "n": snap.get("n_post_loss")}))
        out.append(PlaybookRule("track", "post_loss_review", "post_loss_wr", iid,
                                _ev(ins, status, snap), "track_segment",
                                {"kind": "post_loss", "name": "post-loss WR", "p": None}))

    elif iid == "DRAWDOWN_RECOVERY_SIZING":
        if status == "finding":
            out.append(PlaybookRule("limit", "risk", "fixed_pct", iid, _ev(ins, status, snap),
                                    "limit_risk", {"ratio": snap.get("size_ratio")}))
        else:
            out.append(PlaybookRule("track", "risk", "size_vs_state", iid, _ev(ins, status, snap),
                                    "track_segment", {"kind": "risk", "name": "position size",
                                                      "p": snap.get("p_value")}))

    elif iid == "PAYOFF_IMBALANCE":
        if status == "finding":
            out.append(PlaybookRule("test", "exit", "let_winners_run", iid, _ev(ins, status, snap),
                                    "test_exit", {"ratio": snap.get("payoff_ratio"),
                                                  "unit": snap.get("unit", "")}))
        out.append(PlaybookRule("track", "exit", "mfe_mae_exit_reason", iid, _ev(ins, status, snap),
                                "track_segment", {"kind": "exit", "name": "exits", "p": None}))

    return out


def _keep_rules(insights: list) -> list:
    """`keep` rules from data-supported strengths — drawn ONLY from engine snapshots
    (all_sessions / all_symbols), never recomputed in L2 (golden rule). Picks the
    single best positive, adequately-sampled segment of each kind."""
    out = []
    for ins in insights:
        snap = ins.get("metric_snapshot") or {}
        iid = ins.get("insight_id", "")
        if iid == "SESSION_TOXICITY":
            segs = snap.get("all_sessions") or []
            worst = (snap.get("worst_session") or {}).get("session")
            pos = [s for s in segs if s.get("avg_pnl", 0) > 0 and s.get("session") != worst
                   and int(s.get("trades", 0)) >= 5]
            if pos:
                best = max(pos, key=lambda s: s.get("avg_pnl", 0))
                out.append(PlaybookRule("keep", "session", best["session"], "engine:strength",
                                        Evidence("strength", _conf_from_n(int(best.get("trades", 0))),
                                                 int(best.get("trades", 0))),
                                        "keep_segment",
                                        {"kind": "session", "name": best["session"],
                                         "avg_pnl": best.get("avg_pnl")}))
        elif iid == "SYMBOL_NO_EDGE":
            segs = snap.get("all_symbols") or []
            worst = (snap.get("worst_symbol") or {}).get("symbol")
            pos = [s for s in segs if s.get("total_pnl", 0) > 0 and s.get("symbol") != worst
                   and int(s.get("trades", 0)) >= 8]
            if pos:
                best = max(pos, key=lambda s: s.get("total_pnl", 0))
                out.append(PlaybookRule("keep", "symbol", best["symbol"], "engine:strength",
                                        Evidence("strength", _conf_from_n(int(best.get("trades", 0))),
                                                 int(best.get("trades", 0))),
                                        "keep_segment",
                                        {"kind": "symbol", "name": best["symbol"],
                                         "total_pnl": best.get("total_pnl")}))
    return out


def _affected_trades(rule: PlaybookRule) -> int:
    return int((rule.params or {}).get("trades") or 0)


def _resolve_conflicts(rules: list, total_trades: int, limitations: list):
    """Locked §15: a `remove` is permitted only if firm removes keep >40% of trades
    AND leave >=30 testable trades; otherwise downgrade `remove`→`limit`. Returns
    (rules, conservative_flag)."""
    removes = [r for r in rules if r.op == "remove"]
    if not removes:
        return rules, False
    removed = sum(_affected_trades(r) for r in removes)
    share = (removed / total_trades) if total_trades else 1.0
    remaining = total_trades - removed
    conservative = remaining < MIN_CYCLE_TRADES
    if share > REMOVE_TRADE_SHARE_MAX or conservative:
        for r in removes:
            r.op = "limit"
            r.rationale_key = r.rationale_key.replace("remove_", "limit_")
        if conservative:
            limitations.append(
                "Removing the flagged components would leave fewer than 30 testable "
                "trades, so removals were softened to limits (Conservative Protocol).")
        else:
            limitations.append(
                f"Flagged removals would drop >{int(REMOVE_TRADE_SHARE_MAX*100)}% of your "
                "trades, so they were softened to limits (minimum-disruption rule).")
    return rules, conservative


def _over_restriction_warning(rules: list, total_trades: int, limitations: list):
    """QA (Wave 0L): warn when firm restrictions (remove/limit/paper_trade on a
    session/symbol) touch more than the share threshold of historical trades — even
    when they are `limit`/`paper_trade`, not `remove` (the resolver only warns for
    removes). Uses the largest single restriction's share to avoid double-counting
    overlapping segments. Adds a warning only (never silently over-restricts)."""
    if not total_trades:
        return
    shares = [((r.params or {}).get("trades") or 0) / total_trades
              for r in rules if r.op in ("remove", "limit", "paper_trade")
              and r.target in ("session", "symbol")]
    if shares and max(shares) > REMOVE_TRADE_SHARE_MAX:
        already = any(("more than" in x or "minimum-disruption" in x or "Conservative" in x
                       or "fewer than 30" in x) for x in limitations)
        if not already:
            pct = int(REMOVE_TRADE_SHARE_MAX * 100)
            limitations.append(
                f"These adjustments touch more than {pct}% of your historical trades — "
                "applying them all at once would change most of your trading. Introduce "
                "them gradually and re-check next cycle.")


def _apply_systemic_override(rules: list, insights: list, limitations: list):
    """If the core edge is unproven (systemic finding), demote behavioral firm rules
    to `track` — you don't fix a no-edge core by trimming sessions (spec §7)."""
    has_systemic = any(i.get("insight_id") == "SYSTEMIC_UNDERPERFORMANCE"
                       and not (i.get("metric_snapshot") or {}).get("observation")
                       for i in insights)
    if not has_systemic:
        return rules
    demoted = False
    for r in rules:
        if r.source != "SYSTEMIC_UNDERPERFORMANCE" and r.op in ("remove", "limit"):
            r.op = "track"
            r.rationale_key = "track_segment"
            r.params = {"kind": r.target, "name": str(r.value), "p": (r.evidence.p_value)}
            demoted = True
        elif r.op == "keep":
            # F3 fix (Wave 0M): don't say "keep trading X" while the whole core is being
            # paper-traded — that's a mixed message. Demote keeps to a tracking note about
            # the strongest area, to confirm once the core edge is proven.
            r.op = "track"
            r.rationale_key = "track_strength_pending_core"
            r.params = {"kind": r.target, "name": str(r.value)}
            demoted = True
    if demoted:
        limitations.append(
            "Your core strategy is below breakeven with evidence; behavioral fixes and "
            "strengths were demoted to tracking until the core edge is proven "
            "(paper-trade the core first).")
    return rules


def _success_metrics(cm: dict) -> dict:
    """Engine-computed baselines the next cycle should move, WITH an uncertainty band.
    No invented targets — only current engine values + a wide-CI caveat (spec §8)."""
    metrics = []
    if cm.get("expectancy_R") is not None:
        metrics.append({"metric": "expectancy_R", "current": cm.get("expectancy_R")})
    metrics.append({"metric": "expectancy_dollar", "current": cm.get("expectancy_dollar")})
    metrics.append({"metric": "profit_factor", "current": cm.get("profit_factor")})
    metrics.append({"metric": "win_rate_vs_breakeven",
                    "current": cm.get("win_rate"), "breakeven": cm.get("breakeven_wr")})
    return {"computed_by": "engine", "with_uncertainty_band": True, "metrics": metrics,
            "note": "At ~30 trades the confidence interval is wide; one cycle usually "
                    "yields 'insufficient_evidence'. Firm verdicts accrue over multiple cycles (L3)."}


def _setup_tag_rule(df) -> Optional[PlaybookRule]:
    """§15: only if user-supplied setup_tag with >=70% coverage. NO clustering. Emits a
    tracking rule (no performance claim — L1 has no per-setup number to cite)."""
    if df is None or "setup_tag" not in getattr(df, "columns", []):
        return None
    try:
        n = len(df)
        cov = int(df["setup_tag"].notna().sum()) / n if n else 0.0
    except Exception:
        return None
    if cov < 0.70:
        return None
    return PlaybookRule("track", "setup_tag", "per_setup_outcomes", "engine:setup_tag",
                        Evidence("strength", "MEDIUM", n=int(getattr(df, "__len__", lambda: 0)())),
                        "track_setup", {"coverage": round(cov, 2)})


# ── public API ──────────────────────────────────────────────────────────────────

def generate_playbook(audit_result: dict, df=None, questionnaire=None) -> Playbook:
    """Compile an L1 `AuditReport.to_dict()` into a deterministic Playbook (Candidate v1).
    Pure function: no clocks, no RNG, no LLM. `generated_at` is left None (caller stamps)."""
    report_id = str(audit_result.get("trader_id", "report"))
    total = int(audit_result.get("total_trades", 0) or 0)
    cm = audit_result.get("core_metrics", {}) or {}
    insights = audit_result.get("insights", []) or []
    sample_ok = bool(audit_result.get("sample_size_ok", False))

    level = ("insufficient" if total < 30 else "limited" if total < 100 else "adequate")
    data_sufficiency = {"total_trades": total, "sample_size_ok": sample_ok, "level": level,
                        "note": ""}
    limitations = [
        "This playbook is a HYPOTHESIS built from your past trades — not a proven plan "
        "and not a promise of future results.",
        "It only rebalances your EXISTING strategy components (keep/limit/remove/"
        "paper-trade/track/test); it never adds new rules or new instruments.",
    ]

    # ── Data Collection / Conservative Protocol when there isn't enough to test ──
    if not sample_ok or total < MIN_CYCLE_TRADES:
        data_sufficiency["note"] = "Data is not strong enough yet."
        rules = [PlaybookRule("track", "data", f"reach_{MIN_CYCLE_TRADES}_trades", "engine:sample_size",
                              Evidence("data_gap", "HIGH", total), "track_data",
                              {"have": total, "need": MIN_CYCLE_TRADES})]
        st_rule = _setup_tag_rule(df)
        if st_rule:
            rules.append(st_rule)
        limitations.append("Fewer than 30 trades — collect more before acting on any pattern.")
        return _build(report_id, total, LICENSE_DATA_COLLECTION, data_sufficiency, rules, cm,
                      tracking=["Log every trade with session, symbol, side, pnl, and (ideally) "
                                "pnl_R / initial_risk_amount, balance_before, lot_or_size."],
                      confidence="LOW", limitations=limitations)

    # ── full playbook ──
    rules = []
    for ins in insights:
        if str(ins.get("insight_id", "")).startswith("SAMPLE_SIZE"):
            continue   # data-quality caveat handled via confidence cap, not a firm rule
        rules.extend(_rules_from_insight(ins))
    rules.extend(_keep_rules(insights))
    st_rule = _setup_tag_rule(df)
    if st_rule:
        rules.append(st_rule)

    # conflict resolution + systemic override (order matters: resolve removes, then demote)
    rules, _conservative = _resolve_conflicts(rules, total, limitations)
    rules = _apply_systemic_override(rules, insights, limitations)
    _over_restriction_warning(rules, total, limitations)   # QA Wave 0L: warn on limit/paper-trade over-restriction

    # tracking requirements = the `track`/`test` rules' intents (+ sample caveat)
    tracking = sorted({_tracking_line(r) for r in rules if r.op in ("track", "test")})
    if level == "limited":
        tracking.append("Keep logging toward 100+ trades to sharpen confidence.")
        limitations.append("30–99 trades: directional but limited; confidence is capped at MEDIUM.")

    # overall confidence = capped by data level, bounded by best firm-rule confidence
    ceiling = {"insufficient": "LOW", "limited": "MEDIUM", "adequate": "HIGH"}[level]
    firm = [r for r in rules if r.op in ("remove", "limit", "paper_trade")]
    best_firm = max((_CONF_RANK.get(r.evidence.confidence, 0) for r in firm), default=0)
    confidence = _cap(_RANK_CONF[best_firm], ceiling) if firm else _cap("LOW", ceiling)

    return _build(report_id, total, LICENSE_CANDIDATE, data_sufficiency, rules, cm,
                  tracking=tracking, confidence=confidence, limitations=limitations)


def _tracking_line(rule: PlaybookRule) -> str:
    t = rule.target
    return {
        "session": f"Tag the '{rule.value}' session on each trade and re-check next cycle.",
        "symbol": f"Tag the '{rule.value}' symbol on each trade and re-check next cycle.",
        "trade_count": "Log the trade sequence number (1st, 2nd, …) within each day.",
        "post_loss_review": "Record post-loss outcomes; note the gap since the prior close.",
        "risk": "Record position size and account state (balance) per trade.",
        "exit": "Record exit_reason and MFE/MAE (R) per trade.",
        "costs": "Record exact spread and commission per trade; compute net PnL.",
        "edge": "Recompute net (after-cost) expectancy next cycle.",
        "setup_tag": "Record outcomes per setup_tag for a future setup analysis.",
        "data": f"Continue logging trades toward {MIN_CYCLE_TRADES}+.",
    }.get(t, f"Track {t}.")


def _build(report_id, total, license_, data_sufficiency, rules, cm, tracking, confidence, limitations):
    cycle = PlaybookCycle(
        success_metrics=_success_metrics(cm),
        failure_conditions={
            "note": "A rule is judged a failure only if the tracked metric stays adverse with "
                    "sufficient evidence across cycles — never on a single ~30-trade sample.",
            "verdict_default": "insufficient_evidence",
        },
    )
    sig = "|".join(sorted(f"{r.op}:{r.target}:{r.value}:{r.source}" for r in rules))
    pid = "pb_" + hashlib.sha256(f"{report_id}|{total}|{sig}".encode("utf-8")).hexdigest()[:12]
    hypothesis = _hypothesis_text(rules, license_)
    return Playbook(playbook_id=pid, based_on_report_id=report_id, license=license_,
                    hypothesis=hypothesis, data_sufficiency=data_sufficiency, rules=rules,
                    next_cycle=cycle, tracking_requirements=tracking, confidence=confidence,
                    limitations=limitations)


def _hypothesis_text(rules, license_) -> str:
    if license_ == LICENSE_DATA_COLLECTION:
        return ("Not enough trades to form a playbook yet. The plan for now is to keep logging "
                "trades until there are at least 30 to test a hypothesis against.")
    firm = [r for r in rules if r.op in ("remove", "limit", "paper_trade")]
    keeps = [r for r in rules if r.op == "keep"]
    parts = []
    if keeps:
        parts.append(f"keep what works ({len(keeps)} component(s))")
    if firm:
        parts.append(f"adjust {len(firm)} weak component(s)")
    watch = [r for r in rules if r.op in ("track", "test")]
    if watch:
        parts.append(f"track/test {len(watch)} pattern(s) next cycle")
    body = "; ".join(parts) if parts else "keep trading and gather more evidence"
    return ("Hypothesis for your next 30 trades: " + body +
            ". Each action is drawn from your own audited data; verify it over the next cycle.")


# ── rendering (deterministic, fixed glossary; English source of truth) ───────────

GLOSSARY = {  # rationale_key -> {lang: template}
    "paper_trade_core": {
        "en": "Paper-trade the core strategy until its edge after costs is proven (WR {wr}, needs {bwr}, PF {pf}).",
        "fa": "هسته استراتژی را تا اثبات edge بعد از هزینه‌ها فقط روی کاغذ اجرا کن (WR {wr}، حد لازم {bwr}، PF {pf}).",
        "ar": "تداول جوهر الاستراتيجية على الورق حتى تثبت أفضليتها بعد التكاليف (WR {wr}، المطلوب {bwr}، PF {pf}).",
    },
    "track_costs": {
        "en": "Track exact spread/commission and recompute net edge before any structural change.",
        "fa": "اسپرد/کمیسیون دقیق را ثبت کن و edge خالص را قبل از هر تغییر ساختاری دوباره حساب کن.",
        "ar": "سجّل السبريد/العمولة بدقة وأعد حساب الأفضلية الصافية قبل أي تغيير هيكلي.",
    },
    "limit_session": {
        "en": "Limit trading in the {session} session (your weakest: {trades} trades, avg {avg_pnl}, p={p}).",
        "fa": "معامله در سشن {session} را محدود کن (ضعیف‌ترین: {trades} معامله، میانگین {avg_pnl}، p={p}).",
        "ar": "قلّل التداول في جلسة {session} (الأضعف: {trades} صفقة، متوسط {avg_pnl}، p={p}).",
    },
    "remove_session": {
        "en": "Stop trading the {session} session (confirmed weakest: {trades} trades, avg {avg_pnl}, p={p}).",
        "fa": "معامله در سشن {session} را متوقف کن (ضعیف‌ترین تأییدشده: {trades} معامله، میانگین {avg_pnl}، p={p}).",
        "ar": "أوقف التداول في جلسة {session} (الأضعف المؤكد: {trades} صفقة، متوسط {avg_pnl}، p={p}).",
    },
    "limit_symbol": {
        "en": "Reduce exposure to {symbol} (weak: {trades} trades, total {total_pnl}, p={p}).",
        "fa": "حجم/تعداد معاملات {symbol} را کم کن (ضعیف: {trades} معامله، مجموع {total_pnl}، p={p}).",
        "ar": "قلّل التعرض لـ {symbol} (ضعيف: {trades} صفقة، الإجمالي {total_pnl}، p={p}).",
    },
    "paper_trade_symbol": {
        "en": "Paper-trade {symbol} until more data confirms an edge ({trades} trades, total {total_pnl}, p={p}).",
        "fa": "{symbol} را تا تأیید edge با داده بیشتر فقط روی کاغذ معامله کن ({trades} معامله، مجموع {total_pnl}، p={p}).",
        "ar": "تداول {symbol} على الورق حتى تؤكد بيانات أكثر وجود أفضلية ({trades} صفقة، الإجمالي {total_pnl}، p={p}).",
    },
    "remove_symbol": {
        "en": "Stop trading {symbol} (confirmed weak: {trades} trades, total {total_pnl}, p={p}).",
        "fa": "معامله {symbol} را متوقف کن (ضعف تأییدشده: {trades} معامله، مجموع {total_pnl}، p={p}).",
        "ar": "أوقف تداول {symbol} (ضعف مؤكد: {trades} صفقة، الإجمالي {total_pnl}، p={p}).",
    },
    "limit_trade_count": {
        "en": "Cap your day at {cap} trade(s) — win rate drops {drop} pts after trade #{cliff}.",
        "fa": "هر روز را به {cap} معامله محدود کن — بعد از معامله {cliff}ام نرخ برد {drop} امتیاز افت می‌کند.",
        "ar": "حُدّ يومك بـ {cap} صفقة — تنخفض نسبة الفوز {drop} نقطة بعد الصفقة #{cliff}.",
    },
    "limit_cooldown": {
        "en": "Add a {minutes}-minute cooldown after any loss (fast re-entry WR {fast_wr}, n={n}).",
        "fa": "بعد از هر ضرر {minutes} دقیقه cooldown بگذار (WR ورود سریع {fast_wr}، n={n}).",
        "ar": "أضف فترة تهدئة {minutes} دقيقة بعد أي خسارة (WR الدخول السريع {fast_wr}، n={n}).",
    },
    "test_post_loss": {
        "en": "Test a structured review before re-entering after a loss (WR drops {drop} pts, n={n}).",
        "fa": "قبل از ورود دوباره بعد از ضرر یک بازبینی ساختاری را آزمایش کن (افت WR {drop} امتیاز، n={n}).",
        "ar": "اختبر مراجعة منظمة قبل إعادة الدخول بعد الخسارة (انخفاض WR {drop} نقطة، n={n}).",
    },
    "limit_risk": {
        "en": "Hold position size to a fixed risk % regardless of account state (size was {ratio}x larger in drawdown).",
        "fa": "سایز را با درصد ریسک ثابت نگه دار، مستقل از وضعیت حساب (در drawdown سایز {ratio}x بزرگ‌تر بود).",
        "ar": "ثبّت حجم الصفقة كنسبة مخاطرة ثابتة بغضّ النظر عن حالة الحساب (كان الحجم أكبر بـ {ratio}x في التراجع).",
    },
    "test_exit": {
        "en": "Test letting winners run / cutting losers sooner (payoff ratio {ratio}{unit}).",
        "fa": "آزمایش کن که برنده‌ها را بیشتر نگه داری و بازنده‌ها را زودتر ببندی (نسبت سود/ضرر {ratio}{unit}).",
        "ar": "اختبر ترك الرابحين يمتدون وقطع الخاسرين أسرع (نسبة العائد {ratio}{unit}).",
    },
    "keep_segment": {
        "en": "Keep trading {name} — a data-supported strength.",
        "fa": "به معامله {name} ادامه بده — یک نقطه‌قوت با پشتوانه داده.",
        "ar": "استمر في تداول {name} — نقطة قوة مدعومة بالبيانات.",
    },
    "track_segment": {
        "en": "Track {name} next cycle — evidence isn't conclusive yet.",
        "fa": "{name} را چرخه بعد زیر نظر بگیر — شواهد هنوز قطعی نیست.",
        "ar": "راقب {name} في الدورة القادمة — الأدلة ليست حاسمة بعد.",
    },
    "track_strength_pending_core": {
        "en": "Your relatively strongest area is {name} — confirm it still holds once the "
              "core edge is proven (don't trade it live until then).",
        "fa": "نسبتاً قوی‌ترین بخش تو {name} است — بعد از اثبات edge هسته بررسی کن که هنوز "
              "برقرار است (تا آن زمان live معامله‌اش نکن).",
        "ar": "أقوى مجالاتك نسبياً هو {name} — تأكد من بقائه بعد إثبات أفضلية الجوهر "
              "(لا تتداوله مباشرة حتى ذلك الحين).",
    },
    "track_setup": {
        "en": "Record outcomes per setup_tag (coverage {coverage}) for a future setup analysis.",
        "fa": "نتایج را به تفکیک setup_tag ثبت کن (پوشش {coverage}) برای تحلیل ستاپ در آینده.",
        "ar": "سجّل النتائج لكل setup_tag (التغطية {coverage}) لتحليل الإعداد مستقبلاً.",
    },
    "track_data": {
        "en": "Keep logging trades — you have {have}, you need {need} to test a plan.",
        "fa": "به ثبت معاملات ادامه بده — {have} تا داری، برای تست پلن {need} لازم است.",
        "ar": "واصل تسجيل الصفقات — لديك {have}، تحتاج {need} لاختبار خطة.",
    },
}


def render_rule_text(rule: dict, lang: str = "en") -> str:
    """Render one rule (dict form) to localized text via the fixed glossary."""
    key = rule.get("rationale_key", "")
    tmpl = (GLOSSARY.get(key) or {}).get(lang) or (GLOSSARY.get(key) or {}).get("en") or rule.get("op", "")
    try:
        return tmpl.format(**(rule.get("params") or {}))
    except Exception:
        return tmpl


def render_playbook(playbook: dict, lang: str = "en") -> str:
    """Deterministic markdown preview (no LLM). Internal/feature-flagged use only."""
    groups = [("keep", "Keep"), ("limit", "Limit"), ("remove", "Remove"),
              ("paper_trade", "Paper-trade"), ("test", "Test"), ("track", "Track")]
    lines = [f"# Personal Strategy Playbook — {playbook.get('license')}",
             f"_{playbook.get('hypothesis','')}_", ""]
    rules = playbook.get("rules", [])
    for op, label in groups:
        grp = [r for r in rules if r.get("op") == op]
        if not grp:
            continue
        lines.append(f"## {label}")
        for r in grp:
            ev = r.get("evidence", {})
            lines.append(f"- {render_rule_text(r, lang)}  "
                         f"_(source: {r.get('source')}, {ev.get('status')}/{ev.get('confidence')})_")
        lines.append("")
    if playbook.get("tracking_requirements"):
        lines.append("## Next-cycle tracking")
        lines += [f"- {t}" for t in playbook["tracking_requirements"]]
        lines.append("")
    lines.append("## Limitations")
    lines += [f"- {x}" for x in playbook.get("limitations", [])]
    return "\n".join(lines)


# ── validation (the contract; rejects forbidden output) ──────────────────────────

class PlaybookValidationError(ValueError):
    pass


def validate_playbook(playbook: dict) -> None:
    """Enforce the locked contract: valid ops, every rule sourced, license known, and
    no forbidden tokens in any rendered text (en/fa/ar). Raises on violation."""
    if playbook.get("license") not in (LICENSE_CANDIDATE, LICENSE_DATA_COLLECTION):
        raise PlaybookValidationError(f"bad license: {playbook.get('license')}")
    for r in playbook.get("rules", []):
        if r.get("op") not in OPS:
            raise PlaybookValidationError(f"illegal op: {r.get('op')}")
        if not r.get("source"):
            raise PlaybookValidationError(f"rule without source: {r}")
    # forbidden-content scan over all rendered text in all languages
    blob_parts = [playbook.get("hypothesis", "")] + list(playbook.get("limitations", [])) \
        + list(playbook.get("tracking_requirements", []))
    for lang in ("en", "fa", "ar"):
        blob_parts += [render_rule_text(r, lang) for r in playbook.get("rules", [])]
    blob = " ".join(blob_parts).lower()
    for tok in _FORBIDDEN_TOKENS:
        if tok in blob:
            raise PlaybookValidationError(f"forbidden token in output: {tok!r}")
