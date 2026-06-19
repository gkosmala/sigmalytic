# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/portfolio_api.py

Phase 16 — Portfolio Intelligence API

Endpoints:
    GET /api/portfolio/rankings
    GET /api/portfolio/summary
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from fastapi import APIRouter, Query

portfolio_router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY are required")
    return url, key


def _headers() -> dict[str, str]:
    _, key = _supabase_config()
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _rest_get(path: str, params: Optional[dict[str, str]] = None, timeout: int = 20) -> Any:
    url, _ = _supabase_config()
    r = requests.get(
        f"{url}/rest/v1/{path.lstrip('/')}",
        headers=_headers(),
        params=params or {},
        timeout=timeout,
    )
    if r.status_code not in (200, 206):
        return {
            "error": True,
            "status_code": r.status_code,
            "message": r.text[:500],
        }
    return r.json()


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


@portfolio_router.get("/rankings")
async def get_portfolio_rankings(
    limit: int = Query(100, ge=1, le=500),
    band: str | None = Query(None),
):
    """
    Return latest Phase 16 portfolio rankings.
    """
    params = {
        "select": "*",
        "order": "portfolio_rank.asc",
        "limit": str(limit),
    }

    if band:
        params["priority_band"] = f"eq.{band.upper().strip()}"

    rows = _rest_get("portfolio_rankings", params=params)

    if isinstance(rows, dict) and rows.get("error"):
        return {
            "ok": False,
            "error": rows,
            "rankings": [],
            "count": 0,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    rows = rows if isinstance(rows, list) else []

    return {
        "ok": True,
        "count": len(rows),
        "rankings": rows,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


@portfolio_router.get("/summary")
async def get_portfolio_summary():
    """
    Return Phase 16 portfolio summary metrics.
    """
    rows = _rest_get(
        "portfolio_rankings",
        params={
            "select": "*",
            "order": "portfolio_rank.asc",
            "limit": "500",
        },
    )

    if isinstance(rows, dict) and rows.get("error"):
        return {
            "ok": False,
            "error": rows,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    rows = rows if isinstance(rows, list) else []
    total = len(rows)

    band_counts: dict[str, int] = {}
    for r in rows:
        band = str(r.get("priority_band") or "UNKNOWN")
        band_counts[band] = band_counts.get(band, 0) + 1

    weights = [_f(r.get("capital_weight"), 0) for r in rows]
    scores = [_f(r.get("portfolio_score"), 0) for r in rows]
    expected_returns = [_f(r.get("expected_return"), 0) for r in rows]
    risks = [_f(r.get("risk_score"), 0) for r in rows]

    investable = [r for r in rows if str(r.get("priority_band") or "").upper() not in ("AVOID",)]
    top_10 = rows[:10]

    return {
        "ok": True,
        "total": total,
        "investable": len(investable),
        "band_counts": band_counts,
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "avg_expected_return": round(sum(expected_returns) / len(expected_returns), 2) if expected_returns else 0,
        "avg_risk_score": round(sum(risks) / len(risks), 2) if risks else 0,
        "total_capital_weight": round(sum(weights), 2) if weights else 0,
        "top_10": top_10,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }

