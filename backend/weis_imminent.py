"""Completed-bar Spring/Upthrust events for the Weis quantum handoff.

The structural boundary is found from prior bars only. An event requires a
literal breach and close back inside. Wave readings strengthen the evidence;
none is asserted to be proof of institutional participation.
"""
from __future__ import annotations

import math

import pandas as pd

from backend.weis_trade_finder import _preceding_climax


def _number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def _separated_touches(prepared, level, *, is_support, gap=10):
    """Require two distinct swings at the line, separated in bar time."""
    if level is None:
        return False
    window = prepared.iloc[:-5]
    flag, price = ("is_low", "low") if is_support else ("is_high", "high")
    positions = [i for i, row in enumerate(window.itertuples(index=False))
                 if bool(getattr(row, flag)) and
                 abs(float(getattr(row, price)) / level - 1) <= .0015]
    return len(positions) >= 2 and positions[-1] - positions[0] >= gap


def _volume_ratio(waves, current, direction):
    """Compare the just-ended penetration wave to preceding same-side waves."""
    same = [w for w in waves if w.get("dir") == direction and _number(w.get("vol"))]
    if current and current.get("dir") == direction:
        tested, prior = current, same[-3:]
    elif same:
        tested, prior = same[-1], same[-4:-1]
    else:
        return None
    volumes = [_number(w.get("vol")) for w in prior]
    value = _number(tested.get("vol"))
    if not volumes or any(v is None or v <= 0 for v in volumes) or value is None:
        return None
    return value / (sum(volumes) / len(volumes))


def wave_effort_result(waves, current, direction):
    """Compare cumulative volume, wave distance, and new extremes on one side."""
    same = [w for w in waves if w.get("dir") == direction]
    if current and current.get("dir") == direction:
        tested, prior = current, same[-3:]
    elif same:
        tested, prior = same[-1], same[-4:-1]
    else:
        return {"effort_without_result": False, "diminished_volume_new_extreme": False}
    valid = [w for w in prior if all(_number(w.get(k)) is not None for k in ("vol", "delta", "end"))]
    vol, delta, end = (_number(tested.get(k)) for k in ("vol", "delta", "end"))
    if len(valid) < 2 or any(v is None for v in (vol, delta, end)):
        return {"effort_without_result": False, "diminished_volume_new_extreme": False}
    avg_vol = sum(float(w["vol"]) for w in valid) / len(valid)
    avg_delta = sum(float(w["delta"]) for w in valid) / len(valid)
    prior_extreme = _number(valid[-1]["end"])
    if avg_vol <= 0 or avg_delta <= 0 or prior_extreme is None:
        return {"effort_without_result": False, "diminished_volume_new_extreme": False}
    fresh_extreme = end < prior_extreme if direction == -1 else end > prior_extreme
    return {
        "effort_without_result": vol >= 1.5 * avg_vol and delta <= .5 * avg_delta,
        "diminished_volume_new_extreme": fresh_extreme and vol <= .7 * avg_vol,
        "effort_ratio": round(vol / avg_vol, 4),
        "result_ratio": round(delta / avg_delta, 4),
    }


def find_imminent_weis_events(symbol, bars, timeframe, *, structure_engine=None, weis_engine=None):
    """Return latest-bar, level-validated directional reversals.

    A future fill is never claimed. The next bar must reach the test bar's
    high (long) or low (short); the stop is beyond its opposite extreme.
    """
    if len(bars) < 65:
        return []
    if structure_engine is None:
        from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
        structure_engine = WyckoffVerdictEngine()
    if weis_engine is None:
        from backend.research_engine.weis_verdict_engine import WeisVerdictEngine
        weis_engine = WeisVerdictEngine()
    sample = bars[-252:]
    df = pd.DataFrame([{"open": b["o"], "high": b["h"], "low": b["l"],
                        "close": b["c"], "volume": b["v"], "date": b.get("t")}
                       for b in sample])
    if any(df[k].map(_number).isna().any() for k in ("open", "high", "low", "close", "volume")):
        return []
    prior = df.iloc[:-1]
    prepared = structure_engine._prepare(prior)
    if len(prepared) < 64:
        return []
    idx = len(prepared) - 1
    support = structure_engine._find_well_defined_level(prepared, idx, is_support=True)
    resistance = structure_engine._find_well_defined_level(prepared, idx, is_support=False)
    if not _separated_touches(prepared, support, is_support=True):
        support = None
    if not _separated_touches(prepared, resistance, is_support=False):
        resistance = None
    bar = df.iloc[-1]
    tests = []
    if support and bar["low"] < support < bar["close"]:
        tests.append(("Long", "SPRING", support, -1, "high", "low", resistance,
                      "sot_downwaves", "volume_exhaustion", "effort_without_reward"))
    if resistance and bar["close"] < resistance < bar["high"] and bar["high"] <= 1.15 * resistance:
        tests.append(("Short", "UPTHRUST", resistance, 1, "low", "high", support,
                      "sot_upwaves", "buying_exhaustion", "buying_effort_without_reward"))
    if not tests:
        return []

    # Pre-event Weis readings cannot see the penetration bar or future bars.
    wave = weis_engine.evaluate(prior, symbol=symbol)
    completed, _, _, current = weis_engine.build_waves(weis_engine._prepare(df))
    results = []
    for side, signal, level, direction, entry_key, stop_key, opposite, sot_key, exhaust_key, effort_key in tests:
        entry, stop, close = (_number(bar[entry_key]), _number(bar[stop_key]), _number(bar["close"]))
        if not all(v is not None and v > 0 for v in (entry, stop, close)):
            continue
        if not (stop < level < close <= entry if side == "Long" else
                entry <= close < level < stop):
            continue
        ratio = _volume_ratio(completed, current, direction)
        behavior = wave_effort_result(completed, current, direction)
        climax = _preceding_climax(completed, direction)
        risk = abs(entry - stop)
        target = _number(opposite)
        reward = ((target - entry) if side == "Long" else (entry - target)) if target else None
        results.append({
            "symbol": symbol, "timeframe": timeframe, "side": side,
            "test_bar_time": str(sample[-1].get("t") or ""), "state": "TRIGGERED",
            "signals": [signal], "structure_level": round(float(level), 4),
            "test_close": close, "entry_trigger": entry, "invalidation": stop,
            "target": target if reward is not None and reward > 0 else None,
            "reward_risk": round(reward / risk, 4) if reward is not None and reward > 0 and risk > 0 else None,
            "risk_per_share": round(risk, 4),
            "wave_volume_ratio": round(ratio, 4) if ratio is not None else None,
            "low_volume_test": ratio is not None and ratio < .7,
            "wave_behavior": behavior,
            "test_score": 100, "sot_score": wave.get(sot_key, 0),
            "exhaustion_score": wave.get(exhaust_key, 0),
            "effort_without_reward_score": wave.get(effort_key, 0),
            "preceding_climax": climax,
        })
    return results
