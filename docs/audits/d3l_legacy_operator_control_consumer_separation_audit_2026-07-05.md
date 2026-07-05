# D3L Legacy Operator-Control Consumer Separation Audit

Date: 2026-07-05

## Purpose

D3L corrected consumer-facing diagnostic language so that legacy operator-control evidence is no longer displayed or grouped as production-confirmed operator control.

This was necessary because D3K and D3K.1 identified that some diagnostic endpoints were using legacy `operator_control_confirmed` language in a way that could imply production confirmation.

## Core Doctrine

Operator control is evidence, not a score.

Operator control shall not be derived from composite score, survival score, campaign rank, gamma exposure, options overlay, probability score, edge score, expected return, historical outcome, price target, or future return.

Legacy operator-control evidence is not D3D production-confirmed operator control.

Shadow-confirmable means plausibility, not production confirmation.

## Files Modified

- backend/campaign_api.py
- backend/campaign_engine/operator_control_confirmation_candidate_engine.py

## What Was Corrected

The old diagnostic consumer language included:

- operator_control_confirmed_count
- operator_control_confirmed_ranked
- operator_control_confirmed_campaigns
- Operator control is confirmed
- Existing operator_control engine already confirms tape-derived Composite Operator control

D3L replaced that language with:

- legacy_operator_control_evidence_count
- legacy_operator_control_evidence_ranked_diagnostic_only
- legacy_operator_control_evidence_campaigns
- d3d_production_confirmed_operator_control_count
- d3d_production_confirmed_operator_control_ranked
- LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION

## Live Verification

Endpoint verified:

/api/campaign/evidence-diagnostic-rankings

Live keys now include:

- legacy_operator_control_evidence_count
- legacy_operator_control_evidence_ranked_diagnostic_only
- d3d_production_confirmed_operator_control_count
- d3d_production_confirmed_operator_control_ranked
- operator_control_confirmation_label_policy

Live result:

- legacy_operator_control_evidence_count: 52
- d3d_production_confirmed_operator_control_count: 0
- operator_control_confirmation_label_policy: LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION
- old operator_control_confirmed_count key: blank / absent

## D3J No-Drift Verification

D3J endpoint:

/api/campaign/operator-control-plausibility-status-review

Live result:

- guardrail failures: 0
- no-drift status: PASS 228

## D3D Gate Verification

D3D endpoint:

/api/campaign/operator-control-production-mutation-gate

Live dry-run result:

- dry_run: true
- execution_authorized: false
- writes_to_supabase: false
- mutates_campaigns: false
- eligible_count: 0

## No-Drift Result

D3L did not mutate Supabase.

D3L did not confirm operator control.

D3L did not unconfirm operator control.

D3L did not execute D3D.

D3L did not change score, rank, campaign state, transition state, gamma confirmation, or trade signal status.

D3L only corrected consumer-facing diagnostic naming so legacy evidence is not mislabeled as production confirmation.

## Conclusion

D3L successfully separated legacy operator-control evidence from D3D production-confirmed operator control at the diagnostic consumer layer.

The 52 legacy rows remain preserved as evidence.

Zero rows are D3D production-confirmed.

The application can now display legacy evidence without implying that D3D has certified operator control.
