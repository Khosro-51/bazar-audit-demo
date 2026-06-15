# Bazar Audit Engine — Fresh Independent Re-Audit

**Date:** 2026-06-15
**Trigger:** Post Wave 0A–0E + E1 Supabase state work. Independent pass — the prior audit (`audit_structural.md`) is treated as *claims*, not ground truth.
**Method:** Re-read the current integrated source (engine, report layer, UI, state store, tools, tests, migration, demo CSVs). Focus weighted toward defects *introduced or left behind by the 0A–0E fixes*. Read-only — no code patched.
**Build state at audit:** `pytest` **34/34 PASS**; Monte Carlo (600) `med_high` **5.83%**, `high_only` **3.17%** (both < 10%).

> **Wave 0I update (2026-06-15).** **NOTE-1 (B4) → ✅ ADDRESSED.** Two-tier Monte Carlo validation: a fast coarse tripwire in every `pytest` (N=100, ~4s) plus an authoritative `@pytest.mark.release` gate (N=1000, deselected by default) that enforces **med_high < 10% AND high_only < 10%**. Both share `tools/monte_carlo_validation.false_finding_rates()`; the CLI tool now self-asserts and exits non-zero on breach. Policy documented in `docs/validation.md`; `pytest.ini` registers the marker and deselects `release` by default. Verified: fast suite 43 passed / 1 deselected in 6.5s; `pytest -m release` and `python tools/monte_carlo_validation.py 1000` both PASS (med_high 0.058, high_only 0.033). The N=150-strict approach was rejected — at small N the ~5% rate's sampling noise can exceed 10% (seed 2026 → 11.3%), so a strict 10% there would false-fail; the 10% gate lives at release N where it is statistically meaningful. No engine thresholds changed.

> **Wave 0H update (2026-06-15).** **RA-2, RA-3, RA-6, RA-7 → ✅ RESOLVED.** Single decided-basis win rate (`_decided_win_rate`/`_decided_counts`) applied engine-wide — display *and* gates — for session/symbol/cliff/post-loss (RA-2). Dead code removed: 3 UI helpers, 11 pre-E1 JSON helpers, and the orphaned invite-pool/quota constants (RA-3). Drawdown threshold copy now interpolates `DD_THRESHOLD_PCT` (RA-6). Demo CSVs' `trade_index_in_day` recomputed to match the engine, and the engine's `open_time` sort made **stable** so tie-ordering (and the derived index) is deterministic — also firming up D3 (RA-7). `pytest` **43/43 PASS** (2 new RA-2 tests); Monte Carlo unchanged (`med_high` 5.33%, `high_only` 2.5%); samples byte-identical in their audit output. **All re-audit findings (RA-1…RA-7) are now resolved.**

> **Wave 0G update (2026-06-15).** **RA-4, RA-5 → ✅ RESOLVED.** NaT-timestamp rows are dropped up front in `audit_from_df` with a data-quality warning, and `_drawdown_buckets` ignores NaN balance/lot rows (RA-4). `SupabaseStateStore.request_code` is now a single atomic `upsert(on_conflict="email_hash")` instead of SELECT-then-INSERT, with a client-injection hook enabling the first Supabase-backend unit tests (RA-5). `pytest` **41/41 PASS** (4 new tests); Monte Carlo unchanged (`med_high` 5.33%, `high_only` 2.5%); samples unaffected (0 warnings). RA-2, RA-3, RA-6, RA-7 remain open.

> **Wave 0F update (2026-06-15).** **RA-1 → ✅ RESOLVED.** `DRAWDOWN_RECOVERY_SIZING` is now permutation-gated (LOW observation below significance, finding above) and the Monte Carlo generators emit `balance_before`/`lot_or_size`, so it is finally *exercised and measured*. Post-fix: `pytest` **37/37 PASS** (3 new RA-1 tests); Monte Carlo (600) shows `DRAWDOWN_RECOVERY_SIZING` firing **3/600 ≈ 0.5%** (within alpha), `med_high` **5.33%**, `high_only` **2.5%**. RA-2…RA-7 and the notes remain open. See RA-1 below for detail.

---

## Summary verdict

The engine is in materially better shape than at the original audit: no outcome-leakage, test/display alignment, single score formula, durable state with fail-closed config, deterministic indexing. **No code-level launch blocker found.**

