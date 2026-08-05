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

ALERT_STATUSES = {
    "Armed", "Triggered", "Confirmed", "Failed",
    "Short Trigger", "Short Confirmed", "Short Armed",
}


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
    """
    The restored, real template -- reconstructed directly from the actual
    working version (git history, pre-2026-05-25), not rebuilt from memory.
    """
    symbol    = sym.get("symbol", "")
    price     = sym.get("price", 0)
    score     = sym.get("composite_score", 0)
    setup     = sym.get("setup_type", "—")
    trigger   = sym.get("trigger", 0)
    inval     = sym.get("invalidation", 0)
    target1   = sym.get("target1", 0)
    target2   = sym.get("target2", 0)
    regime    = sym.get("regime", "—")
    chg       = sym.get("change_pct", 0)
    proximity = sym.get("trigger_proximity", 0)
    atr       = sym.get("atr", 0)
    emoji     = _status_emoji(new_status)

    bear1 = round(inval - atr, 2)
    bear2 = round(inval - atr * 2, 2)

    chg_color    = "#34d399" if chg >= 0 else "#f87171"
    score_color  = "#34d399" if score >= 75 else ("#fde68a" if score >= 60 else "#f87171")
    status_color = {
        "Armed":           "#34d399",
        "Triggered":       "#93c5fd",
        "Confirmed":       "#34d399",
        "Failed":          "#f87171",
        "Short Trigger":   "#f87171",
        "Short Confirmed": "#f87171",
        "Short Armed":     "#ff6b6b",
    }.get(new_status, "#94a3b8")

    now = datetime.now(timezone.utc).strftime("%B %d, %Y %I:%M %p UTC")

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#0d1b2e;font-family:'Helvetica Neue',Arial,sans-serif;">
<div style="max-width:600px;margin:0 auto;padding:32px 16px;">

  <div style="text-align:center;margin-bottom:32px;">
    <div style="font-size:32px;font-weight:900;color:#34d399;letter-spacing:-.02em;">Σ SIGMALYTIC</div>
    <div style="font-size:11px;font-weight:700;color:#64748b;letter-spacing:.3em;text-transform:uppercase;margin-top:4px;">QUANT CORPORATION · RADAR ALERT</div>
  </div>

  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:28px;margin-bottom:20px;">

    <div style="text-align:center;margin-bottom:20px;">
      <span style="background:{status_color}18;border:1px solid {status_color};border-radius:999px;padding:6px 20px;font-size:12px;font-weight:800;color:{status_color};text-transform:uppercase;letter-spacing:.1em;">
        {emoji} {new_status}
      </span>
    </div>

    <div style="text-align:center;margin-bottom:24px;">
      <div style="font-size:48px;font-weight:900;color:#f1f5f9;letter-spacing:-.02em;font-family:'Courier New',monospace;">{symbol}</div>
      <div style="font-size:22px;font-weight:700;color:#f1f5f9;margin-top:4px;">${price:,.2f} <span style="font-size:16px;color:{chg_color};">{'+' if chg>=0 else ''}{chg:.2f}%</span></div>
      <div style="font-size:13px;color:#94a3b8;margin-top:6px;">{setup}</div>
    </div>

    <div style="display:flex;gap:12px;margin-bottom:20px;">
      <div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;text-align:center;">
        <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">Score</div>
        <div style="font-size:28px;font-weight:900;color:{score_color};">{score:.0f}</div>
      </div>
      <div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;text-align:center;">
        <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">Regime</div>
        <div style="font-size:14px;font-weight:800;color:#f1f5f9;">{regime}</div>
      </div>
      <div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;text-align:center;">
        <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">To Trigger</div>
        <div style="font-size:16px;font-weight:800;color:#fde68a;">{proximity:+.1f}%</div>
      </div>
    </div>

    <div style="border-top:1px solid rgba(255,255,255,.08);padding-top:20px;">
      <div style="font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:.2em;margin-bottom:14px;">Projection Paths</div>

      <div style="background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.25);border-radius:10px;padding:12px 14px;margin-bottom:8px;">
        <div style="font-size:11px;font-weight:800;color:#34d399;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;">▲ Bull Path</div>
        <div style="font-size:13px;color:#34d399;font-family:'Courier New',monospace;">Above ${trigger:,.2f} → ${target1:,.2f} → ${target2:,.2f}</div>
      </div>

      <div style="background:rgba(253,230,138,.08);border:1px solid rgba(253,230,138,.25);border-radius:10px;padding:12px 14px;margin-bottom:8px;">
        <div style="font-size:11px;font-weight:800;color:#fde68a;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;">◆ Neutral Zone</div>
        <div style="font-size:13px;color:#fde68a;font-family:'Courier New',monospace;">${inval:,.2f} – ${trigger:,.2f} chop zone</div>
      </div>

      <div style="background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.25);border-radius:10px;padding:12px 14px;">
        <div style="font-size:11px;font-weight:800;color:#f87171;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px;">▼ Bear Path</div>
        <div style="font-size:13px;color:#f87171;font-family:'Courier New',monospace;">Below ${inval:,.2f} → ${bear1:,.2f} → ${bear2:,.2f}</div>
      </div>
    </div>

    <div style="display:flex;gap:8px;margin-top:16px;">
      <div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(253,230,138,.25);border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;">Trigger</div>
        <div style="font-size:15px;font-weight:800;color:#fde68a;font-family:'Courier New',monospace;">${trigger:,.2f}</div>
      </div>
      <div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(248,113,113,.25);border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;">Invalidation</div>
        <div style="font-size:15px;font-weight:800;color:#f87171;font-family:'Courier New',monospace;">${inval:,.2f}</div>
      </div>
      <div style="flex:1;background:rgba(0,0,0,.25);border:1px solid rgba(52,211,153,.25);border-radius:10px;padding:12px;text-align:center;">
        <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px;">Target 1</div>
        <div style="font-size:15px;font-weight:800;color:#34d399;font-family:'Courier New',monospace;">${target1:,.2f}</div>
      </div>
    </div>

  </div>

  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;margin-bottom:20px;text-align:center;">
    <span style="font-size:12px;color:#94a3b8;">Status changed: </span>
    <span style="font-size:12px;font-weight:700;color:#94a3b8;">{old_status or 'New'}</span>
    <span style="font-size:12px;color:#64748b;"> → </span>
    <span style="font-size:12px;font-weight:800;color:{status_color};">{new_status}</span>
    <span style="font-size:11px;color:#64748b;display:block;margin-top:4px;">{now}</span>
  </div>

  <div style="text-align:center;padding-top:16px;border-top:1px solid rgba(255,255,255,.06);">
    <div style="font-size:11px;color:#475569;">Sigmalytic Quant Corporation · Decision Intelligence Platform</div>
    <div style="font-size:10px;color:#334155;">Data is 15-minute delayed (Alpaca IEX free feed). Not financial advice.</div>
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

    score = int(symbol_data.get("composite_score", 0))
    emoji = _status_emoji(new_status)
    subject = (
        f"{emoji} {symbol} — {new_status} | Score {score} | "
        f"Trigger ${symbol_data.get('trigger', 0):,.2f}"
    )
    html_body = _build_status_change_email_html(symbol_data, old_status, new_status)

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
        _alerted[symbol] = new_status
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
