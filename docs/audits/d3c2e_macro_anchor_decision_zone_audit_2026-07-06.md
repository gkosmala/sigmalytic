# Sigmalytic V2 D3C.2E Macro-Anchor Decision-Zone Audit

Date: 2026-07-06

## Purpose

D3C.2E adds a read-only decision-zone review above D3C.2D.

D3C.2E isolates campaigns at immediate validated macro resistance and separates early-state decision-zone context from advanced-state decision-zone context.

## Preflight Findings

Total campaigns: 228

Immediate resistance test campaigns: 105

Advanced-state immediate resistance campaigns: 57

Decision-zone by campaign state:

- SURVIVING: 51
- BIRTH: 36
- CONFIRMED: 12
- EXPANDING: 6

Decision-zone by quality tier:

- TIER_B_DUAL_ANCHOR_ACCEPTABLE: 66
- TIER_A_DUAL_ANCHOR_HIGH_QUALITY: 39

Decision-zone by state-alignment class:

- ACCEPTABLE_DUAL_ANCHOR_DECISION_ZONE: 66
- DECISION_ZONE_HIGH_QUALITY_SURVIVING_OR_EXPANDING: 23
- HIGH_QUALITY_EARLY_CAMPAIGN_CONTEXT: 16

## Doctrine

Operator control is evidence, not a score.

Decision-zone status is structural-location diagnostic evidence only.

D3C.2E does not confirm operator control.

D3C.2E does not write to Supabase.

D3C.2E does not mutate campaigns.

D3C.2E does not change score, rank, state, transition, gamma, probability, expected return, edge, target, or historical outcome fields.

D3C.2E is not a trade signal.

## Endpoint

GET /api/campaign/macro-anchor-decision-zone-review

## Required Guardrails

guardrail_failure_count = 0

row_error_count = 0

writes_to_supabase = False

mutates_campaigns = False

operator_control_confirmed_by_this_engine = False

score_impact = NONE

rank_impact = NONE

state_impact = NONE

transition_impact = NONE

gamma_confirmation_impact = NONE

not_a_trade_signal = True
