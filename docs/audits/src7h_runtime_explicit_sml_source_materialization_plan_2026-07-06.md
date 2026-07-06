# SRC7H - Runtime Explicit SML Source Materialization Plan

SRC7H creates the runtime materialization plan for real explicit SML / structural-location records.

## Context

SRC7A created the explicit SML evidence contract.

SRC7B created the read-only explicit SML source adapter.

SRC7C deployed the read-only runtime explicit SML source probe.

SRC7D created the source-evidence preflight validator.

SRC7E created the D3D dry-run source binding review.

SRC7F created the no-drift dry-run eligibility review.

SRC7G deployed the runtime dry-run preflight endpoint.

## SRC7G Finding

Fixture mode proves that the system can validate an explicit SML record and pass source-only dry-run readiness.

Runtime mode still requires real explicit SML records.

Fixture success is not runtime evidence.

## SRC7H Materialization Decision

SRC7H selects the first materialization path:

`READ_ONLY_EXPLICIT_SML_JSON_SOURCE_FIRST`

The SRC7B adapter already supports this path through:

`SIGMALYTIC_EXPLICIT_SML_JSON_PATH`

## Runtime Source Requirements

A runtime explicit SML record must be:

- real;
- symbol-bound;
- price-bound;
- timestamped;
- explicitly sourced;
- non-inferred;
- non-proxy;
- non-score-derived;
- non-rank-derived;
- non-edge-derived;
- non-probability-derived;
- non-trade-signal-derived;
- non-options-overlay-derived;
- non-OHLCV-profile-approximation-derived.

## Rejected Sources

SRC7H continues to reject:

- inferred SML;
- inferred structural location;
- HVN_ABSORPTION_PROXY;
- OHLCV-derived profile approximation;
- score-derived levels;
- rank-derived levels;
- edge/probability-derived levels;
- target-derived levels;
- trade-signal-derived levels;
- gamma/options-overlay-derived levels.

## Strict Boundary

SRC7H is read-only and dry-run only.

SRC7H does not provide runtime evidence.
SRC7H does not persist records.
SRC7H does not write to Supabase.
SRC7H does not mutate campaigns.
SRC7H does not execute D3D.
SRC7H does not authorize D3D.
SRC7H does not confirm operator control.
SRC7H does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Template Warning

The SRC7H JSON template is not runtime evidence.

It is a structure for future real explicit SML records only.

## Next Step

Proceed to SRC7I read-only runtime JSON source probe.

D3D remains blocked.
