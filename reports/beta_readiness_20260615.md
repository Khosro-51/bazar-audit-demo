# Bazar Audit — Limited External Beta Readiness

**Date:** 2026-06-15
**Author:** structural audit / readiness review (Prompt 5)
**Product framing:** Bazar is a **statement-first strategy audit engine** — it analyzes a trader's *past* trades. It is **not** a signal service: no live market data, no buy/sell calls, no price targets, no financial advice.

---

## Verdict (go / no-go)

| Beta type | Verdict | Why |
|-----------|---------|-----|
| **Internal only** (you + trusted testers) | **🟢 GO** — with conditions | Engine/report/safety are verified. Quota durability is fine to accept loosely for trusted internal users. |
| **Limited external FREE beta** | **🔴 NO-GO (yet)** | Two operational blockers (B1, B2) — the *engine* is ready, the *durable access path* is not yet proven live. |
| **Paid beta** | **🔴 NO-GO** | Same blockers, higher bar. Do not enable or advertise paid access. |

**One-line:** the analytical engine, report layer, and product-safety posture are **launch-ready and fully test-covered**; what's *not* cleared is the **live state/access backend** (durable one-free-report enforcement on Streamlit Cloud), which has only ever run fail-closed in this environment. Clear B1+B2 below and limited external free beta becomes GO.

---

## Blockers (must clear before any *external* beta)

- **B1 — Live Supabase state path unverified.** `tools/supabase_smoke.py` has only run **fail-closed (exit 2)** — no Supabase project is wired. On Streamlit Cloud the SQLite backend is **ephemeral** (resets on restart) → the one-free-report quota would silently reset → free-report bypass. Durable enforcement *requires* the Supabase backend, which is not yet proven against a real database. **External beta on Streamlit Cloud MUST use `BAZAR_STATE_BACKEND=supabase`.**
- **B2 — Streamlit Cloud end-to-end UI flow not executed.** The request→verify→upload→report→second-attempt-block→restart-persistence path has not been run against the live UI + Supabase (Prompt 2). The `StateStore` beneath it is unit-tested; the wiring is not.

---

## Checklist by area

Legend: ✅ verified · ☐ manual pre-launch check · ⚠️ warning (non-blocking)

### 1. Access control
- ✅ Durable `StateStore` is the single source of truth; local JSON is not authoritative (E1; legacy JSON helpers deleted in RA-3).
- ✅ One-time, email-bound, hashed, 30-min, single-use codes; one free report per email enforced by an atomic conditional UPDATE (`mark_report_generated`). 13 state tests pass.
- ✅ Fails closed: `BAZAR_STATE_BACKEND=supabase` with missing secrets raises and stops — never falls back to local files (verified, exit 2).
- ✅ No access code is ever shown on screen (E2); on email-send failure the user gets "contact support", not the code.
- ✅ Supabase `request_code` is a single atomic upsert (RA-5).
- ☐ **B1/B2** — live Supabase smoke + live UI flow (see Blockers).
- ⚠️ The Streamlit gate flow has no automated test (NOTE-2) — covered only by the StateStore tests + the manual smoke. Treat the manual UI run as mandatory.

### 2. Engine integrity
- ✅ All original audit findings (0A–0E, 21 items) and all re-audit findings (RA-1…RA-7) resolved; B4 addressed (0I).
- ✅ No outcome leakage (decision-time fields: `balance_before`, non-post-loss complement, completed-prior-by-close).
- ✅ Every behavioral finding is statistically gated (permutation / two-proportion / z); drawdown is now gated too (RA-1).
- ✅ Single decided-basis win rate engine-wide (RA-2); deterministic indexing (D3 + stable sort, RA-7).
- ✅ Fast tests **43/43 pass**; **release Monte Carlo gate (N=1000) PASS** — med_high 0.058, high_only 0.033 (both < 10%).
- ☐ Run `pytest -m release` (or `python tools/monte_carlo_validation.py 1000`) on the deploy commit as a pre-launch gate (see `docs/validation.md`).

