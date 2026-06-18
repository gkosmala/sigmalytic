
"""
SAVE AS:
backend/main.py

Sigmalytic V2
FastAPI Application Entry Point
"""

from fastapi import FastAPI

from backend.campaign_api import router as campaign_router
from backend.research_api import router as research_router
from backend.intelligence_api import router as intelligence_router
from operator_dominance.operator_dominance_api import (
    router as operator_router,
)

app = FastAPI(
    title="Sigmalytic V2",
    version="2.0.0",
)

app.include_router(
    campaign_router
)

app.include_router(
    research_router
)

app.include_router(
    intelligence_router
)

app.include_router(
    operator_router
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

    return {
        "status": "healthy",
    }
