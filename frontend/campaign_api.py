from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.parse
import ssl
import os
import json
import math
import threading
from fastapi import APIRouter
from typing import Any, Dict, List

from backend.campaign_engine.campaign_store import CampaignStore

router = APIRouter(
    prefix="/api/campaign",
    tags=["campaign"],
)


# FIX (2026-07-27): _store() used to create a brand new CampaignStore()
# (and therefore a brand new Supabase client/connection) on EVERY single
# call -- 24 separate call sites in this file alone, meaning every API
# request opened its own fresh database connection instead of reusing
# one. Confirmed via real production evidence: the underlying SQL query
# itself executes in under 1ms, but /api/campaigns/active and
# /api/campaigns/summary were taking ~16-20 seconds end-to-end, and
# pg_stat_activity showed exactly 15/15 connections in use (the Micro
# compute tier's pool limit) -- classic connection pool exhaustion from
# constantly creating new clients instead of reusing one.
#
# This makes _store() a thread-safe singleton: the real CampaignStore
# (and its one underlying Supabase client) is created once per backend
# worker process and reused for every subsequent call, exactly like the
# fix already proven for frontend/shared_cache.py's coordination pattern
# earlier tonight. Tested with 20 concurrent threads producing exactly
# one instance before this was applied to the real file.
_store_instance = None
_store_lock = threading.Lock()


def _store():
    global _store_instance
    if _store_instance is not None:
        return _store_instance
    with _store_lock:
        if _store_instance is None:
            _store_instance = CampaignStore()
        return _store_instance


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

@router.get("/macro-anchor-decision-zone-review")
def macro_anchor_decision_zone_review():
    """
    D3C.2E read-only macro-anchor decision-zone review.

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
            "endpoint": "/api/campaign/macro-anchor-decision-zone-review",
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
            "engine": "D3C2E_MACRO_ANCHOR_DECISION_ZONE_ENDPOINT",
            "version": "phase_d3c2e_macro_anchor_decision_zone_read_only_v1",
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
            "decision_zone_status_distribution": {},
            "decision_zone_class_distribution": {},
            "decision_zone_by_state_distribution": {},
            "decision_zone_by_quality_tier_distribution": {},
            "decision_zone_flag_distribution": {},
            "caution_flag_distribution": {},
        })
        return payload

    try:
        try:
            from backend.campaign_engine.macro_anchor_decision_zone_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_decision_zone,
            )
        except Exception:
            from campaign_engine.macro_anchor_decision_zone_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_decision_zone,
            )
    except Exception as exc:
        return _error_payload("IMPORT_ENGINE", exc)

    try:
        campaigns = _store().get_active_campaigns()
    except Exception as exc:
        return _error_payload("LOAD_ACTIVE_CAMPAIGNS", exc)

    status_counter = Counter()
    class_counter = Counter()
    state_counter = Counter()
    quality_counter = Counter()
    decision_flag_counter = Counter()
    caution_flag_counter = Counter()
    guardrail_failures = []
    row_errors = []
    rows = []

    for campaign in campaigns:
        try:
            row = classify_macro_anchor_decision_zone(campaign)
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
                "decision_zone_status": "ROW_EVALUATION_ERROR",
                "decision_zone_class": "ROW_EVALUATION_ERROR",
                "decision_zone_flags": ["ROW_EVALUATION_ERROR"],
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
        quality_tier = str(row.get("macro_anchor_quality_tier") or "UNKNOWN_QUALITY_TIER")

        status_counter[str(row.get("decision_zone_status"))] += 1
        class_counter[str(row.get("decision_zone_class"))] += 1
        state_counter[str(row.get("decision_zone_class")) + " | " + campaign_state] += 1
        quality_counter[str(row.get("decision_zone_class")) + " | " + quality_tier] += 1

        for flag in row.get("decision_zone_flags") or []:
            decision_flag_counter[str(flag)] += 1

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
                "reason": "D3C.2E guardrail failure",
            })

    rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("decision_zone_status") or ""),
            str(row.get("decision_zone_class") or ""),
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
        "decision_zone_status_distribution": _safe_counter(status_counter),
        "decision_zone_class_distribution": _safe_counter(class_counter),
        "decision_zone_by_state_distribution": _safe_counter(state_counter),
        "decision_zone_by_quality_tier_distribution": _safe_counter(quality_counter),
        "decision_zone_flag_distribution": _safe_counter(decision_flag_counter),
        "caution_flag_distribution": _safe_counter(caution_flag_counter),
        "rows": rows,
    })
    return payload

@router.get("/macro-anchor-behavioral-resolution-confluence-review")
def macro_anchor_behavioral_resolution_confluence_review():
    """
    D3C.2F read-only D3C.2E / D3J confluence review.

    This endpoint uses D3C.2E decision-zone rows and D3J plausibility rows.

    This endpoint does NOT write to Supabase.
    This endpoint does NOT mutate campaigns.
    This endpoint does NOT confirm operator control.
    This endpoint does NOT unconfirm operator control.
    This endpoint does NOT execute D3D.
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
            "endpoint": "/api/campaign/macro-anchor-behavioral-resolution-confluence-review",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_unconfirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "d3d_execution_allowed": False,
            "d3d_source_used_by_this_engine": False,
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
            "engine": "D3C2F_MACRO_ANCHOR_BEHAVIORAL_RESOLUTION_CONFLUENCE_ENDPOINT",
            "version": "phase_d3c2f_macro_anchor_behavioral_resolution_confluence_read_only_v1",
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
            "behavioral_resolution_confluence_distribution": {},
            "confluence_priority_distribution": {},
            "behavioral_resolution_requirement_distribution": {},
            "decision_zone_by_d3j_plausibility_distribution": {},
            "d3j_plausibility_by_decision_zone_distribution": {},
            "d3c2f_no_drift_status_distribution": {},
            "confluence_flag_distribution": {},
            "caution_flag_distribution": {},
        })
        return payload

    def _key(row):
        return str(row.get("campaign_id")) + "|" + str(row.get("symbol"))

    try:
        try:
            from backend.campaign_engine.macro_anchor_behavioral_resolution_confluence_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_behavioral_resolution_confluence,
            )
        except Exception:
            from campaign_engine.macro_anchor_behavioral_resolution_confluence_engine import (
                ENGINE_NAME,
                ENGINE_VERSION,
                classify_macro_anchor_behavioral_resolution_confluence,
            )
    except Exception as exc:
        return _error_payload("IMPORT_ENGINE", exc)

    try:
        decision_payload = macro_anchor_decision_zone_review()
    except Exception as exc:
        return _error_payload("LOAD_D3C2E_DECISION_ZONE_PAYLOAD", exc)

    try:
        d3j_payload = operator_control_plausibility_status_review()
    except Exception as exc:
        return _error_payload("LOAD_D3J_PLAUSIBILITY_PAYLOAD", exc)

    decision_rows = decision_payload.get("rows") or []
    d3j_rows = d3j_payload.get("rows") or []

    d3j_by_key = {_key(row): row for row in d3j_rows}

    confluence_counter = Counter()
    priority_counter = Counter()
    requirement_counter = Counter()
    decision_by_plausibility_counter = Counter()
    plausibility_by_decision_counter = Counter()
    no_drift_counter = Counter()
    confluence_flag_counter = Counter()
    caution_flag_counter = Counter()
    guardrail_failures = []
    row_errors = []
    rows = []

    for decision_row in decision_rows:
        try:
            d3j_row = d3j_by_key.get(_key(decision_row), {})
            row = classify_macro_anchor_behavioral_resolution_confluence(decision_row, d3j_row)
        except Exception as exc:
            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,
                "symbol": decision_row.get("symbol"),
                "campaign_id": decision_row.get("campaign_id"),
                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_unconfirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "d3d_execution_allowed": False,
                "d3d_source_used_by_this_engine": False,
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,
                "behavioral_resolution_confluence_status": "ROW_EVALUATION_ERROR",
                "confluence_priority": "ROW_EVALUATION_ERROR",
                "behavioral_resolution_requirement": "ROW_EVALUATION_ERROR",
                "d3c2f_no_drift_status": "ROW_EVALUATION_ERROR",
                "confluence_flags": ["ROW_EVALUATION_ERROR"],
                "caution_flags": ["ROW_EVALUATION_ERROR"],
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            row_errors.append({
                "symbol": decision_row.get("symbol"),
                "campaign_id": decision_row.get("campaign_id"),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            })

        rows.append(row)

        confluence_counter[str(row.get("behavioral_resolution_confluence_status"))] += 1
        priority_counter[str(row.get("confluence_priority"))] += 1
        requirement_counter[str(row.get("behavioral_resolution_requirement"))] += 1
        no_drift_counter[str(row.get("d3c2f_no_drift_status"))] += 1

        decision_by_plausibility_counter[
            str(row.get("decision_zone_class")) + " | " + str(row.get("d3j_plausibility_status"))
        ] += 1

        plausibility_by_decision_counter[
            str(row.get("d3j_plausibility_status")) + " | " + str(row.get("decision_zone_class"))
        ] += 1

        for flag in row.get("confluence_flags") or []:
            confluence_flag_counter[str(flag)] += 1

        for flag in row.get("caution_flags") or []:
            caution_flag_counter[str(flag)] += 1

        guardrail_ok = bool(
            row.get("diagnostic_only") is True
            and row.get("read_only") is True
            and row.get("writes_to_supabase") is False
            and row.get("mutates_campaigns") is False
            and row.get("production_confirmation_allowed") is False
            and row.get("operator_control_confirmed_by_this_engine") is False
            and row.get("operator_control_unconfirmed_by_this_engine") is False
            and row.get("operator_control_confirmation_impact") == "NONE"
            and row.get("d3d_execution_allowed") is False
            and row.get("d3d_source_used_by_this_engine") is False
            and row.get("score_impact") == "NONE"
            and row.get("rank_impact") == "NONE"
            and row.get("state_impact") == "NONE"
            and row.get("transition_impact") == "NONE"
            and row.get("gamma_confirmation_impact") == "NONE"
            and row.get("state_transition_enabled") is False
            and row.get("not_a_trade_signal") is True
            and row.get("d3c2f_no_drift_status") == "PASS"
        )

        if not guardrail_ok:
            guardrail_failures.append({
                "symbol": row.get("symbol"),
                "campaign_id": row.get("campaign_id"),
                "reason": "D3C.2F guardrail failure",
                "d3c2f_no_drift_status": row.get("d3c2f_no_drift_status"),
            })

    rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("confluence_priority") or ""),
            str(row.get("behavioral_resolution_confluence_status") or ""),
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint_status": "OK" if not row_errors else "ROW_ERRORS_RETURNED_NO_MUTATION",
        "upstream_sources": [
            "D3C.2E:/api/campaign/macro-anchor-decision-zone-review",
            "D3J:/api/campaign/operator-control-plausibility-status-review",
        ],
        "total_campaigns": len(rows),
        "d3c2e_rows_count": len(decision_rows),
        "d3j_rows_count": len(d3j_rows),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "behavioral_resolution_confluence_distribution": _safe_counter(confluence_counter),
        "confluence_priority_distribution": _safe_counter(priority_counter),
        "behavioral_resolution_requirement_distribution": _safe_counter(requirement_counter),
        "decision_zone_by_d3j_plausibility_distribution": _safe_counter(decision_by_plausibility_counter),
        "d3j_plausibility_by_decision_zone_distribution": _safe_counter(plausibility_by_decision_counter),
        "d3c2f_no_drift_status_distribution": _safe_counter(no_drift_counter),
        "confluence_flag_distribution": _safe_counter(confluence_flag_counter),
        "caution_flag_distribution": _safe_counter(caution_flag_counter),
        "rows": rows,
    })
    return payload

