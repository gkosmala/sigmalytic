# Sigmalytic V2 Phase C — Diagnostic Doctrine Classifier Design

Date: 2026-07-03
Status: Phase C1 design checkpoint
Scope: Diagnostic doctrine classifier design only

Code impact: NONE
Score impact: NONE
Rank impact: NONE
State impact: NONE
Transition impact: NONE
Frontend impact: NONE
Database impact: NONE

## Purpose

Phase C designs the diagnostic doctrine classifier.

The classifier translates live campaign evidence into human-readable doctrine interpretations.

It is an explanation engine only.

It is not a trading signal engine.
It is not a scoring engine.
It is not a ranking engine.
It is not a state-transition engine.

## Controlling Source

The classifier must follow:

docs/v2_phase_b_doctrine_mapping_table.md

No classifier rule may be added unless its source evidence is mapped in the Phase B doctrine table.

## Guardrails

Every classifier output must preserve:

- diagnostic_only: true
- score_impact: NONE
- rank_impact: NONE
- state_impact: NONE
- transition_impact: NONE
- state_transition_enabled: false
- output_type: explanatory_diagnostic

The classifier must never mutate campaign evidence.
The classifier must never write campaign state.
The classifier must never alter score, rank, or transition eligibility.

## Allowed Inputs

The classifier may read only existing live evidence sections:

- raw_metrics
- operator_control
- wyckoff_doctrine
- multi_scale_weis
- vsa_weis_overlay
- transition_readiness
- symbol_behavior_profile

## Output Shape

The classifier should eventually emit:

- engine
- version
- diagnostic_only
- score_impact
- rank_impact
- state_impact
- transition_impact
- state_transition_enabled
- symbol
- overall_interpretation
- doctrine_labels
- wyckoff_interpretation
- weis_interpretation
- vsa_interpretation
- operator_control_interpretation
- survival_interpretation
- distribution_risk_interpretation
- conflict_interpretation
- blocking_warnings
- evidence_references

All outputs are explanatory only.

## Allowed Diagnostic Labels

The classifier may use labels such as:

- OPERATOR_CONTROL_CONFIRMED
- WYCKOFF_ACCUMULATION_SUPPORT
- WYCKOFF_SURVIVAL_PRESENT
- WYCKOFF_SURVIVAL_AT_RISK
- SPRING_SUPPORT_PRESENT
- SOS_SUPPORT_PRESENT
- ABSORPTION_SUPPORT_PRESENT
- WEIS_EXPANSION_SUPPORT
- WEIS_ALIGNED_UP
- WEIS_CONFLICT_PRESENT
- VSA_NO_SUPPLY_SUPPORT
- VSA_NO_DEMAND_CAUTION
- VSA_UPTHRUST_RISK
- VSA_BUYING_CLIMAX_RISK
- DISTRIBUTION_RISK_PRESENT
- LOW_LIQUIDITY_CAUTION
- INSUFFICIENT_EVIDENCE

These labels are not scores, ranks, states, or signals.

## Conflict Handling

The classifier must preserve conflicts.

Examples:

- Operator control confirmed but VSA no-demand present: control exists, but demand caution is present.
- Weis expansion support but Wyckoff survival at risk: expansion exists, but survival remains incomplete.
- Upward wave alignment but no-demand alert: upward structure exists, but participation quality is suspect.
- Low liquidity with volume evidence: volume interpretation requires caution.

The classifier must not hide cautionary evidence.

## Phase C1 Non-Goals

Phase C1 does not implement code.
Phase C1 does not create an endpoint.
Phase C1 does not modify campaign_evidence_builder.py.
Phase C1 does not modify campaign_state_engine.py.
Phase C1 does not modify discovery.
Phase C1 does not modify rankings.
Phase C1 does not modify frontend.
Phase C1 does not modify Supabase.

## Completion Criteria

Phase C1 is complete when this design document is committed and tagged.

Phase C2 may then implement the diagnostic-only classifier module.

The classifier must remain diagnostic-only until separately authorized.
