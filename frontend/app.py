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
FRONTEND_URL      = os.getenv("FRONTEND_URL", "https://sigmalytic-frontend.onrender.com")
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
@keyframes sigmaAlertToast {{
    0%   {{ opacity: 0; transform: translateY(-12px); }}
    8%   {{ opacity: 1; transform: translateY(0); }}
    88%  {{ opacity: 1; transform: translateY(0); }}
    100% {{ opacity: 0; transform: translateY(-12px); }}
}}
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

def _current_user_id(session=None):
    """Real logged-in user id if available, else the shared demo id."""
    return (session or {}).get("user_id") or USER_ID


def _auth_headers(session=None):
    """Authorization header for the logged-in user, or empty for demo/no session."""
    token = (session or {}).get("access_token", "")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _track(event_type, symbol, price=None, timeframe=None, regime=None,
           decision_score=None, decision_status=None, metadata=None, session=None):
    """Fire-and-forget behavioral event to backend.

    SECURITY/CORRECTNESS FIX (2026-07-28): this used to always send the
    hardcoded USER_ID constant ("demo_user_001") no matter who was actually
    logged in -- meaning every real user's behavior events were being
    written into the shared demo account instead of their own. Now takes
    the caller's session and sends that user's real id and auth token
    (the backend verifies the token independently either way, but sending
    the right identity is what makes a logged-in user's own dashboard
    show their own data).
    """
    try:
        req.post(f"{BACKEND_HTTP}/api/behavior/event", json={
            "user_id": _current_user_id(session), "event_type": event_type, "symbol": symbol,
            "price": price, "timeframe": timeframe, "market_regime": regime,
            "decision_score": decision_score, "decision_status": decision_status,
            "metadata": metadata or {},
        }, headers=_auth_headers(session), timeout=2)
    except Exception:
        pass

def _get(path, headers=None, **params):
    def _do_fetch():
        try:
            r = req.get(f"{BACKEND_HTTP}{path}", params=params, headers=headers or {}, timeout=15)
            return r.json() if r.ok else {}
        except Exception:
            return {}

    if shared_cache is None or params or headers:
        # Don't cache calls with extra query params or per-user auth headers --
        # the cache key is just the path string, so a parameterized/authenticated
        # call could silently return another call's (or another user's!)
        # cached result. Rare in this codebase, but safer to just fetch fresh.
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


def _build_d3f1b_controlled_persistence_lifecycle_panel(session=None):
    endpoint = "/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep"

    try:
        data = _get(endpoint, headers=_auth_headers(session))
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
        # FIX (2026-08-06): now that threaded=True enables genuine
        # concurrent request handling, two separate key writes here
        # created a brief window where a concurrent read could see an
        # updated as_of paired with stale data. A single, atomic dict
        # reassignment removes that window entirely.
        _WEIS_GAMMA_STATUS_CACHE.update({"as_of": now, "data": data})
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


def _wg_label(value, category="gamma"):
    """
    FIX (2026-07-28): this used to be a single label dictionary shared
    across five conceptually different metric categories (gamma status,
    option-chain fetch status, fusion state, phase, rank bucket). Several
    raw backend status codes happen to collide across categories (e.g.
    both a gamma computation and an option-chain fetch can independently
    report "OK"), so the *same* human-readable text -- "Gamma OK" -- was
    appearing in unrelated panels like "Option Chain Status", where it
    doesn't describe what that panel is actually showing. This reads as
    duplicated output even though the underlying counts are genuinely
    different fields. Each category now has its own accurate label set.
    """
    shared = {
        "NONE": "Missing Overlay",
        "EMPTY": "Empty",
        "NOT_PRESENT": "Not Present",
    }

    by_category = {
        "gamma": {
            "OK": "Gamma OK",
            "NO_OPTIONS_RETURNED": "No Options Returned",
            "NO_OPTION_CHAIN_INPUT": "No Option-Chain Input",
            "NO_GAMMA_INPUT": "No Gamma Input",
            "CALL_SIGNATURE_MISMATCH": "Call Signature Mismatch",
        },
        "option_chain": {
            "OK": "Chain Fetched OK",
            "NO_OPTIONS_RETURNED": "No Options Returned",
            "SKIPPED_FETCH_CAP_REACHED": "Skipped - Fetch Cap Reached",
            "SKIPPED_SYMBOL_NOT_ALLOWED": "Skipped - Symbol Not Allowed",
            "SKIPPED_NOT_DISCOVERED": "Skipped - Not Yet Discovered",
            "DISABLED": "Option-Chain Fetch Disabled",
            "ADAPTER_UNAVAILABLE": "Adapter Unavailable",
            "FETCH_EXCEPTION": "Fetch Exception",
        },
        "fusion": {
            "WEIS_ONLY_GAMMA_STALE": "Weis Only - Gamma Stale",
            "WEIS_ONLY_NO_OPTIONS_RETURNED": "Weis Only - No Options Returned",
            "WEIS_EXPANSION_GAMMA_NEUTRAL": "Weis Expansion - Gamma Neutral",
            "WEIS_GAMMA_UNRESOLVED": "Weis Gamma Unresolved",
        },
        "phase": {
            "WEIS_EXPANSION": "Weis Expansion",
            "WEIS_BASELINE": "Weis Baseline",
            "WEIS_TEST": "Weis Test",
            "WEIS_EXHAUSTION": "Weis Exhaustion",
        },
        "rank": {
            "A_PLUS": "A+",
            "LOW_PRIORITY": "Low Priority",
            "WATCHLIST": "Watchlist",
            "AVOID": "Avoid",
        },
    }

    key = str(value or "NONE")
    if key in shared:
        return shared[key]
    mapping = by_category.get(category, by_category["gamma"])
    if key in mapping:
        return mapping[key]
    return key.replace("_", " ").title()


