"""
Sigmalytic V2 — Campaign Pipeline Validation API.

Read-only diagnostic router.

This router does not run the nightly pipeline.
This router does not call Alpaca.
This router does not write Supabase.
This router does not mutate campaigns.
This router does not authorize D3D.
This router does not confirm operator control.
This router does not create trade signals.
This router does not touch Stripe.
"""
from __future__ import annotations

try:
    from fastapi import APIRouter
except Exception:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]

try:
    from campaign_engine.campaign_pipeline_read_only_validation_snapshot import (
        build_campaign_pipeline_read_only_validation_snapshot,
    )
except Exception:
    from backend.campaign_engine.campaign_pipeline_read_only_validation_snapshot import (
        build_campaign_pipeline_read_only_validation_snapshot,
    )


if APIRouter is not None:
    campaign_pipeline_validation_router = APIRouter(
        prefix="/api/campaigns/read-only",
        tags=["campaign-pipeline-validation-read-only"],
    )
else:
    campaign_pipeline_validation_router = None


def get_campaign_pipeline_validation_snapshot():
    """
    Build the GET-only campaign pipeline validation snapshot.

    This function is diagnostic-only and does not mutate production state.
    """
    return build_campaign_pipeline_read_only_validation_snapshot()


if campaign_pipeline_validation_router is not None:
    @campaign_pipeline_validation_router.get("/pipeline-validation-snapshot")
    def campaign_pipeline_read_only_validation_snapshot():
        """
        GET-only campaign pipeline validation snapshot.

        No nightly run.
        No Alpaca call.
        No Supabase write.
        No campaign mutation.
        No D3D.
        No operator-control confirmation.
        No trade signal.
        No Stripe.
        """
        return get_campaign_pipeline_validation_snapshot()


__all__ = [
    "campaign_pipeline_validation_router",
    "get_campaign_pipeline_validation_snapshot",
]
