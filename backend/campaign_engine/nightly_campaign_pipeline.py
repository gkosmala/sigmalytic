# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_engine/nightly_campaign_pipeline.py
-----------------------------------------------------
Nightly pipeline that drives the campaign lifecycle engine.

Runs after market close (21:00 UTC / 5:00 PM ET) — after the EOD audit
and geometry recalculation have completed.

WHAT IT DOES EACH NIGHT
------------------------
1. Loads all active campaigns from Supabase via campaign_store.
2. For each active campaign, fetches today's daily bar from the
   existing HISTORICAL_BARS cache in radar_service.
3. Pulls the confluence bridge output for the symbol (Weis + Wyckoff +
   behavioral state) via the existing confluence_bridge.
4. Translates that output into WyckoffSignals via wyckoff_signal_bridge.
5. Runs CampaignEngine.run_daily_cycle() — FSM evaluates every campaign.
6. Bulk-upserts all updated campaigns to Supabase in one call.
7. Logs a summary: how many campaigns advanced, closed, or held state.

SCHEDULER INTEGRATION
---------------------
Wire into main.py lifespan() exactly like _nightly_geometry_runner:

    from campaign_engine.nightly_campaign_pipeline import (
        run_nightly_campaign_pipeline,
        _CAMPAIGN_PIPELINE_AVAILABLE,
    )

    def _nightly_campaign_runner():
        while True:
            now = _dt.now(_tz.utc)
            target = now.replace(hour=21, minute=0, second=0, microsecond=0)
            if now >= target:
                target += _td(days=1)
            _t.sleep((target - now).total_seconds())
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(run_nightly_campaign_pipeline())
                loop.close()
            except Exception as _e:
                log.error(f"Nightly campaign pipeline failed: {_e}")

    _threading.Thread(target=_nightly_campaign_runner, daemon=True).start()

CLAUDE.md compliance
--------------------
• Credentials via os.environ only — passed through to store/bridge.
• Decimal used for all prices in the domain objects.
• Full type hints.
• Structured try/except with logging throughout.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

log = logging.getLogger("nightly_campaign_pipeline")

# ---------------------------------------------------------------------------
# Safe imports — mirrors the pattern in main.py
# ---------------------------------------------------------------------------

try:
    from campaign_engine.campaign_state_engine import (
        CampaignEngine,
        CampaignState,
        DailyBar,
        Campaign,
        ResearchSignal,
        build_engine,
    )
    _ENGINE_AVAILABLE = True
except Exception as _e:
    _ENGINE_AVAILABLE = False
    log.warning(f"campaign_state_engine import failed: {_e}")

try:
    from campaign_engine.campaign_store import CampaignStore
    _STORE_AVAILABLE = True
except Exception as _e:
    _STORE_AVAILABLE = False
    log.warning(f"campaign_store import failed: {_e}")

try:
    from campaign_engine.wyckoff_signal_bridge import (
        build_wyckoff_signals,
        signals_from_confluence_output,
    )
    _BRIDGE_AVAILABLE = True
except Exception as _e:
    _BRIDGE_AVAILABLE = False
    log.warning(f"wyckoff_signal_bridge import failed: {_e}")

# Confluence bridge already exists in backend — import safely
try:
    from confluence_bridge import get_confluence_scores
    _CONFLUENCE_AVAILABLE = True
except Exception as _e:
    _CONFLUENCE_AVAILABLE = False
    log.warning(f"confluence_bridge import failed: {_e}")

# Historical bars cache from radar_service (already loaded at startup)
try:
    from radar_service import _historical_bars as HISTORICAL_BARS
    _BARS_AVAILABLE = True
except Exception as _e:
    _BARS_AVAILABLE = False
    HISTORICAL_BARS = {}
    log.warning(f"radar_service bars import failed: {_e}")

# Flag for main.py safe-import check
_CAMPAIGN_PIPELINE_AVAILABLE = (
    _ENGINE_AVAILABLE
    and _STORE_AVAILABLE
    and _BRIDGE_AVAILABLE
)


# ---------------------------------------------------------------------------
# Daily bar extraction
# ---------------------------------------------------------------------------

def _extract_daily_bar(symbol: str, bars_cache: dict) -> Optional[DailyBar]:
    """
    Pull today's (or most recent) daily bar from the radar_service cache.

    The cache format matches supabase_bars.py:
    {symbol: [{"t": date_str, "o": open, "h": high, "l": low, "c": close, "v": vol}]}
    """
    bars = bars_cache.get(symbol)
    if not bars:
        return None

    latest = bars[-1]
    try:
        bar_date_raw = latest.get("t", "")
        bar_date     = date.fromisoformat(str(bar_date_raw)[:10])

        return DailyBar(
            symbol   = symbol,
            bar_date = bar_date,
            open     = Decimal(str(latest.get("o", 0))),
            high     = Decimal(str(latest.get("h", 0))),
            low      = Decimal(str(latest.get("l", 0))),
            close    = Decimal(str(latest.get("c", 0))),
            volume   = Decimal(str(latest.get("v", 0))),
        )
    except Exception as exc:
        log.warning("Could not parse daily bar for %s: %s", symbol, exc)
        return None


# ---------------------------------------------------------------------------
# Confluence output → WyckoffSignals
# ---------------------------------------------------------------------------

