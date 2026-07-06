# Sigmalytic V2 D3C.2C External Macro-Anchor Quality Tier Audit

Date: 2026-07-06

## Purpose

D3C.2C adds a read-only macro-anchor quality-tier review above D3C.2B.

D3C.2B validates whether macro support/resistance anchors exist.

D3C.2C classifies the quality and current-location relevance of those anchors.

## Doctrine

Operator control is evidence, not a score.

Macro-anchor quality tiers are structural-location diagnostics only.

D3C.2C does not confirm operator control.

D3C.2C does not write to Supabase.

D3C.2C does not mutate campaigns.

D3C.2C does not change score, rank, state, transition, gamma, probability, expected return, edge, target, or historical outcome fields.

D3C.2C is not a trade signal.

## Endpoint

GET /api/campaign/external-macro-anchor-quality-tier-review

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
