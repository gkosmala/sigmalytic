# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Renders /api/admin/radar-bars-check for the Admin tab (read-only diagnostic)."""
from __future__ import annotations

from typing import Any, Dict

from dash import html

WHITE, MUTED = "#f1f5f9", "#94a3b8"
RED, YELLOW = "#f87171", "#fde68a"
BORDER = "rgba(255,255,255,.08)"


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


def _bars(d):
    d = d or {}
    return f"{d.get('bars', 0)} ({d.get('first') or '-'} to {d.get('last') or '-'})"


def _used(d):
    if not d:
        return "-"
    return f"{d.get('count')} ({d.get('first')} to {d.get('last')})"


def _diffs(d):
    if d is None:
        return "-"
    if not d:
        return "none"
    return "; ".join(f"{x['day']}: radar {x['radar']} vs fresh {x['fresh']}" for x in d[:4])


def render_radar_bars_check(payload: Dict[str, Any]) -> html.Div:
    if not isinstance(payload, dict) or "rows" not in payload:
        return html.Div("Unexpected response: " + str(payload)[:200], style={"color": RED, "fontSize": "12px"})
    rows = payload["rows"]
    if not rows:
        return html.Div(payload.get("note") or "No rows.", style={"color": YELLOW, "fontSize": "12px"})
    head = ["Symbol", "Radar status now", "State on fresh bars (last N, your setting)",
            "State on fresh bars with the worker's last bars", "Reproduces radar?",
            "Same bars?", "Last-10 closes that differ", "Supabase copy (date: close, updated)"]
    body = []
    for r in rows:
        radar = f"{r.get('radar_status_direction') or '-'}/{r.get('radar_status_now')}"
        sub = r.get("state_on_fresh_with_radar_tail")
        repro = None if sub is None else (sub == radar)
        sb = r.get("supabase_rows")
        sbtxt = "-" if sb is None else "; ".join(
            f"{x.get('date')}: {x.get('close')} ({str(x.get('updated_at'))[:16]})" for x in sb[-3:]) or "no rows"
        body.append(html.Tr([
            _td(r["symbol"], bold=True, mono=True),
            _td(radar),
            _td(r.get("state_on_fresh_last_setting") or "-"),
            _td(sub or "not yet"),
            _td({True: "yes", False: "NO", None: "not yet"}[repro],
                RED if repro is False else WHITE, bold=True),
            _td({True: "yes", False: "NO", None: "not yet"}[r.get("same_window")],
                RED if r.get("same_window") is False else WHITE, bold=True),
            _td(_diffs(r.get("tail_differences")), MUTED, mono=True),
            _td(sbtxt, MUTED, mono=True),
        ]))
    src = ((rows[0].get("radar_bars_source") or {}) if rows else {})
    loaded = src.get("loaded_at")
    when = "-"
    if loaded:
        from datetime import datetime, timezone
        when = datetime.fromtimestamp(loaded, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rc = payload.get("redis_copy") or {}
    redis_txt = ("Redis copy: " + (f"age {rc.get('age_hours')} h, {rc.get('bytes')} bytes" if rc.get("present")
                 else f"not present ({rc.get('reason') or rc.get('error') or rc.get('ttl')})"))
    return html.Div([
        html.Div(f"{len(rows)} symbols compared. Radar status comes from the worker's shared cache; the radar reads the last {payload.get('radar_bar_count_setting') or '?'} completed daily bars (your setting).",
                 style={"fontSize": "12px", "color": WHITE, "marginBottom": "4px"}),
        html.Div(f"Worker loaded its bars from: {src.get('source') or 'not yet recorded'} at {when}. {redis_txt}.",
                 style={"fontSize": "12px", "color": WHITE, "marginBottom": "8px"}),
        html.Div(html.Table([html.Thead(html.Tr([_th(h) for h in head])), html.Tbody(body)],
                            style={"borderCollapse": "collapse", "width": "100%"}),
                 style={"overflowX": "auto"}),
        html.Div(payload.get("note", ""), style={"fontSize": "10px", "color": MUTED, "marginTop": "8px"}),
    ])
