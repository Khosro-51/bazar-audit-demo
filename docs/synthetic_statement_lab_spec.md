# Synthetic Statement Lab — Specification

**Date:** 2026-06-15 · **Status:** active (implemented).

> **Principle:** **Trader feedback validates usability and trust. Synthetic controlled statements validate the algorithm.**

## 1. Purpose

The Synthetic Statement Lab is Bazar's **internal algorithm-validation gate**. It is a set of *controlled trade statements with known expected diagnoses* (golden datasets). Each statement is engineered to trigger — or deliberately NOT trigger — a specific L1 diagnosis, with the corresponding expected L2 playbook contract. Running them proves the deterministic L1 → L2 pipeline behaves exactly as designed, repeatably, without any human in the loop.

This corrects an earlier sequencing error: external trader feedback is **not** algorithm validation and must **not** gate the deterministic L2-core. Trader feedback is collected *later*, and only for UX, clarity, trust, adoption, pricing, testimonials, and marketing proof.

## 2. Validation model & sequencing

```
L1 structural integrity
  → Synthetic Statement Lab / Golden Datasets        (algorithm correctness — THIS doc)
  → L1 expected-output validation                     (insight IDs / severity / evidence class)
  → L2 deterministic playbook compiler
  → L2 expected-playbook validation                   (rule verbs / source / no forbidden output)
  → limited trader feedback                           (UX / clarity / trust / adoption / marketing only)
```

- **Algorithm is considered valid** only when the synthetic golden validation passes (this gate).
- **Trader feedback is required later** for usability/trust/adoption/pricing/testimonials/marketing — never as algorithm validation, never as a build gate on L2-core.
- This gate is in addition to the permanent Monte-Carlo false-finding validation (`docs/validation.md`), which proves the *statistical-honesty* (noise) property; the Lab proves the *expected-diagnosis* (signal) property.

## 3. What a golden case asserts (semantic contract, not text matching)

Human-facing copy is intentionally **not** matched verbatim. Each case asserts the semantic contract:

- expected **L1 insight IDs** present, with the right **evidence class** (`finding` = `observation:false`, or `observation` = `observation:true`);
- expected **L2 rule verbs** (`keep/limit/remove/paper_trade/track/test`) on the correct **existing** component;
- **forbidden L2 verbs** absent (e.g. no `remove`/`limit` from noise or from an observation);
- every rule carries `source = insight_id` (unsourced rules fail validation);
- **no forbidden output** in any language (no buy/sell, entry/SL/TP price, signal, profit guarantee, financial-advice language).

## 4. Golden scenarios (minimum set)

| Scenario | Expected L1 | Expected L2 | Forbidden |
|----------|-------------|-------------|-----------|
| **GOOD_TRADER_CLEAN** | no MEDIUM/HIGH defects (only sample/data notes if any) | no firm `remove`/`limit` | any firm action |
| **NOISE_TRADER_RANDOM** | no MEDIUM/HIGH false findings | no firm `remove`/`limit` | any firm action |
| **SESSION_TOXICITY_CONFIRMED** | `SESSION_TOXICITY` finding | `limit`/`remove` on **that** session | firm action on any other component |
| **SYMBOL_NO_EDGE_CONFIRMED** | `SYMBOL_NO_EDGE` finding | `limit`/`paper_trade`/`remove` on **that traded** symbol | rule on a symbol not in the data |
| **POST_LOSS_DECAY_CONFIRMED** | `POST_LOSS_DECAY`/`POST_LOSS_FAST_REENTRY` finding (no systemic) | cooldown / post-loss tracking protocol | trade signal |
| **PAYOFF_IMBALANCE_CONFIRMED** | `PAYOFF_IMBALANCE` finding | risk/reward (exit) `test`/`track` review | trade signal; firm remove/limit from payoff |
| **TRADE_COUNT_CLIFF_CHRONOLOGICAL** | `TRADE_COUNT_CLIFF` finding from the **chronological** open_time-derived index (cliff at #3) | `limit trade_count` (cap = cliff−1) | result controlled by a supplied `trade_index_in_day` |
| **WEAK_EVIDENCE_OBSERVATION_ONLY** | LOW **observation** only | `track`/`test` only | firm `remove`/`limit` |
| **DATA_GAP_LOW_SAMPLE** | sample/data limitation (`SAMPLE_SIZE_INSUFFICIENT`) | Data Collection Protocol (`track` only) | any firm action |

## 5. Implementation

- **Generators:** `tests/synthetic_lab.py` — one deterministic generator per scenario (seeded RNG for win/loss draws so there are no spurious sequence artifacts). Run `python tests/synthetic_lab.py` to print each case's actual L1 insights + L2 rules (diagnostic / calibration).
- **Contracts & assertions:** `tests/test_synthetic_statement_lab.py` — a universal contract (parametrized over all cases: legal+sourced ops, observation→track, firm→finding, no forbidden phrases in en/fa/ar) plus a focused per-scenario semantic test.
- All cases are deterministic (fixed seeds), so the gate is a stable pass/fail.

## 6. Pass criteria & gating

- **L2-core is "algorithmically valid"** iff `pytest tests/test_synthetic_statement_lab.py` (and `tests/test_playbook.py`) pass **and** the Monte-Carlo release gate passes.
- This gate does **not** depend on, and is not blocked by, trader feedback.
- External *exposure* (turning `ENABLE_L2_PLAYBOOK` on, or any paid beta) remains an **operational** gate (live Supabase smoke + Streamlit Cloud end-to-end), independent of this algorithm-validation gate.

## 7. Maintenance rule

Every time a new L1 insight or L2 rule type is added, **add a golden case** for it (both a "confirmed finding" and a "weak observation" variant where applicable). The Lab is the contract; new behavior is not "done" until it has a golden case.
