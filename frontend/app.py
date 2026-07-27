# SIGMALYTIC_STEP100R_L3_FAST_FIRST_LOAD_TAB_STATE_SYNC
# SIGMALYTIC_STEP100R_K_CAMPAIGN_TAB_ACTIVE_ROUTER_WIRING
# SIGMALYTIC_STEP100R_I_LINE_BASED_TAB_FREEZE_REPAIR
# SIGMALYTIC_STEP100R_E_FORCE_VALID_FIRST_LOAD_RADAR_TAB
# SIGMALYTIC_STEP100R_C_FRONTEND_PERMANENT_NAG_REPAIR
# Sigmalytic v2.2 — integer x-axis for proper candle rendering
"""
Sigmalytic Quant Corporation — Decision Intelligence Platform
Institutional-Grade Frontend · Dash + Plotly
Includes: Behavioral Intelligence Layer v1.0
"""

# test build filter frontend
from __future__ import annotations
import json
import os
import random
from datetime import datetime, timezone, timedelta

import dash
from dash import dcc, html, Input, Output, State, no_update, callback_context
import plotly.graph_objects as go
import requests as req

# FIX (2026-07-25): When this file is loaded as `frontend.app` (as gunicorn
# does: `gunicorn "frontend.app:server"`), Python only adds the repo root to
# sys.path -- NOT frontend/ itself. The old `python frontend/app.py`
# invocation auto-added frontend/ as the running script's own directory,
# which is why the bare imports directly below (campaign_tab, portfolio_tab,
# trade_journal_tab, status_center) worked under that invocation style but
# silently failed under gunicorn's -- falling back to None and showing
# "module did not import" in the UI. This restores the same behavior
# explicitly, regardless of how the file is loaded. Must run before any of
# the bare imports below, which is why it's here rather than further down
# near the other sys.path.insert call.
import sys as _early_sys
_early_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from shared_cache import shared_cache
except Exception:
    shared_cache = None

# SIGMALYTIC_STEP100R_K_CAMPAIGN_TAB_IMPORT
try:
    from campaign_tab import build_campaign_tab as build_campaign_tab
except Exception:
    build_campaign_tab = None

try:
    from portfolio_tab import build_portfolio_tab as build_portfolio_tab
except Exception:
    build_portfolio_tab = None

try:
    from trade_journal_tab import build_trade_journal_tab as build_trade_journal_tab
except Exception:
    build_trade_journal_tab = None

try:
    from status_center import build_status_center as build_status_center
except Exception:
    build_status_center = None

import sys, pathlib

# ── Safe preflight palette definitions ────────────────────────────────────────
# These must exist before any global CSS f-strings are evaluated.
WHITE = "#FFFFFF"
TEXT = WHITE
MUTED = WHITE
TEXT_DIM = WHITE
SUBTLE = WHITE
GRAY = WHITE
GRAY_DIM = WHITE

NAVY = "#081827"
NAVY_MID = "#0B1F35"
NAVY_LIGHT = "#102A44"
BORDER = "rgba(148,163,184,.24)"
BORDER_T = "rgba(45,212,191,.55)"
TEAL = "#2DD4BF"
TEAL_DIM = "#34D399"
TEAL_GLOW = "rgba(45,212,191,.16)"
BLUE_DIM = "#93C5FD"
YELLOW_DIM = "#FDE68A"
RED_DIM = "#FB7185"
PURPLE = "#C4B5FD"
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from shared.engine import (
    sanitize_symbol, create_live_update, get_key_levels,
)

BACKEND_HTTP      = os.getenv("BACKEND_URL", "https://sigmalytic-backend.onrender.com")
SUPABASE_URL      = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
BACKEND_WS   = os.getenv("BACKEND_WS_URL", "ws://localhost:8000")


# FIX (2026-07-25): proactively keeps the shared cache warm for every
# endpoint used across tabs, instead of waiting for a user's click to
# trigger a refresh after the TTL expires. This is what actually makes
# tab-switching consistently fast rather than "fast most of the time,
# occasionally slow when the cache just expired." Registered once per
# worker process at import time; with Redis active, all worker processes
# coordinate so only one of them performs each scheduled refresh.
def _start_all_background_refreshers():
    if shared_cache is None:
        return

    def _make_fetcher(path, extra_headers=None, timeout=20):
        def _fetch():
            try:
                r = req.get(f"{BACKEND_HTTP}{path}", headers=extra_headers or {}, timeout=timeout)
                return r.json() if r.ok else {}
            except Exception:
                return {}
        return _fetch

    demo_auth_headers = {"Authorization": "Bearer demo"}

    # FIX (2026-07-27): real production logs showed 6-7 of these large,
    # campaign-heavy endpoints all firing within the same 20-40 second
    # window, every single cycle -- because every thread started at
    # roughly the same moment (worker boot) with similar intervals. That
    # repeated concurrent burst, not slow gradual growth, is what was
    # actually spiking memory and crashing the backend. Each endpoint now
    # gets a staggered initial delay (roughly 8s apart) so they land at
    # different points in time on every cycle, not just the first one.
    #
    # (path, ttl_seconds, refresh_interval_seconds, extra_headers, initial_delay_seconds)
    endpoints = [
        ("/api/campaigns/active", 120, 90, None, 0),
        ("/api/campaigns/summary", 120, 90, None, 8),
        ("/api/radar/scores", 90, 65, None, 16),
        ("/api/radar/scores?limit=25", 90, 65, None, 24),
        ("/api/scoreboard", 120, 90, None, 32),
        ("/api/radar/divergence", 90, 65, None, 40),
        ("/api/intelligence/status-center", 90, 65, None, 48),
        ("/api/intelligence/opportunities?limit=25", 90, 65, None, 56),
        ("/api/radar/intelligence?limit=8", 90, 65, None, 64),
        ("/api/journal/trades", 90, 65, demo_auth_headers, 72),
        ("/api/journal/profile", 90, 65, demo_auth_headers, 80),
    ]

    for path, ttl_seconds, refresh_interval_seconds, headers, initial_delay in endpoints:
        shared_cache.start_background_refresh(
            key=path,
            fetch_fn=_make_fetcher(path, extra_headers=headers),
            ttl_seconds=ttl_seconds,
            refresh_interval_seconds=refresh_interval_seconds,
            initial_delay_seconds=initial_delay,
        )


_start_all_background_refreshers()


# SIGMALYTIC_RFA25H_COMMAND_CENTER_FRESHNESS_VISIBLE_START
def _rfa25h_color(name, fallback):
    return globals().get(name, fallback)


def _rfa25h_fetch_json(path, timeout=20):
    def _do_fetch():
        try:
            response = req.get(f"{BACKEND_HTTP}{path}", timeout=timeout)
            if not response.ok:
                return {}
            data = response.json()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    if shared_cache is None:
        return _do_fetch()

    return shared_cache.get_or_fetch(path, _do_fetch, ttl_seconds=120)


def _rfa25h_safe_list(value):
    return value if isinstance(value, list) else []


def _rfa25h_max_ts(rows, key):
    values = []
    for row in _rfa25h_safe_list(rows):
        if not isinstance(row, dict):
            continue
        value = str(row.get(key) or "").strip()
        if value:
            values.append(value)
    return max(values) if values else "-"


def _rfa25h_fmt_ts(value):
    if not value:
        return "-"
    text = str(value).strip()
    if not text:
        return "-"
    had_utc = text.endswith("Z") or "+00:00" in text
    text = text.replace("T", " ").replace("Z", "").replace("+00:00", "")
    if "." in text:
        text = text.split(".", 1)[0]
    return text + (" UTC" if had_utc else "")


def _rfa25h_chip(label, value, accent):
    navy_mid = _rfa25h_color("NAVY_MID", "#0f172a")
    border = _rfa25h_color("BORDER", "rgba(255,255,255,.08)")
    muted = _rfa25h_color("MUTED", "#64748b")

    return html.Div([
        html.Div(label, style={
            "fontSize": "8px",
            "fontWeight": "900",
            "color": muted,
            "textTransform": "uppercase",
            "letterSpacing": ".08em",
            "marginBottom": "3px",
        }),
        html.Div(_rfa25h_fmt_ts(value), style={
            "fontSize": "10px",
            "fontWeight": "900",
            "color": accent,
            "fontFamily": "DM Mono, monospace",
            "whiteSpace": "nowrap",
        }),
    ], style={
        "background": navy_mid,
        "border": f"1px solid {border}",
        "borderRadius": "9px",
        "padding": "7px 9px",
        "minWidth": "132px",
    })


def _rfa25h_freshness_status(campaign_refresh_iso):
    """
    Returns (label, color) based on how old campaign_refresh_iso is.
    Never raises; a missing or unparseable timestamp is always treated as
    NOT live, since this function must never claim freshness it cannot
    actually verify.
    """
    red = _rfa25h_color("RED_DIM", "#fb7185")
    yellow = _rfa25h_color("YELLOW_DIM", "#fde68a")
    teal = _rfa25h_color("TEAL_DIM", "#34d399")

    if not campaign_refresh_iso or campaign_refresh_iso == "-":
        return "NO DATA", red

    try:
        text = str(campaign_refresh_iso).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        ts = datetime.fromisoformat(text)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return "UNKNOWN", red

    age = datetime.now(timezone.utc) - ts
    if age < timedelta(0):
        return "UNKNOWN", yellow
    if age <= timedelta(hours=20):
        return "LIVE", teal
    return "STALE", red


def _rfa25h_command_center_freshness_title():
    white = _rfa25h_color("WHITE", "#f1f5f9")
    muted = _rfa25h_color("MUTED", "#64748b")
    teal = _rfa25h_color("TEAL_DIM", "#34d399")
    blue = _rfa25h_color("BLUE_DIM", "#93c5fd")
    yellow = _rfa25h_color("YELLOW_DIM", "#fde68a")
    border = _rfa25h_color("BORDER", "rgba(255,255,255,.08)")

    active = _rfa25h_fetch_json("/api/campaigns/active")
    rows = _rfa25h_safe_list(active.get("campaigns"))

    radar = _rfa25h_fetch_json("/api/radar/scores?limit=25")
    cache = radar.get("cache") if isinstance(radar.get("cache"), dict) else {}

    campaign_refresh = _rfa25h_max_ts(rows, "updated_at")
    evidence_refresh = _rfa25h_max_ts(rows, "evidence_updated_at")
    radar_refresh = radar.get("generated_at") or "-"
    radar_served = radar.get("served_at") or "-"
    radar_cache = cache.get("mode") or "-"

    # FIX: this used to call itself here (infinite recursion -> RecursionError
    # on every render). The title is now computed directly from the same
    # campaign_refresh timestamp already fetched above, with real
    # staleness-aware coloring instead of a hardcoded "white" title.
    freshness_label, freshness_color = _rfa25h_freshness_status(campaign_refresh)
    title_text = f"Data Freshness — {freshness_label}"

    return html.Div([
        html.Div(title_text, style={
            "fontSize": "14px",
            "fontWeight": "900",
            "color": freshness_color,
            "marginBottom": "8px",
        }),
        html.Div("Data Freshness", style={
            "fontSize": "9px",
            "fontWeight": "900",
            "color": muted,
            "textTransform": "uppercase",
            "letterSpacing": ".1em",
            "marginBottom": "7px",
        }),
        html.Div([
            _rfa25h_chip("Campaign Refresh", campaign_refresh, teal),
            _rfa25h_chip("Evidence Refresh", evidence_refresh, teal),
            _rfa25h_chip("Radar Refresh", radar_refresh, blue),
            _rfa25h_chip("Radar Cache", radar_cache, yellow),
            _rfa25h_chip("Radar Served", radar_served, muted),
        ], style={
            "display": "flex",
            "gap": "8px",
            "flexWrap": "wrap",
            "alignItems": "center",
            "borderTop": f"1px solid {border}",
            "paddingTop": "8px",
        }),
    ])
# SIGMALYTIC_RFA25H_COMMAND_CENTER_FRESHNESS_VISIBLE_END



TIMEFRAMES   = ["1m", "5m", "15m", "1H", "1D", "1W"]
USER_ID      = "demo_user_001"

TF_VOLATILITY = {"1m": 0.25, "5m": 0.60, "15m": 1.10, "1H": 2.00, "1D": 4.50, "1W": 9.00}
TF_INTERVAL   = {"1m": 60,   "5m": 300,  "15m": 900,  "1H": 3600, "1D": 86400, "1W": 604800}
TF_TICKFMT    = {"1m": "%H:%M", "5m": "%H:%M", "15m": "%H:%M",
                 "1H": "%b %d %H:%M", "1D": "%b %d", "1W": "%b %d '%y"}

# ── Brand tokens ───────────────────────────────────────────────────────────────
WHITE = "#FFFFFF"
NAVY      = "#0d1b2e"; NAVY_CARD = "#111f35"; NAVY_MID = "#0f172a"
TEAL      = "#2d8f6f"; TEAL_DIM  = "#34d399"; TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"; RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"; YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"; MUTED = WHITE; TEXT = WHITE
PURPLE    = "#a78bfa"; PURPLE_GLOW = "rgba(167,139,250,.15)"

GLOBAL_CSS = f"""
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700;800;900&family=DM+Mono:wght@400;500&display=swap');
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:{NAVY};color:{WHITE};font-family:'DM Sans',ui-sans-serif,system-ui,sans-serif;font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}}
::-webkit-scrollbar{{width:8px;height:4px;}}
::-webkit-scrollbar-track{{background:{NAVY};}}
::-webkit-scrollbar-thumb{{background:{TEAL};border-radius:2px;}}
button{{font-family:inherit;cursor:pointer;border:none;outline:none;}}
input,textarea,select{{font-family:inherit;outline:none;}}
.Select-control,.Select-menu-outer,.Select--single>.Select-control .Select-value,
.Select-placeholder,.Select-value-label{{background:{NAVY_MID} !important;color:{WHITE} !important;}}
.Select-menu-outer{{border:1px solid {BORDER} !important;border-radius:10px !important;overflow:hidden;z-index:9999 !important;}}
.Select-option{{background:{NAVY_MID} !important;color:{TEXT} !important;padding:10px 14px !important;font-size:13px !important;}}
.Select-option:hover,.Select-option.is-focused{{background:{TEAL_GLOW} !important;color:{WHITE} !important;}}
.Select-option.is-selected{{background:rgba(45,143,111,.3) !important;color:{TEAL_DIM} !important;font-weight:700;}}
.Select-arrow{{border-color:{MUTED} transparent transparent !important;}}
.Select-control{{border:1px solid {BORDER} !important;border-radius:10px !important;min-height:40px !important;}}
.Select-control:hover{{border-color:{BORDER_T} !important;}}
.is-open .Select-control{{border-color:{BORDER_T} !important;border-radius:10px 10px 0 0 !important;}}
"""

# ── Helpers ────────────────────────────────────────────────────────────────────


# ── Historical Probability Display Helpers ───────────────────────────────────
def _fmt_pct(v, default="—"):
    try:
        if v is None or v == "":
            return default
        return f"{float(v):.1f}%"
    except Exception:
        return default

def _fmt_signed_pct(v, default="—"):
    try:
        if v is None or v == "":
            return default
        n = float(v)
        return f"{n:+.2f}%"
    except Exception:
        return default

def _fmt_num(v, default="—"):
    try:
        if v is None or v == "":
            return default
        n = float(v)
        if abs(n) >= 1000:
            return f"{n:,.0f}"
        return f"{n:.2f}"
    except Exception:
        return default

def _fmt_int(v, default="—"):
    try:
        if v is None or v == "":
            return default
        return f"{int(float(v)):,}"
    except Exception:
        return default

def _probability_grade_color(grade):
    g = str(grade or "").upper().strip()
    if g.startswith("A"):
        return TEAL
    if g.startswith("B"):
        return BLUE_DIM
    if g.startswith("C"):
        return YELLOW_DIM
    if g in {"D", "F", "AVOID"}:
        return RED_DIM
    return WHITE

def _historical_edge_payload(row):
    row = row or {}
    return {
        "grade": row.get("probability_grade") or row.get("historical_grade") or "Unrated",
        "success": row.get("historical_success") or row.get("historical_success_rate") or row.get("historical_tradeable_rate"),
        "expected_return": row.get("expected_return") or row.get("historical_expected_return"),
        "edge_ratio": row.get("edge_ratio") or row.get("historical_edge_ratio"),
        "matches": row.get("historical_matches"),
        "confidence": row.get("probability_confidence") or row.get("historical_confidence"),
        "score": row.get("expected_opportunity_score"),
        "edge_score": row.get("edge_score") or row.get("expected_opportunity_score"),
        "match_type": row.get("probability_match_type"),
        "setup": row.get("probability_setup_type") or row.get("setup_type"),
        "weekly": row.get("probability_weekly_regime") or row.get("weekly_regime"),
    }

def historical_edge_card(row):
    p = _historical_edge_payload(row)
    grade = p["grade"]
    grade_color = _probability_grade_color(grade)
    return html.Div([
        html.Div("Historical Edge", style={"fontSize":"13px","fontWeight":"800","color":WHITE,"letterSpacing":".4px","marginBottom":"8px"}),
        html.Div([
            html.Div([
                html.Div("Grade", style={"fontSize":"11px","color":WHITE}),
                html.Div(str(grade), style={"fontSize":"30px","fontWeight":"900","color":grade_color,"lineHeight":"1"}),
            ], style={"minWidth":"76px"}),
            html.Div([
                html.Div("Probability", style={"fontSize":"11px","color":WHITE}),
                html.Div(_fmt_pct(p["success"]), style={"fontSize":"22px","fontWeight":"900","color":WHITE}),
            ], style={"minWidth":"130px"}),
            html.Div([
                html.Div("Expected Return", style={"fontSize":"11px","color":WHITE}),
                html.Div(_fmt_signed_pct(p["expected_return"]), style={"fontSize":"22px","fontWeight":"900","color":WHITE}),
            ], style={"minWidth":"130px"}),
        ], style={"display":"flex","gap":"16px","flexWrap":"wrap","alignItems":"center"}),
        html.Div([
            html.Div([
                html.Div("Edge Ratio", style={"fontSize":"11px","color":WHITE}),
                html.Div(_fmt_num(p["edge_ratio"]), style={"fontSize":"16px","fontWeight":"800","color":WHITE}),
            ]),
            html.Div([
                html.Div("Matches", style={"fontSize":"11px","color":WHITE}),
                html.Div(_fmt_int(p["matches"]), style={"fontSize":"16px","fontWeight":"800","color":WHITE}),
            ]),
            html.Div([
                html.Div("Confidence", style={"fontSize":"11px","color":WHITE}),
                html.Div(str(p["confidence"] or "—"), style={"fontSize":"16px","fontWeight":"800","color":WHITE}),
            ]),
            html.Div([
                html.Div("Match", style={"fontSize":"11px","color":WHITE}),
                html.Div(str(p["match_type"] or "—").replace("_"," "), style={"fontSize":"13px","fontWeight":"700","color":WHITE}),
            ]),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,minmax(90px,1fr))","gap":"10px","marginTop":"12px"}),
        html.Div([
            html.Span(str(p["weekly"] or "Weekly: —"), style={"color":WHITE,"fontSize":"12px","fontWeight":"700"}),
            html.Span(" · ", style={"color":WHITE}),
            html.Span(str(p["setup"] or "Setup: —"), style={"color":WHITE,"fontSize":"12px","fontWeight":"700"}),
        ], style={"marginTop":"10px"}),
    ], style={
        "border":"1px solid rgba(45,212,191,.26)",
        "background":"rgba(8,24,39,.72)",
        "borderRadius":"16px",
        "padding":"14px",
        "boxShadow":"0 0 0 1px rgba(45,212,191,.08) inset",
        "color":WHITE,
    })

def probability_metric_pills(row):
    p = _historical_edge_payload(row)
    grade_color = _probability_grade_color(p["grade"])
    return html.Div([
        html.Div([html.Span("Grade ", style={"color":WHITE}), html.B(str(p["grade"]), style={"color":grade_color})], className="prob-pill"),
        html.Div([html.Span("Success ", style={"color":WHITE}), html.B(_fmt_pct(p["success"]), style={"color":WHITE})], className="prob-pill"),
        html.Div([html.Span("Exp Ret ", style={"color":WHITE}), html.B(_fmt_signed_pct(p["expected_return"]), style={"color":WHITE})], className="prob-pill"),
        html.Div([html.Span("Edge ", style={"color":WHITE}), html.B(_fmt_num(p["edge_ratio"]), style={"color":WHITE})], className="prob-pill"),
        html.Div([html.Span("Matches ", style={"color":WHITE}), html.B(_fmt_int(p["matches"]), style={"color":WHITE})], className="prob-pill"),
    ], style={"display":"flex","gap":"8px","flexWrap":"wrap","marginTop":"10px"})

def _track(event_type, symbol, price=None, timeframe=None, regime=None,
           decision_score=None, decision_status=None, metadata=None):
    """Fire-and-forget behavioral event to backend."""
    try:
        req.post(f"{BACKEND_HTTP}/api/behavior/event", json={
            "user_id": USER_ID, "event_type": event_type, "symbol": symbol,
            "price": price, "timeframe": timeframe, "market_regime": regime,
            "decision_score": decision_score, "decision_status": decision_status,
            "metadata": metadata or {},
        }, timeout=2)
    except Exception:
        pass

def _get(path, **params):
    def _do_fetch():
        try:
            r = req.get(f"{BACKEND_HTTP}{path}", params=params, timeout=15)
            return r.json() if r.ok else {}
        except Exception:
            return {}

    if shared_cache is None or params:
        # Don't cache calls with extra query params -- the cache key is
        # just the path string, so a parameterized call could silently
        # return another call's cached result. Rare in this codebase, but
        # safer to just fetch fresh in that case.
        return _do_fetch()

    return shared_cache.get_or_fetch(path, _do_fetch, ttl_seconds=90)


# ============================================================
# D3F.1B LIVE DASH CONTROLLED PERSISTENCE PANEL
# Mode: read-only frontend display. GET only. No write. No D3D. No Stripe.
# ============================================================
def _d3f1b_bool_text(value):
    if value is True:
        return "True"
    if value is False:
        return "False"
    return "Unknown"


def _d3f1b_guardrail_clean(data):
    if not isinstance(data, dict):
        return False

    return (
        data.get("writes_to_supabase") is False
        and data.get("supabase_write_authorized") is False
        and data.get("persistence_write_authorized") is False
        and data.get("mutates_campaigns") is False
        and data.get("executes_d3d") is False
        and data.get("authorizes_d3d") is False
        and data.get("operator_control_confirmed") is False
        and data.get("composite_operator_control_confirmed") is False
        and data.get("not_a_trade_signal") is True
        and data.get("touches_stripe") is False
    )


def _d3f1b_row(label, value):
    return html.Div(
        [
            html.Span(label, style={"color": "#94a3b8"}),
            html.Span(str(value), style={"fontWeight": "700", "textAlign": "right"}),
        ],
        style={
            "display": "flex",
            "justifyContent": "space-between",
            "gap": "14px",
            "padding": "6px 0",
            "borderTop": "1px solid rgba(148,163,184,0.14)",
            "fontSize": "13px",
        },
    )


def _build_d3f1b_controlled_persistence_lifecycle_panel():
    endpoint = "/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep"

    try:
        data = _get(endpoint)
    except Exception as exc:
        data = {
            "ok": False,
            "d3e_phase": "D3E.9",
            "final_lifecycle_verified": False,
            "final_lifecycle_status": "D3F1B_FRONTEND_FETCH_ERROR",
            "error": str(exc)[:240],
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

    if not isinstance(data, dict):
        data = {"ok": False, "final_lifecycle_verified": False}

    complete = data.get("final_lifecycle_verified") is True
    guardrail_clean = _d3f1b_guardrail_clean(data)

    status_text = "COMPLETE" if complete else "ATTENTION"
    guardrail_text = "Clean" if guardrail_clean else "Needs review"

    lifecycle_rows = [
        ("Phase", data.get("d3e_phase", "D3E.9")),
        ("Final lifecycle verified", _d3f1b_bool_text(data.get("final_lifecycle_verified"))),
        ("Lifecycle status", data.get("final_lifecycle_status", "Unknown")),
        ("Inserted audit row id", data.get("inserted_row_id", "Unknown")),
        ("Audit symbol", data.get("lifecycle_symbol", "Unknown")),
        ("Audit version", data.get("lifecycle_audit_version", "Unknown")),
        ("Operator-control status", data.get("lifecycle_operator_control_evidence_audit_status", "Unknown")),
        ("D3D status", data.get("lifecycle_d3d_dry_run_gate_audit_status", "Unknown")),
    ]

    guardrail_rows = [
        ("Writes to Supabase", _d3f1b_bool_text(data.get("writes_to_supabase"))),
        ("Supabase write authorized", _d3f1b_bool_text(data.get("supabase_write_authorized"))),
        ("Persistence write authorized", _d3f1b_bool_text(data.get("persistence_write_authorized"))),
        ("Campaign mutation", _d3f1b_bool_text(data.get("mutates_campaigns"))),
        ("D3D executed", _d3f1b_bool_text(data.get("executes_d3d"))),
        ("D3D authorized", _d3f1b_bool_text(data.get("authorizes_d3d"))),
        ("Operator control confirmed", _d3f1b_bool_text(data.get("operator_control_confirmed"))),
        ("Composite operator control confirmed", _d3f1b_bool_text(data.get("composite_operator_control_confirmed"))),
        ("Trade signal created", "False" if data.get("not_a_trade_signal") is True else "Unknown"),
        ("Stripe touched", _d3f1b_bool_text(data.get("touches_stripe"))),
    ]

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                "Controlled Persistence Lifecycle",
                                style={
                                    "fontSize": "12px",
                                    "letterSpacing": "0.08em",
                                    "color": "#94a3b8",
                                    "textTransform": "uppercase",
                                },
                            ),
                            html.H2(
                                "D3E.9 Final Lifecycle Regression Sweep",
                                style={"margin": "6px 0 4px", "fontSize": "22px"},
                            ),
                            html.Div(
                                "Read-only Status Center display. No write. No campaign mutation. No D3D. No operator-control confirmation. No Stripe.",
                                style={"color": "#cbd5e1", "fontSize": "14px"},
                            ),
                        ]
                    ),
                    html.Div(
                        status_text,
                        style={
                            "borderRadius": "999px",
                            "padding": "8px 12px",
                            "fontWeight": "800",
                            "background": "rgba(22,101,52,0.35)" if complete else "rgba(127,29,29,0.35)",
                            "border": "1px solid rgba(34,197,94,0.5)" if complete else "1px solid rgba(248,113,113,0.5)",
                        },
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "gap": "16px",
                    "alignItems": "center",
                    "marginBottom": "16px",
                },
            ),
            html.Div(
                [
                    html.Div(
                        [html.H3("Lifecycle Proof", style={"margin": "0 0 10px", "fontSize": "16px"})]
                        + [_d3f1b_row(label, value) for label, value in lifecycle_rows],
                        style={
                            "border": "1px solid rgba(148,163,184,0.22)",
                            "borderRadius": "12px",
                            "padding": "14px",
                        },
                    ),
                    html.Div(
                        [html.H3("Doctrine Guardrails", style={"margin": "0 0 10px", "fontSize": "16px"})]
                        + [_d3f1b_row(label, value) for label, value in guardrail_rows]
                        + [
                            html.Div(
                                f"Guardrail status: {guardrail_text}",
                                style={
                                    "marginTop": "12px",
                                    "fontWeight": "800",
                                    "color": "#86efac" if guardrail_clean else "#fecaca",
                                },
                            )
                        ],
                        style={
                            "border": "1px solid rgba(148,163,184,0.22)",
                            "borderRadius": "12px",
                            "padding": "14px",
                        },
                    ),
                ],
                style={
                    "display": "grid",
                    "gridTemplateColumns": "repeat(auto-fit, minmax(260px, 1fr))",
                    "gap": "14px",
                },
            ),
        ],
        id="d3f1b-controlled-persistence-lifecycle-panel",
        **{
            "data-d3f1b-endpoint": endpoint,
            "data-d3e-phase": "D3E.9",
            "data-read-only": "true",
        },
        style={
            "border": "1px solid rgba(148,163,184,0.35)",
            "borderRadius": "16px",
            "padding": "18px",
            "margin": "18px 0",
            "background": "rgba(15,23,42,0.78)",
            "color": "#e5e7eb",
        },
    )
# Weis-Gamma Status Center display cache.
_WEIS_GAMMA_STATUS_CACHE = {
    "as_of": None,
    "data": None,
}


def _cached_campaign_summary(ttl_seconds: int = 30):
    now = datetime.now(timezone.utc)
    cached_at = _WEIS_GAMMA_STATUS_CACHE.get("as_of")

    if cached_at is not None:
        try:
            age = (now - cached_at).total_seconds()
            if age < ttl_seconds and isinstance(_WEIS_GAMMA_STATUS_CACHE.get("data"), dict):
                return _WEIS_GAMMA_STATUS_CACHE.get("data") or {}
        except Exception:
            pass

    data = _get("/api/campaigns/summary")

    if not isinstance(data, dict) or not data:
        data = _get("/api/campaign/status")

    if isinstance(data, dict):
        _WEIS_GAMMA_STATUS_CACHE["as_of"] = now
        _WEIS_GAMMA_STATUS_CACHE["data"] = data
        return data

    return {}


