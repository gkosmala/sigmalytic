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
import psutil
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

from backend.supabase_isolation import get_user_id_from_request
from backend.radar_alerts import maybe_send_alert, send_daily_summary
from backend.scoreboard_service import log_signal, grade_pending_signals
from backend.sms_alerts import maybe_send_sms

# ── Behavioral Transition Engine (safe import) ────────────────────────────────
try:
    from backend.behavioral_transition_engine import evaluate_behavioral_transition
    _BEHAVIORAL_TRANSITIONS_AVAILABLE = True
except Exception as _bt:
    _BEHAVIORAL_TRANSITIONS_AVAILABLE = False
    logging.getLogger("radar").warning(f"Behavioral Transition Engine not loaded: {_bt}")

# ── Historical Probability Service (safe import) ──────────────────────────────
try:
    from backend.probability_service import get_probability_profile, probability_status
    _PROBABILITY_SERVICE_AVAILABLE = True
except Exception as _ps:
    _PROBABILITY_SERVICE_AVAILABLE = False
    logging.getLogger("radar").warning(f"Historical Probability Service not loaded: {_ps}")

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
    from backend.confluence_bridge import score_symbol_ab, ab_summary as _ab_summary
    _CONFLUENCE_AVAILABLE = True
except Exception as _ce:
    _CONFLUENCE_AVAILABLE = False

# ── Doctrine-aligned deep engine (safe import) ────────────────────────────────
# FIX (2026-07-30): run_eod_audit() (Layer 2 / Intelligence Change Detector)
# now uses this instead of ConfluenceEngine -- see doctrine_deep_engine.py's
# module docstring for the full product-decision rationale. Only depends
# on backend.weis_wave (a real, existing Wyckoff/Weis engine already used
# elsewhere in this codebase), decoupled from confluence_bridge entirely.
try:
    from backend.doctrine_deep_engine import compute_doctrine_deep_score
    _DOCTRINE_ENGINE_AVAILABLE = True
except Exception as _de:
    _DOCTRINE_ENGINE_AVAILABLE = False
    logging.getLogger("radar").warning(f"Confluence bridge not loaded: {_ce}")

# ── Weis Wave radar scoring (safe import) ──────────────────────────────────────
try:
    from backend.weis_wave import score_weis_wave_radar
    _WEIS_RADAR_AVAILABLE = True
except Exception as _we:
    _WEIS_RADAR_AVAILABLE = False
    logging.getLogger("radar").warning(f"Weis Wave radar not loaded: {_we}")

# ── GEX engine (safe import) ───────────────────────────────────────────────────
try:
    from backend.gex_engine import score_gex
    _GEX_AVAILABLE = True
except Exception as _ge:
    _GEX_AVAILABLE = False
    logging.getLogger("radar").warning(f"GEX engine not loaded: {_ge}")

# ── Confluence engine direct import for divergence scoring ─────────────────────
try:
    from backend.confluence_engine import (
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

# FIX (2026-07-29): this file was the one place in the codebase that only
# checked ALPACA_API_KEY/ALPACA_API_SECRET with no fallback. Every other
# module (campaign_api.py, campaign_discovery_engine.py, main.py,
# gamma/alpaca_option_chain_adapter.py) already falls back across all
# three naming conventions Alpaca credentials show up under in this repo's
# history. If Render's backend service only has credentials set under a
# different name than this one, this module silently got empty strings --
# which produces a generic edge-level 401 (a bare nginx auth-wall HTML
# page, not Alpaca's own JSON error format) rather than a clear failure,
# because the request never carried real credentials in the first place.
ALPACA_API_KEY    = (
    os.getenv("ALPACA_API_KEY")
    or os.getenv("APCA_API_KEY_ID")
    or os.getenv("ALPACA_KEY_ID")
    or ""
)
ALPACA_API_SECRET = (
    os.getenv("ALPACA_API_SECRET")
    or os.getenv("APCA_API_SECRET_KEY")
    or os.getenv("ALPACA_SECRET_KEY")
    or ""
)
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

# Full production universe loader.
# Primary source: backend/csv_import.py if it exposes a symbol list or loader.
# Fallback source: active Alpaca assets expanded to the requested target.
CLEAN_STARTER_UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'GOOG', 'GOOGL',
    'AMZN', 'META', 'TSLA', 'SPY', 'QQQ',
    'IWM', 'GLD', 'JPM', 'GS', 'GE',
    'AMD', 'AVGO', 'NFLX', 'COST', 'WMT',
    'BAC', 'WFC', 'MS', 'C', 'AXP',
    'V', 'MA', 'PYPL', 'SCHW', 'BLK',
    'BRK.B', 'UNH', 'JNJ', 'MRK', 'LLY',
    'ABBV', 'PFE', 'TMO', 'ABT', 'DHR',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG',
    'MPC', 'PSX', 'VLO', 'OXY', 'KMI',
    'HD', 'LOW', 'TGT', 'NKE', 'MCD',
    'SBUX', 'BKNG', 'DIS', 'CMCSA', 'T',
    'ADBE', 'CRM', 'ORCL', 'INTC', 'QCOM',
    'TXN', 'MU', 'AMAT', 'LRCX', 'NOW',
    'PANW', 'CRWD', 'IBM', 'CSCO', 'UBER',
    'SHOP', 'CAT', 'DE', 'BA', 'RTX',
    'HON', 'LMT', 'UNP', 'UPS', 'FDX',
    'GEV', 'MMM', 'ETN', 'EMR', 'NOC',
    'PG', 'KO', 'PEP', 'CROX', 'CL',
    'KMB', 'MO', 'PM', 'MDLZ', 'GIS',
]


def _sanitize_symbols(items, max_symbols: int | None = None) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()

    def add(sym: str):
        sym = str(sym or "").strip().upper()
        if not sym or sym in seen:
            return
        if len(sym) > 8:
            return
        if any(sym.endswith(m) for m in ["WS", "WT", "W", "U", "R"]):
            return
        if any(x in sym for x in ["/", "^", "=", "+"]):
            return
        out.append(sym)
        seen.add(sym)

    for item in items or []:
        if isinstance(item, dict):
            add(item.get("symbol") or item.get("ticker") or item.get("Symbol") or item.get("Ticker"))
        else:
            add(item)
        if max_symbols and len(out) >= max_symbols:
            break
    return out


def _load_symbols_from_csv_import(max_symbols: int | None = None) -> List[str]:
    """
    Safely read symbols from backend/csv_import.py without assuming one exact API.
    This preserves compatibility with the existing app while letting csv_import be
    the authoritative universe source.
    """
    try:
        from backend import csv_import as ci
    except Exception as e:
        log.warning(f"csv_import unavailable for universe loading: {e}")
        return []

    # Common function names.
    for name in (
        "get_symbols",
        "load_symbols",
        "get_universe",
        "load_universe",
        "get_active_symbols",
        "load_active_symbols",
        "get_active_universe",
        "load_active_universe",
    ):
        fn = getattr(ci, name, None)
        if callable(fn):
            try:
                data = fn()
                symbols = _sanitize_symbols(data, max_symbols=max_symbols)
                if symbols:
                    log.info(f"Loaded {len(symbols)} symbols from csv_import.{name}()")
                    return symbols
            except Exception as e:
                log.warning(f"csv_import.{name}() failed: {e}")

    # Common variable names.
    for name in (
        "SYMBOLS",
        "ACTIVE_SYMBOLS",
        "ACTIVE_UNIVERSE",
        "UNIVERSE",
        "TICKERS",
    ):
        data = getattr(ci, name, None)
        symbols = _sanitize_symbols(data, max_symbols=max_symbols)
        if symbols:
            log.info(f"Loaded {len(symbols)} symbols from csv_import.{name}")
            return symbols

    log.warning("csv_import imported, but no symbol loader/list was found")
    return []


def load_russell1000() -> List[str]:
    """
    Production universe loader.

    1. Try csv_import.py first.
    2. If csv_import does not expose a usable list, use active Alpaca assets.
    3. Preserve benchmarks.
    """
    target = int(os.getenv("RADAR_CLEAN_UNIVERSE_TARGET", "1500"))
    use_csv_import = os.getenv("RADAR_USE_CSV_IMPORT_UNIVERSE", "true").lower() not in ("0", "false", "no")

    symbols: List[str] = []
    if use_csv_import:
        symbols = _load_symbols_from_csv_import(max_symbols=target)

    if not symbols:
        symbols = _build_active_clean_universe(target=target)
        log.warning(f"Using active Alpaca universe fallback with {len(symbols)} symbols; target={target}")

    benchmarks = ["SPY", "QQQ", "IWM", "GLD", "SMH"]
    for b in benchmarks:
        if b not in symbols:
            symbols.append(b)

    symbols = _sanitize_symbols(symbols, max_symbols=target)
    log.info(f"Production radar universe loaded: {len(symbols)} symbols")
    return symbols


def _build_active_clean_universe(target: int = 1500) -> List[str]:
    """
    Build a clean active universe from Alpaca active tradable US equities.
    Starts with verified major symbols, then fills from active assets.
    """
    target = max(int(target or 1500), len(CLEAN_STARTER_UNIVERSE))
    out: List[str] = []
    seen: Set[str] = set()

    def add(sym: str):
        sym = str(sym or "").strip().upper()
        if not sym or sym in seen:
            return
        if len(sym) > 8:
            return
        if any(sym.endswith(m) for m in ["WS", "WT", "W", "U", "R"]):
            return
        if any(x in sym for x in ["/", "^", "=", "+"]):
            return
        out.append(sym)
        seen.add(sym)

    for sym in CLEAN_STARTER_UNIVERSE:
        add(sym)

    try:
        asset_base = os.getenv("ALPACA_TRADING_BASE_URL", "https://api.alpaca.markets")
        r = _req.get(
            f"{asset_base}/v2/assets",
            headers=_alpaca_headers(),
            params={"status": "active", "asset_class": "us_equity"},
            timeout=20,
        )
        if r.status_code == 200:
            assets = r.json() if isinstance(r.json(), list) else []
            allowed_exchanges = {"NYSE", "NASDAQ", "AMEX", "ARCA", "BATS"}
            candidates = []
            for a in assets:
                try:
                    sym = str(a.get("symbol", "")).upper().strip()
                    exch = str(a.get("exchange", "")).upper().strip()
                    status = str(a.get("status", "")).lower().strip()
                    tradable = bool(a.get("tradable", False))
                    asset_class = str(a.get("class", a.get("asset_class", ""))).lower()
                    if status != "active" or not tradable:
                        continue
                    if exch and exch not in allowed_exchanges:
                        continue
                    if asset_class and asset_class not in ("us_equity", "us equity"):
                        continue
                    candidates.append(sym)
                except Exception:
                    continue

            for sym in sorted(set(candidates)):
                if len(out) >= target:
                    break
                add(sym)
            log.info(f"Active Alpaca universe expansion: assets={len(assets)} output={len(out)} target={target}")
        else:
            log.warning(f"Alpaca assets fetch failed {r.status_code}: {r.text[:160]}")
    except Exception as e:
        log.warning(f"Active universe expansion failed: {e}")

    return out[:target]


