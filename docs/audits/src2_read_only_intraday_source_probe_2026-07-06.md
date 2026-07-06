# SRC2 - Read-Only Intraday Source Feasibility Probe

SRC2 adds a deployed read-only endpoint:

`/api/campaign/src2-read-only-intraday-source-probe`

## Purpose

SRC1 confirmed that the system has live read-only daily OHLCV access and a read-only OHLCV-derived D4F profile prototype, but no true D3D structural source.

SRC2 tests whether the deployed Alpaca SIP source can provide intraday OHLCV bars through the existing read-only adapter.

## Strict Boundary

SRC2 is read-only.

SRC2 does not persist bars.
SRC2 does not write to Supabase.
SRC2 does not mutate campaigns.
SRC2 does not construct HVN/POC.
SRC2 does not execute D3D.
SRC2 does not authorize D3D.
SRC2 does not confirm operator control.
SRC2 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Doctrine Limitation

Intraday OHLCV is not true exchange volume-at-price.

If SRC2 confirms intraday OHLCV availability, the next step is SRC3 source-quality review, not D3D.
