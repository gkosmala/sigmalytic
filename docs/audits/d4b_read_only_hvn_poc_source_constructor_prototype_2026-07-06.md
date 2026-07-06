# D4B - Read-Only True HVN/POC Source Constructor Prototype

## Status

D4B is a read-only constructor prototype.

It attempts to construct proposed true HVN/POC fields only when existing runtime payloads already contain usable OHLCV/volume bars.

D4B does not persist proposed fields.
D4B does not write to Supabase.
D4B does not mutate campaigns.
D4B does not execute D3D.
D4B does not authorize D3D.
D4B does not confirm operator control.
D4B does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Purpose

D4A defined the required source contract.

D4B performs the first read-only prototype attempt to construct:

- proposed POC price
- proposed HVN levels
- proposed HVN zones
- volume-profile bin size
- volume-profile total volume
- source-quality fields

## Doctrine Boundary

A D4B proposed HVN/POC construction is not D3D eligibility.

D4B output must not be treated as production confirmation.

D4B cannot use the following as substitutes for true HVN/POC:

- HVN_ABSORPTION_PROXY
- inferred SML
- campaign state
- score
- rank
- survival score
- operator-control score
- probability
- expected return
- gamma/options overlay
- future return

## Expected Interpretation

If usable OHLCV bars are missing from the runtime candidate payload, D4B must report the blocker directly.

It must not invent HVN/POC levels.

It must not fall back to HVN_ABSORPTION_PROXY.

## Next Phase

If D4B shows that runtime candidate payloads do not contain usable OHLCV/volume bars, D4C should identify the correct read-only market-data source path for supplying bars to the constructor.

## D4B.1 Source-Gap Reporting Hotfix

D4B.1 corrects the reporting logic so that `source_gap_flags` explicitly reflects the runtime constructor blocker when all D4B candidate attempts are blocked by missing OHLCV bars.

This is a reporting-only hotfix.

It does not persist HVN/POC fields.
It does not write to Supabase.
It does not mutate campaigns.
It does not execute D3D.
It does not authorize D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

The expected D4B.1 result remains:

- zero D4B D3D eligibility
- zero mutation
- D3D execution recommendation remains DO_NOT_EXECUTE_D3D
- missing runtime OHLCV bars are explicitly reported as a source gap
