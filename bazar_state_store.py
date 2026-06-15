"""
bazar_state_store.py — durable entitlement/state storage for Bazar Audit (audit E1).

Source of truth for:
  * one-time access codes (email-bound, hashed, expiring, single-use)
  * one-free-report-per-email enforcement
  * an append-only access-event log

This replaces the old local-JSON files (beta_usage.json / code_assignments.json
/ access_log.json), which were non-durable, unlocked, race-prone and reset on
Streamlit Cloud restarts (audit finding E1).

Backends
--------
  * SQLiteStateStore   — local/dev only. sqlite3 transactions + UNIQUE(email_hash).
  * SupabaseStateStore — production/cloud. Postgres via supabase-py.

Backend is selected by the BAZAR_STATE_BACKEND env/secret ("sqlite" | "supabase");
default "sqlite". If backend == "supabase" and the Supabase URL/key are missing,
the factory FAILS CLOSED (raises StateStoreConfigError) — it never silently falls
back to local files.

Security
--------
  * Raw access codes are NEVER persisted — only a peppered SHA-256 ``code_hash``.
  * Codes are generated with the ``secrets`` module and expire (default 30 min).
  * A code can be consumed at most once (``code_used_at``); reuse fails.
  * ``report_generated`` is enforced with a single conditional UPDATE — one free
    report per email, race-safe.
  * Raw email is never stored — only ``email_hash`` (SHA-256 of the normalized
    email). ``request_code`` returns the raw code to the *caller* only so the
    e-mail-sending layer can deliver it; it is never persisted or shown in the UI.

This module deliberately has NO dependency on Streamlit so it can be unit-tested
standalone and reused outside the app.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import json
from datetime import datetime, timedelta, timezone

DEFAULT_CODE_TTL_MINUTES = 30
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguous 0/O/1/I/L
_CODE_LEN = 8


class StateStoreConfigError(RuntimeError):
    """Raised when a backend is selected but cannot be configured (fail closed)."""


# ── pure helpers (shared by both backends) ──────────────────────────────────

def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def email_hash(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def generate_code(n: int = _CODE_LEN) -> str:
    """Cryptographically secure, human-typeable, unambiguous code."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(n))


def _pepper() -> str:
    return os.getenv("BAZAR_CODE_PEPPER", "")


def hash_code(eh: str, code: str) -> str:
    """Peppered, email-bound SHA-256 of the (case-insensitive) code. Never reversible."""
    material = f"{eh}:{(code or '').strip().upper()}:{_pepper()}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ── base interface ───────────────────────────────────────────────────────────

class StateStore:
    """Stable interface used by the app. Subclasses implement the storage."""

    def __init__(self, code_ttl_minutes: int | None = None):
        self.code_ttl_minutes = (
            DEFAULT_CODE_TTL_MINUTES if code_ttl_minutes is None else int(code_ttl_minutes)
        )

    # ---- to be implemented by backends -------------------------------------
    def request_code(self, email: str, ip_hash: str | None = None,
                     user_agent_hash: str | None = None) -> dict:
        raise NotImplementedError

    def verify_code(self, email: str, code: str) -> dict:
        raise NotImplementedError

    def mark_report_generated(self, email: str, report_id: str | None = None) -> dict:
        raise NotImplementedError

    def has_used_free_report(self, email: str) -> bool:
        raise NotImplementedError

    def log_access_event(self, email_hash: str, event_type: str,
                         metadata: dict | None = None) -> None:
        raise NotImplementedError

    def recent_events(self, limit: int = 20) -> list:
        raise NotImplementedError

    # ---- shared helper -----------------------------------------------------
    def _new_code(self, eh: str):
        code = generate_code()
        return code, hash_code(eh, code), _now() + timedelta(minutes=self.code_ttl_minutes)


