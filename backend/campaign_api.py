
from fastapi import APIRouter
from typing import Dict, Any, List

router = APIRouter(
    prefix="/api/campaign",
    tags=["campaign"],
)

_ACTIVE_CAMPAIGNS: List[Dict[str, Any]] = []


@router.get("/health")
def health():

    return {
        "status": "ok",
        "service": "campaign_api",
    }


@router.get("/active")
def active_campaigns():

    return {
        "campaigns": _ACTIVE_CAMPAIGNS
    }


@router.get("/rankings")
def rankings():

    ranked = sorted(
        _ACTIVE_CAMPAIGNS,
        key=lambda x: x.get(
            "ucr_score",
            0
        ),
        reverse=True
    )

    return {
        "campaigns": ranked
    }


@router.get("/status")
def status():

    active = len(_ACTIVE_CAMPAIGNS)

    expanding = len([
        x for x in _ACTIVE_CAMPAIGNS
        if x.get("state")
        == "EXPANDING"
    ])

    birth = len([
        x for x in _ACTIVE_CAMPAIGNS
        if x.get("state")
        == "BIRTH"
    ])

    distribution = len([
        x for x in _ACTIVE_CAMPAIGNS
        if x.get("state")
        == "DISTRIBUTION_RISK"
    ])

    return {
        "active_campaigns": active,
        "birth_candidates": birth,
        "expanding_campaigns": expanding,
        "distribution_risk": distribution,
    }


@router.post("/register")
def register_campaign(
    campaign: Dict[str, Any]
):

    _ACTIVE_CAMPAIGNS.append(
        campaign
    )

    return {
        "status": "registered"
    }

