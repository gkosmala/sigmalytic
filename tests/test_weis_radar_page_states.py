"""Weis Radar page runs on the Weis setup state (same engine and window as the Radar Status)."""
import os
import sys

HERE = os.path.dirname(__file__)
ROOT = os.path.join(HERE, "..")
for p in (ROOT, os.path.join(ROOT, "backend"), os.path.join(ROOT, "frontend"), HERE):
    sys.path.insert(0, p)

import test_weis_setup_state as t
from backend import weis_radar_states as wrs
from backend import weis_setup_state as wss


def _bars():
    return t._with([t._bar(100.2, lo=99.0, hi=100.4)])


def test_state_row_matches_the_engine_on_the_same_window():
    bars = _bars()
    row = wrs.state_row("AAA", bars, 289)
    direct = wss.evaluate_setup_state(wss.drop_incomplete(bars, "1Day")[-289:])
    assert row["state"] == direct["state"] == "Setting Up"
    assert row["direction"] == direct["direction"]
    assert row["symbol"] == "AAA"


def test_state_row_respects_the_bar_count_window(monkeypatch):
    seen = {}
    real = wss.evaluate_setup_state

    def spy(bars, *a, **k):
        seen["n"] = len(bars)
        return real(bars, *a, **k)

    monkeypatch.setattr(wss, "evaluate_setup_state", spy)
    bars = _bars()
    wrs.state_row("AAA", bars, 60)
    assert seen["n"] <= 60


def test_state_row_none_when_no_setup_or_too_few_bars():
    assert wrs.state_row("AAA", [t._bar(100)] * 5, 289) is None


def test_block_orders_armed_first_and_counts():
    rows = [{"symbol": s, "state": st} for s, st in
            [("Z", "Avoid"), ("B", "Watching"), ("A", "Armed"), ("C", "Setting Up"), ("D", "Armed")]]
    blk = wrs.build_block(rows, 289, 1000, "1Day")
    assert [r["symbol"] for r in blk["rows"]] == ["A", "D", "C", "B", "Z"]
    assert blk["counts"] == {"Armed": 2, "Setting Up": 1, "Watching": 1, "Avoid": 1}
    assert blk["available"] and blk["bar_count"] == 289


def test_block_unavailable_for_non_daily_timeframes():
    assert wrs.unavailable_block("1Hour")["available"] is False
    assert wrs.build_block([], 289, 10, "1Hour")["available"] is False


def test_by_symbol_handles_missing_block():
    assert wrs.by_symbol(None) == {}
    assert wrs.by_symbol({"rows": [{"symbol": "X", "state": "Armed"}]})["X"]["state"] == "Armed"


def test_page_renders_state_table_and_labels_older_engine():
    import app
    block = wrs.build_block([
        {"symbol": "GXO", "state": "Avoid", "direction": "long", "reason": "against the longer-term trend (p.87, p.96)",
         "trends_by_frame": {"1Day": "down", "1Week": "up"}, "stop": 45.2, "target": 66.85},
        {"symbol": "TRV", "state": "Armed", "direction": "long", "line_source": "trendline", "line_touches": 2,
         "stop": 353.79, "target": None}], 289, 1000, "1Day")
    text = str(app._render_weis_state_table(block))
    assert text.index("TRV") < text.index("GXO")          # Armed before Avoid
    assert "No target defined" in text and "against the longer-term trend" in text
    states = app._weis_state_map({"weis_states": block})
    old = str(app._render_weis_quantum_handoff(
        {"validated_events": [{"symbol": "GXO", "side": "Long", "signals": ["SPRING"],
                               "raw": {"armed": True, "entry_trigger": 46.17, "invalidation": 45.21}}],
         "candidate_count": 1}, states))
    assert "Armed (older rule)" in old and "Weis setup state" in old and "Older engine" in old
    assert "Avoid long" in old                              # GXO now shows the Weis state next to the old Armed