@router.get("/macro-anchor-high-priority-resolution-evidence-review")
def macro_anchor_high_priority_resolution_evidence_review():
    """
    D3C.2O repair of D3C.2G.

    Purpose:
    - Keep D3C.2G read-only and diagnostic-only.
    - Preserve D3J as plausibility context.
    - Use D3C Wyckoff / Weis review_rows as the true source for:
      demand/support validation,
      supply/exhaustion validation,
      contrary/failure presence,
      SML presence and SML evidence quality.

    No-drift rule:
    This endpoint does not confirm operator control, does not execute D3D,
    does not mutate Supabase, and does not affect score/rank/state/transition/gamma/trade signal.
    """
    from collections import Counter

    ENGINE_NAME = "D3C2G_HIGH_PRIORITY_BEHAVIORAL_RESOLUTION_EVIDENCE"
    ENGINE_VERSION = "phase_d3c2o_d3c2g_d3c_source_bridge_repair_read_only_v1"

    def _base_payload():
        return {
            "endpoint": "/api/campaign/macro-anchor-high-priority-resolution-evidence-review",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_unconfirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "d3d_execution_allowed": False,
            "d3d_source_used_by_this_engine": False,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
            "d3c_source_bridge_policy": "D3C_REVIEW_ROWS_ARE_TRUE_BEHAVIORAL_RESOLUTION_SOURCE_READ_ONLY",
            "d3j_source_policy": "D3J_RETAINED_AS_PLAUSIBILITY_CONTEXT_NOT_BEHAVIORAL_FIELD_SOURCE",
            "explicit_sml_policy": "EXPLICIT_SML_TRUE_ONLY_WHEN_D3C_SML_EVIDENCE_QUALITY_EQUALS_EXPLICIT_GEOMETRY",
            "production_confirmation_policy": "D3C2G_NEVER_CONFIRMS_OPERATOR_CONTROL_D3D_ONLY",
        }

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "engine": ENGINE_NAME + "_ENDPOINT",
            "version": ENGINE_VERSION,
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": str(stage),
            "error": str(exc),
            "total_campaigns": 0,
            "d3c2f_rows_count": 0,
            "d3c_rows_count": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 1,
            "guardrail_failures": [],
            "row_errors": [{"stage": str(stage), "error": str(exc)}],
            "rows": [],
        })
        return payload

    def _rows_from_payload(payload):
        if not isinstance(payload, dict):
            return []
        rows = payload.get("rows")
        if isinstance(rows, list):
            return rows
        review_rows = payload.get("review_rows")
        if isinstance(review_rows, list):
            return review_rows
        return []

    def _safe_counter(counter):
        return dict(sorted(counter.items(), key=lambda item: str(item[0])))

    def _get(row, key, default=None):
        if isinstance(row, dict):
            return row.get(key, default)
        return default

    def _key(row):
        return (
            str(_get(row, "symbol") or "").upper(),
            str(_get(row, "campaign_id") or ""),
        )

    def _symbol_key(row):
        return str(_get(row, "symbol") or "").upper()

    def _bool(value):
        if value is True:
            return True
        if value is False:
            return False
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "y"}
        return False

    def _list(value):
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if value is None:
            return []
        return [value]

    def _is_high_priority_confluence(row):
        return (
            _get(row, "confluence_priority") == "HIGH_PRIORITY_UNCONFIRMED_BEHAVIORAL_RESOLUTION_REVIEW"
            or _get(row, "behavioral_resolution_confluence_status") == "HIGH_PRIORITY_BEHAVIORAL_RESOLUTION_REVIEW"
            or (
                _get(row, "decision_zone_class") == "HIGH_QUALITY_ADVANCED_DECISION_ZONE"
                and _get(row, "d3j_plausibility_status") == "D3D_PRODUCTION_CONFIRMED_OPERATOR_CONTROL"
            )
        )

    try:
        confluence_payload = macro_anchor_behavioral_resolution_confluence_review()
    except Exception as exc:
        return _error_payload("LOAD_D3C2F_CONFLUENCE_PAYLOAD", exc)

    try:
        d3c_payload = wyckoff_weis_operator_confirmation_review()
    except Exception as exc:
        return _error_payload("LOAD_D3C_WYCKOFF_WEIS_PAYLOAD", exc)

    confluence_rows = _rows_from_payload(confluence_payload)
    d3c_rows = _rows_from_payload(d3c_payload)

    d3c_by_key = {}
    d3c_by_symbol = {}

    for row in d3c_rows:
        d3c_by_key[_key(row)] = row
        d3c_by_symbol[_symbol_key(row)] = row

    rows = []
    row_errors = []
    guardrail_failures = []

    evidence_class_counter = Counter()
    requirement_counter = Counter()
    priority_counter = Counter()
    no_drift_counter = Counter()
    evidence_flag_counter = Counter()
    caution_flag_counter = Counter()
    d3c_doctrine_counter = Counter()
    d3c_sml_quality_counter = Counter()
    d3c_demand_counter = Counter()
    d3c_supply_counter = Counter()
    d3c_contrary_counter = Counter()
    d3c_source_counter = Counter()

    for confluence_row in confluence_rows:
        try:
            key = _key(confluence_row)
            symbol_key = _symbol_key(confluence_row)

            d3c_row = d3c_by_key.get(key) or d3c_by_symbol.get(symbol_key)

            source_d3j_row = _get(confluence_row, "source_d3j_row") or {}
            source_d3c2e_row = _get(confluence_row, "source_d3c2e_row") or {}

            d3c_source_found = isinstance(d3c_row, dict)

            doctrine_verdict = _get(d3c_row, "doctrine_verdict") if d3c_source_found else None
            demand_support = _bool(_get(d3c_row, "demand_support_validated")) if d3c_source_found else False
            supply_exhaustion = _bool(_get(d3c_row, "supply_exhaustion_validated")) if d3c_source_found else False
            contrary_failure = _bool(_get(d3c_row, "contrary_failure_present")) if d3c_source_found else False
            sml_present = _bool(_get(d3c_row, "sml_present")) if d3c_source_found else False
            sml_quality = _get(d3c_row, "sml_evidence_quality") if d3c_source_found else None

            explicit_sml = bool(
                d3c_source_found
                and sml_present is True
                and str(sml_quality or "").upper() == "EXPLICIT_GEOMETRY"
            )

            is_high_priority = _is_high_priority_confluence(confluence_row)

            evidence_flags = []
            caution_flags = []

            for flag in _list(_get(confluence_row, "caution_flags")):
                caution_flags.append(str(flag))

            if is_high_priority:
                evidence_flags.append("D3C2F_HIGH_PRIORITY_CONFLUENCE_ROW")
            else:
                evidence_flags.append("NOT_D3C2F_HIGH_PRIORITY_CONFLUENCE_ROW")

            if d3c_source_found:
                evidence_flags.append("D3C_REVIEW_ROW_SOURCE_PRESENT")
            else:
                caution_flags.append("D3C_REVIEW_ROW_SOURCE_MISSING")

            if doctrine_verdict == "DOCTRINE_CONFIRMABLE_SHADOW":
                evidence_flags.append("D3C_DOCTRINE_CONFIRMABLE_SHADOW")
            elif doctrine_verdict:
                caution_flags.append(f"D3C_DOCTRINE_{doctrine_verdict}")

            if demand_support is True:
                evidence_flags.append("D3C_DEMAND_SUPPORT_VALIDATED")
            else:
                caution_flags.append("D3C_DEMAND_SUPPORT_NOT_VALIDATED")

            if supply_exhaustion is True:
                evidence_flags.append("D3C_SUPPLY_EXHAUSTION_VALIDATED")
            else:
                caution_flags.append("D3C_SUPPLY_EXHAUSTION_NOT_VALIDATED")

            if contrary_failure is False:
                evidence_flags.append("D3C_NO_CONTRARY_FAILURE_PRESENT")
            else:
                caution_flags.append("D3C_CONTRARY_FAILURE_PRESENT")

            if sml_present is True:
                evidence_flags.append("D3C_SML_PRESENT")
            else:
                caution_flags.append("D3C_SML_MISSING")

            if explicit_sml is True:
                evidence_flags.append("D3C_EXPLICIT_GEOMETRY_SML_PRESENT")
            else:
                caution_flags.append("D3C_EXPLICIT_GEOMETRY_SML_NOT_PRESENT")

            if str(sml_quality or "").upper() == "INFERRED_FROM_ABSORPTION_EVENT":
                caution_flags.append("D3C_SML_INFERRED_FROM_ABSORPTION_EVENT_NOT_D3D_ELIGIBLE")

            caution_flags.append("D3D_PRODUCTION_CONFIRMATION_NOT_GRANTED")
            caution_flags.append("D3C2G_READ_ONLY_DIAGNOSTIC_NOT_CONFIRMATION")
            caution_flags.append("DECISION_ZONE_IS_NOT_BREAKOUT_CONFIRMATION")

            if (
                d3c_source_found
                and demand_support is True
                and supply_exhaustion is True
                and contrary_failure is False
                and sml_present is True
            ):
                behavioral_class = "COMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
            elif d3c_source_found and demand_support is True and supply_exhaustion is True:
                behavioral_class = "PARTIAL_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
            elif d3c_source_found and (demand_support is True or supply_exhaustion is True or contrary_failure is True or sml_present is True):
                behavioral_class = "INCOMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
            elif not d3c_source_found:
                behavioral_class = "MISSING_D3C_BEHAVIORAL_RESOLUTION_SOURCE_READ_ONLY"
            else:
                behavioral_class = "NO_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"

            if is_high_priority and behavioral_class == "COMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY":
                review_priority = "HIGH_REVIEW_PRIORITY_COMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_UNCONFIRMED"
                requirement = "BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_BUT_D3D_PRODUCTION_CONFIRMATION_STILL_REQUIRED"
            elif is_high_priority:
                review_priority = "HIGH_REVIEW_PRIORITY_INCOMPLETE_EVIDENCE_UNCONFIRMED"
                requirement = "REQUIRES_SEPARATE_BEHAVIORAL_RESOLUTION_EVIDENCE"
            else:
                review_priority = "STANDARD_REVIEW_PRIORITY_READ_ONLY"
                requirement = "NO_HIGH_PRIORITY_DECISION_ZONE_REVIEW_REQUIRED"

            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,
                "symbol": _get(confluence_row, "symbol"),
                "campaign_id": _get(confluence_row, "campaign_id"),
                "campaign_state": _get(confluence_row, "campaign_state"),

                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_unconfirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "d3d_execution_allowed": False,
                "d3d_source_used_by_this_engine": False,
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,

                "is_high_priority_confluence_row": bool(is_high_priority),
                "d3c2g_review_priority": review_priority,
                "behavioral_resolution_requirement": requirement,
                "behavioral_resolution_evidence_class": behavioral_class,

                "d3c_source_found": bool(d3c_source_found),
                "d3c_shadow_doctrine_verdict": doctrine_verdict,
                "d3c_shadow_explicit_geometry_sml": explicit_sml,
                "d3c_shadow_sml_evidence_quality": sml_quality,
                "d3c_shadow_demand_support_validated": demand_support,
                "d3c_shadow_supply_exhaustion_validated": supply_exhaustion,
                "d3c_shadow_contrary_failure_present": contrary_failure,

                "d3c_sml_present": sml_present,
                "d3c_sml_locations": _list(_get(d3c_row, "sml_locations")) if d3c_source_found else [],
                "d3c_sml_reason": _list(_get(d3c_row, "sml_reason")) if d3c_source_found else [],
                "d3c_doctrine_reason": _get(d3c_row, "doctrine_reason") if d3c_source_found else None,

                "d3j_plausibility_status": _get(source_d3j_row, "plausibility_status"),
                "d3j_shadow_confirmable": _get(source_d3j_row, "shadow_confirmable"),
                "d3j_legacy_operator_control_confirmed": _get(source_d3j_row, "legacy_operator_control_confirmed"),
                "d3j_d3d_production_confirmed": _get(source_d3j_row, "d3d_production_confirmed"),
                "d3j_operator_control_verdict": _get(source_d3j_row, "operator_control_verdict"),
                "d3j_operator_control_status": _get(source_d3j_row, "operator_control_status"),
                "d3j_operator_control_evidence_count": _get(source_d3j_row, "operator_control_evidence_count"),

                "decision_zone_status": _get(confluence_row, "decision_zone_status"),
                "decision_zone_class": _get(confluence_row, "decision_zone_class"),
                "macro_anchor_quality_tier": _get(confluence_row, "macro_anchor_quality_tier"),
                "current_location_relevance": _get(confluence_row, "current_location_relevance"),

                "support_touch_count": _get(confluence_row, "support_touch_count"),
                "support_rejection_count": _get(confluence_row, "support_rejection_count"),
                "resistance_touch_count": _get(confluence_row, "resistance_touch_count"),
                "resistance_rejection_count": _get(confluence_row, "resistance_rejection_count"),
                "resistance_distance_atr": _get(confluence_row, "resistance_distance_atr"),
                "resistance_distance_bucket": _get(confluence_row, "resistance_distance_bucket"),

                "evidence_flags_present": sorted(set(evidence_flags)),
                "caution_flags": sorted(set(caution_flags)),
                "d3c2g_no_drift_status": "PASS",

                "source_d3c2f_row": confluence_row,
                "source_d3c_row": d3c_row if d3c_source_found else None,
                "source_d3j_row": source_d3j_row,
                "source_d3c2e_row": source_d3c2e_row,
            }

            guardrail_ok = bool(
                row.get("diagnostic_only") is True
                and row.get("read_only") is True
                and row.get("writes_to_supabase") is False
                and row.get("mutates_campaigns") is False
                and row.get("production_confirmation_allowed") is False
                and row.get("operator_control_confirmed_by_this_engine") is False
                and row.get("operator_control_unconfirmed_by_this_engine") is False
                and row.get("operator_control_confirmation_impact") == "NONE"
                and row.get("d3d_execution_allowed") is False
                and row.get("d3d_source_used_by_this_engine") is False
                and row.get("score_impact") == "NONE"
                and row.get("rank_impact") == "NONE"
                and row.get("state_impact") == "NONE"
                and row.get("transition_impact") == "NONE"
                and row.get("gamma_confirmation_impact") == "NONE"
                and row.get("state_transition_enabled") is False
                and row.get("not_a_trade_signal") is True
                and row.get("d3c2g_no_drift_status") == "PASS"
            )

            if not guardrail_ok:
                guardrail_failures.append({
                    "symbol": row.get("symbol"),
                    "campaign_id": row.get("campaign_id"),
                    "reason": "D3C.2O D3C.2G guardrail failure",
                })

            rows.append(row)

            evidence_class_counter[str(behavioral_class)] += 1
            requirement_counter[str(requirement)] += 1
            priority_counter[str(review_priority)] += 1
            no_drift_counter[str(row.get("d3c2g_no_drift_status"))] += 1
            d3c_doctrine_counter[str(doctrine_verdict)] += 1
            d3c_sml_quality_counter[str(sml_quality)] += 1
            d3c_demand_counter[str(bool(demand_support))] += 1
            d3c_supply_counter[str(bool(supply_exhaustion))] += 1
            d3c_contrary_counter[str(bool(contrary_failure))] += 1
            d3c_source_counter[str(bool(d3c_source_found))] += 1

            for flag in row.get("evidence_flags_present") or []:
                evidence_flag_counter[str(flag)] += 1

            for flag in row.get("caution_flags") or []:
                caution_flag_counter[str(flag)] += 1

        except Exception as exc:
            row_errors.append({
                "symbol": _get(confluence_row, "symbol"),
                "campaign_id": _get(confluence_row, "campaign_id"),
                "reason": "ROW_EVALUATION_ERROR",
                "error": str(exc),
            })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("is_high_priority_confluence_row") is True else 1,
            str(row.get("behavioral_resolution_evidence_class") or ""),
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "engine": ENGINE_NAME + "_ENDPOINT",
        "version": ENGINE_VERSION,
        "endpoint_status": "OK" if not row_errors else "ROW_ERRORS_RETURNED_NO_MUTATION",
        "upstream_sources": [
            "D3C.2F:/api/campaign/macro-anchor-behavioral-resolution-confluence-review",
            "D3C:/api/campaign/wyckoff-weis-operator-confirmation-review",
            "D3J:/api/campaign/operator-control-plausibility-status-review retained as plausibility context only",
        ],
        "total_campaigns": len(rows),
        "d3c2f_rows_count": len(confluence_rows),
        "d3c_rows_count": len(d3c_rows),
        "high_priority_count": sum(1 for row in rows if row.get("is_high_priority_confluence_row") is True),
        "complete_behavioral_resolution_count": sum(
            1 for row in rows
            if row.get("behavioral_resolution_evidence_class") == "COMPLETE_BEHAVIORAL_RESOLUTION_EVIDENCE_PRESENT_READ_ONLY"
        ),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "behavioral_resolution_evidence_class_distribution": _safe_counter(evidence_class_counter),
        "behavioral_resolution_requirement_distribution": _safe_counter(requirement_counter),
        "d3c2g_review_priority_distribution": _safe_counter(priority_counter),
        "d3c2g_no_drift_status_distribution": _safe_counter(no_drift_counter),
        "d3c_source_found_distribution": _safe_counter(d3c_source_counter),
        "d3c_doctrine_verdict_distribution": _safe_counter(d3c_doctrine_counter),
        "d3c_sml_evidence_quality_distribution": _safe_counter(d3c_sml_quality_counter),
        "d3c_demand_support_validated_distribution": _safe_counter(d3c_demand_counter),
        "d3c_supply_exhaustion_validated_distribution": _safe_counter(d3c_supply_counter),
        "d3c_contrary_failure_present_distribution": _safe_counter(d3c_contrary_counter),
        "evidence_flag_distribution": _safe_counter(evidence_flag_counter),
        "caution_flag_distribution": _safe_counter(caution_flag_counter),
        "rows": rows,
    })
    return payload

