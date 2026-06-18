
"""
SAVE AS:
operator_dominance/operator_dominance_engine.py

Sigmalytic V2
Operator Dominance Engine

Implements baseline ODS framework.
"""

from typing import Dict, Any
import pandas as pd


class OperatorDominanceEngine:

    def __init__(
        self,
        volume_multiplier: float = 2.0,
        spread_multiplier: float = 1.5,
        lookback: int = 20,
    ):
        self.volume_multiplier = volume_multiplier
        self.spread_multiplier = spread_multiplier
        self.lookback = lookback

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> Dict[str, Any]:

        if len(df) < self.lookback:
            return {
                "ods_score": 0.0,
                "institutional_volume": 0.0,
                "classification": "INSUFFICIENT_DATA",
            }

        volume_ma = (
            df["volume"]
            .rolling(self.lookback)
            .mean()
        )

        spread = (
            df["high"] - df["low"]
        )

        spread_ma = (
            spread
            .rolling(self.lookback)
            .mean()
        )

        institutional_mask = (
            (df["volume"] > volume_ma * self.volume_multiplier)
            &
            (spread > spread_ma * self.spread_multiplier)
        )

        institutional_volume = float(
            df.loc[
                institutional_mask,
                "volume"
            ].sum()
        )

        total_volume = float(
            df["volume"].sum()
        )

        if total_volume <= 0:
            ods = 0.0
        else:
            ods = (
                institutional_volume
                / total_volume
            )

        ods = round(ods, 4)

        if ods >= 0.35:
            classification = "OPERATOR_DOMINANT"
        elif ods >= 0.20:
            classification = "MIXED_CONTROL"
        else:
            classification = "RETAIL_DOMINANT"

        return {
            "ods_score": ods,
            "institutional_volume": institutional_volume,
            "total_volume": total_volume,
            "classification": classification,
        }
