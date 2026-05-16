"""
backend/radar_service.py
------------------------
Sigmalytic Radar — Real-time scoring engine for Russell 1000.

HOW IT WORKS
────────────
1. Loads Russell 1000 symbol list from backend/data/russell1000.csv on startup
2. APScheduler polls Alpaca snapshot endpoint every 60 seconds
3. Scores each symbol across 5 dimensions
4. Keeps top results in memory (RADAR_CACHE dict)
5. Writes meaningful events to Supabase (status changes, threshold crossings)
6. FastAPI endpoints expose the cache to the Dash frontend

ENDPOINTS (register in main.py)
────────────────────────────────
GET /api/radar/scores          — top 100 symbols by composite score
GET /api/radar/symbol/{symbol} — full detail for one symbol
GET /api/radar/status          — service health, last scan time, symbol count
POST /api/radar/watchlist      — add symbol to user watchlist
GET /api/radar/watchlist/{user_id} — get user watchlist with scores
"""

from __future__ import annotations
import os
import uuid
import logging
import time
import pathlib
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests as _req
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from apscheduler.schedulers.background import BackgroundScheduler

from supabase_isolation import get_user_id_from_request
from radar_alerts import maybe_send_alert, send_daily_summary

log = logging.getLogger("radar")

# ── Config ─────────────────────────────────────────────────────────────────────

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_FEED       = os.getenv("ALPACA_FEED", "iex")   # "iex" free | "sip" paid
DATABASE_URL      = os.getenv("DATABASE_URL", "")

SCAN_INTERVAL_SECONDS = 60
SNAPSHOT_INTERVAL     = 300   # write snapshot to Supabase every 5 min per symbol
SCORE_THRESHOLD       = 75    # log event when symbol crosses this score
TOP_N                 = 100   # symbols returned by /api/radar/scores

# ── In-memory cache ────────────────────────────────────────────────────────────

RADAR_CACHE: Dict[str, dict] = {}   # symbol → full score dict
LAST_SCAN_TIME: Optional[float] = None
SYMBOLS: List[str] = []
_prev_statuses: Dict[str, str] = {}   # symbol → last known status
_last_snapshot_times: Dict[str, float] = {}

# ── Router ─────────────────────────────────────────────────────────────────────

radar_router = APIRouter(prefix="/api/radar", tags=["radar"])

# ── Pydantic ───────────────────────────────────────────────────────────────────

class WatchlistAdd(BaseModel):
    symbol: str
    notes:  str = ""

# ── Symbol universe ────────────────────────────────────────────────────────────

def load_russell1000() -> List[str]:
    """Load Russell 1000 symbols from CSV file."""
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
    return symbols if symbols else _fallback_universe()


def _fallback_universe() -> List[str]:
    """Fallback: Magnificent 7 + major sector leaders for demo."""
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

# ── Alpaca data fetch ──────────────────────────────────────────────────────────

def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def fetch_snapshots(symbols: List[str]) -> dict:
    """
    Fetch Alpaca snapshots for a list of symbols in one request.
    Returns dict of symbol → snapshot data.
    Batches into groups of 1000 (Alpaca limit per request).
    """
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
    """
    Fetch historical daily bars for relative strength and ATR calculation.
    Fetches each symbol individually to avoid Alpaca multi-symbol pagination issues.
    """
    from datetime import timedelta
    results = {}
    start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")

    for symbol in symbols:
        try:
            r = _req.get(
                f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars",
                headers=_alpaca_headers(),
                params={
                    "timeframe":  timeframe,
                    "start":      start_date,
                    "feed":       ALPACA_FEED,
                    "sort":       "asc",
                    "adjustment": "raw",
                },
                timeout=10,
            )
            if r.status_code == 200:
                bars = r.json().get("bars") or []
                if bars:
                    results[symbol] = bars
            elif r.status_code == 429:
                log.warning("Rate limit hit during bar fetch — pausing 5s")
                time.sleep(5)
        except Exception as e:
            log.debug(f"Bar fetch error {symbol}: {e}")
        time.sleep(0.05)  # 50ms between requests = ~20 req/sec, well under 200/min limit

    log.info(f"Individual bar fetch complete — {len(results)}/{len(symbols)} symbols loaded")
    return results

# ── Scoring engine ─────────────────────────────────────────────────────────────

