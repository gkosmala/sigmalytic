# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/research_engine/pnf_weis_engine.py
----------------------------------------------------
Fifth piece of the new, parallel "pure Weis" engine: SOT/exhaustion/
confirmation scoring for Point-and-Figure columns, mirroring
RenkoWeisWaveEngine's exact structure and thresholds -- the same
principle applied to PnF's own construction instead of Renko's.

A PnF column is already a complete, same-direction run (confirmed in
PointInTimePnFGenerator's own docstring) -- it IS the wave-equivalent
unit directly, so unlike Renko bricks there's no separate grouping
step needed here; this engine operates directly on the columns
PointInTimePnFGenerator produces.

The underlying generator was empirically validated against a real,
trusted PnF reference dataset and confirmed correct (46/46 real,
complete columns matched exactly) before this scoring layer was
built on top of it.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

from backend.research_engine.point_in_time_pnf_generator import (
    PointInTimePnFGenerator,
    PnFColumn,
)


@dataclass
class PnFWeisVerdict:
    symbol: str
    weis_score: float
    verdict: str
    sot_downcolumns: float
    volume_exhaustion: float
    effort_without_reward: float
    upcolumn_confirmation: float

    weis_score_bearish: float
    verdict_bearish: str
    sot_upcolumns: float
    buying_exhaustion: float
    buying_effort_without_reward: float
    downcolumn_confirmation: float

    column_count: int
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PnFWeisEngine:
    """
    Mirrors RenkoWeisWaveEngine's scoring thresholds exactly (SOT
    requires 3 same-type columns with strictly decreasing box counts;
    exhaustion requires SOT confirmed AND the final column's volume
    under 60% of the prior same-type column's; confirmation requires
    the current column's volume exceeding 1.25x the combined volume
    of the last two opposite-type columns) -- applied to PnF columns
    ("X"=up, "O"=down) instead of Renko waves.
    """

    def __init__(self, pnf_generator: PointInTimePnFGenerator = None):
        self.pnf_generator = pnf_generator or PointInTimePnFGenerator()

    def build_columns(self, bars: List[Dict[str, Any]]) -> List[PnFColumn]:
        return self.pnf_generator.generate(bars)

    def shortening_of_thrust_score(self, columns: List[PnFColumn]) -> float:
        down = [c for c in columns if c.column_type == "O"]
        if len(down) < 3:
            return 0.0
        c1, c2, c3 = down[-3:]
        if c3.boxes < c2.boxes < c1.boxes:
            return 100.0
        return 0.0

    def shortening_of_thrust_score_bearish(self, columns: List[PnFColumn]) -> float:
        up = [c for c in columns if c.column_type == "X"]
        if len(up) < 3:
            return 0.0
        c1, c2, c3 = up[-3:]
        if c3.boxes < c2.boxes < c1.boxes:
            return 100.0
        return 0.0

    def volume_exhaustion_score(self, columns: List[PnFColumn], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        down = [c for c in columns if c.column_type == "O"]
        if len(down) < 2:
            return 0.0
        c2, c3 = down[-2], down[-1]
        if c3.volume < (0.60 * c2.volume):
            return 100.0
        return 0.0

    def buying_exhaustion_score(self, columns: List[PnFColumn], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        up = [c for c in columns if c.column_type == "X"]
        if len(up) < 2:
            return 0.0
        c2, c3 = up[-2], up[-1]
        if c3.volume < (0.60 * c2.volume):
            return 100.0
        return 0.0

    def effort_without_reward_score(self, columns: List[PnFColumn], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        down = [c for c in columns if c.column_type == "O"]
        if len(down) < 2:
            return 0.0
        c2, c3 = down[-2], down[-1]
        if c3.volume >= c2.volume:
            return 100.0
        return 0.0

    def buying_effort_without_reward_score(self, columns: List[PnFColumn], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        up = [c for c in columns if c.column_type == "X"]
        if len(up) < 2:
            return 0.0
        c2, c3 = up[-2], up[-1]
        if c3.volume >= c2.volume:
            return 100.0
        return 0.0

    def upcolumn_confirmation_score(self, columns: List[PnFColumn]) -> float:
        if not columns:
            return 0.0
        down = [c for c in columns if c.column_type == "O"]
        if len(down) < 2:
            return 0.0
        last_two = down[-1].volume + down[-2].volume
        current = columns[-1]
        if current.column_type == "X" and current.volume > (1.25 * last_two):
            return 100.0
        return 0.0

    def downcolumn_confirmation_score(self, columns: List[PnFColumn]) -> float:
        if not columns:
            return 0.0
        up = [c for c in columns if c.column_type == "X"]
        if len(up) < 2:
            return 0.0
        last_two = up[-1].volume + up[-2].volume
        current = columns[-1]
        if current.column_type == "O" and current.volume > (1.25 * last_two):
            return 100.0
        return 0.0

    def current_column_reading(self, columns: List[PnFColumn]) -> Dict[str, Any]:
        """
        Mirrors RenkoWeisWaveEngine.current_wave_reading() -- the
        always-informative reading (Effort vs. Result, plus
        structural pace via avg_volume_per_box) independent of
        whether the full, strict SOT/exhaustion/confirmation gate has
        fired, since that gate is genuinely rare by design.
        """
        if not columns:
            return {"available": False, "reason": "No columns detected yet."}

        current = columns[-1]
        current_avg_vol_per_box = (current.volume / current.boxes) if current.boxes > 0 else 0.0
        same_type_prior = [c for c in columns[:-1] if c.column_type == current.column_type]

        direction_label = "UP" if current.column_type == "X" else "DOWN"

        if not same_type_prior:
            return {
                "available": True,
                "direction": direction_label,
                "current_column_volume": round(current.volume, 0),
                "current_column_boxes": current.boxes,
                "prior_same_type_volume": None,
                "effort_vs_result": "INSUFFICIENT_HISTORY",
                "avg_volume_per_box": round(current_avg_vol_per_box, 0),
                "relative_pace_ratio": None,
                "market_condition": "INSUFFICIENT_HISTORY",
                "reading": (
                    f"Current column is {direction_label} ({current.boxes} boxes, "
                    f"{current.volume:,.0f} volume) -- no prior same-type column yet "
                    f"to compare effort against."
                ),
                "pace_reading": "No prior same-type column yet to compare structural pace against.",
            }

        prior = same_type_prior[-1]
        if current.volume < prior.volume:
            effort_vs_result = "EXHAUSTING"
            reading_verb = "less volume than the prior column -- effort is fading"
        elif current.volume > prior.volume:
            effort_vs_result = "BUILDING"
            reading_verb = "more volume than the prior column -- fresh participation, trend building"
        else:
            effort_vs_result = "UNCHANGED"
            reading_verb = "about the same volume as the prior column"

        prior_avg_vol_per_box = (prior.volume / prior.boxes) if prior.boxes > 0 else 0.0
        pace_ratio = None
        if prior_avg_vol_per_box > 0:
            pace_ratio = current_avg_vol_per_box / prior_avg_vol_per_box

        if pace_ratio is None:
            market_condition = "INSUFFICIENT_HISTORY"
            pace_reading = "Prior column's per-box volume unavailable -- cannot assess structural pace."
        elif pace_ratio >= 1.40:
            market_condition = "ABSORPTION"
            pace_reading = (
                f"Structural pace is slowing ({pace_ratio:.1f}x more volume per box than the prior "
                f"same-type column) -- heavy absorption forming, a possible roadblock ahead."
            )
        elif pace_ratio <= 0.74:
            market_condition = "EASE_OF_MOVEMENT"
            pace_reading = (
                f"Structural pace is fast ({pace_ratio:.2f}x the volume per box of the prior "
                f"same-type column) -- little resistance, price moving with ease."
            )
        else:
            market_condition = "SYMMETRICAL"
            pace_reading = (
                f"Structural pace is steady ({pace_ratio:.1f}x the prior same-type column's "
                f"volume per box) -- effort matches historical norms."
            )

        return {
            "available": True,
            "direction": direction_label,
            "current_column_volume": round(current.volume, 0),
            "current_column_boxes": current.boxes,
            "prior_same_type_volume": round(prior.volume, 0),
            "effort_vs_result": effort_vs_result,
            "avg_volume_per_box": round(current_avg_vol_per_box, 0),
            "relative_pace_ratio": round(pace_ratio, 3) if pace_ratio is not None else None,
            "market_condition": market_condition,
            "reading": (
                f"Current column is {direction_label} ({current.boxes} boxes, "
                f"{current.volume:,.0f} volume) -- printing {reading_verb} ({prior.volume:,.0f})."
            ),
            "pace_reading": pace_reading,
        }

    def evaluate(self, bars: List[Dict[str, Any]], symbol: str = "") -> PnFWeisVerdict:
        columns = self.build_columns(bars)

        sot = self.shortening_of_thrust_score(columns)
        sot_confirmed = sot >= 100
        exhaustion = self.volume_exhaustion_score(columns, sot_confirmed=sot_confirmed)
        effort_without_reward = self.effort_without_reward_score(columns, sot_confirmed=sot_confirmed)
        confirmation = self.upcolumn_confirmation_score(columns)

        score = sot * 0.30 + exhaustion * 0.30 + confirmation * 0.40
        if score >= 90:
            verdict = "PRIMARY_CAMPAIGN_LAUNCH"
        elif score >= 60:
            verdict = "ABSORPTION_WARNING"
        elif score >= 30:
            verdict = "WATCH"
        else:
            verdict = "NO_WEIS_SIGNAL"

        sot_bearish = self.shortening_of_thrust_score_bearish(columns)
        sot_bearish_confirmed = sot_bearish >= 100
        buying_exhaustion = self.buying_exhaustion_score(columns, sot_confirmed=sot_bearish_confirmed)
        buying_effort_without_reward = self.buying_effort_without_reward_score(columns, sot_confirmed=sot_bearish_confirmed)
        downcolumn_confirmation = self.downcolumn_confirmation_score(columns)

        score_bearish = sot_bearish * 0.30 + buying_exhaustion * 0.30 + downcolumn_confirmation * 0.40
        if score_bearish >= 90:
            verdict_bearish = "PRIMARY_DISTRIBUTION_LAUNCH"
        elif score_bearish >= 60:
            verdict_bearish = "SUPPLY_WARNING"
        elif score_bearish >= 30:
            verdict_bearish = "WATCH"
        else:
            verdict_bearish = "NO_WEIS_SIGNAL"

        return PnFWeisVerdict(
            symbol=symbol,
            weis_score=round(score, 2),
            verdict=verdict,
            sot_downcolumns=round(sot, 2),
            volume_exhaustion=round(exhaustion, 2),
            effort_without_reward=round(effort_without_reward, 2),
            upcolumn_confirmation=round(confirmation, 2),
            weis_score_bearish=round(score_bearish, 2),
            verdict_bearish=verdict_bearish,
            sot_upcolumns=round(sot_bearish, 2),
            buying_exhaustion=round(buying_exhaustion, 2),
            buying_effort_without_reward=round(buying_effort_without_reward, 2),
            downcolumn_confirmation=round(downcolumn_confirmation, 2),
            column_count=len(columns),
            explanation=(
                f"[PnF-based] SOT={sot:.1f}, Exhaustion={exhaustion:.1f}, "
                f"Confirmation={confirmation:.1f}, Bearish SOT={sot_bearish:.1f}, "
                f"BuyingExhaustion={buying_exhaustion:.1f}, DowncolumnConfirmation={downcolumn_confirmation:.1f}, "
                f"columns={len(columns)}"
            ),
        )