def _get_wyckoff_signals_for_symbol(
    symbol:       str,
    bars_cache:   dict,
    supabase_url: str,
    supabase_key: str,
) -> Optional[Any]:
    """
    Call the existing confluence bridge for a symbol and translate
    its output into a WyckoffSignals object.

    Falls back to a neutral WyckoffSignals if confluence is unavailable.
    """
    if not _BRIDGE_AVAILABLE:
        return None

    # If the full confluence bridge is available, use it
    if _CONFLUENCE_AVAILABLE:
        try:
            bars = bars_cache.get(symbol, [])
            if not bars:
                return None

            # confluence_bridge.get_confluence_scores() returns a dict
            # with weis_wave, wyckoff, behavioral_state sub-keys
            result = get_confluence_scores(
                symbol       = symbol,
                bars_daily   = bars,
                bars_5m      = [],   # daily-only for nightly cycle
                current_price= float(bars[-1].get("c", 0)),
            )
            return signals_from_confluence_output(result)

        except Exception as exc:
            log.warning("Confluence bridge error for %s: %s", symbol, exc)

    # Minimal fallback — neutral signals, no state change will trigger
    from campaign_engine.campaign_state_engine import WyckoffSignals
    return WyckoffSignals()


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

async def run_nightly_campaign_pipeline(
    bars_cache: Optional[dict] = None,
) -> dict[str, Any]:
    """
    Run the full nightly campaign evaluation cycle.

    Parameters
    ----------
    bars_cache:
        Optional override for the historical bars dict.
        Defaults to the live radar_service._historical_bars cache.

    Returns
    -------
    dict with pipeline run summary — logged and available for /health endpoint.
    """
    if not _CAMPAIGN_PIPELINE_AVAILABLE:
        log.error("Nightly campaign pipeline unavailable — missing dependencies.")
        return {"status": "unavailable", "reason": "missing dependencies"}

    started_at = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("NIGHTLY CAMPAIGN PIPELINE starting — %s", started_at.isoformat())
    log.info("=" * 60)

    bars = bars_cache or HISTORICAL_BARS
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )

    store  = CampaignStore()
    engine = build_engine(store)

    # ── 1. Fetch all active campaigns ─────────────────────────────────────
    try:
        active_campaigns: list[Campaign] = await store.fetch_active_campaigns()
    except Exception as exc:
        log.error("Could not fetch active campaigns: %s", exc)
        return {"status": "error", "reason": str(exc)}

    if not active_campaigns:
        log.info("No active campaigns — pipeline complete.")
        return {"status": "ok", "active": 0, "evaluated": 0}

    log.info("Active campaigns: %d", len(active_campaigns))

    # ── 2. Build bars and signals for each symbol ─────────────────────────
    symbols = list({c.symbol for c in active_campaigns})

    bars_by_symbol:    dict[str, DailyBar]  = {}
    signals_by_symbol: dict[str, Any]       = {}

    for symbol in symbols:
        bar = _extract_daily_bar(symbol, bars)
        if bar:
            bars_by_symbol[symbol] = bar
        else:
            log.warning("No daily bar available for %s — skipping", symbol)
            continue

        signals = _get_wyckoff_signals_for_symbol(
            symbol, bars, supabase_url, supabase_key
        )
        if signals:
            signals_by_symbol[symbol] = signals
        else:
            log.warning("No Wyckoff signals for %s — skipping", symbol)

    # ── 3. Run the FSM cycle ──────────────────────────────────────────────
    log.info(
        "Evaluating %d campaigns across %d symbols",
        len(active_campaigns), len(bars_by_symbol),
    )

    try:
        results: dict[str, CampaignState] = await engine.run_daily_cycle(
            bars_by_symbol    = bars_by_symbol,
            signals_by_symbol = signals_by_symbol,
        )
    except Exception as exc:
        log.error("Campaign engine cycle failed: %s", exc, exc_info=True)
        return {"status": "error", "reason": str(exc)}

    # ── 4. Summarise results ──────────────────────────────────────────────
    state_counts: dict[str, int] = {}
    for state in results.values():
        state_counts[state.value] = state_counts.get(state.value, 0) + 1

    closed_count   = state_counts.get("CLOSED", 0)
    active_count   = len(results) - closed_count
    elapsed        = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "status":       "ok",
        "run_at":       started_at.isoformat(),
        "elapsed_secs": round(elapsed, 1),
        "active_start": len(active_campaigns),
        "evaluated":    len(results),
        "closed":       closed_count,
        "remaining":    active_count,
        "by_state":     state_counts,
    }

    log.info("=" * 60)
    log.info("NIGHTLY CAMPAIGN PIPELINE complete in %.1fs", elapsed)
    log.info("  Evaluated : %d", len(results))
    log.info("  Closed    : %d", closed_count)
    log.info("  Remaining : %d", active_count)
    for state, count in state_counts.items():
        log.info("  %-20s: %d", state, count)
    log.info("=" * 60)

    return summary


# ---------------------------------------------------------------------------
# Sync wrapper — for the threading pattern used in main.py
# ---------------------------------------------------------------------------

def run_nightly_campaign_pipeline_sync() -> dict[str, Any]:
    """
    Synchronous wrapper for use in main.py's daemon thread pattern.

    Usage in main.py _nightly_campaign_runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_nightly_campaign_pipeline())
        loop.close()
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(run_nightly_campaign_pipeline())
    finally:
        loop.close()
