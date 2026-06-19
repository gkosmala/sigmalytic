
"""
SAVE AS:
operator_dominance/operator_flow_tracker.py

Tracks operator dominance changes through time.
"""

from typing import Dict, Any, List


class OperatorFlowTracker:

    def calculate_trend(
        self,
        ods_history: List[float],
    ) -> Dict[str, Any]:

        if len(ods_history) < 2:
            return {
                "trend": "INSUFFICIENT_DATA",
                "slope": 0.0,
            }

        slope = (
            ods_history[-1]
            - ods_history[0]
        )

        if slope > 0.05:
            trend = "OPERATOR_ACCUMULATING"

        elif slope < -0.05:
            trend = "OPERATOR_DISTRIBUTING"

        else:
            trend = "NEUTRAL"

        return {
            "trend": trend,
            "slope": round(
                slope,
                4,
            ),
            "current_ods": round(
                ods_history[-1],
                4,
            ),
        }

    def compare(
        self,
        previous_ods: float,
        current_ods: float,
    ) -> Dict[str, Any]:

        delta = (
            current_ods
            - previous_ods
        )

        return {
            "delta": round(
                delta,
                4,
            ),
            "strengthening": delta > 0,
            "weakening": delta < 0,
        }