@router.get("/hvn-poc-source-enrichment-review")
def hvn_poc_source_enrichment_review():
    """
    D3C.2R read-only HVN / POC source-enrichment review.

    Purpose:
    - Distinguish true HVN / POC source evidence from HVN_ABSORPTION_PROXY.
    - Treat HVN_ABSORPTION_PROXY as inferred behavioral-location evidence only.
    - Preserve D3D as the only production mutation gate.
    - Never confirm operator control.
    - Never mutate campaigns.
    - Never affect score, rank, state, transition, gamma, options, edge, probability,
      targets, or trade signals.
    """
    from collections import Counter

    ENGINE_NAME = "D3C2R_HVN_POC_SOURCE_ENRICHMENT_REVIEW"
    ENGINE_VERSION = "phase_d3c2r_hvn_poc_source_enrichment_read_only_v1"

    TRUE_HVN_POC_FIELDS = [
        "hvn",
        "high_volume_node",
        "volume_profile_poc",
        "poc",
        "vpoc",
        "volume_node",
        "major_volume_node",
        "high_volume_zone",
        "volume_profile_node",
        "hvn_poc",
    ]

    def _base_payload():
        return {
            "engine": ENGINE_NAME + "_ENDPOINT",
            "version": ENGINE_VERSION,
            "endpoint": "/api/campaign/hvn-poc-source-enrichment-review",
            "endpoint_status": "OK",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_unconfirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "d3d_execution_allowed": False,
            "d3d_source_used_by_this_engine": False,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
            "true_hvn_poc_policy": "TRUE_HVN_POC_REQUIRES_EXPLICIT_HVN_POC_SOURCE_FIELD",
            "proxy_policy": "HVN_ABSORPTION_PROXY_IS_INFERRED_BEHAVIORAL_LOCATION_NOT_TRUE_HVN_POC",
            "production_confirmation_policy": "D3C2R_NEVER_CONFIRMS_OPERATOR_CONTROL_D3D_ONLY",
        }

    def _safe_counter(counter):
        return dict(sorted(counter.items(), key=lambda item: str(item[0])))

    def _as_dict(value):
        return value if isinstance(value, dict) else {}

    def _list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        return [value]

    def _rows_from_payload(payload):
        payload = _as_dict(payload)
        for key in [
            "rows",
            "review_rows",
            "validation_rows",
            "structural_location_rows",
            "structural_location_reviews",
            "campaign_rows",
            "results",
            "items",
            "data",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ["true", "1", "yes", "y"]
        return bool(value)

    def _present(value):
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) > 0
        return True

    def _key(row):
        row = _as_dict(row)
        return (
            str(row.get("symbol") or "").upper(),
            str(row.get("campaign_id") or ""),
        )

    def _symbol_key(row):
        row = _as_dict(row)
        return str(row.get("symbol") or "").upper()

    def _get_nested(mapping, path):
        current = mapping
        for part in path:
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _collect_true_hvn_poc_sources(row):
        row = _as_dict(row)
        sources = []

        top_level_paths = []
        for field in TRUE_HVN_POC_FIELDS:
            top_level_paths.append(([field], field))
            top_level_paths.append((["structural_location", field], "structural_location." + field))
            top_level_paths.append((["evidence", field], "evidence." + field))
            top_level_paths.append((["evidence", "structural_location", field], "evidence.structural_location." + field))

        explicit_fields = [
            "hvn_level",
            "poc_level",
            "volume_node_level",
            "hvn_poc_source",
            "hvn_poc_status",
            "volume_node_type",
        ]

        for field in explicit_fields:
            top_level_paths.append(([field], field))

        for path_parts, label in top_level_paths:
            value = _get_nested(row, path_parts)
            if _present(value):
                sources.append({
                    "source_path": label,
                    "source_value": value,
                })

        return sources

    def _has_proxy(row):
        row = _as_dict(row)

        locations = []
        locations.extend(_list(row.get("sml_locations")))
        locations.extend(_list(row.get("d3c_sml_locations")))
        locations.extend(_list(row.get("d3c_shadow_sml_locations")))

        source_d3c_row = _as_dict(row.get("source_d3c_row"))
        locations.extend(_list(source_d3c_row.get("sml_locations")))

        return "HVN_ABSORPTION_PROXY" in [str(item) for item in locations]

    def _call_first_payload(names):
        for name in names:
            fn = globals().get(name)
            if callable(fn):
                return fn(), name
        raise RuntimeError("None of the expected payload functions are available: " + ", ".join(names))

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": str(stage),
            "error": str(exc),
            "total_campaigns": 0,
            "rows_count": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "rows": [],
            "guardrail_failures": [],
            "row_errors": [],
        })
        return payload

    try:
        d3c1_payload, d3c1_function_used = _call_first_payload([
            "structural_location_input_review",
            "structural_location_input_review_endpoint",
            "d3c_structural_location_input_review",
            "campaign_structural_location_input_review",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3C1_STRUCTURAL_LOCATION_INPUT_REVIEW", exc)

    try:
        d3c2o_payload, d3c2o_function_used = _call_first_payload([
            "macro_anchor_high_priority_resolution_evidence_review",
            "macro_anchor_high_priority_resolution_evidence_endpoint",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3C2O_HIGH_PRIORITY_BEHAVIORAL_RESOLUTION", exc)

    d3c1_rows = _rows_from_payload(d3c1_payload)
    d3c2o_rows = _rows_from_payload(d3c2o_payload)

    d3c2o_by_key = {}
    d3c2o_by_symbol = {}

    for row in d3c2o_rows:
        row = _as_dict(row)
        d3c2o_by_key[_key(row)] = row
        d3c2o_by_symbol[_symbol_key(row)] = row

    rows = []
    row_errors = []
    guardrail_failures = []

    truth_counter = Counter()
    proxy_counter = Counter()
    status_counter = Counter()
    priority_counter = Counter()
    no_drift_counter = Counter()
    d3c1_hvn_available_counter = Counter()
    d3c1_explicit_hvn_ready_counter = Counter()

    for source_row in d3c1_rows:
        try:
            source_row = _as_dict(source_row)
            key = _key(source_row)
            symbol_key = _symbol_key(source_row)
            d3c2o_row = d3c2o_by_key.get(key) or d3c2o_by_symbol.get(symbol_key) or {}

            true_sources = _collect_true_hvn_poc_sources(source_row)

            d3c1_hvn_available = _bool(source_row.get("hvn_poc_available"))
            d3c1_explicit_hvn_ready = _bool(source_row.get("explicit_hvn_zone_ready"))
            true_hvn_poc_available = bool(true_sources) or d3c1_hvn_available or d3c1_explicit_hvn_ready

            proxy_present = _has_proxy(d3c2o_row)

            is_high_priority = _bool(d3c2o_row.get("is_high_priority_confluence_row"))

            if true_hvn_poc_available:
                truth_status = "TRUE_HVN_POC_SOURCE_AVAILABLE_READ_ONLY"
                enrichment_status = "TRUE_HVN_POC_ENRICHMENT_SOURCE_PRESENT_UNCONFIRMED"
                requirement = "TRUE_HVN_POC_PRESENT_BUT_D3D_PRODUCTION_CONFIRMATION_STILL_REQUIRED"
            elif proxy_present:
                truth_status = "HVN_ABSORPTION_PROXY_ONLY_READ_ONLY"
                enrichment_status = "PROXY_ONLY_TRUE_HVN_POC_SOURCE_MISSING"
                requirement = "DO_NOT_TREAT_HVN_ABSORPTION_PROXY_AS_TRUE_HVN_POC"
            else:
                truth_status = "NO_TRUE_HVN_POC_SOURCE_PRESENT_READ_ONLY"
                enrichment_status = "TRUE_HVN_POC_SOURCE_MISSING"
                requirement = "TRUE_HVN_POC_SOURCE_FIELD_REQUIRED_FOR_ENRICHMENT"

            if is_high_priority and true_hvn_poc_available:
                review_priority = "HIGH_PRIORITY_TRUE_HVN_POC_SOURCE_PRESENT_UNCONFIRMED"
            elif is_high_priority and proxy_present:
                review_priority = "HIGH_PRIORITY_PROXY_ONLY_TRUE_HVN_POC_MISSING"
            elif is_high_priority:
                review_priority = "HIGH_PRIORITY_TRUE_HVN_POC_MISSING"
            else:
                review_priority = "STANDARD_REVIEW_PRIORITY_READ_ONLY"

            caution_flags = []
            evidence_flags = []

            if true_hvn_poc_available:
                evidence_flags.append("TRUE_HVN_POC_SOURCE_PRESENT")
            else:
                caution_flags.append("TRUE_HVN_POC_SOURCE_MISSING")

            if proxy_present:
                caution_flags.append("HVN_ABSORPTION_PROXY_PRESENT_NOT_TRUE_HVN_POC")

            if d3c1_explicit_hvn_ready:
                evidence_flags.append("D3C1_EXPLICIT_HVN_ZONE_READY")
            else:
                caution_flags.append("D3C1_EXPLICIT_HVN_ZONE_NOT_READY")

            if d3c1_hvn_available:
                evidence_flags.append("D3C1_HVN_POC_AVAILABLE")
            else:
                caution_flags.append("D3C1_HVN_POC_NOT_AVAILABLE")

            caution_flags.append("D3C2R_READ_ONLY_DIAGNOSTIC_NOT_CONFIRMATION")
            caution_flags.append("D3D_PRODUCTION_CONFIRMATION_NOT_GRANTED")

            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,

                "symbol": source_row.get("symbol"),
                "campaign_id": source_row.get("campaign_id"),
                "campaign_state": source_row.get("campaign_state"),
                "timeframe": source_row.get("timeframe"),

                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_unconfirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "d3d_execution_allowed": False,
                "d3d_source_used_by_this_engine": False,
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,

                "d3c2r_review_priority": review_priority,
                "hvn_poc_truth_status": truth_status,
                "hvn_poc_enrichment_status": enrichment_status,
                "hvn_poc_enrichment_requirement": requirement,

                "true_hvn_poc_available": bool(true_hvn_poc_available),
                "true_hvn_poc_source_count": len(true_sources),
                "true_hvn_poc_sources": true_sources,

                "hvn_absorption_proxy_present": bool(proxy_present),
                "proxy_policy": "HVN_ABSORPTION_PROXY_IS_NOT_TRUE_HVN_POC",

                "d3c1_hvn_poc_available": bool(d3c1_hvn_available),
                "d3c1_explicit_hvn_zone_ready": bool(d3c1_explicit_hvn_ready),
                "d3c1_structural_location_readiness": source_row.get("structural_location_readiness"),
                "d3c1_production_sml_possible_now": source_row.get("production_sml_possible_now"),
                "d3c1_explicit_trading_range_ready": source_row.get("explicit_trading_range_ready"),
                "d3c1_explicit_lp_zone_ready": source_row.get("explicit_lp_zone_ready"),
                "d3c1_explicit_support_resistance_ready": source_row.get("explicit_support_resistance_ready"),

                "is_high_priority_confluence_row": bool(is_high_priority),
                "d3c2o_behavioral_resolution_evidence_class": d3c2o_row.get("behavioral_resolution_evidence_class"),
                "d3c2o_review_priority": d3c2o_row.get("d3c2g_review_priority"),
                "d3c2o_decision_zone_status": d3c2o_row.get("decision_zone_status"),
                "d3c2o_decision_zone_class": d3c2o_row.get("decision_zone_class"),
                "d3c2o_d3c_shadow_sml_evidence_quality": d3c2o_row.get("d3c_shadow_sml_evidence_quality"),
                "d3c2o_d3c_sml_locations": d3c2o_row.get("d3c_sml_locations") or [],

                "evidence_flags_present": evidence_flags,
                "caution_flags": caution_flags,
                "d3c2r_no_drift_status": "PASS",

                "source_d3c1_row": source_row,
                "source_d3c2o_row": d3c2o_row,
            }

            guardrail_ok = (
                row.get("diagnostic_only") is True
                and row.get("read_only") is True
                and row.get("writes_to_supabase") is False
                and row.get("mutates_campaigns") is False
                and row.get("production_confirmation_allowed") is False
                and row.get("operator_control_confirmed_by_this_engine") is False
                and row.get("operator_control_unconfirmed_by_this_engine") is False
                and row.get("operator_control_confirmation_impact") == "NONE"
                and row.get("d3d_execution_allowed") is False
                and row.get("d3d_source_used_by_this_engine") is False
                and row.get("score_impact") == "NONE"
                and row.get("rank_impact") == "NONE"
                and row.get("state_impact") == "NONE"
                and row.get("transition_impact") == "NONE"
                and row.get("gamma_confirmation_impact") == "NONE"
                and row.get("state_transition_enabled") is False
                and row.get("not_a_trade_signal") is True
                and row.get("d3c2r_no_drift_status") == "PASS"
            )

            if not guardrail_ok:
                guardrail_failures.append({
                    "symbol": row.get("symbol"),
                    "campaign_id": row.get("campaign_id"),
                    "reason": "D3C.2R guardrail failure",
                    "row": row,
                })

            rows.append(row)

            truth_counter[str(bool(true_hvn_poc_available))] += 1
            proxy_counter[str(bool(proxy_present))] += 1
            status_counter[str(truth_status)] += 1
            priority_counter[str(review_priority)] += 1
            no_drift_counter[str(row.get("d3c2r_no_drift_status"))] += 1
            d3c1_hvn_available_counter[str(bool(d3c1_hvn_available))] += 1
            d3c1_explicit_hvn_ready_counter[str(bool(d3c1_explicit_hvn_ready))] += 1

        except Exception as exc:
            row_errors.append({
                "symbol": _as_dict(source_row).get("symbol"),
                "campaign_id": _as_dict(source_row).get("campaign_id"),
                "reason": "ROW_EVALUATION_ERROR",
                "error": str(exc),
            })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("is_high_priority_confluence_row") else 1,
            0 if row.get("true_hvn_poc_available") else 1,
            0 if row.get("hvn_absorption_proxy_present") else 1,
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "d3c1_function_used": d3c1_function_used,
        "d3c2o_function_used": d3c2o_function_used,
        "total_campaigns": len(d3c1_rows),
        "d3c1_rows_count": len(d3c1_rows),
        "d3c2o_rows_count": len(d3c2o_rows),
        "rows_count": len(rows),
        "high_priority_count": len([row for row in rows if row.get("is_high_priority_confluence_row") is True]),
        "true_hvn_poc_available_count": len([row for row in rows if row.get("true_hvn_poc_available") is True]),
        "hvn_absorption_proxy_count": len([row for row in rows if row.get("hvn_absorption_proxy_present") is True]),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "true_hvn_poc_available_distribution": _safe_counter(truth_counter),
        "hvn_absorption_proxy_distribution": _safe_counter(proxy_counter),
        "hvn_poc_truth_status_distribution": _safe_counter(status_counter),
        "d3c2r_review_priority_distribution": _safe_counter(priority_counter),
        "d3c2r_no_drift_status_distribution": _safe_counter(no_drift_counter),
        "d3c1_hvn_poc_available_distribution": _safe_counter(d3c1_hvn_available_counter),
        "d3c1_explicit_hvn_zone_ready_distribution": _safe_counter(d3c1_explicit_hvn_ready_counter),
        "rows": rows,
    })

    return payload

@router.get("/doctrine-leg-explanation-enrichment-review")
def doctrine_leg_explanation_enrichment_review():
    """
    D3C.2S read-only doctrine-leg explanation enrichment review.

    Purpose:
    - Explain the doctrine legs behind behavioral-resolution evidence.
    - Separate demand support, supply exhaustion, contrary failure, and SML.
    - Preserve inferred SML as inferred evidence only.
    - Preserve HVN_ABSORPTION_PROXY as proxy-only, not true HVN/POC.
    - Never confirm operator control.
    - Never execute D3D.
    - Never mutate campaigns.
    - Never affect score, rank, state, transition, gamma, options, edge,
      probability, targets, or trade signals.
    """
    from collections import Counter

    ENGINE_NAME = "D3C2S_DOCTRINE_LEG_EXPLANATION_ENRICHMENT_REVIEW"
    ENGINE_VERSION = "phase_d3c2s_doctrine_leg_explanation_enrichment_read_only_v1"

    def _base_payload():
        return {
            "engine": ENGINE_NAME + "_ENDPOINT",
            "version": ENGINE_VERSION,
            "endpoint": "/api/campaign/doctrine-leg-explanation-enrichment-review",
            "endpoint_status": "OK",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_unconfirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "d3d_execution_allowed": False,
            "d3d_source_used_by_this_engine": False,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
            "doctrine_leg_policy": "DOCTRINE_LEGS_ARE_EXPLANATORY_EVIDENCE_NOT_PRODUCTION_CONFIRMATION",
            "sml_policy": "INFERRED_SML_REMAINS_INFERRED_UNTIL_EXPLICIT_GEOMETRY_EXISTS",
            "hvn_proxy_policy": "HVN_ABSORPTION_PROXY_IS_NOT_TRUE_HVN_POC",
            "production_confirmation_policy": "D3C2S_NEVER_CONFIRMS_OPERATOR_CONTROL_D3D_ONLY",
        }

    def _safe_counter(counter):
        return dict(sorted(counter.items(), key=lambda item: str(item[0])))

    def _as_dict(value):
        return value if isinstance(value, dict) else {}

    def _list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        return [value]

    def _bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ["true", "1", "yes", "y"]
        return bool(value)

    def _rows_from_payload(payload):
        payload = _as_dict(payload)
        for key in [
            "rows",
            "review_rows",
            "validation_rows",
            "campaign_rows",
            "results",
            "items",
            "data",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _has_hvn_proxy(locations):
        return "HVN_ABSORPTION_PROXY" in [str(item) for item in _list(locations)]

    def _call_first_payload(names):
        for name in names:
            fn = globals().get(name)
            if callable(fn):
                return fn(), name
        raise RuntimeError("None of the expected payload functions are available: " + ", ".join(names))

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": str(stage),
            "error": str(exc),
            "total_campaigns": 0,
            "rows_count": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "rows": [],
            "guardrail_failures": [],
            "row_errors": [],
        })
        return payload

    try:
        d3c2o_payload, d3c2o_function_used = _call_first_payload([
            "macro_anchor_high_priority_resolution_evidence_review",
            "macro_anchor_high_priority_resolution_evidence_endpoint",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3C2O_HIGH_PRIORITY_BEHAVIORAL_RESOLUTION", exc)

    d3c2o_rows = _rows_from_payload(d3c2o_payload)

    rows = []
    guardrail_failures = []
    row_errors = []

    completeness_counter = Counter()
    priority_counter = Counter()
    demand_counter = Counter()
    supply_counter = Counter()
    contrary_counter = Counter()
    sml_counter = Counter()
    sml_quality_counter = Counter()
    hvn_proxy_counter = Counter()
    no_drift_counter = Counter()

    for source_row in d3c2o_rows:
        try:
            source_row = _as_dict(source_row)
            source_d3c_row = _as_dict(source_row.get("source_d3c_row"))

            demand_support = _bool(source_row.get("d3c_shadow_demand_support_validated"))
            supply_exhaustion = _bool(source_row.get("d3c_shadow_supply_exhaustion_validated"))
            contrary_failure = _bool(source_row.get("d3c_shadow_contrary_failure_present"))
            sml_present = _bool(source_row.get("d3c_sml_present"))
            sml_quality = source_row.get("d3c_shadow_sml_evidence_quality")
            sml_locations = _list(source_row.get("d3c_sml_locations"))
            is_high_priority = _bool(source_row.get("is_high_priority_confluence_row"))

            hvn_proxy_present = _has_hvn_proxy(sml_locations)
            explicit_sml = bool(sml_present and str(sml_quality or "").upper() == "EXPLICIT_GEOMETRY")
            inferred_sml = bool(sml_present and str(sml_quality or "").upper().startswith("INFERRED"))

            complete_leg_set = bool(
                demand_support is True
                and supply_exhaustion is True
                and contrary_failure is False
                and sml_present is True
            )

            partial_leg_set = bool(
                not complete_leg_set
                and (
                    demand_support is True
                    or supply_exhaustion is True
                    or contrary_failure is True
                    or sml_present is True
                )
            )

            if complete_leg_set:
                doctrine_leg_completeness = "COMPLETE_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"
                requirement = "DOCTRINE_LEGS_COMPLETE_BUT_D3D_PRODUCTION_CONFIRMATION_STILL_REQUIRED"
            elif partial_leg_set:
                doctrine_leg_completeness = "PARTIAL_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"
                requirement = "DOCTRINE_LEGS_PARTIAL_D3D_PRODUCTION_CONFIRMATION_NOT_ALLOWED"
            else:
                doctrine_leg_completeness = "NO_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"
                requirement = "DOCTRINE_LEG_EVIDENCE_REQUIRED_BEFORE_ANY_D3D_REVIEW"

            if is_high_priority and complete_leg_set:
                review_priority = "HIGH_PRIORITY_COMPLETE_DOCTRINE_LEG_SET_UNCONFIRMED"
            elif is_high_priority and partial_leg_set:
                review_priority = "HIGH_PRIORITY_PARTIAL_DOCTRINE_LEG_SET_UNCONFIRMED"
            elif is_high_priority:
                review_priority = "HIGH_PRIORITY_DOCTRINE_LEG_SET_MISSING"
            else:
                review_priority = "STANDARD_REVIEW_PRIORITY_READ_ONLY"

            evidence_flags = []
            caution_flags = []

            if demand_support:
                evidence_flags.append("DEMAND_SUPPORT_VALIDATED")
            else:
                caution_flags.append("DEMAND_SUPPORT_NOT_VALIDATED")

            if supply_exhaustion:
                evidence_flags.append("SUPPLY_EXHAUSTION_VALIDATED")
            else:
                caution_flags.append("SUPPLY_EXHAUSTION_NOT_VALIDATED")

            if contrary_failure:
                caution_flags.append("CONTRARY_FAILURE_PRESENT")
            else:
                evidence_flags.append("NO_CONTRARY_FAILURE_PRESENT")

            if sml_present:
                evidence_flags.append("SML_PRESENT")
            else:
                caution_flags.append("SML_MISSING")

            if explicit_sml:
                evidence_flags.append("EXPLICIT_GEOMETRY_SML_PRESENT")
            elif inferred_sml:
                caution_flags.append("SML_INFERRED_NOT_D3D_ELIGIBLE")
            else:
                caution_flags.append("SML_NOT_EXPLICIT")

            if hvn_proxy_present:
                caution_flags.append("HVN_ABSORPTION_PROXY_PRESENT_NOT_TRUE_HVN_POC")

            caution_flags.append("D3C2S_READ_ONLY_DIAGNOSTIC_NOT_CONFIRMATION")
            caution_flags.append("D3D_PRODUCTION_CONFIRMATION_NOT_GRANTED")

            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,

                "symbol": source_row.get("symbol"),
                "campaign_id": source_row.get("campaign_id"),
                "campaign_state": source_row.get("campaign_state"),

                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_unconfirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "d3d_execution_allowed": False,
                "d3d_source_used_by_this_engine": False,
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,

                "is_high_priority_confluence_row": bool(is_high_priority),
                "d3c2s_review_priority": review_priority,
                "doctrine_leg_completeness": doctrine_leg_completeness,
                "doctrine_leg_requirement": requirement,

                "demand_support_validated": bool(demand_support),
                "demand_support_flags_present": _list(source_d3c_row.get("demand_support_flags_present")),
                "demand_support_explanation": (
                    "Demand/support leg is validated by D3C source evidence."
                    if demand_support else
                    "Demand/support leg is not validated by D3C source evidence."
                ),

                "supply_exhaustion_validated": bool(supply_exhaustion),
                "supply_exhaustion_flags_present": _list(source_d3c_row.get("supply_exhaustion_flags_present")),
                "supply_exhaustion_explanation": (
                    "Supply-exhaustion leg is validated by D3C source evidence."
                    if supply_exhaustion else
                    "Supply-exhaustion leg is not validated by D3C source evidence."
                ),

                "contrary_failure_present": bool(contrary_failure),
                "contrary_failure_flags_present": _list(source_d3c_row.get("contrary_failure_flags_present")),
                "contrary_failure_explanation": (
                    "Contrary failure is present; behavioral-resolution evidence is blocked or cautionary."
                    if contrary_failure else
                    "No contrary failure is present in D3C source evidence."
                ),

                "sml_present": bool(sml_present),
                "sml_locations": sml_locations,
                "sml_evidence_quality": sml_quality,
                "sml_reason": _list(source_d3c_row.get("sml_reason")),
                "explicit_geometry_sml": bool(explicit_sml),
                "inferred_sml": bool(inferred_sml),
                "hvn_absorption_proxy_present": bool(hvn_proxy_present),
                "sml_explanation": (
                    "SML is explicit geometry."
                    if explicit_sml else
                    "SML is inferred and remains non-production evidence."
                    if inferred_sml else
                    "SML is missing or not explicit."
                ),

                "footprint_present": source_d3c_row.get("footprint_present"),
                "footprint_count": source_d3c_row.get("footprint_count"),
                "footprint_archetypes": _list(source_d3c_row.get("footprint_archetypes")),
                "doctrine_verdict": source_row.get("d3c_shadow_doctrine_verdict"),
                "doctrine_reason": source_row.get("d3c_doctrine_reason"),
                "behavioral_resolution_evidence_class": source_row.get("behavioral_resolution_evidence_class"),
                "behavioral_resolution_requirement": source_row.get("behavioral_resolution_requirement"),
                "decision_zone_status": source_row.get("decision_zone_status"),
                "decision_zone_class": source_row.get("decision_zone_class"),

                "evidence_flags_present": evidence_flags,
                "caution_flags": caution_flags,
                "d3c2s_no_drift_status": "PASS",

                "source_d3c2o_row": source_row,
                "source_d3c_row": source_d3c_row,
            }

            guardrail_ok = (
                row.get("diagnostic_only") is True
                and row.get("read_only") is True
                and row.get("writes_to_supabase") is False
                and row.get("mutates_campaigns") is False
                and row.get("production_confirmation_allowed") is False
                and row.get("operator_control_confirmed_by_this_engine") is False
                and row.get("operator_control_unconfirmed_by_this_engine") is False
                and row.get("operator_control_confirmation_impact") == "NONE"
                and row.get("d3d_execution_allowed") is False
                and row.get("d3d_source_used_by_this_engine") is False
                and row.get("score_impact") == "NONE"
                and row.get("rank_impact") == "NONE"
                and row.get("state_impact") == "NONE"
                and row.get("transition_impact") == "NONE"
                and row.get("gamma_confirmation_impact") == "NONE"
                and row.get("state_transition_enabled") is False
                and row.get("not_a_trade_signal") is True
                and row.get("d3c2s_no_drift_status") == "PASS"
            )

            if not guardrail_ok:
                guardrail_failures.append({
                    "symbol": row.get("symbol"),
                    "campaign_id": row.get("campaign_id"),
                    "reason": "D3C.2S guardrail failure",
                    "row": row,
                })

            rows.append(row)

            completeness_counter[str(doctrine_leg_completeness)] += 1
            priority_counter[str(review_priority)] += 1
            demand_counter[str(bool(demand_support))] += 1
            supply_counter[str(bool(supply_exhaustion))] += 1
            contrary_counter[str(bool(contrary_failure))] += 1
            sml_counter[str(bool(sml_present))] += 1
            sml_quality_counter[str(sml_quality)] += 1
            hvn_proxy_counter[str(bool(hvn_proxy_present))] += 1
            no_drift_counter[str(row.get("d3c2s_no_drift_status"))] += 1

        except Exception as exc:
            row_errors.append({
                "symbol": _as_dict(source_row).get("symbol"),
                "campaign_id": _as_dict(source_row).get("campaign_id"),
                "reason": "ROW_EVALUATION_ERROR",
                "error": str(exc),
            })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("is_high_priority_confluence_row") else 1,
            0 if row.get("doctrine_leg_completeness") == "COMPLETE_DOCTRINE_LEG_SET_PRESENT_READ_ONLY" else 1,
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "d3c2o_function_used": d3c2o_function_used,
        "total_campaigns": len(d3c2o_rows),
        "d3c2o_rows_count": len(d3c2o_rows),
        "rows_count": len(rows),
        "high_priority_count": len([row for row in rows if row.get("is_high_priority_confluence_row") is True]),
        "complete_doctrine_leg_set_count": len([row for row in rows if row.get("doctrine_leg_completeness") == "COMPLETE_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"]),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "doctrine_leg_completeness_distribution": _safe_counter(completeness_counter),
        "d3c2s_review_priority_distribution": _safe_counter(priority_counter),
        "demand_support_validated_distribution": _safe_counter(demand_counter),
        "supply_exhaustion_validated_distribution": _safe_counter(supply_counter),
        "contrary_failure_present_distribution": _safe_counter(contrary_counter),
        "sml_present_distribution": _safe_counter(sml_counter),
        "sml_evidence_quality_distribution": _safe_counter(sml_quality_counter),
        "hvn_absorption_proxy_distribution": _safe_counter(hvn_proxy_counter),
        "d3c2s_no_drift_status_distribution": _safe_counter(no_drift_counter),
        "rows": rows,
    })

    return payload

