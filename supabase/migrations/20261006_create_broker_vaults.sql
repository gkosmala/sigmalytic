-- SIGMALYTIC — Broker Behavioural Intelligence vaults (2026-10-06)
-- Five account "vaults" per user (slot 1-5). Each vault holds many uploaded
-- statements (CSV): transactions ("trades") and/or holdings ("positions").
-- The backend uses its service-role key (bypasses RLS); RLS is enabled with no
-- policies, matching this project's hardening pattern, so there is no public
-- access. Idempotent: safe to run more than once.

create table if not exists public.broker_vaults (
    user_id     text not null,
    slot        smallint not null check (slot between 1 and 5),
    name        text not null default '',
    broker      text not null default '',
    created_at  timestamptz default now(),
    updated_at  timestamptz default now(),
    primary key (user_id, slot)
);

create table if not exists public.broker_statements (
    statement_id text primary key,
    user_id      text not null,
    slot         smallint not null check (slot between 1 and 5),
    filename     text not null default '',
    kind         text not null check (kind in ('trades', 'positions')),
    row_count    integer not null default 0,
    period_start text,
    period_end   text,
    rows         jsonb not null default '[]'::jsonb,
    uploaded_at  timestamptz default now()
);

create index if not exists idx_broker_statements_vault
    on public.broker_statements (user_id, slot);

alter table public.broker_vaults     enable row level security;
alter table public.broker_statements enable row level security;
