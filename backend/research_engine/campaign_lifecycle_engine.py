
"""
SAVE AS:
research_engine/campaign_lifecycle_engine.py

Master lifecycle controller.

Orchestrates:
- Birth
- Confirmation
- Expansion
- Distribution Risk
"""

from typing import Dict, Any


class CampaignLifecycleEngine:

    def determine_state(
        self,
        birth_qualified: bool,
        confirmed: bool,
        expanding: bool,
        distribution_risk: bool,
    ) -> Dict[str, Any]:

        if distribution_risk:
            state = "DISTRIBUTION_RISK"

        elif expanding:
            state = "EXPANDING"

        elif confirmed:
            state = "CONFIRMED"

        elif birth_qualified:
            state = "BIRTH"

        else:
            state = "OBSERVATION"

        return {
            "campaign_state": state,
        }

    def evaluate(
        self,
        birth_result: Dict[str, Any],
        confirmation_result: Dict[str, Any],
        expansion_result: Dict[str, Any],
        distribution_result: Dict[str, Any],
    ) -> Dict[str, Any]:

        state = self.determine_state(
            birth_qualified=birth_result.get(
                "qualified",
                False,
            ),
            confirmed=confirmation_result.get(
                "confirmed",
                False,
            ),
            expanding=expansion_result.get(
                "expanding",
                False,
            ),
            distribution_risk=distribution_result.get(
                "distribution_risk",
                False,
            ),
        )

        return {
            **state,
            "birth": birth_result,
            "confirmation": confirmation_result,
            "expansion": expansion_result,
            "distribution": distribution_result,
        }
