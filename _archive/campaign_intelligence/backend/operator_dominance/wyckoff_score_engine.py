"""
wyckoff_score_engine.py

Purpose:
Quantify evidence of Wyckoff-style operator control.

This engine does NOT write to the database.

It simply evaluates a campaign and returns a
Wyckoff Control Score (0-100).

Version:
13B.1
"""

from typing import Dict, Any


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _state_score(state: str) -> float:

    state = (state or "").upper()

    mapping = {
        "BIRTH": 20,
        "CONFIRMED": 40,
        "SURVIVING": 60,
        "EXPANDING": 80,
        "MATURING": 90,
        "DISTRIBUTION_RISK": 35,
        "CLOSED": 0,
    }

    return mapping.get(state, 20)


def compute_wyckoff_score(campaign: Dict[str, Any]) -> Dict[str, float]:

    obs = float(campaign.get("obstacle_score") or 0)
    prog = float(campaign.get("progress_score") or 0)
    d_score = float(campaign.get("d_score") or 0)

    state = campaign.get("current_state")

    state_component = _state_score(state)

    # Cause Development
    #
    # Large obstacle + meaningful progress
    # = evidence of cause building
    #
    cause_component = (
        (obs * 0.50)
        +
        (prog * 0.50)
    )

    wyckoff_score = (
        (obs * 0.25)
        +
        (prog * 0.25)
        +
        (d_score * 0.20)
        +
        (state_component * 0.15)
        +
        (cause_component * 0.15)
    )

    wyckoff_score = round(_clamp(wyckoff_score), 2)

    return {
        "wyckoff_score": wyckoff_score,
        "obstacle_component": round(obs, 2),
        "progress_component": round(prog, 2),
        "persistence_component": round(d_score, 2),
        "state_component": round(state_component, 2),
        "cause_component": round(cause_component, 2),
    }