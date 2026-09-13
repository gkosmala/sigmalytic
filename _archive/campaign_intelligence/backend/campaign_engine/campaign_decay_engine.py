
"""
SAVE AS:
campaign_engine/campaign_decay_engine.py
"""

import math
from typing import Dict, Any


class CampaignDecayEngine:
    """
    Campaign Survival & Decay Engine (CSD)
    """

    def __init__(
        self,
        decay_lambda: float = 0.015,
    ):
        self.decay_lambda = decay_lambda

    def calculate_csd(
        self,
        current_price: float,
        sc_low: float,
        ar_high: float,
        bars_elapsed: int,
    ) -> float:

        range_width = ar_high - sc_low

        if range_width <= 0:
            return 0.0

        position_ratio = (
            current_price - sc_low
        ) / range_width

        decay = math.exp(
            -self.decay_lambda * bars_elapsed
        )

        score = position_ratio * decay

        return round(
            max(0.0, min(score, 1.5)),
            4,
        )

    def evaluate(
        self,
        current_price: float,
        sc_low: float,
        ar_high: float,
        bars_elapsed: int,
    ) -> Dict[str, Any]:

        csd = self.calculate_csd(
            current_price=current_price,
            sc_low=sc_low,
            ar_high=ar_high,
            bars_elapsed=bars_elapsed,
        )

        if csd < 0.20:
            status = "DECAIED_HIGH_RISK"
        elif csd < 0.50:
            status = "WEAKENING"
        else:
            status = "SURVIVING"

        return {
            "csd_score": csd,
            "status": status,
        }