def _wg_counts_text(counts, category="gamma"):
    if not isinstance(counts, dict) or not counts:
        return "-"

    parts = []
    for key, value in counts.items():
        parts.append(f"{_wg_label(key, category=category)}: {value}")

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
    # FIX (2026-07-29): this badge was labeled "TRANSITIONS OFF" /
    # "TRANSITIONS ENABLED", which reads as if it reports whether your
    # actual campaign lifecycle engine (BIRTH -> ... -> CLOSED, which
    # genuinely runs nightly via campaign_state_engine.py) is active.
    # It doesn't -- this flag comes from a read-only Weis-Gamma evidence
    # *preview* (_build_transition_readiness_evidence in
    # campaign_evidence_builder.py) that is explicitly documented as
    # "does not change the campaign state engine, only explains what
    # evidence would support" -- i.e. it's SUPPOSED to always read as
    # off, as a safety self-check, and has no bearing on whether your
    # real product is actually transitioning campaigns. Renamed so it
    # can't be mistaken for the real engine's status.
    safety_color = TEAL_DIM if transitions_off else RED_DIM
    safety_label = "GAMMA PREVIEW: READ-ONLY (EXPECTED)" if transitions_off else "⚠ GAMMA PREVIEW CLAIMS WRITE ACCESS"

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
            _wg_metric_card("Gamma Preview Read-Only", "YES" if transitions_off else "NO", safety_color),
            _wg_metric_card("Missing Overlay", missing, YELLOW_DIM),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
            "gap": "10px",
        }),

        html.Div([
            html.Div([
                html.Div("Phase Counts", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(phase_counts, category="phase"), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Rank Buckets", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(rank_counts, category="rank"), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Effective Gamma Status", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(gamma_counts, category="gamma"), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Option Chain Status", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(option_chain_counts, category="option_chain"), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Effective Fusion State", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(fusion_counts, category="fusion"), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
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


def _post(path, body, headers=None):
    try:
        r = req.post(f"{BACKEND_HTTP}{path}", json=body, headers=headers or {}, timeout=4)
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

def build_chart(candles, price, nodes, tf="5m", call_wall=None, put_wall=None, gamma_pivot=None):
    """Clean chart — integer index x-axis for proper candle rendering."""
    kl = get_key_levels(price)
    # FIX (2026-07-30): user-reported the candlesticks don't match the
    # live price shown elsewhere on the page. Root cause: fetch_real_candles
    # only returns bars the backend's Alpaca endpoint has already closed
    # (its own docstring says "No synthetic candles are created here") --
    # so the chart's rightmost candle can lag the live tick price by up
    # to a full bar duration (up to 5 minutes on the 5m timeframe) even
    # though the live price display updates every tick. Nothing anywhere
    # between the fetch and this render function ever reconciled the two.
    # Fixing this here, at render time only (not in fetch_real_candles,
    # which deliberately stays fetch-only per its own docstring) --
    # updating a copy of the last candle's close/high/low to reflect the
    # live price, so the chart visually tracks real-time price movement
    # between actual bar closes instead of only updating once per bar.
    if candles and price and price > 0:
        candles = candles[:-1] + [dict(candles[-1])]
        last = candles[-1]
        last["c"] = price
        last["h"] = max(last["h"], price)
        last["l"] = min(last["l"], price)
    # FIX (2026-07-30): user clarified that Call Wall / Put Wall / Gamma
    # Flip Point represent *current* options/gamma structure -- they
    # should always be visible and always move with real, live options
    # data, regardless of which historical timeframe the chart happens
    # to be showing. Earlier tonight this was set to hide on 1D/1W,
    # reasoning that short-term levels would visually cluster near the
    # top when stretched across months of daily candles -- but that
    # visual-clustering concern doesn't justify hiding genuinely current,
    # real data. Always showing them now.
    show_price_overlays = True
    xs = list(range(len(candles)))
    fig = go.Figure()

    if show_price_overlays:
        _flip = gamma_pivot if gamma_pivot is not None else kl.confirm
        _highs = [c["h"] for c in candles] if candles else [price]
        _lows  = [c["l"] for c in candles] if candles else [price]
        _y_top = max(max(_highs), _flip, price) * 1.02
        _y_bot = min(min(_lows),  _flip, price) * 0.98
        fig.add_hrect(y0=_flip, y1=_y_top, fillcolor=TEAL_DIM, opacity=0.06, layer="below", line_width=0)
        fig.add_hrect(y0=_y_bot, y1=_flip, fillcolor=RED_DIM,  opacity=0.06, layer="below", line_width=0)

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
    # Level lines — the 4 generic structural levels stay unlabeled (labels
    # live in the Price Ladder panel), but Call Wall / Put Wall / Gamma
    # Pivot are the exact same numbers shown in the Options Matrix widget
    # below, and were previously indistinguishable from the other 4 faint
    # lines -- same thin width, no text, easy to lose track of which line
    # was which. These three now get their own clear, bolder, labeled
    # lines so they're immediately identifiable on the chart itself.
    if show_price_overlays:
        for level,color,dash,width in [
            (kl.prior_high, TEAL_DIM,   "dot",     1.0),
            (kl.expansion,  TEAL_DIM,   "dashdot", 1.0),
            (kl.trigger,    YELLOW_DIM, "dash",    1.0),
            (kl.trap,       RED_DIM,    "dot",     1.0),
        ]:
            fig.add_hline(y=level, line_color=color, line_dash=dash,
                          line_width=width, opacity=0.6)

    # BUG FIX (2026-07-29): the label f-strings here were built as part of
    # the list literal itself, which Python evaluates fully *before* the
    # for-loop assigns `level` on each iteration -- so every label used
    # whatever `level` was left over from the previous loop above (kl.trap)
    # instead of each line's own value. All three labels were silently
    # showing the same wrong number. Fixed by building the label text
    # inside the loop body, after `level` is actually bound per-iteration.
    if show_price_overlays:
        for level,color,prefix in [
            (call_wall   if call_wall   is not None else kl.breakout, TEAL_DIM,   "CALL WALL"),
            (gamma_pivot if gamma_pivot is not None else kl.confirm,  YELLOW_DIM, "GAMMA FLIP POINT"),
            (put_wall    if put_wall    is not None else kl.fail,     RED_DIM,    "PUT WALL"),
        ]:
            label = f"{prefix}  ${level:.0f}"
            fig.add_hline(
                y=level, line_color=color, line_dash="solid", line_width=2.5, opacity=0.95,
                annotation_text=label,
                annotation_position="top left",
                annotation_font=dict(color=color, size=11, family="DM Mono, monospace"),
                annotation_bgcolor="rgba(8,24,39,.85)",
                annotation_bordercolor=color,
                annotation_borderwidth=1,
            )
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

def _render_market_wire(items):
    """
    Top-of-page ticker: DJIA/S&P/Nasdaq/Russell 2000/Gold/Oil/Bitcoin.
    VIX intentionally excluded -- see the backend endpoint's own comment
    for why (no reliable, non-misleading proxy available).
    """
    if not items:
        return html.Div()

    pills = []
    for item in items:
        price = item.get("price")
        change_pct = item.get("change_pct")
        label = item.get("label", item.get("symbol", "—"))

        if price is None:
            continue

        if item.get("asset_class") == "crypto":
            price_text = f"${price:,.0f}"
        else:
            price_text = f"${price:,.2f}"

        if change_pct is None:
            change_text, change_color = "—", MUTED
        elif change_pct >= 0:
            change_text, change_color = f"+{change_pct:.2f}%", TEAL_DIM
        else:
            change_text, change_color = f"{change_pct:.2f}%", RED_DIM

        pills.append(html.Div([
            html.Span(label, style={"color": WHITE, "fontSize": "11px", "fontWeight": "700", "marginRight": "6px"}),
            html.Span(price_text, style={"color": WHITE, "fontSize": "11px", "fontWeight": "800", "marginRight": "6px"}),
            html.Span(change_text, style={"color": change_color, "fontSize": "11px", "fontWeight": "800"}),
        ], style={"display": "flex", "alignItems": "center", "padding": "6px 12px",
                   "background": NAVY_MID, "border": f"1px solid {BORDER}", "borderRadius": "10px",
                   "whiteSpace": "nowrap"}))

    return html.Div(pills, style={
        "display": "flex", "gap": "8px", "overflowX": "auto",
        "justifyContent": "center", "flexWrap": "wrap",
    })


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

# ── Behavioral Analysis Panel ────────────────────────────────────────────────
def _score_tier(score):
    """Matches the exact thresholds used in build_direction_panel's Score Tier."""
    if score < 35:
        return "Trap Door"
    elif score < 55:
        return "Monitoring"
    elif score < 80:
        return "Score Tier B"
    else:
        return "Score Tier A"


def _build_behavioral_analysis(live):
    """
    Interprets the app's own current, real data for whatever symbol is
    loaded -- not generic trading advice, a live reading of this specific
    tool's own logic (Bias/Confidence/Status/Grade/Mode/Score/Volume),
    matching the style of a manual walkthrough of these exact metrics.
    Rule-based and deterministic (no LLM call), so it can run on every
    live-price tick without added latency or external dependencies.
    """
    symbol   = live.get("symbol", "—")
    price    = live.get("price", 0)
    decision = live.get("decision", {}) or {}
    rel_vol  = live.get("rel_volume")

    bias       = str(decision.get("bias", "Neutral"))
    status     = str(decision.get("status", "Watching"))
    grade      = str(decision.get("grade", "—"))
    mode       = str(decision.get("mode", "Standard"))
    confidence = str(decision.get("confidence", ""))
    score      = decision.get("score", 0) or 0
    tier       = _score_tier(score)

    bias_lower = bias.lower()
    is_directional = bias_lower in ("bullish", "bearish")
    is_qualified_status = status.upper() not in ("PROBE", "WATCHING")
    is_qualified_grade = grade.upper() in ("A", "B")
    is_expanding = rel_vol is not None and rel_vol >= 1.5
    tier_actionable = tier in ("Score Tier A", "Score Tier B")

    bullets = []

    # Bias/Confidence line
    if is_directional:
        bullets.append(
            f"Bias: {bias.upper()}, Confidence: {confidence or 'n/a'} — the Decision Engine "
            f"has committed to a {bias_lower} read on {symbol}."
        )
    else:
        bullets.append(
            f"Bias: {bias.upper()}, Confidence: {confidence or 'LOW'} — the Decision Engine "
            f"hasn't picked a direction yet for {symbol}."
        )

    # Status/Grade line
    if is_qualified_status and is_qualified_grade:
        bullets.append(
            f"Status - Grade: {status} - {grade} — a qualified status with a strong grade means "
            f"the engine sees this as a real, actionable setup, not just an exploratory read."
        )
    else:
        bullets.append(
            f"Status - Grade: {status} - {grade} — "
            f"{'a low-conviction status' if not is_qualified_status else 'a weak grade'} means "
            f"the engine sees this as an exploratory read, not a qualified setup yet."
        )

    # Mode line
    bullets.append(
        f"Mode: {mode} — "
        + ("the app is explicitly flagging this as a consolidation/absorption phase, not a trending one."
           if "digestion" in mode.lower() or "caution" in mode.lower()
           else "the app is reading current conditions as tradeable, not just noise.")
    )

    # Score/Tier line
    if tier == "Trap Door":
        bullets.append(f"Engine Score: {score}%, Score Tier: {tier} — a warning-style zone; conditions look deteriorating, not building.")
    elif tier == "Monitoring":
        bullets.append(f"Engine Score: {score}%, Score Tier: {tier} — sits in the \"watch, don't act\" middle zone (35-54), below the 55+ needed to reach Score Tier B.")
    else:
        bullets.append(f"Engine Score: {score}%, Score Tier: {tier} — real conviction behind the move, not just noise.")

    # Volume line
    if rel_vol is None:
        bullets.append("Volume: data unavailable right now — can't confirm whether real participation is behind this move.")
    elif is_expanding:
        bullets.append(
            f"Volume: {rel_vol:.2f}x average, met — real, elevated participation is happening. "
            f"But volume alone just means \"something's happening\" — it doesn't tell you which direction."
        )
    else:
        bullets.append(f"Volume: {rel_vol:.2f}x average, not met — no unusual participation behind the current move yet.")

    # Overall verdict + gates
    fully_actionable = is_directional and is_qualified_status and is_qualified_grade and tier_actionable
    if fully_actionable:
        verdict = (
            f"What the current combination says: {symbol} is showing a qualified, actionable "
            f"{bias_lower} setup right now — Bias, Status, Grade, and Score Tier are all "
            f"aligned. This is the kind of alignment a disciplined trader using this framework "
            f"would treat as a real, engine-confirmed opportunity, not just a possibility."
        )
        gates = None
    else:
        verdict = (
            f"What the current combination says: right now, nothing here is actionable yet"
            + (f", despite {'strong' if is_expanding else 'available'} volume" if rel_vol is not None else "")
            + f". The honest summary: {'you have fuel but no direction and no conviction' if is_expanding and not is_directional else 'the engine has not yet confirmed a real, qualified setup'}. "
            f"A disciplined trader using this framework would treat this as \"stand aside, wait "
            f"for the engine to actually commit\" rather than force a trade off any single signal "
            f"alone — the whole point of Confidence/Grade/Status existing separately from raw "
            f"score is to catch exactly this situation."
        )
        long_gates = []
        if bias_lower != "bullish":
            long_gates.append("Bias shifts from Neutral/Bearish → Bullish")
        if not tier_actionable or tier == "Trap Door":
            long_gates.append(f"Engine Score climbs out of {tier} into Score Tier B (55+) or Score Tier A (80+)")
        if not is_qualified_status:
            long_gates.append(f"Status upgrades out of \"{status}\" into a qualified state like Armed or Setting Up")
        if not is_qualified_grade:
            long_gates.append(f"Grade improves from {grade} to B or A")
        if not long_gates:
            long_gates.append("Price clears a defined trigger level, confirming the move is real")

        short_gates = []
        if bias_lower != "bearish":
            short_gates.append("Bias shifts from Neutral/Bullish → Bearish")
        short_gates.append("Score Tier moves toward Trap Door (below 35) rather than up")
        short_gates.append("Price breaks down through a defined invalidation/support level")

        gates = (long_gates, short_gates)

    return symbol, price, bullets, verdict, gates


def _render_behavioral_analysis_panel(live):
    if not live:
        return card([html.Div("Behavioral Analysis will appear once live data loads.",
                               style={"color": MUTED, "fontSize": "13px"})])

    symbol, price, bullets, verdict, gates = _build_behavioral_analysis(live)

    children = [
        html.Div([
            html.H2("Behavioral Analysis", style={"fontSize": "16px", "fontWeight": "800", "color": WHITE, "margin": "0"}),
            html.Span(f"{symbol} · ${price:.2f}", style={"fontSize": "12px", "color": WHITE}),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "12px"}),
        html.P(verdict, style={"fontSize": "12px", "color": WHITE, "lineHeight": "1.6", "marginBottom": "12px"}),
        html.Ul([
            html.Li(b, style={"fontSize": "12px", "color": WHITE, "lineHeight": "1.6", "marginBottom": "6px"})
            for b in bullets
        ], style={"paddingLeft": "18px", "marginBottom": "12px"}),
    ]

    if gates:
        long_gates, short_gates = gates
        children.append(html.Div([
            slabel("Gates for Long"),
            html.Ul([html.Li(g, style={"fontSize": "11px", "color": TEAL_DIM, "lineHeight": "1.6"}) for g in long_gates],
                    style={"paddingLeft": "18px", "marginBottom": "10px"}),
            slabel("Gates for Short"),
            html.Ul([html.Li(g, style={"fontSize": "11px", "color": RED_DIM, "lineHeight": "1.6"}) for g in short_gates],
                    style={"paddingLeft": "18px"}),
        ]))

    # Real, validated Phase 10 position sizing -- first time this
    # research output is shown anywhere in the UI, not just the backend
    # endpoint added earlier tonight.
    sizing = live.get("sizing_data")
    if sizing and sizing.get("sized"):
        result = sizing.get("result", {})
        if result.get("approved"):
            children.append(html.Div([
                slabel("Validated Position Sizing (Phase 10 research)"),
                html.P(result.get("summary", ""), style={"fontSize": "11px", "color": TEAL_DIM,
                                                            "lineHeight": "1.6", "marginTop": "6px"}),
            ], style={"marginTop": "12px"}))
        else:
            children.append(html.Div([
                slabel("Validated Position Sizing (Phase 10 research)"),
                html.P(f"Not sized — {result.get('blocked_reason', 'blocked')}",
                       style={"fontSize": "11px", "color": RED_DIM, "lineHeight": "1.6", "marginTop": "6px"}),
            ], style={"marginTop": "12px"}))
    elif sizing and not sizing.get("sized"):
        children.append(html.Div([
            slabel("Validated Position Sizing (Phase 10 research)"),
            html.P(sizing.get("reason", "Not enough data to size."),
                   style={"fontSize": "11px", "color": MUTED, "lineHeight": "1.6", "marginTop": "6px"}),
        ], style={"marginTop": "12px"}))

    # Real Livermore/ODS-style operator control score -- only present
    # once an active campaign record exists for this symbol (Layer 5).
    dominance = live.get("dominance_data")
    if dominance:
        score = dominance.get("score", {})
        children.append(html.Div([
            slabel("Operator Control Score"),
            html.P(
                f"{score.get('livermore_score', '—')}/100 — campaign state: {dominance.get('current_state', 'Unknown')}",
                style={"fontSize": "11px", "color": BLUE_DIM, "lineHeight": "1.6", "marginTop": "6px"},
            ),
        ], style={"marginTop": "12px"}))

    # Real, read-only transition preview -- what state this campaign
    # is likely to move to next, with a specific rationale, without
    # mutating anything.
    tp = live.get("transition_preview_data")
    if tp:
        current = tp.get("current_state", "—")
        proposed = tp.get("proposed_next_state")
        rationale_list = tp.get("rationale") or []
        rationale_text = rationale_list[0] if rationale_list else ""
        if proposed and proposed != current:
            preview_text = f"{current} → {proposed}"
            preview_color = TEAL_DIM
        else:
            preview_text = f"{current} (no transition previewed)"
            preview_color = MUTED
        children.append(html.Div([
            slabel("Transition Preview"),
            html.P(preview_text, style={"fontSize": "11px", "color": preview_color,
                                          "lineHeight": "1.6", "marginTop": "6px", "fontWeight": "700"}),
            html.P(rationale_text, style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.6", "marginTop": "4px"}),
        ], style={"marginTop": "12px"}))

    # Real, per-symbol evidence diagnostics -- confirmed genuine,
    # database-only diagnostic (found via full audit of campaign_api.py,
    # confirmed never called from the frontend at all).
    ed = live.get("evidence_diagnostics_data")
    if ed:
        summary = ed.get("single_symbol_summary", {})
        tier = summary.get("diagnostic_priority_tier", "—")
        tier_color = TEAL_DIM if str(tier).startswith("A_") else (BLUE_DIM if str(tier).startswith("B_") else MUTED)
        children.append(html.Div([
            slabel("Evidence Diagnostics"),
            html.P(f"{tier} — score {summary.get('diagnostic_priority_score', '—')}",
                   style={"fontSize": "11px", "color": tier_color, "lineHeight": "1.6",
                          "marginTop": "6px", "fontWeight": "700"}),
            html.P(summary.get("campaign_explanation", ""),
                   style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.6", "marginTop": "4px"}),
        ], style={"marginTop": "12px"}))

    # Real, validated research classification (Layer 1/2) -- the ACTUAL
    # winning formula from the original research (OBS_Q4+PROG_Q4+
    # SPD=Y|DEI=N), not the different, disconnected setup_type/bucket
    # system used elsewhere in the app.
    vc = live.get("validated_classification")
    if vc:
        state = vc.get("behavioral_state", "—")
        is_optimal = vc.get("is_validated_optimal_entry", False)
        state_color = TEAL_DIM if is_optimal else WHITE
        state_text = (
            f"{state} — the validated research's optimal entry window (SPD=Y, DEI=N)"
            if is_optimal else
            f"{state} (SPD={'Y' if vc.get('spd') else 'N'}, DEI={'Y' if vc.get('dei') else 'N'})"
        )
        children.append(html.Div([
            slabel("Validated Research Classification"),
            html.P(state_text, style={"fontSize": "11px", "color": state_color,
                                        "lineHeight": "1.6", "marginTop": "6px", "fontWeight": "700" if is_optimal else "400"}),
            html.P(f"Obstacle score: {vc.get('obstacle_score', '—')} (raw; population quartile not computed live)",
                   style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.6", "marginTop": "4px"}),
        ], style={"marginTop": "12px"}))

    # Real Wyckoff Verdict Engine -- stopping climax, supply absorption,
    # spring, sign of strength, survival score, all computed from real
    # daily bars.
    wv = live.get("wyckoff_verdict")
    if wv and wv.get("verdict"):
        v = wv["verdict"]
        verdict_color = TEAL_DIM if v.get("birth_eligible") else MUTED
        children.append(html.Div([
            slabel("Wyckoff Verdict"),
            html.P(f"{v.get('verdict', '—')} — {v.get('phase', '—')}"
                   f"{' (birth eligible)' if v.get('birth_eligible') else ''}",
                   style={"fontSize": "11px", "color": verdict_color, "lineHeight": "1.6",
                          "marginTop": "6px", "fontWeight": "700" if v.get("birth_eligible") else "400"}),
            html.P(f"Score {v.get('wyckoff_score', '—')} · Survival {v.get('survival_score', '—')} · "
                   f"Spring {v.get('spring_score', '—')} · SOS {v.get('sign_of_strength_score', '—')}",
                   style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.6", "marginTop": "4px"}),
        ], style={"marginTop": "12px"}))

    # Real Historical Analog Engine -- matched against actual closed
    # campaigns from this app's own database, with honest confidence
    # labeling and graceful fallback to research benchmarks.
    an = live.get("campaign_analogs")
    if an and an.get("analog"):
        a = an["analog"]
        source_label = "Live analogs" if a.get("source") == "LIVE_ANALOGS" else "Research benchmark (insufficient live analogs)"
        children.append(html.Div([
            slabel("Historical Analogs"),
            html.P(f"{source_label} — {a.get('confidence_level', '—')} confidence"
                   f"{(' · n=' + str(a.get('analog_count'))) if a.get('analog_count') else ''}",
                   style={"fontSize": "11px", "color": WHITE, "lineHeight": "1.6", "marginTop": "6px"}),
            html.P(f"Success rate {a.get('success_rate', '—')}% · Avg MFE90 {a.get('avg_mfe90', '—')}% · "
                   f"Median {a.get('median_days', '—')} days",
                   style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.6", "marginTop": "4px"}),
        ], style={"marginTop": "12px"}))

    return card(children, sx={"height": "640px", "overflowY": "auto", "boxSizing": "border-box"})


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
        dcc.Loading(
            html.Div(id="exit-status", style={"marginTop":"8px","fontSize":"12px","color":TEAL_DIM}),
            type="dot", color=RED_DIM,
        ),

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
    # FIX (2026-07-28): this previously called /api/import/analysis/{USER_ID},
    # which has no matching backend route (confirmed via full route audit) and
    # always silently returned {}. The working endpoint that actually returns
    # this data is /api/trades/history in import_history_restore_api.py.
    # Its payload nests the actual numbers (total_trades, win_rate, etc.)
    # under an "analysis" key rather than at the top level, so unwrap that
    # here -- the rest of this function reads analysis.get("total_trades"),
    # analysis.get("win_rate"), etc. directly.
    _history_payload = _get("/api/trades/history")
    analysis = (_history_payload or {}).get("analysis") or {}

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
            dcc.Loading(
                html.Div(id="csv-upload-status",
                         style={"fontSize":"13px","color":TEAL_DIM,"minHeight":"20px"}),
                type="dot", color=TEAL,
            ),
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


def build_behavior_tab(session=None):
    # FIX (2026-07-28): was always fetching demo_user_001's dashboard
    # regardless of who was actually logged in.
    dash_data = _get(f"/api/behavior/dashboard/{_current_user_id(session)}", headers=_auth_headers(session))
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
                    dcc.Loading(html.Div(id="login-error", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}), type="dot", color=TEAL),
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
                    ], style={"textAlign":"center", "marginBottom": "12px"}),
                    html.Div([
                        html.Button("Forgot your password?", id="goto-forgot-btn", n_clicks=0,
                            style={"background":"none","border":"none","color":MUTED,"fontSize":"12px",
                                   "fontWeight":"600","cursor":"pointer","padding":"0","textDecoration":"underline"}),
                    ], style={"textAlign":"center"}),
                ]),

                # Forgot-password section (hidden initially) -- request a reset email
                html.Div(id="forgot-section", style={"display":"none"}, children=[
                    html.H2("Reset Password", style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"12px","textAlign":"center"}),
                    html.P("Enter your account email and we'll send you a link to set a new password.",
                           style={"fontSize":"12px","color":WHITE,"marginBottom":"20px","textAlign":"center"}),
                    html.Div([
                        html.Label("Email", style={"fontSize":"11px","fontWeight":"700","color":WHITE,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="forgot-email", type="email", placeholder="you@example.com",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"20px"}),
                    dcc.Loading(html.Div(id="forgot-message", style={"color":TEAL_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}), type="dot", color=TEAL),
                    html.Button("Send Reset Link", id="forgot-submit-btn", n_clicks=0,
                        style={"width":"100%","background":TEAL,"color":WHITE,"border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700",
                               "cursor":"pointer","marginBottom":"16px"}),
                    html.Div([
                        html.Button("Back to Sign In", id="goto-login-from-forgot-btn", n_clicks=0,
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
                    dcc.Loading(html.Div(id="signup-error", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}), type="dot", color=TEAL),
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

                # Set-new-password section (hidden initially) -- shown when a
                # Supabase recovery token is detected in the URL fragment
                # (see the client-side script in index_string that extracts it).
                html.Div(id="set-password-section", style={"display":"none"}, children=[
                    html.H2("Set New Password", style={"fontSize":"20px","fontWeight":"800","color":WHITE,"marginBottom":"24px","textAlign":"center"}),
                    html.Div([
                        html.Label("New Password", style={"fontSize":"11px","fontWeight":"700","color":WHITE,"textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="set-password-new", type="password", placeholder="Min 6 characters",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                                         "borderRadius":"8px","padding":"12px 16px","color":WHITE,"fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"24px"}),
                    dcc.Loading(html.Div(id="set-password-message", style={"color":RED_DIM,"fontSize":"12px","marginBottom":"16px","textAlign":"center"}), type="dot", color=TEAL),
                    html.Button("Set Password", id="set-password-btn", n_clicks=0,
                        style={"width":"100%","background":TEAL,"color":WHITE,"border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700",
                               "cursor":"pointer"}),
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

def _build_volume_expansion_note(price, rel_volume):
    """
    FIX (2026-08-04): this note used to be a static, always-identical
    disclaimer ("A-grade requires live-volume expansion.") that never
    reflected the actual current volume condition for the symbol being
    viewed. Now shows the real, live relative-volume reading (from the
    radar engine's own computed rel_volume, via the new
    /api/radar/symbol/{symbol} endpoint) and whether the expansion
    condition is genuinely met right now -- 1.5x average volume is a
    common, standard threshold for "unusual"/expanding volume.
    """
    EXPANSION_THRESHOLD = 1.5

    if rel_volume is None:
        return note_box(
            f"Ref: ${price:.2f}  ·  Volume data unavailable for this symbol right now.",
            "yellow",
        )

    is_expanding = rel_volume >= EXPANSION_THRESHOLD
    variant = "teal" if is_expanding else "yellow"
    status_text = "met" if is_expanding else "not met"
    return note_box(
        f"Ref: ${price:.2f}  ·  Live volume: {rel_volume:.2f}x average "
        f"({status_text} — Score Tier A requires ≥{EXPANSION_THRESHOLD:.1f}x).",
        variant,
    )


def build_direction_panel(decision, score, symbol=None, price=None, regime=None, rel_volume=None):
    """Compact, user-readable Direction & Confidence panel.

    FIX (2026-08-04): merged in the previously-separate Symbol/Live
    Price/Engine Score/Regime tile per request, so all of this related
    context lives in one place instead of two side-by-side cards.
    """
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

    extra_tiles = []
    if symbol is not None:
        extra_tiles.append(metric_tile("Symbol", symbol, WHITE))
    if price is not None:
        extra_tiles.append(metric_tile("Live Price", f"${price:.2f}", WHITE))
    extra_tiles.append(metric_tile("Engine Score", f"{score}%", color))
    if regime is not None:
        extra_tiles.append(metric_tile("Regime", regime.replace("_", " ").title(), YELLOW_DIM))

    # Persistent alert-tier indicator -- shows the CURRENT state at all
    # times (not just a transient banner on a crossing), per request.
    if score < 35:
        tier_label, tier_color = "Trap Door", RED_DIM
    elif score < 55:
        tier_label, tier_color = "Monitoring", MUTED
    elif score < 80:
        tier_label, tier_color = "Score Tier B — Audio Active", BLUE_DIM
    else:
        tier_label, tier_color = "Score Tier A — Audio Active", TEAL_DIM
    extra_tiles.append(metric_tile("Score Tier", tier_label, tier_color))

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
            metric_tile("Status - Grade", f"{status} - {grade}", color),
            metric_tile("Mode", mode, BLUE_DIM),
            *extra_tiles,
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "6px"}),
        html.Div(
            "Score Tier (below) is a separate alert system based on Engine Score -- not the same as Status - Grade above.",
            style={"fontSize": "9px", "color": MUTED, "marginTop": "10px", "fontStyle": "italic"},
        ),
        html.Div([
            html.Span("Below 35: ", style={"color": WHITE, "fontWeight": "700"}),
            html.Span("\"Trap Door\" (warning-style zone)", style={"color": RED_DIM}),
            html.Span("  ·  ", style={"color": WHITE}),
            html.Span("55-79: ", style={"color": WHITE, "fontWeight": "700"}),
            html.Span("\"Score Tier B — Audio Active\"", style={"color": BLUE_DIM}),
            html.Span("  ·  ", style={"color": WHITE}),
            html.Span("80+: ", style={"color": WHITE, "fontWeight": "700"}),
            html.Span("\"Score Tier A — Audio Active\"", style={"color": TEAL_DIM}),
        ], style={"fontSize": "10px", "marginTop": "10px", "lineHeight": "1.6"}),
        html.Div(_build_volume_expansion_note(price, rel_volume), style={"marginTop": "10px"}) if price is not None else None,
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

    # FIX (2026-07-29): the Options Matrix widget below only ever showed
    # synthetic price-percentage numbers, even though real Alpaca options
    # data is already wired up and working elsewhere in the app (the
    # Campaign Intelligence gamma overlay). Now fetches the same real
    # gamma-exposure-based call/put walls for the currently loaded symbol,
    # falling back to the synthetic model only if no real options data is
    # available for this symbol right now (e.g. options aren't listed, or
    # the chain snapshot came back empty).
    real_gamma = _get(f"/api/options/gamma-matrix/{symbol}", spot_price=price)
    has_real_options = bool(real_gamma.get("has_real_data"))
    real_call_walls = real_gamma.get("top_call_walls") or []
    real_put_walls  = real_gamma.get("top_put_walls") or []

    _REGIME_LABELS = {
        "DEEP_POSITIVE": "Deep positive gamma — strong pinning",
        "POSITIVE":      "Positive gamma — pinning likely",
        "NEUTRAL":       "Neutral gamma regime",
        "NEGATIVE":      "Negative gamma — moves can accelerate",
        "DEEP_NEGATIVE": "Deep negative gamma — high volatility risk",
    }

    if has_real_options and real_call_walls and real_put_walls:
        call_wall_level = real_call_walls[0]["strike"]
        put_wall_level  = real_put_walls[0]["strike"]
        gamma_pivot_level = real_gamma.get("zero_gamma_level") or price
        _cs = max(0.0, float(real_call_walls[0].get("call_wall_strength") or 0))
        _ps = max(0.0, float(real_put_walls[0].get("put_wall_strength") or 0))
        cp = round(_cs / (_cs + _ps) * 100) if (_cs + _ps) > 0 else 50
        pp = 100 - cp
        _regime = real_gamma.get("net_gamma_regime") or "NEUTRAL"
        gamma_flip_subtitle = _REGIME_LABELS.get(_regime, _regime.replace("_"," ").title())
        vs = max(18, min(96, round(abs(price - gamma_pivot_level) * 18 + (seq % 9) * 4)))
        fb = _regime
        options_note = f"Live options data — Alpaca chain snapshot, {real_gamma.get('contract_count', 0)} contracts."
    else:
        call_wall_level, put_wall_level, gamma_pivot_level = kl.breakout, kl.fail, kl.confirm
        vs   = max(18,min(96,round(abs(price-kl.trigger)*18+(seq%9)*4)))
        cp   = max(12,min(94,round(score+(8 if price>kl.confirm else -10)+(seq%5))))
        pp   = max(8,min(92,100-cp)); gp = max(20,min(95,round(55+(price-kl.confirm)*7)))
        gamma_flip_subtitle = f"{gp}% dealer sensitivity (synthetic)"
        fb   = "Call Accumulation / Supportive Flow" if price>=kl.confirm else "Neutral Rotation / Pinning"
        # BUG FIX (2026-07-29): this only checked `has_real_options`, but
        # we reach this branch whenever has_real_options is True AND the
        # wall lists are empty (chain data came back, just no qualifying
        # gamma walls near the current price) -- that case was wrongly
        # showing "connect Tradier or CBOE", which implies no options
        # data exists at all. That's misleading when real data genuinely
        # was received; now distinguishes the two cases correctly.
        if has_real_options:
            options_note = "Live options chain received, but no active gamma walls found near the current price — showing the synthetic model instead."
        else:
            _reason = real_gamma.get("error") or real_gamma.get("status") or "unknown_reason"
            options_note = f"Synthetic options layer — no live options data available ({_reason})."
    as_  = "Expansion Alert" if score>=80 else ("Trap-Door Alert" if price<kl.trap else "Monitoring")
    aa   = as_ != "Monitoring"
    fig  = build_chart(candles, price, nodes, tf, call_wall=call_wall_level, put_wall=put_wall_level, gamma_pivot=gamma_pivot_level)
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
            html.Span(f"Vol {(candles[-1]['v'] if candles else live['volume']):,}",
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
                build_direction_panel(decision, score, symbol=symbol, price=price, regime=regime,
                                       rel_volume=live.get("rel_volume")),
            ], style={"flex":"1.2","minWidth":"160px",
                       "borderRight":f"1px solid {BORDER}","paddingRight":"16px"}),

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
                html.P(
                    "Live gamma-exposure data from your Alpaca options chain." if has_real_options
                    else "Synthetic intelligence from price, volume, volatility proxy, and decision score.",
                    style={"fontSize":"12px","color":WHITE})]),
            badge(fb,"blue"),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start",
                   "flexWrap":"wrap","gap":"10px","marginBottom":"14px"}),
        html.Div([
            zcard("Call Wall",   f"${round(call_wall_level):.0f}",   f"{cp}% call-side pressure", TEAL_DIM),
            zcard("Put Wall",    f"${round(put_wall_level):.0f}",    f"{pp}% put-side pressure",  RED_DIM),
            zcard("Gamma Flip Point", f"${round(gamma_pivot_level):.0f}", gamma_flip_subtitle, YELLOW_DIM),
            zcard("Vol Trigger", "LIVE",                        f"{vs}% expansion energy",   TEAL_DIM),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px","marginBottom":"12px"}),
        note_box(options_note, "blue"),
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
                    ("Score Tier A — Audio Active" if score>=80 else
                     "Score Tier B — Audio Active" if score>=55 else "Monitoring"),
                    style={"fontSize":"11px","fontWeight":"700","marginTop":"3px","display":"block",
                           "color":RED_DIM if score<35 else (TEAL_DIM if score>=55 else MUTED)}),
            ]),
        ], sx={"flex":"1"}),

    ], style={**ROW,"alignItems":"start","marginBottom":"16px"})

    return html.Div([row1, row2, row3, row4],
                    style={"display":"flex","flexDirection":"column"})


def _build_heatmap_treemap(timeframe: str = "daily"):
    """
    Builds the Plotly treemap figure for the Sector/Industry Heat Map --
    sector -> industry -> symbol hierarchy, sized by volume, colored by
    real % change at the requested time frame. Similar in concept to
    Barchart's Industry Heat Map (barchart.com/stocks/sectors/industry-heat-map),
    adapted with an hourly option given this app already tracks intraday
    data, on top of Barchart's own daily/weekly/monthly-style granularity.
    """
    try:
        r = req.get(f"{BACKEND_HTTP}/api/heatmap/data", params={"timeframe": timeframe}, timeout=90)
        if r.ok:
            payload = r.json()
            request_error = ""
        else:
            payload = {}
            request_error = f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as exc:
        payload = {}
        request_error = f"request failed: {exc}"

    symbols = payload.get("symbols") or []
    if not symbols:
        detail = request_error or payload.get("reason") or "no details available"
        fig = go.Figure()
        fig.add_annotation(
            text=f"Heat map data unavailable for this time frame.<br><span style='font-size:12px'>{detail}</span>",
            showarrow=False, font=dict(color=WHITE, size=16), align="center",
        )
        fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=600)
        return fig

    ids, labels, parents, values, colors, hovertext = [], [], [], [], [], []
    sectors_seen = set()
    industries_seen = set()

    for s in symbols:
        sector = s.get("sector") or "Unknown"
        industry = s.get("industry") or "Unknown"
        ticker = s.get("ticker")
        change = s.get("change_pct") or 0
        volume = max(s.get("volume") or 0, 1)

        sector_id = f"sector::{sector}"
        industry_id = f"industry::{sector}::{industry}"
        symbol_id = f"symbol::{sector}::{industry}::{ticker}"

        if sector_id not in sectors_seen:
            ids.append(sector_id); labels.append(sector); parents.append(""); values.append(0); colors.append(0)
            hovertext.append(sector)
            sectors_seen.add(sector_id)

        if industry_id not in industries_seen:
            ids.append(industry_id); labels.append(industry); parents.append(sector_id); values.append(0); colors.append(0)
            hovertext.append(f"{industry} ({sector})")
            industries_seen.add(industry_id)

        ids.append(symbol_id)
        labels.append(ticker)
        parents.append(industry_id)
        values.append(volume)
        colors.append(change)
        hovertext.append(f"{ticker} — {change:+.2f}%<br>{industry}")

    fig = go.Figure(go.Treemap(
        ids=ids,
        labels=labels,
        parents=parents,
        values=values,
        marker=dict(
            colors=colors,
            colorscale=[[0, RED_DIM], [0.5, "#1e2a3d"], [1, TEAL_DIM]],
            cmid=0,
            line=dict(width=1, color=NAVY),
        ),
        text=hovertext,
        hoverinfo="text",
        textfont=dict(color=WHITE, size=13),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=4, r=4, t=4, b=4),
        height=650,
    )
    return fig


def build_heatmap_tab(timeframe: str = "daily"):
    """
    Sector/Industry Heat Map tab -- groups the tracked Russell 1000
    universe by real sector and industry classification (sourced
    directly from iShares' own official fund holdings export), colored
    by real price performance, with a selectable time frame. Similar in
    concept to Barchart's Industry Heat Map, adapted for this app's own
    universe and with an hourly option on top of the daily/weekly/
    monthly granularity Barchart itself offers.
    """
    timeframes = [("hourly", "Hourly"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]

    def _tf_button(key, label):
        active = key == timeframe
        return html.Button(
            label,
            id=f"heatmap-tf-{key}",
            n_clicks=0,
            style={
                "background": TEAL_GLOW if active else "transparent",
                "border": f"1px solid {TEAL if active else BORDER}",
                "borderRadius": "10px",
                "color": TEAL_DIM if active else "rgba(255,255,255,.7)",
                "cursor": "pointer",
                "fontSize": "13px",
                "fontWeight": "800",
                "padding": "8px 16px",
                "marginRight": "8px",
            },
        )

    return card([
        html.Div([
            html.Div([
                html.H2("Sector / Industry Heat Map", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE, "margin": "0 0 4px"}),
                html.P("Real Russell 1000 sector and industry groupings, colored by price performance. Box size reflects trading volume.",
                       style={"fontSize": "13px", "color": WHITE, "margin": "0"}),
            ]),
            html.Div([_tf_button(k, l) for k, l in timeframes], id="heatmap-tf-row"),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "16px"}),
        dcc.Graph(
            id="heatmap-treemap",
            figure=_build_heatmap_treemap(timeframe),
            config={"displayModeBar": False},
            style={"height": "650px", "width": "100%"},
        ),
        dcc.Store(id="heatmap-selected-tf", data=timeframe),
    ])


def build_reports_tab(selected_date=None, session=None):
    """
    Reports tab -- lets subscribers browse and read the daily
    subscriber intelligence report (backend/reports_engine.py), one
    per calendar date, generated once daily by a Render cron job.

    selected_date: the date the user currently has selected, if any.
    This callback gets re-invoked on every ~20s live-price tick (needed
    for the Command Center tab), so without this, the date picker would
    silently reset to the most recent date on every rebuild, out from
    under a user actively reading an older report.
    """
    try:
        r = req.get(f"{BACKEND_HTTP}/api/reports/list", timeout=15)
        dates = (r.json().get("dates") or []) if r.ok else []
    except Exception:
        dates = []

    _generate_control = html.Div([
        html.Label("Generate report for date:", style={"fontSize": "12px", "color": WHITE, "marginRight": "8px"}),
        dcc.Input(id="reports-generate-date", type="text", placeholder="YYYY-MM-DD",
                  style={"width": "130px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
                         "borderRadius": "8px", "padding": "8px 12px", "color": WHITE, "fontSize": "13px",
                         "marginRight": "8px"}),
        html.Button("Generate Report", id="reports-generate-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
        dcc.Loading(
            html.Div(id="reports-generate-message", style={"fontSize": "12px", "color": TEAL_DIM, "marginTop": "8px"}),
            type="dot", color=TEAL,
        ),
    ], style={"marginTop": "16px", "padding": "16px", "border": f"1px solid {BORDER}", "borderRadius": "12px"}) if is_admin(session) else None

    if not dates:
        return card([
            html.H2("Reports", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE, "marginBottom": "8px"}),
            html.P("No daily reports are available yet. The first report is generated once daily; check back after the next scheduled run.",
                   style={"fontSize": "13px", "color": "rgba(255,255,255,.6)"}),
            _generate_control,
        ])

    most_recent = selected_date if selected_date in dates else dates[0]
    try:
        r = req.get(f"{BACKEND_HTTP}/api/reports/{most_recent}", timeout=20)
        payload = r.json() if r.ok else {}
        html_doc = payload.get("html") if payload.get("ok") else None
    except Exception:
        html_doc = None

    return card([
        html.Div([
            html.Div([
                html.H2("Reports", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE, "margin": "0 0 4px"}),
                html.P("Daily subscriber intelligence report, generated once per day from the live full-universe campaign engine.",
                       style={"fontSize": "13px", "color": WHITE, "margin": "0"}),
            ]),
            html.Div([
                dcc.Dropdown(
                    id="reports-date-picker",
                    options=[{"label": d, "value": d} for d in dates],
                    value=most_recent,
                    clearable=False,
                    style={"width": "220px", "color": "#111"},
                ),
                html.A(
                    "⬇ Download PDF",
                    id="reports-download-btn",
                    href=f"{BACKEND_HTTP}/api/reports/{most_recent}/pdf?download=true",
                    download=f"Sigmalytic_Daily_Report_{most_recent}.pdf",
                    style={"background": TEAL_GLOW, "border": f"1px solid {BORDER_T}", "borderRadius": "10px",
                           "color": TEAL_DIM, "cursor": "pointer", "fontSize": "13px", "fontWeight": "800",
                           "padding": "10px 18px", "textDecoration": "none", "whiteSpace": "nowrap",
                           "marginLeft": "10px"},
                ),
            ], style={"display": "flex", "alignItems": "center"}),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "16px"}),
        _generate_control,
        html.Iframe(
            id="reports-iframe",
            srcDoc=html_doc or "<p style='font-family:sans-serif;padding:20px;'>Report content unavailable.</p>",
            style={"width": "100%", "height": "85vh", "border": f"1px solid {BORDER}", "borderRadius": "14px"},
        ),
    ])


