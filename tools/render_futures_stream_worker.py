"""
tools/render_futures_stream_worker.py
-------------------------------------
Standalone, continuously-running tastytrade DXLink futures stream.

WHY THIS EXISTS: the futures stream used to run inside sigmalytic-backend's
gunicorn worker. That worker is recycled every 75-95 requests
(--max-requests 75, kept for the OOM protection documented in render.yaml),
and every recycle killed the DXLink connection. With the futures dashboard
open (2 requests every 5 seconds) the feed was torn down roughly every 70
seconds and spent much of its life reconnecting and re-collecting quotes,
so the dashboard regularly showed "UNKNOWN", 0 contracts and no prices.

This worker owns the one DXLink connection and publishes snapshots to Redis.
The backend's /api/futures/* endpoints read those snapshots
(backend/futures_feed.py), so backend restarts no longer touch the stream.

Read-only: market data only. No account access, no order execution.

Redis keys (JSON strings):
  futures:status     stream status + published_at         TTL 30s
  futures:quotes     latest quote/trade/summary per symbol TTL 30s
  futures:contracts  discovered contract catalog          TTL 3h
  futures:leader     single-instance lock                 TTL 30s

Env: REDIS_URL, TASTYTRADE_CLIENT_ID, TASTYTRADE_CLIENT_SECRET,
     TASTYTRADE_REFRESH_TOKEN.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import socket
import sys
import time
import uuid
from datetime import datetime, timezone

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _repo_root)

import redis  # noqa: E402

from backend.tastytrade_futures_service import TastytradeFuturesService  # noqa: E402

PUBLISH_INTERVAL_SECONDS = 2
SNAPSHOT_TTL_SECONDS = 30
CONTRACTS_TTL_SECONDS = 3 * 3600
LEADER_TTL_SECONDS = 30
STATUS_KEY = "futures:status"
QUOTES_KEY = "futures:quotes"
CONTRACTS_KEY = "futures:contracts"
LEADER_KEY = "futures:leader"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("futures_worker")

# Release the lock only if this instance still holds it.
_RELEASE_LUA = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
# Renew the lock only if this instance still holds it.
_RENEW_LUA = ("if redis.call('get', KEYS[1]) == ARGV[1] then "
              "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end")


def _redis_client():
    url = os.getenv("REDIS_URL")
    if not url:
        sys.exit("REDIS_URL is not set on this service.")
    return redis.Redis.from_url(url, decode_responses=True, socket_timeout=5, socket_connect_timeout=5)


class FuturesStreamWorker:
    def __init__(self):
        self.redis = _redis_client()
        self.token = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.service: TastytradeFuturesService | None = None
        self.is_leader = False
        self._stop = asyncio.Event()
        self._contracts_published_for = None

    # ---- single-instance lock ------------------------------------------
    def _try_lead(self) -> bool:
        if self.is_leader:
            ok = bool(self.redis.eval(_RENEW_LUA, 1, LEADER_KEY, self.token, LEADER_TTL_SECONDS))
            if not ok:
                log.warning("Lost the futures leader lock")
            return ok
        return bool(self.redis.set(LEADER_KEY, self.token, nx=True, ex=LEADER_TTL_SECONDS))

    # ---- publishing -----------------------------------------------------
    def _publish(self):
        svc = self.service
        snap = svc.stream.snapshot()
        now = time.time()
        status = svc.status()
        status.update(
            source="futures_worker",
            worker=self.token,
            published_epoch=now,
            published_at=datetime.fromtimestamp(now, timezone.utc).isoformat(),
        )
        # Raw quotes keep received_epoch; readers compute staleness themselves.
        quotes = {sym: {k: v for k, v in data.items() if k != "stale"} for sym, data in snap["quotes"].items()}
        pipe = self.redis.pipeline()
        pipe.set(QUOTES_KEY, json.dumps(quotes, separators=(",", ":")), ex=SNAPSHOT_TTL_SECONDS)
        pipe.set(STATUS_KEY, json.dumps(status, separators=(",", ":")), ex=SNAPSHOT_TTL_SECONDS)
        if svc.contracts and svc.last_catalog_refresh != self._contracts_published_for:
            pipe.set(CONTRACTS_KEY, json.dumps(svc.contracts, separators=(",", ":")), ex=CONTRACTS_TTL_SECONDS)
            self._contracts_published_for = svc.last_catalog_refresh
        elif svc.contracts:
            pipe.expire(CONTRACTS_KEY, CONTRACTS_TTL_SECONDS)
        pipe.execute()

    # ---- lifecycle ------------------------------------------------------
    async def _start_stream(self):
        self.service = TastytradeFuturesService()
        await self.service.start()
        self._contracts_published_for = None
        log.warning("Futures stream started (leader %s)", self.token)

    async def _stop_stream(self):
        if self.service is not None:
            await self.service.stop()
            self.service = None
            log.warning("Futures stream stopped")

    async def run(self):
        log.warning("Futures stream worker starting as %s", self.token)
        last_heartbeat = 0.0
        while not self._stop.is_set():
            try:
                leading = await asyncio.to_thread(self._try_lead)
                if leading and not self.is_leader:
                    self.is_leader = True
                    await self._start_stream()
                elif not leading and self.is_leader:
                    self.is_leader = False
                    await self._stop_stream()

                if self.is_leader and self.service is not None:
                    await asyncio.to_thread(self._publish)
                    if time.time() - last_heartbeat > 300:
                        st = self.service.status()
                        log.warning("Futures heartbeat: connected=%s received=%s/%s entitlement=%s",
                                    st["stream_connected"], st["received_symbols"],
                                    st["subscribed_symbols"], st["entitlement_level"])
                        last_heartbeat = time.time()
            except redis.RedisError as exc:
                log.warning("Redis error: %s", type(exc).__name__)
            except Exception as exc:  # keep the worker alive; the stream reconnects itself
                log.warning("Futures worker loop error: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=PUBLISH_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

        await self._stop_stream()
        if self.is_leader:
            try:
                self.redis.eval(_RELEASE_LUA, 1, LEADER_KEY, self.token)
            except redis.RedisError:
                pass
        log.warning("Futures stream worker stopped")

    def request_stop(self):
        self._stop.set()


async def _main():
    worker = FuturesStreamWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:
            pass
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
