"""Admin card + view for the Weis setup state preview (read-only)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))


def _text(node):
    if node is None:
        return ""
    if isinstance(node, (str, int, float)):
        return str(node)
    if isinstance(node, (list, tuple)):
        return " ".join(_text(n) for n in node)
    return _text(getattr(node, "children", None))


def test_view_renders_rows_and_hides_no_setup():
    sys.path.insert(0, os.path.join(ROOT, "frontend"))
    import weis_state_preview_view as v
    rows = [
        {"symbol": "AAA", "state": "Armed", "direction": "long", "reason": "r", "flipped_from": None,
         "line_source": "axis", "line_touches": 5, "stop": 99.0, "target": 110.2,
         "trends_by_frame": {"1Day": "up", "1Week": "up"}, "angle_change_of_character": [],
         "radar_status_today": "Watching", "break_time": "2026-09-30", "bars_since_break": 4,
         "close_back_time": "2026-09-30"},
        {"symbol": "BBB", "state": "Watching", "direction": "short", "reason": "r", "flipped_from": "spring",
         "line_source": "trendline", "line_touches": 3, "stop": 12.0, "target": None,
         "trends_by_frame": None, "angle_change_of_character": ["bullish: later up-legs below 45 degrees"],
         "radar_status_today": None},
        {"symbol": "CCC", "state": "No setup", "direction": None, "reason": "none", "flipped_from": None,
         "line_source": None, "line_touches": None, "stop": None, "target": None, "trends_by_frame": None,
         "angle_change_of_character": [], "radar_status_today": "Watching"},
    ]
    payload = {"mode": "swing", "summary": {"symbols": 3, "states": {"long/Armed": 1}, "flipped": 1,
                                            "angle_change_of_character": 1}, "rows": rows, "skipped": [],
               "note": "NOT from Weis"}
    out = _text(v.render_weis_state_preview(payload))
    assert "AAA" in out and "BBB" in out and "CCC" not in out
    assert "flipped from spring" in out and "1 flipped setups" in out
    assert "2026-09-30" in out and "Bars ago" in out
    assert "No symbols could be evaluated" in _text(v.render_weis_state_preview({"summary": {"symbols": 0}, "skipped": []}))
    assert "Unexpected response" in _text(v.render_weis_state_preview({"oops": 1}))


def test_card_and_callback_are_wired_in_app_source():
    src = open(os.path.join(ROOT, "frontend", "app.py")).read()
    assert 'id="btn-weis-state-swing"' in src and 'id="btn-weis-state-day"' in src
    assert 'Output("weis-state-output", "children")' in src
    assert "weis_state_block,\n        radar_bars_block,\n        radar_bar_count_block,\n        setup_deployment_block" in src
    assert "/api/admin/weis-state-preview" in src
    assert "from weis_state_preview_view import render_weis_state_preview" in src
