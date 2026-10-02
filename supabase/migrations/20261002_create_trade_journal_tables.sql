-- SIGMALYTIC — Create trade_journal + trader_profile tables (2026-10-02)
-- ADDED: the journal's read/write functions (backend/trade_journal_service.py)
-- were migrated to the Supabase client on 2026-07-28, but the tables they
-- read/write were never actually created in Supabase -- the one function
-- that would have created them (_ensure_tables(), the old psycopg2/
-- DATABASE_URL path) is dead code, deliberately never called (see
-- tests/test_trade_journal_supabase_activation_static.py). Every journal
-- save has been failing with "relation does not exist" since that
-- migration, silently swallowed into a generic 500.
--
-- Mirrors the schema _ensure_tables() used to create, plus every column
-- log_trade_entry/log_trade_exit/_update_trader_profile actually write.
-- RLS is enabled (no policies) to match this project's hardening pattern
-- elsewhere -- the backend only ever connects with its service-role key,
-- which bypasses RLS by design, so this closes public-access exposure
-- without changing any app behavior.
-- Idempotent -- safe to run more than once.

create table if not exists public.trade_journal (
    journal_id          text primary key,
    user_id             text not null,
    symbol              text not null,
    direction           text not null default 'LONG',
    entry_date          date,
    entry_price         numeric(18,6),
    exit_date           date,
    exit_price          numeric(18,6),
    shares              integer,
    position_value      numeric(18,2),
    pnl                 numeric(18,2),
    pnl_pct             numeric(10,4),
    hold_days           integer,
    signal_id           text,
    campaign_id         text,
    tier                text,
    entry_quality_grade text,
    exit_quality_grade  text,
    patience_score      numeric(6,2),
    fomo_score          numeric(6,2),
    sizing_grade        text,
    rule_compliance     boolean default true,
    notes               text,
    status              text default 'OPEN',
    created_at          timestamptz default now(),
    updated_at          timestamptz default now()
);

create index if not exists idx_journal_user   on public.trade_journal(user_id);
create index if not exists idx_journal_symbol on public.trade_journal(symbol);
create index if not exists idx_journal_status on public.trade_journal(status);

create table if not exists public.trader_profile (
    user_id            text primary key,
    total_trades       integer default 0,
    open_trades        integer default 0,
    win_rate           numeric(6,2),
    avg_pnl_pct        numeric(10,4),
    avg_hold_days      numeric(8,2),
    avg_entry_quality  numeric(6,2),
    avg_exit_quality   numeric(6,2),
    avg_patience_score numeric(6,2),
    avg_fomo_score     numeric(6,2),
    entry_grade_dist   jsonb,
    exit_grade_dist    jsonb,
    behavioral_trend   text,
    strongest_pattern  text,
    weakest_pattern    text,
    updated_at         timestamptz default now()
);

alter table public.trade_journal  enable row level security;
alter table public.trader_profile enable row level security;