def _fallback_universe() -> List[str]:
    return _build_active_clean_universe(target=int(os.getenv("RADAR_CLEAN_UNIVERSE_TARGET", "1500")))

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


def fetch_bars_batch(symbols: List[str], timeframe: str = "1Day", limit: int = 252) -> dict:
    """
    Fetch historical bars for the radar universe.

    Important Alpaca behavior discovered in production:
    calling /bars with only timeframe+limit can return only the current daily
    bar. A real start/end window is required for usable MA20, MA50, ATR and
    relative-volume calculations.
    """
    results = {}

    # Use a wide calendar window so we reliably get enough trading sessions.
    # Default target is 252 daily bars (about one trading year) so MA20, MA50,
    # ATR14, relative volume, compression, and trend structure are real.
    # Alpaca needs both start and end; otherwise it may only return today's bar.
    target_limit = max(int(limit or 252), 60)
    end_dt = datetime.now(timezone.utc) + timedelta(days=1)
    calendar_days = max(180, int(target_limit * 2.2))
    start_dt = end_dt - timedelta(days=calendar_days)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")

    log.info(
        f"Fetching historical bars for {len(symbols)} symbols | "
        f"timeframe={timeframe} limit={target_limit} "
        f"start={start_date} end={end_date} feed={ALPACA_FEED}"
    )

    debug_samples = []
    error_samples = []

    for symbol in symbols:
        try:
            params = {
                "timeframe": timeframe,
                "start": start_date,
                "end": end_date,
                "feed": ALPACA_FEED,
                "sort": "asc",
                "adjustment": "raw",
                "limit": target_limit,
            }

            r = _req.get(
                f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
                headers=_alpaca_headers(),
                params=params,
                timeout=12,
            )

            if r.status_code == 200:
                bars = r.json().get("bars") or []

                # Keep the most recent `limit` bars and ignore obviously empty rows.
                cleaned = [b for b in bars if b.get("c") and b.get("v") is not None]
                if len(debug_samples) < 8:
                    debug_samples.append(f"{symbol}:status=200 raw={len(bars)} clean={len(cleaned)}")

                if cleaned:
                    results[symbol] = cleaned[-target_limit:]
                else:
                    log.warning(f"No usable historical bars for {symbol}; raw={len(bars)}")

            elif r.status_code == 429:
                msg = f"{symbol}:429 rate_limit"
                if len(error_samples) < 8:
                    error_samples.append(msg)
                log.warning("Rate limit during bar fetch — pausing 5s")
                time.sleep(5)
            else:
                msg = f"{symbol}:status={r.status_code} body={r.text[:160]}"
                if len(error_samples) < 8:
                    error_samples.append(msg)
                log.warning(f"Bar fetch failed: {msg}")

        except Exception as e:
            msg = f"{symbol}:exception={e}"
            if len(error_samples) < 8:
                error_samples.append(msg)
            log.warning(f"Bar fetch error: {msg}")

        time.sleep(0.02)

    if debug_samples:
        log.info("Historical bar sample responses: " + " | ".join(debug_samples))
    if error_samples:
        log.warning("Historical bar sample errors: " + " | ".join(error_samples))

    log.info(
        f"Bar fetch complete — {len(results)}/{len(symbols)} symbols "
        f"from {start_date} to {end_date}"
    )
    return results


