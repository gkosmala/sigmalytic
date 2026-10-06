# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/imbalance_tab.py
-------------------------
Imbalance Alerts tab. While the feature is in testing it is shown to
administrators only: the recent alert log and the track record (how often
alerts were right at 1, 3, 5 and 10 trading days). Everyone else sees a short
"coming soon" note.

Plugs into app.py:
  1. from imbalance_tab import build_imbalance_tab
  2. ALL_TABS: ("imbalance", "Imbalance Alerts")
  3. render_main: elif tab == "imbalance": main = build_imbalance_tab(session, admin)
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests as _rq
from dash import html

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

NAVY_CARD = "#111f35"
TEAL_DIM = "#34d399"
RED_DIM = "#f87171"
YELLOW_DIM = "#fde68a"
WHITE = "#f1f5f9"
MUTED = "#94a3b8"
BORDER = "rgba(255,255,255,.08)"

PILLAR_LABELS = {"options_flow": "Options flow", "price_structure": "Price structure", "volume_flow": "Volume flow"}
HORIZONS = ("1", "3", "5", "10")


def _headers(session: Optional[dict]) -> Dict[str, str]:
    token = ""
    if isinstance(session, dict):
        token = session.get("access_token") or session.get("supabase_access_token") or session.get("token") or ""
    return {"Authorization": f"Bearer {token}"} if token else {"Authorization": "Bearer demo"}


def _get(path: str, session: Optional[dict]) -> Any:
    r = _rq.get(f"{BACKEND_HTTP}{path}", headers=_headers(session), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"{path} returned {r.status_code}")
    return r.json()


def _card(children, sx=None):
    base = {"background": NAVY_CARD, "border": f"1px solid {BORDER}", "borderRadius": "16px",
            "padding": "20px", "marginBottom": "16px"}
    if sx:
        base.update(sx)
    return html.Div(children, style=base)


def _section(text):
    return html.Div(text, style={"fontSize": "10px", "fontWeight": "700", "color": WHITE,
                                 "textTransform": "uppercase", "letterSpacing": ".1em", "marginBottom": "10px"})


def _note(text: str, color: str = YELLOW_DIM) -> html.Div:
    return html.Div(text, style={"fontSize": "12px", "color": color, "padding": "10px 12px",
                                 "border": f"1px solid {color}55", "borderRadius": "10px",
                                 "background": f"{color}10", "marginBottom": "10px"})


def _title():
    return html.H2("Imbalance Alerts", style={"color": WHITE, "fontSize": "18px", "fontWeight": "900",
                                              "marginBottom": "6px"})


def _pct(v: Any) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "pending"
    return f"{x:+.2f}%"


def _pct_color(v: Any) -> str:
    try:
        return TEAL_DIM if float(v) > 0 else RED_DIM if float(v) < 0 else WHITE
    except (TypeError, ValueError):
        return MUTED


def _cell(content, color=WHITE, mono=False, bold=False):
    style = {"padding": "8px 10px", "fontSize": "12px", "color": color, "borderBottom": f"1px solid {BORDER}",
             "whiteSpace": "nowrap"}
    if mono:
        style["fontFamily"] = "DM Mono, monospace"
    if bold:
        style["fontWeight"] = "800"
    return html.Td(content, style=style)


def _head(text):
    return html.Th(text, style={"padding": "8px 10px", "fontSize": "10px", "color": MUTED, "textAlign": "left",
                                "textTransform": "uppercase", "letterSpacing": ".08em",
                                "borderBottom": f"1px solid {BORDER}"})


def render_status(universe: Dict[str, Any]) -> html.Div:
    if universe.get("live"):
        mode, color = "LIVE: alerts are emailed to subscribers", TEAL_DIM
    elif universe.get("scan_enabled") and universe.get("admin_preview"):
        mode, color = "TESTING: alerts are logged and emailed to administrators only", YELLOW_DIM
    elif universe.get("scan_enabled"):
        mode, color = "TESTING: alerts are logged only, nobody is emailed", YELLOW_DIM
    else:
        mode, color = "OFF: the scan is not running", RED_DIM
    return _card([_section("Status"), _note(mode, color),
                  html.Div("Scanning: " + ", ".join(universe.get("symbols") or []),
                           style={"fontSize": "12px", "color": MUTED})])


