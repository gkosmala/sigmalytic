
"""
SAVE AS:
research_engine/campaign_confirmation_engine.py

Campaign Confirmation Engine

Promotes qualified birth candidates into
confirmed campaigns.
"""

from typing import Dict, Any


class CampaignConfirmationEngine:

    def evaluate(
        self,
        birth_qualified: bool,
        ods_score: float,
        mta_score: float,
        csd_score: float,
        wwe_ratio: float,
    ) -> Dict[str, Any]:

        confirmed = (
            birth_qualified
            and ods_score >= 0.35
            and mta_score >= 0.60
            and csd_score >= 0.20
            and wwe_ratio > 0.0
        )

        if confirmed:
            state = "CONFIRMED"
            classification = "ACTIVE_CAMPAIGN"
        else:
            state = "OBSERVATION"
            classification = "UNCONFIRMED"

        return {
            "confirmed": confirmed,
            "state": state,
            "classification": classification,
            "ods_score": ods_score,
            "mta_score": mta_score,
            "csd_score": csd_score,
            "wwe_ratio": wwe_ratio,
        }
