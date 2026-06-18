
from fastapi import APIRouter

from backend.campaign_api import (
    active_campaigns,
    rankings,
    status,
)

router = APIRouter(
    prefix="/api/status-center",
    tags=["status_center"],
)


@router.get("/dashboard")
def dashboard():

    return {
        "campaign_status": status(),
        "rankings": rankings(),
        "active_campaigns": active_campaigns(),
    }


@router.get("/health")
def health():

    return {
        "status": "ok",
        "service": "status_center",
    }
