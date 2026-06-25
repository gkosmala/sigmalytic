from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import math


@dataclass
class WeisGammaFusionResult:
    symbol: str
    engine: str
    status: str

    fusion_state: str
    fusion_direction: str
    gamma_regime: str
    router_state: str

    weis_wave_direction: str
    dominant_wave_direction: str
    wave_coherence_score: float
    phase_permission: str

    nearest_gamma_wall: Optional[float]
    nearest_wall_type: Optional[str]
    nearest_wall_status: Optional[str]
    distance_to_wall_pct: Optional[float]

    active_0dte: bool
    zero_dte_state: str
    zero_dte_vol_oi_ratio: float
    theta_flush_risk: bool
    liquidation_risk: bool

    gamma_data_fresh: bool
    phase_confidence_modifier: float

    confidence: float
    reason: str
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WeisGammaFusionEngine:
    """
    Weis-Gamma Fusion Engine.

    Purpose:
    - Fuse Weis wave behavior with Gamma wall structure.
    - Classify whether effort is expanding, being absorbed, pinned,
      collapsing, or at theta-flush risk.
    - Gamma does not replace Weis.
    - Weis defines the wave.
    - Gamma defines the battlefield around the wave.

    This module does NOT trade.
    This module does NOT use Wyckoff or Livermore.
    """

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

        if isinstance(evidence, dict):
            return evidence

        return {}

    @classmethod
    def _nearest_wall_object(cls, gamma_matrix: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not isinstance(gamma_matrix, dict):
            return None

        nearest = gamma_matrix.get("nearest_gamma_wall")

        # If nearest_gamma_wall is only the strike value, search active/top wall objects.
        if isinstance(nearest, dict):
            return nearest

        candidates = []

        for key in ["active_walls", "top_call_walls", "top_put_walls"]:
            value = gamma_matrix.get(key)
            if isinstance(value, list):
                candidates.extend([x for x in value if isinstance(x, dict)])

        if not candidates:
            return None

        nearest_strike = cls._safe_float(nearest, None)

        if nearest_strike is not None:
            for wall in candidates:
                if cls._safe_float(wall.get("strike")) == nearest_strike:
                    return wall

        return candidates[0]

    @classmethod
    def _wall_distance_pct(cls, wall: Optional[Dict[str, Any]]) -> Optional[float]:
        if not isinstance(wall, dict):
            return None

        value = wall.get("distance_to_spot_pct")

        if value is None:
            return None

        return round(cls._safe_float(value), 6)

    @classmethod
    def _confidence(
        cls,
        base: float,
        coherence: float,
        freshness_modifier: float,
        zero_dte_confidence: float,
    ) -> float:
        coherence_boost = min(abs(coherence), 1.0) * 0.20
        zero_dte_boost = min(zero_dte_confidence, 1.0) * 0.10

        confidence = base + coherence_boost + zero_dte_boost
        confidence *= max(0.0, min(freshness_modifier, 1.0))

        return round(max(0.0, min(confidence, 1.0)), 4)

    @classmethod
    def build(
        cls,
        symbol: str,
        weis_wave_result: Optional[Dict[str, Any]] = None,
        multi_scale_weis_result: Optional[Dict[str, Any]] = None,
        gamma_matrix_result: Optional[Dict[str, Any]] = None,
        gamma_freshness_result: Optional[Dict[str, Any]] = None,
        zero_dte_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        warnings: List[str] = []

        weis_evidence = cls._latest_weis_evidence(weis_wave_result)

        wave_direction = cls._safe_str(weis_evidence.get("wave_direction"))
        wave_distance_atr = cls._safe_float(weis_evidence.get("wave_distance_atr"))
        wave_efficiency = cls._safe_float(weis_evidence.get("wave_efficiency"))
        wave_volume_z = cls._safe_float(weis_evidence.get("wave_volume_z"))

        demand_dominance = cls._safe_bool(weis_evidence.get("demand_dominance"))
        supply_dominance = cls._safe_bool(weis_evidence.get("supply_dominance"))

        effort_up = cls._safe_bool(weis_evidence.get("effort_producing_upside_result"))
        effort_down = cls._safe_bool(weis_evidence.get("effort_producing_downside_result"))
        failing_up = cls._safe_bool(weis_evidence.get("effort_failing_upside_result"))
        failing_down = cls._safe_bool(weis_evidence.get("effort_failing_downside_result"))

        if not isinstance(multi_scale_weis_result, dict):
            multi_scale_weis_result = {}

        dominant_wave_direction = cls._safe_str(multi_scale_weis_result.get("dominant_wave_direction"))
        coherence = cls._safe_float(multi_scale_weis_result.get("wave_coherence_score"))
        phase_permission = cls._safe_str(multi_scale_weis_result.get("phase_permission"), "BLOCKED")

        if not isinstance(gamma_matrix_result, dict):
            gamma_matrix_result = {}
            warnings.append("Missing gamma matrix result.")

        gamma_regime = cls._safe_str(gamma_matrix_result.get("net_gamma_regime"))
        wall = cls._nearest_wall_object(gamma_matrix_result)
        nearest_wall = cls._safe_float(gamma_matrix_result.get("nearest_gamma_wall"), None)

        if wall and nearest_wall is None:
            nearest_wall = cls._safe_float(wall.get("strike"), None)

        nearest_wall_type = cls._safe_str(gamma_matrix_result.get("nearest_wall_type") or (wall or {}).get("wall_type"))
        nearest_wall_status = cls._safe_str(gamma_matrix_result.get("nearest_wall_status") or (wall or {}).get("status"))
        distance_to_wall_pct = cls._wall_distance_pct(wall)

        if not isinstance(gamma_freshness_result, dict):
            gamma_freshness_result = {}
            warnings.append("Missing gamma freshness result.")

        router_state = cls._safe_str(gamma_freshness_result.get("router_state"), "YELLOW")
        gamma_data_fresh = cls._safe_bool(gamma_freshness_result.get("gamma_data_fresh"))
        confidence_modifier = cls._safe_float(gamma_freshness_result.get("phase_confidence_modifier"), 0.35)

        if not isinstance(zero_dte_result, dict):
            zero_dte_result = {}

        active_0dte = cls._safe_bool(zero_dte_result.get("active_0dte"))
        zero_dte_state = cls._safe_str(zero_dte_result.get("squeeze_state"), "NO_0DTE_ANOMALY")
        zero_dte_vol_oi_ratio = cls._safe_float(zero_dte_result.get("zero_dte_vol_oi_ratio"))
        theta_flush_risk = cls._safe_bool(zero_dte_result.get("theta_flush_risk"))
        liquidation_risk = cls._safe_bool(zero_dte_result.get("liquidation_risk"))
        zero_dte_confidence = cls._safe_float(zero_dte_result.get("confidence"))

        call_resistance = nearest_wall_status == "CALL_GAMMA_RESISTANCE"
        put_support = nearest_wall_status == "PUT_GAMMA_SUPPORT"
        pin_zone = nearest_wall_status in {"MIXED_PIN_ZONE", "MONITORING"} or nearest_wall_type == "MIXED_GAMMA_CLUSTER"

        negative_gamma = gamma_regime in {"NEGATIVE", "DEEP_NEGATIVE"}
        positive_gamma = gamma_regime in {"POSITIVE", "DEEP_POSITIVE"}

        if router_state == "RED":
            fusion_state = "WEIS_GAMMA_DATA_BLOCKED"
            fusion_direction = "BLOCKED"
            base_confidence = 0.0
            reason = "Gamma freshness router is RED. Fast-changing evidence is not safe to use."

        elif not gamma_data_fresh:
            fusion_state = "WEIS_ONLY_GAMMA_STALE"
            fusion_direction = wave_direction if wave_direction in {"UP", "DOWN"} else "UNKNOWN"
            base_confidence = 0.40
            reason = "Weis evidence exists, but Gamma data is stale. Gamma cannot confirm the phase."

        elif theta_flush_risk:
            fusion_state = "THETA_FLUSH_RISK"
            fusion_direction = "RISK"
            base_confidence = 0.65
            reason = "0DTE activity is elevated while wave efficiency is stalling late in the session."

        elif liquidation_risk and wave_direction == "DOWN" and effort_down:
            fusion_state = "WEIS_GAMMA_COLLAPSE"
            fusion_direction = "DOWN"
            base_confidence = 0.75
            reason = "Weis downwave is producing downside result while 0DTE liquidation risk is active."

        elif wave_direction == "UP" and effort_up and demand_dominance and not call_resistance:
            if active_0dte and zero_dte_state == "0DTE_UPSIDE_SQUEEZE_CONFIRMED":
                fusion_state = "WEIS_GAMMA_EXPANSION"
                fusion_direction = "UP"
                base_confidence = 0.80
                reason = "Weis upwave is producing reward and 0DTE upside squeeze confirms continuation pressure."
            elif negative_gamma:
                fusion_state = "WEIS_GAMMA_EXPANSION"
                fusion_direction = "UP"
                base_confidence = 0.70
                reason = "Weis upwave is producing reward in negative gamma where continuation can accelerate."
            else:
                fusion_state = "WEIS_EXPANSION_GAMMA_NEUTRAL"
                fusion_direction = "UP"
                base_confidence = 0.60
                reason = "Weis upwave is producing reward; Gamma is not blocking the move."

        elif wave_direction == "DOWN" and effort_down and supply_dominance and not put_support:
            if active_0dte and zero_dte_state == "0DTE_DOWNSIDE_LIQUIDATION_CONFIRMED":
                fusion_state = "WEIS_GAMMA_COLLAPSE"
                fusion_direction = "DOWN"
                base_confidence = 0.80
                reason = "Weis downwave is producing reward and 0DTE downside liquidation confirms pressure."
            elif negative_gamma:
                fusion_state = "WEIS_GAMMA_COLLAPSE"
                fusion_direction = "DOWN"
                base_confidence = 0.70
                reason = "Weis downwave is producing reward in negative gamma where downside continuation can accelerate."
            else:
                fusion_state = "WEIS_DOWNSIDE_EXPANSION_GAMMA_NEUTRAL"
                fusion_direction = "DOWN"
                base_confidence = 0.60
                reason = "Weis downwave is producing reward; Gamma is not blocking the move."

        elif wave_direction == "DOWN" and put_support and failing_down:
            fusion_state = "WEIS_GAMMA_ABSORPTION_SUPPORT"
            fusion_direction = "UP_POTENTIAL"
            base_confidence = 0.70
            reason = "Selling effort is failing to produce downside reward at a put gamma support wall."

        elif wave_direction == "UP" and call_resistance and failing_up:
            fusion_state = "WEIS_GAMMA_ABSORPTION_CEILING"
            fusion_direction = "DOWN_RISK"
            base_confidence = 0.70
            reason = "Buying effort is failing to produce upside reward at a call gamma resistance wall."

        elif pin_zone and positive_gamma and wave_efficiency < 0.75:
            fusion_state = "WEIS_GAMMA_PIN"
            fusion_direction = "NEUTRAL"
            base_confidence = 0.60
            reason = "Positive gamma / mixed wall conditions are pinning price while Weis efficiency is weak."

        else:
            fusion_state = "WEIS_GAMMA_UNRESOLVED"
            fusion_direction = wave_direction if wave_direction in {"UP", "DOWN"} else "UNKNOWN"
            base_confidence = 0.35
            reason = "No decisive Weis-Gamma fusion condition is present."

        if phase_permission == "BLOCKED" and fusion_state not in {"WEIS_GAMMA_DATA_BLOCKED", "THETA_FLUSH_RISK"}:
            warnings.append("Multi-scale Weis phase permission is BLOCKED.")
            base_confidence *= 0.60

        confidence = cls._confidence(
            base=base_confidence,
            coherence=coherence,
            freshness_modifier=confidence_modifier,
            zero_dte_confidence=zero_dte_confidence,
        )

        status = "OK" if fusion_state not in {"WEIS_GAMMA_DATA_BLOCKED"} else "BLOCKED"

        return WeisGammaFusionResult(
            symbol=symbol,
            engine="WEIS_GAMMA_FUSION",
            status=status,
            fusion_state=fusion_state,
            fusion_direction=fusion_direction,
            gamma_regime=gamma_regime,
            router_state=router_state,
            weis_wave_direction=wave_direction,
            dominant_wave_direction=dominant_wave_direction,
            wave_coherence_score=round(coherence, 4),
            phase_permission=phase_permission,
            nearest_gamma_wall=nearest_wall,
            nearest_wall_type=nearest_wall_type,
            nearest_wall_status=nearest_wall_status,
            distance_to_wall_pct=distance_to_wall_pct,
            active_0dte=active_0dte,
            zero_dte_state=zero_dte_state,
            zero_dte_vol_oi_ratio=round(zero_dte_vol_oi_ratio, 4),
            theta_flush_risk=theta_flush_risk,
            liquidation_risk=liquidation_risk,
            gamma_data_fresh=gamma_data_fresh,
            phase_confidence_modifier=round(confidence_modifier, 4),
            confidence=confidence,
            reason=reason,
            warnings=warnings,
        ).to_dict()
