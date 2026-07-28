from pathlib import Path

path = Path("backend/campaign_api.py")
text = path.read_text(encoding="utf-8")

old_import = '''from fastapi import APIRouter
from typing import Any, Dict, List
'''

new_import = '''import json

from fastapi import APIRouter
from typing import Any, Dict, List
'''

if old_import not in text:
    raise SystemExit("Import block not found.")

text = text.replace(old_import, new_import, 1)

insert_after = '''def _store():
    return CampaignStore()


'''

helper = '''def _json_dict(value: Any) -> Dict[str, Any]:
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
        out["weis_gamma_fusion_state"] = None
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

    out["weis_gamma_gamma_status"] = gamma.get("status")
    out["weis_gamma_gamma_regime"] = gamma.get("net_gamma_regime")
    out["weis_gamma_gamma_router"] = freshness.get("router_state")
    out["weis_gamma_gamma_fresh"] = bool(
        gamma.get("gamma_data_fresh")
        or freshness.get("gamma_data_fresh")
    )

    out["weis_gamma_fusion_state"] = fusion.get("fusion_state")
    out["weis_gamma_zero_dte_state"] = zero_dte.get("squeeze_state")
    out["weis_gamma_warning"] = _first_warning(wg.get("warnings"))

    return out


def _attach_weis_gamma_summaries(
    campaigns: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return [_attach_weis_gamma_summary(c) for c in campaigns]


'''

if insert_after not in text:
    raise SystemExit("Could not find _store insertion point.")

text = text.replace(insert_after, insert_after + helper, 1)

old_active = '''@router.get("/active")
def active_campaigns():
    campaigns = _store().get_active_campaigns()
    return {"campaigns": campaigns}
'''

new_active = '''@router.get("/active")
def active_campaigns():
    campaigns = _store().get_active_campaigns()
    campaigns = _attach_weis_gamma_summaries(campaigns)
    return {"campaigns": campaigns}
'''

if old_active not in text:
    raise SystemExit("active_campaigns block not found.")

text = text.replace(old_active, new_active, 1)

old_rankings = '''@router.get("/rankings")
def rankings():
    campaigns = _store().get_top_campaigns(limit=100)

    ranked = sorted(
        campaigns,
'''

new_rankings = '''@router.get("/rankings")
def rankings():
    campaigns = _store().get_top_campaigns(limit=100)
    campaigns = _attach_weis_gamma_summaries(campaigns)

    ranked = sorted(
        campaigns,
'''

if old_rankings not in text:
    raise SystemExit("rankings block not found.")

text = text.replace(old_rankings, new_rankings, 1)

path.write_text(text, encoding="utf-8")
print("Patched campaign_api.py with Weis-Gamma top-level API fields.")
