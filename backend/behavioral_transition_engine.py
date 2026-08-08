# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/behavioral_transition_engine.py
---------------------------------------
Sigmalytic Behavioral Transition Detection Engine v1.0

Converts raw radar/confluence/intelligence fields into trader-facing
behavioral transition calls and pre-trigger opportunity labels.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _s(x: Any, default: str = "") -> str:
    try:
        if x is None:
            return default
        return str(x)
    except Exception:
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _pct_distance(price: float, level: float) -> Optional[float]:
    if price <= 0 or level <= 0:
        return None
    return (level - price) / price * 100.0


def _near_level(price: float, level: float, pct: float = 1.5) -> bool:
    d = _pct_distance(price, level)
    return False if d is None else abs(d) <= pct


def _direction_from_setup(setup: str, status: str, regime: str, delta: float) -> str:
    text = f"{setup} {status} {regime}".lower()

    bearish_terms = [
        "upthrust", "breakdown", "distribution", "short",
        "bear expansion", "bear rally", "markdown", "failed breakout"
    ]
    bullish_terms = [
        "spring", "breakout", "accumulation", "bull expansion",
        "bull pullback", "markup", "trend continuation", "momentum leader"
    ]

    if any(t in text for t in bearish_terms):
        return "Short"
    if any(t in text for t in bullish_terms):
        return "Long"

    return "Short" if delta < -10 else "Long"


def _confidence_label(score: float) -> str:
    if score >= 90:
        return "Elite"
    if score >= 80:
        return "High"
    if score >= 70:
        return "Qualified"
    if score >= 60:
        return "Developing"
    return "Low"


@dataclass
class BehavioralTransition:
    symbol: str
    side: str
    behavioral_state: str
    transition_candidate: str
    opportunity_state: str
    readiness_score: float
    confidence_label: str
    alert_type: str
    trigger: Optional[float]
    invalidation: Optional[float]
    target1: Optional[float]
    target2: Optional[float]
    why_this_trade: str
    evidence: List[str]
    risk_notes: List[str]
    invalidation_reason: str
    trader_summary: str
    raw_components: Dict[str, Any]
    setup_risk_reward: Optional[float] = None


def classify_behavioral_state(data: Dict[str, Any]) -> str:
    setup = _s(data.get("setup_type")).lower()
    status = _s(data.get("status")).lower()
    regime = _s(data.get("regime")).lower()

    composite = _f(data.get("composite_score", data.get("score")))
    expansion = _f(data.get("expansion_node"))
    rs = _f(data.get("relative_strength"))
    volume_pressure = _f(data.get("volume_pressure"))
    rel_volume = _f(data.get("rel_volume"), 1.0)
    delta = _f(data.get("intelligence_delta", data.get("delta")))

    if "spring" in setup:
        return "Accumulation / Spring Test"

    if "upthrust" in setup:
        return "Distribution / Upthrust Test"

    if "distribution" in setup or "breakdown" in setup or "short" in status:
        if rel_volume >= 1.5 or volume_pressure >= 65:
            return "Distribution to Markdown Pressure"
        return "Distribution"

    if "compression" in setup or "volatility expansion" in setup:
        if delta >= 10 and rs >= 60:
            return "Absorption / Markup Loading"
        if delta <= -10:
            return "Compression / Failure Risk"
        return "Compression / Balance"

    if "trend continuation" in setup or "momentum leader" in setup:
        if expansion >= 65 and rs >= 65:
            return "Markup"
        return "Markup Attempt"

    if regime == "bull expansion":
        return "Markup"

    if regime == "bull pullback":
        return "Pullback Within Markup"

    if regime == "bear expansion":
        return "Markdown"

    if regime == "bear rally":
        return "Bear Rally / Short Reset"

    change_pct = _f(data.get("change_pct"))
    if rel_volume >= 2.0 and abs(change_pct) >= 3:
        return "FOMO Expansion" if change_pct > 0 else "Capitulation / Markdown"

    if composite >= 75 and delta >= 0:
        return "Constructive Setup"

    return "Neutral / Noise"


