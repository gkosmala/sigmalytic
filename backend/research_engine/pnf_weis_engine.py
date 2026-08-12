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
from backend.research_engine.point_figure_target_engine import PointFigureTargetEngine


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

    def detect_climax(self, column: PnFColumn, multiplier: float = 2.0) -> Dict[str, Any]:
        """
        Mirrors RenkoWeisWaveEngine.detect_climax() -- the "Climax
        Variant" from the shared research, adapted honestly for PnF's
        genuinely different structure: unlike Renko bricks, a PnF
        column doesn't have discrete, individually-tracked box
        boundaries (a column can extend by more than one box in a
        single price step, and the underlying state machine -- already
        empirically validated against real reference data -- was
        deliberately left untouched here rather than risk it). So this
        checks each CONTRIBUTING BAR's volume within the column,
        rather than each individual box, against the running average
        of the other contributing bars in that same column.
        """
        if len(column.bar_volumes) < 3:
            return {"detected": False, "reason": "Needs at least 3 contributing bars in the current column to assess."}

        baseline_bars = column.bar_volumes[:-1]
        final_bar_volume = column.bar_volumes[-1]
        running_avg = sum(baseline_bars) / len(baseline_bars)

        if running_avg <= 0:
            return {"detected": False, "reason": "Baseline volume unavailable."}

        ratio = final_bar_volume / running_avg
        detected = ratio >= multiplier

        return {
            "detected": detected,
            "final_bar_volume": round(final_bar_volume, 0),
            "running_avg_volume": round(running_avg, 0),
            "climax_ratio": round(ratio, 2),
            "reading": (
                f"Climax bar detected: the most recent contributing bar in this column carried "
                f"{ratio:.1f}x the volume of the {len(baseline_bars)} bars before it "
                f"({final_bar_volume:,.0f} vs. a {running_avg:,.0f} running average) -- a sudden, "
                f"concentrated effort spike, signaling an immediate structural roadblock."
                if detected else
                f"No climax bar -- the most recent contributing bar's volume ({final_bar_volume:,.0f}) "
                f"is in line with the column's own running average ({running_avg:,.0f})."
            ),
        }

    def identify_current_range(self, columns: List[PnFColumn], max_lookback: int = 30) -> Dict[str, Any]:
        """
        Identifies the genuine, currently-relevant consolidation range
        by working backward from the most recent column, expanding the
        range while prior columns' own high/low stay within (or
        overlap) it -- stopping once a prior column falls entirely
        outside the accumulated range, since that signals the edge of
        the current base rather than part of it. Capped at
        max_lookback columns as a sanity bound.
        """
        if not columns:
            return {"available": False, "reason": "No columns detected yet."}

        range_high = columns[-1].high
        range_low = columns[-1].low
        column_count = 1

        for col in reversed(columns[:-1]):
            if column_count >= max_lookback:
                break
            # A column entirely outside the current accumulated range
            # marks the edge of this base -- stop expanding.
            if col.high < range_low or col.low > range_high:
                break
            range_high = max(range_high, col.high)
            range_low = min(range_low, col.low)
            column_count += 1

        return {
            "available": True,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "column_count": column_count,
        }

    def count_guide_projection(self, columns: List[PnFColumn], reversal_boxes: int = 3) -> Dict[str, Any]:
        """
        The Wyckoff Count Guide, per the shared research: the
        horizontal width of a consolidation (the "Cause") sets the
        expected vertical size of the subsequent move (the "Effect").
        Revives the correct, existing math from
        point_figure_target_engine.py (found dead/unused earlier
        tonight) -- combined with identify_current_range() above to
        genuinely determine the relevant range width from real column
        data, rather than assuming an arbitrary lookback.
        """
        range_info = self.identify_current_range(columns)
        if not range_info.get("available"):
            return {"available": False, "reason": range_info.get("reason", "No range available.")}

        box_size = columns[-1].box_size
        range_high = range_info["range_high"]
        range_low = range_info["range_low"]
        horizontal_count = max(1, round((range_high - range_low) / box_size)) if box_size > 0 else 1

        target_engine = PointFigureTargetEngine()
        up_targets = target_engine.calculate_targets(
            base_price=range_high, horizontal_count=horizontal_count,
            box_size=box_size, reversal=reversal_boxes,
        )
        down_targets = target_engine.calculate_targets(
            base_price=-range_low, horizontal_count=horizontal_count,
            box_size=box_size, reversal=reversal_boxes,
        )
        # down_targets was computed on negated prices to reuse the same
        # (always-additive) formula for a downside projection -- negate back.
        down_conservative = -down_targets["conservative_target"]
        down_aggressive = -down_targets["aggressive_target"]

        return {
            "available": True,
            "range_high": range_high,
            "range_low": range_low,
            "range_column_count": range_info["column_count"],
            "box_size": box_size,
            "horizontal_count": horizontal_count,
            "cause": up_targets["cause"],
            "upside_conservative_target": up_targets["conservative_target"],
            "upside_aggressive_target": up_targets["aggressive_target"],
            "downside_conservative_target": round(down_conservative, 4),
            "downside_aggressive_target": round(down_aggressive, 4),
        }

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
                "climax": self.detect_climax(current),
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
            "climax": self.detect_climax(current),
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
