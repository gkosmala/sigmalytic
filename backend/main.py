# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
""" 
Sigmalytic Backend — FastAPI + Alpaca Real-Time
------------------------------------------------
Endpoints:
  GET  /api/health                    — health check
  GET  /api/stock/{symbol}            — latest quote (REST fallback)
  GET  /api/candles/{symbol}          — historical bars
  WS   /ws/{symbol}                   — real-time price stream
  GET  /api/v1/permissions/{user_id}  — role-based feature permissions
  GET  /api/v1/billing/{user_id}      — billing state
  POST /api/v1/billing/{user_id}/upgrade — simulate upgrade
  GET  /api/radar/scores              — top 100 radar symbols
  GET  /api/radar/symbol/{symbol}     — single symbol detail
  GET  /api/radar/status              — radar service health
  GET  /api/radar/health              — deep health check with heartbeat
  POST /api/v1/alerts/dispatch-confluence-alert — send confluence alert email
  GET  /api/admin/report              — private admin performance report
  GET  /api/admin/report/public       — dev admin report (no auth)
  POST /api/admin/snapshot/write-now  — force snapshot write
  GET  /api/debug/user-emails         — list all alert recipients
  POST /api/admin/run-eod-audit       — manually trigger EOD divergence audit

Run:
  uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations
import sys, os as _os
sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), "."))
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import requests

# ── Geometry engines (safe import) ────────────────────────────────────────────
try:
    from wyckoff_anchor import (
        seed_intelligence_universe as seed_wyckoff,
        run_nightly_wyckoff_recalculation,
    )
    _WYCKOFF_AVAILABLE = True
    print("WYCKOFF_ENGINE: loaded OK", flush=True)
except Exception as _we:
    _WYCKOFF_AVAILABLE = False
    print(f"WYCKOFF_ENGINE: FAILED — {_we}", flush=True)

try:
    from gann_engine import (
        seed_gann_vectors,
        run_nightly_gann_recalculation,
    )
    _GANN_AVAILABLE = True
    print("GANN_ENGINE: loaded OK", flush=True)
except Exception as _ge:
    _GANN_AVAILABLE = False
    print(f"GANN_ENGINE: FAILED — {_ge}", flush=True)

try:
    from behavioral_memory import train_batch as bme_train_batch, get_memory_status, load_memory_from_supabase as bme_load_cache
    _BME_AVAILABLE = True
    print("BME_ENGINE: loaded OK", flush=True)
except Exception as _bme:
    _BME_AVAILABLE = False
    import traceback as _tb
    print(f"BME_ENGINE: FAILED — {_bme}", flush=True)
    print(_tb.format_exc(), flush=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

# ── Optional: load .env locally ────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Path setup — ensures sibling modules resolve on Render ─────────────────
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

# ── Shared engine ──────────────────────────────────────────────────────────
from shared.engine import (
    sanitize_symbol, create_live_update
)

# ── Routers ────────────────────────────────────────────────────────────────
from csv_import       import csv_router
from billing_router   import billing_router
from radar_service    import radar_router, start_radar_scheduler, stop_radar_scheduler
from snapshot_service import snapshot_router
from legal_pages      import legal_router
from email_service    import router as email_router
from preferences_router import preferences_router

# ── Access Control ─────────────────────────────────────────────────────────
from access_control import get_permissions, check_access

# ── Price cache — serves last known price instantly ───────────────────────
_price_cache: dict = {}

def cache_price(symbol: str, price: float, volume: int):
    _price_cache[symbol] = {"price": price, "volume": volume}

def get_cached_price(symbol: str) -> dict | None:
    return _price_cache.get(symbol)

# ── Config ─────────────────────────────────────────────────────────────────
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
ALPACA_WS_URL     = "wss://stream.data.alpaca.markets/v2/iex"
IS_PAPER          = os.getenv("ALPACA_PAPER", "true").lower() == "true"

log = logging.getLogger("sigmalytic")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# ── WebSocket connection manager ───────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self._clients: dict[str, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, symbol: str):
        await ws.accept()
        self._clients.setdefault(symbol, set()).add(ws)
        log.info(f"Client connected for {symbol} — total: {self._client_count()}")

    def disconnect(self, ws: WebSocket, symbol: str):
        self._clients.get(symbol, set()).discard(ws)
        log.info(f"Client disconnected from {symbol} — total: {self._client_count()}")

    async def broadcast(self, symbol: str, payload: dict):
        dead = set()
        for ws in list(self._clients.get(symbol, set())):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.get(symbol, set()).discard(ws)

    def has_clients(self, symbol: str) -> bool:
        return bool(self._clients.get(symbol))

    def _client_count(self) -> int:
        return sum(len(v) for v in self._clients.values())


manager = ConnectionManager()


# ── Alpaca REST helpers ────────────────────────────────────────────────────

def _alpaca_headers() -> dict:
    return {
        "APCA-API-KEY-ID":     ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
    }


def fetch_latest_quote(symbol: str) -> dict[str, Any]:
    if not ALPACA_API_KEY:
        raise HTTPException(503, "Alpaca API key not configured")
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/trades/latest"
    try:
        r = requests.get(url, headers=_alpaca_headers(), timeout=5)
        r.raise_for_status()
        data  = r.json()
        trade = data.get("trade", {})
        return {
            "symbol":    symbol,
            "price":     float(trade.get("p", 0)),
            "volume":    int(trade.get("s", 0)),
            "timestamp": trade.get("t", ""),
            "source":    "alpaca_trade",
        }
    except requests.HTTPError as e:
        raise HTTPException(e.response.status_code, f"Alpaca error: {e}")
    except Exception as e:
        raise HTTPException(503, f"Data fetch failed: {e}")


def fetch_bars(symbol: str, timeframe: str = "1Min", limit: int = 200) -> list[dict]:
    """
    Fetch REAL OHLCV bars from Alpaca only.

    No synthetic candles are generated here. If Alpaca credentials are missing,
    Alpaca rejects the request, or Alpaca returns no bars, this function returns
    an empty list and logs the reason.
    """
    clean = sanitize_symbol(symbol)
    if not clean:
        log.warning(f"BAR_FETCH_INVALID_SYMBOL {symbol!r}")
        return []

    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        log.warning("BAR_FETCH_SKIPPED: Alpaca API key/secret not configured")
        return []

    # Normalize app timeframe labels into Alpaca timeframe names.
    tf_map = {
        "1m": "1Min",
        "1min": "1Min",
        "1Min": "1Min",
        "5m": "5Min",
        "5min": "5Min",
        "5Min": "5Min",
        "15m": "15Min",
        "15min": "15Min",
        "15Min": "15Min",
        "1h": "1Hour",
        "1H": "1Hour",
        "1Hour": "1Hour",
        "1d": "1Day",
        "1D": "1Day",
        "1Day": "1Day",
        "1w": "1Week",
        "1W": "1Week",
        "1Week": "1Week",
    }
    alpaca_timeframe = tf_map.get(str(timeframe), str(timeframe) or "5Min")

    # Keep limits reasonable for chart rendering and Alpaca response size.
    try:
        limit = int(limit)
    except Exception:
        limit = 200
    limit = max(1, min(limit, 1000))

    url = f"{ALPACA_BASE_URL}/v2/stocks/{clean}/bars"
    params = {
        "timeframe": alpaca_timeframe,
        "limit": limit,
        "feed": os.getenv("ALPACA_FEED", "sip"),
        "adjustment": "raw",
        "sort": "asc",
    }

    try:
        r = requests.get(url, headers=_alpaca_headers(), params=params, timeout=10)

        if r.status_code != 200:
            log.warning(
                f"BAR_FETCH_FAILED {clean} {alpaca_timeframe}: "
                f"status={r.status_code} body={r.text[:300]}"
            )
            return []

        raw = r.json()
        bars = raw.get("bars", []) if isinstance(raw, dict) else []

        if not bars:
            log.warning(f"BAR_FETCH_EMPTY {clean} {alpaca_timeframe}: raw={str(raw)[:300]}")
            return []

        cleaned = []
        for b in bars:
            try:
                cleaned.append({
                    "o": float(b["o"]),
                    "h": float(b["h"]),
                    "l": float(b["l"]),
                    "c": float(b["c"]),
                    "v": int(b.get("v", 0) or 0),
                    "t": b.get("t", ""),
                })
            except Exception as row_error:
                log.debug(f"BAR_ROW_SKIPPED {clean}: {row_error} row={b}")

        log.info(f"BAR_FETCH_OK {clean} {alpaca_timeframe}: bars={len(cleaned)} feed={params['feed']}")
        return cleaned

    except Exception as e:
        log.warning(f"BAR_FETCH_EXCEPTION {clean} {alpaca_timeframe}: {e}")
        return []

# ── Alpaca WebSocket stream ────────────────────────────────────────────────

async def alpaca_stream(symbol: str):
    import websockets
    sequence = 0
    backoff  = 1
    while True:
        try:
            log.info(f"Connecting to Alpaca stream for {symbol}…")
            async with websockets.connect(ALPACA_WS_URL, ping_interval=20) as ws:
                backoff = 1
                await ws.send(json.dumps({
                    "action": "auth",
                    "key":    ALPACA_API_KEY,
                    "secret": ALPACA_API_SECRET,
                }))
                await ws.send(json.dumps({
                    "action": "subscribe",
                    "trades": [symbol],
                }))
                async for raw in ws:
                    messages = json.loads(raw)
                    for msg in messages:
                        msg_type = msg.get("T")
                        if msg_type == "t":
                            price  = float(msg.get("p", 0))
                            volume = int(msg.get("s", 0))
                            sequence += 1
                            update = create_live_update(symbol, price, volume, sequence)
                            await manager.broadcast(symbol, update.to_dict())
                        elif msg_type == "error":
                            log.error(f"Alpaca stream error: {msg}")
        except Exception as e:
            log.warning(f"Alpaca stream disconnected ({symbol}): {e} — retrying in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


# ── Background stream registry ─────────────────────────────────────────────

_active_streams: dict[str, asyncio.Task] = {}


def ensure_stream(symbol: str):
    if symbol not in _active_streams or _active_streams[symbol].done():
        task = asyncio.create_task(alpaca_stream(symbol))
        _active_streams[symbol] = task
        log.info(f"Started Alpaca stream task for {symbol}")


# ── EOD Audit — runs nightly at 8:30 PM ET ────────────────────────────────

async def run_eod_audit():
    """
    Scores all cached symbols with the full ConfluenceEngine.
    Symbols where deep score diverges >=15 pts from composite
    are written to the divergence_watchlist table in Supabase.
    These symbols receive intraday deep scoring the following day.
    """
    from datetime import datetime as _dt, timezone as _tz

    log.info("EOD AUDIT: Starting full ConfluenceEngine run on all symbols...")

    try:
        from confluence_engine import ConfluenceEngine, MarketData, OptionsData
        from radar_service import RADAR_CACHE
    except Exception as e:
        log.error(f"EOD AUDIT: Import failed — {e}")
        return

    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    if not supabase_url or not supabase_key:
        log.error("EOD AUDIT: Supabase credentials missing — aborting")
        return

    if not RADAR_CACHE:
        log.error("EOD AUDIT: RADAR_CACHE is empty — aborting")
        return

    engine = ConfluenceEngine()
    divergence_rows = []
    processed = 0
    errors = 0

    log.info(f"EOD AUDIT: Processing {len(RADAR_CACHE)} symbols...")

    for symbol, cached in list(RADAR_CACHE.items()):
        try:
            composite_score = cached.get("composite_score", 0)
            price = cached.get("price", 0)

            if composite_score < 30 or price <= 0:
                continue

            market = MarketData(
                symbol               = symbol,
                price                = price,
                previous_close       = cached.get("prev_close") or price,
                day_open             = cached.get("day_open") or price,
                day_high             = cached.get("day_high") or price,
                day_low              = cached.get("day_low") or price,
                volume               = int(cached.get("volume", 0)),
                avg_volume           = int(cached.get("avg_volume", 1)) or 1,
                vwap                 = cached.get("vwap"),
                atr                  = cached.get("atr"),
                benchmark_change_pct = cached.get("benchmark_change_pct"),
            )

            result = engine.evaluate(market, OptionsData())
            deep_score = result.score
            delta = abs(deep_score - composite_score)
            processed += 1

            if delta >= 15:
                divergence_rows.append({
                    "symbol"         : symbol,
                    "composite_score": round(composite_score, 2),
                    "deep_score"     : round(deep_score, 2),
                    "delta"          : round(delta, 2),
                    "direction"      : result.direction,
                    "old_status"     : cached.get("status", "Unknown"),
                    "new_status"     : result.status,
                    "regime"         : result.regime,
                    "price"          : round(price, 4),
                    "audited_at"     : _dt.now(_tz.utc).isoformat(),
                })

        except Exception as e:
            errors += 1
            if errors <= 10:
                log.warning(f"EOD AUDIT: Error on {symbol} — {e}")

    log.info(
        f"EOD AUDIT: Processed {processed} symbols | "
        f"{len(divergence_rows)} divergences found | "
        f"{errors} errors"
    )

    if not divergence_rows:
        log.info("EOD AUDIT: No divergences found — watchlist unchanged")
        return

    # ── Write to Supabase ────────────────────────────────────────────────
    headers = {
        "apikey"       : supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type" : "application/json",
        "Prefer"       : "return=minimal",
    }

    try:
        # Delete all existing rows first
        del_resp = requests.delete(
            f"{supabase_url}/rest/v1/divergence_watchlist",
            headers={**headers, "Prefer": ""},
            params={"audited_at": "not.is.null"},
            timeout=15,
        )
        log.info(f"EOD AUDIT: Cleared old watchlist rows — status {del_resp.status_code}")
    except Exception as e:
        log.warning(f"EOD AUDIT: Failed to clear old rows — {e}")

    # Insert new rows in batches of 50
    batch_size = 50
    written = 0
    for i in range(0, len(divergence_rows), batch_size):
        batch = divergence_rows[i:i + batch_size]
        try:
            resp = requests.post(
                f"{supabase_url}/rest/v1/divergence_watchlist",
                headers=headers,
                json=batch,
                timeout=15,
            )
            if resp.status_code in (200, 201):
                written += len(batch)
                log.info(f"EOD AUDIT: Wrote batch {i // batch_size + 1} ({len(batch)} rows)")
            else:
                log.error(f"EOD AUDIT: Supabase write failed — {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            log.error(f"EOD AUDIT: Supabase write exception — {e}")

    log.info(f"EOD AUDIT: Complete — {written}/{len(divergence_rows)} rows written to divergence_watchlist")


def _eod_audit_scheduler():
    """Background thread — fires run_eod_audit() nightly at 8:30 PM ET (00:30 UTC)."""
    import time as _t
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    while True:
        now = _dt.now(_tz.utc)
        # 8:30 PM ET = 00:30 UTC (during EDT, UTC-4)
        target = now.replace(hour=0, minute=30, second=0, microsecond=0)
        if now >= target:
            target += _td(days=1)
        sleep_secs = (target - now).total_seconds()
        log.info(f"EOD AUDIT: Scheduler sleeping {sleep_secs / 3600:.1f}h until next run at 00:30 UTC")
        _t.sleep(sleep_secs)

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_eod_audit())
            loop.close()
        except Exception as e:
            log.error(f"EOD AUDIT: Scheduler run failed — {e}")


# ── App lifecycle ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _BME_AVAILABLE
    log.info("Sigmalytic backend starting…")
    start_radar_scheduler()

    # ── Nightly geometry recalculation at 20:00 UTC ───────────────────────
    import threading as _threading
    from datetime import datetime as _dt, timezone as _tz
    import time as _t

    def _nightly_geometry_runner():
        """Runs Wyckoff + Gann recalculation nightly at 20:00 UTC."""
        while True:
            now = _dt.now(_tz.utc)
            target = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=target.day + 1)
            sleep_secs = (target - now).total_seconds()
            _t.sleep(sleep_secs)
            if _WYCKOFF_AVAILABLE:
                try:
                    run_nightly_wyckoff_recalculation()
                except Exception as _e:
                    log.warning(f"Nightly Wyckoff failed: {_e}")
            if _GANN_AVAILABLE:
                try:
                    run_nightly_gann_recalculation()
                except Exception as _e:
                    log.warning(f"Nightly Gann failed: {_e}")
            if globals().get("_BME_AVAILABLE", False):
                try:
                    from radar_service import _historical_bars
                    bme_train_batch(_historical_bars)
                    log.info("Nightly BME retraining complete.")
                except Exception as _e:
                    log.warning(f"Nightly BME failed: {_e}")

    _threading.Thread(target=_nightly_geometry_runner, daemon=True).start()
    log.info("Nightly geometry scheduler started (20:00 UTC)")

    # ── EOD Audit scheduler — 8:30 PM ET (00:30 UTC) ─────────────────────
    _threading.Thread(target=_eod_audit_scheduler, daemon=True).start()
    log.info("EOD audit scheduler started (runs nightly at 8:30 PM ET)")

    # ── Initial BME — load cache from Supabase first, then retrain ────────
    if globals().get("_BME_AVAILABLE", False):
        try:
            loaded = bme_load_cache()
            log.info(f"BME cache loaded from Supabase: {loaded} symbols")
        except Exception as _e:
            log.warning(f"BME cache load failed: {_e}")

        def _initial_bme_training():
            import time as _t
            _t.sleep(180)  # Wait 3 min for radar bars to load
            last_trained = 0
            for _attempt in range(48):  # Try every 5 min for 4 hours
                try:
                    from radar_service import _historical_bars
                    current = len(_historical_bars)
                    if current > 0 and current != last_trained:
                        trained = bme_train_batch(dict(_historical_bars))
                        last_trained = current
                        log.info(f"BME training pass {_attempt+1}: {trained}/{current} symbols trained")
                        if current > 1000:
                            log.info("BME fully trained on complete universe.")
                            break
                except Exception as _e:
                    log.warning(f"BME training attempt {_attempt+1} failed: {_e}")
                _t.sleep(300)

        import threading as _bme_thread
        _bme_thread.Thread(target=_initial_bme_training, daemon=True).start()
        log.info("BME training thread started (3min initial delay, then every 5 min)")

    # ── Supabase heartbeat — prevents free tier auto-pause ─────────────────
    import threading, time as _time

    def _supabase_heartbeat():
        import requests as _req
        while True:
            try:
                _supabase_url = os.getenv("SUPABASE_URL", "")
                _supabase_key = os.getenv("SUPABASE_ANON_KEY", "")
                if not _supabase_url:
                    _time.sleep(3600)
                    continue
                _req.get(
                    f"{_supabase_url}/rest/v1/user_preferences?limit=1",
                    headers={"apikey": _supabase_key, "Authorization": f"Bearer {_supabase_key}"},
                    timeout=5
                )
                log.info("Supabase heartbeat OK")
            except Exception as e:
                log.warning(f"Supabase heartbeat failed: {e}")
            _time.sleep(3600)

    threading.Thread(target=_supabase_heartbeat, daemon=True).start()

    yield
    stop_radar_scheduler()
    for task in _active_streams.values():
        task.cancel()
    log.info("Sigmalytic backend stopped.")


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="Sigmalytic Decision Intelligence API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register all routers ───────────────────────────────────────────────────
app.include_router(csv_router)
app.include_router(billing_router)
app.include_router(radar_router)
app.include_router(snapshot_router)
app.include_router(legal_router)
app.include_router(email_router)
app.include_router(preferences_router)

# ── REST endpoints ─────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":     "ok",
        "timestamp":  time.time(),
        "alpaca_key": bool(ALPACA_API_KEY),
        "streams":    list(_active_streams.keys()),
    }


@app.get("/api/auth/reset-form")
async def reset_form():
    from fastapi.responses import HTMLResponse
    html = """