However this pass surfaced **one MEDIUM correctness/validation gap that predates the waves and was never caught** (un-gated, unmeasured drawdown finding), plus a cluster of LOW robustness/cleanup residuals — several of them direct consequences of the 0A–0E changes. None block an *internal* beta; **RA-1 should be resolved before any external user relies on the drawdown finding**, and the live-Supabase operational gate (below) remains the hard blocker for paid beta.

**Standing operational blocker (not a code defect, restated for honesty):** the live Supabase smoke (`tools/supabase_smoke.py`) has only ever run **fail-closed (exit 2)** in this environment — no real project is wired. External **paid** beta remains **BLOCKED** until that runs exit 0 against a real Supabase project (see `audit_structural.md` E1 caveat; not re-verified here).

---

## Launch blockers

| ID | Blocker | Type |
|----|---------|------|
| — | None at code level. | — |
| OPS-1 | Live Supabase state path unverified (smoke only fail-closed). Blocks **paid** beta only. | Operational |

---

## Findings

### RA-1 — MEDIUM — `DRAWDOWN_RECOVERY_SIZING` is un-gated *and* unmeasured — ✅ RESOLVED (Wave 0F)
`bazar_insights.py:670-708` (`insight_drawdown_recovery`); `tools/monte_carlo_validation.py` (`make_random_trader`)

> **Resolution (2026-06-15).** Two parts:
> 1. **Gate added** — new `_perm_p_dd_oversize(normal_lots, dd_lots)` permutation test (null: lot size unrelated to drawdown state; shuffles the dd/normal labels across pooled lots, `p = P(shuffled mean(dd)/mean(rest) ≥ observed)`). `insight_drawdown_recovery` now emits a MEDIUM/HIGH **finding** only when `p < ALPHA_FINDING`, else a **LOW observation** (matching session/symbol/cliff). Snapshot carries `p_value` + `observation`. Bonus correctness: a non-significant pattern is now an observation, so it no longer wrongly penalizes the Bazar Score's discipline component.
> 2. **Now measured** — both Monte Carlo generators (`tools/monte_carlo_validation.py` and the permanent `tests/test_all.py::_random_trader`) emit `balance_before` + a state-**independent** `lot_or_size`, so the finding is exercised on noise.
>
> **Verification:** 3 new tests in `tests/test_lows_fixes.py` (clear oversizing → significant finding; flat sizing → no finding; MC generator now emits the columns). `pytest` **37/37**. Monte Carlo (600): `DRAWDOWN_RECOVERY_SIZING` fires **3/600 ≈ 0.5%** (within the 1.5% alpha), `med_high` **5.33%**, `high_only` **2.5%** — all < 10%. The finding is no longer un-gated, and its false-positive rate is now bounded by the test suite.
>
> *Original finding retained below for history.*

Every other behavioral finding is promoted to MEDIUM/HIGH only behind a statistical gate — permutation (`SESSION_TOXICITY`, `SYMBOL_NO_EDGE`, `TRADE_COUNT_CLIFF`), two-proportion (`POST_LOSS_*`), or z-test (`SYSTEMIC`/`EDGE`). `DRAWDOWN_RECOVERY_SIZING` is the exception: it emits `observation: False` purely on a **bare ratio threshold** (`ratio >= DD_OVERSIZE_RATIO_MIN`), with **no p-value** in its snapshot. That contradicts the engine's own "Phase 2: finding only with evidence" contract.

Worse, it is **invisible to the Monte Carlo false-positive validation**: `make_random_trader` emits only `pnl/pnl_R/session/symbol/initial_risk_amount` — **no `balance_before` or `lot_or_size`**, so `insight_drawdown_recovery` returns `None` for every synthetic trader. Its real-world false-positive rate is therefore **unknown and unbounded by the test suite**. (`PAYOFF_IMBALANCE` is also threshold-only, but it *does* surface in MC — ~5/600 — so it is at least bounded; see RA-note.)

- **Evidence:** snapshot at `:702-705` has no `p_value`/`observation` gate; MC id-counts never include `DRAWDOWN_RECOVERY_SIZING`; no test asserts the insight on realistic data.
- **Risk:** a trader who simply trades larger lots in volatile periods can be told "you size up in drawdowns" with HIGH severity on noise, unmeasured.
- **Fix options:** (a) add a permutation/Mann-Whitney test of dd-bucket vs normal-bucket sizes and gate on it (preferred — matches the rest of the engine); or (b) extend `make_random_trader` to emit `balance_before`/`lot_or_size` and assert its FP rate stays < 10%. Ideally both.

