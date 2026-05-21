"""
backend/radar_alerts.py
-----------------------
Sigmalytic Radar — Email Alert System via Resend

Sends email alerts when symbols change to Armed or Triggered status.
Called from radar_service.py _process_events()

ALERT TYPES
───────────
Armed          — Setup is ready, trigger is imminent
Triggered      — Price crossed trigger level on volume
Confirmed      — Setup followed through
Failed         — Setup failed below invalidation
Short Trigger  — Price broke below invalidation on volume
Short Confirmed— Continued lower
Short Armed    — Approaching breakdown level

MULTI-USER
──────────
Alerts are sent to ALL registered Supabase users, not just the admin.
User list is refreshed every 10 minutes from Supabase auth.
"""

from __future__ import annotations
import os
import logging
import time
import requests as _req
from datetime import datetime, timezone

log = logging.getLogger("radar_alerts")

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
ALERT_TO_EMAIL  = os.getenv("ALERT_EMAIL", "greg.kosmala@gmail.com")
ALERT_FROM      = "Sigmalytic Quant Corporation <alerts@sigmalyticquantcorp.com>"
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ANON_KEY    = os.getenv("SUPABASE_ANON_KEY", "")

# Only send alerts for these status transitions
ALERT_STATUSES = {
    "Armed", "Triggered", "Confirmed", "Failed",
    "Short Trigger", "Short Confirmed", "Short Armed"
}

# Track which alerts have been sent to avoid duplicates
# symbol → last alerted status
_alerted: dict[str, str] = {}

# Cached user email list — refreshed every 10 minutes
_user_emails: list[str] = []
_user_emails_last_refresh: float = 0
USER_EMAIL_REFRESH_INTERVAL = 600   # 10 minutes


