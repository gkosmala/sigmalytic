# SIGMALYTIC_STEP100R_C_FRONTEND_PERMANENT_NAG_REPAIR
# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/status_center.py
--------------------------
Status Center - the first screen after login in Sigmalytic V2.

Per the blueprint (Part X):
  "The first screen is NOT a chart.
   The first screen is NOT a scanner.
   The first screen is NOT AI predictions.
   The Status Center is an available intelligence panel, not the mandatory first-load screen"

Contains four intelligence sections:
  1. Portfolio Intelligence  - active campaigns, P&L, ODS health
  2. Radar Intelligence      - today's top signals, Pre-Spark opportunities
  3. Opportunity Intelligence - new TIER_1 sparks, state changes, exits
  4. System Alerts           - decay monitor status, conjunction exits

Plugs into sigmalytic_app_TODAY.py:
  1. from status_center import build_status_center
  2. Add ("status", "ALERT Status") as FIRST entry in ALL_TABS
  3. Change dcc.Store(id="s-tab", data="status") to make it the default
  4. Add elif tab=="status": main = build_status_center() to tab router
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import requests as _rq
from dash import html

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Brand tokens ──────────────────────────────────────────────────────────────
NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED     = "#f1f5f9"; TEXT = "#94a3b8"
WHITE     = "#f1f5f9"; BORDER    = "rgba(255,255,255,.08)"
PURPLE    = "#a78bfa"
# FIX (2026-07-25): MUTED was #64748b (a dim gray) -- per explicit request,
# changed to match WHITE. Every text color in this file that used MUTED
# now renders bright white instead of muted gray.

OPTIMAL_MIN = 20
OPTIMAL_MAX = 25

STATE_COLORS = {
    "BIRTH": BLUE_DIM, "CONFIRMED": TEAL_DIM, "SURVIVING": TEAL_DIM,
    "EXPANDING": YELLOW_DIM, "MATURING": YELLOW, "DISTRIBUTION_RISK": RED_DIM,
}
STATE_ICONS = {
    "BIRTH": "BIRTH",
    "CONFIRMED": "CONFIRMED",
    "SURVIVING": "SURVIVING",
    "EXPANDING": "EXPANDING",
    "MATURING": "MATURING",
    "DISTRIBUTION_RISK": "RISK",
}


# ── UI helpers ────────────────────────────────────────────────────────────────

def _card(children, sx=None):
    base = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
            "borderRadius": "16px", "padding": "20px", "marginBottom": "16px"}
    if sx:
        base.update(sx)
    return html.Div(children, style=base)


def _section(text, color=MUTED):
    return html.Div(text, style={
        "fontSize": "10px", "fontWeight": "700", "color": color,
        "textTransform": "uppercase", "letterSpacing": ".1em", "marginBottom": "12px",
    })


def _badge(text, color=TEAL_DIM):
    return html.Span(text, style={
        "fontSize": "10px", "fontWeight": "800", "color": color,
        "background": f"{color}18", "borderRadius": "6px",
        "padding": "2px 8px", "border": f"1px solid {color}35",
    })


def _kpi(label, value, color=WHITE, sub="", icon=""):
    return html.Div([
        html.Div([
            html.Span(icon + " " if icon else "", style={"fontSize": "14px"}),
            html.Span(label, style={"fontSize": "10px", "color": MUTED, "fontWeight": "700",
                                    "textTransform": "uppercase", "letterSpacing": ".08em"}),
        ], style={"display": "flex", "alignItems": "center", "marginBottom": "6px"}),
        html.Div(value, style={"fontSize": "24px", "fontWeight": "900", "color": color,
                               "fontFamily": "DM Mono, monospace"}),
        html.Div(sub, style={"fontSize": "11px", "color": MUTED, "marginTop": "3px"}) if sub else html.Div(),
    ], style={
        "background": NAVY_MID, "border": f"1px solid {BORDER}",
        "borderRadius": "12px", "padding": "14px 16px", "flex": "1", "minWidth": "100px",
    })


def _alert_banner(text, level="YELLOW"):
    colors = {"YELLOW": YELLOW_DIM, "ORANGE": "#f97316", "RED": RED_DIM}
    color  = colors.get(level, YELLOW_DIM)
    icons  = {"YELLOW": "", "ORANGE": "", "RED": ""}
    icon   = icons.get(level, "")
    return html.Div([
        html.Span(f"{icon} {level} ALERT", style={
            "fontSize": "11px", "fontWeight": "800", "color": color,
            "marginRight": "12px",
        }),
        html.Span(text, style={"fontSize": "12px", "color": WHITE}),
    ], style={
        "background": f"{color}12", "border": f"1px solid {color}40",
        "borderRadius": "10px", "padding": "12px 16px",
        "display": "flex", "alignItems": "center", "marginBottom": "8px",
    })


def _safe_list(value):
    if isinstance(value, list):
        return value
    return []


def _safe_int(value, default=0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _campaign_state(c: dict) -> str:
    return str(
        c.get("current_state")
        or c.get("state")
        or c.get("status")
        or ""
    ).upper()


def _campaign_age_days(c: dict, default=99) -> int:
    return _safe_int(
        c.get("campaign_age_days")
        if c.get("campaign_age_days") is not None
        else c.get("duration_days", default),
        default,
    )


def _normalize_campaign_row(c: dict) -> dict:
    row = dict(c or {})

    state = (
        row.get("current_state")
        or row.get("state")
        or row.get("status")
        or "UNKNOWN"
    )

    row["current_state"] = str(state).upper()
    row.setdefault("state", row["current_state"])
    row.setdefault("status", row["current_state"])

    if row.get("campaign_age_days") is None:
        row["campaign_age_days"] = row.get("duration_days", 0)

    if row.get("current_price") is None:
        row["current_price"] = row.get("price")

    if row.get("historical_confidence") is None:
        row["historical_confidence"] = row.get("grade") or row.get("rank_bucket")

    if row.get("ticker") is None:
        row["ticker"] = row.get("symbol")

    return row


def _normalize_radar_row(item: dict) -> dict:
    row = dict(item or {})

    row.setdefault("ticker", row.get("symbol"))
    row.setdefault("signal", row.get("status") or row.get("regime"))
    row.setdefault("score", row.get("composite_score"))

    return row



# SIGMALYTIC_RFA25D_STATUS_CENTER_FRESHNESS_VISIBILITY_START
def _format_freshness_ts(value) -> str:
    if not value:
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    text = text.replace("T", " ").replace("Z", " UTC").replace("+00:00", " UTC")

    if "." in text:
        head, tail = text.split(".", 1)
        suffix = " UTC" if "UTC" in tail else ""
        return head + suffix

    return text


def _max_timestamp(rows, key: str) -> str:
    values = []

    for row in _safe_list(rows):
        if not isinstance(row, dict):
            continue

        value = str(row.get(key) or "").strip()
        if value:
            values.append(value)

    if not values:
        return "-"

    return max(values)


def _freshness_pill(label: str, value, color=TEAL_DIM) -> html.Div:
    return html.Div([
        html.Div(label, style={
            "fontSize": "9px",
            "fontWeight": "800",
            "color": MUTED,
            "textTransform": "uppercase",
            "letterSpacing": ".08em",
            "marginBottom": "3px",
        }),
        html.Div(_format_freshness_ts(value), style={
            "fontSize": "11px",
            "fontWeight": "800",
            "color": color,
            "fontFamily": "DM Mono, monospace",
            "whiteSpace": "nowrap",
        }),
    ], style={
        "background": NAVY_MID,
        "border": f"1px solid {BORDER}",
        "borderRadius": "10px",
        "padding": "8px 10px",
        "minWidth": "165px",
    })


def _freshness_strip(
    last_campaign_refresh="-",
    last_evidence_refresh="-",
    last_radar_refresh="-",
    radar_cache_mode="-",
    radar_served_at="-",
) -> html.Div:
    return _card([
        html.Div([
            html.Div([
                html.Div("Data Freshness", style={
                    "fontSize": "11px",
                    "fontWeight": "900",
                    "color": WHITE,
                    "textTransform": "uppercase",
                    "letterSpacing": ".08em",
                }),
                html.Div("Read-only visibility into the latest campaign and Radar refresh cycle.", style={
                    "fontSize": "10px",
                    "color": MUTED,
                    "marginTop": "3px",
                }),
            ], style={"minWidth": "210px"}),

            html.Div([
                _freshness_pill("Campaign Refresh", last_campaign_refresh, TEAL_DIM),
                _freshness_pill("Evidence Refresh", last_evidence_refresh, TEAL_DIM),
                _freshness_pill("Radar Refresh", last_radar_refresh, BLUE_DIM),
                _freshness_pill("Radar Cache", radar_cache_mode, YELLOW_DIM),
                _freshness_pill("Radar Served", radar_served_at, MUTED),
            ], style={
                "display": "flex",
                "gap": "8px",
                "flexWrap": "wrap",
                "alignItems": "center",
            }),
        ], style={
            "display": "flex",
            "justifyContent": "space-between",
            "gap": "14px",
            "alignItems": "center",
            "flexWrap": "wrap",
        }),
    ], sx={
        "padding": "12px 14px",
        "marginBottom": "14px",
        "border": f"1px solid {TEAL_DIM}30",
    })
# SIGMALYTIC_RFA25D_STATUS_CENTER_FRESHNESS_VISIBILITY_END


def _campaign_mini(c: dict) -> html.Div:
    """Compact campaign row for Status Center."""
    symbol  = c.get("symbol", "-")
    state   = c.get("current_state", "BIRTH")
    tier    = c.get("historical_confidence", "-")
    ret_pct = float(c.get("return_pct", 0))
    ods     = float(c.get("operator_dominance") or 0)
    days    = _campaign_age_days(c, default=0)
    s_color = STATE_COLORS.get(state, MUTED)
    r_color = TEAL_DIM if ret_pct >= 0 else RED_DIM
    conj    = ods < 40 and state in {"MATURING", "DISTRIBUTION_RISK"}

    return html.Div([
        html.Span(STATE_ICONS.get(state, "-"), style={"fontSize": "13px", "marginRight": "6px"}),
        html.Span(symbol, style={"fontFamily": "DM Mono, monospace", "fontWeight": "900",
                                 "fontSize": "13px", "color": WHITE, "flex": "1"}),
        html.Span(tier, style={"fontSize": "9px", "color": MUTED, "flex": ".8"}),
        html.Span(f"D{days}", style={"fontSize": "10px", "color": MUTED, "flex": ".5"}),
        html.Span(f"{ret_pct:+.1f}%", style={"fontSize": "12px", "fontWeight": "800",
                                              "color": r_color, "fontFamily": "DM Mono, monospace",
                                              "flex": ".7", "textAlign": "right"}),
        html.Span("ALERT", style={"color": RED_DIM, "fontSize": "12px",
                               "marginLeft": "6px"}) if conj else html.Span(),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "6px",
        "padding": "7px 0", "borderBottom": f"1px solid {BORDER}",
    })


def _radar_mini(item: dict) -> html.Div:
    """Compact radar signal row."""
    symbol = item.get("symbol", "-")
    score  = float(item.get("score", 0))
    signal = item.get("signal_type", item.get("setup", "-"))
    s_color = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 45 else MUTED)
    return html.Div([
        html.Span(symbol, style={"fontFamily": "DM Mono, monospace", "fontWeight": "900",
                                 "fontSize": "13px", "color": WHITE, "flex": "1"}),
        html.Span(str(signal)[:24], style={"fontSize": "11px", "color": TEXT, "flex": "2"}),
        html.Span(f"{score:.0f}", style={"fontSize": "13px", "fontWeight": "800",
                                         "color": s_color, "fontFamily": "DM Mono, monospace"}),
    ], style={
        "display": "flex", "alignItems": "center", "gap": "10px",
        "padding": "7px 0", "borderBottom": f"1px solid {BORDER}",
    })


