import json

from fastapi import APIRouter
from typing import Any, Dict, List

from backend.campaign_engine.campaign_store import CampaignStore

router = APIRouter(
    prefix="/api/campaign",
    tags=["campaign"],
)


def _store():
    return CampaignStore()


def _json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    return {}


def _first_warning(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return ""


def _attach_weis_gamma_summary(campaign: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add frontend-friendly Weis-Gamma summary fields.

    This is display/API enrichment only.
    It does not alter campaign lifecycle transitions.
    """
    out = dict(campaign or {})

    evidence = _json_dict(
        out.get("evidence")
        or out.get("evidence_payload")
        or {}
    )

    raw_metrics = (
        evidence.get("raw_metrics")
        if isinstance(evidence, dict)
        else {}
    )

    if not isinstance(raw_metrics, dict):
        raw_metrics = {}

    wg = evidence.get("weis_gamma") if isinstance(evidence, dict) else None

    if not isinstance(wg, dict):
        out["weis_gamma_present"] = False
        out["weis_gamma_status"] = "NOT_PRESENT"
        out["weis_gamma_wired"] = False
        out["weis_gamma_transition_enabled"] = False
        out["weis_gamma_phase"] = None
        out["weis_gamma_mapped_state"] = None
        out["weis_gamma_rank_score"] = None
        out["weis_gamma_rank_bucket"] = None
        out["weis_gamma_gamma_status"] = None
        out["weis_gamma_effective_gamma_status"] = None
        out["weis_gamma_fusion_state"] = None
        out["weis_gamma_effective_fusion_state"] = None
        out["weis_gamma_option_chain_status"] = raw_metrics.get("option_chain_status")
        out["weis_gamma_option_chain_rows"] = raw_metrics.get("option_chain_rows")
        out["weis_gamma_warning"] = ""
        return out

    phase = wg.get("phase") or {}
    ranking = wg.get("ranking") or {}
    gamma = wg.get("gamma_matrix") or {}
    freshness = wg.get("gamma_freshness") or {}
    fusion = wg.get("fusion") or {}
    zero_dte = wg.get("zero_dte") or {}

    out["weis_gamma_present"] = True
    out["weis_gamma_status"] = wg.get("status")
    out["weis_gamma_wired"] = bool(wg.get("wired_into_evidence_builder"))
    out["weis_gamma_transition_enabled"] = bool(wg.get("state_transition_enabled"))

    out["weis_gamma_phase"] = phase.get("weis_phase")
    out["weis_gamma_mapped_state"] = phase.get("mapped_campaign_state")
    out["weis_gamma_phase_confidence"] = (
        phase.get("phase_confidence")
        or phase.get("confidence")
    )

    out["weis_gamma_rank_score"] = ranking.get("rank_score")
    out["weis_gamma_rank_bucket"] = ranking.get("rank_bucket")
    out["weis_gamma_rank_reason"] = ranking.get("reason")

    option_chain_status = raw_metrics.get("option_chain_status")
    option_chain_rows = raw_metrics.get("option_chain_rows")

    gamma_status = gamma.get("status")
    fusion_state = fusion.get("fusion_state")

    effective_gamma_status = gamma_status
    effective_fusion_state = fusion_state

    if option_chain_status == "NO_OPTIONS_RETURNED":
        effective_gamma_status = "NO_OPTIONS_RETURNED"
        if fusion_state == "WEIS_ONLY_GAMMA_STALE":
            effective_fusion_state = "WEIS_ONLY_NO_OPTIONS_RETURNED"

    out["weis_gamma_gamma_status"] = gamma_status
    out["weis_gamma_effective_gamma_status"] = effective_gamma_status
    out["weis_gamma_gamma_regime"] = gamma.get("net_gamma_regime")
    out["weis_gamma_gamma_router"] = freshness.get("router_state")
    out["weis_gamma_gamma_fresh"] = bool(
        gamma.get("gamma_data_fresh")
        or freshness.get("gamma_data_fresh")
    )
    out["weis_gamma_option_chain_status"] = option_chain_status
    out["weis_gamma_option_chain_rows"] = option_chain_rows

    out["weis_gamma_fusion_state"] = fusion_state
    out["weis_gamma_effective_fusion_state"] = effective_fusion_state
    out["weis_gamma_zero_dte_state"] = zero_dte.get("squeeze_state")
    out["weis_gamma_warning"] = _first_warning(wg.get("warnings"))

    return out


def _attach_weis_gamma_summaries(
    campaigns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [_attach_weis_gamma_summary(c) for c in campaigns]


def _count_by_field(
    campaigns: List[Dict[str, Any]],
    field: str,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for campaign in campaigns:
        value = campaign.get(field)

        if value is None:
            key = "NONE"
        elif value == "":
            key = "EMPTY"
        else:
            key = str(value)

        counts[key] = counts.get(key, 0) + 1

    return counts



def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    return {}


def _evidence_section(campaign: Dict[str, Any], section: str) -> Dict[str, Any]:
    evidence = _as_dict(campaign.get("evidence"))
    return _as_dict(evidence.get(section))


def _count_nested_evidence_field(
    campaigns: List[Dict[str, Any]],
    section: str,
    field: str,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for campaign in campaigns:
        value = _evidence_section(campaign, section).get(field)
        key = str(value) if value not in (None, "") else "NONE"
        counts[key] = counts.get(key, 0) + 1

    return counts


def _count_raw_metric_field(
    campaigns: List[Dict[str, Any]],
    field: str,
) -> Dict[str, int]:
    counts: Dict[str, int] = {}

    for campaign in campaigns:
        evidence = _as_dict(campaign.get("evidence"))
        raw_metrics = _as_dict(evidence.get("raw_metrics"))
        value = raw_metrics.get(field)
        key = str(value) if value not in (None, "") else "NONE"
        counts[key] = counts.get(key, 0) + 1

    return counts


def _count_nested_bool(
    campaigns: List[Dict[str, Any]],
    section: str,
    field: str,
) -> Dict[str, int]:
    counts = {"true": 0, "false": 0, "missing": 0}

    for campaign in campaigns:
        section_payload = _evidence_section(campaign, section)
        if field not in section_payload:
            counts["missing"] += 1
        elif bool(section_payload.get(field)):
            counts["true"] += 1
        else:
            counts["false"] += 1

    return counts


def _evidence_presence_counts(campaigns: List[Dict[str, Any]]) -> Dict[str, int]:
    sections = [
        "bar_depth",
        "operator_control",
        "transition_readiness",
        "vsa_weis_overlay",
        "weis_gamma",
    ]

    counts = {section: 0 for section in sections}

    for campaign in campaigns:
        evidence = _as_dict(campaign.get("evidence"))
        for section in sections:
            if isinstance(evidence.get(section), dict):
                counts[section] += 1

    return counts




@router.get("/evidence-diagnostics")
def evidence_diagnostics():
    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)

    full_depth_rows = []

    for campaign in campaigns:
        evidence = _as_dict(campaign.get("evidence"))
        bar_depth = _as_dict(evidence.get("bar_depth"))

        if not bar_depth:
            continue

        operator_control = _as_dict(evidence.get("operator_control"))
        transition_readiness = _as_dict(evidence.get("transition_readiness"))
        raw_metrics = _as_dict(evidence.get("raw_metrics"))
        vsa_weis_overlay = _as_dict(evidence.get("vsa_weis_overlay"))
        weis_gamma = _as_dict(evidence.get("weis_gamma"))

        operator_confirmed = bool(operator_control.get("operator_control_confirmed"))
        transition_enabled = bool(transition_readiness.get("state_transition_enabled"))

        row = {
            "symbol": campaign.get("symbol"),
            "campaign_state": (
                campaign.get("campaign_state")
                or campaign.get("current_state")
                or campaign.get("state_enum")
                or campaign.get("state")
                or raw_metrics.get("campaign_state")
            ),
            "rank_bucket": (
                campaign.get("rank_bucket")
                or campaign.get("campaign_rank_bucket")
                or weis_gamma.get("rank_bucket")
            ),
            "timeframe": (
                campaign.get("timeframe")
                or evidence.get("timeframe")
                or raw_metrics.get("timeframe")
            ),
            "bar_count": bar_depth.get("bar_count"),
            "depth_tier": bar_depth.get("depth_tier"),
            "max_campaign_state": bar_depth.get("max_campaign_state"),
            "bar_depth_diagnostic_key": bar_depth.get("diagnostic_key"),
            "operator_control_confirmed": operator_confirmed,
            "operator_control_verdict": operator_control.get("verdict"),
            "operator_control_evidence_count": operator_control.get("evidence_count"),
            "operator_control_depth_requirement_met": operator_control.get("depth_requirement_met"),
            "operator_control_method_basis": operator_control.get("method_basis"),
            "operator_control_not_derived_from_scores": operator_control.get("not_derived_from_scores"),
            "transition_readiness_verdict": transition_readiness.get("readiness_verdict"),
            "evidence_supported_state": transition_readiness.get("evidence_supported_state"),
            "state_transition_enabled": transition_enabled,
            "transition_diagnostic_only": transition_readiness.get("diagnostic_only"),
            "vsa_weis_phase": vsa_weis_overlay.get("phase"),
            "vsa_weis_verdict": vsa_weis_overlay.get("verdict"),
            "weis_gamma_phase": weis_gamma.get("phase"),
            "weis_gamma_rank_bucket": weis_gamma.get("rank_bucket"),
        }

        full_depth_rows.append(row)

    full_depth_rows.sort(
        key=lambda row: (
            str(row.get("symbol") or ""),
        )
    )

    legacy_operator_control_evidence_rows = [
        row for row in full_depth_rows
        if row.get("operator_control_confirmed") is True
    ]

    return {
        "api_fields_enabled": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_enabled": 0,
        "transition_enabled_expected": False,
        "total_campaigns": len(campaigns),
        "full_depth_count": len(full_depth_rows),
        "legacy_operator_control_evidence_count": len(legacy_operator_control_evidence_rows),
        "d3d_production_confirmed_operator_control_count": 0,
        "operator_control_confirmation_label_policy": "LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION",
        "full_depth_campaigns": full_depth_rows,
        "legacy_operator_control_evidence_campaigns": legacy_operator_control_evidence_rows,
        "d3d_production_confirmed_operator_control_campaigns": [],
    }



def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _diagnostic_priority_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    weis_gamma_phase = _as_dict(row.get("weis_gamma_phase"))

    legacy_operator_control_evidence_present = bool(row.get("operator_control_confirmed"))
    operator_evidence_count = int(row.get("operator_control_evidence_count") or 0)
    d3d_production_confirmed_operator_control = False

    readiness = str(row.get("transition_readiness_verdict") or "NONE").upper()
    supported_state = str(row.get("evidence_supported_state") or "NONE").upper()

    gamma_fresh = bool(weis_gamma_phase.get("gamma_data_fresh"))
    phase_permission = str(weis_gamma_phase.get("phase_permission") or "").upper()
    phase_direction = str(weis_gamma_phase.get("phase_direction") or "").upper()
    wave_direction = str(weis_gamma_phase.get("wave_direction") or "").upper()
    fusion_direction = str(weis_gamma_phase.get("fusion_direction") or "").upper()
    mapped_campaign_state = str(weis_gamma_phase.get("mapped_campaign_state") or "").upper()

    phase_confidence = _safe_float(weis_gamma_phase.get("phase_confidence"))
    wave_coherence = _safe_float(weis_gamma_phase.get("wave_coherence_score"))

    score = 0.0
    reasons = []
    conflict_flags = []

    if legacy_operator_control_evidence_present:
        reasons.append("legacy operator-control evidence present; not D3D production-confirmed and not score/rank boosting")
    else:
        reasons.append("legacy operator-control evidence absent")

    if operator_evidence_count:
        reasons.append(f"operator evidence count {operator_evidence_count}; diagnostic metadata only")

    if readiness == "FULL_CAMPAIGN_READY_DIAGNOSTIC":
        score += 25.0
        reasons.append("full campaign readiness diagnostic")
    elif readiness == "CONFIRMATION_READY_DIAGNOSTIC":
        score += 15.0
        reasons.append("confirmation readiness diagnostic")
    elif readiness == "BIRTH_WATCH_READY_DIAGNOSTIC":
        score += 5.0
        reasons.append("birth/watch readiness diagnostic")

    if supported_state == "MATURING":
        score += 10.0
        reasons.append("evidence-supported state is MATURING")
    elif supported_state == "CONFIRMED":
        score += 5.0
        reasons.append("evidence-supported state is CONFIRMED")

    if gamma_fresh:
        score += 15.0
        reasons.append("gamma data fresh")
    else:
        conflict_flags.append("GAMMA_REFRESH_NEEDED")

    score += min(max(phase_confidence, 0.0), 1.0) * 10.0
    score += min(max(wave_coherence, 0.0), 1.0) * 10.0

    if phase_permission == "BLOCKED":
        score -= 50.0
        conflict_flags.append("PHASE_PERMISSION_BLOCKED")

    if "DOWN" in {phase_direction, wave_direction, fusion_direction}:
        score -= 25.0
        conflict_flags.append("DOWNSIDE_WEIS_GAMMA_DIRECTION")

    if mapped_campaign_state and mapped_campaign_state not in {"", "NONE", supported_state}:
        conflict_flags.append(f"WEIS_GAMMA_MAPS_TO_{mapped_campaign_state}")

    score = round(score, 4)

    if "PHASE_PERMISSION_BLOCKED" in conflict_flags or "DOWNSIDE_WEIS_GAMMA_DIRECTION" in conflict_flags:
        tier = "CONFLICT_BLOCKED_DIAGNOSTIC"
    elif d3d_production_confirmed_operator_control and gamma_fresh and readiness == "FULL_CAMPAIGN_READY_DIAGNOSTIC" and score >= 85:
        tier = "A_DIAGNOSTIC"
    elif d3d_production_confirmed_operator_control and not gamma_fresh:
        tier = "GAMMA_REFRESH_REQUIRED_DIAGNOSTIC"
    elif d3d_production_confirmed_operator_control:
        tier = "B_DIAGNOSTIC"
    elif readiness == "CONFIRMATION_READY_DIAGNOSTIC":
        tier = "WATCHLIST_DIAGNOSTIC"
    else:
        tier = "LOW_PRIORITY_DIAGNOSTIC"

    return {
        "diagnostic_priority_score": score,
        "diagnostic_priority_tier": tier,
        "diagnostic_priority_reason": "; ".join(reasons),
        "conflict_flags": conflict_flags,
        "gamma_refresh_needed": "GAMMA_REFRESH_NEEDED" in conflict_flags,
    }


@router.get("/evidence-diagnostic-rankings")
def evidence_diagnostic_rankings():
    base = evidence_diagnostics()
    rows = list(base.get("full_depth_campaigns") or [])

    ranked_rows = []
    for row in rows:
        enriched = dict(row)
        enriched.update(_diagnostic_priority_for_row(row))
        ranked_rows.append(enriched)

    tier_order = {
        "A_DIAGNOSTIC": 0,
        "B_DIAGNOSTIC": 1,
        "GAMMA_REFRESH_REQUIRED_DIAGNOSTIC": 2,
        "WATCHLIST_DIAGNOSTIC": 3,
        "LOW_PRIORITY_DIAGNOSTIC": 4,
        "CONFLICT_BLOCKED_DIAGNOSTIC": 5,
    }

    ranked_rows.sort(
        key=lambda row: (
            tier_order.get(row.get("diagnostic_priority_tier"), 99),
            -_safe_float(row.get("diagnostic_priority_score")),
            str(row.get("symbol") or ""),
        )
    )

    return {
        "api_fields_enabled": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_enabled": 0,
        "transition_enabled_expected": False,
        "total_campaigns": base.get("total_campaigns"),
        "full_depth_count": base.get("full_depth_count"),
        "legacy_operator_control_evidence_count": base.get("legacy_operator_control_evidence_count"),
        "d3d_production_confirmed_operator_control_count": 0,
        "operator_control_confirmation_label_policy": "LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION",
        "ranked_diagnostic_campaigns": ranked_rows,
        "legacy_operator_control_evidence_ranked_diagnostic_only": [
            row for row in ranked_rows
            if row.get("operator_control_confirmed") is True
        ],
        "d3d_production_confirmed_operator_control_ranked": [],
        "conflicted_campaigns": [
            row for row in ranked_rows
            if row.get("conflict_flags")
        ],
    }



@router.get("/evidence-diagnostics/{symbol}")
def single_symbol_evidence_diagnostics(symbol: str):
    requested_symbol = str(symbol or "").upper().strip()

    ranking_payload = evidence_diagnostic_rankings()
    rows = list(ranking_payload.get("ranked_diagnostic_campaigns") or [])

    match = None
    for row in rows:
        if str(row.get("symbol") or "").upper() == requested_symbol:
            match = row
            break

    available_symbols = [
        str(row.get("symbol") or "")
        for row in rows
        if row.get("symbol")
    ]

    if match is None:
        return {
            "found": False,
            "symbol": requested_symbol,
            "diagnostic_only": True,
            "message": "Symbol not found in full-depth evidence diagnostics.",
            "available_full_depth_symbols": available_symbols,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_enabled": 0,
            "transition_enabled_expected": False,
        }

    weis_gamma_phase = _as_dict(match.get("weis_gamma_phase"))
    conflict_flags = list(match.get("conflict_flags") or [])

    legacy_operator_control_evidence_present = bool(match.get("operator_control_confirmed"))
    d3d_production_confirmed_operator_control = False
    transition_enabled = bool(match.get("state_transition_enabled"))
    gamma_fresh = bool(weis_gamma_phase.get("gamma_data_fresh"))

    operator_summary = (
        "Legacy operator-control evidence is present from raw OHLCV tape behavior, but this is not D3D production-confirmed."
        if legacy_operator_control_evidence_present
        else "Operator control is not D3D production-confirmed by the current doctrine gate."
    )

    if "PHASE_PERMISSION_BLOCKED" in conflict_flags:
        campaign_explanation = "Diagnostic conflict: operator/control evidence exists or partial evidence exists, but Weis/Gamma phase permission is blocked."
    elif "DOWNSIDE_WEIS_GAMMA_DIRECTION" in conflict_flags:
        campaign_explanation = "Diagnostic conflict: Weis/Gamma directional evidence is downside or non-confirmatory."
    elif legacy_operator_control_evidence_present and gamma_fresh:
        campaign_explanation = "Diagnostic note: legacy operator-control evidence is present and Gamma is fresh, but operator control is not D3D production-confirmed."
    elif legacy_operator_control_evidence_present and not gamma_fresh:
        campaign_explanation = "Diagnostic note: legacy operator-control evidence is present, but Gamma refresh is required and operator control is not D3D production-confirmed."
    elif match.get("transition_readiness_verdict") == "CONFIRMATION_READY_DIAGNOSTIC":
        campaign_explanation = "Watchlist diagnostic: confirmation evidence exists, but operator control is not confirmed."
    else:
        campaign_explanation = "Lower-priority diagnostic: full-depth data exists, but confirmation is incomplete."

    failed_or_missing_items = []

    if not legacy_operator_control_evidence_present:
        failed_or_missing_items.append("legacy_operator_control_evidence_present")
    failed_or_missing_items.append("d3d_production_confirmation_not_established")
    if not gamma_fresh:
        failed_or_missing_items.append("gamma_data_fresh")
    if conflict_flags:
        failed_or_missing_items.append("conflict_flags_present")
    if transition_enabled:
        failed_or_missing_items.append("unexpected_transition_enabled")

    return {
        "found": True,
        "symbol": requested_symbol,
        "api_fields_enabled": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_enabled": 0,
        "transition_enabled_expected": False,
        "single_symbol_summary": {
            "campaign_state": match.get("campaign_state"),
            "rank_bucket": match.get("rank_bucket"),
            "timeframe": match.get("timeframe"),
            "bar_count": match.get("bar_count"),
            "depth_tier": match.get("depth_tier"),
            "max_campaign_state": match.get("max_campaign_state"),
            "diagnostic_priority_tier": match.get("diagnostic_priority_tier"),
            "diagnostic_priority_score": match.get("diagnostic_priority_score"),
            "campaign_explanation": campaign_explanation,
        },
        "operator_control_explanation": {
            "summary": operator_summary,
            "confirmed": d3d_production_confirmed_operator_control,
            "d3d_production_confirmed": d3d_production_confirmed_operator_control,
            "legacy_operator_control_evidence_present": legacy_operator_control_evidence_present,
            "legacy_operator_control_boolean_source": match.get("operator_control_confirmed"),
            "confirmation_label_policy": "LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION",
            "verdict": match.get("operator_control_verdict"),
            "evidence_count": match.get("operator_control_evidence_count"),
            "depth_requirement_met": match.get("operator_control_depth_requirement_met"),
            "method_basis": match.get("operator_control_method_basis"),
            "not_derived_from_scores": match.get("operator_control_not_derived_from_scores"),
        },
        "transition_readiness_explanation": {
            "readiness_verdict": match.get("transition_readiness_verdict"),
            "evidence_supported_state": match.get("evidence_supported_state"),
            "state_transition_enabled": match.get("state_transition_enabled"),
            "transition_diagnostic_only": match.get("transition_diagnostic_only"),
            "explanation": "Transition readiness is diagnostic only. It does not move campaign state.",
        },
        "weis_gamma_explanation": {
            "risk_state": weis_gamma_phase.get("risk_state"),
            "weis_phase": weis_gamma_phase.get("weis_phase"),
            "fusion_state": weis_gamma_phase.get("fusion_state"),
            "phase_reason": weis_gamma_phase.get("phase_reason"),
            "router_state": weis_gamma_phase.get("router_state"),
            "phase_permission": weis_gamma_phase.get("phase_permission"),
            "phase_direction": weis_gamma_phase.get("phase_direction"),
            "wave_direction": weis_gamma_phase.get("wave_direction"),
            "fusion_direction": weis_gamma_phase.get("fusion_direction"),
            "gamma_data_fresh": gamma_fresh,
            "gamma_refresh_needed": match.get("gamma_refresh_needed"),
            "phase_confidence": weis_gamma_phase.get("phase_confidence"),
            "wave_coherence_score": weis_gamma_phase.get("wave_coherence_score"),
            "mapped_campaign_state": weis_gamma_phase.get("mapped_campaign_state"),
            "dominant_wave_direction": weis_gamma_phase.get("dominant_wave_direction"),
            "next_possible_phase": weis_gamma_phase.get("next_possible_phase"),
            "transition_hint": weis_gamma_phase.get("transition_hint"),
        },
        "diagnostic_priority_explanation": {
            "tier": match.get("diagnostic_priority_tier"),
            "score": match.get("diagnostic_priority_score"),
            "reason": match.get("diagnostic_priority_reason"),
            "conflict_flags": conflict_flags,
            "failed_or_missing_items": failed_or_missing_items,
        },
        "raw_diagnostic_row": match,
    }



@router.get("/evidence-audit-export")
def evidence_audit_export():
    summary_payload = status()
    diagnostics_payload = evidence_diagnostics()
    ranking_payload = evidence_diagnostic_rankings()

    ranked_rows = list(ranking_payload.get("ranked_diagnostic_campaigns") or [])
    legacy_operator_rows = list(ranking_payload.get("legacy_operator_control_evidence_ranked_diagnostic_only") or [])
    conflicted_rows = list(ranking_payload.get("conflicted_campaigns") or [])

    gamma_refresh_rows = [
        row for row in ranked_rows
        if row.get("gamma_refresh_needed") is True
    ]

    aligned_a_rows = [
        row for row in ranked_rows
        if row.get("diagnostic_priority_tier") == "A_DIAGNOSTIC"
    ]

    blocked_rows = [
        row for row in ranked_rows
        if row.get("diagnostic_priority_tier") == "CONFLICT_BLOCKED_DIAGNOSTIC"
    ]

    tier_counts: Dict[str, int] = {}
    for row in ranked_rows:
        tier = str(row.get("diagnostic_priority_tier") or "NONE")
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

    symbol_digest = [
        {
            "symbol": row.get("symbol"),
            "campaign_state": row.get("campaign_state"),
            "diagnostic_priority_tier": row.get("diagnostic_priority_tier"),
            "diagnostic_priority_score": row.get("diagnostic_priority_score"),
            "legacy_operator_control_evidence_present": row.get("operator_control_confirmed"),
            "d3d_production_confirmed_operator_control": False,
            "operator_control_confirmation_label_policy": "LEGACY_BOOLEAN_IS_EVIDENCE_NOT_D3D_PRODUCTION_CONFIRMATION",
            "operator_control_evidence_count": row.get("operator_control_evidence_count"),
            "evidence_supported_state": row.get("evidence_supported_state"),
            "gamma_refresh_needed": row.get("gamma_refresh_needed"),
            "conflict_flags": row.get("conflict_flags"),
        }
        for row in ranked_rows
    ]

    return {
        "api_fields_enabled": True,
        "audit_export_enabled": True,
        "diagnostic_only": True,
        "audit_contract": {
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_enabled": 0,
            "transition_enabled_expected": False,
            "frontend_impact": "NONE",
            "operator_control_basis": "RAW_OHLCV_TAPE_BEHAVIOR_ONLY",
            "operator_control_not_derived_from_scores": True,
        },
        "counts": {
            "total_campaigns": ranking_payload.get("total_campaigns"),
            "full_depth_count": ranking_payload.get("full_depth_count"),
            "legacy_operator_control_evidence_count": ranking_payload.get("legacy_operator_control_evidence_count"),
            "d3d_production_confirmed_operator_control_count": ranking_payload.get("d3d_production_confirmed_operator_control_count"),
            "aligned_a_diagnostic_count": len(aligned_a_rows),
            "gamma_refresh_needed_count": len(gamma_refresh_rows),
            "conflicted_count": len(conflicted_rows),
            "conflict_blocked_count": len(blocked_rows),
        },
        "diagnostic_tier_counts": tier_counts,
        "symbol_digest": symbol_digest,
        "aligned_a_diagnostic_campaigns": aligned_a_rows,
        "legacy_operator_control_evidence_campaigns": legacy_operator_rows,
        "d3d_production_confirmed_operator_control_campaigns": [],
        "gamma_refresh_needed_campaigns": gamma_refresh_rows,
        "conflict_blocked_campaigns": blocked_rows,
        "conflicted_campaigns": conflicted_rows,
        "summary_payload": summary_payload,
        "diagnostics_payload": diagnostics_payload,
        "ranking_payload": ranking_payload,
    }



@router.get("/evidence-calibration-review")
def evidence_calibration_review():
    audit_payload = evidence_audit_export()
    ranking_payload = evidence_diagnostic_rankings()

    rows = list(ranking_payload.get("ranked_diagnostic_campaigns") or [])

    hard_conflict_flags = {
        "PHASE_PERMISSION_BLOCKED",
        "DOWNSIDE_WEIS_GAMMA_DIRECTION",
    }

    refresh_flags = {
        "GAMMA_REFRESH_NEEDED",
    }

    state_mapping_prefix = "WEIS_GAMMA_MAPS_TO_"

    hard_conflict_rows = []
    refresh_needed_rows = []
    state_mapping_rows = []
    state_mapping_only_rows = []
    operator_confirmed_rows = []
    operator_confirmed_hard_conflict_rows = []
    operator_confirmed_refresh_needed_rows = []

    for row in rows:
        flags = set(row.get("conflict_flags") or [])

        has_hard_conflict = bool(flags.intersection(hard_conflict_flags))
        has_refresh_flag = bool(flags.intersection(refresh_flags))
        has_state_mapping_flag = any(
            str(flag).startswith(state_mapping_prefix)
            for flag in flags
        )

        if row.get("operator_control_confirmed") is True:
            operator_confirmed_rows.append(row)

        if has_hard_conflict:
            hard_conflict_rows.append(row)

        if has_refresh_flag:
            refresh_needed_rows.append(row)

        if has_state_mapping_flag:
            state_mapping_rows.append(row)

        if has_state_mapping_flag and not has_hard_conflict and not has_refresh_flag:
            state_mapping_only_rows.append(row)

        if row.get("operator_control_confirmed") is True and has_hard_conflict:
            operator_confirmed_hard_conflict_rows.append(row)

        if row.get("operator_control_confirmed") is True and has_refresh_flag:
            operator_confirmed_refresh_needed_rows.append(row)

    current_conflicted_count = len(list(ranking_payload.get("conflicted_campaigns") or []))
    hard_conflict_count = len(hard_conflict_rows)
    state_mapping_only_count = len(state_mapping_only_rows)

    calibration_warnings = []

    if current_conflicted_count > hard_conflict_count:
        calibration_warnings.append(
            "Current conflicted_campaigns count includes soft flags such as gamma refresh or state-mapping differences."
        )

    if state_mapping_only_count > 0:
        calibration_warnings.append(
            "WEIS_GAMMA_MAPS_TO_* appears as a conflict flag even when no hard conflict or gamma-refresh issue is present."
        )

    if len(refresh_needed_rows) > hard_conflict_count:
        calibration_warnings.append(
            "Gamma refresh need is common and should remain a data freshness condition, not a hard conflict."
        )

    return {
        "api_fields_enabled": True,
        "calibration_review_enabled": True,
        "diagnostic_only": True,
        "audit_contract": {
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_enabled": 0,
            "transition_enabled_expected": False,
            "frontend_impact": "NONE",
        },
        "calibration_summary": {
            "total_campaigns": audit_payload.get("counts", {}).get("total_campaigns"),
            "full_depth_count": audit_payload.get("counts", {}).get("full_depth_count"),
            "legacy_operator_control_evidence_count": len(operator_confirmed_rows),
            "d3d_production_confirmed_operator_control_count": 0,
            "current_conflicted_count": current_conflicted_count,
            "hard_conflict_count": hard_conflict_count,
            "gamma_refresh_needed_count": len(refresh_needed_rows),
            "state_mapping_flag_count": len(state_mapping_rows),
            "state_mapping_only_count": state_mapping_only_count,
            "legacy_operator_control_evidence_hard_conflict_count": len(operator_confirmed_hard_conflict_rows),
            "legacy_operator_control_evidence_gamma_refresh_needed_count": len(operator_confirmed_refresh_needed_rows),
        },
        "diagnostic_tier_counts": audit_payload.get("diagnostic_tier_counts"),
        "hard_conflict_flags": sorted(hard_conflict_flags),
        "refresh_flags": sorted(refresh_flags),
        "state_mapping_flag_prefix": state_mapping_prefix,
        "calibration_warnings": calibration_warnings,
        "recommended_next_action": {
            "phase": "Phase 11",
            "name": "Diagnostic Conflict Taxonomy Split",
            "description": (
                "Separate conflict_flags into hard_conflict_flags, refresh_required_flags, "
                "and state_mapping_flags so gamma refresh and state-mapping differences do not inflate hard conflict counts."
            ),
            "production_impact": "NONE until explicitly wired later",
        },
        "hard_conflict_campaigns": hard_conflict_rows,
        "gamma_refresh_needed_campaigns": refresh_needed_rows,
        "state_mapping_only_campaigns": state_mapping_only_rows,
        "operator_confirmed_hard_conflict_campaigns": operator_confirmed_hard_conflict_rows,
        "operator_confirmed_gamma_refresh_needed_campaigns": operator_confirmed_refresh_needed_rows,
    }



def _split_diagnostic_conflict_flags(row: Dict[str, Any]) -> Dict[str, Any]:
    flags = [
        str(flag)
        for flag in list(row.get("conflict_flags") or [])
        if str(flag)
    ]

    hard_flag_set = {
        "PHASE_PERMISSION_BLOCKED",
        "DOWNSIDE_WEIS_GAMMA_DIRECTION",
    }

    refresh_flag_set = {
        "GAMMA_REFRESH_NEEDED",
    }

    hard_conflict_flags = [
        flag for flag in flags
        if flag in hard_flag_set
    ]

    refresh_required_flags = [
        flag for flag in flags
        if flag in refresh_flag_set
    ]

    state_mapping_flags = [
        flag for flag in flags
        if flag.startswith("WEIS_GAMMA_MAPS_TO_")
    ]

    categorized = set(hard_conflict_flags + refresh_required_flags + state_mapping_flags)

    soft_conflict_flags = [
        flag for flag in flags
        if flag not in categorized
    ]

    has_hard_conflict = bool(hard_conflict_flags)
    has_refresh_required = bool(refresh_required_flags)
    has_state_mapping = bool(state_mapping_flags)
    state_mapping_only = (
        has_state_mapping
        and not has_hard_conflict
        and not has_refresh_required
        and not soft_conflict_flags
    )

    if has_hard_conflict:
        taxonomy_tier = "HARD_CONFLICT"
    elif has_refresh_required and has_state_mapping:
        taxonomy_tier = "REFRESH_AND_STATE_MAPPING"
    elif has_refresh_required:
        taxonomy_tier = "REFRESH_REQUIRED"
    elif state_mapping_only:
        taxonomy_tier = "STATE_MAPPING_ONLY"
    elif soft_conflict_flags:
        taxonomy_tier = "SOFT_CONFLICT"
    else:
        taxonomy_tier = "NO_CONFLICT"

    return {
        "hard_conflict_flags": hard_conflict_flags,
        "refresh_required_flags": refresh_required_flags,
        "state_mapping_flags": state_mapping_flags,
        "soft_conflict_flags": soft_conflict_flags,
        "has_hard_conflict": has_hard_conflict,
        "has_refresh_required": has_refresh_required,
        "has_state_mapping": has_state_mapping,
        "state_mapping_only": state_mapping_only,
        "conflict_taxonomy_tier": taxonomy_tier,
    }


@router.get("/evidence-conflict-taxonomy")
def evidence_conflict_taxonomy():
    ranking_payload = evidence_diagnostic_rankings()
    calibration_payload = evidence_calibration_review()

    rows = list(ranking_payload.get("ranked_diagnostic_campaigns") or [])

    enriched_rows = []
    taxonomy_tier_counts: Dict[str, int] = {}

    hard_conflict_rows = []
    refresh_required_rows = []
    state_mapping_only_rows = []
    no_conflict_rows = []

    for row in rows:
        enriched = dict(row)
        taxonomy = _split_diagnostic_conflict_flags(row)
        enriched.update(taxonomy)

        tier = taxonomy["conflict_taxonomy_tier"]
        taxonomy_tier_counts[tier] = taxonomy_tier_counts.get(tier, 0) + 1

        if taxonomy["has_hard_conflict"]:
            hard_conflict_rows.append(enriched)

        if taxonomy["has_refresh_required"]:
            refresh_required_rows.append(enriched)

        if taxonomy["state_mapping_only"]:
            state_mapping_only_rows.append(enriched)

        if tier == "NO_CONFLICT":
            no_conflict_rows.append(enriched)

        enriched_rows.append(enriched)

    return {
        "api_fields_enabled": True,
        "conflict_taxonomy_enabled": True,
        "diagnostic_only": True,
        "audit_contract": {
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_enabled": 0,
            "transition_enabled_expected": False,
            "frontend_impact": "NONE",
        },
        "taxonomy_summary": {
            "total_full_depth_rows": len(rows),
            "legacy_conflicted_count": len(list(ranking_payload.get("conflicted_campaigns") or [])),
            "hard_conflict_count": len(hard_conflict_rows),
            "refresh_required_count": len(refresh_required_rows),
            "state_mapping_only_count": len(state_mapping_only_rows),
            "no_conflict_count": len(no_conflict_rows),
            "taxonomy_tier_counts": taxonomy_tier_counts,
        },
        "calibration_summary": calibration_payload.get("calibration_summary"),
        "taxonomy_definitions": {
            "HARD_CONFLICT": "Phase permission blocked and/or Weis/Gamma directional evidence is downside.",
            "REFRESH_REQUIRED": "Gamma or related options confirmation must refresh before stronger confirmation.",
            "STATE_MAPPING_ONLY": "Weis/Gamma maps to a different campaign state but does not create a hard block.",
            "REFRESH_AND_STATE_MAPPING": "Both refresh requirement and state-mapping difference are present.",
            "SOFT_CONFLICT": "Unclassified non-hard diagnostic conflict flag.",
            "NO_CONFLICT": "No conflict flags are present.",
        },
        "hard_conflict_campaigns": hard_conflict_rows,
        "refresh_required_campaigns": refresh_required_rows,
        "state_mapping_only_campaigns": state_mapping_only_rows,
        "no_conflict_campaigns": no_conflict_rows,
        "taxonomy_enriched_campaigns": enriched_rows,
    }










@router.get("/structural-location-input-review")
def structural_location_input_review():
    """
    D3C.1 Structural Location Input Review.
    Read-only diagnostic endpoint.
    Purpose:
        Audit whether active campaign evidence contains explicit structural-location
        inputs needed to locate Wyckoff / Weis events inside the campaign structure.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT change scores, ranks, states, or transitions.
    """
    from collections import Counter
    try:
        from backend.campaign_engine.structural_location_input_review_engine import (
            review_structural_location_inputs,
            ENGINE_NAME,
            ENGINE_VERSION,
        )
    except Exception:
        from campaign_engine.structural_location_input_review_engine import (
            review_structural_location_inputs,
            ENGINE_NAME,
            ENGINE_VERSION,
        )
    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}
    def _get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)
    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))
    campaigns = _store().get_active_campaigns()
    rows = []
    guardrail_failures = []
    readiness_counter = Counter()
    available_group_counter = Counter()
    missing_group_counter = Counter()
    production_sml_counter = Counter()
    explicit_tr_counter = Counter()
    explicit_lp_counter = Counter()
    explicit_hvn_counter = Counter()
    explicit_sr_counter = Counter()
    campaign_state_counter = Counter()
    boolean_input_counters = {
        "current_price_available": Counter(),
        "range_floor_available": Counter(),
        "range_ceiling_available": Counter(),
        "atr_available": Counter(),
        "support_available": Counter(),
        "resistance_available": Counter(),
        "hvn_poc_available": Counter(),
        "spring_shakeout_available": Counter(),
        "last_point_of_support_available": Counter(),
        "upthrust_utad_available": Counter(),
        "price_series_available": Counter(),
    }
    for campaign in campaigns:
        c = _as_dict(campaign)
        evidence = _as_dict(_get(c, "evidence", {}))
        symbol = _get(c, "symbol")
        campaign_id = _get(c, "campaign_id") or _get(c, "id")
        campaign_state = (
            _get(c, "current_state")
            or _get(c, "state_enum")
            or _get(c, "campaign_state")
            or _get(c, "state")
            or _get(c, "lifecycle_state")
            or _get(c, "campaign_lifecycle_state")
        )
        timeframe = _get(c, "timeframe") or _get(evidence, "timeframe") or "DAILY"
        review = review_structural_location_inputs(
            evidence=evidence,
            symbol=symbol,
            campaign_state=campaign_state,
        )
        guardrail_ok = (
            review.get("diagnostic_only") is True
            and review.get("read_only") is True
            and review.get("writes_to_supabase") is False
            and review.get("mutates_campaigns") is False
            and review.get("production_confirmation_allowed") is False
            and review.get("operator_control_confirmed_by_this_engine") is False
            and review.get("operator_control_confirmation_impact") == "NONE"
            and review.get("score_impact") == "NONE"
            and review.get("rank_impact") == "NONE"
            and review.get("state_impact") == "NONE"
            and review.get("transition_impact") == "NONE"
            and review.get("state_transition_enabled") is False
            and review.get("not_a_trade_signal") is True
        )
        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "D3C.1 structural location input review guardrail failure",
                "payload": review,
            })
        readiness = review.get("structural_location_readiness")
        readiness_counter[str(readiness)] += 1
        production_sml_counter[str(bool(review.get("production_sml_possible_now")))] += 1
        explicit_tr_counter[str(bool(review.get("explicit_trading_range_ready")))] += 1
        explicit_lp_counter[str(bool(review.get("explicit_lp_zone_ready")))] += 1
        explicit_hvn_counter[str(bool(review.get("explicit_hvn_zone_ready")))] += 1
        explicit_sr_counter[str(bool(review.get("explicit_support_resistance_ready")))] += 1
        campaign_state_counter[str(campaign_state)] += 1
        for group in review.get("available_input_groups") or []:
            available_group_counter[str(group)] += 1
        for group in review.get("missing_input_groups") or []:
            missing_group_counter[str(group)] += 1
        for key, counter in boolean_input_counters.items():
            counter[str(bool(review.get(key)))] += 1
        rows.append({
            "symbol": symbol,
            "campaign_id": campaign_id,
            "campaign_state": campaign_state,
            "timeframe": timeframe,
            "structural_location_readiness": readiness,
            "production_sml_possible_now": review.get("production_sml_possible_now"),
            "readiness_reasons": review.get("readiness_reasons") or [],
            "recommendation": review.get("recommendation"),
            "explicit_trading_range_ready": review.get("explicit_trading_range_ready"),
            "explicit_lp_zone_ready": review.get("explicit_lp_zone_ready"),
            "explicit_hvn_zone_ready": review.get("explicit_hvn_zone_ready"),
            "explicit_support_resistance_ready": review.get("explicit_support_resistance_ready"),
            "current_price_available": review.get("current_price_available"),
            "range_floor_available": review.get("range_floor_available"),
            "range_ceiling_available": review.get("range_ceiling_available"),
            "atr_available": review.get("atr_available"),
            "support_available": review.get("support_available"),
            "resistance_available": review.get("resistance_available"),
            "hvn_poc_available": review.get("hvn_poc_available"),
            "spring_shakeout_available": review.get("spring_shakeout_available"),
            "last_point_of_support_available": review.get("last_point_of_support_available"),
            "upthrust_utad_available": review.get("upthrust_utad_available"),
            "price_series_available": review.get("price_series_available"),
            "available_input_groups": review.get("available_input_groups") or [],
            "missing_input_groups": review.get("missing_input_groups") or [],
            "matched_paths": review.get("matched_paths") or {},
            "field_match_count_by_group": review.get("field_match_count_by_group") or {},
            "footprint_archetypes": review.get("footprint_archetypes") or [],
            "classical_event_inference_available": review.get("classical_event_inference_available"),
            "production_confirmation_allowed": review.get("production_confirmation_allowed"),
            "operator_control_confirmed_by_this_engine": review.get("operator_control_confirmed_by_this_engine"),
            "operator_control_confirmation_impact": review.get("operator_control_confirmation_impact"),
            "score_impact": review.get("score_impact"),
            "rank_impact": review.get("rank_impact"),
            "state_impact": review.get("state_impact"),
            "transition_impact": review.get("transition_impact"),
        })
    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("structural_location_readiness") == "MISSING_CORE_LOCATION_INPUTS" else
            1 if row.get("structural_location_readiness") == "INFERRED_CLASSICAL_EVENT_ONLY" else
            2 if row.get("structural_location_readiness") == "PARTIAL_EXPLICIT_EVENT_LOCATION_READY" else
            3,
            str(row.get("symbol") or ""),
        ),
    )
    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/structural-location-input-review",
        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,
        "purpose": (
            "Audit explicit structural-location inputs needed to locate Wyckoff / Weis "
            "events inside the campaign structure before production confirmation."
        ),
        "total_campaigns": len(campaigns),
        "review_rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),
        "structural_location_readiness_distribution": _counter_to_dict(readiness_counter),
        "production_sml_possible_distribution": _counter_to_dict(production_sml_counter),
        "explicit_trading_range_ready_distribution": _counter_to_dict(explicit_tr_counter),
        "explicit_lp_zone_ready_distribution": _counter_to_dict(explicit_lp_counter),
        "explicit_hvn_zone_ready_distribution": _counter_to_dict(explicit_hvn_counter),
        "explicit_support_resistance_ready_distribution": _counter_to_dict(explicit_sr_counter),
        "campaign_state_distribution": _counter_to_dict(campaign_state_counter),
        "available_input_group_distribution": _counter_to_dict(available_group_counter),
        "missing_input_group_distribution": _counter_to_dict(missing_group_counter),
        "boolean_input_distributions": {
            key: _counter_to_dict(counter)
            for key, counter in boolean_input_counters.items()
        },
        "review_rows": rows,
        "guardrail_failures": guardrail_failures,
    }


@router.get("/structural-location-validation-review")
def structural_location_validation_review():
    """
    D3C.3 Structural Location Validation Review.
    Read-only diagnostic endpoint.
    Purpose:
        Validate that D3C.2 structural-location evidence is internally coherent
        before any future D3D production mutation gate may rely on it.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT change scores, ranks, states, or transitions.
    """
    from collections import Counter
    try:
        from backend.campaign_engine.structural_location_input_review_engine import (
            review_structural_location_inputs,
        )
        from backend.campaign_engine.structural_location_validation_engine import (
            validate_structural_location,
            ENGINE_NAME,
            ENGINE_VERSION,
        )
    except Exception:
        from campaign_engine.structural_location_input_review_engine import (
            review_structural_location_inputs,
        )
        from campaign_engine.structural_location_validation_engine import (
            validate_structural_location,
            ENGINE_NAME,
            ENGINE_VERSION,
        )
    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}
    def _get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)
    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))
    campaigns = _store().get_active_campaigns()
    rows = []
    guardrail_failures = []
    validation_status_counter = Counter()
    validation_pass_counter = Counter()
    production_sml_validation_counter = Counter()
    campaign_state_counter = Counter()
    warning_counter = Counter()
    failed_check_counter = Counter()
    boolean_counters = {
        "range_bounds_valid": Counter(),
        "range_height_matches_bounds": Counter(),
        "range_midpoint_matches_bounds": Counter(),
        "range_position_matches_bounds": Counter(),
        "current_bar_consistent": Counter(),
        "atr_valid": Counter(),
        "support_resistance_consistent": Counter(),
        "price_series_usable": Counter(),
        "spring_upthrust_flags_valid": Counter(),
        "hvn_poc_available": Counter(),
    }
    for campaign in campaigns:
        c = _as_dict(campaign)
        evidence = _as_dict(_get(c, "evidence", {}))
        symbol = _get(c, "symbol")
        campaign_id = _get(c, "campaign_id") or _get(c, "id")
        campaign_state = (
            _get(c, "current_state")
            or _get(c, "state_enum")
            or _get(c, "campaign_state")
            or _get(c, "state")
            or _get(c, "lifecycle_state")
            or _get(c, "campaign_lifecycle_state")
        )
        timeframe = _get(c, "timeframe") or _get(evidence, "timeframe") or "DAILY"
        d3c1_review = review_structural_location_inputs(
            evidence=evidence,
            symbol=symbol,
            campaign_state=campaign_state,
        )
        validation = validate_structural_location(
            evidence=evidence,
            symbol=symbol,
            campaign_state=campaign_state,
            d3c1_review=d3c1_review,
        )
        guardrail_ok = (
            validation.get("diagnostic_only") is True
            and validation.get("read_only") is True
            and validation.get("writes_to_supabase") is False
            and validation.get("mutates_campaigns") is False
            and validation.get("production_confirmation_allowed") is False
            and validation.get("operator_control_confirmed_by_this_engine") is False
            and validation.get("operator_control_confirmation_impact") == "NONE"
            and validation.get("score_impact") == "NONE"
            and validation.get("rank_impact") == "NONE"
            and validation.get("state_impact") == "NONE"
            and validation.get("transition_impact") == "NONE"
            and validation.get("state_transition_enabled") is False
            and validation.get("not_a_trade_signal") is True
        )
        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "D3C.3 structural location validation guardrail failure",
                "payload": validation,
            })
        status = str(validation.get("validation_status"))
        validation_status_counter[status] += 1
        validation_pass_counter[str(bool(validation.get("structural_location_validation_passed")))] += 1
        production_sml_validation_counter[str(bool(validation.get("production_sml_validation_passed")))] += 1
        campaign_state_counter[str(campaign_state)] += 1
        for warning in validation.get("warnings") or []:
            warning_counter[str(warning)] += 1
        for failed_check in validation.get("failed_checks") or []:
            failed_check_counter[str(failed_check)] += 1
        for key, counter in boolean_counters.items():
            counter[str(bool(validation.get(key)))] += 1
        rows.append({
            "symbol": symbol,
            "campaign_id": campaign_id,
            "campaign_state": campaign_state,
            "timeframe": timeframe,
            "validation_status": validation.get("validation_status"),
            "structural_location_validation_passed": validation.get("structural_location_validation_passed"),
            "production_sml_validation_passed": validation.get("production_sml_validation_passed"),
            "d3c1_structural_location_readiness": validation.get("d3c1_structural_location_readiness"),
            "d3c1_production_sml_possible_now": validation.get("d3c1_production_sml_possible_now"),
            "missing_required_fields": validation.get("missing_required_fields") or [],
            "passed_checks": validation.get("passed_checks") or [],
            "failed_checks": validation.get("failed_checks") or [],
            "warnings": validation.get("warnings") or [],
            "range_bounds_valid": validation.get("range_bounds_valid"),
            "range_height_matches_bounds": validation.get("range_height_matches_bounds"),
            "range_midpoint_matches_bounds": validation.get("range_midpoint_matches_bounds"),
            "range_position_matches_bounds": validation.get("range_position_matches_bounds"),
            "current_bar_consistent": validation.get("current_bar_consistent"),
            "atr_valid": validation.get("atr_valid"),
            "support_resistance_consistent": validation.get("support_resistance_consistent"),
            "price_series_usable": validation.get("price_series_usable"),
            "price_series_bar_count": validation.get("price_series_bar_count"),
            "price_series_usable_bar_count": validation.get("price_series_usable_bar_count"),
            "spring_upthrust_flags_valid": validation.get("spring_upthrust_flags_valid"),
            "hvn_poc_available": validation.get("hvn_poc_available"),
            "structural_location_engine": validation.get("structural_location_engine"),
            "structural_location_version": validation.get("structural_location_version"),
            "production_confirmation_allowed": validation.get("production_confirmation_allowed"),
            "operator_control_confirmed_by_this_engine": validation.get("operator_control_confirmed_by_this_engine"),
            "operator_control_confirmation_impact": validation.get("operator_control_confirmation_impact"),
            "score_impact": validation.get("score_impact"),
            "rank_impact": validation.get("rank_impact"),
            "state_impact": validation.get("state_impact"),
            "transition_impact": validation.get("transition_impact"),
        })
    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("validation_status") != "STRUCTURAL_LOCATION_VALIDATED" else 1,
            str(row.get("symbol") or ""),
        ),
    )
    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/structural-location-validation-review",
        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,
        "purpose": (
            "Validate D3C.2 structural-location evidence for internal coherence "
            "before any future D3D production mutation gate."
        ),
        "total_campaigns": len(campaigns),
        "validation_rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),
        "validation_status_distribution": _counter_to_dict(validation_status_counter),
        "structural_location_validation_passed_distribution": _counter_to_dict(validation_pass_counter),
        "production_sml_validation_passed_distribution": _counter_to_dict(production_sml_validation_counter),
        "campaign_state_distribution": _counter_to_dict(campaign_state_counter),
        "boolean_validation_distributions": {
            key: _counter_to_dict(counter)
            for key, counter in boolean_counters.items()
        },
        "warning_distribution": _counter_to_dict(warning_counter),
        "failed_check_distribution": _counter_to_dict(failed_check_counter),
        "validation_rows": rows,
        "guardrail_failures": guardrail_failures,
    }

@router.get("/wyckoff-weis-operator-confirmation-review")
def wyckoff_weis_operator_confirmation_review():
    """
    D3C Wyckoff / Weis shadow-production confirmation review.

    This endpoint applies the doctrinal rule:

    Composite Operator Control =
        Tested Supply Exhaustion
        AND Active Demand / Support Validation
        AND Structurally Meaningful Location
        AND NOT Contrary Failure

    This endpoint is read-only and diagnostic-only.
    It does NOT confirm operator control in production.
    It does NOT write to Supabase.
    It does NOT mutate campaigns.
    It does NOT change scores, ranks, states, or transitions.
    """
    from collections import Counter

    try:
        from backend.campaign_engine.wyckoff_weis_operator_confirmation_engine import (
            classify_wyckoff_weis_operator_confirmation,
            ENGINE_NAME,
            ENGINE_VERSION,
        )
    except Exception:
        from campaign_engine.wyckoff_weis_operator_confirmation_engine import (
            classify_wyckoff_weis_operator_confirmation,
            ENGINE_NAME,
            ENGINE_VERSION,
        )

    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}

    def _get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    guardrail_failures = []

    doctrine_verdict_counter = Counter()
    doctrine_confirmable_counter = Counter()
    existing_control_context_counter = Counter()
    campaign_state_counter = Counter()
    sml_counter = Counter()
    sml_location_counter = Counter()
    sml_quality_counter = Counter()
    supply_counter = Counter()
    demand_counter = Counter()
    contrary_counter = Counter()
    block_reason_counter = Counter()

    for campaign in campaigns:
        c = _as_dict(campaign)
        evidence = _as_dict(_get(c, "evidence", {}))

        symbol = _get(c, "symbol")
        campaign_id = _get(c, "campaign_id") or _get(c, "id")
        campaign_state = (
            _get(c, "current_state")
            or _get(c, "state_enum")
            or _get(c, "campaign_state")
            or _get(c, "state")
            or _get(c, "lifecycle_state")
            or _get(c, "campaign_lifecycle_state")
        )
        timeframe = _get(c, "timeframe") or _get(evidence, "timeframe") or "DAILY"

        review = classify_wyckoff_weis_operator_confirmation(
            evidence=evidence,
            symbol=symbol,
            campaign_state=campaign_state,
        )

        guardrail_ok = (
            review.get("diagnostic_only") is True
            and review.get("read_only") is True
            and review.get("shadow_production") is True
            and review.get("writes_to_supabase") is False
            and review.get("mutates_campaigns") is False
            and review.get("production_confirmation_allowed") is False
            and review.get("operator_control_confirmed_by_this_engine") is False
            and review.get("operator_control_confirmation_impact") == "NONE"
            and review.get("score_impact") == "NONE"
            and review.get("rank_impact") == "NONE"
            and review.get("state_impact") == "NONE"
            and review.get("transition_impact") == "NONE"
            and review.get("state_transition_enabled") is False
            and review.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "D3C shadow confirmation guardrail failure",
                "payload": review,
            })

        doctrine_verdict = review.get("doctrine_verdict")
        doctrine_confirmable = bool(review.get("doctrine_confirmable"))
        existing_control_context = review.get("existing_control_context")

        doctrine_verdict_counter[str(doctrine_verdict)] += 1
        doctrine_confirmable_counter[str(doctrine_confirmable)] += 1
        existing_control_context_counter[str(existing_control_context)] += 1
        campaign_state_counter[str(campaign_state)] += 1
        sml_counter[str(bool(review.get("sml_present")))] += 1
        sml_quality_counter[str(review.get("sml_evidence_quality"))] += 1

        for location in review.get("sml_locations") or []:
            sml_location_counter[str(location)] += 1

        for flag in review.get("supply_exhaustion_flags_present") or []:
            supply_counter[str(flag)] += 1

        for flag in review.get("demand_support_flags_present") or []:
            demand_counter[str(flag)] += 1

        for flag in review.get("contrary_failure_flags_present") or []:
            contrary_counter[str(flag)] += 1

        for flag in review.get("contrary_risk_context_present") or []:
            contrary_counter[str(flag)] += 1

        for reason in review.get("block_reasons") or []:
            block_reason_counter[str(reason)] += 1

        rows.append({
            "symbol": symbol,
            "campaign_id": campaign_id,
            "campaign_state": campaign_state,
            "timeframe": timeframe,

            "doctrine_confirmable": doctrine_confirmable,
            "doctrine_verdict": doctrine_verdict,
            "doctrine_reason": review.get("doctrine_reason"),
            "existing_control_context": existing_control_context,

            "footprint_present": review.get("footprint_present"),
            "footprint_count": review.get("footprint_count"),
            "footprint_archetypes": review.get("footprint_archetypes") or [],
            "operator_control_confirmed_current": review.get("operator_control_confirmed_current"),

            "sml_present": review.get("sml_present"),
            "sml_locations": review.get("sml_locations") or [],
            "sml_evidence_quality": review.get("sml_evidence_quality"),
            "sml_reason": review.get("sml_reason") or [],
            "explicit_geometry_available": review.get("explicit_geometry_available"),
            "geometry_inputs": review.get("geometry_inputs") or {},

            "supply_exhaustion_validated": review.get("supply_exhaustion_validated"),
            "supply_exhaustion_flags_present": review.get("supply_exhaustion_flags_present") or [],

            "demand_support_validated": review.get("demand_support_validated"),
            "demand_support_flags_present": review.get("demand_support_flags_present") or [],

            "contrary_failure_present": review.get("contrary_failure_present"),
            "contrary_failure_flags_present": review.get("contrary_failure_flags_present") or [],
            "contrary_risk_context_present": review.get("contrary_risk_context_present") or [],

            "block_reasons": review.get("block_reasons") or [],
            "doctrine_rule": review.get("doctrine_rule"),

            "production_confirmation_allowed": review.get("production_confirmation_allowed"),
            "operator_control_confirmed_by_this_engine": review.get("operator_control_confirmed_by_this_engine"),
            "operator_control_confirmation_impact": review.get("operator_control_confirmation_impact"),
            "score_impact": review.get("score_impact"),
            "rank_impact": review.get("rank_impact"),
            "state_impact": review.get("state_impact"),
            "transition_impact": review.get("transition_impact"),
        })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("existing_control_context") == "SHADOW_CONFIRMABLE_BUT_EXISTING_ENGINE_UNCONFIRMED" else
            1 if row.get("doctrine_verdict") == "DOCTRINE_NOT_CONFIRMABLE" and row.get("footprint_count", 0) >= 4 else
            2 if row.get("existing_control_context") == "ALREADY_CONFIRMED_BY_EXISTING_OPERATOR_CONTROL_ENGINE" else
            3,
            -int(row.get("footprint_count") or 0),
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": ENGINE_NAME + "_REVIEW",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/wyckoff-weis-operator-confirmation-review",
        "read_only": True,
        "diagnostic_only": True,
        "shadow_production": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "not_a_trade_signal": True,
        "total_campaigns": len(campaigns),
        "review_rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),

        "doctrine_rule": (
            "Composite Operator Control = Tested Supply Exhaustion "
            "AND Active Demand/Support Validation "
            "AND Structurally Meaningful Location "
            "AND NOT Contrary Failure"
        ),

        "doctrine_confirmable_distribution": _counter_to_dict(doctrine_confirmable_counter),
        "doctrine_verdict_distribution": _counter_to_dict(doctrine_verdict_counter),
        "existing_control_context_distribution": _counter_to_dict(existing_control_context_counter),
        "campaign_state_distribution": _counter_to_dict(campaign_state_counter),
        "sml_present_distribution": _counter_to_dict(sml_counter),
        "sml_location_distribution": _counter_to_dict(sml_location_counter),
        "sml_evidence_quality_distribution": _counter_to_dict(sml_quality_counter),
        "supply_exhaustion_flag_distribution": _counter_to_dict(supply_counter),
        "demand_support_flag_distribution": _counter_to_dict(demand_counter),
        "contrary_failure_distribution": _counter_to_dict(contrary_counter),
        "block_reason_distribution": _counter_to_dict(block_reason_counter),

        "review_rows": rows,
        "guardrail_failures": guardrail_failures,
    }










@router.get("/explicit-sml-taxonomy-audit-review")
def explicit_sml_taxonomy_audit_review():
    """
    D3G read-only no-drift taxonomy audit endpoint.

    Separates explicit SML evidence into:
    1. constructive lower-zone SML
    2. risk-side upper-zone SML

    This endpoint does NOT repair D3C.
    This endpoint does NOT alter D3D.
    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    """
    from collections import Counter

    try:
        from backend.campaign_engine.explicit_sml_taxonomy_audit_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            audit_explicit_sml_taxonomy,
        )
    except Exception:
        from campaign_engine.explicit_sml_taxonomy_audit_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            audit_explicit_sml_taxonomy,
        )

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    guardrail_failures = []

    taxonomy_counter = Counter()
    no_drift_counter = Counter()
    d3d_allowed_counter = Counter()
    lower_zone_counter = Counter()
    upper_zone_counter = Counter()
    lower_flag_counter = Counter()
    upper_flag_counter = Counter()

    for campaign in campaigns:
        row = audit_explicit_sml_taxonomy(campaign)
        rows.append(row)

        taxonomy_counter[str(row.get("taxonomy_classification"))] += 1
        no_drift_counter[str(row.get("no_drift_status"))] += 1
        d3d_allowed_counter[str(bool(row.get("d3d_allowed_by_taxonomy")))] += 1
        lower_zone_counter[str(bool(row.get("constructive_lower_zone")))] += 1
        upper_zone_counter[str(bool(row.get("risk_side_upper_zone")))] += 1

        for flag in row.get("lower_zone_flags") or []:
            lower_flag_counter[str(flag)] += 1

        for flag in row.get("upper_zone_flags") or []:
            upper_flag_counter[str(flag)] += 1

        guardrail_ok = (
            row.get("read_only") is True
            and row.get("diagnostic_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("no_drift_status") == "FAIL" else 1,
            0 if row.get("risk_side_upper_zone") is True else 1,
            0 if row.get("constructive_lower_zone") is True else 1,
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/explicit-sml-taxonomy-audit-review",

        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "production_confirmation_allowed": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,

        "total_campaigns": len(campaigns),
        "rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),

        "taxonomy_classification_distribution": _counter_to_dict(taxonomy_counter),
        "no_drift_status_distribution": _counter_to_dict(no_drift_counter),
        "d3d_allowed_by_taxonomy_distribution": _counter_to_dict(d3d_allowed_counter),
        "constructive_lower_zone_distribution": _counter_to_dict(lower_zone_counter),
        "risk_side_upper_zone_distribution": _counter_to_dict(upper_zone_counter),
        "lower_zone_flag_distribution": _counter_to_dict(lower_flag_counter),
        "upper_zone_flag_distribution": _counter_to_dict(upper_flag_counter),

        "rows": rows,
        "guardrail_failures": guardrail_failures,
    }



@router.get("/explicit-upper-zone-diagnostic-review")
def explicit_upper_zone_diagnostic_review():
    """
    D3F read-only diagnostic endpoint.

    Separates constructive lower-zone SML from upper-zone / upthrust risk-side
    SML so D3D does not drift by treating all explicit geometry as operator
    control confirmation.

    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT change scores, ranks, states, transitions, gamma,
    probabilities, expected return, edge, targets, or historical outcomes.
    """
    from collections import Counter

    try:
        from backend.campaign_engine.explicit_upper_zone_diagnostic_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            diagnose_explicit_upper_zone,
        )
    except Exception:
        from campaign_engine.explicit_upper_zone_diagnostic_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            diagnose_explicit_upper_zone,
        )

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    guardrail_failures = []

    constructive_lower_counter = Counter()
    explicit_upper_counter = Counter()
    upper_class_counter = Counter()
    doctrine_handling_counter = Counter()
    state_counter = Counter()
    confirmed_counter = Counter()

    for campaign in campaigns:
        row = diagnose_explicit_upper_zone(campaign)
        rows.append(row)

        constructive_lower_counter[str(bool(row.get("constructive_lower_zone")))] += 1
        explicit_upper_counter[str(bool(row.get("explicit_upper_zone")))] += 1
        upper_class_counter[str(row.get("upper_zone_classification"))] += 1
        doctrine_handling_counter[str(row.get("doctrine_handling"))] += 1
        state_counter[str(row.get("campaign_state"))] += 1
        confirmed_counter[str(bool(row.get("operator_control_confirmed_current")))] += 1

        guardrail_ok = (
            row.get("read_only") is True
            and row.get("diagnostic_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("explicit_upper_zone") is True else 1,
            0 if row.get("operator_control_confirmed_current") is False else 1,
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/explicit-upper-zone-diagnostic-review",

        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "production_confirmation_allowed": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,

        "total_campaigns": len(campaigns),
        "rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),

        "constructive_lower_zone_distribution": _counter_to_dict(constructive_lower_counter),
        "explicit_upper_zone_distribution": _counter_to_dict(explicit_upper_counter),
        "upper_zone_classification_distribution": _counter_to_dict(upper_class_counter),
        "doctrine_handling_distribution": _counter_to_dict(doctrine_handling_counter),
        "campaign_state_distribution": _counter_to_dict(state_counter),
        "operator_control_confirmed_distribution": _counter_to_dict(confirmed_counter),

        "rows": rows,
        "guardrail_failures": guardrail_failures,
    }



@router.get("/explicit-geometry-sml-diagnostic-review")
def explicit_geometry_sml_diagnostic_review():
    """
    D3E read-only diagnostic endpoint.

    Explains why campaigns do or do not produce EXPLICIT_GEOMETRY SML.

    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT change scores, ranks, states, transitions, gamma,
    probabilities, expected return, edge, targets, or historical outcomes.
    """
    from collections import Counter

    try:
        from backend.campaign_engine.explicit_geometry_sml_diagnostic_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            diagnose_explicit_geometry_sml,
        )
    except Exception:
        from campaign_engine.explicit_geometry_sml_diagnostic_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            diagnose_explicit_geometry_sml,
        )

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    explicit_geometry_counter = Counter()
    sml_quality_counter = Counter()
    doctrine_counter = Counter()
    d3d_counter = Counter()
    gap_reason_counter = Counter()
    flag_counter = Counter()
    guardrail_failures = []

    for campaign in campaigns:
        row = diagnose_explicit_geometry_sml(campaign)
        rows.append(row)

        explicit_geometry_counter[str(bool(row.get("explicit_geometry_available")))] += 1
        sml_quality_counter[str(row.get("d3c_shadow_sml_evidence_quality"))] += 1
        doctrine_counter[str(row.get("d3c_shadow_doctrine_verdict"))] += 1
        d3d_counter[str(bool(row.get("d3d_eligible_for_mutation")))] += 1

        for reason in row.get("geometry_gap_reasons") or []:
            gap_reason_counter[str(reason)] += 1

        for flag in row.get("explicit_sml_flags_present") or []:
            flag_counter[str(flag)] += 1

        guardrail_ok = (
            row.get("read_only") is True
            and row.get("diagnostic_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("d3c_shadow_sml_evidence_quality") == "EXPLICIT_GEOMETRY" else 1,
            0 if row.get("d3c_shadow_doctrine_confirmable") is True else 1,
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/explicit-geometry-sml-diagnostic-review",

        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "production_confirmation_allowed": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,

        "total_campaigns": len(campaigns),
        "rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),

        "explicit_geometry_available_distribution": _counter_to_dict(explicit_geometry_counter),
        "sml_evidence_quality_distribution": _counter_to_dict(sml_quality_counter),
        "doctrine_verdict_distribution": _counter_to_dict(doctrine_counter),
        "d3d_eligible_distribution": _counter_to_dict(d3d_counter),
        "geometry_gap_reason_distribution": _counter_to_dict(gap_reason_counter),
        "explicit_sml_flag_distribution": _counter_to_dict(flag_counter),

        "rows": rows,
        "guardrail_failures": guardrail_failures,
    }





@router.get("/operator-control-plausibility-status-review")
def operator_control_plausibility_status_review():
    """
    D3J read-only operator-control plausibility status endpoint.

    Identifies shadow-confirmable / plausible stealth operator-control campaigns
    without confirming, unconfirming, repairing, or mutating operator control.

    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT unconfirm operator control.
    This endpoint does NOT execute D3D.
    """
    from collections import Counter

    try:
        from backend.campaign_engine.operator_control_plausibility_status_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            classify_operator_control_plausibility,
        )
        from backend.campaign_engine.operator_control_production_mutation_gate import (
            evaluate_d3d_operator_control_candidate,
        )
    except Exception:
        from campaign_engine.operator_control_plausibility_status_engine import (
            ENGINE_NAME,
            ENGINE_VERSION,
            classify_operator_control_plausibility,
        )
        from campaign_engine.operator_control_production_mutation_gate import (
            evaluate_d3d_operator_control_candidate,
        )

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    guardrail_failures = []

    status_counter = Counter()
    no_drift_counter = Counter()
    shadow_counter = Counter()
    legacy_counter = Counter()
    d3d_production_counter = Counter()
    d3d_eligible_counter = Counter()
    state_counter = Counter()

    for campaign in campaigns:
        d3d_candidate = evaluate_d3d_operator_control_candidate(campaign)
        row = classify_operator_control_plausibility(campaign, d3d_candidate)
        rows.append(row)

        status_counter[str(row.get("plausibility_status"))] += 1
        no_drift_counter[str(row.get("no_drift_status"))] += 1
        shadow_counter[str(bool(row.get("shadow_confirmable")))] += 1
        legacy_counter[str(bool(row.get("legacy_operator_control_confirmed")))] += 1
        d3d_production_counter[str(bool(row.get("d3d_production_confirmed")))] += 1
        d3d_eligible_counter[str(bool(row.get("d3d_eligible_dry_run_only")))] += 1
        state_counter[str(row.get("campaign_state"))] += 1

        guardrail_ok = (
            row.get("read_only") is True
            and row.get("diagnostic_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("operator_control_unconfirmed_by_this_engine") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("d3d_execution_allowed") is False
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append(row)

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("plausibility_status") == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED" else
            1 if row.get("plausibility_status") == "LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE" else
            2 if row.get("plausibility_status") == "LEGACY_OPERATOR_CONTROL_NOT_CURRENTLY_SHADOW_CONFIRMABLE" else
            3,
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/operator-control-plausibility-status-review",

        "read_only": True,
        "diagnostic_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_unconfirmed_by_this_engine": False,
        "production_confirmation_allowed": False,
        "d3d_execution_allowed": False,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_a_trade_signal": True,

        "total_campaigns": len(campaigns),
        "rows_count": len(rows),
        "guardrail_failure_count": len(guardrail_failures),

        "plausibility_status_distribution": _counter_to_dict(status_counter),
        "no_drift_status_distribution": _counter_to_dict(no_drift_counter),
        "shadow_confirmable_distribution": _counter_to_dict(shadow_counter),
        "legacy_operator_control_confirmed_distribution": _counter_to_dict(legacy_counter),
        "d3d_production_confirmed_distribution": _counter_to_dict(d3d_production_counter),
        "d3d_eligible_dry_run_only_distribution": _counter_to_dict(d3d_eligible_counter),
        "campaign_state_distribution": _counter_to_dict(state_counter),

        "rows": rows,
        "guardrail_failures": guardrail_failures,
    }



@router.post("/operator-control-production-mutation-gate")
def operator_control_production_mutation_gate(request: dict | None = None):
    """
    D3D controlled production mutation gate.
    Default behavior is dry-run only.
    Execution requires:
    - request.execute == True
    - request.confirm_phrase == D3D_OPERATOR_CONTROL_PRODUCTION_MUTATION_APPROVED
    Mutation target:
    - evidence.operator_control.operator_control_confirmed only
    This endpoint must not mutate scores, ranks, states, transitions, gamma,
    probability, expected return, edge, target, or historical outcome fields.
    """
    from collections import Counter
    try:
        from backend.campaign_engine.operator_control_production_mutation_gate import (
            ENGINE_NAME,
            ENGINE_VERSION,
            CONFIRM_PHRASE,
            evaluate_d3d_operator_control_candidate,
            build_d3d_operator_control_mutation,
        )
    except Exception:
        from campaign_engine.operator_control_production_mutation_gate import (
            ENGINE_NAME,
            ENGINE_VERSION,
            CONFIRM_PHRASE,
            evaluate_d3d_operator_control_candidate,
            build_d3d_operator_control_mutation,
        )
    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}
    payload = request or {}
    execute_requested = bool(payload.get("execute") is True)
    confirm_phrase = str(payload.get("confirm_phrase") or "")
    execution_authorized = bool(execute_requested and confirm_phrase == CONFIRM_PHRASE)
    max_mutations = int(payload.get("max_mutations") or 10)
    if max_mutations < 0:
        max_mutations = 0
    requested_symbols = payload.get("symbols") or payload.get("symbol") or []
    if isinstance(requested_symbols, str):
        requested_symbols = [requested_symbols]
    requested_symbols = {str(symbol).upper() for symbol in requested_symbols if symbol}
    campaigns = _store().get_active_campaigns()
    rows = []
    eligible_rows = []
    skipped_rows = []
    mutation_summaries = []
    mutation_errors = []
    eligibility_counter = Counter()
    verdict_counter = Counter()
    sml_quality_counter = Counter()
    block_reason_counter = Counter()
    for campaign in campaigns:
        c = _as_dict(campaign)
        symbol = str(c.get("symbol") or "").upper()
        if requested_symbols and symbol not in requested_symbols:
            continue
        candidate = evaluate_d3d_operator_control_candidate(c)
        rows.append(candidate)
        eligibility_counter[str(bool(candidate.get("eligible_for_d3d_mutation")))] += 1
        verdict_counter[str(candidate.get("d3c_shadow_doctrine_verdict"))] += 1
        sml_quality_counter[str(candidate.get("d3c_shadow_sml_evidence_quality"))] += 1
        for reason in candidate.get("block_reasons") or []:
            block_reason_counter[str(reason)] += 1
        if candidate.get("eligible_for_d3d_mutation") is True:
            eligible_rows.append(candidate)
        else:
            skipped_rows.append(candidate)
    if execution_authorized:
        mutation_limit = min(max_mutations, len(eligible_rows))
        for candidate in eligible_rows[:mutation_limit]:
            try:
                source_campaign = None
                for campaign in campaigns:
                    c = _as_dict(campaign)
                    if (
                        str(c.get("symbol") or "").upper() == str(candidate.get("symbol") or "").upper()
                        and str(c.get("timeframe") or "DAILY") == str(candidate.get("timeframe") or "DAILY")
                    ):
                        source_campaign = c
                        break
                if source_campaign is None:
                    mutation_errors.append({
                        "symbol": candidate.get("symbol"),
                        "campaign_id": candidate.get("campaign_id"),
                        "error": "SOURCE_CAMPAIGN_NOT_FOUND",
                    })
                    continue
                updated_campaign, mutation_summary = build_d3d_operator_control_mutation(
                    source_campaign,
                    candidate,
                )
                _store().save_campaign(updated_campaign)
                mutation_summaries.append(mutation_summary)
            except Exception as exc:
                mutation_errors.append({
                    "symbol": candidate.get("symbol"),
                    "campaign_id": candidate.get("campaign_id"),
                    "error": str(exc),
                })
    return {
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/operator-control-production-mutation-gate",
        "dry_run": not execution_authorized,
        "execute_requested": execute_requested,
        "execution_authorized": execution_authorized,
        "required_confirm_phrase": CONFIRM_PHRASE if execute_requested and not execution_authorized else None,
        "writes_to_supabase": bool(execution_authorized and len(mutation_summaries) > 0),
        "mutates_campaigns": bool(execution_authorized and len(mutation_summaries) > 0),
        "production_confirmation_allowed": bool(execution_authorized),
        "mutation_target": "evidence.operator_control.operator_control_confirmed",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "gamma_confirmation_impact": "NONE",
        "not_derived_from_scores": True,
        "not_a_trade_signal": True,
        "total_campaigns_seen": len(campaigns),
        "total_campaigns_reviewed": len(rows),
        "eligible_count": len(eligible_rows),
        "skipped_count": len(skipped_rows),
        "max_mutations": max_mutations,
        "mutations_attempted": len(mutation_summaries) + len(mutation_errors),
        "mutations_succeeded": len(mutation_summaries),
        "mutations_failed": len(mutation_errors),
        "eligibility_distribution": dict(sorted(eligibility_counter.items())),
        "doctrine_verdict_distribution": dict(sorted(verdict_counter.items())),
        "sml_evidence_quality_distribution": dict(sorted(sml_quality_counter.items())),
        "block_reason_distribution": dict(sorted(block_reason_counter.items())),
        "eligible_rows": eligible_rows,
        "mutation_summaries": mutation_summaries,
        "mutation_errors": mutation_errors,
    }


@router.get("/operator-control-confirmation-candidate-review")
def operator_control_confirmation_candidate_review():
    """
    D3A read-only diagnostic endpoint.

    Reviews which campaigns qualify as Composite Operator confirmation
    candidates under the D3A doctrine.

    This endpoint does NOT confirm operator control.
    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT change scores, ranks, states, transitions,
    or existing operator-control confirmation.
    """
    from collections import Counter

    try:
        from backend.campaign_engine.operator_control_confirmation_candidate_engine import (
            classify_operator_control_confirmation_candidate,
            ENGINE_NAME,
            ENGINE_VERSION,
        )
    except Exception:
        from campaign_engine.operator_control_confirmation_candidate_engine import (
            classify_operator_control_confirmation_candidate,
            ENGINE_NAME,
            ENGINE_VERSION,
        )

    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}

    def _get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    guardrail_failures = []

    verdict_counter = Counter()
    candidate_counter = Counter()
    campaign_state_counter = Counter()
    hard_flag_counter = Counter()
    vsa_weis_counter = Counter()
    caution_counter = Counter()
    footprint_count_counter = Counter()

    for campaign in campaigns:
        c = _as_dict(campaign)
        evidence = _as_dict(_get(c, "evidence", {}))

        symbol = _get(c, "symbol")
        campaign_id = _get(c, "campaign_id") or _get(c, "id")
        campaign_state = (
            _get(c, "current_state")
            or _get(c, "state_enum")
            or _get(c, "campaign_state")
            or _get(c, "state")
            or _get(c, "lifecycle_state")
            or _get(c, "campaign_lifecycle_state")
        )
        timeframe = _get(c, "timeframe") or _get(evidence, "timeframe") or "DAILY"

        candidate = classify_operator_control_confirmation_candidate(
            evidence=evidence,
            symbol=symbol,
            campaign_state=campaign_state,
        )

        guardrail_ok = (
            candidate.get("diagnostic_only") is True
            and candidate.get("read_only") is True
            and candidate.get("production_confirmation_allowed") is False
            and candidate.get("operator_control_confirmed_by_this_engine") is False
            and candidate.get("operator_control_confirmation_impact") == "NONE"
            and candidate.get("score_impact") == "NONE"
            and candidate.get("rank_impact") == "NONE"
            and candidate.get("state_impact") == "NONE"
            and candidate.get("transition_impact") == "NONE"
            and candidate.get("state_transition_enabled") is False
            and candidate.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "D3A candidate guardrail failure",
                "payload": candidate,
            })

        candidate_verdict = candidate.get("candidate_verdict")
        confirmation_candidate = bool(candidate.get("confirmation_candidate"))

        verdict_counter[str(candidate_verdict)] += 1
        candidate_counter[str(confirmation_candidate)] += 1
        campaign_state_counter[str(campaign_state)] += 1
        footprint_count_counter[str(candidate.get("footprint_count"))] += 1

        for flag in candidate.get("hard_confirmation_flags_present") or []:
            hard_flag_counter[str(flag)] += 1

        for flag in candidate.get("vsa_weis_confirmation_flags_present") or []:
            vsa_weis_counter[str(flag)] += 1

        for flag in candidate.get("caution_flags_present") or []:
            caution_counter[str(flag)] += 1

        rows.append({
            "symbol": symbol,
            "campaign_id": campaign_id,
            "campaign_state": campaign_state,
            "timeframe": timeframe,
            "confirmation_candidate": confirmation_candidate,
            "candidate_verdict": candidate_verdict,
            "candidate_reason": candidate.get("candidate_reason"),
            "footprint_present": candidate.get("footprint_present"),
            "footprint_count": candidate.get("footprint_count"),
            "footprint_archetypes": candidate.get("footprint_archetypes") or [],
            "operator_control_confirmed_current": candidate.get("operator_control_confirmed_current"),
            "hard_confirmation_flags_present": candidate.get("hard_confirmation_flags_present") or [],
            "vsa_weis_confirmation_flags_present": candidate.get("vsa_weis_confirmation_flags_present") or [],
            "caution_flags_present": candidate.get("caution_flags_present") or [],
            "hard_confirmation_count": candidate.get("hard_confirmation_count"),
            "caution_count": candidate.get("caution_count"),
            "risk_context": candidate.get("risk_context") or [],
            "candidate_rule": candidate.get("candidate_rule"),
            "production_confirmation_allowed": candidate.get("production_confirmation_allowed"),
            "operator_control_confirmed_by_this_engine": candidate.get("operator_control_confirmed_by_this_engine"),
            "score_impact": candidate.get("score_impact"),
            "rank_impact": candidate.get("rank_impact"),
            "state_impact": candidate.get("state_impact"),
            "transition_impact": candidate.get("transition_impact"),
            "operator_control_confirmation_impact": candidate.get("operator_control_confirmation_impact"),
        })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("candidate_verdict") == "D3A_CONFIRMATION_CANDIDATE" else
            1 if row.get("candidate_verdict") == "D3A_CANDIDATE_BLOCKED_BY_CAUTION" else
            2 if row.get("candidate_verdict") == "D3A_DENSE_FOOTPRINT_MISSING_HARD_CONFIRMATION" else
            3 if row.get("candidate_verdict") == "LEGACY_OPERATOR_CONTROL_EVIDENCE_ALREADY_PRESENT" else
            4,
            -int(row.get("footprint_count") or 0),
            -int(row.get("hard_confirmation_count") or 0),
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": ENGINE_NAME + "_REVIEW",
        "version": ENGINE_VERSION,
        "endpoint": "/api/campaign/operator-control-confirmation-candidate-review",
        "read_only": True,
        "diagnostic_only": True,
        "production_confirmation_allowed": False,
        "operator_control_confirmed_by_this_engine": False,
        "operator_control_confirmation_impact": "NONE",
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "total_campaigns": len(campaigns),
        "review_rows_count": len(rows),
        "confirmation_candidate_distribution": _counter_to_dict(candidate_counter),
        "candidate_verdict_distribution": _counter_to_dict(verdict_counter),
        "campaign_state_distribution": _counter_to_dict(campaign_state_counter),
        "footprint_count_distribution": _counter_to_dict(footprint_count_counter),
        "hard_confirmation_flag_distribution": _counter_to_dict(hard_flag_counter),
        "vsa_weis_confirmation_distribution": _counter_to_dict(vsa_weis_counter),
        "caution_flag_distribution": _counter_to_dict(caution_counter),
        "guardrail_failure_count": len(guardrail_failures),
        "review_rows": rows,
        "guardrail_failures": guardrail_failures,
    }



@router.get("/operator-control-reconciliation-review")
def operator_control_reconciliation_review():
    """
    Read-only diagnostic reconciliation between early operator footprints
    and legacy tape-derived operator-control evidence.
    """
    from collections import Counter

    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}

    def _get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    def _true_flags(payload, names):
        payload = _as_dict(payload)
        return [name for name in names if bool(payload.get(name))]

    campaigns = _store().get_active_campaigns()

    hard_confirmation_flag_names = [
        "survives_adverse_tests",
        "recapture_after_breakdown",
        "demand_efficiency_dominates_supply",
        "shortening_downside_thrust",
        "high_volume_controlled_spread",
        "absorption_against_resistance",
        "supply_failure",
    ]

    vsa_weis_confirmation_names = [
        "effort_vs_result_divergence",
        "no_supply_test",
    ]

    caution_flag_names = [
        "no_demand_test",
        "upthrust_supply",
        "buying_climax",
    ]

    rows = []
    missing_rows = []
    guardrail_failures = []

    reconciliation_counter = Counter()
    campaign_state_counter = Counter()
    footprint_count_counter = Counter()
    hard_flag_counter = Counter()
    vsa_weis_counter = Counter()
    caution_counter = Counter()

    for campaign in campaigns:
        c = _as_dict(campaign)
        evidence = _as_dict(_get(c, "evidence", {}))

        symbol = _get(c, "symbol")
        campaign_id = _get(c, "campaign_id") or _get(c, "id")
        campaign_state = (
            _get(c, "current_state")
            or _get(c, "state_enum")
            or _get(c, "campaign_state")
            or _get(c, "state")
            or _get(c, "lifecycle_state")
            or _get(c, "campaign_lifecycle_state")
        )
        timeframe = _get(c, "timeframe") or _get(evidence, "timeframe") or "DAILY"

        footprints = _as_dict(evidence.get("early_operator_footprints"))
        operator_control = _as_dict(evidence.get("operator_control"))

        if not footprints:
            missing_rows.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "missing early_operator_footprints",
            })
            continue

        raw_flags = _as_dict(footprints.get("raw_operator_flags"))
        vsa_weis = _as_dict(footprints.get("vsa_weis_inputs"))
        wyckoff_inputs = _as_dict(footprints.get("wyckoff_inputs"))

        footprint_present = bool(footprints.get("footprint_present"))
        footprint_count = int(footprints.get("footprint_count") or 0)
        operator_control_confirmed = bool(operator_control.get("operator_control_confirmed"))
        operator_control_verdict = operator_control.get("verdict")

        hard_flags_present = _true_flags(raw_flags, hard_confirmation_flag_names)
        vsa_weis_confirmation_flags_present = _true_flags(vsa_weis, vsa_weis_confirmation_names)
        caution_flags_present = _true_flags(vsa_weis, caution_flag_names)

        hard_confirmation_count = len(hard_flags_present) + len(vsa_weis_confirmation_flags_present)
        caution_count = len(caution_flags_present)

        archetype_names = []
        for item in footprints.get("footprint_archetypes") or []:
            d = _as_dict(item)
            name = d.get("archetype")
            if name:
                archetype_names.append(name)

        if operator_control_confirmed:
            reconciliation_bucket = "CONFIRMED_CONTROL"
        elif footprint_present and footprint_count >= 4 and hard_confirmation_count >= 1 and caution_count == 0:
            reconciliation_bucket = "HIGH_DENSITY_UNCONFIRMED_WITH_HARD_CONFIRMATION"
        elif footprint_present and footprint_count >= 4 and hard_confirmation_count == 0:
            reconciliation_bucket = "HIGH_DENSITY_UNCONFIRMED_MISSING_HARD_CONFIRMATION"
        elif footprint_present and footprint_count >= 4 and caution_count > 0:
            reconciliation_bucket = "HIGH_DENSITY_UNCONFIRMED_WITH_CAUTION"
        elif footprint_present:
            reconciliation_bucket = "EARLY_FOOTPRINT_NOT_CONFIRMED"
        else:
            reconciliation_bucket = "NO_OPERATOR_FOOTPRINT"

        guardrail_ok = (
            footprints.get("diagnostic_only") is True
            and footprints.get("score_impact") == "NONE"
            and footprints.get("rank_impact") == "NONE"
            and footprints.get("state_impact") == "NONE"
            and footprints.get("transition_impact") == "NONE"
            and footprints.get("state_transition_enabled") is False
            and footprints.get("operator_control_confirmation_impact") == "NONE"
            and footprints.get("operator_control_confirmed_by_this_engine") is False
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "early_operator_footprints guardrail failure",
            })

        reconciliation_counter[reconciliation_bucket] += 1
        campaign_state_counter[str(campaign_state)] += 1
        footprint_count_counter[str(footprint_count)] += 1

        for flag in hard_flags_present:
            hard_flag_counter[flag] += 1
        for flag in vsa_weis_confirmation_flags_present:
            vsa_weis_counter[flag] += 1
        for flag in caution_flags_present:
            caution_counter[flag] += 1

        rows.append({
            "symbol": symbol,
            "campaign_id": campaign_id,
            "campaign_state": campaign_state,
            "timeframe": timeframe,
            "footprint_present": footprint_present,
            "footprint_count": footprint_count,
            "footprint_archetypes": archetype_names,
            "risk_context": footprints.get("risk_context") or [],
            "operator_control_verdict": operator_control_verdict,
            "operator_control_confirmed": operator_control_confirmed,
            "hard_confirmation_flags_present": hard_flags_present,
            "vsa_weis_confirmation_flags_present": vsa_weis_confirmation_flags_present,
            "caution_flags_present": caution_flags_present,
            "hard_confirmation_count": hard_confirmation_count,
            "caution_count": caution_count,
            "reconciliation_bucket": reconciliation_bucket,
            "raw_operator_flags": raw_flags,
            "wyckoff_inputs": wyckoff_inputs,
            "vsa_weis_inputs": vsa_weis,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "operator_control_confirmation_impact": "NONE",
        })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("reconciliation_bucket") == "HIGH_DENSITY_UNCONFIRMED_WITH_HARD_CONFIRMATION" else
            1 if row.get("reconciliation_bucket") == "HIGH_DENSITY_UNCONFIRMED_MISSING_HARD_CONFIRMATION" else
            2 if row.get("reconciliation_bucket") == "HIGH_DENSITY_UNCONFIRMED_WITH_CAUTION" else
            3 if row.get("reconciliation_bucket") == "CONFIRMED_CONTROL" else
            4,
            -int(row.get("footprint_count") or 0),
            -int(row.get("hard_confirmation_count") or 0),
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": "OPERATOR_CONTROL_RECONCILIATION_REVIEW",
        "version": "phase_d2_12_read_only_v1",
        "endpoint": "/api/campaign/operator-control-reconciliation-review",
        "read_only": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "operator_control_confirmation_impact": "NONE",
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "total_campaigns": len(campaigns),
        "review_rows_count": len(rows),
        "missing_early_operator_footprints_count": len(missing_rows),
        "guardrail_failure_count": len(guardrail_failures),
        "reconciliation_distribution": _counter_to_dict(reconciliation_counter),
        "campaign_state_distribution": _counter_to_dict(campaign_state_counter),
        "footprint_count_distribution": _counter_to_dict(footprint_count_counter),
        "hard_confirmation_flag_distribution": _counter_to_dict(hard_flag_counter),
        "vsa_weis_confirmation_distribution": _counter_to_dict(vsa_weis_counter),
        "caution_flag_distribution": _counter_to_dict(caution_counter),
        "hard_confirmation_flag_names": hard_confirmation_flag_names,
        "vsa_weis_confirmation_names": vsa_weis_confirmation_names,
        "caution_flag_names": caution_flag_names,
        "review_rows": rows,
        "missing_rows": missing_rows,
        "guardrail_failures": guardrail_failures,
    }



@router.get("/early-operator-footprint-review")
def early_operator_footprint_review():
    """
    Read-only diagnostic review of early Composite Operator footprint evidence.

    This endpoint does not write to Supabase.
    This endpoint does not mutate campaigns.
    This endpoint does not change scores, ranks, campaign states, transitions,
    or operator-control confirmation.
    """
    from collections import Counter

    def _as_dict(value):
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception:
                return {}
        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception:
                return {}
        return {}

    def _get(value, key, default=None):
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    def _counter_to_dict(counter):
        return dict(sorted(counter.items(), key=lambda item: (-item[1], str(item[0]))))

    campaigns = _store().get_active_campaigns()

    rows = []
    missing_rows = []
    guardrail_failures = []

    archetype_counter = Counter()
    risk_counter = Counter()
    footprint_count_counter = Counter()
    footprint_present_counter = Counter()
    status_counter = Counter()
    operator_cross_counter = Counter()
    campaign_state_counter = Counter()

    for campaign in campaigns:
        c = _as_dict(campaign)
        evidence = _as_dict(_get(c, "evidence", {}))

        symbol = _get(c, "symbol")
        campaign_id = _get(c, "campaign_id") or _get(c, "id")
        campaign_state = (
            _get(c, "current_state")
            or _get(c, "state_enum")
            or _get(c, "campaign_state")
            or _get(c, "state")
            or _get(c, "lifecycle_state")
            or _get(c, "campaign_lifecycle_state")
        )
        timeframe = _get(c, "timeframe") or _get(evidence, "timeframe") or "DAILY"

        footprints = _as_dict(evidence.get("early_operator_footprints"))
        operator_control = _as_dict(evidence.get("operator_control"))
        doctrine = _as_dict(evidence.get("doctrine_classifier"))

        if not footprints:
            missing_rows.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "missing early_operator_footprints",
            })
            continue

        status = footprints.get("status")
        footprint_present = bool(footprints.get("footprint_present"))
        footprint_count = footprints.get("footprint_count", 0)
        archetypes_raw = footprints.get("footprint_archetypes") or []
        risk_context = footprints.get("risk_context") or []

        archetype_names = []
        for item in archetypes_raw:
            d = _as_dict(item)
            name = d.get("archetype")
            if name:
                archetype_names.append(name)
                archetype_counter[name] += 1

        for risk in risk_context:
            risk_counter[risk] += 1

        footprint_present_counter[str(footprint_present)] += 1
        footprint_count_counter[str(footprint_count)] += 1
        status_counter[str(status)] += 1
        campaign_state_counter[str(campaign_state)] += 1

        operator_control_confirmed = bool(operator_control.get("operator_control_confirmed"))
        operator_control_verdict = operator_control.get("verdict")

        if footprint_present and operator_control_confirmed:
            operator_cross_context = "FOOTPRINT_PRESENT_AND_OPERATOR_CONTROL_CONFIRMED"
        elif footprint_present and not operator_control_confirmed:
            operator_cross_context = "FOOTPRINT_PRESENT_OPERATOR_CONTROL_NOT_CONFIRMED"
        elif not footprint_present and operator_control_confirmed:
            operator_cross_context = "NO_FOOTPRINT_BUT_OPERATOR_CONTROL_CONFIRMED"
        else:
            operator_cross_context = "NO_FOOTPRINT_AND_OPERATOR_CONTROL_NOT_CONFIRMED"

        operator_cross_counter[operator_cross_context] += 1

        guardrail_ok = (
            footprints.get("diagnostic_only") is True
            and footprints.get("score_impact") == "NONE"
            and footprints.get("rank_impact") == "NONE"
            and footprints.get("state_impact") == "NONE"
            and footprints.get("transition_impact") == "NONE"
            and footprints.get("state_transition_enabled") is False
            and footprints.get("operator_control_confirmation_impact") == "NONE"
            and footprints.get("operator_control_confirmed_by_this_engine") is False
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "campaign_state": campaign_state,
                "reason": "early_operator_footprints guardrail failure",
                "payload": footprints,
            })

        rows.append({
            "symbol": symbol,
            "campaign_id": campaign_id,
            "campaign_state": campaign_state,
            "timeframe": timeframe,
            "engine": footprints.get("engine"),
            "version": footprints.get("version"),
            "status": status,
            "diagnostic_only": footprints.get("diagnostic_only"),
            "score_impact": footprints.get("score_impact"),
            "rank_impact": footprints.get("rank_impact"),
            "state_impact": footprints.get("state_impact"),
            "transition_impact": footprints.get("transition_impact"),
            "state_transition_enabled": footprints.get("state_transition_enabled"),
            "operator_control_confirmation_impact": footprints.get("operator_control_confirmation_impact"),
            "operator_control_confirmed_by_this_engine": footprints.get("operator_control_confirmed_by_this_engine"),
            "not_derived_from_gamma": footprints.get("not_derived_from_gamma"),
            "not_a_trade_signal": footprints.get("not_a_trade_signal"),
            "footprint_present": footprint_present,
            "footprint_count": footprint_count,
            "footprint_archetypes": archetype_names,
            "risk_context": risk_context,
            "operator_cross_context": operator_cross_context,
            "operator_control_verdict": operator_control_verdict,
            "operator_control_confirmed": operator_control_confirmed,
            "doctrine_labels": doctrine.get("doctrine_labels") or [],
            "wyckoff_inputs": footprints.get("wyckoff_inputs") or {},
            "raw_operator_flags": footprints.get("raw_operator_flags") or {},
            "vsa_weis_inputs": footprints.get("vsa_weis_inputs") or {},
        })

    rows = sorted(
        rows,
        key=lambda row: (
            -int(row.get("footprint_count") or 0),
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": "EARLY_OPERATOR_FOOTPRINT_REVIEW",
        "version": "phase_d2_8_read_only_v1",
        "endpoint": "/api/campaign/early-operator-footprint-review",
        "read_only": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "operator_control_confirmation_impact": "NONE",
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "total_campaigns": len(campaigns),
        "review_rows_count": len(rows),
        "missing_early_operator_footprints_count": len(missing_rows),
        "guardrail_failure_count": len(guardrail_failures),
        "footprint_present_distribution": _counter_to_dict(footprint_present_counter),
        "footprint_count_distribution": _counter_to_dict(footprint_count_counter),
        "archetype_distribution": _counter_to_dict(archetype_counter),
        "risk_context_distribution": _counter_to_dict(risk_counter),
        "status_distribution": _counter_to_dict(status_counter),
        "operator_cross_context_distribution": _counter_to_dict(operator_cross_counter),
        "campaign_state_distribution": _counter_to_dict(campaign_state_counter),
        "review_rows": rows,
        "missing_rows": missing_rows,
        "guardrail_failures": guardrail_failures,
    }



@router.get("/evidence-doctrine-review-rankings")
def evidence_doctrine_review_rankings():
    """
    Phase D1 - Doctrine review rankings.

    Read-only diagnostic endpoint.

    This endpoint organizes active campaigns by doctrine_classifier evidence.

    It does not:
    - score campaigns,
    - replace campaign rankings,
    - change campaign state,
    - enable transitions,
    - write to Supabase,
    - mutate evidence.
    """

    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)

    review_rows = []
    missing_classifier_rows = []
    bucket_distribution = {}
    gamma_overlay_context_distribution = {}
    existing_rank_context_distribution = {}
    diagnostic_cross_context_distribution = {}
    support_flag_distribution = {}
    risk_flag_distribution = {}
    label_distribution = {}
    status_counts = {}

    def _inc(target, key):
        key = str(key or "UNKNOWN")
        target[key] = int(target.get(key, 0)) + 1

    for campaign in campaigns:
        evidence = _as_dict(campaign.get("evidence"))
        classifier = _as_dict(evidence.get("doctrine_classifier"))

        symbol = str(campaign.get("symbol") or "").upper()
        campaign_state = (
            campaign.get("campaign_state")
            or campaign.get("current_state")
            or campaign.get("state_enum")
            or campaign.get("state")
        )
        timeframe = (
            campaign.get("timeframe")
            or evidence.get("timeframe")
            or "DAILY"
        )

        base_row = {
            "symbol": symbol,
            "campaign_id": campaign.get("campaign_id"),
            "campaign_state": campaign_state,
            "timeframe": timeframe,
        }

        if not classifier:
            missing_classifier_rows.append({
                **base_row,
                "reason": "MISSING_DOCTRINE_CLASSIFIER",
            })
            continue

        labels = classifier.get("doctrine_labels") or []
        if not isinstance(labels, list):
            labels = [str(labels)]
        labels = [str(label) for label in labels if str(label or "").strip()]
        label_set = set(labels)

        for label in labels:
            _inc(label_distribution, label)

        status = str(classifier.get("status") or "MISSING_STATUS")
        _inc(status_counts, status)

        conflict = _as_dict(classifier.get("conflict_interpretation"))
        conflicts_present = bool(conflict.get("conflicts_present"))

        has_operator = "OPERATOR_CONTROL_CONFIRMED" in label_set
        has_accumulation = "WYCKOFF_ACCUMULATION_SUPPORT" in label_set
        has_absorption = "ABSORPTION_SUPPORT_PRESENT" in label_set
        has_sos = "SOS_SUPPORT_PRESENT" in label_set
        has_spring = "SPRING_SUPPORT_PRESENT" in label_set
        has_no_supply = "VSA_NO_SUPPLY_SUPPORT" in label_set
        has_survival_risk = "WYCKOFF_SURVIVAL_AT_RISK" in label_set

        has_distribution_caution = any(item in label_set for item in [
            "DISTRIBUTION_RISK_PRESENT",
            "VSA_NO_DEMAND_CAUTION",
            "VSA_UPTHRUST_RISK",
        ])

        support_flags = []
        risk_flags = []

        if has_operator:
            support_flags.append("OPERATOR_CONTROL_CONFIRMED")
        if has_accumulation:
            support_flags.append("WYCKOFF_ACCUMULATION_SUPPORT")
        if has_absorption:
            support_flags.append("ABSORPTION_SUPPORT_PRESENT")
        if has_sos:
            support_flags.append("SOS_SUPPORT_PRESENT")
        if has_spring:
            support_flags.append("SPRING_SUPPORT_PRESENT")
        if has_no_supply:
            support_flags.append("VSA_NO_SUPPLY_SUPPORT")

        if has_survival_risk:
            risk_flags.append("WYCKOFF_SURVIVAL_AT_RISK")
        if has_distribution_caution:
            risk_flags.append("DISTRIBUTION_OR_VSA_CAUTION")
        if conflicts_present:
            risk_flags.append("CONFLICT_PRESENT")

        for flag in support_flags:
            _inc(support_flag_distribution, flag)
        for flag in risk_flags:
            _inc(risk_flag_distribution, flag)

        if conflicts_present:
            review_bucket = "CONFLICTED_EVIDENCE_REVIEW"
            diagnostic_review_order = 6
        elif has_operator and (has_accumulation or has_absorption) and (has_sos or has_spring):
            review_bucket = "OPERATOR_WITH_SPRING_SOS_SUPPORT"
            diagnostic_review_order = 1
        elif has_operator and (has_accumulation or has_absorption):
            review_bucket = "OPERATOR_ACCUMULATION_EVIDENCED"
            diagnostic_review_order = 2
        elif has_accumulation and has_absorption:
            review_bucket = "ACCUMULATION_ABSORPTION_EVIDENCED"
            diagnostic_review_order = 3
        elif has_sos or has_spring:
            review_bucket = "SPRING_SOS_EVIDENCED"
            diagnostic_review_order = 4
        elif has_survival_risk and not support_flags and not has_distribution_caution:
            review_bucket = "SURVIVAL_AT_RISK_ONLY"
            diagnostic_review_order = 7
        elif has_distribution_caution and not support_flags:
            review_bucket = "DISTRIBUTION_OR_VSA_CAUTION"
            diagnostic_review_order = 8
        elif labels:
            review_bucket = "DOCTRINE_EVIDENCE_PRESENT"
            diagnostic_review_order = 5
        else:
            review_bucket = "LOW_INFORMATION"
            diagnostic_review_order = 9

        _inc(bucket_distribution, review_bucket)

        weis_gamma = _as_dict(evidence.get("weis_gamma"))
        ranking = _as_dict(weis_gamma.get("ranking"))
        fusion_state = _as_dict(weis_gamma.get("fusion")).get("fusion_state")
        gamma_status = _as_dict(weis_gamma.get("gamma_matrix")).get("status")
        existing_rank_bucket = ranking.get("rank_bucket")

        strong_doctrine = review_bucket in [
            "OPERATOR_WITH_SPRING_SOS_SUPPORT",
            "OPERATOR_ACCUMULATION_EVIDENCED",
        ]

        rank_high_context = existing_rank_bucket in ["A_PLUS", "A", "B"]
        rank_low_context = existing_rank_bucket in ["AVOID", "LOW_PRIORITY"]

        gamma_stale = fusion_state == "WEIS_ONLY_GAMMA_STALE"
        gamma_aligned = fusion_state == "WEIS_EXPANSION_GAMMA_NEUTRAL"
        gamma_unresolved = fusion_state == "WEIS_GAMMA_UNRESOLVED"
        gamma_downside_overlay = str(fusion_state or "").startswith("WEIS_DOWNSIDE")

        if conflicts_present:
            gamma_overlay_context = "CONFLICT_REVIEW_REQUIRED"
        elif strong_doctrine and gamma_aligned:
            gamma_overlay_context = "DOCTRINE_STRONG_GAMMA_ALIGNED"
        elif strong_doctrine and gamma_stale:
            gamma_overlay_context = "DOCTRINE_STRONG_GAMMA_STALE"
        elif strong_doctrine and gamma_unresolved:
            gamma_overlay_context = "DOCTRINE_STRONG_GAMMA_UNRESOLVED"
        elif strong_doctrine and gamma_downside_overlay:
            gamma_overlay_context = "DOCTRINE_STRONG_GAMMA_DOWNSIDE_OVERLAY"
        elif strong_doctrine:
            gamma_overlay_context = "DOCTRINE_STRONG_GAMMA_CONTEXT_OTHER"
        elif has_distribution_caution:
            gamma_overlay_context = "CAUTION_OR_DISTRIBUTION_REVIEW"
        elif gamma_stale:
            gamma_overlay_context = "GAMMA_STALE_DOCTRINE_PRESENT"
        else:
            gamma_overlay_context = "STANDARD_DOCTRINE_REVIEW"

        if rank_high_context:
            existing_rank_context = "EXISTING_RANK_HIGH_CONTEXT"
        elif rank_low_context:
            existing_rank_context = "EXISTING_RANK_LOW_CONTEXT"
        elif existing_rank_bucket:
            existing_rank_context = "EXISTING_RANK_OTHER_CONTEXT"
        else:
            existing_rank_context = "EXISTING_RANK_MISSING_CONTEXT"

        if conflicts_present:
            diagnostic_cross_context = "CONFLICTS_OVERRIDE_CROSS_CONTEXT"
        elif strong_doctrine and gamma_stale and rank_low_context:
            diagnostic_cross_context = "DOCTRINE_STRONG_WITH_STALE_GAMMA_AND_LOW_EXISTING_RANK"
        elif strong_doctrine and gamma_aligned and rank_high_context:
            diagnostic_cross_context = "DOCTRINE_STRONG_WITH_GAMMA_OVERLAY_AND_HIGH_EXISTING_RANK"
        elif strong_doctrine and gamma_unresolved:
            diagnostic_cross_context = "DOCTRINE_STRONG_WITH_UNRESOLVED_GAMMA_OVERLAY"
        elif strong_doctrine and rank_low_context:
            diagnostic_cross_context = "DOCTRINE_STRONG_WITH_LOW_EXISTING_RANK_CONTEXT"
        elif strong_doctrine:
            diagnostic_cross_context = "DOCTRINE_STRONG_GENERAL_REVIEW"
        elif has_distribution_caution:
            diagnostic_cross_context = "CAUTIONARY_DOCTRINE_CONTEXT"
        else:
            diagnostic_cross_context = "STANDARD_CROSS_CONTEXT"

        _inc(gamma_overlay_context_distribution, gamma_overlay_context)
        _inc(existing_rank_context_distribution, existing_rank_context)
        _inc(diagnostic_cross_context_distribution, diagnostic_cross_context)

        review_rows.append({
            **base_row,
            "engine": classifier.get("engine"),
            "classifier_version": classifier.get("version"),
            "classifier_status": classifier.get("status"),
            "diagnostic_review_bucket": review_bucket,
            "diagnostic_review_order": diagnostic_review_order,
            "support_flags": support_flags,
            "risk_flags": risk_flags,
            "doctrine_labels": labels,
            "overall_interpretation": classifier.get("overall_interpretation"),
            "conflicts_present": conflicts_present,
            "blocking_warnings": classifier.get("blocking_warnings") or [],
            "existing_rank_bucket": existing_rank_bucket,
            "existing_fusion_state": fusion_state,
            "existing_gamma_status": gamma_status,
            "gamma_overlay_context": gamma_overlay_context,
            "existing_rank_context": existing_rank_context,
            "diagnostic_cross_context": diagnostic_cross_context,
            "strong_doctrine": strong_doctrine,
            "rank_high_context": rank_high_context,
            "rank_low_context": rank_low_context,
            "gamma_stale": gamma_stale,
            "gamma_aligned": gamma_aligned,
            "gamma_unresolved": gamma_unresolved,
            "gamma_downside_overlay": gamma_downside_overlay,
            "diagnostic_only": True,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "state_transition_enabled": False,
        })

    review_rows = sorted(
        review_rows,
        key=lambda row: (
            int(row.get("diagnostic_review_order") or 99),
            str(row.get("symbol") or ""),
        ),
    )

    return {
        "engine": "EVIDENCE_DOCTRINE_REVIEW_RANKINGS",
        "version": "phase_d1_3_read_only_v1",
        "endpoint": "/api/campaign/evidence-doctrine-review-rankings",
        "read_only": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "total_campaigns": len(campaigns),
        "review_rows_count": len(review_rows),
        "missing_classifier_count": len(missing_classifier_rows),
        "bucket_distribution": dict(sorted(bucket_distribution.items())),
        "gamma_overlay_context_distribution": dict(sorted(gamma_overlay_context_distribution.items())),
        "existing_rank_context_distribution": dict(sorted(existing_rank_context_distribution.items())),
        "diagnostic_cross_context_distribution": dict(sorted(diagnostic_cross_context_distribution.items())),
        "support_flag_distribution": dict(sorted(support_flag_distribution.items())),
        "risk_flag_distribution": dict(sorted(risk_flag_distribution.items())),
        "label_distribution": dict(sorted(label_distribution.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "review_rows": review_rows,
        "missing_classifier_rows": missing_classifier_rows,
    }

@router.get("/evidence-doctrine-classifier-review")
def evidence_doctrine_classifier_review():
    """
    Phase C4 ? Doctrine classifier evidence review.

    Read-only diagnostic endpoint.

    This endpoint reviews evidence.doctrine_classifier payloads already stored
    on active campaigns.

    It does not:
    - score campaigns,
    - rank campaigns,
    - change campaign state,
    - enable transitions,
    - write to Supabase,
    - mutate evidence.
    """

    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)

    classifier_rows = []
    missing_classifier_rows = []
    sample_payloads = []
    label_distribution = {}
    status_counts = {}
    guardrail_failures = []

    expected_guardrails = {
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
    }

    for campaign in campaigns:
        evidence = _as_dict(campaign.get("evidence"))
        classifier = _as_dict(evidence.get("doctrine_classifier"))

        symbol = str(campaign.get("symbol") or "").upper()
        campaign_state = (
            campaign.get("campaign_state")
            or campaign.get("current_state")
            or campaign.get("state_enum")
            or campaign.get("state")
        )
        timeframe = (
            campaign.get("timeframe")
            or evidence.get("timeframe")
            or "DAILY"
        )

        base_row = {
            "symbol": symbol,
            "campaign_id": campaign.get("campaign_id"),
            "campaign_state": campaign_state,
            "timeframe": timeframe,
        }

        if not classifier:
            missing_classifier_rows.append({
                **base_row,
                "reason": "MISSING_DOCTRINE_CLASSIFIER",
            })
            continue

        labels = classifier.get("doctrine_labels") or []
        if not isinstance(labels, list):
            labels = [str(labels)]

        for label in labels:
            key = str(label or "UNKNOWN")
            label_distribution[key] = int(label_distribution.get(key, 0)) + 1

        status = str(classifier.get("status") or "MISSING_STATUS")
        status_counts[status] = int(status_counts.get(status, 0)) + 1

        failed_guardrails = []
        for key, expected in expected_guardrails.items():
            if classifier.get(key) != expected:
                failed_guardrails.append({
                    "field": key,
                    "expected": expected,
                    "actual": classifier.get(key),
                })

        if failed_guardrails:
            guardrail_failures.append({
                **base_row,
                "failed_guardrails": failed_guardrails,
            })

        conflict = _as_dict(classifier.get("conflict_interpretation"))
        evidence_refs = _as_dict(classifier.get("evidence_references"))

        row = {
            **base_row,
            "engine": classifier.get("engine"),
            "version": classifier.get("version"),
            "status": classifier.get("status"),
            "wired_into_evidence_builder": classifier.get("wired_into_evidence_builder"),
            "diagnostic_only": classifier.get("diagnostic_only"),
            "score_impact": classifier.get("score_impact"),
            "rank_impact": classifier.get("rank_impact"),
            "state_impact": classifier.get("state_impact"),
            "transition_impact": classifier.get("transition_impact"),
            "state_transition_enabled": classifier.get("state_transition_enabled"),
            "doctrine_labels": labels,
            "overall_interpretation": classifier.get("overall_interpretation"),
            "conflicts_present": conflict.get("conflicts_present"),
            "blocking_warnings": classifier.get("blocking_warnings") or [],
            "evidence_references": evidence_refs,
        }

        classifier_rows.append(row)

        if len(sample_payloads) < 10:
            sample_payloads.append({
                **base_row,
                "doctrine_classifier": classifier,
            })

    return {
        "engine": "EVIDENCE_DOCTRINE_CLASSIFIER_REVIEW",
        "version": "phase_c4_read_only_v1",
        "endpoint": "/api/campaign/evidence-doctrine-classifier-review",
        "read_only": True,
        "diagnostic_only": True,
        "score_impact": "NONE",
        "rank_impact": "NONE",
        "state_impact": "NONE",
        "transition_impact": "NONE",
        "state_transition_enabled": False,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "total_campaigns": len(campaigns),
        "with_classifier_count": len(classifier_rows),
        "missing_classifier_count": len(missing_classifier_rows),
        "label_distribution": dict(sorted(label_distribution.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "classifier_rows": classifier_rows,
        "missing_classifier_rows": missing_classifier_rows,
        "sample_payloads": sample_payloads,
    }

@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": "campaign_api",
    }


@router.get("/active")
def active_campaigns():
    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)
    return {"campaigns": campaigns}


@router.get("/rankings")
def rankings():
    campaigns = _store().get_top_campaigns(limit=100)
    campaigns = _attach_weis_gamma_summaries(campaigns)

    ranked = sorted(
        campaigns,
        key=lambda x: float(
            x.get("operator_dominance")
            or x.get("outcome_quality_score")
            or x.get("obstacle_score")
            or 0
        ),
        reverse=True,
    )

    return {"campaigns": ranked}


@router.get("/status")
def status():
    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)

    def state(c):
        return str(c.get("current_state") or c.get("state_enum") or "").upper()

    weis_gamma_present = sum(
        1 for c in campaigns if c.get("weis_gamma_present") is True
    )

    weis_gamma_missing = sum(
        1 for c in campaigns if c.get("weis_gamma_present") is not True
    )

    weis_gamma_transition_enabled = sum(
        1 for c in campaigns if c.get("weis_gamma_transition_enabled") is True
    )

    gamma_ok = sum(
        1
        for c in campaigns
        if c.get("weis_gamma_effective_gamma_status") == "OK"
    )

    gamma_no_options_returned = sum(
        1
        for c in campaigns
        if c.get("weis_gamma_option_chain_status") == "NO_OPTIONS_RETURNED"
    )

    gamma_no_option_chain = sum(
        1
        for c in campaigns
        if (
            c.get("weis_gamma_gamma_status") == "NO_OPTION_CHAIN_INPUT"
            and c.get("weis_gamma_option_chain_status") != "NO_OPTIONS_RETURNED"
        )
    )

    gamma_stale_or_unconfirmed = sum(
        1
        for c in campaigns
        if (
            c.get("weis_gamma_present") is True
            and c.get("weis_gamma_option_chain_status") != "NO_OPTIONS_RETURNED"
            and (
                c.get("weis_gamma_phase") == "WEIS_ONLY_GAMMA_STALE"
                or c.get("weis_gamma_fusion_state") == "WEIS_ONLY_GAMMA_STALE"
                or c.get("weis_gamma_gamma_status") in {
                    "NO_OPTION_CHAIN_INPUT",
                    "NO_GAMMA_INPUT",
                    "NOT_PRESENT",
                    None,
                }
                or c.get("weis_gamma_gamma_fresh") is False
            )
        )
    )

    return {
        "active_campaigns": len(campaigns),
        "birth_candidates": sum(1 for c in campaigns if state(c) == "BIRTH"),
        "expanding_campaigns": sum(1 for c in campaigns if state(c) == "EXPANDING"),
        "distribution_risk": sum(
            1 for c in campaigns if state(c) == "DISTRIBUTION_RISK"
        ),
        "weis_gamma_status_center": {
            "api_fields_enabled": True,
            "total_campaigns": len(campaigns),
            "weis_gamma_present": weis_gamma_present,
            "weis_gamma_missing": weis_gamma_missing,
            "transition_enabled": weis_gamma_transition_enabled,
            "transition_enabled_expected": False,
            "gamma_ok": gamma_ok,
            "gamma_no_options_returned": gamma_no_options_returned,
            "gamma_no_option_chain": gamma_no_option_chain,
            "gamma_stale_or_unconfirmed": gamma_stale_or_unconfirmed,
            "phase_counts": _count_by_field(campaigns, "weis_gamma_phase"),
            "rank_bucket_counts": _count_by_field(campaigns, "weis_gamma_rank_bucket"),
            "gamma_status_counts": _count_by_field(campaigns, "weis_gamma_effective_gamma_status"),
            "raw_gamma_status_counts": _count_by_field(campaigns, "weis_gamma_gamma_status"),
            "option_chain_status_counts": _count_by_field(campaigns, "weis_gamma_option_chain_status"),
            "fusion_state_counts": _count_by_field(campaigns, "weis_gamma_effective_fusion_state"),
            "raw_fusion_state_counts": _count_by_field(campaigns, "weis_gamma_fusion_state"),
        },
        "evidence_diagnostics_status_center": {
            "api_fields_enabled": True,
            "diagnostic_only": True,
            "transition_enabled": 0,
            "transition_enabled_expected": False,
            "total_campaigns": len(campaigns),
            "evidence_presence_counts": _evidence_presence_counts(campaigns),
            "bar_depth_tier_counts": _count_nested_evidence_field(
                campaigns,
                "bar_depth",
                "depth_tier",
            ),
            "bar_depth_max_state_counts": _count_nested_evidence_field(
                campaigns,
                "bar_depth",
                "max_campaign_state",
            ),
            "bar_depth_diagnostic_key_counts": _count_nested_evidence_field(
                campaigns,
                "bar_depth",
                "diagnostic_key",
            ),
            "legacy_operator_control_evidence_counts": _count_nested_bool(
                campaigns,
                "operator_control",
                "operator_control_confirmed",
            ),
            "operator_control_verdict_counts": _count_nested_evidence_field(
                campaigns,
                "operator_control",
                "verdict",
            ),
            "operator_control_evidence_count_counts": _count_nested_evidence_field(
                campaigns,
                "operator_control",
                "evidence_count",
            ),
            "transition_readiness_verdict_counts": _count_nested_evidence_field(
                campaigns,
                "transition_readiness",
                "readiness_verdict",
            ),
            "transition_supported_state_counts": _count_nested_evidence_field(
                campaigns,
                "transition_readiness",
                "evidence_supported_state",
            ),
            "transition_state_transition_enabled_counts": _count_nested_bool(
                campaigns,
                "transition_readiness",
                "state_transition_enabled",
            ),
            "raw_metric_transition_readiness_verdict_counts": _count_raw_metric_field(
                campaigns,
                "transition_readiness_verdict",
            ),
            "raw_metric_legacy_operator_control_evidence_counts": _count_raw_metric_field(
                campaigns,
                "operator_control_confirmed",
            ),
        },
    }


@router.post("/register")
def register_campaign(campaign: Dict[str, Any]):
    saved = _store().save_campaign(campaign)
    return {
        "status": "registered",
        "result": saved,
    }

@router.get("/external-macro-anchor-enrichment-review")
def external_macro_anchor_enrichment_review():
    """
    D3C.2B read-only external macro-anchor enrichment review.

    Hardened endpoint:
    - returns diagnostic JSON instead of opaque 500 errors
    - does not write to Supabase
    - does not mutate campaigns
    - does not confirm operator control
    - does not affect score, rank, state, transition, gamma, probability,
      expected return, edge, target, or historical outcome fields
    """
    from collections import Counter
    import traceback

    def _safe_counter(counter):
        try:
            return _counter_to_dict(counter)
        except Exception:
            return dict(sorted(counter.items()))

    def _base_payload():
        return {
            "endpoint": "/api/campaign/external-macro-anchor-enrichment-review",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
            "old_pivot_gate_policy": "OLD_PIVOTS_BLOCKED_UNLESS_TOUCH_AND_CLOSE_REJECTION_VALIDATED",
        }

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "engine": "D3C2B_EXTERNAL_MACRO_ANCHOR_ENRICHMENT_ENDPOINT",
            "version": "phase_d3c2b_external_macro_anchor_enrichment_read_only_v1",
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": stage,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-10:],
            "total_campaigns": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "guardrail_failures": [],
            "row_errors": [],
            "macro_anchor_status_distribution": {},
            "macro_anchor_validated_count_distribution": {},
            "gate_reason_distribution": {},
            "rows": [],
        })
        return payload

    try:
        try:
            from backend.campaign_engine.external_macro_anchor_enrichment_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                evaluate_external_macro_anchor,
            )
        except Exception:
            from campaign_engine.external_macro_anchor_enrichment_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                evaluate_external_macro_anchor,
            )
    except Exception as exc:
        return _error_payload("IMPORT_ENGINE", exc)

    try:
        campaigns = _store().get_active_campaigns()
    except Exception as exc:
        return _error_payload("LOAD_ACTIVE_CAMPAIGNS", exc)

    status_counter = Counter()
    validated_counter = Counter()
    gate_counter = Counter()
    guardrail_failures = []
    row_errors = []
    rows = []

    for campaign in campaigns:
        try:
            row = evaluate_external_macro_anchor(campaign)
        except Exception as exc:
            symbol = campaign.get("symbol") if isinstance(campaign, dict) else getattr(campaign, "symbol", None)
            campaign_id = campaign.get("campaign_id") if isinstance(campaign, dict) else getattr(campaign, "campaign_id", None)

            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,
                "symbol": symbol,
                "campaign_id": campaign_id,
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,
                "macro_anchor_status": "ROW_EVALUATION_ERROR",
                "macro_anchor_validated_count": 0,
                "old_pivot_gate_policy": "OLD_PIVOTS_BLOCKED_UNLESS_TOUCH_AND_CLOSE_REJECTION_VALIDATED",
                "usable_bar_count": 0,
                "macro_support": {},
                "macro_resistance": {},
                "gate_reasons": ["ROW_EVALUATION_ERROR"],
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }

            row_errors.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })

        rows.append(row)

        status_counter[str(row.get("macro_anchor_status"))] += 1
        validated_counter[str(row.get("macro_anchor_validated_count"))] += 1

        for reason in row.get("gate_reasons") or []:
            gate_counter[str(reason)] += 1

        guardrail_ok = bool(
            row.get("diagnostic_only") is True
            and row.get("read_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("operator_control_confirmation_impact") == "NONE"
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("state_transition_enabled") is False
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": row.get("symbol"),
                "campaign_id": row.get("campaign_id"),
                "reason": "D3C.2B guardrail failure",
            })

    rows = sorted(
        rows,
        key=lambda row: (
            -int(row.get("macro_anchor_validated_count") or 0),
            str(row.get("macro_anchor_status") or ""),
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint_status": "OK" if not row_errors else "ROW_ERRORS_RETURNED_NO_MUTATION",
        "total_campaigns": len(campaigns),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "macro_anchor_status_distribution": _safe_counter(status_counter),
        "macro_anchor_validated_count_distribution": _safe_counter(validated_counter),
        "gate_reason_distribution": _safe_counter(gate_counter),
        "rows": rows,
    })
    return payload
@router.get("/external-macro-anchor-quality-tier-review")
def external_macro_anchor_quality_tier_review():
    """
    D3C.2C read-only macro-anchor quality-tier review.

    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT change scores, ranks, states, transitions, gamma,
    probability, expected return, edge, targets, or historical outcomes.
    This endpoint is not a trade signal.
    """
    from collections import Counter
    import traceback

    def _safe_counter(counter):
        try:
            return _counter_to_dict(counter)
        except Exception:
            return dict(sorted(counter.items()))

    def _base_payload():
        return {
            "endpoint": "/api/campaign/external-macro-anchor-quality-tier-review",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
        }

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "engine": "D3C2C_EXTERNAL_MACRO_ANCHOR_QUALITY_TIER_ENDPOINT",
            "version": "phase_d3c2c_external_macro_anchor_quality_tier_read_only_v1",
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": stage,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-10:],
            "total_campaigns": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "rows": [],
            "row_errors": [],
            "guardrail_failures": [],
            "quality_tier_distribution": {},
            "current_location_relevance_distribution": {},
            "d3c2b_status_distribution": {},
            "caution_flag_distribution": {},
        })
        return payload

    try:
        try:
            from backend.campaign_engine.external_macro_anchor_quality_tier_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_quality,
            )
        except Exception:
            from campaign_engine.external_macro_anchor_quality_tier_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_quality,
            )
    except Exception as exc:
        return _error_payload("IMPORT_ENGINE", exc)

    try:
        campaigns = _store().get_active_campaigns()
    except Exception as exc:
        return _error_payload("LOAD_ACTIVE_CAMPAIGNS", exc)

    tier_counter = Counter()
    relevance_counter = Counter()
    d3c2b_status_counter = Counter()
    caution_counter = Counter()
    guardrail_failures = []
    row_errors = []
    rows = []

    for campaign in campaigns:
        try:
            row = classify_macro_anchor_quality(campaign)
        except Exception as exc:
            symbol = campaign.get("symbol") if isinstance(campaign, dict) else getattr(campaign, "symbol", None)
            campaign_id = campaign.get("campaign_id") if isinstance(campaign, dict) else getattr(campaign, "campaign_id", None)
            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,
                "symbol": symbol,
                "campaign_id": campaign_id,
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,
                "macro_anchor_quality_tier": "ROW_EVALUATION_ERROR",
                "current_location_relevance": "ROW_EVALUATION_ERROR",
                "d3c2b_macro_anchor_status": "ROW_EVALUATION_ERROR",
                "caution_flags": ["ROW_EVALUATION_ERROR"],
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            row_errors.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })

        rows.append(row)

        tier_counter[str(row.get("macro_anchor_quality_tier"))] += 1
        relevance_counter[str(row.get("current_location_relevance"))] += 1
        d3c2b_status_counter[str(row.get("d3c2b_macro_anchor_status"))] += 1

        for flag in row.get("caution_flags") or []:
            caution_counter[str(flag)] += 1

        guardrail_ok = bool(
            row.get("diagnostic_only") is True
            and row.get("read_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("operator_control_confirmation_impact") == "NONE"
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("state_transition_enabled") is False
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": row.get("symbol"),
                "campaign_id": row.get("campaign_id"),
                "reason": "D3C.2C guardrail failure",
            })

    rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("macro_anchor_quality_tier") or ""),
            str(row.get("current_location_relevance") or ""),
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint_status": "OK" if not row_errors else "ROW_ERRORS_RETURNED_NO_MUTATION",
        "total_campaigns": len(campaigns),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "quality_tier_distribution": _safe_counter(tier_counter),
        "current_location_relevance_distribution": _safe_counter(relevance_counter),
        "d3c2b_status_distribution": _safe_counter(d3c2b_status_counter),
        "caution_flag_distribution": _safe_counter(caution_counter),
        "rows": rows,
    })
    return payload

@router.get("/macro-anchor-state-alignment-review")
def macro_anchor_state_alignment_review():
    """
    D3C.2D read-only macro-anchor state alignment review.

    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT change scores, ranks, states, transitions, gamma,
    probability, expected return, edge, targets, or historical outcomes.
    This endpoint is not a trade signal.
    """
    from collections import Counter
    import traceback

    def _safe_counter(counter):
        try:
            return _counter_to_dict(counter)
        except Exception:
            return dict(sorted(counter.items()))

    def _base_payload():
        return {
            "endpoint": "/api/campaign/macro-anchor-state-alignment-review",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
        }

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "engine": "D3C2D_MACRO_ANCHOR_STATE_ALIGNMENT_ENDPOINT",
            "version": "phase_d3c2d_macro_anchor_state_alignment_read_only_v1",
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": stage,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-10:],
            "total_campaigns": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "rows": [],
            "row_errors": [],
            "guardrail_failures": [],
            "state_macro_alignment_distribution": {},
            "quality_tier_by_state_distribution": {},
            "location_relevance_by_state_distribution": {},
            "alignment_flag_distribution": {},
            "caution_flag_distribution": {},
        })
        return payload

    try:
        try:
            from backend.campaign_engine.external_macro_anchor_state_alignment_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_state_alignment,
            )
        except Exception:
            from campaign_engine.external_macro_anchor_state_alignment_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_state_alignment,
            )
    except Exception as exc:
        return _error_payload("IMPORT_ENGINE", exc)

    try:
        campaigns = _store().get_active_campaigns()
    except Exception as exc:
        return _error_payload("LOAD_ACTIVE_CAMPAIGNS", exc)

    alignment_counter = Counter()
    quality_state_counter = Counter()
    relevance_state_counter = Counter()
    alignment_flag_counter = Counter()
    caution_flag_counter = Counter()
    guardrail_failures = []
    row_errors = []
    rows = []

    for campaign in campaigns:
        try:
            row = classify_macro_anchor_state_alignment(campaign)
        except Exception as exc:
            symbol = campaign.get("symbol") if isinstance(campaign, dict) else getattr(campaign, "symbol", None)
            campaign_id = campaign.get("campaign_id") if isinstance(campaign, dict) else getattr(campaign, "campaign_id", None)
            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,
                "symbol": symbol,
                "campaign_id": campaign_id,
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,
                "state_macro_alignment_class": "ROW_EVALUATION_ERROR",
                "macro_anchor_quality_tier": "ROW_EVALUATION_ERROR",
                "current_location_relevance": "ROW_EVALUATION_ERROR",
                "alignment_flags": ["ROW_EVALUATION_ERROR"],
                "caution_flags": ["ROW_EVALUATION_ERROR"],
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            row_errors.append({
                "symbol": symbol,
                "campaign_id": campaign_id,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })

        rows.append(row)

        campaign_state = str(row.get("campaign_state") or "UNKNOWN_STATE")
        alignment_counter[str(row.get("state_macro_alignment_class"))] += 1
        quality_state_counter[str(row.get("macro_anchor_quality_tier")) + " | " + campaign_state] += 1
        relevance_state_counter[str(row.get("current_location_relevance")) + " | " + campaign_state] += 1

        for flag in row.get("alignment_flags") or []:
            alignment_flag_counter[str(flag)] += 1

        for flag in row.get("caution_flags") or []:
            caution_flag_counter[str(flag)] += 1

        guardrail_ok = bool(
            row.get("diagnostic_only") is True
            and row.get("read_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("operator_control_confirmation_impact") == "NONE"
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("state_transition_enabled") is False
            and row.get("not_a_trade_signal") is True
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": row.get("symbol"),
                "campaign_id": row.get("campaign_id"),
                "reason": "D3C.2D guardrail failure",
            })

    rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("state_macro_alignment_class") or ""),
            str(row.get("campaign_state") or ""),
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint_status": "OK" if not row_errors else "ROW_ERRORS_RETURNED_NO_MUTATION",
        "total_campaigns": len(campaigns),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "state_macro_alignment_distribution": _safe_counter(alignment_counter),
        "quality_tier_by_state_distribution": _safe_counter(quality_state_counter),
        "location_relevance_by_state_distribution": _safe_counter(relevance_state_counter),
        "alignment_flag_distribution": _safe_counter(alignment_flag_counter),
        "caution_flag_distribution": _safe_counter(caution_flag_counter),
        "rows": rows,
    })
    return payload
