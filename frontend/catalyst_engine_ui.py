# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Multi-Catalyst Alignment Engine rendering (Admin tab): turns /api/admin/catalyst-engine/run output into Dash components."""
from __future__ import annotations

from dash import html

WHITE, MUTED, BORDER = "#f8fafc", "#94a3b8", "rgba(255,255,255,.08)"
GREEN, RED, AMBER, SKY = "#34d399", "#f87171", "#f59e0b", "#38bdf8"


def _fmt(v, digits=2, suffix="%"):
    if v is None:
        return "—"
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v):.{digits}f}{suffix}"


def _move(v, sub=None):
    color = GREEN if (v or 0) > 0 else RED if (v or 0) < 0 else MUTED
    kids = [html.Span(_fmt(v), style={"color": color, "fontWeight": "800"})]
    if sub is not None:
        kids.append(html.Span(f"  {_fmt(sub)} vs SPY", style={"color": MUTED, "fontSize": "11px"}))
    return html.Div(kids)


def _small(text):
    return html.Div(text, style={"fontSize": "11px", "color": MUTED})


def _tile(label, value, sub=None, color=WHITE):
    return html.Div([
        html.Div(label, style={"fontSize": "10px", "fontWeight": "800", "color": MUTED, "letterSpacing": ".1em",
                               "textTransform": "uppercase"}),
        html.Div(value, style={"fontSize": "22px", "fontWeight": "800", "color": color, "marginTop": "4px"}),
        _small(sub) if sub else None,
    ], style={"flex": "1 1 160px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
              "borderRadius": "10px", "padding": "12px"})


def _links(items, key="headline"):
    out = []
    for h in items or []:
        text = h.get(key) or h.get("label") or ""
        out.append(html.Div(html.A(text, href=h.get("url") or None, target="_blank", rel="noopener",
                                   style={"color": "#cbd5e1", "textDecoration": "none"}),
                            style={"fontSize": "11px", "marginTop": "2px", "fontStyle": "italic"}))
    return out


def _badge(status):
    color = {"Reversal": AMBER, "Aligned": GREEN}.get(status, SKY)
    return html.Span(status, style={"fontSize": "11px", "fontWeight": "800", "color": color, "border": f"1px solid {color}",
                                    "borderRadius": "4px", "padding": "2px 8px", "whiteSpace": "nowrap"})


TH = {"fontSize": "10px", "fontWeight": "800", "color": MUTED, "textTransform": "uppercase", "letterSpacing": ".08em",
      "textAlign": "left", "padding": "8px 10px", "borderBottom": f"1px solid {BORDER}", "verticalAlign": "bottom"}
TD = {"padding": "10px", "borderBottom": f"1px solid {BORDER}", "verticalAlign": "top", "fontSize": "12px", "color": WHITE}


def _row(r, has_kw):
    pre = r.get("pre")
    cat = r.get("catalyst")
    cells = [html.Td([html.Div(r["reaction_date"], style={"fontWeight": "800"}),
                      _small(f"Window {r['window_start']} → {r['window_end']}")], style=TD)]
    if has_kw:
        src = None
        if pre:
            src = (html.A(pre["source"], href=pre.get("filing_url"), target="_blank", rel="noopener",
                          style={"fontSize": "11px", "color": MUTED}) if pre.get("filing_url") else _small(pre.get("source", "")))
        cells.append(html.Td([_small(pre["date"]), _move(pre["move"], pre["abn"]), src] + _links(pre["headlines"])
                             if pre else [_small("Not found")], style=TD))
    if cat:
        detail = _links(cat["headlines"]) + _links(cat["filings"], key="label")
        if not cat["explained"]:
            detail = [_small("Unexplained: no company-specific headline or 8-K")]
        cells.append(html.Td([_small(cat["date"]), _move(cat["move"], cat["abn"])] + detail, style={**TD, "maxWidth": "380px"}))
    else:
        cells.append(html.Td(_small("—"), style=TD))
    cells.append(html.Td(_move(r["runup"]), style=TD))
    cells.append(html.Td([html.A(f"8-K {r['release']}", href=r["filing_url"], target="_blank", rel="noopener",
                                 style={"fontSize": "11px", "color": MUTED}),
                          _small(r["timing"]), _move(r["earn_move"], r["earn_abn"]),
                          _small(f"{r['sigma_mult']:.1f}× a normal day") if r.get("sigma_mult") is not None else None],
                         style=TD))
    cells.append(html.Td(_move(r["post5"]), style=TD))
    cells.append(html.Td([_badge(r["status"]), _small(f"lead: {r['lead_source']}")], style=TD))
    return html.Tr(cells)


