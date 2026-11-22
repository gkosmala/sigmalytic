
# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Tastytrade DXLink futures market data — read-only.

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timezone

import websockets

from backend.tastytrade_futures import get_dxlink_credentials

log = logging.getLogger(__name__)

CHANNEL = 3
KEEPALIVE_SECONDS = 30
STALE_SECONDS = 120
BATCH_SIZE = 250

EVENT_FIELDS = {
    "Quote": [
        "eventType", "eventSymbol",
        "bidPrice", "askPrice", "bidSize", "askSize",
    ],
    "Trade": [
        "eventType", "eventSymbol",
        "price", "dayVolume", "size",
    ],
    "Summary": [
        "eventType", "eventSymbol",
        "openInterest", "dayOpenPrice",
        "dayHighPrice", "dayLowPrice",
        "prevDayClosePrice",
    ],
}


class DXLinkFutures:
    def __init__(self):
        self.symbols = set()
        self.quotes = {}
        self.connected = False
        self.authorized = False
        self.entitlement_level = None
        self.last_error = None
        self._stop = False
        self._socket = None

    def set_symbols(self, contracts):
        self.symbols = {
            item["streamer_symbol"]
            for item in contracts
            if item.get("streamer_symbol")
        }

    def snapshot(self):
        now = time.time()
        return {
            "connected": self.connected,
            "authorized": self.authorized,
            "entitlement_level": self.entitlement_level,
            "subscribed_symbols": len(self.symbols),
            "received_symbols": len(self.quotes),
            "last_error": self.last_error,
            "quotes": {
                symbol: {
                    **data,
                    "stale": now - data["received_epoch"]
                    > STALE_SECONDS,
                }
                for symbol, data in self.quotes.items()
            },
        }

    async def _send(self, message):
        await self._socket.send(json.dumps(message))

    async def _wait_for(self, expected, timeout=20):
        deadline = time.monotonic() + timeout

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"DXLink handshake timed out: {expected}"
                )

            raw = await asyncio.wait_for(
                self._socket.recv(), timeout=remaining
            )
            message = json.loads(raw)
            kind = message.get("type")

            if kind == "ERROR":
                raise RuntimeError(
                    "DXLink returned a protocol error"
                )

            if kind == "AUTH_STATE":
                state = message.get("state")
                if state == "AUTHORIZED":
                    self.authorized = True
                elif state == "UNAUTHORIZED":
                    self.authorized = False

            if kind == expected:
                return message

    async def _handshake(self, token):
        await self._send({
            "type": "SETUP",
            "channel": 0,
            "version": "0.1-DXF-JS/0.3.0",
            "keepaliveTimeout": 60,
            "acceptKeepaliveTimeout": 60,
        })

        await self._wait_for("SETUP")
        state = await self._wait_for("AUTH_STATE")

        if state.get("state") != "UNAUTHORIZED":
            raise RuntimeError("Unexpected DXLink auth state")

        await self._send({
            "type": "AUTH",
            "channel": 0,
            "token": token,
        })

        state = await self._wait_for("AUTH_STATE")
        if state.get("state") != "AUTHORIZED":
            raise RuntimeError("DXLink authorization failed")

        await self._send({
            "type": "CHANNEL_REQUEST",
            "channel": CHANNEL,
            "service": "FEED",
            "parameters": {"contract": "AUTO"},
        })

        await self._wait_for("CHANNEL_OPENED")

        await self._send({
            "type": "FEED_SETUP",
            "channel": CHANNEL,
            "acceptAggregationPeriod": 0.1,
            "acceptDataFormat": "COMPACT",
            "acceptEventFields": EVENT_FIELDS,
        })

        await self._wait_for("FEED_CONFIG")

    async def _subscribe(self):
        symbols = sorted(self.symbols)

        for offset in range(0, len(symbols), BATCH_SIZE):
            batch = symbols[offset:offset + BATCH_SIZE]
            additions = [
                {"type": event_type, "symbol": symbol}
                for symbol in batch
                for event_type in EVENT_FIELDS
            ]

            await self._send({
                "type": "FEED_SUBSCRIPTION",
                "channel": CHANNEL,
                "reset": offset == 0,
                "add": additions,
            })

            await asyncio.sleep(0.1)

    def _handle_feed(self, message):
        data = message.get("data", [])
        if not isinstance(data, list):
            return

        index = 0
        while index + 1 < len(data):
            event_type = data[index]
            rows = data[index + 1]
            index += 2

            fields = EVENT_FIELDS.get(event_type)
            if not fields or not isinstance(rows, list):
                continue

            for row in rows:
                if not isinstance(row, list):
                    continue

                event = dict(zip(fields, row))
                symbol = event.get("eventSymbol")
                if not symbol or symbol not in self.symbols:
                    continue

                now = time.time()
                quote = self.quotes.setdefault(symbol, {})
                quote[event_type.lower()] = event
                quote["received_epoch"] = now
                quote["received_at"] = datetime.fromtimestamp(
                    now, timezone.utc
                ).isoformat()

    async def _keepalive(self):
        while not self._stop:
            await asyncio.sleep(KEEPALIVE_SECONDS)
            await self._send({
                "type": "KEEPALIVE",
                "channel": 0,
            })

    async def run(self):
        delay = 2

        while not self._stop:
            self.connected = False
            self.authorized = False

            try:
                credentials = await asyncio.to_thread(
                    get_dxlink_credentials
                )
                self.entitlement_level = credentials["level"]

                async with websockets.connect(
                    credentials["url"],
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=8 * 1024 * 1024,
                ) as socket:
                    self._socket = socket
                    await self._handshake(credentials["token"])
                    self.connected = True
                    self.last_error = None
                    delay = 2

                    await self._subscribe()

                    keepalive = asyncio.create_task(
                        self._keepalive()
                    )

                    try:
                        async for raw in socket:
                            message = json.loads(raw)
                            kind = message.get("type")

                            if kind == "FEED_DATA":
                                self._handle_feed(message)
                            elif kind == "AUTH_STATE":
                                self.authorized = (
                                    message.get("state")
                                    == "AUTHORIZED"
                                )
                                if not self.authorized:
                                    raise RuntimeError(
                                        "DXLink authorization lost"
                                    )
                            elif kind == "ERROR":
                                raise RuntimeError(
                                    "DXLink protocol error"
                                )
                    finally:
                        keepalive.cancel()
                        await asyncio.gather(
                            keepalive,
                            return_exceptions=True,
                        )

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = type(exc).__name__
                log.warning(
                    "DXLink futures disconnected: %s",
                    type(exc).__name__,
                )
            finally:
                self.connected = False
                self.authorized = False
                self._socket = None

            if not self._stop:
                await asyncio.sleep(
                    delay + random.uniform(0, 1)
                )
                delay = min(delay * 2, 60)

    async def stop(self):
        self._stop = True
        if self._socket is not None:
            await self._socket.close()


dxlink_futures = DXLinkFutures()