@router.get("/stealth-monitoring-diagnostic-review")
def stealth_monitoring_diagnostic_review():
    """
    D3C.2T read-only stealth monitoring diagnostic review.

    Purpose:
    - Monitor unresolved stealth / shadow-confirmable operator-control evidence.
    - Combine D3J plausibility context with D3C.2S doctrine-leg explanation.
    - Preserve all evidence as diagnostic and unconfirmed.
    - Never confirm operator control.
    - Never execute D3D.
    - Never mutate campaigns.
    - Never affect score, rank, state, transition, gamma, options, edge,
      probability, targets, or trade signals.
    """
    from collections import Counter

    ENGINE_NAME = "D3C2T_STEALTH_MONITORING_DIAGNOSTIC_REVIEW"
    ENGINE_VERSION = "phase_d3c2t_stealth_monitoring_diagnostic_read_only_v1"

    def _base_payload():
        return {
            "engine": ENGINE_NAME + "_ENDPOINT",
            "version": ENGINE_VERSION,
            "endpoint": "/api/campaign/stealth-monitoring-diagnostic-review",
            "endpoint_status": "OK",
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_unconfirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "d3d_execution_allowed": False,
            "d3d_source_used_by_this_engine": False,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
            "stealth_policy": "STEALTH_MONITORING_IS_DIAGNOSTIC_ONLY_NOT_CONFIRMATION",
            "operator_control_policy": "OPERATOR_CONTROL_REMAINS_UNCONFIRMED_UNLESS_D3D_SEPARATELY_AUTHORIZED",
            "d3d_policy": "D3C2T_NEVER_EXECUTES_D3D",
        }

    def _safe_counter(counter):
        return dict(sorted(counter.items(), key=lambda item: str(item[0])))

    def _as_dict(value):
        return value if isinstance(value, dict) else {}

    def _list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        return [value]

    def _bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ["true", "1", "yes", "y"]
        return bool(value)

    def _rows_from_payload(payload):
        payload = _as_dict(payload)
        for key in [
            "rows",
            "review_rows",
            "validation_rows",
            "campaign_rows",
            "results",
            "items",
            "data",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _key(row):
        row = _as_dict(row)
        return (
            str(row.get("symbol") or "").upper(),
            str(row.get("campaign_id") or ""),
        )

    def _symbol_key(row):
        row = _as_dict(row)
        return str(row.get("symbol") or "").upper()

    def _call_first_payload(names):
        for name in names:
            fn = globals().get(name)
            if callable(fn):
                return fn(), name
        raise RuntimeError("None of the expected payload functions are available: " + ", ".join(names))

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": str(stage),
            "error": str(exc),
            "total_campaigns": 0,
            "rows_count": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "rows": [],
            "guardrail_failures": [],
            "row_errors": [],
        })
        return payload

    try:
        d3j_payload, d3j_function_used = _call_first_payload([
            "operator_control_plausibility_status_review",
            "operator_control_plausibility_status_endpoint",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3J_OPERATOR_CONTROL_PLAUSIBILITY", exc)

    try:
        d3c2s_payload, d3c2s_function_used = _call_first_payload([
            "doctrine_leg_explanation_enrichment_review",
            "doctrine_leg_explanation_enrichment_endpoint",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3C2S_DOCTRINE_LEG_EXPLANATION", exc)

    d3j_rows = _rows_from_payload(d3j_payload)
    d3c2s_rows = _rows_from_payload(d3c2s_payload)

    d3c2s_by_key = {}
    d3c2s_by_symbol = {}

    for row in d3c2s_rows:
        row = _as_dict(row)
        d3c2s_by_key[_key(row)] = row
        d3c2s_by_symbol[_symbol_key(row)] = row

    rows = []
    guardrail_failures = []
    row_errors = []

    stealth_status_counter = Counter()
    monitor_priority_counter = Counter()
    plausibility_counter = Counter()
    doctrine_completeness_counter = Counter()
    high_priority_counter = Counter()
    no_drift_counter = Counter()

    for d3j_row in d3j_rows:
        try:
            d3j_row = _as_dict(d3j_row)
            d3c2s_row = d3c2s_by_key.get(_key(d3j_row)) or d3c2s_by_symbol.get(_symbol_key(d3j_row)) or {}

            plausibility_status = str(d3j_row.get("plausibility_status") or "")
            shadow_confirmable = _bool(d3j_row.get("shadow_confirmable"))
            legacy_operator_control_confirmed = _bool(d3j_row.get("legacy_operator_control_confirmed"))
            d3d_production_confirmed = _bool(d3j_row.get("d3d_production_confirmed"))

            doctrine_leg_completeness = str(d3c2s_row.get("doctrine_leg_completeness") or "MISSING_D3C2S_DOCTRINE_LEG_CONTEXT")
            complete_doctrine_legs = doctrine_leg_completeness == "COMPLETE_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"
            partial_doctrine_legs = doctrine_leg_completeness == "PARTIAL_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"
            is_high_priority = _bool(d3c2s_row.get("is_high_priority_confluence_row"))
            hvn_proxy_present = _bool(d3c2s_row.get("hvn_absorption_proxy_present"))
            inferred_sml = _bool(d3c2s_row.get("inferred_sml"))
            explicit_sml = _bool(d3c2s_row.get("explicit_geometry_sml"))

            plausible_stealth = plausibility_status == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED"
            legacy_shadow = plausibility_status == "LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE"

            if plausible_stealth and complete_doctrine_legs:
                stealth_status = "PLAUSIBLE_STEALTH_COMPLETE_DOCTRINE_LEGS_UNCONFIRMED"
                monitor_priority = "STEALTH_MONITOR_HIGH_PRIORITY_READ_ONLY"
            elif plausible_stealth and partial_doctrine_legs:
                stealth_status = "PLAUSIBLE_STEALTH_PARTIAL_DOCTRINE_LEGS_UNCONFIRMED"
                monitor_priority = "STEALTH_MONITOR_ELEVATED_PRIORITY_READ_ONLY"
            elif plausible_stealth:
                stealth_status = "PLAUSIBLE_STEALTH_DOCTRINE_LEGS_INCOMPLETE_UNCONFIRMED"
                monitor_priority = "STEALTH_MONITOR_ELEVATED_PRIORITY_READ_ONLY"
            elif legacy_shadow and complete_doctrine_legs:
                stealth_status = "LEGACY_SHADOW_COMPLETE_DOCTRINE_LEGS_UNCONFIRMED"
                monitor_priority = "LEGACY_SHADOW_MONITOR_HIGH_PRIORITY_READ_ONLY"
            elif legacy_shadow:
                stealth_status = "LEGACY_SHADOW_INCOMPLETE_DOCTRINE_LEGS_UNCONFIRMED"
                monitor_priority = "LEGACY_SHADOW_MONITOR_STANDARD_READ_ONLY"
            elif is_high_priority and complete_doctrine_legs:
                stealth_status = "HIGH_PRIORITY_COMPLETE_DOCTRINE_LEGS_NOT_STEALTH_CLASSIFIED_UNCONFIRMED"
                monitor_priority = "HIGH_PRIORITY_DOCTRINE_MONITOR_READ_ONLY"
            else:
                stealth_status = "STANDARD_NO_STEALTH_MONITORING_ESCALATION_READ_ONLY"
                monitor_priority = "STANDARD_REVIEW_PRIORITY_READ_ONLY"

            evidence_flags = []
            caution_flags = []

            if plausible_stealth:
                evidence_flags.append("D3J_PLAUSIBLE_STEALTH_UNCONFIRMED")

            if legacy_shadow:
                evidence_flags.append("D3J_LEGACY_OPERATOR_CONTROL_SHADOW_CONFIRMABLE")

            if shadow_confirmable:
                evidence_flags.append("D3J_SHADOW_CONFIRMABLE")

            if complete_doctrine_legs:
                evidence_flags.append("D3C2S_COMPLETE_DOCTRINE_LEG_SET")
            elif partial_doctrine_legs:
                caution_flags.append("D3C2S_PARTIAL_DOCTRINE_LEG_SET")
            else:
                caution_flags.append("D3C2S_DOCTRINE_LEG_SET_INCOMPLETE_OR_MISSING")

            if is_high_priority:
                evidence_flags.append("D3C2S_HIGH_PRIORITY_CONFLUENCE_ROW")

            if hvn_proxy_present:
                caution_flags.append("HVN_ABSORPTION_PROXY_PRESENT_NOT_TRUE_HVN_POC")

            if inferred_sml:
                caution_flags.append("SML_INFERRED_NOT_D3D_ELIGIBLE")

            if explicit_sml:
                evidence_flags.append("EXPLICIT_GEOMETRY_SML_PRESENT")

            if legacy_operator_control_confirmed:
                caution_flags.append("LEGACY_OPERATOR_CONTROL_EVIDENCE_PRESENT_NOT_D3D_PRODUCTION_CONFIRMATION")

            if d3d_production_confirmed:
                caution_flags.append("D3D_PRODUCTION_CONFIRMATION_ALREADY_PRESENT_REVIEW_REQUIRED")

            caution_flags.append("D3C2T_READ_ONLY_DIAGNOSTIC_NOT_CONFIRMATION")
            caution_flags.append("D3D_PRODUCTION_CONFIRMATION_NOT_GRANTED_BY_D3C2T")

            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,

                "symbol": d3j_row.get("symbol"),
                "campaign_id": d3j_row.get("campaign_id"),
                "campaign_state": d3j_row.get("campaign_state"),

                "diagnostic_only": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_unconfirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "d3d_execution_allowed": False,
                "d3d_source_used_by_this_engine": False,
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,

                "stealth_monitor_status": stealth_status,
                "stealth_monitor_priority": monitor_priority,

                "d3j_plausibility_status": plausibility_status,
                "d3j_shadow_confirmable": bool(shadow_confirmable),
                "d3j_legacy_operator_control_confirmed": bool(legacy_operator_control_confirmed),
                "d3j_d3d_production_confirmed": bool(d3d_production_confirmed),
                "d3j_operator_control_evidence_count": d3j_row.get("operator_control_evidence_count"),

                "d3c2s_source_found": bool(d3c2s_row),
                "d3c2s_review_priority": d3c2s_row.get("d3c2s_review_priority"),
                "doctrine_leg_completeness": doctrine_leg_completeness,
                "demand_support_validated": d3c2s_row.get("demand_support_validated"),
                "supply_exhaustion_validated": d3c2s_row.get("supply_exhaustion_validated"),
                "contrary_failure_present": d3c2s_row.get("contrary_failure_present"),
                "sml_present": d3c2s_row.get("sml_present"),
                "sml_evidence_quality": d3c2s_row.get("sml_evidence_quality"),
                "explicit_geometry_sml": bool(explicit_sml),
                "inferred_sml": bool(inferred_sml),
                "hvn_absorption_proxy_present": bool(hvn_proxy_present),
                "is_high_priority_confluence_row": bool(is_high_priority),

                "evidence_flags_present": evidence_flags,
                "caution_flags": caution_flags,
                "d3c2t_no_drift_status": "PASS",

                "source_d3j_row": d3j_row,
                "source_d3c2s_row": d3c2s_row,
            }

            guardrail_ok = (
                row.get("diagnostic_only") is True
                and row.get("read_only") is True
                and row.get("writes_to_supabase") is False
                and row.get("mutates_campaigns") is False
                and row.get("production_confirmation_allowed") is False
                and row.get("operator_control_confirmed_by_this_engine") is False
                and row.get("operator_control_unconfirmed_by_this_engine") is False
                and row.get("operator_control_confirmation_impact") == "NONE"
                and row.get("d3d_execution_allowed") is False
                and row.get("d3d_source_used_by_this_engine") is False
                and row.get("score_impact") == "NONE"
                and row.get("rank_impact") == "NONE"
                and row.get("state_impact") == "NONE"
                and row.get("transition_impact") == "NONE"
                and row.get("gamma_confirmation_impact") == "NONE"
                and row.get("state_transition_enabled") is False
                and row.get("not_a_trade_signal") is True
                and row.get("d3c2t_no_drift_status") == "PASS"
            )

            if not guardrail_ok:
                guardrail_failures.append({
                    "symbol": row.get("symbol"),
                    "campaign_id": row.get("campaign_id"),
                    "reason": "D3C.2T guardrail failure",
                    "row": row,
                })

            rows.append(row)

            stealth_status_counter[str(stealth_status)] += 1
            monitor_priority_counter[str(monitor_priority)] += 1
            plausibility_counter[str(plausibility_status)] += 1
            doctrine_completeness_counter[str(doctrine_leg_completeness)] += 1
            high_priority_counter[str(bool(is_high_priority))] += 1
            no_drift_counter[str(row.get("d3c2t_no_drift_status"))] += 1

        except Exception as exc:
            row_errors.append({
                "symbol": _as_dict(d3j_row).get("symbol"),
                "campaign_id": _as_dict(d3j_row).get("campaign_id"),
                "reason": "ROW_EVALUATION_ERROR",
                "error": str(exc),
            })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("stealth_monitor_priority") == "STEALTH_MONITOR_HIGH_PRIORITY_READ_ONLY" else
            1 if row.get("stealth_monitor_priority") == "STEALTH_MONITOR_ELEVATED_PRIORITY_READ_ONLY" else
            2 if row.get("stealth_monitor_priority") == "LEGACY_SHADOW_MONITOR_HIGH_PRIORITY_READ_ONLY" else
            3 if row.get("stealth_monitor_priority") == "HIGH_PRIORITY_DOCTRINE_MONITOR_READ_ONLY" else 4,
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "d3j_function_used": d3j_function_used,
        "d3c2s_function_used": d3c2s_function_used,
        "total_campaigns": len(d3j_rows),
        "d3j_rows_count": len(d3j_rows),
        "d3c2s_rows_count": len(d3c2s_rows),
        "rows_count": len(rows),
        "stealth_monitor_candidate_count": len([row for row in rows if str(row.get("stealth_monitor_priority")) != "STANDARD_REVIEW_PRIORITY_READ_ONLY"]),
        "plausible_stealth_unconfirmed_count": len([row for row in rows if row.get("d3j_plausibility_status") == "SHADOW_CONFIRMABLE_PLAUSIBLE_STEALTH_UNCONFIRMED"]),
        "high_priority_count": len([row for row in rows if row.get("is_high_priority_confluence_row") is True]),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "stealth_monitor_status_distribution": _safe_counter(stealth_status_counter),
        "stealth_monitor_priority_distribution": _safe_counter(monitor_priority_counter),
        "d3j_plausibility_status_distribution": _safe_counter(plausibility_counter),
        "doctrine_leg_completeness_distribution": _safe_counter(doctrine_completeness_counter),
        "high_priority_distribution": _safe_counter(high_priority_counter),
        "d3c2t_no_drift_status_distribution": _safe_counter(no_drift_counter),
        "rows": rows,
    })

    return payload

@router.get("/d3d-dry-run-candidate-preflight-review")
def d3d_dry_run_candidate_preflight_review():
    """
    D3V read-only D3D dry-run candidate preflight review.

    Purpose:
    - Identify which campaigns would be considered for future D3D review.
    - Apply D3U protocol preconditions without authorizing mutation.
    - Reject inferred SML.
    - Reject HVN_ABSORPTION_PROXY as true HVN/POC.
    - Require explicit geometry before any future D3D candidate can be eligible.
    - Never execute production D3D.
    - Never mutate campaigns.
    - Never confirm operator control.
    - Never affect score, rank, state, transition, gamma, options, edge,
      probability, targets, or trade signals.
    """
    from collections import Counter

    ENGINE_NAME = "D3V_D3D_DRY_RUN_CANDIDATE_PREFLIGHT_REVIEW"
    ENGINE_VERSION = "phase_d3v_d3d_dry_run_candidate_preflight_read_only_v1"

    def _base_payload():
        return {
            "engine": ENGINE_NAME + "_ENDPOINT",
            "version": ENGINE_VERSION,
            "endpoint": "/api/campaign/d3d-dry-run-candidate-preflight-review",
            "endpoint_status": "OK",
            "diagnostic_only": True,
            "read_only": True,
            "dry_run": True,
            "execution_authorized": False,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "production_confirmation_allowed": False,
            "operator_control_confirmed_by_this_engine": False,
            "operator_control_unconfirmed_by_this_engine": False,
            "operator_control_confirmation_impact": "NONE",
            "d3d_execution_allowed": False,
            "d3d_source_used_by_this_engine": False,
            "score_impact": "NONE",
            "rank_impact": "NONE",
            "state_impact": "NONE",
            "transition_impact": "NONE",
            "gamma_confirmation_impact": "NONE",
            "state_transition_enabled": False,
            "not_a_trade_signal": True,
            "d3u_protocol_policy": "D3V_APPLIES_D3U_PREFLIGHT_RULES_WITHOUT_MUTATION",
            "mutation_target_policy": "ONLY_FUTURE_D3D_MAY_MUTATE_EVIDENCE_OPERATOR_CONTROL_OPERATOR_CONTROL_CONFIRMED",
            "explicit_geometry_policy": "INFERRED_SML_REJECTED_FOR_D3D_PREFLIGHT_ELIGIBILITY",
            "hvn_proxy_policy": "HVN_ABSORPTION_PROXY_REJECTED_AS_TRUE_HVN_POC",
        }

    def _safe_counter(counter):
        return dict(sorted(counter.items(), key=lambda item: str(item[0])))

    def _as_dict(value):
        return value if isinstance(value, dict) else {}

    def _bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ["true", "1", "yes", "y"]
        return bool(value)

    def _rows_from_payload(payload):
        payload = _as_dict(payload)
        for key in [
            "rows",
            "review_rows",
            "validation_rows",
            "campaign_rows",
            "results",
            "items",
            "data",
        ]:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _key(row):
        row = _as_dict(row)
        return (
            str(row.get("symbol") or "").upper(),
            str(row.get("campaign_id") or ""),
        )

    def _symbol_key(row):
        row = _as_dict(row)
        return str(row.get("symbol") or "").upper()

    def _call_first_payload(names):
        for name in names:
            fn = globals().get(name)
            if callable(fn):
                return fn(), name
        raise RuntimeError("None of the expected payload functions are available: " + ", ".join(names))

    def _error_payload(stage, exc):
        payload = _base_payload()
        payload.update({
            "endpoint_status": "ERROR_RETURNED_NO_MUTATION",
            "error_stage": str(stage),
            "error": str(exc),
            "total_campaigns": 0,
            "rows_count": 0,
            "preflight_candidate_count": 0,
            "preflight_eligible_count": 0,
            "guardrail_failure_count": 0,
            "row_error_count": 0,
            "rows": [],
            "guardrail_failures": [],
            "row_errors": [],
        })
        return payload

    try:
        d3c2t_payload, d3c2t_function_used = _call_first_payload([
            "stealth_monitoring_diagnostic_review",
            "stealth_monitoring_diagnostic_endpoint",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3C2T_STEALTH_MONITORING", exc)

    try:
        d3c2r_payload, d3c2r_function_used = _call_first_payload([
            "hvn_poc_source_enrichment_review",
            "hvn_poc_source_enrichment_endpoint",
        ])
    except Exception as exc:
        return _error_payload("LOAD_D3C2R_HVN_POC_SOURCE_REVIEW", exc)

    d3c2t_rows = _rows_from_payload(d3c2t_payload)
    d3c2r_rows = _rows_from_payload(d3c2r_payload)

    d3c2r_by_key = {}
    d3c2r_by_symbol = {}

    for row in d3c2r_rows:
        row = _as_dict(row)
        d3c2r_by_key[_key(row)] = row
        d3c2r_by_symbol[_symbol_key(row)] = row

    rows = []
    guardrail_failures = []
    row_errors = []

    preflight_status_counter = Counter()
    preflight_priority_counter = Counter()
    block_reason_counter = Counter()
    candidate_counter = Counter()
    eligible_counter = Counter()
    no_drift_counter = Counter()

    for source_row in d3c2t_rows:
        try:
            source_row = _as_dict(source_row)
            source_r_row = d3c2r_by_key.get(_key(source_row)) or d3c2r_by_symbol.get(_symbol_key(source_row)) or {}

            monitor_priority = str(source_row.get("stealth_monitor_priority") or "")
            monitor_status = str(source_row.get("stealth_monitor_status") or "")
            plausibility_status = str(source_row.get("d3j_plausibility_status") or "")

            candidate_source = monitor_priority != "STANDARD_REVIEW_PRIORITY_READ_ONLY"

            complete_doctrine_legs = source_row.get("doctrine_leg_completeness") == "COMPLETE_DOCTRINE_LEG_SET_PRESENT_READ_ONLY"
            inferred_sml = _bool(source_row.get("inferred_sml"))
            explicit_geometry_sml = _bool(source_row.get("explicit_geometry_sml"))
            hvn_proxy_present = _bool(source_row.get("hvn_absorption_proxy_present"))
            true_hvn_poc_available = _bool(source_r_row.get("true_hvn_poc_available"))

            d3d_production_confirmed = _bool(source_row.get("d3j_d3d_production_confirmed"))
            legacy_operator_control_present = _bool(source_row.get("d3j_legacy_operator_control_confirmed"))

            block_reasons = []

            if not candidate_source:
                block_reasons.append("NOT_STEALTH_OR_LEGACY_SHADOW_MONITOR_CANDIDATE")

            if not complete_doctrine_legs:
                block_reasons.append("COMPLETE_DOCTRINE_LEG_SET_MISSING")

            if inferred_sml:
                block_reasons.append("INFERRED_SML_REJECTED_BY_D3U_PROTOCOL")

            if not explicit_geometry_sml:
                block_reasons.append("EXPLICIT_GEOMETRY_SML_MISSING")

            if hvn_proxy_present:
                block_reasons.append("HVN_ABSORPTION_PROXY_REJECTED_AS_TRUE_HVN_POC")

            if not true_hvn_poc_available:
                block_reasons.append("TRUE_HVN_POC_SOURCE_MISSING")

            if d3d_production_confirmed:
                block_reasons.append("ALREADY_D3D_PRODUCTION_CONFIRMED_REVIEW_REQUIRED")

            d3v_preflight_eligible = bool(
                candidate_source
                and complete_doctrine_legs
                and explicit_geometry_sml
                and not inferred_sml
                and not hvn_proxy_present
                and true_hvn_poc_available
                and not d3d_production_confirmed
            )

            if d3v_preflight_eligible:
                preflight_status = "D3D_DRY_RUN_PREFLIGHT_ELIGIBLE_UNMUTATED"
                preflight_priority = "D3D_DRY_RUN_PREFLIGHT_ELIGIBLE_REVIEW_ONLY"
            elif candidate_source:
                preflight_status = "D3D_DRY_RUN_PREFLIGHT_BLOCKED_UNMUTATED"
                preflight_priority = "D3D_DRY_RUN_BLOCKED_MONITOR_CANDIDATE_REVIEW_ONLY"
            else:
                preflight_status = "NOT_D3D_PREFLIGHT_CANDIDATE_READ_ONLY"
                preflight_priority = "STANDARD_REVIEW_PRIORITY_READ_ONLY"

            row = {
                "engine": ENGINE_NAME,
                "version": ENGINE_VERSION,

                "symbol": source_row.get("symbol"),
                "campaign_id": source_row.get("campaign_id"),
                "campaign_state": source_row.get("campaign_state"),

                "diagnostic_only": True,
                "read_only": True,
                "dry_run": True,
                "execution_authorized": False,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "production_confirmation_allowed": False,
                "operator_control_confirmed_by_this_engine": False,
                "operator_control_unconfirmed_by_this_engine": False,
                "operator_control_confirmation_impact": "NONE",
                "d3d_execution_allowed": False,
                "d3d_source_used_by_this_engine": False,
                "score_impact": "NONE",
                "rank_impact": "NONE",
                "state_impact": "NONE",
                "transition_impact": "NONE",
                "gamma_confirmation_impact": "NONE",
                "state_transition_enabled": False,
                "not_a_trade_signal": True,

                "d3v_preflight_status": preflight_status,
                "d3v_preflight_priority": preflight_priority,
                "d3v_preflight_candidate": bool(candidate_source),
                "d3v_preflight_eligible": bool(d3v_preflight_eligible),
                "d3v_block_reasons": block_reasons,

                "stealth_monitor_status": monitor_status,
                "stealth_monitor_priority": monitor_priority,
                "d3j_plausibility_status": plausibility_status,
                "legacy_operator_control_evidence_present": bool(legacy_operator_control_present),
                "d3d_production_confirmed": bool(d3d_production_confirmed),

                "complete_doctrine_legs": bool(complete_doctrine_legs),
                "doctrine_leg_completeness": source_row.get("doctrine_leg_completeness"),
                "explicit_geometry_sml": bool(explicit_geometry_sml),
                "inferred_sml": bool(inferred_sml),
                "hvn_absorption_proxy_present": bool(hvn_proxy_present),
                "true_hvn_poc_available": bool(true_hvn_poc_available),
                "true_hvn_poc_source_count": source_r_row.get("true_hvn_poc_source_count"),

                "source_payload_policy": "COMPACT_SUMMARY_ONLY",
                "source_d3c2t_summary": {
                    "symbol": source_row.get("symbol"),
                    "campaign_id": source_row.get("campaign_id"),
                    "campaign_state": source_row.get("campaign_state"),
                    "stealth_monitor_status": source_row.get("stealth_monitor_status"),
                    "stealth_monitor_priority": source_row.get("stealth_monitor_priority"),
                    "d3j_plausibility_status": source_row.get("d3j_plausibility_status"),
                    "doctrine_leg_completeness": source_row.get("doctrine_leg_completeness"),
                    "explicit_geometry_sml": source_row.get("explicit_geometry_sml"),
                    "inferred_sml": source_row.get("inferred_sml"),
                    "hvn_absorption_proxy_present": source_row.get("hvn_absorption_proxy_present"),
                },
                "source_d3c2r_summary": {
                    "symbol": source_r_row.get("symbol"),
                    "campaign_id": source_r_row.get("campaign_id"),
                    "hvn_poc_truth_status": source_r_row.get("hvn_poc_truth_status"),
                    "true_hvn_poc_available": source_r_row.get("true_hvn_poc_available"),
                    "true_hvn_poc_source_count": source_r_row.get("true_hvn_poc_source_count"),
                    "hvn_absorption_proxy_present": source_r_row.get("hvn_absorption_proxy_present"),
                },

                "d3v_no_drift_status": "PASS",
            }

            guardrail_ok = (
                row.get("diagnostic_only") is True
                and row.get("read_only") is True
                and row.get("dry_run") is True
                and row.get("execution_authorized") is False
                and row.get("writes_to_supabase") is False
                and row.get("mutates_campaigns") is False
                and row.get("production_confirmation_allowed") is False
                and row.get("operator_control_confirmed_by_this_engine") is False
                and row.get("operator_control_unconfirmed_by_this_engine") is False
                and row.get("operator_control_confirmation_impact") == "NONE"
                and row.get("d3d_execution_allowed") is False
                and row.get("d3d_source_used_by_this_engine") is False
                and row.get("score_impact") == "NONE"
                and row.get("rank_impact") == "NONE"
                and row.get("state_impact") == "NONE"
                and row.get("transition_impact") == "NONE"
                and row.get("gamma_confirmation_impact") == "NONE"
                and row.get("state_transition_enabled") is False
                and row.get("not_a_trade_signal") is True
                and row.get("d3v_no_drift_status") == "PASS"
            )

            if not guardrail_ok:
                guardrail_failures.append({
                    "symbol": row.get("symbol"),
                    "campaign_id": row.get("campaign_id"),
                    "reason": "D3V guardrail failure",
                    "row": row,
                })

            rows.append(row)

            preflight_status_counter[str(preflight_status)] += 1
            preflight_priority_counter[str(preflight_priority)] += 1
            candidate_counter[str(bool(candidate_source))] += 1
            eligible_counter[str(bool(d3v_preflight_eligible))] += 1
            no_drift_counter[str(row.get("d3v_no_drift_status"))] += 1

            for reason in block_reasons:
                block_reason_counter[str(reason)] += 1

        except Exception as exc:
            row_errors.append({
                "symbol": _as_dict(source_row).get("symbol"),
                "campaign_id": _as_dict(source_row).get("campaign_id"),
                "reason": "ROW_EVALUATION_ERROR",
                "error": str(exc),
            })

    rows = sorted(
        rows,
        key=lambda row: (
            0 if row.get("d3v_preflight_eligible") else
            1 if row.get("d3v_preflight_candidate") else 2,
            str(row.get("symbol") or ""),
        ),
    )

    payload = _base_payload()
    payload.update({
        "d3c2t_function_used": d3c2t_function_used,
        "d3c2r_function_used": d3c2r_function_used,
        "total_campaigns": len(d3c2t_rows),
        "d3c2t_rows_count": len(d3c2t_rows),
        "d3c2r_rows_count": len(d3c2r_rows),
        "rows_count": len(rows),
        "preflight_candidate_count": len([row for row in rows if row.get("d3v_preflight_candidate") is True]),
        "preflight_eligible_count": len([row for row in rows if row.get("d3v_preflight_eligible") is True]),
        "guardrail_failure_count": len(guardrail_failures),
        "row_error_count": len(row_errors),
        "guardrail_failures": guardrail_failures,
        "row_errors": row_errors,
        "d3v_preflight_status_distribution": _safe_counter(preflight_status_counter),
        "d3v_preflight_priority_distribution": _safe_counter(preflight_priority_counter),
        "d3v_candidate_distribution": _safe_counter(candidate_counter),
        "d3v_eligible_distribution": _safe_counter(eligible_counter),
        "d3v_block_reason_distribution": _safe_counter(block_reason_counter),
        "d3v_no_drift_status_distribution": _safe_counter(no_drift_counter),
        "rows": rows,
    })

    return payload

# === D4E2 LIVE READ-ONLY BAR SOURCE BRIDGE START ===
# This endpoint is intentionally read-only. It exists only to determine whether
# the deployed Render environment can access OHLCV bars using existing runtime
# credentials. It does not persist bars, write Supabase rows, mutate campaigns,
# construct HVN/POC, authorize D3D, or confirm operator control.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _d4e2_load_read_only_ohlcv,
    )
except Exception as _d4e2_import_exc:
    _d4e2_load_read_only_ohlcv = None
    _d4e2_import_error = f"{type(_d4e2_import_exc).__name__}: {_d4e2_import_exc}"
else:
    _d4e2_import_error = None


def _d4e2_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:50] or ["SPY"]


def _d4e2_compact_bar_probe_result(result):
    warnings = result.get("warnings") or []

    return {
        "symbol": result.get("symbol"),
        "adapter_status": result.get("adapter_status"),
        "source_type": result.get("source_type"),
        "source_quality": result.get("source_quality"),
        "bar_count": result.get("bar_count"),
        "window_start": result.get("window_start"),
        "window_end": result.get("window_end"),
        "warning_count": len(warnings),
        "warnings_sample": warnings[:3],
        "read_only": result.get("read_only"),
        "writes_to_supabase": result.get("writes_to_supabase"),
        "mutates_campaigns": result.get("mutates_campaigns"),
        "executes_d3d": result.get("executes_d3d"),
        "authorizes_d3d": result.get("authorizes_d3d"),
        "confirms_operator_control": result.get("confirms_operator_control"),
        "constructs_hvn_poc": result.get("constructs_hvn_poc"),
        "not_a_trade_signal": result.get("not_a_trade_signal"),
    }


@router.get("/d4e-read-only-live-bar-source-probe")
def d4e_read_only_live_bar_source_probe(
    symbols: str = "SPY",
    lookback_bars: int = 252,
    minimum_usable_bars: int = 30,
):
    requested_symbols = _d4e2_parse_symbols(symbols)

    results = []
    status_distribution = {}
    source_type_distribution = {}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _d4e2_load_read_only_ohlcv is None:
            result = {
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "window_start": None,
                "window_end": None,
                "warnings": [_d4e2_import_error or "adapter import failed"],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "confirms_operator_control": False,
                "constructs_hvn_poc": False,
                "not_a_trade_signal": True,
            }
        else:
            result = _d4e2_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe="1Day",
                lookback_bars=int(lookback_bars or 252),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={"symbol": symbol},
                timeout_seconds=25,
            )

        compact = _d4e2_compact_bar_probe_result(result)
        results.append(compact)

        status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))

        status_distribution[status] = status_distribution.get(status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1

        expected_false_fields = [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_hvn_poc",
        ]

        for field in expected_false_fields:
            if compact.get(field) is not False:
                guardrail_failures.append({
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": compact.get(field),
                })

        if compact.get("not_a_trade_signal") is not True:
            guardrail_failures.append({
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": compact.get("not_a_trade_signal"),
            })

    usable = [
        item for item in results
        if item.get("adapter_status") == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
        and int(item.get("bar_count") or 0) >= int(minimum_usable_bars or 30)
    ]

    if usable:
        source_status = "LIVE_READ_ONLY_BAR_SOURCE_AVAILABLE"
        d4f_readiness = "READY_FOR_D4F_READ_ONLY_HVN_POC_CONSTRUCTION_PROTOTYPE"
        source_gap_flags = [
            "D4E2_LIVE_READ_ONLY_SOURCE_BRIDGE_AVAILABLE",
            "D4E2_USABLE_OHLCV_BARS_CONFIRMED_IN_DEPLOYED_ENVIRONMENT",
            "D4E2_DOES_NOT_CONSTRUCT_HVN_POC",
            "D4E2_DOES_NOT_AUTHORIZE_D3D",
        ]
    else:
        source_status = "LIVE_READ_ONLY_BAR_SOURCE_NOT_AVAILABLE"
        d4f_readiness = "BLOCKED_UNTIL_LIVE_READ_ONLY_BAR_SOURCE_AVAILABLE"
        source_gap_flags = [
            "D4E2_LIVE_READ_ONLY_SOURCE_BRIDGE_AVAILABLE",
            "D4E2_NO_USABLE_OHLCV_BARS_CONFIRMED_IN_DEPLOYED_ENVIRONMENT",
            "D4E2_DOES_NOT_CONSTRUCT_HVN_POC",
            "D4E2_DOES_NOT_AUTHORIZE_D3D",
        ]

    return {
        "engine": "D4E2_LIVE_READ_ONLY_BAR_SOURCE_BRIDGE",
        "version": "phase_d4e2_live_read_only_bar_source_bridge_v1",
        "audit_status": "PASS_D4E2_LIVE_READ_ONLY_BAR_SOURCE_BRIDGE_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "constructs_hvn_poc": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "symbol_count_with_usable_bars": len(usable),
            "symbol_count_without_usable_bars": len(results) - len(usable),
            "lookback_bars": int(lookback_bars or 252),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
        },
        "runtime_distributions": {
            "adapter_status_distribution": status_distribution,
            "source_type_distribution": source_type_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "source_status": source_status,
            "d4f_readiness": d4f_readiness,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4e2_makes_any_campaign_d3d_eligible": False,
            "reason": "D4E.2 only probes deployed read-only OHLCV source access. It does not persist bars, mutate campaigns, construct HVN/POC, authorize D3D, or confirm operator control.",
        },
    }
