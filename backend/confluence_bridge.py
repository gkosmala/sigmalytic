"""
================================================================================
SIGMALYTIC — Confluence Engine Bridge
================================================================================
Purpose : Run the new ConfluenceEngine in parallel with the existing
          shared/engine.py score_symbol() function.

Phase   : A/B Mode — both engines run every scan cycle.
          Old engine remains primary (frontend keys unchanged).
          New engine scores are logged alongside for comparison.

Integration : This file is imported by radar_service.py.
              Call score_symbol_ab(symbol, snap, bars) instead of
              score_symbol(symbol, snap, bars).

Output keys added to each result dict:
    new_composite_score   — confluence engine composite (0–100)
    new_confidence        — confluence engine confidence
    new_confluence        — C factor (maps to old 'confluence')
    new_expansion_node    — E factor (maps to old 'expansion_node')
    new_relative_strength — RS factor (maps to old 'relative_strength')
    new_volume_pressure   — VP factor (maps to old 'volume_pressure')
    new_behavioral        — B factor (maps to old 'behavioral')
    new_regime            — confluence engine regime
    new_status            — confluence engine status
    new_direction         — confluence engine direction
    new_setup             — confluence engine setup label
    new_wyckoff_phase     — Wyckoff phase
    new_candle_pattern    — candle pattern
    new_trigger           — confluence engine upside trigger
    new_lower_boundary    — confluence engine downside trigger
    new_bull_path         — bull path targets
    new_bear_path         — bear path targets
    new_engine_error      — error message if confluence engine failed
    score_delta           — new_composite_score minus old composite_score
    ab_mode               — always True (flag for logging/filtering)

Frontend impact : ZERO. All existing keys are untouched.

Author  : Sigmalytic Quant Corp
================================================================================
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("confluence_bridge")

# ── Lazy import of confluence engine ─────────────────────────────────────────
# We import lazily so a confluence engine import error never crashes the
# existing radar scan. If it fails, old scores still flow normally.

_confluence_engine_instance = None
_confluence_import_error    = None


def _get_engine():
    """Return a singleton ConfluenceEngine, importing on first call."""
    global _confluence_engine_instance, _confluence_import_error

    if _confluence_engine_instance is not None:
        return _confluence_engine_instance

    if _confluence_import_error is not None:
        return None  # Already failed — don't retry every scan

    try:
        from confluence_engine import ConfluenceEngine
        _confluence_engine_instance = ConfluenceEngine()
        log.info("ConfluenceEngine loaded and initialized successfully.")
        return _confluence_engine_instance
    except Exception as e:
        _confluence_import_error = str(e)
        log.error(f"ConfluenceEngine failed to load: {e}")
        return None


# ── Data builder — Alpaca snapshot → MarketData ───────────────────────────────

def _build_market_data(symbol: str, snap: dict, bars: list):
    """
    Convert Alpaca snapshot + historical bars into a MarketData object
    for the confluence engine.

    Alpaca snapshot structure:
        snap["dailyBar"]    — today's OHLCV
        snap["prevDailyBar"]— yesterday's OHLCV
        snap["minuteBar"]   — latest 1-min bar
        snap["latestTrade"] — most recent trade
        snap["latestQuote"] — most recent quote

    bars — list of daily bar dicts from fetch_bars_batch()
        Each bar: {"o", "h", "l", "c", "v", "vw", "t"}
    """
    try:
        from confluence_engine import (
            MarketData, OptionsData, Candle, Direction
        )
    except ImportError:
        return None, None

    daily_bar  = snap.get("dailyBar",    {}) or {}
    prev_daily = snap.get("prevDailyBar", {}) or {}
    latest_trade = snap.get("latestTrade", {}) or {}

    price      = float(latest_trade.get("p", 0) or daily_bar.get("c", 0) or 0)
    prev_close = float(prev_daily.get("c", 0) or 0)
    day_open   = float(daily_bar.get("o", price) or price)
    day_high   = float(daily_bar.get("h", price) or price)
    day_low    = float(daily_bar.get("l", price) or price)
    volume     = float(daily_bar.get("v", 0) or 0)
    vwap       = float(daily_bar.get("vw", price) or price)

    if price <= 0 or prev_close <= 0:
        return None, None

    # Average volume from historical bars
    bar_volumes = [float(b.get("v", 0)) for b in bars if b.get("v")]
    avg_volume  = (sum(bar_volumes[-20:]) / len(bar_volumes[-20:])
                   if len(bar_volumes) >= 20 else volume)

    # Build daily Candle objects from historical bars
    candles_daily = []
    now_utc = datetime.now(timezone.utc)
    for b in bars[-60:]:   # last 60 daily bars
        try:
            ts = datetime.fromisoformat(b["t"].replace("Z", "+00:00")) if b.get("t") else now_utc
            candles_daily.append(Candle(
                timestamp = ts,
                open      = float(b.get("o", 0)),
                high      = float(b.get("h", 0)),
                low       = float(b.get("l", 0)),
                close     = float(b.get("c", 0)),
                volume    = float(b.get("v", 0)),
            ))
        except Exception:
            continue

    # Prior day levels from prev bar
    prior_high  = float(prev_daily.get("h", 0) or 0) or None
    prior_low   = float(prev_daily.get("l", 0) or 0) or None
    prior_close = float(prev_daily.get("c", 0) or 0) or None

    # ATR from daily bars (14-period)
    atr = _calc_atr_from_candles(candles_daily, 14)

    # 52-week high/low from bars
    bar_highs = [float(b.get("h", 0)) for b in bars if b.get("h")]
    bar_lows  = [float(b.get("l", 0)) for b in bars if b.get("l")]
    week52_high = max(bar_highs[-252:]) if len(bar_highs) >= 20 else day_high
    week52_low  = min(bar_lows[-252:])  if len(bar_lows)  >= 20 else day_low

    market = MarketData(
        symbol         = symbol,
        price          = price,
        previous_close = prev_close,
        day_open       = day_open,
        day_high       = day_high,
        day_low        = day_low,
        volume         = volume,
        avg_volume     = avg_volume,
        vwap           = vwap,
        atr            = atr if atr > 0 else None,
        prior_high     = prior_high,
        prior_low      = prior_low,
        prior_close    = prior_close,
        week_high      = week52_high,
        week_low       = week52_low,
        candles_daily  = candles_daily,
        # 5m and 1h candles not available from daily snapshot
        # TODO: add intraday bars fetch here when available
        # This will significantly improve: candle patterns, VSA, Wyckoff, behavioral
    )

    options = OptionsData()   # No options data yet — placeholder

    return market, options


def _calc_atr_from_candles(candles, period: int = 14) -> float:
    """True Range ATR from Candle list."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        c    = candles[i]
        prev = candles[i - 1]
        tr = max(
            c.high - c.low,
            abs(c.high - prev.close),
            abs(c.low  - prev.close),
        )
        trs.append(tr)
    recent = trs[-period:]
    return round(sum(recent) / len(recent), 4) if recent else 0.0


