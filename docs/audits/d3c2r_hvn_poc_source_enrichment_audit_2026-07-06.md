# D3C.2R HVN / POC Source-Enrichment Review Audit

## Purpose

D3C.2R creates a read-only diagnostic endpoint that separates true HVN / POC source evidence from the existing `HVN_ABSORPTION_PROXY`.

## Doctrine Boundary

`HVN_ABSORPTION_PROXY` is inferred behavioral-location evidence only. It is not true HVN / POC evidence and must not become production SML evidence by implication.

## True HVN / POC Source Rule

True HVN / POC requires an explicit source field such as:

- `hvn`
- `high_volume_node`
- `volume_profile_poc`
- `poc`
- `vpoc`
- `volume_node`
- `major_volume_node`
- `high_volume_zone`
- `volume_profile_node`

## Guardrails

D3C.2R:

- does not write to Supabase
- does not mutate campaigns
- does not confirm operator control
- does not unconfirm operator control
- does not execute D3D
- does not use D3D as source
- does not affect score
- does not affect rank
- does not affect campaign state
- does not affect transitions
- does not affect gamma/options
- does not create trade signals

## Endpoint

`/api/campaign/hvn-poc-source-enrichment-review`

## Expected Initial Finding

Because D3C.2P and D3C.2Q showed no true live HVN / POC source fields, D3C.2R is expected to report zero true HVN / POC availability until the upstream evidence payload is enriched with actual volume-profile data.

## No-Drift Statement

D3C.2R is diagnostic only. It may identify the absence or presence of true HVN / POC source fields, but it cannot convert inferred absorption proxy evidence into production confirmation.
