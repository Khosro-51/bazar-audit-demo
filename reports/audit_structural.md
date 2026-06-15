# Bazar Audit Engine — Structural Audit

**Date:** 2026-06-15
**Scope:** `bazar_audit_engine.py`, `bazar_metrics.py`, `bazar_insights.py`, `bazar_schema.py`, `bazar_report_extras.py`, `streamlit_app.py`, `tools/`, `tests/`
**Method:** Full read of the engine + UI + report layer; empirical checks (test suite, sample data, dead-code/usage grep). Tests pass (8/8) — none of the findings below are caught by the existing suite.

> **Nature of the product.** This is a *post-hoc audit* of a trader's already-realized trades, not a live/backtest strategy runner. So "lookahead bias" here means **outcome leakage** (using a trade's own result to classify/judge it) and **in-sample data-snooping**; "live vs backtest equivalence" means **the result a user gets in the app vs. the result baked into the downloadable report, and the result via CSV entry-point vs. UI entry-point**. Findings are framed accordingly.

> **Wave 0A status (2026-06-15).** Five items fixed and verified: **E2, D1, D2, A1, A2** → ✅ RESOLVED. After the fixes the suite is 8/8 green and the standalone Monte Carlo false-finding rate is 5.67% over 600 random traders (under the 10% ceiling). See each section for the fix detail.

> **Wave 0B status (2026-06-15).** Three more items fixed and verified: **A3, A4, A5** → ✅ RESOLVED. Suite still 8/8; Monte Carlo false-finding rate unchanged at 5.67% (these fixes touch reporting/selection/edge-case gating, not the core significance gates).

> **E1 closure (2026-06-15).** Durable state storage implemented: **E1** → ✅ RESOLVED. New `bazar_state_store.py` (SQLite dev backend / Supabase production backend) is now the source of truth for access codes and the one-free-report rule; local JSON is no longer authoritative. 11 new tests added (`tests/test_state_store.py`), full suite **19/19** green, Monte Carlo unchanged at 5.67%. (Live Supabase path still needs an end-to-end run via `tools/supabase_smoke.py` before external paid beta.)

