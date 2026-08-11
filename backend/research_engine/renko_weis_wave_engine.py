# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/research_engine/renko_weis_wave_engine.py
----------------------------------------------------
Second piece of the new, parallel "pure Weis" engine: wires
PointInTimeRenkoGenerator (non-repainting brick generation) into
WeisWaveAccumulator (groups same-direction brick runs into waves,
accumulating price progress and volume per wave) -- both built or
revived this session, per David Weis's own original approach of
mapping Weis Wave Volume onto Renko structure rather than time bars.

WeisWaveAccumulator was found as dead, unwired code during this
session's investigation, but its wave-grouping logic was verified
correct and is reused here unmodified rather than rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from backend.research_engine.point_in_time_renko_generator import (
    PointInTimeRenkoGenerator,
    RenkoBrick,
)
from backend.research_engine.weis_wave_accumulator import WeisWaveAccumulator


@dataclass
class RenkoWeisWave:
    direction: int  # 1 for up, -1 for down
    brick_count: int
    price_progress: float
    cumulative_volume: float
    start_index: int  # bar index of the first brick in this wave
    end_index: int  # bar index of the last brick in this wave

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RenkoWeisWaveEngine:
    """
    Produces Weis Waves built on non-repainting Renko brick structure,
    genuinely separate from (not a replacement for) the existing,
    validated time-bar-based WeisVerdictEngine.
    """

    def __init__(self, renko_generator: PointInTimeRenkoGenerator = None):
        self.renko_generator = renko_generator or PointInTimeRenkoGenerator()
        self.accumulator = WeisWaveAccumulator()

    def build_waves(self, bars: List[Dict[str, Any]]) -> List[RenkoWeisWave]:
        bricks = self.renko_generator.generate(bars)
        if not bricks:
            return []

        # WeisWaveAccumulator expects plain dicts with direction/open/
        # close/volume -- converting RenkoBrick objects to that shape
        # without modifying the accumulator's own, already-verified
        # logic.
        brick_dicts = [
            {
                "index": b.index,
                "direction": b.direction,
                "open": b.open,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bricks
        ]

        raw_waves = self.accumulator.build_waves(brick_dicts)

        # The accumulator's own output doesn't track which bar indices
        # a wave actually spans (needed for anything downstream that
        # wants to know "when" a wave happened) -- recovering that by
        # re-walking the same brick_dicts alongside raw_waves, since
        # both were built from the identical, ordered brick sequence.
        waves: List[RenkoWeisWave] = []
        brick_cursor = 0
        for w in raw_waves:
            span = brick_dicts[brick_cursor: brick_cursor + w["brick_count"]]
            start_index = span[0]["index"] if span else None
            end_index = span[-1]["index"] if span else None
            waves.append(RenkoWeisWave(
                direction=w["direction"],
                brick_count=w["brick_count"],
                price_progress=w["price_progress"],
                cumulative_volume=w["cumulative_volume"],
                start_index=start_index,
                end_index=end_index,
            ))
            brick_cursor += w["brick_count"]

        return waves
