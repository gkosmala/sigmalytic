"""
frontend/shared_cache.py
-------------------------
A small, thread-safe, TTL-based in-memory cache shared across frontend tab
modules (app.py, status_center.py, portfolio_tab.py, trade_journal_tab.py).

Why this exists (2026-07-25):
Several different tabs each independently fetch the same large backend
payloads (most notably /api/campaigns/active, which returns full data for
every active campaign) with no sharing between them. Switching between
Command Center, Status Center, and Portfolio in quick succession re-fetched
and re-parsed the same ~250-campaign payload from scratch every single time,
which was the main contributor to sluggish tab-switching. Campaign data only
genuinely changes once a night (the nightly pipeline), so a short TTL cache
shared across tabs eliminates almost all of that redundant work.

Scope and limitations, stated plainly:
- This is in-memory and per-process. Each gunicorn worker has its own
  independent cache. That's fine for this use case: the goal is avoiding
  redundant fetches within a single user's rapid tab-switching, not
  perfect cross-worker consistency. A cache miss just means a normal
  fresh fetch, same as before this existed -- there is no failure mode
  where stale data persists beyond ttl_seconds.
- Thundering herd protection: if many callers request the same uncached
  key at once, only one real fetch happens; the rest wait for it and
  share the result. Verified with a dedicated concurrency test.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class SharedCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._store: dict = {}
        self._key_locks: dict = defaultdict(threading.Lock)

    def get_or_fetch(self, key: str, fetch_fn, ttl_seconds: int = 25):
        """
        Returns cached data for `key` if it's younger than ttl_seconds.
        Otherwise calls fetch_fn() (no arguments) to get fresh data, caches
        it, and returns it. Concurrent callers for the same uncached key
        are serialized so only one real fetch happens.
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                age = time.monotonic() - entry["cached_at"]
                if age < ttl_seconds:
                    return entry["data"]

        key_lock = self._key_locks[key]
        with key_lock:
            with self._lock:
                entry = self._store.get(key)
                if entry is not None:
                    age = time.monotonic() - entry["cached_at"]
                    if age < ttl_seconds:
                        return entry["data"]

            data = fetch_fn()

            with self._lock:
                self._store[key] = {"data": data, "cached_at": time.monotonic()}

            return data

    def invalidate(self, key: str = None):
        """Clears one key, or the whole cache if key is None."""
        with self._lock:
            if key is None:
                self._store.clear()
            else:
                self._store.pop(key, None)


# Module-level singleton -- every file that does
# `from shared_cache import shared_cache` gets the SAME instance within a
# given worker process, which is what makes the sharing actually work.
shared_cache = SharedCache()
