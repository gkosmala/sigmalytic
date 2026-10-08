"""Renko-Weis / PnF-Weis panels: a failed refresh must not replace the last good data."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app, shared_cache as sc


def _wait():
    for _ in range(200):
        if not app._cc_bg_fetch_in_progress:
            return
        time.sleep(0.01)
    raise AssertionError("background fetch did not finish")


def _fresh(monkeypatch):
    monkeypatch.setattr(app, "shared_cache", sc.SharedCache(redis_url=None) if hasattr(sc, "SharedCache") else None)


def _ttl0(key, fetch, good=None):
    out = app._cc_cached_background_fetch(key, fetch, ttl_seconds=0, is_good=good)
    _wait()
    return out


GOOD = {"status": "OK", "weis_score": 70}
BAD = {"status": "BACKEND_ERROR", "error": "Backend returned 502"}


def test_failed_refresh_keeps_last_good(monkeypatch):
    _fresh(monkeypatch)
    _ttl0("k1", lambda: GOOD, app._weis_engine_ok)
    _ttl0("k1", lambda: BAD, app._weis_engine_ok)
    assert _ttl0("k1", lambda: BAD, app._weis_engine_ok) == GOOD


def test_good_refresh_replaces_old_good(monkeypatch):
    _fresh(monkeypatch)
    _ttl0("k2", lambda: GOOD, app._weis_engine_ok)
    new = {"status": "OK", "weis_score": 80}
    _ttl0("k2", lambda: new, app._weis_engine_ok)
    assert _ttl0("k2", lambda: new, app._weis_engine_ok) == new


def test_error_is_stored_when_there_was_never_good_data(monkeypatch):
    _fresh(monkeypatch)
    _ttl0("k3", lambda: BAD, app._weis_engine_ok)
    assert _ttl0("k3", lambda: BAD, app._weis_engine_ok) == BAD


def test_insufficient_history_counts_as_a_real_answer():
    assert app._weis_engine_ok({"status": "INSUFFICIENT_HISTORY"})
    assert not app._weis_engine_ok({"ok": False, "error": "x"})
    assert not app._weis_engine_ok({})


def test_without_is_good_behaviour_is_unchanged(monkeypatch):
    _fresh(monkeypatch)
    _ttl0("k4", lambda: GOOD)
    _ttl0("k4", lambda: BAD)
    assert _ttl0("k4", lambda: BAD) == BAD


def test_loading_text_is_not_data_not_available():
    src = open(os.path.join(os.path.dirname(__file__), "..", "frontend", "app.py"), encoding="utf-8").read()
    assert 'renko_weis_status == "LOADING_IN_BACKGROUND"' in src
    assert 'pnf_weis_status == "LOADING_IN_BACKGROUND"' in src