def fetch_bars_multi(symbols: List[str], timeframe: str = "1Day", lookback_days: int = 280) -> dict:
    """
    Genuinely batched multi-symbol bars fetch, using Alpaca's real
    /v2/stocks/bars endpoint (distinct from fetch_bars_batch()'s
    /v2/stocks/{symbol}/bars, which makes one sequential request per
    symbol). Modeled directly on the proven, already-working pattern
    in campaign_enriched_table_api.py's _bars() -- comma-separated
    symbols, batched 40 per request. This is what makes it safe to run
    across an entire page of results (a ~50-100 row page needs only
    2-3 requests total this way, not one call per symbol).
    """
    out: Dict[str, list] = {s: [] for s in symbols}
    if not symbols:
        return out

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    for i in range(0, len(symbols), 40):
        batch = symbols[i:i + 40]
        try:
            r = _req.get(
                f"{ALPACA_BASE_URL}/v2/stocks/bars",
                headers=_alpaca_headers(),
                params={
                    "symbols": ",".join(batch),
                    "timeframe": timeframe,
                    "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "adjustment": "split",
                    "feed": ALPACA_FEED,
                    "limit": "10000",
                    "sort": "asc",
                },
                timeout=20,
            )
            if r.status_code == 200:
                raw = r.json().get("bars", {})
                if isinstance(raw, dict):
                    for s in batch:
                        if isinstance(raw.get(s), list):
                            out[s] = raw[s]
            else:
                log.warning(f"fetch_bars_multi batch error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"fetch_bars_multi batch failed (non-fatal): {e}")

    return out


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

    # Filter out data anomalies — splits, bad ticks, stale prev_close
    if abs(change_pct) > 50:
        return {}
    closes     = [float(b.get("c", 0)) for b in bars if b.get("c")]
    volumes    = [float(b.get("v", 0)) for b in bars if b.get("v")]
    highs      = [float(b.get("h", 0)) for b in bars if b.get("h")]
    lows       = [float(b.get("l", 0)) for b in bars if b.get("l")]

    bars_count = len(closes)
    has_ma20_history = len(closes) >= 20
    has_ma50_history = len(closes) >= 50
    has_volume_history = len(volumes) >= 20
    has_atr_history = len(highs) >= 15 and len(lows) >= 15 and len(closes) >= 15
    history_ready = has_ma20_history and has_volume_history and has_atr_history

    # IMPORTANT:
    # Do not let missing history pretend to be real history.
    # The old fallback used ma20=price, ma50=price, rel_vol=1.0, atr=1.0.
    # That made every symbol look like the same trend-continuation profile.
    ma20 = sum(closes[-20:]) / len(closes[-20:]) if has_ma20_history else price
    ma50 = sum(closes[-50:]) / len(closes[-50:]) if has_ma50_history else ma20

    avg_vol_20 = sum(volumes[-20:]) / len(volumes[-20:]) if has_volume_history else 0.0
    rel_vol = (volume / avg_vol_20) if avg_vol_20 > 0 else 0.0

    if has_atr_history:
        atr = _calc_atr(highs, lows, closes, 14)
    else:
        atr = max(day_high - day_low, price * 0.02, 0.01)

    high_52w = max(highs[-252:]) if len(highs) >= 52 else max(day_high, price)
    low_52w  = min(lows[-252:])  if len(lows)  >= 52 else min(day_low, price)

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
    else:
        rel_strength = _fallback_relative_strength(
            price=price,
            vwap=vwap,
            day_open=day_open,
            prev_close=prev_close,
            change_pct=change_pct,
            rel_vol=rel_vol,
        )

    if len(volumes) >= 20:
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
    else:
        vol_pressure = _fallback_volume_pressure(
            rel_vol=rel_vol,
            change_pct=change_pct,
            volume=volume,
            price=price,
            day_open=day_open,
            vwap=vwap,
        )

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

    # If historical bars are missing/thin, cap the score so snapshot-only rows
    # do not dominate the radar or all map into the same probability profile.
    if not history_ready:
        composite = min(composite, 67.0)

    setup_type   = _classify_setup(price, ma20, ma50, atr, day_high, day_low,
                                   high_52w, rel_vol, change_pct, closes,
                                   history_ready=history_ready, bars_count=bars_count)
    trigger      = round(day_high + atr * 0.1, 2) if atr > 0 else round(price * 1.005, 2)
    invalidation = round(day_low  - atr * 0.1, 2) if atr > 0 else round(price * 0.99,  2)
    target1      = round(price + atr * 1.0, 2)
    target2      = round(price + atr * 2.0, 2)
    prev_status  = _prev_statuses.get(symbol, "")
    status       = _determine_status(composite, expansion, rel_vol, change_pct,
                                     price=price, trigger=trigger,
                                     invalidation=invalidation,
                                     prev_status=prev_status, ma20=ma20, ma50=ma50)
    regime       = _infer_regime(change_pct, rel_vol, price, ma20, ma50, history_ready=history_ready)

    # ── BME scoring ──────────────────────────────────────────────────────────
    bme_score  = None
    bme_regime = None
    try:
        from backend.behavioral_memory import evaluate as _bme_evaluate
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

    result = {
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
        "historical_bars_count": bars_count,
        "history_ready":      bool(history_ready),
        "data_quality":       "historical" if history_ready else "snapshot_only",
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

    return _attach_behavioral_transition(result)


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


def _fallback_relative_strength(price: float, vwap: float, day_open: float,
                                prev_close: float, change_pct: float,
                                rel_vol: float) -> float:
    """
    Snapshot-based relative-strength proxy used when historical bars are not
    ready. This is NOT RSI. It is a Sigmalytic 0-100 strength factor.
    """
    score = 50.0

    if change_pct >= 5:
        score += 25
    elif change_pct >= 3:
        score += 18
    elif change_pct >= 2:
        score += 12
    elif change_pct >= 1:
        score += 7
    elif change_pct <= -5:
        score -= 25
    elif change_pct <= -3:
        score -= 18
    elif change_pct <= -2:
        score -= 12
    elif change_pct <= -1:
        score -= 7

    if price > vwap:
        score += 6
    elif price < vwap:
        score -= 6

    if price > day_open:
        score += 5
    elif price < day_open:
        score -= 5

    if price > prev_close:
        score += 4
    elif price < prev_close:
        score -= 4

    if rel_vol >= 2.0 and change_pct > 0:
        score += 6
    elif rel_vol >= 2.0 and change_pct < 0:
        score -= 6

    return _clamp(round(score, 1))


def _fallback_volume_pressure(rel_vol: float, change_pct: float,
                              volume: float, price: float,
                              day_open: float, vwap: float) -> float:
    """
    Snapshot-based volume/pressure proxy used when avg-volume history is not
    available. Keeps 50 as neutral, but separates strong buying/selling pressure.
    """
    score = 50.0

    if rel_vol >= 3.0:
        score += 28
    elif rel_vol >= 2.0:
        score += 20
    elif rel_vol >= 1.5:
        score += 12
    elif rel_vol >= 1.2:
        score += 6
    elif rel_vol <= 0.5:
        score -= 18
    elif rel_vol <= 0.7:
        score -= 10

    if change_pct >= 4:
        score += 14
    elif change_pct >= 2:
        score += 9
    elif change_pct >= 1:
        score += 5
    elif change_pct <= -4:
        score -= 14
    elif change_pct <= -2:
        score -= 9
    elif change_pct <= -1:
        score -= 5

    if price > day_open and price > vwap:
        score += 6
    elif price < day_open and price < vwap:
        score -= 6

    # Absolute activity nudge. This avoids treating very active names and very
    # inactive names as identical when avg-volume history is missing.
    try:
        if volume >= 5_000_000:
            score += 5
        elif volume >= 1_000_000:
            score += 3
        elif volume < 50_000:
            score -= 4
    except Exception:
        pass

    return _clamp(round(score, 1))


def _classify_setup(price, ma20, ma50, atr, day_high, day_low,
                    high_52w, rel_vol, change_pct, closes,
                    history_ready: bool = True, bars_count: int = 0) -> str:
    """
    Live setup classifier.

    Important guardrail:
    Missing historical bars must NOT be treated as a confirmed trend.
    When bars are thin, ma20/ma50/rel_vol/ATR are not reliable, so classify
    conservatively from the live snapshot only.
    """
    atr = atr if atr and atr > 0 else max(day_high - day_low, price * 0.01, 0.01)

    if closes and len(closes) >= 5:
        recent_range = max(closes[-5:]) - min(closes[-5:])
    else:
        recent_range = max(day_high - day_low, atr)

    avg_range = atr * 5 if atr > 0 else recent_range
    compressed = recent_range < avg_range * 0.75
    near_52w_high = high_52w > 0 and ((high_52w - price) / high_52w) < 0.04

    # Snapshot-only classification. This prevents a bad data state where
    # ma20=price, ma50=price, rel_vol=1.0, atr=1.0 turns every row into
    # Trend Continuation.
    if not history_ready:
        if change_pct <= -5:
            return "Breakdown Risk"
        if change_pct <= -2:
            return "Distribution"
        if change_pct >= 6 and near_52w_high:
            return "Momentum Leader"
        if change_pct >= 3 and near_52w_high:
            return "Compression Breakout Candidate"
        if change_pct >= 2:
            return "Volatility Expansion Candidate"
        if abs(change_pct) < 0.5:
            return "Low Edge - Avoid"
        return "Monitoring"

    if change_pct < -3 and rel_vol >= 1.2:
        return "Breakdown Risk"

    if change_pct < -1 and price < ma20:
        return "Distribution"

    if change_pct > 4 and price >= ma20 and ma20 >= ma50:
        if rel_vol >= 1.3 and near_52w_high:
            return "Momentum Leader"
        if rel_vol >= 1.1:
            return "Trend Continuation"
        return "Volatility Expansion Candidate"

    if change_pct > 1.5 and price >= ma20 and ma20 >= ma50:
        if compressed and near_52w_high:
            return "Compression Breakout Candidate"
        if rel_vol >= 1.2:
            return "Trend Continuation"
        return "Monitoring"

    if compressed and near_52w_high:
        return "Compression Breakout Candidate"

    if compressed:
        return "Volatility Expansion Candidate"

    if near_52w_high and change_pct >= 0:
        return "Compression Breakout Candidate"

    if abs(change_pct) < 0.5 and rel_vol < 0.8:
        return "Low Edge - Avoid"

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


def _infer_regime(change_pct, rel_vol, price, ma20, ma50, history_ready: bool = True) -> str:
    if not history_ready:
        if change_pct >= 5: return "Bull Expansion"
        if change_pct <= -5: return "Bear Expansion"
        if abs(change_pct) < 0.3: return "Compression"
        return "Neutral"

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


def _refresh_historical_bars(force_alpaca: bool = False):
    global _historical_bars, _bars_last_refresh, _bars_loading
    _bars_loading = True
    log.info("Refreshing historical bars…")
    try:
        target_limit = int(os.getenv("RADAR_HISTORICAL_BARS_LIMIT", "252"))

        # ── Step 1: Try Supabase cache first (fast startup) ───────────────────
        if not force_alpaca and not _historical_bars:
            try:
                from backend.supabase_bars import load_bars_from_supabase, supabase_bars_available
                if supabase_bars_available():
                    sb_bars = load_bars_from_supabase()
                    if sb_bars:
                        for sym, bars in sb_bars.items():
                            _historical_bars[sym] = bars[-target_limit:]
                        _bars_last_refresh = time.time()
                        log.info(f"Loaded {len(_historical_bars)} symbols from Supabase cache")
                        # Trigger BME training from Supabase data
                        try:
                            from backend.behavioral_memory import train_batch as _bme_train
                            trained = _bme_train(dict(_historical_bars))
                            log.info(f"BME training from Supabase: {trained}/{len(_historical_bars)} symbols")
                        except Exception as _bme_e:
                            log.warning(f"BME training from Supabase failed: {_bme_e}")
                        return  # Supabase load succeeded — skip Alpaca fetch
            except Exception as _sb_e:
                log.warning(f"Supabase bar load failed — falling back to Alpaca: {_sb_e}")

        # ── Step 2: Fetch from Alpaca (nightly refresh or Supabase miss) ─────
        raw = fetch_bars_batch(SYMBOLS, timeframe="1Day", limit=target_limit)
        _log_mem(f"_refresh_historical_bars: after fetch_bars_batch ({len(raw)} symbols)")
        sample_raw = list(raw.items())[:8]
        if sample_raw:
            log.info(
                "fetch_bars_batch returned "
                + str(len(raw))
                + " symbols; samples="
                + " | ".join(f"{sym}:{len(bars)}" for sym, bars in sample_raw)
            )
        else:
            log.warning("fetch_bars_batch returned 0 symbols")

        loaded = 0
        for sym, bars in raw.items():
            if bars:
                _historical_bars[sym] = bars[-target_limit:]
                loaded += 1
        _bars_last_refresh = time.time()
        _log_mem(f"_refresh_historical_bars: after copying into _historical_bars ({loaded} loaded)")
        log.info(f"Historical bars loaded for {loaded}/{len(SYMBOLS)} symbols; cache={len(_historical_bars)}")

        # ── Step 3: Save to Supabase for next startup ─────────────────────────
        if loaded > 0:
            try:
                from backend.supabase_bars import save_bars_to_supabase
                threading.Thread(
                    target=save_bars_to_supabase,
                    args=(dict(_historical_bars),),
                    daemon=True
                ).start()
                log.info("Supabase bar save started in background")
            except Exception as _sb_save_e:
                log.warning(f"Supabase bar save failed: {_sb_save_e}")

        # ── Trigger BME training immediately after bars load ───────────────────
        try:
            from backend.behavioral_memory import train_batch as _bme_train
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

    # Critical: do not let the first live scan score the universe with empty
    # historical bars. Empty bars force ma20=price, ma50=price, rel_volume=0/1,
    # and collapse every symbol into the same setup bucket. On startup, load
    # bars synchronously once; later refreshes can run in the background.
    if not _historical_bars and not _bars_loading:
        log.info("Historical bar cache empty — loading synchronously before first radar scan")
        _refresh_historical_bars()
    elif time.time() - _bars_last_refresh > 1800 and not _bars_loading:
        threading.Thread(target=_refresh_historical_bars, daemon=True).start()

    log.info(f"Radar scan starting — {len(SYMBOLS)} symbols (lightweight)")
    snapshots = fetch_snapshots(SYMBOLS)
    _log_mem(f"radar_scan: after fetch_snapshots ({len(snapshots)} returned)")

    # Seed SPY benchmark
    try:
        spy_snap = snapshots.get("SPY", {})
        spy_bars = _historical_bars.get("SPY", [])
        if spy_snap and _CONFLUENCE_AVAILABLE:
            spy_result = score_symbol("SPY", spy_snap, spy_bars)
            if spy_result and spy_result.get("change_pct") is not None:
                from backend.confluence_bridge import update_spy_benchmark
                update_spy_benchmark(spy_result["change_pct"])
                log.info(f"SPY benchmark seeded: {spy_result['change_pct']:.2f}%")
    except Exception as _e:
        log.debug(f"SPY benchmark seed error: {_e}")

    # Load divergence watchlist symbols for flagging
    div_symbols = {d["symbol"] for d in DIVERGENCE_WATCHLIST}

    scored = []
    for _idx, symbol in enumerate(SYMBOLS):
        if _idx > 0 and _idx % 200 == 0:
            _log_mem(f"radar_scan: mid-loop at symbol {_idx}/{len(SYMBOLS)}")
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

    # FIX (2026-07-29): user-confirmed OOM crashes from running this
    # scanner in the same process as the main web backend (~1000-symbol
    # scan pushed combined memory past 2GB when it overlapped with other
    # heavy work). Moving this scanner to its own separate Render worker
    # service (mirroring the earlier fix for the nightly campaign
    # pipeline) -- this write makes its results available to the main
    # backend via Redis (already used elsewhere in this codebase, e.g.
    # the heartbeat below) instead of an in-process dict only that
    # process itself could see.
    try:
        if _redis_client:
            import json as _radar_json
            _redis_client.set("radar:cache", _radar_json.dumps(RADAR_CACHE), ex=900)
    except Exception as _rce:
        log.warning(f"Radar cache Redis write failed: {_rce}")

    # Heartbeat
    try:
        if _redis_client:
            _redis_client.set("health:scanner:last_pulse", int(time.time()))
    except Exception as _he:
        log.debug(f"Heartbeat write failed: {_he}")

    LAST_SCAN_TIME = time.time()

    # FIX (2026-07-30): user-confirmed via direct API inspection that
    # "last_scan" was null on the main backend, even though real scans
    # are genuinely completing in this worker process. Same root cause
    # already fixed for DIVERGENCE_WATCHLIST: LAST_SCAN_TIME is a local,
    # in-process variable -- it gets set here, in the worker, but the
    # main backend (a separate process that no longer runs this
    # function itself) never sees this update, since only RADAR_CACHE
    # itself was being pushed to Redis, not this separate variable.
    try:
        if _redis_client:
            _redis_client.set("radar:last_scan_time", str(LAST_SCAN_TIME), ex=900)
    except Exception as _lste:
        log.warning(f"LAST_SCAN_TIME Redis write failed: {_lste}")

    log.info(f"Radar scan complete — {len(scored)} symbols scored (lightweight)")

    _process_events(scored)

# ── EOD Audit — Full ConfluenceEngine on entire universe ──────────────────────

def run_eod_audit():
    """
    UPDATE (2026-08-07): despite the name (kept unchanged to avoid
    touching other references to this job id), this no longer runs
    only nightly -- it's now scheduled every 30 minutes (see
    start_radar_scheduler()). Also fixed to persist the real
    intelligence_score/status/regime/delta for every symbol processed,
    not just the ones exceeding DIVERGENCE_THRESHOLD -- previously the
    real computed value was thrown away for any symbol where the
    engines genuinely agreed, which was the direct cause of "Deep
    engine confirms radar (+0.0)" showing for virtually every symbol
    regardless of what the real comparison actually found.

    Scores all symbols with the doctrine-aligned deep engine (Wyckoff/Weis/
    Livermore-based, see doctrine_deep_engine.py), computes delta vs composite_score.
    Symbols with |delta| >= 15 written to divergence_watchlist in Supabase.
    """
    global DIVERGENCE_WATCHLIST, LAST_EOD_AUDIT_TIME

    if not _DOCTRINE_ENGINE_AVAILABLE:
        log.warning("EOD audit skipped — doctrine deep engine not available")
        return
    if not RADAR_CACHE:
        log.warning("EOD audit skipped — radar cache empty")
        return

    log.info(f"EOD audit starting — {len(RADAR_CACHE)} symbols")
    divergences = []

    for _idx, (symbol, cached) in enumerate(list(RADAR_CACHE.items())):
        if _idx > 0 and _idx % 200 == 0:
            _log_mem(f"eod_audit: mid-loop at symbol {_idx}/{len(RADAR_CACHE)}")
        # FIX (2026-07-30): PRODUCT DECISION -- following a full read-only
        # audit (confirmed by direct file/line citations) that found the
        # previous Layer 2 engine (ConfluenceEngine.evaluate()) computed
        # its "deep score" from twelve weighted families, only ~10-20%
        # of which relate to this product's stated doctrine (Wyckoff /
        # Weis / Livermore behavioral campaign intelligence) -- the rest
        # being Gann geometry, time cycles, astrology, numerology/
        # biblical, Fibonacci, and Elliott waves. Explicit decision: do
        # not reweight, replace the doctrine entirely. This now calls
        # compute_doctrine_deep_score() (backend/doctrine_deep_engine.py),
        # built from seven pillars, all genuine Wyckoff/Weis/Livermore-
        # aligned price/volume evidence, no exotic methodologies at all.
        _live_price = float(cached.get("price") or 0)
        bars = _historical_bars.get(symbol, [])
        composite = cached.get("composite_score", 0)
        if not composite:
            continue
        try:
            result = compute_doctrine_deep_score(symbol, bars, _live_price)
            if _idx < 5 or result.get("new_engine_error"):
                log.warning(
                    f"[EOD_SCORE_CHECK] {symbol}: new_engine_error={result.get('new_engine_error')!r} "
                    f"new_composite_score={result.get('new_composite_score')}"
                )
            new_score = result.get("new_composite_score")
            if new_score is None:
                continue
            delta = round(new_score - composite, 2)

            # FIX (2026-08-07): confirmed the real, direct root cause of
            # "Deep engine confirms radar (+0.0)" showing for virtually
            # every symbol on the Radar Screen -- this loop genuinely
            # computes the real per-symbol deep-engine comparison for
            # every symbol here, but previously only ever persisted the
            # result (below, into DIVERGENCE_WATCHLIST) when it exceeded
            # DIVERGENCE_THRESHOLD. For every symbol where the engines
            # genuinely agree (delta small -- precisely the case this
            # evidence line is meant to describe), the real computed
            # value was thrown away immediately after being computed,
            # so behavioral_transition_engine.py's fallback
            # (deep_score = composite, i.e. delta forced to exactly 0)
            # fired instead -- manufacturing a fake "perfect agreement"
            # regardless of what the real engine actually found. Now
            # persists the real value for every symbol processed, using
            # the same "intelligence_score" key radar_service.py's own
            # existing fallback logic (~line 2164) already checks for
            # first, before falling back.
            if symbol in RADAR_CACHE:
                RADAR_CACHE[symbol]["intelligence_score"]  = new_score
                RADAR_CACHE[symbol]["intelligence_status"] = result.get("new_status") or result.get("status")
                RADAR_CACHE[symbol]["intelligence_regime"] = result.get("new_regime") or result.get("regime")
                RADAR_CACHE[symbol]["intelligence_delta"]  = delta

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

    # Sort by signed delta descending.
    # Positive delta first = deep intelligence scores stronger than radar.
    # Negative delta last = deep intelligence scores weaker than radar.
    divergences.sort(key=lambda x: x.get("delta", 0), reverse=True)
    DIVERGENCE_WATCHLIST = divergences

    log.info(f"EOD audit complete — {len(divergences)} divergences found")

    # Write to Supabase
    _write_divergence_watchlist(divergences)

    # Mark divergence symbols in RADAR_CACHE
    div_set = {d["symbol"] for d in divergences}
    for sym in RADAR_CACHE:
        RADAR_CACHE[sym]["on_divergence_watchlist"] = sym in div_set

    LAST_EOD_AUDIT_TIME = time.time()

    # FIX (2026-07-29): user confirmed the Intelligence Change Detector
    # tab stayed stuck on a stale (June 18) audit date even after a
    # successful manual audit run. Root cause: both the read fallback
    # (get_divergence_watchlist's _load_divergence_watchlist_from_db)
    # and the write path (_write_divergence_watchlist, just above/below)
    # use the same raw DATABASE_URL/psycopg2 connection that's been
    # failing all day with a password authentication error -- confirmed
    # in production logs. On top of that, DIVERGENCE_WATCHLIST is a
    # local in-process variable, so even a working DB write wouldn't
    # help the main backend see it directly (this scanner runs in its
    # own separate worker service now, same issue already fixed for
    # RADAR_CACHE). Writing to Redis here too, bypassing the broken DB
    # path entirely -- see get_divergence_watchlist's Redis read below.
    try:
        if _redis_client:
            import json as _div_json
            _redis_client.set(
                "radar:divergence",
                _div_json.dumps({
                    "symbols": divergences,
                    "last_audit": LAST_EOD_AUDIT_TIME,
                }),
                ex=90000,  # 25h -- comfortably survives until the next nightly run
            )
            log.warning(
                f"[DIVERGENCE_WRITE] Wrote {len(divergences)} symbols to Redis, "
                f"last_audit={LAST_EOD_AUDIT_TIME}"
            )
        else:
            log.warning("[DIVERGENCE_WRITE] Skipped -- _redis_client is not configured")
    except Exception as _dve:
        log.warning(f"[DIVERGENCE_WRITE] Failed: {_dve}")


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
    """
    Load the previous divergence watchlist into memory.

    Primary path: DATABASE_URL/Postgres.
    Fallback path: Supabase REST using SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.

    This fallback is important on Render because the in-memory
    DIVERGENCE_WATCHLIST can be empty after restart while Supabase
    still contains the latest audit rows.
    """
    global DIVERGENCE_WATCHLIST, LAST_EOD_AUDIT_TIME

    rows = []

    # 1) Try direct Postgres first.
    if DATABASE_URL:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute("SELECT * FROM divergence_watchlist ORDER BY delta DESC")
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            log.info(f"Loaded {len(rows)} divergence rows from DATABASE_URL")
        except Exception as e:
            log.warning(f"Could not load divergence watchlist from DATABASE_URL: {e}")

    # 2) Fallback to Supabase REST if Postgres returned nothing.
    if not rows:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if supabase_url and supabase_key:
            try:
                r = _req.get(
                    f"{supabase_url}/rest/v1/divergence_watchlist?order=delta.desc&limit=500",
                    headers={
                        "apikey": supabase_key,
                        "Authorization": f"Bearer {supabase_key}",
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    rows = r.json() if isinstance(r.json(), list) else []
                    log.info(f"Loaded {len(rows)} divergence rows from Supabase REST fallback")
                else:
                    log.warning(f"Supabase REST divergence load failed: {r.status_code} {r.text[:200]}")
            except Exception as e:
                log.warning(f"Could not load divergence watchlist from Supabase REST: {e}")

    DIVERGENCE_WATCHLIST = rows or []

    # Keep the status endpoint useful after restart by deriving last audit from rows.
    try:
        if DIVERGENCE_WATCHLIST:
            latest = max(
                (str(r.get("audited_at", "")) for r in DIVERGENCE_WATCHLIST),
                default="",
            )
            if latest:
                dt = datetime.fromisoformat(latest.replace("Z", "+00:00"))
                LAST_EOD_AUDIT_TIME = dt.timestamp()
    except Exception as e:
        log.debug(f"Could not derive LAST_EOD_AUDIT_TIME from divergence rows: {e}")

    log.info(f"Loaded {len(DIVERGENCE_WATCHLIST)} symbols from divergence watchlist")

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

            intelligence_row = {
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
                "composite_score": RADAR_CACHE.get(symbol, {}).get("composite_score"),
                "trigger": RADAR_CACHE.get(symbol, {}).get("trigger"),
                "invalidation": RADAR_CACHE.get(symbol, {}).get("invalidation"),
                "target1": RADAR_CACHE.get(symbol, {}).get("target1"),
                "target2": RADAR_CACHE.get(symbol, {}).get("target2"),
                "volume_pressure": RADAR_CACHE.get(symbol, {}).get("volume_pressure"),
                "relative_strength": RADAR_CACHE.get(symbol, {}).get("relative_strength"),
                "expansion_node": RADAR_CACHE.get(symbol, {}).get("expansion_node"),
                "behavioral": RADAR_CACHE.get(symbol, {}).get("behavioral"),
                "rel_volume": RADAR_CACHE.get(symbol, {}).get("rel_volume"),
            }

            INTELLIGENCE_CACHE[symbol] = _attach_behavioral_transition(intelligence_row)

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
    """
    Convert Alpaca/Supabase bar dictionaries into ConfluenceEngine Candle objects.

    Important:
    Normalize every timestamp to offset-aware UTC. The divergence engine compares
    candle timestamps against UTC-aware datetimes. A single offset-naive candle
    can raise:
        can't subtract offset-naive and offset-aware datetimes
    """
    candles = []
    for b in bars:
        try:
            raw_ts = b.get("t")

            if raw_ts:
                ts = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            else:
                ts = datetime.now(timezone.utc)

            # Force UTC-aware timestamps for all downstream engine math.
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)

            candles.append(Candle(
                timestamp = ts,
                open      = float(b.get("o", 0)),
                high      = float(b.get("h", 0)),
                low       = float(b.get("l", 0)),
                close     = float(b.get("c", 0)),
                volume    = float(b.get("v", 0)),
            ))
        except Exception as e:
            log.debug(f"Candle conversion skipped: {e}")
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


def _log_mem(tag: str) -> None:
    """
    DIAGNOSTIC INSTRUMENTATION (2026-07-29): added specifically to get
    certainty about the source of repeated production OOM crashes (>2GB),
    rather than continuing to infer it from timing coincidences. Logs
    the actual current process memory (RSS) before and after every
    scheduled background job, so the next crash's logs will show exactly
    which job was running and how much memory it was using at the time --
    real evidence instead of another hypothesis.
    """
    try:
        rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        log.warning(f"[MEM] {tag}: {rss_mb:.1f} MB RSS")
    except Exception as e:
        log.warning(f"[MEM] {tag}: failed to read memory ({e})")


_HEAVY_JOB_LOCK = threading.Lock()


def _instrumented(name: str, fn):
    # FIX (2026-07-29): user-confirmed OOM crash on the new radar scanner
    # worker service, traced to multiple heavy jobs (radar_scan, gex_scan,
    # divergence_scan, snapshot_intraday, and a manually-triggered
    # eod_audit) all running concurrently in the same process -- the
    # exact same memory-stacking pattern already diagnosed and fixed on
    # the main backend earlier today (see campaign_api.py's
    # _cached_endpoint_result single-flight fix), just now happening
    # here instead since this service inherited all of these jobs when
    # it was split out. A shared, non-blocking lock means only one of
    # these heavy jobs can actually run at a time process-wide -- if a
    # second one's scheduled moment arrives while another is still
    # running, it's skipped (not queued) rather than allowed to stack on
    # top and compound memory. All jobs registered below go through this
    # wrapper, so this one change protects all of them uniformly.
    def _wrapped(*args, **kwargs):
        acquired = _HEAVY_JOB_LOCK.acquire(blocking=False)
        if not acquired:
            log.warning(
                f"[SKIP] {name} skipped -- another heavy job is already running "
                f"(prevents concurrent jobs from stacking memory on top of each other)"
            )
            return None
        try:
            _log_mem(f"BEFORE {name}")
            try:
                return fn(*args, **kwargs)
            finally:
                _log_mem(f"AFTER {name}")
        finally:
            _HEAVY_JOB_LOCK.release()
    return _wrapped


def _start_memory_heartbeat(scheduler: "BackgroundScheduler") -> None:
    """Logs memory every 60s regardless of whether any job is running,
    so a gradual leak (steadily rising baseline) is distinguishable from
    a sudden single-job spike (baseline flat, one BEFORE/AFTER pair jumps)."""
    scheduler.add_job(
        lambda: _log_mem("heartbeat"),
        trigger="interval", seconds=60, id="memory_heartbeat",
    )


def start_radar_scheduler():
    global SYMBOLS, _scheduler
    SYMBOLS = load_russell1000()
    log.info(f"Radar scheduler starting — {len(SYMBOLS)} symbols")

    # Load last night's divergence watchlist from Supabase
    _load_divergence_watchlist_from_db()

    # FIX (2026-08-04): load_memory_from_supabase() existed and worked
    # correctly, but was never actually called anywhere -- confirmed via
    # full codebase search. save_memory_to_supabase() (the other half of
    # this same persistence design) genuinely does run after successful
    # training, but with nothing ever restoring it, every worker restart
    # wiped the in-memory bank back to empty regardless of what had
    # already been learned, forcing every symbol back through "NO_MEMORY"
    # each time -- the root cause of "Deep engine confirms radar (+0.0)"
    # and "Strong engine agreement (100.0)" showing identically for every
    # symbol (bme_score was never anything but its 50.0 neutral default).
    # Loading here, before training/scanning starts, means a restart only
    # needs to train genuinely new symbols, not the whole universe again.
    try:
        from backend.behavioral_memory import load_memory_from_supabase as _bme_load
        loaded = _bme_load()
        log.info(f"BME memory bank restored from Supabase: {loaded} symbols")
    except Exception as e:
        log.warning(f"BME Supabase load failed, will train fresh: {e}")

    if ALPACA_API_KEY:
        threading.Thread(target=_refresh_historical_bars, daemon=True).start()
        log.info("Historical bar fetch started in background thread")

    _scheduler = BackgroundScheduler(timezone="UTC")

    # GEX focused scan — runs every 8 minutes during market hours
    if _GEX_AVAILABLE:
        _scheduler.add_job(
            lambda: threading.Thread(target=_instrumented("gex_scan", run_gex_scan), daemon=True).start(),
            trigger="interval",
            seconds=SCAN_INTERVAL_SECONDS,
            id="gex_scan",
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=90),
        )
        log.info("GEX scan scheduled every 8 minutes")

    # Layer 1 — Lightweight universe scan every 8 minutes
    _scheduler.add_job(
        _instrumented("radar_scan", run_radar_scan),
        trigger="interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="radar_scan",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=45),
    )

    # Divergence watchlist intraday deep scan — runs alongside radar scan
    if _INTELLIGENCE_AVAILABLE:
        _scheduler.add_job(
            lambda: threading.Thread(target=_instrumented("divergence_scan", run_divergence_scan), daemon=True).start(),
            trigger="interval",
            seconds=SCAN_INTERVAL_SECONDS,
            id="divergence_scan",
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=60),
        )
        log.info("Divergence watchlist scan scheduled every 8 minutes")

    # UPDATE (2026-08-07): changed from a once-daily cron (8:30 PM ET)
    # to a regular 30-minute interval. Root cause found: this function
    # is the ONLY place that computes the real, per-symbol deep-engine
    # comparison across the full universe, but at once-daily frequency,
    # "Deep engine confirms radar" was showing up to 24 hours stale for
    # the entire trading day. Kept the function/job id unchanged (still
    # "eod_audit") to avoid touching the separate manual-trigger logic
    # and Redis key naming elsewhere that reference this same id --
    # only the schedule itself changes. 30 minutes chosen as a real,
    # moderate improvement (48x more frequent) rather than the most
    # aggressive possible interval, given this processes the full
    # ~900+ symbol universe and given real OOM history on this exact
    # worker service earlier tonight.
    _scheduler.add_job(
        lambda: threading.Thread(target=_instrumented("eod_audit", run_eod_audit), daemon=True).start(),
        trigger="interval",
        minutes=30,
        id="eod_audit",
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=120),
    )
    log.info("EOD audit (deep-engine universe comparison) scheduled every 30 minutes")

    # NOTE (2026-08-04): campaign discovery is intentionally NOT scheduled
    # here. Confirmed after initially adding a job for this here, then
    # catching the mistake: a dedicated, separate Render cron service
    # (sigmalytic-nightly-campaign-refresh, tools/render_nightly_campaign_
    # refresh.py) already runs the real nightly_campaign_pipeline daily at
    # 22:15 UTC -- it was deliberately redesigned (2026-07-28) to run as
    # its own isolated process specifically to avoid memory/worker-
    # recycling conflicts with shared services like this one. Adding a
    # second, independent trigger here would duplicate that real,
    # already-working infrastructure and risk two processes writing to
    # the same campaigns table at different times.

    _scheduler.add_job(
        _instrumented("daily_summary", lambda: send_daily_summary(list(RADAR_CACHE.values()))),
        trigger="cron", hour=12, minute=0, id="daily_summary",
    )
    _scheduler.add_job(
        lambda: threading.Thread(target=_instrumented("grade_signals", grade_pending_signals), daemon=True).start(),
        trigger="cron", hour=21, minute=15, id="grade_signals",
    )
    try:
        from backend.snapshot_service import write_intraday_snapshots, write_daily_close_snapshots
        _scheduler.add_job(
            _instrumented("snapshot_intraday", lambda: write_intraday_snapshots(RADAR_CACHE)),
            trigger="interval", seconds=300, id="snapshot_intraday",
        )
        _scheduler.add_job(
            _instrumented("snapshot_daily_close", lambda: write_daily_close_snapshots(RADAR_CACHE)),
            trigger="cron", hour=20, minute=15, id="snapshot_daily_close",
        )
        log.info("Snapshot writer jobs scheduled")
    except ImportError:
        log.warning("snapshot_service not found — snapshot writing disabled")

    _start_memory_heartbeat(_scheduler)

    # FIX (2026-07-29): user asked to manually trigger run_eod_audit()
    # right now rather than wait for its regular 8:30 PM ET schedule.
    # This scanner runs as a Background Worker with no public HTTP
    # endpoint of its own (that's the whole point of moving it out of
    # the web-serving process). Instead, this checks a Redis flag every
    # 20s -- the main backend (which IS reachable via HTTP) can set that
    # flag through a new admin endpoint, and this picks it up shortly
    # after without needing a redeploy or direct network access to this
    # worker.
    def _check_manual_triggers():
        # FIX (2026-07-29): user-confirmed the manual trigger kept losing
        # the race against regularly-scheduled jobs (radar_scan/gex_scan/
        # divergence_scan fire every 5-8 minutes, leaving little idle
        # time) -- the old version deleted the Redis flag as soon as it
        # was seen, then separately tried to acquire the heavy-job lock;
        # if that lock wasn't free, the whole attempt was silently
        # wasted, and the flag was already gone. Now acquires the lock
        # directly here first -- if unavailable, the flag is left in
        # place so the next check (20s later) retries, instead of
        # consuming the trigger on a failed attempt.
        try:
            if not _redis_client:
                return
            if not _redis_client.get("trigger:eod_audit"):
                return
            acquired = _HEAVY_JOB_LOCK.acquire(blocking=False)
            if not acquired:
                log.info("Manual EOD audit trigger pending -- waiting for a clear window")
                return
            try:
                _redis_client.delete("trigger:eod_audit")
                log.info("Manual EOD audit trigger received -- running now")
                _log_mem("BEFORE eod_audit_manual")
                try:
                    run_eod_audit()
                finally:
                    _log_mem("AFTER eod_audit_manual")
            finally:
                _HEAVY_JOB_LOCK.release()
        except Exception as e:
            log.warning(f"Manual trigger check failed: {e}")

    _scheduler.add_job(
        _check_manual_triggers,
        trigger="interval", seconds=20, id="manual_trigger_check",
    )

    _scheduler.start()
    log.info("Radar scheduler started")


