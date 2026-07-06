# D4A - True HVN/POC + Explicit Geometry Source Construction Blueprint

## Status

D4A is a read-only blueprint and audit phase.

It does not construct runtime source fields.
It does not mutate campaigns.
It does not write to Supabase.
It does not execute D3D.
It does not authorize D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Reason for D4A

D3Z proved that the runtime D3D gate is blocked by missing source evidence.

Current blockers include:

- true HVN/POC source unavailable
- D3V eligible count zero
- HVN_ABSORPTION_PROXY present only as proxy evidence
- inferred SML present but not eligible by itself
- D3D execution recommendation remains DO_NOT_EXECUTE_D3D

## True HVN/POC Doctrine

True HVN/POC cannot be inferred from a behavioral label.

True HVN/POC must come from one of the following:

1. an auditable volume-by-price distribution constructed from OHLCV bars
2. an anchored volume profile constructed from an explicit structural window
3. an externally supplied auditable POC/HVN/VPOC field
4. a separately documented volume-profile source with source-quality metadata

## Rejected Substitutes

The following must not be treated as true HVN/POC:

- HVN_ABSORPTION_PROXY
- absorption labels
- inferred behavioral location
- campaign state
- score
- rank
- survival score
- operator-control score
- probability
- expected return
- gamma/options overlay
- future return

## Explicit Geometry Doctrine

Explicit geometry must identify the structural window before volume profile can be used for D3D eligibility.

Required geometry includes:

- explicit range high
- explicit range low
- explicit range start
- explicit range end
- explicit SML or last-point reference
- support/resistance reference
- source-quality label

Inferred SML remains non-eligible by itself.

## Future D4B

D4B should build a read-only source constructor that computes proposed true HVN/POC and explicit geometry fields without mutating campaigns.

D4B must remain:

- dry-run
- read-only
- no Supabase writes
- no campaign mutation
- no D3D execution
- no operator-control confirmation
- no score/rank/state/transition impact
- not a trade signal
