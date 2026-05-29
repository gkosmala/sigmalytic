# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/radar_service.py
------------------------
Sigmalytic Radar — Two-Layer Intelligence Architecture

LAYER 1 — Market Radar (Universe)
──────────────────────────────────
1,429 symbols | 8-minute scan | daily bars | lightweight composite score only
Purpose: broad surveillance, finds candidates, feeds watchlist

LAYER 2 — Divergence Watchlist (EOD Audit)
───────────────────────────────────────────
Runs nightly at 8:30 PM ET on full universe
Compares composite score vs full ConfluenceEngine score
Symbols with delta ≥ 15 or ≤ -15 written to divergence_watchlist in Supabase
Next day: only divergence watchlist symbols get heavy intraday scoring

ENDPOINTS
─────────────────────────────────────────────────────────────────────────────
GET /api/radar/scores              — top 100 symbols by composite score
GET /api/radar/symbol/{symbol}     — full detail for one symbol
GET /api/radar/status              — service health, scan times, engine status
GET /api/radar/health              — deep health check with heartbeat
GET /api/radar/divergence          — current divergence watchlist
GET /api/radar/intelligence        — deep scores for divergence watchlist
GET /api/radar/intelligence/{symbol} — full intelligence detail for one symbol
POST /api/radar/watchlist          — add symbol to user watchlist
GET /api/radar/watchlist/{user_id} — get user watchlist with scores
"""

from __future__ import annotations
import os
import uuid
import logging
import time
import threading
import pathlib
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set

import requests as _req
import psycopg2
import psycopg2.extras
import redis as _redis
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

from supabase_isolation import get_user_id_from_request
from radar_alerts import maybe_send_alert, send_daily_summary
from scoreboard_service import log_signal, grade_pending_signals
from sms_alerts import maybe_send_sms

# ── Redis heartbeat client ─────────────────────────────────────────────────────
try:
    _redis_url = os.getenv("REDIS_URL", "")
    if _redis_url:
        _redis_client = _redis.Redis.from_url(
            _redis_url,
            decode_responses=True,
            socket_timeout=2
        )
    else:
        _redis_client = _redis.Redis(
            host="localhost",
            port=6379,
            db=0,
            decode_responses=True,
            socket_timeout=2
        )
except Exception:
    _redis_client = None

# ── Confluence bridge (safe import) ───────────────────────────────────────────
try:
    from confluence_bridge import score_symbol_ab, ab_summary as _ab_summary
    _CONFLUENCE_AVAILABLE = True
except Exception as _ce:
    _CONFLUENCE_AVAILABLE = False
    logging.getLogger("radar").warning(f"Confluence bridge not loaded: {_ce}")

# ── Weis Wave radar scoring (safe import) ──────────────────────────────────────
try:
    from weis_wave import score_weis_wave_radar
    _WEIS_RADAR_AVAILABLE = True
except Exception as _we:
    _WEIS_RADAR_AVAILABLE = False
    logging.getLogger("radar").warning(f"Weis Wave radar not loaded: {_we}")

# ── GEX engine (safe import) ───────────────────────────────────────────────────
try:
    from gex_engine import score_gex
    _GEX_AVAILABLE = True
except Exception as _ge:
    _GEX_AVAILABLE = False
    logging.getLogger("radar").warning(f"GEX engine not loaded: {_ge}")

# ── Confluence engine direct import for divergence scoring ─────────────────────
try:
    from confluence_engine import (
        ConfluenceEngine, MarketData, OptionsData, Candle, Direction
    )
    _intelligence_engine = ConfluenceEngine()
    _INTELLIGENCE_AVAILABLE = True
except Exception as _ie:
    _INTELLIGENCE_AVAILABLE = False
    _intelligence_engine   = None
    logging.getLogger("radar").warning(f"Intelligence engine not loaded: {_ie}")

log = logging.getLogger("radar")

# ── Config ─────────────────────────────────────────────────────────────────────

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_FEED       = os.getenv("ALPACA_FEED", "iex")
DATABASE_URL      = os.getenv("DATABASE_URL", "")

SCAN_INTERVAL_SECONDS = 480   # 8 minutes — lightweight only, completes fast
GEX_FOCUS_SYMBOLS = ["SPY","QQQ","IWM","AAPL","NVDA","TSLA","AMD","META","MSFT","AMZN"]
SNAPSHOT_INTERVAL     = 300
SCORE_THRESHOLD       = 75
TOP_N                 = 100

DIVERGENCE_THRESHOLD  = 15.0  # delta ≥ 15 or ≤ -15 flagged

# ── In-memory caches ──────────────────────────────────────────────────────────

RADAR_CACHE:        Dict[str, dict] = {}
INTELLIGENCE_CACHE: Dict[str, dict] = {}  # divergence watchlist deep scores
DIVERGENCE_WATCHLIST: List[dict]    = []  # populated by EOD audit

LAST_SCAN_TIME:         Optional[float] = None
GEX_SCORE_CACHE:        Dict[str, dict]  = {}   # symbol → {gex_score, gex_regime, gex_wall, ts}
GEX_CACHE_TTL           = 1800  # 30 minutes
LAST_INTELLIGENCE_TIME: Optional[float] = None
LAST_EOD_AUDIT_TIME:    Optional[float] = None
SYMBOLS: List[str] = []
_prev_statuses: Dict[str, str]       = {}
_last_snapshot_times: Dict[str, float] = {}

# ── Router ─────────────────────────────────────────────────────────────────────

radar_router = APIRouter(prefix="/api/radar", tags=["radar"])

class WatchlistAdd(BaseModel):
    symbol: str
    notes:  str = ""

# ── Symbol universe ────────────────────────────────────────────────────────────

def load_russell1000() -> List[str]:
    csv_path = pathlib.Path(__file__).parent / "data" / "russell1000.csv"
    if not csv_path.exists():
        log.warning("russell1000.csv not found — using fallback universe")
        return _fallback_universe()
    symbols = []
    with open(csv_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.lower().startswith("symbol"):
                continue
            sym = line.split(",")[0].strip().upper()
            if sym and 1 <= len(sym) <= 5 and sym.isalpha():
                symbols.append(sym)
    log.info(f"Loaded {len(symbols)} symbols from russell1000.csv")
    benchmarks = ["SPY", "QQQ", "IWM", "GLD", "SMH"]
    for b in benchmarks:
        if b not in symbols:
            symbols.append(b)
    return symbols if symbols else _fallback_universe()


def _fallback_universe() -> List[str]:
    return [
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA",
        "JPM","BAC","GS","MS","WFC",
        "UNH","JNJ","PFE","ABBV","MRK",
        "XOM","CVX","COP",
        "HD","WMT","COST","TGT",
        "CAT","BA","RTX","GE",
        "AMD","INTC","QCOM","AVGO",
        "SPY","QQQ","IWM",
    ]

# ── Alpaca helpers ─────────────────────────────────────────────────────────────

def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def fetch_snapshots(symbols: List[str]) -> dict:
    results = {}
    batch_size = 1000
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        try:
            r = _req.get(
                f"{ALPACA_BASE_URL}/v2/stocks/snapshots",
                headers=_alpaca_headers(),
                params={"symbols": ",".join(batch), "feed": ALPACA_FEED},
                timeout=15,
            )
            if r.status_code == 200:
                results.update(r.json())
            elif r.status_code == 429:
                log.warning("Alpaca rate limit hit — skipping batch")
            else:
                log.warning(f"Alpaca snapshot error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"Snapshot fetch error: {e}")
    return results


def fetch_bars_batch(symbols: List[str], timeframe: str = "1Day", limit: int = 60) -> dict:
    results    = {}
    start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    for symbol in symbols:
        try:
            r = _req.get(
                f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
                headers=_alpaca_headers(),
                params={
                    "timeframe": timeframe, "start": start_date,
                    "feed": ALPACA_FEED, "sort": "asc", "adjustment": "raw",
                },
                timeout=10,
            )
            if r.status_code == 200:
                bars = r.json().get("bars") or []
                if bars:
                    results[symbol] = bars
            elif r.status_code == 429:
                log.warning("Rate limit during bar fetch — pausing 5s")
                time.sleep(5)
        except Exception as e:
            log.debug(f"Bar fetch error {symbol}: {e}")
        time.sleep(0.02)
    log.info(f"Bar fetch complete — {len(results)}/{len(symbols)} symbols")
    return results


def fetch_intraday_bars(symbol: str, timeframe: str = "5Min",
                        limit: int = 78) -> List[dict]:
    try:
        start_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
            headers=_alpaca_headers(),
            params={
                "timeframe": timeframe,
                "start":     start_date,
                "feed":      ALPACA_FEED,
                "sort":      "asc",
                "limit":     limit,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("bars") or []
        log.debug(f"Intraday bar fetch {symbol} {timeframe}: {r.status_code}")
    except Exception as e:
        log.debug(f"Intraday bar error {symbol}: {e}")
    return []

# ── Layer 1 — Lightweight scoring engine (universe) ───────────────────────────

def score_symbol(symbol: str, snap: dict, bars: list) -> dict:
    daily_bar    = snap.get("dailyBar",    {}) or {}
    prev_daily   = snap.get("prevDailyBar", {}) or {}
    latest_trade = snap.get("latestTrade", {}) or {}

    price      = float(latest_trade.get("p", 0) or daily_bar.get("c", 0) or 0)
    volume     = float(daily_bar.get("v", 0) or 0)
    prev_close = float(prev_daily.get("c", 1) or 1)
    day_open   = float(daily_bar.get("o", price) or price)
    day_high   = float(daily_bar.get("h", price) or price)
    day_low    = float(daily_bar.get("l", price) or price)
    day_close  = float(daily_bar.get("c", price) or price)
    vwap       = float(daily_bar.get("vw", price) or price)

    if price <= 0 or prev_close <= 0:
        return {}

    change_pct = ((price - prev_close) / prev_close) * 100
    closes     = [float(b.get("c", 0)) for b in bars if b.get("c")]
    volumes    = [float(b.get("v", 0)) for b in bars if b.get("v")]
    highs      = [float(b.get("h", 0)) for b in bars if b.get("h")]
    lows       = [float(b.get("l", 0)) for b in bars if b.get("l")]

    ma20       = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 20 else price
    ma50       = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else price
    avg_vol_20 = sum(volumes[-20:]) / len(volumes[-20:]) if len(volumes) >= 20 else volume

    atr     = _calc_atr(highs, lows, closes, 14)
    rel_vol = (volume / avg_vol_20) if avg_vol_20 > 0 else 1.0

    high_52w = max(highs[-252:]) if len(highs) >= 52 else day_high
    low_52w  = min(lows[-252:])  if len(lows)  >= 52 else day_low

    confluence = 50.0
    if price > vwap:          confluence += 8
    if price > ma20:          confluence += 8
    if price > ma50:          confluence += 6
    if price > day_open:      confluence += 5
    if change_pct > 0:        confluence += 5
    if rel_vol > 1.5:         confluence += 8
    if rel_vol > 2.0:         confluence += 4
    if day_close > day_open:  confluence += 3
    if price > prev_close:    confluence += 3
    confluence = _clamp(confluence)

    expansion = 50.0
    if atr > 0:
        rng_ratio = (day_high - day_low) / atr
        if rng_ratio < 0.6:   expansion += 20
        elif rng_ratio < 0.8: expansion += 10
        elif rng_ratio > 1.5: expansion -= 10
    dist_52w = ((high_52w - price) / high_52w) if high_52w > 0 else 1
    if dist_52w < 0.02:   expansion += 15
    elif dist_52w < 0.05: expansion += 8
    elif dist_52w > 0.20: expansion -= 10
    if rel_vol > 1.3 and change_pct > 0: expansion += 7
    expansion = _clamp(expansion)

    rel_strength = 50.0
    if len(closes) >= 20:
        perf_1m = ((price - closes[-20]) / closes[-20] * 100) if closes[-20] > 0 else 0
        if perf_1m > 5:    rel_strength += 20
        elif perf_1m > 2:  rel_strength += 12
        elif perf_1m > 0:  rel_strength += 5
        elif perf_1m < -5: rel_strength -= 15
        elif perf_1m < -2: rel_strength -= 8
    if price > ma20 > ma50: rel_strength += 10
    if price < ma20 < ma50: rel_strength -= 10
    rel_strength = _clamp(rel_strength)

    vol_pressure = 50.0
    if rel_vol > 3.0:   vol_pressure += 30
    elif rel_vol > 2.0: vol_pressure += 20
    elif rel_vol > 1.5: vol_pressure += 12
    elif rel_vol > 1.2: vol_pressure += 6
    elif rel_vol < 0.7: vol_pressure -= 15
    elif rel_vol < 0.5: vol_pressure -= 25
    if change_pct > 0 and rel_vol > 1.5: vol_pressure += 5
    if change_pct < 0 and rel_vol > 1.5: vol_pressure -= 5
    vol_pressure = _clamp(vol_pressure)

    behavioral = 50.0
    if day_close > day_open:        behavioral += 10
    if price > vwap:                behavioral += 8
    if day_low > prev_close * 0.98: behavioral += 8
    if change_pct > 2:              behavioral += 8
    if change_pct > 5:              behavioral += 7
    if change_pct < -3:             behavioral -= 15
    if day_close < day_open:        behavioral -= 8
    behavioral = _clamp(behavioral)

    composite = _clamp(round(
        confluence   * 0.25 +
        expansion    * 0.20 +
        rel_strength * 0.20 +
        vol_pressure * 0.20 +
        behavioral   * 0.15, 1
    ))

    setup_type   = _classify_setup(price, ma20, ma50, atr, day_high, day_low,
                                   high_52w, rel_vol, change_pct, closes)
    trigger      = round(day_high + atr * 0.1, 2) if atr > 0 else round(price * 1.005, 2)
    invalidation = round(day_low  - atr * 0.1, 2) if atr > 0 else round(price * 0.99,  2)
    target1      = round(price + atr * 1.0, 2)
    target2      = round(price + atr * 2.0, 2)
    prev_status  = _prev_statuses.get(symbol, "")
    status       = _determine_status(composite, expansion, rel_vol, change_pct,
                                     price=price, trigger=trigger,
                                     invalidation=invalidation,
                                     prev_status=prev_status, ma20=ma20, ma50=ma50)
    regime       = _infer_regime(change_pct, rel_vol, price, ma20, ma50)

    # ── BME scoring ──────────────────────────────────────────────────────────
    bme_score  = None
    bme_regime = None
    try:
        from behavioral_memory import evaluate as _bme_evaluate
        bme_result = _bme_evaluate(
            symbol       = symbol,
            current_price= price,
            bars_5m      = [],   # 5m bars not available in lightweight scan
            weis_signal  = "NONE",
            gex_regime   = "NEUTRAL",
        )
        bme_score  = bme_result.get("bme_score")
        bme_regime = bme_result.get("bme_regime")
        # Blend BME score into behavioral factor
        if bme_score is not None and bme_score != 50.0:
            behavioral = _clamp(round(behavioral * 0.6 + bme_score * 0.4, 1))
    except Exception:
        pass

    return {
        "symbol":            symbol,
        "price":             round(price, 2),
        "change_pct":        round(change_pct, 2),
        "volume":            int(volume),
        "rel_volume":        round(rel_vol, 2),
        "composite_score":   composite,
        "confluence":        round(confluence, 1),
        "expansion_node":    round(expansion, 1),
        "relative_strength": round(rel_strength, 1),
        "volume_pressure":   round(vol_pressure, 1),
        "behavioral":        round(behavioral, 1),
        "setup_type":        setup_type,
        "status":            status,
        "trigger":           trigger,
        "invalidation":      invalidation,
        "target1":           target1,
        "target2":           target2,
        "regime":            regime,
        "vwap":              round(vwap, 2),
        "ma20":              round(ma20, 2),
        "ma50":              round(ma50, 2),
        "atr":               round(atr, 2),
        "high_52w":          round(high_52w, 2),
        "low_52w":           round(low_52w, 2),
        "updated_at":        datetime.now(timezone.utc).isoformat(),
        "data_delay":        "15min" if ALPACA_FEED == "iex" else "live",
        "trigger_proximity": round((trigger - price) / price * 100, 2)
                             if price > 0 and trigger > 0 else 0,
        "on_divergence_watchlist": False,
        "weis_signal"       : None,
        "weis_score"        : None,
        "weis_macro_bias"   : None,
        "three_bar_reversal": None,
        "bme_score"         : round(bme_score, 1) if bme_score is not None else None,
        "bme_regime"        : bme_regime,
    }


def _calc_atr(highs, lows, closes, period=14) -> float:
    if len(highs) < period + 1:
        return (highs[-1] - lows[-1]) if highs and lows else 1.0
    trs = []
    for i in range(1, len(highs)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i]  - closes[i-1]))
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 4)


def _clamp(v: float, lo=0.0, hi=100.0) -> float:
    return max(lo, min(hi, v))


def _classify_setup(price, ma20, ma50, atr, day_high, day_low,
                    high_52w, rel_vol, change_pct, closes) -> str:
    if len(closes) < 5:
        return "Insufficient data"
    recent_range  = max(closes[-5:]) - min(closes[-5:])
    avg_range     = atr * 5 if atr > 0 else recent_range
    compressed    = recent_range < avg_range * 0.6
    near_52w_high = high_52w > 0 and ((high_52w - price) / high_52w) < 0.03
    if compressed and near_52w_high:                       return "Compression Breakout Candidate"
    if compressed:                                          return "Volatility Expansion Candidate"
    if change_pct > 2 and rel_vol > 1.5 and price > ma20: return "Trend Continuation"
    if change_pct > 1 and price > ma20 > ma50:            return "Momentum Leader"
    if change_pct < -3 and rel_vol > 1.5:                 return "Breakdown Risk"
    if change_pct < -1 and price < ma20:                  return "Distribution"
    if abs(change_pct) < 0.5 and rel_vol < 0.8:           return "Low Edge — Avoid"
    return "Monitoring"


def _determine_status(composite, expansion, rel_vol, change_pct,
                      price=0, trigger=0, invalidation=0,
                      prev_status="", ma20=0, ma50=0) -> str:
    if invalidation > 0 and price <= invalidation and rel_vol >= 1.2 and change_pct < -2:
        return "Short Trigger"
    if prev_status == "Short Trigger" and price <= invalidation * 1.002:
        return "Short Confirmed"
    if change_pct < -1.5 and rel_vol >= 1.1 and invalidation > 0 and price > 0:
        if (price - invalidation) / price <= 0.01 and price < ma20:
            return "Short Armed"
    if trigger > 0 and price >= trigger and rel_vol >= 1.2:
        return "Triggered"
    if prev_status == "Triggered" and price >= trigger * 0.998:
        return "Confirmed"
    if prev_status in ("Triggered", "Confirmed") and invalidation > 0 and price < invalidation:
        return "Failed"
    if composite >= 75 and expansion >= 60:
        if trigger > 0 and price > 0 and (trigger - price) / price <= 0.015:
            return "Armed"
        elif not (trigger > 0 and price > 0):
            return "Armed"
    if composite >= 68:
        return "Building"
    if change_pct < -3 or composite < 45:
        return "Avoid"
    return "Watching"


def _infer_regime(change_pct, rel_vol, price, ma20, ma50) -> str:
    if price > ma20 > ma50 and change_pct > 1:  return "Bull Expansion"
    if price > ma20 > ma50 and change_pct < 0:  return "Bull Pullback"
    if price < ma20 < ma50 and change_pct < -1: return "Bear Expansion"
    if price < ma20 < ma50 and change_pct > 0:  return "Bear Rally"
    if abs(change_pct) < 0.3 and rel_vol < 0.8: return "Compression"
    return "Neutral"

# ── Historical bars ────────────────────────────────────────────────────────────

_historical_bars: Dict[str, list] = {}
_bars_last_refresh: float = 0
_bars_loading: bool = False


def _refresh_historical_bars():
    global _historical_bars, _bars_last_refresh, _bars_loading
    _bars_loading = True
    log.info("Refreshing historical bars…")
    try:
        raw = fetch_bars_batch(SYMBOLS, timeframe="1Day", limit=60)
        for sym, bars in raw.items():
            _historical_bars[sym] = bars
        _bars_last_refresh = time.time()
        log.info(f"Historical bars loaded for {len(_historical_bars)} symbols")
        # ── Trigger BME training immediately after bars load ───────────────────
        try:
            from behavioral_memory import train_batch as _bme_train
            trained = _bme_train(dict(_historical_bars))
            log.info(f"BME training triggered from bar refresh: {trained}/{len(_historical_bars)} symbols")
        except Exception as _bme_e:
            log.warning(f"BME training from bar refresh failed: {_bme_e}")
    except Exception as e:
        log.warning(f"Historical bar refresh failed: {e}")
    finally:
        _bars_loading = False

# ── GEX score helper ──────────────────────────────────────────────────────────

def _gex_score_from_cache(symbol: str) -> dict:
    """Return cached GEX result if fresh, else empty."""
    cached = GEX_SCORE_CACHE.get(symbol, {})
    if cached and (time.time() - cached.get("ts", 0)) < GEX_CACHE_TTL:
        return cached
    return {}


def _gex_to_composite_score(gex: dict, price: float) -> float:
    """
    Convert GEX result to a 0-100 composite sub-score.
    Used to blend into composite_score with 10% weight.

    Scoring logic:
      Positive GEX + near put wall  = 75-100 (strong support)
      Positive GEX + mid-range      = 55-70  (stable, range-bound)
      Neutral GEX                   = 50     (no adjustment)
      Negative GEX + breakout setup = 70-85  (momentum confirmed)
      Negative GEX + at resistance  = 20-40  (reversal risk)
      No GEX data                   = 50     (neutral)
    """
    if not gex or not gex.get("gex_available"):
        return 50.0

    regime    = gex.get("gex_regime", "NEUTRAL")
    gex_score = float(gex.get("gex_score", 50) or 50)
    wall      = gex.get("gex_wall")

    base = gex_score  # already 0-100 from engine

    # Regime adjustment
    if regime == "POSITIVE":
        base = max(base, 55)  # floor at 55 for positive regime
        # Bonus if price is near put wall (support)
        if wall and price and abs(price - wall) / price < 0.02:
            base = min(100, base + 15)
    elif regime == "NEGATIVE":
        # Negative GEX can be good (momentum) or bad (reversal risk)
        # Engine already captures this in gex_score
        pass
    elif regime in ("PLACEHOLDER", "NO_DATA", "ERROR"):
        return 50.0

    return round(max(0, min(100, base)), 1)


# ── GEX focused scan — runs on key symbols every 8 minutes ───────────────────

def run_gex_scan():
    """
    Fetches intraday bars and scores GEX for focus symbols + divergence watchlist.
    Lightweight — only 10-20 symbols, runs in under 30 seconds.
    """
    if not _GEX_AVAILABLE:
        return

    # Combine focus symbols + divergence watchlist + Armed/Triggered symbols
    action_symbols = [
        s for s, d in RADAR_CACHE.items()
        if d.get("status") in ("Armed", "Triggered", "Confirmed", "Building")
    ]
    symbols = list(set(
        GEX_FOCUS_SYMBOLS +
        [d["symbol"] for d in DIVERGENCE_WATCHLIST] +
        action_symbols[:20]  # cap at 20 to avoid overload
    ))
    log.info(f"GEX scan starting — {len(symbols)} symbols")

    for symbol in symbols:
        try:
            cached = RADAR_CACHE.get(symbol, {})
            price  = cached.get("price", 0)
            if not price:
                continue

            bars_5m = fetch_intraday_bars(symbol, "5Min", limit=78)
            if not bars_5m:
                continue

            gex = score_gex(symbol, price, bars_5m, is_intelligence_layer=False)

            # Cache GEX result
            gex["ts"] = time.time()
            GEX_SCORE_CACHE[symbol] = gex

            # Compute composite GEX sub-score
            cached_radar = RADAR_CACHE.get(symbol, {})
            price_now    = cached_radar.get("price", 0) or 0
            gex_sub      = _gex_to_composite_score(gex, price_now)

            if symbol in RADAR_CACHE:
                RADAR_CACHE[symbol]["gex_score"]     = gex.get("gex_score")
                RADAR_CACHE[symbol]["gex_regime"]    = gex.get("gex_regime")
                RADAR_CACHE[symbol]["gex_available"] = gex.get("gex_available", False)
                RADAR_CACHE[symbol]["gex_strategy"]  = gex.get("gex_strategy")
                RADAR_CACHE[symbol]["gex_wall"]      = gex.get("gex_wall") or gex.get("nearest_wall")
                RADAR_CACHE[symbol]["gex_sub_score"] = gex_sub

                # Recompute composite score with GEX (10% weight)
                old_composite = cached_radar.get("composite_score", 50) or 50
                new_composite = round(
                    old_composite * 0.90 + gex_sub * 0.10, 1
                )
                RADAR_CACHE[symbol]["composite_score"] = new_composite
                log.info(
                    f"GEX {symbol}: regime={gex.get('gex_regime')} "
                    f"score={gex.get('gex_score'):.1f} "
                    f"composite {old_composite:.1f}→{new_composite:.1f}"
                )

            if INTELLIGENCE_CACHE.get(symbol):
                INTELLIGENCE_CACHE[symbol]["gex_score"]  = gex.get("gex_score")
                INTELLIGENCE_CACHE[symbol]["gex_regime"] = gex.get("gex_regime")

        except Exception as e:
            log.debug(f"GEX scan error {symbol}: {e}")
        time.sleep(0.1)

    log.info(f"GEX scan complete — {len(symbols)} symbols")


# ── Layer 1 — Main scan loop (lightweight only) ────────────────────────────────

def run_radar_scan():
    """Layer 1 — Lightweight universe scan. No AB confluence. No intraday fetches."""
    global LAST_SCAN_TIME

    if not SYMBOLS:
        log.warning("No symbols loaded — skipping scan")
        return
    if not ALPACA_API_KEY:
        log.warning("No Alpaca API key — skipping scan")
        _populate_synthetic_cache()
        return

    if time.time() - _bars_last_refresh > 1800 and not _bars_loading:
        threading.Thread(target=_refresh_historical_bars, daemon=True).start()

    log.info(f"Radar scan starting — {len(SYMBOLS)} symbols (lightweight)")
    snapshots = fetch_snapshots(SYMBOLS)

    # Seed SPY benchmark
    try:
        spy_snap = snapshots.get("SPY", {})
        spy_bars = _historical_bars.get("SPY", [])
        if spy_snap and _CONFLUENCE_AVAILABLE:
            spy_result = score_symbol("SPY", spy_snap, spy_bars)
            if spy_result and spy_result.get("change_pct") is not None:
                from confluence_bridge import update_spy_benchmark
                update_spy_benchmark(spy_result["change_pct"])
                log.info(f"SPY benchmark seeded: {spy_result['change_pct']:.2f}%")
    except Exception as _e:
        log.debug(f"SPY benchmark seed error: {_e}")

    # Load divergence watchlist symbols for flagging
    div_symbols = {d["symbol"] for d in DIVERGENCE_WATCHLIST}

    scored = []
    for symbol in SYMBOLS:
        snap = snapshots.get(symbol, {})
        if not snap:
            continue
        bars = _historical_bars.get(symbol, [])
        try:
            result = score_symbol(symbol, snap, bars)
            if result and result.get("composite_score", 0) > 0:
                result["on_divergence_watchlist"] = symbol in div_symbols
                # Add lightweight Weis Wave signal from daily bars
                if _WEIS_RADAR_AVAILABLE and bars:
                    try:
                        price = result.get("price", 0)
                        weis  = score_weis_wave_radar(symbol, bars, price)
                        result.update(weis)
                    except Exception as _we:
                        pass
                scored.append(result)
        except Exception as e:
            log.debug(f"Score error {symbol}: {e}")

    for s in scored:
        RADAR_CACHE[s["symbol"]] = s

    # Heartbeat
    try:
        if _redis_client:
            _redis_client.set("health:scanner:last_pulse", int(time.time()))
    except Exception as _he:
        log.debug(f"Heartbeat write failed: {_he}")

    LAST_SCAN_TIME = time.time()
    log.info(f"Radar scan complete — {len(scored)} symbols scored (lightweight)")

    _process_events(scored)

# ── EOD Audit — Full ConfluenceEngine on entire universe ──────────────────────

def run_eod_audit():
    """
    Runs nightly at 8:30 PM ET.
    Scores all symbols with full ConfluenceEngine, computes delta vs composite_score.
    Symbols with |delta| >= 15 written to divergence_watchlist in Supabase.
    """
    global DIVERGENCE_WATCHLIST, LAST_EOD_AUDIT_TIME

    if not _CONFLUENCE_AVAILABLE:
        log.warning("EOD audit skipped — confluence bridge not available")
        return
    if not RADAR_CACHE:
        log.warning("EOD audit skipped — radar cache empty")
        return

    log.info(f"EOD audit starting — {len(RADAR_CACHE)} symbols")
    divergences = []

    for symbol, cached in list(RADAR_CACHE.items()):
        snap = {}
        bars = _historical_bars.get(symbol, [])
        composite = cached.get("composite_score", 0)
        if not composite:
            continue
        try:
            result = score_symbol_ab(symbol, snap, bars, dict(cached))
            new_score = result.get("new_composite_score") or result.get("composite_score", 0)
            delta = round(new_score - composite, 2)

            if abs(delta) >= DIVERGENCE_THRESHOLD:
                direction = "BULLISH" if delta > 0 else "BEARISH"
                divergences.append({
                    "symbol":          symbol,
                    "composite_score": composite,
                    "deep_score":      round(new_score, 2),
                    "delta":           delta,
                    "direction":       direction,
                    "old_status":      cached.get("status"),
                    "new_status":      result.get("new_status") or result.get("status"),
                    "regime":          result.get("new_regime") or result.get("regime"),
                    "price":           cached.get("price"),
                    "audited_at":      datetime.now(timezone.utc).isoformat(),
                })
                log.info(
                    f"DIVERGENCE {symbol}: composite={composite:.1f} "
                    f"deep={new_score:.1f} delta={delta:+.1f} | {direction}"
                )
        except Exception as e:
            log.debug(f"EOD audit error {symbol}: {e}")

    # Sort by absolute delta descending
    divergences.sort(key=lambda x: abs(x["delta"]), reverse=True)
    DIVERGENCE_WATCHLIST = divergences

    log.info(f"EOD audit complete — {len(divergences)} divergences found")

    # Write to Supabase
    _write_divergence_watchlist(divergences)

    # Mark divergence symbols in RADAR_CACHE
    div_set = {d["symbol"] for d in divergences}
    for sym in RADAR_CACHE:
        RADAR_CACHE[sym]["on_divergence_watchlist"] = sym in div_set

    LAST_EOD_AUDIT_TIME = time.time()


def _write_divergence_watchlist(divergences: list):
    if not DATABASE_URL or not divergences:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        # Clear previous night's watchlist
        cur.execute("DELETE FROM divergence_watchlist")
        for d in divergences:
            cur.execute("""
                INSERT INTO divergence_watchlist
                (symbol, composite_score, deep_score, delta, direction,
                 old_status, new_status, regime, price, audited_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (symbol) DO UPDATE SET
                    composite_score = EXCLUDED.composite_score,
                    deep_score      = EXCLUDED.deep_score,
                    delta           = EXCLUDED.delta,
                    direction       = EXCLUDED.direction,
                    old_status      = EXCLUDED.old_status,
                    new_status      = EXCLUDED.new_status,
                    regime          = EXCLUDED.regime,
                    price           = EXCLUDED.price,
                    audited_at      = EXCLUDED.audited_at
            """, (
                d["symbol"], d["composite_score"], d["deep_score"],
                d["delta"], d["direction"], d["old_status"],
                d["new_status"], d["regime"], d["price"], d["audited_at"]
            ))
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Wrote {len(divergences)} divergences to Supabase")
    except Exception as e:
        log.warning(f"Divergence watchlist write error: {e}")


def _load_divergence_watchlist_from_db():
    """Load previous night's divergence watchlist from Supabase on startup."""
    global DIVERGENCE_WATCHLIST
    if not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM divergence_watchlist ORDER BY ABS(delta) DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        DIVERGENCE_WATCHLIST = [dict(r) for r in rows]
        log.info(f"Loaded {len(DIVERGENCE_WATCHLIST)} symbols from divergence watchlist")
    except Exception as e:
        log.warning(f"Could not load divergence watchlist: {e}")

# ── Divergence watchlist intraday deep scan ────────────────────────────────────

def run_divergence_scan():
    """
    Runs every 8 minutes during market hours.
    Deep-scores only the divergence watchlist symbols with intraday bars.
    """
    global LAST_INTELLIGENCE_TIME

    if not DIVERGENCE_WATCHLIST:
        log.debug("Divergence scan skipped — watchlist empty")
        return
    if not _INTELLIGENCE_AVAILABLE:
        return

    symbols = [d["symbol"] for d in DIVERGENCE_WATCHLIST]
    log.info(f"Divergence scan starting — {len(symbols)} symbols")

    for symbol in symbols:
        try:
            snap = fetch_snapshots([symbol]).get(symbol, {})
            if not snap:
                continue

            daily_bar  = snap.get("dailyBar",    {}) or {}
            prev_daily = snap.get("prevDailyBar", {}) or {}
            trade      = snap.get("latestTrade",  {}) or {}

            price      = float(trade.get("p", 0) or daily_bar.get("c", 0) or 0)
            prev_close = float(prev_daily.get("c", 0) or 0)
            if price <= 0 or prev_close <= 0:
                continue

            bars_5m  = fetch_intraday_bars(symbol, "5Min",  limit=78)
            bars_1h  = fetch_intraday_bars(symbol, "1Hour", limit=20)
            bars_day = _historical_bars.get(symbol, [])

            market = MarketData(
                symbol               = symbol,
                price                = price,
                previous_close       = prev_close,
                day_open             = float(daily_bar.get("o", price) or price),
                day_high             = float(daily_bar.get("h", price) or price),
                day_low              = float(daily_bar.get("l", price) or price),
                volume               = float(daily_bar.get("v", 0) or 0),
                avg_volume           = _avg_volume_from_bars(bars_day),
                vwap                 = float(daily_bar.get("vw", price) or price),
                atr                  = _atr_from_daily_bars(bars_day),
                prior_high           = float(prev_daily.get("h", 0) or 0) or None,
                prior_low            = float(prev_daily.get("l", 0) or 0) or None,
                prior_close          = prev_close,
                candles_5m           = _bars_to_candles(bars_5m),
                candles_1h           = _bars_to_candles(bars_1h),
                candles_daily        = _bars_to_candles(bars_day[-60:]),
                benchmark_change_pct = _benchmark_change(),
            )

            result = _intelligence_engine.evaluate(market, OptionsData())

            INTELLIGENCE_CACHE[symbol] = {
                "symbol":          symbol,
                "price":           result.price,
                "score":           result.score,
                "confidence":      result.confidence,
                "direction":       result.direction,
                "status":          result.status,
                "regime":          result.regime,
                "setup":           result.setup,
                "wyckoff_phase":   result.wyckoff_phase,
                "candle_pattern":  result.candle_pattern,
                "cycle_hits":      len(result.cycle_hits),
                "factor_scores":   result.factor_scores,
                "internal_scores": result.internal_scores,
                "levels":          result.levels,
                "paths":           result.paths,
                "alert_reason":    result.alert_reason,
                "updated_at":      datetime.now(timezone.utc).isoformat(),
                "bars_5m_count":   len(bars_5m),
                "bars_1h_count":   len(bars_1h),
                "divergence_delta": next(
                    (d["delta"] for d in DIVERGENCE_WATCHLIST if d["symbol"] == symbol), None
                ),
            }

            if symbol in RADAR_CACHE:
                RADAR_CACHE[symbol]["intelligence_score"]  = result.score
                RADAR_CACHE[symbol]["intelligence_status"] = result.status
                RADAR_CACHE[symbol]["intelligence_regime"] = result.regime

        except Exception as e:
            log.warning(f"Divergence scan error {symbol}: {e}")

        time.sleep(0.2)

    LAST_INTELLIGENCE_TIME = time.time()
    log.info(f"Divergence scan complete — {len(INTELLIGENCE_CACHE)} symbols graded")


def _bars_to_candles(bars: List[dict]) -> List["Candle"]:
    candles = []
    for b in bars:
        try:
            ts = datetime.fromisoformat(
                b["t"].replace("Z", "+00:00")
            ) if b.get("t") else datetime.now(timezone.utc)
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


def _avg_volume_from_bars(bars: list) -> float:
    vols = [float(b.get("v", 0)) for b in bars[-20:] if b.get("v")]
    return sum(vols) / len(vols) if vols else 1_000_000


def _atr_from_daily_bars(bars: list) -> Optional[float]:
    if len(bars) < 2:
        return None
    trs = []
    for i in range(1, min(len(bars), 15)):
        c    = bars[-i]
        prev = bars[-(i+1)]
        tr = max(
            float(c.get("h", 0)) - float(c.get("l", 0)),
            abs(float(c.get("h", 0)) - float(prev.get("c", 0))),
            abs(float(c.get("l", 0)) - float(prev.get("c", 0))),
        )
        trs.append(tr)
    return round(sum(trs) / len(trs), 4) if trs else None


def _benchmark_change() -> Optional[float]:
    spy = RADAR_CACHE.get("SPY", {})
    return spy.get("change_pct") if spy else None

# ── Event processing ───────────────────────────────────────────────────────────

def _process_events(scored: list):
    if not DATABASE_URL:
        return
    events = []
    now = time.time()

    for s in scored:
        sym    = s["symbol"]
        score  = s["composite_score"]
        status = s["status"]
        prev   = _prev_statuses.get(sym)

        if prev and prev != status:
            events.append({
                "event_id":       "re_" + uuid.uuid4().hex[:12],
                "symbol":         sym,
                "event_type":     "status_change",
                "old_status":     prev,
                "new_status":     status,
                "composite_score":score,
                "price":          s["price"],
                "trigger_level":  s["trigger"],
                "invalidation":   s["invalidation"],
                "notes":          f"{s['setup_type']} · {s['regime']}",
            })
            maybe_send_alert(s, prev, status)
            log_signal(s, status)
            maybe_send_sms(s, prev, status)
        _prev_statuses[sym] = status

        last_snap = _last_snapshot_times.get(sym, 0)
        if now - last_snap > SNAPSHOT_INTERVAL:
            if score >= SCORE_THRESHOLD:
                events.append({
                    "event_id":       "re_" + uuid.uuid4().hex[:12],
                    "symbol":         sym,
                    "event_type":     "score_threshold",
                    "old_status":     None,
                    "new_status":     status,
                    "composite_score":score,
                    "price":          s["price"],
                    "trigger_level":  s["trigger"],
                    "invalidation":   s["invalidation"],
                    "notes":          f"Score {score} · {s['setup_type']}",
                })
            _last_snapshot_times[sym] = now

    if not events:
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        for ev in events:
            cur.execute("""
                INSERT INTO radar_events
                (event_id, symbol, event_type, old_status, new_status,
                 composite_score, price, trigger_level, invalidation, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (event_id) DO NOTHING
            """, (ev["event_id"], ev["symbol"], ev["event_type"],
                  ev["old_status"], ev["new_status"], ev["composite_score"],
                  ev["price"], ev["trigger_level"], ev["invalidation"], ev["notes"]))
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Wrote {len(events)} radar events to Supabase")
    except Exception as e:
        log.warning(f"Event write error: {e}")


def _populate_synthetic_cache():
    import random
    for sym in SYMBOLS[:50]:
        score = random.uniform(45, 92)
        RADAR_CACHE[sym] = {
            "symbol":                 sym,
            "price":                  round(random.uniform(50, 500), 2),
            "change_pct":             round(random.uniform(-3, 4), 2),
            "volume":                 random.randint(500_000, 5_000_000),
            "rel_volume":             round(random.uniform(0.5, 3.0), 2),
            "composite_score":        round(score, 1),
            "confluence":             round(random.uniform(40, 95), 1),
            "expansion_node":         round(random.uniform(40, 95), 1),
            "relative_strength":      round(random.uniform(40, 95), 1),
            "volume_pressure":        round(random.uniform(40, 95), 1),
            "behavioral":             round(random.uniform(40, 95), 1),
            "setup_type":             random.choice(["Compression Breakout Candidate",
                                                     "Trend Continuation", "Monitoring"]),
            "status":                 random.choice(["Armed", "Building", "Watching"]),
            "trigger":                round(random.uniform(100, 500), 2),
            "invalidation":           round(random.uniform(80, 400), 2),
            "target1":                round(random.uniform(120, 550), 2),
            "target2":                round(random.uniform(140, 600), 2),
            "regime":                 random.choice(["Bull Expansion", "Compression", "Neutral"]),
            "vwap":                   round(random.uniform(80, 480), 2),
            "ma20":                   round(random.uniform(80, 480), 2),
            "ma50":                   round(random.uniform(80, 480), 2),
            "atr":                    round(random.uniform(1, 20), 2),
            "high_52w":               round(random.uniform(150, 600), 2),
            "low_52w":                round(random.uniform(50, 300), 2),
            "updated_at":             datetime.now(timezone.utc).isoformat(),
            "data_delay":             "synthetic",
            "trigger_proximity":      0,
            "on_divergence_watchlist": False,
        }

# ── Scheduler ─────────────────────────────────────────────────────────────────

_scheduler: Optional[BackgroundScheduler] = None


def start_radar_scheduler():
    global SYMBOLS, _scheduler
    SYMBOLS = load_russell1000()
    log.info(f"Radar scheduler starting — {len(SYMBOLS)} symbols")

    # Load last night's divergence watchlist from Supabase
    _load_divergence_watchlist_from_db()

    if ALPACA_API_KEY:
        threading.Thread(target=_refresh_historical_bars, daemon=True).start()
        log.info("Historical bar fetch started in background thread")

    _scheduler = BackgroundScheduler(timezone="UTC")

    # GEX focused scan — runs every 8 minutes during market hours
    if _GEX_AVAILABLE:
        _scheduler.add_job(
            lambda: threading.Thread(target=run_gex_scan, daemon=True).start(),
            trigger="interval",
            seconds=SCAN_INTERVAL_SECONDS,
            id="gex_scan",
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=90),
        )
        log.info("GEX scan scheduled every 8 minutes")

    # Layer 1 — Lightweight universe scan every 8 minutes
    _scheduler.add_job(
        run_radar_scan,
        trigger="interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="radar_scan",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=45),
    )

    # Divergence watchlist intraday deep scan — runs alongside radar scan
    if _INTELLIGENCE_AVAILABLE:
        _scheduler.add_job(
            lambda: threading.Thread(target=run_divergence_scan, daemon=True).start(),
            trigger="interval",
            seconds=SCAN_INTERVAL_SECONDS,
            id="divergence_scan",
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        log.info("Divergence watchlist scan scheduled every 8 minutes")

    # EOD audit — 8:30 PM ET = 00:30 UTC
    _scheduler.add_job(
        lambda: threading.Thread(target=run_eod_audit, daemon=True).start(),
        trigger="cron",
        hour=0, minute=30,
        id="eod_audit",
    )
    log.info("EOD audit scheduled at 8:30 PM ET (00:30 UTC)")

    _scheduler.add_job(
        lambda: send_daily_summary(list(RADAR_CACHE.values())),
        trigger="cron", hour=12, minute=0, id="daily_summary",
    )
    _scheduler.add_job(
        lambda: threading.Thread(target=grade_pending_signals, daemon=True).start(),
        trigger="cron", hour=21, minute=15, id="grade_signals",
    )
    try:
        from snapshot_service import write_intraday_snapshots, write_daily_close_snapshots
        _scheduler.add_job(
            lambda: write_intraday_snapshots(RADAR_CACHE),
            trigger="interval", seconds=300, id="snapshot_intraday",
        )
        _scheduler.add_job(
            lambda: write_daily_close_snapshots(RADAR_CACHE),
            trigger="cron", hour=20, minute=15, id="snapshot_daily_close",
        )
        log.info("Snapshot writer jobs scheduled")
    except ImportError:
        log.warning("snapshot_service not found — snapshot writing disabled")

    _scheduler.start()
    log.info("Radar scheduler started")


def stop_radar_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Radar scheduler stopped")

# ── API Endpoints ──────────────────────────────────────────────────────────────

@radar_router.get("/status")
def radar_status():
    return {
        "ok":                    True,
        "symbol_count":          len(SYMBOLS),
        "cached_count":          len(RADAR_CACHE),
        "last_scan":             LAST_SCAN_TIME,
        "last_scan_ago":         round(time.time() - LAST_SCAN_TIME, 1) if LAST_SCAN_TIME else None,
        "feed":                  ALPACA_FEED,
        "data_delay":            "15min" if ALPACA_FEED == "iex" else "live",
        "bars_loaded":           len(_historical_bars),
        "bars_last_refresh":     _bars_last_refresh,
        "bars_loading":          _bars_loading,
        "confluence_engine":     _CONFLUENCE_AVAILABLE,
        "intelligence_engine":   _INTELLIGENCE_AVAILABLE,
        "intelligence_cached":   len(INTELLIGENCE_CACHE),
        "last_intelligence":     LAST_INTELLIGENCE_TIME,
        "divergence_watchlist":  len(DIVERGENCE_WATCHLIST),
        "last_eod_audit":        LAST_EOD_AUDIT_TIME,
    }


@radar_router.get("/health")
def scanner_health():
    try:
        if not _redis_client:
            return {"status": "unhealthy", "reason": "Redis client not initialized."}
        last_pulse = _redis_client.get("health:scanner:last_pulse")
        if not last_pulse:
            return {"status": "unhealthy", "reason": "No heartbeat pulse recorded yet."}
        seconds_offline = int(time.time()) - int(last_pulse)
        if seconds_offline > 120:
            return {"status": "stalled", "seconds_since_pulse": seconds_offline}
        return {"status": "operational", "seconds_since_pulse": seconds_offline}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@radar_router.get("/divergence")
def get_divergence_watchlist():
    return {
        "count":          len(DIVERGENCE_WATCHLIST),
        "symbols":        DIVERGENCE_WATCHLIST,
        "last_audit":     LAST_EOD_AUDIT_TIME,
        "threshold":      DIVERGENCE_THRESHOLD,
    }


@radar_router.get("/intelligence")
def get_intelligence():
    results = list(INTELLIGENCE_CACHE.values())
    results.sort(key=lambda x: abs(x.get("divergence_delta", 0) or 0), reverse=True)
    return {
        "count":        len(results),
        "symbols":      results,
        "last_updated": LAST_INTELLIGENCE_TIME,
    }


@radar_router.get("/intelligence/{symbol}")
def get_intelligence_symbol(symbol: str):
    sym = symbol.upper().strip()
    div_symbols = {d["symbol"] for d in DIVERGENCE_WATCHLIST}
    if sym not in INTELLIGENCE_CACHE:
        if sym not in div_symbols:
            raise HTTPException(404, f"{sym} is not on the divergence watchlist")
        raise HTTPException(404, f"{sym} intelligence data not yet available — check back after next scan")
    return INTELLIGENCE_CACHE[sym]


@radar_router.get("/ab-summary")
def get_ab_summary():
    return {
        "message": "AB divergence now runs as EOD audit at 8:30 PM ET",
        "divergence_count": len(DIVERGENCE_WATCHLIST),
        "last_audit": LAST_EOD_AUDIT_TIME,
        "watchlist": DIVERGENCE_WATCHLIST[:10],
    }


@radar_router.get("/debug/bars")
def debug_bars():
    if not ALPACA_API_KEY:
        return {"error": "No Alpaca API key"}
    start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    test_sym = "AAPL"
    try:
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{test_sym}/bars",
            headers=_alpaca_headers(),
            params={"timeframe": "1Day", "start": start_date, "feed": ALPACA_FEED, "sort": "asc"},
            timeout=10,
        )
        single_result = {
            "status_code": r.status_code,
            "bar_count":   len((r.json().get("bars") or [])) if r.status_code == 200 else 0,
            "sample":      (r.json().get("bars") or [None])[-1] if r.status_code == 200 else r.text[:200],
        }
    except Exception as e:
        single_result = {"error": str(e)}
    return {"bars_in_cache": len(_historical_bars), "bars_loading": _bars_loading,
            "single_symbol": single_result}


