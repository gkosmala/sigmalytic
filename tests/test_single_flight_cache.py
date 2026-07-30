"""
tests/test_single_flight_cache.py
-----------------------------------
Regression coverage for campaign_api.py's _cached_endpoint_result().

WHY THIS EXISTS: this cache originally had a real thundering-herd bug --
the lock only protected the *check* ("is there a fresh cached value"),
not the actual computation, so multiple requests arriving close
together could each independently run the same expensive (~400-500MB)
computation at the same time, directly compounding into the OOM
crashes confirmed via live memory instrumentation on 2026-07-29. Fixed
with a proper per-key single-flight lock held for the entire
check+compute+store. A second, more subtle bug was found afterward:
an empty-but-genuinely-fresh result (e.g. "0 divergences found today")
was being treated as a cache miss and silently overwritten by a stale
fallback -- these tests cover both.
"""
import sys
import os
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.campaign_api import _cached_endpoint_result, _CAMPAIGN_ENDPOINT_CACHE


def _fresh_key(prefix: str) -> str:
    # Avoid cross-test pollution -- each test gets its own cache key.
    return f"{prefix}_{threading.get_ident()}_{time.time()}"


def test_single_call_computes_once():
    key = _fresh_key("single")
    calls = []

    def compute():
        calls.append(1)
        return "result"

    result = _cached_endpoint_result(key, 15, compute)
    assert result == "result"
    assert len(calls) == 1


def test_concurrent_calls_for_the_same_key_collapse_into_one_computation():
    """
    Reproduces the exact production bug: multiple requests for the same
    key arriving at nearly the same instant. Before the fix, each one
    independently ran the expensive computation; after the fix, exactly
    one computation runs and every caller gets its result.
    """
    key = _fresh_key("concurrent")
    call_count = [0]
    lock = threading.Lock()

    def slow_expensive_compute():
        with lock:
            call_count[0] += 1
        time.sleep(0.3)  # simulate a slow, memory-heavy computation
        return "computed"

    results = []
    results_lock = threading.Lock()

    def worker():
        r = _cached_endpoint_result(key, 15, slow_expensive_compute)
        with results_lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert call_count[0] == 1, (
        f"Expected exactly 1 real computation for 8 concurrent callers, "
        f"got {call_count[0]} -- the thundering-herd bug has regressed."
    )
    assert all(r == "computed" for r in results)


def test_cache_hit_within_ttl_does_not_recompute():
    key = _fresh_key("ttl_hit")
    calls = []

    def compute():
        calls.append(1)
        return "v1"

    _cached_endpoint_result(key, 15, compute)
    _cached_endpoint_result(key, 15, compute)
    _cached_endpoint_result(key, 15, compute)
    assert len(calls) == 1


def test_cache_expires_and_recomputes_after_ttl():
    key = _fresh_key("ttl_expire")
    calls = []

    def compute():
        calls.append(1)
        return f"v{len(calls)}"

    first = _cached_endpoint_result(key, 0.2, compute)
    time.sleep(0.3)
    second = _cached_endpoint_result(key, 0.2, compute)

    assert first == "v1"
    assert second == "v2"
    assert len(calls) == 2


def test_genuinely_empty_result_is_still_cached_not_treated_as_a_miss():
    """
    Regression test for the second bug found the same night: a real,
    fresh "0 results" answer must be cached and returned as-is on
    subsequent calls within the TTL -- not treated as empty/absent and
    silently replaced by a stale fallback from elsewhere.
    """
    key = _fresh_key("empty_result")
    calls = []

    def compute():
        calls.append(1)
        return {"symbols": [], "count": 0}

    first = _cached_endpoint_result(key, 15, compute)
    second = _cached_endpoint_result(key, 15, compute)

    assert first == {"symbols": [], "count": 0}
    assert second == {"symbols": [], "count": 0}
    assert len(calls) == 1
