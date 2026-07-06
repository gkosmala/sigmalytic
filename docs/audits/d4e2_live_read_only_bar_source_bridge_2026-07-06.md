# D4E.2 - Live Read-Only Bar Source Bridge

D4E.2 adds a deployed read-only backend probe endpoint:

`/api/campaign/d4e-read-only-live-bar-source-probe`

## Purpose

D4E and D4E.1 proved the local environment has no readable Supabase or Alpaca credentials.

D4E.2 therefore checks the deployed Render environment, where production market-data credentials may already exist.

## Strict Boundary

D4E.2 is read-only.

D4E.2 does not persist bars.
D4E.2 does not write to Supabase.
D4E.2 does not mutate campaigns.
D4E.2 does not construct HVN/POC.
D4E.2 does not execute D3D.
D4E.2 does not authorize D3D.
D4E.2 does not confirm operator control.
D4E.2 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## D4F Condition

D4F remains blocked unless D4E.2 confirms usable OHLCV bars inside the deployed environment.
