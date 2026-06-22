"""
SAVE AS:
backend/research_engine/wyckoff_survival_engine.py

Sigmalytic V2
Wyckoff Campaign Survival Engine

Purpose:
Measure whether a potential Wyckoff accumulation campaign is surviving after birth.

Measures:
1. SOS Persistence
2. LPS Quality
3. Range Escape Stability
4. Absorption Continuation
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class WyckoffSurvivalVerdict:
    symbol: str
    wyckoff_survival_score: float
    survival_grade: str
    survival_state: str
    survival_confirmed: bool
    sos_persistence_score: float
    lps_quality_score: float
    range_escape_stability_score: float
    absorption_continuation_score: float
    support_level: Optional[float]
    resistance_level: Optional[float]
    current_close: Optional[float]
    explanation: str
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WyckoffSurvivalEngine:
    REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}

    def __init__(
        self,
        lookback: int = 60,
        survival_window: int = 30,
        vol_sma_period: int = 20,
        atr_period: int = 14,
    ):
        self.lookback = lookback
        self.survival_window = survival_window
        self.vol_sma_period = vol_sma_period
        self.atr_period = atr_period

    @staticmethod
    def _safe_score(value: Any) -> float:
        try:
            value = float(value)
            if value < 0:
                return 0.0
            if value > 100:
                return 100.0
            return round(value, 2)
        except Exception:
            return 0.0

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 90:
            return "A+"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 60:
            return "C"
        if score >= 50:
            return "D"
        return "F"

    @staticmethod
    def _state(score: float) -> str:
        if score >= 80:
            return "STRONG_SURVIVAL"
        if score >= 70:
            return "SURVIVING"
        if score >= 60:
            return "MARGINAL_SURVIVAL"
        if score >= 50:
            return "AT_RISK"
        return "FAILURE_RISK"

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"Missing required OHLCV column: {col}")
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close", "volume"])

        df["vol_sma"] = df["volume"].rolling(self.vol_sma_period).mean()
        df["spread"] = df["high"] - df["low"]
        df["spread_sma"] = df["spread"].rolling(self.vol_sma_period).mean()
        df["close_pct_of_range"] = (
            (df["close"] - df["low"])
            / df["spread"].replace(0, np.nan)
        ).fillna(0.5)

        high_low = df["high"] - df["low"]
        high_cp = (df["high"] - df["close"].shift(1)).abs()
        low_cp = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
        df["atr"] = tr.rolling(self.atr_period).mean()

        return df

    def _levels(self, df: pd.DataFrame) -> Dict[str, Optional[float]]:
        if len(df) < self.lookback + 1:
            return {"support": None, "resistance": None}

        prior = df.iloc[:-1]
        window = prior.tail(self.lookback)

        return {
            "support": float(window["low"].min()),
            "resistance": float(window["high"].max()),
        }

    def score_sos_persistence(self, df: pd.DataFrame, resistance: float) -> float:
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        closes_above = (recent["close"] > resistance).sum()
        lows_hold_zone = (recent["low"] >= resistance * 0.97).sum()
        closes_upper_half = (recent["close_pct_of_range"] >= 0.50).sum()

        close_score = closes_above / len(recent) * 100.0
        hold_score = lows_hold_zone / len(recent) * 100.0
        quality_score = closes_upper_half / len(recent) * 100.0

        return self._safe_score(close_score * 0.45 + hold_score * 0.35 + quality_score * 0.20)

    def score_lps_quality(self, df: pd.DataFrame, resistance: float) -> float:
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        down_days = recent[recent["close"] < recent["open"]]

        if down_days.empty:
            return 70.0

        pullbacks_hold = (
            (down_days["low"] >= resistance * 0.96)
            & (down_days["close"] >= resistance * 0.97)
        ).sum()

        lower_volume_reactions = (down_days["volume"] < down_days["vol_sma"]).sum()

        shallow_reactions = (
            (down_days["high"] - down_days["low"]) <= 1.25 * down_days["atr"]
        ).sum()

        n = max(1, len(down_days))

        return self._safe_score(
            (pullbacks_hold / n * 100.0) * 0.45
            + (lower_volume_reactions / n * 100.0) * 0.35
            + (shallow_reactions / n * 100.0) * 0.20
        )

    def score_range_escape_stability(self, df: pd.DataFrame, support: float, resistance: float) -> float:
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        current_close = float(recent["close"].iloc[-1])
        days_above_resistance = (recent["close"] > resistance).sum()
        days_below_midrange = (recent["close"] < ((support + resistance) / 2.0)).sum()
        decisive_failures = (recent["close"] < support).sum()

        above_score = days_above_resistance / len(recent) * 100.0
        failure_penalty = min(100.0, decisive_failures * 25.0)
        midrange_penalty = min(40.0, days_below_midrange / len(recent) * 40.0)

        if current_close > resistance:
            position_score = 100.0
        elif current_close > (support + resistance) / 2.0:
            position_score = 70.0
        else:
            position_score = 30.0

        return self._safe_score(
            above_score * 0.45
            + position_score * 0.35
            + (100.0 - failure_penalty - midrange_penalty) * 0.20
        )

    def score_absorption_continuation(self, df: pd.DataFrame) -> float:
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        down_days = recent[recent["close"] < recent["open"]]
        up_days = recent[recent["close"] >= recent["open"]]

        if down_days.empty:
            return 75.0

        down_volume_avg = float(down_days["volume"].mean())
        up_volume_avg = float(up_days["volume"].mean()) if not up_days.empty else down_volume_avg

        supply_drying = down_volume_avg < float(recent["vol_sma"].mean())
        demand_dominates = up_volume_avg >= down_volume_avg

        narrow_down_spreads = (down_days["spread"] <= down_days["spread_sma"]).sum()
        constructive_down_closes = (down_days["close_pct_of_range"] >= 0.40).sum()

        n = max(1, len(down_days))

        score = 0.0
        if supply_drying:
            score += 30.0
        if demand_dominates:
            score += 25.0

        score += min(25.0, narrow_down_spreads / n * 25.0)
        score += min(20.0, constructive_down_closes / n * 20.0)

        return self._safe_score(score)

    def evaluate_bars(self, df: pd.DataFrame, symbol: str = "") -> Dict[str, Any]:
        symbol = str(symbol or "").upper()

        if df is None or len(df) == 0:
            return WyckoffSurvivalVerdict(
                symbol=symbol,
                wyckoff_survival_score=0.0,
                survival_grade="F",
                survival_state="NO_BARS",
                survival_confirmed=False,
                sos_persistence_score=0.0,
                lps_quality_score=0.0,
                range_escape_stability_score=0.0,
                absorption_continuation_score=0.0,
                support_level=None,
                resistance_level=None,
                current_close=None,
                explanation="No OHLCV bars supplied.",
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        df = self._prepare(df)

        if len(df) < self.lookback + 10:
            return WyckoffSurvivalVerdict(
                symbol=symbol,
                wyckoff_survival_score=0.0,
                survival_grade="F",
                survival_state="INSUFFICIENT_DATA",
                survival_confirmed=False,
                sos_persistence_score=0.0,
                lps_quality_score=0.0,
                range_escape_stability_score=0.0,
                absorption_continuation_score=0.0,
                support_level=None,
                resistance_level=None,
                current_close=None,
                explanation="Insufficient bars for Wyckoff survival evaluation.",
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        levels = self._levels(df)
        support = levels["support"]
        resistance = levels["resistance"]

        if support is None or resistance is None or resistance <= support:
            return WyckoffSurvivalVerdict(
                symbol=symbol,
                wyckoff_survival_score=0.0,
                survival_grade="F",
                survival_state="NO_MEANINGFUL_STRUCTURE",
                survival_confirmed=False,
                sos_persistence_score=0.0,
                lps_quality_score=0.0,
                range_escape_stability_score=0.0,
                absorption_continuation_score=0.0,
                support_level=None,
                resistance_level=None,
                current_close=round(float(df["close"].iloc[-1]), 4),
                explanation="No meaningful support/resistance range available.",
                as_of=datetime.now(timezone.utc).isoformat(),
            ).to_dict()

        sos = self.score_sos_persistence(df, resistance)
        lps = self.score_lps_quality(df, resistance)
        range_stability = self.score_range_escape_stability(df, support, resistance)
        absorption = self.score_absorption_continuation(df)

        survival_score = self._safe_score(
            sos * 0.30
            + lps * 0.25
            + range_stability * 0.25
            + absorption * 0.20
        )

        grade = self._grade(survival_score)
        state = self._state(survival_score)
        confirmed = survival_score >= 70.0

        explanation = (
            f"Wyckoff Survival {state}; score={survival_score}; "
            f"SOS={sos}, LPS={lps}, range_escape={range_stability}, absorption={absorption}."
        )

        return WyckoffSurvivalVerdict(
            symbol=symbol,
            wyckoff_survival_score=survival_score,
            survival_grade=grade,
            survival_state=state,
            survival_confirmed=confirmed,
            sos_persistence_score=sos,
            lps_quality_score=lps,
            range_escape_stability_score=range_stability,
            absorption_continuation_score=absorption,
            support_level=round(float(support), 4),
            resistance_level=round(float(resistance), 4),
            current_close=round(float(df["close"].iloc[-1]), 4),
            explanation=explanation,
            as_of=datetime.now(timezone.utc).isoformat(),
        ).to_dict()

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper()
        bars = record.get("bars")

        if not bars:
            return {
                "symbol": symbol,
                "wyckoff_survival_score": 0.0,
                "survival_grade": "F",
                "survival_state": "NO_BARS",
                "survival_confirmed": False,
                "explanation": "Record does not contain bars.",
                "as_of": datetime.now(timezone.utc).isoformat(),
            }

        return self.evaluate_bars(pd.DataFrame(bars), symbol=symbol)


def run_wyckoff_survival(record: Dict[str, Any]) -> Dict[str, Any]:
    return WyckoffSurvivalEngine().evaluate_record(record)


__all__ = [
    "WyckoffSurvivalEngine",
    "WyckoffSurvivalVerdict",
    "run_wyckoff_survival",
]
