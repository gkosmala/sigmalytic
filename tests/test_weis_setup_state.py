"""Tests for backend/weis_setup_state.py -- Weis-only setup states.

Synthetic bars: a range oscillating between a support line (~99.8, swing lows)
and a resistance line (~110.2, swing highs) with 5 touches each, so the line
engine produces horizontal axis lines. Each test appends bars that do (or do
not) break a line and checks the state against the book's sequence.
"""
import pytest

from backend import weis_setup_state as ws


def _bar(c, lo=None, hi=None, v=1000, i=0):
    lo = c - 0.2 if lo is None else lo
    hi = c + 0.2 if hi is None else hi
    return {"t": f"d{i}", "o": c, "h": hi, "l": lo, "c": c, "v": v}


def _range_bars(cycles=6):
    """Triangle wave 100 <-> 110, period 20 bars. Lows at 99.8, highs at 110.2."""
    closes = []
    for _ in range(cycles):
        closes += [100 + k for k in range(0, 10)]          # 100..109
        closes += [110 - k for k in range(0, 10)]          # 110..101
    closes.append(100.0)
    return [_bar(c, i=i) for i, c in enumerate(closes)]


def _with(extra):
    bars = _range_bars()
    base = len(bars)
    for k, b in enumerate(extra):
        b = dict(b)
        b["t"] = f"x{k}"
        bars.append(b)
    return bars


def test_plain_range_is_no_setup():
    out = ws.evaluate_setup_state(_range_bars())
    assert out["state"] == "No setup"


def test_spring_watching_broke_not_back_inside():
    bars = _with([_bar(99.4, lo=99.0, hi=99.9)])
    out = ws.evaluate_setup_state(bars)
    assert out["state"] == "Watching" and out["direction"] == "long"


def test_spring_setting_up_closed_back_inside_on_break_bar():
    bars = _with([_bar(100.2, lo=99.0, hi=100.4)])
    out = ws.evaluate_setup_state(bars)
    assert out["state"] == "Setting Up" and out["direction"] == "long"
    assert out["stop"] == 99.0


def test_spring_armed_after_no_follow_through():
    bars = _with([_bar(100.2, lo=99.0, hi=100.4), _bar(100.8, lo=100.1, hi=101.0)])
    out = ws.evaluate_setup_state(bars)
    assert out["state"] == "Armed" and out["direction"] == "long"


def test_spring_follow_through_flips_to_short():
    # break bar low 99.0 close 99.3; next bar closes below 99.0 = follow-through
    bars = _with([_bar(99.3, lo=99.0, hi=99.9), _bar(98.7, lo=98.5, hi=99.2)])
    out = ws.evaluate_setup_state(bars)
    # the failed spring is not "avoid": support failed, so the line is now supply
    assert out["direction"] == "short" and out["flipped_from"] == "spring"
    assert out["state"] == "Watching"


def test_spring_too_deep_is_not_a_spring():
    # 20 percent below the line is beyond the 15 percent ceiling (p.75, p.99)
    bars = _with([_bar(100.0, lo=80.0, hi=100.4)])
    out = ws.evaluate_setup_state(bars)
    assert out["state"] == "No setup"


def test_upthrust_watching_and_setting_up_and_armed():
    w = ws.evaluate_setup_state(_with([_bar(110.6, lo=110.0, hi=111.0)]))
    assert w["state"] == "Watching" and w["direction"] == "short"
    s = ws.evaluate_setup_state(_with([_bar(109.8, lo=109.6, hi=111.0)]))
    assert s["state"] == "Setting Up" and s["direction"] == "short"
    assert s["stop"] == 111.0
    a = ws.evaluate_setup_state(_with([_bar(109.8, lo=109.6, hi=111.0),
                                        _bar(109.0, lo=108.8, hi=109.7)]))
    assert a["state"] == "Armed" and a["direction"] == "short"


def test_upthrust_follow_through_flips_to_long():
    bars = _with([_bar(110.7, lo=110.0, hi=111.0), _bar(111.6, lo=110.9, hi=111.8)])
    out = ws.evaluate_setup_state(bars)
    assert out["direction"] == "long" and out["flipped_from"] == "upthrust"
    assert out["state"] == "Watching"


