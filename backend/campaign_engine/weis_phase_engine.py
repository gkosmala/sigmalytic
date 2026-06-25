from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import math


@dataclass
class WeisPhaseResult:
    symbol: str
    engine: str
    status: str

    weis_phase: str
    mapped_campaign_state: str
    phase_direction: str
    phase_confidence: float
    phase_reason: str

    next_possible_phase: str
    transition_hint: str
    risk_state: str

    fusion_state: str
    fusion_direction: str
    router_state: str
    gamma_data_fresh: bool

    wave_direction: str
    dominant_wave_direction: str
    wave_coherence_score: float
    phase_permission: str

    theta_flush_risk: bool
    liquidation_risk: bool
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WeisPhaseEngine:
    """
    Weis-only Phase Engine.

    Purpose:
    - Convert Weis-Gamma fusion evidence into a Weis-centered phase.
    - Map Weis phase back into the existing campaign lifecycle without requiring
      Wyckoff or Livermore.
    - Do not let stale Gamma confirm Gamma expansion.
    - Do not let execution logic pollute campaign detection.
    - Do not generate trades.

    This engine is the bridge between:
    Weis Wave -> Gamma Matrix -> Fusion -> V2 campaign lifecycle.
    """

    PHASE_TO_CAMPAIGN_STATE = {
        "NO_WEIS_STRUCTURE": "NO_CAMPAIGN",
        "WEIS_BASELINE": "NO_CAMPAIGN",
        "WEIS_ABSORPTION": "BIRTH",
        "WEIS_TEST": "BIRTH",
        "WEIS_TURN": "CONFIRMED",
        "WEIS_EXPANSION": "SURVIVING",
        "WEIS_GAMMA_EXPANSION": "EXPANDING",
        "WEIS_GAMMA_PINNED": "MATURING",
        "WEIS_GAMMA_COLLAPSE": "DISTRIBUTION_RISK",
        "WEIS_EXHAUSTION": "MATURING",
        "WEIS_THETA_FLUSH_RISK": "MATURING",
        "WEIS_FAILED_CAMPAIGN": "CLOSED",
        "WEIS_ONLY_GAMMA_STALE": "SURVIVING",
        "WEIS_DATA_BLOCKED": "NO_CAMPAIGN",
    }

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            x = float(value)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    @staticmethod
    def _safe_bool(value: Any) -> bool:
        return bool(value)

    @staticmethod
    def _safe_str(value: Any, default: str = "UNKNOWN") -> str:
        try:
            if value is None:
                return default
            text = str(value).strip()
            return text.upper() if text else default
        except Exception:
            return default

    @classmethod
    def _latest_weis_evidence(cls, weis_wave_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(weis_wave_result, dict):
            return {}

        evidence = weis_wave_result.get("evidence")
        return evidence if isinstance(evidence, dict) else {}

    @classmethod
    def _confidence(
        cls,
        base: float,
        fusion_confidence: float,
        coherence: float,
        phase_permission: str,
    ) -> float:
        score = base

        score += min(max(fusion_confidence, 0.0), 1.0) * 0.35
        score += min(abs(coherence), 1.0) * 0.20

        if phase_permission == "EXPANSION_CONFIRMED":
            score += 0.15
        elif phase_permission == "ALLOWED_FULL":
            score += 0.10
        elif phase_permission == "ALLOWED_SMALL":
            score += 0.05
        elif phase_permission == "PROBATIONARY":
            score -= 0.10
        elif phase_permission == "BLOCKED":
            score -= 0.25

        return round(max(0.0, min(score, 1.0)), 4)

    @classmethod
    def _next_phase(cls, phase: str) -> str:
        sequence = [
            "NO_WEIS_STRUCTURE",
            "WEIS_BASELINE",
            "WEIS_ABSORPTION",
            "WEIS_TEST",
            "WEIS_TURN",
            "WEIS_EXPANSION",
            "WEIS_GAMMA_EXPANSION",
            "WEIS_EXHAUSTION",
        ]

        if phase in {"WEIS_GAMMA_COLLAPSE", "WEIS_FAILED_CAMPAIGN"}:
            return "RESET_OR_CLOSED"

        if phase == "WEIS_THETA_FLUSH_RISK":
            return "RETEST_AFTER_THETA_RISK"

        if phase == "WEIS_GAMMA_PINNED":
            return "BREAK_PIN_OR_REJECT"

        if phase == "WEIS_ONLY_GAMMA_STALE":
            return "REFRESH_GAMMA_CONFIRMATION"

        if phase in sequence:
            idx = sequence.index(phase)
            if idx + 1 < len(sequence):
                return sequence[idx + 1]

        return "MONITOR"

    @classmethod
    def _transition_hint(cls, phase: str) -> str:
        hints = {
            "NO_WEIS_STRUCTURE": "No Weis wave structure yet.",
            "WEIS_BASELINE": "Monitor for absorption or meaningful wave turn.",
            "WEIS_ABSORPTION": "Look for successful test or reversal wave.",
            "WEIS_TEST": "Look for turn confirmation and improving wave efficiency.",
            "WEIS_TURN": "Look for sustained wave coherence and continuation.",
            "WEIS_EXPANSION": "Look for Gamma confirmation before EXPANDING.",
            "WEIS_GAMMA_EXPANSION": "Expansion confirmed by Weis-Gamma fusion.",
            "WEIS_GAMMA_PINNED": "Price may be trapped near Gamma wall; wait for break or rejection.",
            "WEIS_GAMMA_COLLAPSE": "Downside Gamma/Weis collapse risk active.",
            "WEIS_EXHAUSTION": "Wave quality deteriorating; monitor for failure or reset.",
            "WEIS_THETA_FLUSH_RISK": "0DTE theta risk active; confirmation should wait.",
            "WEIS_FAILED_CAMPAIGN": "Weis campaign failed.",
            "WEIS_ONLY_GAMMA_STALE": "Weis evidence remains, but Gamma must refresh before confirmation.",
            "WEIS_DATA_BLOCKED": "Data is blocked or unsafe.",
        }

        return hints.get(phase, "Monitor for next Weis-Gamma evidence update.")

    @classmethod
    def build(
        cls,
        symbol: str,
        weis_wave_result: Optional[Dict[str, Any]] = None,
        multi_scale_weis_result: Optional[Dict[str, Any]] = None,
        weis_gamma_fusion_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        warnings: List[str] = []

        weis_evidence = cls._latest_weis_evidence(weis_wave_result)

        wave_direction = cls._safe_str(weis_evidence.get("wave_direction"))
        demand_dominance = cls._safe_bool(weis_evidence.get("demand_dominance"))
        supply_dominance = cls._safe_bool(weis_evidence.get("supply_dominance"))
        effort_up = cls._safe_bool(weis_evidence.get("effort_producing_upside_result"))
        effort_down = cls._safe_bool(weis_evidence.get("effort_producing_downside_result"))
        failing_up = cls._safe_bool(weis_evidence.get("effort_failing_upside_result"))
        failing_down = cls._safe_bool(weis_evidence.get("effort_failing_downside_result"))
        shortening_down = cls._safe_bool(weis_evidence.get("shortening_downside_thrust"))
        shortening_up = cls._safe_bool(weis_evidence.get("shortening_upside_thrust"))

        wave_distance_atr = cls._safe_float(weis_evidence.get("wave_distance_atr"))
        wave_efficiency = cls._safe_float(weis_evidence.get("wave_efficiency"))
        wave_volume_z = cls._safe_float(weis_evidence.get("wave_volume_z"))

        if not isinstance(multi_scale_weis_result, dict):
            multi_scale_weis_result = {}

        dominant_wave_direction = cls._safe_str(multi_scale_weis_result.get("dominant_wave_direction"))
        coherence = cls._safe_float(multi_scale_weis_result.get("wave_coherence_score"))
        phase_permission = cls._safe_str(multi_scale_weis_result.get("phase_permission"), "BLOCKED")

        if not isinstance(weis_gamma_fusion_result, dict):
            weis_gamma_fusion_result = {}
            warnings.append("Missing Weis-Gamma fusion result.")

        fusion_state = cls._safe_str(weis_gamma_fusion_result.get("fusion_state"), "WEIS_GAMMA_UNRESOLVED")
        fusion_direction = cls._safe_str(weis_gamma_fusion_result.get("fusion_direction"))
        router_state = cls._safe_str(weis_gamma_fusion_result.get("router_state"), "YELLOW")
        gamma_data_fresh = cls._safe_bool(weis_gamma_fusion_result.get("gamma_data_fresh"))
        fusion_confidence = cls._safe_float(weis_gamma_fusion_result.get("confidence"))

        theta_flush_risk = cls._safe_bool(weis_gamma_fusion_result.get("theta_flush_risk"))
        liquidation_risk = cls._safe_bool(weis_gamma_fusion_result.get("liquidation_risk"))

        # Phase determination.
        if router_state == "RED" or fusion_state == "WEIS_GAMMA_DATA_BLOCKED":
            weis_phase = "WEIS_DATA_BLOCKED"
            phase_direction = "BLOCKED"
            risk_state = "DATA_BLOCKED"
            base_confidence = 0.0
            reason = "Router is RED or data is blocked; Weis-Gamma phase cannot be trusted."

        elif fusion_state == "WEIS_ONLY_GAMMA_STALE":
            weis_phase = "WEIS_ONLY_GAMMA_STALE"
            phase_direction = wave_direction if wave_direction in {"UP", "DOWN"} else "UNKNOWN"
            risk_state = "STALE_GAMMA"
            base_confidence = 0.25
            reason = "Weis evidence exists, but stale Gamma cannot confirm the phase."

        elif fusion_state == "THETA_FLUSH_RISK" or theta_flush_risk:
            weis_phase = "WEIS_THETA_FLUSH_RISK"
            phase_direction = "RISK"
            risk_state = "THETA_FLUSH"
            base_confidence = 0.45
            reason = "0DTE theta-flush risk is active."

        elif fusion_state == "WEIS_GAMMA_COLLAPSE" or liquidation_risk:
            weis_phase = "WEIS_GAMMA_COLLAPSE"
            phase_direction = "DOWN"
            risk_state = "COLLAPSE_RISK"
            base_confidence = 0.60
            reason = "Weis-Gamma downside collapse or liquidation risk is active."

        elif fusion_state == "WEIS_GAMMA_ABSORPTION_SUPPORT":
            weis_phase = "WEIS_ABSORPTION"
            phase_direction = "UP_POTENTIAL"
            risk_state = "OPPORTUNITY_DEVELOPING"
            base_confidence = 0.50
            reason = "Selling effort failed to produce downside reward at Gamma support."

        elif fusion_state == "WEIS_GAMMA_ABSORPTION_CEILING":
            weis_phase = "WEIS_EXHAUSTION"
            phase_direction = "DOWN_RISK"
            risk_state = "UPSIDE_BLOCKED"
            base_confidence = 0.50
            reason = "Buying effort failed to produce upside reward at Gamma resistance."

        elif fusion_state == "WEIS_GAMMA_PIN":
            weis_phase = "WEIS_GAMMA_PINNED"
            phase_direction = "NEUTRAL"
            risk_state = "PIN_RISK"
            base_confidence = 0.45
            reason = "Gamma wall/pin behavior is suppressing Weis reward."

        elif fusion_state == "WEIS_GAMMA_EXPANSION":
            weis_phase = "WEIS_GAMMA_EXPANSION"
            phase_direction = "UP" if fusion_direction == "UP" else fusion_direction
            risk_state = "EXPANSION_CONFIRMED"
            base_confidence = 0.65
            reason = "Weis expansion is confirmed by fresh Gamma/0DTE context."

        elif fusion_state in {"WEIS_EXPANSION_GAMMA_NEUTRAL", "WEIS_DOWNSIDE_EXPANSION_GAMMA_NEUTRAL"}:
            if wave_direction == "UP" and effort_up and demand_dominance:
                weis_phase = "WEIS_EXPANSION"
                phase_direction = "UP"
                risk_state = "WEIS_EXPANSION_NO_GAMMA_CONFIRM"
                base_confidence = 0.50
                reason = "Weis wave is expanding, but Gamma is neutral or not confirmatory."
            elif wave_direction == "DOWN" and effort_down and supply_dominance:
                weis_phase = "WEIS_GAMMA_COLLAPSE"
                phase_direction = "DOWN"
                risk_state = "DOWNSIDE_EXPANSION"
                base_confidence = 0.50
                reason = "Weis downwave is expanding."
            else:
                weis_phase = "WEIS_BASELINE"
                phase_direction = "UNKNOWN"
                risk_state = "UNRESOLVED"
                base_confidence = 0.25
                reason = "Fusion state is neutral, and Weis evidence is not decisive."

        elif failing_down or shortening_down:
            weis_phase = "WEIS_TEST"
            phase_direction = "UP_POTENTIAL"
            risk_state = "TESTING_SUPPLY"
            base_confidence = 0.35
            reason = "Downside thrust or downside result is failing; Weis test condition present."

        elif failing_up or shortening_up:
            weis_phase = "WEIS_EXHAUSTION"
            phase_direction = "DOWN_RISK"
            risk_state = "UPSIDE_EFFORT_FADING"
            base_confidence = 0.35
            reason = "Upside thrust or upside result is failing; Weis exhaustion risk present."

        elif wave_direction in {"UP", "DOWN"} and wave_distance_atr > 0:
            weis_phase = "WEIS_BASELINE"
            phase_direction = wave_direction
            risk_state = "BASELINE_WAVE_STRUCTURE"
            base_confidence = 0.25
            reason = "Basic Weis wave structure exists, but no decisive phase evidence is present."

        else:
            weis_phase = "NO_WEIS_STRUCTURE"
            phase_direction = "UNKNOWN"
            risk_state = "NO_STRUCTURE"
            base_confidence = 0.0
            reason = "No usable Weis wave structure is present."

        mapped_campaign_state = cls.PHASE_TO_CAMPAIGN_STATE.get(weis_phase, "NO_CAMPAIGN")

        phase_confidence = cls._confidence(
            base=base_confidence,
            fusion_confidence=fusion_confidence,
            coherence=coherence,
            phase_permission=phase_permission,
        )

        # Phase-specific confidence caps.
        # These prevent early, stale, pinned, or risk phases from being treated
        # as equal to confirmed Weis-Gamma expansion.
        phase_confidence_caps = {
            "NO_WEIS_STRUCTURE": 0.00,
            "WEIS_DATA_BLOCKED": 0.00,
            "WEIS_BASELINE": 0.45,
            "WEIS_ABSORPTION": 0.88,
            "WEIS_TEST": 0.78,
            "WEIS_TURN": 0.82,
            "WEIS_EXPANSION": 0.90,
            "WEIS_GAMMA_EXPANSION": 1.00,
            "WEIS_GAMMA_PINNED": 0.80,
            "WEIS_GAMMA_COLLAPSE": 0.95,
            "WEIS_EXHAUSTION": 0.85,
            "WEIS_THETA_FLUSH_RISK": 0.90,
            "WEIS_FAILED_CAMPAIGN": 0.50,
            "WEIS_ONLY_GAMMA_STALE": 0.45,
        }

        phase_confidence = round(
            min(phase_confidence, phase_confidence_caps.get(weis_phase, 1.0)),
            4,
        )

        if not gamma_data_fresh and weis_phase not in {"WEIS_ONLY_GAMMA_STALE", "WEIS_DATA_BLOCKED"}:
            warnings.append("Gamma data is stale but phase was not explicitly marked stale.")

        status = "OK"
        if weis_phase in {"WEIS_DATA_BLOCKED"}:
            status = "BLOCKED"
        elif weis_phase == "NO_WEIS_STRUCTURE":
            status = "NO_STRUCTURE"

        return WeisPhaseResult(
            symbol=symbol,
            engine="WEIS_PHASE",
            status=status,
            weis_phase=weis_phase,
            mapped_campaign_state=mapped_campaign_state,
            phase_direction=phase_direction,
            phase_confidence=phase_confidence,
            phase_reason=reason,
            next_possible_phase=cls._next_phase(weis_phase),
            transition_hint=cls._transition_hint(weis_phase),
            risk_state=risk_state,
            fusion_state=fusion_state,
            fusion_direction=fusion_direction,
            router_state=router_state,
            gamma_data_fresh=gamma_data_fresh,
            wave_direction=wave_direction,
            dominant_wave_direction=dominant_wave_direction,
            wave_coherence_score=round(coherence, 4),
            phase_permission=phase_permission,
            theta_flush_risk=theta_flush_risk,
            liquidation_risk=liquidation_risk,
            warnings=warnings,
        ).to_dict()
