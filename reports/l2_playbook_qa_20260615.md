# L2 Playbook — Internal QA / Red-Team

**Date:** 2026-06-15 · **Scope:** L2-core (`bazar_playbook.py`), deterministic, internal/flagged-off.
**Harness:** `tools/l2_qa_redteam.py` (reproducible: `python tools/l2_qa_redteam.py [--dump]`).
**Method:** generate playbooks across the required demo profiles + adversarial edge cases; run automated safety/correctness/quality checks; patch only trivial+safe issues, report the rest.

---

## Verdict: 🟢 PASS (as of Wave 0M, 2026-06-15)

> **Update (Wave 0M):** F3 has been **resolved** — under a systemic core `paper_trade`, `keep` rules are now demoted to a "track your strongest area, confirm once the core edge is proven" note, removing the mixed message. Harness now reports **0 FAIL, 0 WARN** across all 9 profiles; suite **57 passed / 1 deselected**.

Original red-team (this report): two real defects found and **fixed** (trivial + safe, F1/F2); one **design-choice warning** (F3) reported, now resolved in Wave 0M. L2 remains internal-only and OFF by default (`ENABLE_L2_PLAYBOOK=false`), so none of this was ever user-facing.

---

## Profiles exercised (9)

| Profile | Source | Result |
|---------|--------|--------|
| GOOD | sample | PASS — 1 rule (track), conf LOW |
| AVERAGE | sample (observation-heavy) | PASS — 3 rules (track + keep), conf LOW |
| PROBLEM | sample (systemic) | PASS — 5 rules; `paper_trade` core leads, behaviorals → track |
| LOW_SAMPLE (n=15) | synthetic | PASS — `data_collection_plan`, 1 track rule, "not strong enough yet" |
| OBS_HEAVY_MARGINAL (n=140) | synthetic | PASS — 7 rules, all track/keep (no firm), conf LOW |
| ALL_WINS (no losses) | synthetic | PASS — 0 rules (nothing to act on); no crash on PF ceiling |
| SCRATCH_HEAVY | synthetic | PASS — 1 rule; scratches handled (decided basis) |
| EXTREME_TOXIC_SESSION (70% one session) | synthetic | PASS *(after F2 fix)* — over-restriction now warned |
| SYSTEMIC_WITH_STRENGTH | hand-built | PASS *(after F3 fix)* — keep demoted to "track strongest area"; no mixed message |

## Checks run (per profile)
C1 forbidden language (buy/sell/long/short/**signal**/price/SL/TP/guarantee — en/fa/ar) · C2 no firm action from an observation/data_gap · C3 no keep-vs-restrict contradiction (+ C3b keep-vs-core-paper_trade clarity) · C4 over-restriction must be warned · C5 clear 30-trade protocol · C6 success/failure engine-sourced + uncertainty band · C7 `validate_playbook` · C8 determinism · C9 license correctness.

---

## Findings

### F1 — FAIL → ✅ FIXED — "signal" language in output (all profiles)
The hypothesis text said "track/test N **signal(s)**" and a safety disclaimer said "never adds new rules, symbols, or **signals**". For a product that is explicitly *not* a signal service, the literal word is a brand/safety risk.
**Fix (trivial+safe):** reworded to "track/test N **pattern(s)**" and "never adds new rules or new instruments"; added bare `signal` to the module's `_FORBIDDEN_TOKENS` so `validate_playbook` now rejects any future reintroduction (in any language). Regression test `test_qa_no_signal_or_advice_language`.

### F2 — FAIL → ✅ FIXED — over-restriction via `limit`/`paper_trade` was unwarned
EXTREME_TOXIC produced `limit session=Asia` (70% of trades) + `paper_trade symbol=EURUSD` (70%) with **no warning**. The conflict resolver only warned when downgrading a `remove`; a MEDIUM finding maps straight to `limit`, which bypassed it — so a playbook could quietly tell a user to avoid ~70% of their trading.
**Fix (trivial+safe):** added `_over_restriction_warning()` — when any firm `remove`/`limit`/`paper_trade` on a session/symbol touches > 40% of historical trades, append an explicit "touches more than 40% … introduce gradually" limitation (uses the largest single restriction's share to avoid double-counting overlapping segments). It only *adds a warning*; it doesn't silently over-restrict. Regression test `test_qa_over_restriction_limit_is_warned`.

### F3 — WARN → ✅ RESOLVED (Wave 0M) — `keep` coexisted with core `paper_trade`
SYSTEMIC_WITH_STRENGTH yielded `paper_trade strategy_core` **and** `keep session=London` — a mixed message ("paper-trade your whole core" vs "keep trading London").
**Resolution (Wave 0M):** the systemic override now also demotes `keep` rules to `track`, with a dedicated message — *"Your relatively strongest area is {name} — confirm it still holds once the core edge is proven (don't trade it live until then)."* No `keep` survives under a core `paper_trade`, so the contradiction is gone while the strength is still surfaced honestly (as something to confirm, not to act on live). Regression test `test_f3_keep_demoted_under_systemic_core_paper_trade`; the harness C3b WARN no longer fires (0 WARN).

---

## Observations (no action required)
- **ALL_WINS** yields a 0-rule playbook (no fabricated actions) — correct and honest; the engine has no segment breakdown to cite for a `keep`, so none is invented. Minor UX note only.
- **EXTREME_TOXIC** still produces a heavily-restrictive plan (now warned). A deeper, df-aware collateral model (accounting for overlap between session and symbol restrictions) is a possible future refinement, not required for correctness.
- Evidence discipline held everywhere: every `remove`/`limit` traced to a `finding`; every `observation`/`data_gap` produced only `track`; no contradictions (keep vs restrict on the same component).

---

## Patches applied (trivial + safe, this wave)
- `bazar_playbook.py`: reworded hypothesis ("pattern(s)"); reworded disclaimer (no "signals"); added `signal` to `_FORBIDDEN_TOKENS`; added `_over_restriction_warning()` + call.
- `tests/test_playbook.py`: +2 regression tests (no-signal-language, over-restriction-warned). Now 13 L2 tests.

## Tests (after Wave 0M)
- `pytest tests/test_playbook.py` → **14 passed**.
- Full suite → **57 passed, 1 deselected**.
- `python tools/l2_qa_redteam.py` → **0 FAIL, 0 WARN**, exit 0.

## Bottom line
L2-core is safe and correct for **internal** use: no signal/advice/price language, no firm action without a finding, over-restriction is warned, no keep/paper-trade contradiction, deterministic, and validating. All red-team findings (F1, F2, F3) are resolved. L2-core's algorithm is validated **internally** by the Synthetic Statement Lab golden gate (`docs/synthetic_statement_lab_spec.md`) + the Monte-Carlo honesty gate — not by trader feedback. No external exposure is implied — L2 stays behind `ENABLE_L2_PLAYBOOK=false`; external exposure remains a separate operational gate (live Supabase smoke + Streamlit Cloud end-to-end).