def test_against_trend_is_avoid(monkeypatch):
    monkeypatch.setattr(ws, "_trend_before", lambda *a, **k: "down")
    spring = _with([_bar(100.2, lo=99.0, hi=100.4)])
    assert ws.evaluate_setup_state(spring)["state"] == "Avoid"
    monkeypatch.setattr(ws, "_trend_before", lambda *a, **k: "up")
    up = _with([_bar(109.8, lo=109.6, hi=111.0)])
    assert ws.evaluate_setup_state(up)["state"] == "Avoid"


def test_with_trend_keeps_state(monkeypatch):
    monkeypatch.setattr(ws, "_trend_before", lambda *a, **k: "up")
    assert ws.evaluate_setup_state(_with([_bar(100.2, lo=99.0, hi=100.4)]))["state"] == "Setting Up"


def test_target_reached_means_move_already_happened():
    # spring, then a run all the way up through the resistance line
    rally = [_bar(100.2, lo=99.0, hi=100.4)] + [_bar(100.2 + k, i=k) for k in range(1, 12)]
    out = ws.evaluate_setup_state(_with(rally))
    # the spring's own setup is gone (its move already happened); what is left
    # is the failed upthrust at the top of the range, not the spring bar (121)
    assert out.get("flipped_from") == "upthrust" and out["break_index"] > 121


def test_radar_style_bar_keys_are_accepted():
    bars = [{"date": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
             "close": b["c"], "volume": b["v"]} for b in _with([_bar(100.2, lo=99.0, hi=100.4)])]
    assert ws.evaluate_setup_state(bars)["state"] == "Setting Up"


def test_too_few_bars():
    assert ws.evaluate_setup_state([_bar(100)] * 5)["state"] == "No setup"


def test_flipped_short_setting_up_and_armed():
    # spring breaks (low 99.0), next bar closes below it (follow-through), then
    # price retests the broken line from below and closes back under it.
    base = [_bar(99.3, lo=99.0, hi=99.9), _bar(98.7, lo=98.5, hi=99.2)]
    retest = _bar(99.5, lo=99.0, hi=100.0)             # high reaches the 99.8 line
    s = ws.evaluate_setup_state(_with(base + [retest]))
    assert s["state"] == "Setting Up" and s["direction"] == "short"
    a = ws.evaluate_setup_state(_with(base + [retest, _bar(98.9, lo=98.6, hi=99.4)]))
    assert a["state"] == "Armed" and a["direction"] == "short"


def test_flipped_short_dies_if_retest_goes_through():
    base = [_bar(99.3, lo=99.0, hi=99.9), _bar(98.7, lo=98.5, hi=99.2),
            _bar(99.5, lo=99.0, hi=100.0), _bar(100.6, lo=99.4, hi=100.9)]
    out = ws.evaluate_setup_state(_with(base))
    assert out.get("flipped_from") != "spring"


def _zig(start, step, legs=8, bars_per_leg=5, rise=6.0):
    """Zigzag where every leg moves `rise` over `bars_per_leg` bars; up legs
    climb net `step` per cycle."""
    out, p = [], start
    for k in range(legs):
        direction = 1 if k % 2 == 0 else -1
        amt = rise if direction == 1 else rise - step
        for _ in range(bars_per_leg):
            p += direction * amt / bars_per_leg
            out.append(p)
    return out


def test_trend_higher_highs_higher_lows_is_up_and_mirror_is_down():
    up = _zig(100, 2.0, legs=14)
    bars = ws._normalize([_bar(c, i=i) for i, c in enumerate(up)])
    assert ws._swing_trend(bars, "1Day") == "up"
    down = [200 - c + 100 for c in up]
    bars = ws._normalize([_bar(c, i=i) for i, c in enumerate(down)])
    assert ws._swing_trend(bars, "1Day") == "down"


def test_range_has_no_trend():
    assert ws._swing_trend(ws._normalize(_range_bars()), "1Day") == "none"


def test_weekly_grouping_by_iso_week():
    days = []
    import datetime
    d = datetime.date(2026, 1, 5)          # a Monday
    for i in range(14):
        days.append({"t": (d + datetime.timedelta(days=i)).isoformat(),
                     "o": 1, "h": 2 + i, "l": 0, "c": 1, "v": 1})
    weeks = ws._to_weekly(days)
    assert len(weeks) == 2


