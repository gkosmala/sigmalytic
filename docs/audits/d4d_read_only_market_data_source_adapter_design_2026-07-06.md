# D4D - Read-Only Market-Data Source Adapter Design

## Status

D4D is a read-only adapter design phase.

It does not implement the adapter.
It does not supply bars to D4B.
It does not construct HVN/POC.
It does not persist proposed HVN/POC fields.
It does not write to Supabase.
It does not mutate campaigns.
It does not execute D3D.
It does not authorize D3D.
It does not confirm operator control.
It does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Reason for D4D

D4B.1 proved that all 30 D4B candidate attempts are blocked by missing runtime OHLCV bars.

D4C inventoried market-data source-path candidates but did not supply bars.

D4D defines the adapter contract required before D4B can receive bars.

## Adapter Contract

The proposed adapter is:

`load_read_only_ohlcv_bars_for_d4b_candidate`

Proposed future module:

`backend/market_data/read_only_ohlcv_adapter.py`

Minimum input contract:

- symbol
- requested timeframe
- explicit window start and end, or configured lookback bars
- campaign id, if available
- campaign state, if available
- source-priority policy

Output contract:

- symbol
- timeframe
- source type
- source quality
- bars
- bar count
- window start
- window end
- warnings
- adapter status

Required bar schema:

- timestamp
- open
- high
- low
- close
- volume

## Accepted Read-Only Source Priority

1. Existing non-mutating runtime payload bars
2. Existing read-only cache or snapshot bars
3. Existing read-only Supabase market-data or snapshot table
4. Read-only Alpaca/SIP historical bars fetch

## Rejected Substitutes

The adapter must not use the following as true HVN/POC or as substitutes for bars:

- HVN_ABSORPTION_PROXY
- inferred SML
- campaign state
- score
- rank
- operator-control score
- survival score
- probability
- expected return
- gamma/options overlay
- future return

## D4E Requirement

D4E should implement the read-only adapter prototype and feed bars into D4B without persistence or mutation.

D4E must remain:

- read-only
- dry-run
- no Supabase writes
- no cache writes
- no campaign mutation
- no D3D execution
- no D3D authorization
- no operator-control confirmation
- no score/rank/state/transition impact
- not a trade signal

## D4D Runtime Parser Resume Correction

During the first D4D run, the D4D script attempted to parse the full JSON output emitted by D4C. D4C emits a very large static/source inventory payload. D4D does not need the full D4C JSON payload to design the adapter.

The D4D runtime logic was corrected to validate D4C by confirming its final PASS result rather than reparsing the entire D4C JSON inventory.

This correction does not change the doctrine.

D4D remains:

- design only
- read-only
- no bar supply
- no HVN/POC construction
- no Supabase writes
- no cache writes
- no campaign mutation
- no D3D execution
- no D3D authorization
- no operator-control confirmation
- no score/rank/state/transition impact
- not a trade signal

## D4D Runtime Parser Resume Correction

During the first D4D run, the D4D script attempted to parse the full JSON output emitted by D4C. D4C emits a very large static/source inventory payload. D4D does not need the full D4C JSON payload to design the adapter.

The D4D runtime logic was corrected to validate D4C by confirming its final PASS result rather than reparsing the entire D4C JSON inventory.

This correction does not change the doctrine.

D4D remains:

- design only
- read-only
- no bar supply
- no HVN/POC construction
- no Supabase writes
- no cache writes
- no campaign mutation
- no D3D execution
- no D3D authorization
- no operator-control confirmation
- no score/rank/state/transition impact
- not a trade signal
