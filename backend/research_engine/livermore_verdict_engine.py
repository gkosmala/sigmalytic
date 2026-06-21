"""
SAVE AS:
backend/research_engine/livermore_verdict_engine.py

Sigmalytic V2
Livermore Emerging Campaign Verdict Engine

Measures:
- Operator Persistence
- Progressive Advancement
- Failure Frequency
- Campaign Continuity

Purpose:
Measure campaign emergence and campaign quality from
price/volume behavior, not from existing scores.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any

import pandas as pd
import numpy as np


@dataclass
class LivermoreVerdict:
    symbol: str
    livermore_score: float
    verdict: str
    birth_eligible: bool

    operator_persistence: float
    progressive_advancement: float
    failure_frequency: float
    campaign_continuity: float

    explanation: str
    as_of: str

    def to_dict(self):
        return asdict(self)


class LivermoreVerdictEngine:

    def __init__(self,
                 atr_period: int = 14,
                 vol_period: int = 20,
                 structure_window: int = 50):
        self.atr_period = atr_period
        self.vol_period = vol_period
        self.structure_window = structure_window

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:

        df = df.copy()

        df["vol_sma"] = df["volume"].rolling(self.vol_period).mean()

        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift()).abs()
        tr3 = (df["low"] - df["close"].shift()).abs()

        df["atr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1).rolling(
            self.atr_period
        ).mean()

        return df

    def operator_persistence_score(self, df: pd.DataFrame) -> float:

        recent = df.tail(20)

        score = 0

        absorption = (
            (recent["volume"] > recent["vol_sma"] * 1.5)
            &
            (recent["close"] >
             recent["low"] +
             ((recent["high"] - recent["low"]) * 0.50))
        )

        score += min(100, absorption.sum() * 15)

        return float(score)

    def progressive_advancement_score(self, df: pd.DataFrame) -> float:

        recent = df.tail(30)

        lows = recent["low"].tail(10).values

        score = 0

        higher_lows = 0

        for i in range(1, len(lows)):
            if lows[i] > lows[i - 1]:
                higher_lows += 1

        score += min(100, higher_lows * 10)

        breakout = recent["close"].iloc[-1] > recent["high"].tail(20).max() * 0.995

        if breakout:
            score += 20

        return min(score, 100)

    def failure_frequency_score(self, df: pd.DataFrame) -> float:

        recent = df.tail(30)

        support = recent["low"].tail(20).min()

        failures = (
            (recent["low"] < support)
            &
            (recent["close"] > support)
        ).sum()

        return min(100, failures * 20)

    def campaign_continuity_score(self,
                                  df: pd.DataFrame,
                                  sister_df: pd.DataFrame | None = None) -> float:

        if sister_df is None:
            trend = (
                df["close"].tail(20).iloc[-1]
                >
                df["close"].tail(20).mean()
            )
            return 70.0 if trend else 30.0

        merged = pd.DataFrame({
            "leader": df["close"],
            "sister": sister_df["close"]
        }).dropna()

        if len(merged) < 20:
            return 0.0

        corr = merged["leader"].tail(20).corr(
            merged["sister"].tail(20)
        )

        corr = 0 if pd.isna(corr) else corr

        return max(0, min(100, corr * 100))

    def evaluate(self,
                 df: pd.DataFrame,
                 symbol: str = "",
                 sister_df: pd.DataFrame | None = None) -> Dict[str, Any]:

        df = self._prepare(df)

        op = self.operator_persistence_score(df)
        adv = self.progressive_advancement_score(df)
        fail = self.failure_frequency_score(df)
        cont = self.campaign_continuity_score(df, sister_df)

        score = (
            op * 0.25 +
            adv * 0.30 +
            fail * 0.20 +
            cont * 0.25
        )

        if score >= 80:
            verdict = "CAMPAIGN_BIRTH"
        elif score >= 65:
            verdict = "CAMPAIGN_BUILDING"
        elif score >= 45:
            verdict = "CAMPAIGN_HOLDING"
        else:
            verdict = "CAMPAIGN_FAILURE"

        return LivermoreVerdict(
            symbol=symbol,
            livermore_score=round(score, 2),
            verdict=verdict,
            birth_eligible=verdict in [
                "CAMPAIGN_BIRTH",
                "CAMPAIGN_BUILDING"
            ],
            operator_persistence=round(op, 2),
            progressive_advancement=round(adv, 2),
            failure_frequency=round(fail, 2),
            campaign_continuity=round(cont, 2),
            explanation=(
                f"Persistence={op:.1f}, "
                f"Advancement={adv:.1f}, "
                f"FailureFreq={fail:.1f}, "
                f"Continuity={cont:.1f}"
            ),
            as_of=datetime.now(timezone.utc).isoformat()
        ).to_dict()


def run_livermore_verdict(record: Dict[str, Any]):

    bars = record.get("bars", [])
    symbol = record.get("symbol", "")

    sister = record.get("sister_bars")

    sister_df = None

    if sister:
        sister_df = pd.DataFrame(sister)

    return LivermoreVerdictEngine().evaluate(
        pd.DataFrame(bars),
        symbol=symbol,
        sister_df=sister_df
    )
