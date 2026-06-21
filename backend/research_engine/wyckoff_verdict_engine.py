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

    def _score_spring(self, df: pd.DataFrame, idx: int, support: float) -> float:
        row = df.iloc[idx]
        score = 0
        if row["low"] < 0.995 * support:
            score += 30
        if row["close"] > support:
            score += 35
        if row["volume"] >= 1.5 * row["vol_sma"]:
            score += 20
        if row["close_pct_of_range"] >= 0.50:
            score += 15
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
        spring = self._score_spring(df, idx, support)
        sos = self._score_sign_of_strength(df, idx, resistance)
        resistance_result = self._score_meaningful_resistance(current_close, support, resistance)
        resolution_result = self._score_behavioral_resolution(df, idx, resistance)
        survival = self._score_survival(df, idx)

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
