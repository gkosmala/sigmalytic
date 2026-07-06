# SRC1 - True Structural Source Resolution Inventory

SRC1 begins the post-D4H source-resolution track.

## Context

D4H closed the D4E to D4H chain with the correct final decision:

STOP before D3D.

The reason was not a software failure. The reason was source quality.

D4F constructed a useful read-only OHLCV-derived HVN/POC prototype, but D4G and D4H correctly determined that daily OHLCV bars are not true exchange volume-at-price, not tick-level profile data, and not explicit SML/structural-location evidence.

## Purpose

SRC1 inventories the repository and live read-only endpoints for possible true structural source paths.

## Strict Boundary

SRC1 is read-only.

SRC1 does not persist bars.
SRC1 does not write to Supabase.
SRC1 does not mutate campaigns.
SRC1 does not execute D3D.
SRC1 does not authorize D3D.
SRC1 does not confirm operator control.
SRC1 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Expected Finding

SRC1 should confirm:

1. D4E live read-only OHLCV source access exists.
2. D4F read-only OHLCV-derived profile prototype exists.
3. True exchange volume-at-price source is not yet confirmed.
4. Tick-level or intrabar volume-profile source is not yet confirmed.
5. Explicit SML or structural-location source is not yet confirmed for D3D.
6. D3D remains blocked.

## Next Step

Proceed to SRC2 source selection or implementation.

Acceptable SRC2 paths include:

- explicit SML/structural-location source that is not inferred;
- true exchange volume-at-price or tick-derived HVN/POC source;
- intraday profile source-quality bridge, still blocked from D3D until separately reviewed.
