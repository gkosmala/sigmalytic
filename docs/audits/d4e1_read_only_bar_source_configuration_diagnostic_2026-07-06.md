# D4E.1 - Read-Only Bar Source Configuration Diagnostic

## Status

D4E.1 diagnoses why D4E found zero usable OHLCV bars.

D4E.1 is read-only.

D4E.1 does not supply bars to D4B.
D4E.1 does not construct HVN/POC.
D4E.1 does not persist bars.
D4E.1 does not write to Supabase.
D4E.1 does not mutate campaigns.
D4E.1 does not execute D3D.
D4E.1 does not authorize D3D.
D4E.1 does not confirm operator control.
D4E.1 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Purpose

D4E closed successfully but reported:

- candidate_count_attempted: 30
- candidate_count_with_usable_bars: 0
- d4f_readiness: BLOCKED_UNTIL_READ_ONLY_BAR_SOURCE_AVAILABLE

D4E.1 therefore checks:

1. local Supabase environment-variable presence
2. local Alpaca environment-variable presence
3. readable Supabase candidate bar tables
4. readable Alpaca bar access
5. D4E adapter sample warnings for candidate symbols

## Non-Drift Boundary

D4E.1 must not substitute:

- HVN_ABSORPTION_PROXY
- inferred SML
- score
- rank
- probability
- expected return
- gamma/options overlay
- target
- future return
- campaign state

for true OHLCV bar evidence.

## Next Step

D4F remains blocked until D4E reports usable OHLCV bars.

If D4E.1 finds a readable source, rerun D4E with the confirmed source configuration.

If D4E.1 does not find a readable source, resolve source access before continuing.
