"""
email_service.py — Sigmalytic Quant
Async Resend email router via FastAPI BackgroundTasks.
Now preference-aware: pulls user_preferences from Supabase before sending.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# ── Router (mounted in main.py) ───────────────────────────────────────────────
router = APIRouter()

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
RESEND_URL = "https://api.resend.com/emails"
FROM_ADDRESS = os.environ.get("ALERT_FROM_EMAIL", "alerts@sigmalytic.com")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ── Preference loader ─────────────────────────────────────────────────────────

async def get_all_user_preferences() -> list[dict]:
    try:
        result = _supabase.table("user_preferences").select("*").execute()
        return result.data or []
    except Exception as e:
        logger.error(f"[email_service] Failed to fetch user preferences: {e}")
        return []


# ── Filter logic ──────────────────────────────────────────────────────────────

def user_wants_alert(prefs: dict, alert: dict) -> bool:
    symbol      = alert.get("symbol", "").upper()
    alert_type  = alert.get("alert_type", "")
    score       = alert.get("score", 0)
    ts: datetime = alert.get("timestamp", datetime.now(timezone.utc))

    watchlist = prefs.get("watchlist") or []
    if watchlist and symbol not in [s.upper() for s in watchlist]:
        return False

    allowed_types = prefs.get("alert_types") or []
    if allowed_types and alert_type not in allowed_types:
        return False

    min_score = prefs.get("min_score", 60)
    if score < min_score:
        return False

    if prefs.get("market_hours_only", True):
        weekday = ts.weekday()
        hour_utc = ts.hour + ts.minute / 60
        if weekday >= 5 or not (13.5 <= hour_utc <= 20.0):
            return False

    quiet_start = prefs.get("quiet_start_utc")
    quiet_end   = prefs.get("quiet_end_utc")
    if quiet_start is not None and quiet_end is not None:
        hour = ts.hour
        if quiet_start > quiet_end:
            in_quiet = hour >= quiet_start or hour < quiet_end
        else:
            in_quiet = quiet_start <= hour < quiet_end
        if in_quiet:
            return False

    return True


# ── Resend sender ─────────────────────────────────────────────────────────────

async def _send_via_resend(to_email: str, subject: str, html_body: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_URL,
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": FROM_ADDRESS,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                },
            )
            if resp.status_code not in (200, 201):
                logger.error(f"[resend] Failed for {to_email}: {resp.status_code} {resp.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"[resend] Exception sending to {to_email}: {e}")
        return False


# ── Public API ────────────────────────────────────────────────────────────────

async def dispatch_alert_to_all_users(
    alert: dict,
    subject: str,
    html_body: str,
    background_tasks: Optional[BackgroundTasks] = None,
) -> None:
    all_prefs = await get_all_user_preferences()
    for prefs in all_prefs:
        if not user_wants_alert(prefs, alert):
            continue
        email = prefs.get("email")
        if not email:
            continue
        if background_tasks:
            background_tasks.add_task(_send_via_resend, email, subject, html_body)
        else:
            await _send_via_resend(email, subject, html_body)


async def send_digest(
    user_prefs: dict,
    alerts: list[dict],
    build_html_fn,
) -> None:
    qualifying = [a for a in alerts if user_wants_alert(user_prefs, a)]
    if not qualifying:
        return
    subject, html_body = build_html_fn(qualifying)
    await _send_via_resend(user_prefs["email"], subject, html_body)