# ── Data fetching ─────────────────────────────────────────────────────────────

try:
    from shared_cache import shared_cache
except Exception:
    shared_cache = None


def _fetch(path: str, timeout: int = 20) -> dict | list:
    # FIX (2026-07-25): was timeout=6. This function is called five times per
    # render, including large campaign payloads -- the same class of issue
    # already found and fixed in sigmalytic_app_TODAY.py's freshness check.
    # 20s matches that fix.
    #
    # FIX (2026-07-25, part 2): previously only /api/campaigns/active and
    # /api/campaigns/summary were cached. Given the explicit requirement
    # that tab switching stay under 1 second consistently in every
    # direction, all five endpoints this function touches are now cached
    # -- not just the two campaign-wide ones. A shorter 15s TTL is used
    # so radar/intelligence data doesn't go as stale as the 25s campaign
    # cache.
    def _do_fetch():
        try:
            r = _rq.get(f"{BACKEND_HTTP}{path}", timeout=timeout)
            return r.json() if r.ok else {}
        except Exception:
            return {}

    if shared_cache is None:
        return _do_fetch()

    ttl = 25 if path.startswith(("/api/campaigns/active", "/api/campaigns/summary")) else 15
    return shared_cache.get_or_fetch(path, _do_fetch, ttl_seconds=ttl)


# ── Main builder ──────────────────────────────────────────────────────────────

