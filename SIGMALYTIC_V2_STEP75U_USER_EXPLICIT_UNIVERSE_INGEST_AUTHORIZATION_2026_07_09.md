# Sigmalytic V2 — Step 75U Explicit User Authorization Service-Key Repair Retry

Generated: 2026-07-09T19:02:54.2871837-04:00

Authorization reference:

$AuthorizationRef

User authorization phrase:

> I explicitly authorize one append-only persisted universe snapshot ingest.

This retry resets and validates the Supabase service-role/secret key before any write is attempted.

Allowed write scope:

- Insert exactly one row into public.campaign_universe_snapshots.
- Insert normalized symbol rows into public.campaign_universe_symbols for that snapshot.

Forbidden scope:

- No campaign mutation.
- No daily_bars mutation.
- No readiness mutation.
- No D3D authorization.
- No operator-control confirmation.
- No trade signal.
- No Stripe/billing activation.
