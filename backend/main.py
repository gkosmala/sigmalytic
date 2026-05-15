"""
Sigmalytic Backend — FastAPI + Alpaca Real-Time
------------------------------------------------
Endpoints:
  GET  /api/health              — health check
  GET  /api/stock/{symbol}      — latest quote (REST fallback)
  GET  /api/candles/{symbol}    — historical bars
  WS   /ws/{symbol}             — real-time price stream

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
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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

# ── Behavioral Intelligence Router ─────────────────────────────────────────
from behavior   import behavior_router
from csv_import import csv_router

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
    yield
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

app.include_router(behavior_router)
app.include_router(csv_router)


# ── REST endpoints ─────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status":     "ok",
        "timestamp":  time.time(),
        "alpaca_key": bool(ALPACA_API_KEY),
        "streams":    list(_active_streams.keys()),
    }


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
