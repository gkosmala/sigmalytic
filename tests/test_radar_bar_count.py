import pytest
from backend import radar_settings as rs
from backend import radar_service as svc
from backend import weis_state_preview as wsp


class FakeRedis:
    def __init__(self): self.d = {}
    def get(self, k): return self.d.get(k)
    def set(self, k, v): self.d[k] = v


def test_default_when_unset():
    assert rs.get_bar_count(client=FakeRedis()) == 289


def test_set_and_get_roundtrip():
    c = FakeRedis()
    assert rs.set_bar_count(252, client=c) == 252
    assert rs.get_bar_count(client=c) == 252


@pytest.mark.parametrize("bad", [10, 59, 1001, "abc", None, 252.5])
def test_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        rs.validate(bad)


def test_bad_stored_value_falls_back_to_default():
    c = FakeRedis(); c.d[rs.REDIS_KEY] = "7"
    assert rs.get_bar_count(client=c) == 289


def test_lookback_grows_with_count():
    assert rs.daily_lookback_days(252) == 428
    assert rs.daily_lookback_days(600) == 1020
    assert rs.daily_lookback_days(100) == 420


def _bars(n):
    out = []
    for i in range(n):
        d = f"{2020 + i // 365}-{(i % 365) // 31 + 1:02d}-{(i % 28) + 1:02d}"
        out.append({"t": d + "T05:00:00Z", "o": 10, "h": 11, "l": 9, "c": 10, "v": 1})
    return out


def test_radar_status_reads_only_the_set_count(monkeypatch):
    seen = {}
    monkeypatch.setattr(svc, "_radar_bar_count", lambda: 100)
    monkeypatch.setattr(svc, "drop_incomplete", lambda b, tf: b)
    def fake_eval(done):
        seen["n"] = len(done)
        return {"state": "No setup"}
    monkeypatch.setattr(svc, "evaluate_setup_state", fake_eval)
    svc._weis_cache.clear()
    svc._weis_status(_bars(300), "ZZZ")
    assert seen["n"] == 100


def test_preview_cuts_swing_window_and_widens_lookback():
    calls = []
    def fetch(syms, timeframe, lookback_days):
        calls.append(lookback_days)
        return {s: _bars(400) for s in syms}
    seen = []
    orig = wsp.wss.evaluate_setup_state
    wsp.wss.evaluate_setup_state = lambda eb, **k: seen.append(len(eb)) or {"state": "No setup"}
    try:
        wsp.run_preview({}, ["AAA"], 1, "swing", fetch, bar_count=600)
    finally:
        wsp.wss.evaluate_setup_state = orig
    assert calls == [1020]
    assert seen and seen[0] <= 600
