"""
Sigmalytic V2 Phase C2 — Diagnostic Doctrine Classifier

Diagnostic-only explanation engine.

This module reads existing campaign evidence and returns human-readable
doctrine labels and interpretations.

It must not change score, rank, campaign state, transition eligibility,
Supabase data, frontend data, or campaign evidence.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


class DiagnosticDoctrineClassifier:
    ENGINE = "DIAGNOSTIC_DOCTRINE_CLASSIFIER"
    VERSION = "phase_c2_diagnostic_only_v1"

    GUARDRAILS = {
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "output_type": "explanatory_diagnostic",
        "source": "v2_phase_b_doctrine_mapping_table",
    }

    def classify(
        self,
        evidence: Optional[Dict[str, Any]],
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        ev = deepcopy(evidence or {})
        labels: List[str] = []
        warnings: List[str] = []

        self._operator_control(ev, labels)
        self._wyckoff(ev, labels)
        self._weis(ev, labels)
        self._vsa(ev, labels)
        self._distribution_risk(ev, labels)
        self._context(ev, labels, warnings)

        conflicts = self._conflicts(labels)
        warnings.extend(conflicts)

        if not labels:
            labels.append("INSUFFICIENT_EVIDENCE")
            warnings.append("No diagnostic doctrine labels were produced.")

        label_list = sorted(set(labels))

        return {
            "engine": self.ENGINE,
            "version": self.VERSION,
            "status": "OK",
            **self.GUARDRAILS,
            "wired_into_evidence_builder": True,
            "symbol": symbol,
            "overall_interpretation": self._overall(label_list),
            "doctrine_labels": label_list,
            "operator_control_interpretation": self._operator_summary(ev),
            "wyckoff_interpretation": self._wyckoff_summary(ev),
            "weis_interpretation": self._weis_summary(ev),
            "vsa_interpretation": self._vsa_summary(ev),
            "distribution_risk_interpretation": {
                "present": "DISTRIBUTION_RISK_PRESENT" in label_list,
                "summary": (
                    "Distribution-risk evidence is present."
                    if "DISTRIBUTION_RISK_PRESENT" in label_list
                    else "No distribution-risk label was produced."
                ),
            },
            "conflict_interpretation": {
                "conflicts_present": bool(conflicts),
                "conflicts": conflicts,
            },
            "blocking_warnings": warnings,
            "evidence_references": self._sections_present(ev),
        }

    def _operator_control(self, ev: Dict[str, Any], labels: List[str]) -> None:
        oc = ev.get("operator_control") or {}
        if oc.get("operator_control_confirmed") is True:
            labels.append("OPERATOR_CONTROL_CONFIRMED")

    def _wyckoff(self, ev: Dict[str, Any], labels: List[str]) -> None:
        wd = ev.get("wyckoff_doctrine") or {}
        scores = wd.get("scores") or {}
        survival = wd.get("survival") or {}

        spring = self._num(scores.get("spring_score"))
        sos = self._num(scores.get("sign_of_strength_score"))
        absorption = self._num(scores.get("supply_absorption_score"))
        absorption_cont = self._num(scores.get("absorption_continuation_score"))
        lps = self._num(scores.get("lps_quality_score"))

        if spring >= 70:
            labels.append("SPRING_SUPPORT_PRESENT")

        if sos >= 70:
            labels.append("SOS_SUPPORT_PRESENT")

        if absorption >= 70 or absorption_cont >= 70:
            labels.append("ABSORPTION_SUPPORT_PRESENT")

        if spring >= 70 or absorption >= 70 or absorption_cont >= 70 or lps >= 70:
            labels.append("WYCKOFF_ACCUMULATION_SUPPORT")

        if survival.get("survival_confirmed") is True:
            labels.append("WYCKOFF_SURVIVAL_PRESENT")
        elif str(survival.get("survival_state") or "").upper() in {"AT_RISK", "FAILURE_RISK"}:
            labels.append("WYCKOFF_SURVIVAL_AT_RISK")

    def _weis(self, ev: Dict[str, Any], labels: List[str]) -> None:
        weis = ev.get("multi_scale_weis") or {}
        dominant = str(weis.get("dominant_wave_direction") or "").upper()
        conflict = str(weis.get("conflict_state") or "").upper()
        permission = str(weis.get("phase_permission") or "").upper()

        if conflict and conflict != "ALIGNED":
            labels.append("WEIS_CONFLICT_PRESENT")

        if dominant == "UP" and conflict == "ALIGNED":
            labels.append("WEIS_ALIGNED_UP")

        if dominant == "UP" and "EXPANSION" in permission:
            labels.append("WEIS_EXPANSION_SUPPORT")

    def _vsa(self, ev: Dict[str, Any], labels: List[str]) -> None:
        evidence = ((ev.get("vsa_weis_overlay") or {}).get("evidence") or {})

        if evidence.get("no_supply_test") is True:
            labels.append("VSA_NO_SUPPLY_SUPPORT")

        if evidence.get("no_demand_test") is True:
            labels.append("VSA_NO_DEMAND_CAUTION")

        if evidence.get("upthrust_supply") is True:
            labels.append("VSA_UPTHRUST_RISK")

        if evidence.get("buying_climax") is True:
            labels.append("VSA_BUYING_CLIMAX_RISK")

    def _distribution_risk(self, ev: Dict[str, Any], labels: List[str]) -> None:
        evidence = ((ev.get("vsa_weis_overlay") or {}).get("evidence") or {})

        if (
            evidence.get("no_demand_test") is True
            or evidence.get("upthrust_supply") is True
            or evidence.get("buying_climax") is True
            or self._scale_flag(ev, "effort_failing_upside_result")
            or self._scale_flag(ev, "shortening_upside_thrust")
            or self._scale_flag(ev, "supply_dominance")
        ):
            labels.append("DISTRIBUTION_RISK_PRESENT")

    def _context(self, ev: Dict[str, Any], labels: List[str], warnings: List[str]) -> None:
        profile = ev.get("symbol_behavior_profile") or {}
        if str(profile.get("liquidity_class") or "").upper() == "LOW_LIQUIDITY":
            labels.append("LOW_LIQUIDITY_CAUTION")
            warnings.append("Low liquidity may weaken volume-based doctrine interpretation.")

    def _conflicts(self, labels: List[str]) -> List[str]:
        s = set(labels)
        conflicts: List[str] = []

        if "OPERATOR_CONTROL_CONFIRMED" in s and "VSA_NO_DEMAND_CAUTION" in s:
            conflicts.append("Legacy operator-control evidence is present, but VSA no-demand caution is present.")

        if "WEIS_EXPANSION_SUPPORT" in s and "WYCKOFF_SURVIVAL_AT_RISK" in s:
            conflicts.append("Weis expansion support exists, but Wyckoff survival remains at risk.")

        if "WEIS_ALIGNED_UP" in s and "VSA_NO_DEMAND_CAUTION" in s:
            conflicts.append("Weis waves align upward, but VSA demand quality is suspect.")

        if "LOW_LIQUIDITY_CAUTION" in s:
            conflicts.append("Low liquidity requires caution when interpreting volume evidence.")

        return conflicts

    def _overall(self, labels: List[str]) -> str:
        s = set(labels)
        parts: List[str] = []

        if "OPERATOR_CONTROL_CONFIRMED" in s:
            parts.append("Legacy operator-control evidence is present; D3D production confirmation is not implied.")

        if "WYCKOFF_ACCUMULATION_SUPPORT" in s:
            parts.append("Wyckoff evidence supports accumulation behavior.")
        elif "SOS_SUPPORT_PRESENT" in s:
            parts.append("Wyckoff sign-of-strength evidence is present.")
        elif "SPRING_SUPPORT_PRESENT" in s:
            parts.append("Wyckoff spring evidence is present.")
        elif "ABSORPTION_SUPPORT_PRESENT" in s:
            parts.append("Wyckoff absorption evidence is present.")

        if "WYCKOFF_SURVIVAL_PRESENT" in s:
            parts.append("Wyckoff survival evidence is present.")
        elif "WYCKOFF_SURVIVAL_AT_RISK" in s:
            parts.append("Wyckoff survival remains at risk.")

        if "WEIS_EXPANSION_SUPPORT" in s:
            parts.append("Weis wave evidence supports expansion.")
        elif "WEIS_ALIGNED_UP" in s:
            parts.append("Weis wave evidence is aligned upward.")

        if "VSA_NO_DEMAND_CAUTION" in s:
            parts.append("VSA no-demand caution is present.")
        elif "VSA_NO_SUPPLY_SUPPORT" in s:
            parts.append("VSA no-supply support is present.")

        if "DISTRIBUTION_RISK_PRESENT" in s:
            parts.append("Distribution-risk evidence is present.")

        if "LOW_LIQUIDITY_CAUTION" in s:
            parts.append("Low liquidity requires caution.")

        return " ".join(parts) if parts else "Evidence is insufficient for doctrine interpretation."

    def _operator_summary(self, ev: Dict[str, Any]) -> Dict[str, Any]:
        oc = ev.get("operator_control") or {}
        return {
            "confirmed": bool(oc.get("operator_control_confirmed")),
            "verdict": oc.get("verdict"),
            "evidence_count": oc.get("evidence_count"),
            "not_derived_from_scores": bool(oc.get("not_derived_from_scores")),
        }

    def _wyckoff_summary(self, ev: Dict[str, Any]) -> Dict[str, Any]:
        wd = ev.get("wyckoff_doctrine") or {}
        return {
            "phase": wd.get("phase"),
            "status": wd.get("status"),
            "scores": wd.get("scores") or {},
            "survival": (wd.get("survival") or {}),
        }

    def _weis_summary(self, ev: Dict[str, Any]) -> Dict[str, Any]:
        w = ev.get("multi_scale_weis") or {}
        return {
            "dominant_wave_direction": w.get("dominant_wave_direction"),
            "conflict_state": w.get("conflict_state"),
            "phase_permission": w.get("phase_permission"),
            "wave_coherence_score": w.get("wave_coherence_score"),
        }

    def _vsa_summary(self, ev: Dict[str, Any]) -> Dict[str, Any]:
        v = ev.get("vsa_weis_overlay") or {}
        return {
            "vsa_bias": v.get("vsa_bias"),
            "vsa_alert": v.get("vsa_alert"),
            "evidence": v.get("evidence") or {},
        }

    def _sections_present(self, ev: Dict[str, Any]) -> Dict[str, bool]:
        sections = [
            "raw_metrics",
            "operator_control",
            "wyckoff_doctrine",
            "multi_scale_weis",
            "vsa_weis_overlay",
            "transition_readiness",
            "symbol_behavior_profile",
        ]
        return {name: bool(ev.get(name)) for name in sections}

    def _scale_flag(self, ev: Dict[str, Any], flag: str) -> bool:
        scales = ((ev.get("multi_scale_weis") or {}).get("scales") or {})
        for name in ("micro", "meso", "macro"):
            evidence = ((scales.get(name) or {}).get("evidence") or {})
            if evidence.get(flag) is True:
                return True
        return False

    def _num(self, value: Any) -> float:
        try:
            return float(value or 0.0)
        except Exception:
            return 0.0


def classify_diagnostic_doctrine(
    evidence: Optional[Dict[str, Any]],
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    return DiagnosticDoctrineClassifier().classify(evidence=evidence, symbol=symbol)


__all__ = ["DiagnosticDoctrineClassifier", "classify_diagnostic_doctrine"]
