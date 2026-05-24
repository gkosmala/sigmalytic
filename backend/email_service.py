"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Async Email Alert Service
================================================================================
File    : email_service.py
Version : 1.0.0
Date    : 2026-05-24

PURPOSE
-------
Asynchronous email alert router using Resend and FastAPI BackgroundTasks.
Delivers confluence alerts to subscribers without blocking the 60-second
scan loop.

This is the primary notification channel while Twilio A2P 10DLC
registration is pending.

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

import os
import logging
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
import resend

log = logging.getLogger("email_service")

# ── Resend API key ─────────────────────────────────────────────────────────────
resend.api_key = os.environ.get("RESEND_API_KEY", "")

# ── Router ─────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


# ── Payload model ──────────────────────────────────────────────────────────────
class ConfluenceAlertPayload(BaseModel):
    ticker         : str
    score          : int
    price          : float
    setup_type     : str   # e.g. 'Spring Reversal', 'Upthrust', 'Apex Absorption'
    recipient_email: str


# ================================================================================
# CORE EMAIL FUNCTION
# ================================================================================

def execute_async_email_send(
    to_email  : str,
    ticker    : str,
    score     : int,
    price     : float,
    setup_type: str
) -> None:
    """
    Builds and sends a rich HTML confluence alert email via Resend.
    Called as a FastAPI BackgroundTask — never blocks the scan loop.
    """
    if not resend.api_key:
        log.warning("RESEND_API_KEY not set — email not sent.")
        return

    try:
        html_content = f"""
        <div style="background-color:#090d16;color:#f8fafc;padding:32px;
                    font-family:sans-serif;border-radius:16px;max-width:520px;
                    border:1px solid #1e293b;">

            <div style="border-bottom:1px solid #1e293b;padding-bottom:16px;
                        margin-bottom:20px;">
                <span style="background-color:#f59e0b;color:#090d16;font-size:11px;
                             font-weight:bold;padding:4px 8px;border-radius:4px;
                             text-transform:uppercase;">
                    Confluence Triggered
                </span>
                <h2 style="color:#ffffff;margin:8px 0 0 0;font-size:22px;">
                    Sigmalytic Intelligence Alert
                </h2>
            </div>

            <p style="font-size:15px;color:#cbd5e1;line-height:1.5;">
                The confluence engine has verified an imminent
                <strong>{setup_type}</strong> setup on <strong>{ticker}</strong>.
            </p>

            <div style="background-color:#0f172a;padding:20px;border-radius:12px;
                        margin:24px 0;border:1px solid #334155;">
                <table style="width:100%;font-size:14px;border-collapse:collapse;">
                    <tr>
                        <td style="padding:6px 0;color:#94a3b8;">Execution Node:</td>
                        <td style="padding:6px 0;text-align:right;color:#ffffff;
                                   font-weight:bold;font-family:monospace;">
                            ${price:.2f}
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#94a3b8;">Matrix Confluence:</td>
                        <td style="padding:6px 0;text-align:right;color:#10b981;
                                   font-weight:bold;">
                            {score}% Match
                        </td>
                    </tr>
                    <tr>
                        <td style="padding:6px 0;color:#94a3b8;">Engine Validation:</td>
                        <td style="padding:6px 0;text-align:right;color:#eab308;
                                   font-weight:bold;">
                            Gann + Wyckoff Verified
                        </td>
                    </tr>
                </table>
            </div>

            <p style="font-size:13px;color:#64748b;margin-bottom:24px;">
                Price is testing the low-risk danger point.
                Ensure your protective stop levels are configured
                within structural parameters.
            </p>

            <a href="https://sigmalytic-frontend.onrender.com"
               style="display:block;text-align:center;background-color:#2563eb;
                      color:#ffffff;padding:14px 24px;text-decoration:none;
                      font-weight:bold;border-radius:8px;font-size:14px;
                      box-shadow:0 4px 12px rgba(37,99,235,0.2);">
                Open Sigmalytic Dashboard
            </a>
        </div>
        """

        resend.Emails.send({
            "from"   : "Sigmalytic Engine <alerts@sigmalyticquantcorp.com>",
            "to"     : to_email,
            "subject": f"[SIGNAL] {setup_type} on {ticker} — {score}% Confluence",
            "html"   : html_content
        })

        log.info(f"Alert email sent to {to_email} for {ticker} ({score}%)")

    except Exception as e:
        log.error(f"Resend error for {ticker} → {to_email}: {str(e)}")


# ================================================================================
# API ENDPOINT
# ================================================================================

@router.post("/dispatch-confluence-alert")
async def dispatch_confluence_alert(
    payload         : ConfluenceAlertPayload,
    background_tasks: BackgroundTasks
):
    """
    Receives a confluence alert payload from the scan loop.
    Offloads email delivery to a background thread instantly
    without blocking the 60-second radar cycle.
    """
    try:
        background_tasks.add_task(
            execute_async_email_send,
            to_email   = payload.recipient_email,
            ticker     = payload.ticker,
            score      = payload.score,
            price      = payload.price,
            setup_type = payload.setup_type
        )
        return {
            "status" : "accepted",
            "message": f"Alert queued for {payload.ticker} → {payload.recipient_email}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================================================================================
# DIRECT SEND UTILITY (called internally by radar_alerts.py)
# ================================================================================

def send_confluence_alert_direct(
    to_email  : str,
    ticker    : str,
    score     : int,
    price     : float,
    setup_type: str
) -> None:
    """
    Direct synchronous send — use when BackgroundTasks is not available.
    Called by radar_alerts.py when a status change triggers an alert.
    """
    execute_async_email_send(to_email, ticker, score, price, setup_type)