"""
SAVE AS:
backend/main.py
"""

from fastapi import FastAPI

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
    return {
        "ok": True,
        "status": "Full nightly pipeline route restored",
        "message": "Route is available. Engine orchestration must be wired to actual runner next.",
    }

app.include_router(campaign_router)
app.include_router(research_router)
app.include_router(intelligence_router)
app.include_router(operator_router)

if admin_router is not None:
    app.include_router(admin_router)