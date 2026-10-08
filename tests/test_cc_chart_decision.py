"""Command Center chart: only a real change may rebuild (reload) the iframe."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from frontend import app


def _bars(*dates):
    return [{"date": d} for d in dates]


def _fp(n, last, sym="AAPL", tf="5m", hrs="all"):
    return (sym, tf, hrs, n, last)


def test_first_chart_is_a_rebuild():
    assert app._cc_chart_decision(None, _fp(3, "c"), _bars("a", "b", "c")) == "rebuild"


def test_unchanged_is_reused():
    assert app._cc_chart_decision(_fp(3, "c"), _fp(3, "c"), _bars("a", "b", "c")) == "reuse"


def test_rollover_with_a_growing_series_pushes_the_bar():
    assert app._cc_chart_decision(_fp(3, "c"), _fp(4, "d"), _bars("a", "b", "c", "d")) == "push"


def test_rollover_with_a_full_window_pushes_the_bar():
    """13:55:00 production case: 252 bars before and after, the oldest dropped off."""
    window = _bars(*[f"b{i}" for i in range(250)], "13:50", "13:55")[-252:]
    assert len(window) == 252
    assert app._cc_chart_decision(_fp(252, "13:50"), _fp(252, "13:55"), window) == "push"


def test_empty_tick_keeps_the_chart_on_screen():
    """13:54:05 production case: a tick that returned 0 bars blanked and reloaded the chart."""
    assert app._cc_chart_decision(_fp(252, "13:50"), _fp(0, None), []) == "reuse"


def test_jump_of_more_than_one_bar_rebuilds():
    assert app._cc_chart_decision(_fp(3, "c"), _fp(5, "e"), _bars("a", "b", "c", "d", "e")) == "rebuild"


def test_symbol_timeframe_or_hours_change_rebuilds():
    b = _bars("a", "b", "c", "d")
    assert app._cc_chart_decision(_fp(3, "c"), _fp(4, "d", sym="MSFT"), b) == "rebuild"
    assert app._cc_chart_decision(_fp(3, "c"), _fp(4, "d", tf="1m"), b) == "rebuild"
    assert app._cc_chart_decision(_fp(3, "c"), _fp(4, "d", hrs="rth"), b) == "rebuild"


def test_a_series_that_does_not_continue_the_old_one_rebuilds():
    assert app._cc_chart_decision(_fp(3, "c"), _fp(3, "z"), _bars("a", "b", "z")) == "rebuild"