def stop_radar_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Radar scheduler stopped")


def _divergence_bias_summary(rows: list) -> dict:
    """
    Summarize signed divergence direction.

    delta > 0 means deep intelligence is stronger than radar.
    delta < 0 means deep intelligence is weaker than radar.
    """
    rows = rows or []

    positive = [r for r in rows if float(r.get("delta", 0) or 0) > 0]
    negative = [r for r in rows if float(r.get("delta", 0) or 0) < 0]
    neutral  = [r for r in rows if float(r.get("delta", 0) or 0) == 0]

    total = len(rows)
    pos_count = len(positive)
    neg_count = len(negative)
    neutral_count = len(neutral)

    pos_pct = round(pos_count / max(total, 1) * 100, 1)
    neg_pct = round(neg_count / max(total, 1) * 100, 1)

    if total == 0:
        audit_bias = "No Divergence Data"
    elif pos_pct >= 80:
        audit_bias = "Bullish Intelligence Upgrade"
    elif neg_pct >= 80:
        audit_bias = "Bearish Intelligence Downgrade"
    elif pos_count > neg_count:
        audit_bias = "Mixed / Bullish Lean"
    elif neg_count > pos_count:
        audit_bias = "Mixed / Bearish Lean"
    else:
        audit_bias = "Balanced / Mixed"

    return {
        "audit_bias": audit_bias,
        "positive_delta_count": pos_count,
        "negative_delta_count": neg_count,
        "neutral_delta_count": neutral_count,
        "positive_delta_pct": pos_pct,
        "negative_delta_pct": neg_pct,
        "total": total,
        "positive_divergence": sorted(
            positive,
            key=lambda x: float(x.get("delta", 0) or 0),
            reverse=True,
        ),
        "negative_divergence": sorted(
            negative,
            key=lambda x: float(x.get("delta", 0) or 0),
        ),
    }



