# Synthetic Statement Lab — L1→L2 Validation Report

**Date:** 2026-06-15 · **Cases:** 10 · **Gate:** internal algorithm validation (not trader feedback).

> Trader feedback validates usability and trust. Synthetic controlled statements validate the algorithm.

Each case is a deterministic controlled statement with a known expected diagnosis. A case PASSES when its actual L1 insights, evidence class, and L2 rule verbs match the expected semantic contract, every rule is sourced to an `insight_id`, and no forbidden (buy/sell/price/signal/advice) language appears in any language.

## Summary

| # | Case | Trades | Result |
|---|------|--------|--------|
| 1 | GOOD_TRADER_CLEAN | 120 | ✅ PASS |
| 2 | NOISE_TRADER_RANDOM | 120 | ✅ PASS |
| 3 | SESSION_TOXICITY_CONFIRMED | 160 | ✅ PASS |
| 4 | SYMBOL_NO_EDGE_CONFIRMED | 150 | ✅ PASS |
| 5 | POST_LOSS_DECAY_CONFIRMED | 160 | ✅ PASS |
| 6 | PAYOFF_IMBALANCE_CONFIRMED | 120 | ✅ PASS |
| 7 | TRADE_COUNT_CLIFF_CHRONOLOGICAL | 150 | ✅ PASS |
| 8 | WEAK_EVIDENCE_OBSERVATION_ONLY | 120 | ✅ PASS |
| 9 | DATA_GAP_LOW_SAMPLE | 15 | ✅ PASS |
| 10 | MIXED_MULTI_LEAK_TRADER | 240 | ✅ PASS |

**Overall: ✅ ALL PASS** (10/10 cases pass)


---

## GOOD_TRADER_CLEAN — ✅ PASS

*Positive edge, single session/symbol, no intraday clustering.*  · n=120 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_good_clean()` (deterministic, seeded)
- **Actual L1:** —
- **Actual L2:** —
- **Forbidden L2 verbs:** limit, remove
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ no MEDIUM/HIGH false finding
    - ✅ no 'limit' rule
    - ✅ no 'remove' rule
    - ✅ no forbidden language (en/fa/ar)

## NOISE_TRADER_RANDOM — ✅ PASS

*Pure noise (zero edge), sizes/sessions independent of outcome.*  · n=120 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_noise_random()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/LOW/obs, SYMBOL_NO_EDGE/LOW/obs
- **Actual L2:** track session=Overlap, track symbol=XAUUSD, keep session=London, keep symbol=NAS100
- **Forbidden L2 verbs:** limit, remove
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ no MEDIUM/HIGH false finding
    - ✅ no 'limit' rule
    - ✅ no 'remove' rule
    - ✅ no forbidden language (en/fa/ar)

## SESSION_TOXICITY_CONFIRMED — ✅ PASS

*One session (Asia) clearly negative; others fine.*  · n=160 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_session_toxicity()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/MEDIUM/FIND, TRADE_COUNT_CLIFF/LOW/obs
- **Actual L2:** limit session=Asia, track trade_count=sequence_per_day, keep session=Overlap
- **Expected findings:** SESSION_TOXICITY
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: SESSION_TOXICITY
    - ✅ L2 rule ['limit', 'remove'] on session=Asia (src SESSION_TOXICITY)
    - ✅ firm session rules only on ['Asia']
    - ✅ no forbidden language (en/fa/ar)

## SYMBOL_NO_EDGE_CONFIRMED — ✅ PASS

*One traded symbol (XAUUSD) no-edge; others fine.*  · n=150 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_symbol_no_edge()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/LOW/obs, SYMBOL_NO_EDGE/MEDIUM/FIND
- **Actual L2:** track session=NY, paper_trade symbol=XAUUSD, keep symbol=EURUSD
- **Expected findings:** SYMBOL_NO_EDGE
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: SYMBOL_NO_EDGE
    - ✅ L2 rule ['limit', 'paper_trade', 'remove'] on symbol=XAUUSD (src SYMBOL_NO_EDGE)
    - ✅ firm symbol rules only on ['XAUUSD']
    - ✅ no forbidden language (en/fa/ar)

## POST_LOSS_DECAY_CONFIRMED — ✅ PASS

*Win rate collapses right after a loss (fast re-entry); no systemic.*  · n=160 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_post_loss_decay()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/LOW/obs, TRADE_COUNT_CLIFF/LOW/obs, SYMBOL_NO_EDGE/LOW/obs, POST_LOSS_DECAY/HIGH/FIND
- **Actual L2:** track session=NY, track trade_count=sequence_per_day, track symbol=EURUSD, test post_loss_review=structured_review, track post_loss_review=post_loss_wr
- **Expected findings:** POST_LOSS_DECAY
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: POST_LOSS_DECAY
    - ✅ L1 NOT a finding: SYSTEMIC_UNDERPERFORMANCE
    - ✅ L2 rule ['test', 'track'] on post_loss_review=None
    - ✅ no forbidden language (en/fa/ar)

## PAYOFF_IMBALANCE_CONFIRMED — ✅ PASS

*Small wins, big losses (payoff ratio ~0.4); expectancy ~0.*  · n=120 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_payoff_imbalance()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/LOW/obs, PAYOFF_IMBALANCE/HIGH/FIND, SYMBOL_NO_EDGE/LOW/obs
- **Actual L2:** track session=NY, test exit=let_winners_run, track exit=mfe_mae_exit_reason, track symbol=EURUSD
- **Expected findings:** PAYOFF_IMBALANCE
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: PAYOFF_IMBALANCE
    - ✅ payoff did not fabricate firm remove/limit
    - ✅ L2 rule ['test', 'track'] on exit=None
    - ✅ no forbidden language (en/fa/ar)

## TRADE_COUNT_CLIFF_CHRONOLOGICAL — ✅ PASS

*WR drops after trade #3/day; supplied index is misleading (D3).*  · n=150 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_trade_count_cliff()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/LOW/obs, TRADE_COUNT_CLIFF/HIGH/FIND, SYMBOL_NO_EDGE/LOW/obs, POST_LOSS_DECAY/HIGH/FIND
- **Actual L2:** track session=NY, limit trade_count=2, track symbol=EURUSD, test post_loss_review=structured_review, track post_loss_review=post_loss_wr
- **Expected findings:** TRADE_COUNT_CLIFF
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: TRADE_COUNT_CLIFF
    - ✅ L2 rule ['limit'] on trade_count=2
    - ✅ no forbidden language (en/fa/ar)

## WEAK_EVIDENCE_OBSERVATION_ONLY — ✅ PASS

*Payoff ratio in the soft band → LOW observation, not a finding.*  · n=120 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_weak_observation()` (deterministic, seeded)
- **Actual L1:** PAYOFF_IMBALANCE/LOW/obs
- **Actual L2:** track exit=mfe_mae_exit_reason
- **Forbidden L2 verbs:** limit, remove
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 NOT a finding: PAYOFF_IMBALANCE
    - ✅ no 'limit' rule
    - ✅ no 'remove' rule
    - ✅ L2 rule ['track'] on exit=None
    - ✅ no forbidden language (en/fa/ar)

