"""Weis setup states: the Bars ago column is centered and can be sorted ascending or descending."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
import app as dash_app  # noqa: E402

ROWS = [{"symbol": "AAA", "state": "Armed", "bars_since_break": 5}, {"symbol": "BBB", "state": "Setting Up", "bars_since_break": 1},
        {"symbol": "CCC", "state": "Watching", "bars_since_break": None}, {"symbol": "DDD", "state": "Armed", "bars_since_break": 12}]


def _symbols(trs):
    return [tr.children[0].children for tr in trs]


def test_default_order_is_state_priority_on_sample():
    assert _symbols(dash_app._weis_state_rows(ROWS, None)) == ["AAA", "DDD", "BBB", "CCC"]


def test_sort_stays_inside_each_state_and_missing_last():
    assert _symbols(dash_app._weis_state_rows(ROWS, "asc")) == ["AAA", "DDD", "BBB", "CCC"]
    assert _symbols(dash_app._weis_state_rows(ROWS, "desc")) == ["DDD", "AAA", "BBB", "CCC"]


def test_bars_ago_cells_are_centered():
    td = dash_app._weis_state_rows(ROWS, None)[0].children[5]
    assert td.children == "5" and td.style["textAlign"] == "center"


def test_click_toggles_direction():
    rows1, label1 = dash_app.sort_weis_state_by_bars_ago(1, ROWS)
    rows2, label2 = dash_app.sort_weis_state_by_bars_ago(2, ROWS)
    rows3, _ = dash_app.sort_weis_state_by_bars_ago(3, ROWS)
    assert _symbols(rows1)[0] == "AAA" and "▲" in label1
    assert _symbols(rows2)[0] == "DDD" and "▼" in label2
    assert _symbols(rows3)[0] == "AAA"


def test_table_has_centered_header_and_sort_button():
    block = {"available": True, "rows": ROWS, "counts": {}, "bar_count": 252, "scanned": 4}
    html_str = str(dash_app._render_weis_state_table(block))
    assert "weis-state-sort-bars" in html_str and "weis-state-tbody" in html_str and "'textAlign': 'center'" in html_str


def test_default_order_is_state_priority():
    rows = [{"symbol": s, "state": st, "bars_since_break": i}
            for i, (s, st) in enumerate([("A", "Avoid"), ("B", "Watching"), ("C", "Armed"),
                                         ("D", "Setting Up"), ("E", "Armed"), ("F", "Avoid")])]
    out = [r.children[0].children for r in dash_app._weis_state_rows(rows, None)]
    assert out == ["C", "E", "D", "B", "A", "F"]


def test_sort_keeps_armed_first_and_avoid_last():
    rows = [{"symbol": "V", "state": "Avoid", "bars_since_break": 0}, {"symbol": "W", "state": "Watching", "bars_since_break": 9},
            {"symbol": "X", "state": "Armed", "bars_since_break": 20}, {"symbol": "Y", "state": "Armed", "bars_since_break": 2},
            {"symbol": "Z", "state": "Armed", "bars_since_break": None}]
    assert _symbols(dash_app._weis_state_rows(rows, "asc")) == ["Y", "X", "Z", "W", "V"]
    assert _symbols(dash_app._weis_state_rows(rows, "desc")) == ["X", "Y", "Z", "W", "V"]
