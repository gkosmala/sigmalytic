"""
SAVE AS:
backend/research_engine/weis_survival_engine.py

Sigmalytic V2
David Weis Campaign Survival Engine

Purpose:
Measure whether a Weis campaign continues to survive
AFTER initial campaign emergence.

Focus:
1. SOT Persistence
2. Selling Exhaustion Persistence
3. Demand Wave Dominance
4. Effort vs Result Integrity
5. Wave Structure Continuity
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict

import numpy as np
import pandas as pd


@dataclass
class WeisSurvivalVerdict:
    symbol: str

    weis_survival_score: float
    survival_grade: str
    survival_state: str
    survival_confirmed: bool

    sot_persistence_score: float
    selling_exhaustion_score: float
    demand_dominance_score: float
    effort_result_score: float
    wave_continuity_score: float

    explanation: str
    as_of: str

    def to_dict(self):
        return asdict(self)


class WeisSurvivalEngine:

    REQUIRED_COLUMNS = {
        "open",
        "high",
        "low",
        "close",
        "volume",
    }

    def __init__(
        self,
        wave_window=20,
        survival_window=40,
    ):
        self.wave_window = wave_window
        self.survival_window = survival_window

    @staticmethod
    def _safe_score(v):
        try:
            return round(max(0.0, min(100.0, float(v))), 2)
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

        for col in self.REQUIRED_COLUMNS:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df = df.dropna()

        df["spread"] = (
            df["high"] - df["low"]
        )

        df["direction"] = np.where(
            df["close"] >= df["open"],
            1,
            -1,
        )

        return df

    def score_sot_persistence(self, df):
        recent = df.tail(self.survival_window)

        down_bars = recent[
            recent["direction"] < 0
        ]

        if len(down_bars) < 5:
            return 50.0

        thrust = (
            down_bars["high"] -
            down_bars["low"]
        )

        first = thrust.head(
            max(1, len(thrust)//2)
        ).mean()

        second = thrust.tail(
            max(1, len(thrust)//2)
        ).mean()

        if second < first:
            reduction = (
                (first - second)
                / max(first, 0.0001)
            )
            return self._safe_score(
                reduction * 100
            )

        return 20.0

    def score_selling_exhaustion(self, df):
        recent = df.tail(self.survival_window)

        down = recent[
            recent["direction"] < 0
        ]

        if len(down) < 5:
            return 50.0

        first = down.head(
            max(1, len(down)//2)
        )["volume"].mean()

        second = down.tail(
            max(1, len(down)//2)
        )["volume"].mean()

        if second < first:
            reduction = (
                (first - second)
                / max(first, 1)
            )

            return self._safe_score(
                reduction * 100
            )

        return 20.0

    def score_demand_dominance(self, df):
        recent = df.tail(self.survival_window)

        up = recent[
            recent["direction"] > 0
        ]

        down = recent[
            recent["direction"] < 0
        ]

        if len(up) == 0 or len(down) == 0:
            return 50.0

        up_volume = up["volume"].mean()
        down_volume = down["volume"].mean()

        if up_volume <= 0:
            return 0.0

        ratio = (
            up_volume /
            max(down_volume, 1)
        )

        return self._safe_score(
            min(100.0, ratio * 50)
        )

    def score_effort_vs_result(self, df):
        recent = df.tail(self.survival_window)

        up = recent[
            recent["direction"] > 0
        ]

        if len(up) < 5:
            return 50.0

        effort = up["volume"].sum()

        result = (
            up["close"].iloc[-1]
            -
            up["close"].iloc[0]
        )

        if effort <= 0:
            return 0.0

        efficiency = (
            result /
            effort
        )

        normalized = (
            efficiency * 100000
        )

        return self._safe_score(
            normalized
        )

    def score_wave_continuity(self, df):
        recent = df.tail(self.survival_window)

        closes = recent["close"]

        higher_closes = (
            closes.diff() > 0
        ).sum()

        continuity = (
            higher_closes /
            len(closes)
        ) * 100

        return self._safe_score(
            continuity
        )

    def evaluate_bars(
        self,
        df,
        symbol=""
    ):
        symbol = str(symbol).upper()

        df = self._prepare(df)

        sot = self.score_sot_persistence(df)

        exhaustion = self.score_selling_exhaustion(df)

        demand = self.score_demand_dominance(df)

        effort = self.score_effort_vs_result(df)

        continuity = self.score_wave_continuity(df)

        score = self._safe_score(
            sot * 0.25 +
            exhaustion * 0.20 +
            demand * 0.25 +
            effort * 0.15 +
            continuity * 0.15
        )

        return WeisSurvivalVerdict(
            symbol=symbol,

            weis_survival_score=score,

            survival_grade=self._grade(score),

            survival_state=self._state(score),

            survival_confirmed=(
                score >= 70
            ),

            sot_persistence_score=sot,

            selling_exhaustion_score=exhaustion,

            demand_dominance_score=demand,

            effort_result_score=effort,

            wave_continuity_score=continuity,

            explanation=(
                f"SOT={sot}, "
                f"Exhaustion={exhaustion}, "
                f"Demand={demand}, "
                f"EffortResult={effort}, "
                f"Continuity={continuity}"
            ),

            as_of=datetime.now(
                timezone.utc
            ).isoformat(),
        ).to_dict()


def run_weis_survival(
    record
):
    engine = WeisSurvivalEngine()

    return engine.evaluate_bars(
        pd.DataFrame(
            record["bars"]
        ),
        symbol=record.get(
            "symbol",
            ""
        ),
    )


__all__ = [
    "WeisSurvivalEngine",
    "WeisSurvivalVerdict",
    "run_weis_survival",
]
