# Sigmalytic V2 D3C.2F Macro-Anchor Behavioral-Resolution Confluence Audit

Date: 2026-07-06

## Purpose

D3C.2F adds a read-only confluence review between:

1. D3C.2E macro-anchor decision-zone evidence
2. D3J operator-control plausibility evidence

D3C.2F exists because D3C.2E isolated a large immediate-resistance decision-zone population, while D3J already provides the correct read-only plausibility source for shadow-confirmable operator-control evidence.

## Upstream Sources

D3C.2E endpoint:

GET /api/campaign/macro-anchor-decision-zone-review

D3J endpoint:

GET /api/campaign/operator-control-plausibility-status-review

D3C.2F does not use D3D as a production source.

D3C.2F does not execute D3D.

## Preflight Findings

D3C.2E:

- Total campaigns: 228
- Immediate resistance decision-zone campaigns: 105
- Non-decision-zone macro context: 123
- High-quality advanced decision-zone campaigns: 23
- Acceptable advanced decision-zone campaigns: 34

D3J:

- Total campaigns: 228
- Guardrail failure count: 0
- SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED: 5
- LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE: 25
- LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE: 27
- NOT_SHADOW_CONFIRMABLE: 171
- no_drift_status_distribution.PASS: 228

## Doctrine

Operator control is evidence, not a score.

Behavioral-resolution confluence is diagnostic evidence only.

D3C.2F does not confirm operator control.

D3C.2F does not unconfirm operator control.

D3C.2F does not execute D3D.

D3C.2F does not write to Supabase.

D3C.2F does not mutate campaigns.

D3C.2F does not change score, rank, state, transition, gamma, probability, expected return, edge, target, or historical outcome fields.

D3C.2F is not a trade signal.

## Endpoint

GET /api/campaign/macro-anchor-behavioral-resolution-confluence-review

## Required Guardrails

guardrail_failure_count = 0

row_error_count = 0

writes_to_supabase = False

mutates_campaigns = False

operator_control_confirmed_by_this_engine = False

operator_control_unconfirmed_by_this_engine = False

d3d_execution_allowed = False

d3d_source_used_by_this_engine = False

score_impact = NONE

rank_impact = NONE

state_impact = NONE

transition_impact = NONE

gamma_confirmation_impact = NONE

not_a_trade_signal = True
