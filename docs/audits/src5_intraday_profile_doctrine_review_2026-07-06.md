# SRC5 - Intraday Profile Doctrine Review

SRC5 reviews the SRC4 read-only intraday profile refinement prototype.

## Context

SRC2 confirmed that deployed Alpaca SIP can return intraday OHLCV bars.

SRC3 confirmed that intraday OHLCV is a source-quality improvement over daily OHLCV but is still not true exchange volume-at-price.

SRC4 constructed a read-only profile refinement prototype from 1-minute OHLCV bars.

## Doctrine Finding

SRC4 is useful for research, diagnostics, and future visual inspection.

However, SRC4 remains an intraday OHLCV-derived approximation.

SRC4 is not true exchange volume-at-price.
SRC4 is not tick-level trade print data.
SRC4 is not explicit SML.
SRC4 does not construct true production HVN/POC.
SRC4 does not confirm operator control.
SRC4 does not authorize D3D.

## No-Drift Rule

Operator control is evidence, not a score.

Operator control SHALL NOT be derived from composite score, campaign score, survival score, rank, tier, gamma/options overlay, probability, edge, expected return, historical outcomes, target projections, future returns, or trade signals.

D3D is the only production mutation gate.

Read-only endpoints must never mutate, score, rank, transition, confirm/unconfirm operator control, or produce trade signals.

## Final SRC5 Decision

STOP before D3D.

Proceed to SRC6 true structural source selection.

Acceptable future sources include:

- true exchange volume-at-price;
- tick-derived volume profile;
- explicit SML or structural-location source.