### 3. Report integrity
- ✅ Single Bazar Score formula feeds the downloadable report (D2); equity curve attaches from the analyzed frame (D1).
- ✅ Source banner correctly distinguishes uploaded file vs demo profile.
- ✅ Finding vs Observation language is honest (LOW observations are not firm claims); Recoverable (confirmed, p<ALPHA) vs Watchlist (unconfirmed) split is correct and shares the engine alpha (D4).
- ✅ "Recoverable" is labeled retrospective, not a promise.
- ☐ Manually download one report per profile and eyeball: score, equity curve renders, no raw JSON for non-admin.

### 4. Product safety
- ✅ No buy/sell, long/short, entry-signal, or price-target language anywhere in the engine (grep-verified); `recommended_action`s are behavioral/risk only (cooldowns, per-day caps, session avoidance, exit review, consistent sizing).
- ✅ Disclaimer present in en/fa/ar; "not financial advice / no signals" stated.
- ✅ No live market data; no price-specific guidance.
- ☐ Confirm the disclaimer is visible on the landing/gate screen and in the downloaded report (it is in code — verify rendered).

### 5. Operations
- ✅ Supabase migration exists: `db/migrations/0001_bazar_state.sql` (UNIQUE email_hash, indexes).
- ✅ Validation policy documented: `docs/validation.md`.
- ☐ Apply the migration to the Supabase project.
- ☐ Configure secrets: `BAZAR_STATE_BACKEND=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and `SMTP_*` (email delivery is **required** — without it codes can't be sent and, by design, are not shown, so users can't unlock).
- ⚠️ **No `README_DEPLOY.md` / rollback runbook exists.** Add one before external beta (a rollback plan is sketched below).
- ☐ Define a support contact (email) surfaced to testers.

### 6. Beta scope (recommended)
- Limited external **free** beta only; **one report per verified email**.
- File: CSV with required columns `trade_id, open_time, close_time, symbol, side, pnl, session`; recommend `pnl_R`/`initial_risk_amount` and `balance_before`/`lot_or_size` for full insights; 5 MB cap.
- Suggested cohort: a small, named tester list you can email-support directly.
- Collect: did the flow work, was the report understandable, any wording that felt like advice/over-claim, any crashes.

---

## Required manual checks before flipping external beta ON
1. Apply `db/migrations/0001_bazar_state.sql` to Supabase.
2. Set `BAZAR_STATE_BACKEND=supabase` + `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `SMTP_*` in Streamlit Cloud secrets.
3. `python tools/supabase_smoke.py --keep` → **exit 0**; confirm in Supabase: `report_generated_at`/`code_used_at` set, second attempt blocked, reused/wrong/expired codes fail.
4. Live UI flow (Prompt 2): new email → code arrives by email → verify → upload sample CSV → report → second different upload blocked → **reboot the app** → same email still blocked.
5. `pytest` (fast) and `pytest -m release` (N=1000 gate) → all pass.
6. Confirm no code on screen; confirm app fails closed if Supabase secrets are removed.

Only when 1–6 pass: **limited external free beta = GO.**

---

## Rollback plan
- **App:** redeploy the previous known-good commit on Streamlit Cloud (or take the app private). To *pause* signups without a code change, removing/clearing `SMTP_*` makes code delivery fail → users see "contact support" (no bypass, no code leak) → effectively pauses new unlocks.
- **Data:** the `entitlements` table in Supabase is the source of truth and persists across app rollbacks, so re-enabling is safe. Export/snapshot `entitlements` before any schema change. Reverting the app does **not** lose entitlement state.
- **Backend:** if the Supabase path misbehaves, the engine still **fails closed** (no silent local-JSON fallback) — the app refuses access rather than serving ungated.

---

## What NOT to promise (tester comms guardrails)
- ❌ No profit, performance-improvement, or "recover $X" promises. The "recoverable" figure is an explicitly-labeled **historical** counterfactual, not a forecast.
- ❌ Not financial advice; no buy/sell signals; no price targets.
- ❌ Findings are **statistical observations on past trades**, not predictions of future results.
- ❌ Free tier = **one report per email** — don't imply unlimited.
- ❌ Don't promise long-term storage/retention of uploaded files (demo states files aren't stored); keep messaging consistent.

---

## Bottom line
- **Allowed now:** internal beta with trusted testers (accepting that quota is only loosely enforced until Supabase is live).
- **Not yet allowed:** limited external free beta — clear **B1** (live Supabase smoke) and **B2** (live UI flow), plus the manual checks above.
- **Blocked:** paid beta.

No code was changed by this review.
