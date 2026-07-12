from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body

router = APIRouter(
    prefix="/api/email-alerts",
    tags=["controlled-email-alert-test"],
)

RESEND_URL = "https://api.resend.com/emails"
CONFIRMATION_PHRASE = "SEND ONE CONTROLLED SIGMALYTIC EMAIL TEST"
DEFAULT_FROM_EMAIL = "alerts@sigmalyticquantcorp.com"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safety() -> Dict[str, Any]:
    return {
        "one_email_only": True,
        "subscriber_blast": False,
        "database_write": False,
        "supabase_write": False,
        "campaign_mutation": False,
        "daily_bars_mutation": False,
        "d3d": False,
        "operator_control_confirmation": False,
        "trade_signal": False,
        "stripe": False,
    }


def _blocked(reason: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "status": "BLOCKED",
        "reason": reason,
        "created_utc": _now(),
        "email_sent": False,
        "extra": extra or {},
        "safety": _safety(),
    }


def _email_valid(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value or ""))


@router.get("/controlled-one-email-test/status")
def controlled_one_email_test_status() -> Dict[str, Any]:
    return {
        "status": "PASS",
        "mode": "CONTROLLED_ONE_EMAIL_TEST_STATUS",
        "created_utc": _now(),
        "enabled": os.environ.get("SIGMALYTIC_EMAIL_ALERT_TEST_ENABLED", "").strip().lower() == "true",
        "has_resend_api_key": bool(os.environ.get("RESEND_API_KEY", "").strip()),
        "has_test_token": bool(os.environ.get("SIGMALYTIC_EMAIL_ALERT_TEST_TOKEN", "").strip()),
        "from_email": os.environ.get("ALERT_FROM_EMAIL", DEFAULT_FROM_EMAIL),
        "confirmation_phrase_required": CONFIRMATION_PHRASE,
        "email_sent": False,
        "safety": {
            **_safety(),
            "status_check_only": True,
        },
    }


@router.post("/controlled-one-email-test")
async def controlled_one_email_test(payload: Optional[Dict[str, Any]] = Body(default=None)) -> Dict[str, Any]:
    payload = payload or {}

    enabled = os.environ.get("SIGMALYTIC_EMAIL_ALERT_TEST_ENABLED", "").strip().lower() == "true"
    if not enabled:
        return _blocked(
            "SIGMALYTIC_EMAIL_ALERT_TEST_ENABLED is not true. No email sent.",
            {"required_render_env": "SIGMALYTIC_EMAIL_ALERT_TEST_ENABLED=true"},
        )

    expected_token = os.environ.get("SIGMALYTIC_EMAIL_ALERT_TEST_TOKEN", "").strip()
    provided_token = str(payload.get("test_token", "")).strip()

    if not expected_token:
        return _blocked(
            "SIGMALYTIC_EMAIL_ALERT_TEST_TOKEN is not configured on the backend. No email sent.",
            {"required_render_env": "SIGMALYTIC_EMAIL_ALERT_TEST_TOKEN"},
        )

    if provided_token != expected_token:
        return _blocked("Test token mismatch. No email sent.")

    confirmation = str(payload.get("confirmation", "")).strip()
    if confirmation != CONFIRMATION_PHRASE:
        return _blocked(
            "Confirmation phrase mismatch. No email sent.",
            {"required_confirmation": CONFIRMATION_PHRASE},
        )

    to_email = str(payload.get("to_email", "")).strip()
    if not _email_valid(to_email):
        return _blocked("Invalid test recipient email. No email sent.", {"to_email": to_email})

    resend_api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not resend_api_key:
        return _blocked("RESEND_API_KEY is missing on the backend. No email sent.")

    from_email = os.environ.get("ALERT_FROM_EMAIL", DEFAULT_FROM_EMAIL).strip()
    if not _email_valid(from_email):
        return _blocked("ALERT_FROM_EMAIL is invalid. No email sent.", {"from_email": from_email})

    subject = "Sigmalytic V2 Email Alert Test - No Trade Signal"

    html_body = """
    <div style="font-family:Arial,Helvetica,sans-serif;color:#111;line-height:1.45;">
      <h2 style="color:#0B4F9C;">Sigmalytic Quant Corporation</h2>
      <h3>Controlled Email Alert Test</h3>
      <p>This is a controlled one-email test of the Sigmalytic V2 live email alert path.</p>
      <p><strong>No trade signal was generated.</strong></p>
      <p><strong>No campaign state was changed.</strong></p>
      <p><strong>No subscriber-wide alert was sent.</strong></p>
      <p>If you received this message, the live Render Resend email path is working for a single controlled test email.</p>
      <hr>
      <p style="font-size:12px;color:#555;">Copyright 2026 Sigmalytic Quant Corporation. All rights reserved.</p>
    </div>
    """

    try:
        import httpx
    except Exception as exc:
        return {
            "status": "FAIL",
            "reason": "httpx is not available in the backend runtime.",
            "created_utc": _now(),
            "email_sent": False,
            "error": repr(exc),
            "safety": _safety(),
        }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                RESEND_URL,
                headers={
                    "Authorization": "Bearer " + resend_api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Sigmalytic-Backend-Controlled-Email-Test/1.0",
                },
                json={
                    "from": from_email,
                    "to": [to_email],
                    "subject": subject,
                    "html": html_body,
                },
            )

        raw_text = response.text

        try:
            resend_response: Any = response.json()
        except Exception:
            resend_response = raw_text

        if response.status_code >= 400:
            return {
                "status": "FAIL",
                "reason": "Resend returned an HTTP error.",
                "created_utc": _now(),
                "email_sent": False,
                "resend_status_code": response.status_code,
                "resend_error_body": raw_text,
                "from_email": from_email,
                "to_email": to_email,
                "safety": _safety(),
            }

        return {
            "status": "PASS",
            "mode": "CONTROLLED_ONE_EMAIL_RESEND_TEST",
            "created_utc": _now(),
            "email_sent": True,
            "to_email": to_email,
            "from_email": from_email,
            "subject": subject,
            "resend_status_code": response.status_code,
            "resend_response": resend_response,
            "safety": _safety(),
        }

    except Exception as exc:
        return {
            "status": "FAIL",
            "reason": "Exception during controlled Resend test.",
            "created_utc": _now(),
            "email_sent": False,
            "error": repr(exc),
            "from_email": from_email,
            "to_email": to_email,
            "safety": _safety(),
        }