# ── Score mapper — ConfluenceResult → frontend-safe dict ──────────────────────

def _map_result(result) -> Dict[str, Any]:
    """
    Map ConfluenceResult to the dict keys the frontend already expects.
    All new keys are prefixed with 'new_' to avoid collision.
    """
    pf = result.factor_scores   # C, E, RS, VP, B

    return {
        # New engine composite (does NOT replace old composite_score)
        "new_composite_score"   : result.score,
        "new_confidence"        : result.confidence,

        # Mapped to old frontend factor key names
        "new_confluence"        : pf.get("C",  50.0),
        "new_expansion_node"    : pf.get("E",  50.0),
        "new_relative_strength" : pf.get("RS", 50.0),
        "new_volume_pressure"   : pf.get("VP", 50.0),
        "new_behavioral"        : pf.get("B",  50.0),

        # New engine classification fields
        "new_regime"            : result.regime,
        "new_status"            : result.status,
        "new_direction"         : result.direction,
        "new_setup"             : result.setup,

        # New engine detail
        "new_wyckoff_phase"     : result.wyckoff_phase,
        "new_candle_pattern"    : result.candle_pattern,
        "new_cycle_hits"        : len(result.cycle_hits),

        # New engine levels
        "new_trigger"           : result.levels.get("upside_trigger"),
        "new_lower_boundary"    : result.levels.get("downside_trigger"),
        "new_key_magnet"        : result.levels.get("key_magnet"),

        # New engine paths
        "new_bull_path"         : result.paths.get("bull_path", []),
        "new_bear_path"         : result.paths.get("bear_path", []),
        "new_neutral_zone"      : result.paths.get("neutral_zone"),
        "new_bull_narrative"    : result.paths.get("bull_narrative", ""),
        "new_bear_narrative"    : result.paths.get("bear_narrative", ""),

        # Internal scores (for logging/analysis — not displayed on frontend)
        "new_internal_scores"   : result.internal_scores,

        # A/B metadata
        "new_engine_error"      : None,
        "ab_mode"               : True,
    }


