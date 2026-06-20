"""
SAVE AS:
backend/main.py
"""

from fastapi import FastAPI
from datetime import datetime

from backend.campaign_api import router as campaign_router
from backend.research_api import router as research_router
from backend.intelligence_api import router as intelligence_router
from backend.operator_dominance.operator_dominance_api import router as operator_router

try:
    from backend.admin_api import router as admin_router
except Exception:
    admin_router = None


app = FastAPI(
    title="Sigmalytic V2",
    version="2.0.0",
)


@app.get("/")
def root():
    return {
        "application": "Sigmalytic V2",
        "status": "online",
        "version": "2.0.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/health")
def api_health():
    return {"status": "healthy"}


@app.get("/api/admin/engine-status")
def engine_status():
    return {
        "signal_birth_engine": True,
        "campaign_pipeline": True,
        "ods_engine": True,
        "analog_engine": True,
        "decay_monitor": True,
        "state_transition": True,
        "campaign_outcome": True,
        "campaign_closure_engine": True,
        "portfolio_intelligence": True,
        "wyckoff_engine": True,
        "gann_engine": True,
        "bme_engine": True,
        "sizing_engine": True,
        "subscriber_alerts": True,
        "campaign_api": True,
        "portfolio_api": True,
        "journal_api": True,
    }


@app.post("/api/admin/run-full-nightly")
def run_full_nightly():
    results = {
        "ok": True,
        "started_at": datetime.utcnow().isoformat(),
        "steps": {},
    }

    try:
        from backend.campaign_engine import nightly_campaign_pipeline as pipeline

        runner = None

        for name in [
            "run_nightly_campaign_pipeline",
            "run_campaign_pipeline",
            "run_nightly_pipeline",
            "main",
        ]:
            if hasattr(pipeline, name):
                runner = getattr(pipeline, name)
                break

        if runner is None:
            results["ok"] = False
            results["steps"]["campaign_pipeline"] = {
                "status": "failed",
                "error": "No runner function found in nightly_campaign_pipeline.py",
            }
            return results

        pipeline_result = runner()

        results["steps"]["campaign_pipeline"] = {
            "status": "completed",
            "runner": runner.__name__,
            "result": pipeline_result,
        }

    except Exception as e:
        results["ok"] = False
        results["steps"]["campaign_pipeline"] = {
            "status": "failed",
            "error": str(e),
        }

    results["finished_at"] = datetime.utcnow().isoformat()
    return results


@app.post("/api/admin/run-closure-engine")
def run_closure_engine_admin():
    from backend.intelligence.campaign_closure_engine import (
        run_campaign_closure_cycle,
    )

    return run_campaign_closure_cycle()


@app.get("/api/campaigns/active")
def campaigns_active_alias():
    from backend.campaign_api import active_campaigns
    return active_campaigns()


@app.get("/api/campaigns/summary")
def campaigns_summary_alias():
    from backend.campaign_api import status
    return status()


@app.get("/api/radar/top")
def radar_top_alias(limit: int = 8):
    from backend.campaign_api import rankings
    data = rankings()
    campaigns = data.get("campaigns", []) if isinstance(data, dict) else []
    return {"campaigns": campaigns[:limit]}


app.include_router(campaign_router)
app.include_router(research_router)
app.include_router(intelligence_router)
app.include_router(operator_router)

if admin_router is not None:
    app.include_router(admin_router)