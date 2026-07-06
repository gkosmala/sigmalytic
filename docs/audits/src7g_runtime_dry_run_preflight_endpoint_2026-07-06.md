# SRC7G - Runtime Dry-Run Preflight Endpoint

SRC7G adds a deployed read-only dry-run endpoint:

`/api/campaign/src7g-runtime-dry-run-preflight-endpoint`

## Purpose

SRC7G exposes the SRC7F no-drift dry-run eligibility review through the deployed backend.

It can prove that source-only dry-run readiness is possible when valid explicit SML evidence is supplied.

## Strict Boundary

SRC7G is read-only and dry-run only.

SRC7G does not persist records.
SRC7G does not write to Supabase.
SRC7G does not mutate campaigns.
SRC7G does not execute D3D.
SRC7G does not authorize D3D.
SRC7G does not confirm operator control.
SRC7G does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Important Limitation

Fixture-mode success is not runtime production evidence.

Runtime mode may still return no explicit SML records until a real explicit structural-location source is supplied.

D3D remains blocked.
