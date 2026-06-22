"""
SAVE AS:
backend/research_engine/livermore_survival_engine.py

Sigmalytic V2
Livermore Campaign Survival Engine

Purpose:
Measure whether a Livermore-style institutional campaign is surviving
after emergence.

Core Concepts:
1. Progressive Advancement
2. Higher Pivot Persistence
3. Normal Reaction Quality
4. Campaign Continuity
5. Group Confirmation

Livermore Principle:
A campaign survives because it continues to "act right."
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class LivermoreSurvivalVerdict:
    symbol: str

    livermore_survival_score: float
    survival_grade: str
    survival_state: str
    survival_confirmed: bool

    progressive_advancement_score: float
    higher_pivot_score: float
    normal_reaction_score: float
    campaign_continuity_score: float
    group_confirmation_score: float

    current_close: Optional[float]

    explanation: str
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LivermoreSurvivalEngine:

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
    def _safe_score(value):
        try:
            value = float(value)
            return round(max(0.0, min(100.0, value)), 2)
        except Exception:
            return 0.0

    @staticmethod
    def _grade(score):
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
    def _state(score):
        if score >= 80:
            return "STRONG_SURVIVAL"
        if score >= 70:
            return "SURVIVING"
        if score >= 60:
            return "MARGINAL_SURVIVAL"
        if score >= 50:
            return "AT_RISK"
        return "FAILURE_RISK"

    def _prepare(self, df):
        df = df.copy()

        for col in self.REQUIRED_COLUMNS:
            if col not in df.columns:
                raise ValueError(f"Missing column: {col}")

        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

        df["vol_sma"] = (
            df["volume"]
            .rolling(self.vol_sma_period)
            .mean()
        )

        df["ma20"] = df["close"].rolling(20).mean()
        df["ma50"] = df["close"].rolling(50).mean()

        return df.dropna()

    def score_progressive_advancement(self, df):
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        positive_closes = (
            recent["close"].diff() > 0
        ).sum()

        score = (
            positive_closes / len(recent)
        ) * 100.0

        return self._safe_score(score)

    def score_higher_pivots(self, df):
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        highs = recent["high"].rolling(5).max()
        lows = recent["low"].rolling(5).min()

        hh = (highs.diff() > 0).sum()
        hl = (lows.diff() > 0).sum()

        score = (
            ((hh + hl) / (2 * len(recent)))
            * 100.0
        )

        return self._safe_score(score * 2)

    def score_normal_reactions(self, df):
        recent = df.tail(self.survival_window)

        down_days = recent[
            recent["close"] < recent["open"]
        ]

        if len(down_days) == 0:
            return 80.0

        lower_volume = (
            down_days["volume"] <
            down_days["vol_sma"]
        ).sum()

        score = (
            lower_volume / len(down_days)
        ) * 100.0

        return self._safe_score(score)

    def score_campaign_continuity(self, df):
        recent = df.tail(self.survival_window)

        if len(recent) < 10:
            return 0.0

        ma20_above_ma50 = (
            recent["ma20"] > recent["ma50"]
        ).sum()

        score = (
            ma20_above_ma50 / len(recent)
        ) * 100.0

        return self._safe_score(score)

    def score_group_confirmation(
        self,
        df,
        sister_df=None,
    ):
        if sister_df is None:
            return 50.0

        try:
            merged = pd.DataFrame({
                "leader": df["close"],
                "sister": sister_df["close"],
            }).dropna()

            if len(merged) < 20:
                return 50.0

            corr = merged["leader"].pct_change().corr(
                merged["sister"].pct_change()
            )

            return self._safe_score(
                max(0.0, corr) * 100.0
            )

        except Exception:
            return 50.0

    def evaluate_bars(
        self,
        df,
        symbol="",
        sister_df=None,
    ):
        symbol = str(symbol).upper()

        df = self._prepare(df)

        if len(df) < self.lookback:
            return {
                "symbol": symbol,
                "livermore_survival_score": 0.0,
                "survival_grade": "F",
                "survival_state": "INSUFFICIENT_DATA",
                "survival_confirmed": False,
            }

        pa = self.score_progressive_advancement(df)
        hp = self.score_higher_pivots(df)
        nr = self.score_normal_reactions(df)
        cc = self.score_campaign_continuity(df)
        gc = self.score_group_confirmation(
            df,
            sister_df=sister_df,
        )

        score = self._safe_score(
            pa * 0.25 +
            hp * 0.20 +
            nr * 0.20 +
            cc * 0.20 +
            gc * 0.15
        )

        grade = self._grade(score)
        state = self._state(score)

        return LivermoreSurvivalVerdict(
            symbol=symbol,
            livermore_survival_score=score,
            survival_grade=grade,
            survival_state=state,
            survival_confirmed=score >= 70.0,

            progressive_advancement_score=pa,
            higher_pivot_score=hp,
            normal_reaction_score=nr,
            campaign_continuity_score=cc,
            group_confirmation_score=gc,

            current_close=round(
                float(df["close"].iloc[-1]),
                4,
            ),

            explanation=(
                f"Livermore Survival "
                f"{state}; "
                f"PA={pa}, "
                f"HP={hp}, "
                f"NR={nr}, "
                f"CC={cc}, "
                f"GC={gc}"
            ),

            as_of=datetime.now(
                timezone.utc
            ).isoformat(),
        ).to_dict()


def run_livermore_survival(
    record,
):
    engine = LivermoreSurvivalEngine()

    return engine.evaluate_bars(
        pd.DataFrame(
            record["bars"]
        ),
        symbol=record.get(
            "symbol",
            "",
        ),
    )


__all__ = [
    "LivermoreSurvivalEngine",
    "LivermoreSurvivalVerdict",
    "run_livermore_survival",
]
