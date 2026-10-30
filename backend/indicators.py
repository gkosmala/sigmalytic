# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/indicators.py
---------------------
Standard technical indicators computed from bars the platform already has. Pure functions, no data requests.

RSI uses Wilder's smoothing, the definition charting platforms show by default: the first average gain and loss
are simple averages of the first `period` changes, then each later average is (previous * (period - 1) + current)
/ period. Values settle once there are several times `period` bars; the nightly scan supplies about 290.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence


def rsi_wilder(closes: Sequence[float], period: int = 14) -> Optional[float]:
    """Latest RSI(period) of the closes (oldest first), rounded to 2 decimals. None with fewer than period + 1
    usable closes."""
    vals: List[float] = []
    for c in closes:
        try:
            x = float(c)
        except (TypeError, ValueError):
            continue
        if not math.isnan(x) and not math.isinf(x):
            vals.append(x)
    if len(vals) < period + 1:
        return None
    changes = [b - a for a, b in zip(vals, vals[1:])]
    gain = sum(max(d, 0.0) for d in changes[:period]) / period
    loss = sum(max(-d, 0.0) for d in changes[:period]) / period
    for d in changes[period:]:
        gain = (gain * (period - 1) + max(d, 0.0)) / period
        loss = (loss * (period - 1) + max(-d, 0.0)) / period
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return round(100.0 - 100.0 / (1.0 + gain / loss), 2)


def rsi_series(closes: Sequence[float], period: int = 14) -> List[Optional[float]]:
    """RSI(period) for every bar (Wilder), aligned with `closes`; None until there are period + 1 closes. The last
    value equals rsi_wilder(closes, period)."""
    vals = [float(c) for c in closes]
    out: List[Optional[float]] = [None] * len(vals)
    if len(vals) < period + 1:
        return out
    changes = [b - a for a, b in zip(vals, vals[1:])]
    gain = sum(max(d, 0.0) for d in changes[:period]) / period
    loss = sum(max(-d, 0.0) for d in changes[:period]) / period

    def value(g: float, l: float) -> float:
        if l == 0:
            return 100.0 if g > 0 else 50.0
        return round(100.0 - 100.0 / (1.0 + g / l), 2)

    out[period] = value(gain, loss)
    for i, d in enumerate(changes[period:], start=period + 1):
        gain = (gain * (period - 1) + max(d, 0.0)) / period
        loss = (loss * (period - 1) + max(-d, 0.0)) / period
        out[i] = value(gain, loss)
    return out


def sma(closes: Sequence[float], n: int) -> Optional[float]:
    vals = [float(c) for c in closes]
    return round(sum(vals[-n:]) / n, 2) if len(vals) >= n else None