def _get_all_user_emails() -> list[str]:
    """
    Fetch all registered user emails from Supabase auth.
    Uses service role key if available, falls back to listing
    from the users table. Caches results for 10 minutes.
    """
    global _user_emails, _user_emails_last_refresh

    # Return cached list if still fresh
    if time.time() - _user_emails_last_refresh < USER_EMAIL_REFRESH_INTERVAL:
        return _user_emails

    emails = set()

    # Always include the admin email
    if ALERT_TO_EMAIL:
        emails.add(ALERT_TO_EMAIL)

    # Try Supabase admin API to get all users
    # Requires SUPABASE_SERVICE_ROLE_KEY (different from anon key)
    service_key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    if SUPABASE_URL and service_key:
        try:
            r = _req.get(
                f"{SUPABASE_URL}/auth/v1/admin/users",
                headers={
                    "apikey":        service_key,
                    "Authorization": f"Bearer {service_key}",
                },
                params={"per_page": 1000},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                users = data.get("users", [])
                for user in users:
                    email = user.get("email", "")
                    # Only include confirmed users
                    confirmed = user.get("email_confirmed_at") or user.get("confirmed_at")
                    if email and confirmed:
                        emails.add(email)
                log.info(f"Loaded {len(emails)} user emails from Supabase")
            else:
                log.warning(f"Supabase user list failed {r.status_code}: {r.text[:200]}")
                log.info("Falling back to admin email only")
        except Exception as e:
            log.warning(f"User email fetch error: {e}")

    result = list(emails)
    _user_emails = result
    _user_emails_last_refresh = time.time()
    return result


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


def _build_email_html(sym: dict, old_status: str, new_status: str) -> str:
    """Build the HTML email body for a radar alert."""
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

  <!-- Header -->
  <div style="text-align:center;margin-bottom:32px;">
    <div style="font-size:32px;font-weight:900;color:#34d399;letter-spacing:-.02em;">Σ SIGMALYTIC</div>
    <div style="font-size:11px;font-weight:700;color:#64748b;letter-spacing:.3em;text-transform:uppercase;margin-top:4px;">QUANT CORPORATION · RADAR ALERT</div>
  </div>

  <!-- Alert card -->
  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:20px;padding:28px;margin-bottom:20px;">

    <!-- Status badge -->
    <div style="text-align:center;margin-bottom:20px;">
      <span style="background:{status_color}18;border:1px solid {status_color};border-radius:999px;padding:6px 20px;font-size:12px;font-weight:800;color:{status_color};text-transform:uppercase;letter-spacing:.1em;">
        {emoji} {new_status}
      </span>
    </div>

    <!-- Symbol + price -->
    <div style="text-align:center;margin-bottom:24px;">
      <div style="font-size:48px;font-weight:900;color:#f1f5f9;letter-spacing:-.02em;font-family:'Courier New',monospace;">{symbol}</div>
      <div style="font-size:22px;font-weight:700;color:#f1f5f9;margin-top:4px;">${price:,.2f} <span style="font-size:16px;color:{chg_color};">{'+' if chg>=0 else ''}{chg:.2f}%</span></div>
      <div style="font-size:13px;color:#94a3b8;margin-top:6px;">{setup}</div>
    </div>

    <!-- Score + Regime + Proximity -->
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

    <!-- Projection paths -->
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

    <!-- Key levels -->
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

  <!-- Status transition -->
  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:14px;margin-bottom:20px;text-align:center;">
    <span style="font-size:12px;color:#94a3b8;">Status changed: </span>
    <span style="font-size:12px;font-weight:700;color:#94a3b8;">{old_status or 'New'}</span>
    <span style="font-size:12px;color:#64748b;"> → </span>
    <span style="font-size:12px;font-weight:800;color:{status_color};">{new_status}</span>
    <span style="font-size:11px;color:#64748b;display:block;margin-top:4px;">{now}</span>
  </div>

  <!-- Footer -->
  <div style="text-align:center;padding-top:16px;border-top:1px solid rgba(255,255,255,.06);">
    <div style="font-size:11px;color:#475569;margin-bottom:4px;">Sigmalytic Quant Corporation · Decision Intelligence Platform</div>
    <div style="font-size:10px;color:#334155;">Data is 15-minute delayed (Alpaca IEX free feed). Not financial advice.</div>
  </div>

</div>
</body>
</html>
"""


def send_alert(sym: dict, old_status: str, new_status: str) -> bool:
    """
    Send an email alert to ALL registered users for a status change.
    Returns True if at least one email sent successfully.
    """
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY not set — skipping alert")
        return False

    symbol  = sym.get("symbol", "Unknown")
    emoji   = _status_emoji(new_status)
    subject = f"{emoji} {symbol} — {new_status} | Score {sym.get('composite_score',0):.0f} | Trigger ${sym.get('trigger',0):,.2f}"
    html    = _build_email_html(sym, old_status, new_status)

    # Get all user emails
    recipients = _get_all_user_emails()
    if not recipients:
        recipients = [ALERT_TO_EMAIL]

    log.info(f"Sending alert for {symbol} → {new_status} to {len(recipients)} recipient(s)")

    success = False
    for email in recipients:
        if not email or "@" not in email:
            continue
        try:
            r = _req.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "from":    ALERT_FROM,
                    "to":      [email],
                    "subject": subject,
                    "html":    html,
                },
                timeout=10,
            )
            if r.status_code in (200, 201):
                log.info(f"Alert sent: {symbol} → {new_status} → {email}")
                success = True
            else:
                log.warning(f"Alert failed for {email} — {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"Alert error for {email}: {e}")

    return success


def maybe_send_alert(sym: dict, old_status: str, new_status: str):
    """
    Send alert only if:
    1. New status is in ALERT_STATUSES
    2. We haven't already alerted for this symbol+status combo
    """
    symbol = sym.get("symbol", "")

    if new_status not in ALERT_STATUSES:
        return

    # Don't resend the same alert
    last = _alerted.get(symbol)
    if last == new_status:
        return

    sent = send_alert(sym, old_status, new_status)
    if sent:
        _alerted[symbol] = new_status


def send_daily_summary(symbols: list):
    """
    Send a daily summary email to ALL registered users.
    Called once per day from the scheduler at 8:00 AM ET.
    """
    if not RESEND_API_KEY:
        return

    top      = sorted(symbols, key=lambda x: x.get("composite_score", 0), reverse=True)[:10]
    armed    = [s for s in symbols if s.get("status") == "Armed"]
    building = [s for s in symbols if s.get("status") == "Building"]
    triggered= [s for s in symbols if s.get("status") in ("Triggered", "Confirmed")]

    rows = ""
    for i, s in enumerate(top, 1):
        score  = s.get("composite_score", 0)
        status = s.get("status", "Watching")
        sc     = "#34d399" if score >= 75 else ("#fde68a" if score >= 60 else "#f87171")
        rows += f"""
        <tr style="border-bottom:1px solid rgba(255,255,255,.06);">
          <td style="padding:10px 12px;color:#94a3b8;font-size:12px;">#{i}</td>
          <td style="padding:10px 12px;color:#f1f5f9;font-weight:800;font-family:'Courier New',monospace;">{s.get('symbol','')}</td>
          <td style="padding:10px 12px;color:#f1f5f9;">${s.get('price',0):,.2f}</td>
          <td style="padding:10px 12px;color:{sc};font-weight:800;">{score:.0f}</td>
          <td style="padding:10px 12px;color:#94a3b8;">{status}</td>
          <td style="padding:10px 12px;color:#fde68a;">${s.get('trigger',0):,.2f}</td>
          <td style="padding:10px 12px;color:#94a3b8;font-size:11px;">{s.get('setup_type','')}</td>
        </tr>"""

    now = datetime.now(timezone.utc).strftime("%B %d, %Y")

    html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#0d1b2e;font-family:'Helvetica Neue',Arial,sans-serif;">
<div style="max-width:700px;margin:0 auto;padding:32px 16px;">
  <div style="text-align:center;margin-bottom:32px;">
    <div style="font-size:28px;font-weight:900;color:#34d399;">Σ SIGMALYTIC</div>
    <div style="font-size:11px;color:#64748b;letter-spacing:.3em;text-transform:uppercase;margin-top:4px;">Daily Radar Summary · {now}</div>
  </div>

  <div style="display:flex;gap:12px;margin-bottom:24px;">
    <div style="flex:1;background:#111f35;border:1px solid rgba(52,211,153,.25);border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">Armed</div>
      <div style="font-size:32px;font-weight:900;color:#34d399;">{len(armed)}</div>
    </div>
    <div style="flex:1;background:#111f35;border:1px solid rgba(253,230,138,.25);border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">Building</div>
      <div style="font-size:32px;font-weight:900;color:#fde68a;">{len(building)}</div>
    </div>
    <div style="flex:1;background:#111f35;border:1px solid rgba(147,197,253,.25);border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">Triggered</div>
      <div style="font-size:32px;font-weight:900;color:#93c5fd;">{len(triggered)}</div>
    </div>
    <div style="flex:1;background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:16px;text-align:center;">
      <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:.12em;margin-bottom:6px;">Scanned</div>
      <div style="font-size:32px;font-weight:900;color:#94a3b8;">{len(symbols)}</div>
    </div>
  </div>

  <div style="background:#111f35;border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:hidden;margin-bottom:24px;">
    <div style="padding:16px 20px;border-bottom:1px solid rgba(255,255,255,.08);">
      <div style="font-size:13px;font-weight:800;color:#f1f5f9;">Top 10 Radar Picks · {now}</div>
    </div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="border-bottom:1px solid rgba(255,255,255,.08);">
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">#</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">Symbol</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">Price</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">Score</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">Status</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">Trigger</th>
          <th style="padding:8px 12px;text-align:left;font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.1em;">Setup</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <div style="text-align:center;padding-top:16px;border-top:1px solid rgba(255,255,255,.06);">
    <div style="font-size:11px;color:#475569;">Sigmalytic Quant Corporation · Decision Intelligence Platform</div>
    <div style="font-size:10px;color:#334155;margin-top:4px;">15-minute delayed data. Not financial advice.</div>
  </div>
</div>
</body>
</html>"""

    # Send to all registered users
    recipients = _get_all_user_emails()
    if not recipients:
        recipients = [ALERT_TO_EMAIL]

    subject = f"📡 Sigmalytic Daily Radar — {now} · {len(armed)} Armed · {len(building)} Building"

    for email in recipients:
        if not email or "@" not in email:
            continue
        try:
            r = _req.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json={
                    "from":    ALERT_FROM,
                    "to":      [email],
                    "subject": subject,
                    "html":    html,
                },
                timeout=10,
            )
            if r.status_code in (200, 201):
                log.info(f"Daily summary sent to {email}")
            else:
                log.warning(f"Daily summary failed for {email} — {r.status_code}: {r.text[:200]}")
        except Exception as e:
            log.warning(f"Daily summary error for {email}: {e}")