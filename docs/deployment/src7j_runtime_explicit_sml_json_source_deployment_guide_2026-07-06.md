# SRC7J - Runtime Explicit SML JSON Source Deployment Guide

SRC7J defines how to deploy real explicit SML / structural-location records through the read-only JSON source path.

## Current Status

SRC7I proved that the JSON source path works using temporary fixture JSON.

That fixture was not runtime production evidence.

SRC7J does not create runtime production evidence.

## Required Runtime Path

The deployed backend must be configured with:

`SIGMALYTIC_EXPLICIT_SML_JSON_PATH`

That variable must point to a read-only JSON file available inside the deployed runtime environment.

## Required JSON Shape

The runtime JSON file must contain an `explicit_sml_records` array. Each record must include:

- symbol
- campaign_id, if already bound
- level_type
- price_low
- price_mid
- price_high
- source_method
- source_reference
- source_timestamp_utc
- observed_window_start_utc
- observed_window_end_utc
- is_explicit = true
- is_inferred = false
- is_proxy = false
- is_hvn_absorption_proxy = false
- derived_from_score = false
- derived_from_rank = false
- derived_from_probability = false
- derived_from_edge = false
- derived_from_expected_return = false
- derived_from_target_projection = false
- derived_from_trade_signal = false
- derived_from_gamma_options_overlay = false
- derived_from_ohlcv_profile_approximation = false
- confirms_operator_control = false
- authorizes_d3d = false
- mutates_campaigns = false
- writes_to_supabase = false
- eligible_for_immediate_d3d_mutation = false

## Rejected Sources

The runtime JSON source must not contain records derived from:

- inferred SML;
- inferred structural location;
- HVN_ABSORPTION_PROXY;
- daily OHLCV profile approximation;
- intraday OHLCV profile approximation;
- score;
- rank;
- edge;
- probability;
- expected return;
- target projection;
- trade signal;
- gamma/options overlay.

## Deployment Steps

1. Create a real explicit SML JSON file outside the repository or in a secure runtime-mounted location.
2. Validate every record against the SRC7A contract before deployment.
3. Configure `SIGMALYTIC_EXPLICIT_SML_JSON_PATH` in the deployed environment.
4. Redeploy the backend.
5. Probe runtime mode with `/api/campaign/src7c-read-only-runtime-explicit-sml-source-probe?symbols=SPY&fixture_mode=none`.
6. Probe dry-run source-only readiness with `/api/campaign/src7g-runtime-dry-run-preflight-endpoint?symbols=SPY&fixture_mode=none`.
7. Confirm all guardrails remain intact:
   - writes_to_supabase = false
   - mutates_campaigns = false
   - executes_d3d = false
   - authorizes_d3d = false
   - operator_control_confirmed = false
   - production_d3d_eligibility_satisfied = false
   - d3d_execution_recommendation = DO_NOT_EXECUTE_D3D

## Strict Boundary

SRC7J is documentation and audit only.

SRC7J does not create runtime evidence.
SRC7J does not persist records.
SRC7J does not write to Supabase.
SRC7J does not mutate campaigns.
SRC7J does not execute D3D.
SRC7J does not authorize D3D.
SRC7J does not confirm operator control.
SRC7J does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Final Decision

D3D remains blocked.

The next phase is SRC7K runtime environment readiness probe after a real explicit SML JSON source is configured.
