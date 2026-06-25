from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import math
import pandas as pd

from backend.structural.weis_wave_engine import WeisWaveEngine


@dataclass
class MultiScaleWeisResult:
    symbol: str
    engine: str
    status: str

    micro_direction: str
    meso_direction: str
    macro_direction: str

    micro_reversal_quality: str
    dominant_wave_direction: str
    wave_coherence_score: float
    conflict_state: str
    phase_permission: str

    micro_wave_count: int
    meso_wave_count: int
    macro_wave_count: int

    scales: Dict[str, Any]
    warnings: list[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MultiScaleWeisEngine:
    """
    Fractional Multi-Scale Weis Engine.

    Purpose:
    - Run Weis Wave analysis at Micro, Meso, and Macro reversal scales.
    - Avoid crude binary alignment.
    - Allow micro reversals to lead, but not override larger structure.
    - Produce a fractional wave coherence score.
    - Classify whether evidence is BLOCKED, PROBATIONARY, ALLOWED_SMALL,
      ALLOWED_FULL, or EXPANSION_CONFIRMED.

    This module does NOT trade.
    This module does NOT use Wyckoff or Livermore.
    This module prepares Weis-only phase evidence.
    """

    DEFAULT_SCALES = {
        "micro": 1.0,
        "meso": 2.0,
        "macro": 3.5,
    }

    DEFAULT_WEIGHTS = {
        "micro": 0.20,
        "meso": 0.30,
        "macro": 0.50,
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

    @classmethod
    def _direction_score(cls, direction: str) -> float:
        direction = str(direction or "").upper()

        if direction == "UP":
            return 1.0
        if direction == "DOWN":
            return -1.0
        return 0.0

    @classmethod
    def _evidence_strength(cls, result: Dict[str, Any]) -> float:
        """
        Convert a Weis wave result into a 0..1 quality score.

        This is not a trading score.
        It is used only to weight directional evidence.
        """
        evidence = result.get("evidence") or {}

        distance_atr = cls._safe_float(evidence.get("wave_distance_atr"))
        efficiency = cls._safe_float(evidence.get("wave_efficiency"))
        volume_z = cls._safe_float(evidence.get("wave_volume_z"))

        producing = bool(
            evidence.get("effort_producing_upside_result")
            or evidence.get("effort_producing_downside_result")
        )

        failing = bool(
            evidence.get("effort_failing_upside_result")
            or evidence.get("effort_failing_downside_result")
        )

        # Normalize components.
        distance_component = min(distance_atr / 3.0, 1.0)
        efficiency_component = min(efficiency / 3.0, 1.0)
        volume_component = min(abs(volume_z) / 3.0, 1.0)

        strength = (
            0.40 * distance_component
            + 0.35 * efficiency_component
            + 0.25 * volume_component
        )

        if producing:
            strength += 0.15

        if failing:
            strength -= 0.20

        return round(max(0.0, min(strength, 1.0)), 4)

    @classmethod
    def _extract_direction(cls, result: Dict[str, Any]) -> str:
        evidence = result.get("evidence") or {}
        return str(evidence.get("wave_direction") or "UNKNOWN").upper()

    @classmethod
    def _is_extreme_micro_reversal(
        cls,
        micro: Dict[str, Any],
        meso_direction: str,
        macro_direction: str,
    ) -> bool:
        """
        A micro reversal is only considered extreme if:
        - micro turns against meso/macro,
        - distance and efficiency are strong,
        - and either volume is extreme or effort/result confirms.

        This avoids blocking the first real turn while still preventing
        weak micro wiggles from overriding larger structure.
        """
        evidence = micro.get("evidence") or {}

        micro_direction = str(evidence.get("wave_direction") or "UNKNOWN").upper()

        if micro_direction not in {"UP", "DOWN"}:
            return False

        larger_against = (
            (micro_direction == "UP" and (meso_direction == "DOWN" or macro_direction == "DOWN"))
            or (micro_direction == "DOWN" and (meso_direction == "UP" or macro_direction == "UP"))
        )

        if not larger_against:
            return False

        distance_atr = cls._safe_float(evidence.get("wave_distance_atr"))
        efficiency = cls._safe_float(evidence.get("wave_efficiency"))
        volume_z = cls._safe_float(evidence.get("wave_volume_z"))

        producing = bool(
            evidence.get("effort_producing_upside_result")
            or evidence.get("effort_producing_downside_result")
        )

        extreme_volume = volume_z >= 3.0
        extreme_efficiency = efficiency >= 2.0
        strong_distance = distance_atr >= 1.5

        return bool(strong_distance and producing and (extreme_volume or extreme_efficiency))

    @classmethod
    def _dominant_direction_from_score(cls, score: float) -> str:
        if score >= 0.20:
            return "UP"
        if score <= -0.20:
            return "DOWN"
        return "NEUTRAL"

    @classmethod
    def _conflict_state(
        cls,
        micro_direction: str,
        meso_direction: str,
        macro_direction: str,
    ) -> str:
        directions = [micro_direction, meso_direction, macro_direction]
        active = [d for d in directions if d in {"UP", "DOWN"}]

        if len(active) < 2:
            return "INSUFFICIENT_DIRECTION"

        if len(set(active)) == 1:
            return "ALIGNED"

        if micro_direction in {"UP", "DOWN"} and meso_direction == macro_direction and micro_direction != meso_direction:
            return "MICRO_AGAINST_LARGER_STRUCTURE"

        return "MIXED"

    @classmethod
    def _phase_permission(
        cls,
        coherence_score: float,
        dominant_direction: str,
        conflict_state: str,
        extreme_micro_reversal: bool,
    ) -> str:
        """
        This is phase permission, not trade permission.

        It describes how much confidence the Weis phase engine should place
        in the current multi-scale wave structure.
        """
        if dominant_direction == "NEUTRAL":
            return "BLOCKED"

        if conflict_state == "MICRO_AGAINST_LARGER_STRUCTURE":
            return "PROBATIONARY" if extreme_micro_reversal else "BLOCKED"

        if conflict_state == "MIXED":
            return "ALLOWED_SMALL" if abs(coherence_score) >= 0.25 else "PROBATIONARY"

        if conflict_state == "ALIGNED":
            if abs(coherence_score) >= 0.70:
                return "EXPANSION_CONFIRMED"
            if abs(coherence_score) >= 0.45:
                return "ALLOWED_FULL"
            if abs(coherence_score) >= 0.25:
                return "ALLOWED_SMALL"

        return "BLOCKED"

    @classmethod
    def build(
        cls,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        lookback: int = 180,
        scales: Optional[Dict[str, float]] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        scales = scales or cls.DEFAULT_SCALES
        weights = weights or cls.DEFAULT_WEIGHTS

        warnings: list[str] = []

        scale_results: Dict[str, Any] = {}

        for scale_name, reversal_atr in scales.items():
            result = WeisWaveEngine.build(
                df=df,
                symbol=symbol,
                reversal_atr=float(reversal_atr),
                lookback=lookback,
            )

            evidence = result.get("evidence") or {}
            direction = cls._extract_direction(result)
            strength = cls._evidence_strength(result)
            direction_score = cls._direction_score(direction)
            weighted_score = direction_score * strength * cls._safe_float(weights.get(scale_name, 0.0))

            scale_results[scale_name] = {
                "reversal_atr": reversal_atr,
                "status": result.get("status"),
                "wave_count": int(result.get("wave_count") or 0),
                "direction": direction,
                "strength": strength,
                "weighted_score": round(weighted_score, 4),
                "latest_wave": result.get("latest_wave"),
                "evidence": evidence,
                "warnings": result.get("warnings") or [],
            }

        micro = scale_results.get("micro", {})
        meso = scale_results.get("meso", {})
        macro = scale_results.get("macro", {})

        micro_direction = str(micro.get("direction") or "UNKNOWN").upper()
        meso_direction = str(meso.get("direction") or "UNKNOWN").upper()
        macro_direction = str(macro.get("direction") or "UNKNOWN").upper()

        weighted_total = sum(cls._safe_float(v.get("weighted_score")) for v in scale_results.values())
        total_weight = sum(cls._safe_float(weights.get(k, 0.0)) for k in scale_results.keys())

        coherence_score = round(weighted_total / total_weight, 4) if total_weight > 0 else 0.0
        dominant_direction = cls._dominant_direction_from_score(coherence_score)
        conflict = cls._conflict_state(micro_direction, meso_direction, macro_direction)

        extreme_micro = cls._is_extreme_micro_reversal(
            micro=micro,
            meso_direction=meso_direction,
            macro_direction=macro_direction,
        )

        micro_reversal_quality = "EXTREME" if extreme_micro else "NORMAL"

        phase_permission = cls._phase_permission(
            coherence_score=coherence_score,
            dominant_direction=dominant_direction,
            conflict_state=conflict,
            extreme_micro_reversal=extreme_micro,
        )

        statuses = [str(v.get("status")) for v in scale_results.values()]
        if all(s == "NO_COMPLETED_WAVES" for s in statuses):
            status = "NO_COMPLETED_WAVES"
            warnings.append("No completed waves across micro, meso, or macro scales.")
        elif any(s == "OK" for s in statuses):
            status = "OK"
        else:
            status = "LIMITED"

        result = MultiScaleWeisResult(
            symbol=symbol,
            engine="MULTI_SCALE_WEIS",
            status=status,
            micro_direction=micro_direction,
            meso_direction=meso_direction,
            macro_direction=macro_direction,
            micro_reversal_quality=micro_reversal_quality,
            dominant_wave_direction=dominant_direction,
            wave_coherence_score=coherence_score,
            conflict_state=conflict,
            phase_permission=phase_permission,
            micro_wave_count=int(micro.get("wave_count") or 0),
            meso_wave_count=int(meso.get("wave_count") or 0),
            macro_wave_count=int(macro.get("wave_count") or 0),
            scales=scale_results,
            warnings=warnings,
        )

        return result.to_dict()