### RA-2 — LOW — Residual scratch-basis inconsistency in sequential insights — ✅ RESOLVED (Wave 0H)
`bazar_metrics.py:58` vs `bazar_insights.py` (post-loss `ref_wr`/`pl_wr`; cliff `_pooled_wr`)

> **Resolution (2026-06-15).** Added `_decided_counts()` / `_decided_win_rate()` (wins / (wins+losses), scratches excluded) — the single engine-wide basis matching `compute_core_metrics.win_rate`. Applied to **every** win rate: session & symbol display rates, cliff bucket rates (and the permutation now runs over decided trades only, so display and test stay aligned per A6), and post-loss `pl_wr`/`ref_wr`/`fast_wr` **plus the two-proportion test denominators**. Scratch-free data (all samples + Monte Carlo) is byte-identical (decided count == total), so no regression; verified with a new scratch-heavy test where a session's reported win rate is `2/6` (decided), not `2/10` (the old all-trades basis).

C2 (Wave 0C) made `compute_core_metrics.win_rate` exclude scratches (decided-trade basis). But the post-loss reference (`ref_wr = (non_pl['pnl']>0).mean()`), `pl_wr`, and the cliff pooled win rates still compute `(pnl>0).mean()` over **all** rows including `pnl==0`. So the global `win_rate` and these per-segment rates sit on **different denominators** when scratches exist. Harmless on the scratch-free samples/MC, but a scratch-heavy upload would show subtly inconsistent rates across insights. Decide one basis engine-wide.

### RA-3 — LOW — Dead code / drift in `streamlit_app.py` — ✅ RESOLVED (Wave 0H)

> **Resolution (2026-06-15).** Verified the dead set forms a closed reference cluster (every reference was a definition, a call inside another dead function, or a comment — no live E1-path caller), then removed: the 3 uncalled UI helpers (`biggest_recoverable`, `_score_color`, `score_panel_html`, `journey_html`), the 11 pre-E1 JSON-model functions (`load/save_assignments`, `assign_code_for_email`, `get_invite_codes`, `get_token_activation`, `activate_token`, `token_expired`, `email_for_code`, `email_bound_elsewhere`, `load/save_beta_usage`), and the now-orphaned constants (`DEFAULT_INVITE_CODES`, `MAX_UPLOADS_PER_CODE`, `TOKEN_TTL_HOURS`, `BETA_USAGE_FILE`, `ASSIGN_FILE`, `ACCESS_LOG_FILE`). Removing the pre-E1 helpers also eliminates the D5-style re-wiring risk (no leftover ungated upload/quota code). Post-removal grep confirms zero dangling references (only explanatory comments remain); `py_compile` clean. Kept: `get_access_code`/`DEFAULT_ACCESS_CODE` (live admin), `_send_access_code_email`, `_client_ip`, `email_hash`, `MAX_UPLOAD_MB`, `compute_bazar_score`.
- **Uncalled UI helpers:** `biggest_recoverable` (`:742`), `score_panel_html` (`:765`), `journey_html` (`:793`) — defined, never called. The report uses `journey_bar_html` from `bazar_report_extras` (`:917`), so there are **two journey implementations, one dead**.
- **Retained legacy entitlement helpers (11):** `load/save_assignments`, `assign_code_for_email`, `activate_token`, `token_expired`, `get_token_activation`, `email_for_code`, `email_bound_elsewhere`, `load/save_beta_usage`, `get_invite_codes` — intentionally kept post-E1 as "read-only debug", but never called in any live path.
- **Now-unused constants:** `MAX_UPLOADS_PER_CODE`, `TOKEN_TTL_HOURS`, `DEFAULT_INVITE_CODES`.
- **Risk:** drift / accidental re-wiring of a pre-E1 ungated path (the D5 branch was exactly that). Recommend a cleanup wave that deletes them (now that E1 is the sole path) or moves the debug helpers behind an explicit `# DEPRECATED` module.

### RA-4 — LOW — Timestamp / balance robustness not guarded — ✅ RESOLVED (Wave 0G)
`bazar_insights.py` `_post_loss_indices` (`:139-165`), `_drawdown_buckets` (`:168-186`), cliff date derivation (`:~360`)

