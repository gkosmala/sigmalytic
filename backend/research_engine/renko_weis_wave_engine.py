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
    avg_volume_per_brick: float = 0.0  # structural pace: volume required per brick, NOT time-based

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RenkoWeisVerdict:
    symbol: str
    weis_score: float
    verdict: str
    sot_downwaves: float
    volume_exhaustion: float
    effort_without_reward: float
    upwave_confirmation: float

    weis_score_bearish: float
    verdict_bearish: str
    sot_upwaves: float
    buying_exhaustion: float
    buying_effort_without_reward: float
    downwave_confirmation: float

    wave_count: int
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RenkoWeisWaveEngine:
    """
    Produces Weis Waves built on non-repainting Renko brick structure,
    genuinely separate from (not a replacement for) the existing,
    validated time-bar-based WeisVerdictEngine.

    Scoring logic below mirrors WeisVerdictEngine's exact structure
    and thresholds (SOT requires 3 same-direction waves with strictly
    decreasing price_progress; exhaustion requires SOT confirmed AND
    the final wave's volume under 60% of the prior same-direction
    wave's; confirmation requires the current wave's volume exceeding
    1.25x the combined volume of the last two opposite-direction
    waves) -- applied to brick-based waves instead of time-bar waves.
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
            brick_count = w["brick_count"]
            avg_vol_per_brick = (w["cumulative_volume"] / brick_count) if brick_count > 0 else 0.0
            waves.append(RenkoWeisWave(
                direction=w["direction"],
                brick_count=brick_count,
                price_progress=w["price_progress"],
                cumulative_volume=w["cumulative_volume"],
                start_index=start_index,
                end_index=end_index,
                avg_volume_per_brick=avg_vol_per_brick,
            ))
            brick_cursor += brick_count

        return waves

    def shortening_of_thrust_score(self, waves: List[RenkoWeisWave]) -> float:
        down = [w for w in waves if w.direction == -1]
        if len(down) < 3:
            return 0.0
        w1, w2, w3 = down[-3:]
        if w3.price_progress < w2.price_progress < w1.price_progress:
            return 100.0
        return 0.0

    def shortening_of_thrust_score_bearish(self, waves: List[RenkoWeisWave]) -> float:
        up = [w for w in waves if w.direction == 1]
        if len(up) < 3:
            return 0.0
        w1, w2, w3 = up[-3:]
        if w3.price_progress < w2.price_progress < w1.price_progress:
            return 100.0
        return 0.0

    def volume_exhaustion_score(self, waves: List[RenkoWeisWave], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        down = [w for w in waves if w.direction == -1]
        if len(down) < 2:
            return 0.0
        w2, w3 = down[-2], down[-1]
        if w3.cumulative_volume < (0.60 * w2.cumulative_volume):
            return 100.0
        return 0.0

    def buying_exhaustion_score(self, waves: List[RenkoWeisWave], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        up = [w for w in waves if w.direction == 1]
        if len(up) < 2:
            return 0.0
        w2, w3 = up[-2], up[-1]
        if w3.cumulative_volume < (0.60 * w2.cumulative_volume):
            return 100.0
        return 0.0

    def effort_without_reward_score(self, waves: List[RenkoWeisWave], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        down = [w for w in waves if w.direction == -1]
        if len(down) < 2:
            return 0.0
        w2, w3 = down[-2], down[-1]
        if w3.cumulative_volume >= w2.cumulative_volume:
            return 100.0
        return 0.0

    def buying_effort_without_reward_score(self, waves: List[RenkoWeisWave], sot_confirmed: bool = False) -> float:
        if not sot_confirmed:
            return 0.0
        up = [w for w in waves if w.direction == 1]
        if len(up) < 2:
            return 0.0
        w2, w3 = up[-2], up[-1]
        if w3.cumulative_volume >= w2.cumulative_volume:
            return 100.0
        return 0.0

    def upwave_confirmation_score(self, waves: List[RenkoWeisWave]) -> float:
        if not waves:
            return 0.0
        down = [w for w in waves if w.direction == -1]
        if len(down) < 2:
            return 0.0
        last_two = down[-1].cumulative_volume + down[-2].cumulative_volume
        current = waves[-1]
        if current.direction == 1 and current.cumulative_volume > (1.25 * last_two):
            return 100.0
        return 0.0

    def downwave_confirmation_score(self, waves: List[RenkoWeisWave]) -> float:
        if not waves:
            return 0.0
        up = [w for w in waves if w.direction == 1]
        if len(up) < 2:
            return 0.0
        last_two = up[-1].cumulative_volume + up[-2].cumulative_volume
        current = waves[-1]
        if current.direction == -1 and current.cumulative_volume > (1.25 * last_two):
            return 100.0
        return 0.0

    def current_wave_reading(self, waves: List[RenkoWeisWave]) -> Dict[str, Any]:
        """
        FIX (2026-08-09): user pointed out the score/verdict alone
        ("0 -- No Weis Signal") throws away exactly the step-by-step
        reading David Weis's own workflow describes -- what the
        current directional swing actually looks like right now, and
        whether its volume is shrinking or growing versus the prior
        same-direction wave (Effort vs. Result), independent of
        whether the full, strict 3-wave SOT gate has fired. This is
        genuinely informative on its own, and true for every symbol
        with at least two same-direction waves -- not gated behind the
        much rarer, stricter conditions the score/verdict require.
        """
        if not waves:
            return {"available": False, "reason": "No waves detected yet."}

        current = waves[-1]
        same_direction_prior = [
            w for w in waves[:-1] if w.direction == current.direction
        ]

        if not same_direction_prior:
            return {
                "available": True,
                "direction": "UP" if current.direction == 1 else "DOWN",
                "current_wave_volume": round(current.cumulative_volume, 0),
                "current_wave_price_progress": round(current.price_progress, 4),
                "current_wave_brick_count": current.brick_count,
                "prior_same_direction_volume": None,
                "effort_vs_result": "INSUFFICIENT_HISTORY",
                "avg_volume_per_brick": round(current.avg_volume_per_brick, 0),
                "relative_pace_ratio": None,
                "market_condition": "INSUFFICIENT_HISTORY",
                "reading": (
                    f"Current swing is {'UP' if current.direction == 1 else 'DOWN'} "
                    f"({current.brick_count} bricks, {current.price_progress:.2f} price progress, "
                    f"{current.cumulative_volume:,.0f} volume) -- no prior same-direction wave yet "
                    f"to compare effort against."
                ),
                "pace_reading": "No prior same-direction wave yet to compare structural pace against.",
            }

        prior = same_direction_prior[-1]
        if current.cumulative_volume < prior.cumulative_volume:
            effort_vs_result = "EXHAUSTING"
            reading_verb = "less volume than the prior swing -- effort is fading"
        elif current.cumulative_volume > prior.cumulative_volume:
            effort_vs_result = "BUILDING"
            reading_verb = "more volume than the prior swing -- fresh participation, trend building"
        else:
            effort_vs_result = "UNCHANGED"
            reading_verb = "about the same volume as the prior swing"

        # FIX (2026-08-09): structural pace -- volume required per
        # brick, deliberately NOT time-based (bars per brick would
        # reintroduce the exact temporal distortion Weis's own
        # framework is built to eliminate). Genuinely distinct from
        # effort_vs_result above: a longer wave can carry more total
        # volume while still moving with LESS volume per unit of
        # price progress -- this metric isolates that, normalized for
        # wave length. Thresholds (1.40 / 0.74) are carried over from
        # shared research, not independently empirically validated
        # against real reference data the way the wave-detection
        # threshold was earlier tonight.
        pace_ratio = None
        if prior.avg_volume_per_brick > 0:
            pace_ratio = current.avg_volume_per_brick / prior.avg_volume_per_brick

        if pace_ratio is None:
            market_condition = "INSUFFICIENT_HISTORY"
            pace_reading = "Prior wave's per-brick volume unavailable -- cannot assess structural pace."
        elif pace_ratio >= 1.40:
            market_condition = "ABSORPTION"
            pace_reading = (
                f"Structural pace is slowing ({pace_ratio:.1f}x more volume per brick than the prior "
                f"same-direction swing) -- heavy absorption forming, a possible roadblock ahead."
            )
        elif pace_ratio <= 0.74:
            market_condition = "EASE_OF_MOVEMENT"
            pace_reading = (
                f"Structural pace is fast ({pace_ratio:.2f}x the volume per brick of the prior "
                f"same-direction swing) -- little resistance, price moving with ease."
            )
        else:
            market_condition = "SYMMETRICAL"
            pace_reading = (
                f"Structural pace is steady ({pace_ratio:.1f}x the prior same-direction swing's "
                f"volume per brick) -- effort matches historical norms."
            )

        return {
            "available": True,
            "direction": "UP" if current.direction == 1 else "DOWN",
            "current_wave_volume": round(current.cumulative_volume, 0),
            "current_wave_price_progress": round(current.price_progress, 4),
            "current_wave_brick_count": current.brick_count,
            "prior_same_direction_volume": round(prior.cumulative_volume, 0),
            "effort_vs_result": effort_vs_result,
            "avg_volume_per_brick": round(current.avg_volume_per_brick, 0),
            "relative_pace_ratio": round(pace_ratio, 3) if pace_ratio is not None else None,
            "market_condition": market_condition,
            "reading": (
                f"Current swing is {'UP' if current.direction == 1 else 'DOWN'} "
                f"({current.brick_count} bricks, {current.cumulative_volume:,.0f} volume) -- "
                f"printing {reading_verb} ({prior.cumulative_volume:,.0f})."
            ),
            "pace_reading": pace_reading,
        }

    def evaluate(self, bars: List[Dict[str, Any]], symbol: str = "") -> RenkoWeisVerdict:
        waves = self.build_waves(bars)

        sot = self.shortening_of_thrust_score(waves)
        sot_confirmed = sot >= 100
        exhaustion = self.volume_exhaustion_score(waves, sot_confirmed=sot_confirmed)
        effort_without_reward = self.effort_without_reward_score(waves, sot_confirmed=sot_confirmed)
        confirmation = self.upwave_confirmation_score(waves)

        score = sot * 0.30 + exhaustion * 0.30 + confirmation * 0.40
        if score >= 90:
            verdict = "PRIMARY_CAMPAIGN_LAUNCH"
        elif score >= 60:
            verdict = "ABSORPTION_WARNING"
        elif score >= 30:
            verdict = "WATCH"
        else:
            verdict = "NO_WEIS_SIGNAL"

        sot_bearish = self.shortening_of_thrust_score_bearish(waves)
        sot_bearish_confirmed = sot_bearish >= 100
        buying_exhaustion = self.buying_exhaustion_score(waves, sot_confirmed=sot_bearish_confirmed)
        buying_effort_without_reward = self.buying_effort_without_reward_score(waves, sot_confirmed=sot_bearish_confirmed)
        downwave_confirmation = self.downwave_confirmation_score(waves)

        score_bearish = sot_bearish * 0.30 + buying_exhaustion * 0.30 + downwave_confirmation * 0.40
        if score_bearish >= 90:
            verdict_bearish = "PRIMARY_DISTRIBUTION_LAUNCH"
        elif score_bearish >= 60:
            verdict_bearish = "SUPPLY_WARNING"
        elif score_bearish >= 30:
            verdict_bearish = "WATCH"
        else:
            verdict_bearish = "NO_WEIS_SIGNAL"

        return RenkoWeisVerdict(
            symbol=symbol,
            weis_score=round(score, 2),
            verdict=verdict,
            sot_downwaves=round(sot, 2),
            volume_exhaustion=round(exhaustion, 2),
            effort_without_reward=round(effort_without_reward, 2),
            upwave_confirmation=round(confirmation, 2),
            weis_score_bearish=round(score_bearish, 2),
            verdict_bearish=verdict_bearish,
            sot_upwaves=round(sot_bearish, 2),
            buying_exhaustion=round(buying_exhaustion, 2),
            buying_effort_without_reward=round(buying_effort_without_reward, 2),
            downwave_confirmation=round(downwave_confirmation, 2),
            wave_count=len(waves),
            explanation=(
                f"[Renko-based] SOT={sot:.1f}, Exhaustion={exhaustion:.1f}, "
                f"Confirmation={confirmation:.1f}, Bearish SOT={sot_bearish:.1f}, "
                f"BuyingExhaustion={buying_exhaustion:.1f}, DownwaveConfirmation={downwave_confirmation:.1f}, "
                f"waves={len(waves)}"
            ),
        )

