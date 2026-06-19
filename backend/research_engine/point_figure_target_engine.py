
"""
SAVE AS:
research_engine/point_figure_target_engine.py

Point & Figure Target Engine

Computes:
- Horizontal cause counts
- Conservative targets
- Aggressive targets
"""

from typing import Dict, Any


class PointFigureTargetEngine:

    def calculate_targets(
        self,
        base_price: float,
        horizontal_count: int,
        box_size: float,
        reversal: int = 3,
    ) -> Dict[str, Any]:

        cause = horizontal_count * box_size

        conservative = (
            base_price + cause
        )

        aggressive = (
            base_price
            + (cause * reversal)
        )

        return {
            "horizontal_count": horizontal_count,
            "cause": round(
                cause,
                4,
            ),
            "conservative_target": round(
                conservative,
                4,
            ),
            "aggressive_target": round(
                aggressive,
                4,
            ),
        }

    def remaining_opportunity(
        self,
        current_price: float,
        target_price: float,
    ) -> float:

        if current_price <= 0:
            return 0.0

        return round(
            (
                (target_price - current_price)
                / current_price
            ) * 100.0,
            2,
        )

