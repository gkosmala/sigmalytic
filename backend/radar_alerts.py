# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
radar_alerts.py — Sigmalytic Quant
Builds rich HTML alert emails and dispatches via email_service.
Wyckoff SC/AR/ST anchor levels included.
Routes through preference-aware dispatch in email_service.
"""

import logging
from datetime import datetime, timezone
from fastapi import BackgroundTasks

from backend.email_service import dispatch_alert_to_all_users

logger = logging.getLogger(__name__)


# ── HTML Builder ──────────────────────────────────────────────────────────────

def build_alert_html(
    symbol: str,
    alert_type: str,
    score: int,
    details: dict,
) -> tuple[str, str]:
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
        for g in gann_angles[:5]:
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
          <a href="https://sigmalytic-frontend.onrender.com/preferences.html" style="color:#c9a84c;">
            Manage alert preferences
          </a>
        </p>
      </div>
    </body>
    </html>
    """
    return subject, html_body


# ── maybe_send_alert — called by radar_service.py ────────────────────────────

def maybe_send_alert(symbol_data: dict, old_status: str, new_status: str) -> bool:
    """
    Synchronous wrapper called by radar_service.py on status changes.
    Builds alert payload and queues via dispatch (fire-and-forget).
    """
    import asyncio

    symbol = symbol_data.get("symbol", "")
    score  = int(symbol_data.get("composite_score", 0))

    details = {
        "price":      symbol_data.get("price", 0),
        "ab_score":   symbol_data.get("ab_score"),
        "wyckoff_sc": symbol_data.get("wyckoff_sc"),
        "wyckoff_ar": symbol_data.get("wyckoff_ar"),
        "wyckoff_st": symbol_data.get("wyckoff_st"),
        "message":    f"Status changed: {old_status} → {new_status}",
    }

    subject, html_body = build_alert_html(symbol, "ab_score", score, details)

    alert_meta = {
        "symbol":     symbol,
        "alert_type": "ab_score",
        "score":      score,
        "timestamp":  datetime.now(timezone.utc),
    }

    try:
        import threading

        def _run():
            asyncio.run(dispatch_alert_to_all_users(
                alert=alert_meta,
                subject=subject,
                html_body=html_body,
            ))

        threading.Thread(target=_run, daemon=True).start()
        return True
    except Exception as e:
        logger.error(f"[maybe_send_alert] Failed for {symbol}: {e}")
        return False


# ── send_daily_summary — called by radar_service.py ──────────────────────────

def send_daily_summary(top_symbols: list[dict]) -> bool:
    """
    Sends a daily summary email of top-scoring symbols.
    Called by radar_service.py at market close.
    """
    import asyncio

    if not top_symbols:
        return False

    rows = ""
    for s in top_symbols[:20]:
        symbol = s.get("symbol", "")
        score  = s.get("composite_score", 0)
        status = s.get("status", "")
        rows += f"<tr><td>{symbol}</td><td>{score:.1f}</td><td>{status}</td></tr>"

    html_body = f"""
    <html>
    <body style="background:#0d0d0d;color:#e8e8e8;font-family:monospace;padding:24px;">
      <div style="max-width:600px;margin:0 auto;border:1px solid #2a2a2a;
                  border-radius:8px;padding:24px;background:#111;">
        <div style="font-size:20px;font-weight:bold;color:#c9a84c;margin-bottom:16px;">
          📊 Sigmalytic Daily Summary
        </div>
        <div style="font-size:12px;color:#888;margin-bottom:20px;">
          {datetime.now(timezone.utc).strftime("%Y-%m-%d")} — Top Signals
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr style="color:#c9a84c;">
            <th style="text-align:left;padding:4px 0;">Symbol</th>
            <th style="text-align:left;padding:4px 0;">Score</th>
            <th style="text-align:left;padding:4px 0;">Status</th>
          </tr>
          {rows}
        </table>
        <p style="margin-top:24px;font-size:11px;color:#444;border-top:1px solid #222;padding-top:12px;">
          Sigmalytic Quant — not financial advice.<br>
          <a href="https://sigmalytic-frontend.onrender.com/preferences.html" style="color:#c9a84c;">
            Manage alert preferences
          </a>
        </p>
      </div>
    </body>
    </html>
    """

    subject = f"[Sigmalytic] Daily Summary — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

    alert_meta = {
        "symbol":     "SUMMARY",
        "alert_type": "ab_score",
        "score":      100,
        "timestamp":  datetime.now(timezone.utc),
    }

    try:
        import threading

        def _run():
            asyncio.run(dispatch_alert_to_all_users(
                alert=alert_meta,
                subject=subject,
                html_body=html_body,
            ))

        threading.Thread(target=_run, daemon=True).start()
        return True
    except Exception as e:
        logger.error(f"[send_daily_summary] Failed: {e}")
        return False


# ── fire_alert — async dispatch ───────────────────────────────────────────────

async def fire_alert(
    symbol: str,
    alert_type: str,
    score: int,
    details: dict,
    background_tasks: BackgroundTasks,
    timestamp: datetime | None = None,
) -> None:
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


# ── Legacy send_alert wrapper ─────────────────────────────────────────────────

def send_alert(symbol_data: dict, old_status: str, new_status: str) -> bool:
    """Alias for maybe_send_alert for backward compatibility."""
    return maybe_send_alert(symbol_data, old_status, new_status)
