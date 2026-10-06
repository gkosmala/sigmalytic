# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/imbalance_api.py
------------------------
    GET  /api/imbalance/universe     symbols scanned and current mode
    GET  /api/imbalance/log          recent alerts (admin only while in testing)
    GET  /api/imbalance/track-record hit rate / average move per horizon (admin only)
    POST /api/imbalance/scan         run one scan now (admin only)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header

try:
    import imbalance_scanner as sc
except Exception:  # pragma: no cover
    from backend import imbalance_scanner as sc


def _admin_dependency():
    try:
        from backend.main import require_admin
    except Exception:  # pragma: no cover
        from main import require_admin
    return require_admin


def _admin(authorization: str = Header(default="")) -> str:
    # Resolved lazily to avoid a circular import with main.py. The explicit
    # Header parameter is what makes FastAPI read the Authorization header.
    return _admin_dependency()(authorization)


imbalance_router = APIRouter(prefix="/api/imbalance", tags=["imbalance"])


@imbalance_router.get("/universe")
def universe():
    return {"symbols": sc.UNIVERSE, "live": sc.is_live(), "scan_enabled": sc.scan_enabled(),
            "admin_preview": sc.admin_preview()}


@imbalance_router.get("/log")
def log_rows(limit: int = 50, _admin_email: str = Depends(_admin)):
    limit = max(1, min(int(limit), 200))
    return {"alerts": sc.default_store().recent(limit)}


@imbalance_router.get("/track-record")
def track_record(_admin_email: str = Depends(_admin)):
    return sc.track_record()


@imbalance_router.post("/scan")
def scan_now(_admin_email: str = Depends(_admin)):
    result = sc.run_scan()
    sc.update_outcomes()
    return result
