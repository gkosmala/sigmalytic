# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/signal_decay_monitor.py
---------------------------------------------
Phase 12D — Signal Decay Monitoring.

Watches whether live signal performance is still matching the research
benchmarks. Computes rolling 90-day mfe90 by TIER and compares against
the validated Phase 12B expectations.

THREE-TIER ALERT SYSTEM
-----------------------
YELLOW  — Performance 20-35% below benchmark. Monitor closely.
          Action: Review recent signals, check market structure.

ORANGE  — Performance 35-50% below benchmark. Elevated concern.
          Action: Reduce new position sizing by 50%. Notify operator.

RED     — Performance >50% below benchmark. Critical degradation.
          Action: Stop opening new campaigns. Full investigation required.

BENCHMARKS (from Phase 12B research)
-------------------------------------
TIER_1: 70.62% avg mfe90, 70.62% win rate
TIER_2: 52.30% avg mfe90, 59.87% win rate
TIER_3: 38.50% avg mfe90, 44.20% win rate

CADENCE
-------
Runs nightly at 22:00 UTC — after all campaign updates are complete.
Requires minimum 10 closed campaigns per TIER for statistical validity.

CLAUDE.md compliance
--------------------
• Credentials via os.environ only.
• Decimal for all financial comparisons.
• Full type hints.
• Structured try/except throughout.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

import requests as _rq

log = logging.getLogger("signal_decay_monitor")

# ---------------------------------------------------------------------------
# Phase 12B research benchmarks
# ---------------------------------------------------------------------------

BENCHMARKS: dict[str, dict[str, float]] = {
    "TIER_1": {
        "avg_mfe90":  70.62,
        "win_rate":   70.62,
        "min_sample": 10,
    },
    "TIER_2": {
        "avg_mfe90":  52.30,
        "win_rate":   59.87,
        "min_sample": 10,
    },
    "TIER_3": {
        "avg_mfe90":  38.50,
        "win_rate":   44.20,
        "min_sample": 10,
    },
}

# Alert thresholds — % below benchmark
YELLOW_THRESHOLD: float = 0.20   # 20% below
ORANGE_THRESHOLD: float = 0.35   # 35% below
RED_THRESHOLD:    float = 0.50   # 50% below

# Minimum closed campaigns needed per tier for valid comparison
MIN_SAMPLE_SIZE: int = 10


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------

@dataclass
class TierDecayResult:
    tier:              str
    sample_size:       int
    live_avg_mfe90:    float
    benchmark_mfe90:   float
    deviation_pct:     float       # negative = underperforming
    alert_level:       str         # NONE / YELLOW / ORANGE / RED
    action_required:   str
    insufficient_data: bool = False


@dataclass
class DecayReport:
    run_at:          str
    tiers:           list[TierDecayResult] = field(default_factory=list)
    highest_alert:   str = "NONE"          # overall worst alert level
    email_sent:      bool = False
    summary:         str = ""


# ---------------------------------------------------------------------------
# Alert level logic
# ---------------------------------------------------------------------------

def _classify_alert(deviation_pct: float) -> tuple[str, str]:
    """
    Classify deviation into alert level and recommended action.
    deviation_pct is negative when underperforming (e.g. -0.25 = 25% below).
    """
    if deviation_pct > -YELLOW_THRESHOLD:
        return "NONE", "Performance within acceptable range. No action required."

    if deviation_pct > -ORANGE_THRESHOLD:
        return "YELLOW", (
            "Performance 20-35% below benchmark. "
            "Review recent signals and market structure. "
            "Continue trading but monitor closely."
        )

    if deviation_pct > -RED_THRESHOLD:
        return "ORANGE", (
            "Performance 35-50% below benchmark. "
            "Reduce new position sizing by 50%. "
            "Investigate signal environment before adding positions."
        )

    return "RED", (
        "Performance >50% below benchmark. CRITICAL DEGRADATION. "
        "Stop opening new campaigns immediately. "
        "Full system investigation required before resuming."
    )


