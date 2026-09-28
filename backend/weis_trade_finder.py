"""Structural trade setups from the active Weis scan's completed OHLCV bars.

An ARMED setup is a plan, not an executed trade or a profit probability.
The entry requires a subsequent bar to reach the test bar's extreme.
"""
from __future__ import annotations

import math


def _num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _preceding_climax(waves, direction):
    """Last completed same-direction wave dwarfs earlier waves in volume and reach."""
    same = [w for w in waves if w.get("dir") == direction]
    if len(same) < 3:
        return False
    current, prior = same[-1], same[-3:-1]
    volumes = sorted(float(w["vol"]) for w in prior)
    distances = sorted(float(w["delta"]) for w in prior)
    return (volumes[0] > 0 and distances[0] > 0 and
            float(current["vol"]) >= 2 * (sum(volumes) / len(volumes)) and
            float(current["delta"]) >= 1.5 * (sum(distances) / len(distances)))


def _test_wave_volume_ratio(waves, current, direction):
    """Test wave volume divided by preceding waves in the same direction."""
    same = [w for w in waves if w.get("dir") == direction and _num(w.get("vol")) is not None]
    if current and current.get("dir", direction) == direction:
        tested, prior = current, same[-3:]
    elif same:
        tested, prior = same[-1], same[-4:-1]
    else:
        return None
    volumes = [_num(w.get("vol")) for w in prior]
    tested_volume = _num(tested.get("vol"))
    if not volumes or any(v is None or v <= 0 for v in volumes) or tested_volume is None or tested_volume <= 0:
        return None
    return tested_volume / (sum(volumes) / len(volumes))


def build_trade_setup(symbol, bars, timeframe, *, wyckoff_engine=None, weis_engine=None,
                      min_reward_risk=2.0):
    """Require mature structure, wave exhaustion, and a light-volume sweep/reclaim.

    All fields use bars at or before the scan bar. No future result is used to
    select a setup. Existing verdict engines own structure and wave scoring.
    """
    if len(bars) < 65:
        return None
    import pandas as pd
    from backend.research_engine.weis_verdict_engine import WeisVerdictEngine
    from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine

    wyckoff_engine = wyckoff_engine or WyckoffVerdictEngine()
    weis_engine = weis_engine or WeisVerdictEngine()
    df = pd.DataFrame([{"open": b["o"], "high": b["h"], "low": b["l"],
                        "close": b["c"], "volume": b["v"], "date": b.get("t")}
                       for b in bars[-252:]])
    if not all(df[col].map(_num).notna().all() for col in ("open", "high", "low", "close", "volume")):
        return None
    prepared = wyckoff_engine._prepare(df)
    idx = len(prepared) - 1
    if idx < 64:
        return None
    test = prepared.iloc[-1]
    support = wyckoff_engine._find_well_defined_level(prepared, idx, is_support=True)
    resistance = wyckoff_engine._find_well_defined_level(prepared, idx, is_support=False)
    long_test = support is not None and test["low"] < support < test["close"]
    short_test = resistance is not None and test["close"] < resistance < test["high"]
    if not (long_test or short_test):
        return None
    structure = wyckoff_engine.evaluate_bars(df, symbol=symbol)
    if structure.get("verdict") in {"INSUFFICIENT_DATA", "NO_MEANINGFUL_STRUCTURE"}:
        return None
    # The exhaustion and mature range must exist BEFORE the test bar.
    wave = weis_engine.evaluate(df.iloc[:-1], symbol=symbol)
    if not wave.get("range_is_mature"):
        return None
    prior_waves, _, _, _ = weis_engine.build_waves(weis_engine._prepare(df.iloc[:-1]))
    # Use this same ATR-calibrated Weis wave segmentation for the test's
    # volume comparison. The Wyckoff chart series has different boundaries.
    test_waves, _, _, current_test_wave = weis_engine.build_waves(weis_engine._prepare(df))
    possibilities = (
        ("Long", "spring_score", "sot_downwaves", "volume_exhaustion",
         "effort_without_reward", "range_resistance", "low", "high"),
        ("Short", "upthrust_score", "sot_upwaves", "buying_exhaustion",
         "buying_effort_without_reward", "range_support", "high", "low"),
    )
    qualified = []
    for side, test_key, sot_key, exhaustion_key, friction_key, target_key, stop_key, entry_key in possibilities:
        volume_ratio = _test_wave_volume_ratio(test_waves, current_test_wave,
                                                -1 if side == "Long" else 1)
        if volume_ratio is None or volume_ratio >= .7:
            continue
        test_score = _num(structure.get(test_key)) or 0
        sot = _num(wave.get(sot_key)) or 0
        exhaustion = _num(wave.get(exhaustion_key)) or 0
        friction = _num(wave.get(friction_key)) or 0
        climax = _preceding_climax(prior_waves, -1 if side == "Long" else 1)
        if test_score < 65 or not (climax or sot >= 100 and max(exhaustion, friction) >= 100):
            continue
        # The level score alone is not sufficient: verify the actual sweep,
        # close back inside, and the structural level used for the trade.
        level = support if side == "Long" else resistance
        level = _num(level)
        target = _num(wave.get(target_key))
        entry = _num(test[entry_key])
        stop = _num(test[stop_key])
        close = _num(test["close"])
        if any(v is None or v <= 0 for v in (level, target, entry, stop, close)):
            continue
        if side == "Long":
            if not (stop < level < close <= entry < target):
                continue
            risk, reward = entry - stop, target - entry
        else:
            if not (target < entry <= close < level < stop):
                continue
            risk, reward = stop - entry, entry - target
        if risk <= 0 or reward <= 0 or reward / risk < min_reward_risk:
            continue
        qualified.append({
            "symbol": symbol, "timeframe": timeframe, "side": side, "state": "ARMED",
            "test_bar_time": str(bars[-1].get("t") or ""),
            "test_close": close, "structure_level": level,
            "entry_trigger": entry, "invalidation": stop, "target": target,
            "risk_per_share": round(risk, 6), "reward_per_share": round(reward, 6),
            "risk_pct": round(risk / entry * 100, 4),
            "reward_risk": round(reward / risk, 4),
            "test_score": test_score, "wave_volume_ratio": round(volume_ratio, 4),
            "sot_score": sot, "exhaustion_score": exhaustion,
            "effort_without_reward_score": friction,
            "preceding_climax": climax,
            "range_support_touches": wave.get("range_support_touches"),
            "range_resistance_touches": wave.get("range_resistance_touches"),
            "evidence": ["mature range", "multi-touch level sweep and reclaim",
                         "light-volume test wave"] +
                        (["preceding climactic wave"] if climax else []) +
                        (["shortening of thrust",
                          "weak-volume exhaustion" if exhaustion >= 100 else "heavy-volume effort without result"]
                         if sot >= 100 and max(exhaustion, friction) >= 100 else []),
        })
    if len(qualified) != 1:
        return None
    return qualified[0]


