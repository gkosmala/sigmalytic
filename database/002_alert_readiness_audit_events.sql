-- Sigmalytic V2 - D3E.3 Controlled Persistence Schema Draft
-- Target table: public.alert_readiness_audit_events
-- Local schema draft only. No Supabase execution is performed by this step.

CREATE TABLE IF NOT EXISTS public.alert_readiness_audit_events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_read_only_audit TEXT NOT NULL DEFAULT 'sigmalytic_controlled_persistence',
    symbol TEXT NOT NULL,
    audit_component TEXT NOT NULL,
    audit_version TEXT NOT NULL,
    source_coverage_completion_status TEXT,
    evidence_payload_completeness_status TEXT,
    operator_control_evidence_audit_status TEXT,
    d3d_dry_run_gate_audit_status TEXT,
    controlled_persistence_contract_audit_status TEXT,
    controlled_persistence_activation_readiness_audit_status TEXT,
    activation_hypothetically_ready BOOLEAN NOT NULL DEFAULT FALSE,
    activation_readiness_blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
    read_only_guardrails JSONB NOT NULL DEFAULT '{}'::jsonb,
    allowed_persistence_fields_if_later_authorized JSONB NOT NULL DEFAULT '[]'::jsonb,
    absolutely_prohibited_persistence_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    doctrine_statement TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    writes_to_supabase BOOLEAN NOT NULL DEFAULT TRUE,
    append_only BOOLEAN NOT NULL DEFAULT TRUE,
    mutates_campaigns BOOLEAN NOT NULL DEFAULT FALSE,
    executes_d3d BOOLEAN NOT NULL DEFAULT FALSE,
    authorizes_d3d BOOLEAN NOT NULL DEFAULT FALSE,
    operator_control_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    composite_operator_control_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    not_a_trade_signal BOOLEAN NOT NULL DEFAULT TRUE,
    changes_scores BOOLEAN NOT NULL DEFAULT FALSE,
    changes_ranks BOOLEAN NOT NULL DEFAULT FALSE,
    changes_states BOOLEAN NOT NULL DEFAULT FALSE,
    changes_probabilities BOOLEAN NOT NULL DEFAULT FALSE,
    changes_edge BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT chk_alert_readiness_audit_events_append_only_true CHECK (append_only IS TRUE),
    CONSTRAINT chk_alert_readiness_audit_events_no_campaign_mutation CHECK (mutates_campaigns IS FALSE),
    CONSTRAINT chk_alert_readiness_audit_events_no_d3d_execution CHECK (executes_d3d IS FALSE),
    CONSTRAINT chk_alert_readiness_audit_events_no_d3d_authorization CHECK (authorizes_d3d IS FALSE),
    CONSTRAINT chk_alert_readiness_audit_events_no_operator_control_confirmation CHECK (operator_control_confirmed IS FALSE),
    CONSTRAINT chk_alert_readiness_audit_events_no_composite_operator_control_confirmation CHECK (composite_operator_control_confirmed IS FALSE),
    CONSTRAINT chk_alert_readiness_audit_events_not_trade_signal CHECK (not_a_trade_signal IS TRUE),
    CONSTRAINT chk_alert_readiness_audit_events_no_score_rank_state_probability_edge_mutation CHECK (changes_scores IS FALSE AND changes_ranks IS FALSE AND changes_states IS FALSE AND changes_probabilities IS FALSE AND changes_edge IS FALSE)
);

CREATE INDEX IF NOT EXISTS idx_alert_readiness_audit_events_created_at ON public.alert_readiness_audit_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_readiness_audit_events_symbol_created_at ON public.alert_readiness_audit_events (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alert_readiness_audit_events_audit_component ON public.alert_readiness_audit_events (audit_component);
CREATE INDEX IF NOT EXISTS idx_alert_readiness_audit_events_payload_gin ON public.alert_readiness_audit_events USING GIN (payload);

COMMENT ON TABLE public.alert_readiness_audit_events IS 'Sigmalytic V2 controlled append-only audit/event persistence table. Does not confirm operator control, authorize or execute D3D, mutate campaigns, alter scores/ranks/states/probabilities/edge, create trade signals, or touch Stripe.';