def _attach_behavioral_transition(row: dict) -> dict:
    """
    Add Behavioral Transition Engine output to a radar/intelligence/divergence row.

    Non-destructive:
      - Returns the original row plus fields.
      - Does not block, delete, or change the base radar score.
    """
    if not row or not isinstance(row, dict):
        return row

    if not _BEHAVIORAL_TRANSITIONS_AVAILABLE:
        return row

    try:
        enriched = dict(row)

        # Normalize common names so the transition engine has enough context.
        if "composite_score" not in enriched and "score" in enriched:
            enriched["composite_score"] = enriched.get("score")

        if "deep_score" not in enriched:
            if "intelligence_score" in enriched:
                enriched["deep_score"] = enriched.get("intelligence_score")
            elif "score" in enriched and "composite_score" in enriched:
                enriched["deep_score"] = enriched.get("score")

        if "intelligence_delta" not in enriched:
            if "delta" in enriched:
                enriched["intelligence_delta"] = enriched.get("delta")
            elif "divergence_delta" in enriched:
                enriched["intelligence_delta"] = enriched.get("divergence_delta")

        if "setup_type" not in enriched and "setup" in enriched:
            enriched["setup_type"] = enriched.get("setup")

        # DIAGNOSTIC (2026-07-29): user-reported every symbol on the Radar
        # Screen tab showing identical zero/dash readiness, probability,
        # edge ratio, grade, etc. Confirmed via isolated testing that
        # evaluate_behavioral_transition() itself produces real, varied,
        # non-zero output when given realistic non-null inputs -- so the
        # function isn't the problem. Also confirmed via log search that
        # the broad exception handler around this code isn't firing
        # (enrichment isn't silently failing). That leaves one remaining
        # explanation: the actual production inputs (volume_pressure,
        # relative_strength, expansion_node, behavioral, composite_score)
        # are themselves null/missing for real symbols. Logging the actual
        # values for a small sample so the next scan's logs show real
        # evidence instead of another guess.
        import random as _diag_random
        if _diag_random.random() < 0.05:
            log.warning(
                f"[RADAR_DIAG] {enriched.get('symbol')}: "
                f"composite_score={enriched.get('composite_score')} "
                f"volume_pressure={enriched.get('volume_pressure')} "
                f"relative_strength={enriched.get('relative_strength')} "
                f"expansion_node={enriched.get('expansion_node')} "
                f"behavioral={enriched.get('behavioral')} "
                f"regime={enriched.get('regime')!r}"
            )

        bt = evaluate_behavioral_transition(enriched)

        enriched["behavioral_transition"] = bt
        enriched["behavioral_state"] = bt.get("behavioral_state")
        enriched["transition_candidate"] = bt.get("transition_candidate")
        enriched["opportunity_state"] = bt.get("opportunity_state")
        enriched["readiness_score"] = bt.get("readiness_score")
        enriched["readiness_label"] = bt.get("confidence_label")
        enriched["trade_side"] = bt.get("side")
        enriched["alert_type"] = bt.get("alert_type")
        enriched["why_this_trade"] = bt.get("why_this_trade")
        enriched["evidence"] = bt.get("evidence")
        enriched["risk_notes"] = bt.get("risk_notes")
        enriched["trader_summary"] = bt.get("trader_summary")
        enriched["setup_risk_reward"] = bt.get("setup_risk_reward")

        # Historical Probability Engine
        try:
            if _PROBABILITY_SERVICE_AVAILABLE:
                hp = get_probability_profile(enriched)
                enriched.update(hp)

                # Trader-facing aliases for frontend cards.
                enriched["historical_success_rate"] = hp.get("historical_success")
                enriched["historical_tradeable_rate"] = hp.get("historical_success")
                enriched["historical_expected_return"] = hp.get("expected_return")
                enriched["historical_edge_ratio"] = hp.get("edge_ratio")
                enriched["historical_grade"] = hp.get("probability_grade")
                enriched["historical_confidence"] = hp.get("probability_confidence")
                # Frontend field name aliases
                enriched["probability"] = hp.get("historical_success")
                enriched["edge_ratio"] = hp.get("edge_ratio")
                enriched["expected_return"] = hp.get("expected_return")
                enriched["historical_matches"] = hp.get("historical_matches")
                enriched["probability_available"] = hp.get("probability_available")
                enriched["probability_grade"] = hp.get("probability_grade")
                # Inject into behavioral_transition dict so frontend card reads it
                if isinstance(enriched.get("behavioral_transition"), dict):
                    raw_prob = hp.get("historical_success")
                    # Frontend _fmt_pct displays value as-is with % sign
                    # historical_success is 0-1, needs to be multiplied by 100
                    prob_display = round(raw_prob * 100, 1) if raw_prob is not None else None
                    enriched["behavioral_transition"]["probability"] = prob_display
                    enriched["behavioral_transition"]["edge_ratio"] = hp.get("edge_ratio")
                    enriched["behavioral_transition"]["expected_return"] = hp.get("expected_return")
                    enriched["behavioral_transition"]["historical_matches"] = hp.get("historical_matches")
                    enriched["behavioral_transition"]["probability_grade"] = hp.get("probability_grade")
                    enriched["behavioral_transition"]["probability_confidence"] = hp.get("probability_confidence")
                    enriched["probability"] = prob_display
                    # Convert all success rate fields to percentage for frontend display
                    enriched["historical_success"] = prob_display
                    enriched["historical_success_rate"] = prob_display
                    enriched["historical_tradeable_rate"] = prob_display
        except Exception as e:
            try:
                log.debug(f"Probability profile attach error {symbol if 'symbol' in locals() else row.get('symbol')}: {e}")
            except Exception:
                pass

        return enriched

    except Exception as e:
        try:
            log.debug(f"Behavioral transition attach error {row.get('symbol')}: {e}")
        except Exception:
            pass
        return row


