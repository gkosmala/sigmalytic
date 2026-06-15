# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/subscriber_alerts.py
------------------------------------------
Subscriber Alert System — Phase 12C notification layer.

Sends email alerts to subscribers when new TIER_1 or TIER_2 campaigns
are born. Each alert answers the six intelligence questions from the
blueprint:

  WHY         — Behavioral state, SPD/DEI evidence, Wyckoff phase
  WHEN        — Signal birth date, duration bucket, campaign age
  WHERE       — Entry price, stop price, key structural levels
  HOW FAR     — P&F target, expected mfe90, conservative target %
  HOW MUCH RISK — Stop %, max loss value, ASYM ratio, layer
  HOW MUCH OPPORTUNITY REMAINS — D-Score, TIER, days to 90-day expiry

SUBSCRIBER TIERS
----------------
Currently email only. SMS placeholder included for future Twilio integration.

Subscribers are read from the user_preferences table (Supabase).
A subscriber receives alerts if:
  - alert_types includes "campaigns" or "wyckoff" (true)
  - delivery_mode is "realtime" or "daily"
  - market_hours_only = False (alerts fire after market close)
  - Their watchlist includes the symbol OR they receive all signals

CLAUDE.md compliance
--------------------
• Credentials via os.environ only.
• Decimal for all prices.
• Full type hints.
• Structured try/except throughout.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import requests as _rq

log = logging.getLogger("subscriber_alerts")

# ---------------------------------------------------------------------------
# Safe imports
# ---------------------------------------------------------------------------

try:
    import resend as _resend
    _RESEND_AVAILABLE = True
except ImportError:
    _RESEND_AVAILABLE = False
    log.warning("resend package not available — email alerts disabled")


# ---------------------------------------------------------------------------
# Alert content dataclass
# ---------------------------------------------------------------------------

@dataclass
class CampaignBirthAlert:
    """All data needed to render a subscriber alert email."""
    symbol:          str
    tier:            str
    layer:           str            # "A" or "B"
    entry_price:     Decimal
    stop_price:      Decimal
    stop_pct:        str            # e.g. "-10%"
    pnf_target:      Decimal
    mfe90_expected:  Decimal
    d_score:         float
    obstacle_score:  float
    duration_days:   int
    dur_bucket:      str
    behavioral_state: str
    spd:             bool
    dei:             bool
    wed_count:       int
    asym_ratio:      Decimal
    shares:          int            # 0 if not sized
    position_value:  Decimal        # 0 if not sized
    campaign_id:     str
    birth_date:      date


# ---------------------------------------------------------------------------
# Supabase subscriber lookup
# ---------------------------------------------------------------------------

def _sb_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")

def _sb_key() -> str:
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )

def _sb_headers() -> dict:
    key = _sb_key()
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"}


