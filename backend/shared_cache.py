# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/shared_cache.py
------------------------
A TTL-based cache shared across ALL gunicorn worker processes, via
Redis, ported directly from the already-proven, already-tested
frontend/shared_cache.py (see that file's own docstring for the full
history and verification notes -- confirmed with genuinely separate
OS processes that a fetch in one process is immediately visible to a
separate process reading the same key, and that N processes racing on
the same uncached key produce exactly 1 real fetch, not N).

WHY THIS EXISTS: confirmed real, root cause of a production OOM crash
on 2026-08-06 -- campaign_api.py's _cached_endpoint_result() used a
plain, module-level Python dict + threading.Lock, which only works
within a single process. With gunicorn workers > 1, each worker had
its own independent copy, so two workers could each independently run
the same ~400-1000MB active_campaigns/rankings/status computation at
the same time, completely defeating the intended protection. Reusing
this proven, Redis-backed pattern (rather than reinventing it) means
campaign_api.py's cache can become genuinely safe across multiple
workers, which is the actual, correct fix for the "one slow request
blocks the entire single-worker backend" problem -- not simply
reverting to 1 worker forever.

Deliberately a smaller port than the frontend's version: only the
core get_or_fetch() distributed-cache-with-lock pattern is included,
not the background-refresh machinery, since campaign_api.py's current
design doesn't have (or need, at this TTL) that infrastructure.

Reuses the backend's own, already-configured Redis connection
(backend.radar_service._redis_client) rather than creating a second,
separate connection to the same Redis instance.

Public interface:
    from backend.shared_cache import shared_cache
    shared_cache.get_or_fetch(key, fetch_fn, ttl_seconds=15)
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict


class SharedCache:
    def __init__(self, key_prefix: str = "sigmalytic_backend_cache:"):
        self._key_prefix = key_prefix

        self._memory_lock = threading.Lock()
        self._memory_store: dict = {}
        self._memory_key_locks: dict = defaultdict(threading.Lock)

    def _redis(self):
        """
        Resolved lazily on every call (not cached at import time) so
        this always reflects radar_service's current, live connection
        state rather than a stale snapshot from whenever this module
        first loaded.
        """
        try:
            from backend.radar_service import _redis_client
            return _redis_client
        except Exception:
            return None

    @property
    def backend(self) -> str:
        """Returns 'redis' or 'memory' -- useful for diagnostics/logging."""
        return "redis" if self._redis() is not None else "memory"

    def get_or_fetch(self, key: str, fetch_fn, ttl_seconds: int = 15,
                      lock_ttl_seconds: int = 30, lock_wait_seconds: int = 10):
        """
        Returns cached data for `key` if younger than ttl_seconds.
        Otherwise calls fetch_fn() (no arguments), caches the result,
        and returns it. Concurrent callers -- across threads AND
        across separate gunicorn worker processes when Redis is
        active -- for the same uncached key are serialized so only
        one real fetch happens.

        FIX (2026-08-20): confirmed a real, genuine bug -- lock_ttl_seconds
        and lock_wait_seconds previously hardcoded to 30/10, regardless
        of how long fetch_fn() itself could legitimately take. For any
        computation slower than lock_wait_seconds (confirmed true of
        campaign_full_enrichment_api.py's full_universe_enriched_campaign_table,
        which genuinely fetches 100 symbols x 7 years of history and can
        take well over 10 seconds), a second caller arriving while the
        first is still computing would give up waiting after only 10
        seconds and run the SAME expensive computation itself too --
        directly defeating this cache's own stated guarantee ("N
        processes racing produce exactly 1 real fetch, not N"), and a
        very plausible real cause of report generation crashing the
        whole backend: two or more full 100-symbol/7-year computations
        running concurrently, multiplying the same heavy memory load.

        Now configurable per-call, defaulting to the exact same 30/10
        values as before so every EXISTING caller's behavior is
        completely unchanged -- only a caller that knows its own
        fetch_fn() is genuinely slow needs to pass larger values.
        """
        redis_client = self._redis()
        if redis_client is not None:
            try:
                return self._get_or_fetch_redis(redis_client, key, fetch_fn, ttl_seconds,
                                                  lock_ttl_seconds, lock_wait_seconds)
            except Exception:
                pass
        return self._get_or_fetch_memory(key, fetch_fn, ttl_seconds)

    # ---- Redis backend: shared across all worker processes ----

    def _get_or_fetch_redis(self, redis_client, key, fetch_fn, ttl_seconds,
                             lock_ttl_seconds=30, lock_wait_seconds=10):
        data_key = f"{self._key_prefix}data:{key}"
        lock_key = f"{self._key_prefix}lock:{key}"

        raw = redis_client.get(data_key)
        if raw is not None:
            return json.loads(raw)

        acquired = redis_client.set(lock_key, "1", nx=True, ex=lock_ttl_seconds)

        if not acquired:
            deadline = time.monotonic() + lock_wait_seconds
            while time.monotonic() < deadline:
                raw = redis_client.get(data_key)
                if raw is not None:
                    return json.loads(raw)
                time.sleep(0.1)
            return fetch_fn()

        try:
            data = fetch_fn()
            redis_client.set(data_key, json.dumps(data), ex=ttl_seconds)
            return data
        finally:
            try:
                redis_client.delete(lock_key)
            except Exception:
                pass

    # ---- In-memory fallback: single-process only, used if Redis is
    # unavailable ----

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


shared_cache = SharedCache()
