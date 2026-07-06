# D4E - Read-Only Market-Data Adapter Prototype

## Status

D4E implements the read-only OHLCV adapter prototype.

D4E does not construct HVN/POC.
D4E does not persist bars.
D4E does not write to Supabase.
D4E does not mutate campaigns.
D4E does not execute D3D.
D4E does not authorize D3D.
D4E does not confirm operator control.
D4E does not alter score, rank, campaign state, transition, gamma/options, probability, edge, target, or trade signals.

## Adapter Module

The D4E adapter module is:

`backend/market_data/read_only_ohlcv_adapter.py`

Primary function:

`load_read_only_ohlcv_bars_for_d4b_candidate`

## Purpose

D4E attempts to load OHLCV bars read-only for D3V candidate symbols.

Accepted read-only source priority:

1. existing non-mutating runtime candidate payload bars
2. Supabase REST read-only bar tables, if local readable credentials and tables exist
3. Alpaca REST read-only historical bars, if local credentials exist

## Strict Boundary

D4E is not D4F.

D4E only attempts to load and validate OHLCV bars.

D4E does not compute volume profile.
D4E does not compute POC.
D4E does not compute HVN.
D4E does not create explicit geometry.
D4E does not change D3D eligibility.

## Required Bar Schema

Each usable bar must contain:

- timestamp
- open
- high
- low
- close
- volume

## D4F Condition

D4F may proceed only if D4E reports usable OHLCV bars.

If D4E reports zero usable OHLCV bars, the correct result is stop/hold and identify the read-only source gap. Do not substitute HVN_ABSORPTION_PROXY, inferred SML, score, rank, probability, expected return, gamma/options, target, future return, or campaign state.
