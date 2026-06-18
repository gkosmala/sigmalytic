
"""
SAVE AS:
research_engine/weis_wave_accumulator.py

Converts Renko bricks into Weis Waves.
"""

from typing import Dict, Any, List


class WeisWaveAccumulator:

    def build_waves(
        self,
        bricks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        if not bricks:
            return []

        waves = []

        current = {
            "direction": bricks[0]["direction"],
            "brick_count": 0,
            "price_progress": 0.0,
            "cumulative_volume": 0.0,
        }

        for brick in bricks:

            direction = brick["direction"]

            if direction == current["direction"]:

                current["brick_count"] += 1

                current["price_progress"] += abs(
                    brick["close"]
                    - brick["open"]
                )

                current["cumulative_volume"] += float(
                    brick.get(
                        "volume",
                        0,
                    )
                )

            else:

                waves.append(
                    current
                )

                current = {
                    "direction": direction,
                    "brick_count": 1,
                    "price_progress": abs(
                        brick["close"]
                        - brick["open"]
                    ),
                    "cumulative_volume": float(
                        brick.get(
                            "volume",
                            0,
                        )
                    ),
                }

        waves.append(
            current
        )

        return waves