> **Resolution (2026-06-15).** `audit_from_df` now drops rows whose `open_time`/`close_time` failed to parse (NaT) **once, up front**, right after coercion — before sequencing, the per-day index, and the 3D map see them — and appends a data-quality warning (`"N trade(s) had unparseable open/close timestamps and were excluded"`). Because this runs before everything else, `_post_loss_indices` and the cliff derivation never see NaT and need no internal guard (and must not filter internally — they return positional indices into the frame). `_drawdown_buckets` separately drops NaN `balance`/`lot` rows so a single bad value can't poison the running peak or the size means. Verified: a 36-row frame with one unparseable-timestamp row → 35 analyzed + warning + no crash; `_drawdown_buckets` with NaN balance/lot drops those rows cleanly.

The engine coerces bad datetimes with `pd.to_datetime(errors='coerce')` → `NaT` is possible, and broker exports can carry `NaN` balances. `_post_loss_indices` runs `np.argsort`/`searchsorted` on a possibly-`NaT` close array; `_drawdown_buckets` seeds `peak = balance[0]` (a `NaN` first row makes `peak` stay `NaN`, classifying everything "normal"). Behavior is **degenerate but non-crashing**, not validated. Recommend dropping/flagging `NaT`-close / `NaN`-balance rows up front (and surfacing a data-quality note).

### RA-5 — LOW — Supabase `request_code` is not atomic for a brand-new email — ✅ RESOLVED (Wave 0G)
`bazar_state_store.py` `SupabaseStateStore.request_code`

> **Resolution (2026-06-15).** Replaced the SELECT-exists → INSERT/UPDATE pair with a **single** `.upsert(payload, on_conflict="email_hash").execute()`, matching the SQLite backend's `ON CONFLICT` upsert. `first_seen_at` is omitted (DB default fills it on insert, preserved on update) and `report_generated` is omitted (never reset by a re-issue); `code_used_at` is set to NULL so the freshly issued code is usable while the prior one is invalidated. Added a `client=` dependency-injection hook to `__init__` so the Supabase logic can be unit-tested with a fake PostgREST client — closing part of the NOTE-2 coverage gap. Verified: `request_code` makes exactly one `upsert` with `on_conflict="email_hash"` and no select/insert; a re-issue preserves an existing `report_generated=True` and leaves `code_used_at` NULL. *(Note: the live Postgres round-trip is still only operationally verifiable via `tools/supabase_smoke.py` against a real project.)*

The SQLite backend upserts (`ON CONFLICT(email_hash) DO UPDATE`) — race-safe. The Supabase backend does **SELECT-exists → INSERT/UPDATE** in two calls; two simultaneous *first* requests for the same email can both miss the SELECT and the second `INSERT` then violates `UNIQUE(email_hash)` → unhandled `APIError`. Low probability (same email, same instant) and integrity is still protected by the constraint, but it surfaces as an error instead of a clean re-issue. Fix: use `.upsert(payload, on_conflict="email_hash")` to mirror the SQLite path.

### RA-6 — LOW — Drawdown body copy hardcodes "۳٪", decoupled from `DD_THRESHOLD_PCT` — ✅ RESOLVED (Wave 0H)
`bazar_insights.py:694`

B3 (Wave 0E) centralized `DD_THRESHOLD_PCT = 3.0`, but the Persian body still said "بیش از ۳٪" as a literal.

> **Resolution (2026-06-15).** The body now interpolates `{int(DD_THRESHOLD_PCT)}٪`, so the copy tracks the constant.

### RA-7 — LOW — Demo CSVs still carry the timestamp-inconsistent `trade_index_in_day` — ✅ RESOLVED (Wave 0H)
`sample_data/bazar_sample_*_trader.csv`

> **Resolution (2026-06-15).** Recomputed `trade_index_in_day` in all three demo CSVs to the faithful per-calendar-day, open_time-ordered sequence (read with `dtype=str` so only that column changed — no float/date reformatting of the fixtures). The engine ignores the column (D3 always derives), so audit output is unchanged. To make the rewrite match the engine exactly on tied timestamps — and to remove a latent D3 non-determinism (pandas default `sort_values` is not stable) — the engine's `open_time` sort in `audit_from_df`/`load` is now `kind='stable'`. Verified: all three samples' `trade_index_in_day` now equals the engine-derived index exactly; suite 43/43; samples' audit output unchanged.

