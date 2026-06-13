-- =====================================================
-- SIGMALYTIC CAMPAIGN PLATFORM
-- CAMPAIGN STATE MACHINE V1
-- =====================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_state') THEN
        CREATE TYPE campaign_state AS ENUM (
            'BIRTH',
            'CONFIRMED',
            'SURVIVING',
            'EXPANDING',
            'MATURING',
            'DISTRIBUTION_RISK',
            'CLOSED'
        );
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_close_reason') THEN
        CREATE TYPE campaign_close_reason AS ENUM (
            'TARGET_REACHED',
            'STOP_HIT',
            'OPERATOR_EXIT',
            'TIMEOUT',
            'MANUAL',
            'INVALIDATED'
        );
    END IF;
END
$$;

ALTER TABLE campaigns
ADD COLUMN IF NOT EXISTS state_enum campaign_state DEFAULT 'BIRTH';

ALTER TABLE campaigns
ADD COLUMN IF NOT EXISTS close_reason campaign_close_reason;

ALTER TABLE campaigns
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP;

ALTER TABLE campaigns
ADD COLUMN IF NOT EXISTS close_notes TEXT;

ALTER TABLE campaign_state_history
ADD COLUMN IF NOT EXISTS prior_state_enum campaign_state;

ALTER TABLE campaign_state_history
ADD COLUMN IF NOT EXISTS new_state_enum campaign_state;

ALTER TABLE campaign_state_history
ADD COLUMN IF NOT EXISTS transition_score NUMERIC(8,4);

ALTER TABLE campaign_state_history
ADD COLUMN IF NOT EXISTS operator_dominance NUMERIC(6,2);

ALTER TABLE campaign_state_history
ADD COLUMN IF NOT EXISTS distribution_risk NUMERIC(6,2);

ALTER TABLE campaign_state_history
ADD COLUMN IF NOT EXISTS transition_metrics JSONB;

CREATE INDEX IF NOT EXISTS idx_campaign_state_enum
ON campaigns(state_enum);

CREATE INDEX IF NOT EXISTS idx_campaign_close_reason
ON campaigns(close_reason);

CREATE INDEX IF NOT EXISTS idx_state_history_new_state_enum
ON campaign_state_history(new_state_enum);