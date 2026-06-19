
"""
SAVE AS:
campaign_engine/fractal_router.py
"""

from typing import Any, Dict, List


class FractalRouter:

    TIMEFRAME_MATRIX = {
        "TICK": ["1MIN", "5MIN"],
        "1MIN": ["5MIN", "HOURLY"],
        "5MIN": ["HOURLY", "DAILY"],
        "HOURLY": ["DAILY", "WEEKLY"],
        "DAILY": ["WEEKLY", "MONTHLY"],
        "WEEKLY": ["MONTHLY"],
        "MONTHLY": [],
    }

    def normalize_timeframe(self, timeframe: str) -> str:

        tf = timeframe.upper().replace("-", "")

        aliases = {
            "1M": "1MIN",
            "5M": "5MIN",
            "H": "HOURLY",
            "D": "DAILY",
            "W": "WEEKLY",
            "M": "MONTHLY",
        }

        return aliases.get(tf, tf)

    def get_macro_timeframes(
        self,
        timeframe: str,
    ) -> List[str]:

        tf = self.normalize_timeframe(timeframe)

        return self.TIMEFRAME_MATRIX.get(
            tf,
            [],
        )

    def route(
        self,
        symbol: str,
        timeframe: str,
    ) -> Dict[str, Any]:

        tf = self.normalize_timeframe(timeframe)

        return {
            "symbol": symbol.upper(),
            "timeframe": tf,
            "macro_timeframes": self.get_macro_timeframes(tf),
        }

