
"""
SAVE AS:
operator_dominance/operator_control_classifier.py

Classifies operator control regime.
"""

from typing import Dict, Any


class OperatorControlClassifier:

    def classify(
        self,
        ods_score: float,
        ods_trend: str,
        campaign_state: str,
    ) -> Dict[str, Any]:

        campaign_state = str(
            campaign_state
        ).upper()

        if (
            ods_score >= 0.35
            and ods_trend == "OPERATOR_ACCUMULATING"
        ):
            control = "ACCUMULATION_CONTROL"

        elif (
            ods_score >= 0.35
            and campaign_state in [
                "EXPANDING",
                "MATURING",
            ]
        ):
            control = "MARKUP_CONTROL"

        elif (
            ods_trend == "OPERATOR_DISTRIBUTING"
        ):
            control = "DISTRIBUTION_CONTROL"

        elif (
            ods_score < 0.20
            and campaign_state in [
                "FAILED",
                "DISTRIBUTION_RISK",
            ]
        ):
            control = "MARKDOWN_CONTROL"

        else:
            control = "NEUTRAL_CONTROL"

        return {
            "control_regime": control,
            "ods_score": round(
                ods_score,
                4,
            ),
            "campaign_state": campaign_state,
        }