def render(payload: dict):
    s = payload.get("summary") or {}
    rows = payload.get("rows") or []
    has_kw = any(r.get("pre") for r in rows) or bool(payload.get("keyword"))
    kw_label = payload.get("keyword") or "pre-announcement"
    q = s.get("quarters") or 0

    def pct(v):
        return "—" if v is None else f"{v:.1f}%"

    def avg(v):
        return "—" if v is None else f"±{v:.2f}%"

    tiles = [
        _tile("Quarters", str(q), f"Prices through {payload.get('price_through', '')}"),
        _tile("Avg earnings move", avg(s.get("avg_abs_earn")), f"{avg(s.get('avg_abs_earn_abn'))} vs SPY"),
        _tile("Earnings vs normal day", "—" if s.get("avg_sigma_mult") is None else f"{s['avg_sigma_mult']:.1f}×",
              "Market-adjusted move ÷ typical day"),
        _tile("Avg catalyst move", avg(s.get("avg_abs_catalyst")), f"{s.get('catalysts_explained', 0)} of {q} matched to news/8-K"),
    ]
    if has_kw:
        tiles.append(_tile(f"Avg {kw_label} move", avg(s.get("avg_abs_pre")), f"Found in {s.get('pre_found', 0)} of {q}"))
    else:
        tiles.append(_tile("Avg run-up between prints", avg(s.get("avg_abs_runup"))))
    tiles += [
        _tile("Reversal rate", pct(s.get("reversal_rate")),
              f"{'Pre-announcement (or run-up)' if has_kw else 'Run-up'} vs earnings, opposite sign", color=AMBER),
        _tile("5-day follow-through", pct(s.get("follow_through_rate")), "Kept the reaction's direction"),
    ]

    head = ["Earnings reaction day"] + (["Pre-announcement"] if has_kw else []) + \
           ["Biggest pre-earnings catalyst", "Run-up", "Earnings print", "Next 5 days", "Alignment"]
    table = html.Div(html.Table([
        html.Thead(html.Tr([html.Th(h, style=TH) for h in head])),
        html.Tbody([_row(r, has_kw) for r in rows]),
    ], style={"width": "100%", "borderCollapse": "collapse"}), style={"overflowX": "auto"})

    title = f"{payload.get('symbol', '')} · {payload.get('years', '')}-year multi-catalyst alignment"
    if payload.get("cached"):
        title += " (cached)"
    return html.Div([
        html.Div(title, style={"fontSize": "14px", "fontWeight": "800", "color": WHITE, "marginBottom": "10px"}),
        html.Div(tiles, style={"display": "flex", "flexWrap": "wrap", "gap": "10px", "marginBottom": "14px"}),
        table if rows else _small("No complete quarters in this period."),
        html.Details([
            html.Summary("How this is calculated", style={"cursor": "pointer", "fontSize": "11px", "color": MUTED,
                                                          "marginTop": "12px"}),
            html.Ul([html.Li(n, style={"fontSize": "11px", "color": MUTED, "lineHeight": "1.6"})
                     for n in payload.get("notes") or []]),
        ]),
        _small(f"Generated {payload.get('generated', '')}. Research output only; not investment advice."),
    ])