# ── SQLite backend (local/dev) ───────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS entitlements (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash        TEXT    NOT NULL UNIQUE,
    email_verified    INTEGER NOT NULL DEFAULT 0,
    code_hash         TEXT,
    code_expires_at   TEXT,
    code_used_at      TEXT,
    report_generated  INTEGER NOT NULL DEFAULT 0,
    report_generated_at TEXT,
    upload_count      INTEGER NOT NULL DEFAULT 0,
    first_seen_at     TEXT,
    last_seen_at      TEXT,
    ip_hash           TEXT,
    user_agent_hash   TEXT
);
CREATE TABLE IF NOT EXISTS access_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    email_hash   TEXT,
    event_type   TEXT NOT NULL,
    metadata_json TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_access_events_created ON access_events(created_at);
CREATE INDEX IF NOT EXISTS idx_access_events_email   ON access_events(email_hash);
"""


class SQLiteStateStore(StateStore):
    """Transactional SQLite store. Durable on a persistent disk; for LOCAL/DEV use.

    Note: on an ephemeral filesystem (e.g. Streamlit Cloud) SQLite is *not* durable
    across restarts — use the Supabase backend in production.
    """

    def __init__(self, path: str, code_ttl_minutes: int | None = None):
        super().__init__(code_ttl_minutes)
        self.path = path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level="DEFERRED")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SQLITE_SCHEMA)

    def request_code(self, email, ip_hash=None, user_agent_hash=None) -> dict:
        eh = email_hash(email)
        code, ch, expires = self._new_code(eh)
        now = _iso(_now())
        with self._connect() as conn:
            # Upsert by email_hash — never creates a duplicate entitlement row.
            conn.execute(
                """
                INSERT INTO entitlements
                    (email_hash, code_hash, code_expires_at, code_used_at,
                     first_seen_at, last_seen_at, ip_hash, user_agent_hash)
                VALUES (?, ?, ?, NULL, ?, ?, ?, ?)
                ON CONFLICT(email_hash) DO UPDATE SET
                    code_hash       = excluded.code_hash,
                    code_expires_at = excluded.code_expires_at,
                    code_used_at    = NULL,
                    last_seen_at    = excluded.last_seen_at,
                    ip_hash         = COALESCE(excluded.ip_hash, entitlements.ip_hash),
                    user_agent_hash = COALESCE(excluded.user_agent_hash, entitlements.user_agent_hash)
                """,
                (eh, ch, _iso(expires), now, now, ip_hash, user_agent_hash),
            )
            row = conn.execute(
                "SELECT report_generated FROM entitlements WHERE email_hash=?", (eh,)
            ).fetchone()
        used = bool(row["report_generated"]) if row else False
        # The raw code is returned to the CALLER only (for the e-mail layer).
        return {"status": "ok", "code": code,
                "already_used_free_report": used}

    def verify_code(self, email, code) -> dict:
        eh = email_hash(email)
        ch = hash_code(eh, code)
        now = _now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT code_hash, code_expires_at, code_used_at FROM entitlements WHERE email_hash=?",
                (eh,),
            ).fetchone()
            if row is None or not row["code_hash"]:
                return {"status": "not_found"}
            if row["code_used_at"]:
                return {"status": "used"}
            exp = _parse_iso(row["code_expires_at"])
            if exp is None or now >= exp:
                return {"status": "expired"}
            if not secrets.compare_digest(row["code_hash"], ch):
                return {"status": "mismatch"}
            # Atomic single-use consume: guarded so a concurrent verify can't double-spend.
            cur = conn.execute(
                """
                UPDATE entitlements
                   SET email_verified=1, code_used_at=?, last_seen_at=?
                 WHERE email_hash=? AND code_used_at IS NULL AND code_hash=?
                """,
                (_iso(now), _iso(now), eh, ch),
            )
            if cur.rowcount != 1:
                return {"status": "used"}
        return {"status": "ok"}

    def mark_report_generated(self, email, report_id=None) -> dict:
        eh = email_hash(email)
        now = _iso(_now())
        with self._connect() as conn:
            # One free report per email: conditional UPDATE is atomic.
            cur = conn.execute(
                """
                UPDATE entitlements
                   SET report_generated=1, report_generated_at=?,
                       upload_count=upload_count+1, last_seen_at=?
                 WHERE email_hash=? AND email_verified=1 AND report_generated=0
                """,
                (now, now, eh),
            )
            if cur.rowcount == 1:
                return {"status": "ok"}
            row = conn.execute(
                "SELECT email_verified, report_generated FROM entitlements WHERE email_hash=?",
                (eh,),
            ).fetchone()
        if row is None:
            return {"status": "not_found"}
        if not row["email_verified"]:
            return {"status": "not_verified"}
        return {"status": "already_used"}

    def has_used_free_report(self, email) -> bool:
        eh = email_hash(email)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_generated FROM entitlements WHERE email_hash=?", (eh,)
            ).fetchone()
        return bool(row["report_generated"]) if row else False

    def log_access_event(self, email_hash, event_type, metadata=None) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO access_events (email_hash, event_type, metadata_json, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (email_hash, event_type,
                     json.dumps(metadata, ensure_ascii=False) if metadata else None,
                     _iso(_now())),
                )
        except Exception:
            pass  # logging must never break the request path

    def recent_events(self, limit=20) -> list:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT email_hash, event_type, metadata_json, created_at "
                    "FROM access_events ORDER BY id DESC LIMIT ?", (int(limit),)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []


# ── Supabase backend (production/cloud) ──────────────────────────────────────

class SupabaseStateStore(StateStore):
    """Postgres-backed store via supabase-py. For PRODUCTION/cloud.

    Atomicity relies on PostgREST conditional updates (a single UPDATE ... WHERE
    is atomic in Postgres) plus the UNIQUE(email_hash) constraint for upserts.
    """

    TABLE = "entitlements"
    EVENTS = "access_events"

    def __init__(self, url: str, key: str, code_ttl_minutes: int | None = None, client=None):
        super().__init__(code_ttl_minutes)
        # `client` is a dependency-injection hook for tests (a fake PostgREST client).
        if client is not None:
            self._client = client
            return
        if not url or not key:
            raise StateStoreConfigError(
                "SupabaseStateStore requires both a URL and a service/anon key.")
        try:
            from supabase import create_client  # imported lazily so dev/tests need no dep
        except Exception as e:  # pragma: no cover - exercised only in prod installs
            raise StateStoreConfigError(
                "BAZAR_STATE_BACKEND=supabase but the 'supabase' package is not installed. "
                "Add 'supabase' to requirements and redeploy. Refusing to start (fail closed)."
            ) from e
        self._client = create_client(url, key)

    def request_code(self, email, ip_hash=None, user_agent_hash=None) -> dict:
        eh = email_hash(email)
        code, ch, expires = self._new_code(eh)
        now = _iso(_now())
        payload = {
            "email_hash": eh,
            "code_hash": ch,
            "code_expires_at": _iso(expires),
            "code_used_at": None,
            "last_seen_at": now,
        }
        if ip_hash:
            payload["ip_hash"] = ip_hash
        if user_agent_hash:
            payload["user_agent_hash"] = user_agent_hash
        # RA-5 fix: a SINGLE atomic upsert on the unique email_hash, instead of the
        # previous SELECT-exists → INSERT/UPDATE (two calls) which could race on a
        # brand-new email and trip the UNIQUE(email_hash) constraint. `first_seen_at`
        # is omitted so the DB default fills it on insert and it is preserved on
        # update; `report_generated` is omitted so it is never reset by a re-issue.
        res = (self._client.table(self.TABLE)
               .upsert(payload, on_conflict="email_hash")
               .execute())
        used = bool(res.data and res.data[0].get("report_generated"))
        return {"status": "ok", "code": code, "already_used_free_report": used}

    def verify_code(self, email, code) -> dict:
        eh = email_hash(email)
        ch = hash_code(eh, code)
        now = _now()
        res = (self._client.table(self.TABLE)
               .select("code_hash, code_expires_at, code_used_at")
               .eq("email_hash", eh).limit(1).execute())
        if not res.data or not res.data[0].get("code_hash"):
            return {"status": "not_found"}
        row = res.data[0]
        if row.get("code_used_at"):
            return {"status": "used"}
        exp = _parse_iso(row.get("code_expires_at"))
        if exp is None or now >= exp:
            return {"status": "expired"}
        if not secrets.compare_digest(str(row.get("code_hash")), ch):
            return {"status": "mismatch"}
        # Atomic consume: only succeeds while code_used_at is still null.
        upd = (self._client.table(self.TABLE)
               .update({"email_verified": True, "code_used_at": _iso(now),
                        "last_seen_at": _iso(now)})
               .eq("email_hash", eh).is_("code_used_at", "null").execute())
        if not upd.data:
            return {"status": "used"}
        return {"status": "ok"}

    def mark_report_generated(self, email, report_id=None) -> dict:
        eh = email_hash(email)
        now = _iso(_now())
        # Conditional UPDATE enforces one free report atomically at the row level.
        upd = (self._client.table(self.TABLE)
               .update({"report_generated": True, "report_generated_at": now,
                        "last_seen_at": now})
               .eq("email_hash", eh).eq("email_verified", True)
               .eq("report_generated", False).execute())
        if upd.data:
            # best-effort increment (not part of the gating decision)
            try:
                cur = (self._client.table(self.TABLE).select("upload_count")
                       .eq("email_hash", eh).limit(1).execute())
                n = int((cur.data or [{}])[0].get("upload_count", 0)) + 1
                self._client.table(self.TABLE).update({"upload_count": n}).eq("email_hash", eh).execute()
            except Exception:
                pass
            return {"status": "ok"}
        res = (self._client.table(self.TABLE).select("email_verified, report_generated")
               .eq("email_hash", eh).limit(1).execute())
        if not res.data:
            return {"status": "not_found"}
        if not res.data[0].get("email_verified"):
            return {"status": "not_verified"}
        return {"status": "already_used"}

    def has_used_free_report(self, email) -> bool:
        eh = email_hash(email)
        res = (self._client.table(self.TABLE).select("report_generated")
               .eq("email_hash", eh).limit(1).execute())
        return bool(res.data and res.data[0].get("report_generated"))

    def log_access_event(self, email_hash, event_type, metadata=None) -> None:
        try:
            self._client.table(self.EVENTS).insert({
                "email_hash": email_hash,
                "event_type": event_type,
                "metadata_json": json.dumps(metadata, ensure_ascii=False) if metadata else None,
                "created_at": _iso(_now()),
            }).execute()
        except Exception:
            pass

    def recent_events(self, limit=20) -> list:
        try:
            res = (self._client.table(self.EVENTS).select("*")
                   .order("created_at", desc=True).limit(int(limit)).execute())
            return res.data or []
        except Exception:
            return []


# ── factory / backend selection ──────────────────────────────────────────────

DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bazar_state.db")


def get_state_store(backend: str | None = None, *,
                    sqlite_path: str | None = None,
                    supabase_url: str | None = None,
                    supabase_key: str | None = None,
                    code_ttl_minutes: int | None = None) -> StateStore:
    """Build the configured StateStore.

    backend resolution: explicit arg → BAZAR_STATE_BACKEND env → "sqlite".
    If backend == "supabase" and the URL/key are missing, raise
    StateStoreConfigError (FAIL CLOSED — never fall back to local files).
    """
    backend = (backend or os.getenv("BAZAR_STATE_BACKEND") or "sqlite").strip().lower()

    if backend == "sqlite":
        path = sqlite_path or os.getenv("BAZAR_SQLITE_PATH") or DEFAULT_SQLITE_PATH
        return SQLiteStateStore(path, code_ttl_minutes=code_ttl_minutes)

    if backend == "supabase":
        url = supabase_url or os.getenv("SUPABASE_URL")
        key = (supabase_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
               or os.getenv("SUPABASE_ANON_KEY"))
        if not url or not key:
            raise StateStoreConfigError(
                "BAZAR_STATE_BACKEND=supabase but SUPABASE_URL and/or "
                "SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY) are not set. "
                "Refusing to start (fail closed) — Bazar will NOT fall back to local JSON/SQLite."
            )
        return SupabaseStateStore(url, key, code_ttl_minutes=code_ttl_minutes)

    raise StateStoreConfigError(
        f"Unknown BAZAR_STATE_BACKEND={backend!r}. Use 'sqlite' (dev) or 'supabase' (prod).")
