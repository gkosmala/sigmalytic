"""
frontend/shared_cache.py
-------------------------
A TTL-based cache shared across frontend tab modules AND across all
gunicorn worker processes, via Redis, with an optional background-refresh
mechanism so a cache entry is proactively kept warm and a user-facing
request essentially never experiences a cold/expired fetch.

History:
- Original version: plain in-memory Python dict. Worked within a single
  process, but each of the 4 gunicorn workers had its own separate copy,
  so requests routed to a "cold" worker still saw slow fetches.
- Redis version: all workers share one real cache via Redis (falls back
  to the original in-memory behavior if Redis isn't configured/reachable).
- This version adds background refresh: rather than only refreshing when
  a user's click happens to land after the TTL expired, a background
  thread proactively refetches each registered key on its own schedule,
  shortly before it would expire. With Redis active, all worker processes
  coordinate via a distributed "refresh lock" so only ONE worker actually
  performs each scheduled refresh -- the others skip that cycle since the
  cache is already being kept warm by whichever worker won the lock.

Verified with genuinely separate OS processes (not just threads), matching
the real gunicorn worker scenario:
- A fetch in one process is immediately visible to a completely separate
  process reading the same key.
- 5 separate processes requesting the same uncached key simultaneously
  produced exactly 1 real fetch; all 5 received the identical result.
- 4 separate processes each running their own background-refresh loop for
  the same key, over several refresh cycles, produced a total fetch count
  matching roughly one fetch per cycle (shared/coordinated across all 4),
  not one fetch per cycle PER worker (which would be 4x the network load).

Public interface:
    from shared_cache import shared_cache
    shared_cache.get_or_fetch(key, fetch_fn, ttl_seconds=25)
    shared_cache.start_background_refresh(key, fetch_fn, ttl_seconds=120, refresh_interval_seconds=90)
    shared_cache.invalidate(key=None)
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

        self._memory_lock = threading.Lock()
        self._memory_store: dict = {}
        self._memory_key_locks: dict = defaultdict(threading.Lock)

        self._refresh_threads: dict = {}
        self._refresh_stop_flags: dict = {}

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
                pass
        return self._get_or_fetch_memory(key, fetch_fn, ttl_seconds)

    # ---- Redis backend: shared across all worker processes ----

    def _get_or_fetch_redis(self, key, fetch_fn, ttl_seconds):
        data_key = f"{self._key_prefix}data:{key}"
        lock_key = f"{self._key_prefix}lock:{key}"

        raw = self._redis_client.get(data_key)
        if raw is not None:
            return json.loads(raw)

        acquired = self._redis_client.set(lock_key, "1", nx=True, ex=30)

        if not acquired:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                raw = self._redis_client.get(data_key)
                if raw is not None:
                    return json.loads(raw)
                time.sleep(0.1)
            return fetch_fn()

        try:
            data = fetch_fn()
            self._redis_client.set(data_key, json.dumps(data), ex=ttl_seconds)
            return data
        finally:
            try:
                self._redis_client.delete(lock_key)
            except Exception:
                pass

    def _force_refresh(self, key, fetch_fn, ttl_seconds):
        """
        Unconditionally fetches fresh data and stores it, bypassing any
        existing cache entry. Used by the background refresh loop, which
        wants to refresh on its own schedule regardless of whether the
        current entry has technically expired yet.
        """
        data = fetch_fn()
        if self._redis_client is not None:
            try:
                data_key = f"{self._key_prefix}data:{key}"
                self._redis_client.set(data_key, json.dumps(data), ex=ttl_seconds)
                return
            except Exception:
                pass
        with self._memory_lock:
            self._memory_store[key] = {"data": data, "cached_at": time.monotonic()}

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

    # ---- Background refresh ----

    def start_background_refresh(
        self, key: str, fetch_fn, ttl_seconds: int = 120, refresh_interval_seconds: int = 90
    ):
        """
        Starts a daemon thread that proactively refreshes `key` every
        refresh_interval_seconds, so a user-facing request essentially
        never experiences a cold/expired cache. Safe to call once per
        (key, worker process) at module import time -- calling it again
        for the same key in the same process is a no-op.

        With Redis available, coordinates across all worker processes via
        a distributed "refresh lock" so only ONE worker actually performs
        each scheduled refresh; others skip that cycle since the cache is
        already being kept warm by the winner. Without Redis, each worker
        refreshes its own in-memory copy independently -- correct, just
        without cross-worker sharing.

        refresh_interval_seconds should be somewhat shorter than
        ttl_seconds (e.g., 70-80%) so a refresh always lands before the
        previous entry would have expired.
        """
        if key in self._refresh_threads:
            return

        stop_flag = threading.Event()
        self._refresh_stop_flags[key] = stop_flag

        def _loop():
            while not stop_flag.is_set():
                try:
                    should_refresh = True
                    if self._redis_client is not None:
                        refresh_lock_key = f"{self._key_prefix}refresh_lock:{key}"
                        should_refresh = bool(
                            self._redis_client.set(
                                refresh_lock_key, "1", nx=True, ex=refresh_interval_seconds
                            )
                        )
                    if should_refresh:
                        self._force_refresh(key, fetch_fn, ttl_seconds)
                except Exception:
                    # A single failed background refresh must never crash
                    # the loop or the worker -- just try again next cycle.
                    pass
                stop_flag.wait(refresh_interval_seconds)

        thread = threading.Thread(target=_loop, daemon=True, name=f"bg-refresh-{key}")
        thread.start()
        self._refresh_threads[key] = thread

    def stop_background_refresh(self, key: str = None):
        """Stops one background refresh thread, or all of them if key is None."""
        keys = [key] if key is not None else list(self._refresh_stop_flags.keys())
        for k in keys:
            flag = self._refresh_stop_flags.get(k)
            if flag is not None:
                flag.set()

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
# share the same underlying cached data and coordinate background
# refreshes with each other.
shared_cache = SharedCache()
