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
            not bool(row.get("operator_control_confirmed")),
            -(int(row.get("operator_control_evidence_count") or 0)),
            str(row.get("symbol") or ""),
        )
    )

    operator_confirmed_rows = [
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
        "operator_control_confirmed_count": len(operator_confirmed_rows),
        "full_depth_campaigns": full_depth_rows,
        "operator_control_confirmed_campaigns": operator_confirmed_rows,
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

    operator_confirmed = bool(row.get("operator_control_confirmed"))
    operator_evidence_count = int(row.get("operator_control_evidence_count") or 0)

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

    if operator_confirmed:
        score += 40.0
        reasons.append("operator control confirmed from raw OHLCV tape behavior")
    else:
        reasons.append("operator control not confirmed")

    score += min(operator_evidence_count, 5) * 5.0
    if operator_evidence_count:
        reasons.append(f"operator evidence count {operator_evidence_count}")

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
    elif operator_confirmed and gamma_fresh and readiness == "FULL_CAMPAIGN_READY_DIAGNOSTIC" and score >= 85:
        tier = "A_DIAGNOSTIC"
    elif operator_confirmed and not gamma_fresh:
        tier = "GAMMA_REFRESH_REQUIRED_DIAGNOSTIC"
    elif operator_confirmed:
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
        "operator_control_confirmed_count": base.get("operator_control_confirmed_count"),
        "ranked_diagnostic_campaigns": ranked_rows,
        "operator_control_confirmed_ranked": [
            row for row in ranked_rows
            if row.get("operator_control_confirmed") is True
        ],
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

    operator_confirmed = bool(match.get("operator_control_confirmed"))
    transition_enabled = bool(match.get("state_transition_enabled"))
    gamma_fresh = bool(weis_gamma_phase.get("gamma_data_fresh"))

    operator_summary = "Operator control is evidenced from raw OHLCV tape behavior." if operator_confirmed else "Operator control is not confirmed by the current raw OHLCV evidence threshold."

    if "PHASE_PERMISSION_BLOCKED" in conflict_flags:
        campaign_explanation = "Diagnostic conflict: operator/control evidence exists or partial evidence exists, but Weis/Gamma phase permission is blocked."
    elif "DOWNSIDE_WEIS_GAMMA_DIRECTION" in conflict_flags:
        campaign_explanation = "Diagnostic conflict: Weis/Gamma directional evidence is downside or non-confirmatory."
    elif operator_confirmed and gamma_fresh:
        campaign_explanation = "Diagnostic alignment: operator control is confirmed and Gamma is fresh."
    elif operator_confirmed and not gamma_fresh:
        campaign_explanation = "Operator control is confirmed, but Gamma refresh is required before stronger confirmation."
    elif match.get("transition_readiness_verdict") == "CONFIRMATION_READY_DIAGNOSTIC":
        campaign_explanation = "Watchlist diagnostic: confirmation evidence exists, but operator control is not confirmed."
    else:
        campaign_explanation = "Lower-priority diagnostic: full-depth data exists, but confirmation is incomplete."

    failed_or_missing_items = []

    if not operator_confirmed:
        failed_or_missing_items.append("operator_control_confirmed")
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
            "confirmed": operator_confirmed,
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
    operator_rows = list(ranking_payload.get("operator_control_confirmed_ranked") or [])
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
            "operator_control_confirmed": row.get("operator_control_confirmed"),
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
            "operator_control_confirmed_count": ranking_payload.get("operator_control_confirmed_count"),
            "aligned_a_diagnostic_count": len(aligned_a_rows),
            "gamma_refresh_needed_count": len(gamma_refresh_rows),
            "conflicted_count": len(conflicted_rows),
            "conflict_blocked_count": len(blocked_rows),
        },
        "diagnostic_tier_counts": tier_counts,
        "symbol_digest": symbol_digest,
        "aligned_a_diagnostic_campaigns": aligned_a_rows,
        "operator_control_confirmed_campaigns": operator_rows,
        "gamma_refresh_needed_campaigns": gamma_refresh_rows,
        "conflict_blocked_campaigns": blocked_rows,
        "conflicted_campaigns": conflicted_rows,
        "summary_payload": summary_payload,
        "diagnostics_payload": diagnostics_payload,
        "ranking_payload": ranking_payload,
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
            "operator_control_confirmed_counts": _count_nested_bool(
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
            "raw_metric_operator_control_confirmed_counts": _count_raw_metric_field(
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