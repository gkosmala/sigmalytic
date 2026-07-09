# Sigmalytic V2 — Persisted Universe Source Design

Generated: 2026-07-09T14:08:23.4359642-04:00

## Purpose

The live coverage reader confirms daily_bars and campaigns, but it cannot advance campaign_pipeline_validated because no persisted universe source/table/count is confirmed.

This design creates a persisted universe source that can be read by the live GET-only coverage reader without calling Alpaca from the route and without substituting bars-symbol coverage as a fake universe.

## Non-Drift Rule

Bars-symbol coverage is diagnostic only. It cannot replace a persisted/live universe source.

## Proposed Tables

### campaign_universe_snapshots

- Append-only snapshot header.
- Stores snapshot_id, source, as_of_utc, universe_count, symbols_hash, is_current, and authorization reference.

### campaign_universe_symbols

- Append-only constituent table.
- Stores one normalized symbol row per snapshot_id.
- May include exchange/status/tradable/shortable/fractionable metadata when available.

## Reader Contract

- GET/select only.
- No Alpaca call from live route.
- No Supabase write from live route.
- No nightly run from live route.
- No readiness mutation from live route.
- Expose persisted universe availability and count as evidence.

## Future Write Boundary

A future universe snapshot ingest job may be designed separately, but it is not authorized here. Any future writer must be append-only, separately audited, and explicitly authorized.

## Campaign Pipeline Validation Gate

The pipeline can only be considered validated after a separate audit confirms persisted universe availability, positive universe count, daily bars readability, campaign schema alignment, pagination completeness, and no write execution during validation.

## Doctrine

Operator control remains evidence, not a score.

Operator control SHALL NOT be derived from composite score, campaign score, survival score, rank, tier, gamma/options overlay, probability, edge, expected return, historical outcomes, target projections, future returns, trade signals, or probability/edge calculations.

No Supabase write, no campaign mutation, no D3D authorization, no operator-control confirmation, no trade signal, and no Stripe/billing activation occur in this design step.