# ── Main A/B function ─────────────────────────────────────────────────────────

def score_symbol_ab(symbol: str, snap: dict, bars: list,
                    old_result: dict) -> dict:
    """
    Run the new ConfluenceEngine alongside the old result.

    Parameters
    ----------
    symbol     : ticker symbol
    snap       : Alpaca snapshot dict
    bars       : historical daily bars list
    old_result : already-scored dict from existing score_symbol()

    Returns
    -------
    Merged dict: old_result + new engine fields.
    If the new engine fails for any reason, old_result is returned unchanged
    with new_engine_error populated.
    """
    engine = _get_engine()

    if engine is None:
        old_result["new_engine_error"] = _confluence_import_error or "Engine not loaded"
        old_result["ab_mode"]          = True
        old_result["score_delta"]      = 0.0
        return old_result

    try:
        market, options = _build_market_data(symbol, snap, bars)

        if market is None:
            old_result["new_engine_error"] = "Could not build MarketData — price or prev_close missing"
            old_result["ab_mode"]          = True
            old_result["score_delta"]      = 0.0
            return old_result

        result     = engine.evaluate(market, options)
        new_fields = _map_result(result)

        # Score delta: positive = new engine is higher, negative = old is higher
        old_score            = old_result.get("composite_score", 0)
        new_score            = result.score
        new_fields["score_delta"] = round(new_score - old_score, 2)

        # Log meaningful divergences
        delta = abs(new_score - old_score)
        if delta >= 15:
            log.info(
                f"AB DIVERGENCE {symbol}: "
                f"old={old_score:.1f} new={new_score:.1f} "
                f"delta={new_score - old_score:+.1f} | "
                f"old_status={old_result.get('status')} "
                f"new_status={result.status} | "
                f"new_regime={result.regime}"
            )
        elif delta >= 8:
            log.debug(
                f"AB {symbol}: old={old_score:.1f} new={new_score:.1f} "
                f"delta={new_score - old_score:+.1f}"
            )

        # Merge: old result is primary, new fields added alongside
        merged = {**old_result, **new_fields}
        return merged

    except Exception as e:
        log.warning(f"ConfluenceEngine error for {symbol}: {e}")
        log.debug(traceback.format_exc())
        old_result["new_engine_error"] = str(e)
        old_result["ab_mode"]          = True
        old_result["score_delta"]      = 0.0
        return old_result


# ── AB Summary reporter ───────────────────────────────────────────────────────

def ab_summary(scored: List[dict]) -> Dict[str, Any]:
    """
    Summarize A/B comparison across a full scan cycle.
    Call this after each scan to get aggregate comparison stats.
    Log or store these for the validation period.
    """
    ab_results = [s for s in scored if s.get("ab_mode")]
    if not ab_results:
        return {"ab_count": 0}

    errors    = [s for s in ab_results if s.get("new_engine_error")]
    successes = [s for s in ab_results if not s.get("new_engine_error")]

    if not successes:
        return {"ab_count": len(ab_results), "errors": len(errors)}

    deltas         = [s.get("score_delta", 0) for s in successes]
    old_scores     = [s.get("composite_score", 0) for s in successes]
    new_scores     = [s.get("new_composite_score", 0) for s in successes]

    # Status agreement: how often do old and new agree on status?
    status_agree   = sum(1 for s in successes
                         if s.get("status") == s.get("new_status"))

    # Large divergences (delta >= 15) — most interesting for validation
    large_divs     = [s for s in successes if abs(s.get("score_delta", 0)) >= 15]
    large_div_syms = [(s["symbol"],
                       round(s.get("composite_score", 0), 1),
                       round(s.get("new_composite_score", 0), 1),
                       s.get("status"),
                       s.get("new_status"))
                      for s in large_divs[:10]]

    return {
        "ab_count"          : len(ab_results),
        "success_count"     : len(successes),
        "error_count"       : len(errors),
        "avg_old_score"     : round(sum(old_scores) / len(old_scores), 2),
        "avg_new_score"     : round(sum(new_scores) / len(new_scores), 2),
        "avg_delta"         : round(sum(deltas) / len(deltas), 2),
        "max_delta"         : round(max(deltas), 2),
        "min_delta"         : round(min(deltas), 2),
        "status_agreement_pct": round(status_agree / len(successes) * 100, 1),
        "large_divergences" : len(large_divs),
        "large_div_samples" : large_div_syms,
    }
