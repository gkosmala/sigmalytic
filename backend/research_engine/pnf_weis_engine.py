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

    def identify_current_range(self, columns: List[PnFColumn], max_lookback: int = 30,
                                 max_range_pct: float = 0.20) -> Dict[str, Any]:
        """
        Identifies the genuine, currently-relevant consolidation range
        by working backward from the most recent column, expanding the
        range while prior columns' own high/low stay within (or
        overlap) it -- stopping once a prior column falls entirely
        outside the accumulated range, since that signals the edge of
        the current base rather than part of it. Capped at
        max_lookback columns as a sanity bound.

        FIX (2026-08-12): confirmed a genuine, serious bug live in
        production -- consecutive PnF columns structurally overlap by
        design (the reversal rule guarantees a new column's open sits
        within 1 box of the prior column's own extreme), so the
        "entirely outside" stopping criterion above rarely fires
        during a sustained trend. On a full year of real AAPL bars,
        this let the range walk back through nearly the entire
        uptrend, producing a downside target of -172.58 -- a
        mathematically impossible negative price shown live in the
        Price Ladder. Added a second, principled bound: stop expanding
        the moment doing so would push the range width beyond
        max_range_pct of the current reference price. A genuine,
        tradeable consolidation shouldn't span that much of the price
        level; anything wider is a trend, not a base, regardless of
        whether individual columns technically overlap.
        """
        if not columns:
            return {"available": False, "reason": "No columns detected yet."}

        range_high = columns[-1].high
        range_low = columns[-1].low
        reference_price = columns[-1].high  # anchor the % bound to the current, real price level
        max_width = reference_price * max_range_pct
        column_count = 1

        for col in reversed(columns[:-1]):
            if column_count >= max_lookback:
                break
            # A column entirely outside the current accumulated range
            # marks the edge of this base -- stop expanding.
            if col.high < range_low or col.low > range_high:
                break
            candidate_high = max(range_high, col.high)
            candidate_low = min(range_low, col.low)
            # A genuine consolidation shouldn't span more than
            # max_range_pct of the current price -- stop before
            # including a column that would blow past that, even if
            # it technically overlaps.
            if (candidate_high - candidate_low) > max_width:
                break
            range_high = candidate_high
            range_low = candidate_low
            column_count += 1

        return {
            "available": True,
            "range_high": round(range_high, 2),
            "range_low": round(range_low, 2),
            "column_count": column_count,
            # The actual column objects making up the identified range,
            # oldest first -- needed by count_guide_projection() below for
            # genuine horizontal (row-crossing) counting and wall/phase
            # detection. Not previously returned; the caller had to
            # re-derive range membership from range_high/range_low alone.
            #
            # columns[-column_count:] is already chronological
            # (oldest-first) since the source columns list is built in
            # append order by the generator; no reversal needed --
            # _identify_phase_walls() below walks this list forward
            # accumulating "columns_included", so processing
            # oldest-to-newest is what makes the phase/wall staircase
            # count outward from an anchor toward the present, matching
            # Weis's own worked example (walls counted A->B->C->D->E
            # moving forward in time from a base anchor).
            "columns": list(columns[-column_count:]) if column_count <= len(columns) else list(columns),
        }

    @staticmethod
    def _horizontal_count_at_best_row(columns: List["PnFColumn"], range_low: float, range_high: float,
                                        box_size: float) -> Dict[str, Any]:
        """
        FIX (2026-08-17): genuine horizontal count, per source
        methodology (Weis, "Trades About to Happen," Ch. 11 -- Wyckoff
        before him): "one counts the number of boxes ... plotted along
        a LINE OF CONGESTION" -- i.e. how many columns physically cross
        a chosen horizontal price row, not the vertical height of the
        range divided by box size (the prior implementation's actual
        bug: that measures the range's own vertical extent, a
        different and generally much larger quantity that scales with
        how tall the base is rather than how many columns sit side by
        side within it).

        Classic technique picks the row within the base that the most
        columns cross (the most "congested" line) and counts across
        that -- mirrors Weis choosing "the 154 line" / "the 164 line"
        in his own worked examples, which were visibly the most
        heavily built-up rows in each base, not an arbitrary boundary.
        """
        if box_size <= 0 or not columns:
            return {"count": 1, "row_price": range_low}

        best_row = range_low
        best_count = 0
        row = range_low
        # Step row-by-row (one box at a time) through the range and count
        # how many columns' [low, high] span includes that row.
        while row <= range_high + (box_size / 2):
            crossing = sum(1 for c in columns if c.low <= row <= c.high)
            if crossing > best_count:
                best_count = crossing
                best_row = row
            row += box_size

        return {"count": max(1, best_count), "row_price": round(best_row, 4)}

    @staticmethod
    def _identify_phase_walls(columns: List["PnFColumn"], box_size: float, direction: str) -> List[Dict[str, Any]]:
        """
        FIX (2026-08-17): staged, event-anchored counting, per source
        methodology (Weis, Ch. 11): rather than one count across the
        full width of a base, break the count into phases anchored at
        internal "walls" -- points where price visibly accelerated
        away from the congestion before the base continued. Weis's own
        worked example (FXB, Figure 11.1) shows four such phases
        (walls "B" through "E") built outward from a base anchor
        ("A"), each producing its own, progressively larger target,
        with the nearest phase read as the conservative case and the
        widest (full-range) phase as the aggressive case.

        Weis describes wall placement as visual judgment ("with
        practice, one learns how to find the right balance"), not a
        formula. This is an explicit, documented engineering
        interpretation of that description, not a transcription of a
        rule the book states: a column is treated as a wall when its
        own box count is notably larger (>= 1.5x, min 2 boxes) than
        the running average box count of the columns already included
        -- i.e. a genuine local acceleration relative to the base
        built so far, in the direction being measured (X columns for
        upside phases, O columns for downside phases).

        direction: "up" or "down" -- which column type marks an
        acceleration relevant to that side's projection.
        """
        target_type = "X" if direction == "up" else "O"
        walls: List[Dict[str, Any]] = []
        seen_boxes: List[int] = []
        cumulative_cols = 0

        for col in columns:
            cumulative_cols += 1
            if col.column_type != target_type:
                continue
            avg_so_far = (sum(seen_boxes) / len(seen_boxes)) if seen_boxes else col.boxes
            is_wall = col.boxes >= max(2, avg_so_far * 1.5)
            seen_boxes.append(col.boxes)
            if is_wall:
                extreme = col.high if direction == "up" else col.low
                walls.append({
                    "extreme_price": extreme,
                    "columns_included": cumulative_cols,
                })

        return walls

    def count_guide_projection(self, columns: List[PnFColumn], reversal_boxes: int = 3) -> Dict[str, Any]:
        """
        The Wyckoff Count Guide, per the shared research: the
        horizontal width of a consolidation (the "Cause") sets the
        expected vertical size of the subsequent move (the "Effect").

        FIX (2026-08-17): full rework against the primary source
        (Weis, "Trades About to Happen," Ch. 11), replacing the prior
        single full-range x1/x3 calculation with four corrected
        pieces, each independently traceable to that chapter:

        1. Horizontal count now genuinely counts columns crossing a
           congestion row (_horizontal_count_at_best_row), not the
           range's own vertical height in boxes.
        2. Anchor direction corrected: an up-count is anchored from
           the range LOW and projects upward; a down-count is anchored
           from the range HIGH and projects downward (the prior code
           had this backward on both sides).
        3. The multiplier is now the real reversal unit
           (reversal_boxes x box_size) applied consistently, not an
           arbitrary x1 for "conservative" vs. blind x3 for
           "aggressive" -- that blind tripling of the full range was
           the direct mechanism behind the negative-target bug this
           replaces.
        4. Conservative / aggressive targets now come from genuine
           staged phases (_identify_phase_walls) -- the nearest wall's
           phase for conservative, the full range's own phase for
           aggressive -- rather than one number multiplied by 1 and
           the same number multiplied by 3.

           NOTE, added after direct testing against a synthetic
           long-duration/narrow-range base: a genuine horizontal count
           (columns crossing a row) reflects how long a level was
           tested over TIME, which is legitimately independent of the
           range's own vertical height -- a long, heavily-chopped but
           narrow base can still produce a horizontal_count large
           enough that count x reversal_unit exceeds the range itself,
           which can still drive a downside target to or below zero.
           This is a real, structurally possible case, not an
           artifact -- so rather than reinstating a blind clamp (the
           exact silent-failure pattern this rework exists to remove),
           an invalid (<=0) target is now OMITTED from the returned
           dict entirely, letting the caller's own existing, intentional
           fallback (shared/engine.py's get_key_levels(), which already
           falls back to the synthetic formula when a key is absent)
           take over -- visibly, not silently.
        """
        range_info = self.identify_current_range(columns)
        if not range_info.get("available"):
            return {"available": False, "reason": range_info.get("reason", "No range available.")}

        box_size = columns[-1].box_size
        range_high = range_info["range_high"]
        range_low = range_info["range_low"]
        range_columns = range_info["columns"]
        reversal_unit = reversal_boxes * box_size if box_size > 0 else 0

        row_info = self._horizontal_count_at_best_row(range_columns, range_low, range_high, box_size)
        full_range_count = row_info["count"]

        # --- Upside: anchored at range_low, phases built from X columns ---
        up_walls = self._identify_phase_walls(range_columns, box_size, direction="up")
        up_phase_counts = [w["columns_included"] for w in up_walls] or [full_range_count]
        up_conservative_count = min(up_phase_counts)
        up_aggressive_count = max(max(up_phase_counts), full_range_count)
        up_average_count = sum(up_phase_counts) / len(up_phase_counts)

        upside_conservative_target = range_low + (up_conservative_count * reversal_unit)
        upside_aggressive_target = range_low + (up_aggressive_count * reversal_unit)
        upside_average_target = range_low + (up_average_count * reversal_unit)

        # --- Downside: anchored at range_high, phases built from O columns ---
        down_walls = self._identify_phase_walls(range_columns, box_size, direction="down")
        down_phase_counts = [w["columns_included"] for w in down_walls] or [full_range_count]
        down_conservative_count = min(down_phase_counts)
        down_aggressive_count = max(max(down_phase_counts), full_range_count)
        down_average_count = sum(down_phase_counts) / len(down_phase_counts)

        downside_conservative_target = range_high - (down_conservative_count * reversal_unit)
        downside_aggressive_target = range_high - (down_aggressive_count * reversal_unit)
        downside_average_target = range_high - (down_average_count * reversal_unit)

        result: Dict[str, Any] = {
            "available": True,
            "range_high": range_high,
            "range_low": range_low,
            "range_column_count": range_info["column_count"],
            "box_size": box_size,
            "count_row_price": row_info["row_price"],
            "horizontal_count": full_range_count,
            "reversal_unit": round(reversal_unit, 4),
            "upside_phase_count": len(up_phase_counts),
            "downside_phase_count": len(down_phase_counts),
        }

        # Only include a target if it's a structurally valid (positive)
        # price. An invalid one is OMITTED, not clamped or defaulted here
        # -- see the docstring note above on why a blind floor was
        # rejected after testing. Omission lets the caller's own,
        # already-designed fallback take over instead of this function
        # silently fabricating a number.
        invalid_targets = []
        for key, value in [
            ("upside_conservative_target", upside_conservative_target),
            ("upside_aggressive_target", upside_aggressive_target),
            ("upside_average_target", upside_average_target),
            ("downside_conservative_target", downside_conservative_target),
            ("downside_aggressive_target", downside_aggressive_target),
            ("downside_average_target", downside_average_target),
        ]:
            if value > 0:
                result[key] = round(value, 4)
            else:
                invalid_targets.append(key)

        if invalid_targets:
            result["invalid_targets_omitted"] = invalid_targets

        return result

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
