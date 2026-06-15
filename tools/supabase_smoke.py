"""
tools/supabase_smoke.py — headless end-to-end smoke test for the durable
StateStore (audit E1), intended for the LIVE Supabase backend.

It plays the role of the app + e-mail layer and exercises steps 5–13 of the
E1 acceptance checklist against a real backend, WITHOUT the Streamlit UI:

  5) request_code (new email)        -> a code is issued
  6) verify_code                     -> ok
  7) unlock gate                     -> has_used_free_report == False
  8) mark_report_generated           -> ok
  9) read back the row               -> report_generated / report_generated_at set
 10) second mark, same email         -> already_used (blocked)
 11/12) fresh store instance         -> still blocked (durable across "restart")
 13) wrong / unknown / expired / reused codes all fail

It reads the SAME configuration the app uses (env vars first, then
.streamlit/secrets.toml): BAZAR_STATE_BACKEND, SUPABASE_URL, and
SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY.

Privacy: a unique throwaway email is used per run; the raw one-time code is
received internally (like the e-mail layer) and never printed. By default the
test rows are deleted at the end (--keep to retain them for dashboard
inspection of step 9).

Usage:
    # against live Supabase (reads secrets.toml / env):
    python tools/supabase_smoke.py
    # keep the test rows so you can inspect report_generated_at in the dashboard:
    python tools/supabase_smoke.py --keep
    # dry-run the script logic on the local SQLite backend (NOT the prod path):
    python tools/supabase_smoke.py --backend sqlite

Exit code 0 = all checks passed, 1 = a check failed, 2 = misconfigured/fail-closed.
"""
import argparse
import os
import secrets
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_state_store import (  # noqa: E402
    get_state_store, email_hash, StateStoreConfigError,
    SQLiteStateStore, SupabaseStateStore,
)

_SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")
_secrets_cache = None


