# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/imbalance_engine.py
---------------------------
Imbalance Alert engine.

An "imbalance" is a moment when independent evidence lines up on one side:

  Pillar 1  Options flow     - dealer gamma regime, put/call volume, nearest walls
  Pillar 2  Price structure  - trend, range breakout, higher highs / lows
  Pillar 3  Volume flow      - relative volume, up/down volume, close location

Each pillar votes LONG, SHORT or NEUTRAL with a 0-100 strength and plain-English
evidence. An imbalance is declared when at least `min_agree` pillars vote the
same way and none votes the opposite way (default 2 of 3; 3 of 3 is "STRONG").

Behavioural metrics are NOT a directional vote. They are a guardrail on the
subscriber (`behavior_guardrail`) that adds a note to the alert; they never
change the direction or whether it fires.

Pure functions only: no network, no database, no clock. Callers supply data.
The price and volume pillars use only daily bars, so they can be replayed
historically (`replay_bars`). The options pillar needs a live chain snapshot
and cannot be replayed without historical option data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

LONG, SHORT, NEUTRAL = "LONG", "SHORT", "NEUTRAL"

DEFAULTS = {
    "min_agree": 2,
    "min_pillar_strength": 55.0,
    "cooldown_bars": 5,
}

MIN_BARS = 30