# === D4E2 LIVE READ-ONLY BAR SOURCE BRIDGE END ===

# === D4F LIVE READ-ONLY HVN POC CONSTRUCTION START ===
# D4F is read-only. It constructs a prototype HVN/POC geometry from confirmed
# deployed OHLCV bars. It does not persist bars, write Supabase rows, mutate
# campaigns, authorize D3D, or confirm operator control.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _d4f_load_read_only_ohlcv,
    )
except Exception as _d4f_import_exc:
    _d4f_load_read_only_ohlcv = None
    _d4f_import_error = f"{type(_d4f_import_exc).__name__}: {_d4f_import_exc}"
else:
    _d4f_import_error = None


def _d4f_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:50] or ["SPY"]


def _d4f_float(value):
    try:
        parsed = float(value)
    except Exception:
        return None

    if not math.isfinite(parsed):
        return None

    return parsed


def _d4f_extract_raw_bars(adapter_result):
    for key in ["bars", "ohlcv_bars", "normalized_bars", "records", "data"]:
        value = adapter_result.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in ["bars", "ohlcv_bars", "records"]:
                nested_value = value.get(nested_key)

                if isinstance(nested_value, list):
                    return nested_value

    return []


def _d4f_normalize_bar(raw):
    if not isinstance(raw, dict):
        return None

    timestamp = (
        raw.get("timestamp")
        or raw.get("time")
        or raw.get("date")
        or raw.get("datetime")
        or raw.get("t")
    )

    open_value = _d4f_float(raw.get("open", raw.get("o")))
    high_value = _d4f_float(raw.get("high", raw.get("h")))
    low_value = _d4f_float(raw.get("low", raw.get("l")))
    close_value = _d4f_float(raw.get("close", raw.get("c", raw.get("price"))))
    volume_value = _d4f_float(raw.get("volume", raw.get("v", raw.get("vol"))))

    if open_value is None or high_value is None or low_value is None or close_value is None or volume_value is None:
        return None

    if high_value < low_value:
        return None

    if volume_value <= 0:
        return None

    return {
        "timestamp": str(timestamp) if timestamp is not None else None,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume_value,
    }


def _d4f_construct_ohlcv_profile(symbol, bars, bin_count):
    usable_bars = []

    for raw in bars:
        normalized = _d4f_normalize_bar(raw)

        if normalized is not None:
            usable_bars.append(normalized)

    if len(usable_bars) < 5:
        return {
            "symbol": symbol,
            "d4f_construction_status": "D4F_BLOCKED_INSUFFICIENT_NORMALIZED_BARS",
            "bars_received": len(bars),
            "bars_used": len(usable_bars),
            "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
            "hvn_poc_construction_classification": "NOT_CONSTRUCTED",
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "hvn_low": None,
            "hvn_high": None,
            "profile_bin_count": int(bin_count),
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Fewer than five normalized OHLCV bars were available.",
        }

    low_min = min(item["low"] for item in usable_bars)
    high_max = max(item["high"] for item in usable_bars)

    if not math.isfinite(low_min) or not math.isfinite(high_max) or high_max <= low_min:
        return {
            "symbol": symbol,
            "d4f_construction_status": "D4F_BLOCKED_INVALID_PRICE_RANGE",
            "bars_received": len(bars),
            "bars_used": len(usable_bars),
            "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
            "hvn_poc_construction_classification": "NOT_CONSTRUCTED",
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "hvn_low": None,
            "hvn_high": None,
            "profile_bin_count": int(bin_count),
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Normalized bars did not produce a valid high-low range.",
        }

    profile_bin_count = max(12, min(int(bin_count or 48), 160))
    width = (high_max - low_min) / profile_bin_count
    volumes = [0.0 for _ in range(profile_bin_count)]

    for bar in usable_bars:
        bar_low = bar["low"]
        bar_high = bar["high"]
        bar_volume = bar["volume"]

        if bar_high == bar_low:
            index = int((bar["close"] - low_min) / width)
            index = max(0, min(profile_bin_count - 1, index))
            volumes[index] += bar_volume
            continue

        start_index = max(0, min(profile_bin_count - 1, int((bar_low - low_min) / width)))
        end_index = max(0, min(profile_bin_count - 1, int((bar_high - low_min) / width)))

        touched = max(1, end_index - start_index + 1)
        allocated = bar_volume / touched

        for index in range(start_index, end_index + 1):
            volumes[index] += allocated

    max_volume = max(volumes)

    if max_volume <= 0:
        return {
            "symbol": symbol,
            "d4f_construction_status": "D4F_BLOCKED_EMPTY_VOLUME_PROFILE",
            "bars_received": len(bars),
            "bars_used": len(usable_bars),
            "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
            "hvn_poc_construction_classification": "NOT_CONSTRUCTED",
            "poc_price": None,
            "poc_low": None,
            "poc_high": None,
            "hvn_low": None,
            "hvn_high": None,
            "profile_bin_count": profile_bin_count,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Distributed volume profile contained no positive volume.",
        }

    poc_index = max(range(profile_bin_count), key=lambda idx: volumes[idx])
    poc_low = low_min + (poc_index * width)
    poc_high = poc_low + width
    poc_price = (poc_low + poc_high) / 2.0

    hvn_threshold = max_volume * 0.70

    left = poc_index
    right = poc_index

    while left - 1 >= 0 and volumes[left - 1] >= hvn_threshold:
        left -= 1

    while right + 1 < profile_bin_count and volumes[right + 1] >= hvn_threshold:
        right += 1

    hvn_low = low_min + (left * width)
    hvn_high = low_min + ((right + 1) * width)

    total_volume = sum(volumes)

    return {
        "symbol": symbol,
        "d4f_construction_status": "D4F_OK_HVN_POC_CONSTRUCTED_READ_ONLY",
        "bars_received": len(bars),
        "bars_used": len(usable_bars),
        "window_start": usable_bars[0].get("timestamp"),
        "window_end": usable_bars[-1].get("timestamp"),
        "method": "OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_PROTOTYPE",
        "hvn_poc_construction_classification": "OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
        "poc_price": round(poc_price, 6),
        "poc_low": round(poc_low, 6),
        "poc_high": round(poc_high, 6),
        "hvn_low": round(hvn_low, 6),
        "hvn_high": round(hvn_high, 6),
        "profile_low": round(low_min, 6),
        "profile_high": round(high_max, 6),
        "profile_bin_count": profile_bin_count,
        "profile_total_volume": round(total_volume, 6),
        "poc_bin_volume": round(max_volume, 6),
        "hvn_threshold_ratio": 0.70,
        "d3d_eligibility_from_this_endpoint": False,
        "source_limitation": "Daily OHLCV bars do not contain true intrabar volume-at-price. D4F constructs a read-only prototype profile and must pass D4G/D4H source-quality review before any D3D consideration.",
    }


