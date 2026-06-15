# Bazar Audit — Statistical Validation Policy

The engine's core promise is **statistical honesty**: a zero-edge, zero-behavior
trader (pure noise) must not be handed MEDIUM/HIGH "findings" more often than the
nominal false-positive rate. Every behavioral finding is gated by a permutation,
two-proportion, or z-test at `ALPHA_FINDING = 0.015`; the union false-positive rate
across all gates must stay **under 10%**.

This is validated by Monte Carlo: generate many random traders (no edge, sizes and
sessions independent of outcome) and measure how often the engine flags them.

## Two tiers

| Tier | What | N | Criterion | When |
|------|------|---|-----------|------|
| **Fast** | `tests/test_all.py::test_monte_carlo_false_finding_rate_fast` | 100 | `med_high < 0.20` and `high_only < 0.15` (**coarse tripwire**) | every `pytest` (~4s) |
| **Release** | `tests/test_all.py::test_monte_carlo_false_finding_rate_release` (marked `release`) | 1000 | `med_high < 0.10` **and** `high_only < 0.10` (**authoritative gate**) | before deploy |

Both tiers share one implementation: `tools/monte_carlo_validation.false_finding_rates()`.

### Why the fast tier is coarse, not 10%
At N=100 the true rate (~5–6%) has seed-dependent sampling noise up to ~12%, so a
strict 10% assertion would **false-fail on noise** (e.g. seed 2026 → 11.3% at N=150).
A coarse ceiling (20% / 15%) won't trip on noise but still catches *gross* regressions
(a significance gate removed → rate jumps to 30%+). The strict 10% bound is only
statistically meaningful at large N, so it lives in the release tier, where at N=1000
the estimate is tight (±~0.7%) and reliably clears 10%.

## Commands

```bash
# Fast tier — runs automatically; the release tier is deselected by default (pytest.ini)
pytest

# Release gate (run before any deploy / before widening beta access)
pytest -m release                      # the N=1000 marked test
python tools/monte_carlo_validation.py 1000   # same gate as a standalone CLI; exits 1 on breach
```

The standalone tool prints the rates + per-insight counts and a final
`GATE: ... -> PASS/FAIL` line, exiting non-zero if either ceiling is breached — so it
can be wired directly into CI / a pre-deploy step.

## Pass criteria (release gate)
- `false_positive_rate_med_high < 0.10`
- `false_positive_rate_high_only < 0.10`

Last recorded release run (N=1000, seed=42): **med_high 0.058, high_only 0.033 → PASS.**

## If the gate fails
Do **not** loosen the criterion. A breach means a finding is firing on noise — find
which insight (the `insight_id_counts` in the output points to it) and restore/strengthen
its statistical gate. Engine thresholds (`ALPHA_FINDING`, severity cutoffs) should only
change if validation proves a problem, never to make this gate pass.