def _attach_behavioral_transition_many(rows: list) -> list:
    return [_attach_behavioral_transition(r) for r in (rows or [])]


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
    global DIVERGENCE_WATCHLIST, LAST_EOD_AUDIT_TIME

    source = "memory"

    # FIX (2026-07-30): the previous version only checked Redis when
    # DIVERGENCE_WATCHLIST (a local in-process variable) was completely
    # empty -- meaning once this process successfully loaded data into
    # it ONE time (even from a stale source, ages ago), it never checked
    # Redis again for the rest of that process's lifetime, no matter how
    # many fresh audits ran afterward. Confirmed this was the actual
    # cause of the tab staying frozen all night even after multiple
    # genuinely successful audit runs (verified separately via full mid-
    # loop progression logs) -- the backend process had loaded some old
    # snapshot into memory long ago and never looked at Redis again.
    # Now always prefers Redis (the fresh source, written by every real
    # audit run) over local memory, using the last_audit timestamp to
    # decide, and only falls back to whatever's already in local memory
    # or the DB reload if Redis is genuinely unavailable/empty.
    # FIX (2026-07-30): found via the new unambiguous logging -- the
    # write side confirmed a real, successful audit run correctly wrote
    # "0 symbols found" as today's genuine result. This read function
    # correctly adopted that from Redis... and then a few lines below,
    # saw the resulting empty list and treated "empty" as "Redis must
    # have failed", falling through to the stale DB reload and
    # overwriting the correct fresh answer with old June 18 data. Empty
    # is a legitimate real answer, not a failure signal -- tracking
    # whether Redis gave a genuine fresh response at all (regardless of
    # whether the symbol list itself is empty) so the DB fallback is
    # only used when Redis is truly unavailable, not when it correctly
    # reports zero divergences.
    got_fresh_redis_answer = False
    try:
        if _redis_client:
            import json as _div_json
            _raw = _redis_client.get("radar:divergence")
            if _raw:
                _payload = _div_json.loads(_raw)
                _redis_audit_time = _payload.get("last_audit") or 0
                log.warning(
                    f"[DIVERGENCE_READ] Redis has {len(_payload.get('symbols') or [])} symbols, "
                    f"redis_last_audit={_redis_audit_time}, "
                    f"current_local_last_audit={LAST_EOD_AUDIT_TIME}"
                )
                if _redis_audit_time and _redis_audit_time > (LAST_EOD_AUDIT_TIME or 0):
                    DIVERGENCE_WATCHLIST = _payload.get("symbols") or []
                    LAST_EOD_AUDIT_TIME = _redis_audit_time
                    source = "redis"
                    got_fresh_redis_answer = True
                    log.warning(f"[DIVERGENCE_READ] Adopted fresh Redis data ({len(DIVERGENCE_WATCHLIST)} symbols)")
                else:
                    got_fresh_redis_answer = True
                    log.warning("[DIVERGENCE_READ] Redis data not newer than current local data -- kept existing")
            else:
                log.warning("[DIVERGENCE_READ] Redis key 'radar:divergence' does not exist or is empty")
        else:
            log.warning("[DIVERGENCE_READ] _redis_client is not configured")
    except Exception as e:
        log.warning(f"Divergence endpoint Redis read failed: {e}")

    if not DIVERGENCE_WATCHLIST and not got_fresh_redis_answer:
        try:
            _load_divergence_watchlist_from_db()
            source = "database_fallback" if DIVERGENCE_WATCHLIST else "empty"
        except Exception as e:
            source = "fallback_error"
            log.warning(f"Divergence endpoint fallback load failed: {e}")

    # Always sort current endpoint by signed delta, highest positive first.
    sorted_watchlist = sorted(
        DIVERGENCE_WATCHLIST,
        key=lambda x: float(x.get("delta", 0) or 0),
        reverse=True,
    )
    sorted_watchlist = _attach_behavioral_transition_many(sorted_watchlist)
    bias = _divergence_bias_summary(sorted_watchlist)

    return {
        "count":          len(sorted_watchlist),
        "symbols":        sorted_watchlist,
        "last_audit":     LAST_EOD_AUDIT_TIME,
        "threshold":      DIVERGENCE_THRESHOLD,
        "source":         source,

        # New clarity fields for frontend / debugging.
        "audit_bias":     bias["audit_bias"],
        "positive_delta_count": bias["positive_delta_count"],
        "negative_delta_count": bias["negative_delta_count"],
        "neutral_delta_count":  bias["neutral_delta_count"],
        "positive_delta_pct":   bias["positive_delta_pct"],
        "negative_delta_pct":   bias["negative_delta_pct"],
        "positive_divergence":  bias["positive_divergence"],
        "negative_divergence":  bias["negative_divergence"],
        "sort_mode":      "signed_delta_desc",
        "delta_definition": "delta = deep_score - composite_score",
    }


