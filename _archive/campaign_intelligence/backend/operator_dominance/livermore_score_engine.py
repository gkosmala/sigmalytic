"""
livermore_score_engine.py

Purpose:
Quantify evidence of Livermore-style operator control.

This engine does NOT write to the database.

It evaluates a campaign and returns a Livermore Control Score (0-100).

Livermore evidence focus:
- Line of least resistance
- Pivotal-point progress
- Follow-through after confirmation
- Normal reaction quality
- Relative/sector leadership proxy
- Campaign state advancement

Version:
13B.1
"""

from typing import Any, Dict


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _state_score(state: str) -> float:
    state = (state or "").upper()

    mapping = {
        "BIRTH": 20,
        "CONFIRMED": 45,
        "SURVIVING": 65,
        "EXPANDING": 90,
        "MATURING": 85,
        "DISTRIBUTION_RISK": 25,
        "CLOSED": 0,
    }

    return mapping.get(state, 20)


def _progress_after_pivot_score(campaign: Dict[str, Any]) -> float:
    return_pct = _f(campaign.get("return_pct"), 0.0)
    pnf_progress = _f(campaign.get("pnf_progress_pct"), 0.0)

    return_component = _clamp(50 + (return_pct * 5.0))
    pnf_component = _clamp(pnf_progress)

    return _clamp((return_component * 0.60) + (pnf_component * 0.40))


def _line_of_least_resistance_score(campaign: Dict[str, Any]) -> float:
    expected_return = _f(campaign.get("outcome_expected_return"), 0.0)
    risk_reward = _f(campaign.get("outcome_risk_reward"), 1.0)
    failure_prob = _f(campaign.get("outcome_failure_prob"), 50.0)

    expected_component = _clamp(50 + (expected_return * 5.0))
    rr_component = _clamp(risk_reward * 25.0)
    failure_component = _clamp(100 - failure_prob)

    return _clamp(
        expected_component * 0.40
        + rr_component * 0.25
        + failure_component * 0.35
    )


def _normal_reaction_score(campaign: Dict[str, Any]) -> float:
    mae = abs(_f(campaign.get("outcome_expected_mae"), 0.0))
    decay_score = _f(campaign.get("decay_score"), 0.0)

    mae_component = _clamp(100 - (mae * 8.0))
    decay_component = _clamp(100 - decay_score)

    return _clamp((mae_component * 0.55) + (decay_component * 0.45))


def _leadership_score(campaign: Dict[str, Any]) -> float:
    tier = str(campaign.get("historical_confidence") or "").upper()
    layer = str(campaign.get("layer") or "").upper()

    tier_map = {
        "TIER_1": 85,
        "TIER_2": 65,
        "TIER_3": 45,
        "TIER_4": 25,
    }

    layer_map = {
        "A": 75,
        "B": 60,
        "C": 45,
        "D": 30,
    }

    tier_score = tier_map.get(tier, 50)
    layer_score = layer_map.get(layer, 50)

    return _clamp((tier_score * 0.60) + (layer_score * 0.40))


def compute_livermore_score(campaign: Dict[str, Any]) -> Dict[str, float]:
    state = str(campaign.get("current_state") or campaign.get("state_enum") or "")

    pivotal_progress = _progress_after_pivot_score(campaign)
    resistance_line = _line_of_least_resistance_score(campaign)
    normal_reaction = _normal_reaction_score(campaign)
    leadership = _leadership_score(campaign)
    state_component = _state_score(state)

    livermore_score = (
        pivotal_progress * 0.25
        + resistance_line * 0.25
        + normal_reaction * 0.20
        + leadership * 0.15
        + state_component * 0.15
    )

    livermore_score = round(_clamp(livermore_score), 2)

    return {
        "livermore_score": livermore_score,
        "pivotal_progress_component": round(pivotal_progress, 2),
        "line_of_least_resistance_component": round(resistance_line, 2),
        "normal_reaction_component": round(normal_reaction, 2),
        "leadership_component": round(leadership, 2),
        "state_component": round(state_component, 2),
    }