def evaluate_trade_path(setup, future_bars, *, max_bars=10, cost_bps=0):
    """Conservative bar-level target/stop outcome, beginning after test bar.

    A bar that reaches both levels resolves at the stop. Entry is at the
    trigger or a worse opening gap. No filled trade is labeled profitable
    using only a close or a maximum favorable excursion.
    """
    side = setup["side"]
    trigger, stop, target = (float(setup[k]) for k in ("entry_trigger", "invalidation", "target"))
    entry = None
    observed = 0
    for bar in future_bars[:max_bars]:
        observed += 1
        o, h, l, c = (float(bar[k]) for k in ("o", "h", "l", "c"))
        if entry is None:
            if side == "Long" and h < trigger or side == "Short" and l > trigger:
                continue
            entry = max(o, trigger) if side == "Long" else min(o, trigger)
            if side == "Long" and entry >= target or side == "Short" and entry <= target:
                return {"status": "GAP_PAST_TARGET", "filled": False, "bars_observed": observed}
            risk = (entry - stop) if side == "Long" else (stop - entry)
            if risk <= 0:
                return {"status": "INVALID_FILL", "filled": False, "bars_observed": observed}
        hit_stop = l <= stop if side == "Long" else h >= stop
        hit_target = h >= target if side == "Long" else l <= target
        if hit_stop or hit_target:
            # At OHLC resolution the within-bar sequence is unknowable.
            # Resolve simultaneous touches against the trade.
            if hit_stop:
                exit_price = min(o, stop) if side == "Long" else max(o, stop)
                status = "STOP_FIRST_OR_AMBIGUOUS" if hit_target else "STOP"
            else:
                exit_price = target
                status = "TARGET"
            gross = (exit_price - entry) if side == "Long" else (entry - exit_price)
            net = gross - (entry + exit_price) * cost_bps / 10000
            return {"status": status, "filled": True, "entry": entry, "exit": exit_price,
                    "net_per_share": round(net, 6), "net_r": round(net / risk, 6),
                    "bars_observed": observed}
    if entry is None:
        return {"status": "NO_ENTRY", "filled": False, "bars_observed": observed}
    if len(future_bars) < max_bars:
        return {"status": "OPEN", "filled": True, "entry": entry, "bars_observed": observed}
    last = float(future_bars[max_bars - 1]["c"])
    gross = (last - entry) if side == "Long" else (entry - last)
    net = gross - (entry + last) * cost_bps / 10000
    return {"status": "TIME_EXIT", "filled": True, "entry": entry, "exit": last,
            "net_per_share": round(net, 6), "net_r": round(net / risk, 6),
            "bars_observed": observed}


def backtest_symbol(symbol, bars, timeframe, *, max_bars=10, cost_bps=5,
                    build=build_trade_setup):
    """Walk history forward; never use future bars when constructing a plan."""
    trades = []
    next_allowed = 64
    for i in range(64, len(bars) - max_bars):
        if i < next_allowed:
            continue
        setup = build(symbol, bars[:i + 1], timeframe)
        if not setup:
            continue
        outcome = evaluate_trade_path(setup, bars[i + 1:i + 1 + max_bars],
                                      max_bars=max_bars, cost_bps=cost_bps)
        trades.append({"setup": setup, "outcome": outcome})
        next_allowed = i + max_bars + 1
    completed = [t["outcome"] for t in trades if t["outcome"].get("net_r") is not None]
    return {"symbol": symbol, "timeframe": timeframe, "plans": len(trades),
            "completed": len(completed), "profitable": sum(t["net_r"] > 0 for t in completed),
            "target_first": sum(t["status"] == "TARGET" for t in completed),
            "average_modeled_net_r": round(sum(t["net_r"] for t in completed) / len(completed), 4)
            if completed else None,
            "modeled_cost_bps_per_side": cost_bps, "max_bars": max_bars,
            "trades": trades}
