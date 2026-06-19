
"""
SAVE AS:
research_engine/campaign_birth_engine.py

Sigmalytic V2
Campaign Birth Engine

Determines when a symbol transitions from
observation into a valid campaign candidate.
"""

from typing import Dict, Any


class CampaignBirthEngine:

    def evaluate(
        self,
        obstacle_score: float,
        progress_score: float,
        ods_score: float,
        spd: bool,
        mta_score: float,
    ) -> Dict[str, Any]:

        qualified = (
            obstacle_score >= 70
            and progress_score >= 70
            and ods_score >= 0.35
            and spd
            and mta_score >= 0.60
        )

        if qualified:
            state = "BIRTH"
            classification = "INSTITUTIONAL_ACCUMULATION_CANDIDATE"
        else:
            state = "OBSERVATION"
            classification = "UNQUALIFIED"

        return {
            "qualified": qualified,
            "state": state,
            "classification": classification,
            "obstacle_score": obstacle_score,
            "progress_score": progress_score,
            "ods_score": ods_score,
            "mta_score": mta_score,
        }

