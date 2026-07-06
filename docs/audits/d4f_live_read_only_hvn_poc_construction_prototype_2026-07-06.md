# D4F - Live Read-Only HVN/POC Construction Prototype

D4F adds a deployed read-only backend construction endpoint:

`/api/campaign/d4f-read-only-hvn-poc-construction-prototype`

## Purpose

D4E.2 confirmed the deployed Render environment can read OHLCV bars from Alpaca SIP in read-only mode.

D4F therefore constructs a read-only HVN/POC prototype from deployed OHLCV bars.

## Strict Boundary

D4F is read-only.

D4F does not persist bars.
D4F does not write to Supabase.
D4F does not mutate campaigns.
D4F does not execute D3D.
D4F does not authorize D3D.
D4F does not confirm operator control.
D4F does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Source-Quality Limitation

D4F uses OHLCV range-distributed volume-profile construction.

This is a prototype construction from OHLCV bars, not a true exchange volume-at-price or tick-level market-profile source.

Therefore D4F alone cannot make any campaign D3D eligible.

D4G source-quality review is required next.