def _zig_bars(close_list):
    return ws._normalize([_bar(c, i=i) for i, c in enumerate(close_list)])


def test_angle_45_degrees_is_one_unit_per_bar_and_flags_slowdown():
    # unit forced to 1.0 via monkeypatch below: steep legs (2 units/bar ~63 deg)
    # then a shallow up-leg (0.25 units/bar ~14 deg) -> change of character.
    closes = []
    p = 100.0
    for rise_per_bar, n in ((2.0, 6), (-1.0, 6), (2.0, 6), (-1.0, 6),
                            (0.25, 6), (-0.5, 6), (0.25, 6), (-0.5, 6), (0.25, 6)):
        for _ in range(n):
            p += rise_per_bar
            closes.append(p)
    bars = [_bar(c, i=i) for i, c in enumerate(closes)]
    orig = ws._unit
    ws._unit = lambda *a, **k: 1.0
    try:
        out = ws.angle_profile(bars, "1Day")
    finally:
        ws._unit = orig
    ups = [l["degrees"] for l in out["legs"] if l["direction"] == "up"]
    assert max(ups) >= 45 and ups[-1] < 45
    assert any(x.startswith("bullish") for x in out["character_change"])
    assert "Gann" in out["basis"]


def test_angle_unit_modes():
    bars = ws._normalize([_bar(100 + (i % 7), i=i) for i in range(60)])
    box = ws._unit(bars, "box")
    atr = ws._unit(bars, "atr", 1.5)
    assert box >= 0.01 * bars[-1]["c"] and atr > 0


def test_evaluate_carries_angle_with_label():
    out = ws.evaluate_setup_state(_with([_bar(100.2, lo=99.0, hi=100.4)]))
    assert "angle" in out and "Gann" in out["angle"]["basis"]


def test_trend_uses_weekly_context_for_daily_bars():
    import datetime
    d = datetime.date(2025, 1, 6)
    closes = _zig(100, 2.0, legs=40, bars_per_leg=5)      # clear uptrend
    bars = []
    for i, c in enumerate(closes):
        day = d + datetime.timedelta(days=i + 2 * (i // 5))   # skip weekends
        b = _bar(c, i=i); b["t"] = day.isoformat(); bars.append(b)
    nb = ws._normalize(bars)
    assert ws._trend_before(nb, len(nb), "1Day") == "up"


def _frame(closes, tag):
    out = []
    for i, c in enumerate(closes):
        b = _bar(c, i=i); b["t"] = f"{tag}{i:04d}"; out.append(b)
    return out


def test_ladders_are_defined_and_labeled_user_choice():
    assert ws.LADDERS["day"] == {"exec": "15Min", "structure": ["1Hour", "1Day"]}
    assert ws.LADDERS["swing"]["structure"] == ["1Week"]


def test_longer_frame_decides_shorter_frame_does_not_avoid():
    # execution bars: a range (no own trend). 1Hour frame falls, 1Day frame rises:
    # the daily (highest frame) decides, the hourly downtrend does not.
    bars = _frame([c for c in range(100, 160)], "b")
    for x, i in zip(bars, range(len(bars))):
        x["t"] = f"b{i:04d}"
    up = _zig(100, 2.0, legs=40)
    down = [300 - c for c in up]
    htf = {"1Hour": _frame(down, "a"), "1Day": _frame(up, "a")}
    for fb in htf.values():
        for i, x in enumerate(fb):
            x["t"] = f"a{i:04d}"         # all earlier than "b..." bars
    nb = ws._normalize(bars)
    frames = ws._trends_by_frame(nb, len(nb) - 1, "15Min", htf)
    assert frames["1Hour"] == "down" and frames["1Day"] == "up"
    assert ws._trend_before(nb, len(nb) - 1, "15Min", htf) == "up"


def test_higher_frame_bars_after_the_break_are_not_used():
    up = _zig(100, 2.0, legs=40)
    fb = _frame(up, "z")                 # "z..." sorts AFTER the exec bars
    bars = _frame(list(range(100, 130)), "b")
    nb = ws._normalize(bars)
    frames = ws._trends_by_frame(nb, len(nb) - 1, "15Min", {"1Day": fb})
    assert frames["1Day"] == "none"      # no completed higher bars yet
