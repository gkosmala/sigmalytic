"""
weis_score_engine.py

Purpose:
Quantify evidence of David Weis-style operator control.

This engine does NOT write to the database.

It evaluates a campaign and returns a Weis Control Score (0-100).

Weis evidence focus:
- Effort versus Result
- Absorption
- Shortening of Thrust
- Failure to Follow Through
- Counter-wave / decay evidence
- Campaign state context

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
        "BIRTH": 25,
        "CONFIRMED": 45,
        "SURVIVING": 65,
        "EXPANDING": 85,
        "MATURING": 80,
        "DISTRIBUTION_RISK": 30,
        "CLOSED": 0,
    }

    return mapping.get(state, 25)


def _effort_result_score(campaign: Dict[str, Any]) -> float:
    """
    Weis focuses on whether effort produces result.

    Available V2 proxy fields:
    - progress_score
    - return_pct
    - pnf_progress_pct

    Higher progress with positive return suggests constructive result.
    Low progress with deterioration suggests poor effort/result.
    """
    progress = _f(campaign.get("progress_score"), 0.0)
    return_pct = _f(campaign.get("return_pct"), 0.0)
    pnf_progress = _f(campaign.get("pnf_progress_pct"), 0.0)

    return_component = _clamp(50 + (return_pct * 5.0))
    pnf_component = _clamp(pnf_progress)

    return _clamp(
        progress * 0.45
        + return_component * 0.35
        + pnf_component * 0.20
    )


def _absorption_score(campaign: Dict[str, Any]) -> float:
    """
    Weis/Wyckoff overlap:
    absorption is inferred when obstacles exist but downside result is limited.

    Available V2 proxy fields:
    - obstacle_score
    - d_score
    - outcome_failure_prob
    - decay_score
    """
    obstacle = _f(campaign.get("obstacle_score"), 0.0)
    d_score = _f(campaign.get("d_score"), 0.0)
    failure_prob = _f(campaign.get("outcome_failure_prob"), 50.0)
    decay_score = _f(campaign.get("decay_score"), 0.0)

    failure_health = _clamp(100 - failure_prob)
    decay_health = _clamp(100 - decay_score)

    return _clamp(
        obstacle * 0.30
        + d_score * 0.30
        + failure_health * 0.20
        + decay_health * 0.20
    )


def _shortening_of_thrust_score(campaign: Dict[str, Any]) -> float:
    """
    Shortening of Thrust means price progress weakens despite effort.

    V2 does not yet expose explicit Weis Wave bars here.
    We proxy SOT risk through:
    - low pnf progress
    - high decay
    - high failure probability

    The returned value is a positive quality score:
    higher = less SOT deterioration / healthier thrust.
    """
    pnf_progress = _f(campaign.get("pnf_progress_pct"), 0.0)
    decay_score = _f(campaign.get("decay_score"), 0.0)
    failure_prob = _f(campaign.get("outcome_failure_prob"), 50.0)

    progress_health = _clamp(pnf_progress)
    decay_health = _clamp(100 - decay_score)
    failure_health = _clamp(100 - failure_prob)

    return _clamp(
        progress_health * 0.35
        + decay_health * 0.35
        + failure_health * 0.30
    )


def _failure_to_follow_through_score(campaign: Dict[str, Any]) -> float:
    """
    Weis uses failure to follow through as information.

    Here higher score means better follow-through health.
    """
    transition_advance = _f(campaign.get("transition_advance_prob"), 0.0)
    transition_failure = _f(campaign.get("transition_failure_prob"), 50.0)
    continuation = _f(campaign.get("transition_continuation_prob"), 0.0)

    failure_health = _clamp(100 - transition_failure)

    return _clamp(
        transition_advance * 0.40
        + continuation * 0.30
        + failure_health * 0.30
    )


def _counter_wave_control_score(campaign: Dict[str, Any]) -> float:
    """
    Weis watches the counter-wave.

    Available proxy:
    - decay_score
    - conjunction_exit
    - exit_signal

    Higher score means counter-wave has not seized control.
    """
    decay_score = _f(campaign.get("decay_score"), 0.0)
    conjunction_exit = bool(campaign.get("conjunction_exit"))
    exit_signal = bool(campaign.get("exit_signal"))

    score = 100 - decay_score

    if exit_signal:
        score -= 25

    if conjunction_exit:
        score -= 35

    return _clamp(score)


def compute_weis_score(campaign: Dict[str, Any]) -> Dict[str, float]:
    state = str(campaign.get("current_state") or campaign.get("state_enum") or "")

    effort_result = _effort_result_score(campaign)
    absorption = _absorption_score(campaign)
    shortening_of_thrust = _shortening_of_thrust_score(campaign)
    follow_through = _failure_to_follow_through_score(campaign)
    counter_wave = _counter_wave_control_score(campaign)
    state_component = _state_score(state)

    weis_score = (
        effort_result * 0.25
        + absorption * 0.25
        + shortening_of_thrust * 0.20
        + follow_through * 0.15
        + counter_wave * 0.10
        + state_component * 0.05
    )

    weis_score = round(_clamp(weis_score), 2)

    return {
        "weis_score": weis_score,
        "effort_result_component": round(effort_result, 2),
        "absorption_component": round(absorption, 2),
        "shortening_of_thrust_component": round(shortening_of_thrust, 2),
        "failure_to_follow_through_component": round(follow_through, 2),
        "counter_wave_component": round(counter_wave, 2),
        "state_component": round(state_component, 2),
    }