def classify_transition_candidate(state: str, data: Dict[str, Any]) -> str:
    setup = _s(data.get("setup_type")).lower()
    regime = _s(data.get("regime")).lower()
    delta = _f(data.get("intelligence_delta", data.get("delta")))

    if "Absorption" in state and delta >= 10:
        return "Absorption to Markup Attempt"

    if "Compression" in state and delta >= 0:
        return "Compression to Expansion Attempt"

    if "Compression" in state and delta < -10:
        return "Compression to Breakdown Risk"

    if "Spring" in state:
        return "Spring to Markup Reversal"

    if "Upthrust" in state:
        return "Upthrust to Markdown Reversal"

    if "Distribution" in state:
        return "Distribution to Markdown"

    if "Markup" in state and "breakout" in setup:
        return "Compression to Expansion Attempt"

    if "Markup" in state and "trend" in setup:
        return "Markup Continuation"

    if "Markup" in state and "momentum" in setup:
        if delta >= 10:
            return "Markup Continuation"
        if delta <= -5:
            return "Markup Exhaustion Watch"
        return "No Clear Transition"

    if "Markdown" in state:
        return "Markdown Continuation"

    if regime == "bull expansion" and delta >= 0:
        return "Bull Expansion Continuation"

    if regime == "bear expansion" and delta <= 0:
        return "Bear Expansion Continuation"

    return "No Clear Transition"


def classify_opportunity_state(data: Dict[str, Any], side: str, readiness_score: float) -> str:
    price = _f(data.get("price"))
    trigger = _f(data.get("trigger"))
    invalidation = _f(data.get("invalidation"))
    status = _s(data.get("status")).lower()

    trigger_distance = _pct_distance(price, trigger)
    invalidation_distance = abs(_pct_distance(price, invalidation) or 999)

    if "failed" in status or readiness_score < 45:
        return "Avoid"

    if "triggered" in status or "confirmed" in status:
        return "Triggered"

    if trigger_distance is not None:
        if side == "Long":
            if 0 <= trigger_distance <= 1.5 and invalidation_distance <= 5.0 and readiness_score >= 70:
                return "Armed"
            if 0 <= trigger_distance <= 3.0 and readiness_score >= 60:
                return "Setting Up"
        else:
            if readiness_score >= 75 and invalidation_distance <= 5.0:
                return "Armed"
            if readiness_score >= 60:
                return "Setting Up"

    if readiness_score >= 70:
        return "Setting Up"

    if readiness_score >= 55:
        return "Watching"

    return "Noise"


