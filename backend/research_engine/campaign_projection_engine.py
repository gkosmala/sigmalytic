
"""
SAVE AS:
research_engine/campaign_projection_engine.py

Campaign Projection Engine

Combines:
- Point & Figure targets
- UCR
- Campaign State
- Survival Score

Produces projected outcome profile.
"""

from typing import Dict, Any


class CampaignProjectionEngine:

    def project(
        self,
        current_price: float,
        conservative_target: float,
        aggressive_target: float,
        ucr_score: float,
        survival_score: float,
        campaign_state: str,
    ) -> Dict[str, Any]:

        conservative_return = (
            (conservative_target - current_price)
            / current_price
        ) * 100.0

        aggressive_return = (
            (aggressive_target - current_price)
            / current_price
        ) * 100.0

        if (
            ucr_score >= 80
            and survival_score >= 0.50
        ):
            confidence = "HIGH"

        elif (
            ucr_score >= 50
        ):
            confidence = "MEDIUM"

        else:
            confidence = "LOW"

        return {
            "campaign_state": campaign_state,
            "confidence": confidence,
            "ucr_score": round(
                ucr_score,
                2,
            ),
            "survival_score": round(
                survival_score,
                4,
            ),
            "conservative_target": round(
                conservative_target,
                4,
            ),
            "aggressive_target": round(
                aggressive_target,
                4,
            ),
            "conservative_return_pct": round(
                conservative_return,
                2,
            ),
            "aggressive_return_pct": round(
                aggressive_return,
                2,
            ),
        }

