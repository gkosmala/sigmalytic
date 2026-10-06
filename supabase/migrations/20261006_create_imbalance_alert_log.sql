-- Imbalance Alert log: every alert the engine raises, with later price outcomes.
create table if not exists public.imbalance_alert_log (
    alert_id          text primary key,
    symbol            text not null,
    direction         text not null check (direction in ('LONG', 'SHORT')),
    tier              text not null,
    pillars_agreeing  smallint not null,
    strength          numeric not null,
    entry_price       numeric not null,
    fired_at          timestamptz not null,
    emailed           boolean not null default false,
    outcomes          jsonb not null default '{}'::jsonb,
    outcomes_complete boolean not null default false,
    detail            jsonb not null default '{}'::jsonb
);

create index if not exists idx_imbalance_alert_log_fired
    on public.imbalance_alert_log (fired_at desc);
create index if not exists idx_imbalance_alert_log_open
    on public.imbalance_alert_log (outcomes_complete) where outcomes_complete = false;

alter table public.imbalance_alert_log enable row level security;
