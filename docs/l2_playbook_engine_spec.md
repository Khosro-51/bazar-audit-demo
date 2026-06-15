# L2 — Personal Strategy Playbook Engine — Specification (design only)

**Date:** 2026-06-15 · **Status:** spec for approval, *before any code* (Prompt 6)
**Authority:** This spec implements the locked agreement in `BAZAR_L2_L3_AGENT_DESIGN.md` §8 ("نسخه قفل‌شده نهایی", 2026-06-12). Where this spec and that agreement disagree, the agreement wins.
**Scope:** L2-core only — the **deterministic** Playbook Engine (Line 2). **No LLM. No Agent. No live market behavior. No engine changes.** The conversational mentor is Line 3 (Prompt 8+), explicitly forbidden until L2-core is built and sellable.

> ### Validation model (corrected 2026-06-15)
> **Trader feedback validates usability and trust. Synthetic controlled statements validate the algorithm.**
>
> L2-core's algorithm is gated by the **internal Synthetic Statement Lab / Golden Datasets** (`docs/synthetic_statement_lab_spec.md`), **not** by trader/beta feedback. Correct sequencing:
> **L1 structural integrity → Synthetic Statement Lab / Golden Datasets → L1 expected-output validation → L2 deterministic playbook compiler → L2 expected-playbook validation → limited trader feedback (UX / clarity / trust / adoption / pricing / testimonials / marketing only).**
> Trader feedback is collected *later* and is never algorithm validation and never a build gate on L2-core. (External *exposure* — flag on / paid beta — remains a separate operational gate: live Supabase + Streamlit Cloud end-to-end.)

> **Implementation status (2026-06-15, Prompt 7 — DONE, internal/flagged).** L2-core is implemented in `bazar_playbook.py` (pure, deterministic, no LLM/Streamlit/network) with `tests/test_playbook.py` (14 tests) and the algorithm-validation gate `tests/test_synthetic_statement_lab.py` + `tests/synthetic_lab.py` (18 golden-contract tests). Full suite 75 passed / 1 deselected. It is **internal-only and OFF by default**: surfaced solely behind `ENABLE_L2_PLAYBOOK` (default `false`) **and** admin, as a JSON + markdown preview in the admin tab — the public report path (`build_report_html`) is unchanged and L2 is not exposed to external users. The §15 decisions are locked as below. **L2-core is "algorithmically valid" once the Synthetic Statement Lab + Monte-Carlo gates pass (they do); it is NOT gated on trader feedback.** External *exposure* remains gated on the operational checks (live Supabase + Streamlit E2E).
>
> **Internal QA / red-team (2026-06-15, Prompt 8 + Wave 0M — PASS).** See `reports/l2_playbook_qa_20260615.md` and `tools/l2_qa_redteam.py` (9 profiles). Three findings, all resolved: F1 removed "signal" wording + added it to the forbidden-token contract; F2 added an over-restriction warning for `limit`/`paper_trade` (not just `remove`); **F3 (Wave 0M)** systemic override now demotes `keep` → `track` ("confirm your strongest area once the core edge is proven") so it can't contradict a core `paper_trade`. Harness 0 FAIL / 0 WARN. Tests now 14 (L2) / 57 (full).
>
> **Locked §15 decisions (as built):** `limit` is default, `remove` only for a confirmed HIGH finding + conflict-resolver permission; firm removals >40% of trades → downgrade to `limit`; if <30 testable trades remain → Data Collection / Conservative Protocol; `keep` rules ship by default for data-supported components only; `setup_tag` rules only when user-supplied with ≥70% coverage and **no inferred clustering**; rendering = JSON + internal flagged preview only; en/fa/ar via fixed glossary, English source of truth, no LLM.

---

## 1. Product definition

L2 turns an **L1 audit result** into a **Personal Strategy Playbook (Candidate v1)** — a 30-trade, testable improvement plan built *only* from what the user's own data statistically supports. It is a higher artifact than L1's Immediate Action Plan: L1 says "here are your problems"; L2 says "here is a rebalanced, testable plan over your *existing* strategy components, with a pre-declared way to judge it next cycle."

L2 is deterministic: same audit in → byte-identical playbook out. Every number and every action traces to an engine insight. L2 invents nothing.

The 30-trade cycle is the standard progress unit. **L2 issues a hypothesis, not a verdict** — n=30 cannot confirm an edge (PF/expectancy variance is huge at n=30). Confirmation is L3's job, across cycles, with an uncertainty band.

## 2. Non-goals (hard)

