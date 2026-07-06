# SRC7A - Explicit SML / Structural-Location Evidence Contract

SRC7A creates the explicit structural-location contract required before any future D3D preflight can consider production mutation.

## Purpose

D4H, SRC5, and SRC6 confirmed that OHLCV-derived profiles are useful research artifacts but are not true HVN/POC, not tick data, and not explicit SML.

SRC7A therefore defines the strict contract for acceptable explicit structural-location records.

## Contract Rule

An acceptable structural-location record must be:

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

SRC7A rejects:

- inferred SML;
- inferred structural location;
- HVN_ABSORPTION_PROXY;
- OHLCV-derived profile approximation;
- score-derived levels;
- rank-derived levels;
- edge/probability-derived levels;
- trade-signal-derived levels.

## Strict Boundary

SRC7A is read-only.

SRC7A does not persist records.
SRC7A does not write to Supabase.
SRC7A does not mutate campaigns.
SRC7A does not execute D3D.
SRC7A does not authorize D3D.
SRC7A does not confirm operator control.
SRC7A does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Final Decision

SRC7A creates the contract only.

D3D remains blocked.

Next step:

SRC7B runtime explicit SML source adapter design.