def _f(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _vote(direction: str, strength: float, evidence: List[str], available: bool = True) -> Dict[str, Any]:
    return {
        "direction": direction,
        "strength": round(_clamp(strength), 1),
        "evidence": evidence,
        "available": available,
    }


def _unavailable(reason: str) -> Dict[str, Any]:
    return _vote(NEUTRAL, 0.0, [reason], available=False)


def _sma(vals: Sequence[float], n: int) -> Optional[float]:
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


# ---------------------------------------------------------------------------
# Pillar 1: options flow
# ---------------------------------------------------------------------------

def options_pillar(opt: Optional[Dict[str, Any]], call_volume: Optional[float] = None,
                   put_volume: Optional[float] = None) -> Dict[str, Any]:
    """
    `opt` is the GammaStrikeMatrixEngine.build() result. call_volume/put_volume
    are chain-wide totals when the caller has them (the engine only reports
    per-strike figures).
    """
    if not opt or opt.get("status") != "OK":
        return _unavailable("No options data for this symbol right now")

    spot = _f(opt.get("spot_price"))
    if spot <= 0:
        return _unavailable("Invalid spot price")

    score = 0.0  # positive = long, negative = short
    ev: List[str] = []

    regime = str(opt.get("net_gamma_regime") or "UNKNOWN")
    zero = opt.get("zero_gamma_level")
    if regime in ("POSITIVE", "DEEP_POSITIVE"):
        # spot above the zero-gamma level: dealers dampen moves; supportive for longs
        score += 20 if regime == "POSITIVE" else 30
        ev.append(f"Spot is above the zero-gamma level ({_f(zero):.2f}); dealer hedging cushions dips")
    elif regime in ("NEGATIVE", "DEEP_NEGATIVE"):
        score -= 20 if regime == "NEGATIVE" else 30
        ev.append(f"Spot is below the zero-gamma level ({_f(zero):.2f}); dealer hedging amplifies drops")

    if call_volume is not None and put_volume is not None and (call_volume + put_volume) > 0:
        total = call_volume + put_volume
        skew = (call_volume - put_volume) / total  # -1..1
        score += skew * 45
        ev.append(f"Calls are {call_volume / total * 100:.0f}% of option volume today")

    above, below = opt.get("nearest_wall_above"), opt.get("nearest_wall_below")
    if above and below:
        da = abs(_f(above.get("distance_to_spot_pct")))
        db = abs(_f(below.get("distance_to_spot_pct")))
        if da + db > 0:
            room = (db - da) / (da + db)  # >0: resistance closer than support -> bearish lean
            # more room above than below favours longs
            score += (-room) * 15
            if abs(room) > 0.3:
                side = "above" if room < 0 else "below"
                ev.append(f"More open room {side} the price before the next gamma wall")

    direction = LONG if score > 0 else SHORT if score < 0 else NEUTRAL
    return _vote(direction, abs(score), ev or ["Options data is balanced"])


# ---------------------------------------------------------------------------
# Pillar 2: price structure
# ---------------------------------------------------------------------------

def price_pillar(bars: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if len(bars) < MIN_BARS:
        return _unavailable(f"Need {MIN_BARS} daily bars; have {len(bars)}")

    closes = [_f(b.get("c")) for b in bars]
    highs = [_f(b.get("h")) for b in bars]
    lows = [_f(b.get("l")) for b in bars]
    last = closes[-1]
    if last <= 0:
        return _unavailable("Invalid last price")

    score = 0.0
    ev: List[str] = []

    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50) if len(closes) >= 50 else None
    if sma20:
        if last > sma20:
            score += 20
            ev.append("Closing above the 20-day average")
        elif last < sma20:
            score -= 20
            ev.append("Closing below the 20-day average")
    if sma50:
        if last > sma50:
            score += 10
        elif last < sma50:
            score -= 10

    prior_high = max(highs[-21:-1])
    prior_low = min(lows[-21:-1])
    if last > prior_high:
        score += 40
        ev.append("Closed above the prior 20-day high (breakout)")
    elif last < prior_low:
        score -= 40
        ev.append("Closed below the prior 20-day low (breakdown)")

    recent_h, earlier_h = max(highs[-10:]), max(highs[-20:-10])
    recent_l, earlier_l = min(lows[-10:]), min(lows[-20:-10])
    if recent_h > earlier_h and recent_l > earlier_l:
        score += 20
        ev.append("Higher highs and higher lows over the last 20 days")
    elif recent_h < earlier_h and recent_l < earlier_l:
        score -= 20
        ev.append("Lower highs and lower lows over the last 20 days")

    direction = LONG if score > 0 else SHORT if score < 0 else NEUTRAL
    return _vote(direction, abs(score), ev or ["No clear structure"])


# ---------------------------------------------------------------------------
# Pillar 3: volume flow
# ---------------------------------------------------------------------------

def volume_pillar(bars: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if len(bars) < MIN_BARS:
        return _unavailable(f"Need {MIN_BARS} daily bars; have {len(bars)}")

    vols = [_f(b.get("v")) for b in bars]
    closes = [_f(b.get("c")) for b in bars]
    opens = [_f(b.get("o")) for b in bars]
    highs = [_f(b.get("h")) for b in bars]
    lows = [_f(b.get("l")) for b in bars]

    base = sum(vols[-21:-1]) / 20.0
    if base <= 0:
        return _unavailable("No volume history")
    rvol = vols[-1] / base

    score = 0.0
    ev: List[str] = []

    rng = highs[-1] - lows[-1]
    loc = (closes[-1] - lows[-1]) / rng if rng > 0 else 0.5  # 0 = low, 1 = high
    day_dir = 1 if closes[-1] > opens[-1] else -1 if closes[-1] < opens[-1] else 0

    if rvol >= 1.5 and day_dir:
        score += day_dir * min(40.0, (rvol - 1.0) * 30.0)
        ev.append(f"Volume is {rvol:.1f}x normal on a {'up' if day_dir > 0 else 'down'} day")
    if loc >= 0.7:
        score += 15
        ev.append("Closed near the high of the day")
    elif loc <= 0.3:
        score -= 15
        ev.append("Closed near the low of the day")

    up_v = sum(v for v, c, o in zip(vols[-10:], closes[-10:], opens[-10:]) if c > o)
    dn_v = sum(v for v, c, o in zip(vols[-10:], closes[-10:], opens[-10:]) if c < o)
    if up_v + dn_v > 0:
        skew = (up_v - dn_v) / (up_v + dn_v)
        score += skew * 45
        ev.append(f"{up_v / (up_v + dn_v) * 100:.0f}% of the last 10 days' volume came on up days")

    direction = LONG if score > 0 else SHORT if score < 0 else NEUTRAL
    return _vote(direction, abs(score), ev or ["Volume is unremarkable"])


# ---------------------------------------------------------------------------
# Behavioural guardrail (not a vote)
# ---------------------------------------------------------------------------

def behavior_guardrail(behavior: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    `behavior` is optional subscriber context, e.g.
    {"losing_streak": 4, "trades_today": 9, "size_up_after_loss": True}.
    Returns a note only. It never alters the direction of an alert.
    """
    if not behavior:
        return {"caution": False, "notes": []}
    notes: List[str] = []
    if int(_f(behavior.get("losing_streak"))) >= 3:
        notes.append(f"You are on a {int(_f(behavior.get('losing_streak')))}-trade losing streak. Consider smaller size.")
    if int(_f(behavior.get("trades_today"))) >= 8:
        notes.append("You have already placed many trades today. Check you are not forcing entries.")
    if behavior.get("size_up_after_loss"):
        notes.append("Your history shows sizing up after losses. Keep size the same.")
    return {"caution": bool(notes), "notes": notes}


# ---------------------------------------------------------------------------
# Combine
# ---------------------------------------------------------------------------

def evaluate(symbol: str, bars: Sequence[Dict[str, Any]], opt: Optional[Dict[str, Any]] = None,
             call_volume: Optional[float] = None, put_volume: Optional[float] = None,
             behavior: Optional[Dict[str, Any]] = None, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = {**DEFAULTS, **(config or {})}
    pillars = {
        "options_flow": options_pillar(opt, call_volume, put_volume),
        "price_structure": price_pillar(bars),
        "volume_flow": volume_pillar(bars),
    }
    floor = float(cfg["min_pillar_strength"])
    votes = {k: p["direction"] for k, p in pillars.items()
             if p["available"] and p["direction"] != NEUTRAL and p["strength"] >= floor}

    longs = [k for k, d in votes.items() if d == LONG]
    shorts = [k for k, d in votes.items() if d == SHORT]
    min_agree = int(cfg["min_agree"])

    direction, agreeing = NEUTRAL, []
    if longs and not shorts and len(longs) >= min_agree:
        direction, agreeing = LONG, longs
    elif shorts and not longs and len(shorts) >= min_agree:
        direction, agreeing = SHORT, shorts

    fired = direction != NEUTRAL
    tier = None
    if fired:
        tier = "STRONG" if len(agreeing) == 3 else "STANDARD"
    strength = round(sum(pillars[k]["strength"] for k in agreeing) / len(agreeing), 1) if fired else 0.0

    return {
        "symbol": symbol,
        "fired": fired,
        "direction": direction,
        "tier": tier,
        "pillars_agreeing": len(agreeing),
        "agreeing": agreeing,
        "strength": strength,
        "pillars": pillars,
        "guardrail": behavior_guardrail(behavior),
        "min_agree": min_agree,
    }


def replay_bars(bars: Sequence[Dict[str, Any]], config: Optional[Dict[str, Any]] = None,
                horizons: Sequence[int] = (1, 3, 5, 10)) -> Dict[str, Any]:
    """
    Walk daily bars and score every alert the PRICE and VOLUME pillars would
    have raised (options flow is unavailable historically, so min_agree is
    capped at 2). Measures the forward close-to-close move in the alert's
    direction. One alert per cooldown window.
    """
    cfg = {**DEFAULTS, **(config or {})}
    cfg["min_agree"] = min(int(cfg["min_agree"]), 2)
    cooldown = int(cfg["cooldown_bars"])
    alerts: List[Dict[str, Any]] = []
    next_ok = 0
    for i in range(MIN_BARS, len(bars)):
        if i < next_ok:
            continue
        res = evaluate("", bars[: i + 1], config=cfg)
        if not res["fired"]:
            continue
        sign = 1 if res["direction"] == LONG else -1
        entry = _f(bars[i].get("c"))
        if entry <= 0:
            continue
        fwd = {}
        for h in horizons:
            if i + h < len(bars):
                fwd[h] = round(sign * (_f(bars[i + h].get("c")) / entry - 1.0) * 100.0, 3)
        alerts.append({"index": i, "direction": res["direction"], "forward_pct": fwd})
        next_ok = i + cooldown

    summary: Dict[str, Any] = {"alerts": len(alerts), "by_horizon": {}}
    for h in horizons:
        vals = [a["forward_pct"][h] for a in alerts if h in a["forward_pct"]]
        if vals:
            summary["by_horizon"][h] = {
                "n": len(vals),
                "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals), 3),
                "avg_move_pct": round(sum(vals) / len(vals), 3),
            }
    return {"summary": summary, "alerts": alerts}


class AlertGate:
    """Per-symbol de-dup: one alert per (symbol, direction) until the cooldown passes or direction flips."""

    def __init__(self, cooldown_seconds: float = 6 * 3600):
        self.cooldown = cooldown_seconds
        self._last: Dict[str, Any] = {}

    def allow(self, symbol: str, direction: str, now: float) -> bool:
        prev = self._last.get(symbol)
        if prev and prev[0] == direction and now - prev[1] < self.cooldown:
            return False
        self._last[symbol] = (direction, now)
        return True