L2 is **not** a journal, a signal seller, a setup teacher, or a live assistant. It does **not**:
- emit buy/sell, long/short, entry signals, price targets, or SL/TP levels;
- invent new rules, new symbols, or new setups ("add a rule" is not in the verb set);
- produce any number not computed by the deterministic engine (no "PF > 1.2 from the sky");
- promise profit or improvement; "recoverable" stays a labeled historical counterfactual;
- issue a firm verdict on a small sample — the standard answer is *"Data is not strong enough yet."*
- use an LLM anywhere in L2-core.

## 3. The locked verb set (non-negotiable)

A playbook rule's `op` is exactly one of — and operates **only on existing components** of the user's strategy:

| `op` | Meaning | Created from |
|------|---------|--------------|
| `keep` | Reinforce a component that works | engine-identified strength (positive segment, adequate n) |
| `remove` | Stop trading a component | a **confirmed finding** (significant) *and* the conflict resolver permits removal |
| `limit` | Reduce/cap a component (size, count, exposure, cooldown) | a confirmed finding (default for single weak segment / count / cooldown / sizing) |
| `paper_trade` | Trade a component on paper until proven | unproven core (systemic) or unconfirmed-but-watched segment |
| `track` | Log/measure a component for next-cycle evidence | an **observation**, a data gap, or any metric to watch |
| `test` | Run a defined experiment next cycle | a behavior the data flags but where the fix must be measured (e.g. cooldown, exit) |

There is **no** `add`/`create` verb. `remove` is gated harder than `limit`: only from a confirmed finding *and* only if removing it doesn't gut the dataset (see §7 conflict resolver) — otherwise it degrades to `limit`.

## 4. Inputs

