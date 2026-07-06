# D3X — Frontend Display Policy Remediation

## Status

D3X adds a frontend display-separation policy manifest.

It does not mutate campaigns.
It does not execute D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Purpose

D3W found six missing required display-separation labels. D3X remediates that by adding a frontend policy manifest containing all required labels and their required UI meanings.

## Added File

`frontend/display_policy/operator_control_display_separation_policy.json`

## Required Labels Added

- `LEGACY_EVIDENCE_ONLY_NOT_D3D_CONFIRMATION`
- `D3C_SHADOW_READ_ONLY_DIAGNOSTIC`
- `D3C2_DIAGNOSTIC_ENRICHMENT_UNCONFIRMED`
- `D3D_PRODUCTION_CONFIRMATION`
- `D3D_DRY_RUN_UNAUTHORIZED`
- `HVN_ABSORPTION_PROXY_NOT_TRUE_HVN_POC`
- `D3V_PREFLIGHT_BLOCKED_UNMUTATED`

## D3W Scanner Fix

The D3W audit scanner was patched to include `.json` files so frontend display-policy manifests are included in the required-label scan.

## No-Drift Rule

This remediation adds display language only. It does not change any production field, evidence field, scoring field, state field, transition field, gamma/options field, or trade-signal field.