def calculate_readiness_score(data: Dict[str, Any], state: str, transition: str, side: str) -> tuple[float, List[str], List[str]]:
    evidence: List[str] = []
    risk_notes: List[str] = []

    composite = _f(data.get("composite_score", data.get("score")))
    deep = _f(data.get("deep_score", data.get("intelligence_score", composite)))
    delta = _f(data.get("intelligence_delta", data.get("delta", deep - composite)))
    agreement = _f(data.get("agreement_score"), 100 - abs(delta))
    expansion = _f(data.get("expansion_node"))
    rs = _f(data.get("relative_strength"))
    volume_pressure = _f(data.get("volume_pressure"))
    behavioral = _f(data.get("behavioral"))
    price = _f(data.get("price"))
    trigger = _f(data.get("trigger"))
    invalidation = _f(data.get("invalidation"))
    setup = _s(data.get("setup_type"))
    regime = _s(data.get("regime"))

    score = 0.0

    if composite >= 80:
        score += 18
        evidence.append(f"High confluence score ({composite:.1f})")
    elif composite >= 70:
        score += 13
        evidence.append(f"Qualified confluence score ({composite:.1f})")
    elif composite >= 60:
        score += 8

    if delta >= 20:
        score += 18
        evidence.append(f"Major intelligence upgrade ({delta:+.1f})")
    elif delta >= 10:
        score += 15
        evidence.append(f"Positive intelligence upgrade ({delta:+.1f})")
    elif delta >= 0:
        score += 8
        evidence.append(f"Deep engine confirms radar ({delta:+.1f})")
    elif delta <= -20:
        score -= 18
        risk_notes.append(f"Major intelligence downgrade ({delta:+.1f})")
    elif delta <= -10:
        score -= 12
        risk_notes.append(f"Deep engine materially disagrees ({delta:+.1f})")
    else:
        score -= 4

    if agreement >= 90:
        score += 8
        evidence.append(f"Strong engine agreement ({agreement:.1f})")
    elif agreement >= 80:
        score += 5
        evidence.append(f"Good engine agreement ({agreement:.1f})")
    elif agreement < 70:
        score -= 8
        risk_notes.append(f"Weak engine agreement ({agreement:.1f})")

    setup_l = setup.lower()
    regime_l = regime.lower()

    if any(x in setup_l for x in ["compression", "breakout", "breakdown", "spring", "upthrust"]):
        score += 12
        evidence.append(f"Actionable setup type: {setup}")

    if side == "Long":
        if "bull expansion" in regime_l or "markup" in state:
            score += 10
            evidence.append("Bullish regime supports long setup")
        if "distribution" in state or "bear expansion" in regime_l:
            score -= 12
            risk_notes.append("Regime conflicts with long setup")
    else:
        if "distribution" in state or "markdown" in state or "bear expansion" in regime_l:
            score += 10
            evidence.append("Bearish regime supports short setup")
        if "bull expansion" in regime_l and "upthrust" not in setup_l:
            score -= 10
            risk_notes.append("Bullish regime conflicts with short setup")

    if side == "Long":
        if rs >= 70:
            score += 10
            evidence.append(f"Relative strength is strong ({rs:.1f})")
        elif rs >= 60:
            score += 6
            evidence.append(f"Relative strength is constructive ({rs:.1f})")
        elif rs < 45:
            score -= 8
            risk_notes.append(f"Relative strength is weak ({rs:.1f})")
    else:
        if rs <= 40:
            score += 10
            evidence.append(f"Relative weakness supports short ({rs:.1f})")
        elif rs <= 50:
            score += 5
            evidence.append(f"Relative strength is fading ({rs:.1f})")
        elif rs > 65:
            score -= 8
            risk_notes.append(f"Relative strength conflicts with short ({rs:.1f})")

    if volume_pressure >= 70:
        score += 10
        evidence.append(f"Volume pressure confirms interest ({volume_pressure:.1f})")
    elif volume_pressure >= 60:
        score += 6
        evidence.append(f"Volume pressure improving ({volume_pressure:.1f})")
    elif volume_pressure < 40:
        score -= 6
        risk_notes.append(f"Volume pressure weak ({volume_pressure:.1f})")

    if expansion >= 70:
        score += 8
        evidence.append(f"Expansion node active ({expansion:.1f})")
    elif 55 <= expansion < 70 and "compression" in setup_l:
        score += 8
        evidence.append("Compression with expansion potential")

    trigger_distance = _pct_distance(price, trigger)
    invalidation_distance = abs(_pct_distance(price, invalidation) or 999)

    if trigger_distance is not None:
        if side == "Long":
            if 0 <= trigger_distance <= 1.0:
                score += 12
                evidence.append(f"Price is within {trigger_distance:.2f}% of trigger")
            elif 0 <= trigger_distance <= 2.5:
                score += 8
                evidence.append(f"Price is approaching trigger ({trigger_distance:.2f}%)")
            elif trigger_distance < 0:
                score += 4
                evidence.append("Trigger already breached; monitor confirmation")
        else:
            if abs(trigger_distance) <= 2.0:
                score += 8
                evidence.append("Price is near short trigger zone")

    if invalidation_distance <= 3.0:
        score += 8
        evidence.append(f"Risk is tightly defined ({invalidation_distance:.2f}% to invalidation)")
    elif invalidation_distance <= 5.0:
        score += 5
        evidence.append(f"Risk is defined ({invalidation_distance:.2f}% to invalidation)")
    elif invalidation_distance > 8.0:
        score -= 8
        risk_notes.append("Invalidation is too far away for efficient risk")

    gex_score = data.get("gex_score")
    gex_wall = _f(data.get("gex_wall"))

    if gex_score is not None:
        gex = _f(gex_score, 50)
        if side == "Long" and gex >= 65:
            score += 6
            evidence.append(f"Options/GEX backdrop supportive ({gex:.1f})")
        elif side == "Short" and gex <= 40:
            score += 6
            evidence.append(f"Options/GEX backdrop supports downside ({gex:.1f})")

    if gex_wall and _near_level(price, gex_wall, pct=1.5):
        score += 4
        evidence.append("Price is near key options wall")

    if behavioral >= 70:
        score += 6
        evidence.append(f"Behavioral pressure constructive ({behavioral:.1f})")
    elif behavioral <= 35:
        score -= 6
        risk_notes.append(f"Behavioral pressure weak ({behavioral:.1f})")

    return round(_clamp(score), 1), evidence[:8], risk_notes[:6]