L2 consumes the L1 `AuditReport.to_dict()` and nothing it can't trace:
- `core_metrics` (win_rate, breakeven_wr, profit_factor, payoff_ratio, expectancy_dollar/R, r_mode, no_loss_trades, scratch_trades);
- `insights[]` — each with `insight_id`, `severity`, `confidence`, `sample_size`, and `metric_snapshot` (which carries `observation` true/false, `p_value`, and segment payloads: `worst_session`/`all_sessions`, `worst_symbol`/`all_symbols`, `counterfactual`, `cliff_at_trade`, `n_fast_reentry`, `size_ratio`, …);
- `total_trades`, `sample_size_ok`, `r_mode`, `warnings`.
- **Optional** `questionnaire` (user's stated intent/rules) — used only for *labeling/context*, never to invent rules.
- **Optional** per-trade `setup_tag`/`session`/`symbol` metadata. With `setup_tag` → "Setup Performance Analysis"; without → no setup claims (clustering is a later, classic-ML step, not part of L2-core).

**Evidence status** of each insight (the spine of L2): `finding` (`observation == False`, statistically gated) → may create a firm verb; `observation` (`observation == True`) → only `track`/`paper_trade`/`test`; `data_gap` (SAMPLE_SIZE_*) → only `track`/collect.

## 5. Outputs

1. **Playbook (Candidate v1)** — JSON per §9, plus a deterministic human-readable **"Your Next 30 Trades Protocol"** (multilingual templating like L1's `body_fa`, no LLM).
2. Grouped rule lists: **Keep / Limit / Remove (confirmed only) / Watchlist (track) / Experiments (test)**.
3. **Tracking requirements** — what to log next cycle so L3 can judge (e.g., tag session, record exit_reason/MFE/MAE, log trade sequence #).
4. **Success / failure criteria** for the next cycle — *engine-computed, with an uncertainty band*, framed as a hypothesis. `verdict_states = [improved, worsened, insufficient_evidence]` (decided at L3).
5. **License state:** always `playbook_candidate` (see §10).

## 6. Rule mapping table (L1 insight_id → L2 rule)

The engine is the brain; this table is the deterministic compiler. "F" = finding (`observation:false`), "O" = observation (`observation:true`), "gap" = sample-size.

| insight_id | Evidence | `op` | `target` | Notes |
|------------|----------|------|----------|-------|
| `SAMPLE_SIZE_INSUFFICIENT` (n<30) | gap | `track` | `data` | No playbook — **Data Collection Plan** only ("Data is not strong enough yet"). |
| `SAMPLE_SIZE_LIMITED` (30≤n<100) | gap | `track` | `data` | Playbook issued but confidence capped; track to 100+. |
| `SYSTEMIC_UNDERPERFORMANCE` | F (HIGH) | `paper_trade` + `track` | `strategy_core` | Core edge unproven after costs → paper-trade core, track cost-adjusted edge. **Leads the playbook; behavioral rules are explicitly secondary and not claimed to fix a systemic problem.** |
| `EDGE_BELOW_BREAKEVEN` | F | `track` | `costs`/`edge` | Track spread/commission, recompute net edge; no removal. |
| `EDGE_BELOW_BREAKEVEN` | O | `track` | `edge` | Watch only. |
| `SESSION_TOXICITY` | F | `limit` (→`remove` only if conflict resolver allows) | `session=<worst>` | Counterfactual + confidence from snapshot. |
| `SESSION_TOXICITY` | O | `track` | `session=<worst>` | Tag session, re-check next cycle. |
| `SYMBOL_NO_EDGE` | F | `limit`/`paper_trade` (→`remove` if allowed) | `symbol=<worst>` | Default `paper_trade` the symbol. |
| `SYMBOL_NO_EDGE` | O | `track` | `symbol=<worst>` | |
| `TRADE_COUNT_CLIFF` | F | `limit` | `trade_count=<cliff-1>/day` | Daily cap. Directly EA-compilable (L5a). |
| `TRADE_COUNT_CLIFF` | O | `track` | `trade_count` | Log trade sequence # per day. |
| `POST_LOSS_FAST_REENTRY` | F | `limit` | `cooldown=<gap_min>` | Mandatory cooldown after a loss. EA-compilable. |
| `POST_LOSS_DECAY` | F | `test` + `track` | `cooldown`/`post_loss_review` | Test a structured post-loss review; track post-loss WR. |
| `DRAWDOWN_RECOVERY_SIZING` | F | `limit` | `risk=fixed_pct` | Fix risk % regardless of account state. EA-compilable. |
| `DRAWDOWN_RECOVERY_SIZING` | O | `track` | `risk` | |
| `PAYOFF_IMBALANCE` | F | `test` + `track` | `exit` | Test a defined exit change as an experiment; track MFE/MAE & exit_reason. **No prescribed new exit rule** (stays in the verb set). |
| `PAYOFF_IMBALANCE` | O | `track` | `exit` | |
| *(no toxic finding on a positive segment)* | strength | `keep` | `session`/`symbol=<best>` | From `all_sessions`/`all_symbols` with positive avg & adequate n. Reinforces what works. |

Every emitted rule carries `source = <insight_id>` (or `engine:strength` for `keep`). **A rule without a `source` is invalid and rejected by the validation layer.**

## 7. Weakness prioritization & conflict resolution (deterministic, engine-owned)

- **Prioritization:** reuse L1's evidence ordering — systemic/edge before behavioral; within behavioral, rank by the engine's counterfactual magnitude (`net_pnl_without_segment - current_net_pnl`) and confidence. No manual weights.
- **Conflict resolver (the doc's "minimum effective subset"):** if the union of `remove`/`limit` rules would eliminate more than a configured share of the user's trades (e.g. removing Asia *and* GBPUSD wipes 70%), solve a small constrained optimization: keep the smallest set of firm actions that captures most of the confirmed counterfactual gain; **downgrade the rest from `remove`/`limit` to `track`**. Deterministic, no LLM. This prevents a playbook that tells the user to stop trading almost everything.
- **Systemic override:** when `SYSTEMIC_UNDERPERFORMANCE` is a finding, behavioral `remove`/`limit` rules are demoted to `track`/secondary and the playbook leads with core `paper_trade` — you don't "fix" a no-edge core by trimming sessions.

## 8. Success / failure criteria (statistical honesty)

- All criteria are **engine-computed** and carry an **uncertainty band**; none are hand-set thresholds.
- Framed as a *hypothesis*: e.g. "If removing/limiting `<segment>` helps, the engine's counterfactual suggests next-cycle expectancy ≈ current + Δ — but at n=30 the confidence interval is wide, so the verdict is deferred."
- `next_cycle.verdict_states = ["improved", "worsened", "insufficient_evidence"]`. The default expected outcome at one cycle is `insufficient_evidence`; firm verdicts accrue over multiple cycles (L3).
- Failure conditions are likewise expressed with bands (e.g. "if post-loss WR stays ≥X below baseline with sufficient n").

## 9. JSON schema (adopted from the locked agreement §8, completed)

```json
{
  "playbook_id": "string",
  "based_on_report_id": "string",
  "schema_version": "l2.v1",
  "license": "playbook_candidate",
  "generated_at": "ISO-8601 (stamped by caller, not the pure engine)",
  "hypothesis": "string — plain-language summary, templated, no invented numbers",
  "data_sufficiency": {
    "total_trades": 0,
    "sample_size_ok": true,
    "level": "insufficient | limited | adequate",
    "note": "string"
  },
  "rules": [
    {
      "op": "keep | remove | limit | paper_trade | track | test",
      "target": "session | symbol | trade_count | cooldown | risk | exit | costs | edge | strategy_core | setup_tag | data",
      "value": "string|number|null",
      "evidence": {
        "status": "finding | observation | data_gap | strength",
        "counterfactual": { "current_pf": 0, "pf_without_segment": 0,
                            "current_net_pnl": 0, "net_pnl_without_segment": 0 },
        "p_value": 0.0,
        "confidence": "LOW | MEDIUM | HIGH",
        "n": 0
      },
      "source": "engine_insight_id | engine:strength",
      "rationale_key": "i18n key (templated text, no LLM)"
    }
  ],
  "next_cycle": {
    "min_trades": 30,
    "success_metrics": { "computed_by": "engine", "with_uncertainty_band": true, "metrics": [] },
    "failure_conditions": {},
    "verdict_states": ["improved", "worsened", "insufficient_evidence"]
  },
  "tracking_requirements": ["string"],
  "confidence": "LOW | MEDIUM | HIGH",
  "limitations": ["string"]
}
```

Validation contract: `op` ∈ verb set; `source` present; numbers present in `evidence` must equal the originating insight's snapshot values (no drift); no forbidden tokens in any text field (§11).

## 10. "Playbook Candidate License" criteria

A playbook is issued as **`playbook_candidate`** (never "confirmed") when:
1. `sample_size_ok == true` (n ≥ 30). If not → a **Data Collection Plan** is returned instead (only `track`/collect rules), not a Playbook Candidate.
2. Every `remove`/`limit`/`paper_trade(core)` rule is backed by a **finding** (`observation:false`) with `confidence ≥ MEDIUM`. Findings below that, and all observations, may only produce `track`/`test`.
3. The conflict resolver has run (no playbook that removes a majority of trades).
4. It is explicitly labeled a **hypothesis to be tested over the next 30 trades**, validated only by L3 out-of-sample comparison. L2 never marks a playbook "proven."

The "license" is permission for the *user to test it*, not a claim that it works.

## 11. Safety guardrails (Forbidden Output Policy — from §8.6, enforced by a validation layer)

Reject (do not emit) any output that:
- contains an invented number (every number must equal an engine snapshot value);
- references a new symbol/instrument or a new rule not present in the user's data;
- promises profit/return or implies future performance;
- contains live-trading / entry / SL / TP / price-level guidance;
- issues a firm verdict on an insufficient sample (n<30 → Data Collection Plan + "Data is not strong enough yet");
- uses narrative in place of data, or any `op` outside the verb set, or any rule without a `source`.

A grep-style content check (no buy/sell/long/short/price/guarantee/profit language) runs on the rendered output, mirroring the L1 product-safety check.

## 12. Test plan (write tests before implementation)

1. **Determinism:** same audit dict → byte-identical playbook (no clocks/RNG in the pure engine; `generated_at` injected by the caller).
2. **Verb-set & source enforcement:** no rule with `op` outside the set; no rule without `source`; validation layer rejects a hand-crafted bad rule.
3. **Evidence discipline:** a `finding` may yield `remove`/`limit`; an `observation` **must not** yield `remove`/`limit` (only `track`/`test`/`paper_trade`); a `data_gap` yields only `track`/collect. (The core honesty test.)
4. **No firm rule from noise (L2 Monte-Carlo analog):** run L2 on the zero-edge random traders from `tools/monte_carlo_validation.py`; the playbook must contain **no `remove`/`limit` firm rules** (L1 produced no findings → L2 has nothing firm to act on) at a rate matching the L1 false-finding ceiling.
5. **Conflict resolver:** a dataset whose naive firm rules remove >X% of trades → engine returns the minimum effective subset and downgrades the rest to `track`.
6. **Systemic override:** `SYSTEMIC_UNDERPERFORMANCE` finding → core `paper_trade` leads; behavioral rules demoted; no claim a session tweak fixes the core.
7. **Keep rules:** a profitable, adequately-sampled segment yields a `keep` rule.
8. **Low sample:** n<30 → Data Collection Plan, no Playbook Candidate.
9. **Schema validity:** output validates against the §9 schema; numbers equal source snapshot values.
10. **Forbidden language:** rendered output passes the content safety check (no signal/price/profit terms), in en/fa/ar.
11. **Number provenance:** every numeric field traces to an insight snapshot (property test).

## 13. Implementation plan (waves — all deterministic, no LLM)

- **L2-1 — Contract:** `bazar_playbook.py` skeleton — dataclasses (`Playbook`, `PlaybookRule`, `PlaybookCycle`, `Evidence`), the §9 schema, and the validation layer (verb set, required `source`, forbidden-content check). Tests 2, 9, 10 first.
- **L2-2 — Mapper:** `generate_playbook(audit_result, df=None, questionnaire=None)` implementing §6 with strict finding/observation/gap discipline. Tests 3, 8.
- **L2-3 — Strengths & prioritization:** `keep` rules from positive segments + engine-sourced weakness ordering. Tests 7.
- **L2-4 — Conflict resolver:** minimum-effective-subset optimization + systemic override. Tests 5, 6.
- **L2-5 — Cycle criteria:** engine-computed success/failure with uncertainty band + the Next-30 protocol object. Test 1, 11.
- **L2-6 — Rendering:** deterministic multilingual "Next 30 Trades Protocol" section; optional integration into the downloadable HTML report behind an `L2_ENABLED` flag (off by default; L1 unchanged).
- **L2-7 — Validation suite:** the full test plan incl. the L2 Monte-Carlo honesty guard (test 4) wired into the two-tier validation policy (`docs/validation.md`).

No Agent, no clustering, no live data in any wave above — those are Line 3 / later steps, gated by the vision-freeze rule (§9b). Per the corrected validation model, a level is *algorithmically* unlocked by passing its own internal synthetic-validation gate (golden datasets + Monte-Carlo honesty), **not** by trader/beta feedback. Trader feedback informs UX, clarity, trust, adoption, pricing, and marketing only — it is never an algorithm-validation step or a build gate.

---

## 14. Key design choices (summary)
- **Engine is the brain; L2 is a deterministic compiler** from insights → a locked verb set. Zero invented numbers, every rule sourced.
- **Findings act; observations track; gaps collect** — the L1 statistical-honesty discipline carried up one layer.
- **Hypothesis, not verdict** — 30-trade cycle issues a testable plan with an uncertainty band; confirmation is L3's multi-cycle job.
- **Conflict resolver** prevents "stop trading everything"; **systemic override** prevents pretending tweaks fix a no-edge core.
- **EA-forward schema** — `op/target/value` is directly compilable to a MetaTrader discipline-EA config (L5a), per the agreement; designed in, not bolted on.

## 15. Open questions (founder decisions before/at implementation)
1. **`limit` vs `remove` default** for a single confirmed weak segment — the agreement shows "remove Asia" but also favors minimum-disruption. Propose: default `limit`/`paper_trade`, escalate to `remove` only when the conflict resolver confirms low collateral. Confirm.
2. **Conflict-resolver threshold** — what share of removed trades triggers downgrade to `track`? (Propose ~30%.)
3. **`keep` rules** — include by default, or only when explicitly requested? (Propose: include; a playbook should reinforce strengths.)
4. **`setup_tag`** — include per-setup rules in L2-core, or defer all setup analysis to the later clustering step? (Propose: defer; L2-core uses session/symbol/count/cooldown/risk only.)
5. **Rendering surface** — HTML report section vs a separate downloadable Playbook artifact vs gated behind an L2 access tier.
6. **Multilingual** — confirm en/fa/ar deterministic templating parity with L1.

## 16. Can implementation start? (corrected validation model)
**L2-core implementation is DONE** (see the Implementation status banner at the top of this spec) and was gated by **internal synthetic validation, not trader feedback**. The corrected gate is:

> **Internal synthetic validation is required before L2 is considered algorithmically valid. Trader feedback is required later — for UX, clarity, trust, adoption, pricing, testimonials, and marketing proof — and is never an algorithm-validation step or a build gate on L2-core.**

Concretely, L2-core is **"algorithmically valid"** when both internal gates pass (they do):
- the **Synthetic Statement Lab** golden gate — `docs/synthetic_statement_lab_spec.md`, `tests/synthetic_lab.py`, `tests/test_synthetic_statement_lab.py` (expected-diagnosis / signal property);
- the **Monte-Carlo honesty** gate — `docs/validation.md` (no-false-finding / noise property).

This replaces the earlier (incorrect) "collect L1 beta feedback before L2 implementation" sequencing. The correct order is: **L1 structural integrity → Synthetic Statement Lab / Golden Datasets → L1 expected-output validation → L2 deterministic compiler → L2 expected-playbook validation → limited trader feedback (UX/trust/marketing only).**

External *exposure* (turning `ENABLE_L2_PLAYBOOK` on, or any paid beta) remains a **separate operational gate**, unchanged: live Supabase smoke + Streamlit Cloud end-to-end. It is independent of this algorithm-validation gate.
