# SRC4 - Read-Only Intraday Profile Refinement Prototype

SRC4 adds a deployed read-only endpoint:

`/api/campaign/src4-read-only-intraday-profile-refinement-prototype`

## Purpose

SRC3 confirmed that intraday OHLCV bars are available from the deployed Alpaca SIP read-only source.

SRC4 constructs a refined read-only profile prototype from 1-minute OHLCV bars.

## Strict Boundary

SRC4 is read-only.

SRC4 does not persist bars.
SRC4 does not write to Supabase.
SRC4 does not mutate campaigns.
SRC4 does not construct true production HVN/POC.
SRC4 does not execute D3D.
SRC4 does not authorize D3D.
SRC4 does not confirm operator control.
SRC4 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Doctrine Limitation

SRC4 output is an intraday OHLCV-derived profile refinement.

It is not true exchange volume-at-price.
It is not tick-level trade print data.
It is not explicit SML.

If SRC4 succeeds, the next step is SRC5 doctrine review.

D3D remains blocked.
