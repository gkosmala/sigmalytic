# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/research_engine/point_in_time_renko_generator.py
----------------------------------------------------------
Point-in-time (non-repainting) Renko brick generator -- the
foundational piece of a new, parallel "pure Weis" engine (Weis Wave
Volume mapped onto Renko/PnF structure rather than time bars), per
the user's explicit request.

Why this exists: the live, existing Renko overlay
(campaign_full_enrichment_api.py's _renko_read_only_overlay())
computes a single brick_size from present-day volatility data, then
applies that one brick_size across the entire historical
reconstruction. Confirmed directly against that code: brick_size is
computed once, before the bar loop, and never changes as the loop
walks through history. That means re-running it after a volatility
regime shift reconstructs a genuinely different historical brick
structure from the exact same, unchanged past prices -- "repainting."

This generator eliminates that by recalculating the brick size at
every single step, using only bars up to and including that step
(bars[0:t+1]) -- never bars from the future relative to step t. A
brick formed at index 50 always used the same brick_size whether you
run this generator on 100 bars or 1000 bars, since nothing after
index 50 can influence it.

Deliberately matches the existing overlay's reversal convention
(1-brick reversal -- any opposite-direction move of one full brick
size immediately flips direction) rather than introducing a
different 2-brick convention, since changing that is a separate,
undiscussed decision, not a side effect of fixing repainting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class RenkoBrick:
    index: int  # bar index (into the input bars list) where this brick completed
    direction: int  # 1 for up, -1 for down
    open: float
    close: float
    brick_size: float  # the brick size actually in effect when this brick formed
    volume: float  # volume attributed to this specific brick (see accounting note below)


class PointInTimeRenkoGenerator:
    """
    Volume accounting note: a single bar can complete multiple bricks
    (a large move), and a bar that doesn't complete any brick still
    has volume that genuinely contributed to eventually completing the
    next one. Handled here by carrying a pending_volume accumulator
    forward across non-completing bars, then splitting the bar's own
    volume plus any pending volume evenly across however many bricks
    that bar completes -- daily bars don't carry intrabar tick data,
    so an even split is the most defensible approximation available,
    not a claim of tick-level precision.
    """

    def __init__(
        self,
        atr_period: int = 14,
        atr_lookback_bars: int = 30,
        atr_multiplier: float = 0.5,
        pct_floor: float = 0.005,
        max_bricks_per_bar: int = 60,
    ):
        self.atr_period = atr_period
        self.atr_lookback_bars = atr_lookback_bars
        self.atr_multiplier = atr_multiplier
        self.pct_floor = pct_floor
        self.max_bricks_per_bar = max_bricks_per_bar

    def _point_in_time_brick_size(self, bars_so_far: List[Dict[str, Any]]) -> Optional[float]:
        """
        Computes the brick size using ONLY bars_so_far -- the caller
        is responsible for never passing bars beyond the current step.
        Mirrors the live overlay's formula (max(0.5x ATR(14), 0.5% of
        price)) exactly, just recalculated fresh at each step instead
        of once from the full, present-day series.
        """
        if len(bars_so_far) < 2:
            return None

        window = bars_so_far[-self.atr_lookback_bars:]
        true_ranges: List[float] = []
        prev_close = window[0]["close"]
        for bar in window:
            high, low = bar["high"], bar["low"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            if tr > 0:
                true_ranges.append(tr)
            prev_close = bar["close"]

        current_price = bars_so_far[-1]["close"]
        if current_price is None or current_price <= 0:
            return None

        atr = sum(true_ranges[-self.atr_period:]) / len(true_ranges[-self.atr_period:]) if true_ranges else current_price * 0.01
        atr_brick = atr * self.atr_multiplier
        pct_brick = current_price * self.pct_floor
        return max(atr_brick, pct_brick, 0.0001)

    def generate(self, bars: List[Dict[str, Any]]) -> List[RenkoBrick]:
        """
        bars: list of dicts with open/high/low/close/volume (or o/h/l/c/v).
        Returns bricks in chronological order. No look-ahead: the
        brick_size used to evaluate bar t is computed from bars[0:t+1]
        only.
        """
        cleaned: List[Dict[str, float]] = []
        for bar in bars or []:
            if not isinstance(bar, dict):
                continue
            close = _f(bar.get("c", bar.get("close")))
            if close is None:
                continue
            high = _f(bar.get("h", bar.get("high")), close)
            low = _f(bar.get("l", bar.get("low")), close)
            open_ = _f(bar.get("o", bar.get("open")), close)
            volume = _f(bar.get("v", bar.get("volume")), 0.0) or 0.0
            cleaned.append({"open": open_, "high": high, "low": low, "close": close, "volume": volume})

        if len(cleaned) < 5:
            return []

        bricks: List[RenkoBrick] = []
        last_price = cleaned[0]["close"]
        pending_volume = 0.0

        for idx in range(1, len(cleaned)):
            bars_so_far = cleaned[: idx + 1]
            brick_size = self._point_in_time_brick_size(bars_so_far)
            bar = cleaned[idx]
            close = bar["close"]
            pending_volume += bar["volume"]

            if brick_size is None or brick_size <= 0:
                continue

            guard = 0
            bricks_this_bar: List[Dict[str, Any]] = []
            while abs(close - last_price) >= brick_size and guard < self.max_bricks_per_bar:
                previous = last_price
                if close > last_price:
                    last_price += brick_size
                    direction = 1
                else:
                    last_price -= brick_size
                    direction = -1
                bricks_this_bar.append({
                    "index": idx, "direction": direction,
                    "open": previous, "close": last_price, "brick_size": brick_size,
                })
                guard += 1

            if bricks_this_bar:
                # Split this bar's total contributed volume (its own
                # volume plus anything carried forward from bars that
                # didn't complete a brick) evenly across however many
                # bricks it completed.
                vol_share = pending_volume / len(bricks_this_bar)
                for b in bricks_this_bar:
                    bricks.append(RenkoBrick(
                        index=b["index"], direction=b["direction"],
                        open=b["open"], close=b["close"],
                        brick_size=b["brick_size"], volume=vol_share,
                    ))
                pending_volume = 0.0

        return bricks


def _f(value, default=None):
    try:
        if value is None:
            return default
        x = float(value)
        if pd.isna(x):
            return default
        return x
    except (TypeError, ValueError):
        return default
