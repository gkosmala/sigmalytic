
"""
SAVE AS:
research_engine/campaign_distribution_engine.py

Campaign Distribution Engine

Detects deterioration of campaign quality and
transition toward distribution risk.
"""

from typing import Dict, Any


class CampaignDistributionEngine:

    def evaluate(
        self,
        campaign_state: str,
        csd_score: float,
        ods_score: float,
        ucr_score: float,
        spd: bool,
        dei: bool,
    ) -> Dict[str, Any]:

        campaign_state = campaign_state.upper()

        distribution_risk = (
            csd_score < 0.20
            or ucr_score < 50
            or (not dei and not spd)
        )

        if distribution_risk:
            new_state = "DISTRIBUTION_RISK"
            classification = "OPERATOR_EXITING"
        else:
            new_state = campaign_state
            classification = "CAMPAIGN_INTACT"

        return {
            "distribution_risk": distribution_risk,
            "state": new_state,
            "classification": classification,
            "csd_score": csd_score,
            "ods_score": ods_score,
            "ucr_score": ucr_score,
        }
