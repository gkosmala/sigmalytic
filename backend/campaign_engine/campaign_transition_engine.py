
"""
SAVE AS:
campaign_engine/campaign_transition_engine.py

Campaign lifecycle transition controller.
"""

from typing import Dict, Any


class CampaignTransitionEngine:

    VALID_TRANSITIONS = {
        "BIRTH": ["CONFIRMED", "FAILED"],
        "CONFIRMED": ["SURVIVING", "FAILED"],
        "SURVIVING": ["EXPANDING", "DISTRIBUTION_RISK"],
        "EXPANDING": ["MATURING", "DISTRIBUTION_RISK"],
        "MATURING": ["DISTRIBUTION_RISK", "CLOSED"],
        "DISTRIBUTION_RISK": ["CLOSED", "FAILED"],
        "FAILED": [],
        "CLOSED": [],
    }

    def can_transition(
        self,
        current_state: str,
        proposed_state: str,
    ) -> bool:

        current_state = current_state.upper()
        proposed_state = proposed_state.upper()

        return proposed_state in self.VALID_TRANSITIONS.get(
            current_state,
            [],
        )

    def evaluate_transition(
        self,
        current_state: str,
        metrics: Dict[str, Any],
    ) -> str:

        ucr = float(metrics.get("ucr_score", 0))
        csd = float(metrics.get("csd_score", 0))

        current_state = current_state.upper()

        if current_state == "BIRTH" and ucr >= 50:
            return "CONFIRMED"

        if current_state == "CONFIRMED" and ucr >= 60:
            return "SURVIVING"

        if current_state == "SURVIVING" and ucr >= 80:
            return "EXPANDING"

        if current_state == "EXPANDING" and csd >= 0.75:
            return "MATURING"

        if csd < 0.20:
            return "DISTRIBUTION_RISK"

        return current_state

