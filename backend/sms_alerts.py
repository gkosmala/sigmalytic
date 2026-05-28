# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/sms_alerts.py
---------------------
Sigmalytic — SMS Alert System via Twilio

Sends text alerts when symbols hit Armed, Triggered,
Short Armed, or Short Trigger status.

SMS is gated behind premium accounts only.
Free accounts receive email alerts only.
"""

from __future__ import annotations
import os
import logging

log = logging.getLogger("sms_alerts")

TWILIO_ACCOUNT_SID  = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN   = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER  = os.getenv("TWILIO_FROM_NUMBER", "")
ALERT_PHONE         = os.getenv("ALERT_PHONE", "")

# Status types that trigger SMS
SMS_ALERT_STATUSES = {
    "Armed", "Triggered", "Confirmed",
    "Short Armed", "Short Trigger", "Short Confirmed"
}

# Track sent alerts to avoid duplicates
_sms_alerted: dict[str, str] = {}


def _status_emoji(status: str) -> str:
    return {
        "Armed":           "🎯",
        "Triggered":       "⚡",
        "Confirmed":       "✅",
        "Short Armed":     "⚠️",
        "Short Trigger":   "🔻",
        "Short Confirmed": "🔴",
    }.get(status, "📡")


def _build_sms(sym: dict, status: str) -> str:
    """Build a concise SMS message — under 160 chars where possible."""
    symbol    = sym.get("symbol", "")
    price     = sym.get("price", 0)
    score     = sym.get("composite_score", 0)
    trigger   = sym.get("trigger", 0)
    inval     = sym.get("invalidation", 0)
    target1   = sym.get("target1", 0)
    target2   = sym.get("target2", 0)
    proximity = sym.get("trigger_proximity", 0)
    atr       = sym.get("atr", 1)
    emoji     = _status_emoji(status)
    is_short  = "Short" in status

    # Bear targets
    bear1 = round(inval - atr, 2)
    bear2 = round(inval - atr * 2, 2)

    if is_short:
        msg = (
            f"{emoji} SIGMALYTIC ALERT\n"
            f"{symbol} \u2192 {status.upper()}\n"
            f"Price: ${price:,.2f} | Score: {score:.0f}\n"
            f"Breakdown: ${inval:,.2f}\n"
            f"Bear: ${bear1:,.2f} \u2192 ${bear2:,.2f}\n"
            f"Not financial advice."
        )
    else:
        msg = (
            f"{emoji} SIGMALYTIC ALERT\n"
            f"{symbol} \u2192 {status.upper()}\n"
            f"Score: {score:.0f} | {proximity:+.1f}% to trigger\n"
            f"Trigger: ${trigger:,.2f}\n"
            f"Bull: ${target1:,.2f} \u2192 ${target2:,.2f}\n"
            f"Not financial advice."
        )
    return msg


def send_sms(sym: dict, status: str, to_number: str = None) -> bool:
    """
    Send an SMS alert for a status change.
    Returns True if sent successfully.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        log.warning("Twilio credentials not set — skipping SMS")
        return False

    phone = to_number or ALERT_PHONE
    if not phone:
        log.warning("No alert phone number set — skipping SMS")
        return False

    try:
        from twilio.rest import Client
        client  = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=_build_sms(sym, status),
            from_=TWILIO_FROM_NUMBER,
            to=phone,
        )
        log.info(f"SMS sent: {sym.get('symbol')} → {status} to {phone} (SID: {message.sid})")
        return True
    except Exception as e:
        log.warning(f"SMS error: {e}")
        return False


def maybe_send_sms(sym: dict, old_status: str, new_status: str, to_number: str = None):
    """
    Send SMS only if:
    1. New status is in SMS_ALERT_STATUSES
    2. Haven't already sent this status for this symbol
    """
    symbol = sym.get("symbol", "")

    if new_status not in SMS_ALERT_STATUSES:
        return

    # Don't resend same alert
    last = _sms_alerted.get(symbol)
    if last == new_status:
        return

    sent = send_sms(sym, new_status, to_number)
    if sent:
        _sms_alerted[symbol] = new_status


def send_test_sms(to_number: str = None) -> dict:
    """Send a test SMS to verify Twilio is working."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_FROM_NUMBER:
        return {"ok": False, "error": "Twilio credentials not configured"}

    phone = to_number or ALERT_PHONE
    if not phone:
        return {"ok": False, "error": "No phone number configured"}

    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=(
                "🎯 SIGMALYTIC TEST ALERT\n"
                "XOM → ARMED\n"
                "Score: 75 | +0.3% to trigger\n"
                "Trigger: $158.36\n"
                "Bull: $161.86 → $165.80\n"
                "SMS alerts are working correctly.\n"
                "Not financial advice."
            ),
            from_=TWILIO_FROM_NUMBER,
            to=phone,
        )
        return {"ok": True, "sid": message.sid, "to": phone}
    except Exception as e:
        return {"ok": False, "error": str(e)}

