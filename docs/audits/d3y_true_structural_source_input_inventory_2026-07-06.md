# D3Y — True Structural Source / HVN-POC Input Inventory

## Status

D3Y is a static source-code inventory.

It does not mutate campaigns.
It does not execute D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Purpose

D3V proved that the D3D production gate is blocked by evidence conditions, not software execution.

The strongest blockers were:

- true HVN/POC source missing
- explicit geometry SML missing
- inferred SML rejected
- HVN_ABSORPTION_PROXY rejected as true HVN/POC

D3Y inventories the codebase for possible source fields and construction inputs related to:

1. true HVN / POC / VPOC / volume-profile sources
2. HVN_ABSORPTION_PROXY proxy-only evidence
3. explicit structural geometry
4. inferred structural geometry
5. OHLCV / bar / volume market-data inputs
6. D3D dry-run / no-mutation gate references

## Added File

`tools/audits/d3y_true_structural_source_input_inventory.py`

## Doctrine Boundary

D3Y is inventory only.

D3Y must not:

- write to Supabase
- mutate campaigns
- execute D3D
- authorize D3D
- confirm operator control
- unconfirm operator control
- alter score
- alter rank
- alter campaign state
- alter transitions
- alter gamma/options
- create trade signals

## Expected Use

D3Y identifies where true structural-source work should be done next.

It does not decide that any campaign is eligible for D3D.

## No-Drift Statement

HVN_ABSORPTION_PROXY remains proxy-only evidence.

Inferred SML remains non-eligible for D3D by itself.

True HVN/POC requires explicit source fields or a separately constructed and auditable volume-profile source.
