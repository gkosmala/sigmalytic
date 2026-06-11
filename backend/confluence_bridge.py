# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC — Confluence Engine Bridge
================================================================================
Version : 1.1.0  — RS benchmark fix + intraday bar pass-through
Date    : 2026-05-23

Changes from 1.0.0:
  - RS benchmark now pulled from snapshot change_pct directly (no RADAR_CACHE dependency)
  - Intraday 5m bars fetched for A/B symbols when available
  - SPY change_pct used as benchmark_change_pct for all symbols
  - VSA/Wyckoff/Candle/Behavioral now receive real intraday candles
================================================================================
"""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

log = logging.getLogger("confluence_bridge")

# ── Person's Pivots (safe import) ─────────────────────────────────────────────
try:
    from persons_pivots import calculate_from_bars, get_pivot_levels_for_chart
    _PERSONS_PIVOTS_AVAILABLE = True
except Exception as _ppe:
    _PERSONS_PIVOTS_AVAILABLE = False
    log.debug(f"Person's Pivots not loaded: {_ppe}")

# ── Weis Wave (safe import) ────────────────────────────────────────────────────
try:
    from weis_wave import score_weis_wave, score_weis_wave_enhanced
    _WEIS_AVAILABLE = True
except Exception as _we:
    _WEIS_AVAILABLE = False
    log.debug(f"Weis Wave not loaded: {_we}")

# ── Hurst Cycle (safe import) ──────────────────────────────────────────────────
try:
    from hurst_cycle import score_hurst_cycle
    _HURST_AVAILABLE = True
except Exception as _he:
    _HURST_AVAILABLE = False
    log.debug(f"Hurst Cycle not loaded: {_he}")

# ── GEX Engine (safe import) ───────────────────────────────────────────────────
try:
    from gex_engine import score_gex
    _GEX_AVAILABLE = True
except Exception as _ge:
    _GEX_AVAILABLE = False
    log.debug(f"GEX engine not loaded: {_ge}")

# ── Behavioral Memory Engine (safe import) ─────────────────────────────────────
try:
    from behavioral_memory import evaluate as bme_evaluate, train_memory_bank
    _BME_AVAILABLE = True
except Exception as _bme:
    _BME_AVAILABLE = False
    log.debug(f"Behavioral Memory Engine not loaded: {_bme}")

# Intelligence Layer symbols get full GEX + Market Tide
_INTELLIGENCE_SYMBOLS = {
    "SPY","QQQ","IWM","AAPL","NVDA","TSLA","AMD",
    "GOOG","META","AMZN","MSFT","NFLX","GLD","SMH"
}

_confluence_engine_instance = None
_confluence_import_error    = None


def _get_engine():
    global _confluence_engine_instance, _confluence_import_error
    if _confluence_engine_instance is not None:
        return _confluence_engine_instance
    if _confluence_import_error is not None:
        return None
    try:
        from confluence_engine import ConfluenceEngine
        _confluence_engine_instance = ConfluenceEngine()
        log.info("ConfluenceEngine loaded successfully.")
        return _confluence_engine_instance
    except Exception as e:
        _confluence_import_error = str(e)
        log.error(f"ConfluenceEngine failed to load: {e}")
        return None


# ── Intraday bar cache (shared across all bridge calls) ───────────────────────
# Populated lazily — fetched once per symbol per scan cycle
_intraday_cache: Dict[str, List[dict]] = {}
_intraday_last_fetch: Dict[str, float] = {}
_INTRADAY_TTL = 300   # 5 minutes — don't refetch more often than this

import time as _time


def _fetch_intraday_bars_cached(symbol: str) -> List[dict]:
    """
    Fetch 5-minute bars for a symbol, with a 5-minute TTL cache.
    Returns empty list if fetch fails or API key not available.
    """
    import os
    import requests

    now = _time.time()
    if (symbol in _intraday_cache and
            now - _intraday_last_fetch.get(symbol, 0) < _INTRADAY_TTL):
        return _intraday_cache[symbol]

    api_key    = os.getenv("ALPACA_API_KEY", "")
    api_secret = os.getenv("ALPACA_API_SECRET", "")
    base_url   = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
    feed       = os.getenv("ALPACA_FEED", "sip")

    if not api_key:
        return []

    try:
        start = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        r = requests.get(
            f"{base_url}/v2/stocks/{symbol}/bars",
            headers={"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret},
            params={"timeframe": "5Min", "start": start,
                    "feed": feed, "sort": "asc", "limit": 78},
            timeout=8,
        )
        if r.status_code == 200:
            bars = r.json().get("bars") or []
            _intraday_cache[symbol]      = bars
            _intraday_last_fetch[symbol] = now
            return bars
    except Exception as e:
        log.debug(f"Intraday fetch error {symbol}: {e}")

    return []


def _bars_to_candles(bars: List[dict]):
    """Convert Alpaca bar dicts to Candle objects."""
    try:
        from confluence_engine import Candle
    except ImportError:
        return []
    candles = []
    for b in bars:
        try:
            ts = (datetime.fromisoformat(b["t"].replace("Z", "+00:00"))
                  if b.get("t") else datetime.now(timezone.utc))
            candles.append(Candle(
                timestamp = ts,
                open      = float(b.get("o", 0)),
                high      = float(b.get("h", 0)),
                low       = float(b.get("l", 0)),
                close     = float(b.get("c", 0)),
                volume    = float(b.get("v", 0)),
            ))
        except Exception:
            continue
    return candles


# ── SPY benchmark tracker ─────────────────────────────────────────────────────
# Updated each time SPY is scored so all other symbols get a real benchmark

_spy_change_pct: Optional[float] = None


def update_spy_benchmark(change_pct: float) -> None:
    """Call this when SPY is scored to keep benchmark current."""
    global _spy_change_pct
    _spy_change_pct = change_pct


# ── Data builder ──────────────────────────────────────────────────────────────

def _build_market_data(symbol: str, snap: dict, bars: list,
                       bars_5m: List[dict]):
    try:
        from confluence_engine import MarketData, OptionsData
    except ImportError:
        return None, None

    daily_bar    = snap.get("dailyBar",    {}) or {}
    prev_daily   = snap.get("prevDailyBar", {}) or {}
    latest_trade = snap.get("latestTrade", {}) or {}

    price      = float(latest_trade.get("p", 0) or daily_bar.get("c", 0) or 0)
    prev_close = float(prev_daily.get("c", 0) or 0)
    day_open   = float(daily_bar.get("o", price) or price)
    day_high   = float(daily_bar.get("h", price) or price)
    day_low    = float(daily_bar.get("l", price) or price)
    volume     = float(daily_bar.get("v", 0) or 0)
    vwap       = float(daily_bar.get("vw", price) or price)

    # Fallback: use last historical bar close as prev_close if snapshot is missing it
    if prev_close <= 0 and bars:
        try:
            prev_close = float(bars[-2].get("c", 0) or bars[-1].get("c", 0) or 0)
        except Exception:
            pass

    if price <= 0 or prev_close <= 0:
        return None, None

    # Benchmark: use SPY tracker, fall back to snapshot change
    change_pct = ((price - prev_close) / prev_close) * 100
    if symbol == "SPY":
        update_spy_benchmark(change_pct)

    benchmark = _spy_change_pct if symbol != "SPY" else None

    # Average volume from daily bars
    bar_volumes = [float(b.get("v", 0)) for b in bars if b.get("v")]
    avg_volume  = (sum(bar_volumes[-20:]) / len(bar_volumes[-20:])
                   if len(bar_volumes) >= 20 else max(volume, 1))

    # Daily candles
    candles_daily = _bars_to_candles(bars[-60:])

    # Intraday candles
    candles_5m = _bars_to_candles(bars_5m)

    # ATR from daily bars
    atr = _calc_atr_from_bars(bars)

    # Prior day levels
    prior_high  = float(prev_daily.get("h", 0) or 0) or None
    prior_low   = float(prev_daily.get("l", 0) or 0) or None

    # 52-week levels
    bar_highs = [float(b.get("h", 0)) for b in bars if b.get("h")]
    bar_lows  = [float(b.get("l", 0)) for b in bars if b.get("l")]
    week52_high = max(bar_highs[-252:]) if len(bar_highs) >= 20 else day_high
    week52_low  = min(bar_lows[-252:])  if len(bar_lows)  >= 20 else day_low

    market = MarketData(
        symbol               = symbol,
        price                = price,
        previous_close       = prev_close,
        day_open             = day_open,
        day_high             = day_high,
        day_low              = day_low,
        volume               = volume,
        avg_volume           = avg_volume,
        vwap                 = vwap,
        atr                  = atr if atr > 0 else None,
        prior_high           = prior_high,
        prior_low            = prior_low,
        prior_close          = prev_close,
        week_high            = week52_high,
        week_low             = week52_low,
        benchmark_change_pct = benchmark,
        candles_5m           = candles_5m,
        candles_daily        = candles_daily,
    )

    # ── Person's Pivots — add to market data extra fields ────────────────────
    persons_data = {}
    if _PERSONS_PIVOTS_AVAILABLE:
        try:
            pivot_result = calculate_from_bars(bars)
            if pivot_result:
                persons_data = get_pivot_levels_for_chart(pivot_result)
        except Exception as _pe:
            pass

    # Store pivots in market data for engine access
    if persons_data:
        market.__dict__.update({"persons_pivots": persons_data})

    return market, OptionsData()


def _calc_atr_from_bars(bars: list, period: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, min(len(bars), period + 1)):
        c    = bars[-i]
        prev = bars[-(i + 1)]
        tr = max(
            float(c.get("h", 0)) - float(c.get("l", 0)),
            abs(float(c.get("h", 0)) - float(prev.get("c", 0))),
            abs(float(c.get("l", 0)) - float(prev.get("c", 0))),
        )
        trs.append(tr)
    return round(sum(trs) / len(trs), 4) if trs else 0.0


# ── Score mapper ──────────────────────────────────────────────────────────────

def _map_result(result) -> Dict[str, Any]:
    pf = result.factor_scores
    return {
        "new_composite_score"   : result.score,
        "new_confidence"        : result.confidence,
        "new_confluence"        : pf.get("C",  50.0),
        "new_expansion_node"    : pf.get("E",  50.0),
        "new_relative_strength" : pf.get("RS", 50.0),
        "new_volume_pressure"   : pf.get("VP", 50.0),
        "new_behavioral"        : pf.get("B",  50.0),
        "new_regime"            : result.regime,
        "new_status"            : result.status,
        "new_direction"         : result.direction,
        "new_setup"             : result.setup,
        "new_wyckoff_phase"     : result.wyckoff_phase,
        "new_candle_pattern"    : result.candle_pattern,
        "new_cycle_hits"        : len(result.cycle_hits),
        "new_trigger"           : result.levels.get("upside_trigger"),
        "new_lower_boundary"    : result.levels.get("downside_trigger"),
        "new_key_magnet"        : result.levels.get("key_magnet"),
        "new_bull_path"         : result.paths.get("bull_path", []),
        "new_bear_path"         : result.paths.get("bear_path", []),
        "new_neutral_zone"      : result.paths.get("neutral_zone"),
        "new_bull_narrative"    : result.paths.get("bull_narrative", ""),
        "new_bear_narrative"    : result.paths.get("bear_narrative", ""),
        "new_internal_scores"   : result.internal_scores,
        "new_engine_error"      : None,
        "ab_mode"               : True,
    }


# ── Main A/B function ─────────────────────────────────────────────────────────

def score_symbol_ab(symbol: str, snap: dict, bars: list,
                    old_result: dict) -> dict:
    engine = _get_engine()

    if engine is None:
        old_result["new_engine_error"] = _confluence_import_error or "Engine not loaded"
        old_result["ab_mode"]          = True
        old_result["score_delta"]      = 0.0
        return old_result

    try:
        # Fetch intraday bars (cached, 5-min TTL)
        bars_5m = _fetch_intraday_bars_cached(symbol)

        market, options = _build_market_data(symbol, snap, bars, bars_5m)

        if market is None:
            old_result["new_engine_error"] = "Could not build MarketData"
            old_result["ab_mode"]          = True
            old_result["score_delta"]      = 0.0
            return old_result

        result     = engine.evaluate(market, options)
        new_fields = _map_result(result)

        old_score = old_result.get("composite_score", 0)
        new_score = result.score
        new_fields["score_delta"] = round(new_score - old_score, 2)

        delta = abs(new_score - old_score)
        if delta >= 15:
            log.info(
                f"AB DIVERGENCE {symbol}: "
                f"old={old_score:.1f} new={new_score:.1f} "
                f"delta={new_score - old_score:+.1f} | "
                f"old_status={old_result.get('status')} "
                f"new_status={result.status} | "
                f"new_regime={result.regime} | "
                f"5m_bars={len(bars_5m)}"
            )

        # Add Person's Pivots data to result
        if _PERSONS_PIVOTS_AVAILABLE:
            try:
                pivot_result = calculate_from_bars(bars)
                if pivot_result:
                    new_fields["persons_pivots"] = get_pivot_levels_for_chart(pivot_result)
            except Exception:
                pass

        # Add Weis Wave scoring
        if _WEIS_AVAILABLE:
            try:
                price = market.price if market else 0
                tf = old_result.get("timeframe", "5m")
                user_thresh = old_result.get("weis_threshold")
                weis = score_weis_wave_enhanced(
                    symbol, tf, bars_5m, bars, price, user_thresh
                )
                new_fields.update(weis)
                if weis.get("weis_score", 0) > 0:
                    new_fields["weis_active"] = True
                # Log 3-bar reversals
                if weis.get("three_bar_reversal"):
                    log.info(f"3-BAR REVERSAL {symbol}: {weis['three_bar_reversal']} | {weis.get('three_bar_note','')}")
                # Log validated Springs
                if weis.get("spring_validated"):
                    log.info(f"VALIDATED SPRING {symbol}: confidence={weis.get('spring_confidence')} sc_low={weis.get('spring_sc_low')}")
            except Exception as _we:
                log.debug(f"Weis Wave scoring error {symbol}: {_we}")

        # Add Hurst Cycle scoring
        if _HURST_AVAILABLE:
            try:
                price   = market.price if market else 0
                profile = old_result.get("hurst_profile", "MEDIUM")
                hurst   = score_hurst_cycle(symbol, bars, price, profile)
                new_fields.update(hurst)
            except Exception as _he:
                log.debug(f"Hurst Cycle error {symbol}: {_he}")

        # Add GEX / Options Flow / Market Tide scoring
        if _GEX_AVAILABLE:
            try:
                price  = market.price if market else 0
                is_il  = symbol in _INTELLIGENCE_SYMBOLS
                gex    = score_gex(symbol, price, bars_5m, is_il)
                new_fields.update(gex)
            except Exception as _ge:
                log.debug(f"GEX scoring error {symbol}: {_ge}")

        # Add Behavioral Memory Engine scoring
        if _BME_AVAILABLE:
            try:
                price         = market.price if market else 0
                weis_signal   = new_fields.get("weis_signal", "NONE")
                wyckoff_phase = new_fields.get("new_wyckoff_phase", "")
                gex_regime    = new_fields.get("gex_regime", "NEUTRAL")
                whale_sweep   = new_fields.get("gex_sweep_bias") == "BULLISH"

                bme = bme_evaluate(
                    symbol        = symbol,
                    current_price = price,
                    bars_5m       = bars_5m,
                    weis_signal   = weis_signal,
                    wyckoff_phase = str(wyckoff_phase),
                    gex_regime    = gex_regime,
                    whale_sweeping= whale_sweep,
                )
                new_fields.update(bme)
            except Exception as _bme_e:
                log.debug(f"BME scoring error {symbol}: {_bme_e}")

        return {**old_result, **new_fields}

    except Exception as e:
        log.warning(f"ConfluenceEngine error for {symbol}: {e}")
        log.debug(traceback.format_exc())
        old_result["new_engine_error"] = str(e)
        old_result["ab_mode"]          = True
        old_result["score_delta"]      = 0.0
        return old_result


# ── AB Summary ────────────────────────────────────────────────────────────────

def ab_summary(scored: List[dict]) -> Dict[str, Any]:
    ab_results = [s for s in scored if s.get("ab_mode")]
    if not ab_results:
        return {"ab_count": 0}

    errors    = [s for s in ab_results if s.get("new_engine_error")]
    successes = [s for s in ab_results if not s.get("new_engine_error")]

    if not successes:
        return {"ab_count": len(ab_results), "errors": len(errors)}

    deltas     = [s.get("score_delta", 0) for s in successes]
    old_scores = [s.get("composite_score", 0) for s in successes]
    new_scores = [s.get("new_composite_score", 0) for s in successes]

    status_agree = sum(1 for s in successes
                       if s.get("status") == s.get("new_status"))

    large_divs     = [s for s in successes if abs(s.get("score_delta", 0)) >= 15]
    large_div_syms = [(s["symbol"],
                       round(s.get("composite_score", 0), 1),
                       round(s.get("new_composite_score", 0), 1),
                       s.get("status"),
                       s.get("new_status"))
                      for s in large_divs[:10]]

    # RS health check — flag if RS is suspiciously flat
    rs_values  = [s.get("new_relative_strength", 0) for s in successes]
    rs_unique  = len(set(round(v, 1) for v in rs_values))
    rs_warning = rs_unique <= 3   # flag if fewer than 3 distinct RS values

    return {
        "ab_count"             : len(ab_results),
        "success_count"        : len(successes),
        "error_count"          : len(errors),
        "avg_old_score"        : round(sum(old_scores) / len(old_scores), 2),
        "avg_new_score"        : round(sum(new_scores) / len(new_scores), 2),
        "avg_delta"            : round(sum(deltas) / len(deltas), 2),
        "max_delta"            : round(max(deltas), 2),
        "min_delta"            : round(min(deltas), 2),
        "status_agreement_pct" : round(status_agree / len(successes) * 100, 1),
        "large_divergences"    : len(large_divs),
        "large_div_samples"    : large_div_syms,
        "spy_benchmark"        : _spy_change_pct,
        "rs_warning"           : rs_warning,
        "rs_unique_values"     : rs_unique,
    }

