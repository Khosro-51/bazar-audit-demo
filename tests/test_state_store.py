"""
E1 closure tests — durable entitlement/state storage (bazar_state_store).

Covers the acceptance checklist from the E1 work order:
  1. request -> verify -> one report succeeds
  2. second free report is blocked once report_generated is set
  3. a code cannot be reused after a successful verify
  4. an expired code fails
  5. a wrong code fails
  6. BAZAR_STATE_BACKEND=supabase with missing secrets fails closed
  7. SQLite state persists across a NEW store instance on the same db file
  8. no local JSON file is required for quota/token behavior
  9. raw code is only ever returned by request_code (the e-mail layer), never by
     the verify / report / quota methods
"""
import os
import sys

import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from bazar_state_store import (
    get_state_store, SQLiteStateStore, SupabaseStateStore, StateStoreConfigError,
    email_hash, hash_code,
)

EMAIL = "Trader@Example.com"
OTHER = "someone-else@example.com"


def _store(tmp_path, ttl=30):
    return get_state_store(backend="sqlite",
                           sqlite_path=str(tmp_path / "state.db"),
                           code_ttl_minutes=ttl)


# 1 + happy path -------------------------------------------------------------
def test_request_verify_one_report(tmp_path):
    s = _store(tmp_path)
    res = s.request_code(EMAIL, ip_hash="iphash", user_agent_hash="uahash")
    assert res["status"] == "ok" and res["code"]
    assert s.verify_code(EMAIL, res["code"])["status"] == "ok"
    assert s.has_used_free_report(EMAIL) is False
    assert s.mark_report_generated(EMAIL)["status"] == "ok"
    assert s.has_used_free_report(EMAIL) is True


# 2 -------------------------------------------------------------------------
def test_second_free_report_blocked(tmp_path):
    s = _store(tmp_path)
    code = s.request_code(EMAIL)["code"]
    s.verify_code(EMAIL, code)
    assert s.mark_report_generated(EMAIL)["status"] == "ok"
    second = s.mark_report_generated(EMAIL)
    assert second["status"] == "already_used"
    assert s.has_used_free_report(EMAIL) is True


# 3 -------------------------------------------------------------------------
def test_code_cannot_be_reused(tmp_path):
    s = _store(tmp_path)
    code = s.request_code(EMAIL)["code"]
    assert s.verify_code(EMAIL, code)["status"] == "ok"
    # same code again must fail as already used
    assert s.verify_code(EMAIL, code)["status"] == "used"


# 4 -------------------------------------------------------------------------
def test_expired_code_fails(tmp_path):
    s = _store(tmp_path, ttl=-1)  # issued already-expired
    code = s.request_code(EMAIL)["code"]
    assert s.verify_code(EMAIL, code)["status"] == "expired"


# 5 -------------------------------------------------------------------------
def test_wrong_code_fails(tmp_path):
    s = _store(tmp_path)
    s.request_code(EMAIL)
    assert s.verify_code(EMAIL, "WRONGCODE")["status"] == "mismatch"
    # an email that never requested a code
    assert s.verify_code(OTHER, "ANYCODE")["status"] == "not_found"