D3 (Wave 0D) established that the demo files' supplied `trade_index_in_day` disagrees with their own `open_time` (PROBLEM's first chronological trade is index 5). The engine now ignores the column (always derives), **but it is still present in the CSVs and shown in the Data tab**, so an attentive user sees an index column that contradicts the analysis. Cosmetic/integrity only — recommend recomputing or dropping the column in the demo fixtures. *(Confirmed positive: no demo narrative string promises a cliff, so D3's removal of the PROBLEM cliff did not create a narrative contradiction.)*

---

## Non-defect notes

- **NOTE-1 (was B4) — ✅ ADDRESSED (Wave 0I, 2026-06-15):** replaced the weak single N=40 test with a two-tier model — fast coarse tripwire (N=100, every `pytest`) + authoritative release gate (N=1000, `pytest -m release` / `python tools/monte_carlo_validation.py 1000`, enforcing med_high<10% AND high_only<10%). One shared implementation; CLI self-asserts (exit≠0 on breach); documented in `docs/validation.md`. See the Wave 0I banner above.
- **NOTE-2 — Coverage gaps:** `SupabaseStateStore` methods have no unit tests (need a live/mock server; the smoke tool covers them operationally). The Streamlit **gate flow** (request→verify→upload→mark) is not unit-tested — only the store beneath it is. `insight_drawdown_recovery`'s *full path* is untested on realistic data (only its `_drawdown_buckets` helper is).
- **NOTE-3 — Product safety: PASS.** `recommended_action` strings are behavioral/risk only (cooldowns, per-day trade caps, session avoidance, exit review, position-size discipline) — no buy/sell, no price levels, no financial-advice phrasing. Disclaimer present in en/fa/ar; no live market data anywhere.
- **NOTE-4 — Report/score equivalence: PASS.** Single `compute_bazar_score` formula feeds the report (D2 held); equity curve attaches from `df` (D1 held); recoverable card shares `ALPHA_FINDING` (D4 held).
- **NOTE-5 — Decision-time discipline: PASS.** A1 (`balance_before`), A2 (non-post-loss complement), E3 (decision-time DD), A7 (last *completed* prior trade by close_time) are all decision-time-correct on re-read.
- **NOTE-6 — `_r_series` computed mode** divides `pnl / initial_risk_amount` with only a `risk > 0` guard; a tiny positive risk yields an outlier R that can dominate `expectancy_R` and the z-test. Pre-existing, low-likelihood; worth a sanity floor on risk if computed mode sees real use.

---

## Recommended patch waves

- **Wave 0F (correctness/validation) — ✅ DONE 2026-06-15:** RA-1 — gated `DRAWDOWN_RECOVERY_SIZING` with a permutation test *and* extended both MC generators to measure it. Drawdown now fires ~0.5% on noise; suite 37/37.
- **Wave 0G (robustness) — ✅ DONE 2026-06-15:** RA-4 (NaT/NaN guards + data-quality warning), RA-5 (Supabase atomic upsert + client-injection test hook). Suite 41/41.
- **Wave 0H (cleanup/consistency) — ✅ DONE 2026-06-15:** RA-2 (single decided-basis win rate engine-wide), RA-3 (deleted dead code/constants), RA-6 (interpolated threshold copy), RA-7 (recomputed demo index + stable engine sort). Suite 43/43. **All RA findings resolved.**

---

## Suggested tests

1. Extend `make_random_trader` with `balance_before`/`lot_or_size`; assert `DRAWDOWN_RECOVERY_SIZING` FP rate < 10% (RA-1).
2. `insight_drawdown_recovery` on a crafted realistic dataset: oversizing-in-drawdown → finding; flat sizing → none (RA-1).
3. Scratch-heavy dataset: assert `win_rate`, post-loss `ref_wr`, and cliff rates use a consistent basis (RA-2).
4. `NaT` close_time / `NaN` balance rows → engine returns gracefully with a data-quality flag, no crash (RA-4).
5. Supabase `request_code` idempotency under a simulated concurrent first-request (mock client) (RA-5).
6. (Release gate) larger-N Monte Carlo with explicit `med_high` and `high_only` thresholds (NOTE-1).

---

## Rules honored

- The prior `audit_structural.md` was **not** edited and nothing there was re-marked. This is a standalone report.
- **No code was patched** in this pass.
- No beta-readiness claim is made beyond: internal/dev usable; external **paid** beta remains blocked on the live-Supabase operational gate; RA-1 is the most material correctness residual to clear before external users lean on the drawdown finding.
