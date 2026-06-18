
"""
SAVE AS:
research_engine/campaign_expansion_engine.py

Campaign Expansion Engine

Identifies transition from confirmed campaign
to true markup / expansion phase.
"""

from typing import Dict, Any


class CampaignExpansionEngine:

    def evaluate(
        self,
        confirmed: bool,
        ods_score: float,
        mta_score: float,
        csd_score: float,
        ucr_score: float,
        dei: bool,
    ) -> Dict[str, Any]:

        expanding = (
            confirmed
            and ods_score >= 0.35
            and mta_score >= 0.60
            and csd_score >= 0.50
            and ucr_score >= 80
            and dei
        )

        if expanding:
            state = "EXPANDING"
            classification = "MARKUP_PHASE"
        else:
            state = "CONFIRMED"
            classification = "NON_EXPANSION"

        return {
            "expanding": expanding,
            "state": state,
            "classification": classification,
            "ucr_score": ucr_score,
            "csd_score": csd_score,
        }
