from backend import radar_service as svc


def _set(monkeypatch, bars, loading, source, tried=0.0):
    monkeypatch.setattr(svc, "_historical_bars", bars)
    monkeypatch.setattr(svc, "_bars_loading", loading)
    monkeypatch.setattr(svc, "_bars_source", source)
    monkeypatch.setattr(svc, "_stored_refresh_tried_at", tried)


def test_due_when_loaded_from_redis_by_startup_thread(monkeypatch):
    _set(monkeypatch, {"A": [1]}, False, "redis")
    assert svc._stored_copy_due_for_refresh(now=1000.0)


def test_not_due_after_alpaca_load(monkeypatch):
    _set(monkeypatch, {"A": [1]}, False, "alpaca")
    assert not svc._stored_copy_due_for_refresh(now=1000.0)


def test_not_due_while_loading_or_empty(monkeypatch):
    _set(monkeypatch, {"A": [1]}, True, "redis")
    assert not svc._stored_copy_due_for_refresh(now=1000.0)
    _set(monkeypatch, {}, False, "redis")
    assert not svc._stored_copy_due_for_refresh(now=1000.0)


def test_retries_only_after_ten_minutes(monkeypatch):
    _set(monkeypatch, {"A": [1]}, False, "supabase", tried=1000.0)
    assert not svc._stored_copy_due_for_refresh(now=1300.0)
    assert svc._stored_copy_due_for_refresh(now=1700.0)
