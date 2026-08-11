# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/research_engine/point_in_time_pnf_generator.py
----------------------------------------------------------
Fourth piece of the new, parallel "pure Weis" engine: a point-in-time
(non-repainting) Point-and-Figure column generator, mirroring the
Renko generator's fix applied to PnF's genuinely different
construction (close-only price series, box-size + 3-box reversal
state machine, rather than a single brick-size flip rule).

Why this exists: the live, existing PnF overlay
(campaign_full_enrichment_api.py's _pnf()) computes box_size once
from present-day volatility (1% of latest close, or half the average
day-to-day move over the last 20 days, whichever is bigger), then
applies that single box_size across the entire ~252-day historical
column reconstruction. Same repainting issue confirmed for Renko
applies here: re-running this after a volatility shift reconstructs a
different historical column structure from the same, unchanged past
closes.

This generator recalculates box_size at every step using only closes
up to and including that step -- never future closes relative to that
step. Deliberately keeps the existing 3-box reversal rule and the
same price-tiered rounding unit unchanged, since those are the
established convention, not something under discussion.

Unlike Renko bricks (which WeisWaveAccumulator groups into waves), a
PnF column is already a complete, same-direction run -- it IS the
wave-equivalent unit directly, so no separate grouping step is
needed. Volume accumulation per column is new here: the existing
overlay never tracked it at all, but it's required for the
"cumulative Weis Wave volume inside a PnF column" mapping this
engine is being built toward.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class PnFColumn:
    column_type: str  # "X" or "O"
    high: float
    low: float
    boxes: int
    box_size: float  # the box size actually in effect when this column formed
    volume: float
    start_index: int
    end_index: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PointInTimePnFGenerator:
    def __init__(
        self,
        avg_move_lookback: int = 20,
        reversal_boxes: int = 3,
    ):
        self.avg_move_lookback = avg_move_lookback
        self.reversal_boxes = reversal_boxes

    def _point_in_time_box_size(self, closes_so_far: List[float]) -> Optional[float]:
        """
        Mirrors _pnf()'s box_size formula exactly (max(1% of latest
        close, 0.5x the average absolute day-to-day move over the
        last 20 days, 0.01), rounded to the same price-tiered unit),
        just recalculated fresh at each step from closes_so_far only
        -- the caller is responsible for never passing closes beyond
        the current step.
        """
        if len(closes_so_far) < 2:
            return None

        latest_close = closes_so_far[-1]
        if latest_close is None or latest_close <= 0:
            return None

        window = closes_so_far[-(self.avg_move_lookback + 1):]
        moves = [abs(window[i] - window[i - 1]) for i in range(1, len(window)) if window[i - 1] > 0 and window[i] > 0]

        avg_abs_move = sum(moves) / len(moves) if moves else latest_close * 0.01
        percent_box = latest_close * 0.01
        raw_box_size = max(percent_box, avg_abs_move * 0.50, 0.01)

        if latest_close >= 100:
            rounding_unit = 0.25
        elif latest_close >= 25:
            rounding_unit = 0.10
        elif latest_close >= 5:
            rounding_unit = 0.05
        else:
            rounding_unit = 0.01

        return max(round(raw_box_size / rounding_unit) * rounding_unit, rounding_unit)

    def generate(self, bars: List[Dict[str, Any]]) -> List[PnFColumn]:
        """
        bars: list of dicts with close/c and volume/v (high/low/open
        are not used, matching the existing overlay's close-only
        construction).
        """
        closes: List[float] = []
        volumes: List[float] = []
        for bar in bars or []:
            if not isinstance(bar, dict):
                continue
            close = _f(bar.get("c", bar.get("close")))
            if close is None or close <= 0:
                continue
            closes.append(close)
            volumes.append(_f(bar.get("v", bar.get("volume")), 0.0) or 0.0)

        if len(closes) < 20:
            return []

        columns: List[PnFColumn] = []
        base = closes[0]
        current_type: Optional[str] = None
        col_high = base
        col_low = base
        col_start_index = 0
        pending_volume = volumes[0]

        for i in range(1, len(closes)):
            price = closes[i]
            pending_volume += volumes[i]
            box_size = self._point_in_time_box_size(closes[: i + 1])
            if box_size is None or box_size <= 0:
                continue
            reversal_amount = box_size * self.reversal_boxes

            if current_type is None:
                if price >= base + box_size:
                    current_type = "X"
                    col_low, col_high = base, price
                    col_start_index = i
                    pending_volume = 0.0
                elif price <= base - box_size:
                    current_type = "O"
                    col_high, col_low = base, price
                    col_start_index = i
                    pending_volume = 0.0
                continue

            if current_type == "X":
                if price >= col_high + box_size:
                    col_high = price
                elif price <= col_high - reversal_amount:
                    boxes = max(1, int(round((col_high - col_low) / box_size)))
                    columns.append(PnFColumn(
                        column_type="X", high=col_high, low=col_low, boxes=boxes,
                        box_size=box_size, volume=pending_volume,
                        start_index=col_start_index, end_index=i,
                    ))
                    current_type = "O"
                    col_high = col_high - box_size
                    col_low = price
                    col_start_index = i
                    pending_volume = 0.0
            else:
                if price <= col_low - box_size:
                    col_low = price
                elif price >= col_low + reversal_amount:
                    boxes = max(1, int(round((col_high - col_low) / box_size)))
                    columns.append(PnFColumn(
                        column_type="O", high=col_high, low=col_low, boxes=boxes,
                        box_size=box_size, volume=pending_volume,
                        start_index=col_start_index, end_index=i,
                    ))
                    current_type = "X"
                    col_low = col_low + box_size
                    col_high = price
                    col_start_index = i
                    pending_volume = 0.0

        return columns


def _f(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
