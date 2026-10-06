# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/weis_direction.py
-------------------------
Which way a Weis Wave signal points. The radar's composite_score is the
Weis signal strength and is the SAME for a bullish and a bearish signal (a
Spring and an Upthrust both score 100), so anything that needs direction must
read the signal name. Signals follow weis_wave.py's own notes:

  Spring, Selling Climax, No Supply, 3-bar bullish reversal   -> bullish
  Upthrust, Buying Climax, No Demand, 3-bar bearish reversal  -> bearish
"""
from __future__ import annotations

from typing import Optional

BULLISH = "BULL"
BEARISH = "BEAR"

_DIRECTION = {
    "SPRING": BULLISH,
    "CLIMAX_SELL": BULLISH,
    "NO_SUPPLY": BULLISH,
    "3BAR_BULLISH": BULLISH,
    "UPTHRUST": BEARISH,
    "CLIMAX_BUY": BEARISH,
    "NO_DEMAND": BEARISH,
    "3BAR_BEARISH": BEARISH,
}

_LABEL = {
    "SPRING": "Spring", "CLIMAX_SELL": "Selling Climax", "NO_SUPPLY": "No Supply",
    "3BAR_BULLISH": "3-Bar Reversal", "UPTHRUST": "Upthrust", "CLIMAX_BUY": "Buying Climax",
    "NO_DEMAND": "No Demand", "3BAR_BEARISH": "3-Bar Reversal",
}


def signal_direction(signal: Optional[str]) -> Optional[str]:
    """'BULL', 'BEAR', or None when there is no signal or it is not a known one."""
    return _DIRECTION.get(str(signal or "").strip().upper())


def signal_label(signal: Optional[str]) -> str:
    """Readable name for the admin report, e.g. 'Upthrust (bearish)'. '-' when no signal."""
    key = str(signal or "").strip().upper()
    if not key or key == "NONE":
        return "-"
    name = _LABEL.get(key, key.replace("_", " ").title())
    d = _DIRECTION.get(key)
    return f"{name} ({'bullish' if d == BULLISH else 'bearish'})" if d else name