def score_symbol(symbol: str, snap: dict, bars: list) -> dict:
    """
    Score a single symbol across 5 dimensions.
    Returns a full score dict with composite, sub-scores, status, and levels.
    """
    # ── Extract snapshot fields ────────────────────────────────────────────────
    daily_bar   = snap.get("dailyBar", {})
    prev_daily  = snap.get("prevDailyBar", {})
    minute_bar  = snap.get("minuteBar", {})
    latest_trade= snap.get("latestTrade", {})
    latest_quote= snap.get("latestQuote", {})

    price       = float(latest_trade.get("p", 0) or daily_bar.get("c", 0) or 0)
    volume      = float(daily_bar.get("v", 0) or 0)
    prev_close  = float(prev_daily.get("c", 1) or 1)
    day_open    = float(daily_bar.get("o", price) or price)
    day_high    = float(daily_bar.get("h", price) or price)
    day_low     = float(daily_bar.get("l", price) or price)
    day_close   = float(daily_bar.get("c", price) or price)
    vwap        = float(daily_bar.get("vw", price) or price)

    if price <= 0 or prev_close <= 0:
        return {}

    change_pct  = ((price - prev_close) / prev_close) * 100

    # ── Historical context from bars ───────────────────────────────────────────
    closes      = [float(b.get("c", 0)) for b in bars if b.get("c")]
    volumes     = [float(b.get("v", 0)) for b in bars if b.get("v")]
    highs       = [float(b.get("h", 0)) for b in bars if b.get("h")]
    lows        = [float(b.get("l", 0)) for b in bars if b.get("l")]

    ma20  = sum(closes[-20:]) / len(closes[-20:]) if len(closes) >= 20 else price
    ma50  = sum(closes[-50:]) / len(closes[-50:]) if len(closes) >= 50 else price
    avg_vol_20 = sum(volumes[-20:]) / len(volumes[-20:]) if len(volumes) >= 20 else volume

    # ATR (14-day)
    atr = _calc_atr(highs, lows, closes, 14)

    # Relative volume
    rel_vol = (volume / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # 52-week high/low
    high_52w = max(highs[-252:]) if len(highs) >= 52 else day_high
    low_52w  = min(lows[-252:])  if len(lows)  >= 52 else day_low

    # ── 1. Confluence Score ────────────────────────────────────────────────────
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

    # ── 2. Expansion Node Score ────────────────────────────────────────────────
    expansion = 50.0
    if atr > 0:
        daily_range_pct = ((day_high - day_low) / atr) if atr > 0 else 1
        if daily_range_pct < 0.6:   expansion += 20   # compression — coiling
        elif daily_range_pct < 0.8: expansion += 10
        elif daily_range_pct > 1.5: expansion -= 10   # already expanded
    # Near 52-week high = expansion candidate
    dist_from_52w_high = ((high_52w - price) / high_52w) if high_52w > 0 else 1
    if dist_from_52w_high < 0.02:   expansion += 15   # within 2% of 52w high
    elif dist_from_52w_high < 0.05: expansion += 8
    elif dist_from_52w_high > 0.20: expansion -= 10   # too far from highs
    if rel_vol > 1.3 and change_pct > 0: expansion += 7
    expansion = _clamp(expansion)

    # ── 3. Relative Strength Score ─────────────────────────────────────────────
    rel_strength = 50.0
    if len(closes) >= 20:
        perf_1m  = ((price - closes[-20]) / closes[-20] * 100) if closes[-20] > 0 else 0
        if perf_1m > 5:    rel_strength += 20
        elif perf_1m > 2:  rel_strength += 12
        elif perf_1m > 0:  rel_strength += 5
        elif perf_1m < -5: rel_strength -= 15
        elif perf_1m < -2: rel_strength -= 8
    if price > ma20 > ma50:  rel_strength += 10   # uptrend alignment
    if price < ma20 < ma50:  rel_strength -= 10   # downtrend
    rel_strength = _clamp(rel_strength)

    # ── 4. Volume Pressure Score ───────────────────────────────────────────────
    vol_pressure = 50.0
    if rel_vol > 3.0:    vol_pressure += 30
    elif rel_vol > 2.0:  vol_pressure += 20
    elif rel_vol > 1.5:  vol_pressure += 12
    elif rel_vol > 1.2:  vol_pressure += 6
    elif rel_vol < 0.7:  vol_pressure -= 15
    elif rel_vol < 0.5:  vol_pressure -= 25
    if change_pct > 0 and rel_vol > 1.5: vol_pressure += 5   # volume confirms up move
    if change_pct < 0 and rel_vol > 1.5: vol_pressure -= 5   # volume confirms down
    vol_pressure = _clamp(vol_pressure)

    # ── 5. Behavioral Score ────────────────────────────────────────────────────
    behavioral = 50.0
    if day_close > day_open:       behavioral += 10   # closed strong
    if price > vwap:               behavioral += 8    # above vwap = buyers in control
    if day_low > prev_close * 0.98:behavioral += 8    # holding above prior close
    if change_pct > 2:             behavioral += 8
    if change_pct > 5:             behavioral += 7
    if change_pct < -3:            behavioral -= 15
    if day_close < day_open:       behavioral -= 8    # closed weak
    behavioral = _clamp(behavioral)

    # ── Composite Score ────────────────────────────────────────────────────────
    composite = (
        confluence   * 0.25 +
        expansion    * 0.20 +
        rel_strength * 0.20 +
        vol_pressure * 0.20 +
        behavioral   * 0.15
    )
    composite = _clamp(round(composite, 1))

    # ── Setup type ─────────────────────────────────────────────────────────────
    setup_type = _classify_setup(
        price, ma20, ma50, atr, day_high, day_low,
        high_52w, rel_vol, change_pct, closes
    )

    # ── Trigger and invalidation levels ───────────────────────────────────────
    trigger      = round(day_high + atr * 0.1, 2)  if atr > 0 else round(price * 1.005, 2)
    invalidation = round(day_low  - atr * 0.1, 2)  if atr > 0 else round(price * 0.99,  2)
    target1      = round(price + atr * 1.0, 2)
    target2      = round(price + atr * 2.0, 2)

    # ── Status ─────────────────────────────────────────────────────────────────
    prev_status = _prev_statuses.get(symbol, "")
    status = _determine_status(
        composite, expansion, rel_vol, change_pct,
        price=price, trigger=trigger, invalidation=invalidation,
        prev_status=prev_status,
    )

    # ── Regime tag ─────────────────────────────────────────────────────────────
    regime = _infer_regime(change_pct, rel_vol, price, ma20, ma50)

    return {
        "symbol":          symbol,
        "price":           round(price, 2),
        "change_pct":      round(change_pct, 2),
        "volume":          int(volume),
        "rel_volume":      round(rel_vol, 2),
        "composite_score": composite,
        "confluence":      round(confluence, 1),
        "expansion_node":  round(expansion, 1),
        "relative_strength": round(rel_strength, 1),
        "volume_pressure": round(vol_pressure, 1),
        "behavioral":      round(behavioral, 1),
        "setup_type":      setup_type,
        "status":          status,
        "trigger":         trigger,
        "invalidation":    invalidation,
        "target1":         target1,
        "target2":         target2,
        "regime":          regime,
        "vwap":            round(vwap, 2),
        "ma20":            round(ma20, 2),
        "ma50":            round(ma50, 2),
        "atr":             round(atr, 2),
        "high_52w":        round(high_52w, 2),
        "low_52w":         round(low_52w, 2),
        "updated_at":      datetime.now(timezone.utc).isoformat(),
        "data_delay":      "15min" if ALPACA_FEED == "iex" else "live",
        "trigger_proximity": round((trigger - price) / price * 100, 2) if price > 0 and trigger > 0 else 0,
    }


def _calc_atr(highs, lows, closes, period=14) -> float:
    if len(highs) < period + 1:
        return (highs[-1] - lows[-1]) if highs and lows else 1.0
    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i]  - closes[i-1]),
        )
        trs.append(tr)
    return round(sum(trs[-period:]) / period, 4)


