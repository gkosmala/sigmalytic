-- SIGMALYTIC V2
-- PHASE 12.28 APPEND-ONLY CAMPAIGN STATE TRANSITION AUDIT TABLE
-- Purpose:
--   Create the required append-only audit table before any controlled
--   production campaign lifecycle mutation is authorized.
--
-- This migration creates audit storage only.
-- It does not mutate campaigns.
-- It does not change campaign states.
-- It does not authorize D3D.
-- It does not confirm operator control.
-- It does not create trade signals.
-- It does not send alerts.
-- It does not touch Stripe/billing.

create table if not exists public.campaign_state_transition_audit_events (
    id bigserial primary key,
    created_at timestamptz not null default now(),

    source text not null default 'phase12_controlled_campaign_state_mutation',
    mode text not null default 'APPEND_ONLY_CAMPAIGN_STATE_TRANSITION_AUDIT',

    symbol text not null,
    campaign_id text null,

    before_state text not null,
    after_state text not null,
    transition_required boolean not null default true,

    lifecycle_field text not null default 'current_state',
    evidence_source text not null,
    rationale jsonb not null default '[]'::jsonb,

    guardrails jsonb not null default '{}'::jsonb,
    request_payload jsonb not null default '{}'::jsonb,
    response_payload jsonb not null default '{}'::jsonb,

    operator_control_confirmed boolean not null default false,
    authorizes_d3d boolean not null default false,
    not_a_trade_signal boolean not null default true,

    writes_to_supabase boolean not null default true,
    mutates_campaigns boolean not null default false,
    changes_states boolean not null default false,

    alert_send_execution boolean not null default false,
    stripe_touched boolean not null default false,
    billing_touched boolean not null default false,

    constraint campaign_state_transition_audit_events_before_state_check
        check (before_state in (
            'BIRTH',
            'CONFIRMED',
            'SURVIVING',
            'EXPANDING',
            'MATURING',
            'DISTRIBUTION_RISK',
            'CLOSED'
        )),

    constraint campaign_state_transition_audit_events_after_state_check
        check (after_state in (
            'BIRTH',
            'CONFIRMED',
            'SURVIVING',
            'EXPANDING',
            'MATURING',
            'DISTRIBUTION_RISK',
            'CLOSED'
        )),

    constraint campaign_state_transition_audit_events_lifecycle_field_check
        check (lifecycle_field = 'current_state'),

    constraint campaign_state_transition_audit_events_no_operator_control_check
        check (operator_control_confirmed = false),

    constraint campaign_state_transition_audit_events_no_d3d_authorization_check
        check (authorizes_d3d = false),

    constraint campaign_state_transition_audit_events_not_trade_signal_check
        check (not_a_trade_signal = true),

    constraint campaign_state_transition_audit_events_no_alert_send_check
        check (alert_send_execution = false),

    constraint campaign_state_transition_audit_events_no_stripe_touch_check
        check (stripe_touched = false),

    constraint campaign_state_transition_audit_events_no_billing_touch_check
        check (billing_touched = false)
);

create index if not exists idx_campaign_state_transition_audit_events_symbol_created_at
    on public.campaign_state_transition_audit_events (symbol, created_at desc);

create index if not exists idx_campaign_state_transition_audit_events_campaign_id_created_at
    on public.campaign_state_transition_audit_events (campaign_id, created_at desc);

create index if not exists idx_campaign_state_transition_audit_events_before_after_state
    on public.campaign_state_transition_audit_events (before_state, after_state);

alter table public.campaign_state_transition_audit_events enable row level security;

-- Read access remains explicit and narrow.
-- Service-role controlled backend writes are expected for future controlled execution.
create policy if not exists campaign_state_transition_audit_events_select_authenticated
    on public.campaign_state_transition_audit_events
    for select
    to authenticated
    using (true);

-- Append-only protection: no update/delete policy is created.
-- Future controlled backend execution may insert using service role only.