@radar_router.get("/intelligence")
def get_intelligence():
    results = _attach_behavioral_transition_many(list(INTELLIGENCE_CACHE.values()))
    results.sort(
        key=lambda x: (
            x.get("opportunity_state") == "Armed",
            x.get("opportunity_state") == "Setting Up",
            float(x.get("readiness_score", 0) or 0),
            float(x.get("divergence_delta", 0) or 0),
        ),
        reverse=True,
    )
    return {
        "count":        len(results),
        "symbols":      results,
        "last_updated": LAST_INTELLIGENCE_TIME,
        "sort_mode":    "opportunity_state_readiness_delta",
    }


@radar_router.get("/intelligence/{symbol}")
def get_intelligence_symbol(symbol: str):
    sym = symbol.upper().strip()
    div_symbols = {d["symbol"] for d in DIVERGENCE_WATCHLIST}
    if sym not in INTELLIGENCE_CACHE:
        if sym not in div_symbols:
            raise HTTPException(404, f"{sym} is not on the divergence watchlist")
        raise HTTPException(404, f"{sym} intelligence data not yet available — check back after next scan")
    return _attach_behavioral_transition(INTELLIGENCE_CACHE[sym])


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


@radar_router.get("/probability-status")
def get_probability_engine_status():
    if not _PROBABILITY_SERVICE_AVAILABLE:
        return {
            "available": False,
            "reason": "probability_service.py not loaded",
        }
    try:
        return probability_status()
    except Exception as e:
        return {
            "available": False,
            "reason": str(e),
        }