def _clamp(v: float, lo=0.0, hi=100.0) -> float:
    return max(lo, min(hi, v))


def _classify_setup(price, ma20, ma50, atr, day_high, day_low,
                    high_52w, rel_vol, change_pct, closes) -> str:
    if len(closes) < 5:
        return "Insufficient data"
    recent_range = max(closes[-5:]) - min(closes[-5:])
    avg_range    = atr * 5 if atr > 0 else recent_range
    compressed   = recent_range < avg_range * 0.6

    near_52w_high = high_52w > 0 and ((high_52w - price) / high_52w) < 0.03

    if compressed and near_52w_high:    return "Compression Breakout Candidate"
    if compressed:                      return "Volatility Expansion Candidate"
    if change_pct > 2 and rel_vol > 1.5 and price > ma20: return "Trend Continuation"
    if change_pct > 1 and price > ma20 > ma50:            return "Momentum Leader"
    if change_pct < -3 and rel_vol > 1.5:                 return "Breakdown Risk"
    if change_pct < -1 and price < ma20:                  return "Distribution"
    if abs(change_pct) < 0.5 and rel_vol < 0.8:           return "Low Edge — Avoid"
    return "Monitoring"


def _determine_status(composite, expansion, rel_vol, change_pct,
                      price=0, trigger=0, invalidation=0, prev_status="") -> str:
    """
    Status state machine with 6 states:
    Armed     — setup is ready, trigger is imminent
    Triggered — price has crossed trigger level
    Confirmed — price held above trigger on volume
    Building  — conditions improving, not yet ready
    Watching  — monitoring, setup forming
    Avoid     — poor conditions, high risk
    """
    # Triggered — price crossed above trigger
    if trigger > 0 and price >= trigger:
        if rel_vol >= 1.2:
            return "Triggered"

    # Confirmed — was Triggered and held (prev status check)
    if prev_status == "Triggered" and price >= trigger * 0.998:
        return "Confirmed"

    # Failed — was Triggered but dropped below invalidation
    if prev_status in ("Triggered", "Confirmed") and invalidation > 0 and price < invalidation:
        return "Failed"

    # Armed — score ≥ 75, expansion ≥ 60, within 1.5% of trigger
    if composite >= 75 and expansion >= 60:
        if trigger > 0 and price > 0:
            dist_to_trigger = (trigger - price) / price
            if dist_to_trigger <= 0.015:   # within 1.5% of trigger
                return "Armed"
        else:
            return "Armed"

    # Building — good score, improving
    if composite >= 68:
        return "Building"

    # Avoid — down hard or poor conditions
    if change_pct < -3:
        return "Avoid"
    if composite < 45:
        return "Avoid"

    # Watching — everything else
    return "Watching"


