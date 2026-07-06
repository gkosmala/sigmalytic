# Sigmalytic V2 D3C.2G High-Priority Behavioral-Resolution Evidence Audit

Date: 2026-07-06

## Purpose

D3C.2G adds a read-only review above D3C.2F.

D3C.2G inspects high-priority confluence rows and exposes the exact D3J behavioral-resolution evidence fields:

- d3c_shadow_doctrine_verdict
- d3c_shadow_explicit_geometry_sml
- d3c_shadow_sml_evidence_quality
- d3c_shadow_demand_support_validated
- d3c_shadow_supply_exhaustion_validated
- d3c_shadow_contrary_failure_present
- operator_control_method_basis
- operator_control_evidence_count
- operator_control_status
- operator_control_verdict

## Upstream Sources

D3C.2F endpoint:

GET /api/campaign/macro-anchor-behavioral-resolution-confluence-review

D3J source:

Embedded source_d3j_row from D3C.2F.

D3C.2E source:

Embedded source_d3c2e_row from D3C.2F.

D3C.2G does not execute D3D.

D3C.2G does not use D3D as a production source.

## Doctrine

Operator control is evidence, not a score.

Behavioral-resolution evidence is diagnostic evidence only.

D3C.2G does not confirm operator control.

D3C.2G does not unconfirm operator control.

D3C.2G does not execute D3D.

D3C.2G does not use D3D as a production source.

D3C.2G does not write to Supabase.

D3C.2G does not mutate campaigns.

D3C.2G does not change score, rank, state, transition, gamma, probability, expected return, edge, target, or historical outcome fields.

D3C.2G is not a trade signal.

## Endpoint

GET /api/campaign/macro-anchor-high-priority-resolution-evidence-review

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
