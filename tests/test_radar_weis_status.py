"""Radar Status is the Weis setup state (five words), not the old generic one."""
from backend import radar_service as rs


def _bars(n=80):
    return [{"t": f"d{i}", "o": 100, "h": 100.5, "l": 99.5, "c": 100, "v": 1000} for i in range(n)]


def test_flat_history_is_no_setup():
    w = rs._weis_status(_bars())
    assert w["state"] == "No setup" and w["direction"] is None


def test_bad_bars_never_raise():
    assert rs._weis_status(None)["state"] == "No setup"
    assert rs._weis_status([{"x": 1}])["state"] == "No setup"


def test_status_is_always_one_of_five_words():
    assert rs._weis_status(_bars())["state"] in {"No setup", "Watching", "Setting Up", "Armed", "Avoid"}


def test_alert_label_marks_short_armed_only():
    assert rs._alert_label({"status": "Armed", "status_direction": "short"}) == "Short Armed"
    assert rs._alert_label({"status": "Armed", "status_direction": "long"}) == "Armed"
    assert rs._alert_label({"status": "Setting Up", "status_direction": "short"}) == "Setting Up"
    assert rs._alert_label({"status": "Avoid"}) == "Avoid"


def test_forming_daily_bar_is_ignored_and_state_cached(monkeypatch):
    from datetime import datetime, timezone
    from backend import weis_setup_state as ws
    b = [{"t": f"2026-09-{(i % 28) + 1:02d}T04:00:00Z", "o": 100, "h": 100.5, "l": 99.5, "c": 100, "v": 1} for i in range(60)]
    b[-1]["t"] = "2026-10-07T04:00:00Z"
    open_t = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc)     # 10:00 ET, market open
    assert len(ws.drop_incomplete(b, "1Day", open_t)) == 59
    closed_t = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)   # 17:00 ET, bar finished
    assert len(ws.drop_incomplete(b, "1Day", closed_t)) == 60


def test_intraday_bar_completes_after_its_length():
    from datetime import datetime, timezone
    from backend import weis_setup_state as ws
    h = [{"t": "2026-10-07T13:00:00Z"}, {"t": "2026-10-07T14:00:00Z"}]
    assert len(ws.drop_incomplete(h, "1Hour", datetime(2026, 10, 7, 14, 30, tzinfo=timezone.utc))) == 1
    assert len(ws.drop_incomplete(h, "1Hour", datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc))) == 2


def test_state_is_computed_once_per_completed_bar(monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "evaluate_setup_state", lambda bars: calls.append(1) or {"state": "Watching", "direction": "long"})
    b = [{"t": f"2026-01-{i + 1:02d}T05:00:00Z", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1} for i in range(30)]
    rs._weis_cache.clear()
    rs._weis_status(b, "ZZZ"); rs._weis_status(b, "ZZZ")
    assert len(calls) == 1


def test_corrected_last_bar_recomputes_the_cached_state(monkeypatch):
    calls = []
    monkeypatch.setattr(rs, "evaluate_setup_state", lambda bars: calls.append(bars[-1]["c"]) or {"state": "Watching", "direction": "long"})
    b = [{"t": f"2026-01-{i + 1:02d}T05:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.0, "v": 1} for i in range(30)]
    rs._weis_cache.clear()
    rs._weis_status(b, "ZZZ")
    rs._weis_status(b, "ZZZ")
    assert len(calls) == 1                                   # same bars: reused
    fixed = [dict(x) for x in b]
    fixed[-1]["c"] = 1.5                                     # same date, corrected close
    rs._weis_status(fixed, "ZZZ")
    assert len(calls) == 2 and calls[-1] == 1.5


def test_redis_copy_is_written_and_a_stored_load_is_refreshed(monkeypatch):
    class R:
        def __init__(self): self.sets = []
        def set(self, k, v, ex=None): self.sets.append((k, ex))
    r = R()
    monkeypatch.setattr(rs, "_redis_client", r)
    monkeypatch.setattr(rs, "_historical_bars", {"AAA": [{"t": "2026-01-01", "c": 1}]})
    assert rs._save_bars_to_redis() is True and r.sets == [("historical_bars:v1", 86400)]
    monkeypatch.setattr(rs, "_historical_bars", {})
    assert rs._save_bars_to_redis() is False                 # nothing to save
    assert rs._stored_copy_needs_refresh("redis") and rs._stored_copy_needs_refresh("supabase")
    assert not rs._stored_copy_needs_refresh("alpaca") and not rs._stored_copy_needs_refresh("")