def evaluate_behavioral_transition(data: Dict[str, Any]) -> Dict[str, Any]:
    symbol = _s(data.get("symbol"), "UNKNOWN").upper()
    setup = _s(data.get("setup_type"))
    status = _s(data.get("status"))
    regime = _s(data.get("regime"))

    composite = _f(data.get("composite_score", data.get("score")))
    deep = _f(data.get("deep_score", data.get("intelligence_score", composite)))
    delta = _f(data.get("intelligence_delta", data.get("delta", deep - composite)))

    side = _direction_from_setup(setup, status, regime, delta)
    state = classify_behavioral_state(data)
    transition = classify_transition_candidate(state, data)
    readiness, evidence, risk_notes = calculate_readiness_score(data, state, transition, side)
    opportunity_state = classify_opportunity_state(data, side, readiness)

    confidence = _confidence_label(readiness)

    if opportunity_state == "Armed":
        alert_type = "Pre-trigger opportunity"
    elif opportunity_state == "Setting Up":
        alert_type = "Setup forming"
    elif opportunity_state == "Triggered":
        alert_type = "Triggered / monitor confirmation"
    elif opportunity_state == "Avoid":
        alert_type = "Avoid / wait"
    else:
        alert_type = "Watchlist only"

    trigger = data.get("trigger")
    invalidation = data.get("invalidation")
    target1 = data.get("target1")
    target2 = data.get("target2")

    # Genuine, symbol-specific risk/reward -- computed directly from
    # this setup's own real trigger/invalidation/target1 levels, not
    # a shared historical average across unrelated symbols (see
    # probability_service.py's expected_return, which several sessions
    # of investigation confirmed is a mean over a small, coarsely-
    # bucketed sample shared across many unrelated stocks). This is a
    # different, complementary number from campaign_outcome_engine.py's
    # separate, model-derived outcome_risk_reward.
    setup_risk_reward = None
    try:
        t  = _f(trigger)
        inv = _f(invalidation)
        tgt = _f(target1)
        if t and inv and tgt:
            if side == "Short":
                risk   = inv - t
                reward = t - tgt
            else:
                risk   = t - inv
                reward = tgt - t
            if risk > 0 and reward > 0:
                setup_risk_reward = round(reward / risk, 2)
    except Exception as _srr_exc:
        print(f"[SETUP_RR_DIAG] {symbol}: exception={_srr_exc!r} "
              f"raw_trigger={trigger!r} raw_invalidation={invalidation!r} raw_target1={target1!r}",
              flush=True)

    # DIAGNOSTIC (2026-08-08): user reported setup_risk_reward showing
    # empty for every symbol despite the underlying formula already
    # being tested and confirmed correct against real numbers, and
    # despite all three services (frontend/backend/scanner) confirmed
    # redeployed with this code live. Logging the real, raw inputs
    # whenever this ends up None, to get direct evidence of the actual
    # cause instead of continuing to guess.
    if setup_risk_reward is None:
        print(f"[SETUP_RR_DIAG] {symbol}: result=None side={side!r} "
              f"raw_trigger={trigger!r} raw_invalidation={invalidation!r} raw_target1={target1!r} "
              f"parsed_t={_f(trigger)} parsed_inv={_f(invalidation)} parsed_tgt={_f(target1)}",
              flush=True)

    why = "; ".join(evidence[:4]) if evidence else "Insufficient evidence for a high-quality setup."
    invalidation_reason = "; ".join(risk_notes[:3]) if risk_notes else "Invalidation is defined by current setup structure."

    trader_summary = (
        f"{symbol} is classified as {opportunity_state} for a {side} setup. "
        f"Behavioral transition: {transition}. "
        f"Readiness score: {readiness:.1f}/100."
    )

    result = BehavioralTransition(
        symbol=symbol,
        side=side,
        behavioral_state=state,
        transition_candidate=transition,
        opportunity_state=opportunity_state,
        readiness_score=readiness,
        confidence_label=confidence,
        alert_type=alert_type,
        trigger=_f(trigger) if trigger not in (None, "") else None,
        invalidation=_f(invalidation) if invalidation not in (None, "") else None,
        target1=_f(target1) if target1 not in (None, "") else None,
        target2=_f(target2) if target2 not in (None, "") else None,
        why_this_trade=why,
        evidence=evidence,
        risk_notes=risk_notes,
        invalidation_reason=invalidation_reason,
        trader_summary=trader_summary,
        setup_risk_reward=setup_risk_reward,
        raw_components={
            "composite_score": composite,
            "deep_score": deep,
            "intelligence_delta": delta,
            "agreement_score": data.get("agreement_score"),
            "setup_type": setup,
            "status": status,
            "regime": regime,
            "volume_pressure": data.get("volume_pressure"),
            "relative_strength": data.get("relative_strength"),
            "expansion_node": data.get("expansion_node"),
            "behavioral": data.get("behavioral"),
        },
    )

    return asdict(result)


def evaluate_many(rows: List[Dict[str, Any]], min_readiness: float = 55.0) -> List[Dict[str, Any]]:
    out = []
    for row in rows or []:
        try:
            item = evaluate_behavioral_transition(row)
            if item.get("readiness_score", 0) >= min_readiness:
                out.append(item)
        except Exception:
            continue

    out.sort(
        key=lambda x: (
            x.get("opportunity_state") == "Armed",
            x.get("opportunity_state") == "Setting Up",
            x.get("readiness_score", 0),
        ),
        reverse=True,
    )
    return out