def test_page_state_table_handles_missing_and_non_daily():
    import app
    assert "after the next scan" in str(app._render_weis_state_table(None))
    assert "daily-bar rule" in str(app._render_weis_state_table(wrs.unavailable_block("1Hour")))


def test_older_tables_say_pending_not_no_setup_before_the_first_new_scan():
    import app
    assert app._weis_state_map({}) is None                       # scan from before the upgrade
    assert app._weis_state_map({"weis_states": wrs.unavailable_block("1Hour")}) is None
    pending = str(app._render_weis_quantum_handoff(
        {"validated_events": [{"symbol": "GXO", "side": "Long", "signals": ["SPRING"],
                               "raw": {"armed": True, "entry_trigger": 46.17, "invalidation": 45.21}}],
         "candidate_count": 1}, None))
    assert "Pending next scan" in pending and "No setup" not in pending
    block = wrs.build_block([], 289, 10, "1Day")                 # new scan, GXO has no setup
    known = str(app._render_weis_quantum_handoff(
        {"validated_events": [{"symbol": "GXO", "side": "Long", "signals": ["SPRING"],
                               "raw": {"armed": True, "entry_trigger": 46.17, "invalidation": 45.21}}],
         "candidate_count": 1}, app._weis_state_map({"weis_states": block})))
    assert "No setup" in known and "Pending next scan" not in known

def test_event_list_says_pending_for_a_scan_without_setup_states():
    import app
    old = str(app._render_weis_radar_table([{"symbol": "GXO", "hits": [{"type": "SPRING", "price": 45.99, "score": 100}]}]))
    assert "Pending next scan" in old and "No setup" not in old
    new_none = str(app._render_weis_radar_table([{"symbol": "GXO", "weis_state": None, "weis_direction": None,
                                                  "hits": [{"type": "SPRING", "price": 45.99, "score": 100}]}]))
    assert "No setup" in new_none and "Pending next scan" not in new_none
    armed = str(app._render_weis_radar_table([{"symbol": "TRV", "weis_state": "Armed", "weis_direction": "long",
                                               "hits": [{"type": "SPRING", "price": 360.6, "score": 100}]}]))
    assert "Armed long" in armed


def test_target_is_never_zero_or_negative():
    from types import SimpleNamespace as L
    mk = lambda v, side: L(value_at=lambda b, v=v: v, side=side)
    # short setup: the only line below the break extrapolates to -2.29, so there is no target
    assert wss._target([mk(-2.29, "support")], "resistance", 10, 78.0) is None
    # a valid line below the break is still found, and the negative one is ignored
    assert wss._target([mk(-2.29, "support"), mk(70.0, "support"), mk(60.0, "support")], "resistance", 10, 78.0) == 70.0
    # long setup unchanged
    assert wss._target([mk(90.0, "resistance"), mk(95.0, "resistance")], "support", 10, 80.0) == 90.0


def test_book_page_citations_are_not_shown_on_the_weis_radar_page():
    import app
    f = app._strip_book_pages
    assert f("no follow-through after the close back inside (p.78, p.88)") == "no follow-through after the close back inside"
    assert f("retest of the broken line closed back away from it (p.76, pp.112-113)") == "retest of the broken line closed back away from it"
    assert f("against the longer-term trend (p.87, p.96)") == "against the longer-term trend"
    assert f("closed back inside earlier, then closed beyond the line again; waiting for a fresh close back (secondary test, p.78)") == \
        "closed back inside earlier, then closed beyond the line again; waiting for a fresh close back (secondary test)"
    assert f(None) == ""
    block = wrs.build_block([{"symbol": "AAA", "state": "Armed", "direction": "long",
                              "reason": "no follow-through after the close back inside (p.78, p.88)"}], 289, 10, "1Day")
    text = str(app._render_weis_state_table(block))
    assert "no follow-through after the close back inside" in text and "p.78" not in text