@radar_router.get("/scores")
def get_radar_scores(limit: int = 100, status: str = None, min_score: float = 0):
    results = list(RADAR_CACHE.values())
    if status:
        results = [r for r in results if r.get("status") == status]
    if min_score > 0:
        results = [r for r in results if r.get("composite_score", 0) >= min_score]
    results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    return {
        "count":      len(results[:limit]),
        "symbols":    results[:limit],
        "last_scan":  LAST_SCAN_TIME,
        "data_delay": "15min" if ALPACA_FEED == "iex" else "live",
    }


@radar_router.get("/symbol/{symbol}")
def get_symbol_detail(symbol: str):
    sym = symbol.upper().strip()
    if sym not in RADAR_CACHE:
        raise HTTPException(404, f"{sym} not in radar cache")
    return RADAR_CACHE[sym]


@radar_router.post("/watchlist")
def add_to_watchlist(payload: WatchlistAdd, request: Request,
                     user_id: str = Depends(get_user_id_from_request)):
    sym = payload.symbol.upper().strip()
    if not sym or len(sym) > 5:
        raise HTTPException(400, "Invalid symbol")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO user_watchlists (id, user_id, symbol, notes)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, symbol) DO NOTHING
        """, ("wl_" + uuid.uuid4().hex[:12], user_id, sym, payload.notes))
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "symbol": sym, "user_id": user_id}
    except Exception as e:
        raise HTTPException(500, str(e))


@radar_router.get("/watchlist/{user_id}")
def get_watchlist(user_id: str):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute("SELECT symbol FROM user_watchlists WHERE user_id=%s ORDER BY added_at DESC",
                    (user_id,))
        rows    = cur.fetchall()
        cur.close()
        conn.close()
        symbols = [r[0] for r in rows]
        scores  = [RADAR_CACHE[s] for s in symbols if s in RADAR_CACHE]
        return {"symbols": symbols, "scores": scores}
    except Exception as e:
        return {"symbols": [], "scores": [], "error": str(e)}

