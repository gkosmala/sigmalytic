-- =====================================================
-- SIGMALYTIC CAMPAIGN PLATFORM
-- CORE DATABASE SCHEMA V1
-- =====================================================

-- =====================================================
-- SYMBOL METADATA
-- Permanent reference table
-- One row per symbol
-- =====================================================

CREATE TABLE IF NOT EXISTS symbol_metadata (

```
symbol                  TEXT PRIMARY KEY,

company_name            TEXT,

sector                  TEXT,

industry                TEXT,

exchange                TEXT,

market_cap_tier         TEXT,

avg_daily_volume        BIGINT,

is_active               BOOLEAN DEFAULT TRUE,

russell_1000_member     BOOLEAN DEFAULT FALSE,

created_at              TIMESTAMP DEFAULT NOW(),

updated_at              TIMESTAMP DEFAULT NOW()
```

);

CREATE INDEX idx_symbol_sector
ON symbol_metadata(sector);

CREATE INDEX idx_symbol_active
ON symbol_metadata(is_active);

-- =====================================================
-- DAILY BARS
-- Raw market data
-- Independent of campaigns
-- =====================================================

CREATE TABLE IF NOT EXISTS daily_bars (

```
symbol                  TEXT NOT NULL,

bar_date                DATE NOT NULL,

open                    NUMERIC(18,6),

high                    NUMERIC(18,6),

low                     NUMERIC(18,6),

close                   NUMERIC(18,6),

volume                  BIGINT,

PRIMARY KEY(symbol, bar_date)
```

);

CREATE INDEX idx_daily_bars_symbol
ON daily_bars(symbol);

CREATE INDEX idx_daily_bars_date
ON daily_bars(bar_date);

-- =====================================================
-- CAMPAIGNS
-- Primary object in the system
-- One symbol may have many campaigns
-- =====================================================

CREATE TABLE IF NOT EXISTS campaigns (

```
campaign_id             BIGSERIAL PRIMARY KEY,

display_label           TEXT UNIQUE,

symbol                  TEXT NOT NULL,

timeframe               TEXT NOT NULL,

birth_date              DATE NOT NULL,

campaign_age_days       INTEGER DEFAULT 0,

current_state           TEXT,

operator_dominance      NUMERIC(6,2),

distribution_risk       NUMERIC(6,2),

historical_confidence   TEXT,

status                  TEXT DEFAULT 'ACTIVE',

created_at              TIMESTAMP DEFAULT NOW(),

updated_at              TIMESTAMP DEFAULT NOW(),

CONSTRAINT fk_campaign_symbol
    FOREIGN KEY(symbol)
    REFERENCES symbol_metadata(symbol)
```

);

CREATE INDEX idx_campaign_symbol
ON campaigns(symbol);

CREATE INDEX idx_campaign_state
ON campaigns(current_state);

CREATE INDEX idx_campaign_status
ON campaigns(status);

-- =====================================================
-- CAMPAIGN OBSERVATIONS
-- Daily campaign measurements
-- One row per campaign per day
-- =====================================================

CREATE TABLE IF NOT EXISTS campaign_observations (

```
observation_id          BIGSERIAL PRIMARY KEY,

campaign_id             BIGINT NOT NULL,

observation_date        DATE NOT NULL,

obs_score               TEXT,

prog_score              TEXT,

state_classification    TEXT,

d_score                 TEXT,

duration_bucket         TEXT,

spd_flag                BOOLEAN,

dei_flag                BOOLEAN,

wed_score               NUMERIC(10,4),

operator_dominance      NUMERIC(6,2),

distribution_risk       NUMERIC(6,2),

created_at              TIMESTAMP DEFAULT NOW(),

CONSTRAINT fk_observation_campaign
    FOREIGN KEY(campaign_id)
    REFERENCES campaigns(campaign_id)
```

);

CREATE INDEX idx_obs_campaign
ON campaign_observations(campaign_id);

CREATE INDEX idx_obs_date
ON campaign_observations(observation_date);

-- =====================================================
-- CAMPAIGN STATE HISTORY
-- Tracks lifecycle transitions
-- =====================================================

CREATE TABLE IF NOT EXISTS campaign_state_history (

```
state_history_id        BIGSERIAL PRIMARY KEY,

campaign_id             BIGINT NOT NULL,

transition_date         DATE NOT NULL,

prior_state             TEXT,

new_state               TEXT,

transition_reason       TEXT,

created_at              TIMESTAMP DEFAULT NOW(),

CONSTRAINT fk_state_campaign
    FOREIGN KEY(campaign_id)
    REFERENCES campaigns(campaign_id)
```

);

CREATE INDEX idx_state_campaign
ON campaign_state_history(campaign_id);

-- =====================================================
-- HISTORICAL ANALOGS
-- Research engine output
-- =====================================================

CREATE TABLE IF NOT EXISTS historical_analogs (

```
analog_id               BIGSERIAL PRIMARY KEY,

campaign_id             BIGINT NOT NULL,

analog_date             DATE,

observations_count      INTEGER,

success_rate            NUMERIC(8,4),

avg_mfe90               NUMERIC(12,4),

median_mfe90            NUMERIC(12,4),

expected_duration_days  INTEGER,

confidence_level        TEXT,

created_at              TIMESTAMP DEFAULT NOW(),

CONSTRAINT fk_analog_campaign
    FOREIGN KEY(campaign_id)
    REFERENCES campaigns(campaign_id)
```

);

CREATE INDEX idx_analog_campaign
ON historical_analogs(campaign_id);
