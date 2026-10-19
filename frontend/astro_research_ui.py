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


def render_report(p: dict):
    if not p.get("ok"):
        return f"Could not run: {p.get('error', 'unknown error')}"
    row = p["row"]
    kids = [html.Div(f"{row['symbol']} on {p['day']}  |  reference ${p['ref_price']} (close of {p['ref_date']})  |  ${p['unit']:g} per degree",
                     style={"fontWeight": "800", "color": WHITE})]
    for n in p.get("notes", []):
        kids.append(html.Div(n, style={"color": AMBER, "fontSize": "11px"}))
    if p.get("actual"):
        a = p["actual"]
        kids.append(html.Div(f"Actual that day: open {a['open']}, high {a['high']}, low {a['low']}, close {a['close']}",
                             style={"color": MUTED, "fontSize": "11px"}))
    oc = p["open_chart"]
    kids += [_h("1. Ephemeris at the open (9:30 a.m. ET, chart location)"), _table(list(oc.keys()), [[v["position"] for v in oc.values()], [f"{v['lon']}" for v in oc.values()]]),
             html.Div(f"Moon phase at the open: {p['moon_phase_open']} (0 new, 0.5 full)", style={"color": MUTED, "fontSize": "11px"})]
    if p["day_events"]:
        kids.append(html.Div("Today: " + "; ".join(p["day_events"]), style={"color": WHITE, "fontSize": "11px"}))
    kids += [_h("Exact aspects during the session"),
             _table(["Time (ET)", "Aspect"], [[e["time"], e["text"]] for e in p["exact_events"]]) if p["exact_events"]
             else html.Div("None.", style={"color": MUTED, "fontSize": "11px"}),
             _h("Hourly positions"), _table(["ET", "UTC", "Moon phase"] + list(p["hourly"][0]["bodies"].keys()),
                                           [[h["time_et"], h["time_utc"], h["moon_phase"]] + list(h["bodies"].values()) for h in p["hourly"]]),
             _h("IPO chart"), _table(list(p["ipo_chart"].keys()), [list(p["ipo_chart"].values())])]
    kids.append(_h("2. Major market structure and intermediate pivots (daily and weekly, Alpaca split-adjusted)"))
    kids.append(_table(["Frame", "Pivot", "Price", "Date", "Days", "Weeks", "Gann count"],
                       [[x["frame"], x["name"], f"${x['price']:.2f}", x["date"], x["counts"]["days"], x["counts"]["weeks"],
                         (f"near {x['counts']['nearest_day_number']}d / {x['counts']['nearest_week_number']}w" if x["counts"]["flag"] else "")]
                        for x in p["pivot_rows"]]))
    if p.get("pivot_check"):
        kids += [_h("Cross-check against your pasted pivot table"),
                 _table(["Pivot", "Pasted", "Computed", "Computed date", "Difference", "Month matches"],
                        [[c["name"], f"${c['pasted']}", c["computed"], c.get("computed_date", ""),
                          "" if c["diff_pct"] is None else f"{c['diff_pct']}%",
                          "" if c["date_match"] is None else ("yes" if c["date_match"] else "no")] for c in p["pivot_check"]])]
    kids += [_h("3. Gann confluence zones (two or more methods within 0.2%)"),
             _table(["Price", "Score", "Methods", "Members"], [[f"${z['price']:.2f}", z["score"], ", ".join(z["families"]), "; ".join(z["members"][:5])]
                                                                for z in p["top_zones"]]) if p["top_zones"]
             else html.Div(_no_conf(p), style={"color": AMBER, "fontSize": "12px"})]
    kids += [_h("3b. Mean of Five / Cycle of Eight octagon bands (band width is the tightness; no tolerance applied)"),
             _table(["Band", "Width", "Source", "Mean of Five level", "Cycle of Eight level", "Other methods inside"],
                    [[f"${z['low']:.2f} to ${z['high']:.2f}", f"{z['width_pct']}%", z["source"], z["mean_of_five"], z["cycle_of_eight"],
                      "; ".join(z["inside"][:4]) or "-"] for z in p.get("top_bands", [])])
             if p.get("top_bands") else html.Div("No Mean of Five / Cycle of Eight octagon levels fall within range.", style={"color": MUTED, "fontSize": "11px"})]
    kids += [_h("4. Hourly tactical plan"),
             _table(["Time (ET)", "Rule window", "Attention", "Moon", "Astro and time marks", "Zones above", "Zones below", "Mean/Cycle bands"],
                    [[b["time_et"], b["phase"], b["attention"], b["moon"], "; ".join(b["events"] + b["marks"]) or "-",
                      _zones_cell(b, "above", "near_above"), _zones_cell(b, "below", "near_below"),
                      "; ".join(f"${z['low']:.2f}-${z['high']:.2f}" for z in b.get("mean_bands", [])) or "-"]
                     for b in p["blocks"]]),
             html.Div("A reversal needs location, structure and volume to agree. Mid-range prices are a no-trade area. Zones are references, not forecasts.",
                      style={"color": AMBER, "fontSize": "11px"}),
             _h("Report text"), html.Pre(p["draft"], style={"whiteSpace": "pre-wrap", "background": "rgba(0,0,0,.3)",
                                                           "border": f"1px solid {BORDER}", "borderRadius": "8px", "padding": "10px",
                                                           "fontSize": "12px", "color": WHITE, "fontFamily": "DM Mono, monospace"}),
             dcc.Clipboard(content=p["draft"], title="Copy report", style={"cursor": "pointer", "color": WHITE})]
    return html.Div(kids)


def _no_conf(p: dict) -> str:
    d = p.get("confluence_diag") or {}
    cp = d.get("closest_pair")
    txt = (f"No confluence found: no two different methods landed within {d.get('tolerance_pct', 0.2)}% of each other "
           f"({d.get('levels_found', 0)} levels were in range).")
    if cp:
        txt += f" The closest pair was {cp['gap_pct']}% apart ({cp['a']} and {cp['b']})."
    return txt + " The nearest single-method levels are in the hourly plan below; they are not confluence."


def _zones_cell(b: dict, key: str, near_key: str) -> str:
    z = b.get(key) or []
    if z:
        return ", ".join(f"${x['price']:.2f}" for x in z)
    n = b.get(near_key) or []
    return ("nearest (not confluence): " + ", ".join(f"${x['price']:.2f}" for x in n)) if n else "-"


def render_backtest(p: dict):
    if not p.get("ok"):
        return f"Could not run: {p.get('error', 'unknown error')}"
    rows = [[f"{x['horizon']} day(s)", x["n"], x.get("mean_pct", ""), x.get("baseline_mean_pct", ""), x.get("hit_rate_pct", ""),
             x.get("baseline_hit_rate_pct", ""), x.get("p_value", "")] for x in p["results"]]
    return html.Div([html.Div(f"{p['events_found']} events, {p['first_bar']} to {p['last_bar']}", style={"fontWeight": "800", "color": WHITE}),
                     _table(["Horizon", "Events", "Mean %", "All-days mean %", "Hit rate %", "All-days hit rate %", "p-value"], rows),
                     html.Div(p["caveat"], style={"color": AMBER, "fontSize": "11px"})])
