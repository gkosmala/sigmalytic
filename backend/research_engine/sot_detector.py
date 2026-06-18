
"""
SAVE AS:
research_engine/sot_detector.py

Shortening Of Thrust (SOT) Detector

Detects diminishing wave progress and effort,
providing early warning of campaign exhaustion.
"""

from typing import Dict, Any, List


class SOTDetector:

    def detect(
        self,
        waves: List[Dict[str, Any]],
    ) -> Dict[str, Any]:

        if len(waves) < 3:
            return {
                "sot_alert": False,
                "confidence": "INSUFFICIENT_WAVES",
            }

        direction = waves[-1]["direction"]

        same_direction = [
            w for w in waves
            if w["direction"] == direction
        ]

        if len(same_direction) < 3:
            return {
                "sot_alert": False,
                "confidence": "INSUFFICIENT_WAVES",
            }

        w1 = same_direction[-3]
        w2 = same_direction[-2]
        w3 = same_direction[-1]

        diminishing_progress = (
            w3["price_progress"]
            < w2["price_progress"]
            < w1["price_progress"]
        )

        exhausted_effort = (
            w3["cumulative_volume"]
            < w2["cumulative_volume"]
        )

        if diminishing_progress and exhausted_effort:

            return {
                "sot_alert": True,
                "confidence": "HIGH",
                "direction": direction,
                "wave_1": w1["price_progress"],
                "wave_2": w2["price_progress"],
                "wave_3": w3["price_progress"],
            }

        return {
            "sot_alert": False,
            "confidence": "LOW",
            "direction": direction,
        }
