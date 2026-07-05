# D3J Operator-Control Plausibility Status Audit
Date: 2026-07-05

## Purpose

D3J was created to resolve the operator-control provenance problem without drifting from doctrine.

The prior state contained legacy operator-control confirmations. Those confirmations preserved possible raw tape-behavior evidence, but they lacked sufficient production-confirmation provenance to treat them as D3D-certified operator control.

D3J therefore separates operator-control evidence into plausibility statuses without mutating any production confirmation field.

## Doctrine Statement

Operator control is evidence, not a score.

Operator control shall not be derived from composite score, survival score, campaign rank, gamma exposure, options overlay, probability score, edge score, expected return, historical outcome, price target, or future return.

Shadow-confirmable means doctrinal plausibility, not production confirmation.

A shadow-confirmable campaign may later prove plausible as operator control, including possible stealth accumulation or stealth campaign behavior, but it is not D3D production-confirmed unless it passes the controlled D3D mutation gate.

## Endpoint

/api/campaign/operator-control-plausibility-status-review

## Engine

D3J_OPERATOR_CONTROL_PLAUSIBILITY_STATUS_ENDPOINT

## Version

phase_d3j_operator_control_plausibility_status_v1

## Live Verification

Total campaigns: 228

Guardrail failures: 0

No-drift status:
- PASS: 228

D3D production confirmed:
- False: 228

D3D eligible dry-run only:
- False: 228

Shadow-confirmable:
- True: 30
- False: 198

## Plausibility Status Distribution

- NOT_SHADOW_CONFIRMABLE: 171
- LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE: 27
- LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE: 25
- SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED: 5

## Plausible Stealth-Unconfirmed Candidates

These campaigns are shadow-confirmable but are not legacy-confirmed and are not D3D production-confirmed:

- ALLT
- GOVZ
- HNGE
- PAR
- PSCD

These are plausible future operator-control candidates. They may represent early or stealth operator behavior, but D3J does not confirm them.

## No-Drift Guardrails

D3J is read-only.

D3J does not write to Supabase.

D3J does not mutate campaigns.

D3J does not confirm operator control.

D3J does not unconfirm operator control.

D3J does not execute D3D.

D3J does not change score, rank, state, transition, gamma confirmation, or trade signal status.

## Interpretation

D3J fixes the prior ambiguity by separating evidence status from production confirmation.

The 25 legacy-confirmed and shadow-confirmable campaigns remain preserved as legacy operator-control evidence, but they are not D3D production-confirmed.

The 27 legacy-confirmed but not currently shadow-confirmable campaigns remain preserved as historical/legacy evidence, but they are not currently doctrine-confirmable under D3C shadow review.

The 5 shadow-confirmable plausible stealth-unconfirmed campaigns are watchlist candidates for future doctrine development and monitoring, but they are not production-confirmed.

## Conclusion

D3J successfully identifies shadow-confirmable plausibility without production mutation.

This preserves the possibility of stealth operator control while preventing unproven evidence from being promoted into D3D-certified operator-control confirmation.
