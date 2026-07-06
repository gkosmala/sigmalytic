# SRC7B - Runtime Explicit SML Source Adapter Design

SRC7B creates the read-only runtime adapter design for explicit SML / structural-location records.

## Context

SRC7A created the explicit SML / structural-location evidence contract.

SRC7B defines how runtime records may be loaded and validated without mutation.

## Adapter Sources

SRC7B supports only read-only explicit source paths:

1. existing non-mutating runtime payload explicit SML records;
2. read-only JSON file explicit SML records.

SRC7B rejects inferred, proxy, score-derived, rank-derived, edge-derived, probability-derived, trade-signal-derived, options-overlay-derived, and OHLCV-profile-approximation-derived source policies.

## Strict Boundary

SRC7B is read-only.

SRC7B does not persist records.
SRC7B does not write to Supabase.
SRC7B does not mutate campaigns.
SRC7B does not execute D3D.
SRC7B does not authorize D3D.
SRC7B does not confirm operator control.
SRC7B does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Final Decision

SRC7B creates the adapter design only.

D3D remains blocked.

Next step:

SRC7C read-only runtime explicit SML source probe.