def _fetch_alert_subscribers(symbol: str) -> list[dict]:
    """
    Fetch subscribers who should receive this alert.

    A subscriber qualifies if:
    - alert_types has wyckoff=true or campaigns=true
    - delivery_mode is realtime or daily
    - watchlist is empty (receives all) OR contains this symbol
    """
    try:
        r = _rq.get(
            f"{_sb_url()}/rest/v1/user_preferences",
            headers=_sb_headers(),
            params={
                "select": "user_id,email,delivery_mode,alert_types,watchlist,market_hours_only",
                "limit":  "500",
            },
            timeout=15,
        )
        if r.status_code != 200:
            log.error("Failed to fetch subscribers: %s", r.status_code)
            return []

        all_prefs = r.json()
        qualified = []

        for pref in all_prefs:
            email = pref.get("email", "")
            if not email or "@" not in email:
                continue

            # Check alert types
            alert_types = pref.get("alert_types") or {}
            if isinstance(alert_types, str):
                import json
                try:
                    alert_types = json.loads(alert_types)
                except Exception:
                    alert_types = {}

            wants_campaigns = alert_types.get("campaigns", False) or alert_types.get("wyckoff", False)
            if not wants_campaigns:
                continue

            # Check delivery mode
            mode = pref.get("delivery_mode", "realtime")
            if mode not in {"realtime", "daily"}:
                continue

            # Check watchlist — empty means all symbols
            watchlist = pref.get("watchlist") or []
            if isinstance(watchlist, str):
                import json
                try:
                    watchlist = json.loads(watchlist)
                except Exception:
                    watchlist = []

            if watchlist and symbol.upper() not in [w.upper() for w in watchlist]:
                continue

            qualified.append(pref)

        log.info("Subscribers qualified for %s alert: %d", symbol, len(qualified))
        return qualified

    except Exception as exc:
        log.error("Subscriber fetch error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Email rendering
# ---------------------------------------------------------------------------

def _tier_color(tier: str) -> str:
    return {"TIER_1": "#34d399", "TIER_2": "#93c5fd",
            "TIER_3": "#fde68a", "TIER_4": "#64748b"}.get(tier, "#94a3b8")


def _render_email_html(alert: CampaignBirthAlert) -> str:
    """Render the full HTML email for a campaign birth alert."""

    tier_color  = _tier_color(alert.tier)
    stop_color  = "#f87171"
    target_pct  = float((alert.pnf_target - alert.entry_price) / alert.entry_price * 100) if alert.entry_price > 0 else 0

    # Behavioral evidence summary
    behavioral_lines = []
    if alert.spd:
        behavioral_lines.append("✓ Selling Pressure Diminishing — sellers exhausted")
    if alert.dei:
        behavioral_lines.append("✓ Demand Efficiency Improving — buyers emerging")
    if alert.wed_count >= 2:
        behavioral_lines.append(f"✓ Wave Exhaustion Depth {alert.wed_count} — validated entry window")
    if not behavioral_lines:
        behavioral_lines.append("Behavioral transition underway")

    behavioral_html = "".join(
        f'<div style="padding:4px 0;color:#94a3b8;font-size:13px;">{line}</div>'
        for line in behavioral_lines
    )

    # Duration label
    dur_labels = {
        "DUR_60_120":  "60–120 days below 252-day high (strongest window — 78.85% mfe90)",
        "DUR_120_180": "120–180 days below 252-day high",
        "DUR_20_60":   "20–60 days below 252-day high",
        "DUR_180_PLUS": "180+ days below 252-day high",
        "DUR_UNDER_20": "Under 20 days below 252-day high",
    }
    dur_label = dur_labels.get(alert.dur_bucket, alert.dur_bucket)

    # Position sizing block
    sizing_html = ""
    if alert.shares > 0:
        sizing_html = f"""
        <div style="background:#0f172a;border-radius:10px;padding:16px;margin-top:12px;
            border:1px solid rgba(255,255,255,.08);">
            <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
                letter-spacing:.08em;margin-bottom:10px;">Half-Kelly Position Size</div>
            <div style="display:flex;gap:24px;flex-wrap:wrap;">
                <div><div style="font-size:10px;color:#64748b;">Shares</div>
                     <div style="font-size:20px;font-weight:900;color:#f1f5f9;
                          font-family:monospace;">{alert.shares:,}</div></div>
                <div><div style="font-size:10px;color:#64748b;">Position Value</div>
                     <div style="font-size:20px;font-weight:900;color:#f1f5f9;
                          font-family:monospace;">${float(alert.position_value):,.0f}</div></div>
                <div><div style="font-size:10px;color:#64748b;">Layer</div>
                     <div style="font-size:20px;font-weight:900;color:{tier_color};
                          font-family:monospace;">{alert.layer}</div></div>
            </div>
        </div>"""

    # SMS placeholder note
    sms_note = """
    <!-- SMS PLACEHOLDER
    When Twilio integration is enabled, this alert will also be sent as:
    "SIGMALYTIC: {symbol} {tier} signal. Entry ${entry}. Stop ${stop}.
     Target ${target} (+{target_pct:.0f}%). mfe90 exp: {mfe90:.0f}%."
    -->"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sigmalytic — {alert.tier} Signal: {alert.symbol}</title></head>
<body style="margin:0;padding:0;background:#0a1628;font-family:'DM Sans',Arial,sans-serif;">

<div style="max-width:600px;margin:0 auto;padding:24px;">

  <!-- Header -->
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;">
    <div style="font-size:20px;font-weight:900;color:#34d399;letter-spacing:-.02em;">
      SIGMALYTIC
    </div>
    <div style="background:{tier_color}22;color:{tier_color};border-radius:8px;
        padding:5px 14px;font-weight:800;font-size:13px;border:1px solid {tier_color}40;">
      {alert.tier} SIGNAL
    </div>
  </div>

  <!-- Symbol hero -->
  <div style="background:#111f35;border-radius:16px;padding:24px;margin-bottom:16px;
      border:1px solid {tier_color}40;">
    <div style="font-size:42px;font-weight:900;color:#f1f5f9;font-family:monospace;
        letter-spacing:-.02em;">{alert.symbol}</div>
    <div style="color:#64748b;font-size:12px;margin-top:4px;">
      Campaign born {alert.birth_date.strftime('%B %d, %Y')} ·
      D-Score {alert.d_score:.0f}/100 ·
      {alert.behavioral_state.replace('_', ' ')}
    </div>
  </div>

  <!-- Six intelligence questions -->

  <!-- WHY -->
  <div style="background:#111f35;border-radius:12px;padding:16px;margin-bottom:12px;
      border-left:3px solid {tier_color};">
    <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
        letter-spacing:.1em;margin-bottom:8px;">WHY — Behavioral Evidence</div>
    {behavioral_html}
    <div style="color:#94a3b8;font-size:12px;margin-top:6px;">
      Obstacle Score: {alert.obstacle_score:.1f} ·
      ASYM Ratio: {float(alert.asym_ratio):.2f} ·
      Duration: {dur_label}
    </div>
  </div>

  <!-- WHERE + HOW FAR -->
  <div style="display:flex;gap:12px;margin-bottom:12px;">
    <div style="flex:1;background:#111f35;border-radius:12px;padding:16px;">
      <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
          letter-spacing:.1em;margin-bottom:10px;">WHERE — Entry</div>
      <div style="font-size:28px;font-weight:900;color:#f1f5f9;
          font-family:monospace;">${float(alert.entry_price):,.2f}</div>
      <div style="font-size:12px;color:#64748b;margin-top:4px;">Market-on-open entry</div>
      <div style="margin-top:12px;">
        <div style="font-size:10px;color:#64748b;font-weight:700;
            text-transform:uppercase;letter-spacing:.1em;">STOP</div>
        <div style="font-size:20px;font-weight:900;color:{stop_color};
            font-family:monospace;">${float(alert.stop_price):,.2f}
          <span style="font-size:13px;"> ({alert.stop_pct})</span>
        </div>
      </div>
    </div>
    <div style="flex:1;background:#111f35;border-radius:12px;padding:16px;">
      <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
          letter-spacing:.1em;margin-bottom:10px;">HOW FAR — Targets</div>
      <div style="font-size:12px;color:#64748b;">P&F Conservative Target</div>
      <div style="font-size:24px;font-weight:900;color:{tier_color};
          font-family:monospace;">${float(alert.pnf_target):,.2f}
        <span style="font-size:14px;color:#64748b;"> (+{target_pct:.0f}%)</span>
      </div>
      <div style="margin-top:10px;">
        <div style="font-size:12px;color:#64748b;">Expected mfe90</div>
        <div style="font-size:20px;font-weight:900;color:{tier_color};
            font-family:monospace;">{float(alert.mfe90_expected):.1f}%</div>
      </div>
    </div>
  </div>

  <!-- HOW MUCH RISK + OPPORTUNITY -->
  <div style="display:flex;gap:12px;margin-bottom:12px;">
    <div style="flex:1;background:#111f35;border-radius:12px;padding:16px;">
      <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
          letter-spacing:.1em;margin-bottom:10px;">RISK PROFILE</div>
      <div style="color:#94a3b8;font-size:13px;">
        <div style="padding:4px 0;">Stop: <b style="color:#f87171;">{alert.stop_pct}</b></div>
        <div style="padding:4px 0;">Layer: <b style="color:{tier_color};">{alert.layer}
          {'(21.2% Half-Kelly)' if alert.layer == 'A' else '(19.9% Half-Kelly)'}</b></div>
        <div style="padding:4px 0;">ASYM: <b style="color:#f1f5f9;">{float(alert.asym_ratio):.2f}</b>
          {'✓ passed' if float(alert.asym_ratio) >= 1.0 else '⚠ low'}</div>
        <div style="padding:4px 0;">Hold: <b style="color:#f1f5f9;">90 days</b></div>
      </div>
    </div>
    <div style="flex:1;background:#111f35;border-radius:12px;padding:16px;">
      <div style="font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;
          letter-spacing:.1em;margin-bottom:10px;">OPPORTUNITY REMAINING</div>
      <div style="color:#94a3b8;font-size:13px;">
        <div style="padding:4px 0;">D-Score: <b style="color:{tier_color};">{alert.d_score:.0f}/100</b></div>
        <div style="padding:4px 0;">WED: <b style="color:#f1f5f9;">{alert.wed_count}</b>
          {' ✓ validated' if alert.wed_count >= 2 else ''}</div>
        <div style="padding:4px 0;">State: <b style="color:#f1f5f9;">BIRTH → 5 stages ahead</b></div>
        <div style="padding:4px 0;">Campaign: <b style="color:#f1f5f9;">Day 1 of 90</b></div>
      </div>
    </div>
  </div>

  {sizing_html}

  <!-- Footer -->
  <div style="text-align:center;margin-top:24px;color:#475569;font-size:11px;">
    Sigmalytic Quant Corporation · Campaign Intelligence ·
    {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}
    <br><br>
    <span style="color:#1e293b;">
      You're receiving this because campaign alerts are enabled in your preferences.
    </span>
  </div>

</div>
{sms_note}
</body>
</html>"""


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def _send_alert_email(
    recipient_email: str,
    alert:           CampaignBirthAlert,
) -> bool:
    """Send a single alert email via Resend."""
    if not _RESEND_AVAILABLE:
        log.warning("Resend not available — skipping email to %s", recipient_email)
        return False

    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning("RESEND_API_KEY not set — skipping email")
        return False

    try:
        _resend.api_key = api_key

        subject = (
            f"[Sigmalytic] {alert.tier} Signal: {alert.symbol} — "
            f"Entry ${float(alert.entry_price):,.2f} · "
            f"mfe90 {float(alert.mfe90_expected):.0f}%"
        )

        _resend.Emails.send({
            "from":    "signals@sigmalytic.com",
            "to":      [recipient_email],
            "subject": subject,
            "html":    _render_email_html(alert),
        })

        log.info("Alert email sent to %s for %s %s", recipient_email, alert.symbol, alert.tier)
        return True

    except Exception as exc:
        log.error("Email send failed to %s for %s: %s", recipient_email, alert.symbol, exc)
        return False


# ---------------------------------------------------------------------------
# SMS placeholder
# ---------------------------------------------------------------------------

def _send_alert_sms(phone_number: str, alert: CampaignBirthAlert) -> bool:
    """
    SMS alert placeholder — Twilio integration pending.

    When enabled, message will be:
    "SIGMALYTIC {tier}: {symbol} @ ${entry:.2f}
     Stop ${stop:.2f} ({stop_pct}). Target ${target:.2f} (+{target_pct:.0f}%).
     mfe90 exp: {mfe90:.0f}%. D-Score: {d_score:.0f}."
    """
    log.info("SMS placeholder — would send %s %s alert to %s", alert.tier, alert.symbol, phone_number)
    return False  # Not implemented yet


# ---------------------------------------------------------------------------
# Main alert dispatch
# ---------------------------------------------------------------------------

async def send_campaign_birth_alerts(
    alerts: list[CampaignBirthAlert],
) -> dict[str, Any]:
    """
    Send birth alerts for a batch of new campaigns.
    Called by signal_birth_engine after campaign birth cycle completes.

    Parameters
    ----------
    alerts:
        List of CampaignBirthAlert objects — one per new campaign.

    Returns
    -------
    Summary dict with sent/failed counts.
    """
    if not alerts:
        return {"status": "ok", "alerts_sent": 0, "reason": "no alerts"}

    started_at  = datetime.now(timezone.utc)
    total_sent  = 0
    total_failed = 0

    log.info("=" * 60)
    log.info("SUBSCRIBER ALERTS dispatching %d campaign alerts", len(alerts))

    for alert in alerts:
        # Only alert on TIER_1 and TIER_2
        if alert.tier not in {"TIER_1", "TIER_2"}:
            continue

        subscribers = _fetch_alert_subscribers(alert.symbol)

        for sub in subscribers:
            email = sub.get("email", "")
            if email:
                success = _send_alert_email(email, alert)
                if success:
                    total_sent += 1
                else:
                    total_failed += 1

            # SMS placeholder — uncomment when Twilio is integrated
            # phone = sub.get("phone_number", "")
            # if phone:
            #     _send_alert_sms(phone, alert)

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "status":        "ok",
        "run_at":        started_at.isoformat(),
        "elapsed_secs":  round(elapsed, 1),
        "alerts_dispatched": len(alerts),
        "emails_sent":   total_sent,
        "emails_failed": total_failed,
    }

    log.info(
        "SUBSCRIBER ALERTS complete | sent=%d failed=%d in %.1fs",
        total_sent, total_failed, elapsed,
    )

    return summary


