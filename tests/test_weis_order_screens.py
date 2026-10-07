"""Armed symbols first: radar scores order, Weis state map, Live Opportunity Center column, restored Radar tab."""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))
sys.path.insert(0, os.path.join(ROOT, "frontend"))

from backend import radar_service as rsvc
import live_opportunity_center as loc


def _row(sym, status, score=50.0, rv=1.0, direction=None):
    return {"symbol": sym, "status": status, "composite_score": score, "rel_volume": rv,
            "status_direction": direction, "price": 10.0, "change_pct": 0.0}


def _scores(monkeypatch, rows):
    monkeypatch.setattr(rsvc, "RADAR_CACHE", {r["symbol"]: r for r in rows})
    monkeypatch.setattr(rsvc, "_attach_methodology_verdicts", lambda page: None)
    monkeypatch.setattr(rsvc, "_attach_behavioral_transition_many", lambda page: page, raising=False)
    monkeypatch.setattr(rsvc, "_attach_behavioral_transition", lambda r: r)
    return rsvc.get_radar_scores(limit=50)


def test_scores_list_puts_armed_first_then_weis_state_order(monkeypatch):
    rows = [_row("NO", "No setup", 100, 9), _row("AV", "Avoid", 100, 9), _row("WA", "Watching", 90),
            _row("SU", "Setting Up", 80), _row("AR1", "Armed", 55, 1), _row("AR2", "Armed", 70, 1),
            _row("AR3", "Armed", 70, 3)]
    out = [r["symbol"] for r in _scores(monkeypatch, rows)["symbols"]]
    assert out == ["AR3", "AR2", "AR1", "SU", "WA", "AV", "NO"]


def test_weis_states_endpoint_maps_symbol_to_state_and_direction(monkeypatch):
    monkeypatch.setattr(rsvc, "RADAR_CACHE", {"A": _row("A", "Armed", direction="short"), "B": _row("B", "No setup")})
    out = rsvc.get_weis_states()
    assert out["states"]["A"] == {"state": "Armed", "direction": "short"}
    assert out["states"]["B"]["state"] == "No setup" and out["count"] == 2


def test_live_opportunity_center_puts_armed_first_and_keeps_order_within_a_state():
    rows = [{"symbol": s, "stage": "TRIGGERED"} for s in ("AAA", "BBB", "CCC", "DDD", "EEE")]
    states = {"AAA": {"state": "Watching", "direction": "long"},
              "BBB": {"state": "Armed", "direction": "short"},
              "CCC": {"state": "Setting Up", "direction": "long"},
              "DDD": {"state": "Armed", "direction": "long"}}
    out = loc._attach_weis_states(rows, states)
    assert [r["symbol"] for r in out] == ["BBB", "DDD", "CCC", "AAA", "EEE"]
    assert out[-1]["weis_state"] == "No setup"
    assert loc._weis_label(out[0]) == "Armed · short" and loc._weis_label(out[-1]) == "No setup"


def test_live_opportunity_center_table_shows_the_weis_state_column():
    rows = [{"symbol": "ZZZ", "stage": "ARMED", "direction": "Bullish", "primary_tf": "1Day", "event": "x",
             "detected": None, "signal_count": 1, "weis_state": "Armed", "weis_direction": "long"}]
    text = str(loc._opportunity_table(rows).to_plotly_json())
    assert "Weis state" in text and "Armed · long" in text


def test_radar_screen_is_back_in_the_left_menu_and_wired():
    src = open(os.path.join(ROOT, "frontend", "app.py"), encoding="utf-8").read()
    assert '("radar",       "Radar Screen")' in src
    assert "'tab-status', 'tab-radar'," in src
    assert 'Input("tab-status","n_clicks"),\n    Input("tab-radar","n_clicks"),' in src
    assert 'elif tab=="radar":' in src and "build_radar_tab(session=session)" in src


def test_radio_counts_use_the_weis_state():
    src = open(os.path.join(ROOT, "frontend", "app.py"), encoding="utf-8").read()
    assert "def _radio_state(s):" in src
    assert '"armed" in _radio_state(s).lower()' in src


def test_radar_screen_renders_with_weis_badges_and_counts(monkeypatch):
    import radar_tab
    rows = [{"symbol": "AAA", "status": "Armed", "status_direction": "short", "opportunity_state": "Watching",
             "composite_score": 90, "price": 10, "change_pct": 1.0, "rel_volume": 2.0, "readiness_score": 50},
            {"symbol": "BBB", "status": "Setting Up", "status_direction": "long", "opportunity_state": "Armed",
             "composite_score": 80, "price": 20, "change_pct": -1.0, "rel_volume": 1.0, "readiness_score": 60},
            {"symbol": "CCC", "status": "No setup", "opportunity_state": "Armed",
             "composite_score": 70, "price": 5, "change_pct": 0.0, "rel_volume": 1.0}]

    class R:
        ok = True
        def json(self): return {"symbols": rows, "sort_mode": "x"}
    monkeypatch.setattr("requests.get", lambda *a, **k: R())
    monkeypatch.setattr(radar_tab, "shared_cache", None)
    out = str(radar_tab.build_radar_tab().to_plotly_json())
    assert "AAA" in out and "BBB" in out
    assert "Setting Up" in out and "Armed" in out