def render_track_record(tr: Dict[str, Any]) -> html.Div:
    by = tr.get("by_horizon") or {}
    if not by:
        body: Any = _note("No results yet. Outcomes appear 1, 3, 5 and 10 trading days after each alert.")
    else:
        rows = []
        for h in HORIZONS:
            if h not in by:
                continue
            d = by[h]
            rows.append(html.Tr([_cell(f"{h} day{'s' if h != '1' else ''}"),
                                 _cell(str(d["n"]), mono=True),
                                 _cell(f"{float(d['hit_rate']) * 100:.0f}%", mono=True, bold=True),
                                 _cell(_pct(d["avg_move_pct"]), _pct_color(d["avg_move_pct"]), mono=True)]))
        body = html.Table([html.Thead(html.Tr([_head("After"), _head("Alerts scored"), _head("Right direction"),
                                               _head("Average move")])), html.Tbody(rows)],
                          style={"width": "100%", "borderCollapse": "collapse"})
    return _card([_section(f"Track record ({tr.get('alerts', 0)} alerts logged)"), body,
                  html.Div("Right direction means price moved the way the alert said. Moves are close to close "
                           "from the alert price. A high-probability label should wait for a meaningful sample.",
                           style={"fontSize": "11px", "color": MUTED, "marginTop": "10px"})])


def _alert_row(r: Dict[str, Any]) -> html.Tr:
    outcomes = r.get("outcomes") or {}
    detail = r.get("detail") or {}
    agreeing = [PILLAR_LABELS.get(k, k) for k in (detail.get("agreeing") or [])]
    dcolor = TEAL_DIM if r.get("direction") == "LONG" else RED_DIM
    cells = [
        _cell(str(r.get("fired_at", ""))[:16].replace("T", " ")),
        _cell(r.get("symbol", ""), bold=True),
        _cell(r.get("direction", ""), dcolor, bold=True),
        _cell(f"{r.get('tier', '')} ({r.get('pillars_agreeing', '')} of 3)"),
        _cell(", ".join(agreeing)),
        _cell(f"${float(r.get('entry_price') or 0):,.2f}", mono=True),
    ]
    for h in HORIZONS:
        v = outcomes.get(h)
        cells.append(_cell(_pct(v), _pct_color(v), mono=True))
    cells.append(_cell("Yes" if r.get("emailed") else "No", MUTED))
    return html.Tr(cells)


def render_log(rows: List[Dict[str, Any]]) -> html.Div:
    if not rows:
        return _card([_section("Recent alerts"),
                      _note("No alerts yet. Alerts appear here when at least two of the three pillars agree.")])
    head = html.Thead(html.Tr([_head(x) for x in
                               ("Time (UTC)", "Symbol", "Direction", "Tier", "Pillars", "Price",
                                "+1d", "+3d", "+5d", "+10d", "Emailed")]))
    return _card([_section("Recent alerts"),
                  html.Div(html.Table([head, html.Tbody([_alert_row(r) for r in rows])],
                                      style={"width": "100%", "borderCollapse": "collapse"}),
                           style={"overflowX": "auto"})])


def build_imbalance_tab(session: Optional[dict] = None, admin: bool = False) -> html.Div:
    intro = html.Div(
        "Raised when options flow, price structure and volume flow line up on the same side. "
        "At least two of the three must agree and none may disagree; all three is marked STRONG.",
        style={"fontSize": "12px", "color": MUTED, "marginBottom": "16px", "maxWidth": "760px"})
    if not admin:
        return html.Div([_title(), intro,
                         _card([_note("Imbalance Alerts are being tested and will be available to subscribers soon.",
                                      TEAL_DIM)])])
    parts: List[Any] = [_title(), intro]
    for label, path, renderer in (("Status", "/api/imbalance/universe", render_status),
                                  ("Track record", "/api/imbalance/track-record", render_track_record),
                                  ("Recent alerts", "/api/imbalance/log?limit=100",
                                   lambda d: render_log(d.get("alerts") or []))):
        try:
            parts.append(renderer(_get(path, session)))
        except Exception as exc:
            parts.append(_card([_section(label), _note(f"Could not load: {exc}", RED_DIM)]))
    return html.Div(parts)
