# D3I Existing Operator-Control Confirmation Provenance Audit
Date: 2026-07-05

## Status

Read-only provenance audit completed.

No Supabase writes.
No campaign mutation.
No operator-control confirmation.
No operator-control reversal.
No D3D execution.
No score impact.
No rank impact.
No state impact.
No transition impact.

## Purpose

Audit the 52 campaigns where evidence.operator_control.operator_control_confirmed is already true.

The purpose is not to trust, repair, reconfirm, or reverse those confirmations.

The purpose is provenance classification only.

## Live Audit Result

Total campaigns reviewed: 228

Already-confirmed operator-control rows: 52

Current D3C shadow status of the already-confirmed rows:

- Doctrine-confirmable shadow: 25
- Doctrine-not-confirmable: 27

SML evidence quality among already-confirmed rows:

- Inferred from absorption event: 13
- Inferred from classical event: 18
- Missing: 21
- Explicit geometry: 0

## Raw Operator-Control Provenance Findings

The 52 already-confirmed rows generally show:

- operator_control_confirmed: true
- verdict: OPERATOR_CONTROL_EVIDENCED
- status: OK
- method_basis: RAW_OHLCV_TAPE_BEHAVIOR_ONLY
- not_derived_from_scores: true
- score_impact: NONE
- rank_impact: NONE
- state_impact: NONE

However, the following provenance fields are missing or null:

- engine
- engine_version
- confirmation_engine
- confirmation_engine_version
- production_confirmation_engine
- production_confirmation_engine_version
- not_derived_from_gamma
- transition_impact

## No-Drift Conclusion

D3I identifies a legacy provenance gap.

The existing 52 confirmed operator-control rows must not be treated as D3D-confirmed production confirmations.

They should be classified as legacy operator-control confirmations with incomplete provenance metadata.

No row was modified.
No row was unconfirmed.
No row was reconfirmed.
No substitute evidence was inferred.
No score-derived confirmation was accepted.
No D3D mutation was authorized.
