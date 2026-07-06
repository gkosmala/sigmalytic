# SRC3 - Intraday Source-Quality Review

SRC3 reviews the SRC2 intraday OHLCV source probe.

## Context

SRC2 confirmed that the deployed Alpaca SIP read-only source can return intraday OHLCV bars.

## Finding

Intraday OHLCV is a meaningful source improvement over daily OHLCV because it provides finer time resolution.

However, intraday OHLCV is still not true exchange volume-at-price.
It is not tick-level trade print data.
It does not identify exact volume transacted at each price.
It is not explicit SML or structural-location evidence.
It cannot authorize D3D.

## Strict Boundary

SRC3 is read-only.

SRC3 does not persist bars.
SRC3 does not write to Supabase.
SRC3 does not mutate campaigns.
SRC3 does not construct production HVN/POC.
SRC3 does not execute D3D.
SRC3 does not authorize D3D.
SRC3 does not confirm operator control.
SRC3 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Next Step

SRC3 may proceed to SRC4 read-only intraday profile refinement.

D3D remains blocked.
