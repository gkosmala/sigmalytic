# Sigmalytic V2 D3C.2D Macro-Anchor State Alignment Audit

Date: 2026-07-06

## Purpose

D3C.2D adds a read-only alignment review between:

1. D3C.2C macro-anchor quality tier
2. Campaign state
3. Current macro-location relevance

This phase exists because D3C.2C showed that macro-anchor quality is meaningful but must be interpreted in state context.

## Preflight Findings

Total campaigns: 228

Campaign state distribution:

- SURVIVING: 102
- BIRTH: 95
- CONFIRMED: 18
- EXPANDING: 13

Quality-tier distribution:

- TIER_A_DUAL_ANCHOR_HIGH_QUALITY: 57
- TIER_B_DUAL_ANCHOR_ACCEPTABLE: 116
- TIER_C_STRONG_SUPPORT_ONLY: 50
- TIER_D_PARTIAL_OR_WEAK_MACRO_CONTEXT: 3
- TIER_E_BLOCKED_OR_INSUFFICIENT_MACRO_ANCHOR: 2

Immediate resistance tests by state:

- SURVIVING: 51
- BIRTH: 36
- CONFIRMED: 12
- EXPANDING: 6

## Doctrine

Operator control is evidence, not a score.

State / macro-anchor alignment is structural-location diagnostic evidence only.

D3C.2D does not confirm operator control.

D3C.2D does not write to Supabase.

D3C.2D does not mutate campaigns.

D3C.2D does not change score, rank, state, transition, gamma, probability, expected return, edge, target, or historical outcome fields.

D3C.2D is not a trade signal.

## Endpoint

GET /api/campaign/macro-anchor-state-alignment-review

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
