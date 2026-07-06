# D3Z - Runtime Structural Source Availability Audit

## Status

D3Z is a runtime read-only availability audit.

It does not mutate campaigns.
It does not execute D3D.
It does not authorize D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Purpose

D3Y showed that the codebase contains structural-source terms, proxy terms, inferred geometry terms, market-data terms, and D3D gate terms.

D3Z moves from static code inventory to live runtime availability.

D3Z calls the existing live endpoints:

- `/api/campaign/hvn-poc-source-enrichment-review`
- `/api/campaign/d3d-dry-run-candidate-preflight-review`

D3Z measures whether live runtime evidence currently contains:

- true HVN/POC source availability
- HVN_ABSORPTION_PROXY presence
- D3V dry-run preflight candidates
- D3V eligible candidates
- explicit geometry SML
- inferred SML
- D3V block reasons

## Doctrine Boundary

D3Z is not D3D.

D3Z never writes to Supabase.
D3Z never mutates campaigns.
D3Z never confirms operator control.
D3Z never unconfirms operator control.
D3Z never creates state transitions.
D3Z never creates score/rank effects.
D3Z never creates trade signals.

## Expected Result

D3V previously showed:

- 30 dry-run preflight candidates
- 0 eligible D3D mutations
- true HVN/POC source missing
- explicit geometry SML missing
- inferred SML rejected
- HVN_ABSORPTION_PROXY rejected as true HVN/POC

D3Z should preserve that same no-drift boundary and report runtime availability only.

## No-Drift Statement

Even if D3Z finds runtime source terms or candidates, it cannot authorize D3D and cannot produce production operator-control confirmation.
