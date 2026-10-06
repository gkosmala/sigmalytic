"""Imbalance Alert engine: pillars, combining rule, guardrail, replay, gate."""
import os
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

import imbalance_engine as ie


def _bars(n=60, drift=0.0, last=None):
    out, px = [], 100.0
    for i in range(n):
        px *= 1 + drift + (0.004 if i % 2 else -0.004)
        out.append({"o": px * 0.998, "h": px * 1.006, "l": px * 0.994, "c": px, "v": 1_000_000})
    if last:
        out[-1].update(last)
    return out


def _breakout_up():
    b = _bars(60)
    top = max(x["h"] for x in b[-21:-1])
    b[-1].update({"o": top * 1.0, "c": top * 1.03, "h": top * 1.032, "l": top * 0.999, "v": 3_000_000})
    return b


def _breakdown():
    b = _bars(60)
    low = min(x["l"] for x in b[-21:-1])
    b[-1].update({"o": low * 1.0, "c": low * 0.97, "h": low * 1.001, "l": low * 0.968, "v": 3_000_000})
    return b


OPT_BULL = {"status": "OK", "spot_price": 100, "net_gamma_regime": "POSITIVE", "zero_gamma_level": 95,
            "nearest_wall_above": {"distance_to_spot_pct": 0.05}, "nearest_wall_below": {"distance_to_spot_pct": -0.01}}


def test_breakout_votes_long_on_price_and_volume():
    b = _breakout_up()
    assert ie.price_pillar(b)["direction"] == ie.LONG
    assert ie.volume_pillar(b)["direction"] == ie.LONG


def test_breakdown_votes_short():
    b = _breakdown()
    assert ie.price_pillar(b)["direction"] == ie.SHORT
    assert ie.volume_pillar(b)["direction"] == ie.SHORT


def test_too_few_bars_unavailable():
    assert not ie.price_pillar(_bars(10))["available"]
    assert not ie.volume_pillar(_bars(10))["available"]


def test_options_unavailable_without_data():
    assert not ie.options_pillar(None)["available"]
    assert not ie.options_pillar({"status": "NO_OPTIONS_DATA"})["available"]


def test_options_bull_with_call_skew():
    p = ie.options_pillar(OPT_BULL, call_volume=8000, put_volume=2000)
    assert p["direction"] == ie.LONG and p["strength"] > 55


def test_two_of_three_fires_without_options():
    r = ie.evaluate("X", _breakout_up())
    assert r["fired"] and r["direction"] == ie.LONG and r["tier"] == "STANDARD" and r["pillars_agreeing"] == 2


def test_three_of_three_is_strong():
    r = ie.evaluate("X", _breakout_up(), OPT_BULL, 8000, 2000)
    assert r["fired"] and r["tier"] == "STRONG"


def test_opposing_pillar_blocks_alert():
    bear_opt = {"status": "OK", "spot_price": 100, "net_gamma_regime": "DEEP_NEGATIVE", "zero_gamma_level": 105,
                "nearest_wall_above": {"distance_to_spot_pct": 0.01}, "nearest_wall_below": {"distance_to_spot_pct": -0.05}}
    r = ie.evaluate("X", _breakout_up(), bear_opt, 1000, 9000)
    assert not r["fired"]


def test_min_agree_three_requires_all():
    r = ie.evaluate("X", _breakout_up(), config={"min_agree": 3})
    assert not r["fired"]


def test_quiet_market_no_alert():
    assert not ie.evaluate("X", _bars(60))["fired"]


def test_guardrail_adds_notes_but_never_changes_direction():
    base = ie.evaluate("X", _breakout_up())
    warned = ie.evaluate("X", _breakout_up(), behavior={"losing_streak": 4, "trades_today": 9})
    assert warned["guardrail"]["caution"] and len(warned["guardrail"]["notes"]) == 2
    assert warned["direction"] == base["direction"] and warned["fired"] == base["fired"]
    assert ie.behavior_guardrail(None) == {"caution": False, "notes": []}


def test_replay_scores_alerts_and_respects_cooldown():
    b = _bars(80)
    b += _breakout_up()[-1:] * 1
    res = ie.replay_bars(b, horizons=(1, 3))
    assert "summary" in res and res["summary"]["alerts"] >= 0
    idx = [a["index"] for a in res["alerts"]]
    assert all(y - x >= 5 for x, y in zip(idx, idx[1:]))


def test_gate_dedup_and_flip():
    g = ie.AlertGate(cooldown_seconds=100)
    assert g.allow("A", ie.LONG, 0)
    assert not g.allow("A", ie.LONG, 50)
    assert g.allow("A", ie.SHORT, 60)
    assert g.allow("A", ie.SHORT, 400)
