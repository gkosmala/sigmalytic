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


# ── Restored rich status-change template ──────────────────────────────────────
# FIX (2026-08-05): user confirmed a real email received 2026-05-24 had rich
# content (Armed badge, Score/Regime/To Trigger, Projection Paths with Bull/
# Neutral/Bear paths) that no longer matched anything in the current app.
# Traced via git history: a real, working template existed in this exact file
# before commit c4d12f1 ("Add user preferences filter system for alert
# emails", 2026-05-25 -- one day after that email) rewrote this file and
# replaced it with the much simpler template below (build_alert_html/
# fire_alert, still preserved as-is further down, unused by anything today
# but left intact for backward compatibility). This restores that original,
# richer template for maybe_send_alert() specifically -- the function that's
# still genuinely called by radar_service.py on every real status change --
# while keeping the CURRENT, improved preference-aware dispatch_alert_to_
# all_users() for actual sending rather than reverting to the old direct
# per-recipient Resend loop, since the preference-filtering system is a real,
# valuable addition from that same rewrite worth keeping.

# Track which alerts have been sent to avoid duplicates -- restored from the
# original: only alert again when a symbol's status genuinely changes, not
# every time a scan cycle re-confirms the same, still-active status. Directly
# answers user's "wouldn't tomorrow's alert be stale" concern.
_alerted: dict[str, str] = {}

# The scan's status is the Weis setup state. Only the armed states are alerted.
ALERT_STATUSES = {"Armed", "Short Armed"}


def _status_emoji(status: str) -> str:
    return {
        "Armed":           "🎯",
        "Triggered":       "⚡",
        "Confirmed":       "✅",
        "Failed":          "❌",
        "Short Trigger":   "🔻",
        "Short Confirmed": "🔴",
        "Short Armed":     "⚠️",
    }.get(status, "📡")


def _build_status_change_email_html(sym: dict, old_status: str, new_status: str) -> str:
    """Weis setup-state alert. Content: the state, direction, the reason, stop and target
    from the Weis setup-state engine. No composite score, trigger or projection paths."""
    symbol    = sym.get("symbol", "")
    price     = sym.get("price", 0) or 0
    chg       = sym.get("change_pct", 0) or 0
    d         = sym.get("status_direction")
    side      = {"long": "Long (spring)", "short": "Short (upthrust)"}.get(d, "—")
    reason    = sym.get("status_reason") or ""
    stop      = sym.get("status_stop")
    target    = sym.get("status_target")
    stop_txt  = f"${stop:,.2f}" if isinstance(stop, (int, float)) else "—"
    tgt_txt   = f"${target:,.2f}" if isinstance(target, (int, float)) else "none defined"
    emoji     = _status_emoji(new_status)
    chg_color = "#34d399" if chg >= 0 else "#f87171"
    status_color = "#ff6b6b" if new_status == "Short Armed" else "#34d399"
    now = datetime.now(timezone.utc).strftime("%B %d, %Y %I:%M %p UTC")

    def tile(label, value, color):
        return (f'<div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.08);'
                f'border-radius:12px;padding:14px;text-align:center;">'
                f'<div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;'
                f'letter-spacing:.12em;margin-bottom:6px;">{label}</div>'
                f'<div style="font-size:16px;font-weight:800;color:{color};font-family:\'Courier New\',monospace;">{value}</div></div>')

    reason_html = (f'<div style="font-size:13px;color:#cbd5e1;text-align:center;margin-bottom:20px;">{reason}</div>'
                   if reason else "")
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0d1b2e;font-family:'Helvetica Neue',Arial,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 16px;">
  <div style="text-align:center;margin-bottom:32px;">
    <div style="font-size:32px;font-weight:900;color:#34d399;letter-spacing:-.02em;">Σ SIGMALYTIC</div>
    <div style="font-size:11px;font-weight:700;color:#64748b;letter-spacing:.3em;text-transform:uppercase;margin-top:4px;">QUANT CORPORATION · WEIS SETUP ALERT</div>
  </div>
  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:28px;margin-bottom:20px;">
    <div style="text-align:center;margin-bottom:20px;">
      <span style="background:{status_color}18;border:1px solid {status_color};border-radius:999px;padding:6px 20px;font-size:12px;font-weight:800;color:{status_color};text-transform:uppercase;letter-spacing:.1em;">{emoji} {new_status}</span>
    </div>
    <div style="text-align:center;margin-bottom:24px;">
      <div style="font-size:48px;font-weight:900;color:#f1f5f9;letter-spacing:-.02em;font-family:'Courier New',monospace;">{symbol}</div>
      <div style="font-size:22px;font-weight:700;color:#f1f5f9;margin-top:4px;">${price:,.2f} <span style="font-size:16px;color:{chg_color};">{'+' if chg>=0 else ''}{chg:.2f}%</span></div>
    </div>
    {reason_html}
    <div style="display:flex;gap:12px;">
      {tile("Direction", side, "#f1f5f9")}
      {tile("Stop", stop_txt, "#f87171")}
      {tile("Target", tgt_txt, "#34d399")}
    </div>
  </div>
  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;margin-bottom:20px;text-align:center;">
    <span style="font-size:12px;color:#94a3b8;">Setup state changed: </span>
    <span style="font-size:12px;font-weight:700;color:#94a3b8;">{old_status or 'New'}</span>
    <span style="font-size:12px;color:#64748b;"> → </span>
    <span style="font-size:12px;font-weight:800;color:{status_color};">{new_status}</span>
    <span style="font-size:11px;color:#64748b;display:block;margin-top:4px;">{now}</span>
  </div>
  <div style="text-align:center;padding-top:16px;border-top:1px solid rgba(255,255,255,.06);">
    <div style="font-size:11px;color:#475569;">Sigmalytic Quant Corporation · Decision Intelligence Platform</div>
    <div style="font-size:10px;color:#334155;">Based on completed daily bars. Not financial advice.</div>
  </div>
