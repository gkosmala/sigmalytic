# Regression Tests

Added 2026-07-30, after an extended debugging session that found and
fixed roughly two dozen real, production bugs -- several of them the
"silent degradation" kind that don't crash anything, they just quietly
return wrong data (a frozen counter, a mismatched field name, a
duplicate route shadowing the real one, a thundering-herd cache bug,
a units error in a date-window calculation). None of these would have
been caught by simply running the app and clicking around; each one
needed to be specifically diagnosed from live evidence.

This suite exists so the highest-risk fixes from that session can't
silently regress again. Each test file's docstring explains the exact
bug it guards against and why.

## Running locally

```bash
pip install -r requirements.txt
pip install pytest
pytest tests/ -v
```

## Running in CI

`.github/workflows/tests.yml` runs this automatically on every push
and pull request to `main`.

## What's covered

- `test_gamma_regime.py` -- the gamma flip regime must be derived from
  comparing spot price to the flip level directly, not a separate
  chain-wide aggregate.
- `test_campaign_age.py` -- campaign age must be computed from
  `birth_date`, not the `campaign_age_days`/`duration_days` counters
  (which are set once at creation and never updated again).
- `test_single_flight_cache.py` -- concurrent requests for the same
  cache key must collapse into exactly one real computation (the
  thundering-herd bug that directly caused production OOM crashes),
  and a genuinely empty-but-fresh result must not be treated as a
  cache miss.
- `test_candle_lookback_window.py` -- intraday candle requests must
  stay within a few weeks of lookback, not balloon out to a
  multi-month window that can return stale historical data instead of
  recent bars.
- `test_status_center_metrics.py` -- tier counts, average ODS, and
  per-campaign return percentages must be derived from real, populated
  fields, not literal string matches or field names that are never
  actually set anywhere in the backend.
- `test_reports_engine.py` -- the daily report's "What Happened in the
  Market Today" section must use the properly Redis-bridged
  `get_radar_scores()`, never read the raw, always-empty-on-this-
  service `RADAR_CACHE` dict directly (the exact bug that broke this
  section on 2026-08-02, after a well-intentioned but ultimately
  reverted attempt to make it date-specific). Also locks in the
  simple, working function signatures (guarding against silently
  reintroducing the more complex, less reliable historical-fetch
  version), the report's core branding/formatting fixes (SPARK label,
  centered table headers, readable ODS/cohort text), and a clean
  "unavailable" message with no leftover internal diagnostic text.

## What's deliberately NOT covered (yet)

This suite focuses on pure, deterministic logic that can be tested
without mocking live network calls, a live Redis instance, or a live
Supabase connection. The many multi-process/multi-service issues fixed
the same night (Redis bridging between the backend and the separate
radar-scanner worker, duplicate/shadow API routes, memory instrumentation)
are architectural and are better caught by the manual verification
protocol used during that session (direct API inspection, live memory
logs) than by a unit test. Extending this suite to cover those with
proper mocking would be a good next step if regressions start slipping
through here.

## Note on `tests/_archive/dead_tests_2026-07-30/`

28 pre-existing test files were found in this directory during this
same cleanup, all dated before this session, all importing a
"controlled persistence status center" architecture that doesn't exist
anywhere in the actual codebase, and all syntactically invalid (a
stray byte-order-mark character at the start of every file). These
were blocking the working test suite from even collecting. Archived
(via `git mv`, history preserved) rather than deleted, matching the
same convention already established in `_archive/` elsewhere in this
repo, in case anything in them is worth salvaging later.