def _infer_regime(change_pct, rel_vol, price, ma20, ma50) -> str:
    if price > ma20 > ma50 and change_pct > 1:  return "Bull Expansion"
    if price > ma20 > ma50 and change_pct < 0:  return "Bull Pullback"
    if price < ma20 < ma50 and change_pct < -1: return "Bear Expansion"
    if price < ma20 < ma50 and change_pct > 0:  return "Bear Rally"
    if abs(change_pct) < 0.3 and rel_vol < 0.8: return "Compression"
    return "Neutral"

# ── Main scan loop ─────────────────────────────────────────────────────────────

_historical_bars: Dict[str, list] = {}   # symbol → list of daily bars
_bars_last_refresh: float = 0


def _refresh_historical_bars():
    """Refresh historical daily bars every 30 minutes."""
    global _historical_bars, _bars_last_refresh
    log.info("Refreshing historical bars…")
    raw = fetch_bars_batch(SYMBOLS, timeframe="1Day", limit=60)
    for sym, bars in raw.items():
        _historical_bars[sym] = bars
    _bars_last_refresh = time.time()
    log.info(f"Historical bars loaded for {len(_historical_bars)} symbols")


def run_radar_scan():
    """Main scan — called by APScheduler every 60 seconds."""
    global LAST_SCAN_TIME

    if not SYMBOLS:
        log.warning("No symbols loaded — skipping scan")
        return

    if not ALPACA_API_KEY:
        log.warning("No Alpaca API key — skipping scan")
        _populate_synthetic_cache()
        return

    # Refresh historical bars every 30 minutes
    if time.time() - _bars_last_refresh > 1800:
        try:
            _refresh_historical_bars()
        except Exception as e:
            log.warning(f"Historical bar refresh failed: {e}")

    log.info(f"Radar scan starting — {len(SYMBOLS)} symbols")
    snapshots = fetch_snapshots(SYMBOLS)

    scored = []
    for symbol in SYMBOLS:
        snap = snapshots.get(symbol, {})
        if not snap:
            continue
        bars = _historical_bars.get(symbol, [])
        try:
            result = score_symbol(symbol, snap, bars)
            if result and result.get("composite_score", 0) > 0:
                scored.append(result)
        except Exception as e:
            log.debug(f"Score error {symbol}: {e}")

    # Update cache
    for s in scored:
        sym = s["symbol"]
        RADAR_CACHE[sym] = s

    LAST_SCAN_TIME = time.time()
    log.info(f"Radar scan complete — {len(scored)} symbols scored")

    # Write events for status changes and threshold crossings
    _process_events(scored)


