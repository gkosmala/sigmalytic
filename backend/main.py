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

Run:
  uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations
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
except Exception as _we:
    _WYCKOFF_AVAILABLE = False

try:
    from gann_engine import (
        seed_gann_vectors,
        run_nightly_gann_recalculation,
    )
    _GANN_AVAILABLE = True
except Exception as _ge:
    _GANN_AVAILABLE = False
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
    sanitize_symbol, create_live_update, generate_initial_candles
)

# ── Routers ────────────────────────────────────────────────────────────────
from behavior         import behavior_router
from csv_import       import csv_router
from billing_stub     import billing_router
from radar_service    import radar_router, start_radar_scheduler, stop_radar_scheduler
from snapshot_service import snapshot_router
from legal_pages      import legal_router
from email_service    import router as email_router
from preferences_router import router as preferences_router

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


def fetch_bars(symbol: str, timeframe: str = "1Min", limit: int = 50) -> list[dict]:
    print(f"BAR_FETCH_CALLED {symbol} {timeframe} key={bool(ALPACA_API_KEY)}", flush=True)
    if not ALPACA_API_KEY:
        candles = generate_initial_candles(280.15)
        return [{"o": c.o, "h": c.h, "l": c.l, "c": c.c, "v": 0, "t": ""} for c in candles]
    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
    params = {"timeframe": timeframe, "limit": limit, "feed": "sip"}
    try:
        r = requests.get(url, headers=_alpaca_headers(), params=params, timeout=8)
        r.raise_for_status()
        raw = r.json()
        if not raw or not isinstance(raw, dict):
            print(f"BAR_FETCH_NULL {symbol} {timeframe}: raw={raw}", flush=True)
            raise ValueError(f"Null/invalid response for {symbol}")
        bars = raw.get("bars", []) or []
        print(f"BAR_FETCH_DEBUG {symbol} {timeframe}: status={r.status_code} bars={len(bars)} raw_keys={list(raw.keys())}", flush=True)
        if not bars:
            print(f"BAR_FETCH_EMPTY {symbol} {timeframe}: {str(raw)[:200]}", flush=True)
        return [
            {"o": float(b["o"]), "h": float(b["h"]), "l": float(b["l"]),
             "c": float(b["c"]), "v": int(b["v"]), "t": b["t"]}
            for b in bars
        ]
    except Exception as e:
        log.warning(f"Bar fetch failed for {symbol}: {e}")
        candles = generate_initial_candles(280.15)
        return [{"o": c.o, "h": c.h, "l": c.l, "c": c.c, "v": 0, "t": ""} for c in candles]


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


# ── App lifecycle ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Sigmalytic backend starting…")
    start_radar_scheduler()

    # ── Nightly geometry recalculation at 20:00 UTC ───────────────────────────
    import threading as _threading
    from datetime import datetime as _dt, timezone as _tz
    import time as _t

    def _nightly_geometry_runner():
        """Runs Wyckoff + Gann recalculation nightly at 20:00 UTC."""
        while True:
            now = _dt.now(_tz.utc)
            # Calculate seconds until next 20:00 UTC
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

    _threading.Thread(target=_nightly_geometry_runner, daemon=True).start()
    log.info("Nightly geometry scheduler started (20:00 UTC)")

    # ── Supabase heartbeat — prevents free tier auto-pause ─────────────────
    import threading, time as _time
    def _supabase_heartbeat():
        import requests as _req
        while True:
            try:
                _req.get(
                    f"{SUPABASE_URL}/rest/v1/user_preferences?limit=1",
                    headers={"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {SUPABASE_ANON_KEY}"},
                    timeout=5
                )
                log.info("Supabase heartbeat OK")
            except Exception as e:
                log.warning(f"Supabase heartbeat failed: {e}")
            _time.sleep(3600)  # ping every hour

    threading.Thread(target=_supabase_heartbeat, daemon=True).start()
    # ── End heartbeat ──────────────────────────────────────────────────────

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
app.include_router(behavior_router)
app.include_router(csv_router)
app.include_router(billing_router)
app.include_router(radar_router)
app.include_router(snapshot_router)
app.include_router(legal_router)
app.include_router(email_router)        # ← EMAIL ALERT ROUTER
app.include_router(preferences_router, prefix="/api/preferences", tags=["preferences"])

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
    from scoreboard_service import clear_duplicate_signals
    deleted = clear_duplicate_signals()
    return {"ok": True, "deleted": deleted}


@app.get("/api/scoreboard")
async def get_scoreboard():
    from scoreboard_service import get_scoreboard_stats
    return get_scoreboard_stats()


@app.post("/api/scoreboard/grade-now")
async def grade_now():
    from scoreboard_service import grade_pending_signals
    grade_pending_signals()
    return {"ok": True, "message": "Grading complete"}


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
    # Try cache first for instant response
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


# ── Geometry seeding endpoints ─────────────────────────────────────────────────

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
        return {
            "total_active"   : len(data),
            "wyckoff_anchors": len(wyckoff),
            "gann_vectors"   : len(gann),
            "wyckoff_engine" : _WYCKOFF_AVAILABLE,
            "gann_engine"    : _GANN_AVAILABLE,
        }
    except Exception as e:
        return {"error": str(e)}