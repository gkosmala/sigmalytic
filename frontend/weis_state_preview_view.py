# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Renders the /api/admin/weis-state-preview result for the Admin tab (read-only diagnostic)."""
from __future__ import annotations

from typing import Any, Dict

from dash import html

WHITE, MUTED = "#f1f5f9", "#94a3b8"
TEAL, RED, YELLOW = "#34d399", "#f87171", "#fde68a"
BORDER = "rgba(255,255,255,.08)"
STATE_COLOR = {"Armed": TEAL, "Setting Up": TEAL, "Watching": YELLOW, "Avoid": RED, "No setup": MUTED}


def _td(text, color=WHITE, bold=False, mono=False):
    st = {"padding": "6px 10px", "fontSize": "12px", "color": color, "borderBottom": f"1px solid {BORDER}",
          "whiteSpace": "nowrap"}
    if bold:
        st["fontWeight"] = "800"
    if mono:
        st["fontFamily"] = "DM Mono, monospace"
    return html.Td(text, style=st)


def _th(text):
    return html.Th(text, style={"padding": "6px 10px", "fontSize": "10px", "color": MUTED, "textAlign": "left",
                                "textTransform": "uppercase", "letterSpacing": ".08em",
                                "borderBottom": f"1px solid {BORDER}"})


def _num(v):
    return "-" if v is None else f"{v:g}"


def _trends(d):
    if not d:
        return "-"
    return " / ".join(f"{k}:{v}" for k, v in d.items())


def render_weis_state_preview(payload: Dict[str, Any]) -> html.Div:
    if not isinstance(payload, dict) or "summary" not in payload:
        return html.Div("Unexpected response: " + str(payload)[:200], style={"color": RED, "fontSize": "12px"})
    summary, rows = payload["summary"], payload.get("rows") or []
    if not summary.get("symbols"):
        return html.Div("No symbols could be evaluated. Skipped: " + str(payload.get("skipped"))[:300],
                        style={"color": YELLOW, "fontSize": "12px"})

    counts = " | ".join(f"{k}: {v}" for k, v in sorted((summary.get("states") or {}).items()))
    shown = [r for r in rows if r["state"] != "No setup"][:60]
    detail = []
    for r in shown:
        flip = f"flipped from {r['flipped_from']}" if r.get("flipped_from") else ""
        detail.append(html.Tr([
            _td(r["symbol"], bold=True, mono=True),
            _td(r["state"], STATE_COLOR.get(r["state"], WHITE), bold=True),
            _td(r.get("direction") or "-"),
            _td(f"{r.get('line_source') or '-'} x{r.get('line_touches') or '-'}", MUTED),
            _td(_num(r.get("stop")), mono=True), _td(_num(r.get("target")), mono=True),
            _td(_trends(r.get("trends_by_frame")), MUTED),
            _td("; ".join(r.get("angle_change_of_character") or []) or "-", MUTED),
            _td(flip or "-", MUTED),
            _td(str(r.get("radar_status_today") or "-"), MUTED),
            _td(str(r.get("reason") or ""), MUTED),
        ]))
    tbl = html.Table(
        [html.Thead(html.Tr([_th(x) for x in ("Symbol", "State", "Side", "Line", "Stop", "Target", "Trend by frame",
                                              "Angle change", "Flip", "Radar status today", "Why")])),
         html.Tbody(detail)], style={"width": "100%", "borderCollapse": "collapse"})
    skipped = payload.get("skipped") or []
    return html.Div([
        html.Div(f"{summary['symbols']} symbols evaluated ({payload.get('mode')}). {counts}",
                 style={"fontSize": "12px", "color": WHITE, "marginBottom": "8px"}),
        html.Div(f"{summary.get('flipped', 0)} flipped setups; {summary.get('angle_change_of_character', 0)} "
                 f"with an angle change of character. Rows with no setup are hidden.",
                 style={"fontSize": "11px", "color": MUTED, "marginBottom": "8px"}),
        html.Div(tbl, style={"overflowX": "auto"}),
        html.Div(f"{len(skipped)} symbols skipped (no data). " + str(payload.get("note", "")),
                 style={"fontSize": "11px", "color": MUTED, "marginTop": "10px"}),
    ])
