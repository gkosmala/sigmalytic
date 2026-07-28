-- SIGMALYTIC — Behavioral Intelligence tables
-- Backs the Behavioral Intelligence tab and the trade-plan/entry/exit
-- workflow in frontend/app.py. Idempotent -- safe to run more than once.

create table if not exists public.behavior_trade_plans (
    plan_id text primary key,
    user_id text not null,
    symbol text not null,
    direction text not null,
    planned_entry numeric,
    planned_stop numeric,
    planned_target numeric,
    planned_size numeric,
    setup_reason text default '',
    signal_score_at_plan numeric default 0,
    regime_at_plan text default 'neutral',
    created_at timestamptz not null default now()
);

create index if not exists idx_behavior_trade_plans_user_id
    on public.behavior_trade_plans (user_id, created_at desc);


create table if not exists public.behavior_trades (
    trade_id text primary key,
    plan_id text references public.behavior_trade_plans(plan_id),
    user_id text not null,
    symbol text not null,
    direction text not null,

    entry_price numeric,
    stop_price numeric,
    target_price numeric,
    size numeric,
    market_regime_entry text default 'neutral',
    signal_score_entry numeric default 0,
    entered_at timestamptz not null default now(),

    exit_price numeric,
    market_regime_exit text,
    signal_score_exit numeric,
    notes text default '',

    no_plan boolean default false,
    stop_moved_wider boolean default false,
    target_moved boolean default false,
    premature_exit boolean default false,
    added_size_adverse boolean default false,
    timeframe_changed boolean default false,

    pnl numeric,
    pnl_percent numeric,
    behavior_flag text,
    composite_score numeric,
    exited_at timestamptz
);

create index if not exists idx_behavior_trades_user_id
    on public.behavior_trades (user_id, exited_at desc);


create table if not exists public.behavior_events (
    id bigserial primary key,
    user_id text not null,
    event_type text not null,
    symbol text,
    price numeric,
    timeframe text,
    market_regime text,
    decision_score numeric,
    decision_status text,
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_behavior_events_user_id
    on public.behavior_events (user_id, created_at desc);
