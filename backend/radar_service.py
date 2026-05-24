"""
backend/radar_service.py
------------------------
Sigmalytic Radar — Two-Layer Intelligence Architecture

LAYER 1 — Market Radar (Universe)
──────────────────────────────────
1,398 symbols | 60-second scan | daily bars | lightweight confluence
Purpose: broad surveillance, finds candidates, feeds watchlist

LAYER 2 — Intelligence Radar (Focus Basket)
────────────────────────────────────────────
14 symbols | 5-minute intraday bars | full confluence engine
Purpose: deep behavioral intelligence, path forecasting, alerts, scoreboard

ENDPOINTS
─────────────────────────────────────────────────────────────────────────────
GET /api/radar/scores              — top 100 symbols by composite score
GET /api/radar/symbol/{symbol}     — full detail for one symbol
GET /api/radar/status              — service health, scan times, engine status
GET /api/radar/health              — deep health check with heartbeat
GET /api/radar/ab-summary          — A/B comparison stats across full universe
GET /api/radar/intelligence        — deep scores for focus basket only
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

# ── Confluence engine direct import for intelligence layer ─────────────────────
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

SCAN_INTERVAL_SECONDS      = 60
INTELLIGENCE_INTERVAL_SECS = 300   # 5 minutes
SNAPSHOT_INTERVAL          = 300
SCORE_THRESHOLD            = 75
TOP_N                      = 100

# ── Layer 2 — Focus basket (Intelligence Radar) ────────────────────────────────
FOCUS_SYMBOLS: Set[str] = {
    "SPY", "QQQ", "IWM",
    "AAPL", "NVDA", "TSLA", "AMD",
    "GOOG", "META", "AMZN", "MSFT",
    "NFLX", "GLD", "SMH",
}

# ── In-memory caches ──────────────────────────────────────────────────────────

RADAR_CACHE: Dict[str, dict]        = {}
INTELLIGENCE_CACHE: Dict[str, dict] = {}

LAST_SCAN_TIME:         Optional[float] = None
LAST_INTELLIGENCE_TIME: Optional[float] = None
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
        time.sleep(0.05)
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
        "intelligence_layer": symbol in FOCUS_SYMBOLS,
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

# ── Layer 2 — Intelligence engine (focus basket) ──────────────────────────────

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


def run_intelligence_scan():
    """
    Layer 2 — Deep confluence engine on focus basket.
    Runs every 5 minutes in a background thread.
    """
    global LAST_INTELLIGENCE_TIME

    if not _INTELLIGENCE_AVAILABLE:
        return
    if not ALPACA_API_KEY:
        return

    log.info(f"Intelligence scan starting — {len(FOCUS_SYMBOLS)} focus symbols")

    for symbol in sorted(FOCUS_SYMBOLS):
        try:
            snaps = fetch_snapshots([symbol])
            snap  = snaps.get(symbol, {})
            if not snap:
                continue

            daily_bar  = snap.get("dailyBar",    {}) or {}
            prev_daily = snap.get("prevDailyBar", {}) or {}
            trade      = snap.get("latestTrade", {}) or {}

            price      = float(trade.get("p", 0) or daily_bar.get("c", 0) or 0)
            prev_close = float(prev_daily.get("c", 0) or 0)
            if price <= 0 or prev_close <= 0:
                continue

            bars_5m  = fetch_intraday_bars(symbol, "5Min",  limit=78)
            bars_1h  = fetch_intraday_bars(symbol, "1Hour", limit=20)
            bars_day = _historical_bars.get(symbol, [])

            market = MarketData(
                symbol              = symbol,
                price               = price,
                previous_close      = prev_close,
                day_open            = float(daily_bar.get("o", price) or price),
                day_high            = float(daily_bar.get("h", price) or price),
                day_low             = float(daily_bar.get("l", price) or price),
                volume              = float(daily_bar.get("v", 0) or 0),
                avg_volume          = _avg_volume_from_bars(bars_day),
                vwap                = float(daily_bar.get("vw", price) or price),
                atr                 = _atr_from_daily_bars(bars_day),
                prior_high          = float(prev_daily.get("h", 0) or 0) or None,
                prior_low           = float(prev_daily.get("l", 0) or 0) or None,
                prior_close         = prev_close,
                candles_5m          = _bars_to_candles(bars_5m),
                candles_1h          = _bars_to_candles(bars_1h),
                candles_daily       = _bars_to_candles(bars_day[-60:]),
                benchmark_change_pct= _benchmark_change(),
            )

            options = OptionsData()

            result = _intelligence_engine.evaluate(market, options)

            INTELLIGENCE_CACHE[symbol] = {
                "symbol"          : symbol,
                "price"           : result.price,
                "score"           : result.score,
                "confidence"      : result.confidence,
                "direction"       : result.direction,
                "status"          : result.status,
                "regime"          : result.regime,
                "setup"           : result.setup,
                "wyckoff_phase"   : result.wyckoff_phase,
                "candle_pattern"  : result.candle_pattern,
                "cycle_hits"      : len(result.cycle_hits),
                "factor_scores"   : result.factor_scores,
                "internal_scores" : result.internal_scores,
                "levels"          : result.levels,
                "paths"           : result.paths,
                "alert_reason"    : result.alert_reason,
                "updated_at"      : datetime.now(timezone.utc).isoformat(),
                "bars_5m_count"   : len(bars_5m),
                "bars_1h_count"   : len(bars_1h),
            }

            if symbol in RADAR_CACHE:
                RADAR_CACHE[symbol]["intelligence_score"]     = result.score
                RADAR_CACHE[symbol]["intelligence_confidence"]= result.confidence
                RADAR_CACHE[symbol]["intelligence_direction"] = result.direction
                RADAR_CACHE[symbol]["intelligence_status"]    = result.status
                RADAR_CACHE[symbol]["intelligence_regime"]    = result.regime
                RADAR_CACHE[symbol]["intelligence_setup"]     = result.setup
                RADAR_CACHE[symbol]["intelligence_layer"]     = True

            log.debug(f"Intelligence {symbol}: score={result.score:.1f} "
                      f"status={result.status} regime={result.regime} "
                      f"5m_bars={len(bars_5m)}")

        except Exception as e:
            log.warning(f"Intelligence scan error {symbol}: {e}")

        time.sleep(0.5)

    LAST_INTELLIGENCE_TIME = time.time()
    log.info(f"Intelligence scan complete — {len(INTELLIGENCE_CACHE)} symbols graded")


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
    except Exception as e:
        log.warning(f"Historical bar refresh failed: {e}")
    finally:
        _bars_loading = False

# ── Layer 1 — Main scan loop ───────────────────────────────────────────────────

def run_radar_scan():
    """Layer 1 — Universe scan every 60 seconds."""
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

    log.info(f"Radar scan starting — {len(SYMBOLS)} symbols")
    snapshots = fetch_snapshots(SYMBOLS)

    scored = []

    if _CONFLUENCE_AVAILABLE:
        try:
            spy_snap = snapshots.get("SPY", {})
            spy_bars = _historical_bars.get("SPY", [])
            if spy_snap:
                spy_result = score_symbol("SPY", spy_snap, spy_bars)
                if spy_result and spy_result.get("change_pct") is not None:
                    from confluence_bridge import update_spy_benchmark
                    update_spy_benchmark(spy_result["change_pct"])
                    log.info(f"SPY benchmark seeded: {spy_result['change_pct']:.2f}%")
        except Exception as _e:
            log.debug(f"SPY benchmark seed error: {_e}")

    for symbol in SYMBOLS:
        snap = snapshots.get(symbol, {})
        if not snap:
            continue
        bars = _historical_bars.get(symbol, [])
        try:
            result = score_symbol(symbol, snap, bars)
            if result and result.get("composite_score", 0) > 0:
                if _CONFLUENCE_AVAILABLE:
                    result = score_symbol_ab(symbol, snap, bars, result)
                scored.append(result)
        except Exception as e:
            log.debug(f"Score error {symbol}: {e}")

    for s in scored:
        RADAR_CACHE[s["symbol"]] = s

    # ── Heartbeat pulse ───────────────────────────────────────────────────────
    try:
        if _redis_client:
            _redis_client.set("health:scanner:last_pulse", int(time.time()))
            log.debug("Heartbeat pulse written to Redis.")
    except Exception as _he:
        log.debug(f"Heartbeat write failed: {_he}")

    LAST_SCAN_TIME = time.time()
    log.info(f"Radar scan complete — {len(scored)} symbols scored")

    if _CONFLUENCE_AVAILABLE:
        try:
            summary = _ab_summary(scored)
            log.info(f"AB Summary: {summary}")
        except Exception as e:
            log.debug(f"AB summary error: {e}")

    _process_events(scored)


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
            "symbol":            sym,
            "price":             round(random.uniform(50, 500), 2),
            "change_pct":        round(random.uniform(-3, 4), 2),
            "volume":            random.randint(500_000, 5_000_000),
            "rel_volume":        round(random.uniform(0.5, 3.0), 2),
            "composite_score":   round(score, 1),
            "confluence":        round(random.uniform(40, 95), 1),
            "expansion_node":    round(random.uniform(40, 95), 1),
            "relative_strength": round(random.uniform(40, 95), 1),
            "volume_pressure":   round(random.uniform(40, 95), 1),
            "behavioral":        round(random.uniform(40, 95), 1),
            "setup_type":        random.choice(["Compression Breakout Candidate",
                                                "Trend Continuation","Monitoring"]),
            "status":            random.choice(["Armed","Building","Watching"]),
            "trigger":           round(random.uniform(100, 500), 2),
            "invalidation":      round(random.uniform(80, 400), 2),
            "target1":           round(random.uniform(120, 550), 2),
            "target2":           round(random.uniform(140, 600), 2),
            "regime":            random.choice(["Bull Expansion","Compression","Neutral"]),
            "vwap":              round(random.uniform(80, 480), 2),
            "ma20":              round(random.uniform(80, 480), 2),
            "ma50":              round(random.uniform(80, 480), 2),
            "atr":               round(random.uniform(1, 20), 2),
            "high_52w":          round(random.uniform(150, 600), 2),
            "low_52w":           round(random.uniform(50, 300), 2),
            "updated_at":        datetime.now(timezone.utc).isoformat(),
            "data_delay":        "synthetic",
            "trigger_proximity": 0,
            "intelligence_layer": False,
        }

# ── Scheduler ─────────────────────────────────────────────────────────────────

_scheduler: Optional[BackgroundScheduler] = None


def start_radar_scheduler():
    global SYMBOLS, _scheduler
    SYMBOLS = load_russell1000()
    log.info(f"Radar scheduler starting — {len(SYMBOLS)} symbols | "
             f"Focus basket: {len(FOCUS_SYMBOLS)} symbols")

    if ALPACA_API_KEY:
        threading.Thread(target=_refresh_historical_bars, daemon=True).start()
        log.info("Historical bar fetch started in background thread")

    _scheduler = BackgroundScheduler(timezone="UTC")

    _scheduler.add_job(
        run_radar_scan,
        trigger="interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="radar_scan",
        next_run_time=datetime.now(timezone.utc),
    )

    if _INTELLIGENCE_AVAILABLE:
        _scheduler.add_job(
            lambda: threading.Thread(target=run_intelligence_scan, daemon=True).start(),
            trigger="interval",
            seconds=INTELLIGENCE_INTERVAL_SECS,
            id="intelligence_scan",
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        log.info("Intelligence scan scheduled every 5 minutes")

    _scheduler.add_job(
        lambda: send_daily_summary(list(RADAR_CACHE.values())),
        trigger="cron", hour=12, minute=0, id="daily_summary",
    )
    _scheduler.add_job(
        grade_pending_signals,
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
        "focus_symbols":         sorted(FOCUS_SYMBOLS),
    }


@radar_router.get("/health")
def scanner_health():
    """Deep health check — verifies Redis connectivity and scanner heartbeat."""
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


@radar_router.get("/ab-summary")
def get_ab_summary():
    if not _CONFLUENCE_AVAILABLE:
        return {"error": "Confluence engine not loaded"}
    return _ab_summary(list(RADAR_CACHE.values()))


@radar_router.get("/intelligence")
def get_intelligence():
    results = list(INTELLIGENCE_CACHE.values())
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {
        "count":            len(results),
        "symbols":          results,
        "last_updated":     LAST_INTELLIGENCE_TIME,
        "engine_available": _INTELLIGENCE_AVAILABLE,
    }


@radar_router.get("/intelligence/{symbol}")
def get_intelligence_symbol(symbol: str):
    sym = symbol.upper().strip()
    if sym not in INTELLIGENCE_CACHE:
        if sym not in FOCUS_SYMBOLS:
            raise HTTPException(404, f"{sym} is not in the focus basket")
        raise HTTPException(404, f"{sym} intelligence data not yet available — check back in 5 minutes")
    return INTELLIGENCE_CACHE[sym]


@radar_router.get("/debug/bars")
def debug_bars():
    if not ALPACA_API_KEY:
        return {"error": "No Alpaca API key"}
    from datetime import timedelta
    start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    test_sym = "AAPL"
    try:
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{test_sym}/bars",
            headers=_alpaca_headers(),
            params={"timeframe":"1Day","start":start_date,"feed":ALPACA_FEED,"sort":"asc"},
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