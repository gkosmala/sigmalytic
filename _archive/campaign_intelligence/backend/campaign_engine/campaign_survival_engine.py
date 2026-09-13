
"""
SAVE AS:
campaign_engine/campaign_survival_engine.py

Campaign survival monitoring engine.
"""

import math
from typing import Dict, Any


class CampaignSurvivalEngine:

    def __init__(
        self,
        decay_lambda: float = 0.015,
    ):
        self.decay_lambda = decay_lambda

    def survival_score(
        self,
        current_price: float,
        sc_low: float,
        ar_high: float,
        bars_elapsed: int,
    ) -> float:

        width = ar_high - sc_low

        if width <= 0:
            return 0.0

        position_ratio = (
            current_price - sc_low
        ) / width

        decay_factor = math.exp(
            -self.decay_lambda * bars_elapsed
        )

        score = position_ratio * decay_factor

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

        score = self.survival_score(
            current_price=current_price,
            sc_low=sc_low,
            ar_high=ar_high,
            bars_elapsed=bars_elapsed,
        )

        if score >= 0.75:
            classification = "STRONG_SURVIVAL"
        elif score >= 0.50:
            classification = "SURVIVING"
        elif score >= 0.20:
            classification = "WEAKENING"
        else:
            classification = "DECAIED_HIGH_RISK"

        return {
            "survival_score": score,
            "classification": classification,
        }