@router.get("/d4f-read-only-hvn-poc-construction-prototype")
def d4f_read_only_hvn_poc_construction_prototype(
    symbols: str = "SPY",
    lookback_bars: int = 252,
    minimum_usable_bars: int = 30,
    profile_bins: int = 48,
):
    requested_symbols = _d4f_parse_symbols(symbols)

    results = []
    status_distribution = {}
    source_type_distribution = {}
    construction_distribution = {}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _d4f_load_read_only_ohlcv is None:
            adapter_result = {
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "bars": [],
                "warnings": [_d4f_import_error or "adapter import failed"],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "confirms_operator_control": False,
                "constructs_hvn_poc": False,
                "not_a_trade_signal": True,
            }
        else:
            adapter_result = _d4f_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe="1Day",
                lookback_bars=int(lookback_bars or 252),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={"symbol": symbol},
                timeout_seconds=25,
            )

        raw_bars = _d4f_extract_raw_bars(adapter_result)
        construction = _d4f_construct_ohlcv_profile(symbol, raw_bars, int(profile_bins or 48))

        warnings = adapter_result.get("warnings") or []

        compact = {
            "symbol": symbol,
            "adapter_status": adapter_result.get("adapter_status"),
            "source_type": adapter_result.get("source_type"),
            "source_quality": adapter_result.get("source_quality"),
            "adapter_bar_count": adapter_result.get("bar_count"),
            "adapter_warning_count": len(warnings),
            "adapter_warnings_sample": warnings[:3],
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "confirms_operator_control": False,
            "not_a_trade_signal": True,
            "construction": construction,
        }

        results.append(compact)

        adapter_status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))
        construction_status = str(construction.get("d4f_construction_status"))

        status_distribution[adapter_status] = status_distribution.get(adapter_status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1
        construction_distribution[construction_status] = construction_distribution.get(construction_status, 0) + 1

        expected_false_fields = [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
        ]

        for field in expected_false_fields:
            if compact.get(field) is not False:
                guardrail_failures.append({
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": compact.get(field),
                })

        if compact.get("not_a_trade_signal") is not True:
            guardrail_failures.append({
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": compact.get("not_a_trade_signal"),
            })

        if construction.get("d3d_eligibility_from_this_endpoint") is not False:
            guardrail_failures.append({
                "symbol": symbol,
                "field": "d3d_eligibility_from_this_endpoint",
                "expected": False,
                "actual": construction.get("d3d_eligibility_from_this_endpoint"),
            })

    constructed = [
        item for item in results
        if item.get("construction", {}).get("d4f_construction_status") == "D4F_OK_HVN_POC_CONSTRUCTED_READ_ONLY"
    ]

    if constructed:
        construction_status = "D4F_CONSTRUCTED_READ_ONLY_HVN_POC_PROTOTYPE"
        d4g_readiness = "READY_FOR_D4G_SOURCE_QUALITY_REVIEW"
        source_gap_flags = [
            "D4F_READ_ONLY_HVN_POC_PROTOTYPE_CONSTRUCTED",
            "D4F_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
            "D4F_DOES_NOT_AUTHORIZE_D3D",
            "D4F_DOES_NOT_CONFIRM_OPERATOR_CONTROL",
            "D4F_NEXT_PHASE_D4G_SOURCE_QUALITY_REVIEW_REQUIRED",
        ]
    else:
        construction_status = "D4F_NO_HVN_POC_PROTOTYPE_CONSTRUCTED"
        d4g_readiness = "BLOCKED_UNTIL_D4F_CONSTRUCTS_PROFILE"
        source_gap_flags = [
            "D4F_NO_HVN_POC_PROTOTYPE_CONSTRUCTED",
            "D4F_DOES_NOT_AUTHORIZE_D3D",
            "D4F_DOES_NOT_CONFIRM_OPERATOR_CONTROL",
        ]

    return {
        "engine": "D4F_LIVE_READ_ONLY_HVN_POC_CONSTRUCTION_PROTOTYPE",
        "version": "phase_d4f_live_read_only_hvn_poc_construction_v1",
        "audit_status": "PASS_D4F_LIVE_READ_ONLY_HVN_POC_CONSTRUCTION_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "symbol_count_with_constructed_hvn_poc_prototype": len(constructed),
            "symbol_count_without_constructed_hvn_poc_prototype": len(results) - len(constructed),
            "lookback_bars": int(lookback_bars or 252),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
            "profile_bins": int(profile_bins or 48),
        },
        "runtime_distributions": {
            "adapter_status_distribution": status_distribution,
            "source_type_distribution": source_type_distribution,
            "construction_status_distribution": construction_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "construction_status": construction_status,
            "d4g_readiness": d4g_readiness,
            "d4h_readiness": "BLOCKED_UNTIL_D4G_SOURCE_QUALITY_REVIEW",
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "d4f_makes_any_campaign_d3d_eligible": False,
            "reason": "D4F constructs a read-only OHLCV-derived HVN/POC prototype only. D4G and D4H must review source quality and doctrine compliance before D3D can even be considered.",
        },
    }
# === D4F LIVE READ-ONLY HVN POC CONSTRUCTION END ===

# === SRC2 READ-ONLY INTRADAY SOURCE PROBE START ===
# SRC2 is a read-only source-resolution probe. It tests whether the deployed
# market-data adapter can load intraday OHLCV bars. Intraday OHLCV is still not
# true exchange volume-at-price and does not authorize D3D.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _src2_load_read_only_ohlcv,
    )
except Exception as _src2_import_exc:
    _src2_load_read_only_ohlcv = None
    _src2_import_error = f"{type(_src2_import_exc).__name__}: {_src2_import_exc}"
else:
    _src2_import_error = None


def _src2_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src2_normalize_timeframe(timeframe):
    raw = str(timeframe or "1Min").strip()

    aliases = {
        "1": "1Min",
        "1m": "1Min",
        "1min": "1Min",
        "1minute": "1Min",
        "5": "5Min",
        "5m": "5Min",
        "5min": "5Min",
        "5minute": "5Min",
        "15": "15Min",
        "15m": "15Min",
        "15min": "15Min",
        "15minute": "15Min",
        "day": "1Day",
        "daily": "1Day",
        "1d": "1Day",
        "1day": "1Day",
    }

    key = raw.lower().replace(" ", "").replace("_", "")

    return aliases.get(key, raw)


def _src2_compact_result(result):
    warnings = result.get("warnings") or []

    return {
        "symbol": result.get("symbol"),
        "adapter_status": result.get("adapter_status"),
        "source_type": result.get("source_type"),
        "source_quality": result.get("source_quality"),
        "bar_count": result.get("bar_count"),
        "window_start": result.get("window_start"),
        "window_end": result.get("window_end"),
        "warning_count": len(warnings),
        "warnings_sample": warnings[:5],
        "read_only": result.get("read_only"),
        "writes_to_supabase": result.get("writes_to_supabase"),
        "mutates_campaigns": result.get("mutates_campaigns"),
        "executes_d3d": result.get("executes_d3d"),
        "authorizes_d3d": result.get("authorizes_d3d"),
        "confirms_operator_control": result.get("confirms_operator_control"),
        "constructs_hvn_poc": result.get("constructs_hvn_poc"),
        "not_a_trade_signal": result.get("not_a_trade_signal"),
    }


@router.get("/src2-read-only-intraday-source-probe")
def src2_read_only_intraday_source_probe(
    symbols: str = "SPY",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 30,
):
    requested_symbols = _src2_parse_symbols(symbols)
    requested_timeframe = _src2_normalize_timeframe(timeframe)

    results = []
    status_distribution = {}
    source_type_distribution = {}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _src2_load_read_only_ohlcv is None:
            result = {
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "window_start": None,
                "window_end": None,
                "warnings": [_src2_import_error or "adapter import failed"],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "confirms_operator_control": False,
                "constructs_hvn_poc": False,
                "not_a_trade_signal": True,
            }
        else:
            result = _src2_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe=requested_timeframe,
                lookback_bars=int(lookback_bars or 390),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={"symbol": symbol},
                timeout_seconds=30,
            )

        compact = _src2_compact_result(result)
        results.append(compact)

        adapter_status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))

        status_distribution[adapter_status] = status_distribution.get(adapter_status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1

        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_hvn_poc",
        ]:
            if compact.get(field) is not False:
                guardrail_failures.append({
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": compact.get(field),
                })

        if compact.get("not_a_trade_signal") is not True:
            guardrail_failures.append({
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": compact.get("not_a_trade_signal"),
            })

    usable = [
        item for item in results
        if item.get("adapter_status") == "ADAPTER_OK_BARS_LOADED_READ_ONLY"
        and int(item.get("bar_count") or 0) >= int(minimum_usable_bars or 30)
    ]

    if usable and requested_timeframe != "1Day":
        source_status = "SRC2_INTRADAY_OHLCV_SOURCE_AVAILABLE"
        next_action = "PROCEED_TO_SRC3_INTRADAY_PROFILE_SOURCE_QUALITY_REVIEW"
        source_gap_flags = [
            "SRC2_INTRADAY_OHLCV_CONFIRMED",
            "SRC2_INTRADAY_OHLCV_IS_NOT_TRUE_VOLUME_AT_PRICE",
            "SRC2_DOES_NOT_CONSTRUCT_HVN_POC",
            "SRC2_DOES_NOT_AUTHORIZE_D3D",
            "SRC2_NEXT_PHASE_SRC3_REQUIRED",
        ]
    elif usable:
        source_status = "SRC2_DAILY_OHLCV_ONLY_CONFIRMED"
        next_action = "STOP_SRC2_INTRADAY_SOURCE_NOT_CONFIRMED"
        source_gap_flags = [
            "SRC2_DAILY_OHLCV_AVAILABLE",
            "SRC2_INTRADAY_OHLCV_NOT_CONFIRMED",
            "SRC2_DOES_NOT_AUTHORIZE_D3D",
        ]
    else:
        source_status = "SRC2_NO_USABLE_INTRADAY_OHLCV_SOURCE_CONFIRMED"
        next_action = "STOP_SRC2_SOURCE_UNAVAILABLE_OR_CONFIGURE_PROVIDER"
        source_gap_flags = [
            "SRC2_NO_USABLE_INTRADAY_OHLCV_BARS",
            "SRC2_DOES_NOT_AUTHORIZE_D3D",
        ]

    return {
        "engine": "SRC2_READ_ONLY_INTRADAY_SOURCE_PROBE",
        "version": "source_resolution_src2_read_only_intraday_source_probe_v1",
        "audit_status": "PASS_SRC2_READ_ONLY_INTRADAY_SOURCE_PROBE_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "constructs_hvn_poc": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "requested_timeframe": requested_timeframe,
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "symbol_count_with_usable_intraday_bars": len(usable) if requested_timeframe != "1Day" else 0,
            "symbol_count_with_usable_bars": len(usable),
            "symbol_count_without_usable_bars": len(results) - len(usable),
            "lookback_bars": int(lookback_bars or 390),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
        },
        "runtime_distributions": {
            "adapter_status_distribution": status_distribution,
            "source_type_distribution": source_type_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "source_status": source_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src2_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC2 only probes intraday OHLCV availability. Intraday OHLCV is still not true exchange volume-at-price and does not authorize D3D.",
        },
    }
# === SRC2 READ-ONLY INTRADAY SOURCE PROBE END ===

# === SRC4 READ-ONLY INTRADAY PROFILE REFINEMENT START ===
# SRC4 is read-only. It constructs an intraday OHLCV-derived profile refinement
# prototype from 1-minute bars. It is still not true exchange volume-at-price,
# not tick data, not explicit SML, and it does not authorize D3D.

try:
    from backend.market_data.read_only_ohlcv_adapter import (
        load_read_only_ohlcv_bars_for_d4b_candidate as _src4_load_read_only_ohlcv,
    )
except Exception as _src4_import_exc:
    _src4_load_read_only_ohlcv = None
    _src4_import_error = f"{type(_src4_import_exc).__name__}: {_src4_import_exc}"
else:
    _src4_import_error = None


def _src4_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src4_float(value):
    try:
        parsed = float(value)
    except Exception:
        return None

    try:
        is_finite = math.isfinite(parsed)
    except Exception:
        is_finite = parsed == parsed and parsed not in [float("inf"), float("-inf")]

    if not is_finite:
        return None

    return parsed


def _src4_extract_raw_bars(adapter_result):
    for key in ["bars", "ohlcv_bars", "normalized_bars", "records", "data"]:
        value = adapter_result.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in ["bars", "ohlcv_bars", "records"]:
                nested_value = value.get(nested_key)

                if isinstance(nested_value, list):
                    return nested_value

    return []


def _src4_normalize_bar(raw):
    if not isinstance(raw, dict):
        return None

    timestamp = (
        raw.get("timestamp")
        or raw.get("time")
        or raw.get("date")
        or raw.get("datetime")
        or raw.get("t")
    )

    open_value = _src4_float(raw.get("open", raw.get("o")))
    high_value = _src4_float(raw.get("high", raw.get("h")))
    low_value = _src4_float(raw.get("low", raw.get("l")))
    close_value = _src4_float(raw.get("close", raw.get("c", raw.get("price"))))
    volume_value = _src4_float(raw.get("volume", raw.get("v", raw.get("vol"))))

    if open_value is None or high_value is None or low_value is None or close_value is None or volume_value is None:
        return None

    if high_value < low_value:
        return None

    if volume_value <= 0:
        return None

    return {
        "timestamp": str(timestamp) if timestamp is not None else None,
        "open": open_value,
        "high": high_value,
        "low": low_value,
        "close": close_value,
        "volume": volume_value,
    }


def _src4_construct_intraday_profile(symbol, raw_bars, profile_bins):
    bars = []

    for raw in raw_bars:
        normalized = _src4_normalize_bar(raw)

        if normalized is not None:
            bars.append(normalized)

    if len(bars) < 30:
        return {
            "symbol": symbol,
            "src4_profile_status": "SRC4_BLOCKED_INSUFFICIENT_INTRADAY_BARS",
            "bars_received": len(raw_bars),
            "bars_used": len(bars),
            "prototype_profile_constructed": False,
            "constructs_true_hvn_poc": False,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Fewer than 30 normalized intraday OHLCV bars were available.",
        }

    low_min = min(item["low"] for item in bars)
    high_max = max(item["high"] for item in bars)

    if high_max <= low_min:
        return {
            "symbol": symbol,
            "src4_profile_status": "SRC4_BLOCKED_INVALID_INTRADAY_PRICE_RANGE",
            "bars_received": len(raw_bars),
            "bars_used": len(bars),
            "prototype_profile_constructed": False,
            "constructs_true_hvn_poc": False,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Intraday bars did not produce a valid high-low range.",
        }

    bin_count = max(24, min(int(profile_bins or 96), 240))
    width = (high_max - low_min) / bin_count
    volumes = [0.0 for _ in range(bin_count)]

    for bar in bars:
        bar_low = bar["low"]
        bar_high = bar["high"]
        bar_volume = bar["volume"]

        if bar_high == bar_low:
            index = int((bar["close"] - low_min) / width)
            index = max(0, min(bin_count - 1, index))
            volumes[index] += bar_volume
            continue

        start_index = max(0, min(bin_count - 1, int((bar_low - low_min) / width)))
        end_index = max(0, min(bin_count - 1, int((bar_high - low_min) / width)))

        touched = max(1, end_index - start_index + 1)
        allocated = bar_volume / touched

        for index in range(start_index, end_index + 1):
            volumes[index] += allocated

    max_volume = max(volumes)
    total_volume = sum(volumes)

    if max_volume <= 0 or total_volume <= 0:
        return {
            "symbol": symbol,
            "src4_profile_status": "SRC4_BLOCKED_EMPTY_INTRADAY_PROFILE",
            "bars_received": len(raw_bars),
            "bars_used": len(bars),
            "prototype_profile_constructed": False,
            "constructs_true_hvn_poc": False,
            "d3d_eligibility_from_this_endpoint": False,
            "warning": "Intraday distributed profile contained no positive volume.",
        }

    poc_index = max(range(bin_count), key=lambda idx: volumes[idx])
    poc_low = low_min + (poc_index * width)
    poc_high = poc_low + width
    poc_price = (poc_low + poc_high) / 2.0

    hvn_threshold = max_volume * 0.70
    left = poc_index
    right = poc_index

    while left - 1 >= 0 and volumes[left - 1] >= hvn_threshold:
        left -= 1

    while right + 1 < bin_count and volumes[right + 1] >= hvn_threshold:
        right += 1

    hvn_low = low_min + (left * width)
    hvn_high = low_min + ((right + 1) * width)

    ranked_indices = sorted(range(bin_count), key=lambda idx: volumes[idx], reverse=True)[:5]
    top_bins = []

    for index in ranked_indices:
        bin_low = low_min + (index * width)
        bin_high = bin_low + width
        top_bins.append(
            {
                "rank": len(top_bins) + 1,
                "bin_index": index,
                "bin_low": round(bin_low, 6),
                "bin_high": round(bin_high, 6),
                "bin_mid": round((bin_low + bin_high) / 2.0, 6),
                "allocated_volume": round(volumes[index], 6),
                "volume_share": round(volumes[index] / total_volume, 8),
            }
        )

    return {
        "symbol": symbol,
        "src4_profile_status": "SRC4_OK_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY",
        "bars_received": len(raw_bars),
        "bars_used": len(bars),
        "window_start": bars[0].get("timestamp"),
        "window_end": bars[-1].get("timestamp"),
        "method": "INTRADAY_OHLCV_RANGE_DISTRIBUTED_VOLUME_PROFILE_REFINEMENT",
        "profile_classification": "INTRADAY_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
        "prototype_profile_constructed": True,
        "constructs_true_hvn_poc": False,
        "poc_price": round(poc_price, 6),
        "poc_low": round(poc_low, 6),
        "poc_high": round(poc_high, 6),
        "hvn_low": round(hvn_low, 6),
        "hvn_high": round(hvn_high, 6),
        "profile_low": round(low_min, 6),
        "profile_high": round(high_max, 6),
        "profile_bin_count": bin_count,
        "profile_total_volume": round(total_volume, 6),
        "poc_bin_volume": round(max_volume, 6),
        "hvn_threshold_ratio": 0.70,
        "top_intraday_profile_bins": top_bins,
        "d3d_eligibility_from_this_endpoint": False,
        "source_limitation": "1-minute OHLCV bars improve profile resolution versus daily OHLCV, but volume remains distributed across bar ranges. This is not true exchange volume-at-price, not tick data, and not explicit SML.",
    }


