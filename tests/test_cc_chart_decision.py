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


def test_same_instant_in_both_date_spellings_is_one_date():
    assert (app._cc_norm_bar_date("2026-10-08T15:45:00Z")
            == app._cc_norm_bar_date("2026-10-08T15:45:00+00:00"))
    assert (app._cc_norm_bar_date("2026-10-08T04:00:00Z")
            == app._cc_norm_bar_date("2026-10-08T00:00:00-04:00"))


def test_unparseable_date_is_left_alone():
    assert app._cc_norm_bar_date("not a date") == "not a date"
    assert app._cc_norm_bar_date(None) is None


def test_date_spelling_flip_does_not_rebuild():
    n = app._cc_norm_bar_date
    cached = ("AAPL", "5m", "all", 252, n("2026-10-08T15:45:00Z"))
    fp = ("AAPL", "5m", "all", 252, n("2026-10-08T15:45:00+00:00"))
    assert app._cc_chart_decision(cached, fp, _bars("a", "b")) == "reuse"


def test_push_still_works_with_mixed_spellings():
    n = app._cc_norm_bar_date
    cached = ("AAPL", "5m", "all", 2, n("2026-10-08T15:45:00Z"))
    fp = ("AAPL", "5m", "all", 2, n("2026-10-08T15:50:00Z"))
    bars = [{"date": "2026-10-08T15:45:00+00:00"}, {"date": "2026-10-08T15:50:00+00:00"}]
    assert app._cc_chart_decision(cached, fp, bars) == "push"