<!DOCTYPE html>
<html>
<head>
<title>Sigmalytic — Reset Password</title>
<style>
body{margin:0;padding:0;background:#0d1b2e;font-family:'Helvetica Neue',Arial,sans-serif;
     display:flex;align-items:center;justify-content:center;min-height:100vh;}
.box{background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:20px;
     padding:40px;width:360px;box-shadow:0 20px 60px rgba(0,0,0,.4);}
h2{color:#f1f5f9;font-size:20px;margin:0 0 24px;text-align:center;}
.logo{text-align:center;font-size:36px;font-weight:900;color:#34d399;margin-bottom:8px;}
.sub{text-align:center;font-size:11px;color:#64748b;letter-spacing:.2em;margin-bottom:32px;}
label{display:block;font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;
      letter-spacing:.1em;margin-bottom:6px;}
input{width:100%;box-sizing:border-box;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.08);
      border-radius:8px;padding:12px 16px;color:#f1f5f9;font-size:14px;outline:none;
      font-family:inherit;margin-bottom:16px;}
button{width:100%;background:#2d8f6f;color:white;border:none;border-radius:8px;
       padding:14px;font-size:14px;font-weight:700;cursor:pointer;}
.msg{text-align:center;font-size:13px;margin-top:16px;min-height:20px;}
.back{text-align:center;margin-top:16px;}
.back a{color:#34d399;font-size:12px;text-decoration:none;}
</style>
</head>
<body>
<div class="box">
  <div class="logo">Σ</div>
  <div class="sub">SIGMALYTIC QUANT CORPORATION</div>
  <h2>Reset Password</h2>
  <label>Your Email Address</label>
  <input type="email" id="email" placeholder="you@example.com">
  <button onclick="sendReset()">Send Reset Email</button>
  <div class="msg" id="msg"></div>
  <div class="back"><a href="https://sigmalytic-frontend.onrender.com">← Back to Sigmalytic</a></div>
</div>
<script>
async function sendReset() {
  var email = document.getElementById('email').value.trim();
  var msg = document.getElementById('msg');
  if (!email) { msg.style.color='#f87171'; msg.innerText='Enter your email first.'; return; }
  msg.style.color='#94a3b8'; msg.innerText='Sending...';
  try {
    var r = await fetch('/api/auth/reset-password?email=' + encodeURIComponent(email), {method:'GET'});
    var d = await r.json();
    if (d.ok) {
      msg.style.color='#34d399';
      msg.innerText='✅ Reset email sent! Check your inbox.';
    } else {
      msg.style.color='#f87171';
      msg.innerText='Error: ' + (d.error || 'Try again.');
    }
  } catch(e) {
    msg.style.color='#f87171';
    msg.innerText='Error: ' + e.message;
  }
}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/api/auth/set-password")
async def set_password_page(access_token: str = "", refresh_token: str = "", type: str = ""):
    from fastapi.responses import HTMLResponse
    html = f"""
<!DOCTYPE html>
<html>
<head>
<title>Sigmalytic — Set New Password</title>
<style>
body{{margin:0;padding:0;background:#0d1b2e;font-family:'Helvetica Neue',Arial,sans-serif;
     display:flex;align-items:center;justify-content:center;min-height:100vh;}}
.box{{background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:20px;
     padding:40px;width:360px;box-shadow:0 20px 60px rgba(0,0,0,.4);}}
h2{{color:#f1f5f9;font-size:20px;margin:0 0 24px;text-align:center;}}
.logo{{text-align:center;font-size:36px;font-weight:900;color:#34d399;margin-bottom:8px;}}
.sub{{text-align:center;font-size:11px;color:#64748b;letter-spacing:.2em;margin-bottom:32px;}}
label{{display:block;font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;
      letter-spacing:.1em;margin-bottom:6px;}}
input{{width:100%;box-sizing:border-box;background:rgba(0,0,0,.3);border:1px solid rgba(255,255,255,.08);
      border-radius:8px;padding:12px 16px;color:#f1f5f9;font-size:14px;outline:none;
      font-family:inherit;margin-bottom:16px;}}
button{{width:100%;background:#2d8f6f;color:white;border:none;border-radius:8px;
       padding:14px;font-size:14px;font-weight:700;cursor:pointer;}}
.msg{{text-align:center;font-size:13px;margin-top:16px;min-height:20px;}}
.back{{text-align:center;margin-top:16px;}}
.back a{{color:#34d399;font-size:12px;text-decoration:none;}}
</style>
</head>
<body>
<div class="box">
  <div class="logo">Σ</div>
  <div class="sub">SIGMALYTIC QUANT CORPORATION</div>
  <h2>Set New Password</h2>
  <label>New Password</label>
  <input type="password" id="password" placeholder="Min 6 characters">
  <label>Confirm Password</label>
  <input type="password" id="confirm" placeholder="Repeat password">
  <button onclick="setPassword()">Set New Password</button>
  <div class="msg" id="msg"></div>
  <div class="back"><a href="https://sigmalytic-frontend.onrender.com">← Back to Sigmalytic</a></div>
</div>
<script>
var ACCESS_TOKEN = "{access_token}";
async function setPassword() {{
  var pwd = document.getElementById('password').value;
  var cfm = document.getElementById('confirm').value;
  var msg = document.getElementById('msg');
  if (!pwd || pwd.length < 6) {{ msg.style.color='#f87171'; msg.innerText='Min 6 characters.'; return; }}
  if (pwd !== cfm) {{ msg.style.color='#f87171'; msg.innerText='Passwords do not match.'; return; }}
  msg.style.color='#94a3b8'; msg.innerText='Updating...';
  try {{
    var r = await fetch('/api/auth/update-password?token=' + encodeURIComponent(ACCESS_TOKEN) + '&password=' + encodeURIComponent(pwd));
    var d = await r.json();
    if (d.ok) {{
      msg.style.color='#34d399';
      msg.innerText='✅ Password updated! Redirecting to login...';
      setTimeout(function(){{ window.location='https://sigmalytic-frontend.onrender.com'; }}, 2000);
    }} else {{
      msg.style.color='#f87171';
      msg.innerText='Error: ' + (d.error || 'Try again.');
    }}
  }} catch(e) {{
    msg.style.color='#f87171';
    msg.innerText='Error: ' + e.message;
  }}
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/api/auth/update-password")
async def update_password(token: str = "", password: str = ""):
    SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    if not token or not password:
        return {"ok": False, "error": "Token and password required"}
    try:
        r = requests.put(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_ANON_KEY,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"password": password},
            timeout=10,
        )
        log.info(f"Update password response: {r.status_code} — {r.text[:200]}")
        if r.status_code == 200:
            return {"ok": True}
        return {"ok": False, "error": r.text[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/auth/test-login")
async def test_login(email: str = "", password: str = ""):
    SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    try:
        r = requests.post(
            f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "password": password},
            timeout=10,
        )
        return {"status": r.status_code, "response": r.json()}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/auth/reset-password")
async def request_password_reset(email: str = ""):
    email = email.strip()
    log.info(f"Password reset requested for: {email!r}")
    if not email:
        return {"ok": False, "error": "Email required"}
    SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
    try:
        r = requests.post(
            f"{SUPABASE_URL}/auth/v1/recover",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={
                "email": email,
                "redirect_to": "https://sigmalytic-backend.onrender.com/api/auth/set-password"
            },
            timeout=10,
        )
        log.info(f"Supabase recover: {r.status_code} — {r.text[:200]}")
        if r.status_code in (200, 204):
            return {"ok": True, "message": f"Reset email sent to {email}"}
        return {"ok": False, "error": f"Supabase {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/api/scoreboard/clean-duplicates")
async def clean_duplicates():
    import threading
    result = {"deleted": 0, "error": None}

    def _run():
        try:
            from scoreboard_service import clear_duplicate_signals
            result["deleted"] = clear_duplicate_signals()
        except Exception as e:
            result["error"] = str(e)
            log.error(f"Duplicate clear error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)

    if result["error"]:
        return {"ok": False, "message": result["error"]}
    return {"ok": True, "deleted": result["deleted"]}


@app.get("/api/scoreboard")
async def get_scoreboard():
    from scoreboard_service import get_scoreboard_stats
    return get_scoreboard_stats()


@app.post("/api/scoreboard/grade-now")
async def grade_now():
    import threading
    result = {"error": None}

    def _run():
        try:
            from scoreboard_service import grade_pending_signals
            log.info("Manual grader triggered via API")
            grade_pending_signals()
            log.info("Manual grader finished")
        except Exception as e:
            result["error"] = str(e)
            log.error(f"Manual grader error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=120)

    if result["error"]:
        return {"ok": False, "message": result["error"]}
    
return {
        "ok": True,
        "message": "Scoreboard repair complete",
        "result": result["repair"]
    }


# ── EOD Audit — manual trigger ─────────────────────────────────────────────

@app.post("/api/admin/run-eod-audit")
async def trigger_eod_audit():
    """Manually trigger the EOD divergence audit. Runs async in background."""
    asyncio.create_task(run_eod_audit())
    return {
        "ok": True,
        "status": "EOD audit started",
        "message": "Running in background — check Render logs for progress. Takes 2-3 minutes.",
    }


@app.get("/api/admin/divergence-watchlist")
async def get_divergence_watchlist():
    """Returns current contents of the divergence watchlist from Supabase."""
    supabase_url = os.getenv("SUPABASE_URL", "")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not supabase_url or not supabase_key:
        return {"error": "Supabase not configured"}
    try:
        r = requests.get(
            f"{supabase_url}/rest/v1/divergence_watchlist?order=delta.desc&limit=100",
            headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
            timeout=10,
        )
        data = r.json()
        return {"count": len(data), "symbols": data}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/options/test/{symbol}")
async def test_options(symbol: str):
    sym = symbol.upper().strip()
    results = {}
    try:
        r1 = requests.get(
            f"https://data.alpaca.markets/v1beta1/options/snapshots/{sym}",
            headers={"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET},
            params={"feed": "indicative", "limit": 5},
            timeout=10,
        )
        data1 = r1.json() if r1.status_code == 200 else {}
        results["test1_no_filter"] = {
            "status": r1.status_code,
            "contracts": len(data1.get("snapshots", {})),
            "raw": r1.text[:300] if r1.status_code != 200 else "OK",
        }
    except Exception as e:
        results["test1_no_filter"] = {"error": str(e)}
    try:
        r2 = requests.get(
            f"https://data.alpaca.markets/v1beta1/options/snapshots/{sym}",
            headers={"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET},
            params={"limit": 5},
            timeout=10,
        )
        data2 = r2.json() if r2.status_code == 200 else {}
        results["test2_no_feed"] = {
            "status": r2.status_code,
            "contracts": len(data2.get("snapshots", {})),
            "raw": r2.text[:300] if r2.status_code != 200 else "OK",
        }
    except Exception as e:
        results["test2_no_feed"] = {"error": str(e)}
    try:
        from datetime import datetime, timedelta
        r3 = requests.get(
            f"https://data.alpaca.markets/v1beta1/options/snapshots/{sym}",
            headers={"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_API_SECRET},
            params={
                "feed": "indicative", "type": "call", "limit": 5,
                "expiration_date_gte": datetime.now().strftime("%Y-%m-%d"),
                "expiration_date_lte": (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d"),
            },
            timeout=10,
        )
        data3 = r3.json() if r3.status_code == 200 else {}
        results["test3_calls_90d"] = {
            "status": r3.status_code,
            "contracts": len(data3.get("snapshots", {})),
            "sample": list(data3.get("snapshots", {}).items())[:2] if data3.get("snapshots") else [],
            "raw": r3.text[:300] if r3.status_code != 200 else "OK",
        }
    except Exception as e:
        results["test3_calls_90d"] = {"error": str(e)}
    return {"symbol": sym, "results": results}


@app.get("/api/radar/test-alert")
async def test_alert():
    from radar_alerts import send_alert
    from radar_service import RADAR_CACHE
    if not RADAR_CACHE:
        return {"ok": False, "error": "Radar cache empty — wait for first scan"}
    top = sorted(RADAR_CACHE.values(), key=lambda x: x.get("composite_score", 0), reverse=True)[0]
    sent = send_alert(top, "Watching", "Armed")
    return {"ok": sent, "symbol": top.get("symbol"), "recipients": "all registered users"}


@app.get("/api/debug/user-emails")
async def debug_user_emails():
    from radar_alerts import _get_all_user_emails
    emails = _get_all_user_emails()
    return {"count": len(emails), "emails": emails}


@app.get("/api/v1/permissions/{user_id}")
async def user_permissions(user_id: str):
    return get_permissions(user_id)


@app.get("/api/stock/{symbol}")
async def get_stock(symbol: str):
    clean = sanitize_symbol(symbol)
    if not clean:
        raise HTTPException(400, "Invalid symbol")
    cached = get_cached_price(clean)
    try:
        quote = fetch_latest_quote(clean)
        cache_price(clean, quote["price"], quote["volume"])
    except Exception:
        if cached:
            quote = cached
        else:
            raise HTTPException(503, "Price unavailable")
    update = create_live_update(clean, quote["price"], quote["volume"], 0)
    return {**quote, "decision": update.decision.__dict__, "confluence": [c.__dict__ for c in update.confluence]}


@app.get("/api/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "1Min", limit: int = 50):
    clean = sanitize_symbol(symbol)
    if not clean:
        raise HTTPException(400, "Invalid symbol")
    return {"symbol": clean, "bars": fetch_bars(clean, timeframe, limit)}


@app.websocket("/ws/{symbol}")
async def websocket_endpoint(ws: WebSocket, symbol: str):
    clean = sanitize_symbol(symbol)
    if not clean:
        await ws.close(code=1008)
        return
    await manager.connect(ws, clean)
    if ALPACA_API_KEY:
        ensure_stream(clean)
    else:
        asyncio.create_task(_synthetic_feed(ws, clean))
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "PING"})
    except WebSocketDisconnect:
        manager.disconnect(ws, clean)


@app.get("/api/debug/csv-test")
async def csv_test():
    import io as _io
    import pandas as pd
    from csv_import import clean_price, clean_qty, normalize_side, parse_timestamp, reconstruct_trades, analyze_behavior
    sample = """date,time,symbol,action,qty,price
01/01/2025 09:43:00,09:43:00,AAPL,buy,67,160.2
01/01/2025 14:52:00,14:52:00,AAPL,sell,67,158.68
01/03/2025 09:35:00,09:35:00,AAPL,buy,127,154.7
01/03/2025 12:25:00,12:25:00,AAPL,sell,127,160.01
"""
    df = pd.read_csv(_io.StringIO(sample), skip_blank_lines=True)
    col_map = {"symbol":"symbol","action":"side","qty":"qty","price":"price","date":"timestamp"}
    df.columns = [c.lower().strip() for c in df.columns]
    df = df.rename(columns={k.lower(): v for k, v in col_map.items()})
    rows = []
    for _, row in df.iterrows():
        price = clean_price(row.get("price"))
        qty, is_sell = clean_qty(row.get("qty"))
        side = normalize_side(str(row.get("side","")), qty_negative=(is_sell or False))
        symbol = str(row.get("symbol","")).strip().upper()
        ts = parse_timestamp(row.get("timestamp"))
        if symbol and price and qty:
            rows.append({"symbol":symbol,"side":side,"qty":qty,"price":price,"timestamp":ts})
    trades, _ = reconstruct_trades(rows)
    analysis = analyze_behavior(trades)
    return {
        "rows_parsed":    len(rows),
        "sides":          list(set(r["side"] for r in rows)),
        "timestamps":     [str(r["timestamp"]) for r in rows[:2]],
        "trades_closed":  len(trades),
        "analysis_keys":  list(analysis.keys()),
    }


@app.delete("/api/trades/reset")
def reset_trades():
    try:
        import psycopg2
        db_url = os.environ.get("DATABASE_URL", "")
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        for tbl in ["decision_scorecards", "behavioral_events", "regime_memory", "trades"]:
            try:
                cur.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass
        conn.commit()
        cur.close()
        conn.close()
        return {"status": "ok", "message": "Trade history cleared successfully."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


async def _synthetic_feed(ws: WebSocket, symbol: str):
    import random
    price    = 280.15
    sequence = 0
    while True:
        await asyncio.sleep(1.4)
        price    = round(max(1.0, price + (random.random() - 0.45) * 1.25), 2)
        volume   = round(500_000 + random.random() * 5_000_000)
        sequence += 1
        update   = create_live_update(symbol, price, volume, sequence)
        try:
            await ws.send_json(update.to_dict())
        except Exception:
            break


# ── Geometry seeding endpoints ─────────────────────────────────────────────

@app.get("/api/admin/seed-geometry")
async def seed_geometry():
    """Seeds Wyckoff and Gann vectors for Intelligence Layer symbols. Run once."""
    results = {}
    if _WYCKOFF_AVAILABLE:
        try:
            seed_wyckoff()
            results["wyckoff"] = "seeded"
        except Exception as e:
            results["wyckoff"] = f"error: {e}"
    else:
        results["wyckoff"] = "engine not available"

    if _GANN_AVAILABLE:
        try:
            seed_gann_vectors()
            results["gann"] = "seeded"
        except Exception as e:
            results["gann"] = f"error: {e}"
    else:
        results["gann"] = "engine not available"

    return results


@app.get("/api/admin/geometry-status")
async def geometry_status():
    """Returns current geometric structures count from Supabase."""
    try:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            return {"error": "Supabase not configured"}
        import requests as _req
        r = _req.get(
            f"{url}/rest/v1/geometric_structures?select=ticker,structure_type&is_active=eq.true",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=5
        )
        data = r.json()
        wyckoff = [d for d in data if 'Wyckoff' in d.get('structure_type', '')]
        gann    = [d for d in data if 'Gann' in d.get('structure_type', '')]
        bme_status = globals().get("get_memory_status", lambda: {"symbols_trained": 0})() if globals().get("_BME_AVAILABLE", False) else {"symbols_trained": 0}
        return {
            "total_active"   : len(data),
            "wyckoff_anchors": len(wyckoff),
            "gann_vectors"   : len(gann),
            "wyckoff_engine" : _WYCKOFF_AVAILABLE,
            "gann_engine"    : _GANN_AVAILABLE,
            "bme_engine"     : globals().get("_BME_AVAILABLE", False),
            "bme_trained"    : bme_status.get("symbols_trained", 0),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/debug/radar/{symbol}")
async def debug_radar(symbol: str):
    """Returns full radar cache for a symbol including GEX, BME, Weis scores."""
    try:
        from radar_service import RADAR_CACHE, INTELLIGENCE_CACHE
        clean = symbol.upper().strip()
        radar_data = RADAR_CACHE.get(clean, {})
        intel_data = INTELLIGENCE_CACHE.get(clean, {})
        if not radar_data and not intel_data:
            return {"error": f"{clean} not in radar cache yet — radar:{len(RADAR_CACHE)} intel:{len(INTELLIGENCE_CACHE)}"}
        internal = intel_data.get("internal_scores", {})
        factor   = intel_data.get("factor_scores", {})
        return {
            "symbol"              : clean,
            "composite_score"     : radar_data.get("composite_score"),
            "status"              : intel_data.get("status") or radar_data.get("status"),
            "regime"              : intel_data.get("regime") or radar_data.get("regime"),
            "price"               : radar_data.get("price"),
            "change_pct"          : radar_data.get("change_pct"),
            "rel_volume"          : radar_data.get("rel_volume"),
            "trigger"             : radar_data.get("trigger"),
            "invalidation"        : radar_data.get("invalidation"),
            "setup_type"          : radar_data.get("setup_type"),
            "on_divergence_watchlist": radar_data.get("on_divergence_watchlist"),
            "weis_signal"         : radar_data.get("weis_signal"),
            "weis_score"          : radar_data.get("weis_score"),
            "weis_macro_bias"     : radar_data.get("weis_macro_bias"),
            "three_bar_reversal"  : radar_data.get("three_bar_reversal"),
            "three_bar_note"      : radar_data.get("three_bar_note"),
            "intelligence_score"  : intel_data.get("score"),
            "confidence"          : intel_data.get("confidence"),
            "direction"           : intel_data.get("direction"),
            "setup"               : intel_data.get("setup"),
            "wyckoff_phase"       : intel_data.get("wyckoff_phase"),
            "candle_pattern"      : intel_data.get("candle_pattern"),
            "gex_score"           : radar_data.get("gex_score") or internal.get("options_liquidity"),
            "gex_regime"          : radar_data.get("gex_regime"),
            "gex_available"       : radar_data.get("gex_available", False),
            "gex_strategy"        : radar_data.get("gex_strategy"),
            "gex_wall"            : radar_data.get("gex_wall"),
            "gex_sub_score"       : radar_data.get("gex_sub_score"),
            "bme_score"           : radar_data.get("bme_score") or internal.get("behavioral"),
            "weis_score_deep"     : internal.get("wyckoff_weis"),
            "hurst_score"         : internal.get("time_cycle"),
            "vsa_score"           : internal.get("vsa"),
            "gann_score"          : internal.get("gann_geometry"),
            "fibonacci_score"     : internal.get("fibonacci"),
            "elliott_score"       : internal.get("elliott"),
            "confluence_factor"   : factor.get("C"),
            "expansion_factor"    : factor.get("E"),
            "rel_strength_factor" : factor.get("RS"),
            "vol_pressure_factor" : factor.get("VP"),
            "behavioral_factor"   : factor.get("B"),
            "upside_trigger"      : intel_data.get("levels", {}).get("upside_trigger"),
            "downside_trigger"    : intel_data.get("levels", {}).get("downside_trigger"),
            "invalidation_bull"   : intel_data.get("levels", {}).get("invalidation_bull"),
            "invalidation_bear"   : intel_data.get("levels", {}).get("invalidation_bear"),
            "bars_5m_count"       : intel_data.get("bars_5m_count"),
            "bars_1h_count"       : intel_data.get("bars_1h_count"),
            "updated_at"          : intel_data.get("updated_at"),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/behavior/open-trade/{user_id}")
async def get_open_trade(user_id: str):
    """
    Open trade endpoint — returns empty response until
    Alpaca order execution is built in v1.1
    """
    return {
        "user_id"   : user_id,
        "open_trade": None,
        "status"    : "no_open_trade",
        "message"   : "No open trade found",
    }
