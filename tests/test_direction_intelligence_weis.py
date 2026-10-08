"""Command Center Direction Intelligence tile = the Weis setup state (not the old score)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _text(node):
    out = []

    def walk(n):
        if n is None:
            return
        if isinstance(n, (list, tuple)):
            for c in n:
                walk(c)
            return
        if isinstance(n, str):
            out.append(n)
            return
        walk(getattr(n, "children", None))

    walk(node)
    return " | ".join(out)


def _panel(ws):
    from frontend import app
    return _text(app.build_direction_panel({"bias": "Neutral", "status": "C PROBE", "grade": "C"},
                                           47, symbol="GXO", price=45.99, regime="discovery",
                                           rel_volume=1.0, weis_state=ws))


def test_armed_long_shows_state_direction_reason_stop_target():
    t = _panel({"state": "Armed", "direction": "long", "reason": "spring closed back inside",
                "stop": 40.1, "target": 52.5, "bar_count": 289, "source": "radar scan"})
    assert "ARMED · LONG" in t and "spring closed back inside" in t
    assert "$40.10" in t and "$52.50" in t and "Long (spring)" in t
    assert "last 289 completed daily bars" in t


def test_avoid_and_no_target():
    t = _panel({"state": "Avoid", "direction": "long", "reason": "against the longer-term trend",
                "stop": 44.0, "target": None, "bar_count": 289, "source": "radar scan"})
    assert "AVOID · LONG" in t and "No target defined" in t


def test_loading_when_state_missing():
    assert "LOADING" in _panel(None)


def test_old_score_tiles_are_gone():
    t = _panel({"state": "Watching", "direction": None, "reason": "", "bar_count": 289})
    for old in ("NEUTRAL", "Engine Score", "Score Tier", "Trap Door", "Confidence", "Status - Grade", "Mode"):
        assert old not in t, old
    assert "WATCHING" in t


def test_symbol_endpoint_uses_scan_row(monkeypatch):
    from backend import radar_service as rs
    monkeypatch.setattr(rs, "_radar_rows_for_states", lambda: [
        {"symbol": "GXO", "status": "Avoid", "status_direction": "long", "status_reason": "r",
         "status_stop": 1.0, "status_target": None}])
    monkeypatch.setattr(rs, "_radar_bar_count", lambda: 289)
    out = rs.get_symbol_weis_state("gxo")
    assert out["ok"] and out["state"] == "Avoid" and out["source"] == "radar scan"


def test_symbol_endpoint_computes_when_not_in_scan(monkeypatch):
    from backend import radar_service as rs
    monkeypatch.setattr(rs, "_radar_rows_for_states", lambda: [])
    monkeypatch.setattr(rs, "_radar_bar_count", lambda: 289)
    monkeypatch.setattr(rs, "fetch_bars_multi", lambda syms, timeframe, lookback_days: {syms[0]: [{"x": 1}]})
    monkeypatch.setattr(rs, "_weis_status", lambda bars, sym="": {
        "state": "Watching", "direction": "long", "reason": "r", "stop": None, "target": None})
    out = rs.get_symbol_weis_state("ZZZ")
    assert out["ok"] and out["state"] == "Watching" and out["source"] == "live daily bars"


def test_symbol_endpoint_reports_no_bars(monkeypatch):
    from backend import radar_service as rs
    monkeypatch.setattr(rs, "_radar_rows_for_states", lambda: [])
    monkeypatch.setattr(rs, "_radar_bar_count", lambda: 289)
    monkeypatch.setattr(rs, "fetch_bars_multi", lambda syms, timeframe, lookback_days: {})
    assert rs.get_symbol_weis_state("ZZZ")["ok"] is False
