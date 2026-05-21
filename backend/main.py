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
  GET  /api/admin/report              — private admin performance report
  GET  /api/admin/report/public       — dev admin report (no auth)
  POST /api/admin/snapshot/write-now  — force snapshot write

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
sys.path.insert(0, str(pathlib.Path(__file__).parent))         # backend/ itself
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))  # project root

# ── Shared engine ──────────────────────────────────────────────────────────
from shared.engine import (
    sanitize_symbol, create_live_update, generate_initial_candles
)

# ── Routers ────────────────────────────────────────────────────────────────
from behavior       import behavior_router
from csv_import     import csv_router
from billing_stub   import billing_router
from radar_service  import radar_router, start_radar_scheduler, stop_radar_scheduler
from snapshot_service import snapshot_router   # ← SNAPSHOT + ADMIN ROUTER

# ── Access Control ─────────────────────────────────────────────────────────
from access_control import get_permissions, check_access

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
    """Tracks all active frontend WebSocket clients per symbol."""

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
    if not ALPACA_API_KEY:
        candles = generate_initial_candles(280.15)
        return [{"o": c.o, "h": c.h, "l": c.l, "c": c.c, "v": 0, "t": ""} for c in candles]

    url = f"{ALPACA_BASE_URL}/v2/stocks/{symbol}/bars"
    params = {
        "timeframe": timeframe,
        "limit":     limit,
        "feed":      "iex",
    }
    try:
        r = requests.get(url, headers=_alpaca_headers(), params=params, timeout=8)
        r.raise_for_status()
        bars = r.json().get("bars", [])
        return [
            {
                "o": float(b["o"]),
                "h": float(b["h"]),
                "l": float(b["l"]),
                "c": float(b["c"]),
                "v": int(b["v"]),
                "t": b["t"],
            }
            for b in bars
        ]
    except Exception as e:
        log.warning(f"Bar fetch failed for {symbol}: {e}")
        candles = generate_initial_candles(280.15)
        return [{"o": c.o, "h": c.h, "l": c.l, "c": c.c, "v": 0, "t": ""} for c in candles]


# ── Alpaca WebSocket stream (per symbol) ──────────────────────────────────

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

# ── Register routers ───────────────────────────────────────────────────────
app.include_router(behavior_router)
app.include_router(csv_router)
app.include_router(billing_router)
app.include_router(radar_router)
app.include_router(snapshot_router)    # ← ADMIN + SNAPSHOT ENDPOINTS


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
    """Simple HTML password reset form — no Dash needed."""
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
    var r = await fetch('/api/auth/reset-password?email=' + encodeURIComponent(email));
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
    """Password reset landing page — shown after user clicks reset email link."""
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
      msg.innerText='✅ Password updated! Redirecting...';
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
    """Update password using recovery token."""
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
    """Test login against Supabase — debug only."""
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
    """Send password reset email via Supabase."""
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


@app.get("/api/sms/test")
async def test_sms():
    """Send a test SMS to verify Twilio is working."""
    from sms_alerts import send_test_sms
    return send_test_sms()


@app.get("/api/scoreboard")
async def get_scoreboard():
    """Public scoreboard — all historical signals with grades."""
    from scoreboard_service import get_scoreboard_stats
    return get_scoreboard_stats()


@app.post("/api/scoreboard/grade-now")
async def grade_now():
    """Manually trigger grading of pending signals."""
    from scoreboard_service import grade_pending_signals
    grade_pending_signals()
    return {"ok": True, "message": "Grading complete"}


@app.get("/api/radar/test-alert")
async def test_alert():
    """Send a test alert email to verify Resend is working."""
    from radar_alerts import send_alert
    from radar_service import RADAR_CACHE
    if not RADAR_CACHE:
        return {"ok": False, "error": "Radar cache empty — wait for first scan"}
    top = sorted(RADAR_CACHE.values(), key=lambda x: x.get("composite_score", 0), reverse=True)[0]
    sent = send_alert(top, "Watching", "Armed")
    return {"ok": sent, "symbol": top.get("symbol"), "recipients": "all registered users"}


@app.get("/api/debug/user-emails")
async def debug_user_emails():
    """Debug — shows which emails would receive alerts."""
    from radar_alerts import _get_all_user_emails
    emails = _get_all_user_emails()
    return {
        "count": len(emails),
        "emails": emails,
    }


@app.get("/api/v1/permissions/{user_id}")
async def user_permissions(user_id: str):
    """Returns the full feature permission map for a user."""
    return get_permissions(user_id)


@app.get("/api/stock/{symbol}")
async def get_stock(symbol: str):
    clean = sanitize_symbol(symbol)
    if not clean:
        raise HTTPException(400, "Invalid symbol")
    quote = fetch_latest_quote(clean)
    update = create_live_update(clean, quote["price"], quote["volume"], 0)
    return {**quote, "decision": update.decision.__dict__, "confluence": [c.__dict__ for c in update.confluence]}


@app.get("/api/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "1Min", limit: int = 50):
    clean = sanitize_symbol(symbol)
    if not clean:
        raise HTTPException(400, "Invalid symbol")
    return {"symbol": clean, "bars": fetch_bars(clean, timeframe, limit)}


# ── WebSocket endpoint ─────────────────────────────────────────────────────

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


@app.delete("/api/trades/reset")
def reset_trades():
    """Lab reset — clears all imported trade history from the database."""
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
