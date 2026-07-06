# D3W — Frontend Display Separation Audit

## Status

D3W is a static, read-only display-separation audit.

It does not mutate campaigns.
It does not execute D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Purpose

D3W prevents frontend or UI language from collapsing the following categories into one display concept:

1. Legacy operator-control evidence
2. D3C shadow diagnostic evidence
3. D3C.2 diagnostic enrichment / confluence evidence
4. D3D production confirmation
5. D3V dry-run preflight status

## Required Display Separation

The UI must preserve these distinctions:

### Legacy Evidence

Legacy operator-control evidence is evidence only.

Required display meaning:

`LEGACY_EVIDENCE_ONLY_NOT_D3D_CONFIRMATION`

### D3C Shadow Review

D3C shadow output is diagnostic and read-only.

Required display meaning:

`D3C_SHADOW_READ_ONLY_DIAGNOSTIC`

### D3C.2 Diagnostic Enrichment

D3C.2O/R/S/T evidence is enrichment, confluence, source review, doctrine-leg review, and stealth monitoring only.

Required display meaning:

`D3C2_DIAGNOSTIC_ENRICHMENT_UNCONFIRMED`

### D3D Production Confirmation

D3D production confirmation is the only production confirmation layer.

Required display meaning:

`D3D_PRODUCTION_CONFIRMATION`

### D3D Dry Run

Dry-run status must never display as production confirmation.

Required display meaning:

`D3D_DRY_RUN_UNAUTHORIZED`

### HVN Absorption Proxy

`HVN_ABSORPTION_PROXY` is not true HVN/POC.

Required display meaning:

`HVN_ABSORPTION_PROXY_NOT_TRUE_HVN_POC`

### D3V Preflight

D3V rows are dry-run preflight only.

Required display meaning:

`D3V_PREFLIGHT_BLOCKED_UNMUTATED`

## D3V Current Doctrine Result

D3V live validation showed:

- total campaigns: 228
- D3V dry-run candidates: 30
- D3V preflight eligible candidates: 0
- D3V guardrail failures: 0
- D3V row errors: 0
- D3D execution allowed: false
- writes to Supabase: false
- mutates campaigns: false
- operator-control confirmed by D3V: false

The UI must therefore show:

`30 monitored dry-run candidates`
`0 D3D-eligible production confirmations`

## Absolute No-Drift UI Rule

The UI must never represent any of the following as production operator-control confirmation:

- legacy operator-control evidence
- D3J plausibility status
- D3C shadow output
- D3C.2O behavioral-resolution evidence
- D3C.2R HVN/POC source review
- D3C.2S doctrine-leg evidence
- D3C.2T stealth monitoring status
- D3V dry-run preflight candidate status
- inferred SML
- `HVN_ABSORPTION_PROXY`

## Audit Tool

D3W adds:

`tools/audits/d3w_frontend_display_separation_audit.py`

The audit scans frontend/backend files for display-risk patterns and reports findings without mutation.

Findings are review inventory. They do not automatically imply production drift.

## Next Step

After D3W, the next clean step is frontend remediation only if the audit identifies unsafe or ambiguous display language.
