"""
radar_alerts.py — Sigmalytic Quant
Builds rich HTML alert emails and dispatches via email_service.
Wyckoff SC/AR/ST anchor levels included.
Now routes through preference-aware dispatch in email_service.
"""

import logging
from datetime import datetime, timezone
from fastapi import BackgroundTasks

from email_service import dispatch_alert_to_all_users

logger = logging.getLogger(__name__)


# ── HTML Builder ──────────────────────────────────────────────────────────────

def build_alert_html(
    symbol: str,
    alert_type: str,
    score: int,
    details: dict,
) -> tuple[str, str]:
    """
    Returns (subject, html_body) for a single alert email.

    details dict can contain:
        price           float
        wyckoff_sc      float | None    SC low anchor
        wyckoff_ar      float | None    AR high anchor
        wyckoff_st      float | None    ST low anchor
        gann_angles     list[dict]      [{"angle": 45, "level": 123.45}, ...]
        ab_score        float | None
        message         str | None      free-form note
    """
    price       = details.get("price", 0)
    wyckoff_sc  = details.get("wyckoff_sc")
    wyckoff_ar  = details.get("wyckoff_ar")
    wyckoff_st  = details.get("wyckoff_st")
    gann_angles = details.get("gann_angles", [])
    ab_score    = details.get("ab_score")
    message     = details.get("message", "")

    subject = f"[Sigmalytic] {symbol} — {alert_type.upper()} Alert | Score: {score}"

    wyckoff_rows = ""
    if any([wyckoff_sc, wyckoff_ar, wyckoff_st]):
        wyckoff_rows = f"""
        <tr><td colspan="2" style="padding:8px 0 4px;font-weight:bold;color:#c9a84c;">
            Wyckoff Anchors
        </td></tr>
        {"<tr><td>SC Low</td><td><b>" + f"{wyckoff_sc:.2f}" + "</b></td></tr>" if wyckoff_sc else ""}
        {"<tr><td>AR High</td><td><b>" + f"{wyckoff_ar:.2f}" + "</b></td></tr>" if wyckoff_ar else ""}
        {"<tr><td>ST Low</td><td><b>" + f"{wyckoff_st:.2f}" + "</b></td></tr>" if wyckoff_st else ""}
        """

    gann_rows = ""
    if gann_angles:
        gann_rows = """<tr><td colspan="2" style="padding:8px 0 4px;font-weight:bold;color:#c9a84c;">
            Gann Vectors
        </td></tr>"""
        for g in gann_angles[:5]:  # top 5 angles
            gann_rows += f"<tr><td>{g['angle']}°</td><td><b>{g['level']:.2f}</b></td></tr>"

    ab_row = ""
    if ab_score is not None:
        ab_row = f"<tr><td>A/B Score</td><td><b>{ab_score:.1f}</b></td></tr>"

    html_body = f"""
    <html>
    <body style="background:#0d0d0d;color:#e8e8e8;font-family:monospace;padding:24px;">
      <div style="max-width:520px;margin:0 auto;border:1px solid #2a2a2a;
                  border-radius:8px;padding:24px;background:#111;">

        <div style="font-size:22px;font-weight:bold;color:#c9a84c;margin-bottom:4px;">
          ⚡ {symbol}
        </div>
        <div style="font-size:13px;color:#888;margin-bottom:20px;">
          {alert_type.upper()} &nbsp;·&nbsp; {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        </div>

        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <tr>
            <td style="padding:4px 0;color:#aaa;">Price</td>
            <td style="padding:4px 0;"><b>${price:.2f}</b></td>
          </tr>
          <tr>
            <td style="padding:4px 0;color:#aaa;">Confluence Score</td>
            <td style="padding:4px 0;">
              <b style="color:{'#4caf50' if score >= 75 else '#ff9800' if score >= 55 else '#f44336'};">
                {score}
              </b>
            </td>
          </tr>
          {ab_row}
          {wyckoff_rows}
          {gann_rows}
        </table>

        {"<p style='margin-top:16px;font-size:13px;color:#aaa;'>" + message + "</p>" if message else ""}

        <p style="margin-top:24px;font-size:11px;color:#444;border-top:1px solid #222;padding-top:12px;">
          Sigmalytic Quant — not financial advice.<br>
          <a href="https://sigmalytic.com/preferences" style="color:#c9a84c;">
            Manage alert preferences
          </a>
        </p>
      </div>
    </body>
    </html>
    """

    return subject, html_body


# ── Dispatch ──────────────────────────────────────────────────────────────────

async def fire_alert(
    symbol: str,
    alert_type: str,
    score: int,
    details: dict,
    background_tasks: BackgroundTasks,
    timestamp: datetime | None = None,
) -> None:
    """
    Build alert payload, construct HTML, and dispatch to all qualifying users.

    alert_type examples: 'wyckoff' | 'gann' | 'ab_score' | 'elliott' | 'fibonacci'
    """
    ts = timestamp or datetime.now(timezone.utc)

    alert_meta = {
        "symbol":     symbol,
        "alert_type": alert_type,
        "score":      score,
        "timestamp":  ts,
    }

    subject, html_body = build_alert_html(symbol, alert_type, score, details)

    logger.info(f"[radar_alerts] Firing {alert_type} alert for {symbol} (score={score})")

    await dispatch_alert_to_all_users(
        alert=alert_meta,
        subject=subject,
        html_body=html_body,
        background_tasks=background_tasks,
    )
