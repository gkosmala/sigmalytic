# SRC6 - True Structural Source Selection

SRC6 selects the next post-SRC5 source-resolution path.

## Context

D4H stopped before D3D because daily OHLCV-derived profile construction was not true volume-at-price and not explicit SML.

SRC2 confirmed deployed intraday OHLCV availability.

SRC3 confirmed intraday OHLCV is a source-quality improvement but still not true volume-at-price.

SRC4 constructed a read-only intraday OHLCV-derived profile refinement.

SRC5 confirmed that SRC4 remains research-only and cannot authorize D3D.

## Source Selection Decision

SRC6 selects:

`SRC7A_EXPLICIT_SML_STRUCTURAL_LOCATION_CONTRACT`

as the primary next path.

## Reason

The no-drift doctrine requires explicit SML or structural-location evidence for future D3D eligibility.

SRC4 cannot satisfy that requirement because it remains an intraday OHLCV-derived approximation.

True volume-at-price provider selection remains a valid parallel research path, but it is not currently confirmed and cannot be assumed.

## Strict Boundary

SRC6 is read-only.

SRC6 does not persist bars.
SRC6 does not write to Supabase.
SRC6 does not mutate campaigns.
SRC6 does not execute D3D.
SRC6 does not authorize D3D.
SRC6 does not confirm operator control.
SRC6 does not alter score, rank, state, transition, probability, edge, target, gamma/options, or trade signals.

## Next Step

Proceed to SRC7A:

Explicit SML / structural-location evidence contract.

D3D remains blocked.
