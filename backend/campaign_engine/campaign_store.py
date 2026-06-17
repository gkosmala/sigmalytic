# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_engine/campaign_store.py

Supabase REST adapter for campaign lifecycle tracking.
The functions are intentionally defensive: if optional tables such as
campaign_observations or campaign_state_history do not exist yet, the nightly
pipeline logs the issue and continues instead of killing the whole run.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import requests

log = logging.getLogger("campaign_store")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_config() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY are required")
    return url, key


def _headers(prefer: Optional[str] = None) -> dict[str, str]:
    _, key = _supabase_config()
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _request(method: str, path: str, *, params: Optional[dict[str, str]] = None, json: Any = None, timeout: int = 20) -> requests.Response:
    url, _ = _supabase_config()
    resp = requests.request(
        method=method,
        url=f"{url}/rest/v1/{path.lstrip('/')}",
        headers=_headers("return=representation" if method.upper() in {"POST", "PATCH"} else None),
        params=params,
        json=json,
        timeout=timeout,
    )
    return resp


def get_active_campaigns(limit: int = 1000) -> list[dict[str, Any]]:
    params = {
        "select": "*",
        "status": "eq.ACTIVE",
        "order": "created_at.asc",
        "limit": str(limit),
    }
    resp = _request("GET", "campaigns", params=params)
    if resp.status_code not in (200, 206):
        raise RuntimeError(f"Failed to fetch active campaigns: {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    return data if isinstance(data, list) else []


def update_campaign(campaign_id: int | str, updates: dict[str, Any]) -> dict[str, Any]:
    payload = dict(updates)
    payload["updated_at"] = utc_now_iso()

    resp = _request(
        "PATCH",
        "campaigns",
        params={"campaign_id": f"eq.{campaign_id}"},
        json=payload,
    )
    if resp.status_code not in (200, 204):
        raise RuntimeError(f"Failed to update campaign {campaign_id}: {resp.status_code} {resp.text[:300]}")
    try:
        data = resp.json()
        return data[0] if isinstance(data, list) and data else {}
    except Exception:
        return {}


def insert_campaign_observation(row: dict[str, Any]) -> bool:
    payload = dict(row)
    payload.setdefault("observed_at", utc_now_iso())
    resp = _request("POST", "campaign_observations", json=payload)
    if resp.status_code in (200, 201, 204):
        return True

    # Optional table may not exist in older deployments.
    log.warning("campaign_observations insert skipped: %s %s", resp.status_code, resp.text[:250])
    return False


def insert_campaign_state_history(row: dict[str, Any]) -> bool:
    payload = dict(row)
    payload.setdefault("changed_at", utc_now_iso())
    resp = _request("POST", "campaign_state_history", json=payload)
    if resp.status_code in (200, 201, 204):
        return True

    # Optional table may not exist in older deployments.
    log.warning("campaign_state_history insert skipped: %s %s", resp.status_code, resp.text[:250])
    return False


def close_campaign(campaign_id: int | str, reason: str) -> dict[str, Any]:
    return update_campaign(campaign_id, {
        "status": "CLOSED",
        "close_reason": reason,
        "close_notes": reason,
        "closed_at": utc_now_iso(),
    })
