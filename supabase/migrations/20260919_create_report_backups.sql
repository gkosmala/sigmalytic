-- SIGMALYTIC — Report backup table
-- ADDED (2026-09-19): a genuine, independent backup of the daily
-- report pipeline's Redis data (reports:index + report:{date}
-- content), living in a completely separate system. Built after a
-- confirmed Redis persistence-mode incident wiped every previously-
-- stored report and its index -- Redis's own dashboard showed
-- "Journal + Snapshot" persistence, yet the live process reported
-- aof_enabled=0 and a fresh restart, so the exact cause remains
-- disputed with Render. This exists so a repeat of that same class of
-- incident can no longer cause real, unrecoverable data loss,
-- regardless of what Render-side setting turns out to be at fault.
-- Idempotent -- safe to run more than once.

create table if not exists public.report_backups (
    report_date text primary key,
    html_content text not null,
    backed_up_at timestamptz not null default now()
);

create index if not exists idx_report_backups_backed_up_at
    on public.report_backups (backed_up_at desc);

-- RLS enabled from the start -- this is only ever read/written by the
-- backend's own service-role key (which bypasses RLS by design), so
-- this closes the same public-access gap fixed on the other four
-- tables this session, without needing any policies here at all.
alter table public.report_backups enable row level security;
