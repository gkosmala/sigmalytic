
"""SAVE AS: campaign_engine/operator_dominance_engine.py"""

import pandas as pd


class OperatorDominanceEngine:

    def calculate(
        self,
        df: pd.DataFrame,
    ) -> float:

        if len(df) < 20:
            return 0.0

        volume_ma = df["volume"].rolling(20).mean()

        institutional = (
            df["volume"] > volume_ma * 2.0
        )

        total_volume = df["volume"].sum()

        if total_volume <= 0:
            return 0.0

        return round(
            df.loc[institutional, "volume"].sum()
            / total_volume,
            4,
        )

