# Copyright (c) 2026 Sigmalytic Quant Corporation.
# Read-only futures feed for the backend's /api/futures/* and /api/indices/spot endpoints.
#
# Prefers the snapshots published to Redis by the standalone
# sigmalytic-futures-stream worker (tools/render_futures_stream_worker.py),
# which keeps one DXLink connection alive regardless of backend restarts.
# Falls back to the in-process tastytrade_futures_service when no fresh
# worker snapshot exists (worker not deployed, stopped, or Redis unreachable).

import json
import logging
import os
import threading
import time
from types import SimpleNamespace

from backend.tastytrade_dxlink import STALE_SECONDS
from backend.tastytrade_futures_service import tastytrade_futures_service

log = logging.getLogger(__name__)

STATUS_KEY = "futures:status"
QUOTES_KEY = "futures:quotes"
CONTRACTS_KEY = "futures:contracts"
CACHE_SECONDS = 1.0
FRESH_SECONDS = 20


class FuturesFeed:
    """Same read interface the endpoints used on tastytrade_futures_service:
    status(), quotes(), .contracts and .stream.entitlement_level."""

    def __init__(self):
        self._lock = threading.Lock()
        self._redis = None
        self._redis_failed_at = 0.0
        self._cache_at = 0.0
        self._status = None
        self._quotes = None
        self._contracts = []

    # ---- Redis snapshot -------------------------------------------------
    def _client(self):
        if self._redis is not None:
            return self._redis
        url = os.getenv("REDIS_URL")
        if not url or time.monotonic() - self._redis_failed_at < 30:
            return None
        try:
            import redis
            self._redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)
        except Exception as exc:
            log.warning("Futures feed Redis setup failed: %s", type(exc).__name__)
            self._redis_failed_at = time.monotonic()
        return self._redis

    def _refresh(self):
        with self._lock:
            if time.monotonic() - self._cache_at < CACHE_SECONDS:
                return
            self._cache_at = time.monotonic()
            client = self._client()
            if client is None:
                self._status = self._quotes = None
                return
            try:
                status_raw, quotes_raw, contracts_raw = client.mget(STATUS_KEY, QUOTES_KEY, CONTRACTS_KEY)
                status = json.loads(status_raw) if status_raw else None
                if status and time.time() - float(status.get("published_epoch", 0)) <= FRESH_SECONDS:
                    self._status = status
                    self._quotes = json.loads(quotes_raw) if quotes_raw else {}
                    if contracts_raw:
                        self._contracts = json.loads(contracts_raw)
                else:
                    self._status = self._quotes = None
            except Exception as exc:
                log.warning("Futures feed Redis read failed: %s", type(exc).__name__)
                self._redis = None
                self._redis_failed_at = time.monotonic()
                self._status = self._quotes = None

    def _worker_live(self):
        self._refresh()
        return self._status is not None

    # ---- public interface -----------------------------------------------
    def status(self):
        if self._worker_live():
            return dict(self._status)
        status = tastytrade_futures_service.status()
        status["source"] = "backend_in_process"
        return status

    def quotes(self):
        if self._worker_live():
            now = time.time()
            return {
                sym: {**data, "stale": now - float(data.get("received_epoch", 0)) > STALE_SECONDS}
                for sym, data in self._quotes.items()
            }
        return tastytrade_futures_service.quotes()

    @property
    def contracts(self):
        if self._worker_live():
            return self._contracts
        return tastytrade_futures_service.contracts

    @property
    def stream(self):
        if self._worker_live():
            return SimpleNamespace(entitlement_level=self._status.get("entitlement_level"))
        return tastytrade_futures_service.stream


futures_feed = FuturesFeed()