def _load_secrets_file() -> dict:
    global _secrets_cache
    if _secrets_cache is not None:
        return _secrets_cache
    data = {}
    try:
        import tomllib  # Python 3.11+
        with open(_SECRETS_PATH, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        data = {}
    _secrets_cache = data
    return data


def cfg(name: str, default=None):
    """env var first, then .streamlit/secrets.toml, then default."""
    if os.getenv(name) is not None:
        return os.getenv(name)
    val = _load_secrets_file().get(name)
    return str(val) if val is not None else default


# ── tiny check harness ────────────────────────────────────────────────────────
_failures = 0


def check(label, ok, extra=""):
    global _failures
    tag = "PASS" if ok else "FAIL"
    if not ok:
        _failures += 1
    print(f"  [{tag}] {label}{(' — ' + extra) if extra else ''}")
    return ok


def _build(backend, ttl=None):
    return get_state_store(
        backend=backend,
        sqlite_path=cfg("BAZAR_SQLITE_PATH"),
        supabase_url=cfg("SUPABASE_URL"),
        supabase_key=cfg("SUPABASE_SERVICE_ROLE_KEY") or cfg("SUPABASE_ANON_KEY"),
        code_ttl_minutes=ttl,
    )


def _cleanup(store, *emails):
    """Delete only the throwaway test rows this run created."""
    hashes = [email_hash(e) for e in emails]
    try:
        if isinstance(store, SupabaseStateStore):
            c = store._client
            for eh in hashes:
                c.table("entitlements").delete().eq("email_hash", eh).execute()
                c.table("access_events").delete().eq("email_hash", eh).execute()
        elif isinstance(store, SQLiteStateStore):
            with store._connect() as conn:
                for eh in hashes:
                    conn.execute("DELETE FROM entitlements WHERE email_hash=?", (eh,))
                    conn.execute("DELETE FROM access_events WHERE email_hash=?", (eh,))
        return True
    except Exception as e:
        print(f"  [WARN] cleanup failed (test rows may remain): {e}")
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Headless E1 StateStore smoke test (Supabase by default).")
    p.add_argument("--backend", default=None,
                   help="override backend (default: BAZAR_STATE_BACKEND or 'supabase')")
    p.add_argument("--keep", action="store_true",
                   help="keep test rows for manual dashboard inspection (step 9)")
    p.add_argument("--email", default=None, help="override the throwaway test email")
    args = p.parse_args(argv)

    backend = (args.backend or cfg("BAZAR_STATE_BACKEND") or "supabase").strip().lower()
    print(f"== Bazar StateStore smoke test — backend={backend} ==")
    if backend != "supabase":
        print("  [INFO] NOT testing the production Supabase path — this is a logic dry-run only.\n")

    # build store (fail closed on misconfig)
    try:
        store = _build(backend)
    except StateStoreConfigError as e:
        print(f"  [FAIL] could not build store (fail-closed): {e}")
        return 2
    except Exception as e:
        print(f"  [FAIL] could not build store: {e}")
        return 2

    rnd = secrets.token_hex(4)
    email = args.email or f"smoke+{rnd}@bazar-smoke.invalid"
    bad_email = f"never-requested+{rnd}@bazar-smoke.invalid"
    exp_email = f"expired+{rnd}@bazar-smoke.invalid"
    print(f"  [INFO] test email (throwaway): {email}\n")

    try:
        # 5) request
        r = store.request_code(email, ip_hash="smoke", user_agent_hash="smoke")
        code = r.get("code")
        check("5  request_code issues a code", bool(code) and r.get("status") == "ok")
        check("5b raw code is NOT echoed back by any later call (only request_code)",
              "code" in r)

        # 6) verify
        check("6  verify_code -> ok", store.verify_code(email, code).get("status") == "ok")

        # 7) gate open (not yet used)
        check("7  has_used_free_report == False before report", store.has_used_free_report(email) is False)

        # 8) mark report
        m1 = store.mark_report_generated(email)
        check("8  mark_report_generated -> ok", m1.get("status") == "ok")
        check("8b mark result does not leak a raw code", "code" not in m1)

        # 9) read back row
        check("9  has_used_free_report == True after report", store.has_used_free_report(email) is True)
        row = _read_row(store, email)
        check("9b report_generated flag set", bool(row and row.get("report_generated")))
        check("9c report_generated_at set", bool(row and row.get("report_generated_at")),
              extra=str(row.get("report_generated_at")) if row else "")
        check("9d code_used_at set (single-use consumed)", bool(row and row.get("code_used_at")))

        # 10) second attempt blocked
        check("10 second mark same email -> already_used",
              store.mark_report_generated(email).get("status") == "already_used")

        # 11/12) durable across a fresh store instance ("restart")
        store2 = _build(backend)
        check("11/12 fresh store instance still blocked",
              store2.has_used_free_report(email) is True
              and store2.mark_report_generated(email).get("status") == "already_used")

        # 13) wrong / unknown / expired / reused
        check("13a unknown email -> not_found",
              store.verify_code(bad_email, "ZZZZZZZZ").get("status") == "not_found")
        store.request_code(bad_email)
        check("13b wrong code -> mismatch",
              store.verify_code(bad_email, "ZZZZZZZZ").get("status") == "mismatch")

        # expired: a store with a negative TTL issues an already-expired code (no waiting)
        store_exp = _build(backend, ttl=-1)
        ecode = store_exp.request_code(exp_email).get("code")
        check("13c expired code -> expired",
              store_exp.verify_code(exp_email, ecode).get("status") == "expired")

        # reused: verify twice
        reuse_email = f"reuse+{rnd}@bazar-smoke.invalid"
        rcode = store.request_code(reuse_email).get("code")
        first = store.verify_code(reuse_email, rcode).get("status")
        second = store.verify_code(reuse_email, rcode).get("status")
        check("13d reused code: first ok, second used", first == "ok" and second == "used",
              extra=f"{first}/{second}")

    finally:
        if not args.keep:
            _cleanup(store, email, bad_email, exp_email, f"reuse+{rnd}@bazar-smoke.invalid")
            print("\n  [INFO] test rows cleaned up (use --keep to retain for dashboard inspection).")
        else:
            print(f"\n  [INFO] --keep set; inspect rows in your dashboard. email_hash(report)={email_hash(email)}")

    print()
    if _failures == 0:
        print(f"RESULT: all checks passed ✅  (backend={backend})")
        return 0
    print(f"RESULT: {_failures} check(s) FAILED ❌  (backend={backend})")
    return 1


def _read_row(store, email):
    """Backend-agnostic read of the entitlement row (for step 9 confirmation)."""
    eh = email_hash(email)
    try:
        if isinstance(store, SupabaseStateStore):
            res = (store._client.table("entitlements")
                   .select("report_generated, report_generated_at, code_used_at, email_verified")
                   .eq("email_hash", eh).limit(1).execute())
            return res.data[0] if res.data else None
        if isinstance(store, SQLiteStateStore):
            with store._connect() as conn:
                r = conn.execute(
                    "SELECT report_generated, report_generated_at, code_used_at, email_verified "
                    "FROM entitlements WHERE email_hash=?", (eh,)).fetchone()
                return dict(r) if r else None
    except Exception as e:
        print(f"  [WARN] could not read row back: {e}")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