def _process_events(scored: list):
    """Write meaningful events to Supabase — status changes and threshold crossings."""
    if not DATABASE_URL:
        return
    events = []
    now = time.time()

    for s in scored:
        sym   = s["symbol"]
        score = s["composite_score"]
        status= s["status"]
        prev  = _prev_statuses.get(sym)

        # Status change event
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
            # Send email alert for important status changes
            maybe_send_alert(s, prev, status)
        _prev_statuses[sym] = status

        # Score threshold crossing — only log once per 5 min per symbol
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
    """Populate cache with synthetic data when no Alpaca key is available."""
    import random
    for sym in SYMBOLS[:50]:
        score = random.uniform(45, 92)
        RADAR_CACHE[sym] = {
            "symbol":          sym,
            "price":           round(random.uniform(50, 500), 2),
            "change_pct":      round(random.uniform(-3, 4), 2),
            "volume":          random.randint(500_000, 5_000_000),
            "rel_volume":      round(random.uniform(0.5, 3.0), 2),
            "composite_score": round(score, 1),
            "confluence":      round(random.uniform(40, 95), 1),
            "expansion_node":  round(random.uniform(40, 95), 1),
            "relative_strength": round(random.uniform(40, 95), 1),
            "volume_pressure": round(random.uniform(40, 95), 1),
            "behavioral":      round(random.uniform(40, 95), 1),
            "setup_type":      random.choice([
                "Compression Breakout Candidate",
                "Trend Continuation",
                "Momentum Leader",
                "Volatility Expansion Candidate",
                "Monitoring",
            ]),
            "status":          random.choice(["Armed","Building","Watching","Watching"]),
            "trigger":         round(random.uniform(100, 500), 2),
            "invalidation":    round(random.uniform(80, 400), 2),
            "target1":         round(random.uniform(120, 550), 2),
            "target2":         round(random.uniform(140, 600), 2),
            "regime":          random.choice(["Bull Expansion","Compression","Neutral","Bull Pullback"]),
            "vwap":            round(random.uniform(80, 480), 2),
            "ma20":            round(random.uniform(80, 480), 2),
            "ma50":            round(random.uniform(80, 480), 2),
            "atr":             round(random.uniform(1, 20), 2),
            "high_52w":        round(random.uniform(150, 600), 2),
            "low_52w":         round(random.uniform(50, 300), 2),
            "updated_at":      datetime.now(timezone.utc).isoformat(),
            "data_delay":      "synthetic",
        }

# ── Scheduler ─────────────────────────────────────────────────────────────────

_scheduler: Optional[BackgroundScheduler] = None


def start_radar_scheduler():
    """Called from main.py lifespan on startup."""
    global SYMBOLS, _scheduler
    SYMBOLS = load_russell1000()
    log.info(f"Radar scheduler starting with {len(SYMBOLS)} symbols")

    # Pre-fetch historical bars BEFORE first scan so setup classification works immediately
    if ALPACA_API_KEY:
        try:
            _refresh_historical_bars()
        except Exception as e:
            log.warning(f"Startup bar fetch failed: {e}")

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_radar_scan,
        trigger="interval",
        seconds=SCAN_INTERVAL_SECONDS,
        id="radar_scan",
        next_run_time=datetime.now(timezone.utc),   # run immediately on start
    )
    # Daily summary — sends at 8:00 AM ET (12:00 UTC)
    _scheduler.add_job(
        lambda: send_daily_summary(list(RADAR_CACHE.values())),
        trigger="cron",
        hour=12,
        minute=0,
        id="daily_summary",
    )
    _scheduler.start()
    log.info("Radar scheduler started")