@radar_router.get("/scores")
def _sanitize_numpy(obj):
    """
    Recursively convert numpy scalar types to plain Python types.

    FIX (2026-08-09): defensive, second-layer protection -- a raw
    numpy.int64 (from pandas' .sum() on a boolean Series, inside
    LivermoreVerdictEngine) already caused a real, complete production
    outage of /api/radar/scores once, since FastAPI's jsonable_encoder
    cannot serialize numpy types. Fixed at the source too, but this
    guards against the same class of bug if these engines (or others
    attached here later) are modified again and reintroduce a leak.
    """
    import numpy as np
    if isinstance(obj, dict):
        return {k: _sanitize_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_numpy(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _compute_setup_grade(wyckoff_verdict: dict, weis_verdict: dict) -> dict:
    """
    Genuine, per-symbol Setup Grade -- replaces the old probability_grade,
    which was pooled across an unrelated, fixed 50-symbol historical
    backtest (confirmed to leave most real symbols "Unrated" and to
    treat unrelated stocks as identical whenever they landed in the
    same coarse bucket).

    Built directly from David Weis's own grading framework (discussed
    and confirmed with the user): a genuine "A" setup requires the full
    sweep -> exhaustion -> reclaim sequence AND a genuinely mature
    prior range (multiple, time-separated touches over weeks) -- the
    same sequence without a mature range is a "B" at best, since
    without real pooled stop-loss liquidity behind the level, the
    sweep doesn't trap anyone and the snap-back lacks the structural
    "Cause" to sustain a real move. No sequence at all is a "C".

    Thresholds: spring_score/upthrust_score >= 65 requires the sweep
    (30) AND reclaim (35) components of that score to both genuinely
    be present (its own confirmed minimum, not an arbitrary round
    number). Weis's exhaustion and reclaim sub-scores are binary (0 or
    100 -- an exact pattern match, not a gradual scale), so >= 100 is
    the only meaningful "confirmed" threshold for those.

    FIX (2026-08-09): extended to evaluate both sides -- long (Spring)
    and short (Upthrust) -- using the newly-built mirror-image Weis
    fields (buying_exhaustion, downwave_confirmation) alongside
    Wyckoff's upthrust_score. A stock can't genuinely sweep both below
    support and above resistance at once, so only one side should
    realistically confirm at a time; whichever side confirms
    determines the grade and reported setup_side.
    """
    spring_score = _f(wyckoff_verdict.get("spring_score")) if wyckoff_verdict else 0
    upthrust_score = _f(wyckoff_verdict.get("upthrust_score")) if wyckoff_verdict else 0
    volume_exhaustion = _f(weis_verdict.get("volume_exhaustion")) if weis_verdict else 0
    upwave_confirmation = _f(weis_verdict.get("upwave_confirmation")) if weis_verdict else 0
    buying_exhaustion = _f(weis_verdict.get("buying_exhaustion")) if weis_verdict else 0
    downwave_confirmation = _f(weis_verdict.get("downwave_confirmation")) if weis_verdict else 0
    range_is_mature = bool(weis_verdict.get("range_is_mature")) if weis_verdict else False

    long_sweep = spring_score >= 65
    long_exhaustion = volume_exhaustion >= 100
    long_reclaim = upwave_confirmation >= 100
    long_confirmed = long_sweep and long_exhaustion and long_reclaim

    short_sweep = upthrust_score >= 65
    short_exhaustion = buying_exhaustion >= 100
    short_reclaim = downwave_confirmation >= 100
    short_confirmed = short_sweep and short_exhaustion and short_reclaim

    if long_confirmed:
        side = "Long"
        sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = long_sweep, long_exhaustion, long_reclaim
    elif short_confirmed:
        side = "Short"
        sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = short_sweep, short_exhaustion, short_reclaim
    else:
        # Neither side confirmed -- report whichever side got closer
        # (more of the three conditions true), defaulting to Long on
        # a tie since it's the more common, primary case.
        long_hits = sum([long_sweep, long_exhaustion, long_reclaim])
        short_hits = sum([short_sweep, short_exhaustion, short_reclaim])
        if short_hits > long_hits:
            side = "Short"
            sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = short_sweep, short_exhaustion, short_reclaim
        else:
            side = "Long"
            sweep_confirmed, exhaustion_confirmed, reclaim_confirmed = long_sweep, long_exhaustion, long_reclaim

    sequence_confirmed = sweep_confirmed and exhaustion_confirmed and reclaim_confirmed

    if sequence_confirmed and range_is_mature:
        grade = "A"
        reason = f"{side} sweep, exhaustion, and reclaim confirmed at a mature range boundary."
    elif sequence_confirmed:
        grade = "B"
        reason = f"{side} sweep, exhaustion, and reclaim confirmed, but the prior range is not yet mature."
    else:
        grade = "C"
        missing = []
        if not sweep_confirmed:
            missing.append("sweep")
        if not exhaustion_confirmed:
            missing.append("exhaustion")
        if not reclaim_confirmed:
            missing.append("reclaim")
        reason = f"{side} sequence not confirmed (missing: {', '.join(missing)})."

    return {
        "setup_grade": grade,
        "setup_grade_reason": reason,
        "setup_side": side,
        "setup_sweep_confirmed": sweep_confirmed,
        "setup_exhaustion_confirmed": exhaustion_confirmed,
        "setup_reclaim_confirmed": reclaim_confirmed,
        "setup_range_mature": range_is_mature,
    }


def _attach_methodology_verdicts(rows: list) -> None:
    """
    Attach genuine, separate Wyckoff/Livermore/Weis verdict scores to
    each row, in place. Uses the three already-built, real engines in
    backend/research_engine/ -- each produces its own distinct 0-100
    score and verdict from real price/volume structure, with no
    blending between methodologies.

    Uses fetch_bars_multi() (genuine multi-symbol batching, ~40 per
    request) rather than fetching bars one symbol at a time, so it's
    safe to call across an entire page of results.
    """
    if not rows:
        return

    import pandas as pd
    from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
    from backend.research_engine.livermore_verdict_engine import LivermoreVerdictEngine
    from backend.research_engine.weis_verdict_engine import WeisVerdictEngine

    symbols = [r.get("symbol") for r in rows if r.get("symbol")]
    bars_by_symbol = fetch_bars_multi(symbols, timeframe="1Day", lookback_days=280)

    wyckoff_engine = WyckoffVerdictEngine()
    livermore_engine = LivermoreVerdictEngine()
    weis_engine = WeisVerdictEngine()

    for row in rows:
        symbol = row.get("symbol")
        bars = bars_by_symbol.get(symbol) if isinstance(bars_by_symbol, dict) else None
        if not bars:
            continue
        try:
            df = pd.DataFrame(bars)
            # FIX (2026-08-09): caught before shipping -- Alpaca's raw
            # bars use short keys (o/h/l/c/v/t), but all three engines
            # require full column names (open/high/low/close/volume),
            # confirmed directly from each engine's REQUIRED_COLUMNS.
            # Without this rename, evaluate()/evaluate_bars() would
            # raise "Missing required OHLCV column" every single time.
            df = df.rename(columns={
                "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
            })
            row["wyckoff_verdict"]   = _sanitize_numpy(wyckoff_engine.evaluate_bars(df, symbol=symbol))
            row["livermore_verdict"] = _sanitize_numpy(livermore_engine.evaluate(df, symbol=symbol))
            row["weis_verdict"]      = _sanitize_numpy(weis_engine.evaluate(df, symbol=symbol))
            row.update(_compute_setup_grade(row["wyckoff_verdict"], row["weis_verdict"]))
        except Exception as e:
            log.warning(f"Methodology verdict failed for {symbol} (non-fatal): {e}")


def get_radar_scores(limit: int = 100, offset: int = 0, status: str = None, min_score: float = 0):
    """
    Fast radar scores endpoint.

    Important production rule:
    The backend may scan 1,500+ symbols, but this endpoint must not enrich and
    serialize the entire universe on every frontend request. The frontend has
    an 8-second timeout, so we rank from cached lightweight rows first, slice
    the requested page, and only then attach the heavier behavioral/probability
    display fields.
    """
    global LAST_SCAN_TIME
    try:
        limit = int(limit or 100)
    except Exception:
        limit = 100
    try:
        offset = int(offset or 0)
    except Exception:
        offset = 0

    # Hard caps keep Dash/frontend calls fast even when the full universe is live.
    limit = max(1, min(limit, 250))
    offset = max(0, offset)

    results = list(RADAR_CACHE.values())

    # FIX (2026-07-29): the radar scanner now runs in its own separate
    # worker process (moved out of this shared web-serving process after
    # confirmed OOM crashes). This process's own RADAR_CACHE will be
    # empty here, since the scan no longer runs in this process at all --
    # falling back to Redis, which the scanner worker now writes its
    # results to after every scan.
    if not results and _redis_client:
        try:
            import json as _radar_json
            _raw = _redis_client.get("radar:cache")
            if _raw:
                results = list(_radar_json.loads(_raw).values())
        except Exception as _rre:
            log.warning(f"Radar cache Redis read failed: {_rre}")

    # FIX (2026-07-30): user-confirmed via direct API inspection that
    # "last_scan" was null on the main backend. Same root cause as the
    # RADAR_CACHE fix above -- LAST_SCAN_TIME is set inside run_radar_scan(),
    # which now only runs in the separate scanner worker process; the
    # main backend's own copy of this variable never gets updated.
    if not LAST_SCAN_TIME and _redis_client:
        try:
            _raw_ts = _redis_client.get("radar:last_scan_time")
            if _raw_ts:
                LAST_SCAN_TIME = float(_raw_ts)
        except Exception as _lsre:
            log.warning(f"LAST_SCAN_TIME Redis read failed: {_lsre}")

    # DIAGNOSTIC (2026-07-29): the previous diagnostic (inside the shared
    # _attach_behavioral_transition, called from 5+ different places) showed
    # volume_pressure/relative_strength/expansion_node/behavioral as None
    # for every symbol -- but that function is shared across multiple
    # callers, so those log lines weren't necessarily from *this* endpoint
    # specifically. This logs the RAW RADAR_CACHE values directly, right
    # here in get_radar_scores (the exact endpoint the Radar Screen tab
    # calls), before any enrichment happens -- unambiguous evidence of
    # whether score_symbol's computed values actually make it into the
    # cache this endpoint reads, or whether something is stripping/
    # overwriting them before this point.
    if results:
        _sample = results[0]
        log.warning(
            f"[RADAR_DIAG_RAW] {_sample.get('symbol')}: "
            f"composite_score={_sample.get('composite_score')} "
            f"volume_pressure={_sample.get('volume_pressure')} "
            f"relative_strength={_sample.get('relative_strength')} "
            f"expansion_node={_sample.get('expansion_node')} "
            f"behavioral={_sample.get('behavioral')} "
            f"all_keys={sorted(_sample.keys())}"
        )

    if status:
        results = [r for r in results if r.get("status") == status]
    if min_score > 0:
        results = [r for r in results if float(r.get("composite_score", 0) or 0) >= min_score]

    total = len(results)

    def _safe_float(row, key, default=0.0):
        try:
            return float(row.get(key, default) or default)
        except Exception:
            return default

    def _rank_key(x):
        # FIX (2026-08-08): removed expected_opportunity_score,
        # historical_success, and edge_score -- all three confirmed
        # to come from probability_service.py's profile-lookup system,
        # which pools historical outcomes across a small, fixed set of
        # unrelated stocks (built from a 50-symbol backtest, no
        # traceability back to any individual symbol), not this
        # specific symbol's own price/volume history. Ranking now
        # based only on the genuine, symbol-specific Wyckoff/Weis/
        # Livermore-derived scores: opportunity_state, readiness_score,
        # and composite_score.
        opportunity_state = str(x.get("opportunity_state", ""))
        return (
            opportunity_state == "Armed",
            opportunity_state == "Setting Up",
            _safe_float(x, "readiness_score"),
            _safe_float(x, "composite_score"),
        )

    results.sort(key=_rank_key, reverse=True)

    page = results[offset:offset + limit]

    # Attach heavier transition/probability display information only to the page.
    try:
        page = _attach_behavioral_transition_many(page)
    except Exception as e:
        log.warning(f"Radar score enrichment failed; returning lightweight page: {e}")

    # FIX (2026-08-09): user's critique -- composite_score blends Wyckoff/
    # Weis/Livermore-derived signals together into weighted percentages,
    # diluting each individual methodology's own signal. Confirmed three
    # genuine, separate, already-built engines exist for exactly this
    # (WyckoffVerdictEngine, LivermoreVerdictEngine, WeisVerdictEngine,
    # in backend/research_engine/) but were never connected anywhere on
    # the Radar Screen. Originally scoped to only the top 3 "hero" cards,
    # since fetch_bars_batch() made one sequential API call per symbol --
    # safe for 3, too slow for the full table.
    #
    # UPDATE (2026-08-09): extended to the full page. Found and reused a
    # genuine, already-proven multi-symbol batch pattern elsewhere in
    # this codebase (campaign_enriched_table_api.py's _bars(), using
    # Alpaca's real /v2/stocks/bars endpoint with comma-separated
    # symbols) -- built fetch_bars_multi() on the same pattern, batching
    # 40 symbols per request. A full ~50-100 row page now needs only 2-3
    # requests total, not one sequential call per row, making it safe to
    # cover every row rather than just the top 3.
    try:
        _attach_methodology_verdicts(page)
    except Exception as e:
        log.warning(f"Methodology verdict enrichment failed (non-fatal): {e}")

    return {
        "count":      len(page),
        "total":      total,
        "limit":      limit,
        "offset":     offset,
        "symbols":    page,
        "last_scan":  LAST_SCAN_TIME,
        "data_delay": "15min" if ALPACA_FEED == "iex" else "live",
        "sort_mode":  "opportunity_state_probability_readiness_score",
    }


@radar_router.get("/symbol/{symbol}")
def get_symbol_detail(symbol: str):
    sym = symbol.upper().strip()
    if sym not in RADAR_CACHE:
        raise HTTPException(404, f"{sym} not in radar cache")
    return _attach_behavioral_transition(RADAR_CACHE[sym])


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
        scores  = [_attach_behavioral_transition(RADAR_CACHE[s]) for s in symbols if s in RADAR_CACHE]
        return {"symbols": symbols, "scores": scores}
    except Exception as e:
        return {"symbols": [], "scores": [], "error": str(e)}
