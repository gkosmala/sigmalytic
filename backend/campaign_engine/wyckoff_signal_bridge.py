
"""
SAVE AS:
campaign_engine/wyckoff_signal_bridge.py

Converts Wyckoff events into campaign lifecycle signals.
"""

from typing import Dict, Any


class WyckoffSignalBridge:

    def evaluate(
        self,
        signal_payload: Dict[str, Any],
    ) -> Dict[str, Any]:

        spring = bool(
            signal_payload.get(
                "spring_detected",
                False,
            )
        )

        upthrust = bool(
            signal_payload.get(
                "upthrust_detected",
                False,
            )
        )

        absorption = bool(
            signal_payload.get(
                "absorption_detected",
                False,
            )
        )

        if spring and absorption:
            return {
                "campaign_signal": "ACCUMULATION_LOADING",
                "direction": "LONG",
                "priority": "HIGH",
            }

        if upthrust:
            return {
                "campaign_signal": "DISTRIBUTION_RISK",
                "direction": "SHORT",
                "priority": "HIGH",
            }

        return {
            "campaign_signal": "NEUTRAL",
            "direction": "AMBIGUOUS",
            "priority": "LOW",
        }