</div>
</body>
</html>
"""


# ── HTML Builder (generic, non-status-change alerts) ──────────────────────────

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
    Called by radar_service.py on status changes. Restored (2026-08-05)
    to use the real, rich status-change template and duplicate-
    prevention logic that existed before the 2026-05-25 rewrite --
    see the module-level comment above _build_status_change_email_html
    for the full trace.

    Only alerts on genuine status changes into ALERT_STATUSES, and
    only once per distinct new status per symbol (via _alerted) --
    a symbol that stays "Armed" across many scan cycles does not
    re-trigger an email every cycle, only when the status itself
    changes to something new.
    """
    import asyncio

    symbol = symbol_data.get("symbol", "")

    if new_status not in ALERT_STATUSES:
        return False

    if _alerted.get(symbol) == new_status:
        return False

    emoji = _status_emoji(new_status)
    stop = symbol_data.get("status_stop")
    subject = f"{emoji} {symbol} — {new_status}" + (f" | Stop ${stop:,.2f}" if isinstance(stop, (int, float)) else "")
    html_body = _build_status_change_email_html(symbol_data, old_status, new_status)

    # weis_state: this alert has no score, so the user's minimum-score setting does not apply.
    alert_meta = {
        "symbol":     symbol,
        "alert_type": "ab_score",
        "score":      0,
        "weis_state": True,
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
        _alerted[symbol] = new_status
        return True
    except Exception as e:
        logger.error(f"[maybe_send_alert] Failed for {symbol}: {e}")
        return False



# ── send_daily_summary — called by radar_service.py ──────────────────────────

_SUMMARY_STATE_ORDER = {"Armed": 0, "Setting Up": 1, "Watching": 2}


def send_daily_summary(top_symbols: list[dict]) -> bool:
    """
    Daily summary of the Weis setup states from the radar scan: Armed, then
    Setting Up, then Watching, with direction, stop and target. No score.
    """
    import asyncio

    picked = [s for s in (top_symbols or []) if s.get("status") in _SUMMARY_STATE_ORDER]
    if not picked:
        return False
    picked.sort(key=lambda s: (_SUMMARY_STATE_ORDER[s["status"]], s.get("symbol", "")))
    counts = {k: sum(1 for s in picked if s["status"] == k) for k in _SUMMARY_STATE_ORDER}

    def _lvl(v):
        return f"${v:,.2f}" if isinstance(v, (int, float)) else "—"

    rows = ""
    for s in picked[:30]:
        d = {"long": "Long (spring)", "short": "Short (upthrust)"}.get(s.get("status_direction"), "—")
        rows += (f"<tr><td>{s.get('symbol', '')}</td><td>{s['status']}</td><td>{d}</td>"
                 f"<td>{_lvl(s.get('status_stop'))}</td><td>{_lvl(s.get('status_target'))}</td></tr>")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    html_body = f"""
    <html>
    <body style="background:#0d0d0d;color:#e8e8e8;font-family:monospace;padding:24px;">
      <div style="max-width:640px;margin:0 auto;border:1px solid #2a2a2a;
                  border-radius:8px;padding:24px;background:#111;">
        <div style="font-size:20px;font-weight:bold;color:#c9a84c;margin-bottom:16px;">
          📊 Sigmalytic Daily Summary
        </div>
        <div style="font-size:12px;color:#888;margin-bottom:20px;">
          {today} — Weis setups: {counts['Armed']} Armed · {counts['Setting Up']} Setting Up · {counts['Watching']} Watching
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <tr style="color:#c9a84c;">
            <th style="text-align:left;padding:4px 0;">Symbol</th>
            <th style="text-align:left;padding:4px 0;">State</th>
            <th style="text-align:left;padding:4px 0;">Direction</th>
            <th style="text-align:left;padding:4px 0;">Stop</th>
            <th style="text-align:left;padding:4px 0;">Target</th>
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

    subject = f"[Sigmalytic] Daily Summary — {today}"

    alert_meta = {
        "symbol":     "SUMMARY",
        "alert_type": "ab_score",
        "score":      0,
        "weis_state": True,
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
