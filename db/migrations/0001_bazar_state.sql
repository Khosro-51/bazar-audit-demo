-- Bazar Audit — durable entitlement/state schema (audit finding E1).
-- Production backend for bazar_state_store.SupabaseStateStore.
--
-- How to apply (pick one):
--   * Supabase Dashboard -> SQL Editor -> paste this file -> Run.   (simplest)
--   * psql "$SUPABASE_DB_URL" -f db/migrations/0001_bazar_state.sql
--   * Supabase CLI: copy/symlink this into your CLI's supabase/migrations/
--     folder, then `supabase db push`.
-- NOTE: this lives under db/migrations/ (NOT a top-level supabase/ folder) on
-- purpose — a supabase/ dir at the repo root would shadow the installed
-- `supabase` Python package, since the app inserts its root onto sys.path.
--
-- Privacy: no raw email and no raw access code are ever stored.
--   * email_hash  = SHA-256 of the normalized (trim+lowercase) email
--   * code_hash   = peppered, email-bound SHA-256 of the one-time code

create table if not exists public.entitlements (
    id                  bigint generated always as identity primary key,
    email_hash          text        not null unique,
    email_verified      boolean     not null default false,
    code_hash           text,
    code_expires_at     timestamptz,
    code_used_at        timestamptz,
    report_generated    boolean     not null default false,
    report_generated_at timestamptz,
    upload_count        integer     not null default 0,
    first_seen_at       timestamptz not null default now(),
    last_seen_at        timestamptz not null default now(),
    ip_hash             text,
    user_agent_hash     text
);

-- email_hash already carries a UNIQUE constraint (one entitlement row per email).
create index if not exists idx_entitlements_report on public.entitlements(report_generated);
create index if not exists idx_entitlements_expires on public.entitlements(code_expires_at);

create table if not exists public.access_events (
    id            bigint generated always as identity primary key,
    email_hash    text,
    event_type    text        not null,
    metadata_json text,
    created_at    timestamptz not null default now()
);

create index if not exists idx_access_events_created on public.access_events(created_at desc);
create index if not exists idx_access_events_email   on public.access_events(email_hash);

-- The store connects with the service-role (or anon) key chosen in app secrets.
-- Row Level Security is intentionally left to the deployment: the service-role
-- key bypasses RLS, so writes from the trusted server work regardless. If the
-- anon key is used instead, add explicit RLS policies before enabling RLS.
--
-- One-free-report-per-email is enforced in the application via a single
-- conditional UPDATE (atomic at the row level):
--   UPDATE entitlements SET report_generated=true ...
--     WHERE email_hash=$1 AND email_verified=true AND report_generated=false;
-- A return of zero rows means the email already consumed its free report.