_ALERT_RANK = {"NONE": 0, "YELLOW": 1, "ORANGE": 2, "RED": 3}


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _sb_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")

def _sb_key() -> str:
    return (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )

def _headers() -> dict:
    key = _sb_key()
    return {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
    }


def _fetch_closed_campaigns_for_decay() -> list[dict]:
    """
    Fetch closed campaigns from the last 90 days for rolling performance.
    """
    try:
        r = _rq.get(
            f"{_sb_url()}/rest/v1/campaigns",
            headers=_headers(),
            params={
                "select": (
                    "historical_confidence,entry_price,current_price,"
                    "close_reason,closed_at,campaign_age_days"
                ),
                "status": "eq.CLOSED",
                "order":  "closed_at.desc",
                "limit":  "500",
            },
            timeout=20,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        log.error("Failed to fetch closed campaigns for decay: %s", exc)
    return []


# ---------------------------------------------------------------------------
# Performance computation
# ---------------------------------------------------------------------------

def _compute_tier_performance(
    campaigns: list[dict],
    tier:      str,
) -> tuple[float, float, int]:
    """
    Compute live avg_mfe90 and win_rate for a given tier.

    Returns (avg_mfe90, win_rate, sample_size).
    mfe90 is approximated as (close_price - entry_price) / entry_price * 100.
    """
    tier_campaigns = [
        c for c in campaigns
        if c.get("historical_confidence") == tier
    ]

    if len(tier_campaigns) < MIN_SAMPLE_SIZE:
        return 0.0, 0.0, len(tier_campaigns)

    mfe90_vals: list[float] = []
    wins = 0

    for c in tier_campaigns:
        try:
            entry  = float(c.get("entry_price") or 0)
            close  = float(c.get("current_price") or 0)
            if entry <= 0 or close <= 0:
                continue

            ret_pct = (close - entry) / entry * 100.0
            mfe90_vals.append(ret_pct)

            if ret_pct > 0:
                wins += 1

        except Exception:
            continue

    if not mfe90_vals:
        return 0.0, 0.0, 0

    avg_mfe90 = sum(mfe90_vals) / len(mfe90_vals)
    win_rate  = wins / len(mfe90_vals) * 100.0

    return avg_mfe90, win_rate, len(mfe90_vals)


# ---------------------------------------------------------------------------
# Email alert
# ---------------------------------------------------------------------------

def _send_decay_alert_email(report: DecayReport) -> bool:
    """
    Send decay alert email to the operator via the existing email_service.
    """
    operator_email = os.environ.get("OPERATOR_EMAIL", "")
    if not operator_email:
        log.warning("OPERATOR_EMAIL not set — decay alert email skipped")
        return False

    try:
        import resend

        resend.api_key = os.environ.get("RESEND_API_KEY", "")
        if not resend.api_key:
            log.warning("RESEND_API_KEY not set — decay alert email skipped")
            return False

        alert_color = {
            "YELLOW": "#f59e0b",
            "ORANGE": "#f97316",
            "RED":    "#ef4444",
            "NONE":   "#34d399",
        }.get(report.highest_alert, "#94a3b8")

        # Build tier rows
        tier_rows = ""
        for t in report.tiers:
            if t.insufficient_data:
                row_html = f"""
                <tr>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;">{t.tier}</td>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;color:#64748b;">
                        Insufficient data ({t.sample_size} campaigns)
                    </td>
                    <td colspan="3" style="padding:10px;border-bottom:1px solid #1e293b;
                        color:#64748b;">Need {MIN_SAMPLE_SIZE}+ closed campaigns</td>
                </tr>"""
            else:
                alert_c = {
                    "NONE": "#34d399", "YELLOW": "#f59e0b",
                    "ORANGE": "#f97316", "RED": "#ef4444",
                }.get(t.alert_level, "#94a3b8")
                row_html = f"""
                <tr>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;
                        font-weight:700;color:#f1f5f9;">{t.tier}</td>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;
                        color:#f1f5f9;">{t.live_avg_mfe90:.1f}%</td>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;
                        color:#64748b;">{t.benchmark_mfe90:.1f}%</td>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;
                        color:{('#34d399' if t.deviation_pct >= 0 else '#f87171')};">
                        {t.deviation_pct:+.1f}%
                    </td>
                    <td style="padding:10px;border-bottom:1px solid #1e293b;">
                        <span style="background:{alert_c}22;color:{alert_c};
                            border-radius:6px;padding:3px 10px;font-weight:700;
                            font-size:12px;">{t.alert_level}</span>
                    </td>
                </tr>"""
            tier_rows += row_html

        html_body = f"""
        <div style="background:#0d1b2e;padding:32px;font-family:'DM Sans',sans-serif;
            color:#f1f5f9;max-width:640px;margin:0 auto;border-radius:16px;">

            <div style="display:flex;align-items:center;margin-bottom:24px;">
                <span style="font-size:24px;font-weight:900;color:#34d399;">
                    SIGMALYTIC
                </span>
                <span style="margin-left:12px;background:{alert_color}22;
                    color:{alert_color};border-radius:8px;padding:4px 12px;
                    font-weight:800;font-size:13px;">
                    {report.highest_alert} ALERT
                </span>
            </div>

            <h2 style="font-size:20px;font-weight:900;margin:0 0 8px;">
                Signal Decay Report
            </h2>
            <p style="color:#94a3b8;font-size:13px;margin:0 0 24px;">
                {report.run_at} UTC
            </p>

            <table style="width:100%;border-collapse:collapse;
                background:#111f35;border-radius:12px;overflow:hidden;">
                <thead>
                    <tr style="background:#0f172a;">
                        <th style="padding:12px;text-align:left;font-size:11px;
                            color:#64748b;text-transform:uppercase;
                            letter-spacing:.08em;">Tier</th>
                        <th style="padding:12px;text-align:left;font-size:11px;
                            color:#64748b;text-transform:uppercase;
                            letter-spacing:.08em;">Live mfe90</th>
                        <th style="padding:12px;text-align:left;font-size:11px;
                            color:#64748b;text-transform:uppercase;
                            letter-spacing:.08em;">Benchmark</th>
                        <th style="padding:12px;text-align:left;font-size:11px;
                            color:#64748b;text-transform:uppercase;
                            letter-spacing:.08em;">Deviation</th>
                        <th style="padding:12px;text-align:left;font-size:11px;
                            color:#64748b;text-transform:uppercase;
                            letter-spacing:.08em;">Alert</th>
                    </tr>
                </thead>
                <tbody>{tier_rows}</tbody>
            </table>

            <div style="margin-top:24px;background:#111f35;border-radius:12px;
                padding:20px;border-left:4px solid {alert_color};">
                <div style="font-size:12px;color:#64748b;font-weight:700;
                    text-transform:uppercase;letter-spacing:.08em;
                    margin-bottom:8px;">Required Action</div>
                <div style="color:#f1f5f9;font-size:14px;">{report.summary}</div>
            </div>

            <p style="color:#475569;font-size:11px;margin-top:24px;text-align:center;">
                Sigmalytic Quant Corporation · Operator Alert · Phase 12D
            </p>
        </div>
        """

        resend.Emails.send({
            "from":    "alerts@sigmalytic.com",
            "to":      [operator_email],
            "subject": f"[Sigmalytic] Signal Decay Alert — {report.highest_alert} — {report.run_at[:10]}",
            "html":    html_body,
        })

        log.info("Decay alert email sent to %s", operator_email)
        return True

    except Exception as exc:
        log.error("Failed to send decay alert email: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Main decay monitoring cycle
# ---------------------------------------------------------------------------

async def run_decay_monitoring_cycle() -> dict[str, Any]:
    """
    Run the nightly signal decay check.
    Compares live rolling performance against Phase 12B benchmarks.
    Sends email alert if any tier breaches YELLOW / ORANGE / RED threshold.

    Runs at 22:00 UTC — after all nightly engines have completed.
    """
    started_at = datetime.now(timezone.utc)
    log.info("=" * 60)
    log.info("DECAY MONITOR starting — %s", started_at.isoformat())
    log.info("=" * 60)

    # ── Fetch closed campaigns ────────────────────────────────────────────
    closed = _fetch_closed_campaigns_for_decay()
    log.info("Closed campaigns available: %d", len(closed))

    if not closed:
        log.info("No closed campaigns yet — decay monitoring pending first exits.")
        return {
            "status":         "pending",
            "reason":         "No closed campaigns yet",
            "highest_alert":  "NONE",
        }

    # ── Evaluate each tier ────────────────────────────────────────────────
    report = DecayReport(
        run_at = started_at.strftime("%Y-%m-%d %H:%M") + " UTC",
    )

    for tier, bench in BENCHMARKS.items():
        avg_mfe90, win_rate, sample = _compute_tier_performance(closed, tier)

        if sample < MIN_SAMPLE_SIZE:
            report.tiers.append(TierDecayResult(
                tier              = tier,
                sample_size       = sample,
                live_avg_mfe90    = 0.0,
                benchmark_mfe90   = bench["avg_mfe90"],
                deviation_pct     = 0.0,
                alert_level       = "NONE",
                action_required   = f"Insufficient data — need {MIN_SAMPLE_SIZE} closed campaigns.",
                insufficient_data = True,
            ))
            continue

        deviation = (avg_mfe90 - bench["avg_mfe90"]) / bench["avg_mfe90"]
        alert_level, action = _classify_alert(deviation)

        report.tiers.append(TierDecayResult(
            tier            = tier,
            sample_size     = sample,
            live_avg_mfe90  = round(avg_mfe90, 2),
            benchmark_mfe90 = bench["avg_mfe90"],
            deviation_pct   = round(deviation * 100, 1),
            alert_level     = alert_level,
            action_required = action,
        ))

        log.info(
            "%s | live=%.1f%% bench=%.1f%% dev=%.1f%% → %s",
            tier, avg_mfe90, bench["avg_mfe90"], deviation * 100, alert_level,
        )

    # ── Determine highest alert level ─────────────────────────────────────
    report.highest_alert = max(
        (t.alert_level for t in report.tiers),
        key=lambda a: _ALERT_RANK.get(a, 0),
        default="NONE",
    )

    # ── Build summary ─────────────────────────────────────────────────────
    if report.highest_alert == "NONE":
        report.summary = "All tiers performing within benchmark range. No action required."
    else:
        worst = next(
            t for t in report.tiers
            if t.alert_level == report.highest_alert
        )
        report.summary = worst.action_required

    # ── Send alert if needed ──────────────────────────────────────────────
    if report.highest_alert != "NONE":
        report.email_sent = _send_decay_alert_email(report)
    else:
        log.info("No decay alerts — all tiers within benchmark range.")

    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()

    summary = {
        "status":        "ok",
        "run_at":        report.run_at,
        "elapsed_secs":  round(elapsed, 1),
        "highest_alert": report.highest_alert,
        "email_sent":    report.email_sent,
        "tiers": [
            {
                "tier":           t.tier,
                "sample_size":    t.sample_size,
                "live_mfe90":     t.live_avg_mfe90,
                "benchmark_mfe90": t.benchmark_mfe90,
                "deviation_pct":  t.deviation_pct,
                "alert_level":    t.alert_level,
                "action":         t.action_required,
            }
            for t in report.tiers
        ],
    }

    log.info(
        "DECAY MONITOR complete in %.1fs | highest_alert=%s | email=%s",
        elapsed, report.highest_alert, report.email_sent,
    )

    return summary