def _wg_metric_card(label, value, color=WHITE):
    return html.Div([
        html.Div(str(label), style={
            "fontSize": "11px",
            "color": WHITE,
            "fontWeight": "800",
            "letterSpacing": ".08em",
            "textTransform": "uppercase",
            "opacity": ".85",
        }),
        html.Div(str(value), style={
            "fontSize": "24px",
            "lineHeight": "1.1",
            "color": color,
            "fontWeight": "900",
            "marginTop": "6px",
        }),
    ], style={
        "background": "rgba(8,24,39,.72)",
        "border": f"1px solid {BORDER}",
        "borderRadius": "14px",
        "padding": "12px",
        "minHeight": "76px",
    })


def _wg_label(value):
    mapping = {
        "OK": "Gamma OK",
        "NONE": "Missing Overlay",
        "EMPTY": "Empty",
        "NO_OPTIONS_RETURNED": "No Options Returned",
        "NO_OPTION_CHAIN_INPUT": "No Option-Chain Input",
        "NO_GAMMA_INPUT": "No Gamma Input",
        "NOT_PRESENT": "Not Present",
        "CALL_SIGNATURE_MISMATCH": "Call Signature Mismatch",
        "WEIS_ONLY_GAMMA_STALE": "Weis Only - Gamma Stale",
        "WEIS_ONLY_NO_OPTIONS_RETURNED": "Weis Only - No Options Returned",
        "WEIS_EXPANSION_GAMMA_NEUTRAL": "Weis Expansion - Gamma Neutral",
        "WEIS_GAMMA_UNRESOLVED": "Weis Gamma Unresolved",
        "WEIS_EXPANSION": "Weis Expansion",
        "WEIS_BASELINE": "Weis Baseline",
        "WEIS_TEST": "Weis Test",
        "WEIS_EXHAUSTION": "Weis Exhaustion",
        "A_PLUS": "A+",
        "LOW_PRIORITY": "Low Priority",
        "WATCHLIST": "Watchlist",
        "AVOID": "Avoid",
    }

    key = str(value or "NONE")
    return mapping.get(key, key.replace("_", " ").title())


def _wg_counts_text(counts):
    if not isinstance(counts, dict) or not counts:
        return "-"

    parts = []
    for key, value in counts.items():
        parts.append(f"{_wg_label(key)}: {value}")

    return " | ".join(parts)


