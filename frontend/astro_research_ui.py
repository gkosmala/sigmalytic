# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Astro Research rendering (Admin tab): turns the /api/admin/astro-research/* payloads into Dash components."""
from __future__ import annotations

from dash import dcc, html

WHITE, MUTED, BORDER = "#f8fafc", "#94a3b8", "rgba(255,255,255,.08)"
AMBER, GREEN = "#f59e0b", "#34d399"
_CELL = {"padding": "4px 8px", "borderBottom": f"1px solid {BORDER}", "fontSize": "11px", "whiteSpace": "nowrap"}
_HEAD = {**_CELL, "color": MUTED, "fontWeight": "800", "textAlign": "left"}


def _table(head, rows):
    return html.Div(html.Table([html.Thead(html.Tr([html.Th(h, style=_HEAD) for h in head])),
                                html.Tbody([html.Tr([html.Td(c, style=_CELL) for c in r]) for r in rows])],
                               style={"borderCollapse": "collapse", "width": "100%"}), style={"overflowX": "auto", "margin": "6px 0"})


def _h(t):
    return html.Div(t, style={"fontSize": "10px", "fontWeight": "800", "color": MUTED, "letterSpacing": ".12em",
                              "textTransform": "uppercase", "marginTop": "14px"})


def render_table(payload: dict):
    rows = [[r["symbol"], r["ipo_date"], r["ipo_utc"], r["address"], f"{r['lat']:.4f}, {r['lon']:.4f}", f"{r['elev_m']} m",
             r["coord_source"]] for r in payload.get("symbols", [])]
    return html.Div([
        html.Div("Elevations are user-supplied and approximate. First trade is 9:30 a.m. ET by default; for listings before 1985 "
                 "the real first print is unknown. Rows marked unreconciled or user-supplied are not independently verified.",
                 style={"color": AMBER, "fontSize": "11px", "marginBottom": "6px"}),
        _table(["Symbol", "IPO date", "Chart moment", "Address at IPO", "Lat, Lon", "Elev.", "Source"], rows)])


def render_run(p: dict):
    if not p.get("ok"):
        return f"Could not run: {p.get('error', 'unknown error')}"
    kids = [html.Div(f"{p['row']['symbol']} natal chart moment: {p['row']['ipo_utc']}", style={"fontWeight": "800", "color": WHITE})]
    kids += [_h("Positions at start (chart location)"),
             _table(list(p["start_chart"].keys()), [list(p["start_chart"].values())]),
             _h("IPO chart"), _table(list(p["ipo_chart"].keys()), [list(p["ipo_chart"].values())])]
    kids += [_h("Transit aspects to the IPO chart (within 1 degree)"),
             _table(["Transit", "Aspect", "Natal", "From", "To", "Tightest"],
                    [[w["transit"], w["aspect"], w["natal"], w["from"], w["to"], f"{w['tightest_orb']} deg {w['tightest_at']}"]
                     for w in p["windows"]]) if p["windows"] else html.Div("None in this window.", style={"color": MUTED, "fontSize": "11px"})]
    piv = p.get("pivots") or {}
    if piv.get("error"):
        kids += [_h("Pivots"), html.Div(piv["error"], style={"color": AMBER, "fontSize": "11px"})]
    else:
        kids += [_h(f"Pivots from Alpaca daily bars (since {piv.get('since')})"),
                 _table(["Pivot", "Price", "Date"], [[x["name"], f"${x['price']:.2f}", x["date"]] for x in piv.get("pivots", [])])]
        if p.get("pivot_check"):
            kids += [_h("Cross-check against your pasted pivot table"),
                     _table(["Pivot", "Pasted", "Computed", "Computed date", "Difference", "Month matches"],
                            [[c["name"], f"${c['pasted']}", c["computed"], c.get("computed_date", ""),
                              "" if c["diff_pct"] is None else f"{c['diff_pct']}%",
                              "" if c["date_match"] is None else ("yes" if c["date_match"] else "no")] for c in p["pivot_check"]])]
    kids += [_h("Hourly positions (first 72 hours, chart location)"),
             _table(["ET", "UTC", "Moon phase"] + list(p["hourly"][0]["bodies"].keys()) if p["hourly"] else [],
                    [[h["time_et"], h["time_utc"], h["moon_phase"]] + list(h["bodies"].values()) for h in p["hourly"]]),
             _h("Plan draft"), html.Pre(p["draft"], style={"whiteSpace": "pre-wrap", "background": "rgba(0,0,0,.3)",
                                                         "border": f"1px solid {BORDER}", "borderRadius": "8px", "padding": "10px",
                                                         "fontSize": "12px", "color": WHITE, "fontFamily": "DM Mono, monospace"}),
             dcc.Clipboard(content=p["draft"], title="Copy draft", style={"cursor": "pointer", "color": WHITE})]
    return html.Div(kids)


def render_backtest(p: dict):
    if not p.get("ok"):
        return f"Could not run: {p.get('error', 'unknown error')}"
    rows = [[f"{x['horizon']} day(s)", x["n"], x.get("mean_pct", ""), x.get("baseline_mean_pct", ""), x.get("hit_rate_pct", ""),
             x.get("baseline_hit_rate_pct", ""), x.get("p_value", "")] for x in p["results"]]
    return html.Div([html.Div(f"{p['events_found']} events, {p['first_bar']} to {p['last_bar']}", style={"fontWeight": "800", "color": WHITE}),
                     _table(["Horizon", "Events", "Mean %", "All-days mean %", "Hit rate %", "All-days hit rate %", "p-value"], rows),
                     html.Div(p["caveat"], style={"color": AMBER, "fontSize": "11px"})])
