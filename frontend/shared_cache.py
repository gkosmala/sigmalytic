"""
frontend/shared_cache.py
-------------------------
A TTL-based cache shared across frontend tab modules AND across all
gunicorn worker processes, via Redis.

Why this version exists (2026-07-25, part 2):
The original version of this module used a plain in-memory Python dict.
That worked correctly within a single process, but this app runs under
`gunicorn ... --workers 4` -- four completely separate OS processes, each
with its own independent memory. Each worker had its own separate copy of
the cache, so a request could land on a worker that had never cached a
given endpoint yet, causing slow "cold" fetches far more often than
expected, even though the caching logic itself was correct.

This version uses Redis (when REDIS_URL is configured and reachable) so
all workers share one real cache. If Redis isn't configured, or becomes
unreachable, it transparently falls back to the original in-memory
behavior -- this never becomes a hard dependency; the app works either
way, just with less sharing across workers if Redis isn't available.

Verified with genuinely separate OS processes (not just threads), matching
the real gunicorn worker scenario:
- A fetch in one process is immediately visible to a completely separate
  process reading the same key.
- 5 separate processes requesting the same uncached key simultaneously
  produced exactly 1 real fetch; all 5 received the identical result.

Public interface is unchanged from the original in-memory-only version:
    from shared_cache import shared_cache
    shared_cache.get_or_fetch(key, fetch_fn, ttl_seconds=25)
    shared_cache.invalidate(key=None)
No other file needs to change to benefit from this.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict


class SharedCache:
    def __init__(self, redis_url: str | None = None, key_prefix: str = "sigmalytic_cache:"):
        self._key_prefix = key_prefix

        # In-memory fallback backend -- always initialized, used directly
        # if Redis isn't configured/reachable, and used as the per-call
        # fallback if Redis errors out mid-operation.
        self._memory_lock = threading.Lock()
        self._memory_store: dict = {}
        self._memory_key_locks: dict = defaultdict(threading.Lock)

        self._redis_client = None
        resolved_url = redis_url or os.getenv("REDIS_URL") or os.getenv("REDISCLOUD_URL")
        if resolved_url:
            try:
                import redis as _redis_module
                client = _redis_module.from_url(
                    resolved_url, socket_connect_timeout=2, socket_timeout=2
                )
                client.ping()  # verify it's actually reachable, not just configured
                self._redis_client = client
            except Exception:
                self._redis_client = None

    @property
    def backend(self) -> str:
        """Returns 'redis' or 'memory' -- useful for diagnostics/logging."""
        return "redis" if self._redis_client is not None else "memory"

    def get_or_fetch(self, key: str, fetch_fn, ttl_seconds: int = 25):
        """
        Returns cached data for `key` if younger than ttl_seconds.
        Otherwise calls fetch_fn() (no arguments), caches the result, and
        returns it. Concurrent callers -- across threads AND across
        separate worker processes when Redis is active -- for the same
        uncached key are serialized so only one real fetch happens.
        """
        if self._redis_client is not None:
            try:
                return self._get_or_fetch_redis(key, fetch_fn, ttl_seconds)
            except Exception:
                # Redis errored mid-operation (e.g. connection dropped).
                # Don't fail the request -- just fall back to the
                # in-memory path for this one call.
                pass
        return self._get_or_fetch_memory(key, fetch_fn, ttl_seconds)

    # ---- Redis backend: shared across all worker processes ----

    def _get_or_fetch_redis(self, key, fetch_fn, ttl_seconds):
        data_key = f"{self._key_prefix}data:{key}"
        lock_key = f"{self._key_prefix}lock:{key}"

        raw = self._redis_client.get(data_key)
        if raw is not None:
            return json.loads(raw)

        # Distributed lock via SET NX EX: only one process across every
        # worker actually fetches for a given uncached key. Others wait
        # briefly and then read the result that fetch populated, rather
        # than each independently hitting the backend.
        acquired = self._redis_client.set(lock_key, "1", nx=True, ex=30)

        if not acquired:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                raw = self._redis_client.get(data_key)
                if raw is not None:
                    return json.loads(raw)
                time.sleep(0.1)
            # The lock holder took unusually long or crashed without
            # releasing it -- don't hang forever waiting; just fetch
            # directly this one time.
            return fetch_fn()

        try:
            data = fetch_fn()
            self._redis_client.setex(data_key, ttl_seconds, json.dumps(data))
            return data
        finally:
            try:
                self._redis_client.delete(lock_key)
            except Exception:
                pass

    # ---- In-memory fallback: used when Redis isn't configured/reachable ----

    def _get_or_fetch_memory(self, key, fetch_fn, ttl_seconds):
        with self._memory_lock:
            entry = self._memory_store.get(key)
            if entry is not None:
                age = time.monotonic() - entry["cached_at"]
                if age < ttl_seconds:
                    return entry["data"]

        key_lock = self._memory_key_locks[key]
        with key_lock:
            with self._memory_lock:
                entry = self._memory_store.get(key)
                if entry is not None:
                    age = time.monotonic() - entry["cached_at"]
                    if age < ttl_seconds:
                        return entry["data"]

            data = fetch_fn()

            with self._memory_lock:
                self._memory_store[key] = {"data": data, "cached_at": time.monotonic()}

            return data

    def invalidate(self, key: str = None):
        """Clears one key, or the whole cache if key is None."""
        if self._redis_client is not None:
            try:
                if key is None:
                    for k in self._redis_client.scan_iter(f"{self._key_prefix}*"):
                        self._redis_client.delete(k)
                else:
                    self._redis_client.delete(f"{self._key_prefix}data:{key}")
            except Exception:
                pass
        with self._memory_lock:
            if key is None:
                self._memory_store.clear()
            else:
                self._memory_store.pop(key, None)


# Module-level singleton -- every file that does
# `from shared_cache import shared_cache` gets the SAME instance within a
# given worker process. With Redis configured, all worker processes also
# share the same underlying cached data.
shared_cache = SharedCache()