def build_weis_gamma_status_center_panel():
    summary = _cached_campaign_summary()
    wg = summary.get("weis_gamma_status_center") or {}

    if not wg:
        return html.Div([
            html.Div(_rfa25h_command_center_freshness_title(), style={
                "fontSize": "14px",
                "fontWeight": "900",
                "color": WHITE,
                "marginBottom": "6px",
            }),
            html.Div("Waiting for Weis-Gamma status data from backend.", style={
                "fontSize": "12px",
                "color": WHITE,
                "opacity": ".85",
            }),
        ], style={
            "border": f"1px solid {BORDER}",
            "background": "rgba(8,24,39,.60)",
            "borderRadius": "18px",
            "padding": "16px",
            "marginBottom": "16px",
        })

    total = wg.get("total_campaigns", summary.get("active_campaigns", 0))
    present = wg.get("weis_gamma_present", 0)
    missing = wg.get("weis_gamma_missing", 0)

    gamma_ok = wg.get("gamma_ok", 0)
    no_options_returned = wg.get("gamma_no_options_returned", 0)
    no_option_chain = wg.get("gamma_no_option_chain", 0)
    stale = wg.get("gamma_stale_or_unconfirmed", 0)
    transition_enabled = wg.get("transition_enabled", 0)

    phase_counts = wg.get("phase_counts") or {}
    rank_counts = wg.get("rank_bucket_counts") or {}
    gamma_counts = wg.get("gamma_status_counts") or {}
    option_chain_counts = wg.get("option_chain_status_counts") or {}
    fusion_counts = wg.get("fusion_state_counts") or {}

    transitions_off = int(transition_enabled or 0) == 0
    safety_color = TEAL_DIM if transitions_off else RED_DIM
    safety_label = "TRANSITIONS OFF" if transitions_off else "TRANSITIONS ENABLED"

    stale_color = TEAL_DIM if int(stale or 0) == 0 else RED_DIM
    no_input_color = TEAL_DIM if int(no_option_chain or 0) == 0 else YELLOW_DIM

    return html.Div([
        html.Div([
            html.Div([
                html.Div(_rfa25h_command_center_freshness_title(), style={
                    "fontSize": "16px",
                    "fontWeight": "900",
                    "color": WHITE,
                }),
                html.Div(
                    "Gamma is a read-only execution-risk overlay. No Options Returned means Alpaca was queried and no listed chain was returned; it is not a stale Gamma failure.",
                    style={
                        "fontSize": "12px",
                        "color": WHITE,
                        "opacity": ".85",
                        "marginTop": "4px",
                    },
                ),
            ]),
            html.Div(safety_label, style={
                "fontSize": "11px",
                "fontWeight": "900",
                "color": safety_color,
                "border": f"1px solid {safety_color}",
                "borderRadius": "999px",
                "padding": "6px 10px",
            }),
        ], style={
            "display": "flex",
            "justifyContent": "space-between",
            "gap": "12px",
            "alignItems": "center",
            "marginBottom": "14px",
        }),

        html.Div([
            _wg_metric_card("Total Campaigns", total, WHITE),
            _wg_metric_card("Weis-Gamma Present", present, TEAL_DIM),
            _wg_metric_card("Gamma OK", gamma_ok, TEAL_DIM),
            _wg_metric_card("No Options Returned", no_options_returned, YELLOW_DIM),
            _wg_metric_card("No Option-Chain Input", no_option_chain, no_input_color),
            _wg_metric_card("Gamma Stale / Unconfirmed", stale, stale_color),
            _wg_metric_card("Transitions Off", "YES" if transitions_off else "NO", safety_color),
            _wg_metric_card("Missing Overlay", missing, YELLOW_DIM),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
            "gap": "10px",
        }),

        html.Div([
            html.Div([
                html.Div("Phase Counts", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(phase_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Rank Buckets", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(rank_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Effective Gamma Status", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(gamma_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Option Chain Status", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(option_chain_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Effective Fusion State", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(fusion_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
            "gap": "10px",
            "marginTop": "12px",
        }),
    ], style={
        "border": "1px solid rgba(45,212,191,.30)",
        "background": "rgba(8,24,39,.72)",
        "borderRadius": "18px",
        "padding": "16px",
        "marginBottom": "16px",
        "boxShadow": "0 0 0 1px rgba(45,212,191,.08) inset",
    })


def _post(path, body):
    try:
        r = req.post(f"{BACKEND_HTTP}{path}", json=body, timeout=4)
        return r.json() if r.ok else {}
    except Exception:
        return {}

def fetch_real_candles(symbol: str, tf: str, limit: int = 200) -> list[dict]:
    """
    Fetch real OHLCV bars from backend Alpaca candle endpoint.
    No synthetic candles are created here.
    """
    tf_map = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "1H": "1Hour",
        "1D": "1Day",
        "1W": "1Week",
    }
    clean = sanitize_symbol(symbol or "")
    if not clean:
        return []

    timeframe = tf_map.get(tf, "5Min")

    try:
        r = req.get(
            f"{BACKEND_HTTP}/api/candles/{clean}",
            params={"timeframe": timeframe, "limit": limit},
            timeout=8,
        )
        if not r.ok:
            print(f"REAL_CANDLES_HTTP_ERROR {clean} {timeframe}: {r.status_code} {r.text[:200]}")
            return []

        data = r.json() if r.ok else {}
        bars = data.get("bars", []) if isinstance(data, dict) else []

        cleaned = []
        for b in bars:
            try:
                cleaned.append({
                    "o": float(b["o"]),
                    "h": float(b["h"]),
                    "l": float(b["l"]),
                    "c": float(b["c"]),
                    "v": int(b.get("v", 0) or 0),
                    "t": str(b.get("t", "")),
                })
            except Exception:
                continue

        return cleaned[-limit:]

    except Exception as e:
        print(f"REAL_CANDLES_FETCH_ERROR {clean} {timeframe}: {e}")
        return []


def _bucket_start(dt: datetime, tf: str) -> datetime:
    """
    Return the beginning of the selected timeframe bucket.
    This is what prevents the chart from creating a new candle on every tick.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)

    if tf == "1m":
        return dt.replace(second=0, microsecond=0)

    if tf == "5m":
        minute = (dt.minute // 5) * 5
        return dt.replace(minute=minute, second=0, microsecond=0)

    if tf == "15m":
        minute = (dt.minute // 15) * 15
        return dt.replace(minute=minute, second=0, microsecond=0)

    if tf == "1H":
        return dt.replace(minute=0, second=0, microsecond=0)

    if tf == "1D":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if tf == "1W":
        # Monday 00:00 UTC week bucket.
        start = dt - timedelta(days=dt.weekday())
        return start.replace(hour=0, minute=0, second=0, microsecond=0)

    minute = (dt.minute // 5) * 5
    return dt.replace(minute=minute, second=0, microsecond=0)


def update_current_candle(candles: list[dict], price: float, volume: int, tick_time: str, tf: str) -> list[dict]:
    """
    Update only the active candle while inside the selected timeframe.
    A new candle is appended only when the timeframe bucket rolls over.
    """
    try:
        tick_dt = datetime.fromisoformat(str(tick_time).replace("Z", "+00:00"))
    except Exception:
        tick_dt = datetime.now(timezone.utc)

    current_bucket = _bucket_start(tick_dt, tf)
    current_t = current_bucket.isoformat()

    if not candles:
        return [{
            "o": price,
            "h": price,
            "l": price,
            "c": price,
            "v": int(volume or 0),
            "t": current_t,
        }]

    new_candles = [dict(c) for c in candles[-199:]]
    last = new_candles[-1]

    try:
        last_dt = datetime.fromisoformat(str(last.get("t", "")).replace("Z", "+00:00"))
        last_bucket = _bucket_start(last_dt, tf)
    except Exception:
        last_bucket = current_bucket

    if last_bucket == current_bucket:
        # Same candle: keep open fixed; update H/L/C and volume.
        last["h"] = max(float(last.get("h", price)), price)
        last["l"] = min(float(last.get("l", price)), price)
        last["c"] = price
        last["v"] = int(last.get("v", 0) or 0) + int(volume or 0)
        last["t"] = current_t
        new_candles[-1] = last
    else:
        # New timeframe bucket: close previous candle, append new candle.
        new_candles.append({
            "o": price,
            "h": price,
            "l": price,
            "c": price,
            "v": int(volume or 0),
            "t": current_t,
        })

    return new_candles[-200:]

def _regime_from_live(live: dict) -> str:
    score = live.get("decision", {}).get("score", 50)
    price = live.get("price", 100)
    kl    = get_key_levels(price)
    if score >= 80 and price >= kl.expansion: return "expansion"
    if score >= 70:                            return "trend_continuation"
    if score >= 45:                            return "neutral"
    if price <= kl.fail:                       return "reversal"
    return "compression"

# ── UI primitives ──────────────────────────────────────────────────────────────

def badge(text, color="teal"):
    p = {"teal":(TEAL_DIM,TEAL_GLOW,BORDER_T),"blue":(BLUE_DIM,"rgba(59,130,246,.12)","rgba(96,165,250,.35)"),
         "yellow":(YELLOW_DIM,"rgba(245,158,11,.12)","rgba(245,158,11,.35)"),
         "red":(RED_DIM,RED_GLOW,"rgba(239,68,68,.35)"),"gray":(TEXT,"rgba(100,116,139,.12)","rgba(100,116,139,.25)"),
         "purple":(PURPLE,PURPLE_GLOW,"rgba(167,139,250,.35)")}
    fg,bg,bdr = p.get(color, p["teal"])
    return html.Span(text, style={"borderRadius":"999px","border":f"1px solid {bdr}",
        "padding":"4px 12px","fontSize":"11px","fontWeight":"800","letterSpacing":".06em",
        "color":fg,"background":bg,"whiteSpace":"nowrap","textTransform":"uppercase"})

def metric_tile(label, value, accent=WHITE, sub=None):
    return html.Div([
        html.Span(label, style={"display":"block","color":WHITE,"fontSize":"11px","fontWeight":"600",
                                "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"6px"}),
        html.Strong(value, style={"display":"block","color":accent,"fontSize":"15px","fontWeight":"800"}),
        *([html.Span(sub, style={"fontSize":"10px","color":WHITE,"marginTop":"2px","display":"block"})] if sub else []),
    ], style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px","minHeight":"64px"})

def card(children, sx=None):
    s = {"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px",
         "padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Section(children, style=s)

def note_box(text, variant=""):
    s = {"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"12px",
         "padding":"12px 14px","color":WHITE,"fontSize":"12px","lineHeight":"1.6"}
    if variant=="yellow": s.update({"borderColor":"rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":"#fef3c7"})
    elif variant=="blue":  s.update({"borderColor":"rgba(59,130,246,.25)","background":"rgba(59,130,246,.08)","color":"#dbeafe"})
    elif variant=="teal":  s.update({"borderColor":BORDER_T,"background":TEAL_GLOW,"color":"#d1fae5"})
    elif variant=="red":   s.update({"borderColor":"rgba(239,68,68,.25)","background":RED_GLOW,"color":"#fecaca"})
    elif variant=="purple":s.update({"borderColor":"rgba(167,139,250,.25)","background":PURPLE_GLOW,"color":"#ede9fe"})
    return html.Div(text, style=s)

def slabel(text):
    return html.Div(text, style={"color":WHITE,"fontSize":"10px","fontWeight":"800",
                                  "textTransform":"uppercase","letterSpacing":".28em","marginBottom":"8px"})

def pbar(label, value, color=None):
    pct = max(0, min(100, value))
    c = color or (TEAL_DIM if pct>=70 else (YELLOW_DIM if pct>=45 else RED_DIM))
    return html.Div([
        html.Div([html.Span(label,style={"color":WHITE,"fontSize":"12px","fontWeight":"600"}),
                  html.Span(f"{pct}%",style={"color":c,"fontWeight":"800","fontSize":"13px"})],
                 style={"display":"flex","justifyContent":"space-between","marginBottom":"6px"}),
        html.Div(html.Div(style={"width":f"{pct}%","height":"100%","borderRadius":"999px",
                                  "background":f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})","transition":"width .5s"}),
                 style={"height":"8px","background":"rgba(255,255,255,.08)","borderRadius":"999px","overflow":"hidden"}),
    ])

def brow(label, value, tone):
    color = TEAL_DIM if tone=="up" else (RED_DIM if tone=="down" else YELLOW_DIM)
    return html.Div([
        html.Div([html.Span(label,style={"fontSize":"13px","fontWeight":"600","color":WHITE}),
                  html.Span(f"{value}%",style={"fontWeight":"800","color":color,"fontSize":"13px"})],
                 style={"display":"flex","justifyContent":"space-between","marginBottom":"6px"}),
        html.Div(html.Div(style={"width":f"{value}%","height":"100%","borderRadius":"999px",
                                  "background":f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})"}),
                 style={"height":"7px","background":"rgba(255,255,255,.08)","borderRadius":"999px","overflow":"hidden"}),
    ], style={"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"12px",
               "padding":"12px 14px","marginBottom":"8px"})

def zcard(name, level, desc, color):
    return html.Div([
        html.P(name, style={"fontSize":"11px","color":WHITE,"margin":"0 0 6px","fontWeight":"600",
                             "textTransform":"uppercase","letterSpacing":".1em"}),
        html.Div(level, style={"fontSize":"26px","fontWeight":"900","color":color,"margin":"4px 0 8px"}),
        html.P(desc,  style={"fontSize":"11px","color":WHITE,"margin":"0"}),
    ], style={"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"14px",
               "padding":"14px","textAlign":"center"})

def _tf_btn_style(tf, active_tf):
    active = tf == active_tf
    return {"background":TEAL_GLOW if active else "transparent","color":TEAL_DIM if active else TEXT,
            "border":f"1px solid {BORDER_T}" if active else "none","borderRadius":"10px",
            "padding":"8px 12px","fontSize":"12px","fontWeight":"800" if active else "700","cursor":"pointer","fontFamily":"inherit"}

def _input_style(width="100%"):
    return {"background":"rgba(0,0,0,.3)","color":WHITE,"border":f"1px solid {BORDER}",
            "borderRadius":"10px","padding":"9px 12px","width":width,"fontSize":"13px",
            "fontWeight":"600","fontFamily":"inherit"}

def _btn(label, id_, color=TEAL_DIM, bg=TEAL_GLOW, border=BORDER_T, extra=None):
    s = {"background":bg,"border":f"1px solid {border}","color":color,"borderRadius":"12px",
         "padding":"10px 18px","fontSize":"13px","fontWeight":"800","cursor":"pointer","fontFamily":"inherit"}
    if extra: s.update(extra)
    return html.Button(label, id=id_, n_clicks=0, style=s)

# ── Chart ──────────────────────────────────────────────────────────────────────

def build_chart(candles, price, nodes, tf="5m"):
    """Clean chart — integer index x-axis for proper candle rendering."""
    kl = get_key_levels(price)
    xs = list(range(len(candles)))
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=xs,
        open=[c["o"] for c in candles],
        high=[c["h"] for c in candles],
        low=[c["l"] for c in candles],
        close=[c["c"] for c in candles],
        name="Price",
        increasing=dict(line=dict(color=TEAL_DIM, width=2), fillcolor=TEAL_DIM),
        decreasing=dict(line=dict(color=RED_DIM,  width=2), fillcolor=RED_DIM),
        whiskerwidth=1.0,
    ))
    # Level lines — no annotations (labels are in the Price Ladder panel)
    for level,color,dash,width in [
        (kl.breakout,   TEAL_DIM,   "dash",    1.0),
        (kl.prior_high, TEAL_DIM,   "dot",     1.0),
        (kl.expansion,  TEAL_DIM,   "dashdot", 1.0),
        (kl.confirm,    YELLOW_DIM, "solid",   1.0),
        (kl.trigger,    YELLOW_DIM, "dash",    1.0),
        (kl.trap,       RED_DIM,    "dot",     1.0),
        (kl.fail,       RED_DIM,    "dash",    1.0),
    ]:
        fig.add_hline(y=level, line_color=color, line_dash=dash,
                      line_width=width, opacity=0.6)
    # Live price line
    fig.add_hline(y=price, line_color=BLUE_DIM, line_dash="solid", line_width=1.5, opacity=0.9)
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=NAVY,
        font=dict(family="DM Sans", color=WHITE, size=12),
        xaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,.06)", zeroline=False,
            rangeslider=dict(visible=False),
            showticklabels=False,
            title=None,
            color=WHITE,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,.06)", zeroline=False,
            color=WHITE, side="right", tickformat=".2f",
            tickfont=dict(color=WHITE, size=12, family="DM Mono, monospace"),
        ),
        # Enough right margin for y-axis labels, bottom for x-axis labels
        margin=dict(l=0, r=60, t=8, b=24),
        height=480,
        showlegend=False,
        hovermode="x unified",
        hoverlabel=dict(bgcolor=NAVY_CARD, font_color=WHITE, bordercolor=BORDER, font_size=12),
        dragmode="pan",
    )
    return fig

def _build_clock_inline():
    EST = timezone(timedelta(hours=-4)); now = datetime.now(EST)
    minutes = now.hour*60+now.minute; in_sess = 570<=minutes<=960
    phase = ("Outside RTH" if not in_sess else "Opening Drive" if minutes<630
             else "Midday Auction" if minutes<840 else "Closing Auction")
    pc = TEAL_DIM if in_sess else MUTED
    return [metric_tile("Clock",now.strftime("%I:%M:%S %p")+" ET"),
            html.Div(style={"height":"8px"}),
            metric_tile("Session Phase",phase,pc),
            html.Div(style={"height":"10px"}),
            note_box("Future: economic releases, auction windows, proprietary cycle layers.")]

# ── Trade Plan Panel ───────────────────────────────────────────────────────────
# The INPUT components (buttons, fields) live in the permanent layout via their IDs.
# This function only builds the card SHELL — the inputs are defined once in the layout.

def _build_trade_plan_contents(live):
    """Only updates the header label — buttons/inputs are permanent in layout."""
    price  = live.get("price", 0)
    symbol = live.get("symbol", "")
    return html.Div([
        html.H2("Plan Trade", style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0"}),
        html.Span(f"{symbol} · ${price:.2f}", style={"fontSize":"12px","color":WHITE}),
    ], style={"display":"flex","justifyContent":"space-between","alignItems":"center"})



# ── Active Trade Panel ─────────────────────────────────────────────────────────

def build_active_trade_panel(trade: dict, current_price: float):
    if not trade:
        return html.Div()
    direction  = trade.get("direction","long")
    entry      = trade.get("entry_price", current_price)
    stop       = trade.get("stop_price")
    target     = trade.get("target_price")
    size       = trade.get("size", 0)
    if direction == "long":
        unreal_pnl = (current_price - entry) * size
        unreal_pct = ((current_price - entry) / entry * 100) if entry else 0
    else:
        unreal_pnl = (entry - current_price) * size
        unreal_pct = ((entry - current_price) / entry * 100) if entry else 0

    pnl_color = TEAL_DIM if unreal_pnl >= 0 else RED_DIM
    entry_time = trade.get("entry_time", "")

    return card([
        html.Div([
            html.H2("Active Trade", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0"}),
            badge(direction.upper(), "teal" if direction=="long" else "red"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"14px"}),

        html.Div([
            metric_tile("Entry",   f"${entry:.2f}",        WHITE),
            metric_tile("Current", f"${current_price:.2f}", BLUE_DIM),
            metric_tile("Unreal P&L", f"${unreal_pnl:+.2f} ({unreal_pct:+.2f}%)", pnl_color),
        ], style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr","gap":"8px","marginBottom":"12px"}),

        html.Div([
            metric_tile("Stop",   f"${stop:.2f}"   if stop   else "—", RED_DIM),
            metric_tile("Target", f"${target:.2f}" if target else "—", TEAL_DIM),
            metric_tile("Size",   str(size),        TEXT),
        ], style={"display":"grid","gridTemplateColumns":"1fr 1fr 1fr","gap":"8px","marginBottom":"14px"}),

        # Exit review fields
        html.Div([
            slabel("Exit Review"),
            html.Div([
                dcc.Checklist(id="exit-flags", options=[
                    {"label": " No trade plan existed",        "value": "no_plan"},
                    {"label": " Stop was moved wider",         "value": "stop_moved_wider"},
                    {"label": " Target moved emotionally",     "value": "target_moved"},
                    {"label": " Exited before invalidation",   "value": "premature_exit"},
                    {"label": " Added size after adverse move","value": "added_size_adverse"},
                    {"label": " Changed TF to justify trade",  "value": "timeframe_changed"},
                ], value=[],
                style={"color":WHITE,"fontSize":"12px","lineHeight":"2"},
                inputStyle={"marginRight":"6px","accentColor":TEAL_DIM}),
            ], style={"marginBottom":"10px"}),
            dcc.Textarea(id="exit-notes", value="", placeholder="Exit notes…",
                style={**_input_style(),"height":"50px","resize":"vertical"}),
        ], style={"borderTop":f"1px solid {BORDER}","paddingTop":"12px","marginBottom":"12px"}),

        _btn("Exit Trade", "btn-exit-trade",
             color=RED_DIM, bg=RED_GLOW, border="rgba(239,68,68,.35)"),
        html.Div(id="exit-status", style={"marginTop":"8px","fontSize":"12px","color":TEAL_DIM}),

        dcc.Store(id="s-active-trade-id", data=trade.get("trade_id")),
    ])


# ── CSV Import Tab ─────────────────────────────────────────────────────────────

BROKER_INFO = {
    "alpaca":       {"name": "Alpaca",                  "icon": "", "priority": "HIGH",   "color": TEAL_DIM},
    "tdameritrade": {"name": "TD Ameritrade / Schwab",  "icon": "", "priority": "HIGH",   "color": TEAL_DIM},
    "ibkr":         {"name": "Interactive Brokers",     "icon": "", "priority": "HIGH",   "color": TEAL_DIM},
    "robinhood":    {"name": "Robinhood",               "icon": "", "priority": "HIGH",   "color": TEAL_DIM},
    "webull":       {"name": "Webull",                  "icon": "", "priority": "MEDIUM", "color": YELLOW_DIM},
    "generic":      {"name": "Generic CSV",             "icon": "", "priority": "ALWAYS", "color": BLUE_DIM},
}

EXPORT_INSTRUCTIONS = {
    "alpaca": [
        "Log in to Alpaca dashboard",
        "Go to Account → Activity",
        "Select date range → Export CSV",
        "Upload the downloaded file here",
    ],
    "tdameritrade": [
        "Log in to thinkorswim or TDA web",
        "Go to My Account → History & Statements",
        "Select Trade History → Export to CSV",
        "Upload the downloaded file here",
    ],
    "ibkr": [
        "Log in to Client Portal or TWS",
        "Go to Reports → Flex Query",
        "Create a Trade Confirmation Flex Query",
        "Export as CSV and upload here",
    ],
    "robinhood": [
        "Log in to Robinhood web (not mobile)",
        "Go to Account → Statements & History",
        "Download Account Statement CSV",
        "Upload the downloaded file here",
    ],
    "webull": [
        "Log in to Webull desktop app",
        "Go to Orders → Order History",
        "Click Export in top right",
        "Upload the downloaded CSV here",
    ],
    "generic": [
        "Export your trade history from any broker",
        "Ensure CSV has: Symbol, Side (buy/sell), Quantity, Price, Date",
        "Upload and map columns if needed",
    ],
}

def build_import_tab():
    # Fetch latest analysis if exists
    analysis = _get(f"/api/import/analysis/{USER_ID}")

    ROW = {"display":"flex","gap":"16px","marginBottom":"16px"}

    # ── Broker cards ──────────────────────────────────────────────────────────
    broker_cards = []
    for key, info in BROKER_INFO.items():
        priority_color = (TEAL_DIM if info["priority"]=="HIGH"
                         else YELLOW_DIM if info["priority"]=="MEDIUM"
                         else BLUE_DIM)
        broker_cards.append(html.Div([
            html.Div([
                html.Span(info["icon"], style={"fontSize":"24px"}),
                html.Div([
                    html.Div(info["name"],
                             style={"fontSize":"13px","fontWeight":"800","color":WHITE}),
                    html.Span(info["priority"],
                              style={"fontSize":"10px","fontWeight":"800","color":priority_color,
                                     "letterSpacing":".1em"}),
                ]),
            ], style={"display":"flex","alignItems":"center","gap":"10px","marginBottom":"10px"}),
            *[html.P(f"• {step}",
                     style={"fontSize":"11px","color":WHITE,"marginBottom":"4px","lineHeight":"1.5"})
              for step in EXPORT_INSTRUCTIONS[key]],
        ], style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}",
                   "borderRadius":"14px","padding":"14px","flex":"1","minWidth":"200px"}))

    # ── Upload section ────────────────────────────────────────────────────────
    upload_section = card([
        html.H2("Upload Brokerage History",
                style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"6px"}),
        html.P("Upload your brokerage trade export and we'll instantly build your behavioral profile.",
               style={"fontSize":"12px","color":WHITE,"marginBottom":"16px"}),

        # Broker cards
        html.Div(broker_cards,
                 style={"display":"flex","flexWrap":"wrap","gap":"12px","marginBottom":"20px"}),

        # Upload widget + reset button
        html.Div([
            html.Div([
                html.Div("Upload Brokerage Statement",
                         style={"fontSize":"13px","fontWeight":"800","color":WHITE}),
                html.Button("️ Clear All Trades", id="btn-reset-imports", n_clicks=0,
                    style={"background":"rgba(239,68,68,.1)","border":"1px solid rgba(239,68,68,.3)",
                           "borderRadius":"10px","color":"#f87171","cursor":"pointer",
                           "fontSize":"12px","fontWeight":"700","padding":"6px 14px",
                           "fontFamily":"DM Sans, sans-serif"}),
            ], style={"display":"flex","justifyContent":"space-between",
                       "alignItems":"center","marginBottom":"12px"}),
            html.Div(id="reset-status"),
        ]),
        html.Div([
            dcc.Upload(
                id="csv-upload",
                children=html.Div([
                    html.Div("", style={"fontSize":"32px","marginBottom":"8px"}),
                    html.Div("Drag & drop your CSV here, or click to browse",
                             style={"fontSize":"14px","fontWeight":"700","color":WHITE,"marginBottom":"4px"}),
                    html.Div("Supports: Alpaca · TD Ameritrade · Schwab · IBKR · Robinhood · Webull · Generic CSV",
                             style={"fontSize":"11px","color":WHITE}),
                ], style={"textAlign":"center","padding":"20px"}),
                style={
                    "border":f"2px dashed {BORDER_T}",
                    "borderRadius":"16px",
                    "background":TEAL_GLOW,
                    "cursor":"pointer",
                    "marginBottom":"14px",
                    "transition":"border-color .2s",
                },
                accept=".csv",
                multiple=False,
            ),
            html.Div(id="csv-upload-status",
                     style={"fontSize":"13px","color":TEAL_DIM,"minHeight":"20px"}),
        ]),
    ])

    # ── Analysis display ──────────────────────────────────────────────────────
    if not analysis:
        analysis_section = card([
            note_box("No import history yet. Upload your brokerage CSV above to generate your behavioral snapshot.", "blue")
        ])
    else:
        total   = analysis.get("total_trades", 0)
        wr      = analysis.get("win_rate", 0)
        pnl     = analysis.get("total_pnl", 0)
        avg_win = analysis.get("avg_win", 0)
        avg_loss= analysis.get("avg_loss", 0)
        rr      = analysis.get("rr_ratio", 0)
        edge    = analysis.get("edge_score", 0)
        hold    = analysis.get("avg_hold_time", "—")
        best_d  = analysis.get("best_day")
        worst_d = analysis.get("worst_day")
        best_s  = analysis.get("best_symbol")
        worst_s = analysis.get("worst_symbol")
        flags   = analysis.get("behavioral_flags", [])
        overtrade = analysis.get("overtrade_rate", 0)
        sym_perf  = analysis.get("symbol_performance", {})
        day_perf  = analysis.get("day_performance", {})

        wr_color  = TEAL_DIM if wr>=55 else (YELLOW_DIM if wr>=45 else RED_DIM)
        pnl_color = TEAL_DIM if pnl>=0 else RED_DIM
        edge_color= TEAL_DIM if edge>0 else RED_DIM
        rr_color  = TEAL_DIM if rr>=1.5 else (YELLOW_DIM if rr>=1.0 else RED_DIM)

        # Mathematical edge insight
        if edge > 0:
            edge_insight = f"Your system has a positive mathematical edge of ${edge:.2f} per trade."
        else:
            edge_insight = f"Your system has a negative edge of ${edge:.2f} per trade — the math works against you long-term."

        # Top symbols table
        top_syms = sorted(sym_perf.items(), key=lambda x: x[1]["total_pnl"], reverse=True)[:8]
        sym_rows = []
        for sym, sp in top_syms:
            c = TEAL_DIM if sp["total_pnl"]>=0 else RED_DIM
            sym_rows.append(html.Tr([
                html.Td(sym, style={"color":WHITE,"fontWeight":"700","padding":"8px 12px","fontSize":"12px"}),
                html.Td(str(sp["trades"]), style={"color":WHITE,"padding":"8px 12px","fontSize":"12px","textAlign":"center"}),
                html.Td(f"{sp['win_rate']:.0f}%", style={"color":TEAL_DIM if sp['win_rate']>=50 else RED_DIM,"fontWeight":"800","padding":"8px 12px","fontSize":"12px","textAlign":"center"}),
                html.Td(f"${sp['total_pnl']:+.2f}", style={"color":c,"fontWeight":"800","padding":"8px 12px","fontSize":"12px","textAlign":"right"}),
            ], style={"borderBottom":f"1px solid {BORDER}"}))

        analysis_section = html.Div([
            # Score cards
            card([
                html.H2("Historical Behavioral Snapshot",
                        style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"16px"}),
                html.Div([
                    metric_tile("Total Trades",    str(total),          WHITE),
                    metric_tile("Win Rate",        f"{wr}%",            wr_color),
                    metric_tile("Total P&L",       f"${pnl:+,.2f}",     pnl_color),
                    metric_tile("Avg Win",         f"${avg_win:+.2f}",  TEAL_DIM),
                    metric_tile("Avg Loss",        f"${avg_loss:+.2f}", RED_DIM),
                    metric_tile("Risk/Reward",     f"{rr:.2f}x",        rr_color),
                    metric_tile("Avg Hold Time",   hold,                BLUE_DIM),
                    metric_tile("Overtrade Rate",  f"{overtrade:.0f}%", YELLOW_DIM if overtrade>20 else TEXT),
                ], style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"10px","marginBottom":"16px"}),

                # Mathematical edge
                html.Div([
                    html.Span("Mathematical Edge: ",
                              style={"fontWeight":"800","color":edge_color,"fontSize":"13px"}),
                    html.Span(edge_insight, style={"color":WHITE,"fontSize":"12px"}),
                ], style={"background":"rgba(0,0,0,.2)","borderRadius":"12px","padding":"12px 16px",
                           "border":f"1px solid {BORDER}","marginBottom":"12px"}),

                # Best/worst
                html.Div([
                    html.Div([
                        html.Span("Best Day: ",   style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px"}),
                        html.Span(best_d or "—",      style={"color":WHITE,"fontSize":"12px"}),
                        html.Span("   Worst Day: ",style={"color":RED_DIM,"fontWeight":"700","fontSize":"12px","marginLeft":"16px"}),
                        html.Span(worst_d or "—",     style={"color":WHITE,"fontSize":"12px"}),
                    ]),
                    html.Div([
                        html.Span("Best Symbol: ",  style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"12px"}),
                        html.Span(best_s or "—",        style={"color":WHITE,"fontSize":"12px"}),
                        html.Span("   Worst Symbol: ",style={"color":RED_DIM,"fontWeight":"700","fontSize":"12px","marginLeft":"16px"}),
                        html.Span(worst_s or "—",       style={"color":WHITE,"fontSize":"12px"}),
                    ], style={"marginTop":"6px"}),
                ], style={"background":"rgba(0,0,0,.2)","borderRadius":"12px","padding":"12px 16px",
                           "border":f"1px solid {BORDER}"}),
            ]),

            html.Div(style={"height":"16px"}),

            html.Div([
                # Behavioral flags
                card([
                    html.H2("Behavioral Flags",
                            style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
                    *([html.Div([
                        html.Span("" if any(w in f for w in ["Strong","Above","positive","discipline"])
                                  else "",
                                  style={"fontSize":"14px"}),
                        html.Span(f, style={"fontSize":"12px","color":WHITE,"lineHeight":"1.6"}),
                    ], style={"padding":"8px 12px","borderRadius":"10px","marginBottom":"6px",
                               "background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}"})
                      for f in flags]
                     if flags else [note_box("No behavioral flags detected yet.", "blue")]),
                ], sx={"flex":"1"}),

                # Symbol performance table
                card([
                    html.H2("Symbol Performance",
                            style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
                    html.Table([
                        html.Thead(html.Tr([
                            html.Th("Symbol",  style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"left"}),
                            html.Th("Trades",  style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"center"}),
                            html.Th("Win %",   style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"center"}),
                            html.Th("Total P&L",style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","padding":"6px 12px","textAlign":"right"}),
                        ])),
                        html.Tbody(sym_rows if sym_rows
                                   else [html.Tr([html.Td("No data",colSpan=4,
                                                           style={"color":WHITE,"padding":"16px","textAlign":"center"})])]),
                    ], style={"width":"100%","borderCollapse":"collapse"}),
                ], sx={"flex":"1"}),
            ], style={**ROW,"alignItems":"start"}),
        ])

    return html.Div([upload_section, html.Div(style={"height":"16px"}), analysis_section])


# ── Behavioral Dashboard Tab ───────────────────────────────────────────────────

def _behavior_empty_state():
    return card([
        html.H2("Behavioral Intelligence", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
        note_box("Behavioral tracking activates after your first trade upload. Go to Import History to upload a brokerage statement.", "blue"),
        html.Div(style={"height":"12px"}),
        note_box("Once trades are imported, your decision scores, regime memory, and behavioral patterns will appear here.", "yellow"),
    ])


def build_behavior_tab():
    dash_data = _get(f"/api/behavior/dashboard/{USER_ID}")
    if not dash_data:
        return card([note_box("No behavioral data yet. Start tracking trades to build your profile.", "blue")])

    total    = dash_data.get("total_trades", 0)
    comp     = dash_data.get("avg_decision_score", 0)
    exec_    = dash_data.get("execution_score", 0)
    disc     = dash_data.get("discipline_score", 0)
    timing   = dash_data.get("timing_score", 0)
    risk     = dash_data.get("risk_score", 0)
    flag     = dash_data.get("common_behavior_flag", "neutral")
    best_r   = dash_data.get("best_regime")
    worst_r  = dash_data.get("worst_regime")
    regimes  = dash_data.get("regime_performance", [])
    cards_   = dash_data.get("recent_scorecards", [])
    warnings = dash_data.get("adaptive_warnings", [])

    def score_color(v): return TEAL_DIM if v>=70 else (YELLOW_DIM if v>=45 else RED_DIM)

    flag_color = {
        "plan_followed":"teal","disciplined_execution":"teal",
        "late_chase":"yellow","premature_exit":"yellow","panic_exit":"red",
        "plan_violated":"red","over_sized":"red","ignored_high_quality_signal":"yellow",
        "revenge_trade":"red","neutral":"gray","under_sized":"gray",
    }.get(flag, "gray")

    ROW = {"display":"flex","gap":"16px","marginBottom":"16px"}

    # Section 1 — Profile scores
    section1 = card([
        html.H2("Behavioral Profile", style={"fontSize":"16px","fontWeight":"800","color":WHITE,"marginBottom":"16px"}),
        html.Div([
            metric_tile("Total Trades",    str(total),          WHITE),
            metric_tile("Composite Score", f"{comp}%",          score_color(comp)),
            metric_tile("Execution",       f"{exec_}%",         score_color(exec_)),
            metric_tile("Discipline",      f"{disc}%",          score_color(disc)),
            metric_tile("Timing",          f"{timing}%",        score_color(timing)),
            metric_tile("Risk Mgmt",       f"{risk}%",          score_color(risk)),
        ], style={"display":"grid","gridTemplateColumns":"repeat(6,1fr)","gap":"10px","marginBottom":"16px"}),
        html.Div([
            pbar("Composite Decision Score", comp),
            html.Div(style={"height":"8px"}),
            pbar("Execution Quality",        exec_),
            html.Div(style={"height":"8px"}),
            pbar("Discipline",               disc),
            html.Div(style={"height":"8px"}),
            pbar("Timing Quality",           timing),
            html.Div(style={"height":"8px"}),
            pbar("Risk Management",          risk),
        ]),
    ])

    # Section 2 — Adaptive warnings
    def warn_box(w):
        variant = "teal" if w["type"]=="strength" else "yellow"
        icon    = "" if w["type"]=="strength" else ""
        return note_box(f"{icon}  {w['message']}", variant)

    section2 = card([
        html.H2("Adaptive Guidance", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
        *([warn_box(w) for w in warnings] if warnings
          else [note_box("No active warnings. Keep trading to build your profile.", "blue")]),
        html.Div(style={"height":"8px"}),
        html.Div([
            html.Span("Most Common Pattern: ", style={"fontSize":"12px","color":WHITE}),
            badge(flag.replace("_"," "), flag_color),
        ], style={"marginTop":"10px"}),
        html.Div([
            *([html.Div([html.Span("Best Regime: ", style={"fontSize":"12px","color":WHITE}),
                         badge(best_r.replace("_"," "), "teal")],
                        style={"marginTop":"8px"})] if best_r else []),
            *([html.Div([html.Span("Worst Regime: ", style={"fontSize":"12px","color":WHITE}),
                         badge(worst_r.replace("_"," "), "red")],
                        style={"marginTop":"8px"})] if worst_r else []),
        ]),
    ])

    # Section 3 — Regime table
    regime_rows_html = []
    for r in regimes:
        wr_color  = TEAL_DIM if r["win_rate"]>=60 else (YELLOW_DIM if r["win_rate"]>=40 else RED_DIM)
        dec_color = TEAL_DIM if r["avg_decision_score"]>=70 else (YELLOW_DIM if r["avg_decision_score"]>=45 else RED_DIM)
        regime_rows_html.append(html.Tr([
            html.Td(r["regime"].replace("_"," ").title(),
                    style={"color":WHITE,"fontWeight":"600","padding":"10px 12px","fontSize":"12px"}),
            html.Td(str(r["total_trades"]),
                    style={"color":WHITE,"padding":"10px 12px","fontSize":"12px","textAlign":"center"}),
            html.Td(f"{r['win_rate']:.0f}%",
                    style={"color":wr_color,"fontWeight":"800","padding":"10px 12px","fontSize":"12px","textAlign":"center"}),
            html.Td(f"{r['avg_decision_score']:.0f}",
                    style={"color":dec_color,"fontWeight":"800","padding":"10px 12px","fontSize":"12px","textAlign":"center"}),
            html.Td(r.get("common_behavior_flag","—").replace("_"," "),
                    style={"color":WHITE,"padding":"10px 12px","fontSize":"11px"}),
        ], style={"borderBottom":f"1px solid {BORDER}"}))

    section3 = card([
        html.H2("Regime Performance Memory", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"14px"}),
        html.Table([
            html.Thead(html.Tr([
                html.Th("Regime",           style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"left"}),
                html.Th("Trades",           style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"center"}),
                html.Th("Win Rate",         style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"center"}),
                html.Th("Avg Score",        style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"center"}),
                html.Th("Common Pattern",   style={"color":WHITE,"fontSize":"10px","fontWeight":"800","textTransform":"uppercase","letterSpacing":".12em","padding":"8px 12px","textAlign":"left"}),
            ])),
            html.Tbody(regime_rows_html if regime_rows_html
                       else [html.Tr([html.Td("No regime data yet.",
                                               colSpan=5,style={"color":WHITE,"padding":"20px","textAlign":"center"})])]),
        ], style={"width":"100%","borderCollapse":"collapse"}),
    ]) if True else html.Div()

    # Section 4 — Recent scorecards
    def scorecard_row(s):
        c = TEAL_DIM if s["composite_decision_score"]>=70 else (YELLOW_DIM if s["composite_decision_score"]>=45 else RED_DIM)
        pnl = s.get("pnl_percent")
        pnl_str = f"{pnl:+.2f}%" if pnl is not None else "—"
        pnl_c = TEAL_DIM if (pnl or 0)>0 else RED_DIM
        return html.Div([
            html.Div([
                html.Span(s.get("symbol","—"), style={"fontWeight":"800","color":WHITE,"fontSize":"13px"}),
                html.Span(s.get("direction","").upper() if s.get("direction") else "",
                          style={"fontSize":"10px","color":WHITE,"marginLeft":"8px"}),
                html.Span(s.get("primary_behavior_flag","").replace("_"," "),
                          style={"fontSize":"10px","color":WHITE,"marginLeft":"8px"}),
            ]),
            html.Div([
                html.Span(f"Score: {s['composite_decision_score']:.0f}",
                          style={"color":c,"fontWeight":"800","fontSize":"13px"}),
                html.Span(f"P&L: {pnl_str}",
                          style={"color":pnl_c,"fontWeight":"700","fontSize":"12px","marginLeft":"12px"}),
                html.Span(s.get("timestamp","")[:16] if s.get("timestamp") else "",
                          style={"color":WHITE,"fontSize":"11px","marginLeft":"12px"}),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"10px 14px","borderBottom":f"1px solid {BORDER}",
                   "borderRadius":"10px","background":"rgba(0,0,0,.15)","marginBottom":"6px"})

    section4 = card([
        html.H2("Recent Decision Scorecards", style={"fontSize":"15px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
        *([scorecard_row(s) for s in cards_] if cards_
          else [note_box("No scorecards yet. Complete a trade to generate your first scorecard.", "blue")]),
    ])

    return html.Div([section1, html.Div(style={"height":"16px"}),
                     html.Div([section2, section3], style={**ROW,"alignItems":"start"}),
                     html.Div(style={"height":"16px"}), section4])

# ── Command tab ────────────────────────────────────────────────────────────────

def build_login_page(error=""):
    return html.Div([
        html.Div([
            html.Div([
                html.Div("Σ", style={"fontSize":"48px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1"}),
                html.Div("SIGMALYTIC", style={"fontSize":"20px","fontWeight":"900","color":WHITE,"letterSpacing":".2em","marginTop":"4px"}),
                html.Div("QUANT CORPORATION", style={"fontSize":"10px","fontWeight":"700","color":WHITE,"letterSpacing":".3em","marginTop":"2px"}),
            ], style={"textAlign":"center","marginBottom":"40px"}),

            html.Div([
                # Login section
                html.Div(id="login-section", children=[
                    html.H2("Sign In", style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
                    html.Div([
                        html.Label("Email", style={"fontSize":"11px","fontWeight":"700","color":WHITE,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="login-email", type="email", placeholder="you@example.com",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"16px"}),
                    html.Div([
                        html.Label("Password", style={"fontSize":"11px","fontWeight":"700","color":WHITE,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="login-password", type="password", placeholder="••••••••",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"24px"}),
                    html.Div(id="login-error", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
                    html.Button("Sign In", id="login-btn", n_clicks=0,
                        style={"width":"100%","background":TEAL,"color":WHITE,"border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700",
                               "cursor":"pointer","marginBottom":"16px"}),
                    html.Div([
                        html.Div(style={"flex":"1","height":"1px","background":BORDER}),
                        html.Span("or", style={"color":WHITE,"fontSize":"12px","padding":"0 12px"}),
                        html.Div(style={"flex":"1","height":"1px","background":BORDER}),
                    ], style={"display":"flex","alignItems":"center","marginBottom":"16px"}),
                    html.Button("Try Demo — No Sign Up Required", id="demo-btn", n_clicks=0,
                        style={"width":"100%","background":"rgba(45,143,111,.15)","color":TEAL_DIM,
                               "border":f"1px solid {BORDER_T}","borderRadius":"8px","padding":"14px",
                               "fontSize":"13px","fontWeight":"700","cursor":"pointer","marginBottom":"24px"}),
                    html.Div([
                        html.Span("Don't have an account? ", style={"color":WHITE,"fontSize":"12px"}),
                        html.Button("Sign Up", id="goto-signup-btn", n_clicks=0,
                            style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px",
                                   "fontWeight":"700","cursor":"pointer","padding":"0"}),
                    ], style={"textAlign":"center"}),
                ]),

                # Signup section (hidden initially)
                html.Div(id="signup-section", style={"display":"none"}, children=[
                    html.H2("Create Account", style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
                    html.Div([
                        html.Label("Email", style={"fontSize":"11px","fontWeight":"700","color":WHITE,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="signup-email", type="email", placeholder="you@example.com",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"16px"}),
                    html.Div([
                        html.Label("Password", style={"fontSize":"11px","fontWeight":"700","color":WHITE,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="signup-password", type="password", placeholder="Min 6 characters",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"24px"}),
                    html.Div(id="signup-error", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}),
                    html.Div([
                        dcc.Checklist(
                            id="signup-agree-terms",
                            options=[{"label": "", "value": "agreed"}],
                            value=[],
                            style={"display":"inline-block","marginRight":"8px","verticalAlign":"middle"},
                            inputStyle={"marginRight":"8px"},
                        ),
                        html.Span([
                            "I agree to the ",
                            html.A("Terms of Service", href=f"{BACKEND_HTTP}/terms", target="_blank",
                                   style={"color":TEAL_DIM,"textDecoration":"underline"}),
                            " and ",
                            html.A("Privacy Policy", href=f"{BACKEND_HTTP}/privacy", target="_blank",
                                   style={"color":TEAL_DIM,"textDecoration":"underline"}),
                        ], style={"fontSize":"12px","color":WHITE}),
                    ], style={"display":"flex","alignItems":"center","marginBottom":"20px"}),
                    html.Button("Create Account", id="signup-btn", n_clicks=0,
                        style={"width":"100%","background":TEAL,"color":WHITE,"border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700",
                               "cursor":"pointer","marginBottom":"24px"}),
                    html.Div([
                        html.Span("Already have an account? ", style={"color":WHITE,"fontSize":"12px"}),
                        html.Button("Sign In", id="goto-login-btn", n_clicks=0,
                            style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px",
                                   "fontWeight":"700","cursor":"pointer","padding":"0"}),
                    ], style={"textAlign":"center"}),
                ]),

            ], style={"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px",
                      "padding":"40px","width":"400px","boxShadow":"0 20px 60px rgba(0,0,0,.4)"}),

            html.Div([
                html.A("Terms of Service", href=f"{BACKEND_HTTP}/terms", target="_blank",
                       style={"color":MUTED,"fontSize":"11px","textDecoration":"underline","marginRight":"16px"}),
                html.A("Privacy Policy", href=f"{BACKEND_HTTP}/privacy", target="_blank",
                       style={"color":MUTED,"fontSize":"11px","textDecoration":"underline"}),
            ], style={"marginTop":"20px","textAlign":"center"}),

        ], style={"display":"flex","flexDirection":"column","alignItems":"center",
                  "justifyContent":"center","minHeight":"100vh","padding":"20px"}),
    ], style={"background":NAVY})

def build_direction_panel(decision, score):
    """Compact, user-readable Direction & Confidence panel."""
    bias = decision.get("bias", "Neutral")
    status = decision.get("status", "Watching")
    confidence = decision.get("confidence", f"{score}%")
    mode = decision.get("mode", "Standard")
    grade = decision.get("grade", "—")

    if str(bias).lower() == "bullish":
        color = TEAL_DIM
        icon = ""
    elif str(bias).lower() == "bearish":
        color = RED_DIM
        icon = ""
    else:
        color = YELLOW_DIM
        icon = ""

    return html.Div([
        slabel("Direction Intelligence"),
        html.Div(
            f"{icon} {str(bias).upper()}",
            style={
                "color": color,
                "fontSize": "28px",
                "fontWeight": "900",
                "lineHeight": "1",
                "letterSpacing": "-.02em",
                "margin": "6px 0 10px",
            }
        ),
        html.Div([
            metric_tile("Confidence", confidence, color),
            metric_tile("Status", status, color),
            metric_tile("Grade", grade, color),
            metric_tile("Mode", mode, BLUE_DIM),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"}),
    ])


def build_command_tab(live, candles, symbol, tf):
    price    = live["price"]; decision = live["decision"]
    nodes    = live["confluence"]; kl = get_key_levels(price)
    seq      = live["sequence"]; score = decision["score"]
    try:
        ts = datetime.fromisoformat(live["timestamp"].replace("Z","+00:00"))
        ts = ts.astimezone(timezone(timedelta(hours=-4))); live_age = ts.strftime("%I:%M:%S %p")
    except: live_age = "—"
    sc   = TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    size = "FULL" if score>=80 else ("HALF" if score>=65 else ("PROBE" if score>=45 else "NONE"))
    top  = nodes[0] if nodes else {"public_label":"—","score":0}
    vs   = max(18,min(96,round(abs(price-kl.trigger)*18+(seq%9)*4)))
    cp   = max(12,min(94,round(score+(8 if price>kl.confirm else -10)+(seq%5))))
    pp   = max(8,min(92,100-cp)); gp = max(20,min(95,round(55+(price-kl.confirm)*7)))
    fb   = "Call Accumulation / Supportive Flow" if price>=kl.confirm else "Neutral Rotation / Pinning"
    as_  = "Expansion Alert" if score>=80 else ("Trap-Door Alert" if price<kl.trap else "Monitoring")
    aa   = as_ != "Monitoring"
    fig  = build_chart(candles, price, nodes, tf)
    ROW  = {"display":"flex","gap":"16px","marginBottom":"16px"}
    regime = _regime_from_live(live)

    # ── Price Ladder row helper ───────────────────────────────────────────────
    def level_row(label, level, color, is_live=False, arrow=""):
        bg  = "rgba(45,143,111,.15)" if is_live else "transparent"
        bdr = f"1px solid {BORDER_T}" if is_live else f"1px solid {BORDER}"
        return html.Div([
            html.Div([
                html.Span(arrow+" " if arrow else "",
                          style={"color":color,"fontWeight":"900","fontSize":"11px","marginRight":"2px"}),
                html.Span(label,
                          style={"fontSize":"11px","fontWeight":"700","color":WHITE,
                                 "textTransform":"uppercase","letterSpacing":".08em"}),
            ], style={"flex":"1"}),
            html.Span(f"${level:.2f}",
                      style={"fontSize":"16px","fontWeight":"900","color":WHITE,
                             "fontFamily":"DM Mono, monospace"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"9px 12px","borderRadius":"10px","marginBottom":"5px",
                   "background":bg,"border":bdr})

    # ── LEFT: Price Ladder ────────────────────────────────────────────────────
    price_ladder = html.Div([
        card([
            slabel("Price Ladder"),
            level_row("Breakout",  kl.breakout,   TEAL_DIM,  arrow="▲"),
            level_row("Liquidity", kl.prior_high, TEAL_DIM,  arrow="▲"),
            level_row("Expansion", kl.expansion,  TEAL_DIM,  arrow="▲"),
            html.Div(style={"height":"3px","background":BORDER,"borderRadius":"2px","margin":"5px 0"}),
            level_row("Live Price",price,          BLUE_DIM,  is_live=True),
            html.Div(style={"height":"3px","background":BORDER,"borderRadius":"2px","margin":"5px 0"}),
            level_row("Trigger",   kl.trigger,    YELLOW_DIM,arrow="▼"),
            level_row("Trap Door", kl.trap,       RED_DIM,   arrow="▼"),
            level_row("Fail Gate", kl.fail,       RED_DIM,   arrow="▼"),
            html.Div(style={"flex":"1"}),  # pushes Distance to bottom
            html.Hr(style={"border":"none","borderTop":f"1px solid {BORDER}","margin":"0 0 12px"}),
            slabel("Distance"),
            html.Div([
                html.Div([
                    html.Span("↑ Breakout",style={"fontSize":"13px","color":WHITE,"fontWeight":"600"}),
                    html.Span(f"+{((kl.breakout-price)/price*100):.2f}%",
                              style={"fontSize":"14px","color":TEAL_DIM,"fontWeight":"900"}),
                ], style={"display":"flex","justifyContent":"space-between","marginBottom":"8px"}),
                html.Div([
                    html.Span("↓ Fail Gate",style={"fontSize":"13px","color":WHITE,"fontWeight":"600"}),
                    html.Span(f"-{((price-kl.fail)/price*100):.2f}%",
                              style={"fontSize":"14px","color":RED_DIM,"fontWeight":"900"}),
                ], style={"display":"flex","justifyContent":"space-between","marginBottom":"8px"}),
                html.Div([
                    html.Span("R/R Ratio",style={"fontSize":"13px","color":WHITE,"fontWeight":"600"}),
                    html.Span(f"{((kl.breakout-price)/(price-kl.fail)):.1f}x" if price>kl.fail else "—",
                              style={"fontSize":"14px","color":YELLOW_DIM,"fontWeight":"900"}),
                ], style={"display":"flex","justifyContent":"space-between"}),
            ], style={"background":"rgba(0,0,0,.2)","borderRadius":"10px","padding":"14px",
                       "border":f"1px solid {BORDER}"}),
        ], sx={"flex":"1","display":"flex","flexDirection":"column"}),
    ], style={"flex":"0 0 230px","minWidth":"0","display":"flex","flexDirection":"column"})

    # ── CENTER: Chart — fills the card tile completely ────────────────────────
    chart_panel = card([
        # Header row
        html.Div([
            html.Div([
                html.Span(f"{symbol}  ·  Smart Chart",
                          style={"fontSize":"13px","fontWeight":"800","color":WHITE}),
                html.Span(f"  {live_age}  ·  {tf}  ·  {regime.replace('_',' ').title()}",
                          style={"fontSize":"10px","color":WHITE}),
            ]),
            html.Span(f"${price:.2f}",
                      style={"fontSize":"14px","fontWeight":"900","color":WHITE,
                             "fontFamily":"DM Mono, monospace"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "marginBottom":"6px"}),

        # Chart — fills remaining space
        html.Div(
            dcc.Graph(figure=fig,
                      config={"displayModeBar":False,"scrollZoom":True,"displaylogo":False},
                      style={"height":"100%"}),
            style={"flex":"1","margin":"0 -20px -8px -20px","overflow":"hidden"},
        ),

        # Footer — aligned with Distance box at bottom of price ladder
        html.Div([
            html.Span(f"{tf}  ·  {len(candles)} candles",
                      style={"fontSize":"13px","color":WHITE,"fontWeight":"700",
                             "fontFamily":"DM Mono, monospace"}),
            html.Span(f"Vol {live['volume']:,}",
                      style={"fontSize":"13px","color":WHITE,"fontWeight":"700",
                             "fontFamily":"DM Mono, monospace"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                   "padding":"8px 0 0 0","borderTop":f"1px solid {BORDER}","marginTop":"4px"}),

    ], sx={"flex":"1","minWidth":"0","padding":"16px 20px 12px 20px",
            "overflow":"hidden","display":"flex","flexDirection":"column"})

    # ── Row 1 ─────────────────────────────────────────────────────────────────
    row1 = html.Div([price_ladder, chart_panel],
                    style={"display":"flex","gap":"16px","marginBottom":"16px",
                           "alignItems":"stretch"})

    # ── Row 2: Decision Engine + Trade Card + Probability Ladder (ONE card) ──
    row2 = card([
        html.Div([

            # Column A — Direction & Confidence Panel
            html.Div([
                build_direction_panel(decision, score),
            ], style={"flex":"1.2","minWidth":"160px",
                       "borderRight":f"1px solid {BORDER}","paddingRight":"16px"}),

            # Column B — Trade Card
            html.Div([
                slabel("Trade Card"),
                html.Div(style={"height":"6px"}),
                html.Div([
                    html.Span("Bias  ",style={"fontSize":"10px","color":WHITE,"fontWeight":"700",
                                              "textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Span(decision["bias"],style={"fontSize":"13px","fontWeight":"900","color":sc}),
                ], style={"marginBottom":"8px"}),
                html.Div([
                    html.Span("Setup  ",style={"fontSize":"10px","color":WHITE,"fontWeight":"700",
                                               "textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Span(decision["status"],style={"fontSize":"13px","fontWeight":"900","color":sc}),
                ], style={"marginBottom":"8px"}),
                html.Div([
                    html.Span("Size  ",style={"fontSize":"10px","color":WHITE,"fontWeight":"700",
                                              "textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Span(size,style={"fontSize":"22px","fontWeight":"900","color":sc}),
                ], style={"marginBottom":"10px"}),
                note_box(f"Ref: ${price:.2f}  ·  A-grade requires live-volume expansion.","yellow"),
            ], style={"flex":"1","minWidth":"140px",
                       "borderRight":f"1px solid {BORDER}","padding":"0 16px"}),

            # Column C — Probability Ladder
            html.Div([
                slabel("Probability Ladder"),
                html.Div(style={"height":"6px"}),
                brow("Upside Expansion", nodes[0]["score"] if nodes else 63, "up"),
                html.P(f"Level ${nodes[0]['level']:.2f}" if nodes else "",
                       style={"fontSize":"9px","color":WHITE,"marginTop":"-3px","marginBottom":"6px"}),
                brow("Liquidity Retest", nodes[1]["score"] if len(nodes)>1 else 60, "up"),
                html.P(f"Level ${nodes[1]['level']:.2f}" if len(nodes)>1 else "",
                       style={"fontSize":"9px","color":WHITE,"marginTop":"-3px","marginBottom":"6px"}),
                brow("Hold / Balance", score, "neutral"),
                html.P(f"Level ${kl.confirm:.2f}",
                       style={"fontSize":"9px","color":WHITE,"marginTop":"-3px","marginBottom":"6px"}),
                brow("Failure Gate", 100-score, "down"),
                html.P(f"Level ${kl.fail:.2f}",
                       style={"fontSize":"9px","color":WHITE,"marginTop":"-3px"}),
            ], style={"flex":"1.5","minWidth":"180px","paddingLeft":"16px"}),

        ], style={"display":"flex","gap":"0","alignItems":"flex-start","flexWrap":"wrap"}),
    ], sx={"marginBottom":"16px"})

    # ── Row 3: Options Matrix ─────────────────────────────────────────────────
    row3 = card([
        html.Div([
            html.Div([
                html.H2("Dynamic Options Matrix + Flow Map",
                        style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                html.P("Synthetic intelligence from price, volume, volatility proxy, and decision score.",
                       style={"fontSize":"12px","color":WHITE})]),
            badge(fb,"blue"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                   "flexWrap":"wrap","gap":"10px","marginBottom":"14px"}),
        html.Div([
            zcard("Call Wall",   f"${round(kl.breakout):.0f}",  f"{cp}% call-side pressure", TEAL_DIM),
            zcard("Put Wall",    f"${round(kl.fail):.0f}",     f"{pp}% put-side pressure",  RED_DIM),
            zcard("Gamma Pivot", f"${round(kl.confirm):.0f}",  f"{gp}% dealer sensitivity", YELLOW_DIM),
            zcard("Vol Trigger", "LIVE",                        f"{vs}% expansion energy",   TEAL_DIM),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"12px"}),
        note_box("Synthetic options layer — connect Tradier or CBOE for live institutional flow data.","blue"),
    ], sx={"marginBottom":"16px"})

    # ── Row 4: Time Engine + Alerts + Footer ──────────────────────────────────
    # Clock with white text
    EST = timezone(timedelta(hours=-4)); now = datetime.now(EST)
    minutes = now.hour*60+now.minute; in_sess = 570<=minutes<=960
    phase = ("Outside RTH" if not in_sess else "Opening Drive" if minutes<630
             else "Midday Auction" if minutes<840 else "Closing Auction")
    phase_color = TEAL_DIM if in_sess else MUTED

    row4 = html.Div([
        card([
            html.H2("️ Time Engine",
                    style={"fontSize":"14px","fontWeight":"800","color":WHITE,"margin":"0 0 12px"}),
            html.Div(now.strftime("%I:%M:%S %p")+" ET",
                     style={"fontSize":"22px","fontWeight":"900","color":WHITE,
                            "fontFamily":"DM Mono, monospace","marginBottom":"8px"}),
            html.Div(phase,
                     style={"fontSize":"13px","fontWeight":"800","color":phase_color,"marginBottom":"8px"}),
            note_box("Future: economic releases, auction windows, proprietary cycle layers."),
        ], sx={"flex":"1"}),

        card([
            html.Div([
                html.H2("Visual + Audio Alerts",
                        style={"fontSize":"14px","fontWeight":"800","color":WHITE,"margin":"0"}),
                html.Button("ON", id="btn-alerts-toggle", n_clicks=0,
                    style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
                           "borderRadius":"20px","padding":"4px 12px","fontSize":"11px",
                           "fontWeight":"800","cursor":"pointer"}),
            ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"12px"}),
            html.Div(as_, style={
                "borderRadius":"12px","padding":"12px","textAlign":"center","fontWeight":"900",
                "fontSize":"12px","letterSpacing":".06em","textTransform":"uppercase",
                **({"border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM} if aa
                   else {"border":"1px solid rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":YELLOW_DIM}),
            }),
            html.Div([
                html.Span(f"Score: {score}",
                          style={"fontSize":"11px","color":WHITE,"marginTop":"8px","display":"block","fontWeight":"700"}),
                html.Span(
                    "Trap Door" if score<35 else
                    ("A-Grade — Audio Active" if score>=80 else
                     "B-Grade — Audio Active" if score>=55 else "Monitoring"),
                    style={"fontSize":"11px","fontWeight":"700","marginTop":"3px","display":"block",
                           "color":RED_DIM if score<35 else (TEAL_DIM if score>=55 else MUTED)}),
            ]),
        ], sx={"flex":"1"}),

        card([html.Div([
            metric_tile("Symbol",       symbol,                           WHITE),
            metric_tile("Live Price",   f"${price:.2f}",                 WHITE),
            metric_tile("Engine Score", f"{score}%",                     sc),
            metric_tile("Regime",       regime.replace("_"," ").title(), YELLOW_DIM),
        ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"10px"})], sx={"flex":"1"}),

    ], style={**ROW,"alignItems":"start","marginBottom":"16px"})

    return html.Div([row1, row2, row3, row4],
                    style={"display":"flex","flexDirection":"column"})


def build_feed_tab(live, live_mode):
    price = live["price"]
    return card([
        html.Div([
            html.Div([html.H2("Live Feed Monitor",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 4px"}),
                      html.P(f"Backend: {BACKEND_HTTP}",style={"fontSize":"12px","color":WHITE})]),
            badge("Connected", "teal"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start","marginBottom":"16px"}),
        html.Div([
            metric_tile("Feed Mode","Live Alpaca"),
            metric_tile("Symbol",live["symbol"]),
            metric_tile("Price",f"${price:.2f}",TEAL_DIM),
            metric_tile("Volume",f"{live['volume']:,}"),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"16px"}),
        html.Pre(json.dumps(live,indent=2),style={"margin":"0","maxHeight":"460px","overflow":"auto","borderRadius":"14px",
            "border":f"1px solid {BORDER}","background":"rgba(0,0,0,.35)","padding":"16px",
            "color":TEAL_DIM,"fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.6"}),
    ])

def build_performance_tab(live):
    price=live["price"]; decision=live["decision"]; score=decision["score"]
    sc=TEAL_DIM if score>=70 else (YELLOW_DIM if score>=45 else RED_DIM)
    return card([
        html.H2("Performance Logger",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Div([
            metric_tile("Current Price",f"${price:.2f}",TEAL_DIM),
            metric_tile("Setup",decision["status"],sc),
            metric_tile("Score",f"{score}%",sc),
            metric_tile("Bias",decision["bias"],BLUE_DIM),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"14px"}),
        note_box("Trade logging reconnects automatically once live feed stabilizes."),
    ])

def build_stub_tab(title, description):
    """Placeholder for tabs under development."""
    return card([
        html.H2(title, style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"12px"}),
        note_box(description, "blue"),
        html.Div(style={"height":"12px"}),
        note_box("This feature is under active development and will be available in an upcoming release.", "yellow"),
    ])


# ═══════════════════════════════════════════════════════════════════════════════
# REAL TAB FUNCTIONS — injected from source files
# ═══════════════════════════════════════════════════════════════════════════════

def build_radar_tab(session=None):
    """Opportunity Dashboard — behavioral transition radar."""
    import requests as _rq

    try:
        def _do_fetch_radar():
            r = _rq.get(f"{BACKEND_HTTP}/api/radar/scores", timeout=15)
            return r.json() if r.ok else {}

        data = (
            shared_cache.get_or_fetch("/api/radar/scores", _do_fetch_radar, ttl_seconds=90)
            if shared_cache is not None
            else _do_fetch_radar()
        )

        if isinstance(data, list):
            signals = data
            sort_mode = "local"
            last_scan = None
            data_delay = "—"
        else:
            signals = (
                data.get("symbols")
                or data.get("signals")
                or data.get("scores")
                or data.get("results")
                or data.get("data")
                or data.get("radar")
                or []
            )
            sort_mode = data.get("sort_mode", "—")
            last_scan = data.get("last_scan")
            data_delay = data.get("data_delay", "—")

    except Exception as e:
        print(f"Radar fetch error: {e}")
        signals = []
        sort_mode = "error"
        last_scan = None
        data_delay = "—"

    def _safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    def _safe_text(value, default="—"):
        if value is None or value == "":
            return default
        return str(value)

    def _fmt_money(value):
        try:
            if value is None or value == "":
                return "—"
            return f"${float(value):,.2f}"
        except Exception:
            return "—"

    def _fmt_pct(value, digits=1, signed=False):
        try:
            if value is None or value == "":
                return "—"
            v = float(value)
            sign = "+" if signed and v > 0 else ""
            return f"{sign}{v:.{digits}f}%"
        except Exception:
            return "—"

    def _state_color(state, score=0):
        st = (state or "").lower()
        if "armed" in st:
            return TEAL_DIM
        if "setting" in st:
            return BLUE_DIM
        if "triggered" in st:
            return YELLOW_DIM
        if "avoid" in st or "reject" in st:
            return RED_DIM
        if score >= 80:
            return TEAL_DIM
        if score >= 70:
            return YELLOW_DIM
        return MUTED

    def _side_color(side):
        sd = (side or "").lower()
        if "short" in sd:
            return RED_DIM
        if "long" in sd:
            return TEAL_DIM
        return MUTED

    def _readiness_label(score):
        if score >= 90:
            return "Elite"
        if score >= 80:
            return "High"
        if score >= 70:
            return "Qualified"
        if score >= 60:
            return "Developing"
        return "Low"

    def _compact_transition(text):
        t = _safe_text(text)
        return t.replace(" to ", " → ").replace(" / ", " / ")

    def _opportunity_card(s, rank):
        symbol = _safe_text(s.get("symbol"), "")
        price = s.get("price")
        chg = _safe_float(s.get("change_pct"))
        score = _safe_float(s.get("composite_score", s.get("score")))
        readiness = _safe_float(s.get("readiness_score"))
        state = _safe_text(s.get("opportunity_state"), "Watching")
        transition = _compact_transition(s.get("transition_candidate"))
        behavioral_state = _safe_text(s.get("behavioral_state"), "—")
        side = _safe_text(s.get("trade_side"), _safe_text(s.get("side"), "—"))
        trigger = s.get("trigger")
        invalidation = s.get("invalidation")
        why = _safe_text(s.get("why_this_trade"), "Awaiting more evidence.")
        evidence = s.get("evidence") if isinstance(s.get("evidence"), list) else []
        risk_notes = s.get("risk_notes") if isinstance(s.get("risk_notes"), list) else []
        setup = _safe_text(s.get("setup_type"), "—")
        regime = _safe_text(s.get("regime"), "—")
        status = _safe_text(s.get("status"), "—")
        alert_type = _safe_text(s.get("alert_type"), "—")

        # Historical probability / edge fields from backend probability engine
        hist_success = _safe_float(s.get("historical_success", s.get("historical_success_rate")))
        hist_matches = _safe_float(s.get("historical_matches"))
        exp_return = _safe_float(s.get("expected_return", s.get("historical_expected_return")))
        edge_ratio = _safe_float(s.get("edge_ratio", s.get("historical_edge_ratio")))
        prob_grade = _safe_text(s.get("probability_grade", s.get("historical_grade")), "Unrated")
        prob_conf = _safe_text(s.get("probability_confidence", s.get("historical_confidence")), "—")
        prob_score = _safe_float(s.get("expected_opportunity_score"))
        edge_score = _safe_float(s.get("edge_score", prob_score))
        prob_setup = _safe_text(s.get("probability_setup_type", setup), setup)
        prob_weekly = _safe_text(s.get("probability_weekly_regime", s.get("weekly_regime", "—")), "—")
        grade_color = TEAL_DIM if str(prob_grade).startswith("A") else (BLUE_DIM if str(prob_grade).startswith("B") else (YELLOW_DIM if str(prob_grade).startswith("C") else RED_DIM))

        color = _state_color(state, readiness)
        side_color = _side_color(side)

        return html.Div([
            html.Div([
                html.Div([
                    html.Div(f"#{rank}", style={
                        "fontSize":"10px","fontWeight":"900","color":WHITE,
                        "textTransform":"uppercase","letterSpacing":".08em"
                    }),
                    html.Div(symbol, style={
                        "fontSize":"24px","fontWeight":"950","color":WHITE,
                        "fontFamily":"DM Mono, monospace","lineHeight":"1"
                    }),
                    html.Div(f"{_fmt_money(price)} · {_fmt_pct(chg, 2, signed=True)}", style={
                        "fontSize":"11px","fontWeight":"800",
                        "color":TEAL_DIM if chg >= 0 else RED_DIM,
                        "marginTop":"5px"
                    }),
                ], style={"flex":"1"}),

                html.Div([
                    html.Div(prob_grade, style={
                        "fontSize":"30px","fontWeight":"950","color":grade_color,
                        "lineHeight":"1","textAlign":"right"
                    }),
                    html.Div("Opportunity", style={
                        "fontSize":"10px","fontWeight":"950","color":WHITE,
                        "textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"
                    }),
                    html.Div(f"Ready {readiness:.0f}", style={
                        "fontSize":"10px","fontWeight":"900","color":color,
                        "textAlign":"right","marginTop":"4px"
                    }),
                ]),
            ], style={"display":"flex","alignItems":"flex-start","gap":"12px"}),

            html.Div(style={"height":"12px"}),

            html.Div([
                html.Span(state, style={
                    "display":"inline-block","padding":"5px 9px",
                    "borderRadius":"999px","background":"rgba(255,255,255,.06)",
                    "border":f"1px solid {color}","color":color,
                    "fontSize":"10px","fontWeight":"900","textTransform":"uppercase",
                    "letterSpacing":".08em","marginRight":"6px"
                }),
                html.Span(side, style={
                    "display":"inline-block","padding":"5px 9px",
                    "borderRadius":"999px","background":"rgba(255,255,255,.04)",
                    "border":f"1px solid {side_color}","color":side_color,
                    "fontSize":"10px","fontWeight":"900","textTransform":"uppercase",
                    "letterSpacing":".08em","marginRight":"6px"
                }),
                html.Span(alert_type, style={
                    "display":"inline-block","padding":"5px 9px",
                    "borderRadius":"999px","background":"rgba(255,255,255,.04)",
                    "border":f"1px solid {BORDER}","color":WHITE,
                    "fontSize":"10px","fontWeight":"800"
                }),
            ]),

            html.Div(style={"height":"12px"}),

            html.Div([
                html.Div([
                    html.Div("Probability", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(_fmt_pct(hist_success, 1), style={"fontSize":"18px","fontWeight":"950","color":TEAL_DIM if hist_success >= 55 else YELLOW_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Edge Ratio", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(f"{edge_ratio:.2f}", style={"fontSize":"18px","fontWeight":"950","color":TEAL_DIM if edge_ratio >= 1.2 else YELLOW_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Expected Return", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(_fmt_pct(exp_return, 2, signed=True), style={"fontSize":"18px","fontWeight":"950","color":TEAL_DIM if exp_return >= 0 else RED_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Grade", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(prob_grade, style={"fontSize":"18px","fontWeight":"950","color":grade_color}),
                ], style={"flex":"1"}),
            ], style={"display":"flex","gap":"10px","padding":"10px","border":f"1px solid {BORDER}","borderRadius":"12px","background":"rgba(255,255,255,.035)"}),

            html.Div([
                html.Span(f"Matches {hist_matches:,.0f}", style={"fontSize":"11px","fontWeight":"850","color":WHITE,"marginRight":"10px"}),
                html.Span(f"Confidence {prob_conf}", style={"fontSize":"11px","fontWeight":"850","color":WHITE,"marginRight":"10px"}),
                html.Span(prob_weekly, style={"fontSize":"11px","fontWeight":"850","color":WHITE}),
            ], style={"marginTop":"7px"}),

            html.Div(style={"height":"12px"}),

            html.Div("Behavioral Transition", style={
                "fontSize":"10px","fontWeight":"950","color":WHITE,
                "textTransform":"uppercase","letterSpacing":".08em","marginBottom":"4px"
            }),
            html.Div(transition, style={
                "fontSize":"14px","fontWeight":"900","color":WHITE,
                "lineHeight":"1.25","minHeight":"34px"
            }),
            html.Div(behavioral_state, style={
                "fontSize":"12px","fontWeight":"900","color":WHITE,
                "marginTop":"4px"
            }),

            html.Div(style={"height":"12px"}),

            html.Div([
                html.Div([
                    html.Div("Trigger", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(_fmt_money(trigger), style={"fontSize":"13px","fontWeight":"900","color":TEAL_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Invalid", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(_fmt_money(invalidation), style={"fontSize":"13px","fontWeight":"900","color":RED_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Score", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(f"{score:.0f}", style={"fontSize":"13px","fontWeight":"900","color":YELLOW_DIM}),
                ], style={"flex":"1"}),
            ], style={"display":"flex","gap":"10px"}),

            html.Div(style={"height":"12px"}),

            html.Div("Why This Trade?", style={
                "fontSize":"10px","fontWeight":"950","color":WHITE,
                "textTransform":"uppercase","letterSpacing":".08em","marginBottom":"6px"
            }),
            html.Div(why, style={
                "fontSize":"12px","color":WHITE,"fontWeight":"850","lineHeight":"1.45",
                "minHeight":"44px"
            }),

            html.Div(style={"height":"10px"}),

            html.Div([
                html.Div("Setup", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                html.Div(prob_setup, style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"800"}),
                html.Div(f"{status} · {regime}", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850","marginTop":"3px"}),
            ]),

            html.Div([
                html.Div("Evidence", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em","marginTop":"10px","marginBottom":"4px"}),
                html.Div([
                    html.Div(f"{e}", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850","lineHeight":"1.35","marginBottom":"3px"})
                    for e in evidence[:4]
                ] if evidence else [
                    html.Div("No evidence details returned yet.", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850"})
                ]),
            ]),

            html.Div([
                html.Div("Risk Notes", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em","marginTop":"8px","marginBottom":"4px"}),
                html.Div([
                    html.Div(f"{r}", style={"fontSize":"12px","color":YELLOW_DIM,"fontWeight":"900","lineHeight":"1.45","marginBottom":"4px"})
                    for r in risk_notes[:3]
                ] if risk_notes else [
                    html.Div("Risk defined by setup invalidation.", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850"})
                ]),
            ]),
        ], style={
            "border":f"1px solid {color}",
            "background":"linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.025))",
            "borderRadius":"18px",
            "padding":"16px",
            "boxShadow":"0 18px 42px rgba(0,0,0,.22)",
            "minHeight":"430px"
        })

    def _row(s):
        symbol = _safe_text(s.get("symbol"), "")
        score = _safe_float(s.get("composite_score", s.get("score")))
        readiness = _safe_float(s.get("readiness_score"))
        state = _safe_text(s.get("opportunity_state"), "Watching")
        transition = _compact_transition(s.get("transition_candidate"))
        behavioral_state = _safe_text(s.get("behavioral_state"), "—")
        side = _safe_text(s.get("trade_side"), _safe_text(s.get("side"), "—"))
        chg = _safe_float(s.get("change_pct"))
        price = s.get("price")
        trigger = s.get("trigger")
        invalidation = s.get("invalidation")
        setup = _safe_text(s.get("probability_setup_type", s.get("setup_type")), "—")
        status = _safe_text(s.get("status"), "—")
        hist_success = _safe_float(s.get("historical_success", s.get("historical_success_rate")))
        exp_return = _safe_float(s.get("expected_return", s.get("historical_expected_return")))
        edge_ratio = _safe_float(s.get("edge_ratio", s.get("historical_edge_ratio")))
        prob_grade = _safe_text(s.get("probability_grade", s.get("historical_grade")), "—")
        color = _state_color(state, readiness)
        side_color = _side_color(side)
        grade_color = TEAL_DIM if str(prob_grade).startswith("A") else (BLUE_DIM if str(prob_grade).startswith("B") else (YELLOW_DIM if str(prob_grade).startswith("C") else RED_DIM))

        return html.Div([
            html.Span(symbol, style={
                "flex":"0 0 72px","fontWeight":"950","fontSize":"13px",
                "color":WHITE,"fontFamily":"DM Mono, monospace"
            }),
            html.Span(_fmt_money(price), style={"flex":"0 0 92px","fontSize":"12px","fontWeight":"800","color":WHITE}),
            html.Span(_fmt_pct(chg, 2, signed=True), style={
                "flex":"0 0 74px","fontSize":"12px","fontWeight":"900",
                "color":TEAL_DIM if chg >= 0 else RED_DIM
            }),
            html.Span(f"{readiness:.0f}", style={
                "flex":"0 0 72px","fontSize":"14px","fontWeight":"950",
                "color":color,"textAlign":"center"
            }),
            html.Span(f"{score:.0f}", style={
                "flex":"0 0 58px","fontSize":"12px","fontWeight":"900",
                "color":YELLOW_DIM,"textAlign":"center"
            }),
            html.Span(prob_grade, style={
                "flex":"0 0 62px","fontSize":"12px","fontWeight":"950",
                "color":grade_color,"textAlign":"center"
            }),
            html.Span(_fmt_pct(hist_success, 1), style={
                "flex":"0 0 86px","fontSize":"12px","fontWeight":"900",
                "color":WHITE,"textAlign":"center"
            }),
            html.Span(_fmt_pct(exp_return, 2, signed=True), style={
                "flex":"0 0 92px","fontSize":"12px","fontWeight":"900",
                "color":TEAL_DIM if exp_return >= 0 else RED_DIM,"textAlign":"center"
            }),
            html.Span(f"{edge_ratio:.2f}", style={
                "flex":"0 0 72px","fontSize":"12px","fontWeight":"900",
                "color":YELLOW_DIM,"textAlign":"center"
            }),
            html.Span(state, style={
                "flex":"0 0 100px","fontSize":"10px","fontWeight":"950",
                "color":color,"textTransform":"uppercase","textAlign":"center"
            }),
            html.Span(side, style={
                "flex":"0 0 58px","fontSize":"10px","fontWeight":"950",
                "color":side_color,"textTransform":"uppercase","textAlign":"center"
            }),
            html.Span(transition, style={
                "flex":"1.4","fontSize":"11px","fontWeight":"850",
                "color":WHITE,"minWidth":"190px"
            }),
            html.Span(behavioral_state, style={
                "flex":"1.2","fontSize":"10px","fontWeight":"750",
                "color":BLUE_DIM,"minWidth":"160px"
            }),
            html.Span(setup, style={
                "flex":"1.1","fontSize":"10px","fontWeight":"750",
                "color":WHITE,"minWidth":"160px"
            }),
            html.Span(status, style={
                "flex":"0 0 82px","fontSize":"10px","fontWeight":"850",
                "color":WHITE,"textAlign":"center"
            }),
            html.Span(_fmt_money(trigger), style={
                "flex":"0 0 86px","fontSize":"10px","fontWeight":"900",
                "color":TEAL_DIM,"textAlign":"right"
            }),
            html.Span(_fmt_money(invalidation), style={
                "flex":"0 0 86px","fontSize":"10px","fontWeight":"900",
                "color":RED_DIM,"textAlign":"right"
            }),
        ], style={
            "display":"flex","alignItems":"center","gap":"10px",
            "padding":"11px 0","borderBottom":f"1px solid {BORDER}",
            "minWidth":"1630px"
        })

    header = html.Div([
        html.Span("Symbol", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em"}),
        html.Span("Price", style={"flex":"0 0 92px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em"}),
        html.Span("Chg%", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em"}),
        html.Span("Ready", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Score", style={"flex":"0 0 58px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Grade", style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Hist %", style={"flex":"0 0 86px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Exp Ret", style={"flex":"0 0 92px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Edge", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("State", style={"flex":"0 0 100px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Side", style={"flex":"0 0 58px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Transition", style={"flex":"1.4","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","minWidth":"190px"}),
        html.Span("Behavior", style={"flex":"1.2","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","minWidth":"160px"}),
        html.Span("Setup", style={"flex":"1.1","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","minWidth":"160px"}),
        html.Span("Status", style={"flex":"0 0 82px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Trigger", style={"flex":"0 0 86px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"}),
        html.Span("Invalid", style={"flex":"0 0 86px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"}),
    ], style={
        "display":"flex","gap":"10px","paddingBottom":"8px",
        "borderBottom":f"1px solid {BORDER}","marginBottom":"4px",
        "minWidth":"1630px"
    })

    # Backend already sorts by opportunity state and readiness. Keep first 3 as hero cards.
    hero = signals[:3] if isinstance(signals, list) else []
    armed_count = sum(1 for s in signals if _safe_text(s.get("opportunity_state")).lower() == "armed")
    setup_count = sum(1 for s in signals if "setting" in _safe_text(s.get("opportunity_state")).lower())
    elite_count = sum(1 for s in signals if _safe_float(s.get("readiness_score")) >= 90)
    avg_ready = sum(_safe_float(s.get("readiness_score")) for s in signals) / max(len(signals), 1)

    return html.Div([
        card([
            html.Div([
                html.Div([
                    html.H2("Opportunity Dashboard", style={
                        "color":WHITE,"fontSize":"20px","fontWeight":"950","margin":"0 0 4px"
                    }),
                    html.P("Pre-trigger trade discovery — ranked by opportunity state, readiness, and behavioral transition.",
                           style={"color":WHITE,"fontSize":"13px","margin":"0"}),
                ]),
                html.Div([
                    html.Div(f"{len(signals)}", style={"fontSize":"20px","fontWeight":"950","color":WHITE,"textAlign":"right"}),
                    html.Div("Candidates", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"}),
                ]),
            ], style={"display":"flex","justifyContent":"space-between","gap":"14px","alignItems":"flex-start","marginBottom":"16px"}),

            html.Div([
                metric_tile("Armed", armed_count, "pre-trigger candidates", "green"),
                metric_tile("Setting Up", setup_count, "forming opportunities", "blue"),
                metric_tile("Elite 90+", elite_count, "highest readiness", "yellow"),
                metric_tile("Avg Ready", f"{avg_ready:.0f}", f"sort: {sort_mode}", "purple"),
            ], style={"display":"grid","gridTemplateColumns":"repeat(4, 1fr)","gap":"12px","marginBottom":"18px"}),

            html.Div([
                html.H3("Top Opportunities", style={
                    "color":WHITE,"fontSize":"15px","fontWeight":"950","margin":"0 0 10px"
                }),
                html.Div([
                    _opportunity_card(s, i+1) for i, s in enumerate(hero)
                ] if hero else [
                    html.Div("No opportunities returned yet.", style={"color":WHITE,"fontSize":"13px","padding":"18px"})
                ], style={"display":"grid","gridTemplateColumns":"repeat(3, 1fr)","gap":"14px"}),
            ]),

            html.Div(style={"height":"20px"}),

            html.Div([
                html.H3("Full Opportunity Radar", style={
                    "color":WHITE,"fontSize":"15px","fontWeight":"950","margin":"0 0 4px"
                }),
                html.Div("Sorted by Armed → Setting Up → Historical Probability → Readiness. Use this table to see what may move next, not what already moved.",
                         style={"fontSize":"12px","color":WHITE,"fontWeight":"850","marginBottom":"12px"}),
                html.Div([
                    header,
                    html.Div([_row(s) for s in signals] if signals else [
                        html.Div("No signals available. Backend may be initializing or market is closed.",
                                 style={"color":WHITE,"fontSize":"13px","padding":"24px 0","textAlign":"center"})
                    ]),
                ], style={"overflowX":"auto"}),
            ]),
        ]),
    ])

def build_scoreboard_tab(session=None):
    """Scoreboard — live outcome analytics from /api/scoreboard."""
    import requests as _rq

    try:
        def _do_fetch_scoreboard():
            r = _rq.get(f"{BACKEND_HTTP}/api/scoreboard", timeout=15)
            return r.json() if r.ok else {}

        board = (
            shared_cache.get_or_fetch("/api/scoreboard", _do_fetch_scoreboard, ttl_seconds=120)
            if shared_cache is not None
            else _do_fetch_scoreboard()
        )
    except Exception:
        board = {}

    entries = board.get("recent_signals", [])
    if not isinstance(entries, list):
        entries = []

    agreement_buckets = board.get("agreement_buckets", [])
    if not isinstance(agreement_buckets, list):
        agreement_buckets = []

    agreement_thresholds = board.get("agreement_thresholds", [])
    if not isinstance(agreement_thresholds, list):
        agreement_thresholds = []

    attribution_report = board.get("attribution_report", {})
    if not isinstance(attribution_report, dict):
        attribution_report = {}

    generated = datetime.now(timezone(timedelta(hours=-4))).strftime("%b %d, %Y %I:%M %p ET")

    def _safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    def _safe_int(value, default=0):
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except Exception:
            return default

    def _fmt_pct(value, digits=1, signed=False):
        if value is None or value == "":
            return "—"
        try:
            v = float(value)
            sign = "+" if signed and v > 0 else ""
            return f"{sign}{v:.{digits}f}%"
        except Exception:
            return "—"

    def _fmt_money(value):
        if value is None or value == "":
            return "—"
        try:
            return f"${float(value):,.2f}"
        except Exception:
            return "—"

    total_signals = _safe_int(board.get("total_signals"))
    with_outcomes = _safe_int(board.get("with_outcomes"))
    pending_outcomes = _safe_int(board.get("pending_outcomes"))
    direction_evaluated = _safe_int(board.get("direction_evaluated"))
    direction_correct_rate = _safe_float(board.get("direction_correct_rate"))
    avg_mfe_pct = _safe_float(board.get("avg_mfe_pct"))
    avg_mae_pct = _safe_float(board.get("avg_mae_pct"))
    edge_ratio = _safe_float(board.get("edge_ratio"))
    hit_target1_rate = _safe_float(board.get("hit_target1_rate"))
    hit_target2_rate = _safe_float(board.get("hit_target2_rate"))
    outcome_window_hours = _safe_int(board.get("outcome_window_hours"))

    def _metric(label, value, color=WHITE, sub=None):
        return html.Div([
            html.Div(label, style={
                "fontSize":"10px","color":WHITE,"fontWeight":"800",
                "textTransform":"uppercase","letterSpacing":".12em",
                "marginBottom":"5px"
            }),
            html.Div(value, style={
                "fontSize":"22px","fontWeight":"900","color":color,
                "fontFamily":"DM Mono, monospace" if any(ch.isdigit() for ch in str(value)) else "inherit"
            }),
            html.Div(sub or "", style={
                "fontSize":"10px","color":WHITE,"marginTop":"3px",
                "minHeight":"14px"
            }),
        ], style={
            "background":"rgba(0,0,0,.22)",
            "border":f"1px solid {BORDER}",
            "borderRadius":"14px",
            "padding":"14px 16px",
            "minHeight":"86px"
        })

    def _entry_row(e, rank):
        symbol = e.get("symbol", "—")
        signal_type = e.get("signal_type", e.get("status", "—"))
        score = _safe_float(e.get("score", e.get("composite_score", 0)))
        setup_type = e.get("setup_type", "—")
        regime = e.get("regime", "—")
        grade = str(e.get("grade", "—") or "—")
        entry_price = e.get("entry_price", e.get("price"))
        outcome_pct = e.get("outcome_pct")
        mfe_pct = e.get("mfe_pct")
        mae_pct = e.get("mae_pct")
        direction_correct = e.get("direction_correct")
        hit_t1 = e.get("hit_t1")
        hit_t2 = e.get("hit_t2")
        agreement_score = e.get("agreement_score")
        intelligence_delta = e.get("intelligence_delta")
        agreement_bucket = e.get("agreement_bucket") or "—"
        delta_quality_label = e.get("delta_quality_label") or "—"
        delta_action = e.get("delta_action") or "—"

        score_color = TEAL_DIM if score >= 75 else (YELLOW_DIM if score >= 60 else RED_DIM)
        grade_color = (
            TEAL_DIM if grade.startswith("A")
            else BLUE_DIM if grade.startswith("B")
            else YELLOW_DIM if grade.startswith("C")
            else RED_DIM if grade.startswith(("W", "F"))
            else MUTED
        )

        if outcome_pct is None or outcome_pct == "":
            outcome_color = MUTED
        else:
            outcome_color = TEAL_DIM if _safe_float(outcome_pct) >= 0 else RED_DIM

        if direction_correct is True:
            dir_text, dir_color = "", TEAL_DIM
        elif direction_correct is False:
            dir_text, dir_color = "", RED_DIM
        else:
            dir_text, dir_color = "—", MUTED

        target_text = "T2" if hit_t2 else ("T1" if hit_t1 else "—")
        target_color = TEAL_DIM if hit_t2 else (YELLOW_DIM if hit_t1 else MUTED)

        agreement_value = _safe_float(agreement_score, -1)
        agreement_color = TEAL_DIM if agreement_value >= 90 else (BLUE_DIM if agreement_value >= 80 else (YELLOW_DIM if agreement_value >= 70 else RED_DIM))

        return html.Div([
            html.Span(f"#{rank}", style={"flex":"0 0 34px","fontSize":"11px","color":WHITE,"fontWeight":"800"}),
            html.Span(symbol, style={
                "flex":"0 0 68px","fontWeight":"900","fontSize":"14px",
                "color":WHITE,"fontFamily":"DM Mono, monospace"
            }),
            html.Span(signal_type, style={"flex":"0 0 92px","fontSize":"11px","color":score_color,"fontWeight":"800"}),
            html.Span(f"{score:.1f}", style={"flex":"0 0 58px","fontSize":"15px","fontWeight":"900","color":score_color}),
            html.Span(grade, style={"flex":"0 0 42px","fontSize":"15px","fontWeight":"900","color":grade_color}),
            html.Span(_fmt_money(entry_price), style={"flex":"0 0 84px","fontSize":"12px","color":WHITE,"fontFamily":"DM Mono, monospace"}),
            html.Span(_fmt_pct(outcome_pct, 2, signed=True), style={"flex":"0 0 74px","fontSize":"12px","fontWeight":"800","color":outcome_color}),
            html.Span(_fmt_pct(mfe_pct, 2), style={"flex":"0 0 62px","fontSize":"12px","color":TEAL_DIM if mfe_pct not in (None, "") else MUTED}),
            html.Span(_fmt_pct(mae_pct, 2), style={"flex":"0 0 62px","fontSize":"12px","color":RED_DIM if mae_pct not in (None, "") else MUTED}),
            html.Span(dir_text, style={"flex":"0 0 36px","fontSize":"14px","fontWeight":"900","color":dir_color,"textAlign":"center"}),
            html.Span(target_text, style={"flex":"0 0 42px","fontSize":"12px","fontWeight":"900","color":target_color,"textAlign":"center"}),
            html.Span(
                "—" if agreement_score in (None, "") else f"{float(agreement_score):.1f}",
                style={"flex":"0 0 74px","fontSize":"12px","fontWeight":"900","color":agreement_color,"textAlign":"center"}
            ),
            html.Span(
                "—" if intelligence_delta in (None, "") else f"{float(intelligence_delta):+.1f}",
                style={"flex":"0 0 62px","fontSize":"12px","fontWeight":"800","color":agreement_color,"textAlign":"center"}
            ),
            html.Span(delta_quality_label, style={"flex":"0 0 104px","fontSize":"10px","fontWeight":"900","color":agreement_color,"textAlign":"center"}),
            html.Span(delta_action, style={"flex":"0 0 118px","fontSize":"10px","fontWeight":"900","color":agreement_color,"textAlign":"center"}),
            html.Span(agreement_bucket.replace(" Confirmation", ""), style={"flex":"0 0 150px","fontSize":"10px","color":agreement_color}),
            html.Span(regime, style={"flex":"0 0 115px","fontSize":"11px","color":WHITE}),
            html.Span(setup_type, style={"flex":"1","fontSize":"11px","color":WHITE,"minWidth":"160px"}),
        ], style={
            "display":"flex",
            "alignItems":"center",
            "gap":"10px",
            "padding":"11px 0",
            "borderBottom":f"1px solid {BORDER}",
            "minWidth":"1620px"
        })

    header = html.Div([
        html.Span("#",       style={"flex":"0 0 34px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Symbol",  style={"flex":"0 0 68px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Signal",  style={"flex":"0 0 92px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Score",   style={"flex":"0 0 58px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Grade",   style={"flex":"0 0 42px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Entry",   style={"flex":"0 0 84px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Outcome", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("MFE",     style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("MAE",     style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Dir",     style={"flex":"0 0 36px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Tgt",     style={"flex":"0 0 42px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Agree",   style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Delta",   style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("D-Quality", style={"flex":"0 0 104px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("D-Action", style={"flex":"0 0 118px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Bucket",  style={"flex":"0 0 150px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Regime",  style={"flex":"0 0 115px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Setup",   style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","minWidth":"160px"}),
    ], style={
        "display":"flex",
        "gap":"10px",
        "paddingBottom":"8px",
        "borderBottom":f"1px solid {BORDER}",
        "marginBottom":"4px",
        "minWidth":"1620px"
    })

    def _bucket_card(b):
        bucket = b.get("bucket", "—")
        total = _safe_int(b.get("total_signals"))
        evaluated = _safe_int(b.get("with_outcomes"))
        acc = _safe_float(b.get("direction_correct_rate"))
        edge = _safe_float(b.get("edge_ratio"))
        mfe = _safe_float(b.get("avg_mfe_pct"))
        mae = _safe_float(b.get("avg_mae_pct"))
        color = TEAL_DIM if bucket.startswith("90") else (BLUE_DIM if bucket.startswith("80") else (YELLOW_DIM if bucket.startswith("70") else RED_DIM))
        return html.Div([
            html.Div(bucket, style={"fontSize":"11px","fontWeight":"900","color":color,"marginBottom":"8px"}),
            html.Div([
                html.Div([html.Span("Signals", style={"color":WHITE,"fontSize":"10px"}), html.Strong(str(total), style={"color":WHITE})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("Evaluated", style={"color":WHITE,"fontSize":"10px"}), html.Strong(str(evaluated), style={"color":WHITE})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("Accuracy", style={"color":WHITE,"fontSize":"10px"}), html.Strong(f"{acc:.1f}%", style={"color":color})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("Edge", style={"color":WHITE,"fontSize":"10px"}), html.Strong(f"{edge:.2f}", style={"color":color})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("MFE / MAE", style={"color":WHITE,"fontSize":"10px"}), html.Strong(f"{mfe:.2f}% / {mae:.2f}%", style={"color":WHITE})], style={"display":"flex","justifyContent":"space-between"}),
            ], style={"display":"grid","gap":"5px"})
        ], style={
            "border":f"1px solid {BORDER}",
            "background":"rgba(0,0,0,.2)",
            "borderRadius":"14px",
            "padding":"14px",
            "minHeight":"134px"
        })

    def _threshold_row(t):
        threshold = _safe_int(t.get("threshold"))
        total = _safe_int(t.get("total_signals"))
        evaluated = _safe_int(t.get("with_outcomes"))
        acc = _safe_float(t.get("direction_correct_rate"))
        edge = _safe_float(t.get("edge_ratio"))
        outcome = _safe_float(t.get("avg_outcome_pct"))
        color = TEAL_DIM if threshold >= 90 else (BLUE_DIM if threshold >= 80 else (YELLOW_DIM if threshold >= 70 else TEXT))
        return html.Div([
            html.Span(f">= {threshold}", style={"flex":"0 0 70px","fontWeight":"900","color":color}),
            html.Span(str(total), style={"flex":"0 0 70px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(str(evaluated), style={"flex":"0 0 80px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(f"{acc:.1f}%", style={"flex":"0 0 90px","color":color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{edge:.2f}", style={"flex":"0 0 80px","color":color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{outcome:+.2f}%", style={"flex":"0 0 90px","color":TEAL_DIM if outcome >= 0 else RED_DIM,"fontWeight":"900","textAlign":"center"}),
        ], style={
            "display":"flex",
            "gap":"10px",
            "alignItems":"center",
            "padding":"9px 0",
            "borderBottom":f"1px solid {BORDER}",
        })


    def _attribution_row(row):
        group = row.get("group", "—")
        n = _safe_int(row.get("total_signals"))
        evaluated = _safe_int(row.get("with_outcomes"))
        direction = _safe_float(row.get("direction_accuracy_rate"))
        edge_acc = _safe_float(row.get("edge_accuracy_rate"))
        tradeable = _safe_float(row.get("tradeable_mfe_rate"))
        strong = _safe_float(row.get("strong_mfe_rate"))
        edge = _safe_float(row.get("edge_ratio"))
        mfe = _safe_float(row.get("avg_mfe_pct"))
        mae = _safe_float(row.get("avg_mae_pct"))
        outcome = _safe_float(row.get("avg_outcome_pct"))

        edge_color = TEAL_DIM if edge >= 1.5 else (YELLOW_DIM if edge >= 1 else RED_DIM)

        return html.Div([
            html.Span(group, style={"flex":"1.4","fontSize":"11px","fontWeight":"900","color":WHITE,"minWidth":"150px"}),
            html.Span(str(n), style={"flex":"0 0 54px","fontSize":"11px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(str(evaluated), style={"flex":"0 0 54px","fontSize":"11px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(f"{direction:.1f}%", style={"flex":"0 0 74px","fontSize":"11px","color":BLUE_DIM,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{edge_acc:.1f}%", style={"flex":"0 0 74px","fontSize":"11px","color":edge_color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{tradeable:.1f}%", style={"flex":"0 0 78px","fontSize":"11px","color":TEAL_DIM if tradeable >= 40 else YELLOW_DIM,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{strong:.1f}%", style={"flex":"0 0 72px","fontSize":"11px","color":PURPLE,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{edge:.2f}", style={"flex":"0 0 64px","fontSize":"11px","color":edge_color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{mfe:.2f}%/{mae:.2f}%", style={"flex":"0 0 94px","fontSize":"11px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(f"{outcome:+.2f}%", style={"flex":"0 0 76px","fontSize":"11px","color":TEAL_DIM if outcome >= 0 else RED_DIM,"fontWeight":"900","textAlign":"center"}),
        ], style={
            "display":"flex",
            "gap":"8px",
            "alignItems":"center",
            "padding":"8px 0",
            "borderBottom":f"1px solid {BORDER}",
            "minWidth":"900px"
        })

    def _attribution_table(title, rows):
        rows = rows if isinstance(rows, list) else []
        return html.Div([
            html.Div(title, style={
                "fontSize":"12px","fontWeight":"900","color":WHITE,
                "textTransform":"uppercase","letterSpacing":".08em",
                "marginBottom":"8px"
            }),
            html.Div([
                html.Span("Group", style={"flex":"1.4","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","minWidth":"150px"}),
                html.Span("Sig", style={"flex":"0 0 54px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Eval", style={"flex":"0 0 54px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Dir", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Edge Acc", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Tradeable", style={"flex":"0 0 78px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Strong", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Edge", style={"flex":"0 0 64px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("MFE/MAE", style={"flex":"0 0 94px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Outcome", style={"flex":"0 0 76px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
            ], style={
                "display":"flex","gap":"8px","paddingBottom":"7px",
                "borderBottom":f"1px solid {BORDER}",
                "minWidth":"900px"
            }),
            html.Div([_attribution_row(r) for r in rows[:10]] if rows else [
                html.Div("No attribution data yet.", style={"fontSize":"12px","color":WHITE,"padding":"10px 0"})
            ]),
        ], style={
            "border":f"1px solid {BORDER}",
            "background":"rgba(0,0,0,.15)",
            "borderRadius":"14px",
            "padding":"14px",
            "overflowX":"auto"
        })


    if edge_ratio >= 1.2 and with_outcomes > 0:
        edge_note = "Positive path edge: average favorable movement is larger than average adverse movement."
        edge_variant = "teal"
    elif with_outcomes > 0:
        edge_note = "Path edge is not yet confirmed. Continue collecting outcomes before relying on this metric."
        edge_variant = "yellow"
    else:
        edge_note = "Outcome statistics populate after signals have enough forward price data."
        edge_variant = "blue"

    return html.Div([
        card([
            html.Div([
                html.Div([
                    html.H2("Scoreboard", style={
                        "color":WHITE,"fontSize":"18px","fontWeight":"900",
                        "margin":"0 0 4px"
                    }),
                    html.P(
                        f"Live outcome validation · {outcome_window_hours}h window · backend /api/scoreboard",
                        style={"color":WHITE,"fontSize":"13px","margin":"0"}
                    ),
                ]),
                badge("LIVE BACKEND", "teal" if board else "red"),
            ], style={
                "display":"flex",
                "justifyContent":"space-between",
                "alignItems":"start",
                "gap":"16px",
                "marginBottom":"16px"
            }),

            html.Div([
                _metric("Total Signals", f"{total_signals}", WHITE, "All logged signals"),
                _metric("Evaluated", f"{with_outcomes}", TEAL_DIM, "Signals with outcomes"),
                _metric("Pending", f"{pending_outcomes}", YELLOW_DIM if pending_outcomes else MUTED, "Awaiting outcome window"),
                _metric("Direction Accuracy", _fmt_pct(direction_correct_rate, 1), TEAL_DIM if direction_correct_rate >= 50 else YELLOW_DIM, f"{direction_evaluated} evaluated signals"),
                _metric("Avg MFE", _fmt_pct(avg_mfe_pct, 2), TEAL_DIM, "Favorable excursion"),
                _metric("Avg MAE", _fmt_pct(avg_mae_pct, 2), RED_DIM, "Adverse excursion"),
                _metric("Edge Ratio", f"{edge_ratio:.2f}", TEAL_DIM if edge_ratio >= 1.2 else YELLOW_DIM, "MFE ÷ MAE"),
                _metric("Targets", f"T1 {hit_target1_rate:.1f}% / T2 {hit_target2_rate:.1f}%", BLUE_DIM, "Hit-rate snapshot"),
            ], style={
                "display":"grid",
                "gridTemplateColumns":"repeat(4,1fr)",
                "gap":"12px",
                "marginBottom":"16px"
            }),

            note_box(edge_note, edge_variant),

            html.Div(style={"height":"16px"}),

            html.Div([
                html.Div([
                    html.H3("Intelligence Agreement Validation", style={
                        "fontSize":"15px","fontWeight":"900","color":WHITE,"margin":"0 0 4px"
                    }),
                    html.Div("Shows whether deeper intelligence agreement improves direction accuracy and path edge.",
                             style={"fontSize":"11px","color":WHITE}),
                ]),
            ], style={"marginBottom":"12px"}),

            html.Div(
                [_bucket_card(b) for b in agreement_buckets] if agreement_buckets else [
                    note_box("Agreement buckets are waiting for repaired or newly logged signals.", "yellow")
                ],
                style={
                    "display":"grid",
                    "gridTemplateColumns":"repeat(4,1fr)",
                    "gap":"12px",
                    "marginBottom":"16px"
                }
            ),

            html.Div([
                html.Div("Minimum Agreement Filter", style={
                    "fontSize":"12px","fontWeight":"900","color":WHITE,
                    "textTransform":"uppercase","letterSpacing":".08em",
                    "marginBottom":"8px"
                }),
                html.Div([
                    html.Span("Filter", style={"flex":"0 0 70px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase"}),
                    html.Span("Signals", style={"flex":"0 0 70px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Eval", style={"flex":"0 0 80px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Accuracy", style={"flex":"0 0 90px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Edge", style={"flex":"0 0 80px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Outcome", style={"flex":"0 0 90px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                ], style={"display":"flex","gap":"10px","borderBottom":f"1px solid {BORDER}","paddingBottom":"7px"}),
                html.Div([_threshold_row(t) for t in agreement_thresholds] if agreement_thresholds else [
                    html.Div("No agreement threshold data yet.", style={"fontSize":"12px","color":WHITE,"padding":"12px 0"})
                ]),
            ], style={
                "border":f"1px solid {BORDER}",
                "background":"rgba(0,0,0,.15)",
                "borderRadius":"14px",
                "padding":"14px",
                "marginBottom":"18px",
                "maxWidth":"620px"
            }),

            html.Div(style={"height":"16px"}),

            html.Div([
                html.Div([
                    html.H3("Live Performance Attribution", style={
                        "fontSize":"15px","fontWeight":"900","color":WHITE,"margin":"0 0 4px"
                    }),
                    html.Div("Ranks which parts of the engine are producing direction, edge, and tradeable opportunity.",
                             style={"fontSize":"11px","color":WHITE}),
                ]),
            ], style={"marginBottom":"12px"}),

            html.Div([
                _attribution_table("Agreement Bucket", attribution_report.get("by_agreement_bucket", [])),
                _attribution_table("Delta Bucket", attribution_report.get("by_delta_bucket", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}),

            html.Div([
                _attribution_table("Regime", attribution_report.get("by_regime", [])),
                _attribution_table("Setup Type", attribution_report.get("by_setup_type", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}),

            html.Div([
                _attribution_table("Grade", attribution_report.get("by_grade", [])),
                _attribution_table("Signal Type", attribution_report.get("by_signal_type", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}),

            html.Div([
                _attribution_table("Delta Quality", attribution_report.get("by_delta_quality", [])),
                _attribution_table("Delta Action", attribution_report.get("by_delta_action", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"18px"}),

            html.Div([
                html.Div([
                    html.Div("Recent Signal Outcomes", style={
                        "fontSize":"12px","fontWeight":"900","color":WHITE,
                        "textTransform":"uppercase","letterSpacing":".08em"
                    }),
                    html.Div("Pending rows show dashes until MFE / MAE / direction fields are populated.",
                             style={"fontSize":"11px","color":WHITE,"marginTop":"3px"}),
                ]),
            ], style={"marginBottom":"12px"}),

            html.Div([
                header,
                html.Div([_entry_row(e, i+1) for i, e in enumerate(entries)] if entries else [
                    html.Div(
                        "Scoreboard data not yet available. Backend returned no recent_signals.",
                        style={"color":WHITE,"fontSize":"13px","padding":"24px 0","textAlign":"center"}
                    )
                ]),
            ], style={
                "overflowX":"auto",
                "border":f"1px solid {BORDER}",
                "borderRadius":"14px",
                "padding":"12px",
                "background":"rgba(0,0,0,.14)"
            }),

            html.Div(f"Last updated: {generated}", style={
                "fontSize":"10px","color":WHITE,"marginTop":"12px"
            }),
        ]),
    ])


def classify_transition(old_status, new_status, delta):
    """
    Intelligence Change Detector transition classifier.

    Delta is calculated as:
        deep_score - composite_score

    Positive delta = deeper intelligence is stronger than surface composite.
    Negative delta = deeper intelligence is weaker than surface composite.

    State transition has priority over delta:
    - Building -> Watching = Improving / upgrade
    - Watching -> Watching = Monitor
    - Watching -> Avoid = Major downgrade
    """
    old_status_l = str(old_status or "").strip().lower()
    new_status_l = str(new_status or "").strip().lower()

    # Normalize common backend labels.
    upgrade_states = ("watching", "armed", "triggered", "opportunity")
    high_states = ("armed", "triggered", "opportunity")

    # No state change should remain a monitor, even if the score delta is negative.
    # This prevents Watching -> Watching rows from being counted as downgrades.
    if old_status_l == new_status_l and old_status_l:
        return "MONITOR", "yellow"

    # Explicit improvement transitions first.
    if old_status_l == "building" and new_status_l == "watching":
        return "IMPROVING", "teal"

    if old_status_l == "building" and new_status_l in high_states:
        return "STRONG UPGRADE", "teal"

    if old_status_l == "avoid" and new_status_l in upgrade_states:
        return "UPGRADE", "teal"

    if old_status_l == "watching" and new_status_l in high_states:
        return "STRONG UPGRADE", "teal"

    # Explicit deterioration transitions.
    if old_status_l in high_states and new_status_l == "watching":
        return "DOWNGRADE", "red"

    if old_status_l in ("building", "watching", "armed", "triggered", "opportunity") and new_status_l == "avoid":
        return "MAJOR DOWNGRADE", "red"

    # Score-delta interpretation only applies when the state transition is not definitive.
    if delta >= 20:
        return "INTELLIGENCE LEAD", "teal"

    if delta >= 10:
        return "MODEST UPGRADE", "teal"

    if delta <= -20:
        return "INTELLIGENCE WARNING", "red"

    if delta <= -10:
        return "MODEST DOWNGRADE", "red"

    return "MONITOR", "yellow"

def build_divergence_tab(session=None):
    """
    Intelligence Change Detector.

    This page uses the actual backend divergence endpoint fields:
    symbol, composite_score, deep_score, delta, old_status, new_status,
    regime, price, audited_at.
    """
    import requests as _rq

    try:
        def _do_fetch_divergence():
            r = _rq.get(f"{BACKEND_HTTP}/api/radar/divergence", timeout=15)
            return r.json() if r.ok else {}

        data = (
            shared_cache.get_or_fetch("/api/radar/divergence", _do_fetch_divergence, ttl_seconds=90)
            if shared_cache is not None
            else _do_fetch_divergence()
        )
    except Exception:
        data = {}

    raw_symbols = data.get("symbols", []) if isinstance(data, dict) else []
    audit_raw = (
        data.get("last_audit")
        or data.get("audited_at")
    ) if isinstance(data, dict) else None

    try:
        if audit_raw:
            audit_dt = datetime.fromtimestamp(
                float(audit_raw),
                tz=timezone.utc
            ).astimezone(
                timezone(timedelta(hours=-4))
            )

            audit_label = audit_dt.strftime(
                "%b %d, %Y %I:%M %p ET"
            )
        else:
            audit_label = "Pending — runs nightly after the EOD audit"

    except Exception:
        audit_label = str(audit_raw) if audit_raw else "Pending — runs nightly after the EOD audit"

    def _num(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    items = []
    for s in (raw_symbols if isinstance(raw_symbols, list) else []):
        if not isinstance(s, dict):
            continue

        composite = _num(s.get("composite_score"), 0)
        deep = _num(s.get("deep_score"), 0)

        # Use intuitive displayed delta: deep intelligence minus surface composite.
        # Example: Composite 62.5, Deep 34.85 = -27.65 = deeper engine downgraded it.
        delta = round(deep - composite, 2)

        old_status = s.get("old_status") or "—"
        new_status = s.get("new_status") or s.get("status") or "—"
        transition, tone = classify_transition(old_status, new_status, delta)

        items.append({
            "symbol": s.get("symbol", ""),
            "price": _num(s.get("price"), 0),
            "composite_score": composite,
            "deep_score": deep,
            "delta": delta,
            "old_status": old_status,
            "new_status": new_status,
            "transition": transition,
            "tone": tone,
            "regime": s.get("regime") or "—",
            "audited_at": s.get("audited_at") or audit_label,
        })

    # Largest intelligence gap first.
    items = sorted(items, key=lambda d: abs(d.get("delta", 0)), reverse=True)

    upgrades = sum(1 for d in items if d["tone"] == "teal")
    downgrades = sum(1 for d in items if d["tone"] == "red")
    monitoring = sum(1 for d in items if d["tone"] == "yellow")

    best_upgrade = max(items, key=lambda d: d["delta"], default=None)
    best_downgrade = min(items, key=lambda d: d["delta"], default=None)

    def _tone_color(tone):
        if tone == "teal":
            return TEAL_DIM
        if tone == "red":
            return RED_DIM
        if tone == "yellow":
            return YELLOW_DIM
        return MUTED

    def _state_badge(value, tone="gray"):
        color = _tone_color(tone)
        bg = TEAL_GLOW if tone == "teal" else RED_GLOW if tone == "red" else "rgba(245,158,11,.10)" if tone == "yellow" else "rgba(100,116,139,.12)"
        border = BORDER_T if tone == "teal" else "rgba(239,68,68,.35)" if tone == "red" else "rgba(245,158,11,.35)" if tone == "yellow" else "rgba(100,116,139,.25)"
        return html.Span(
            str(value),
            style={
                "display": "inline-block",
                "borderRadius": "999px",
                "border": f"1px solid {border}",
                "background": bg,
                "color": color,
                "fontSize": "10px",
                "fontWeight": "900",
                "letterSpacing": ".06em",
                "padding": "4px 9px",
                "textTransform": "uppercase",
                "whiteSpace": "nowrap",
            }
        )

    summary_card = card([
        html.Div([
            html.Div([
                html.H2(
                    "Intelligence Change Detector",
                    style={"color": WHITE, "fontSize": "20px", "fontWeight": "900", "margin": "0 0 4px"}
                ),
                html.P(
                    "Detects where the deeper intelligence engine disagrees with the surface radar score.",
                    style={"color": WHITE, "fontSize": "13px", "margin": "0"}
                ),
            ]),
            _state_badge(f"{len(items)} Symbols Audited", "gray"),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "16px", "marginBottom": "16px"}),

        html.Div([
            metric_tile("Upgrades", str(upgrades), TEAL_DIM),
            metric_tile("Monitoring", str(monitoring), YELLOW_DIM),
            metric_tile("Downgrades", str(downgrades), RED_DIM),
            metric_tile("Last Audit", str(audit_label)[:22], BLUE_DIM),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(4,1fr)", "gap": "10px", "marginBottom": "14px"}),

        html.Div([
            note_box(
                f"Strongest Upgrade: {(best_upgrade or {}).get('symbol','—')} "
                f"({(best_upgrade or {}).get('delta',0):+.1f})",
                "teal"
            ),
            note_box(
                f"Strongest Downgrade: {(best_downgrade or {}).get('symbol','—')} "
                f"({(best_downgrade or {}).get('delta',0):+.1f})",
                "red"
            ),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px"}),
    ], sx={"marginBottom": "16px"})

    def _row(d):
        delta = d.get("delta", 0)
        tone = d.get("tone", "gray")
        color = _tone_color(tone)
        delta_color = TEAL_DIM if delta > 0 else (RED_DIM if delta < 0 else MUTED)

        return html.Div([
            html.Span(
                d.get("symbol", ""),
                style={
                    "flex": "0.75",
                    "fontWeight": "900",
                    "fontSize": "14px",
                    "color": WHITE,
                    "fontFamily": "DM Mono, monospace",
                }
            ),
            html.Span(
                f"${d.get('price', 0):,.2f}",
                style={"flex": "0.85", "fontSize": "13px", "color": WHITE, "fontFamily": "DM Mono, monospace"}
            ),
            html.Span(
                f"{d.get('composite_score', 0):.1f}",
                style={"flex": "0.75", "fontSize": "13px", "fontWeight": "800", "color": YELLOW_DIM}
            ),
            html.Span(
                f"{d.get('deep_score', 0):.1f}",
                style={"flex": "0.75", "fontSize": "13px", "fontWeight": "800", "color": BLUE_DIM}
            ),
            html.Span(
                f"{delta:+.1f}",
                style={"flex": "0.75", "fontSize": "13px", "fontWeight": "900", "color": delta_color}
            ),
            html.Span(
                d.get("old_status", "—"),
                style={"flex": "0.9", "fontSize": "12px", "fontWeight": "700", "color": WHITE}
            ),
            html.Span(
                d.get("new_status", "—"),
                style={"flex": "0.9", "fontSize": "12px", "fontWeight": "900", "color": color}
            ),
            html.Span(
                d.get("transition", "—"),
                style={"flex": "1.65", "fontSize": "11px", "fontWeight": "900", "color": color}
            ),
            html.Span(
                d.get("regime", "—"),
                style={"flex": "0.95", "fontSize": "11px", "color": WHITE}
            ),
        ], style={
            "display": "flex",
            "alignItems": "center",
            "gap": "12px",
            "padding": "12px 0",
            "borderBottom": f"1px solid {BORDER}",
        })

    header = html.Div([
        html.Span("Symbol", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Price", style={"flex": "0.85", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Composite", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Deep Score", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Delta", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Previous", style={"flex": "0.9", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Current", style={"flex": "0.9", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Transition", style={"flex": "1.65", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Regime", style={"flex": "0.95", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
    ], style={
        "display": "flex",
        "gap": "12px",
        "paddingBottom": "8px",
        "borderBottom": f"1px solid {BORDER}",
        "marginBottom": "4px",
    })

    table_card = card([
        html.Div([
            html.H3(
                "Intelligence Transitions",
                style={"color": WHITE, "fontSize": "16px", "fontWeight": "900", "margin": "0"}
            ),
            html.P(
                "Positive delta = deeper intelligence stronger than radar. Negative delta = deeper intelligence weaker than radar.",
                style={"color": WHITE, "fontSize": "12px", "margin": "4px 0 0"}
            ),
        ], style={"marginBottom": "14px"}),

        header,

        html.Div([_row(d) for d in items] if items else [
            html.Div(
                "No intelligence changes yet. The detector populates after the EOD audit.",
                style={"color": WHITE, "fontSize": "13px", "padding": "24px 0", "textAlign": "center"}
            )
        ]),
    ])

    return html.Div([summary_card, table_card])


def build_billing_tab(session=None, perms=None):
    """Delegate to billing_ui module."""
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from billing_ui import build_billing_tab as _build
        return _build(session=session, perms=perms)
    except Exception as e:
        return card([
            html.H2("Billing & Plans", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
            note_box(f"Billing error: {str(e)[:120]}", "yellow"),
        ])


def register_billing_callbacks_from_module(app):
    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from billing_ui import register_billing_callbacks
        # FIX: was calling itself (register_billing_callbacks_from_module),
        # an unconditional self-call that would raise RecursionError the
        # moment this function is actually invoked. Currently dead code
        # (never called anywhere in this file), but fixed so it isn't a
        # landmine if it gets wired up later.
        register_billing_callbacks(app)
    except Exception as e:
        print(f"Warning: billing callbacks: {e}")




def build_preferences_tab(user_id="", session=None):
    import requests as _preqs

    def _card(c):
        return html.Section(c, style={"background":NAVY_CARD,"border":f"1px solid {BORDER}",
            "borderRadius":"20px","padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)","marginBottom":"16px"})

    def _label(t):
        return html.Div(t, style={"color":WHITE,"fontSize":"10px","fontWeight":"800",
            "textTransform":"uppercase","letterSpacing":".28em","marginBottom":"10px"})

    def _stitle(t):
        return html.Div(t, style={"color":TEAL_DIM,"fontSize":"11px","fontWeight":"800",
            "textTransform":"uppercase","letterSpacing":".15em","marginBottom":"16px",
            "paddingBottom":"10px","borderBottom":f"1px solid {BORDER}"})

    def _on():
        return {"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","borderRadius":"8px",
                "color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif","fontSize":"12px",
                "fontWeight":"700","padding":"8px 16px","cursor":"pointer"}

    def _off():
        return {"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}","borderRadius":"8px",
                "color":WHITE,"fontFamily":"DM Sans, sans-serif","fontSize":"12px",
                "fontWeight":"700","padding":"8px 16px","cursor":"pointer"}

    def _render_watchlist(wl):
        if not wl:
            return [html.Span("All symbols — no filter applied",
                              style={"color":WHITE,"fontSize":"12px","fontStyle":"italic"})]
        return [html.Span(s, style={"background":"rgba(0,0,0,.2)","border":f"1px solid {BORDER}",
                "borderRadius":"6px","color":WHITE,"fontSize":"12px","padding":"4px 10px",
                "marginRight":"6px","marginBottom":"6px","display":"inline-block"}) for s in wl]

    def _save(uid, email, payload):
        try:
            url = f"{BACKEND_HTTP}/api/preferences/{uid}"
            r = _preqs.patch(url, json=payload, timeout=8)
            if r.status_code == 404:
                r = _preqs.post(url, json={**payload, "user_id": uid, "email": email}, timeout=8)
            return ("Saved", "teal") if r.ok else (f"Error", "red")
        except Exception as e:
            return (f"{str(e)[:60]}", "red")


    """
    Fetches saved preferences from backend and renders with correct state.
    All buttons save instantly on click.
    """
    # Load saved preferences
    prefs = {
        "delivery_mode":     "realtime",
        "min_score":         60,
        "alert_types":       {"wyckoff":True,"gann":True,"ab_score":True,"elliott":False,"fibonacci":False},
        "watchlist":         [],
        "market_hours_only": True,
        "hurst_profile":     "MEDIUM",
        "weis_threshold":    0.5,
    }

    if user_id:
        try:
            r = _preqs.get(f"{BACKEND_HTTP}/api/preferences/{user_id}", timeout=4)
            if r.ok:
                p = r.json()
                prefs["delivery_mode"]     = p.get("delivery_mode", prefs["delivery_mode"])
                prefs["min_score"]         = p.get("min_score", prefs["min_score"])
                prefs["alert_types"]       = p.get("alert_types", prefs["alert_types"])
                prefs["watchlist"]         = p.get("watchlist", prefs["watchlist"])
                prefs["market_hours_only"] = p.get("market_hours_only", prefs["market_hours_only"])
                prefs["hurst_profile"]     = p.get("hurst_profile", prefs["hurst_profile"])
                prefs["weis_threshold"]    = p.get("weis_threshold", prefs["weis_threshold"])
        except Exception:
            pass

    mode     = prefs["delivery_mode"]
    types    = prefs["alert_types"]
    hours    = prefs["market_hours_only"]
    score    = prefs["min_score"]
    watchlist= prefs["watchlist"]
    hurst    = prefs["hurst_profile"]
    weis     = prefs["weis_threshold"]

    if isinstance(types, list):
        all_keys = ["wyckoff","gann","ab_score","elliott","fibonacci"]
        types = {k: (k in types) for k in all_keys}

    return html.Div([
        # Hidden stores for current state (set on load, updated on each save)
        dcc.Store(id="prefs-uid",        data=user_id),
        dcc.Store(id="prefs-email",      data=(session or {}).get("email","")),
        dcc.Store(id="prefs-mode-cur",   data=mode),
        dcc.Store(id="prefs-types-cur",  data=types),
        dcc.Store(id="prefs-hours-cur",  data=hours),
        dcc.Store(id="prefs-score-cur",  data=score),
        dcc.Store(id="prefs-wl-cur",     data=watchlist),
        dcc.Store(id="prefs-hurst-cur",  data=hurst),
        dcc.Store(id="prefs-weis-cur",   data=weis),

        html.Div([
            html.H2("Alert Preferences", style={"color":WHITE,"fontSize":"22px","fontWeight":"800","marginBottom":"4px"}),
            html.P("Changes save instantly.", style={"color":WHITE,"fontSize":"13px"}),
        ], style={"marginBottom":"24px"}),

        # Status message
        html.Div(id="prefs-status", style={"textAlign":"center","fontSize":"13px",
                 "minHeight":"24px","marginBottom":"8px","color":TEAL_DIM}),

        # Delivery Mode
        _card([_stitle("Delivery Mode"), _label("How often do you want alerts?"),
            html.Div([
                html.Button("Real-time",     id="pref-btn-realtime", n_clicks=0,
                            style=_on() if mode=="realtime" else _off()),
                html.Button("Hourly Digest", id="pref-btn-hourly",   n_clicks=0,
                            style=_on() if mode=="hourly"   else _off()),
                html.Button("Daily Summary", id="pref-btn-daily",    n_clicks=0,
                            style=_on() if mode=="daily"    else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        # Minimum Score
        _card([_stitle("Minimum Confluence Score"), _label("Only alert when score is at least:"),
            dcc.Slider(id="prefs-score-slider", min=0, max=100, step=5, value=score,
                marks={0:"0",25:"25",50:"50",75:"75",100:"100"},
                tooltip={"placement":"bottom","always_visible":True}),
            html.Div(style={"height":"8px"}),
            html.Div("Higher score = fewer, higher-quality alerts",
                     style={"color":WHITE,"fontSize":"11px"}),
            html.Button("Save Score", id="prefs-score-save", n_clicks=0, style={
                "marginTop":"12px","background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                "borderRadius":"8px","color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif",
                "fontSize":"12px","fontWeight":"700","padding":"8px 16px","cursor":"pointer"})]),

        # Alert Types
        _card([_stitle("Alert Types"), _label("Click to toggle — saves instantly:"),
            html.Div([
                html.Button("Structure Alerts", id="pref-btn-wyckoff",   n_clicks=0,
                            style=_on() if types.get("wyckoff")   else _off()),
                html.Button("Vector Alerts",    id="pref-btn-gann",      n_clicks=0,
                            style=_on() if types.get("gann")      else _off()),
                html.Button("Score Alerts",     id="pref-btn-ab_score",  n_clicks=0,
                            style=_on() if types.get("ab_score")  else _off()),
                html.Button("Cycle Alerts",     id="pref-btn-elliott",   n_clicks=0,
                            style=_on() if types.get("elliott")   else _off()),
                html.Button("Level Alerts",     id="pref-btn-fibonacci", n_clicks=0,
                            style=_on() if types.get("fibonacci") else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        # Watchlist
        _card([_stitle("Watchlist"), _label("Only alert on these symbols (leave empty for all)"),
            html.Div([
                dcc.Input(id="prefs-sym-input", type="text", placeholder="e.g. AAPL", maxLength=5,
                    style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                           "borderRadius":"8px","color":WHITE,"fontFamily":"DM Mono, monospace",
                           "fontSize":"13px","padding":"10px 14px","width":"160px",
                           "marginRight":"10px","textTransform":"uppercase"}),
                html.Button("Add Symbol", id="prefs-sym-add", n_clicks=0,
                    style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                           "borderRadius":"8px","color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif",
                           "fontSize":"12px","fontWeight":"700","padding":"10px 18px","cursor":"pointer"}),
            ], style={"display":"flex","alignItems":"center","marginBottom":"12px"}),
            html.Div(id="prefs-wl-display", children=_render_watchlist(watchlist))]),

        # Market Hours
        _card([_stitle("Market Hours"),
            html.Div([
                html.Div([
                    html.Div("Market hours only", style={"color":WHITE,"fontSize":"13px","fontWeight":"600"}),
                    html.Div("Suppress alerts outside 9:30–4:00 PM ET",
                             style={"color":WHITE,"fontSize":"11px","marginTop":"2px"}),
                ], style={"flex":"1"}),
                html.Button("ON" if hours else "OFF", id="pref-btn-hours", n_clicks=0,
                            style=_on() if hours else _off()),
            ], style={"display":"flex","alignItems":"center","gap":"16px"})]),

        # Hurst Cycle Profile
        _card([_stitle("Hurst Cycle Profile"),
            _label("Lookback horizon for cycle timing analysis"),
            html.Div([
                html.Button("Short (90d)",   id="pref-btn-hurst-short",  n_clicks=0,
                            style=_on() if hurst=="SHORT"  else _off()),
                html.Button("Medium (1yr)",  id="pref-btn-hurst-medium", n_clicks=0,
                            style=_on() if hurst=="MEDIUM" else _off()),
                html.Button("Long (3yr)",    id="pref-btn-hurst-long",   n_clicks=0,
                            style=_on() if hurst=="LONG"   else _off()),
            ], style={"display":"flex","flexWrap":"wrap","gap":"8px"})]),

        # Weis Wave Sensitivity
        _card([_stitle("〰️ Weis Wave Sensitivity"),
            _label("Reversal threshold — lower = more sensitive"),
            dcc.Slider(id="prefs-weis-slider", min=0.1, max=3.0, step=0.1, value=weis,
                marks={0.1:"0.1%", 0.5:"0.5%", 1.0:"1.0%", 2.0:"2.0%", 3.0:"3.0%"},
                tooltip={"placement":"bottom","always_visible":True}),
            html.Div(style={"height":"8px"}),
            html.Button("Save Sensitivity", id="prefs-weis-save", n_clicks=0, style={
                "marginTop":"12px","background":TEAL_GLOW,"border":f"1px solid {BORDER_T}",
                "borderRadius":"8px","color":TEAL_DIM,"fontFamily":"DM Sans, sans-serif",
                "fontSize":"12px","fontWeight":"700","padding":"8px 16px","cursor":"pointer"})]),

    ], style={"maxWidth":"600px","margin":"0 auto","padding":"24px 16px"})

def register_preferences_callbacks(app):

    # ── Delivery mode — instant save ───────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children"),
        Output("prefs-status","style"),
        Output("pref-btn-realtime","style"),
        Output("pref-btn-hourly","style"),
        Output("pref-btn-daily","style"),
        Output("prefs-mode-cur","data"),
        Input("pref-btn-realtime","n_clicks"),
        Input("pref-btn-hourly","n_clicks"),
        Input("pref-btn-daily","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-mode-cur","data"),
        prevent_initial_call=True,
    )
    def save_mode(r, h, d, uid, email, cur):
        ctx = callback_context
        if not ctx.triggered: return (no_update,)*6
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        mode_map = {"pref-btn-realtime":"realtime","pref-btn-hourly":"hourly","pref-btn-daily":"daily"}
        mode = mode_map.get(t, cur)
        if not uid: return "Not logged in",_msg_style("yellow"),*[_on() if x==mode else _off() for x in ["realtime","hourly","daily"]],mode
        msg, color = _save(uid, email, {"delivery_mode": mode})
        return msg,_msg_style(color),*[_on() if x==mode else _off() for x in ["realtime","hourly","daily"]],mode

    # ── Alert types — instant save ─────────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("pref-btn-wyckoff","style"),
        Output("pref-btn-gann","style"),
        Output("pref-btn-ab_score","style"),
        Output("pref-btn-elliott","style"),
        Output("pref-btn-fibonacci","style"),
        Output("prefs-types-cur","data"),
        Input("pref-btn-wyckoff","n_clicks"),
        Input("pref-btn-gann","n_clicks"),
        Input("pref-btn-ab_score","n_clicks"),
        Input("pref-btn-elliott","n_clicks"),
        Input("pref-btn-fibonacci","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-types-cur","data"),
        prevent_initial_call=True,
    )
    def save_types(nw,ng,na,ne,nf, uid, email, types):
        ctx = callback_context
        if not ctx.triggered: return (no_update,)*8
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        types = dict(types or {})
        km = {"pref-btn-wyckoff":"wyckoff","pref-btn-gann":"gann","pref-btn-ab_score":"ab_score",
              "pref-btn-elliott":"elliott","pref-btn-fibonacci":"fibonacci"}
        if t in km: types[km[t]] = not types.get(km[t], False)
        styles = [_on() if types.get(k) else _off() for k in ["wyckoff","gann","ab_score","elliott","fibonacci"]]
        if not uid: return "Not logged in",_msg_style("yellow"),*styles,types
        msg, color = _save(uid, email, {"alert_types": types})
        return msg,_msg_style(color),*styles,types

    # ── Market hours — instant save ────────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("pref-btn-hours","children"),
        Output("pref-btn-hours","style"),
        Output("prefs-hours-cur","data"),
        Input("pref-btn-hours","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-hours-cur","data"),
        prevent_initial_call=True,
    )
    def save_hours(n, uid, email, cur):
        new = not cur
        label = "ON" if new else "OFF"
        style = _on() if new else _off()
        if not uid: return "Not logged in",_msg_style("yellow"),label,style,new
        msg, color = _save(uid, email, {"market_hours_only": new})
        return msg,_msg_style(color),label,style,new

    # ── Min score — save on button click ───────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("prefs-score-cur","data"),
        Input("prefs-score-save","n_clicks"),
        State("prefs-score-slider","value"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        prevent_initial_call=True,
    )
    def save_score(n, val, uid, email):
        if not uid: return "Not logged in",_msg_style("yellow"),val
        msg, color = _save(uid, email, {"min_score": val})
        return msg,_msg_style(color),val

    # ── Hurst profile — instant save ───────────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("pref-btn-hurst-short","style"),
        Output("pref-btn-hurst-medium","style"),
        Output("pref-btn-hurst-long","style"),
        Output("prefs-hurst-cur","data"),
        Input("pref-btn-hurst-short","n_clicks"),
        Input("pref-btn-hurst-medium","n_clicks"),
        Input("pref-btn-hurst-long","n_clicks"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        State("prefs-hurst-cur","data"),
        prevent_initial_call=True,
    )
    def save_hurst(s, m, l, uid, email, cur):
        ctx = callback_context
        if not ctx.triggered: return (no_update,)*6
        t = ctx.triggered[0]["prop_id"].split(".")[0]
        hmap = {"pref-btn-hurst-short":"SHORT","pref-btn-hurst-medium":"MEDIUM","pref-btn-hurst-long":"LONG"}
        hurst = hmap.get(t, cur)
        styles = [_on() if h==hurst else _off() for h in ["SHORT","MEDIUM","LONG"]]
        if not uid: return "Not logged in",_msg_style("yellow"),*styles,hurst
        msg, color = _save(uid, email, {"hurst_profile": hurst})
        return msg,_msg_style(color),*styles,hurst

    # ── Weis threshold — save on button click ──────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("prefs-weis-cur","data"),
        Input("prefs-weis-save","n_clicks"),
        State("prefs-weis-slider","value"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        prevent_initial_call=True,
    )
    def save_weis(n, val, uid, email):
        if not uid: return "Not logged in",_msg_style("yellow"),val
        msg, color = _save(uid, email, {"weis_threshold": val})
        return msg,_msg_style(color),val

    # ── Watchlist — add symbol and save ───────────────────────────────────────
    @app.callback(
        Output("prefs-status","children", allow_duplicate=True),
        Output("prefs-status","style", allow_duplicate=True),
        Output("prefs-wl-cur","data"),
        Output("prefs-wl-display","children"),
        Output("prefs-sym-input","value"),
        Input("prefs-sym-add","n_clicks"),
        State("prefs-sym-input","value"),
        State("prefs-wl-cur","data"),
        State("prefs-uid","data"),
        State("prefs-email","data"),
        prevent_initial_call=True,
    )
    def add_symbol(n, sym, wl, uid, email):
        if not sym: return no_update,no_update,wl,_render_watchlist(wl),""
        s = sym.strip().upper()
        wl = list(wl or [])
        if s and s not in wl: wl.append(s)
        if not uid: return "Not logged in",_msg_style("yellow"),wl,_render_watchlist(wl),""
        msg, color = _save(uid, email, {"watchlist": wl})
        return msg,_msg_style(color),wl,_render_watchlist(wl),""

# ── Admin helpers ──────────────────────────────────────────────────────────────

# FIX: GOLD, ADMIN_EMAIL, _tile, _severity_color, and _score_bar were referenced
# below but never defined anywhere in this file -- clicking the Admin tab raised
# a NameError immediately. These are safe, minimal definitions that reuse
# existing patterns already in this file rather than introducing new ones.

GOLD = "#F5C842"

# ADMIN_EMAIL must come from an env var. If unset, default to a value that can
# never match a real session email (NOT an empty string) -- otherwise a
# session with no email set would incorrectly be treated as admin.
ADMIN_EMAIL = os.getenv("SIGMALYTIC_ADMIN_EMAIL") or "no-admin-configured@invalid"


def _admin_tile(label, value, color=None, sub=None):
    color = color or WHITE
    return html.Div([
        html.Div(label, style={"fontSize":"10px","color":WHITE,"fontWeight":"700",
                               "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"6px"}),
        html.Div(value, style={"fontSize":"22px","fontWeight":"900","color":color,"lineHeight":"1"}),
        html.Div(sub,   style={"fontSize":"10px","color":WHITE,"marginTop":"4px"}) if sub else html.Div(),
    ], style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px"})


# Alias: build_admin_tab below calls this as `_tile(...)`.
_tile = _admin_tile


def _severity_color(severity):
    s = str(severity or "").upper().strip()
    if s in {"CRITICAL", "HIGH", "ERROR"}:
        return RED_DIM
    if s in {"MEDIUM", "WARNING", "WARN"}:
        return YELLOW_DIM
    if s in {"LOW", "INFO"}:
        return TEAL_DIM
    return WHITE


def _score_bar(score, width="80px"):
    try:
        pct = max(0, min(100, float(score)))
    except Exception:
        pct = 0
    color = TEAL_DIM if pct >= 70 else (YELLOW_DIM if pct >= 45 else RED_DIM)
    return html.Div(
        html.Div(style={
            "width": f"{pct}%", "height": "100%", "borderRadius": "999px",
            "background": color,
        }),
        style={
            "width": width, "height": "6px", "background": "rgba(255,255,255,.08)",
            "borderRadius": "999px", "overflow": "hidden", "marginTop": "4px",
        },
    )


# Alias: build_admin_tab below calls this as `_grade_color(...)`.
# _probability_grade_color already implements the same A/B/C/D-F mapping.
_grade_color = _probability_grade_color


def _admin_card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
         "borderRadius": "16px", "padding": "20px",
         "boxShadow": "0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Div(children, style=s)


def is_admin(session: dict) -> bool:
    return (session or {}).get("email","") == ADMIN_EMAIL


def build_cache_diagnostics_panel():
    """
    Shows real, measured data about the background cache-refresh system:
    which backend is active (redis vs memory), and per-key last-refresh
    timestamp/duration/success. Built so future slow-spike reports can be
    diagnosed with actual evidence instead of guessing from browser
    Network-tab timings alone.
    """
    if shared_cache is None:
        return _admin_card([
            html.Div("Cache Diagnostics", style={"color":WHITE,"fontSize":"16px","fontWeight":"900","marginBottom":"8px"}),
            html.Div("shared_cache module did not import -- caching is fully disabled.", style={"color":RED_DIM,"fontSize":"12px"}),
        ])

    try:
        diag = shared_cache.get_diagnostics()
    except Exception as e:
        return _admin_card([
            html.Div("Cache Diagnostics", style={"color":WHITE,"fontSize":"16px","fontWeight":"900","marginBottom":"8px"}),
            html.Div(f"Error reading diagnostics: {e}", style={"color":RED_DIM,"fontSize":"12px"}),
        ])

    backend = diag.get("backend", "unknown")
    backend_color = TEAL_DIM if backend == "redis" else YELLOW_DIM

    rows = []
    for key, meta in sorted(diag.get("keys", {}).items()):
        success = meta.get("last_refresh_success")
        refreshed_at = meta.get("last_refreshed_at") or "never yet"
        duration = meta.get("last_refresh_duration_ms")
        error = meta.get("last_refresh_error")

        status_color = TEAL_DIM if success else (RED_DIM if success is False else YELLOW_DIM)
        status_text = "OK" if success else ("FAILED" if success is False else "PENDING")

        rows.append(html.Div([
            html.Span(key, style={"color":WHITE,"fontSize":"11px","flex":"2","fontFamily":"DM Mono, monospace"}),
            html.Span(status_text, style={"color":status_color,"fontSize":"11px","fontWeight":"800","flex":"0.6"}),
            html.Span(refreshed_at, style={"color":TEXT,"fontSize":"11px","flex":"1.2"}),
            html.Span(f"{duration}ms" if duration is not None else "-", style={"color":TEXT,"fontSize":"11px","flex":"0.6"}),
            html.Span(error or "", style={"color":RED_DIM,"fontSize":"10px","flex":"1.5"}),
        ], style={"display":"flex","gap":"8px","padding":"6px 0","borderBottom":f"1px solid {BORDER}"}))

    return _admin_card([
        html.Div([
            html.Span("Cache Diagnostics", style={"color":WHITE,"fontSize":"16px","fontWeight":"900"}),
            html.Span(f"  backend: {backend}", style={"color":backend_color,"fontSize":"12px","fontWeight":"800","marginLeft":"10px"}),
        ], style={"marginBottom":"12px"}),
        html.Div([
            html.Span("Key", style={"color":MUTED,"fontSize":"10px","fontWeight":"800","flex":"2","textTransform":"uppercase"}),
            html.Span("Status", style={"color":MUTED,"fontSize":"10px","fontWeight":"800","flex":"0.6","textTransform":"uppercase"}),
            html.Span("Last Refreshed", style={"color":MUTED,"fontSize":"10px","fontWeight":"800","flex":"1.2","textTransform":"uppercase"}),
            html.Span("Duration", style={"color":MUTED,"fontSize":"10px","fontWeight":"800","flex":"0.6","textTransform":"uppercase"}),
            html.Span("Error", style={"color":MUTED,"fontSize":"10px","fontWeight":"800","flex":"1.5","textTransform":"uppercase"}),
        ], style={"display":"flex","gap":"8px","paddingBottom":"6px","borderBottom":f"2px solid {BORDER}"}),
        html.Div(rows if rows else [html.Div("No background-refreshed keys registered yet.", style={"color":MUTED,"fontSize":"12px","padding":"12px 0"})]),
    ])


def build_admin_tab(session: dict, backend_url: str) -> html.Div:
    """
    Build the full admin monitoring page.
    Returns a 403 message if not admin.
    """
    if not is_admin(session):
        return html.Div([
            html.Div("", style={"fontSize":"48px","marginBottom":"16px"}),
            html.Div("Admin Access Only", style={"fontSize":"18px","fontWeight":"800","color":WHITE}),
            html.Div("This page is only accessible to the system administrator.",
                     style={"fontSize":"13px","color":WHITE,"marginTop":"8px"}),
        ], style={"textAlign":"center","padding":"80px 20px"})

    # ── Fetch report from backend ─────────────────────────────────────────
    try:
        token = session.get("access_token","")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        # FIX: was `_req.get(...)` -- _req is not defined at module scope in
        # this function (it only exists as a local import inside two other,
        # unrelated functions). This module already imports requests as `req`
        # at the top of the file; use that instead.
        def _do_fetch_admin_report():
            r = req.get(f"{backend_url}/api/admin/report", headers=headers, timeout=15)
            return r.json() if r.ok else {}

        data = (
            shared_cache.get_or_fetch("/api/admin/report", _do_fetch_admin_report, ttl_seconds=90)
            if shared_cache is not None
            else _do_fetch_admin_report()
        )
    except Exception as e:
        data = {}

    if not data:
        # FIX: was `_admin_card([...])` -- _card only exists as a local nested
        # function inside build_preferences_tab and is not visible here.
        # _admin_card is the real module-level equivalent already defined above.
        return _admin_card([
            html.Div("Could not load admin report.", style={"color":YELLOW_DIM,"fontSize":"14px"}),
            html.Div("Backend may be initializing. Refresh in 30 seconds.",
                     style={"color":WHITE,"fontSize":"12px","marginTop":"8px"}),
        ])

    live          = data.get("live_stats", {})
    accuracy      = data.get("accuracy_stats", {})
    snap_health   = data.get("snapshot_health", {})
    top_scores    = data.get("top_scores", [])
    top_movers    = data.get("top_movers", [])
    anomalies     = data.get("anomalies", [])
    narrative     = data.get("narrative","—")
    daily_grades  = data.get("daily_grades", [])
    regimes       = data.get("regime_distribution", {})
    generated_at  = data.get("generated_at","")

    # Format timestamp
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(generated_at.replace("Z","+00:00"))
        gen_label = dt.strftime("%b %d, %Y  %I:%M %p UTC")
    except:
        gen_label = generated_at

    # ── Header ────────────────────────────────────────────────────────────
    header = _admin_card([
        html.Div([
            html.Div([
                html.Div([
                    html.Span("", style={"fontSize":"18px"}),
                    html.Span("ADMIN PERFORMANCE MONITOR",
                              style={"fontSize":"16px","fontWeight":"900","color":GOLD,
                                     "letterSpacing":".08em"}),
                ], style={"display":"flex","alignItems":"center","gap":"8px","marginBottom":"4px"}),
                html.Div("Private · Internal Use Only · Sigmalytic Quant Corporation",
                         style={"fontSize":"11px","color":WHITE,"letterSpacing":".06em"}),
            ]),
            html.Div([
                html.Span(snap_health.get("status","—"), style={
                    "fontSize":"10px","fontWeight":"800",
                    "color": TEAL_DIM if "Active" in snap_health.get("status","") else YELLOW_DIM,
                    "border": f"1px solid {BORDER_T}","borderRadius":"999px",
                    "padding":"4px 12px","background":TEAL_GLOW,
                }),
                html.Div(f"Generated: {gen_label}",
                         style={"fontSize":"10px","color":WHITE,"marginTop":"4px","textAlign":"right"}),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start"}),
    ], sx={"borderColor": "rgba(245,200,66,.3)", "marginBottom":"16px"})

    # ── Accuracy stats block (mirrors your PDF scoreboard) ───────────────
    hit  = accuracy.get("hit_rate", 0)
    conf = accuracy.get("conf_rate", 0)
    neut = accuracy.get("neutral_rate", 0)
    miss = accuracy.get("miss_rate", 0)
    perf_num = accuracy.get("a_grade",0)
    perf_den = accuracy.get("total",0)

    accuracy_block = _admin_card([
        html.Div("CLOSED-LOOP PERFORMANCE AUDIT",
                 style={"fontSize":"10px","fontWeight":"900","color":GOLD,
                        "letterSpacing":".2em","textTransform":"uppercase","marginBottom":"16px"}),
        html.Div([
            _tile("CONF",  f"{conf:.0f}%", TEAL_DIM,  "A-grade rate"),
            _tile("HIT",   f"{hit:.0f}%",  TEAL_DIM,  "A + B rate"),
            _tile("NEUTRAL",f"{neut:.0f}%",YELLOW_DIM,"C rate"),
            _tile("MISS",  f"{miss:.0f}%", RED_DIM,   "F rate"),
            _tile("PERF",  f"{perf_num}/{perf_den}" if perf_den else "—",
                  GOLD,   "A grades / total"),
            _tile("SYMBOLS",str(live.get("total_symbols",0)), BLUE_DIM, "in universe"),
            _tile("ARMED",  str(live.get("armed",0)),   TEAL_DIM, "live now"),
            _tile("TRIGGERED",str(live.get("triggered",0)),BLUE_DIM,"live now"),
        ], style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"10px"}),
    ], sx={"marginBottom":"16px","borderColor":"rgba(245,200,66,.2)"})

    # ── Snapshot writer health ────────────────────────────────────────────
    snap_block = _admin_card([
        html.Div([
            html.Div("SNAPSHOT WRITER", style={"fontSize":"12px","fontWeight":"800",
                      "color":WHITE,"marginBottom":"4px"}),
            html.Div([
                html.Span("Status: ", style={"color":WHITE,"fontSize":"11px"}),
                html.Span(snap_health.get("status","—"),
                          style={"color": TEAL_DIM if "Active" in snap_health.get("status","") else YELLOW_DIM,
                                 "fontWeight":"700","fontSize":"11px"}),
                html.Span("  ·  Last write: ", style={"color":WHITE,"fontSize":"11px","marginLeft":"12px"}),
                html.Span(snap_health.get("last_write","—")[:19] if snap_health.get("last_write") else "—",
                          style={"color":WHITE,"fontSize":"11px"}),
                html.Span("  ·  Writes in last 10 min: ", style={"color":WHITE,"fontSize":"11px","marginLeft":"12px"}),
                html.Span(str(snap_health.get("recent_count",0)),
                          style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"11px"}),
            ]),
        ]),
    ], sx={"marginBottom":"16px","padding":"14px 20px"})

    # ── Narrative block ───────────────────────────────────────────────────
    narrative_block = _admin_card([
        html.Div("REGIME NARRATIVE", style={"fontSize":"10px","fontWeight":"900","color":GOLD,
                  "letterSpacing":".2em","marginBottom":"12px"}),
        html.Div(narrative, style={"fontSize":"14px","color":WHITE,"lineHeight":"1.7",
                                   "fontStyle":"italic"}),

        html.Div(style={"height":"16px"}),

        # Regime distribution pills
        html.Div("REGIME DISTRIBUTION", style={"fontSize":"10px","fontWeight":"700","color":WHITE,
                  "letterSpacing":".16em","marginBottom":"8px"}),
        html.Div([
            html.Div([
                html.Span(regime, style={"fontSize":"11px","fontWeight":"700","color":WHITE,
                                         "marginRight":"6px"}),
                html.Span(f"{count}", style={"fontSize":"11px","color":TEAL_DIM,"fontWeight":"900"}),
            ], style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                       "borderRadius":"999px","padding":"4px 12px","display":"inline-flex",
                       "alignItems":"center","marginRight":"6px","marginBottom":"4px"})
            for regime, count in sorted(regimes.items(), key=lambda x: x[1], reverse=True)
        ], style={"display":"flex","flexWrap":"wrap"}),
    ], sx={"marginBottom":"16px"})

    # ── Anomaly flags ─────────────────────────────────────────────────────
    anomaly_rows = []
    for a in anomalies:
        sev_color = _severity_color(a.get("severity","INFO"))
        anomaly_rows.append(html.Div([
            html.Span(a.get("severity",""), style={
                "fontSize":"9px","fontWeight":"900","color":sev_color,
                "border":f"1px solid {sev_color}","borderRadius":"4px",
                "padding":"2px 6px","marginRight":"10px","minWidth":"40px",
                "textAlign":"center","display":"inline-block",
            }),
            html.Span(a.get("symbol",""), style={
                "fontSize":"11px","fontWeight":"800","color":WHITE,
                "fontFamily":"monospace","marginRight":"10px","minWidth":"60px",
                "display":"inline-block",
            }),
            html.Span(a.get("message",""), style={"fontSize":"12px","color":WHITE}),
        ], style={"padding":"8px 0","borderBottom":f"1px solid {BORDER}",
                  "display":"flex","alignItems":"center"}))

    anomaly_block = _admin_card([
        html.Div([
            html.Div("ANOMALY FLAGS", style={"fontSize":"12px","fontWeight":"800","color":WHITE}),
            html.Div(f"{len(anomalies)} issues detected",
                     style={"fontSize":"11px","color": RED_DIM if anomalies else TEAL_DIM}),
        ], style={"display":"flex","justifyContent":"space-between","marginBottom":"12px"}),
        html.Div(anomaly_rows if anomaly_rows else [
            html.Div("No anomalies detected — system running clean.",
                     style={"color":TEAL_DIM,"fontSize":"13px","padding":"12px 0"})
        ]),
    ], sx={"marginBottom":"16px"})

    # ── Top 10 scores table ───────────────────────────────────────────────
    def _sym_row(s):
        score = s.get("composite_score", 0)
        sc    = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 50 else RED_DIM)
        chg   = s.get("change_pct", 0)
        return html.Div([
            html.Span(s.get("symbol",""), style={
                "flex":"1","fontWeight":"800","fontSize":"13px","color":WHITE,
                "fontFamily":"monospace",
            }),
            html.Span(f"${s.get('price',0):,.2f}", style={
                "flex":"1","fontSize":"12px","color":WHITE,
            }),
            html.Span(f"{chg:+.2f}%", style={
                "flex":"1","fontSize":"12px","fontWeight":"700",
                "color": TEAL_DIM if chg >= 0 else RED_DIM,
            }),
            html.Div([
                html.Span(f"{score:.0f}", style={"fontSize":"13px","fontWeight":"900","color":sc}),
                _score_bar(score, width="80px"),
            ], style={"flex":"1"}),
            html.Span(f"C:{s.get('confluence',0):.0f} E:{s.get('expansion_node',0):.0f} "
                      f"RS:{s.get('relative_strength',0):.0f} VP:{s.get('volume_pressure',0):.0f} "
                      f"B:{s.get('behavioral',0):.0f}",
                      style={"flex":"2","fontSize":"10px","color":sc,"fontFamily":"monospace"}),
            html.Span(s.get("status",""), style={
                "flex":"1","fontSize":"10px","fontWeight":"700","color":sc,
            }),
            html.Span(s.get("regime",""), style={
                "flex":"1","fontSize":"10px","color":WHITE,
            }),
        ], style={"display":"flex","alignItems":"center","gap":"12px",
                  "padding":"10px 0","borderBottom":f"1px solid {BORDER}"})

    score_table = _admin_card([
        html.Div("TOP 10 — COMPOSITE SCORE", style={"fontSize":"12px","fontWeight":"800",
                  "color":WHITE,"marginBottom":"12px"}),
        # Header
        html.Div([
            html.Span("Symbol",   style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Price",    style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Chg%",     style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Score",    style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Dimensions (C E RS VP B)", style={"flex":"2","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Status",   style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Regime",   style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        ], style={"display":"flex","gap":"12px","paddingBottom":"8px",
                  "borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),
        html.Div([_sym_row(s) for s in top_scores]),
    ], sx={"marginBottom":"16px"})

    # ── Historical daily grade grid ────────────────────────────────────────
    # Get all unique symbols across all dates
    all_syms_set = set()
    for day in daily_grades:
        all_syms_set.update(day.get("symbols",{}).keys())
    all_syms = sorted(all_syms_set)

    if daily_grades and all_syms:
        # Table header row — dates
        date_headers = [
            html.Th("Symbol", style={"padding":"6px 10px","textAlign":"left",
                                      "fontSize":"9px","color":WHITE,"fontWeight":"700",
                                      "textTransform":"uppercase","letterSpacing":".1em",
                                      "background":NAVY_MID,"position":"sticky","left":0}),
        ] + [
            html.Th(day["date"][5:],  # MM-DD
                    style={"padding":"6px 10px","textAlign":"center","minWidth":"56px",
                           "fontSize":"9px","color":WHITE,"fontWeight":"700",
                           "textTransform":"uppercase","letterSpacing":".06em",
                           "background":NAVY_MID})
            for day in daily_grades
        ]

        # Symbol rows
        table_rows = []
        for sym in all_syms:
            cells = [
                html.Td(sym, style={"padding":"6px 10px","fontWeight":"800","fontSize":"12px",
                                     "color":WHITE,"fontFamily":"monospace",
                                     "background":NAVY_MID,"position":"sticky","left":0,
                                     "borderRight":f"1px solid {BORDER}"}),
            ]
            for day in daily_grades:
                sym_data = day.get("symbols",{}).get(sym)
                if sym_data:
                    grade = sym_data.get("grade","—")
                    gc    = _grade_color(grade)
                    cells.append(html.Td(
                        html.Div([
                            html.Div(grade or "—", style={"fontSize":"12px","fontWeight":"900",
                                                           "color":gc,"lineHeight":"1"}),
                            html.Div(f"{sym_data.get('score',0):.0f}",
                                     style={"fontSize":"9px","color":WHITE,"marginTop":"2px"}),
                        ], style={"textAlign":"center"}),
                        style={"padding":"5px 8px","background":f"{gc}12",
                               "borderLeft":f"1px solid rgba(255,255,255,.04)"},
                    ))
                else:
                    cells.append(html.Td("—", style={"padding":"5px 8px","textAlign":"center",
                                                       "color":WHITE,"fontSize":"11px"}))
            table_rows.append(html.Tr(cells, style={"borderBottom":f"1px solid {BORDER}"}))

        grade_grid = _admin_card([
            html.Div([
                html.Div("CUMULATIVE SCOREBOARD — DAILY GRADE GRID",
                         style={"fontSize":"12px","fontWeight":"800","color":WHITE}),
                html.Div("Grade / Score · A=Full target · B=Partial · C=Neutral · F=Miss",
                         style={"fontSize":"10px","color":WHITE,"marginTop":"4px"}),
            ], style={"marginBottom":"16px"}),
            html.Div([
                html.Table([
                    html.Thead(html.Tr(date_headers,
                               style={"borderBottom":f"1px solid {BORDER}"})),
                    html.Tbody(table_rows),
                ], style={"width":"100%","borderCollapse":"collapse",
                          "fontSize":"12px","color":WHITE}),
            ], style={"overflowX":"auto","maxHeight":"480px","overflowY":"auto",
                      "border":f"1px solid {BORDER}","borderRadius":"10px"}),

            html.Div([
                html.Span("* Starred dates = Pinning Report validation days",
                          style={"fontSize":"10px","color":WHITE,"fontStyle":"italic"}),
            ], style={"marginTop":"12px"}),
        ], sx={"marginBottom":"16px"})
    else:
        grade_grid = _admin_card([
            html.Div("CUMULATIVE SCOREBOARD", style={"fontSize":"12px","fontWeight":"800",
                      "color":WHITE,"marginBottom":"8px"}),
            html.Div("No daily close snapshots yet. The grade grid will populate automatically "
                     "after 4:15 PM ET on the first trading day with the snapshot writer active.",
                     style={"fontSize":"13px","color":WHITE,"lineHeight":"1.7"}),
        ], sx={"marginBottom":"16px"})

    # ── Assemble full page ────────────────────────────────────────────────
    return html.Div([
        header,
        accuracy_block,
        snap_block,
        narrative_block,

        # Two-column row: anomalies + top scores
        html.Div([
            html.Div(anomaly_block, style={"flex":"1","minWidth":"0"}),
        ], style={"marginBottom":"0"}),

        score_table,
        grade_grid,

        # Footer
        html.Div("SIGMALYTIC QUANT CORPORATION  ·  PROPRIETARY & CONFIDENTIAL  ·  INTERNAL USE ONLY",
                 style={"textAlign":"center","fontSize":"9px","color":WHITE,
                        "letterSpacing":".2em","paddingTop":"16px","paddingBottom":"8px"}),
    ])




def build_setup_tab():
    return card([
        html.H2("Setup & Deployment",style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Pre(
            f"Frontend  : Dash (Python)  →  Render\n"
            f"Backend   : FastAPI        →  Render\n"
            f"Data      : Alpaca IEX (free) / SIP (paid)\n"
            f"WebSocket : {BACKEND_WS}/ws/{{symbol}}\n"
            f"REST      : {BACKEND_HTTP}/api/stock/{{symbol}}\n"
            f"Behavior  : {BACKEND_HTTP}/api/behavior/*\n\n"
            f"Env vars:\n"
            f"  ALPACA_API_KEY     — Alpaca key ID\n"
            f"  ALPACA_API_SECRET  — Alpaca secret\n"
            f"  BACKEND_URL        — HTTP base URL\n"
            f"  BACKEND_WS_URL     — WebSocket base URL\n"
            f"  BEHAVIOR_DB        — SQLite path (default: behavior.db)",
            style={"margin":"0","borderRadius":"14px","border":f"1px solid {BORDER}",
                   "background":"rgba(0,0,0,.35)","padding":"16px","color":TEAL_DIM,
                   "fontSize":"12px","fontFamily":"DM Mono, monospace","lineHeight":"1.7"}),
    ])

# ── App ────────────────────────────────────────────────────────────────────────

LOGO = html.Div([
    html.Div("Σ",style={"fontSize":"28px","fontWeight":"900","color":TEAL_DIM,"lineHeight":"1",
                         "fontFamily":"Georgia, serif","marginRight":"4px","flexShrink":"0"}),
    html.Div([
        html.Span("SIGMALYTIC",style={"fontSize":"18px","fontWeight":"900","color":WHITE,"letterSpacing":".08em","lineHeight":"1"}),
        html.Span("QUANT CORPORATION",style={"fontSize":"9px","fontWeight":"700","color":TEAL_DIM,"letterSpacing":".22em","display":"block","marginTop":"2px"}),
    ]),
], style={"display":"flex","alignItems":"center","gap":"10px"})

app = dash.Dash(__name__, title="Sigmalytic Quant Corporation — Decision Intelligence",
                update_title=None, suppress_callback_exceptions=True,
                meta_tags=[{"name":"viewport","content":"width=device-width, initial-scale=1"},
                           {"name":"theme-color","content":NAVY}])
server = app.server

# Allow Stripe scripts and iframes via CSP
@server.after_request
def add_csp_headers(response):
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://js.stripe.com https://cdn.jsdelivr.net; "
        "frame-src 'self' https://js.stripe.com https://hooks.stripe.com; "
        "connect-src 'self' https://api.stripe.com; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:;"
    )
    return response

app.index_string = f"""<!DOCTYPE html>
<html><head>{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}
<style>{GLOBAL_CSS}
.prob-pill {{
    border: 1px solid rgba(148,163,184,.24);
    background: rgba(15,35,55,.70);
    color: #FFFFFF !important;
    border-radius: 999px;
    padding: 6px 9px;
    font-size: 12px;
    font-weight: 700;
}}
</style></head>
<body>{{%app_entry%}}<footer>{{%config%}}</footer>{{%scripts%}}{{%renderer%}}
<script>
window._sigmaAudioCtx = null;
function _getAudioCtx() {{
    if (!window._sigmaAudioCtx) {{
        window._sigmaAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }}
    return window._sigmaAudioCtx;
}}
function sigmaBeep(freq, duration, gain) {{
    try {{
        var ctx = _getAudioCtx();
        var osc = ctx.createOscillator();
        var vol = ctx.createGain();
        osc.connect(vol);
        vol.connect(ctx.destination);
        osc.frequency.value = freq;
        osc.type = 'sine';
        vol.gain.setValueAtTime(gain || 0.3, ctx.currentTime);
        vol.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + duration);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + duration);
    }} catch(e) {{ console.warn('Audio error:', e); }}
}}
function sigmaAlert(level) {{
    if (level === 'A') {{
        // Three rising tones — A grade signal
        sigmaBeep(523, 0.15, 0.4);
        setTimeout(function(){{ sigmaBeep(659, 0.15, 0.4); }}, 160);
        setTimeout(function(){{ sigmaBeep(784, 0.3,  0.5); }}, 320);
    }} else if (level === 'B') {{
        // Two tones — B tactical
        sigmaBeep(440, 0.15, 0.3);
        setTimeout(function(){{ sigmaBeep(554, 0.25, 0.35); }}, 180);
    }} else if (level === 'warn') {{
        // Single low tone — warning / trap door
        sigmaBeep(220, 0.4, 0.3);
    }}
}}
// Called by Dash clientside callback
window.dash_clientside = window.dash_clientside || {{}};
window.dash_clientside.sigmalytic = {{
    fireAlert: function(score, prev_score, alerts_on) {{
        if (!alerts_on) return window.dash_clientside.no_update;
        if (score >= 80 && prev_score < 80) {{ sigmaAlert('A'); }}
        else if (score >= 55 && prev_score < 55) {{ sigmaAlert('B'); }}
        else if (score < 35 && prev_score >= 35) {{ sigmaAlert('warn'); }}
        return score;
    }}
}};
</script>
</body></html>"""

_init_live    = create_live_update("AAPL", 280.15, 750_000, 0).to_dict()
_init_candles = fetch_real_candles("AAPL", "5m")

ALL_TABS = [
    ("home",        "Home"),
    ("command",     "Command Center"),
    ("campaign",    "Campaign Intelligence"),
    ("feed",        "Live Feed"),
    ("performance", "Performance"),
    ("behavior",    "Behavioral Intelligence"),
    ("import",      "Import History"),
    ("radar",       "Radar Screen"),
    ("scoreboard",  "Scoreboard"),
    ("divergence",  "Intelligence Change Detector"),
    ("portfolio",   "Portfolio"),
    ("journal",     "Journal"),
    ("billing",     "Billing"),
    ("preferences", "Preferences"),
    ("admin",       "Admin"),
    ("setup",       "Setup"),
    ("status",      "Status"),
]

app.layout = html.Div([
    dcc.Location(id="url", refresh=True),
    html.Div(id="auth-overlay", children=build_login_page(),
             style={"position":"fixed","top":0,"left":0,"right":0,"bottom":0,
                    "zIndex":9999,"background":"#0a1628","overflowY":"auto"}),
    dcc.Store(id="s-live",      data=_init_live),
    dcc.Store(id="s-session",    data=None, storage_type="session"),
    dcc.Store(id="s-page",       data="login"), 
    dcc.Store(id="s-candles",   data=_init_candles),
    dcc.Store(id="s-seq",       data=0),
    dcc.Store(id="s-live-mode", data=True),
    dcc.Store(id="s-symbol",    data="AAPL"),
    dcc.Store(id="s-tf",        data="5m"),
    dcc.Store(id="s-tab",       data="home"),
    dcc.Store(id="s-alert-score",    data=0),
    dcc.Store(id="s-alerts-on",      data=True),
    dcc.Store(id="s-current-plan-id",data=None),
    dcc.Store(id="s-plan-score",     data=0),
    dcc.Store(id="s-plan-regime",    data="neutral"),
    dcc.Store(id="tp-direction",     data="long"),
    html.Div(id="audio-trigger", style={"display":"none"}),
    dcc.Interval(id="i-alpaca", interval=20_000, n_intervals=0),
    dcc.Interval(id="i-clock",  interval=5_000, n_intervals=0),

    html.Div([html.Div([
        html.Header([
            # ── Compact single-row header ──────────────────────────────────
            html.Div([
                LOGO,
                html.Div([
                    html.H1("Decision Command Center",
                            style={"fontSize":"22px","fontWeight":"900","color":WHITE,
                                   "letterSpacing":"-.02em","margin":"0"}),
                    html.Div([
                        html.Span(id="b-connected"),
                        html.Span(id="b-feed"),
                        html.Span(id="b-tick"),
                    ], style={"display":"flex","gap":"6px","marginTop":"4px"}),
                ], style={"textAlign":"center"}),
                html.Div([
                    html.Div(id="sim-label", style={"display":"none"}),
                    html.Button("Log Out", id="btn-logout", n_clicks=0,
                        style={"background":"rgba(239,68,68,.1)","border":"1px solid rgba(239,68,68,.3)",
                               "borderRadius":"10px","color":"#f87171","cursor":"pointer",
                               "fontSize":"11px","fontWeight":"700","padding":"6px 12px",
                               "fontFamily":"DM Sans, sans-serif"}),
                ], style={"display":"flex","alignItems":"center","gap":"8px"}),
            ], style={"display":"flex","justifyContent":"space-between","alignItems":"center",
                       "width":"100%","marginBottom":"8px"}),

            # ── Controls row ───────────────────────────────────────────────
            html.Div([
                dcc.Input(id="ticker-input", value="AAPL", debounce=False,
                          style={"background":NAVY_MID,"color":WHITE,"border":f"1px solid {BORDER}",
                                 "borderRadius":"12px","padding":"10px 14px","width":"110px",
                                 "fontSize":"14px","fontWeight":"700"}),
                html.Button("Load Symbol", id="btn-load", n_clicks=0,
                            style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
                                   "borderRadius":"12px","padding":"10px 18px","fontSize":"13px","fontWeight":"800"}),
                html.Div(id="price-ctrl"),
                html.Div([
                    html.Button("1m",  id="tf-1m",  n_clicks=0, style=_tf_btn_style("1m",  "5m")),
                    html.Button("5m",  id="tf-5m",  n_clicks=0, style=_tf_btn_style("5m",  "5m")),
                    html.Button("15m", id="tf-15m", n_clicks=0, style=_tf_btn_style("15m", "5m")),
                    html.Button("1H",  id="tf-1H",  n_clicks=0, style=_tf_btn_style("1H",  "5m")),
                    html.Button("1D",  id="tf-1D",  n_clicks=0, style=_tf_btn_style("1D",  "5m")),
                    html.Button("1W",  id="tf-1W",  n_clicks=0, style=_tf_btn_style("1W",  "5m")),
                ], style={"display":"flex","gap":"2px","padding":"4px","background":NAVY_MID,
                           "border":f"1px solid {BORDER}","borderRadius":"12px"}),
            ], style={"display":"flex","flexWrap":"wrap","alignItems":"center",
                       "justifyContent":"center","gap":"10px"}),
        ], style={"display":"flex","flexDirection":"column","alignItems":"center",
                   "gap":"8px","paddingBottom":"0"}),

        html.Nav([
            html.Button(label, id=f"tab-{key}", n_clicks=0,
                        style={"background":"transparent","color":WHITE,"border":"none","borderRadius":"10px",
                               "padding":"10px 20px","fontSize":"13px","fontWeight":"700","whiteSpace":"nowrap"})
            for key, label in ALL_TABS
        ], style={"display":"flex","gap":"4px","padding":"4px","borderRadius":"14px",
                   "background":NAVY_MID,"border":f"1px solid {BORDER}",
                   # FIX (2026-07-25): was justifyContent:"center". With 17 tabs
                   # (~2200px of button width) exceeding any real viewport, centering
                   # pushed the FIRST tabs (Home, Command Center) off-screen to the
                   # left by default -- the browser centers the whole overflowing row,
                   # not just what fits. flex-start makes the tab bar begin at Home/
                   # Command Center as expected, with horizontal scroll available to
                   # reach later tabs -- the standard pattern for overflowing tab bars.
                   "justifyContent":"flex-start","overflowX":"auto"}),

        html.Main(id="main-content"),

        # ── Trade plan + active trade — ALL inputs permanent, never recreated ──
        html.Div([
            # Trade plan card — header updates, inputs are static
            html.Div([
                html.Div(id="trade-plan-panel", style={"marginBottom":"16px"}),
                html.Div([
                    slabel("Direction"),
                    html.Div([
                        html.Button("Long",    id="dir-long",    n_clicks=0,
                            style={"flex":"1","padding":"9px 0","fontSize":"13px","fontWeight":"800",
                                   "cursor":"pointer","fontFamily":"inherit","borderRadius":"8px 0 0 8px",
                                   "border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM}),
                        html.Button("Short",   id="dir-short",   n_clicks=0,
                            style={"flex":"1","padding":"9px 0","fontSize":"13px","fontWeight":"700",
                                   "cursor":"pointer","fontFamily":"inherit","borderRadius":"0",
                                   "border":f"1px solid {BORDER}","borderLeft":"none","borderRight":"none",
                                   "background":"transparent","color":WHITE}),
                        html.Button("Neutral", id="dir-neutral", n_clicks=0,
                            style={"flex":"1","padding":"9px 0","fontSize":"13px","fontWeight":"700",
                                   "cursor":"pointer","fontFamily":"inherit","borderRadius":"0 8px 8px 0",
                                   "border":f"1px solid {BORDER}","background":"transparent","color":WHITE}),
                    ], style={"display":"flex","width":"100%"}),
                ], style={"marginBottom":"12px"}),
                html.Div([
                    html.Div([slabel("Entry Price"),
                              dcc.Input(id="tp-entry", value="0.00", debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                    html.Div([slabel("Stop"),
                              dcc.Input(id="tp-stop",  value="0.00", debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                ], style={"display":"flex","gap":"12px","marginBottom":"12px"}),
                html.Div([
                    html.Div([slabel("Target"),
                              dcc.Input(id="tp-target", value="0.00", debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                    html.Div([slabel("Size"),
                              dcc.Input(id="tp-size",   value="100",  debounce=True, style=_input_style())],
                             style={"flex":"1"}),
                ], style={"display":"flex","gap":"12px","marginBottom":"12px"}),
                html.Div([
                    slabel("Setup Notes"),
                    dcc.Textarea(id="tp-notes", value="", placeholder="Why this setup?",
                        style={**_input_style(),"height":"60px","resize":"vertical","lineHeight":"1.5"}),
                ], style={"marginBottom":"16px"}),
                html.Div([
                    _btn("Save Plan",   "btn-save-plan"),
                    _btn("Enter Trade", "btn-enter-trade",
                         color=WHITE, bg=WHITE, border=BORDER, extra={"color":NAVY}),
                ], style={"display":"flex","gap":"10px"}),
                html.Div(id="tp-status", style={"marginTop":"10px","fontSize":"12px","color":TEAL_DIM}),
            ], style={"flex":"1","minWidth":"0","background":NAVY_CARD,"border":f"1px solid {BORDER}",
                       "borderRadius":"20px","padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)"}),

            # Active trade panel
            html.Div(id="active-trade-panel", style={"flex":"1","minWidth":"0"}),
        ], id="trade-panels-row",
           style={"display":"none","gap":"16px","alignItems":"start"}),

    ], style={"maxWidth":"1440px","margin":"0 auto","display":"flex","flexDirection":"column","gap":"16px"})],
    style={"minHeight":"100vh","background":NAVY,"padding":"24px"}),
], style={"margin":"0","background":NAVY})

# ── Callbacks ──────────────────────────────────────────────────────────────────

@app.callback(
    Output("s-tf","data"), Output("s-candles","data",allow_duplicate=True),
    Output("s-seq","data",allow_duplicate=True),
    Output("tf-1m","style"), Output("tf-5m","style"), Output("tf-15m","style"),
    Output("tf-1H","style"), Output("tf-1D","style"), Output("tf-1W","style"),
    Input("tf-1m","n_clicks"), Input("tf-5m","n_clicks"), Input("tf-15m","n_clicks"),
    Input("tf-1H","n_clicks"), Input("tf-1D","n_clicks"), Input("tf-1W","n_clicks"),
    State("s-live","data"), prevent_initial_call=True,
)
def select_tf(_1m,_5m,_15m,_1H,_1D,_1W, live):
    ctx = callback_context
    if not ctx.triggered:
        return (no_update,)*9
    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    new_tf = btn_id.replace("tf-","")
    symbol = live.get("symbol", "AAPL") if live else "AAPL"
    price  = live.get("price", 0) if live else 0
    fresh  = fetch_real_candles(symbol, new_tf)
    # Track event
    if live:
        _track("timeframe_changed", live.get("symbol",""), price=price, timeframe=new_tf,
               regime=_regime_from_live(live),
               decision_score=live.get("decision",{}).get("score"),
               decision_status=live.get("decision",{}).get("status"))
    s0=_tf_btn_style("1m",new_tf); s1=_tf_btn_style("5m",new_tf); s2=_tf_btn_style("15m",new_tf)
    s3=_tf_btn_style("1H",new_tf); s4=_tf_btn_style("1D",new_tf); s5=_tf_btn_style("1W",new_tf)
    return new_tf, fresh, 0, s0, s1, s2, s3, s4, s5

# Live-only mode — no toggle callback needed

@app.callback(
    Output("s-symbol","data"),
    Output("ticker-input","value"),
    Output("s-candles","data", allow_duplicate=True),
    Input("btn-load","n_clicks"),
    State("ticker-input","value"),
    State("s-live","data"),
    State("s-tf","data"),
    prevent_initial_call=True,
)
def load_symbol(_, ticker, live, tf):
    clean = sanitize_symbol(ticker or "")
    if not clean:
        return no_update, no_update, no_update

    price = live["price"] if live else 0
    _track("symbol_loaded", clean, price=price,
           decision_score=live.get("decision",{}).get("score") if live else None)

    fresh = fetch_real_candles(clean, tf or "5m")
    return clean, clean, fresh

@app.callback(
    Output("s-tab","data"),
    Input("tab-home","n_clicks"),         Input("tab-command","n_clicks"),      Input("tab-campaign","n_clicks"),
    Input("tab-feed","n_clicks"),
    Input("tab-performance","n_clicks"),  Input("tab-behavior","n_clicks"),
    Input("tab-import","n_clicks"),       Input("tab-radar","n_clicks"),
    Input("tab-scoreboard","n_clicks"),   Input("tab-divergence","n_clicks"),
    Input("tab-portfolio","n_clicks"),    Input("tab-journal","n_clicks"),
    Input("tab-billing","n_clicks"),      Input("tab-preferences","n_clicks"),
    Input("tab-admin","n_clicks"),        Input("tab-setup","n_clicks"),
    Input("tab-status","n_clicks"),
    prevent_initial_call=True,
)
def set_tab(*_):
    ctx = callback_context
    if not ctx.triggered: return no_update
    tab = ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")
    return tab


# SIGMALYTIC_STEP100R_L3_ACTIVE_TAB_STYLE_SYNC
@app.callback(
    [Output(f"tab-{key}", "style") for key, _label in ALL_TABS],
    Input("s-tab", "data"),
)
def sync_active_tab_styles(active_tab):
    active_tab = active_tab or "home"

    base = {
        "borderRadius": "999px",
        "padding": "8px 13px",
        "fontSize": "12px",
        "fontWeight": "800",
        "cursor": "pointer",
        "fontFamily": "DM Sans, sans-serif",
        "transition": "background .12s ease, border-color .12s ease, color .12s ease",
        "whiteSpace": "nowrap",
    }

    active_style = dict(base)
    active_style.update({
        "background": "rgba(20,184,166,.22)",
        "border": f"1px solid {BORDER_T}",
        "color": TEAL_DIM,
        "boxShadow": "0 0 0 1px rgba(20,184,166,.10)",
    })

    inactive_style = dict(base)
    inactive_style.update({
        "background": "rgba(15,23,42,.62)",
        "border": f"1px solid {BORDER}",
        "color": WHITE,
        "boxShadow": "none",
    })

    return [active_style if key == active_tab else inactive_style for key, _label in ALL_TABS]

@app.callback(
    Output("s-live","data"),
    Output("s-seq","data",allow_duplicate=True),
    Output("s-candles","data",allow_duplicate=True),
    Input("i-alpaca","n_intervals"),
    State("s-live","data"), State("s-seq","data"), State("s-candles","data"),
    State("s-live-mode","data"), State("s-symbol","data"), State("s-tf","data"),
    prevent_initial_call=True,
)
def on_tick(_, current, seq, candles, live_mode, symbol, tf):
    """
    Live price refresh + real candle bucket behavior.

    Important:
    - Does NOT create a new candle on every tick.
    - Updates only the active candle's high/low/close while the selected timeframe is still open.
    - Appends a new candle only when the selected timeframe rolls over.
    """
    clean = sanitize_symbol(symbol or "AAPL") or "AAPL"

    try:
        r = req.get(f"{BACKEND_HTTP}/api/stock/{clean}", timeout=4)
        r.raise_for_status()
        d      = r.json()
        price  = float(d["price"])
        volume = int(d.get("volume", 0) or 0)
        tick_time = d.get("timestamp") or datetime.now(timezone.utc).isoformat()
    except Exception:
        return no_update, no_update, no_update

    new_seq = (seq or 0) + 1

    # Preserve backend decision/confluence if present. Fall back to local engine output.
    fallback_live = create_live_update(clean, price, volume, new_seq).to_dict()
    new_live = {
        **fallback_live,
        "symbol": clean,
        "price": price,
        "volume": volume,
        "timestamp": tick_time,
        "sequence": new_seq,
        "source": d.get("source", "alpaca"),
    }
    if d.get("decision"):
        new_live["decision"] = d.get("decision")
    if d.get("confluence"):
        new_live["confluence"] = d.get("confluence")

    # If the candle store is empty, fetch real history once.
    if not candles:
        candles = fetch_real_candles(clean, tf or "5m")

    new_candles = update_current_candle(
        candles=candles or [],
        price=price,
        volume=volume,
        tick_time=tick_time,
        tf=tf or "5m",
    )

    return new_live, new_seq, new_candles
@app.callback(
    Output("price-ctrl","children"),
    Input("s-live-mode","data"), Input("s-live","data"),
)
def render_price_ctrl(live_mode, live):
    price=live["price"] if live else 280.15
    return html.Div([
        html.Span("LIVE PRICE",style={"fontSize":"10px","color":WHITE,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".12em"}),
        html.Strong(f"${price:.2f}",style={"fontSize":"17px","color":WHITE,"fontWeight":"900"}),
    ], style={"background":NAVY_MID,"border":f"1px solid {BORDER_T}","borderRadius":"12px",
               "padding":"8px 14px","width":"130px","minHeight":"50px","display":"flex","flexDirection":"column","justifyContent":"center"})

@app.callback(
    Output("b-connected","children"), Output("b-feed","children"), Output("b-tick","children"),
    Input("s-live","data"),
)
def update_badges(live):
    seq = live["sequence"] if live else 0
    return (badge("LIVE","teal"),
            badge("Alpaca IEX","blue"),
            badge(f"Tick #{seq}","yellow"))

@app.callback(
    Output("main-content",       "children"),
    Output("trade-panels-row",   "style"),
    Output("trade-plan-panel",   "children"),
    Output("active-trade-panel", "children"),
    Input("s-tab","data"),
    State("s-live","data"),
    State("s-candles","data"),
    State("s-live-mode","data"),
    State("s-symbol","data"),
    State("s-tf","data"),
    State("s-session","data"),
)
def render_main(tab,live,candles,live_mode,symbol,tf,session=None):
    HIDDEN = {"display":"none"}
    SHOWN  = {"display":"flex","gap":"16px","alignItems":"start"}

    if not live:
        live = _init_live

    if not candles:
        candles = _init_candles

    if tab == "home":
        main = card([
            html.Div("Sigmalytic V2", style={
                "color": TEAL_DIM,
                "fontSize": "13px",
                "fontWeight": "900",
                "letterSpacing": ".18em",
                "textTransform": "uppercase",
                "marginBottom": "8px",
            }),
            html.H2("Decision Intelligence Ready", style={
                "color": WHITE,
                "fontSize": "22px",
                "fontWeight": "900",
                "margin": "0 0 10px 0",
            }),
            html.Div(
                "Select Campaign Intelligence, Radar, Scoreboard, Divergence, Billing, Preferences, or Admin from the tabs above.",
                style={
                    "color": WHITE,
                    "fontSize": "13px",
                    "lineHeight": "1.6",
                    "opacity": ".9",
                },
            ),
            html.Div("Fast-load shell only. No campaign fetch, no backend write, no Supabase mutation, no D3D, no Stripe.", style={
                "color": TEAL_DIM,
                "fontSize": "11px",
                "fontWeight": "800",
                "marginTop": "14px",
                "textTransform": "uppercase",
                "letterSpacing": ".08em",
            }),
        ])
        return main, HIDDEN, no_update, no_update

    if tab == "command":
        open_trade  = _get(f"/api/behavior/open-trade/{USER_ID}")
        trade_plan  = _build_trade_plan_contents(live)
        active_pane = build_active_trade_panel(open_trade, live["price"]) if open_trade else html.Div()
        return (html.Div([
                    build_weis_gamma_status_center_panel(),
                    build_command_tab(live, candles or _init_candles, symbol, tf),
                ], style={"display":"flex","flexDirection":"column","gap":"16px"}),
                SHOWN, trade_plan, active_pane)

    if tab=="campaign":
        if build_campaign_tab is None:
            main = card([
                html.H2("Campaign Intelligence", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Campaign module is present but did not import. Check frontend/campaign_tab.py.", "blue"),
            ])
        else:
            try:
                main = build_campaign_tab(session=session)
            except TypeError:
                try:
                    main = build_campaign_tab()
                except Exception as e:
                    main = card([
                        html.H2("Campaign Intelligence", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                        note_box("Campaign module loading error: " + str(e), "blue"),
                    ])
            except Exception as e:
                main = card([
                    html.H2("Campaign Intelligence", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                    note_box("Campaign module loading error: " + str(e), "blue"),
                ])
    elif tab=="feed":          main = build_feed_tab(live,live_mode)
    elif tab=="performance": main = build_performance_tab(live)
    elif tab=="behavior":    main = build_behavior_tab()
    elif tab=="import":      main = build_import_tab()
    elif tab=="radar":       main = build_radar_tab(session=session)
    elif tab=="scoreboard":  main = build_scoreboard_tab(session=None)
    elif tab=="divergence":  main = build_divergence_tab(session=None)
    elif tab=="portfolio":
        if build_portfolio_tab is None:
            main = card([
                html.H2("Portfolio", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Portfolio module is present but did not import. Check frontend/portfolio_tab.py.", "blue"),
            ])
        else:
            try:
                main = build_portfolio_tab(session=session)
            except Exception as e:
                main = card([
                    html.H2("Portfolio", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                    note_box("Portfolio tab error: " + str(e), "blue"),
                ])
    elif tab=="journal":
        if build_trade_journal_tab is None:
            main = card([
                html.H2("Journal", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Journal module is present but did not import. Check frontend/trade_journal_tab.py.", "blue"),
            ])
        else:
            try:
                main = build_trade_journal_tab(session=session)
            except Exception as e:
                main = card([
                    html.H2("Journal", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                    note_box("Journal tab error: " + str(e), "blue"),
                ])
    elif tab=="status":
        if build_status_center is None:
            main = card([
                html.H2("Status", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Status Center module is present but did not import. Check frontend/status_center.py.", "blue"),
            ])
        else:
            try:
                main = build_status_center(session=session)
            except Exception as e:
                main = card([
                    html.H2("Status", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                    note_box("Status Center error: " + str(e), "blue"),
                ])
    elif tab=="billing":
        try:
            main = build_billing_tab(session=None, perms=None)
        except Exception as e:
            main = card([
                html.H2("Billing", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box(f"Billing module loading. Please refresh in a moment.", "blue"),
            ])
    elif tab=="preferences":
        try:
            main = build_preferences_tab(user_id="", session=None)
        except Exception as e:
            main = card([
                html.H2("️ Preferences", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Preferences loading. Please refresh in a moment.", "blue"),
            ])
    elif tab=="admin":
        try:
            admin_session = session if isinstance(session, dict) else {}
            main = html.Div([
                # D3F.1B: developer/audit-only safety verification panel.
                # Moved here from a global page-wide mount (was showing on
                # every tab) since this is an internal diagnostic tool, not
                # customer-facing content.
                _build_d3f1b_controlled_persistence_lifecycle_panel(),
                # Weis-Gamma Status Center panel intentionally NOT repeated
                # here -- it already lives on Command Center. Showing it
                # twice was redundant, not intentional. (Re-applied here --
                # this exact fix was lost once already during an earlier
                # file handoff tonight.)
                build_cache_diagnostics_panel(),
                build_admin_tab(session=admin_session, backend_url=BACKEND_HTTP),
            ], style={"display":"flex","flexDirection":"column","gap":"16px"})
        except Exception as e:
            main = html.Div([
                html.Div([
                    html.Div("Admin tab error", style={
                        "color": WHITE,
                        "fontSize": "16px",
                        "fontWeight": "900",
                        "marginBottom": "8px",
                    }),
                    html.Div(str(e), style={
                        "color": YELLOW_DIM,
                        "fontSize": "12px",
                        "whiteSpace": "pre-wrap",
                    }),
                ], style={
                    "border": f"1px solid {BORDER}",
                    "background": "rgba(8,24,39,.72)",
                    "borderRadius": "16px",
                    "padding": "18px",
                }),
            ], style={"display":"flex","flexDirection":"column","gap":"16px"})
    elif tab=="setup":       main = build_setup_tab()
    else:                    main = html.Div("Unknown tab")
    return main, HIDDEN, no_update, no_update

# ── Trade plan / entry / exit callbacks ───────────────────────────────────────

@app.callback(
    Output("tp-status","children"),
    Output("s-current-plan-id","data"),
    Input("btn-save-plan","n_clicks"),
    State("tp-direction","data"), State("tp-entry","value"),
    State("tp-stop","value"), State("tp-target","value"),
    State("tp-size","value"), State("tp-notes","value"),
    State("s-live","data"), prevent_initial_call=True,
)
def save_plan(n,direction,entry,stop,target,size,notes,live):
    if not n: return no_update, no_update
    try:
        price  = live["price"] if live else 0
        symbol = live.get("symbol","") if live else ""
        score  = live.get("decision",{}).get("score",0) if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        resp = _post("/api/behavior/trade-plan",{
            "user_id":USER_ID,"symbol":symbol,"direction":direction,
            "planned_entry":float(entry),"planned_stop":float(stop),
            "planned_target":float(target),"planned_size":float(size),
            "setup_reason":notes or "","signal_score_at_plan":score,"regime_at_plan":regime,
        })
        plan_id = resp.get("plan_id")
        _track("trade_planned",symbol,price=price,regime=regime,decision_score=score,
               metadata={"plan_id":plan_id,"direction":direction})
        return f"Plan saved: {plan_id}", plan_id
    except Exception as e:
        return f"Error: {e}", no_update

@app.callback(
    Output("tp-status","children",allow_duplicate=True),
    Input("btn-enter-trade","n_clicks"),
    State("tp-direction","data"), State("tp-entry","value"),
    State("tp-stop","value"), State("tp-target","value"),
    State("tp-size","value"),
    State("s-current-plan-id","data"),
    State("s-live","data"), prevent_initial_call=True,
)
def enter_trade(n,direction,entry,stop,target,size,plan_id,live):
    if not n: return no_update
    try:
        price  = live["price"] if live else 0
        symbol = live.get("symbol","") if live else ""
        score  = live.get("decision",{}).get("score",0) if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        resp = _post("/api/behavior/trade-entry",{
            "user_id":USER_ID,"symbol":symbol,"direction":direction,
            "entry_price":float(entry),"stop_price":float(stop) if stop else None,
            "target_price":float(target) if target else None,"size":float(size),
            "plan_id":plan_id,"market_regime_entry":regime,"signal_score_entry":score,
        })
        trade_id = resp.get("trade_id")
        _track("trade_entered",symbol,price=float(entry),regime=regime,decision_score=score,
               metadata={"trade_id":trade_id,"direction":direction})
        return f"Trade entered: {trade_id}"
    except Exception as e:
        return f"Error: {e}"

@app.callback(
    Output("exit-status","children"),
    Input("btn-exit-trade","n_clicks"),
    State("s-active-trade-id","data"),
    State("exit-flags","value"),
    State("exit-notes","value"),
    State("s-live","data"), prevent_initial_call=True,
)
def exit_trade(n,trade_id,flags,notes,live):
    if not n or not trade_id: return no_update
    try:
        price  = live["price"] if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        score  = live.get("decision",{}).get("score",0) if live else 0
        flags  = flags or []
        resp = _post("/api/behavior/trade-exit",{
            "trade_id":trade_id,"exit_price":price,
            "market_regime_exit":regime,"signal_score_exit":score,"notes":notes or "",
            "no_plan":            "no_plan"            in flags,
            "stop_moved_wider":   "stop_moved_wider"   in flags,
            "target_moved":       "target_moved"        in flags,
            "premature_exit":     "premature_exit"      in flags,
            "added_size_adverse": "added_size_adverse"  in flags,
            "timeframe_changed":  "timeframe_changed"   in flags,
        })
        scores = resp.get("scores",{})
        _track("trade_exited",live.get("symbol",""),price=price,regime=regime,decision_score=score,
               metadata={"trade_id":trade_id,"pnl":resp.get("pnl"),"flag":resp.get("behavior_flag")})
        return (f"Exited · P&L: ${resp.get('pnl',0):+.2f} ({resp.get('pnl_percent',0):+.2f}%) · "
                f"Score: {scores.get('composite',0):.0f} · Flag: {resp.get('behavior_flag','—')}")
    except Exception as e:
        return f"Error: {e}"

# ── Direction toggle buttons ─────────────────────────────────────────────────
def _dir_styles(active):
    base = {"flex":"1","padding":"9px 0","fontSize":"13px","cursor":"pointer","fontFamily":"inherit"}
    styles = {
        "long":    {**base,"fontWeight":"800","borderRadius":"8px 0 0 8px",
                    "border":f"1px solid {BORDER_T}","background":TEAL_GLOW,"color":TEAL_DIM},
        "short":   {**base,"fontWeight":"800","borderRadius":"0",
                    "border":f"1px solid rgba(239,68,68,.35)","borderLeft":"none","borderRight":"none",
                    "background":RED_GLOW,"color":RED_DIM},
        "neutral": {**base,"fontWeight":"800","borderRadius":"0 8px 8px 0",
                    "border":f"1px solid rgba(245,158,11,.35)","background":"rgba(245,158,11,.08)","color":YELLOW_DIM},
    }
    idle = {
        "long":    {**base,"fontWeight":"700","borderRadius":"8px 0 0 8px",
                    "border":f"1px solid {BORDER}","background":"transparent","color":WHITE},
        "short":   {**base,"fontWeight":"700","borderRadius":"0",
                    "border":f"1px solid {BORDER}","borderLeft":"none","borderRight":"none",
                    "background":"transparent","color":WHITE},
        "neutral": {**base,"fontWeight":"700","borderRadius":"0 8px 8px 0",
                    "border":f"1px solid {BORDER}","background":"transparent","color":WHITE},
    }
    return (styles["long"]    if active=="long"    else idle["long"],
            styles["short"]   if active=="short"   else idle["short"],
            styles["neutral"] if active=="neutral" else idle["neutral"])

@app.callback(
    Output("tp-direction", "data"),
    Output("dir-long",    "style"),
    Output("dir-short",   "style"),
    Output("dir-neutral", "style"),
    Input("dir-long",    "n_clicks"),
    Input("dir-short",   "n_clicks"),
    Input("dir-neutral", "n_clicks"),
    prevent_initial_call=True,
)
def select_direction(_l, _s, _n):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update
    btn = ctx.triggered[0]["prop_id"].split(".")[0]
    direction = btn.replace("dir-", "")
    sl, ss, sn = _dir_styles(direction)
    return direction, sl, ss, sn


# ── CSV upload callback ──────────────────────────────────────────────────────
@app.callback(
    Output("csv-upload-status", "children"),
    Input("csv-upload", "contents"),
    State("csv-upload", "filename"),
    prevent_initial_call=True,
)
def handle_csv_upload(contents, filename):
    if not contents:
        return no_update
    import base64, io as _io
    try:
        # Decode base64 data URI
        content_type, content_string = contents.split(",")
        decoded = base64.b64decode(content_string)
        # POST to backend
        resp = req.post(
            f"{BACKEND_HTTP}/api/import/upload",
            files={"file": (filename, _io.BytesIO(decoded), "text/csv")},
            timeout=30,
        )
        if resp.ok:
            data = resp.json()
            a    = data.get("analysis", {})
            return html.Div([
                html.Span(f"{data.get('broker_name','Unknown')} detected · ",
                          style={"color":TEAL_DIM,"fontWeight":"800"}),
                html.Span(f"{data.get('trades_closed',0)} trades imported · "
                          f"Win rate: {a.get('win_rate',0)}% · "
                          f"Total P&L: ${a.get('total_pnl',0):+,.2f}",
                          style={"color":WHITE}),
                html.Br(),
                html.Span("Switch to the Behavioral Intelligence tab to see your full profile.",
                          style={"color":WHITE,"fontSize":"11px"}),
            ])
        else:
            return f"Upload failed: {resp.text[:200]}"
    except Exception as e:
        return f"Error: {str(e)[:200]}"


# ── Audio alert clientside callback ──────────────────────────────────────────
app.clientside_callback(
    """
    function(score, prev_score, alerts_on) {
        if (window.dash_clientside && window.dash_clientside.sigmalytic) {
            return window.dash_clientside.sigmalytic.fireAlert(score, prev_score, alerts_on);
        }
        return score;
    }
    """,
    Output("s-alert-score", "data"),
    Input("s-live", "data"),
    State("s-alert-score", "data"),
    State("s-alerts-on", "data"),
)

@app.callback(
    Output("s-alerts-on", "data"),
    Output("btn-alerts-toggle", "children"),
    Output("btn-alerts-toggle", "style"),
    Input("btn-alerts-toggle", "n_clicks"),
    State("s-alerts-on", "data"),
    prevent_initial_call=True,
)
def toggle_alerts(n, currently_on):
    new_on = not currently_on
    label  = "ON"  if new_on else "OFF"
    style  = {"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","color":TEAL_DIM,
               "borderRadius":"20px","padding":"4px 12px","fontSize":"11px","fontWeight":"800","cursor":"pointer"}
    if not new_on:
        style.update({"background":"rgba(100,116,139,.12)","border":f"1px solid {BORDER}","color":WHITE})
    return new_on, label, style


@app.callback(Output("auth-overlay","style"),
              Input("s-session","data"))
def route_page(session):
    overlay_base = {"position":"fixed","top":0,"left":0,"right":0,"bottom":0,
                    "zIndex":9999,"background":NAVY,"overflowY":"auto"}
    hidden = {"display":"none"}
    if session and session.get("user_id"):
        return hidden
    return overlay_base

@app.callback(Output("login-section","style"), Output("signup-section","style"),
              Input("goto-signup-btn","n_clicks"), Input("goto-login-btn","n_clicks"),
              prevent_initial_call=True)
def toggle_auth_section(to_signup, to_login):
    ctx = callback_context
    if not ctx.triggered: return no_update, no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger == "goto-signup-btn":
        return {"display":"none"}, {"display":"block"}
    return {"display":"block"}, {"display":"none"}

@app.callback(Output("s-session","data"),Output("s-page","data"),
              Output("login-error","children"), Output("signup-error","children"),
              Input("login-btn","n_clicks"),Input("demo-btn","n_clicks"),
              Input("signup-btn","n_clicks"),
              State("login-email","value"),State("login-password","value"),
              State("signup-email","value"),State("signup-password","value"),
              State("signup-agree-terms","value"),
              prevent_initial_call=True)
def handle_auth(login_clicks, demo_clicks, signup_clicks,
                login_email, login_password, signup_email, signup_password,
                signup_agree_terms):
    ctx = callback_context
    if not ctx.triggered: return no_update, no_update, no_update, no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]

    if trigger == "demo-btn":
        return {
            "user_id": "demo_user_001",
            "email": "demo@sigmalytic.com",
            "is_demo": True,
            "plan": "elite",
            "plan_name": "Elite Trader",
            "features": {
                "radar_limit": 9999,
                "delayed_data": False,
                "delay_minutes": 0,
                "alerts": True,
                "sms_limit": -1,
                "live_data": True,
                "intelligence": True,
                "composite_score_only": False,
            }
        }, "app", "", ""

    if trigger == "login-btn":
        if not login_email or not login_password:
            return no_update, no_update, "Please enter both email and password.", no_update

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return (no_update, no_update,
                    "Sign-in is not configured on this server. Try Demo mode, or contact support.",
                    no_update)

        import requests as _req
        try:
            r = _req.post(
                f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                headers={"apikey":SUPABASE_ANON_KEY,"Content-Type":"application/json"},
                json={"email":login_email,"password":login_password}, timeout=10,
            )
            if r.ok:
                data = r.json()
                user = data.get("user",{})
                return ({"user_id":user.get("id",""),"email":user.get("email",""),
                        "access_token":data.get("access_token",""),"is_demo":False}, "app",
                        "", no_update)

            # Non-ok response: show a real reason instead of silently doing nothing.
            if r.status_code in (400, 401, 422):
                msg = "Incorrect email or password."
            else:
                msg = f"Sign-in failed (error {r.status_code}). Please try again."
            return no_update, no_update, msg, no_update

        except Exception as exc:
            return no_update, no_update, f"Could not reach the sign-in service: {exc}", no_update

    if trigger == "signup-btn":
        if not signup_email or not signup_password:
            return no_update, no_update, no_update, "Please enter both email and password."

        if not signup_agree_terms or "agreed" not in signup_agree_terms:
            return (no_update, no_update, no_update,
                    "Please agree to the Terms of Service and Privacy Policy to create an account.")

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            return (no_update, no_update, no_update,
                    "Sign-up is not configured on this server. Try Demo mode, or contact support.")

        import requests as _req
        try:
            r = _req.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers={"apikey":SUPABASE_ANON_KEY,"Content-Type":"application/json"},
                json={"email":signup_email,"password":signup_password}, timeout=10,
            )
            if r.ok:
                data = r.json()
                user = data.get("user",{})
                return ({"user_id":user.get("id",""),"email":user.get("email",""),
                        "access_token":data.get("access_token",""),"is_demo":False}, "app",
                        no_update, "")

            if r.status_code in (400, 422):
                msg = "Could not create account. That email may already be registered."
            else:
                msg = f"Sign-up failed (error {r.status_code}). Please try again."
            return no_update, no_update, no_update, msg

        except Exception as exc:
            return no_update, no_update, no_update, f"Could not reach the sign-up service: {exc}"

    return no_update, no_update, no_update, no_update

# ── Main app callbacks ────────────────────────────────────────────────────────



@app.callback(
    Output("s-session", "data", allow_duplicate=True),
    Output("url", "href"),
    Input("btn-logout", "n_clicks"),
    prevent_initial_call=True,
)
def logout(n):
    if n:
        return None, "/"
    return no_update, no_update


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)

# SIGMALYTIC_HIGH_CONTRAST_TEXT_PATCH
# Note: Opportunity Dashboard inline styles already force descriptive text to WHITE.