def build_guide_tab():
    """
    User Guide tab -- serves the PDF version of the Sigmalytic V2 User
    Guide directly from the frontend's assets folder (Dash serves
    everything under frontend/assets/ automatically at /assets/<file>).
    """
    guide_path = "/assets/Sigmalytic_V2_User_Guide.pdf"
    return card([
        html.Div([
            html.Div([
                html.H2("User Guide", style={"fontSize":"18px","fontWeight":"900","color":WHITE,"margin":"0 0 4px"}),
                html.P("The complete Sigmalytic V2 user guide -- every tab explained, a daily/weekly routine, worked examples, and a full glossary.",
                       style={"fontSize":"13px","color":"rgba(255,255,255,.6)","margin":"0"}),
            ]),
            html.Div([
                html.A(
                    "Open Full Guide ↗",
                    href=guide_path,
                    target="_blank",
                    style={"background":"transparent","border":f"1px solid {BORDER_T}","borderRadius":"10px",
                           "color":WHITE,"cursor":"pointer","fontSize":"13px","fontWeight":"800",
                           "padding":"10px 18px","textDecoration":"none","whiteSpace":"nowrap",
                           "marginRight":"10px"},
                ),
                html.A(
                    "⬇ Download PDF",
                    href=guide_path,
                    download="Sigmalytic_V2_User_Guide.pdf",
                    style={"background":TEAL_GLOW,"border":f"1px solid {BORDER_T}","borderRadius":"10px",
                           "color":TEAL_DIM,"cursor":"pointer","fontSize":"13px","fontWeight":"800",
                           "padding":"10px 18px","textDecoration":"none","whiteSpace":"nowrap"},
                ),
            ], style={"display":"flex","alignItems":"center"}),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"center","marginBottom":"16px"}),
        html.Div(
            "On mobile, tap \"Open Full Guide\" above for the best reading experience -- PDFs don't scroll properly inside this preview on phones. To return to the app afterward, look for a \"Done\" button in the top corner of the screen.",
            id="guide-mobile-note",
            style={"display":"none","fontSize":"13px","color":"rgba(255,255,255,.7)",
                   "padding":"14px","border":f"1px solid {BORDER_T}","borderRadius":"10px",
                   "marginBottom":"12px"},
        ),
        html.Iframe(
            id="guide-pdf-iframe",
            src=guide_path,
            style={"width":"100%","height":"85vh","border":f"1px solid {BORDER}","borderRadius":"14px"},
        ),
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

    def _score_grade(score):
        """
        Genuine composite_score-based letter grade -- matches the
        exact same established thresholds already used in backend/
        main.py's _compat_grade() and backend/intelligence_api.py's
        _grade(), a real, in-production convention. Applied here to
        the genuine, symbol-specific composite_score, not the removed,
        probability-engine-derived probability_grade.
        """
        if score >= 85:
            return "A+"
        if score >= 75:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        return "W"

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
        setup_risk_reward = s.get("setup_risk_reward")
        wyckoff_verdict = s.get("wyckoff_verdict") if isinstance(s.get("wyckoff_verdict"), dict) else None
        livermore_verdict = s.get("livermore_verdict") if isinstance(s.get("livermore_verdict"), dict) else None
        weis_verdict = s.get("weis_verdict") if isinstance(s.get("weis_verdict"), dict) else None
        score_color = TEAL_DIM if score >= 75 else (YELLOW_DIM if score >= 60 else RED_DIM)

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
                    html.Div(f"{score:.0f}", style={
                        "fontSize":"30px","fontWeight":"950","color":score_color,
                        "lineHeight":"1","textAlign":"right"
                    }),
                    html.Div("Score", style={
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
                    html.Div("Risk/Reward", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(
                        f"{setup_risk_reward:.2f}" if isinstance(setup_risk_reward, (int, float)) else "—",
                        style={"fontSize":"18px","fontWeight":"950",
                               "color": (TEAL_DIM if setup_risk_reward >= 2.0 else YELLOW_DIM) if isinstance(setup_risk_reward, (int, float)) else MUTED},
                    ),
                ], style={"flex":"1"}),
            ], style={"display":"flex","gap":"10px","padding":"10px","border":f"1px solid {BORDER}","borderRadius":"12px","background":"rgba(255,255,255,.035)"}),

            html.Div(style={"height":"12px"}) if (wyckoff_verdict or livermore_verdict or weis_verdict) else None,

            html.Div([
                html.Div("Methodology Breakdown", style={
                    "fontSize":"10px","fontWeight":"950","color":WHITE,
                    "textTransform":"uppercase","letterSpacing":".08em","marginBottom":"6px"
                }),
                html.Div([
                    html.Div([
                        html.Div("Wyckoff", style={"fontSize":"9px","fontWeight":"900","color":WHITE,"textTransform":"uppercase"}),
                        html.Div(f"{wyckoff_verdict.get('wyckoff_score', 0):.0f}" if wyckoff_verdict else "—",
                                 style={"fontSize":"16px","fontWeight":"950","color":TEAL_DIM}),
                        html.Div(_safe_text(wyckoff_verdict.get("verdict") if wyckoff_verdict else None, "—"),
                                 style={"fontSize":"9px","color":MUTED,"fontWeight":"700"}),
                    ], style={"flex":"1"}),
                    html.Div([
                        html.Div("Livermore", style={"fontSize":"9px","fontWeight":"900","color":WHITE,"textTransform":"uppercase"}),
                        html.Div(f"{livermore_verdict.get('livermore_score', 0):.0f}" if livermore_verdict else "—",
                                 style={"fontSize":"16px","fontWeight":"950","color":BLUE_DIM}),
                        html.Div(_safe_text(livermore_verdict.get("verdict") if livermore_verdict else None, "—"),
                                 style={"fontSize":"9px","color":MUTED,"fontWeight":"700"}),
                    ], style={"flex":"1"}),
                    html.Div([
                        html.Div("Weis", style={"fontSize":"9px","fontWeight":"900","color":WHITE,"textTransform":"uppercase"}),
                        html.Div(f"{weis_verdict.get('weis_score', 0):.0f}" if weis_verdict else "—",
                                 style={"fontSize":"16px","fontWeight":"950","color":YELLOW_DIM}),
                        html.Div(_safe_text(weis_verdict.get("verdict") if weis_verdict else None, "—"),
                                 style={"fontSize":"9px","color":MUTED,"fontWeight":"700"}),
                    ], style={"flex":"1"}),
                ], style={"display":"flex","gap":"10px"}),
            ], style={"padding":"10px","border":f"1px solid {BORDER}","borderRadius":"12px","background":"rgba(255,255,255,.02)"}) if (wyckoff_verdict or livermore_verdict or weis_verdict) else html.Div(),

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
                html.Div(setup, style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"800"}),
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
        setup_risk_reward = s.get("setup_risk_reward")
        wyckoff_verdict = s.get("wyckoff_verdict") if isinstance(s.get("wyckoff_verdict"), dict) else None
        livermore_verdict = s.get("livermore_verdict") if isinstance(s.get("livermore_verdict"), dict) else None
        weis_verdict = s.get("weis_verdict") if isinstance(s.get("weis_verdict"), dict) else None
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
            html.Span(
                f"{setup_risk_reward:.2f}" if isinstance(setup_risk_reward, (int, float)) else "—",
                style={
                    "flex":"0 0 66px","fontSize":"12px","fontWeight":"900",
                    "color": (TEAL_DIM if setup_risk_reward >= 2.0 else YELLOW_DIM) if isinstance(setup_risk_reward, (int, float)) else MUTED,
                    "textAlign":"center"
                },
            ),
            html.Span(
                f"{wyckoff_verdict.get('wyckoff_score', 0):.0f}" if wyckoff_verdict else "—",
                style={
                    "flex":"0 0 60px","fontSize":"11px","fontWeight":"900",
                    "color": TEAL_DIM if wyckoff_verdict else MUTED,
                    "textAlign":"center"
                },
            ),
            html.Span(
                f"{livermore_verdict.get('livermore_score', 0):.0f}" if livermore_verdict else "—",
                style={
                    "flex":"0 0 60px","fontSize":"11px","fontWeight":"900",
                    "color": BLUE_DIM if livermore_verdict else MUTED,
                    "textAlign":"center"
                },
            ),
            html.Span(
                f"{weis_verdict.get('weis_score', 0):.0f}" if weis_verdict else "—",
                style={
                    "flex":"0 0 60px","fontSize":"11px","fontWeight":"900",
                    "color": YELLOW_DIM if weis_verdict else MUTED,
                    "textAlign":"center"
                },
            ),
        ], style={
            "display":"flex","alignItems":"center","gap":"10px",
            "padding":"11px 0","borderBottom":f"1px solid {BORDER}",
            "minWidth":"1900px"
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
        html.Span("R:R", style={"flex":"0 0 66px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Wyckoff", style={"flex":"0 0 60px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Livermore", style={"flex":"0 0 60px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Weis", style={"flex":"0 0 60px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
    ], style={
        "display":"flex","gap":"10px","paddingBottom":"8px",
        "borderBottom":f"1px solid {BORDER}","marginBottom":"4px",
        "minWidth":"1900px"
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
                         style={"fontSize":"12px","color":WHITE,"fontWeight":"850","marginBottom":"4px"}),
                html.Div("⟷ Scroll right for more columns, including Trigger, Invalid, R:R, Wyckoff, Livermore, and Weis",
                         style={"fontSize":"11px","color":YELLOW_DIM,"fontWeight":"800","marginBottom":"12px"}),
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
        dcc.Loading(
            html.Div(id="prefs-status", style={"textAlign":"center","fontSize":"13px",
                     "minHeight":"24px","marginBottom":"8px","color":TEAL_DIM}),
            type="dot", color=TEAL,
        ),

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

# SECURITY FIX (2026-08-03): user wants staff (not just a single owner) to
# have admin access. The single ADMIN_EMAIL check above can't support that
# at all -- extended to also support a comma-separated list, matching the
# backend's require_admin dependency (backend/main.py) exactly, so both
# sides agree on who counts as admin/staff.
def _get_admin_emails() -> set:
    raw = os.getenv("SIGMALYTIC_ADMIN_EMAILS") or os.getenv("SIGMALYTIC_ADMIN_EMAIL") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


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
    email = (session or {}).get("email", "").strip().lower()
    return bool(email) and email in _get_admin_emails()


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

    # ── Setup & Deployment (merged in from the removed Setup tab) ──────────
    # Defined here, before the early-return check below, and unconditionally
    # appended in both the early-return and full-assembly paths further down
    # -- this is static config info that shouldn't depend on whether the
    # admin report data itself loads successfully.
    setup_deployment_block = _admin_card([
        html.Div("SETUP & DEPLOYMENT", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "12px"}),
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
            style={"margin": "0", "borderRadius": "14px", "border": f"1px solid {BORDER}",
                   "background": "rgba(0,0,0,.35)", "padding": "16px", "color": TEAL_DIM,
                   "fontSize": "12px", "fontFamily": "DM Mono, monospace", "lineHeight": "1.7"}),
    ], sx={"marginBottom": "16px"})

    # ── Symbol Backtest -- single-symbol, full-history check against the
    # production lookup table's own profile definitions, powered by the
    # new /api/admin/symbol-backtest/{symbol} endpoint. Defined here,
    # unconditionally appended like setup_deployment_block above, so it's
    # available regardless of whether the admin report data itself loads.
    symbol_backtest_block = _admin_card([
        html.Div("SYMBOL BACKTEST", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Runs a real, single-symbol backtest against the full available "
            "Alpaca history, using the same production classification logic "
            "as the live radar scan -- for checking whether a specific "
            "profile (Compression Breakout Candidate / Compression to "
            "Expansion Attempt / 90+ Elite readiness) holds up over a longer "
            "timeframe than the current 2-year production lookup table. Can "
            "take a minute or more to run.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Div([
            dcc.Input(id="backtest-symbol", type="text", placeholder="Symbol (e.g. TDY)",
                      style={"width": "160px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
                             "borderRadius": "8px", "padding": "8px 12px", "color": WHITE, "fontSize": "13px",
                             "marginRight": "8px"}),
            dcc.Input(id="backtest-years", type="number", placeholder="Years", value=5, min=1, max=6,
                      style={"width": "80px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
                             "borderRadius": "8px", "padding": "8px 12px", "color": WHITE, "fontSize": "13px",
                             "marginRight": "8px"}),
            html.Button("Run Backtest", id="backtest-run-btn", n_clicks=0,
                style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                       "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
        ], style={"marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="backtest-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    # ── Portfolio Rankings + Decay Monitor -- same pattern as Generate
    # Report and Symbol Backtest above: real, working admin actions that
    # previously required dev tools/manual fetch() calls to trigger.
    # No symbol/date inputs needed -- both operate across the full
    # active-campaign set, not a single symbol.
    portfolio_rankings_block = _admin_card([
        html.Div("PORTFOLIO RANKINGS (Layer 4)", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Deduplicates active campaigns down to one current record per "
            "symbol, scores each on strength/analog/risk, and writes "
            "priority-banded rankings to the campaigns database. Runs "
            "across the full active-campaign set.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Run Portfolio Rankings", id="portfolio-rankings-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="portfolio-rankings-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    decay_monitor_block = _admin_card([
        html.Div("DECAY MONITOR (Layer 7)", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Scores every active campaign into HEALTHY/MONITOR/WEAKENING/"
            "EXIT_CANDIDATE bands per the research's own decay methodology, "
            "and persists results back to the campaigns database.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Run Decay Monitor", id="decay-monitor-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="decay-monitor-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    # ── Subscriber Alerts -- distinct from the other admin actions above:
    # this genuinely sends real emails to real subscribers, not an
    # internal-only batch operation. Clearly warned in the UI itself.
    closure_engine_block = _admin_card([
        html.Div("CLOSURE ENGINE", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Evaluates active campaigns for closure (target reached, stop "
            "hit, operator exit, timeout, or invalidation) and closes them "
            "in the campaigns database. This endpoint was already correctly "
            "wired on the backend -- just missing a way to trigger it "
            "without dev tools.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Run Closure Engine", id="closure-engine-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="closure-engine-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    state_transition_block = _admin_card([
        html.Div("STATE TRANSITION ENGINE", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Computes calibrated advance/failure probabilities for every "
            "active campaign, blending each lifecycle state's base "
            "expectation with real historical rates. A direct dependency "
            "of Campaign Outcome Engine below -- run this first for "
            "genuinely calibrated results.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Run State Transition Engine", id="state-transition-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="state-transition-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    campaign_outcome_block = _admin_card([
        html.Div("CAMPAIGN OUTCOME ENGINE", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Computes Expected Return using a live blend of campaign lifecycle "
            "state, operator dominance, decay, and real current evidence -- "
            "not the static historical average discussed earlier tonight. "
            "Writes results back to the campaigns database.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Run Campaign Outcome Engine", id="campaign-outcome-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="campaign-outcome-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    real_scoreboard_stats_block = _admin_card([
        html.Div("REAL TRACK RECORD STATISTICS", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Genuine win rates, hit rates, MFE/MAE, and direction "
            "accuracy computed from the app's own actual logged signal "
            "history and outcomes -- not the campaign-intelligence "
            "compatibility view already shown in the Scoreboard tab. "
            "Confirmed this real data was never surfaced anywhere "
            "until now.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Load Real Stats", id="real-stats-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="real-stats-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    scoreboard_maintenance_block = _admin_card([
        html.Div("SCOREBOARD MAINTENANCE", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Two real, working maintenance utilities directly supporting "
            "the real track record data above. Repair backfills missing "
            "grades/path metrics on older rows (explicitly documented as "
            "safe to run repeatedly). Clear Duplicates removes duplicate "
            "signal rows, keeping only the most recent per symbol per day.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Div([
            html.Button("Repair History", id="repair-scoreboard-btn", n_clicks=0,
                style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                       "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                       "marginRight": "10px"}),
            html.Button("Clear Duplicates", id="clear-duplicates-btn", n_clicks=0,
                style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                       "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
        ], style={"marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="scoreboard-maintenance-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    journal_correction_block = _admin_card([
        html.Div("JOURNAL ENTRY CORRECTION", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "For support use when a subscriber reports a mistake in "
            "their journal entry (wrong symbol, price, or shares "
            "typed in). Deletes the specified entry so the subscriber "
            "can simply re-log a corrected one. Requires the exact "
            "journal_id -- ask the subscriber for it, or look it up "
            "via their trade history.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Div([
            dcc.Input(id="journal-delete-id", type="text", placeholder="journal_id (e.g. jrn_...)",
                      style={"width": "260px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
                             "borderRadius": "8px", "padding": "8px 12px", "color": WHITE, "fontSize": "13px",
                             "marginRight": "8px"}),
            html.Button("Delete Entry", id="journal-delete-btn", n_clicks=0,
                style={"background": RED_DIM, "color": NAVY, "border": "none", "borderRadius": "8px",
                       "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
        ], style={"marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="journal-delete-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=RED_DIM,
        ),
    ], sx={"marginBottom": "16px"})

    bme_memory_status_block = _admin_card([
        html.Div("BME MEMORY BANK STATUS", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Real, direct check of the Behavioral Memory Engine's "
            "actual current state -- how many symbols have genuinely "
            "been trained. If a symbol shows 'Deep engine confirms "
            "radar (+0.0)' on the Radar Screen, this tells you whether "
            "that's expected (the symbol simply isn't trained yet) or "
            "a real, ongoing problem (it's trained but still showing "
            "the neutral default).",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Check Memory Status", id="bme-status-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="bme-status-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    operator_footprint_block = _admin_card([
        html.Div("EARLY OPERATOR FOOTPRINT REVIEW", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Real, read-only diagnostic (confirmed database-only, never "
            "called from the frontend until now) showing early Composite "
            "Operator footprint evidence across all active campaigns -- "
            "distributions by archetype, risk context, and footprint "
            "count, sorted by footprint strength.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Button("Load Footprint Review", id="operator-footprint-btn", n_clicks=0,
            style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="operator-footprint-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    enriched_campaign_table_block = _admin_card([
        html.Div("ENRICHED CAMPAIGN TABLE (7-Year ODS Evidence)", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "A real, already-built endpoint (confirmed live but never called "
            "from the frontend until now) that formally confirms Operator "
            "Dominance/Control only from direct evidence in 7 years of real "
            "price/volume history -- supply exhaustion, demand/support "
            "validation, structural location, absence of contrary failure. "
            "Fetches real Alpaca bars for each symbol, so this can take a "
            "while for larger limits.",
            style={"fontSize": "11px", "color": MUTED, "marginBottom": "14px", "lineHeight": "1.6"},
        ),
        html.Div([
            dcc.Input(id="enriched-table-limit", type="number", placeholder="Limit", value=25, min=1, max=250,
                      style={"width": "80px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
                             "borderRadius": "8px", "padding": "8px 12px", "color": WHITE, "fontSize": "13px",
                             "marginRight": "8px"}),
            html.Button("Load Enriched Table", id="enriched-table-btn", n_clicks=0,
                style={"background": TEAL, "color": WHITE, "border": "none", "borderRadius": "8px",
                       "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer"}),
        ], style={"marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="enriched-table-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    subscriber_alerts_block = _admin_card([
        html.Div("SEND SUBSCRIBER ALERTS", style={"fontSize": "12px", "fontWeight": "800",
                  "color": WHITE, "marginBottom": "6px"}),
        html.Div(
            "Sends real email alerts to real subscribers for currently-active "
            "TIER_1/TIER_2 campaigns. This genuinely sends live emails -- "
            "not a preview or dry run.",
            style={"fontSize": "11px", "color": YELLOW_DIM, "marginBottom": "14px",
                   "lineHeight": "1.6", "fontWeight": "700"},
        ),
        html.Button("Send Subscriber Alerts", id="subscriber-alerts-btn", n_clicks=0,
            style={"background": RED_DIM, "color": WHITE, "border": "none", "borderRadius": "8px",
                   "padding": "10px 16px", "fontSize": "13px", "fontWeight": "700", "cursor": "pointer",
                   "marginBottom": "14px"}),
        dcc.Loading(
            html.Div(id="subscriber-alerts-result", style={"fontSize": "12px", "color": WHITE}),
            type="dot", color=TEAL,
        ),
    ], sx={"marginBottom": "16px"})

    if not data:
        # FIX: was `_admin_card([...])` -- _card only exists as a local nested
        # function inside build_preferences_tab and is not visible here.
        # _admin_card is the real module-level equivalent already defined above.
        return html.Div([
            _admin_card([
                html.Div("Could not load admin report.", style={"color":YELLOW_DIM,"fontSize":"14px"}),
                html.Div("Backend may be initializing. Refresh in 30 seconds.",
                         style={"color":WHITE,"fontSize":"12px","marginTop":"8px"}),
            ], sx={"marginBottom": "16px"}),
            setup_deployment_block,
            symbol_backtest_block,
            portfolio_rankings_block,
            decay_monitor_block,
            closure_engine_block,
            state_transition_block,
            campaign_outcome_block,
            real_scoreboard_stats_block,
            scoreboard_maintenance_block,
            journal_correction_block,
            bme_memory_status_block,
            operator_footprint_block,
            enriched_campaign_table_block,
            subscriber_alerts_block,
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
        setup_deployment_block,
        symbol_backtest_block,
        portfolio_rankings_block,
        decay_monitor_block,
        closure_engine_block,
        state_transition_block,
        campaign_outcome_block,
        real_scoreboard_stats_block,
        scoreboard_maintenance_block,
        journal_correction_block,
        bme_memory_status_block,
        operator_footprint_block,
        enriched_campaign_table_block,
        subscriber_alerts_block,

        # Footer
        html.Div("SIGMALYTIC QUANT CORPORATION  ·  PROPRIETARY & CONFIDENTIAL  ·  INTERNAL USE ONLY",
                 style={"textAlign":"center","fontSize":"9px","color":WHITE,
                        "letterSpacing":".2em","paddingTop":"16px","paddingBottom":"8px"}),
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
        "frame-src 'self' https://js.stripe.com https://hooks.stripe.com https://sigmalytic-backend.onrender.com; "
        "connect-src 'self' https://api.stripe.com https://sigmalytic-backend.onrender.com; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:;"
    )
    return response


# Extracts a Supabase password-recovery access_token from the URL
# fragment (e.g. #access_token=...&type=recovery). This MUST run
# client-side: the fragment is never sent to the server at all, so no
# Python/server-side code can read it -- only JavaScript in the
# browser can. Runs once per page load, triggered by the existing
# dcc.Location component's href updating.
app.clientside_callback(
    """
    function(href) {
        if (!href) { return null; }
        var hash = window.location.hash;
        if (!hash || hash.indexOf('type=recovery') === -1) { return null; }
        var params = new URLSearchParams(hash.substring(1));
        var token = params.get('access_token');
        return token || null;
    }
    """,
    Output("s-recovery-token", "data"),
    Input("url", "href"),
)


@app.callback(
    Output("reports-iframe", "srcDoc"),
    Output("reports-download-btn", "href"),
    Output("reports-download-btn", "download"),
    Input("reports-date-picker", "value"),
    prevent_initial_call=True,
)
def update_report_view(selected_date):
    if not selected_date:
        return no_update, no_update, no_update
    download_href = f"{BACKEND_HTTP}/api/reports/{selected_date}/pdf?download=true"
    download_name = f"Sigmalytic_Daily_Report_{selected_date}.pdf"
    try:
        r = req.get(f"{BACKEND_HTTP}/api/reports/{selected_date}", timeout=20)
        payload = r.json() if r.ok else {}
        if payload.get("ok"):
            return payload.get("html"), download_href, download_name
    except Exception:
        pass
    return "<p style='font-family:sans-serif;padding:20px;'>Report content unavailable.</p>", download_href, download_name


@app.callback(Output("reports-generate-message","children"),
              Output("reports-date-picker","options"),
              Output("reports-date-picker","value"),
              Input("reports-generate-btn","n_clicks"),
              State("reports-generate-date","value"),
              State("s-session","data"),
              prevent_initial_call=True)
def handle_generate_report(n_clicks, date_str, session):
    """
    Admin-only 'Generate Report' button. Replaces the direct-URL-visit
    workflow (visiting /api/admin/generate-report?date=... in a browser)
    now that that endpoint requires a proper Bearer token -- a plain
    browser navigation can't attach one, so this needed a real in-app
    control that sends the auth header via a normal HTTP request instead.

    FIX (2026-08-07): confirmed a real bug -- a successful generation
    said 'Select it from the date dropdown above', but the dropdown
    itself lives inside build_reports_tab(), which only rebuilds on a
    genuine tab switch (a deliberate 2026-07-31 fix to stop the date
    picker resetting while a user reads an older report). This
    separate callback never touched the dropdown at all, so the newly
    generated date genuinely never appeared until the user manually
    switched tabs away and back. Now directly re-fetches the real,
    current list and updates the dropdown's options/value after a
    successful generation, without needing to rebuild the whole tab
    (so the original 2026-07-31 fix stays intact).
    """
    if not date_str:
        return "Please enter a date in YYYY-MM-DD format.", no_update, no_update

    try:
        r = req.get(
            f"{BACKEND_HTTP}/api/admin/generate-report",
            params={"date": date_str},
            headers=_auth_headers(session),
            timeout=180,  # fetches 7 years of history for up to 100 symbols; can genuinely take a while
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again.", no_update, no_update
        if r.status_code == 403:
            return "Admin access only.", no_update, no_update
        if not r.ok:
            return f"Generation failed (error {r.status_code}): {r.text[:200]}", no_update, no_update
        payload = r.json()
        if not payload.get("ok"):
            return f"Generation failed: {payload.get('error', 'unknown error')}", no_update, no_update

        try:
            list_resp = req.get(f"{BACKEND_HTTP}/api/reports/list", timeout=15)
            dates = (list_resp.json().get("dates") or []) if list_resp.ok else []
        except Exception:
            dates = []

        if date_str not in dates:
            dates = [date_str] + dates

        options = [{"label": d, "value": d} for d in dates]
        return (
            f"Report generated successfully for {date_str}.",
            options,
            date_str,
        )
    except Exception as exc:
        return f"Could not reach the backend: {exc}", no_update, no_update

@app.callback(Output("backtest-result", "children"),
              Input("backtest-run-btn", "n_clicks"),
              State("backtest-symbol", "value"),
              State("backtest-years", "value"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_symbol_backtest(n_clicks, symbol, years, session):
    """
    Admin-only 'Run Backtest' button, calling the new
    /api/admin/symbol-backtest/{symbol} endpoint -- follows the same
    pattern as handle_generate_report (proper Bearer auth header via a
    normal callback-driven request, generous timeout since this
    genuinely takes a while: roughly one classification call per
    trading day in the lookback window).
    """
    if not symbol:
        return "Please enter a symbol."

    sym = symbol.strip().upper()
    yrs = years or 5

    try:
        r = req.get(
            f"{BACKEND_HTTP}/api/admin/symbol-backtest/{sym}",
            params={"years": yrs},
            headers=_auth_headers(session),
            timeout=180,  # genuinely slow -- ~1250 classification calls for 5 years
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Backtest failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Backtest failed: {payload.get('error', 'unknown error')}"

        matches = payload.get("profile_matches_found", 0)
        if matches == 0:
            return (
                f"{sym}: no matches found for this profile across "
                f"{payload.get('total_daily_bars', 0)} trading days "
                f"({yrs} years) of history."
            )

        return html.Div([
            html.Div(f"{sym} — {yrs} year(s), {payload.get('total_daily_bars', 0)} trading days scanned",
                     style={"fontWeight": "700", "marginBottom": "8px"}),
            html.Div(f"Profile matches found: {matches}", style={"marginBottom": "6px"}),
            html.Div(f"Avg return — 5d: {payload.get('avg_return_5d')}%  ·  "
                     f"10d: {payload.get('avg_return_10d')}%  ·  "
                     f"20d: {payload.get('avg_return_20d')}%  ·  "
                     f"90d: {payload.get('avg_return_90d')}%", style={"marginBottom": "6px"}),
            html.Div(f"Avg 90d MFE: {payload.get('avg_mfe_90d')}%  ·  "
                     f"Avg 90d MAE: {payload.get('avg_mae_90d')}%", style={"marginBottom": "6px"}),
            html.Div(f"Match dates: {', '.join(payload.get('match_dates', [])[:20])}",
                     style={"fontSize": "10px", "color": MUTED}),
        ])
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("enriched-table-result", "children"),
              Input("enriched-table-btn", "n_clicks"),
              State("enriched-table-limit", "value"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_enriched_table(n_clicks, limit, session):
    """
    Calls the real, already-live /api/campaigns/read-only/full-universe-
    enriched-campaign-table endpoint (found via audit -- genuinely
    mounted and working, but confirmed never called from the frontend
    at all). Fetches real Alpaca bars per symbol, so kept on-demand
    with an admin-set limit rather than run automatically.
    """
    try:
        r = req.get(
            f"{BACKEND_HTTP}/api/campaigns/read-only/full-universe-enriched-campaign-table",
            params={"limit": limit or 25},
            headers=_auth_headers(session),
            timeout=120,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        rows = payload.get("rows", [])
        coverage = payload.get("coverage", {})

        if not rows:
            return f"No rows returned. Coverage: {coverage}"

        header = html.Tr([
            html.Th(h, style={"textAlign": "left", "padding": "6px 10px", "fontSize": "10px",
                               "color": MUTED, "borderBottom": f"1px solid {BORDER}"})
            for h in ["Symbol", "State", "Score", "ODS Status", "ODS Label", "Price"]
        ])
        body_rows = []
        for row in rows[:100]:
            body_rows.append(html.Tr([
                html.Td(row.get("symbol", "—"), style={"padding": "6px 10px", "fontSize": "11px", "color": WHITE}),
                html.Td(row.get("state", "—"), style={"padding": "6px 10px", "fontSize": "11px", "color": WHITE}),
                html.Td(str(row.get("score", "—")), style={"padding": "6px 10px", "fontSize": "11px", "color": WHITE}),
                html.Td(row.get("ods_status", "—"), style={"padding": "6px 10px", "fontSize": "11px",
                        "color": TEAL_DIM if row.get("ods_status") == "CONFIRMED" else MUTED}),
                html.Td(row.get("ods_label", "—"), style={"padding": "6px 10px", "fontSize": "10px", "color": MUTED}),
                html.Td(f"${row.get('price', 0):,.2f}" if row.get("price") else "—",
                        style={"padding": "6px 10px", "fontSize": "11px", "color": WHITE}),
            ]))

        return html.Div([
            html.Div(f"{coverage.get('enriched_rows', len(rows))} rows · "
                     f"{coverage.get('coverage_pct', '—')}% coverage",
                     style={"fontSize": "11px", "color": MUTED, "marginBottom": "10px"}),
            html.Table([html.Thead(header), html.Tbody(body_rows)],
                       style={"width": "100%", "borderCollapse": "collapse"}),
        ], style={"maxHeight": "500px", "overflowY": "auto"})
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("operator-footprint-result", "children"),
              Input("operator-footprint-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_operator_footprint(n_clicks, session):
    """
    Calls the real, already-mounted /api/campaign/early-operator-
    footprint-review endpoint (found via full audit of campaign_api.py
    -- confirmed database-only, genuinely mounted, but never called
    from the frontend at all).
    """
    try:
        r = req.get(
            f"{BACKEND_HTTP}/api/campaign/early-operator-footprint-review",
            headers=_auth_headers(session),
            timeout=30,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()

        rows = payload.get("review_rows", [])[:20]
        if not rows:
            return f"No footprint rows found. {payload.get('total_campaigns', 0)} total campaigns reviewed."

        header = html.Tr([
            html.Th(h, style={"textAlign": "left", "padding": "6px 10px", "fontSize": "10px",
                               "color": MUTED, "borderBottom": f"1px solid {BORDER}"})
            for h in ["Symbol", "Footprint Count", "Archetype", "Risk Context", "State"]
        ])
        body_rows = [
            html.Tr([
                html.Td(row.get("symbol", "—"), style={"padding": "6px 10px", "fontSize": "11px", "color": WHITE}),
                html.Td(str(row.get("footprint_count", "—")), style={"padding": "6px 10px", "fontSize": "11px", "color": TEAL_DIM}),
                html.Td(str(row.get("archetype", "—")), style={"padding": "6px 10px", "fontSize": "10px", "color": MUTED}),
                html.Td(str(row.get("risk_context", "—")), style={"padding": "6px 10px", "fontSize": "10px", "color": MUTED}),
                html.Td(str(row.get("campaign_state", "—")), style={"padding": "6px 10px", "fontSize": "11px", "color": WHITE}),
            ])
            for row in rows
        ]

        return html.Div([
            html.Div(f"{payload.get('total_campaigns', 0)} campaigns reviewed · "
                     f"{payload.get('review_rows_count', 0)} with footprint evidence",
                     style={"fontSize": "11px", "color": MUTED, "marginBottom": "10px"}),
            html.Table([html.Thead(header), html.Tbody(body_rows)],
                       style={"width": "100%", "borderCollapse": "collapse"}),
        ], style={"maxHeight": "500px", "overflowY": "auto"})
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("real-stats-result", "children"),
              Input("real-stats-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_real_stats(n_clicks, session):
    """
    Calls the real, honest scoreboard statistics endpoint (found via
    audit tonight -- confirmed genuinely never surfaced anywhere,
    distinct from the campaign-intelligence compatibility view already
    shown in the Scoreboard tab).
    """
    try:
        r = req.get(f"{BACKEND_HTTP}/api/scoreboard/real-stats", timeout=30)
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        stats = payload.get("stats", {})

        total = stats.get("total_signals", 0)
        if not total:
            return "No signals logged yet, or DATABASE_URL isn't configured on this environment."

        metrics = [
            ("Total signals", total),
            ("With outcomes", stats.get("with_outcomes")),
            ("Grade A / B / C / W", f"{stats.get('grade_a', 0)} / {stats.get('grade_b', 0)} / {stats.get('grade_c', 0)} / {stats.get('grade_w', 0)}"),
            ("High confidence (A+B) rate", f"{stats.get('high_confidence', 0)}%"),
            ("Direction correct rate", f"{stats.get('direction_correct_rate', 0)}%"),
            ("Hit target 1 / target 2 rate", f"{stats.get('hit_target1_rate', 0)}% / {stats.get('hit_target2_rate', 0)}%"),
            ("Avg MFE / MAE", f"{stats.get('avg_mfe_pct', 0)}% / {stats.get('avg_mae_pct', 0)}%"),
            ("Edge ratio (MFE:MAE)", stats.get("edge_ratio", "—")),
            ("Edge accuracy rate", f"{stats.get('edge_accuracy_rate', 0)}%"),
            ("Avg long / short return", f"{stats.get('avg_long_pct', 0)}% / {stats.get('avg_short_pct', 0)}%"),
            ("Avg days to outcome", stats.get("avg_days", 0)),
        ]

        rows = [
            html.Tr([
                html.Td(label, style={"padding": "6px 10px", "fontSize": "11px", "color": MUTED}),
                html.Td(str(value), style={"padding": "6px 10px", "fontSize": "12px", "color": WHITE, "fontWeight": "700"}),
            ])
            for label, value in metrics
        ]

        return html.Table([html.Tbody(rows)], style={"width": "100%", "borderCollapse": "collapse"})
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("scoreboard-maintenance-result", "children"),
              Input("repair-scoreboard-btn", "n_clicks"),
              Input("clear-duplicates-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_scoreboard_maintenance(repair_clicks, clear_clicks, session):
    """
    Admin-only maintenance buttons sharing one output -- uses
    callback_context to determine which button was actually clicked,
    calling the corresponding real backend endpoint.
    """
    trigger = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
    try:
        if trigger.startswith("repair-scoreboard-btn"):
            r = req.post(f"{BACKEND_HTTP}/api/admin/repair-scoreboard-history",
                         headers=_auth_headers(session), timeout=60)
        elif trigger.startswith("clear-duplicates-btn"):
            r = req.post(f"{BACKEND_HTTP}/api/admin/clear-duplicate-signals",
                         headers=_auth_headers(session), timeout=60)
        else:
            return no_update

        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        return f"Complete: {payload}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("journal-delete-result", "children"),
              Input("journal-delete-btn", "n_clicks"),
              State("journal-delete-id", "value"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_journal_delete_entry(n_clicks, journal_id, session):
    """
    For support use when a subscriber reports a mistake in their
    journal entry. Calls the new, admin-only
    DELETE /api/journal/entry/{journal_id} endpoint.
    """
    if not n_clicks:
        return no_update
    if not journal_id or not str(journal_id).strip():
        return "Please enter a journal_id."
    try:
        r = req.delete(
            f"{BACKEND_HTTP}/api/journal/entry/{journal_id.strip()}",
            headers=_auth_headers(session), timeout=15,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if r.status_code == 404:
            return f"No journal entry found with id: {journal_id}"
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        deleted = payload.get("deleted", {})
        return (f"Deleted: {deleted.get('symbol', '—')} entry "
                f"(entered {deleted.get('entry_date', '—')}, journal_id={journal_id})")
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("bme-status-result", "children"),
              Input("bme-status-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_bme_status(n_clicks, session):
    """
    Real, authenticated call to the BME memory status diagnostic --
    a plain browser URL visit can't attach the required admin auth
    token, so this button provides the actual way to check it.
    """
    if not n_clicks:
        return no_update
    try:
        r = req.get(
            f"{BACKEND_HTTP}/api/admin/bme-memory-status",
            headers=_auth_headers(session), timeout=15,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        trained = payload.get("symbols_trained", 0)
        symbols = payload.get("symbols", [])
        if trained == 0:
            return "0 symbols trained. Every symbol will show the neutral (+0.0) default until training accumulates."
        preview = ", ".join(symbols[:20])
        more = f" (+{len(symbols) - 20} more)" if len(symbols) > 20 else ""
        return f"{trained} symbols trained: {preview}{more}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("portfolio-rankings-result", "children"),
              Input("portfolio-rankings-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_portfolio_rankings(n_clicks, session):
    """
    Admin-only 'Run Portfolio Rankings' button, calling the real
    POST /api/admin/run-portfolio-rankings endpoint -- same pattern as
    Generate Report / Run Backtest: proper Bearer auth header via a
    normal callback-driven request, generous timeout since this scores
    the full active-campaign set, not a single symbol.
    """
    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/admin/run-portfolio-rankings",
            headers=_auth_headers(session),
            timeout=180,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        result = payload.get("result", {})
        return f"Complete: {result}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("campaign-outcome-result", "children"),
              Input("campaign-outcome-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_campaign_outcome(n_clicks, session):
    """
    Admin-only 'Run Campaign Outcome Engine' button, calling the real
    POST /api/admin/run-campaign-outcome endpoint -- same pattern as
    the other admin action buttons.
    """
    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/admin/run-campaign-outcome",
            headers=_auth_headers(session),
            timeout=180,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        result = payload.get("result", {})
        return f"Complete: {result}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("state-transition-result", "children"),
              Input("state-transition-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_state_transition(n_clicks, session):
    """
    Admin-only 'Run State Transition Engine' button, calling the real
    POST /api/admin/run-state-transition endpoint -- same pattern as
    the other admin action buttons.
    """
    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/admin/run-state-transition",
            headers=_auth_headers(session),
            timeout=180,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        result = payload.get("result", {})
        return f"Complete: {result}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("closure-engine-result", "children"),
              Input("closure-engine-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_closure_engine(n_clicks, session):
    """
    Admin-only 'Run Closure Engine' button, calling the real
    POST /api/admin/run-closure-engine endpoint -- this backend
    endpoint was already correctly wired; this adds the missing
    frontend trigger, same pattern as the other admin action buttons.
    """
    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/admin/run-closure-engine",
            headers=_auth_headers(session),
            timeout=180,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        return f"Complete: {payload}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("decay-monitor-result", "children"),
              Input("decay-monitor-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_decay_monitor(n_clicks, session):
    """
    Admin-only 'Run Decay Monitor' button, calling the real
    POST /api/admin/run-decay-monitor endpoint -- same pattern as the
    other admin action buttons.
    """
    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/admin/run-decay-monitor",
            headers=_auth_headers(session),
            timeout=180,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        result = payload.get("result", {})
        return f"Complete: {result}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(Output("subscriber-alerts-result", "children"),
              Input("subscriber-alerts-btn", "n_clicks"),
              State("s-session", "data"),
              prevent_initial_call=True)
def handle_subscriber_alerts(n_clicks, session):
    """
    Admin-only 'Send Subscriber Alerts' button, calling the real
    POST /api/admin/send-subscriber-alerts endpoint -- this genuinely
    sends real emails to real subscribers, unlike the other admin
    action buttons above (all internal-only batch operations).
    """
    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/admin/send-subscriber-alerts",
            headers=_auth_headers(session),
            timeout=60,
        )
        if r.status_code == 401:
            return "Not signed in, or session expired. Please sign in again."
        if r.status_code == 403:
            return "Admin access only."
        if not r.ok:
            return f"Failed (error {r.status_code}): {r.text[:200]}"
        payload = r.json()
        if not payload.get("ok"):
            return f"Failed: {payload.get('error', 'unknown error')}"
        eligible = payload.get("eligible_campaigns", 0)
        result = payload.get("result", {})
        return f"{eligible} eligible campaign(s). Result: {result}"
    except Exception as exc:
        return f"Could not reach the backend: {exc}"

@app.callback(
    Output("heatmap-treemap", "figure"),
    Output("heatmap-selected-tf", "data"),
    Output("heatmap-tf-row", "children"),
    Input("heatmap-tf-hourly", "n_clicks"),
    Input("heatmap-tf-daily", "n_clicks"),
    Input("heatmap-tf-weekly", "n_clicks"),
    Input("heatmap-tf-monthly", "n_clicks"),
    prevent_initial_call=True,
)
def update_heatmap_timeframe(n_hourly, n_daily, n_weekly, n_monthly):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update
    trigger_id = ctx.triggered[0]["prop_id"].split(".")[0]
    timeframe = trigger_id.replace("heatmap-tf-", "")
    if timeframe not in ("hourly", "daily", "weekly", "monthly"):
        return no_update, no_update, no_update

    timeframes = [("hourly", "Hourly"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")]

    def _tf_button(key, label):
        active = key == timeframe
        return html.Button(
            label,
            id=f"heatmap-tf-{key}",
            n_clicks=0,
            style={
                "background": TEAL_GLOW if active else "transparent",
                "border": f"1px solid {TEAL if active else BORDER}",
                "borderRadius": "10px",
                "color": TEAL_DIM if active else "rgba(255,255,255,.7)",
                "cursor": "pointer",
                "fontSize": "13px",
                "fontWeight": "800",
                "padding": "8px 16px",
                "marginRight": "8px",
            },
        )

    return _build_heatmap_treemap(timeframe), timeframe, [_tf_button(k, l) for k, l in timeframes]



app.index_string = f"""<!DOCTYPE html>
<html><head>{{%metas%}}<title>{{%title%}}</title>{{%favicon%}}{{%css%}}
<link rel="manifest" href="/assets/manifest.json">
<meta name="theme-color" content="#0F766E">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Sigmalytic">
<link rel="apple-touch-icon" href="/assets/icon-192.png">
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
    fireAlert: function(live_data, prev_score, alerts_on) {{
        // FIX (2026-08-04): this used to receive the WHOLE live-data
        // object here (Input("s-live","data") passes the full
        // {{price, decision: {{score, ...}}, ...}} dict, not a plain
        // number), then compared that object directly against numbers
        // like `score >= 80`. In JavaScript that always evaluates to
        // false (an object coerces to NaN), so this alert logic never
        // actually fired correctly despite looking fully built. Now
        // extracts the real numeric score from the object first.
        var score = (live_data && live_data.decision && typeof live_data.decision.score === 'number')
            ? live_data.decision.score : null;
        if (score === null || !alerts_on) {{
            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        }}
        var banner = null;
        if (score >= 80 && prev_score < 80) {{
            sigmaAlert('A');
            banner = {{level: 'A', text: 'Score Tier A — Audio Active', ts: Date.now()}};
        }} else if (score >= 55 && score < 80 && prev_score < 55) {{
            sigmaAlert('B');
            banner = {{level: 'B', text: 'Score Tier B — Audio Active', ts: Date.now()}};
        }} else if (score < 35 && prev_score >= 35) {{
            sigmaAlert('warn');
            banner = {{level: 'warn', text: 'Trap Door', ts: Date.now()}};
        }}
        return [score, banner || window.dash_clientside.no_update];
    }}
}};
if ('serviceWorker' in navigator) {{
    window.addEventListener('load', function() {{
        navigator.serviceWorker.register('/assets/sw.js').catch(function(err) {{
            console.warn('Sigmalytic: service worker registration failed', err);
        }});
    }});
}}
// FIX (2026-08-07): confirmed, precisely-diagnosed root cause of a
// long-standing (predates this entire session, confirmed present as
// early as midnight) "Inputs do not match callback definition" error.
// Traced to Dash's own source (_validate.py's
// validate_and_group_input_args): it raises this exact error whenever
// the number of values a client sends doesn't match what the server's
// callback map currently expects for that callback. Since Dash's
// callback map is fixed once at server startup, any browser tab whose
// page load predates the server's current process (e.g. left open
// across a deploy or a worker restart) can carry a stale, mismatched
// count and will keep failing this exact way on every tick until
// manually refreshed. Rather than leaving affected users stuck
// silently failing, this intercepts fetch() specifically on Dash's
// own callback endpoint, detects this exact failure, and forces a
// clean, automatic reload -- the browser then loads fresh markup
// that genuinely matches the current server, resolving it immediately
// instead of requiring the user to notice and refresh manually.
(function() {{
    var _origFetch = window.fetch;
    var _reloading = false;
    window.fetch = function() {{
        return _origFetch.apply(this, arguments).then(function(response) {{
            if (!_reloading && response && response.status === 500
                && typeof response.url === 'string'
                && response.url.indexOf('_dash-update-component') !== -1) {{
                response.clone().text().then(function(body) {{
                    if (!_reloading && body && body.indexOf('Inputs do not match callback definition') !== -1) {{
                        _reloading = true;
                        console.warn('Sigmalytic: stale session detected (server restarted since this page loaded) -- reloading automatically.');
                        window.location.reload();
                    }}
                }}).catch(function() {{}});
            }}
            return response;
        }});
    }};
}})();
</script>
</body></html>"""

_init_live    = create_live_update("AAPL", 280.15, 750_000, 0).to_dict()
# FIX (2026-08-05): was `fetch_real_candles("AAPL", "5m")` here -- a
# blocking, synchronous HTTP call to the backend made unconditionally
# at MODULE IMPORT TIME, on every single process start. This runs
# before the frontend has even finished loading, with no way to skip
# it if the backend isn't ready yet -- exactly the scenario right
# after a coordinated hard reset/redeploy of both services. The
# existing live-tick callback already fetches and populates real
# candles within seconds of the first page load regardless, so this
# initial value only needs to be a safe, empty placeholder, not a
# real network call that can delay or risk startup.
_init_candles = []

ALL_TABS = [
    ("home",        "Home"),
    ("command",     "Command Center"),
    ("heatmap",     "Heat Map"),
    ("radar",       "Radar Screen"),
    ("divergence",  "Intelligence Change Detector"),
    ("scoreboard",  "Scoreboard"),
    ("campaign",    "Campaign Intelligence"),
    ("behavior",    "Behavioral Intelligence"),
    ("import",      "Import History"),
    ("portfolio",   "Portfolio"),
    ("journal",     "Journal"),
    ("billing",     "Billing"),
    ("preferences", "Preferences"),
    ("status",      "Status"),
    ("reports",     "Reports"),
    ("guide",       "User Guide"),
    ("admin",       "Admin"),
]

app.layout = html.Div([
    dcc.Location(id="url", refresh=True),
    html.Div(id="auth-overlay", children=build_login_page(),
             style={"position":"fixed","top":0,"left":0,"right":0,"bottom":0,
                    "zIndex":9999,"background":"#0a1628","overflowY":"auto"}),
    dcc.Store(id="s-live",      data=_init_live),
    dcc.Store(id="s-session",    data=None, storage_type="session"),
    dcc.Store(id="s-recovery-token", data=None),
    dcc.Store(id="s-page",       data="login"), 
    dcc.Store(id="s-candles",   data=_init_candles),
    dcc.Store(id="s-seq",       data=0),
    dcc.Store(id="s-live-mode", data=True),
    dcc.Store(id="s-symbol",    data="AAPL"),
    dcc.Store(id="s-tf",        data="5m"),
    dcc.Store(id="s-tab",       data="home"),
    dcc.Store(id="s-alert-score",    data=0),
    dcc.Store(id="s-alert-banner",   data=None),
    html.Div(id="alert-banner", style={"display": "none"}),
    dcc.Store(id="s-alerts-on",      data=True),
    dcc.Store(id="s-current-plan-id",data=None),
    dcc.Store(id="s-plan-score",     data=0),
    dcc.Store(id="s-plan-regime",    data="neutral"),
    dcc.Store(id="tp-direction",     data="long"),
    html.Div(id="audio-trigger", style={"display":"none"}),
    # FIX (2026-08-04): shortened aggressively (20s->2s, 30s->2s) per
    # request, given user confirmed they're currently the only
    # subscriber. Each of i-alpaca and i-market-wire makes 2 Alpaca API
    # calls per tick, so at 2s this is ~120 calls/min total from a
    # single browser tab -- comfortable headroom under Alpaca's typical
    # ~200 calls/min limit for one user, but this should be revisited
    # (likely lengthened, or made per-user-aware) once there are
    # multiple concurrent subscribers, since it multiplies linearly
    # with active sessions.
    # URGENT (2026-08-06): reduced from 2000ms back toward a safer
    # interval as an immediate, protective measure given a confirmed,
    # recurring (roughly hourly) production OOM crash on this service.
    # The 2s interval was a 10x increase from the original 20s, with
    # several new backend calls added to every tick since -- a real,
    # plausible driver of accumulating memory pressure over time even
    # without a classic, single-object leak. Root cause not yet fully,
    # definitively confirmed -- this is a direct, conservative lever to
    # reduce load while investigation continues, not a claim that this
    # alone fully explains the crash.
    dcc.Interval(id="i-alpaca", interval=10_000, n_intervals=0),
    dcc.Interval(id="i-clock",  interval=5_000, n_intervals=0),
    dcc.Interval(id="i-market-wire", interval=15_000, n_intervals=0),
    dcc.Store(id="s-market-wire", data=None),

    html.Div([html.Div([
        html.Div(id="market-wire", style={"marginBottom": "10px"}),
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

        # ── Trade plan + Behavioral Analysis — clean 2-column row, exactly
        # matching row4's Time Engine + Visual/Audio Alerts structure above
        # (both flex:1, same alignItems:stretch), per explicit request for
        # matching proportions. Active Trade Panel moved to its own separate
        # row below -- with 3 siblings sharing this row, no combination of
        # flex ratios could give Plan Trade and Behavioral Analysis a true,
        # exact 50/50 split while Active Trade Panel (typically empty) still
        # took up real space; splitting it out entirely is the only way to
        # match row4's proportions precisely rather than approximately.
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
                dcc.Loading(
                    html.Div(id="tp-status", style={"marginTop":"10px","fontSize":"12px","color":TEAL_DIM}),
                    type="dot", color=TEAL,
                ),
            ], style={"flex":"1","minWidth":"0","height":"640px","overflowY":"auto",
                       "background":NAVY_CARD,"border":f"1px solid {BORDER}",
                       "borderRadius":"20px","padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)"}),

            # Behavioral Analysis panel -- updates on the same live-tick
            # cycle as the rest of Command Center, independent of the
            # main tab-switching callback.
            html.Div(id="behavioral-analysis-panel", style={"flex":"1","minWidth":"0","height":"640px"}),
        ], id="trade-panels-row",
           style={"display":"none","gap":"16px","alignItems":"stretch"}),

        # Active trade panel -- separate, full-width row below, only
        # meaningfully visible when there's an actual open trade
        html.Div(id="active-trade-panel", style={"marginTop":"16px"}),

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
    State("s-live","data"), State("s-session","data"), prevent_initial_call=True,
)
def select_tf(_1m,_5m,_15m,_1H,_1D,_1W, live, session):
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
               decision_status=live.get("decision",{}).get("status"), session=session)
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
    State("s-session","data"),
    prevent_initial_call=True,
)
def load_symbol(_, ticker, live, tf, session):
    clean = sanitize_symbol(ticker or "")
    if not clean:
        return no_update, no_update, no_update

    price = live["price"] if live else 0
    _track("symbol_loaded", clean, price=price,
           decision_score=live.get("decision",{}).get("score") if live else None, session=session)

    fresh = fetch_real_candles(clean, tf or "5m")
    return clean, clean, fresh

@app.callback(
    Output("s-tab","data"),
    Input("tab-home","n_clicks"),         Input("tab-command","n_clicks"),      Input("tab-heatmap","n_clicks"),      Input("tab-campaign","n_clicks"),
    Input("tab-behavior","n_clicks"),
    Input("tab-import","n_clicks"),       Input("tab-radar","n_clicks"),
    Input("tab-scoreboard","n_clicks"),   Input("tab-divergence","n_clicks"),
    Input("tab-portfolio","n_clicks"),    Input("tab-journal","n_clicks"),
    Input("tab-billing","n_clicks"),      Input("tab-preferences","n_clicks"),
    Input("tab-admin","n_clicks"),
    Input("tab-status","n_clicks"),
    Input("tab-reports","n_clicks"),
    Input("tab-guide","n_clicks"),
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
    # DIAGNOSTIC (2026-08-06): confirmed real, recurring (~hourly) OOM
    # crashes on this service; root cause not yet definitively proven
    # from static code reading alone. Logs actual process RSS so the
    # next crash's logs show the real memory trajectory over time --
    # the same approach that directly revealed the actual backend OOM
    # cause earlier tonight, rather than continuing to infer from code
    # alone.
    # FIX: lowered from every 30 ticks (~5 min) to every 5 ticks
    # (~50s) -- confirmed the worker now recycles roughly every 20
    # requests (~3.3 min) given the aggressive max-requests=20
    # stopgap, meaning the original 30-tick interval could rarely or
    # never fire within a single worker's actual lifespan. This gives
    # several real readings across a worker's life instead of
    # possibly none.
    try:
        if (seq or 0) % 5 == 0:
            import psutil as _psutil, os as _os_mem
            rss_mb = _psutil.Process(_os_mem.getpid()).memory_info().rss / (1024 * 1024)
            print(f"[MEM] on_tick seq={seq}: {rss_mb:.1f} MB RSS", flush=True)
    except Exception as _mem_exc:
        print(f"[MEM] on_tick: failed to read memory ({_mem_exc})", flush=True)

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

    # Real, live relative-volume check -- powers the "A-grade requires
    # live-volume expansion" indicator on Command Center with actual
    # data instead of a static, always-the-same disclaimer. Best-effort:
    # if this fails or the symbol isn't in the radar universe, the
    # indicator falls back to an honest "data unavailable" state rather
    # than blocking the whole live-tick update over optional data.
    rel_volume = None
    try:
        rv_r = req.get(f"{BACKEND_HTTP}/api/radar/symbol/{clean}", timeout=4)
        if rv_r.ok:
            rv_payload = rv_r.json()
            if rv_payload.get("ok"):
                rel_volume = rv_payload.get("data", {}).get("rel_volume")
    except Exception:
        pass

    # Real, validated Phase 10 position sizing -- powers Behavioral
    # Analysis's sizing guidance with actual research output instead of
    # nothing at all. Same best-effort pattern as rel_volume above.
    sizing_data = None
    try:
        sz_r = req.get(f"{BACKEND_HTTP}/api/radar/symbol/{clean}/sizing", timeout=4)
        if sz_r.ok:
            sz_payload = sz_r.json()
            if sz_payload.get("ok"):
                sizing_data = sz_payload
    except Exception:
        pass

    # Real Livermore/ODS-style operator control score -- only present
    # once an active campaign record exists for this symbol (Layer 5).
    dominance_data = None
    try:
        dom_r = req.get(f"{BACKEND_HTTP}/api/campaigns/{clean}/dominance", timeout=4)
        if dom_r.ok:
            dom_payload = dom_r.json()
            if dom_payload.get("ok") and dom_payload.get("has_active_campaign"):
                dominance_data = dom_payload
    except Exception:
        pass

    # Real, read-only transition preview -- lightweight (computation
    # only on already-fetched campaign data, no external API calls),
    # so kept in the fast tier rather than throttled.
    transition_preview_data = None
    try:
        tp_r = req.get(f"{BACKEND_HTTP}/api/campaigns/transition-preview",
                        params={"symbol": clean, "limit": 50}, timeout=6)
        if tp_r.ok:
            tp_payload = tp_r.json()
            if tp_payload.get("ok") and tp_payload.get("transitions"):
                transition_preview_data = tp_payload["transitions"][0]
    except Exception:
        pass

    # Real, per-symbol evidence diagnostics -- confirmed database-only
    # (no live Alpaca calls anywhere in this chain), so kept in the
    # fast tier too.
    evidence_diagnostics_data = None
    try:
        ed_r = req.get(f"{BACKEND_HTTP}/api/campaign/evidence-diagnostics/{clean}", timeout=6)
        if ed_r.ok:
            ed_payload = ed_r.json()
            if ed_payload.get("found"):
                evidence_diagnostics_data = ed_payload
    except Exception:
        pass

    # Real, validated obstacle score / SPD-DEI behavioral state (Layer
    # 1/2) -- meaningfully heavier than the other live-tick fetches
    # above (fetches 500+ daily bars, runs real wave-variable
    # computation), so throttled to roughly once every 5 minutes
    # (30 ticks at the current 10s interval) rather than every tick.
    # Carries forward the previous value from `current` between
    # refreshes so it doesn't flicker to empty.
    validated_classification = (current or {}).get("validated_classification")
    if (seq or 0) % 30 == 0:
        try:
            vc_r = req.get(f"{BACKEND_HTTP}/api/radar/symbol/{clean}/validated-classification", timeout=8)
            if vc_r.ok:
                vc_payload = vc_r.json()
                if vc_payload.get("ok"):
                    validated_classification = vc_payload
        except Exception:
            pass

    # Real Wyckoff Verdict Engine -- also fetches bar data, same
    # throttle as validated_classification above.
    wyckoff_verdict = (current or {}).get("wyckoff_verdict")
    if (seq or 0) % 30 == 0:
        try:
            wv_r = req.get(f"{BACKEND_HTTP}/api/radar/symbol/{clean}/wyckoff-verdict", timeout=8)
            if wv_r.ok:
                wv_payload = wv_r.json()
                if wv_payload.get("ok"):
                    wyckoff_verdict = wv_payload
        except Exception:
            pass

    # Real Historical Analog Engine -- lighter than the two above (no
    # bar fetching, just a database query), but still throttled for
    # consistency and to avoid an unnecessary query on every tick.
    campaign_analogs_data = (current or {}).get("campaign_analogs")
    if (seq or 0) % 30 == 0:
        try:
            an_r = req.get(f"{BACKEND_HTTP}/api/campaigns/{clean}/analogs", timeout=8)
            if an_r.ok:
                an_payload = an_r.json()
                if an_payload.get("ok") and an_payload.get("has_active_campaign"):
                    campaign_analogs_data = an_payload
        except Exception:
            pass

    new_seq = (seq or 0) + 1

    # Preserve backend decision/confluence if present. Fall back to local engine output.
    fallback_live = create_live_update(clean, price, volume, new_seq).to_dict()
    new_live = {
        **fallback_live,
        "symbol": clean,
        "price": price,
        "volume": volume,
        "rel_volume": rel_volume,
        "sizing_data": sizing_data,
        "dominance_data": dominance_data,
        "transition_preview_data": transition_preview_data,
        "evidence_diagnostics_data": evidence_diagnostics_data,
        "validated_classification": validated_classification,
        "wyckoff_verdict": wyckoff_verdict,
        "campaign_analogs": campaign_analogs_data,
        "timestamp": tick_time,
        "sequence": new_seq,
        "source": d.get("source", "alpaca"),
    }
    if d.get("decision"):
        new_live["decision"] = d.get("decision")
    if d.get("confluence"):
        new_live["confluence"] = d.get("confluence")

    # FIX (2026-07-30): user-reported the chart's candlesticks didn't
    # match the live price, by a large and persistent margin that a hard
    # browser refresh never fixed. Root cause: the module-level
    # _init_candles = fetch_real_candles("AAPL", "5m") at the bottom of
    # this file runs exactly once, at Python process boot -- not per
    # session, not per page load. Every user's chart started from that
    # one frozen snapshot (whatever AAPL's price was whenever this
    # server process last restarted, possibly hours or days ago), and
    # this "if not candles" check only ever re-fetched full history if
    # the store was completely empty -- which it never was after that
    # one boot-time fetch. From then on, only the single most recent
    # candle's high/low/close ever got nudged (below); the rest of the
    # historical series stayed frozen indefinitely, which is also why a
    # hard refresh never helped -- this was a server-side Python
    # variable, not anything cached in the browser.
    #
    # FIX (2026-07-30, follow-up): confirmed the ~5-minute version of
    # this self-heal window still wasn't tight enough -- it's keyed to
    # server uptime (every 15th tick since this process booted), not to
    # when an individual user loads the page. Given this backend
    # restarted many times tonight, a freshly-opened page can easily
    # land within that first ~5-minute window and still see a stale
    # snapshot, confirmed directly: user reported a mismatch on a page
    # they'd "just opened fresh." Tightened to every 3 ticks (~1 minute)
    # to substantially shrink the worst-case staleness window, while
    # still not re-fetching full history on every single 20-second tick.
    if not candles or (new_seq % 3 == 0):
        fresh_history = fetch_real_candles(clean, tf or "5m")
        if fresh_history:
            candles = fresh_history

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
    Output("behavioral-analysis-panel", "children"),
    Input("s-live", "data"),
)
def update_behavioral_analysis(live):
    return _render_behavioral_analysis_panel(live)

@app.callback(
    Output("s-market-wire", "data"),
    Input("i-market-wire", "n_intervals"),
    prevent_initial_call=False,
)
def fetch_market_wire(_):
    try:
        r = req.get(f"{BACKEND_HTTP}/api/market-wire", timeout=15)
        if r.ok:
            payload = r.json()
            if payload.get("ok"):
                return payload.get("items", [])
    except Exception:
        pass
    return no_update

@app.callback(
    Output("market-wire", "children"),
    Input("s-market-wire", "data"),
)
def render_market_wire(items):
    return _render_market_wire(items)

@app.callback(
    Output("main-content",       "children"),
    Output("trade-panels-row",   "style"),
    Output("trade-plan-panel",   "children"),
    Output("active-trade-panel", "children"),
    Input("s-tab","data"),
    # FIX (2026-07-29): these were States, not Inputs -- meaning this entire
    # main content area (chart, Trade Card, Price Ladder, decision panel,
    # Options Matrix) only ever re-rendered when the user switched tabs.
    # New live price ticks (i-alpaca fires every 20s) updated s-live in the
    # background, but nothing told this callback to react to it, so the
    # whole dashboard sat frozen on stale/placeholder data (visibly the
    # startup default, $280.15) while only the small top badge -- which
    # correctly already used Input("s-live","data") -- updated live.
    Input("s-live","data"),
    Input("s-candles","data"),
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
        ])
        return main, HIDDEN, no_update, no_update

    if tab == "command":
        open_trade  = _get(f"/api/behavior/open-trade/{_current_user_id(session)}", headers=_auth_headers(session))
        trade_plan  = _build_trade_plan_contents(live)
        active_pane = build_active_trade_panel(open_trade, live["price"]) if open_trade else html.Div()
        return (html.Div([
                    build_weis_gamma_status_center_panel(),
                    build_command_tab(live, candles or _init_candles, symbol, tf),
                ], style={"display":"flex","flexDirection":"column","gap":"16px"}),
                SHOWN, trade_plan, active_pane)

    if tab == "heatmap":
        # FIX (2026-08-03): same bug class already fixed for the Reports
        # tab -- this callback rebuilds every tab from scratch on every
        # ~20s live-price tick (needed for the Command Center), and
        # build_heatmap_tab() always defaults back to "daily" on every
        # rebuild, with no memory of what the user had selected. Only
        # rebuild on a genuine tab switch (s-tab), so a live-tick while
        # already on this tab doesn't reset the user's timeframe choice.
        _trigger = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if _trigger.startswith("s-tab"):
            main = build_heatmap_tab()
        else:
            return no_update, no_update, no_update, no_update
    elif tab=="campaign":
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
    elif tab=="behavior":    main = build_behavior_tab(session=session)
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
        # FIX (2026-08-06): same bug class already fixed for Heatmap,
        # Reports, and Admin tonight -- this callback rebuilds every tab
        # from scratch on every ~2s live-price tick, and
        # build_trade_journal_tab() has real trade-entry form fields
        # (symbol, entry date/price, shares, notes) with no memory of
        # what the user had typed. A user actively logging a new trade
        # could have their input wiped mid-keystroke. Only rebuild on a
        # genuine tab switch.
        _trigger = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if not _trigger.startswith("s-tab"):
            return no_update, no_update, no_update, no_update
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
        # FIX (2026-08-06): same bug class already fixed for Heatmap,
        # Reports, Admin, and Journal tonight -- build_preferences_tab()
        # has a real watchlist symbol input field (prefs-sym-input) with
        # no guard against this callback's every-~2s live-tick rebuild.
        # Only rebuild on a genuine tab switch.
        _trigger = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if not _trigger.startswith("s-tab"):
            return no_update, no_update, no_update, no_update
        try:
            main = build_preferences_tab(user_id="", session=None)
        except Exception as e:
            main = card([
                html.H2("️ Preferences", style={"color":WHITE,"fontSize":"18px","fontWeight":"900","marginBottom":"12px"}),
                note_box("Preferences loading. Please refresh in a moment.", "blue"),
            ])
    elif tab=="admin":
        # FIX (2026-08-04): same bug class already fixed for Heatmap and
        # Reports -- this callback rebuilds every tab from scratch on every
        # live-price tick (now 2s, shortened earlier tonight, making this
        # especially aggressive), and a fresh rebuild recreates the Symbol
        # Backtest input with no value, wiping out whatever the user just
        # typed almost as fast as they can type it. Only rebuild on a
        # genuine tab switch (s-tab), so a live-tick while already on this
        # tab doesn't reset form inputs.
        _trigger = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if not _trigger.startswith("s-tab"):
            return no_update, no_update, no_update, no_update
        try:
            admin_session = session if isinstance(session, dict) else {}
            main = html.Div([
                # D3F.1B: developer/audit-only safety verification panel.
                # Moved here from a global page-wide mount (was showing on
                # every tab) since this is an internal diagnostic tool, not
                # customer-facing content.
                _build_d3f1b_controlled_persistence_lifecycle_panel(admin_session),
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
    elif tab=="reports":
        # FIX (2026-07-31): user reported the Reports tab kept "switching"
        # back to the latest date while reading an older one. Root cause:
        # this callback rebuilds every tab from scratch on every ~20s
        # live-price tick (needed for the Command Center), and
        # build_reports_tab() always defaulted to the most recent date on
        # every rebuild. First attempted fix (reading the date picker's
        # current value back in via State) broke the callback entirely --
        # confirmed via the actual browser console error -- because that
        # component is created by this same callback's own output, a
        # circular dependency Dash's client-side renderer can't resolve,
        # even with suppress_callback_exceptions=True (which only covers
        # server-side Python validation, not this).
        #
        # Correct fix: don't rebuild this tab's content at all on a
        # live-tick-only trigger -- only rebuild it on a genuine tab
        # switch. That preserves whatever the user has on screen
        # (including their date selection) untouched between real
        # navigation events, without needing to read anything back from
        # a component this same callback creates.
        _trigger = callback_context.triggered[0]["prop_id"] if callback_context.triggered else ""
        if _trigger.startswith("s-tab"):
            main = build_reports_tab(session=session)
        else:
            return no_update, no_update, no_update, no_update
    elif tab=="guide":       main = build_guide_tab()
    else:                    main = html.Div("Unknown tab")

    # Persistent copyright footer -- appears at the bottom of every tab's
    # content, regardless of which tab is active, without needing to
    # modify the large static app.layout structure.
    main = html.Div([
        main,
        html.Div([
            html.Span(f"© {datetime.now().year} Sigmalytic Quant Corporation. All rights reserved.",
                      style={"fontSize":"11px","color":"rgba(255,255,255,.35)"}),
            html.A("Terms of Service", href=f"{BACKEND_HTTP}/terms", target="_blank",
                   style={"fontSize":"11px","color":"rgba(255,255,255,.35)","marginLeft":"16px","textDecoration":"underline"}),
            html.A("Privacy Policy", href=f"{BACKEND_HTTP}/privacy", target="_blank",
                   style={"fontSize":"11px","color":"rgba(255,255,255,.35)","marginLeft":"16px","textDecoration":"underline"}),
        ], style={"textAlign":"center","padding":"24px 0 8px","marginTop":"24px"}),
    ])

    return main, HIDDEN, no_update, no_update

# ── Trade plan / entry / exit callbacks ───────────────────────────────────────

@app.callback(
    Output("tp-status","children"),
    Output("s-current-plan-id","data"),
    Input("btn-save-plan","n_clicks"),
    State("tp-direction","data"), State("tp-entry","value"),
    State("tp-stop","value"), State("tp-target","value"),
    State("tp-size","value"), State("tp-notes","value"),
    State("s-live","data"), State("s-session","data"), prevent_initial_call=True,
)
def save_plan(n,direction,entry,stop,target,size,notes,live,session):
    if not n: return no_update, no_update
    try:
        price  = live["price"] if live else 0
        symbol = live.get("symbol","") if live else ""
        score  = live.get("decision",{}).get("score",0) if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        resp = _post("/api/behavior/trade-plan",{
            "user_id":_current_user_id(session),"symbol":symbol,"direction":direction,
            "planned_entry":float(entry),"planned_stop":float(stop),
            "planned_target":float(target),"planned_size":float(size),
            "setup_reason":notes or "","signal_score_at_plan":score,"regime_at_plan":regime,
        }, headers=_auth_headers(session))
        plan_id = resp.get("plan_id")
        _track("trade_planned",symbol,price=price,regime=regime,decision_score=score,
               metadata={"plan_id":plan_id,"direction":direction}, session=session)
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
    State("s-live","data"), State("s-session","data"), prevent_initial_call=True,
)
def enter_trade(n,direction,entry,stop,target,size,plan_id,live,session):
    if not n: return no_update
    try:
        price  = live["price"] if live else 0
        symbol = live.get("symbol","") if live else ""
        score  = live.get("decision",{}).get("score",0) if live else 0
        regime = _regime_from_live(live) if live else "neutral"
        resp = _post("/api/behavior/trade-entry",{
            "user_id":_current_user_id(session),"symbol":symbol,"direction":direction,
            "entry_price":float(entry),"stop_price":float(stop) if stop else None,
            "target_price":float(target) if target else None,"size":float(size),
            "plan_id":plan_id,"market_regime_entry":regime,"signal_score_entry":score,
        }, headers=_auth_headers(session))
        trade_id = resp.get("trade_id")
        _track("trade_entered",symbol,price=float(entry),regime=regime,decision_score=score,
               metadata={"trade_id":trade_id,"direction":direction}, session=session)
        return f"Trade entered: {trade_id}"
    except Exception as e:
        return f"Error: {e}"

@app.callback(
    Output("exit-status","children"),
    Input("btn-exit-trade","n_clicks"),
    State("s-active-trade-id","data"),
    State("exit-flags","value"),
    State("exit-notes","value"),
    State("s-live","data"), State("s-session","data"), prevent_initial_call=True,
)
def exit_trade(n,trade_id,flags,notes,live,session):
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
        }, headers=_auth_headers(session))
        scores = resp.get("scores",{})
        _track("trade_exited",live.get("symbol",""),price=price,regime=regime,decision_score=score,
               metadata={"trade_id":trade_id,"pnl":resp.get("pnl"),"flag":resp.get("behavior_flag")}, session=session)
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
        # FIX (2026-07-28): this posted to /api/import/upload, which has no
        # matching backend route (confirmed via full route audit) -- every
        # CSV upload was silently 404ing, so nothing was ever actually
        # imported. The real, working endpoint is /api/import/upload-generic
        # in import_history_restore_api.py. Its response also uses different
        # key names than this code was reading (trades_imported, not
        # trades_closed; no broker_name field at all), so those are
        # corrected below too.
        resp = req.post(
            f"{BACKEND_HTTP}/api/import/upload-generic",
            files={"file": (filename, _io.BytesIO(decoded), "text/csv")},
            timeout=30,
        )
        if resp.ok:
            data = resp.json()
            a    = data.get("analysis", {})
            return html.Div([
                html.Span(f"{data.get('trades_imported',0)} trades imported · ",
                          style={"color":TEAL_DIM,"fontWeight":"800"}),
                html.Span(f"Win rate: {a.get('win_rate',0)}% · "
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


# ── Audio + Visual alert clientside callback ─────────────────────────────────
app.clientside_callback(
    """
    function(score, prev_score, alerts_on) {
        if (window.dash_clientside && window.dash_clientside.sigmalytic) {
            return window.dash_clientside.sigmalytic.fireAlert(score, prev_score, alerts_on);
        }
        return [score, window.dash_clientside.no_update];
    }
    """,
    Output("s-alert-score", "data"),
    Output("s-alert-banner", "data"),
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


@app.callback(Output("alert-banner", "children"),
              Output("alert-banner", "style"),
              Input("s-alert-banner", "data"),
              prevent_initial_call=True)
def show_alert_banner(banner):
    """
    Renders the visual half of "Visual + Audio Alerts" -- this panel's
    name implied both existed, but only the audio side (sigmaAlert in
    index_string) was ever built. A brief, auto-fading toast banner
    now shows the same score-tier labels alongside the sound:
      - Below 35: "Trap Door" (warning-style zone)
      - 55-79: "Score Tier B — Audio Active"
      - 80+: "Score Tier A — Audio Active"
    """
    if not banner:
        return no_update, {"display": "none"}

    level = banner.get("level")
    text = banner.get("text", "")
    ts = banner.get("ts", 0)

    if level == "A":
        color, glow = TEAL_DIM, "rgba(45,143,111,.9)"
    elif level == "B":
        color, glow = BLUE_DIM, "rgba(59,130,246,.9)"
    else:  # "warn" / Trap Door
        color, glow = RED_DIM, "rgba(239,68,68,.9)"

    outer_style = {"position": "fixed", "top": "18px", "left": "0", "width": "100%",
                   "textAlign": "center", "zIndex": 99999, "pointerEvents": "none"}
    inner_style = {
        "display": "inline-block",
        "background": NAVY_CARD, "border": f"2px solid {color}",
        "borderRadius": "14px", "padding": "14px 28px", "color": color,
        "fontSize": "15px", "fontWeight": "900", "letterSpacing": ".04em",
        "boxShadow": f"0 8px 32px {glow}",
        "animation": "sigmaAlertToast 4s ease-in-out forwards",
    }
    # key forces React to genuinely unmount and remount this specific
    # inner element on every new alert (even repeats of the same
    # level within the same window), so the CSS animation applied to
    # it reliably restarts each time rather than silently no-op'ing
    # on an element React decides to reuse.
    return html.Div(text, key=str(ts), style=inner_style), outer_style


@app.callback(Output("auth-overlay","style"),
              Input("s-session","data"))
def route_page(session):
    overlay_base = {"position":"fixed","top":0,"left":0,"right":0,"bottom":0,
                    "zIndex":9999,"background":NAVY,"overflowY":"auto"}
    hidden = {"display":"none"}
    if session and session.get("user_id"):
        return hidden
    return overlay_base

@app.callback(Output("login-section","style"), Output("signup-section","style"), Output("forgot-section","style"),
              Input("goto-signup-btn","n_clicks"), Input("goto-login-btn","n_clicks"),
              Input("goto-forgot-btn","n_clicks"), Input("goto-login-from-forgot-btn","n_clicks"),
              prevent_initial_call=True)
def toggle_auth_section(to_signup, to_login, to_forgot, to_login2):
    ctx = callback_context
    if not ctx.triggered: return no_update, no_update, no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger == "goto-signup-btn":
        return {"display":"none"}, {"display":"block"}, {"display":"none"}
    if trigger == "goto-forgot-btn":
        return {"display":"none"}, {"display":"none"}, {"display":"block"}
    # goto-login-btn or goto-login-from-forgot-btn -- both go back to Sign In
    return {"display":"block"}, {"display":"none"}, {"display":"none"}


@app.callback(Output("forgot-message","children"),
              Input("forgot-submit-btn","n_clicks"),
              State("forgot-email","value"),
              prevent_initial_call=True)
def handle_forgot_password(n_clicks, email):
    if not email:
        return "Please enter your email address."

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return "Password reset is not configured on this server. Contact support."

    import requests as _req
    try:
        r = _req.post(
            f"{SUPABASE_URL}/auth/v1/recover",
            headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
            json={"email": email, "options": {"redirect_to": FRONTEND_URL}},
            timeout=10,
        )
        # Supabase returns 200 regardless of whether the email exists, by
        # design (prevents leaking which emails are registered) -- so a
        # generic success message here is correct, not a bug.
        if r.ok:
            return f"If an account exists for {email}, a reset link has been sent. Check your inbox."
        return f"Could not send reset email (error {r.status_code}). Please try again."
    except Exception as exc:
        return f"Could not reach the reset service: {exc}"


@app.callback(Output("login-section","style", allow_duplicate=True),
              Output("signup-section","style", allow_duplicate=True),
              Output("forgot-section","style", allow_duplicate=True),
              Output("set-password-section","style"),
              Input("s-recovery-token","data"),
              prevent_initial_call=True)
def show_set_password_section(recovery_token):
    if not recovery_token:
        return no_update, no_update, no_update, no_update
    # A recovery token was found in the URL -- hide every other auth
    # section and show only the set-new-password form.
    return {"display":"none"}, {"display":"none"}, {"display":"none"}, {"display":"block"}


@app.callback(Output("set-password-message","children"),
              Output("s-session","data", allow_duplicate=True),
              Output("s-page","data", allow_duplicate=True),
              Input("set-password-btn","n_clicks"),
              State("set-password-new","value"),
              State("s-recovery-token","data"),
              prevent_initial_call=True)
def handle_set_new_password(n_clicks, new_password, recovery_token):
    if not new_password or len(new_password) < 6:
        return "Password must be at least 6 characters.", no_update, no_update

    if not recovery_token:
        return "Recovery link has expired or is invalid. Please request a new one.", no_update, no_update

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        return "Password reset is not configured on this server. Contact support.", no_update, no_update

    import requests as _req
    auth_headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {recovery_token}",
        "Content-Type": "application/json",
    }
    try:
        r = _req.put(
            f"{SUPABASE_URL}/auth/v1/user",
            headers=auth_headers,
            json={"password": new_password},
            timeout=10,
        )
        if not r.ok:
            return f"Could not set new password (error {r.status_code}). The link may have expired -- request a new one.", no_update, no_update

        # Password updated -- the recovery token is itself a valid access
        # token, so log the user straight into the app rather than making
        # them re-enter the password they just set.
        user = r.json() or {}
        return ("", {
            "user_id": user.get("id", ""),
            "email": user.get("email", ""),
            "access_token": recovery_token,
            "is_demo": False,
        }, "app")

    except Exception as exc:
        return f"Could not reach the reset service: {exc}", no_update, no_update

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



@app.callback(
    Output("jrn-submit-result", "children"),
    Input("jrn-submit", "n_clicks"),
    State("jrn-symbol", "value"),
    State("jrn-entry-date", "value"),
    State("jrn-entry-price", "value"),
    State("jrn-shares", "value"),
    State("jrn-direction", "value"),
    State("jrn-tier", "value"),
    State("jrn-notes", "value"),
    State("jrn-portfolio-value", "value"),
    State("s-session", "data"),
    prevent_initial_call=True,
)
def handle_journal_submit(
    n_clicks,
    symbol,
    entry_date,
    entry_price,
    shares,
    direction,
    tier,
    notes,
    portfolio_value,
    session,
):
    if not n_clicks:
        return no_update

    symbol = (symbol or "").strip().upper()
    direction = (direction or "LONG").strip().upper()
    tier = tier or "MANUAL"
    notes = (notes or "").strip()

    if not symbol:
        return note_box("Journal entry blocked: symbol is required.", "yellow")

    if direction not in {"LONG", "SHORT"}:
        return note_box("Journal entry blocked: direction must be LONG or SHORT.", "yellow")

    if not entry_date:
        return note_box("Journal entry blocked: entry date is required.", "yellow")

    try:
        entry_price = float(entry_price)
        shares = float(shares)
        portfolio_value = float(portfolio_value or 0)
    except Exception:
        return note_box("Journal entry blocked: entry price, shares, and portfolio value must be numeric.", "yellow")

    if entry_price <= 0:
        return note_box("Journal entry blocked: entry price must be greater than zero.", "yellow")

    if shares <= 0:
        return note_box("Journal entry blocked: shares must be greater than zero.", "yellow")

    payload = {
        "symbol": symbol,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "shares": shares,
        "direction": direction,
        "signal_id": None,
        "campaign_id": "manual_journal_entry",
        "tier": tier,
        "notes": notes,
        "portfolio_value": portfolio_value,
    }

    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/journal/entry",
            json=payload,
            headers=_auth_headers(session),
            timeout=20,
        )
        try:
            resp = r.json()
        except Exception:
            resp = {"raw": r.text}
    except Exception as exc:
        return note_box(
            f"Journal entry failed: request exception: {type(exc).__name__}: {exc}",
            "yellow",
        )

    if r.status_code >= 200 and r.status_code < 300 and isinstance(resp, dict) and resp.get("ok"):
        journal_id = resp.get("journal_id", "")
        return html.Div([
            note_box(f"Journal entry saved for {symbol}. Journal ID: {journal_id}. Auto-refreshing journal table.", "green"),
            dcc.Interval(id="jrn-entry-auto-refresh", interval=1500, n_intervals=0, max_intervals=1),
        ])

    detail = resp.get("detail") if isinstance(resp, dict) else None
    error = resp.get("error") if isinstance(resp, dict) else None
    raw = resp.get("raw") if isinstance(resp, dict) else None
    return note_box(f"Journal entry failed: HTTP {r.status_code}: " + str(detail or error or raw or resp), "yellow")


@app.callback(
    Output("jrn-exit-result", "children"),
    Input("jrn-exit-submit", "n_clicks"),
    State("jrn-exit-id", "value"),
    State("jrn-exit-date", "value"),
    State("jrn-exit-price", "value"),
    State("jrn-exit-reason", "value"),
    State("jrn-exit-notes", "value"),
    State("s-session", "data"),
    prevent_initial_call=True,
)
def handle_journal_exit(
    n_clicks,
    journal_id,
    exit_date,
    exit_price,
    exit_reason,
    notes,
    session,
):
    if not n_clicks:
        return no_update

    journal_id = (journal_id or "").strip()
    exit_reason = (exit_reason or "MANUAL").strip().upper()
    notes = (notes or "").strip()

    if not journal_id:
        return note_box("Journal exit blocked: select an open journal trade.", "yellow")

    if not exit_date:
        return note_box("Journal exit blocked: exit date is required.", "yellow")

    try:
        exit_price = float(exit_price)
    except Exception:
        return note_box("Journal exit blocked: exit price must be numeric.", "yellow")

    if exit_price <= 0:
        return note_box("Journal exit blocked: exit price must be greater than zero.", "yellow")

    payload = {
        "exit_date": exit_date,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "notes": notes,
    }

    try:
        r = req.post(
            f"{BACKEND_HTTP}/api/journal/exit/{journal_id}",
            json=payload,
            headers=_auth_headers(session),
            timeout=20,
        )
        try:
            resp = r.json()
        except Exception:
            resp = {"raw": r.text}
    except Exception as exc:
        return note_box(
            f"Journal exit failed: request exception: {type(exc).__name__}: {exc}",
            "yellow",
        )

    if r.status_code >= 200 and r.status_code < 300 and isinstance(resp, dict) and resp.get("ok"):
        return html.Div([
            note_box(f"Journal exit saved for {journal_id}. Auto-refreshing journal table.", "green"),
            dcc.Interval(id="jrn-exit-auto-refresh", interval=1500, n_intervals=0, max_intervals=1),
        ])

    detail = resp.get("detail") if isinstance(resp, dict) else None
    error = resp.get("error") if isinstance(resp, dict) else None
    raw = resp.get("raw") if isinstance(resp, dict) else None
    return note_box(f"Journal exit failed: HTTP {r.status_code}: " + str(detail or error or raw or resp), "yellow")


# JOURNAL_AUTO_REFRESH_CLIENTSIDE_CALLBACK
app.clientside_callback(
    """
    function(entry_ticks, exit_ticks) {
        const entry = entry_ticks || 0;
        const exit = exit_ticks || 0;
        if (entry > 0 || exit > 0) {
            window.location.reload();
        }
        return "";
    }
    """,
    Output("jrn-auto-refresh-dummy", "children"),
    Input("jrn-entry-auto-refresh", "n_intervals"),
    Input("jrn-exit-auto-refresh", "n_intervals"),
    prevent_initial_call=True,
)

if __name__ == "__main__":
    # URGENT REVERT (2026-08-06): threaded=True was added earlier
    # tonight as a "standard, low-risk fix" for the frontend being
    # single-threaded by default. A real OOM crash was then reported
    # on this exact service, timed directly after that change went
    # live. Reverting immediately -- same lesson as the backend's
    # earlier OOM crash tonight: stop a confirmed, active production
    # risk first, investigate the actual root cause properly second,
    # rather than assume a change was safe just because it's a
    # commonly-recommended pattern in general. The real, underlying
    # "one request blocks everyone" problem this was meant to fix is
    # real and still unsolved -- but a crashing service is strictly
    # worse than a slow one. See the follow-up investigation for
    # whether this was the genuine cause or a coincidence, before
    # re-attempting any concurrency fix here.
    try:
        import psutil as _psutil_startup, os as _os_startup
        _startup_rss_mb = _psutil_startup.Process(_os_startup.getpid()).memory_info().rss / (1024 * 1024)
        print(f"[MEM] STARTUP baseline: {_startup_rss_mb:.1f} MB RSS", flush=True)
    except Exception as _startup_mem_exc:
        print(f"[MEM] STARTUP: failed to read memory ({_startup_mem_exc})", flush=True)
    app.run(debug=False, host="0.0.0.0", port=8050)

# SIGMALYTIC_HIGH_CONTRAST_TEXT_PATCH
# Note: Opportunity Dashboard inline styles already force descriptive text to WHITE.