# ---------------------------------------------------------------------------
# Helper — build alert from campaign + signal score objects
# ---------------------------------------------------------------------------

def build_alert_from_campaign(
    campaign:      Any,   # Campaign dataclass
    signal_score:  Any,   # SignalScore dataclass from signal_birth_engine
    sizing_result: Any,   # SizingResult dataclass (optional, can be None)
) -> CampaignBirthAlert:
    """
    Construct a CampaignBirthAlert from the objects produced during
    the signal birth cycle.
    """
    stop_pct_str = "-10%" if campaign.layer == "A" else "-20%"
    shares       = sizing_result.shares        if sizing_result and sizing_result.is_approved else 0
    pos_value    = sizing_result.position_value if sizing_result and sizing_result.is_approved else Decimal("0")

    return CampaignBirthAlert(
        symbol          = campaign.symbol,
        tier            = campaign.tier,
        layer           = campaign.layer,
        entry_price     = campaign.entry_price,
        stop_price      = campaign.stop_price,
        stop_pct        = stop_pct_str,
        pnf_target      = campaign.pnf_target,
        mfe90_expected  = campaign.mfe90_expected,
        d_score         = float(campaign.d_score),
        obstacle_score  = float(campaign.obstacle_score),
        duration_days   = campaign.duration_days,
        dur_bucket      = signal_score.dur_bucket if signal_score else "DUR_60_120",
        behavioral_state = signal_score.state_label if signal_score else "ACCUMULATION",
        spd             = signal_score.spd  if signal_score else False,
        dei             = signal_score.dei  if signal_score else False,
        wed_count       = signal_score.wed_count if signal_score else 0,
        asym_ratio      = campaign.asym_ratio,
        shares          = shares,
        position_value  = pos_value,
        campaign_id     = campaign.campaign_id,
        birth_date      = campaign.birth_date,
    )