def build_status_center(session=None) -> html.Div:
    """Build the Status Center - first screen after login."""

    # ── Fetch all data ────────────────────────────────────────────────────
    # Live Intelligence API consumption.
    # UI display only: no writes, no campaign mutation, no D3D authorization,
    # no operator-control confirmation, and no trade-signal creation.
    #
    # FIX (2026-07-25): these five calls were previously sequential -- each
    # one waiting for the last to finish before starting. With a 20s timeout
    # per call (needed for large campaign payloads, see _fetch's own fix
    # note), a slow backend response on any one of them made every tab
    # switch feel sluggish. Running them concurrently means total wait time
    # is roughly the slowest single call, not the sum of all five.
    fetch_paths = {
        "intelligence_status": "/api/intelligence/status-center",
        "intelligence_opps": "/api/intelligence/opportunities?limit=25",
        "radar_data": "/api/radar/intelligence?limit=8",
        "campaign_freshness_data": "/api/campaigns/active",
        "radar_freshness_data": "/api/radar/scores?limit=25",
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            key: executor.submit(_fetch, path)
            for key, path in fetch_paths.items()
        }
        fetched = {key: future.result() for key, future in futures.items()}

    intelligence_status  = fetched["intelligence_status"]
    intelligence_opps    = fetched["intelligence_opps"]
    radar_data           = fetched["radar_data"]
    campaign_freshness_data = fetched["campaign_freshness_data"]
    radar_freshness_data    = fetched["radar_freshness_data"]

    status_payload = (
        intelligence_status.get("status_center", {})
        if isinstance(intelligence_status, dict)
        else {}
    )

    status_summary = (
        status_payload.get("summary", {})
        if isinstance(status_payload, dict)
        else {}
    )

    summary = (
        intelligence_status.get("campaign_summary", {})
        if isinstance(intelligence_status, dict)
        else {}
    )

    sample_campaigns = _safe_list(status_payload.get("sample_campaigns"))
    opportunities    = _safe_list(
        intelligence_opps.get("opportunities")
        if isinstance(intelligence_opps, dict)
        else intelligence_opps
    )

    campaigns = sample_campaigns or opportunities
    campaigns = [
        _normalize_campaign_row(c)
        for c in campaigns
        if isinstance(c, dict)
    ]

    if isinstance(radar_data, dict):
        radar_items = (
            radar_data.get("symbols")
            or radar_data.get("signals")
            or radar_data.get("rankings")
            or []
        )
    elif isinstance(radar_data, list):
        radar_items = radar_data
    else:
        radar_items = []

    radar_items = [
        _normalize_radar_row(item)
        for item in _safe_list(radar_items)
        if isinstance(item, dict)
    ]

    campaign_freshness_rows = []
    if isinstance(campaign_freshness_data, dict):
        campaign_freshness_rows = _safe_list(campaign_freshness_data.get("campaigns"))

    if not campaign_freshness_rows:
        campaign_freshness_rows = campaigns

    last_campaign_refresh = _max_timestamp(campaign_freshness_rows, "updated_at")
    last_evidence_refresh = _max_timestamp(campaign_freshness_rows, "evidence_updated_at")

    if isinstance(radar_freshness_data, dict):
        last_radar_refresh = radar_freshness_data.get("generated_at") or "-"
        radar_served_at = radar_freshness_data.get("served_at") or "-"
        radar_cache = radar_freshness_data.get("cache")
        radar_cache_mode = (
            radar_cache.get("mode")
            if isinstance(radar_cache, dict)
            else "-"
        )
    else:
        last_radar_refresh = "-"
        radar_served_at = "-"
        radar_cache_mode = "-"

    # ── Derived metrics ───────────────────────────────────────────────────
    total      = _safe_int(status_summary.get("total_campaigns") or summary.get("active_campaigns") or len(campaigns), len(campaigns))
    tier1      = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_1")
    tier2      = sum(1 for c in campaigns if c.get("historical_confidence") == "TIER_2")
    avg_ods    = float(summary.get("avg_ods", 0))
    exits      = int(summary.get("conjunction_exits", 0))
    avg_return = float(summary.get("avg_return_pct", 0))
    state_counts: dict[str, int] = summary.get("state_breakdown", {})

    cap_color = (TEAL_DIM if OPTIMAL_MIN <= total <= OPTIMAL_MAX
                 else YELLOW_DIM if total < OPTIMAL_MIN else RED_DIM)
    cap_label = ("OPTIMAL" if OPTIMAL_MIN <= total <= OPTIMAL_MAX
                 else "BUILDING" if total < OPTIMAL_MIN else "OVER CAPACITY")
    ret_color = TEAL_DIM if avg_return >= 0 else RED_DIM

    # Most urgent campaigns - conjunction exits first, then distribution risk
    urgent = [c for c in campaigns
              if float(c.get("operator_dominance") or 100) < 40
              and c.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"}]

    # Most active - expanding campaigns
    expanding = [c for c in campaigns if _campaign_state(c) == "EXPANDING"]

    # New sparks - less than 3 days old
    new_births = [c for c in campaigns if _campaign_age_days(c, default=99) <= 3]

    now_utc = datetime.now(timezone.utc).strftime("%b %d, %Y - %H:%M UTC")

    return html.Div([

        # ── Header ────────────────────────────────────────────────────────
        html.Div([
            html.Div([
                html.H1("ALERT Status Center", style={
                    "fontSize": "22px", "fontWeight": "900", "color": WHITE, "margin": "0",
                }),
                html.Div(now_utc, style={"fontSize": "12px", "color": MUTED, "marginTop": "4px"}),
            ]),
            html.Div([
                _badge(f"● LIVE", TEAL_DIM),
                html.Span(f" {total} campaigns", style={"fontSize": "12px", "color": TEXT,
                                                         "marginLeft": "8px"}),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "marginBottom": "20px"}),

        # ── System Alerts ─────────────────────────────────────────────────
        _freshness_strip(
            last_campaign_refresh=last_campaign_refresh,
            last_evidence_refresh=last_evidence_refresh,
            last_radar_refresh=last_radar_refresh,
            radar_cache_mode=radar_cache_mode,
            radar_served_at=radar_served_at,
        ),

        html.Div([
            *([_alert_banner(
                f"{exits} conjunction exit signal{'s' if exits > 1 else ''} - "
                f"operator exiting detected. Review campaign tab immediately.",
                "RED" if exits >= 3 else "ORANGE"
            )] if exits > 0 else []),
            *([_alert_banner(
                f"{len(new_births)} new campaign{'s' if len(new_births) > 1 else ''} "
                f"sparked in the last 3 days: "
                f"{', '.join(c.get('symbol','') for c in new_births[:5])}",
                "YELLOW"
            )] if new_births else []),
        ]) if exits > 0 or new_births else html.Div(),

        # ── Row 1: Portfolio KPIs ─────────────────────────────────────────
        _card([
            _section("Portfolio Intelligence"),
            html.Div([
                _kpi("Campaigns", str(total), cap_color, cap_label),
                _kpi("TIER 1", str(tier1), TEAL_DIM, "highest conviction"),
                _kpi("TIER 2", str(tier2), BLUE_DIM, "strong conviction"),
                _kpi("Avg Return", f"{avg_return:+.1f}%", ret_color, "open positions"),
                _kpi("Avg ODS", f"{avg_ods:.0f}",
                     TEAL_DIM if avg_ods >= 60 else YELLOW_DIM, "operator dominance"),
                _kpi("Exit Signals", str(exits),
                     RED_DIM if exits > 0 else MUTED,
                     "conjunction exits" if exits > 0 else "all clear"),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap"}),
        ]),

        # ── Row 2: Three columns ──────────────────────────────────────────
        html.Div([

            # Column 1 - Active campaigns snapshot
            _card([
                _section(" Active Campaigns"),
                html.Div([
                    _campaign_mini(c)
                    for c in sorted(campaigns,
                        key=lambda x: (
                            -int(float(x.get("operator_dominance") or 100) < 40
                                 and x.get("current_state") in {"MATURING", "DISTRIBUTION_RISK"}),
                            -float(x.get("return_pct", 0))
                        ))[:8]
                ]) if campaigns else html.Div(
                    "No active campaigns yet. Signal spark runs at 20:30 UTC.",
                    style={"color": MUTED, "fontSize": "12px", "padding": "20px 0",
                           "textAlign": "center"}
                ),
                html.Div([
                    html.Div(style={"height": "1px", "background": BORDER, "margin": "12px 0"}),
                    html.Div([
                        *[html.Span([
                            html.Span(STATE_ICONS.get(s, "-") + " ", style={"fontSize": "11px"}),
                            html.Span(f"{state_counts.get(s, 0)}", style={
                                "fontWeight": "800", "color": STATE_COLORS.get(s, MUTED),
                                "fontFamily": "DM Mono, monospace", "fontSize": "12px",
                            }),
                            html.Span(f" {('SPARK' if s == 'BIRTH' else s.replace('_',' '))}", style={
                                "fontSize": "10px", "color": MUTED, "marginRight": "10px",
                            }),
                        ]) for s in ["BIRTH","CONFIRMED","SURVIVING","EXPANDING","MATURING","DISTRIBUTION_RISK"]
                           if state_counts.get(s, 0) > 0]
                    ], style={"display": "flex", "flexWrap": "wrap", "gap": "4px"}),
                ]) if campaigns else html.Div(),
            ], sx={"flex": "1.2"}),

            # Column 2 - Radar Intelligence
            _card([
                _section("Radar Intelligence"),
                html.Div([
                    html.Div([
                        html.Span("Symbol", style={"fontSize": "9px", "color": MUTED,
                                                   "fontWeight": "700", "flex": "1",
                                                   "textTransform": "uppercase"}),
                        html.Span("Signal", style={"fontSize": "9px", "color": MUTED,
                                                   "fontWeight": "700", "flex": "2",
                                                   "textTransform": "uppercase"}),
                        html.Span("Score", style={"fontSize": "9px", "color": MUTED,
                                                  "fontWeight": "700",
                                                  "textTransform": "uppercase"}),
                    ], style={"display": "flex", "gap": "10px", "paddingBottom": "6px",
                              "borderBottom": f"1px solid {BORDER}", "marginBottom": "2px"}),
                    *[_radar_mini(item) for item in radar_items[:8]],
                ]) if radar_items else html.Div(
                    "Radar data loading...",
                    style={"color": MUTED, "fontSize": "12px", "padding": "20px 0",
                           "textAlign": "center"}
                ),
            ], sx={"flex": "1"}),

            # Column 3 - Opportunity Intelligence
            _card([
                _section("Opportunity Intelligence"),

                # New sparks
                html.Div([
                    html.Div("New Campaigns (last 3 days)", style={
                        "fontSize": "11px", "fontWeight": "800", "color": TEAL_DIM,
                        "marginBottom": "8px",
                    }),
                    *[_campaign_mini(c) for c in new_births[:4]],
                    html.Div("No new campaigns", style={"color": MUTED, "fontSize": "11px"})
                    if not new_births else html.Div(),
                ]),

                html.Div(style={"height": "1px", "background": BORDER, "margin": "14px 0"}),

                # Expanding
                html.Div([
                    html.Div(" Expanding (energy live)", style={
                        "fontSize": "11px", "fontWeight": "800", "color": YELLOW_DIM,
                        "marginBottom": "8px",
                    }),
                    *[_campaign_mini(c) for c in expanding[:4]],
                    html.Div("None in expansion", style={"color": MUTED, "fontSize": "11px"})
                    if not expanding else html.Div(),
                ]),

                html.Div(style={"height": "1px", "background": BORDER, "margin": "14px 0"}),

                # Exit watch
                html.Div([
                    html.Div("ALERT Exit Watch", style={
                        "fontSize": "11px", "fontWeight": "800", "color": RED_DIM,
                        "marginBottom": "8px",
                    }),
                    *[_campaign_mini(c) for c in urgent[:4]],
                    html.Div("No exit signals", style={"color": TEAL_DIM, "fontSize": "11px"})
                    if not urgent else html.Div(),
                ]),

            ], sx={"flex": "1"}),

        ], style={"display": "flex", "gap": "16px"}),

        # ── Row 3: Nightly schedule status ────────────────────────────────
        _card([
            _section("Nightly Engine Schedule"),
            html.Div([
                *[html.Div([
                    html.Span(time, style={"fontFamily": "DM Mono, monospace", "fontSize": "12px",
                                          "color": BLUE_DIM, "fontWeight": "700",
                                          "minWidth": "55px"}),
                    html.Span(engine, style={"fontSize": "12px", "color": TEXT}),
                ], style={"display": "flex", "gap": "16px", "padding": "6px 0",
                          "borderBottom": f"1px solid {BORDER}"})
                for time, engine in [
                    ("20:00", "Geometry recalculation"),
                    ("20:30", "Signal spark engine - TIER scoring → new campaigns"),
                    ("21:00", "Campaign pipeline - FSM state updates"),
                    ("21:30", "ODS engine - operator dominance scores"),
                    ("21:45", "Analog engine - historical campaign matching"),
                    ("22:00", "Decay monitor - performance vs Phase 12B benchmarks"),
                    ("00:30", "EOD audit"),
                ]],
            ]),
        ]),

    ])
