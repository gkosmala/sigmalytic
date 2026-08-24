"""
SAVE AS:
backend/research_engine/wyckoff_verdict_engine.py

Sigmalytic V2
Wyckoff Emerging Campaign Verdict Engine
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class WyckoffVerdict:
    symbol: str
    wyckoff_score: float
    verdict: str
    phase: str
    birth_eligible: bool
    stopping_climax_score: float
    supply_absorption_score: float
    spring_score: float
    sign_of_strength_score: float
    meaningful_resistance_score: float
    behavioral_resolution_score: float
    survival_score: float
    resistance_level: Optional[float]
    support_level: Optional[float]
    cause_width_pct: Optional[float]
    progress_against_resistance: Optional[float]
    explanation: str
    as_of: str

    # FIX (2026-08-09): per David Weis's own direct words, Upthrusts
    # are NOT a mirror image of Springs -- "generally more difficult
    # to operate than the Springs... supposed Upthrusts in a bullish
    # trend rarely succeed; however, in a downtrend the Upthrusts
    # above a correction[ive] previous[ly] bullish [bounce] have a
    # higher likelihood of working." Added as a genuinely new,
    # separate signal (this engine previously had no Upthrust
    # detection of any kind), with its own trend-context asymmetry.
    upthrust_score: float = 0.0
    trend_context: str = "unknown"

    # FIX (2026-08-13): four genuine Wyckoff/Weis structural signals
    # this engine had no code for at all -- confirmed directly by
    # comparing the full field list against Weis's own terminology in
    # Trades About to Happen. Spring/Upthrust/SOS/SC/BC were already
    # covered; SOW, AR, LPS/LPSY, and ST were not.
    sign_of_weakness_score: float = 0.0
    automatic_rally_score: float = 0.0
    ar_high: Optional[float] = None
    ar_low: Optional[float] = None
    last_point_of_support_score: float = 0.0
    last_point_of_supply_score: float = 0.0
    secondary_test_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WyckoffVerdictEngine:
    REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

    def __init__(
        self,
        atr_period: int = 14,
        vol_sma_period: int = 20,
        swing_window: int = 10,
        structure_lookback: int = 50,
        validation_window: int = 30,
    ):
        self.atr_period = atr_period
        self.vol_sma_period = vol_sma_period
        self.swing_window = swing_window
        self.structure_lookback = structure_lookback
        self.validation_window = validation_window

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
        if pd.isna(value) or np.isinf(value):
            return 0.0
        return round(float(max(low, min(high, value))), 2)

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"Missing required OHLCV column: {col}")
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close", "volume"])

        df["vol_sma"] = df["volume"].rolling(self.vol_sma_period).mean()
        df["daily_range"] = df["high"] - df["low"]
        df["close_pct_of_range"] = (
            (df["close"] - df["low"]) / df["daily_range"].replace(0, np.nan)
        ).fillna(0.5)

        high_low = df["high"] - df["low"]
        high_cp = (df["high"] - df["close"].shift(1)).abs()
        low_cp = (df["low"] - df["close"].shift(1)).abs()
        true_range = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df["atr"] = true_range.rolling(self.atr_period).mean()

        df["is_high"] = df["high"] == df["high"].rolling(self.swing_window, center=True).max()
        df["is_low"] = df["low"] == df["low"].rolling(self.swing_window, center=True).min()
        return df

    def _structure_bounds(self, df: pd.DataFrame, idx: int) -> Dict[str, Optional[float]]:
        window = df.iloc[max(0, idx - self.structure_lookback):idx]
        recent_highs = window[window["is_high"]]["high"].values
        recent_lows = window[window["is_low"]]["low"].values
        if len(recent_highs) < 2 or len(recent_lows) < 2:
            return {"support": None, "resistance": None}
        return {"support": float(recent_lows[-1]), "resistance": float(recent_highs[-1])}

    def _find_well_defined_level(self, df: pd.DataFrame, idx: int, is_support: bool,
                                   lookback: int = 150, proximity_pct: float = 0.0015,
                                   min_touches: int = 2) -> Optional[float]:
        """
        FIX (2026-08-23): a genuine, multi-touch support/resistance
        level -- distinct from _structure_bounds() above, which is
        just the single most recent swing point and remains unchanged
        for everything else in this engine that uses it (absorption,
        climax, meaningful-resistance scoring, etc.). This stricter
        definition is specifically for Spring/Upthrust, matching
        Weis's own words for exactly that context: "a well-defined
        support line" -- confirmed directly against the actual text
        (Trades About to Happen, "Springs" chapter), which describes
        markets that "test and retest" a level, large operators
        gauging "how much demand exists around well-defined support
        levels." A single, never-retested swing point is not that.

        Reuses this engine's own existing is_high/is_low swing
        detection (already computed in _prepare(), same swing_window
        used everywhere else in this engine) rather than introducing a
        second, differently-parameterized swing definition.

        Requires at least min_touches genuine swing points within
        proximity_pct of each other; returns their average as the
        level, or None if no such cluster exists -- callers (Spring/
        Upthrust scoring) must treat None as "no well-defined level to
        evaluate against," not fall back to a weaker single-point
        definition, since that fallback is the exact behavior this
        fix exists to remove.
        """
        col = "is_low" if is_support else "is_high"
        price_col = "low" if is_support else "high"
        hist_start = max(0, idx - lookback)
        hist_end = max(hist_start, idx - 5)  # exclude the most recent 5 bars -- still "ripening"
        window = df.iloc[hist_start:hist_end]
        swings = window[window[col]][price_col].values
        if len(swings) < min_touches:
            return None

        best_zone = None
        best_distance = None
        current_price = float(df["close"].iloc[idx])
        for candidate in swings:
            upper = candidate * (1 + proximity_pct)
            lower = candidate * (1 - proximity_pct)
            matches = swings[(swings >= lower) & (swings <= upper)]
            if len(matches) >= min_touches:
                zone_avg = float(np.mean(matches))
                distance = abs(zone_avg - current_price)
                if best_distance is None or distance < best_distance:
                    best_zone, best_distance = zone_avg, distance
        return best_zone

    def _score_stopping_climax(self, df: pd.DataFrame, idx: int, support: float) -> float:
        row = df.iloc[idx]
        score = 0
        if row["close"] < row["open"]:
            score += 20
        if row["volume"] >= 2.5 * row["vol_sma"]:
            score += 35
        if row["close_pct_of_range"] >= 0.50:
            score += 25
        if row["low"] <= 1.01 * support:
            score += 20
        return self._clamp(score)

    def _score_supply_absorption(self, df: pd.DataFrame, idx: int, support: float, resistance: float) -> float:
        row = df.iloc[idx]
        window = df.iloc[max(0, idx - self.structure_lookback):idx]
        inside_range = support < row["close"] < resistance
        down_days = window[window["close"] < window["open"]]
        recent_down_vol = down_days["volume"].tail(5).mean()
        down_volume_drying = bool(pd.notna(recent_down_vol) and recent_down_vol < row["vol_sma"])
        spreads = window["high"] - window["low"]
        spread_contracting = spreads.tail(10).mean() < spreads.tail(30).mean()
        support_holding = window["low"].tail(10).min() >= 0.98 * support

        score = 0
        if inside_range:
            score += 30
        if down_volume_drying:
            score += 30
        if spread_contracting:
            score += 20
        if support_holding:
            score += 20
        return self._clamp(score)

    def detect_breakout(self, df: pd.DataFrame, idx: int, resistance: Optional[float],
                          lookback_days: int = 20) -> Optional[Dict[str, Any]]:
        """
        ADDED (2026-08-24): the successful-test mirror image of
        Upthrust -- price sweeps above a well-defined resistance level
        and HOLDS there, rather than reverting. Ported directly from
        the same, already-validated logic in the standalone Weis scan
        tool built this session (scanForCrossing). Standalone method,
        deliberately not wired into evaluate_bars()/WyckoffVerdict --
        built specifically for the new Russell 1000 scan, without
        touching the existing dataclass/single-symbol panel already
        live in production.
        """
        return self._scan_for_crossing(df, idx, resistance, is_breakout=True, lookback_days=lookback_days)

    def detect_breakdown(self, df: pd.DataFrame, idx: int, support: Optional[float],
                           lookback_days: int = 20) -> Optional[Dict[str, Any]]:
        """The successful-test mirror image of Spring -- see detect_breakout()."""
        return self._scan_for_crossing(df, idx, support, is_breakout=False, lookback_days=lookback_days)

    def _scan_for_crossing(self, df: pd.DataFrame, idx: int, level: Optional[float],
                             is_breakout: bool, lookback_days: int = 20) -> Optional[Dict[str, Any]]:
        if level is None:
            return None
        row = df.iloc[idx]
        is_beyond = (lambda r: r["close"] > level * 1.001) if is_breakout else (lambda r: r["close"] < level * 0.999)
        if not is_beyond(row):
            return None

        crossing_idx = idx
        for i in range(idx, max(-1, idx - lookback_days - 1), -1):
            if is_beyond(df.iloc[i]):
                crossing_idx = i
            else:
                break
        held = all(is_beyond(df.iloc[i]) for i in range(crossing_idx, idx + 1))
        days_back = idx - crossing_idx
        pct_beyond = (row["close"] / level - 1) * 100 if is_breakout else (1 - row["close"] / level) * 100
        return {
            "level": float(level), "date": str(df.index[crossing_idx]) if hasattr(df, "index") else None,
            "days_back": int(days_back), "held": bool(held), "pct_beyond": round(float(pct_beyond), 2),
        }


    def _get_prior_wave_volumes(self, df: pd.DataFrame, upto_idx: int,
                                  trend_length: int = 2, max_waves: int = 5) -> Dict[str, Any]:
        """
        ADDED (2026-08-24): ported directly from the same, already-
        validated logic built and tested in the standalone Weis scan
        tool this session -- replaces a fixed bar-count volume moving
        average (previously used by _score_spring/_score_upthrust)
        with a comparison against the average of recent COMPLETED
        waves. A "20-bar average" means a different real-world span
        depending on the underlying bar interval (confirmed directly:
        140 hourly bars is ~1 month, not ~4 days, a genuine arithmetic
        error caught in an earlier proposed fix) -- waves, unlike bar
        counts, scale naturally with real market structure regardless
        of timeframe, matching Weis's own stated preference for
        Renko/PnF over time bars for exactly this reason.
        """
        waves: list = []
        current_dir = 0
        up_count = dn_count = 0
        running = 0.0
        for i in range(1, upto_idx + 1):
            is_higher = df["close"].iloc[i] > df["close"].iloc[i - 1]
            is_lower = df["close"].iloc[i] < df["close"].iloc[i - 1]
            up_count = up_count + 1 if is_higher else 0
            dn_count = dn_count + 1 if is_lower else 0
            reversal_to_up = up_count >= trend_length and current_dir != 1
            reversal_to_down = dn_count >= trend_length and current_dir != -1
            if reversal_to_up or reversal_to_down:
                if current_dir != 0:
                    waves.append(running)
                current_dir = 1 if reversal_to_up else -1
                running = 0.0
            running += float(df["volume"].iloc[i])
        return {"prior_waves": waves[-max_waves:], "current_wave_volume": running}

    def _score_spring(self, df: pd.DataFrame, idx: int, support: Optional[float]) -> float:
        """
        FIX (2026-08-23): confirmed via direct testing that the breach
        condition (row["low"] < 0.995*support) was previously just one
        of four additive factors -- a bar that never dipped below
        support at all could still score 70 (the confirmation
        threshold) purely from a strong close, elevated volume, and
        close-of-range, with zero actual shakeout. That's a real
        mismatch with Weis's own definition: "a spring is a washout
        (penetration) of a trading range or support level" -- the
        breach isn't one factor among several, it's the premise the
        whole pattern rests on. Now a hard gate: no genuine breach,
        score is 0, full stop, before any other factor is even
        checked. Also now requires a genuinely well-defined
        (multi-touch) support level -- see _find_well_defined_level()
        -- not just the single most recent swing low.

        FIX (2026-08-24): volume confirmation now uses
        _get_prior_wave_volumes() (wave-relative) instead of a fixed
        20-bar moving average -- see that method's own docstring.
        """
        if support is None:
            return 0
        row = df.iloc[idx]
        if not (row["low"] < 0.995 * support):
            return 0
        score = 30  # breach confirmed -- baseline for meeting the core definition
        if row["close"] > support:
            score += 35
        wave_info = self._get_prior_wave_volumes(df, idx)
        if wave_info["prior_waves"]:
            avg_prior_wave = sum(wave_info["prior_waves"]) / len(wave_info["prior_waves"])
            if wave_info["current_wave_volume"] >= 1.5 * avg_prior_wave:
                score += 20
        if row["close_pct_of_range"] >= 0.50:
            score += 15
        return self._clamp(score)

    def _detect_trend_context(self, df: pd.DataFrame, idx: int, trend_period: int = 100) -> str:
        """
        FIX (2026-08-09): per David Weis's own direct words, Upthrust
        success depends heavily on the broader trend, unlike Springs:
        "supposed Upthrusts in a bullish trend rarely succeed;
        however, in a downtrend the Upthrusts above a correction[ive]
        previous[ly] bullish [bounce] have a higher likelihood of
        working." Approximates the broader (not local-range) trend by
        comparing current price to a longer-term moving average
        (deliberately longer than structure_lookback, which only
        looks at the local range) -- price above it suggests the
        primary trend is bullish (Upthrusts here are the harder,
        lower-probability case); price below it suggests the primary
        trend is bearish, with the current test of resistance more
        likely being a corrective bounce within that larger downtrend
        (the higher-probability case per the book).
        """
        window = df.iloc[max(0, idx - trend_period + 1):idx + 1]
        if len(window) < trend_period // 2:
            return "unknown"
        long_ma = window["close"].mean()
        current_close = float(df["close"].iloc[idx])
        if current_close > long_ma:
            return "bullish"
        return "bearish"

    def _score_upthrust(self, df: pd.DataFrame, idx: int, resistance: Optional[float], trend_context: str) -> float:
        """
        Genuine Upthrust detection -- this engine previously had none
        at all. Mirrors _score_spring()'s structure (sweep, reclaim,
        volume, close position) but is NOT simply spring_score's
        mirror image, per the book's own explicit statements:

        - Size guidance is asymmetric: the book gives Upthrust an
          explicit numeric limit ("a new maximum by 10 to 15% seems
          like a reasonable limitation") that Springs are never given
          in the source material -- enforced here as an upper bound,
          not just a minimum sweep depth.
        - Trend-context asymmetry: rather than a fixed weight, the
          book states Upthrusts in a bullish trend "rarely succeed"
          while Upthrusts in a downtrend (testing a corrective bounce)
          have "a higher likelihood of working" -- modeled as a
          genuine penalty/bonus, not a cosmetic label.

        FIX (2026-08-23): confirmed via direct testing -- the exact
        mirror image of the Spring bug fixed the same day. A bar that
        never once traded above resistance scored 80.5 and would have
        been labeled a confirmed Upthrust, purely from a weak close,
        elevated volume, and closing near its own low -- the one
        factor that actually defines an Upthrust (a genuine sweep
        above resistance) was worth only 30 of 100 points, not a
        precondition. Now a hard gate, same as Spring, plus requiring
        a genuinely well-defined (multi-touch) resistance level.
        """
        if resistance is None:
            return 0
        row = df.iloc[idx]
        sweep_pct = (row["high"] / resistance - 1.0) if resistance else 0.0
        # The sweep must be genuine (above resistance) but not so
        # large it's a real breakout rather than a trap -- the book's
        # own explicit 10-15% ceiling. Hard gate: no genuine sweep,
        # score is 0, before any other factor is even checked.
        if not (0.0 < sweep_pct <= 0.15):
            return 0
        score = 30  # sweep confirmed -- baseline for meeting the core definition
        if row["close"] < resistance:
            score += 35
        # FIX (2026-08-24): volume confirmation now uses
        # _get_prior_wave_volumes() (wave-relative), same fix and
        # same reasoning as _score_spring() above.
        wave_info = self._get_prior_wave_volumes(df, idx)
        if wave_info["prior_waves"]:
            avg_prior_wave = sum(wave_info["prior_waves"]) / len(wave_info["prior_waves"])
            if wave_info["current_wave_volume"] >= 1.5 * avg_prior_wave:
                score += 20
        if row["close_pct_of_range"] <= 0.50:
            score += 15

        score = self._clamp(score)

        # Trend-context asymmetry -- a real penalty/bonus, not cosmetic.
        if trend_context == "bullish":
            score *= 0.5
        elif trend_context == "bearish":
            score = min(100.0, score * 1.15)

        return self._clamp(score)

    def _score_sign_of_strength(self, df: pd.DataFrame, idx: int, resistance: float) -> float:
        row = df.iloc[idx]
        atr = row["atr"] if pd.notna(row["atr"]) else 0
        score = 0
        if row["close"] > resistance:
            score += 25
        if row["close"] > resistance + 1.5 * atr:
            score += 25
        if row["volume"] > 1.5 * row["vol_sma"]:
            score += 25
        if resistance * 0.98 <= row["low"] <= resistance * 1.02 and row["volume"] < row["vol_sma"]:
            score += 25
        return self._clamp(score)

    def _score_sign_of_weakness(self, df: pd.DataFrame, idx: int, support: float) -> float:
        """
        Direct mirror of _score_sign_of_strength() -- unlike Spring
        vs. Upthrust (which Weis's own words explicitly describe as
        asymmetric, not mirror images), SOS and SOW are genuinely
        symmetric Wyckoff concepts: aggressive, high-volume expansion
        of price bars to the downside, signaling supply has fully
        overwhelmed demand.
        """
        row = df.iloc[idx]
        atr = row["atr"] if pd.notna(row["atr"]) else 0
        score = 0
        if row["close"] < support:
            score += 25
        if row["close"] < support - 1.5 * atr:
            score += 25
        if row["volume"] > 1.5 * row["vol_sma"]:
            score += 25
        if support * 0.98 <= row["high"] <= support * 1.02 and row["volume"] < row["vol_sma"]:
            score += 25
        return self._clamp(score)

    def _score_automatic_rally(self, df: pd.DataFrame, idx: int, support: float, lookback: int = 15) -> Dict[str, Any]:
        """
        The sharp, immediate counter-move following a climax (SC or
        BC) -- per Weis, its own high/low establish the initial
        parameters of the range's creek (resistance) or ice
        (support), so this returns those levels directly alongside
        the score, not just a bare number. Looks backward from idx
        for the highest-volume bar in the window (a candidate
        climax), then checks whether a genuine, sharp bounce followed
        it -- not a gradual, multi-week drift.
        """
        window = df.iloc[max(0, idx - lookback):idx + 1]
        if len(window) < 5:
            return {"score": 0.0, "ar_high": None, "ar_low": None}

        climax_candidates = window[window["volume"] >= 2.0 * window["vol_sma"]]
        if climax_candidates.empty:
            return {"score": 0.0, "ar_high": None, "ar_low": None}

        climax_pos = climax_candidates["low"].idxmin()
        climax_row = df.loc[climax_pos]
        after_climax = df.loc[climax_pos:df.index[idx]]
        if len(after_climax) < 2:
            return {"score": 0.0, "ar_high": None, "ar_low": None}

        ar_high = float(after_climax["high"].max())
        climax_low = float(climax_row["low"])
        rally_pct = (ar_high / climax_low - 1.0) if climax_low else 0.0

        score = 0
        if rally_pct >= 0.03:
            score += 50
        if len(after_climax) <= 5:
            score += 30
        if ar_high > support:
            score += 20

        return {
            "score": self._clamp(score),
            "ar_high": round(ar_high, 4),
            "ar_low": round(climax_low, 4),
        }

    def _score_last_point_of_support(self, df: pd.DataFrame, idx: int, support: float) -> float:
        """
        LPS -- the final, low-volume test near support before the
        market leaves the range to markup. A genuine LPS holds near
        support on notably light volume (supply has dried up) with a
        narrowing daily range, not another wide, high-volume swing.
        """
        row = df.iloc[idx]
        atr = row["atr"] if pd.notna(row["atr"]) else 0
        score = 0
        if support * 0.98 <= row["low"] <= support * 1.03:
            score += 30
        if row["volume"] < 0.8 * row["vol_sma"]:
            score += 35
        if row["close"] > support:
            score += 20
        if atr and row["daily_range"] < atr:
            score += 15
        return self._clamp(score)

    def _score_last_point_of_supply(self, df: pd.DataFrame, idx: int, resistance: float) -> float:
        """LPSY -- the direct mirror of LPS, at resistance rather than support."""
        row = df.iloc[idx]
        atr = row["atr"] if pd.notna(row["atr"]) else 0
        score = 0
        if resistance * 0.97 <= row["high"] <= resistance * 1.02:
            score += 30
        if row["volume"] < 0.8 * row["vol_sma"]:
            score += 35
        if row["close"] < resistance:
            score += 20
        if atr and row["daily_range"] < atr:
            score += 15
        return self._clamp(score)

    def _score_secondary_test(self, df: pd.DataFrame, idx: int, support: float) -> float:
        """
        ST -- a return to the prior climax's extreme on genuinely
        lower volume than a typical swing, confirming supply/demand
        was truly exhausted there rather than merely paused.
        """
        row = df.iloc[idx]
        score = 0
        if support * 0.98 <= row["low"] <= support * 1.02:
            score += 40
        if row["volume"] < row["vol_sma"]:
            score += 35
        if row["low"] >= support * 0.99:
            score += 25
        return self._clamp(score)

    def _score_meaningful_resistance(self, current_close: float, support: float, resistance: float) -> Dict[str, float]:
        cause_width = max(0.0, resistance - support)
        cause_width_pct = cause_width / max(current_close, 1.0)
        cause_quality = min(100.0, cause_width_pct * 500.0)
        distance_to_resistance = resistance - current_close
        proximity = 100.0 - min(100.0, max(0.0, distance_to_resistance / max(current_close, 1.0) * 500.0))
        return {"score": self._clamp(cause_quality * 0.60 + proximity * 0.40), "cause_width_pct": round(float(cause_width_pct), 4)}

    def _score_behavioral_resolution(self, df: pd.DataFrame, idx: int, resistance: float) -> Dict[str, float]:
        current_close = float(df["close"].iloc[idx])
        prior_close = float(df["close"].iloc[max(0, idx - 5)])
        progress_against_resistance = current_close / max(resistance, 1.0)
        five_bar_progress = (current_close - prior_close) / max(prior_close, 1.0)
        score = 0
        if progress_against_resistance >= 0.98:
            score += 35
        if current_close > resistance:
            score += 40
        if five_bar_progress > 0:
            score += 25
        return {"score": self._clamp(score), "progress_against_resistance": round(float(progress_against_resistance), 4)}

    def _score_survival(self, df: pd.DataFrame, idx: int) -> float:
        recent = df.iloc[max(0, idx - self.validation_window):idx + 1]
        if len(recent) < 10:
            return 0.0
        higher_lows = (recent["low"] > recent["low"].shift(1)).sum()
        close_above_mid = (recent["close"] > ((recent["high"] + recent["low"]) / 2)).sum()
        max_close = recent["close"].max()
        drawdown = (recent["close"].iloc[-1] - max_close) / max(max_close, 1.0)
        score = min(100, higher_lows * 5) * 0.35 + min(100, close_above_mid * 4) * 0.35 + max(0, 100 + drawdown * 300) * 0.30
        return self._clamp(score)

    def evaluate_bars(self, df: pd.DataFrame, symbol: str = "") -> Dict[str, Any]:
        df = self._prepare(df)
        if len(df) < self.structure_lookback + 10:
            return WyckoffVerdict(
                symbol=symbol.upper(), wyckoff_score=0.0, verdict="INSUFFICIENT_DATA", phase="UNKNOWN",
                birth_eligible=False, stopping_climax_score=0.0, supply_absorption_score=0.0,
                spring_score=0.0, sign_of_strength_score=0.0, meaningful_resistance_score=0.0,
                behavioral_resolution_score=0.0, survival_score=0.0, resistance_level=None,
                support_level=None, cause_width_pct=None, progress_against_resistance=None,
                explanation="Insufficient bars for Wyckoff campaign evaluation.",
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        idx = len(df) - 1
        bounds = self._structure_bounds(df, idx)
        if bounds["support"] is None or bounds["resistance"] is None:
            return WyckoffVerdict(
                symbol=symbol.upper(), wyckoff_score=0.0, verdict="NO_MEANINGFUL_STRUCTURE", phase="UNKNOWN",
                birth_eligible=False, stopping_climax_score=0.0, supply_absorption_score=0.0,
                spring_score=0.0, sign_of_strength_score=0.0, meaningful_resistance_score=0.0,
                behavioral_resolution_score=0.0, survival_score=0.0, resistance_level=None,
                support_level=None, cause_width_pct=None, progress_against_resistance=None,
                explanation="No sufficient swing structure to define support/resistance.",
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        support = bounds["support"]
        resistance = bounds["resistance"]
        current_close = float(df["close"].iloc[idx])

        stopping = self._score_stopping_climax(df, idx, support)
        absorption = self._score_supply_absorption(df, idx, support, resistance)
        # FIX (2026-08-23): Spring/Upthrust now evaluated against a
        # genuinely well-defined (multi-touch) level, not the general
        # single-most-recent-swing "support"/"resistance" used above
        # for absorption/climax/etc. -- see _find_well_defined_level()
        # for why this distinction matters specifically here, per
        # Weis's own words about "well-defined support."
        well_defined_support = self._find_well_defined_level(df, idx, is_support=True)
        well_defined_resistance = self._find_well_defined_level(df, idx, is_support=False)
        spring = self._score_spring(df, idx, well_defined_support)
        sos = self._score_sign_of_strength(df, idx, resistance)
        resistance_result = self._score_meaningful_resistance(current_close, support, resistance)
        resolution_result = self._score_behavioral_resolution(df, idx, resistance)
        survival = self._score_survival(df, idx)

        # FIX (2026-08-09): genuinely separate from wyckoff_score --
        # that score's own verdict tiers (STRONG_ACCUMULATION, etc.)
        # are all bullish-framed, so a strong Upthrust (a distribution
        # signal) must not blend into and inflate it.
        trend_context = self._detect_trend_context(df, idx)
        upthrust = self._score_upthrust(df, idx, well_defined_resistance, trend_context)

        # FIX (2026-08-13): four more genuine Wyckoff/Weis signals,
        # kept just as separate from wyckoff_score as upthrust already
        # is -- these are diagnostic readings in their own right, not
        # inputs to the existing accumulation-framed composite score.
        sow = self._score_sign_of_weakness(df, idx, support)
        ar_result = self._score_automatic_rally(df, idx, support)
        lps = self._score_last_point_of_support(df, idx, support)
        lpsy = self._score_last_point_of_supply(df, idx, resistance)
        st = self._score_secondary_test(df, idx, support)

        raw_phase_score = stopping * 0.20 + absorption * 0.20 + spring * 0.35 + sos * 0.25
        wyckoff_score = self._clamp(raw_phase_score * 0.70 + resistance_result["score"] * 0.10 + resolution_result["score"] * 0.10 + survival * 0.10)

        if sos >= 70:
            phase = "PHASE_D_E_SIGN_OF_STRENGTH"
        elif spring >= 70:
            phase = "PHASE_C_SPRING"
        elif absorption >= 60:
            phase = "PHASE_B_CAUSE_BUILDING"
        elif stopping >= 60:
            phase = "PHASE_A_STOPPING_ACTION"
        else:
            phase = "UNCONFIRMED"

        if wyckoff_score >= 80:
            verdict = "STRONG_ACCUMULATION"
        elif wyckoff_score >= 65:
            verdict = "EMERGING_ACCUMULATION"
        elif wyckoff_score >= 45:
            verdict = "WATCH"
        else:
            verdict = "NO_ACCUMULATION"

        explanation = (
            f"Wyckoff verdict {verdict}; phase {phase}; stopping={stopping}, "
            f"absorption={absorption}, spring={spring}, SOS={sos}; "
            f"resistance={resistance_result['score']}, resolution={resolution_result['score']}, survival={survival}."
        )

        return WyckoffVerdict(
            symbol=symbol.upper(),
            wyckoff_score=wyckoff_score,
            verdict=verdict,
            phase=phase,
            birth_eligible=verdict in {"STRONG_ACCUMULATION", "EMERGING_ACCUMULATION"},
            stopping_climax_score=stopping,
            supply_absorption_score=absorption,
            spring_score=spring,
            sign_of_strength_score=sos,
            meaningful_resistance_score=resistance_result["score"],
            behavioral_resolution_score=resolution_result["score"],
            survival_score=survival,
            resistance_level=round(float(resistance), 4),
            support_level=round(float(support), 4),
            cause_width_pct=resistance_result["cause_width_pct"],
            progress_against_resistance=resolution_result["progress_against_resistance"],
            explanation=explanation,
            as_of=datetime.now(timezone.utc).isoformat(),
            upthrust_score=upthrust,
            trend_context=trend_context,
            sign_of_weakness_score=sow,
            automatic_rally_score=ar_result["score"],
            ar_high=ar_result["ar_high"],
            ar_low=ar_result["ar_low"],
            last_point_of_support_score=lps,
            last_point_of_supply_score=lpsy,
            secondary_test_score=st,
        ).to_dict()

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper()
        bars = record.get("bars")
        if not bars:
            return {
                "symbol": symbol,
                "wyckoff_score": 0.0,
                "verdict": "NO_BARS",
                "phase": "UNKNOWN",
                "birth_eligible": False,
                "explanation": "Record does not contain bars.",
                "as_of": datetime.now(timezone.utc).isoformat(),
            }
        return self.evaluate_bars(pd.DataFrame(bars), symbol=symbol)


def calculate_wyckoff_accumulation_score(df: pd.DataFrame) -> pd.DataFrame:
    engine = WyckoffVerdictEngine()
    prepared = engine._prepare(df)
    prepared["WY_stopping_climax"] = 0
    prepared["WY_supply_absorption"] = 0
    prepared["WY_spring_bear_trap"] = 0
    prepared["WY_sign_of_strength"] = 0
    prepared["WYCKOFF_ACCUMULATION_SCORE_PCT"] = 0.0

    for i in range(engine.structure_lookback, len(prepared)):
        bounds = engine._structure_bounds(prepared, i)
        if bounds["support"] is None or bounds["resistance"] is None:
            continue
        support = bounds["support"]
        resistance = bounds["resistance"]
        stopping = engine._score_stopping_climax(prepared, i, support)
        absorption = engine._score_supply_absorption(prepared, i, support, resistance)
        spring = engine._score_spring(prepared, i, support)
        sos = engine._score_sign_of_strength(prepared, i, resistance)
        prepared.at[prepared.index[i], "WY_stopping_climax"] = int(stopping >= 70)
        prepared.at[prepared.index[i], "WY_supply_absorption"] = int(absorption >= 70)
        prepared.at[prepared.index[i], "WY_spring_bear_trap"] = int(spring >= 70)
        prepared.at[prepared.index[i], "WY_sign_of_strength"] = int(sos >= 70)
        prepared.at[prepared.index[i], "WYCKOFF_ACCUMULATION_SCORE_PCT"] = (
            prepared.at[prepared.index[i], "WY_stopping_climax"] * 20
            + prepared.at[prepared.index[i], "WY_supply_absorption"] * 20
            + prepared.at[prepared.index[i], "WY_spring_bear_trap"] * 35
            + prepared.at[prepared.index[i], "WY_sign_of_strength"] * 25
        )

    return prepared[
        [
            "WY_stopping_climax",
            "WY_supply_absorption",
            "WY_spring_bear_trap",
            "WY_sign_of_strength",
            "WYCKOFF_ACCUMULATION_SCORE_PCT",
        ]
    ]


def run_wyckoff_verdict(record: Dict[str, Any]) -> Dict[str, Any]:
    return WyckoffVerdictEngine().evaluate_record(record)


__all__ = [
    "WyckoffVerdictEngine",
    "WyckoffVerdict",
    "calculate_wyckoff_accumulation_score",
    "run_wyckoff_verdict",
]