def stop_radar_scheduler():
    """Called from main.py lifespan on shutdown."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Radar scheduler stopped")

# ── API Endpoints ──────────────────────────────────────────────────────────────

@radar_router.get("/status")
def radar_status():
    """Service health and last scan info."""
    return {
        "ok":              True,
        "symbol_count":    len(SYMBOLS),
        "cached_count":    len(RADAR_CACHE),
        "last_scan":       LAST_SCAN_TIME,
        "last_scan_ago":   round(time.time() - LAST_SCAN_TIME, 1) if LAST_SCAN_TIME else None,
        "feed":            ALPACA_FEED,
        "data_delay":      "15min" if ALPACA_FEED == "iex" else "live",
        "bars_loaded":     len(_historical_bars),
        "bars_last_refresh": _bars_last_refresh,
    }


@radar_router.get("/debug/bars")
def debug_bars():
    """Debug — tests bar fetch directly and shows raw Alpaca response."""
    if not ALPACA_API_KEY:
        return {"error": "No Alpaca API key"}

    from datetime import timedelta
    start_date = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")

    # Test single symbol first
    test_sym = "AAPL"
    try:
        r = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/{test_sym}/bars",
            headers={
                "APCA-API-KEY-ID":     ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
            },
            params={
                "timeframe": "1Day",
                "start":     start_date,
                "feed":      ALPACA_FEED,
                "sort":      "asc",
            },
            timeout=10,
        )
        single_result = {
            "status_code": r.status_code,
            "bar_count":   len((r.json().get("bars") or [])) if r.status_code == 200 else 0,
            "sample":      (r.json().get("bars") or [None])[-1] if r.status_code == 200 else r.text[:200],
        }
    except Exception as e:
        single_result = {"error": str(e)}

    # Test multi-symbol
    try:
        r2 = _req.get(
            f"{ALPACA_BASE_URL}/v2/stocks/bars",
            headers={
                "APCA-API-KEY-ID":     ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
            },
            params={
                "symbols":   "AAPL,MSFT,XOM",
                "timeframe": "1Day",
                "start":     start_date,
                "feed":      ALPACA_FEED,
                "sort":      "asc",
            },
            timeout=10,
        )
        bars_data = (r2.json().get("bars") or {}) if r2.status_code == 200 else {}
        multi_result = {
            "status_code":    r2.status_code,
            "symbols_returned": list(bars_data.keys()),
            "aapl_bar_count": len(bars_data.get("AAPL", [])),
        }
    except Exception as e:
        multi_result = {"error": str(e)}

    return {
        "bars_in_cache":  len(_historical_bars),
        "single_symbol":  single_result,
        "multi_symbol":   multi_result,
    }


@radar_router.get("/scores")
def get_radar_scores(limit: int = 100, status: str = None, min_score: float = 0):
    """
    Returns top symbols ranked by composite score.
    Optional filters: status, min_score.
    """
    results = list(RADAR_CACHE.values())

    if status:
        results = [r for r in results if r.get("status") == status]
    if min_score > 0:
        results = [r for r in results if r.get("composite_score", 0) >= min_score]

    results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    return {
        "count":    len(results[:limit]),
        "symbols":  results[:limit],
        "last_scan": LAST_SCAN_TIME,
        "data_delay": "15min" if ALPACA_FEED == "iex" else "live",
    }


@radar_router.get("/symbol/{symbol}")
def get_symbol_detail(symbol: str):
    """Full score detail for a single symbol."""
    sym = symbol.upper().strip()
    if sym not in RADAR_CACHE:
        raise HTTPException(404, f"{sym} not in radar cache")
    return RADAR_CACHE[sym]


@radar_router.post("/watchlist")
def add_to_watchlist(
    payload: WatchlistAdd,
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
):
    """Add a symbol to the user's watchlist."""
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
    """Get user's watchlist with current radar scores."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur  = conn.cursor()
        cur.execute(
            "SELECT symbol FROM user_watchlists WHERE user_id=%s ORDER BY added_at DESC",
            (user_id,)
        )
        rows   = cur.fetchall()
        cur.close()
        conn.close()
        symbols = [r[0] for r in rows]
        scores  = [RADAR_CACHE[s] for s in symbols if s in RADAR_CACHE]
        return {"symbols": symbols, "scores": scores}
    except Exception as e:
        return {"symbols": [], "scores": [], "error": str(e)}
