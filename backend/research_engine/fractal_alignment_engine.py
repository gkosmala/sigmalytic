
"""
SAVE AS:
research_engine/fractal_alignment_engine.py

Multi-Timeframe Alignment (MTA) Engine

Measures alignment between a selected execution
timeframe and higher-order campaign structures.
"""

from typing import Dict, Any, List


class FractalAlignmentEngine:

    def calculate_mta(
        self,
        macro_states: List[Dict[str, Any]],
    ) -> Dict[str, Any]:

        if not macro_states:
            return {
                "mta_score": 0.0,
                "aligned": False,
            }

        score = 0.0

        for state in macro_states:

            direction = str(
                state.get(
                    "state",
                    ""
                )
            ).upper()

            weight = float(
                state.get(
                    "weight",
                    0.0
                )
            )

            if direction in [
                "ACCUMULATION",
                "MARKUP",
                "SURVIVING",
                "EXPANDING",
            ]:
                score += weight

            elif direction in [
                "DISTRIBUTION",
                "MARKDOWN",
                "FAILED",
            ]:
                score -= weight

        score = round(
            max(-1.0, min(score, 1.0)),
            4,
        )

        return {
            "mta_score": score,
            "aligned": score >= 0.60,
        }

    def classify(
        self,
        mta_score: float,
    ) -> str:

        if mta_score >= 0.60:
            return "STRONGLY_ALIGNED"

        if mta_score >= 0.30:
            return "PARTIALLY_ALIGNED"

        if mta_score <= -0.30:
            return "CONFLICTED"

        return "NEUTRAL"