@router.get("/src4-read-only-intraday-profile-refinement-prototype")
def src4_read_only_intraday_profile_refinement_prototype(
    symbols: str = "SPY",
    timeframe: str = "1Min",
    lookback_bars: int = 390,
    minimum_usable_bars: int = 30,
    profile_bins: int = 96,
):
    requested_symbols = _src4_parse_symbols(symbols)

    results = []
    adapter_status_distribution = {}
    source_type_distribution = {}
    profile_status_distribution = {}
    guardrail_failures = []

    for symbol in requested_symbols:
        if _src4_load_read_only_ohlcv is None:
            adapter_result = {
                "symbol": symbol,
                "adapter_status": "ADAPTER_BLOCKED_IMPORT_FAILED",
                "source_type": "NONE",
                "source_quality": "UNAVAILABLE",
                "bar_count": 0,
                "bars": [],
                "warnings": [_src4_import_error or "adapter import failed"],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "confirms_operator_control": False,
                "constructs_hvn_poc": False,
                "not_a_trade_signal": True,
            }
        else:
            adapter_result = _src4_load_read_only_ohlcv(
                symbol=symbol,
                requested_timeframe=str(timeframe or "1Min"),
                lookback_bars=int(lookback_bars or 390),
                minimum_usable_bars=int(minimum_usable_bars or 30),
                source_priority_policy=[
                    "alpaca_rest_read_only",
                    "supabase_rest_read_only",
                    "existing_non_mutating_runtime_payload_bars",
                ],
                candidate_payload={"symbol": symbol},
                timeout_seconds=35,
            )

        raw_bars = _src4_extract_raw_bars(adapter_result)
        profile = _src4_construct_intraday_profile(symbol, raw_bars, int(profile_bins or 96))
        warnings = adapter_result.get("warnings") or []

        compact = {
            "symbol": symbol,
            "requested_timeframe": str(timeframe or "1Min"),
            "adapter_status": adapter_result.get("adapter_status"),
            "source_type": adapter_result.get("source_type"),
            "source_quality": adapter_result.get("source_quality"),
            "adapter_bar_count": adapter_result.get("bar_count"),
            "adapter_warning_count": len(warnings),
            "adapter_warnings_sample": warnings[:5],
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "confirms_operator_control": False,
            "constructs_true_hvn_poc": False,
            "not_a_trade_signal": True,
            "profile": profile,
        }

        results.append(compact)

        adapter_status = str(compact.get("adapter_status"))
        source_type = str(compact.get("source_type"))
        profile_status = str(profile.get("src4_profile_status"))

        adapter_status_distribution[adapter_status] = adapter_status_distribution.get(adapter_status, 0) + 1
        source_type_distribution[source_type] = source_type_distribution.get(source_type, 0) + 1
        profile_status_distribution[profile_status] = profile_status_distribution.get(profile_status, 0) + 1

        for field in [
            "writes_to_supabase",
            "mutates_campaigns",
            "executes_d3d",
            "authorizes_d3d",
            "confirms_operator_control",
            "constructs_true_hvn_poc",
        ]:
            if compact.get(field) is not False:
                guardrail_failures.append({
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": compact.get(field),
                })

        if compact.get("not_a_trade_signal") is not True:
            guardrail_failures.append({
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": compact.get("not_a_trade_signal"),
            })

        if profile.get("d3d_eligibility_from_this_endpoint") is not False:
            guardrail_failures.append({
                "symbol": symbol,
                "field": "profile.d3d_eligibility_from_this_endpoint",
                "expected": False,
                "actual": profile.get("d3d_eligibility_from_this_endpoint"),
            })

    constructed = [
        item for item in results
        if item.get("profile", {}).get("src4_profile_status")
        == "SRC4_OK_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY"
    ]

    if constructed:
        profile_status = "SRC4_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED_READ_ONLY"
        next_action = "PROCEED_TO_SRC5_INTRADAY_PROFILE_DOCTRINE_REVIEW"
        source_gap_flags = [
            "SRC4_INTRADAY_PROFILE_REFINEMENT_PROTOTYPE_CONSTRUCTED",
            "SRC4_INTRADAY_OHLCV_DERIVED_APPROXIMATION_NOT_TRUE_VOLUME_AT_PRICE",
            "SRC4_DOES_NOT_AUTHORIZE_D3D",
            "SRC4_DOES_NOT_CONFIRM_OPERATOR_CONTROL",
            "SRC4_NEXT_PHASE_SRC5_DOCTRINE_REVIEW_REQUIRED",
        ]
    else:
        profile_status = "SRC4_NO_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED"
        next_action = "STOP_UNTIL_SRC4_PROFILE_FAILURES_RESOLVED"
        source_gap_flags = [
            "SRC4_NO_INTRADAY_PROFILE_REFINEMENT_CONSTRUCTED",
            "SRC4_DOES_NOT_AUTHORIZE_D3D",
        ]

    return {
        "engine": "SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_PROTOTYPE",
        "version": "source_resolution_src4_intraday_profile_refinement_v1",
        "audit_status": "PASS_SRC4_READ_ONLY_INTRADAY_PROFILE_REFINEMENT_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "constructs_true_hvn_poc": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "requested_timeframe": str(timeframe or "1Min"),
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "symbol_count_with_intraday_profile_refinement": len(constructed),
            "symbol_count_without_intraday_profile_refinement": len(results) - len(constructed),
            "lookback_bars": int(lookback_bars or 390),
            "minimum_usable_bars": int(minimum_usable_bars or 30),
            "profile_bins": int(profile_bins or 96),
        },
        "runtime_distributions": {
            "adapter_status_distribution": adapter_status_distribution,
            "source_type_distribution": source_type_distribution,
            "profile_status_distribution": profile_status_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "profile_status": profile_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src4_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC4 constructs a read-only intraday OHLCV-derived profile refinement prototype only. It is not true volume-at-price, not tick data, not explicit SML, and does not authorize D3D.",
        },
    }
# === SRC4 READ-ONLY INTRADAY PROFILE REFINEMENT END ===

# === SRC7C READ-ONLY RUNTIME EXPLICIT SML SOURCE PROBE START ===
# SRC7C probes the deployed runtime explicit SML adapter created in SRC7B.
# It is read-only and cannot authorize D3D.

try:
    from backend.structural_sources.explicit_sml_source_adapter import (
        load_explicit_sml_records_read_only as _src7c_load_explicit_sml_records_read_only,
    )
except Exception as _src7c_import_exc:
    _src7c_load_explicit_sml_records_read_only = None
    _src7c_import_error = f"{type(_src7c_import_exc).__name__}: {_src7c_import_exc}"
else:
    _src7c_import_error = None


def _src7c_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src7c_fixture_record(symbol):
    return {
        "symbol": str(symbol or "SPY").strip().upper(),
        "campaign_id": "fixture-only-not-runtime",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "fixture_explicit_manual_markup_chart_review",
        "source_timestamp_utc": "2026-07-06T22:00:00Z",
        "observed_window_start_utc": "2023-04-24T08:00:00Z",
        "observed_window_end_utc": "2023-04-24T16:06:00Z",
        "is_explicit": True,
        "is_inferred": False,
        "is_proxy": False,
        "is_hvn_absorption_proxy": False,
        "derived_from_score": False,
        "derived_from_rank": False,
        "derived_from_probability": False,
        "derived_from_edge": False,
        "derived_from_expected_return": False,
        "derived_from_target_projection": False,
        "derived_from_trade_signal": False,
        "derived_from_gamma_options_overlay": False,
        "derived_from_ohlcv_profile_approximation": False,
        "confirms_operator_control": False,
        "authorizes_d3d": False,
        "mutates_campaigns": False,
        "writes_to_supabase": False,
        "eligible_for_immediate_d3d_mutation": False,
    }


def _src7c_invalid_fixture_record(symbol):
    record = _src7c_fixture_record(symbol)
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    return record


def _src7c_candidate_payload_for_fixture_mode(symbol, fixture_mode):
    mode = str(fixture_mode or "none").strip().lower()

    if mode == "valid":
        return {"explicit_sml_records": [_src7c_fixture_record(symbol)]}

    if mode == "invalid":
        return {"explicit_sml_records": [_src7c_invalid_fixture_record(symbol)]}

    if mode == "mixed":
        return {
            "explicit_sml_records": [
                _src7c_fixture_record(symbol),
                _src7c_invalid_fixture_record(symbol),
            ]
        }

    return {}


def _src7c_guardrail_failures_for_adapter_result(symbol, adapter_result):
    failures = []

    expected_false_fields = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed_by_this_adapter",
        "operator_control_unconfirmed_by_this_adapter",
        "src7b_makes_any_campaign_d3d_eligible",
    ]

    for field in expected_false_fields:
        if adapter_result.get(field) is not False:
            failures.append(
                {
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": adapter_result.get(field),
                }
            )

    if adapter_result.get("read_only") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "read_only",
                "expected": True,
                "actual": adapter_result.get("read_only"),
            }
        )

    if adapter_result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": adapter_result.get("not_a_trade_signal"),
            }
        )

    if adapter_result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "symbol": symbol,
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": adapter_result.get("d3d_execution_recommendation"),
            }
        )

    return failures


@router.get("/src7c-read-only-runtime-explicit-sml-source-probe")
def src7c_read_only_runtime_explicit_sml_source_probe(
    symbols: str = "SPY",
    fixture_mode: str = "none",
    json_file_path: str = None,
):
    requested_symbols = _src7c_parse_symbols(symbols)
    normalized_fixture_mode = str(fixture_mode or "none").strip().lower()

    results = []
    adapter_status_distribution = {}
    source_quality_distribution = {}
    guardrail_failures = []

    total_raw_records = 0
    total_symbol_filtered_records = 0
    total_valid_records = 0
    total_invalid_records = 0

    for symbol in requested_symbols:
        if _src7c_load_explicit_sml_records_read_only is None:
            adapter_result = {
                "symbol": symbol,
                "adapter_status": "SRC7C_BLOCKED_IMPORT_FAILED",
                "source_quality": "ADAPTER_IMPORT_FAILED",
                "source_policy": [],
                "attempted_sources": [],
                "selected_source": None,
                "raw_record_count": 0,
                "symbol_filtered_record_count": 0,
                "valid_record_count": 0,
                "invalid_record_count": 0,
                "warnings": [_src7c_import_error or "SRC7B adapter import failed"],
                "policy_failure_count": 0,
                "policy_failures": [],
                "validation_results": [],
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed_by_this_adapter": False,
                "operator_control_unconfirmed_by_this_adapter": False,
                "not_a_trade_signal": True,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "src7b_makes_any_campaign_d3d_eligible": False,
            }
        else:
            candidate_payload = _src7c_candidate_payload_for_fixture_mode(symbol, normalized_fixture_mode)

            adapter_result = _src7c_load_explicit_sml_records_read_only(
                symbol=symbol,
                candidate_payload=candidate_payload,
                json_file_path=json_file_path,
                source_priority_policy=[
                    "existing_non_mutating_runtime_payload_explicit_sml_records",
                    "read_only_json_file_explicit_sml_records",
                ],
            )

        total_raw_records += int(adapter_result.get("raw_record_count") or 0)
        total_symbol_filtered_records += int(adapter_result.get("symbol_filtered_record_count") or 0)
        total_valid_records += int(adapter_result.get("valid_record_count") or 0)
        total_invalid_records += int(adapter_result.get("invalid_record_count") or 0)

        adapter_status = str(adapter_result.get("adapter_status"))
        source_quality = str(adapter_result.get("source_quality"))

        adapter_status_distribution[adapter_status] = adapter_status_distribution.get(adapter_status, 0) + 1
        source_quality_distribution[source_quality] = source_quality_distribution.get(source_quality, 0) + 1

        guardrail_failures.extend(_src7c_guardrail_failures_for_adapter_result(symbol, adapter_result))

        results.append(adapter_result)

    fixture_used = normalized_fixture_mode in ["valid", "invalid", "mixed"]

    if fixture_used and total_valid_records > 0:
        source_status = "SRC7C_FIXTURE_VALIDATION_CONFIRMED_READ_ONLY"
        next_action = "PROBE_RUNTIME_MODE_OR_PROCEED_TO_SRC7D_EXPLICIT_SOURCE_TEMPLATE"
        source_gap_flags = [
            "SRC7C_FIXTURE_ONLY_VALIDATION_CONFIRMED",
            "SRC7C_NO_PRODUCTION_RUNTIME_EVIDENCE_CREATED",
            "SRC7C_DOES_NOT_AUTHORIZE_D3D",
        ]
    elif total_valid_records > 0:
        source_status = "SRC7C_RUNTIME_VALID_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY"
        next_action = "PROCEED_TO_SRC7D_DRY_RUN_EXPLICIT_SML_PREFLIGHT_VALIDATOR"
        source_gap_flags = [
            "SRC7C_RUNTIME_EXPLICIT_SML_RECORDS_FOUND",
            "SRC7C_D3D_STILL_BLOCKED_PENDING_DRY_RUN_PREFLIGHT",
        ]
    elif total_raw_records == 0:
        source_status = "SRC7C_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND_READ_ONLY"
        next_action = "PROCEED_TO_SRC7D_EXPLICIT_SML_SOURCE_TEMPLATE_OR_ADD_RUNTIME_SOURCE"
        source_gap_flags = [
            "SRC7C_RUNTIME_ADAPTER_DEPLOYED",
            "SRC7C_NO_RUNTIME_EXPLICIT_SML_RECORDS_FOUND",
            "SRC7C_D3D_REMAINS_BLOCKED",
        ]
    else:
        source_status = "SRC7C_RECORDS_PRESENT_BUT_CONTRACT_REJECTED_ALL_READ_ONLY"
        next_action = "STOP_OR_REPAIR_EXPLICIT_SML_RECORD_SOURCE"
        source_gap_flags = [
            "SRC7C_RECORDS_PRESENT_BUT_INVALID",
            "SRC7C_D3D_REMAINS_BLOCKED",
        ]

    return {
        "engine": "SRC7C_READ_ONLY_RUNTIME_EXPLICIT_SML_SOURCE_PROBE",
        "version": "source_resolution_src7c_read_only_runtime_explicit_sml_source_probe_v1",
        "audit_status": "PASS_SRC7C_READ_ONLY_RUNTIME_EXPLICIT_SML_SOURCE_PROBE_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "fixture_mode": normalized_fixture_mode,
        "fixture_used": fixture_used,
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "raw_record_count": total_raw_records,
            "symbol_filtered_record_count": total_symbol_filtered_records,
            "valid_record_count": total_valid_records,
            "invalid_record_count": total_invalid_records,
            "symbol_count_with_valid_explicit_sml_records": sum(
                1 for item in results if int(item.get("valid_record_count") or 0) > 0
            ),
            "symbol_count_without_valid_explicit_sml_records": sum(
                1 for item in results if int(item.get("valid_record_count") or 0) == 0
            ),
        },
        "runtime_distributions": {
            "adapter_status_distribution": adapter_status_distribution,
            "source_quality_distribution": source_quality_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "source_status": source_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7c_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC7C probes explicit SML runtime source availability through the SRC7B read-only adapter. It does not persist records, mutate campaigns, confirm operator control, or authorize D3D.",
        },
    }
# === SRC7C READ-ONLY RUNTIME EXPLICIT SML SOURCE PROBE END ===

# === SRC7G RUNTIME DRY-RUN PREFLIGHT ENDPOINT START ===
# SRC7G exposes the deployed dry-run, read-only, no-drift eligibility review.
# It can show source-only dry-run readiness, but it cannot authorize D3D.

try:
    from backend.structural_sources.explicit_sml_no_drift_eligibility_review import (
        run_no_drift_dry_run_eligibility_review as _src7g_run_no_drift_dry_run_eligibility_review,
    )
except Exception as _src7g_import_exc:
    _src7g_run_no_drift_dry_run_eligibility_review = None
    _src7g_import_error = f"{type(_src7g_import_exc).__name__}: {_src7g_import_exc}"
else:
    _src7g_import_error = None


def _src7g_parse_symbols(symbols):
    if symbols is None:
        return ["SPY"]

    cleaned = []

    for raw in str(symbols).replace(";", ",").split(","):
        symbol = raw.strip().upper()

        if symbol and symbol not in cleaned:
            cleaned.append(symbol)

    return cleaned[:25] or ["SPY"]


def _src7g_fixture_record(symbol):
    normalized_symbol = str(symbol or "SPY").strip().upper()

    return {
        "symbol": normalized_symbol,
        "campaign_id": f"fixture-{normalized_symbol.lower()}",
        "level_type": "EXPLICIT_SUPPORT",
        "price_low": 411.42,
        "price_mid": 411.44,
        "price_high": 411.48,
        "source_method": "MANUAL_STRUCTURAL_MARKUP",
        "source_reference": "fixture_explicit_manual_markup_chart_review",
        "source_timestamp_utc": "2026-07-06T22:00:00Z",
        "observed_window_start_utc": "2023-04-24T08:00:00Z",
        "observed_window_end_utc": "2023-04-24T16:06:00Z",
        "is_explicit": True,
        "is_inferred": False,
        "is_proxy": False,
        "is_hvn_absorption_proxy": False,
        "derived_from_score": False,
        "derived_from_rank": False,
        "derived_from_probability": False,
        "derived_from_edge": False,
        "derived_from_expected_return": False,
        "derived_from_target_projection": False,
        "derived_from_trade_signal": False,
        "derived_from_gamma_options_overlay": False,
        "derived_from_ohlcv_profile_approximation": False,
        "confirms_operator_control": False,
        "authorizes_d3d": False,
        "mutates_campaigns": False,
        "writes_to_supabase": False,
        "eligible_for_immediate_d3d_mutation": False,
    }


def _src7g_invalid_fixture_record(symbol):
    record = _src7g_fixture_record(symbol)
    record["source_method"] = "HVN_ABSORPTION_PROXY"
    record["is_proxy"] = True
    record["is_hvn_absorption_proxy"] = True
    return record


def _src7g_candidate_payload_for_fixture_mode(symbol, fixture_mode):
    mode = str(fixture_mode or "none").strip().lower()

    if mode == "valid":
        return {"explicit_sml_records": [_src7g_fixture_record(symbol)]}

    if mode == "invalid":
        return {"explicit_sml_records": [_src7g_invalid_fixture_record(symbol)]}

    if mode == "mixed":
        return {
            "explicit_sml_records": [
                _src7g_fixture_record(symbol),
                _src7g_invalid_fixture_record(symbol),
            ]
        }

    return {}


def _src7g_guardrail_failures_for_result(symbol, result):
    failures = []

    expected_false_fields = [
        "writes_to_supabase",
        "mutates_campaigns",
        "executes_d3d",
        "authorizes_d3d",
        "operator_control_confirmed_by_this_review",
        "operator_control_unconfirmed_by_this_review",
        "production_d3d_eligibility_satisfied",
        "d3d_execution_authorized",
        "production_mutation_authorized",
        "operator_control_confirmed",
        "src7f_makes_any_campaign_d3d_eligible",
    ]

    for field in expected_false_fields:
        if result.get(field) is not False:
            failures.append(
                {
                    "symbol": symbol,
                    "field": field,
                    "expected": False,
                    "actual": result.get(field),
                }
            )

    if result.get("read_only") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "read_only",
                "expected": True,
                "actual": result.get("read_only"),
            }
        )

    if result.get("dry_run") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "dry_run",
                "expected": True,
                "actual": result.get("dry_run"),
            }
        )

    if result.get("not_a_trade_signal") is not True:
        failures.append(
            {
                "symbol": symbol,
                "field": "not_a_trade_signal",
                "expected": True,
                "actual": result.get("not_a_trade_signal"),
            }
        )

    if result.get("d3d_execution_recommendation") != "DO_NOT_EXECUTE_D3D":
        failures.append(
            {
                "symbol": symbol,
                "field": "d3d_execution_recommendation",
                "expected": "DO_NOT_EXECUTE_D3D",
                "actual": result.get("d3d_execution_recommendation"),
            }
        )

    if int(result.get("guardrail_failure_count") or 0) != 0:
        failures.append(
            {
                "symbol": symbol,
                "field": "guardrail_failure_count",
                "expected": 0,
                "actual": result.get("guardrail_failure_count"),
            }
        )

    return failures


