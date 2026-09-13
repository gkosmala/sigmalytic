from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

import math


@dataclass
class WeisGammaRankingResult:
    symbol: str
    engine: str
    status: str

    rank_score: float
    rank_bucket: str
    rank_direction: str
    rank_reason: str

    weis_phase: str
    mapped_campaign_state: str
    phase_confidence: float

    wave_direction: str
    wave_distance_atr: float
    wave_volume_z: float
    wave_efficiency: float
    wave_coherence_score: float

    gamma_regime: str
    nearest_gamma_wall: Optional[float]
    nearest_wall_type: Optional[str]
    nearest_wall_status: Optional[str]
    gamma_data_fresh: bool
    router_state: str

    active_0dte: bool
    zero_dte_state: str
    zero_dte_vol_oi_ratio: float
    theta_flush_risk: bool
    liquidation_risk: bool

    opportunity_score: float
    risk_penalty: float
    freshness_penalty: float
    gamma_bonus: float
    wave_quality_bonus: float

    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WeisGammaRankingEngine:
    """
    Weis-Gamma Ranking Engine.

    Purpose:
    - Rank Weis-Gamma opportunities after the phase engine has classified them.
    - Keep ranking separate from state transition.
    - Reward high-quality Weis wave behavior.
    - Reward fresh Gamma confirmation.
    - Penalize stale Gamma, theta-flush risk, pin risk, liquidation risk,
      and blocked data.

    This module does NOT create trades.
    This module does NOT change campaign state.
    This module orders attention.
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
        return evidence if isinstance(evidence, dict) else {}

    @classmethod
    def _phase_base_score(cls, phase: str) -> float:
        phase = cls._safe_str(phase)

        scores = {
            "NO_WEIS_STRUCTURE": 0.0,
            "WEIS_DATA_BLOCKED": 0.0,
            "WEIS_BASELINE": 18.0,
            "WEIS_ABSORPTION": 58.0,
            "WEIS_TEST": 62.0,
            "WEIS_TURN": 68.0,
            "WEIS_EXPANSION": 76.0,
            "WEIS_GAMMA_EXPANSION": 88.0,
            "WEIS_GAMMA_PINNED": 42.0,
            "WEIS_GAMMA_COLLAPSE": 20.0,
            "WEIS_EXHAUSTION": 35.0,
            "WEIS_THETA_FLUSH_RISK": 28.0,
            "WEIS_FAILED_CAMPAIGN": 0.0,
            "WEIS_ONLY_GAMMA_STALE": 48.0,
        }

        return scores.get(phase, 25.0)

    @classmethod
    def _wave_quality_bonus(
        cls,
        wave_distance_atr: float,
        wave_volume_z: float,
        wave_efficiency: float,
        coherence: float,
    ) -> float:
        distance_component = min(max(wave_distance_atr, 0.0) / 3.0, 1.0) * 5.0
        volume_component = min(max(abs(wave_volume_z), 0.0) / 3.0, 1.0) * 4.0
        efficiency_component = min(max(wave_efficiency, 0.0) / 3.0, 1.0) * 6.0
        coherence_component = min(abs(coherence), 1.0) * 5.0

        return round(distance_component + volume_component + efficiency_component + coherence_component, 4)

    @classmethod
    def _gamma_bonus(
        cls,
        phase: str,
        gamma_regime: str,
        nearest_wall_status: str,
        gamma_data_fresh: bool,
        active_0dte: bool,
        zero_dte_state: str,
    ) -> float:
        if not gamma_data_fresh:
            return 0.0

        bonus = 0.0

        if phase == "WEIS_GAMMA_EXPANSION":
            bonus += 6.0

        if zero_dte_state == "0DTE_UPSIDE_SQUEEZE_CONFIRMED":
            bonus += 4.0

        if nearest_wall_status == "PUT_GAMMA_SUPPORT" and phase in {"WEIS_ABSORPTION", "WEIS_TEST", "WEIS_TURN"}:
            bonus += 4.0

        if gamma_regime in {"NEGATIVE", "DEEP_NEGATIVE"} and phase in {"WEIS_EXPANSION", "WEIS_GAMMA_EXPANSION"}:
            bonus += 3.0

        if gamma_regime in {"POSITIVE", "DEEP_POSITIVE"} and nearest_wall_status == "MIXED_PIN_ZONE":
            bonus -= 3.0

        if active_0dte and zero_dte_state == "0DTE_SQUEEZE_BUILDING":
            bonus += 2.0

        return round(bonus, 4)

    @classmethod
    def _risk_penalty(
        cls,
        weis_phase: str,
        router_state: str,
        gamma_data_fresh: bool,
        theta_flush_risk: bool,
        liquidation_risk: bool,
        nearest_wall_status: str,
        zero_dte_state: str,
    ) -> float:
        penalty = 0.0

        if router_state == "RED":
            penalty += 100.0

        if router_state == "YELLOW":
            penalty += 12.0

        if not gamma_data_fresh:
            penalty += 18.0

        if theta_flush_risk or weis_phase == "WEIS_THETA_FLUSH_RISK":
            penalty += 25.0

        if liquidation_risk or weis_phase == "WEIS_GAMMA_COLLAPSE":
            penalty += 40.0

        if weis_phase == "WEIS_EXHAUSTION":
            penalty += 18.0

        if weis_phase == "WEIS_GAMMA_PINNED":
            penalty += 15.0

        if nearest_wall_status == "CALL_GAMMA_RESISTANCE" and weis_phase in {"WEIS_EXPANSION", "WEIS_GAMMA_EXPANSION"}:
            penalty += 10.0

        if zero_dte_state == "0DTE_DOWNSIDE_LIQUIDATION_CONFIRMED":
            penalty += 20.0

        return round(penalty, 4)

    @classmethod
    def _freshness_penalty(cls, router_state: str, gamma_data_fresh: bool) -> float:
        if router_state == "RED":
            return 100.0

        if not gamma_data_fresh:
            return 20.0

        if router_state == "YELLOW":
            return 10.0

        return 0.0

    @classmethod
    def _bucket(cls, score: float, weis_phase: str, router_state: str) -> str:
        if router_state == "RED" or weis_phase in {"WEIS_DATA_BLOCKED", "WEIS_FAILED_CAMPAIGN"}:
            return "BLOCKED"

        if score >= 90:
            return "A_PLUS"
        if score >= 80:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "WATCHLIST"
        if score >= 35:
            return "LOW_PRIORITY"
        return "AVOID"

    @classmethod
    def _direction(cls, phase_direction: str, fusion_direction: str, wave_direction: str) -> str:
        for value in [phase_direction, fusion_direction, wave_direction]:
            text = cls._safe_str(value)
            if text in {"UP", "DOWN", "UP_POTENTIAL", "DOWN_RISK", "RISK", "NEUTRAL", "BLOCKED"}:
                return text

        return "UNKNOWN"

    @classmethod
    def _rank_reason(cls, bucket: str, phase: str, score: float, risk_penalty: float, gamma_data_fresh: bool) -> str:
        if bucket == "BLOCKED":
            return "Blocked by data freshness or failed Weis-Gamma structure."

        if phase == "WEIS_GAMMA_EXPANSION":
            return "Fresh Weis-Gamma expansion with strong ranking score."

        if phase == "WEIS_ABSORPTION":
            return "Developing opportunity: selling effort is being absorbed."

        if phase == "WEIS_ONLY_GAMMA_STALE":
            return "Weis evidence remains, but Gamma is stale; refresh required before confirmation."

        if phase == "WEIS_THETA_FLUSH_RISK":
            return "Theta-flush risk active; ranking suppressed."

        if phase == "WEIS_GAMMA_COLLAPSE":
            return "Downside collapse risk active; avoid long confirmation."

        if not gamma_data_fresh:
            return "Gamma data stale; ranking downgraded."

        if risk_penalty >= 25:
            return "Risk penalty materially reduced ranking."

        if score >= 70:
            return "High-quality Weis-Gamma candidate."

        return "Monitor only; evidence is not yet strong enough."

    @classmethod
    def build(
        cls,
        symbol: str,
        weis_phase_result: Optional[Dict[str, Any]] = None,
        weis_wave_result: Optional[Dict[str, Any]] = None,
        multi_scale_weis_result: Optional[Dict[str, Any]] = None,
        gamma_matrix_result: Optional[Dict[str, Any]] = None,
        gamma_freshness_result: Optional[Dict[str, Any]] = None,
        zero_dte_result: Optional[Dict[str, Any]] = None,
        weis_gamma_fusion_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        warnings: List[str] = []

        if not isinstance(weis_phase_result, dict):
            weis_phase_result = {}
            warnings.append("Missing Weis phase result.")

        weis_evidence = cls._latest_weis_evidence(weis_wave_result)

        if not isinstance(multi_scale_weis_result, dict):
            multi_scale_weis_result = {}

        if not isinstance(gamma_matrix_result, dict):
            gamma_matrix_result = {}

        if not isinstance(gamma_freshness_result, dict):
            gamma_freshness_result = {}

        if not isinstance(zero_dte_result, dict):
            zero_dte_result = {}

        if not isinstance(weis_gamma_fusion_result, dict):
            weis_gamma_fusion_result = {}

        weis_phase = cls._safe_str(weis_phase_result.get("weis_phase"), "NO_WEIS_STRUCTURE")
        mapped_campaign_state = cls._safe_str(weis_phase_result.get("mapped_campaign_state"), "NO_CAMPAIGN")
        phase_confidence = cls._safe_float(weis_phase_result.get("phase_confidence"))
        phase_direction = cls._safe_str(weis_phase_result.get("phase_direction"))

        wave_direction = cls._safe_str(weis_evidence.get("wave_direction"))
        wave_distance_atr = cls._safe_float(weis_evidence.get("wave_distance_atr"))
        wave_volume_z = cls._safe_float(weis_evidence.get("wave_volume_z"))
        wave_efficiency = cls._safe_float(weis_evidence.get("wave_efficiency"))

        coherence = cls._safe_float(
            multi_scale_weis_result.get("wave_coherence_score")
            or weis_phase_result.get("wave_coherence_score")
        )

        gamma_regime = cls._safe_str(gamma_matrix_result.get("net_gamma_regime"))
        nearest_gamma_wall = gamma_matrix_result.get("nearest_gamma_wall")
        nearest_wall_type = gamma_matrix_result.get("nearest_wall_type")
        nearest_wall_status = gamma_matrix_result.get("nearest_wall_status")

        router_state = cls._safe_str(
            gamma_freshness_result.get("router_state")
            or weis_phase_result.get("router_state"),
            "YELLOW",
        )

        gamma_data_fresh = cls._safe_bool(
            gamma_freshness_result.get("gamma_data_fresh")
            if "gamma_data_fresh" in gamma_freshness_result
            else weis_phase_result.get("gamma_data_fresh")
        )

        active_0dte = cls._safe_bool(zero_dte_result.get("active_0dte"))
        zero_dte_state = cls._safe_str(zero_dte_result.get("squeeze_state"), "NO_0DTE_ANOMALY")
        zero_dte_vol_oi_ratio = cls._safe_float(zero_dte_result.get("zero_dte_vol_oi_ratio"))
        theta_flush_risk = cls._safe_bool(
            zero_dte_result.get("theta_flush_risk")
            or weis_phase_result.get("theta_flush_risk")
        )
        liquidation_risk = cls._safe_bool(
            zero_dte_result.get("liquidation_risk")
            or weis_phase_result.get("liquidation_risk")
        )

        fusion_direction = cls._safe_str(weis_gamma_fusion_result.get("fusion_direction"))
        rank_direction = cls._direction(phase_direction, fusion_direction, wave_direction)

        base = cls._phase_base_score(weis_phase)
        confidence_component = phase_confidence * 10.0
        wave_bonus = cls._wave_quality_bonus(
            wave_distance_atr=wave_distance_atr,
            wave_volume_z=wave_volume_z,
            wave_efficiency=wave_efficiency,
            coherence=coherence,
        )
        gamma_bonus = cls._gamma_bonus(
            phase=weis_phase,
            gamma_regime=gamma_regime,
            nearest_wall_status=cls._safe_str(nearest_wall_status),
            gamma_data_fresh=gamma_data_fresh,
            active_0dte=active_0dte,
            zero_dte_state=zero_dte_state,
        )
        risk_penalty = cls._risk_penalty(
            weis_phase=weis_phase,
            router_state=router_state,
            gamma_data_fresh=gamma_data_fresh,
            theta_flush_risk=theta_flush_risk,
            liquidation_risk=liquidation_risk,
            nearest_wall_status=cls._safe_str(nearest_wall_status),
            zero_dte_state=zero_dte_state,
        )
        freshness_penalty = cls._freshness_penalty(router_state, gamma_data_fresh)

        raw_score = base + confidence_component + wave_bonus + gamma_bonus - risk_penalty
        raw_score -= max(0.0, freshness_penalty - risk_penalty)

        rank_score = round(max(0.0, min(raw_score, 100.0)), 4)
        bucket = cls._bucket(rank_score, weis_phase, router_state)

        reason = cls._rank_reason(
            bucket=bucket,
            phase=weis_phase,
            score=rank_score,
            risk_penalty=risk_penalty,
            gamma_data_fresh=gamma_data_fresh,
        )

        status = "OK" if bucket != "BLOCKED" else "BLOCKED"

        return WeisGammaRankingResult(
            symbol=symbol,
            engine="WEIS_GAMMA_RANKING",
            status=status,
            rank_score=rank_score,
            rank_bucket=bucket,
            rank_direction=rank_direction,
            rank_reason=reason,
            weis_phase=weis_phase,
            mapped_campaign_state=mapped_campaign_state,
            phase_confidence=round(phase_confidence, 4),
            wave_direction=wave_direction,
            wave_distance_atr=round(wave_distance_atr, 4),
            wave_volume_z=round(wave_volume_z, 4),
            wave_efficiency=round(wave_efficiency, 6),
            wave_coherence_score=round(coherence, 4),
            gamma_regime=gamma_regime,
            nearest_gamma_wall=cls._safe_float(nearest_gamma_wall, None) if nearest_gamma_wall is not None else None,
            nearest_wall_type=nearest_wall_type,
            nearest_wall_status=nearest_wall_status,
            gamma_data_fresh=gamma_data_fresh,
            router_state=router_state,
            active_0dte=active_0dte,
            zero_dte_state=zero_dte_state,
            zero_dte_vol_oi_ratio=round(zero_dte_vol_oi_ratio, 4),
            theta_flush_risk=theta_flush_risk,
            liquidation_risk=liquidation_risk,
            opportunity_score=round(base + confidence_component + wave_bonus + gamma_bonus, 4),
            risk_penalty=risk_penalty,
            freshness_penalty=freshness_penalty,
            gamma_bonus=gamma_bonus,
            wave_quality_bonus=wave_bonus,
            warnings=warnings,
        ).to_dict()