# 6 -------------------------------------------------------------------------
def test_supabase_missing_secrets_fails_closed(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BAZAR_STATE_BACKEND", "supabase")
    with pytest.raises(StateStoreConfigError):
        get_state_store()  # must NOT silently fall back to sqlite/json
    # explicit args missing too
    with pytest.raises(StateStoreConfigError):
        get_state_store(backend="supabase", supabase_url=None, supabase_key=None)


# 7 -------------------------------------------------------------------------
def test_sqlite_persists_across_instances(tmp_path):
    db = str(tmp_path / "persist.db")
    s1 = get_state_store(backend="sqlite", sqlite_path=db)
    code = s1.request_code(EMAIL)["code"]
    s1.verify_code(EMAIL, code)
    s1.mark_report_generated(EMAIL)
    del s1
    # brand new instance, same file -> state survives
    s2 = get_state_store(backend="sqlite", sqlite_path=db)
    assert s2.has_used_free_report(EMAIL) is True
    assert s2.mark_report_generated(EMAIL)["status"] == "already_used"


# 8 -------------------------------------------------------------------------
def test_no_json_files_required(tmp_path):
    s = _store(tmp_path)
    code = s.request_code(EMAIL)["code"]
    s.verify_code(EMAIL, code)
    s.mark_report_generated(EMAIL)
    s.log_access_event(email_hash(EMAIL), "unit_test", {"k": "v"})
    files = os.listdir(tmp_path)
    assert any(f.endswith(".db") for f in files), files
    # the legacy JSON entitlement files must NOT be needed/created by the store
    for legacy in ("beta_usage.json", "code_assignments.json", "access_log.json"):
        assert legacy not in files


# 9 -------------------------------------------------------------------------
def test_only_request_code_exposes_raw_code(tmp_path):
    s = _store(tmp_path)
    req = s.request_code(EMAIL)
    assert "code" in req  # request_code hands the raw code to the e-mail layer
    ver = s.verify_code(EMAIL, req["code"])
    mark = s.mark_report_generated(EMAIL)
    # no other method leaks the raw code back to the caller / UI
    assert "code" not in ver
    assert "code" not in mark
    assert isinstance(s.has_used_free_report(EMAIL), bool)


# bonus: re-issuing a code invalidates the previous one (no duplicate rows) ---
def test_reissue_invalidates_previous_code(tmp_path):
    s = _store(tmp_path)
    first = s.request_code(EMAIL)["code"]
    second = s.request_code(EMAIL)["code"]
    # old code no longer verifies; the freshly issued one does
    assert s.verify_code(EMAIL, first)["status"] == "mismatch"
    assert s.verify_code(EMAIL, second)["status"] == "ok"
    # exactly one entitlement row for this email
    with SQLiteStateStore(str(tmp_path / "state.db"))._connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM entitlements WHERE email_hash=?",
                         (email_hash(EMAIL),)).fetchone()["c"]
    assert n == 1


# RA-5 (Wave 0G): Supabase request_code is a single atomic upsert -----------------
class _FakeResp:
    def __init__(self, data): self.data = data
    def execute(self): return self


class _FakeTable:
    """Minimal recording fake of the supabase query builder for request_code."""
    def __init__(self, store, name): self.store = store; self.name = name
    def upsert(self, payload, on_conflict=None, **kw):
        self.store.calls.append(("upsert", self.name, on_conflict))
        eh = payload.get("email_hash")
        row = self.store.rows.get(eh, {"report_generated": False})
        row.update(payload)
        self.store.rows[eh] = row
        return _FakeResp([dict(row)])
    def insert(self, *a, **k):
        self.store.calls.append(("insert", self.name, None)); return _FakeResp([])
    def select(self, *a, **k):
        self.store.calls.append(("select", self.name, None)); return self
    def eq(self, *a, **k): return self
    def limit(self, *a, **k): return self


class _FakeClient:
    def __init__(self): self.calls = []; self.rows = {}
    def table(self, name): return _FakeTable(self, name)


def test_ra5_request_code_single_atomic_upsert():
    fake = _FakeClient()
    store = SupabaseStateStore("", "", client=fake)   # client injection (no real Supabase)
    res = store.request_code("a@b.com", ip_hash="iph", user_agent_hash="uah")
    assert res["status"] == "ok" and res["code"]
    upserts = [c for c in fake.calls if c[0] == "upsert"]
    # exactly ONE upsert, with on_conflict on email_hash — and NO select-then-insert race
    assert len(upserts) == 1
    assert upserts[0][2] == "email_hash"
    assert not any(c[0] in ("insert", "select") for c in fake.calls)


def test_ra5_request_code_preserves_report_generated_on_reissue():
    fake = _FakeClient()
    store = SupabaseStateStore("", "", client=fake)
    eh = email_hash("a@b.com")
    fake.rows[eh] = {"email_hash": eh, "report_generated": True}   # already used a report
    res = store.request_code("a@b.com")                            # re-issue a code
    assert res["already_used_free_report"] is True                 # not reset by re-issue
    assert "report_generated" not in {}  # sanity
    assert fake.rows[eh]["report_generated"] is True               # upsert didn't clobber it
    assert fake.rows[eh]["code_used_at"] is None                   # new code is usable


# raw code is never the stored hash --------------------------------------------
def test_code_is_hashed_not_stored_raw(tmp_path):
    s = _store(tmp_path)
    code = s.request_code(EMAIL)["code"]
    with SQLiteStateStore(str(tmp_path / "state.db"))._connect() as conn:
        row = conn.execute("SELECT code_hash FROM entitlements WHERE email_hash=?",
                           (email_hash(EMAIL),)).fetchone()
    assert row["code_hash"] and row["code_hash"] != code
    assert row["code_hash"] == hash_code(email_hash(EMAIL), code)
