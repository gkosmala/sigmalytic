# D4C - Read-Only Market-Data Source Path Inventory

## Status

D4C is a read-only source-path inventory.

It does not supply bars to D4B.
It does not construct HVN/POC.
It does not persist proposed HVN/POC fields.
It does not write to Supabase.
It does not mutate campaigns.
It does not execute D3D.
It does not authorize D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Reason for D4C

D4B.1 proved that all 30 D4B candidate attempts are blocked by missing runtime OHLCV bars.

The corrected D4B.1 source-gap flags are:

- D4B_NO_TRUE_HVN_POC_CONSTRUCTED_FROM_RUNTIME_PAYLOAD
- D4B_RUNTIME_OHLCV_BARS_MISSING_FROM_CANDIDATE_PAYLOAD
- D4B_EXISTING_CANDIDATE_PAYLOAD_HAS_NO_OHLCV_BAR_SOURCE

D4C therefore inventories where OHLCV bars may already exist in the codebase and runtime pathway.

## D4C Scope

D4C inventories:

- Alpaca/SIP market-data source references
- OHLCV bar field references
- Supabase/storage references
- discovery/nightly pipeline references
- cache/snapshot references
- API route references
- volume-profile/HVN/POC references

## D4C Boundary

D4C must not treat any source-path candidate as proof that bars are available to D4B.

D4C only identifies candidate source paths.

D4D must separately design a read-only adapter that supplies OHLCV bars to D4B without mutation.

## Forbidden Shortcuts

D4C cannot use:

- HVN_ABSORPTION_PROXY as true HVN/POC
- inferred SML as D3D eligibility by itself
- score
- rank
- campaign state
- probability
- expected return
- gamma/options overlay
- target
- future return

## Expected Next Phase

D4D should design a read-only market-data source adapter.

The adapter should define how candidate symbols and campaign windows request OHLCV bars from the correct market-data path and pass them into the D4B constructor without persistence, mutation, or D3D execution.
