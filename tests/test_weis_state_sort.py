"""Weis setup states: the Bars ago column is centered and can be sorted ascending or descending."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
import app as dash_app  # noqa: E402

ROWS = [{"symbol": "AAA", "state": "Armed", "bars_since_break": 5}, {"symbol": "BBB", "state": "Setting Up", "bars_since_break": 1},
        {"symbol": "CCC", "state": "Watching", "bars_since_break": None}, {"symbol": "DDD", "state": "Armed", "bars_since_break": 12}]


def _symbols(trs):
    return [tr.children[0].children for tr in trs]


def test_default_order_is_kept():
    assert _symbols(dash_app._weis_state_rows(ROWS, None)) == ["AAA", "BBB", "CCC", "DDD"]


def test_ascending_and_descending_put_missing_values_last():
    assert _symbols(dash_app._weis_state_rows(ROWS, "asc")) == ["BBB", "AAA", "DDD", "CCC"]
    assert _symbols(dash_app._weis_state_rows(ROWS, "desc")) == ["DDD", "AAA", "BBB", "CCC"]


def test_bars_ago_cells_are_centered():
    td = dash_app._weis_state_rows(ROWS, None)[0].children[5]
    assert td.children == "5" and td.style["textAlign"] == "center"


def test_click_toggles_direction():
    rows1, label1 = dash_app.sort_weis_state_by_bars_ago(1, ROWS)
    rows2, label2 = dash_app.sort_weis_state_by_bars_ago(2, ROWS)
    rows3, _ = dash_app.sort_weis_state_by_bars_ago(3, ROWS)
    assert _symbols(rows1)[0] == "BBB" and "▲" in label1
    assert _symbols(rows2)[0] == "DDD" and "▼" in label2
    assert _symbols(rows3)[0] == "BBB"


def test_table_has_centered_header_and_sort_button():
    block = {"available": True, "rows": ROWS, "counts": {}, "bar_count": 252, "scanned": 4}
    html_str = str(dash_app._render_weis_state_table(block))
    assert "weis-state-sort-bars" in html_str and "weis-state-tbody" in html_str and "'textAlign': 'center'" in html_str