## DATA_GAP_LOW_SAMPLE — ✅ PASS

*n=15 (<30) → data-collection only.*  · n=15 · license=`data_collection_plan`

- **Input:** `tests/synthetic_lab.py::gen_low_sample()` (deterministic, seeded)
- **Actual L1:** SAMPLE_SIZE_INSUFFICIENT/HIGH/FIND
- **Actual L2:** track data=reach_30_trades
- **Expected findings:** SAMPLE_SIZE_INSUFFICIENT
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: SAMPLE_SIZE_INSUFFICIENT
    - ✅ L2 is track-only
    - ✅ license == data_collection_plan
    - ✅ no forbidden language (en/fa/ar)

## MIXED_MULTI_LEAK_TRADER — ✅ PASS

*Two independent leaks (toxic session + no-edge symbol); overall edge intact.*  · n=240 · license=`playbook_candidate`

- **Input:** `tests/synthetic_lab.py::gen_mixed_multi_leak()` (deterministic, seeded)
- **Actual L1:** SESSION_TOXICITY/MEDIUM/FIND, SYMBOL_NO_EDGE/MEDIUM/FIND
- **Actual L2:** limit session=Asia, paper_trade symbol=XAUUSD, keep session=Overlap, keep symbol=GBPUSD
- **Expected findings:** SESSION_TOXICITY, SYMBOL_NO_EDGE
- **Checks:**
    - ✅ playbook validates (legal ops, sourced, clean)
    - ✅ every rule has source
    - ✅ every op in locked verb set
    - ✅ L1 finding present: SYMBOL_NO_EDGE
    - ✅ L1 finding present: SESSION_TOXICITY
    - ✅ L1 NOT a finding: SYSTEMIC_UNDERPERFORMANCE
    - ✅ L2 rule ['limit', 'remove'] on session=Asia (src SESSION_TOXICITY)
    - ✅ L2 rule ['limit', 'paper_trade', 'remove'] on symbol=XAUUSD (src SYMBOL_NO_EDGE)
    - ✅ firm session rules only on ['Asia']
    - ✅ firm symbol rules only on ['XAUUSD']
    - ✅ no forbidden language (en/fa/ar)
