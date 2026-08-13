"""
SAVE AS:
backend/research_engine/weis_verdict_engine.py

Sigmalytic V2
David Weis Emerging Campaign Verdict Engine

Measures:
- Shortening Of Thrust (SOT)
- Wave Volume Exhaustion
- Explosive Up-Wave Confirmation

Purpose:
Measure campaign emergence using Weis Wave
effort-versus-result principles.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any

import pandas as pd
import numpy as np

from backend.research_engine.wyckoff_range_validator import WyckoffRangeValidator


@dataclass
class WeisVerdict:
    symbol: str
    weis_score: float
    verdict: str
    birth_eligible: bool

    sot_downwaves: float
    volume_exhaustion: float
    upwave_confirmation: float

    # FIX (2026-08-09): range maturity, per David Weis's own framework
    # -- a genuine "A" setup requires the sweep/exhaustion/reclaim
    # sequence to occur at the edge of an already-mature range (real,
    # multiple, time-separated touches of the same level over weeks),
    # not just the sequence in isolation.
    range_is_mature: bool = False
    range_support: float = None
    range_resistance: float = None
    range_support_touches: int = 0
    range_resistance_touches: int = 0

    # FIX (2026-08-09): "effort without reward" -- David Weis's own
    # distinct signal for SOT occurring with strong (not shrinking)
    # volume, separate from genuine exhaustion (SOT + weak volume).
    effort_without_reward: float = 0.0

    # FIX (2026-08-09): genuine Upthrust/short-side mirror of the
    # sot_downwaves/volume_exhaustion/upwave_confirmation trio above --
    # kept as fully separate fields, not blended into the long-side
    # score/verdict.
    sot_upwaves: float = 0.0
    buying_exhaustion: float = 0.0
    buying_effort_without_reward: float = 0.0
    downwave_confirmation: float = 0.0
    weis_score_bearish: float = 0.0
    verdict_bearish: str = "NO_WEIS_SIGNAL"

    explanation: str = ""
    as_of: str = ""

    def to_dict(self):
        return asdict(self)


class WeisVerdictEngine:

    def __init__(self,
                 vol_period: int = 20,
                 atr_period: int = 14,
                 atr_multiplier: float = 0.25,
                 zigzag_percent: float = 1.5):

        self.vol_period = vol_period
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        # FIX (2026-08-09): the fixed 1.5% threshold treated every
        # stock identically, so lower-volatility symbols could go an
        # entire 252-day lookback without ever registering a single
        # wave, producing a hollow, uninformative NO_WEIS_SIGNAL/0
        # result even when the underlying price data was perfectly
        # valid (confirmed directly -- Wyckoff/Livermore both produced
        # real, distinct scores from the exact same bars). Per David
        # Weis's own original methodology (his 2013 book, "Trades
        # About to Happen"), the reversal filter should be calibrated
        # to each market's own volatility, with ATR as his recommended
        # method for dynamic assets.
        #
        # UPDATE (2026-08-09): the general research guidance suggested
        # roughly 1.5x-2x the stock's 20-day ATR, but this was directly,
        # empirically tested against a real CSV export from an actual,
        # proven Weis Wave indicator, comparing its own genuine Swing/
        # SumVol wave-transition markers against this engine's output
        # on the identical price data. At 1.75x, this produced only 12
        # waves versus the real indicator's 30 over an initial ~160-day
        # sample -- far too conservative. 0.5x was the closest match on
        # that sample (29 vs. 30 waves, 76% within a day).
        #
        # CORRECTION (2026-08-09): re-validated against the full
        # ~500-day dataset (nearly 2 years) once the user provided it
        # in full -- the initial 160-day sample turned out not to be
        # representative. Over the full dataset, the real indicator
        # produced 131 transitions; 0.5x only found 78, still too
        # conservative. Re-tested multipliers from 0.10 to 0.50 across
        # the full data: 0.25x produced 134 waves (vs. the real 131),
        # with 78% landing within a single day of a real, confirmed
        # transition and 87% within two days -- the genuinely closest,
        # most robust match. Direct, empirical validation against real
        # reference output (on as large a sample as available) was
        # prioritized over both the generic secondary-source figure
        # and the earlier, smaller-sample result.
        #
        # Kept zigzag_percent as an explicit, named fallback default
        # (not silently unused) only if ATR can't be computed at all
        # (e.g. too few bars).
        self.zigzag_percent = zigzag_percent

    def _compute_atr_series(self, df: pd.DataFrame) -> pd.Series:
        """
        Real, per-bar rolling ATR series (True Range averaged over
        self.atr_period). Shared helper reused by both
        _compute_atr_threshold_pct() (wave-detection threshold) and
        WyckoffRangeValidator (range-maturity touch/breakout tolerance),
        so both use the exact same underlying ATR calculation rather
        than two separate, potentially-inconsistent implementations.
        """
        high, low, close = df["high"], df["low"], df["close"]
        prev_close = close.shift(1)
        true_range = pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return true_range.rolling(self.atr_period).mean()

    def _compute_atr_threshold_pct(self, df: pd.DataFrame) -> float:
        """
        Real, per-symbol ATR-based reversal threshold, expressed as a
        percentage of recent price (to match build_waves()'s existing
        percentage-move comparison). Returns self.zigzag_percent as an
        explicit fallback if there isn't enough data for a genuine ATR.
        """
        if len(df) < self.atr_period + 1:
            return self.zigzag_percent

        atr = self._compute_atr_series(df).iloc[-1]
        recent_price = float(df["close"].iloc[-1])
        if pd.isna(atr) or recent_price <= 0:
            return self.zigzag_percent

        return float(atr) * self.atr_multiplier / recent_price * 100

    def _prepare(self, df: pd.DataFrame):

        df = df.copy()

        df["vol_sma"] = (
            df["volume"]
            .rolling(self.vol_period)
            .mean()
        )

        return df

    def build_waves(self, df):

        waves = []

        # FIX (2026-08-09): compute the real, per-symbol ATR-based
        # threshold once per call, instead of the fixed 1.5% that
        # applied identically to every stock regardless of its own
        # actual volatility.
        threshold_pct = self._compute_atr_threshold_pct(df)

        current_dir = (
            -1 if df["close"].iloc[1] <= df["close"].iloc[0]
            else 1
        )

        current_volume = df["volume"].iloc[0]
        current_start = df["close"].iloc[0]
        # FIX (2026-08-09): a running extreme (lowest close reached
        # during a down-wave, highest during an up-wave), separate
        # from current_start. Found while testing the earlier fix
        # above: comparing new bars against the wave's static
        # starting point meant a genuine reversal would never
        # register until price retraced all the way back past where
        # the wave began, not just a meaningful bounce off the actual
        # recent low/high -- itself incorrect zigzag behavior. Real
        # wave/zigzag logic tracks the running extreme and reacts to
        # movement away from *that*, not the original start.
        running_extreme = current_start

        wave_volume = np.zeros(len(df))
        wave_direction = np.zeros(len(df))
        # FIX (2026-08-12): tracks each individual bar's own volume
        # within the current wave, needed for Structural Pace and
        # Climax detection -- mirroring the same addition made
        # earlier for RenkoWeisWave/PnFColumn. Not previously tracked
        # since only the aggregate "vol" was needed for the existing
        # SOT/exhaustion/confirmation scoring.
        current_bar_volumes: list = []

        for i in range(1, len(df)):

            prev_close = df["close"].iloc[i - 1]
            close = df["close"].iloc[i]

            if prev_close == 0 or running_extreme == 0:
                continue

            # Extend the running extreme if this bar continues the
            # current wave's direction further.
            if current_dir == -1 and close < running_extreme:
                running_extreme = close
            elif current_dir == 1 and close > running_extreme:
                running_extreme = close

            diff = close - running_extreme

            pct = (
                abs(diff)
                / running_extreme
                * 100
            )

            if pct >= threshold_pct:

                new_dir = 1 if diff > 0 else -1

                if new_dir != current_dir:

                    waves.append({
                        "dir": int(current_dir),
                        "vol": float(current_volume),
                        "delta": float(abs(
                            running_extreme
                            - current_start
                        )),
                        "bar_volumes": current_bar_volumes,
                    })

                    current_dir = new_dir
                    current_volume = 0
                    current_start = running_extreme
                    running_extreme = close
                    current_bar_volumes = []

            current_volume += df["volume"].iloc[i]
            current_bar_volumes.append(float(df["volume"].iloc[i]))

            wave_volume[i] = current_volume
            wave_direction[i] = current_dir

        # FIX (2026-08-12): the current, still-forming wave never gets
        # appended to `waves` (that only happens on a completed
        # reversal), so it was previously invisible outside this
        # function -- needed for the new current_wave_reading()-style
        # method below. Returned separately, NOT mixed into `waves`
        # itself, to avoid any risk of changing the existing, already-
        # validated SOT/exhaustion/confirmation scoring, which filters
        # and indexes into `waves` directly.
        current_wave = {
            "dir": int(current_dir),
            "vol": float(current_volume),
            "delta": float(abs(df["close"].iloc[-1] - current_start)) if len(df) else 0.0,
            "bar_volumes": current_bar_volumes,
        }

        return waves, wave_volume, wave_direction, current_wave

    def shortening_of_thrust_score(self, waves):

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 3:
            return 0.0

        w1, w2, w3 = down[-3:]

        if w3["delta"] < w2["delta"] < w1["delta"]:
            return 100.0

        return 0.0

    def volume_exhaustion_score(self, waves, sot_confirmed: bool = False):
        """
        FIX (2026-08-09): per David Weis's own direct words (Trades
        About to Happen): "When price advancement shortens but there
        is strong volume, it means that the great effort obtained
        little reward... When the price advance shortens and there is
        also weak volume, it means exhaustion." These are two
        genuinely different signals, not one -- exhaustion specifically
        requires the shortening (SOT) AND weak volume to occur
        together on the same waves, not weak volume computed on its
        own regardless of whether SOT even fired. Now requires
        sot_confirmed=True before genuine exhaustion can register at
        all; the strong-volume case is handled separately as
        effort_without_reward_score(), per the book's own description
        of it as a distinct, meaningful state -- not simply "no
        exhaustion".
        """
        if not sot_confirmed:
            return 0.0

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 2:
            return 0.0

        w2 = down[-2]
        w3 = down[-1]

        if w3["vol"] < (0.60 * w2["vol"]):
            return 100.0

        return 0.0

    def effort_without_reward_score(self, waves, sot_confirmed: bool = False) -> float:
        """
        FIX (2026-08-09): the "great effort, little reward" case from
        David Weis's own description -- shortening (SOT) occurring
        WITH strong (not shrinking) volume. Per the book, this is not
        the same as exhaustion and does not imply supply/demand is
        withdrawing; it's a real, separate divergence signal in its
        own right (demand appearing to absorb, in a bearish example).
        """
        if not sot_confirmed:
            return 0.0

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 2:
            return 0.0

        w2 = down[-2]
        w3 = down[-1]

        # The mirror condition of volume_exhaustion_score(): the final
        # wave's volume is NOT meaningfully shrinking (>= the prior
        # wave's volume), despite the price shortening.
        if w3["vol"] >= w2["vol"]:
            return 100.0

        return 0.0

    def upwave_confirmation_score(
        self,
        waves,
        wave_volume,
        wave_direction
    ):

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 2:
            return 0.0

        last_two = (
            down[-1]["vol"]
            +
            down[-2]["vol"]
        )

        current_green = wave_volume[-1]

        current_dir = wave_direction[-1]

        if (
            current_dir == 1
            and
            current_green > (1.25 * last_two)
        ):
            return 100.0

        return 0.0

    def shortening_of_thrust_score_bearish(self, waves) -> float:
        """
        FIX (2026-08-09): mirror of shortening_of_thrust_score() for
        the Upthrust/short side -- shortening price advancement on
        the way UP into an Upthrust, using up-waves instead of
        down-waves. Same three-push minimum David Weis's own text
        requires ("requires a minimum of three pushes").
        """
        up = [w for w in waves if w["dir"] == 1]

        if len(up) < 3:
            return 0.0

        w1, w2, w3 = up[-3:]

        if w3["delta"] < w2["delta"] < w1["delta"]:
            return 100.0

        return 0.0

    def buying_exhaustion_score(self, waves, sot_confirmed: bool = False) -> float:
        """
        FIX (2026-08-09): mirror of volume_exhaustion_score() for the
        Upthrust/short side -- genuine buying exhaustion requires the
        same SOT (shortening, on up-waves) AND weak volume together,
        per David Weis's own words, applied to the bearish case.
        """
        if not sot_confirmed:
            return 0.0

        up = [w for w in waves if w["dir"] == 1]

        if len(up) < 2:
            return 0.0

        w2 = up[-2]
        w3 = up[-1]

        if w3["vol"] < (0.60 * w2["vol"]):
            return 100.0

        return 0.0

    def buying_effort_without_reward_score(self, waves, sot_confirmed: bool = False) -> float:
        """
        FIX (2026-08-09): mirror of effort_without_reward_score() for
        the Upthrust/short side.
        """
        if not sot_confirmed:
            return 0.0

        up = [w for w in waves if w["dir"] == 1]

        if len(up) < 2:
            return 0.0

        w2 = up[-2]
        w3 = up[-1]

        if w3["vol"] >= w2["vol"]:
            return 100.0

        return 0.0

    def downwave_confirmation_score(
        self,
        waves,
        wave_volume,
        wave_direction
    ) -> float:
        """
        FIX (2026-08-09): mirror of upwave_confirmation_score() for
        the Upthrust/short side -- confirms the breakdown after an
        Upthrust via a genuinely strong down-wave (volume
        overwhelming the last two up-waves combined), not price
        alone.
        """
        up = [w for w in waves if w["dir"] == 1]

        if len(up) < 2:
            return 0.0

        last_two = (
            up[-1]["vol"]
            +
            up[-2]["vol"]
        )

        current_red = wave_volume[-1]

        current_dir = wave_direction[-1]

        if (
            current_dir == -1
            and
            current_red > (1.25 * last_two)
        ):
            return 100.0

        return 0.0

    def detect_climax(self, wave: dict, multiplier: float = 2.0) -> Dict[str, Any]:
        """
        Mirrors RenkoWeisWaveEngine.detect_climax() exactly -- the
        "Climax Variant" from the shared research: a single bar whose
        volume diverges aggressively from the running average of the
        OTHER bars within the same, current wave. Genuinely distinct
        from Structural Pace below (which compares this wave's average
        against a DIFFERENT, prior wave). Same 2.0x default multiplier,
        same honesty caveat: a reasoned default, not independently
        empirically validated against real reference data.
        """
        bar_volumes = wave.get("bar_volumes") or []
        if len(bar_volumes) < 3:
            return {"detected": False, "reason": "Needs at least 3 bars in the current wave to assess."}

        baseline_bars = bar_volumes[:-1]
        final_bar_volume = bar_volumes[-1]
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
                f"Climax bar detected: the final bar in this wave carried {ratio:.1f}x the "
                f"volume of the {len(baseline_bars)} bars before it ({final_bar_volume:,.0f} vs. "
                f"a {running_avg:,.0f} running average) -- a sudden, concentrated effort spike, "
                f"signaling an immediate structural roadblock."
                if detected else
                f"No climax bar -- the final bar's volume ({final_bar_volume:,.0f}) is in line "
                f"with the wave's own running average ({running_avg:,.0f})."
            ),
        }

    def current_wave_reading(self, waves: list, current_wave: dict) -> Dict[str, Any]:
        """
        Mirrors RenkoWeisWaveEngine.current_wave_reading() exactly --
        the always-informative reading (Effort vs. Result, Structural
        Pace, Climax) independent of whether the strict SOT/exhaustion/
        confirmation gate has fired, since that gate is genuinely rare
        by design. Operates on the current, still-forming wave
        (returned separately by build_waves(), not part of `waves`
        itself) compared against the most recent COMPLETED same-
        direction wave in `waves`.
        """
        if not current_wave or not current_wave.get("bar_volumes"):
            return {"available": False, "reason": "No wave data available yet."}

        direction_label = "UP" if current_wave["dir"] == 1 else "DOWN"
        current_bars = current_wave["bar_volumes"]
        current_avg_vol_per_bar = (current_wave["vol"] / len(current_bars)) if current_bars else 0.0

        same_direction_prior = [w for w in waves if w["dir"] == current_wave["dir"]]

        if not same_direction_prior:
            return {
                "available": True,
                "direction": direction_label,
                "current_wave_volume": round(current_wave["vol"], 0),
                "current_wave_bar_count": len(current_bars),
                "prior_same_direction_volume": None,
                "effort_vs_result": "INSUFFICIENT_HISTORY",
                "avg_volume_per_bar": round(current_avg_vol_per_bar, 0),
                "relative_pace_ratio": None,
                "market_condition": "INSUFFICIENT_HISTORY",
                "reading": (
                    f"Current swing is {direction_label} ({len(current_bars)} bars, "
                    f"{current_wave['vol']:,.0f} volume) -- no prior same-direction wave yet "
                    f"to compare effort against."
                ),
                "pace_reading": "No prior same-direction wave yet to compare structural pace against.",
                "climax": self.detect_climax(current_wave),
            }

        prior = same_direction_prior[-1]
        if current_wave["vol"] < prior["vol"]:
            effort_vs_result = "EXHAUSTING"
            reading_verb = "less volume than the prior swing -- effort is fading"
        elif current_wave["vol"] > prior["vol"]:
            effort_vs_result = "BUILDING"
            reading_verb = "more volume than the prior swing -- fresh participation, trend building"
        else:
            effort_vs_result = "UNCHANGED"
            reading_verb = "about the same volume as the prior swing"

        prior_bars = prior.get("bar_volumes") or []
        prior_avg_vol_per_bar = (prior["vol"] / len(prior_bars)) if prior_bars else 0.0
        pace_ratio = None
        if prior_avg_vol_per_bar > 0:
            pace_ratio = current_avg_vol_per_bar / prior_avg_vol_per_bar

        if pace_ratio is None:
            market_condition = "INSUFFICIENT_HISTORY"
            pace_reading = "Prior wave's per-bar volume unavailable -- cannot assess structural pace."
        elif pace_ratio >= 1.40:
            market_condition = "ABSORPTION"
            pace_reading = (
                f"Structural pace is slowing ({pace_ratio:.1f}x more volume per bar than the prior "
                f"same-direction swing) -- heavy absorption forming, a possible roadblock ahead."
            )
        elif pace_ratio <= 0.74:
            market_condition = "EASE_OF_MOVEMENT"
            pace_reading = (
                f"Structural pace is fast ({pace_ratio:.2f}x the volume per bar of the prior "
                f"same-direction swing) -- little resistance, price moving with ease."
            )
        else:
            market_condition = "SYMMETRICAL"
            pace_reading = (
                f"Structural pace is steady ({pace_ratio:.1f}x the prior same-direction swing's "
                f"volume per bar) -- effort matches historical norms."
            )

        return {
            "available": True,
            "direction": direction_label,
            "current_wave_volume": round(current_wave["vol"], 0),
            "current_wave_bar_count": len(current_bars),
            "prior_same_direction_volume": round(prior["vol"], 0),
            "effort_vs_result": effort_vs_result,
            "avg_volume_per_bar": round(current_avg_vol_per_bar, 0),
            "relative_pace_ratio": round(pace_ratio, 3) if pace_ratio is not None else None,
            "market_condition": market_condition,
            "reading": (
                f"Current swing is {direction_label} ({len(current_bars)} bars, "
                f"{current_wave['vol']:,.0f} volume) -- printing {reading_verb} ({prior['vol']:,.0f})."
            ),
            "pace_reading": pace_reading,
            "climax": self.detect_climax(current_wave),
        }

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str = ""
    ) -> Dict[str, Any]:

        df = self._prepare(df)

        waves, wave_volume, wave_direction, current_wave = (
            self.build_waves(df)
        )

        sot = self.shortening_of_thrust_score(waves)
        sot_confirmed = sot >= 100

        exhaustion = (
            self.volume_exhaustion_score(waves, sot_confirmed=sot_confirmed)
        )

        effort_without_reward = self.effort_without_reward_score(waves, sot_confirmed=sot_confirmed)

        confirmation = (
            self.upwave_confirmation_score(
                waves,
                wave_volume,
                wave_direction
            )
        )

        # FIX (2026-08-09): mirror computation for the Upthrust/short
        # side, kept in its own separate score below rather than
        # blended into the existing (bullish-oriented) score/verdict.
        sot_bearish = self.shortening_of_thrust_score_bearish(waves)
        sot_bearish_confirmed = sot_bearish >= 100
        buying_exhaustion = self.buying_exhaustion_score(waves, sot_confirmed=sot_bearish_confirmed)
        buying_effort_without_reward = self.buying_effort_without_reward_score(waves, sot_confirmed=sot_bearish_confirmed)
        downwave_confirmation = self.downwave_confirmation_score(waves, wave_volume, wave_direction)

        # FIX (2026-08-09): range maturity check, per David Weis's own
        # framework -- reuses the same ATR series already computed for
        # wave-threshold detection, so this doesn't duplicate the
        # calculation.
        atr_series = self._compute_atr_series(df)
        range_result = WyckoffRangeValidator().evaluate(df, atr_series)

        score = (
            sot * 0.30
            +
            exhaustion * 0.30
            +
            confirmation * 0.40
        )

        if score >= 90:
            verdict = "PRIMARY_CAMPAIGN_LAUNCH"

        elif score >= 60:
            verdict = "ABSORPTION_WARNING"

        elif score >= 30:
            verdict = "WATCH"

        else:
            verdict = "NO_WEIS_SIGNAL"

        # FIX (2026-08-09): mirrored score/verdict for the Upthrust/
        # short side, kept genuinely separate from the long-side score
        # and verdict above -- not blended into weis_score.
        score_bearish = (
            sot_bearish * 0.30
            +
            buying_exhaustion * 0.30
            +
            downwave_confirmation * 0.40
        )

        if score_bearish >= 90:
            verdict_bearish = "PRIMARY_DISTRIBUTION_LAUNCH"
        elif score_bearish >= 60:
            verdict_bearish = "SUPPLY_WARNING"
        elif score_bearish >= 30:
            verdict_bearish = "WATCH"
        else:
            verdict_bearish = "NO_WEIS_SIGNAL"

        weis_verdict_obj = WeisVerdict(
            symbol=symbol,
            weis_score=round(score, 2),
            verdict=verdict,
            birth_eligible=(
                verdict
                in [
                    "PRIMARY_CAMPAIGN_LAUNCH",
                    "ABSORPTION_WARNING"
                ]
            ),
            sot_downwaves=round(sot, 2),
            volume_exhaustion=round(exhaustion, 2),
            upwave_confirmation=round(
                confirmation,
                2
            ),
            range_is_mature=range_result.is_mature,
            range_support=round(range_result.support, 2) if range_result.support is not None else None,
            range_resistance=round(range_result.resistance, 2) if range_result.resistance is not None else None,
            range_support_touches=range_result.support_touches,
            range_resistance_touches=range_result.resistance_touches,
            effort_without_reward=round(effort_without_reward, 2),
            sot_upwaves=round(sot_bearish, 2),
            buying_exhaustion=round(buying_exhaustion, 2),
            buying_effort_without_reward=round(buying_effort_without_reward, 2),
            downwave_confirmation=round(downwave_confirmation, 2),
            weis_score_bearish=round(score_bearish, 2),
            verdict_bearish=verdict_bearish,
            explanation=(
                f"SOT={sot:.1f}, "
                f"Exhaustion={exhaustion:.1f}, "
                f"EffortWithoutReward={effort_without_reward:.1f}, "
                f"Confirmation={confirmation:.1f}, "
                f"RangeMature={range_result.is_mature} "
                f"(S:{range_result.support_touches} touches, R:{range_result.resistance_touches} touches)"
            ),
            as_of=datetime.now(
                timezone.utc
            ).isoformat()
        )

        result = weis_verdict_obj.to_dict()
        result["current_wave"] = self.current_wave_reading(waves, current_wave)
        return result


def run_weis_verdict(
    record: Dict[str, Any]
):

    bars = record.get(
        "bars",
        []
    )

    symbol = record.get(
        "symbol",
        ""
    )

    return (
        WeisVerdictEngine()
        .evaluate(
            pd.DataFrame(bars),
            symbol=symbol
        )
    )
