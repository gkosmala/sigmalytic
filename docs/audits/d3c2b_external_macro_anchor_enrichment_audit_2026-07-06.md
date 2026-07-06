# Sigmalytic V2 D3C.2B External Macro-Anchor Enrichment Audit

Date: 2026-07-06

## Purpose

D3C.2B adds read-only historical macro support/resistance anchor validation.

## Guardrail

Old pivots are blocked unless gate-validated by repeated touches and close-based rejection/recapture.

## Mutation Statement

D3C.2B performs no Supabase mutation.

D3C.2B does not confirm operator control.

D3C.2B does not change score, rank, state, transition, gamma, probability, expected return, edge, target, or historical outcome fields.

## Endpoint

GET /api/campaign/external-macro-anchor-enrichment-review

## Required Guardrail Result

guardrail_failure_count = 0