> **Wave 0C status (2026-06-15).** Metric-correctness cluster fixed and verified: **B1, B2, C1, C2, C3** → ✅ RESOLVED. 9 new tests (`tests/test_metrics_fixes.py`), full suite **28/28** green, Monte Carlo unchanged at 5.67% (samples are scratch-free/full-mode so these fixes don't perturb them).

> **Wave 0E status (2026-06-15).** Remaining LOWs swept: **A7, B3, D4, D5, E3** → ✅ RESOLVED. Post-loss "previous" is now close-time/overlap-safe (A7); session-toxicity HIGH uses a scale-invariant R cutoff and severity thresholds are centralized (B3); the recoverable card shares the engine's `ALPHA_FINDING` (D4); the dead, ungated non-demo upload branch is fail-closed (D5); drawdown buckets use a running high-water mark with no dropped recovery trade (E3). A7/E3 logic extracted into unit-testable helpers. 6 new tests (`tests/test_lows_fixes.py`), full suite **34/34**, Monte Carlo `med_high` 5.83% / `high_only` 3.17% (both < 10%). Only B4 (a note) and the live-Supabase smoke-test gate remain.

> **Wave 0D status (2026-06-15).** Cliff-consistency + index-equivalence fixed: **A6, D3** → ✅ RESOLVED. `trade_index_in_day` is now always derived deterministically from `open_time` (D3); the reported cliff is the argmax-drop split the permutation p-value actually tests (A6). Investigation finding: the GOOD/PROBLEM demo fixtures carried a supplied index inconsistent with their own timestamps — it was the sole reason PROBLEM showed a `TRADE_COUNT_CLIFF`; under faithful derivation that cliff is (correctly) gone and GOOD shows only a non-significant LOW observation. Two acceptance tests updated to encode the correct behavior. Full suite **28/28**; guarded Monte Carlo FP (`med_high`) unchanged at 5.67%. Remaining open: A7, B3, B4(note), D4, D5, E3.

---

## Severity summary

| ID | Severity | Area | Status | One-liner |
|----|----------|------|--------|-----------|
| A1 | **HIGH** | Leakage | ✅ Fixed (0A) | Drawdown sizing classified using *post-trade* balance (`balance_after`) |
| A2 | **HIGH** | Leakage | ✅ Fixed (0A) | Post-loss WR/binomial test compares the subset against a baseline that *contains* it |
| D1 | **HIGH** | Live≠Report | ✅ Fixed (0A) | Equity curve in the downloadable report is permanently dead (NameError swallowed) |
| D2 | **HIGH** | Live≠Report | ✅ Fixed (0A) | Two divergent Bazar Score formulas; the documented one is dead code |
| E1 | **HIGH** | State | ✅ Fixed (0B) | Quota/token state in local JSON, no locking, ephemeral FS → bypass + races |
| A3 | MED | Logic | ✅ Fixed (0B) | "Worst symbol" chosen by *total* PnL but p-value tests worst-by-*mean* |
| A4 | MED | Logic | ✅ Fixed (0B) | Empty/all-NaN `pnl_R` column disables the systemic significance guard |
| A5 | MED | Formula | ✅ Fixed (0B) | Cliff "before/after WR" is an unweighted mean of buckets, not pooled WR |
| B1 | MED | Config | ✅ Fixed (0C) | `r_mode` threshold asymmetry (80% vs >0) → R metrics on a tiny subset |
| B2 | MED | Config | ✅ Fixed (0C) | `computed` mode can never reach MEDIUM `EDGE_BELOW_BREAKEVEN` |
| C1 | MED | Formula | ✅ Fixed (0C) | `profit_factor`/`payoff_ratio` return `0.0` when there are no losses |
| D3 | MED | Equivalence | ✅ Fixed (0D) | Provided vs derived `trade_index_in_day` can change cliff results |
| E2 | MED | State | ✅ Fixed (0A) | Access code shown on-screen when SMTP unconfigured (contradicts intent) |
| A6 | LOW | Logic | ✅ Fixed (0D) | Cliff p-value tests max-drop split; reported numbers come from first-crossing split |
| A7 | LOW | Logic | ✅ Fixed (0E) | Post-loss sequencing by `open_time` but gap uses prev `close_time` (overlap) |
| B3 | LOW | Config | ✅ Fixed (0E) | Scale-dependent magic numbers (`avg_pnl < -60`, `dd_pct > 3`) |
| C2 | LOW | Formula | ✅ Fixed (0C) | Scratch trades (`pnl==0`) counted as non-win in WR but excluded elsewhere |
| C3 | LOW | Formula | ✅ Fixed (0C) | Rounded `avg_win`/`avg_loss` reused in downstream ratios |
| D4 | LOW | Equivalence | ✅ Fixed (0E) | Recoverable "confirmed" uses p<0.05 vs engine's ALPHA=0.015 |
| D5 | LOW | Dead code | ✅ Fixed (0E) | Non-demo upload branch unreachable (`DEMO_MODE` hardcoded `True`) |
| E3 | LOW | Cold-start | ✅ Fixed (0E) | DD peak init underestimates early drawdown; recovery trade dropped from both buckets |

---

## A. Logic bugs & lookahead / leakage

### A1 — HIGH — Drawdown sizing uses *post-trade* balance (outcome leakage) — ✅ RESOLVED (Wave 0A)
`bazar_insights.py:524-543`

> **Resolution (2026-06-15).** Classification now reads `df['balance_before']` (equity at the moment the size was chosen); the column guard requires `balance_before`. A large losing trade can no longer classify its own outcome as "drawdown." Behavioral note: uploads carrying only `balance_after` now skip `DRAWDOWN_RECOVERY_SIZING` rather than emit a leaky finding — the correct trade-off (`balance_before` is in `RECOMMENDED_COLS` and present in all sample files).

```python
balance = df['balance_after'].values
peak = balance[0]
...
for i, b in enumerate(balance):
    dd_pct = (peak - b) / peak * 100 if peak > 0 else 0
    lot    = df.iloc[i]['lot_or_size']
    if dd_pct > 3:
        in_dd = True; dd_s.append(lot)
```

A trade is classified as "in drawdown" using `balance_after` — the balance **after that trade's own PnL is applied**. A large losing trade pushes the balance below peak and therefore classifies *itself* as a drawdown trade. The insight then concludes "you size up during drawdowns," but the mechanism guarantees that large-lot losers land in the `dd_s` bucket regardless of the trader's intent. This conflates cause (sizing decision) with effect (the loss this trade produced) — classic leakage.

**Fix:** classify the *state at decision time* using `balance_before` (present in the data — confirmed in all three sample files). The position size was chosen before the outcome existed.

```python
balance = df['balance_before'].values   # state when the size was decided
```

---

### A2 — HIGH — Post-loss test reference is contaminated by the test sample — ✅ RESOLVED (Wave 0A)
`bazar_insights.py:396, 411-413, 425, 479`

> **Resolution (2026-06-15).** The reference is now the **non-post-loss complement** (`ref_wr`), used for `wr_drop`, `fast_drop`, the displayed from→to, and the snapshot (overall WR retained as `overall_wr`). Removing the contamination revealed that the old one-sample binomial against `baseline_wr` was only holding false positives down *by accident* (the null contained the tested sample). Testing the disjoint complement with a one-sample binomial against the *estimated* `ref_wr` inflated significance and pushed the Monte Carlo guard to 12.5%. Fixed properly with a **two-proportion z-test** (`_two_prop_p_less`, new helper) on both the post-loss and fast-reentry gates, which accounts for sampling error in both groups. Post-fix: suite 8/8; standalone Monte Carlo MED/HIGH false-finding rate 5.67% over 600 traders (post-loss findings ~1.7% combined).

```python
baseline_wr  = metrics["win_rate"]          # win rate over ALL trades
...
pl_wr   = (pl['pnl'] > 0).mean()
wr_drop = baseline_wr - pl_wr
...
_binom_p_le(_wins_pl, len(post_loss_idx), baseline_wr)   # test subset vs p0=baseline
```

`baseline_wr` is the win rate over **all** trades, which *includes the post-loss trades being tested*. The binomial null `p0 = baseline_wr` and the reported `wr_drop` both use this contaminated reference. Because the weak post-loss trades are blended into the baseline, the baseline is pulled down toward the post-loss rate, so:
- `wr_drop` **understates** the true decay, and
- the binomial p-value is **biased toward non-significance** (loss of power), so real post-loss decay can be silently dropped at the `ALPHA_FINDING` gate.

**Fix:** compare against the complement (non-post-loss trades):
```python
non_pl = df.drop(index=post_loss_idx)
ref_wr = (non_pl['pnl'] > 0).mean()
wr_drop = ref_wr - pl_wr
... _binom_p_le(_wins_pl, len(post_loss_idx), ref_wr)
```

---

### A3 — MEDIUM — "Worst symbol" selected by total PnL, but the p-value tests worst-by-mean — ✅ RESOLVED (Wave 0B)
`bazar_insights.py:640` vs `_perm_p_worst_group` stat at `bazar_insights.py:52-60`

> **Resolution (2026-06-15).** `insight_symbol_edge` now selects `worst = min(toxic, key=lambda x: x["avg_pnl"])` — worst-by-mean — aligning the reported symbol (and its counterfactual) with the mean-based permutation statistic, exactly as `SESSION_TOXICITY` already does. Verified on the PROBLEM sample: the displayed symbol flipped from NAS100 (worst total) to XAUUSD (worst mean, p=0.375), so the shown symbol now owns the p-value that was being reported. No effect on the false-finding rate (the p-value itself was already mean-based).

```python
worst = min(toxic, key=lambda x: x["total_pnl"])      # selection by TOTAL pnl
...
p_val = _perm_p_worst_group(df, 'symbol', min_n=8, ...) # statistic = worst group MEAN
```

The permutation statistic in `_perm_p_worst_group` is the *minimum group mean*. But the symbol reported to the user is the one with the most-negative *total*. A high-volume symbol with a slightly negative mean can win "worst total" while a different, smaller symbol is what actually drives the (mean-based) p-value. The displayed significance therefore may not belong to the displayed symbol.

Note `SESSION_TOXICITY` is internally **consistent** — it selects `worst` by `avg_pnl` (`:258`), matching the statistic. Only the symbol path is mismatched.

**Fix:** select `worst` by `avg_pnl` for symbols too (align the reported entity with the tested statistic), or make the permutation statistic the worst *total*.

---

### A4 — MEDIUM — An empty/all-NaN `pnl_R` column disables the significance guard — ✅ RESOLVED (Wave 0B)
`bazar_insights.py:200-212` (and the symmetric `_sig_edge` at `160-165`)

> **Resolution (2026-06-15).** The `_sig_sys` guard now gates on **data**, not schema: it builds `_r = df['pnl_R'].dropna()` and uses it only when `len(_r) > 10`, otherwise falls back to dollar `pnl.dropna()`. An all-NaN (or near-empty) `pnl_R` column can no longer slip past both branches and leave `_sig_sys = True`. Verified: identical data run with an all-NaN `pnl_R` column vs. with no column at all now yields the **same** systemic verdict (schema-independent), and a high-gap/high-variance zero-edge trader is correctly suppressed in both. *Scope note: `_sig_edge` (the `EDGE_BELOW_BREAKEVEN` z-test) was left to **B2**, since for the all-NaN case it already stays conservative (`exp_R` is `None`, so it emits a LOW observation, not a false finding); B2 covers giving `computed`-mode its R-based edge test.*

```python
_sig_sys = True
if 'pnl_R' in df.columns:
    _r = df['pnl_R'].dropna()
    if len(_r) > 10 and _r.std(ddof=1) > 0:
        _se = _r.std(ddof=1) / (len(_r) ** 0.5)
        _sig_sys = (float(_r.mean()) / _se) < -2.0
else:
    _p = df['pnl'].dropna()
    ...
if not _sig_sys:
    return None
```

The branch keys off **column presence**, not data presence. If a `pnl_R` column exists but is all-NaN (or has ≤10 non-null values), the inner `if` is false, the `else` (dollar-based) guard is **never reached**, and `_sig_sys` stays at its default `True`. The `SYSTEMIC_UNDERPERFORMANCE` HIGH finding then fires on a large WR gap **with no noise check at all**. `r_mode` would be `pnl_only` here, so the guard contradicts the engine's own mode.

**Fix:** gate on data, not schema:
```python
r = df['pnl_R'].dropna() if 'pnl_R' in df.columns else pd.Series(dtype=float)
series = r if len(r) > 10 else df['pnl'].dropna()
```
Same fix for `_sig_edge` (`:160`), which only computes when the column is present — see **B2**.

---

### A5 — MEDIUM — Cliff "before/after win rate" is an unweighted bucket average — ✅ RESOLVED (Wave 0B)
`bazar_insights.py:338-340, 349, 370-372`

> **Resolution (2026-06-15).** The split is still *detected* on the unweighted per-index series (kept consistent with the permutation statistic — A6 remains separate/open), but the win rates **displayed** (`before_wr`, `after_wr`, `drop_pct`, body text) are now the real trade-weighted pooled rates over the buckets before/after the split, via a `_pooled_wr()` helper (`Σ nᵢ·wrᵢ / Σ nᵢ`). Verified on the PROBLEM sample: the shown drop is now **13.8 pts** (pooled) where the unweighted statistic had inflated it past the 15-pt detection threshold — the honest number the trader can reproduce. Severity now reflects the pooled magnitude.

```python
before = np.mean([r["win_rate"] for r in results[:i]])
after  = np.mean([r["win_rate"] for r in results[i:]])
```

Each `trade_index_in_day` bucket contributes equally regardless of how many trades it holds: a bucket with 5 trades counts the same as one with 50. The body text then tells the user "Win Rate drops from X% to Y%," but X and Y are **unweighted averages of per-bucket rates**, not the actual pooled win rate before/after the cliff. The permutation statistic mirrors this (so the p-value is self-consistent), but the *number shown to the trader is not the WR they would compute themselves*.

**Fix:** report pooled WR for display (count wins/trades across buckets), even if the test statistic stays unweighted; or weight both.

---

### A6 — LOW — Cliff p-value tests a different split than the one reported — ✅ RESOLVED (Wave 0D)
`bazar_insights.py:336-353`, `_perm_p_cliff:80-93`

> **Resolution (2026-06-15).** The cliff is now located at the **argmax-drop split** across all cut points — the exact statistic `_perm_p_cliff` tests — instead of the first split to cross 0.15. Same unweighted per-index rates and buckets as the test, so the reported cut point equals the tested one. The trigger set is unchanged (argmax > 0.15 iff some split crosses 0.15). The displayed drop remains the *pooled* (trade-weighted) magnitude at that split per A5; A6 aligns the *location*. Side effect: because the argmax split has a larger drop, a couple of random-noise cliffs shift MEDIUM→HIGH in Monte Carlo (`high_only` 0.0233→0.0267); the gated `med_high` FP rate the permanent test enforces is unchanged at 5.67%.

The engine reports the **first** split where `before - after > 0.15`. The permutation statistic is the **maximum** drop over *all* splits. So the reported `cliff_at_trade`/`drop_pct` and the validated p-value can correspond to different cut points. It's conservative (max ≥ first), but the displayed numbers don't describe the tested quantity.

**Fix:** report the argmax split (the one the statistic actually uses), or test the first-crossing drop directly.

---

### A7 — LOW — Post-loss sequencing by `open_time`, gap measured from prior `close_time` — ✅ RESOLVED (Wave 0E)
`bazar_insights.py:400-406`

> **Resolution (2026-06-15).** Extracted a `_post_loss_indices(opens, closes, pnls)` helper: a trade is "post-loss" iff the **most-recently-completed prior trade** — the one with the latest `close_time` at/before this trade's `open_time` — was a loss. This is correct under overlapping positions (the trade that *opened* just before may still be open), and the fast-re-entry gap is now **always ≥ 0** by construction. Verified: a still-open prior loser is not counted as the predecessor; gaps are non-negative under heavy overlap. (On the non-overlapping samples this reduces to the old behavior — suite unchanged; on the overlapping Monte Carlo traders it removes negative-gap "fast re-entry" artifacts.)

```python
for i in range(1, len(df)):
    if df.iloc[i-1]['pnl'] < 0:                       # "previous" = prior by open_time
        gap = (df.iloc[i]['open_time'] - df.iloc[i-1]['close_time']).total_seconds()/60
```

`audit_from_df` sorts only by `open_time`. With overlapping positions the trade that *opened* just before isn't necessarily the one that *closed* just before, and `gap` can be negative. "Previous trade was a loss" and the 60-minute fast-reentry window are both unreliable when positions overlap.

**Fix:** define "previous" by `close_time` for the post-loss relationship, and clamp/flag negative gaps (overlap).

---

## B. Parameter definitions & misconfigurations

### B1 — MEDIUM — `r_mode` threshold asymmetry → R metrics on a tiny subset — ✅ RESOLVED (Wave 0C)
`bazar_metrics.py:5-10, 13-20`

> **Resolution (2026-06-15).** `computed` mode now requires the **same ≥80% coverage** as `full` (`R_COVERAGE_MIN = 0.8`), counting only rows where R is actually defined (`initial_risk_amount > 0`, matching `_r_series`). A dataset with a single usable risk value stays `pnl_only` instead of fabricating `expectancy_R` from ~1 row. Verified: 1-of-100 risk rows → `pnl_only` (`expectancy_R is None`); full coverage → `computed` with populated R metrics.

```python
if 'pnl_R' in df.columns and df['pnl_R'].notna().sum() > len(df) * 0.8:  # 'full' needs 80%
    return 'full'
if 'initial_risk_amount' in df.columns and df['initial_risk_amount'].notna().sum() > 0:  # 'computed' needs ONE
    return 'computed'
```

`full` requires 80% coverage, but `computed` triggers on a **single** non-null `initial_risk_amount`. A dataset with 1 valid risk value out of 200 becomes `computed`, and `expectancy_R`/`avg_win_R`/`avg_loss_R` are then computed over ~1 row while every dollar metric uses all 200. `PAYOFF_IMBALANCE` (see C/B2) will switch its unit to `R` based on that 1-row statistic.

**Fix:** apply the same coverage floor (e.g. ≥80% non-null risk) to `computed`.

### B2 — MEDIUM — `computed` mode can never produce a MEDIUM `EDGE_BELOW_BREAKEVEN` — ✅ RESOLVED (Wave 0C)
`bazar_insights.py:160-165`

> **Resolution (2026-06-15).** Added a shared `_significance_series(df, mode)` helper that selects the test series by **data, not schema**: it uses the R series of the engine's mode (full OR computed, via `_r_series`) when it carries >10 real points, else falls back to dollar `pnl`. Both `_sig_edge` (this finding) and `_sig_sys` (the A4 guard, refactored to the same helper — single source of truth) now use it, so `computed`-mode and full-mode traders are judged identically. Verified: in computed mode with no `pnl_R` column, `_significance_series` returns the computed `pnl/risk` series (not the dollar fallback / not empty); full-vs-computed encodings of the same data yield identical systemic/edge verdicts.
>
> *Honest caveat:* this establishes parity and removes the schema gate, but it does **not** make the MEDIUM verdict common. The soft `EDGE_BELOW_BREAKEVEN` branch requires an edge that is simultaneously *small* (`exp_R > -0.10`) and *significant* (`z < -2`); standardized, that needs sample sizes in the thousands for **either** mode. So the MEDIUM path stays deliberately hard to reach — by design, not by bug.

```python
if exp_R is not None and 'pnl_R' in df.columns:   # requires the column, not just exp_R
    ...
    _sig_edge = (exp_R / _se) < -2.0
if not _sig_edge:
    return Insight(... LOW observation ...)
```

In `computed` mode `exp_R is not None` but there is **no `pnl_R` column**, so `_sig_edge` stays `False` and the function always emits the LOW observation — the significant MEDIUM branch is unreachable. Full-R and computed-R traders are judged by different rules for the same evidence.

**Fix:** compute `_sig_edge` from the R series via `_r_series(df, mode)` (the same source the metrics use), not from the raw column.

### B3 — LOW — Scale-dependent magic numbers — ✅ RESOLVED (Wave 0E)
`bazar_insights.py:280` (`worst["avg_pnl"] < -60` → HIGH session toxicity), `:532` (`dd_pct > 3`), `:542/545` (ratio 1.2 / 1.5).
The `-60` dollar cutoff is not scale-invariant: a trader running 10× the size trips HIGH on noise; a micro-lot trader never trips it.

> **Resolution (2026-06-15).** All severity thresholds are centralized in a constants block next to `ALPHA_FINDING`/`N_PERM` (`SESSION_TOXIC_HIGH_R`, `SESSION_TOXIC_HIGH_USD`, `DD_THRESHOLD_PCT`, `DD_OVERSIZE_RATIO_MIN`, `DD_OVERSIZE_RATIO_HIGH`, `POST_LOSS_FAST_GAP_MIN`). Session-toxicity HIGH now uses a **scale-invariant R cutoff** (`SESSION_TOXIC_HIGH_R = -0.50`, computed from the worst session's average R), falling back to the dollar cutoff only when R is unavailable. `-0.50R` was chosen to keep the HIGH bar as strict as the legacy `-$60` (≈ -0.5R at a typical 1R≈$120) rather than loosen it — confirmed via Monte Carlo (`high_only` returns to ≈baseline). Verified scale-invariant: the same R-structure at risk 100 vs 1000 ($-40 vs $-400, straddling the old $-60 line) yields the **same** MEDIUM verdict.

### B4 — note — `ALPHA_FINDING = 0.015`, `N_PERM = 300` — ✅ ADDRESSED (Wave 0I)
Min resolvable permutation p-value is `1/301 ≈ 0.0033`, comfortably below `0.015` — fine. But `test_monte_carlo_false_finding_rate_below_10pct` ran only **N=40** traders, a weak guarantee of the "<10% union FP" claim.

> **Resolution (2026-06-15).** Two-tier Monte Carlo validation (see `docs/validation.md`): a fast coarse tripwire in every `pytest` (N=100, ~4s) and an authoritative `@pytest.mark.release` gate at **N=1000** enforcing `med_high < 0.10 AND high_only < 0.10` (run via `pytest -m release` or `python tools/monte_carlo_validation.py 1000`, which self-asserts and exits non-zero on breach). The strict 10% bound is enforced at large N where it is statistically meaningful; the fast tier uses a coarse ceiling so it can't false-fail on small-N sampling noise. Last release run: med_high 0.058 / high_only 0.033. No engine thresholds changed.

---

## C. Formula correctness

### C1 — MEDIUM — `profit_factor` / `payoff_ratio` collapse to 0.0 with no losses — ✅ RESOLVED (Wave 0C)
`bazar_metrics.py:32, 36`

> **Resolution (2026-06-15).** A `_ratio_or_ceiling()` helper now returns a finite ceiling (`PROFIT_FACTOR_CEILING = PAYOFF_RATIO_CEILING = 100.0`) when there are no losses but positive profit — so a flawless sample ranks at the **top**, not at 0.0 (= worst). The all-losses / empty case still returns `0.0`. A `no_loss_trades` flag is exposed in `core_metrics` for transparency. The finite cap (vs `inf`) keeps the value JSON-serializable and display-safe and clamps cleanly through `compute_bazar_score`. Applied to the R payoff (`payoff_R`) too. Verified: all-wins sample → PF/payoff = 100.0 and `no_loss_trades=True`; all-losses → PF 0.0.

```python
payoff_ratio  = round(abs(avg_win / avg_loss), 3) if avg_loss != 0 else 0.0
profit_factor = round(gross_profit / gross_loss, 3) if gross_loss > 0 else 0.0
```

A trader with **zero losing trades** (the best possible outcome) gets `profit_factor = 0.0` and `payoff_ratio = 0.0` — numerically the *worst* score. This flows straight into the report's Bazar Score (`pf_score = (0/1.5)*40 = 0`, see D2) and any PF gating. Edge case, but it inverts the ranking exactly where it should be highest.

**Fix:** return a sentinel/`inf` or cap (e.g. report `>` a ceiling) when `gross_loss == 0` / `avg_loss == 0`, and handle that sentinel in the score.

### C2 — LOW — Scratch trades treated inconsistently — ✅ RESOLVED (Wave 0C)
`bazar_metrics.py:26-31`
`win_rate = (df['pnl'] > 0).mean()` counted `pnl == 0` rows in the denominator as non-wins, but `wins`/`losses` (and therefore `payoff_ratio`, `breakeven_wr`, `profit_factor`) excluded them entirely.

> **Resolution (2026-06-15).** `win_rate` is now computed over **decided** trades — `len(wins) / (len(wins) + len(losses))` — excluding scratches, putting it on the same basis as `breakeven_wr` (which is built from avg win/loss magnitudes and inherently ignores scratches). Expectancy still uses all trades. A `scratch_trades` count is exposed. Verified: 10 wins / 10 losses / 20 scratches → `win_rate = 0.5` (not the old `0.25`). Scratch-free datasets (incl. all samples + Monte Carlo) are unchanged.

### C3 — LOW — Rounded inputs reused in ratios — ✅ RESOLVED (Wave 0C)
`bazar_metrics.py:30-32, 56`
`avg_win`/`avg_loss` were rounded to 2 decimals, then `payoff_ratio` and `breakeven_wr` were computed from the rounded values.

> **Resolution (2026-06-15).** Ratios (`payoff_ratio`, `breakeven_wr`, `payoff_R`) are now computed from full-precision means; only the reported `avg_win_dollar`/`avg_loss_dollar` are rounded for display. Verified with a constructed case (avg_win 100.0049 / avg_loss 33.337) where full-precision payoff rounds to 3.000 but the rounded-input path gives 2.999 — the engine returns 3.000.

---

## D. Live vs backtest / report equivalence gaps

### D1 — HIGH — The downloadable report's equity curve is permanently dead — ✅ RESOLVED (Wave 0A)
`streamlit_app.py:1820-1828`

> **Resolution (2026-06-15).** The block now reads from the analyzed frame `df` directly (`result["pnl_series"] = df["pnl"].tolist()`, with `session`/`symbol` guarded), instead of the never-set `uploaded_df` session key and the undefined `beta_df` local that caused the swallowed `NameError`. Verified: `equity_curve_html` renders a non-empty `<polyline>` when the series is attached.

```python
try:
    _audit_df = st.session_state.get("uploaded_df") or beta_df
    if _audit_df is not None:
        result["pnl_series"] = _audit_df["pnl"].tolist()
        result["trade_meta"] = _audit_df[["session","symbol"]].to_dict(orient="records")
except Exception:
    pass
```

`uploaded_df` is **never** set in `st.session_state` anywhere in the file, and `beta_df` is **not a defined local** (the upload path uses `bdf` / `st.session_state["beta_df"]`, confirmed by grep). So `st.session_state.get("uploaded_df")` returns `None`, `None or beta_df` evaluates `beta_df` → **`NameError`**, which the bare `except` swallows. Result: `pnl_series`/`trade_meta` are *never* attached, and `equity_curve_html` always returns `""` (its `len(pnl_series) < 2` guard). Every report ships without an equity curve, for every dataset. (Secondary risk: had `uploaded_df` ever held a DataFrame, `X or beta_df` would raise "truth value of a DataFrame is ambiguous.")

**Fix:** use the actual analyzed frame, which is in scope as `df`:
```python
result["pnl_series"] = df["pnl"].tolist()
result["trade_meta"] = df[["session","symbol"]].to_dict(orient="records")
```
and stop catching `NameError` silently here.

### D2 — HIGH — Two divergent Bazar Score formulas; the documented one is dead — ✅ RESOLVED (Wave 0A)
`streamlit_app.py:696-733, 759-809` (defined, **never called** — confirmed by grep) vs `bazar_report_extras.py:15-61` (actually used by `bazar_score_html` → in the report).

> **Resolution (2026-06-15).** Single source of truth established: the duplicate `bazar_score()` in `bazar_report_extras.py` was deleted; `bazar_score_html()` now takes the score as a parameter; `build_report_html()` computes it once via the canonical `compute_bazar_score()` and passes it in. The report's score now matches the product's documented Edge/Consistency/Discipline/Data formula. Verified: no remaining references to the removed function; report renders the passed-in score. *(Still open separately: `compute_bazar_score`/`score_panel_html`/`journey_html`/`biggest_recoverable` remain defined-but-uncalled in the app UI — tracked under D5/dead-code cleanup, not this fix.)*

| | App's `compute_bazar_score` (dead) | `report_extras.bazar_score` (used in report) |
|---|---|---|
| Edge/PF | Edge 40 (expectancy_R −0.3..+0.3) | PF 40 (PF 0..1.5) |
| Consistency/WR | Consistency 20 (PF 0.8..1.5) | WR 25 (gap to breakeven ±0.20) |
| Discipline | 25, −10/HIGH, −5/MEDIUM | 20, −7/HIGH, −3/MEDIUM |
| Data/Cliff | Data 15 (n/300) | Cliff penalty 15 |

The user-facing caption text (`score_caption`: *"Edge 40 + Consistency 20 + Discipline 25 + Data 15. No black box."*) describes the **dead** formula. The score actually printed in the downloadable HTML uses the **other** formula. The app UI itself shows **no** score block at all (`score_panel_html`/`journey_html`/`compute_bazar_score`/`biggest_recoverable` are all unreferenced). Net: the product advertises a transparent formula it does not use, and the in-app experience and the report disagree.

**Fix:** pick one formula, delete the other, and make the caption match. Given the "transparent" marketing copy, keep `compute_bazar_score` (it's R/expectancy-based and documented) and route the report through it; remove `report_extras.bazar_score`.

### D3 — MEDIUM — Provided vs derived `trade_index_in_day` changes results — ✅ RESOLVED (Wave 0D)

> **Resolution (2026-06-15).** `insight_trade_count_cliff` now **always derives** `trade_index_in_day` from `open_time` (calendar-day `cumcount`), ignoring any supplied column, so the presence/format of an uploaded column can no longer change the result — identical trades give an identical cliff verdict (live == backtest). A `derived_trade_index` flag and a `trade_index_overrode_supplied` mismatch flag are recorded in the snapshot for transparency.
>
> **Discovery during the fix:** the GOOD/PROBLEM demo fixtures carried a supplied index **inconsistent with their own timestamps** (PROBLEM's first chronological trade carried index 5, which a per-day `cumcount` can never produce — it implies a non-midnight session boundary). That supplied index was the *sole* reason PROBLEM showed a `TRADE_COUNT_CLIFF`; under faithful derivation the cliff is correctly absent, and GOOD shows only a non-significant LOW *observation* (p≈0.20). Re-timestamping the fixtures to preserve the old cliff was rejected: it would require reordering rows, which desyncs the per-row `balance_before/after` columns and risks spurious drawdown/post-loss insights. Per the user decision, the always-derive fix was kept and `test_good_no_false_findings` / `test_problem_systemic_first_and_strong` were updated to encode the correct behavior (GOOD: no MEDIUM/HIGH findings, observations allowed; PROBLEM: real structural+behavioral findings required, cliff no longer required and capped at LOW if present).
>
> **Known limitation (not closed):** the day boundary is the calendar date of `open_time` in whatever timezone the data carries; a configurable broker/session rollover boundary is still not modeled.

#### Original finding
`bazar_insights.py:319-324`

```python
col = 'trade_index_in_day'
if col not in df.columns:
    df['_date'] = df['open_time'].dt.date
    df[col] = df.groupby('_date').cumcount() + 1
```

When the column is absent the engine derives it from the (open_time-sorted) data; when present it trusts it verbatim. Two otherwise-identical uploads — one carrying a precomputed `trade_index_in_day` (possibly computed under a different timezone, broker day boundary, or ordering) — produce **different** `TRADE_COUNT_CLIFF` outcomes. This is a live-vs-source-of-truth equivalence gap.

**Fix:** either always derive it (ignore the supplied column), or validate the supplied column against a derived one and warn on mismatch. Also note `.dt.date` is timezone-naive — define the trading-day boundary explicitly.

### D4 — LOW — Recoverable "confirmed" threshold ≠ engine finding threshold — ✅ RESOLVED (Wave 0E)
`bazar_report_extras.py:208` used `p_val < 0.05`; the engine promotes finding↔observation at `ALPHA_FINDING = 0.015`.

> **Resolution (2026-06-15).** `bazar_report_extras` now imports `ALPHA_FINDING` from `bazar_insights` (with a `0.015` fallback to stay importable standalone) and gates the "confirmed recoverable" split on `p_val < ALPHA_FINDING`. Behaviorally a no-op today (the `observation` flag already encoded the 0.015 gate), but the latent inconsistency is gone. Also removed the user-facing "(p<0.05)" claim from the confirmed-card note so the copy doesn't advertise a wrong threshold.

### D5 — LOW — Dead non-demo upload branch — ✅ RESOLVED (Wave 0E)
`streamlit_app.py:1747-1775`. `DEMO_MODE = True` is hardcoded, so the entire `else:` real-upload branch was unreachable.

> **Resolution (2026-06-15).** The stale `else:` branch held a legacy direct-upload flow that **predated the E1 StateStore and did not enforce the one-free-report quota** — leaving it (and risking it being re-enabled) was a latent entitlement-bypass. It is replaced with a fail-closed guard (`st.error(...) + st.stop()`) plus a comment directing any future non-demo upload to route through `get_store().has_used_free_report` / `mark_report_generated`. There is now a single, E1-gated upload path. *(The harmless sidebar `else` that merely lists columns is left as-is — it is display-only, not a second code path.)*

---

## E. Cold-start & state initialization

### E1 — HIGH — Quota / one-free-audit / token state is non-durable and race-prone — ✅ RESOLVED (Wave 0B)
`streamlit_app.py:1040-1054, 1241-1254, 1701-1724`

> **Resolution (2026-06-15).** Introduced a storage abstraction, **`bazar_state_store.py`**, with a stable interface (`request_code` / `verify_code` / `mark_report_generated` / `has_used_free_report` / `log_access_event`) and two backends:
> - **`SQLiteStateStore`** — local/dev. `sqlite3` transactions, WAL + busy-timeout, `UNIQUE(email_hash)`; conditional UPDATEs make single-use and one-report enforcement atomic. JSON is not the source of truth.
> - **`SupabaseStateStore`** — production/cloud (Postgres via supabase-py), keyed off `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`/`SUPABASE_ANON_KEY`. Migration at `db/migrations/0001_bazar_state.sql` (`UNIQUE(email_hash)`, indexes, atomic conditional UPDATE for the one-report rule). *(The migrations folder is intentionally `db/`, not `supabase/`: a top-level `supabase/` directory would shadow the installed `supabase` PyPI package because the app inserts its root onto `sys.path`.)*
>
> Backend chosen by `BAZAR_STATE_BACKEND` (default `sqlite`; production configured to `supabase`). **Fails closed**: `BAZAR_STATE_BACKEND=supabase` with missing secrets raises `StateStoreConfigError` and never silently falls back to local files.
>
> **Security properties now enforced:** raw access codes are never stored (peppered, email-bound SHA-256 `code_hash` only); codes are generated with `secrets`, expire after 30 min, and are single-use (`code_used_at`); raw email is never stored (only `email_hash`); one free report per email is enforced by an atomic conditional UPDATE. **Wave 0A E2 preserved** — the code is handed only to the e-mail layer and never displayed; no `st.code(access_code)` was reintroduced.
>
> **Streamlit integration:** the access gate (request → e-mail one-time code → verify → unlock), the upload quota, the security event log, and the admin log viewer now flow through the StateStore. The old JSON helpers remain defined but uncalled (read-only debug); legacy JSON files are not deleted and are no longer authoritative.
>
> **Verification:** 11 new tests in `tests/test_state_store.py` (request→verify→one report; second report blocked; code-reuse blocked; expired fails; wrong/unknown code fails; Supabase-missing-secrets fails closed; SQLite persists across new store instances on the same file; no JSON file required; only `request_code` exposes the raw code; re-issue invalidates the prior code; code stored hashed not raw). Full suite **19/19**; Monte Carlo false-finding rate unchanged at **5.67%**.
>
> **Scope/caveat:** the Supabase backend is implemented and unit-covered at the config/fail-closed boundary, but its live Postgres round-trip was **not** executed in this environment (no Supabase project wired). Before enabling external paid beta, run the migration and smoke-test the Supabase path end-to-end against a real project. The original finding text below is retained for history.

`beta_usage.json`, `code_assignments.json`, and `access_log.json` are read/written with plain `open()` + `json.dump`, no file locking. Two issues:
1. **Cold start / ephemeral FS** — the code itself notes (`:1254`) that Streamlit Cloud's filesystem is temporary. On every container restart the quota/usage/activation maps reset to `{}`, so "one free audit per email" and the 24h one-time-token rules **reset for free** (quota bypass).
2. **Concurrency** — `load → mutate → save` is not atomic. Two simultaneous uploads both read the old `upload_count`, both write `+1`, and one increment (and possibly one user's `emails` entry) is lost. Same hazard on `access_log.json` and `code_assignments.json` (token activation timestamps).

**Fix:** move quota/token/assignment state to a real datastore (SQLite with a transaction, or a hosted DB) with atomic compare-and-set; treat the JSON files as cache only. At minimum, document that the limits are advisory in the current build.

### E2 — MEDIUM — Access code printed on screen when SMTP is unconfigured — ✅ RESOLVED (Wave 0A)
`streamlit_app.py:1058-1071, 1559-1566`

> **Resolution (2026-06-15).** On email-send failure the code is no longer displayed: the `st.code(assigned)` fallback was replaced with a `st.error(tx["req_send_failed"])` "contact support" message (new key added to en/fa/ar) plus a `log_access("code_send_failed", ...)` entry. The one-time, email-bound token is never revealed in the browser.

The comment at `:1558` states *"code is not shown on screen — only emailed."* But `_send_access_code_email` returns `False` whenever `SMTP_HOST/USER/PASS` secrets are missing (`:1070`), and the fallback then does `st.code(assigned)` (`:1565`) — displaying the code in the browser. In any deployment without SMTP secrets, the "one-time email-bound token" is handed out in plaintext on the page, defeating the email-binding control.

**Fix:** if email delivery fails, do **not** reveal the code; show "could not send — contact support" and log it. Reserve on-screen display for an explicit admin/dev flag.

### E3 — LOW — Drawdown peak init & dropped recovery trade — ✅ RESOLVED (Wave 0E)
`bazar_insights.py:526, 529-536`

The old `in_dd` state machine appended the first trade to recover above the 3% threshold to **neither** bucket — silently dropping it — and the peak update was tangled with that flag.

> **Resolution (2026-06-15).** Extracted a `_drawdown_buckets(balance, lots, threshold_pct)` helper that keeps a **running high-water mark from the first row** and classifies **every** trade into exactly one bucket by its decision-time drawdown depth — the `in_dd` state machine (and its dropped recovery trade) is gone. Thresholds come from the centralized constants (B3). Verified: `len(normal) + len(dd) == n` (nothing dropped); the recovery trade lands in `normal`; an early dip registers as drawdown against the running peak.

### E4 — positive note — sample-size cold-start guard is correct
`bazar_audit_engine.py:87-92` / `bazar_insights.py:114-136`. `n < 30` short-circuits the whole pipeline with a single clear insight, and `n < 100` downgrades confidence. This is the right cold-start behavior and should be preserved.

---

## Cross-cutting recommendations

1. **Decision-time vs outcome-time discipline.** A1, A2, and E3 are the same root cause: judging a trade with information that only exists after it resolved. Audit every insight for "would this field have been knowable when the decision was made?" Prefer `balance_before`, `initial_risk_amount`, and entry-time features. *(✅ Done 2026-06-15: A1 uses `balance_before` (0A); A2 uses the non-post-loss complement (0A); E3 classifies by decision-time drawdown via `_drawdown_buckets` (0E); A7 uses the last *completed* prior trade by close_time (0E).)*
2. **Test/statistic ↔ display alignment.** A3, A5, A6: the entity/number shown to the user should be exactly the one the p-value validates. *(✅ Done 2026-06-15: A3 reports the worst-by-mean segment the test uses (0B); A5 shows pooled win rates (0B); A6 reports the argmax-drop split the cliff p-value tests (0D).)*
3. **One score, one formula, one caption.** Resolve D2 before any external launch; the current state is a transparency/trust liability given the "no black box" copy.
4. **Single source of truth for thresholds.** Hoist `0.015`, `0.05`, `-60`, `3`, `0.8`, `>0`, score weights into one config block so full/computed modes and app/report can't drift (B1, B2, B3, D4). *(✅ Done 2026-06-15: B1+B2 share `R_COVERAGE_MIN` and one `_significance_series` helper (0C); B3 hoisted all severity thresholds into a constants block with a scale-invariant R cutoff (0E); D4 shares the engine's `ALPHA_FINDING` (0E). Bazar Score weights still live in `compute_bazar_score` — acceptable, single definition since D2.)*
5. **State durability.** ✅ Addressed (2026-06-15, see E1 resolution): durable StateStore with SQLite (dev) / Supabase (prod) backends, atomic one-report enforcement, fail-closed config. Remaining gate before external paid beta: run the Supabase migration and smoke-test the live Postgres path end-to-end.

## Suggested test additions (none currently cover the above)
- All-NaN `pnl_R` column → `SYSTEMIC_UNDERPERFORMANCE` must still be significance-gated (A4).
- No-loss trader → `profit_factor`/score must not be 0/worst (C1).
- Drawdown sizing computed from `balance_before`; an oversized *loser* must not by itself create the finding (A1).
- Post-loss decay with reference = non-post-loss trades; verify a known injected effect's magnitude (A2).
- Report build attaches a non-empty `pnl_series` and renders an equity curve (D1).
- App score == report score for the same `result` (D2).
