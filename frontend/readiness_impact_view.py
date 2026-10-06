# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Renders the /api/admin/readiness-impact result for the Admin tab (read-only diagnostic)."""
from __future__ import annotations

from typing import Any, Dict

from dash import html

WHITE, MUTED = "#f1f5f9", "#94a3b8"
TEAL, RED, YELLOW = "#34d399", "#f87171", "#fde68a"
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


def _signed(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "-", MUTED
    return f"{x:+.1f}", (TEAL if x > 0 else RED if x < 0 else WHITE)


def render_readiness_impact(payload: Dict[str, Any]) -> html.Div:
    if not isinstance(payload, dict) or "summary" not in payload:
        return html.Div("Unexpected response: " + str(payload)[:200], style={"color": RED, "fontSize": "12px"})
    summary, rows = payload["summary"], payload.get("rows") or []
    if not summary.get("symbols"):
        return html.Div("No symbols could be scored. Skipped: " + str(payload.get("skipped"))[:300],
                        style={"color": YELLOW, "fontSize": "12px"})

    sum_rows = []
    for stage, label in (("stage1", "Sort basis (cached)"), ("stage2", "Page shown to users")):
        for side in ("Long", "Short"):
            d = (summary.get(stage) or {}).get(side)
            if not d:
                continue
            sd, color = _signed(d["mean_delta"])
            sum_rows.append(html.Tr([
                _td(label), _td(side, bold=True), _td(str(d["n"]), mono=True),
                _td(sd, color, bold=True, mono=True), _td(_signed(d["median_delta"])[0], mono=True),
                _td(f"{_signed(d['min_delta'])[0]} to {_signed(d['max_delta'])[0]}", mono=True),
                _td(f"{d['state_changes']} of {d['n']}", mono=True),
                _td("; ".join(f"{t['from']} to {t['to']}: {t['count']}" for t in d["transitions"][:4]) or "-", MUTED),
            ]))
    summary_tbl = html.Table(
        [html.Thead(html.Tr([_th(x) for x in ("Stage", "Side", "Symbols", "Mean change", "Median", "Range",
                                              "State changes", "Most common")])),
         html.Tbody(sum_rows)], style={"width": "100%", "borderCollapse": "collapse"})

    detail = []
    for r in sorted(rows, key=lambda x: -abs(x["stage2"]["delta"]))[:40]:
        s2 = r["stage2"]
        ds, dc = _signed(s2["delta"])
        f = r["factors"]
        detail.append(html.Tr([
            _td(r["symbol"], bold=True, mono=True), _td(r["side"]), _td(f"{r['weis_composite']:.0f}", mono=True),
            _td(f"RS {f['relative_strength']:.0f} VP {f['volume_pressure']:.0f} B {f['behavioral']:.0f} "
                f"E {f['expansion_node']:.0f}", MUTED, mono=True),
            _td(f"{s2['now']['readiness']:.0f}", mono=True), _td(f"{s2['restored']['readiness']:.0f}", mono=True),
            _td(ds, dc, bold=True, mono=True),
            _td(f"{s2['now']['state']} to {s2['restored']['state']}" if s2["now"]["state"] != s2["restored"]["state"]
                else s2["now"]["state"], WHITE),
        ]))
    detail_tbl = html.Table(
        [html.Thead(html.Tr([_th(x) for x in ("Symbol", "Side", "Weis", "Real factor values", "Readiness now",
                                              "If restored", "Change", "State")])),
         html.Tbody(detail)], style={"width": "100%", "borderCollapse": "collapse"})

    skipped = payload.get("skipped") or []
    return html.Div([
        html.Div(f"{summary['symbols']} symbols scored live.", style={"fontSize": "12px", "color": WHITE, "marginBottom": "8px"}),
        html.Div(summary_tbl, style={"overflowX": "auto", "marginBottom": "14px"}),
        html.Div("Largest changes (page shown to users)", style={"fontSize": "10px", "fontWeight": "700", "color": WHITE,
                                                                  "textTransform": "uppercase", "marginBottom": "6px"}),
        html.Div(detail_tbl, style={"overflowX": "auto"}),
        html.Div(f"{len(skipped)} symbols skipped (no data). " + str(payload.get("note", "")),
                 style={"fontSize": "11px", "color": MUTED, "marginTop": "10px"}),
    ])
