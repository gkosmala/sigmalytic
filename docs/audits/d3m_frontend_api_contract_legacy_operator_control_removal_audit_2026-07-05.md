# D3M Frontend/API Contract Audit ? Legacy Operator-Control Removal

Date: 2026-07-05

## Purpose

D3M audited and corrected frontend/API-facing diagnostic contract language so that legacy `operator_control_confirmed` evidence can no longer be interpreted as D3D production-confirmed operator control.

## Problem Found

The diagnostic ranking layer still used legacy `operator_control_confirmed` as a scoring and tiering input.

Specifically, the diagnostic priority function previously:

- read `operator_control_confirmed`;
- added +40 diagnostic score points when true;
- used that legacy boolean to assign A/B/Gamma-refresh diagnostic tiers;
- exposed old API keys such as `operator_control_confirmed_count` and `operator_control_confirmed_campaigns`.

That created a consumer-layer drift risk because legacy evidence could influence diagnostic ordering and be displayed as confirmation.

## Patch Applied

D3M removed legacy operator-control confirmation from diagnostic scoring and API contract language.

The patch removed:

- `operator_control_confirmed_count`
- `operator_control_confirmed_campaigns`
- `operator_control_confirmed_ranked`
- the +40 legacy operator-control score boost
- old wording that stated operator control was confirmed
- old candidate verdict routing for `ALREADY_CONFIRMED_BY_OPERATOR_CONTROL_ENGINE`

The patch added:

- `legacy_operator_control_evidence_count`
- `legacy_operator_control_evidence_campaigns`
- `legacy_operator_control_evidence_ranked_diagnostic_only`
- `d3d_production_confirmed_operator_control_count`
- `d3d_production_confirmed_operator_control_ranked`
- `LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION`

## Live Verification

Endpoint verified:

`/api/campaign/evidence-diagnostic-rankings`

Live result:

- legacy_operator_control_evidence_count: 52
- d3d_production_confirmed_operator_control_count: 0
- operator_control_confirmation_label_policy: LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION
- old operator_control_confirmed_count key: blank / absent

First diagnostic rows now show legacy operator-control evidence as diagnostic metadata only, not a score/rank boost.

## D3J Verification

Endpoint verified:

`/api/campaign/operator-control-plausibility-status-review`

Live result:

- guardrail failures: 0
- no-drift status: PASS 228

## D3D Verification

Endpoint verified:

`/api/campaign/operator-control-production-mutation-gate`

Live dry-run result:

- dry_run: true
- execution_authorized: false
- writes_to_supabase: false
- mutates_campaigns: false
- eligible_count: 0

## No-Drift Result

D3M did not mutate Supabase.

D3M did not confirm operator control.

D3M did not unconfirm operator control.

D3M did not execute D3D.

D3M removed legacy operator-control evidence from diagnostic scoring and ranking influence.

D3M preserved legacy evidence as evidence only.

## Conclusion

D3M completed the consumer-layer correction.

Legacy operator-control evidence can still be displayed and audited, but it no longer boosts diagnostic score, drives diagnostic tiering, or masquerades as D3D production-confirmed operator control.