@router.get("/src7g-runtime-dry-run-preflight-endpoint")
def src7g_runtime_dry_run_preflight_endpoint(
    symbols: str = "SPY",
    fixture_mode: str = "none",
    json_file_path: str = None,
):
    requested_symbols = _src7g_parse_symbols(symbols)
    normalized_fixture_mode = str(fixture_mode or "none").strip().lower()

    results = []
    guardrail_failures = []
    status_distribution = {}
    source_only_distribution = {}

    total_source_only_ready = 0
    total_production_eligible = 0

    for symbol in requested_symbols:
        if _src7g_run_no_drift_dry_run_eligibility_review is None:
            result = {
                "review": "SRC7F_NO_DRIFT_DRY_RUN_ELIGIBILITY_REVIEW",
                "review_version": "source_resolution_src7f_no_drift_dry_run_eligibility_review_v1",
                "diagnostic_only": True,
                "dry_run": True,
                "read_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed_by_this_review": False,
                "operator_control_unconfirmed_by_this_review": False,
                "not_a_trade_signal": True,
                "candidate": {
                    "symbol": symbol,
                    "campaign_id": f"runtime-probe-{symbol.lower()}",
                },
                "source_binding_requirement_satisfied": False,
                "no_drift_requirement_satisfied": False,
                "source_only_dry_run_eligibility_satisfied": False,
                "production_d3d_eligibility_satisfied": False,
                "d3d_execution_authorized": False,
                "production_mutation_authorized": False,
                "operator_control_confirmed": False,
                "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                "src7f_makes_any_campaign_d3d_eligible": False,
                "guardrail_failure_count": 0,
                "guardrail_failures": [],
                "runtime_decision": {
                    "src7f_status": "SRC7G_BLOCKED_IMPORT_FAILED",
                    "next_action": "STOP_UNTIL_SRC7F_IMPORT_REPAIRED",
                    "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
                    "src7f_makes_any_campaign_d3d_eligible": False,
                    "reason": _src7g_import_error or "SRC7F import failed.",
                },
            }
        else:
            candidate = {
                "symbol": symbol,
                "campaign_id": f"runtime-probe-{symbol.lower()}",
            }
            candidate_payload = _src7g_candidate_payload_for_fixture_mode(symbol, normalized_fixture_mode)

            result = _src7g_run_no_drift_dry_run_eligibility_review(
                candidate=candidate,
                candidate_payload=candidate_payload,
                json_file_path=json_file_path,
                source_priority_policy=[
                    "existing_non_mutating_runtime_payload_explicit_sml_records",
                    "read_only_json_file_explicit_sml_records",
                ],
            )

        status = str((result.get("runtime_decision") or {}).get("src7f_status"))
        status_distribution[status] = status_distribution.get(status, 0) + 1

        source_only_value = str(result.get("source_only_dry_run_eligibility_satisfied"))
        source_only_distribution[source_only_value] = source_only_distribution.get(source_only_value, 0) + 1

        if result.get("source_only_dry_run_eligibility_satisfied") is True:
            total_source_only_ready += 1

        if result.get("production_d3d_eligibility_satisfied") is True:
            total_production_eligible += 1

        guardrail_failures.extend(_src7g_guardrail_failures_for_result(symbol, result))
        results.append(result)

    fixture_used = normalized_fixture_mode in ["valid", "invalid", "mixed"]

    if fixture_used and total_source_only_ready > 0:
        preflight_status = "SRC7G_FIXTURE_SOURCE_ONLY_DRY_RUN_PREFLIGHT_CONFIRMED"
        next_action = "PROBE_RUNTIME_MODE_OR_PROCEED_TO_SRC7H_RUNTIME_SOURCE_MATERIALIZATION_PLAN"
        source_gap_flags = [
            "SRC7G_FIXTURE_ONLY_SOURCE_READY",
            "SRC7G_NO_PRODUCTION_RUNTIME_EVIDENCE_CREATED",
            "SRC7G_PRODUCTION_D3D_ELIGIBILITY_FALSE",
            "SRC7G_D3D_REMAINS_BLOCKED",
        ]
    elif total_source_only_ready > 0:
        preflight_status = "SRC7G_RUNTIME_SOURCE_ONLY_DRY_RUN_PREFLIGHT_READY"
        next_action = "PROCEED_TO_SRC7H_PRODUCTION_BLOCK_REVIEW_BEFORE_ANY_D3D"
        source_gap_flags = [
            "SRC7G_RUNTIME_SOURCE_ONLY_READY",
            "SRC7G_PRODUCTION_D3D_ELIGIBILITY_FALSE",
            "SRC7G_D3D_REMAINS_BLOCKED_PENDING_FINAL_DOCTRINE_REVIEW",
        ]
    else:
        preflight_status = "SRC7G_NO_RUNTIME_SOURCE_ONLY_DRY_RUN_PREFLIGHT_READY"
        next_action = "PROCEED_TO_SRC7H_RUNTIME_EXPLICIT_SML_SOURCE_MATERIALIZATION_PLAN"
        source_gap_flags = [
            "SRC7G_ENDPOINT_DEPLOYED",
            "SRC7G_NO_RUNTIME_EXPLICIT_SML_SOURCE_READY",
            "SRC7G_D3D_REMAINS_BLOCKED",
        ]

    return {
        "engine": "SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT",
        "version": "source_resolution_src7g_runtime_dry_run_preflight_endpoint_v1",
        "audit_status": "PASS_SRC7G_RUNTIME_DRY_RUN_PREFLIGHT_ENDPOINT_RESPONDED_NO_MUTATION",
        "diagnostic_only": True,
        "dry_run": True,
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed_by_this_endpoint": False,
        "operator_control_unconfirmed_by_this_endpoint": False,
        "not_a_trade_signal": True,
        "requested_symbols": requested_symbols,
        "fixture_mode": normalized_fixture_mode,
        "fixture_used": fixture_used,
        "runtime_counts": {
            "symbol_count_attempted": len(results),
            "symbol_count_source_only_dry_run_ready": total_source_only_ready,
            "symbol_count_source_only_dry_run_not_ready": len(results) - total_source_only_ready,
            "symbol_count_production_d3d_eligible": total_production_eligible,
        },
        "runtime_distributions": {
            "src7f_status_distribution": status_distribution,
            "source_only_dry_run_eligibility_distribution": source_only_distribution,
        },
        "results": results,
        "source_gap_flags": source_gap_flags,
        "guardrail_failure_count": len(guardrail_failures),
        "guardrail_failures": guardrail_failures,
        "runtime_decision": {
            "preflight_status": preflight_status,
            "next_action": next_action,
            "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
            "src7g_makes_any_campaign_d3d_eligible": False,
            "reason": "SRC7G exposes runtime dry-run source-only preflight readiness. It does not persist, mutate, confirm operator control, or authorize D3D.",
        },
    }
# === SRC7G RUNTIME DRY-RUN PREFLIGHT ENDPOINT END ===


# ============================================================
# R4-R14C — Strict WLW explicit event-date fact route
# Read-only market-data derivation only.
# Does not write Supabase.
# Does not mutate campaigns.
# Does not confirm operator control.
# Does not authorize D3D.
# Does not create trade signals.
# Gamma remains overlay only.
# ============================================================

def _r4_r14c_env_first(names):
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""

def _r4_r14c_float(value):
    try:
        if value is None or value == "":
            return None
        number = float(str(value).replace(",", ""))
        if math.isfinite(number):
            return number
    except Exception:
        return None
    return None

def _r4_r14c_price(value):
    number = _r4_r14c_float(value)
    return "" if number is None else f"{number:.2f}"

def _r4_r14c_bar_date(bar):
    value = bar.get("t") or bar.get("timestamp") or bar.get("date") or bar.get("datetime")
    if not value:
        return ""
    return str(value)[:10]

def _r4_r14c_normalize_bar(bar):
    return {
        "date": _r4_r14c_bar_date(bar),
        "open": _r4_r14c_float(bar.get("o", bar.get("open"))),
        "high": _r4_r14c_float(bar.get("h", bar.get("high"))),
        "low": _r4_r14c_float(bar.get("l", bar.get("low"))),
        "close": _r4_r14c_float(bar.get("c", bar.get("close"))),
        "volume": _r4_r14c_float(bar.get("v", bar.get("volume"))),
    }

def _r4_r14c_volume_ratio_20(bars, index):
    if index is None or index < 0 or index >= len(bars):
        return None
    current_volume = bars[index].get("volume")
    if current_volume is None or current_volume <= 0:
        return None
    prior = [
        b.get("volume")
        for b in bars[max(0, index - 20):index]
        if b.get("volume") is not None and b.get("volume") > 0
    ]
    if not prior:
        return None
    average_volume = sum(prior) / len(prior)
    if average_volume <= 0:
        return None
    return current_volume / average_volume

def _r4_r14c_volume_label(ratio):
    number = _r4_r14c_float(ratio)
    if number is None:
        return "unavailable"
    if number >= 1.50:
        return "confirming_high_volume"
    if number >= 1.10:
        return "moderately_confirming_volume"
    if number >= 0.80:
        return "neutral_volume"
    return "low_volume_non_confirmation"

def _r4_r14c_fact(prefix, status, method="", index=None, bar=None, target=None, distance=None, ratio=None):
    return {
        f"{prefix}_event_date": bar.get("date", "") if bar else "",
        f"{prefix}_event_date_status": status,
        f"{prefix}_event_date_method": method,
        f"{prefix}_event_price_target": _r4_r14c_price(target),
        f"{prefix}_event_price_match_distance": _r4_r14c_price(distance),
        f"{prefix}_event_open": _r4_r14c_price(bar.get("open")) if bar else "",
        f"{prefix}_event_high": _r4_r14c_price(bar.get("high")) if bar else "",
        f"{prefix}_event_low": _r4_r14c_price(bar.get("low")) if bar else "",
        f"{prefix}_event_close": _r4_r14c_price(bar.get("close")) if bar else "",
        f"{prefix}_event_volume": str(int(bar.get("volume"))) if bar and bar.get("volume") is not None else "",
        f"{prefix}_event_volume_ratio_20": "" if ratio is None else f"{ratio:.2f}",
        f"{prefix}_event_volume_confirmation": _r4_r14c_volume_label(ratio),
        f"{prefix}_event_bar_index": "" if index is None else str(index),
    }

def _r4_r14c_nearest_bar(bars, target, field):
    target_number = _r4_r14c_float(target)
    if target_number is None or not bars:
        return None, None
    best = None
    best_distance = None
    for index, bar in enumerate(bars):
        value = bar.get(field)
        if value is None:
            continue
        distance = abs(value - target_number)
        if best_distance is None or distance < best_distance:
            best = (index, bar)
            best_distance = distance
    return best, best_distance

def _r4_r14c_derive_upthrust(bars, trigger_price, reference_resistance):
    target = _r4_r14c_float(trigger_price) or _r4_r14c_float(reference_resistance)
    resistance = _r4_r14c_float(reference_resistance) or target
    if target is None or not bars:
        return _r4_r14c_fact("wyckoff_upthrust", "unavailable_no_price_or_bars")
    matches = []
    for index, bar in enumerate(bars):
        high = bar.get("high")
        close = bar.get("close")
        if high is None or close is None:
            continue
        if high >= target and resistance is not None and close <= resistance:
            matches.append((index, bar, abs(high - target)))
    if matches:
        index, bar, distance = matches[-1]
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "wyckoff_upthrust",
            "event_grade_date_derived",
            "latest_bar_high_above_trigger_close_back_below_resistance",
            index,
            bar,
            target,
            distance,
            ratio,
        )
    pair, distance = _r4_r14c_nearest_bar(bars, target, "high")
    if pair:
        index, bar = pair
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "wyckoff_upthrust",
            "review_only_nearest_high_match",
            "nearest_high_to_trigger_price_no_reversal_condition",
            index,
            bar,
            target,
            distance,
            ratio,
        )
    return _r4_r14c_fact("wyckoff_upthrust", "unavailable_no_matching_bar")

def _r4_r14c_derive_spring(bars, trigger_price, reference_support):
    target = _r4_r14c_float(trigger_price) or _r4_r14c_float(reference_support)
    support = _r4_r14c_float(reference_support) or target
    if target is None or not bars:
        return _r4_r14c_fact("wyckoff_spring", "unavailable_no_price_or_bars")
    matches = []
    for index, bar in enumerate(bars):
        low = bar.get("low")
        close = bar.get("close")
        if low is None or close is None:
            continue
        if low <= target and support is not None and close >= support:
            matches.append((index, bar, abs(low - target)))
    if matches:
        index, bar, distance = matches[-1]
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "wyckoff_spring",
            "event_grade_date_derived",
            "latest_bar_low_below_trigger_close_back_above_support",
            index,
            bar,
            target,
            distance,
            ratio,
        )
    pair, distance = _r4_r14c_nearest_bar(bars, target, "low")
    if pair:
        index, bar = pair
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "wyckoff_spring",
            "review_only_nearest_low_match",
            "nearest_low_to_trigger_price_no_reversal_condition",
            index,
            bar,
            target,
            distance,
            ratio,
        )
    return _r4_r14c_fact("wyckoff_spring", "unavailable_no_matching_bar")

def _r4_r14c_derive_livermore_long(bars, pivot_price):
    pivot = _r4_r14c_float(pivot_price)
    if pivot is None or not bars:
        return _r4_r14c_fact("livermore_long_pivot", "unavailable_no_pivot_or_bars")
    matches = []
    for index, bar in enumerate(bars):
        close = bar.get("close")
        previous_close = bars[index - 1].get("close") if index > 0 else None
        if close is None:
            continue
        if close >= pivot and (previous_close is None or previous_close < pivot):
            matches.append((index, bar, abs(close - pivot)))
    if matches:
        index, bar, distance = matches[-1]
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "livermore_long_pivot",
            "event_grade_date_derived",
            "latest_close_cross_above_pivot",
            index,
            bar,
            pivot,
            distance,
            ratio,
        )
    pair, distance = _r4_r14c_nearest_bar(bars, pivot, "close")
    if pair:
        index, bar = pair
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "livermore_long_pivot",
            "review_only_nearest_close_match",
            "nearest_close_to_pivot_no_cross_condition",
            index,
            bar,
            pivot,
            distance,
            ratio,
        )
    return _r4_r14c_fact("livermore_long_pivot", "unavailable_no_matching_bar")

def _r4_r14c_derive_livermore_short(bars, pivot_price):
    pivot = _r4_r14c_float(pivot_price)
    if pivot is None or not bars:
        return _r4_r14c_fact("livermore_short_risk_pivot", "unavailable_no_pivot_or_bars")
    matches = []
    for index, bar in enumerate(bars):
        close = bar.get("close")
        previous_close = bars[index - 1].get("close") if index > 0 else None
        if close is None:
            continue
        if close <= pivot and (previous_close is None or previous_close > pivot):
            matches.append((index, bar, abs(close - pivot)))
    if matches:
        index, bar, distance = matches[-1]
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "livermore_short_risk_pivot",
            "event_grade_date_derived",
            "latest_close_cross_below_pivot",
            index,
            bar,
            pivot,
            distance,
            ratio,
        )
    pair, distance = _r4_r14c_nearest_bar(bars, pivot, "close")
    if pair:
        index, bar = pair
        ratio = _r4_r14c_volume_ratio_20(bars, index)
        return _r4_r14c_fact(
            "livermore_short_risk_pivot",
            "review_only_nearest_close_match",
            "nearest_close_to_pivot_no_cross_condition",
            index,
            bar,
            pivot,
            distance,
            ratio,
        )
    return _r4_r14c_fact("livermore_short_risk_pivot", "unavailable_no_matching_bar")

def _r4_r14c_fetch_bars(symbols, lookback_days=730):
    alpaca_key = _r4_r14c_env_first([
        "ALPACA_API_KEY_ID",
        "ALPACA_API_KEY",
        "APCA_API_KEY_ID",
        "ALPACA_KEY_ID",
    ])
    alpaca_secret = _r4_r14c_env_first([
        "ALPACA_API_SECRET_KEY",
        "ALPACA_API_SECRET",
        "ALPACA_SECRET_KEY",
        "APCA_API_SECRET_KEY",
        "ALPACA_SECRET",
    ])
    if not alpaca_key or not alpaca_secret:
        return {}, {
            "ok": False,
            "error": "missing_alpaca_credentials",
            "key_aliases_checked": [
                "ALPACA_API_KEY_ID",
                "ALPACA_API_KEY",
                "APCA_API_KEY_ID",
                "ALPACA_KEY_ID",
            ],
            "secret_aliases_checked": [
                "ALPACA_API_SECRET_KEY",
                "ALPACA_API_SECRET",
                "ALPACA_SECRET_KEY",
                "APCA_API_SECRET_KEY",
                "ALPACA_SECRET",
            ],
        }

    headers = {
        "APCA-API-KEY-ID": alpaca_key,
        "APCA-API-SECRET-KEY": alpaca_secret,
        "User-Agent": "Sigmalytic-R4-R14C-ReadOnly-Event-Date-Facts/1.0",
    }
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(lookback_days or 730))
    context = ssl.create_default_context()
    output = {symbol: [] for symbol in symbols}
    endpoint_errors = []
    feed_used = None

    for feed in ["sip", "iex"]:
        try:
            params = {
                "symbols": ",".join(symbols[:5]),
                "timeframe": "1Day",
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "limit": "1000",
                "adjustment": "all",
                "feed": feed,
                "sort": "asc",
            }
            url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=45, context=context) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            if isinstance(payload.get("bars"), dict):
                feed_used = feed
                break
        except Exception as exc:
            endpoint_errors.append({"feed": feed, "error": repr(exc)})

    if not feed_used:
        return output, {
            "ok": False,
            "error": "alpaca_bar_fetch_unavailable",
            "endpoint_errors": endpoint_errors,
        }

    batch_size = 50
    for batch_start in range(0, len(symbols), batch_size):
        batch = symbols[batch_start:batch_start + batch_size]
        page_token = ""
        while True:
            params = {
                "symbols": ",".join(batch),
                "timeframe": "1Day",
                "start": start.isoformat().replace("+00:00", "Z"),
                "end": end.isoformat().replace("+00:00", "Z"),
                "limit": "10000",
                "adjustment": "all",
                "feed": feed_used,
                "sort": "asc",
            }
            if page_token:
                params["page_token"] = page_token
            url = "https://data.alpaca.markets/v2/stocks/bars?" + urllib.parse.urlencode(params)
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=60, context=context) as response:
                    payload = json.loads(response.read().decode("utf-8", errors="replace"))
                bars = payload.get("bars") or {}
                for symbol, symbol_bars in bars.items():
                    normalized_symbol = str(symbol).upper()
                    if normalized_symbol in output and isinstance(symbol_bars, list):
                        output[normalized_symbol].extend(_r4_r14c_normalize_bar(bar) for bar in symbol_bars)
                page_token = payload.get("next_page_token") or ""
                if not page_token:
                    break
            except Exception as exc:
                endpoint_errors.append({
                    "batch_start": batch_start,
                    "symbols": batch,
                    "feed": feed_used,
                    "error": repr(exc),
                })
                break

    for symbol, bars in list(output.items()):
        seen = set()
        deduped = []
        for bar in bars:
            key = (bar.get("date"), bar.get("open"), bar.get("high"), bar.get("low"), bar.get("close"), bar.get("volume"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(bar)
        deduped.sort(key=lambda item: item.get("date") or "")
        output[symbol] = deduped

    return output, {
        "ok": True,
        "feed": feed_used,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "endpoint_error_count": len(endpoint_errors),
    }

@router.get("/api/reports/strict-wlw/event-date-facts")
def r4_r14c_strict_wlw_event_date_facts(
    symbols: str = "",
    lookback_days: int = 730,
    upthrust_trigger_price: str = "",
    upthrust_reference_resistance: str = "",
    spring_trigger_price: str = "",
    spring_reference_support: str = "",
    livermore_long_pivot_price: str = "",
    livermore_short_risk_pivot_price: str = "",
):
    symbol_list = [
        symbol.strip().upper()
        for symbol in str(symbols or "").replace(";", ",").split(",")
        if symbol.strip()
    ]
    symbol_list = symbol_list[:250]

    bars_by_symbol, fetch_status = _r4_r14c_fetch_bars(symbol_list, lookback_days)

    facts = []
    for symbol in symbol_list:
        bars = bars_by_symbol.get(symbol, [])
        upthrust = _r4_r14c_derive_upthrust(bars, upthrust_trigger_price, upthrust_reference_resistance)
        spring = _r4_r14c_derive_spring(bars, spring_trigger_price, spring_reference_support)
        livermore_long = _r4_r14c_derive_livermore_long(bars, livermore_long_pivot_price)
        livermore_short = _r4_r14c_derive_livermore_short(bars, livermore_short_risk_pivot_price)

        merged = {
            "symbol": symbol,
            "bar_count": len(bars),
            "bar_source": "alpaca_market_data_get_read_only" if fetch_status.get("ok") else "unavailable",
        }
        merged.update(upthrust)
        merged.update(spring)
        merged.update(livermore_long)
        merged.update(livermore_short)

        primary_event_date = ""
        primary_event_date_source = ""
        primary_event_date_status = ""

        for source in [
            "wyckoff_upthrust",
            "wyckoff_spring",
            "livermore_long_pivot",
            "livermore_short_risk_pivot",
        ]:
            candidate_date = merged.get(f"{source}_event_date", "")
            candidate_status = merged.get(f"{source}_event_date_status", "")
            if candidate_date:
                primary_event_date = candidate_date
                primary_event_date_source = source
                primary_event_date_status = candidate_status
                break

        merged["primary_event_date"] = primary_event_date
        merged["primary_event_date_source"] = primary_event_date_source
        merged["primary_event_date_status"] = primary_event_date_status

        facts.append(merged)

    return {
        "ok": True,
        "mode": "STRICT_WLW_R4_R14C_EVENT_DATE_FACTS_READ_ONLY",
        "read_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "operator_control_confirmed": False,
        "d3d_authorized": False,
        "trade_signal": False,
        "gamma_overlay_only": True,
        "event_date_fields_added": [
            "wyckoff_spring_event_date",
            "wyckoff_spring_event_date_status",
            "wyckoff_upthrust_event_date",
            "wyckoff_upthrust_event_date_status",
            "livermore_long_pivot_event_date",
            "livermore_long_pivot_event_date_status",
            "livermore_short_risk_pivot_event_date",
            "livermore_short_risk_pivot_event_date_status",
            "primary_event_date",
            "primary_event_date_source",
            "primary_event_date_status",
        ],
        "fetch_status": fetch_status,
        "symbol_count": len(symbol_list),
        "facts": facts,
    }
