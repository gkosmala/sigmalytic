# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Astro Research rendering (Admin tab): turns the /api/admin/astro-research/* payloads into Dash components."""
from __future__ import annotations

from dash import dcc, html
import plotly.graph_objects as go

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
    kids += gann_extra_components(p)
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


ANGLE_COLORS = {"8x1": "#ef4444", "4x1": "#f97316", "3x1": "#f59e0b", "2x1": "#eab308", "1x1": "#f8fafc",
                "1x2": "#34d399", "1x3": "#2dd4bf", "1x4": "#38bdf8", "1x8": "#a78bfa"}
SHORT_ANCHOR = {"Extreme low": "Low", "Extreme high": "High", "Latest confirmed bottom": "Bottom", "Second latest confirmed bottom": "Bottom 2",
                "Latest confirmed top": "Top", "Second latest confirmed top": "Top 2"}
CHART_NAMES = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "4h": "4-hour", "2h": "2-hour"}


def render_fan_chart(p: dict):
    """The Gann Fan over the price bars (a category axis, so there are no gaps for weekends or overnight)."""
    if not p.get("ok"):
        return f"Could not draw the fan: {p.get('error', 'unknown error')}"
    bars, labels = p["bars"], p["labels"]
    fig = go.Figure(go.Candlestick(x=labels[:len(bars)], open=[b["o"] for b in bars], high=[b["h"] for b in bars], low=[b["l"] for b in bars],
                                   close=[b["c"] for b in bars], name="Price", increasing_line_color=GREEN, decreasing_line_color="#ef4444"))
    seen = set()
    for ln in sorted(p["lines"], key=lambda x: x["kind"] != "low"):   # rising lines first so each legend entry shows a solid line
        a = ln["angle"]
        fig.add_trace(go.Scatter(x=[labels[ln["x0"]], labels[ln["x1"]]], y=[ln["y0"], ln["y1"]], mode="lines", name=a, legendgroup=a,
                                 showlegend=a not in seen, hovertemplate=f"{a} from {ln['from'].lower()}<br>%{{y:.2f}}<extra></extra>",
                                 line={"color": ANGLE_COLORS.get(a, MUTED), "width": 2.4 if a == "1x1" else 1.1,
                                       "dash": "solid" if ln["kind"] == "low" else "dot"}))
        seen.add(a)
    if p["anchors"]:
        fig.add_trace(go.Scatter(x=[labels[x["x"]] for x in p["anchors"]], y=[x["y"] for x in p["anchors"]], mode="markers+text", name="Starting points",
                                 text=[SHORT_ANCHOR.get(x["label"], x["label"]) for x in p["anchors"]], textposition="top center",
                                 marker={"color": AMBER, "size": 9, "symbol": "diamond"}, textfont={"size": 10, "color": WHITE}))
    lo = min(b["l"] for b in bars)
    hi = max(b["h"] for b in bars)
    pad = (hi - lo) * 0.06
    fig.update_layout(height=620, margin={"l": 50, "r": 20, "t": 30, "b": 40}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,.2)",
                      font={"color": WHITE}, xaxis={"type": "category", "nticks": 12, "rangeslider": {"visible": False}, "gridcolor": BORDER},
                      yaxis={"range": [lo - pad, hi + pad], "gridcolor": BORDER, "side": "right"}, legend={"orientation": "h", "y": 1.06},
                      hovermode="x unified")
    note = (f"{p.get('symbol', '')} {CHART_NAMES.get(p['chart'], p['chart'])} chart: {p['bars_shown']} bars, {p['first']} to {p['last']}. "
            f"The 1x1 moves ${p['unit']:g} (your price-per-degree table) per bar. Solid lines rise from bottoms, dotted lines fall from tops. "
            f"Lines run {p['future_bars']} bars past the last bar. ")
    if p["chart"] in ("2h", "4h"):
        note += ("Hourly bars are as Alpaca returns them. Gann's course has no rule for hourly bars, so the daily chart's pivot rules are used "
                 "and the 1x1 moves the same table unit per hourly bar.")
    return html.Div([html.Div(note, style={"color": MUTED, "fontSize": "11px"}), dcc.Graph(figure=fig, config={"displaylogo": False})])


def render_fan_test(p: dict):
    if not p.get("ok"):
        return f"Could not run: {p.get('error', 'unknown error')}"
    ph = [[r["chart"], r["anchor"], r["phase"], r["days"]] + [("" if r.get(f"fwd_{h}") is None else r[f"fwd_{h}"]) for h in p["horizons"]] for r in p["phase"]]
    ra = [[r["chart"], r["anchor"], r["direction"], r["breaks"]]
          + [("" if r.get(f"reach_{h}") is None else f"{r[f'reach_{h}']}  (same distance, any day: {r.get(f'plain_{h}', '')})") for h in p["reach_horizons"]] for r in p["angles"]]
    ad = p.get("all_days")
    if ad:
        ph.append(["all", "all tested days", "no ray condition", ad["days"]] + [("" if ad.get(f"fwd_{h}") is None else ad[f"fwd_{h}"]) for h in p["horizons"]])
    return html.Div([
        html.Div(f"Gann Fan rules: {p['days_tested']} days ({'every day' if p['step'] == 1 else 'every ' + str(p['step']) + 'th day'}), {p['first_day']} to {p['last_day']}", style={"fontWeight": "800", "color": WHITE}),
        html.Div("Rule of All Angles: after a close through one angle, % of breaks where price reached the next angle within N days", style={"color": WHITE, "marginTop": "8px"}),
        _table(["Chart", "Starting point", "Break", "Breaks"] + [f"Within {h} days (%)" for h in p["reach_horizons"]], ra),
        html.Div("Position on the 1x1 (Gann: above is strong, below is weak): mean % move after the close", style={"color": WHITE, "marginTop": "8px"}),
        _table(["Chart", "Starting point", "Position", "Days"] + [f"Next {h} day(s) (%)" for h in p["horizons"]], ph),
        html.Div(p["caveat"], style={"color": AMBER, "fontSize": "11px"})])


def render_pivot_scan(p: dict):
    rows = p.get("rows", [])
    by = {n: sum(1 for r in rows if r["months"] == n) for n in p.get("months", [])}
    return html.Div([
        html.Div(f"Pivot scan, {p['today']}: {len(rows)} pivots in {p['with_bars']} of {p['universe']} symbols with price history", style={"fontWeight": "800", "color": WHITE}),
        html.Div("Count by months ago: " + ", ".join(f"{n}: {c}" for n, c in by.items()), style={"color": WHITE, "fontSize": "12px"}),
        _table(["Months ago", "Symbol", "Pivot", "Pivot date", "Pivot price", "Date N months ago", "Confirmed"],
               [[r["months"], r["symbol"], r["kind"], r["date"], f"${r['price']:.2f}", r["target"], r["confirmed"]] for r in rows]),
        html.Div(p.get("note", ""), style={"color": AMBER, "fontSize": "11px"})])


def render_level_test(p: dict):
    if not p.get("ok"):
        return f"Could not run: {p.get('error', 'unknown error')}"
    if p.get("rows") is not None and p.get("months") is not None:
        return render_pivot_scan(p)
    if p.get("angles") is not None:
        return render_fan_test(p)
    if p.get("lines") is not None:
        return render_fan_chart(p)
    if p.get("groups"):
        return html.Div([render_level_test({"ok": True, **g}) if "metrics" in g else
                         html.Div(f"{g['label']}: {g.get('error', 'no result')}", style={"color": MUTED, "fontSize": "11px", "marginTop": "8px"})
                         for g in p["groups"]])
    what = p.get("label") or " and ".join({"zone": "confluence zones", "band": "Mean/Cycle bands"}.get(k, k) for k in p.get("kinds", []))
    rows = [[m["label"], "" if m["real"] is None else m["real"]] for m in p["metrics"]]
    return html.Div([
        html.Div(f"Level test ({what}): {p['days_tested']} days ({'every day' if p.get('step', 1) == 1 else 'every ' + str(p['step']) + 'th day'}), {p['first_day']} to {p['last_day']}, {p['touches_real']} touches",
                 style={"fontWeight": "800", "color": WHITE}),
        _table(["Measure", "Report levels"], rows),
        html.Div(p["caveat"], style={"color": AMBER, "fontSize": "11px"})])


def _wheel(c: dict):
    sky, ipo = c.get("wheel", {}).get("sky", {}), c.get("wheel", {}).get("ipo", {})
    fig = go.Figure()
    for name, lons, r, color in (("Sky at the open", sky, 1.0, AMBER), ("IPO chart", ipo, 0.7, GREEN)):
        fig.add_trace(go.Scatterpolar(theta=list(lons.values()), r=[r] * len(lons), mode="markers+text", text=[n[:3] for n in lons],
                                      textposition="top center", name=name, marker={"color": color, "size": 8}, textfont={"size": 10, "color": WHITE}))
    fig.update_layout(height=380, margin={"l": 30, "r": 30, "t": 20, "b": 20}, paper_bgcolor="rgba(0,0,0,0)", font={"color": WHITE},
                      legend={"orientation": "h"},
                      polar={"bgcolor": "rgba(0,0,0,.2)", "radialaxis": {"visible": False, "range": [0, 1.2]},
                             "angularaxis": {"direction": "counterclockwise", "rotation": 180, "tickvals": list(range(0, 360, 30)),
                                             "gridcolor": BORDER, "linecolor": BORDER}})
    return dcc.Graph(figure=fig, config={"displayModeBar": False})


def gann_extra_components(p: dict) -> list:
    """Sections 3c to 3f: Square of 144, numerology, natal cycle dates, cosmogram."""
    kids = [_h("3c. Square of 144 (PDF pp. 42-44; anchors per your rule; distances shown, no tolerance)")]
    rows = []
    for b in p.get("square_of_144", []):
        if b["kind"] == "center":
            rows.append([b["label"], f"${b['price']:.2f}", "price-only", ", ".join(f"${x['price']:.2f}" for x in b["levels"]) or "-", "-"])
            continue
        rows.append([b["label"], f"${b['price']:.2f}", b["date"], ", ".join(f"${x['price']:.2f}" for x in b["levels"]) or "-",
                     "; ".join(f"{t['unit']} {t['elapsed']} (mark {t['nearest_mark']}, {t['days_away']:+d}d)" for t in b["time_marks"])])
    kids.append(_table(["Anchor", "Price", "Date", "Levels in range", "Time vs the nearest mark"], rows))
    kids.append(html.Div("Highest and lowest prices come from the Alpaca history fetched, which may not be the true all-time range.",
                         style={"color": MUTED, "fontSize": "11px"}))
    n = p.get("numerology") or {}
    nv = n.get("natal", {})
    kids += [_h("3d. Numerology (PDF pp. 22-24)"),
             html.Div(f"Natal vibration of {nv.get('date')}: {nv.get('vibration')}. Vibration of {p['day']}: {n.get('day_vibration')}"
                      + (" (matches)" if n.get("day_matches_natal") else "") + ".", style={"color": WHITE, "fontSize": "12px"})]
    groups = {}
    for x in n.get("levels", []):
        for w in x["why"]:
            groups.setdefault(w if not w.startswith("digits") else "digits reduce to the natal vibration", []).append(f"${x['price']:.2f}")
    kids.append(_table(["Rule", "Prices in range"], [[k, ", ".join(v)] for k, v in groups.items()]))
    kids.append(html.Div("Not scored in the confluence list because they are dense. Zones that land on one are marked in section 3.",
                         style={"color": MUTED, "fontSize": "11px"}))
    kids += [_h("3e. Natal cycle dates (PDF p. 24)"),
             _table(["Cycle", "Today?", "Previous", "Next"], [[c["cycle"], "YES" if c["on_report_day"] else "", c["previous"] or "-",
                                                              ", ".join(x["date"] for x in c["next"])] for c in n.get("cycles", [])]),
             ]
    nb = p.get("natal_breakout") or {}
    hits = [m for m in nb.get("matrix", []) if m["once"] or m["repeating"]]
    kids += [_h("3e2. Natal breakout (owner-supplied: date matrix from the listing date, then (sqrt(reference) +/- factor)^2, factors 0.125 to 2.0)"),
             html.Div(f"Days since listing: {nb['matrix'][0]['days_since_listing'] if nb.get('matrix') else '-'}. Cycles hit today: "
                      + ("; ".join(f"{m['cycle']} ({'also the first time that count is reached' if m['once'] else 'repeating'})" for m in hits) or "none"),
                      style={"color": WHITE, "fontSize": "12px"}),
             html.Div("Reading confirmed by the owner: the cycles repeat from the listing date (every 7 days, every 49 days, every 3 months...).",
                      style={"color": MUTED, "fontSize": "11px"})]
    if nb.get("levels"):
        kids += [_table(["Reference", "Price", "Date"], [[x["label"], f"${x['price']:.2f}", x["date"]] for x in nb["references"]]),
                 html.Div("Breakout levels in range: " + ", ".join(f"${x['price']:.2f}" for x in nb["levels"]), style={"color": WHITE, "fontSize": "12px"})]
        if not nb.get("listing_bar_found"):
            kids.append(html.Div("The listing-day bar is not in the Alpaca history fetched, so only the swing references are used.", style={"color": AMBER, "fontSize": "11px"}))
    else:
        kids.append(html.Div("No natal window today, so no breakout levels are computed." if not hits else "No breakout level falls within range.",
                             style={"color": MUTED, "fontSize": "11px"}))
    nbase = p.get("natal_base") or {}
    kids.append(_h("3e3. Natal base (owner-supplied: highs and lows of the first-year natal windows, carried forward as support and resistance)"))
    if not nbase.get("history_starts_at_listing"):
        kids.append(html.Div("Not available: the Alpaca history fetched does not reach back to the listing date, so the first-year windows cannot be read.",
                             style={"color": AMBER, "fontSize": "11px"}))
    else:
        kids.append(_table(["Window", "Dates", "High", "Low"],
                           [[w["window"], w["from"] + ("" if w["to"] == w["from"] else f" to {w['to']}"), f"${w['high']:.2f} ({w['high_date']})",
                             f"${w['low']:.2f} ({w['low_date']})"] for w in nbase.get("windows", [])]))
        kids.append(html.Div("In range today: " + (", ".join(f"${x['price']:.2f}" for x in nbase.get("levels", [])) or "none")
                             + ". A window on a non-trading day uses the next trading bar (my rule). Not weighted in the master confluence.",
                             style={"color": WHITE, "fontSize": "12px"}))
    gf = p.get("gann_fan") or {}
    kids += [_h("3e4. Gann Fan (Gann's course, Chapter 4: up from bottoms, down from tops; the 1x1 moves one table unit per time unit)"),
             _table(["Chart", "Starting point", "Price", "Date"], [[a["chart"], a["label"], f"${a['price']:.2f}", a["date"] + (f" (confirmed {a['confirmed']})" if a.get("confirmed") else "")]
                                                                    for a in gf.get("anchors", [])]),
             html.Div(f"Price per time unit (owner's price-per-degree table): ${gf.get('unit', 0):g}. Time unit: a market day (daily), a week (weekly), a month (monthly).",
                      style={"color": MUTED, "fontSize": "11px"})]
    kids.append(html.Div("Rays per starting point (course pp.124-125): the 1x1 and the rays on the side of it the price is on; the other side comes into use when price crosses the 1x1.",
                         style={"color": MUTED, "fontSize": "11px"}))
    rows = []
    for a in gf.get("anchors", []):
        key = a["label"] + " " + a["date"]
        mine = sorted([x for x in gf.get("lines", []) if x["chart"] == a["chart"] and x.get("anchor") == key and x.get("shown", True)], key=lambda y: y["price"])
        rows.append([a["chart"], a["label"], a["date"], f"${a['price']:.2f}",
                     f"{a['price_vs']} the 1x1 (${a['one_by_one']:.2f})" if a.get("price_vs") else "",
                     "; ".join(f"{x['angle']} ${x['price']:.2f}" for x in mine) or "none"])
    kids.append(_table(["Chart", "Starting point", "Date", "Start price", "Price is", "Rays that apply today"], rows))
    tcy = p.get("time_cycles") or {}

    def _w(x):
        return f"{x['text']} ({x['from']}" + (f" to {x['to']}" if x["to"] != x["from"] else "") + f", {x['page']})"
    kids += [_h("3e5. Time cycles (Gann's course pp.46-51, 119, 122, 279-282; counted from each fan starting point)"),
             _table(["Chart", "Starting point", "Date", "Price", "Days ago", "In effect today", "Latest passed", "Next"],
                    [[a["chart"], a["label"], a["date"], f"${a['price']:.2f}", a["elapsed_days"], "; ".join(_w(x) for x in a["now"]) or "none",
                      _w(a["last"]) if a.get("last") else "", _w(a["next"]) if a.get("next") else ""] for a in tcy.get("anchors", [])]),
             html.Div("Square of the range (p.122): a range of N price-per-degree table units squares with time after N bars (days, weeks or months by chart).",
                      style={"color": MUTED, "fontSize": "11px"}),
             _table(["Chart", "From", "To", "Range", "Bars to square", "Bars elapsed", "Remaining"],
                    [[q["chart"], q["from"], q["to"], f"${q['range']:.2f}", q["bars_to_square"], q["bars_elapsed"], f"{q['bars_remaining']:+g}"]
                     for q in tcy.get("square", [])])]
    c = p.get("cosmogram") or {}
    kids += [_h("3f. Cosmogram, raw wheel: when (PDF pp. 2, 108)"), _wheel(c),
             _table(["Pair", "Bodies", "Angle", "Nearest aspect", "Off by"],
                    [[x["kind"], f"{x['a']} - {x['b']}", f"{x['angle']} deg", x["aspect"], f"{x['orb']} deg"] for x in c.get("pairs", [])])]
    pw = c.get("price_wheel")
    if pw:
        kids += [_h(f"3g. Cosmogram, price wheel: where (reference ${pw['price']:.2f} at ${pw['unit']:g} per degree = {pw['degree']} deg)"),
                 _price_wheel(c, pw),
                 html.Div("Tolerances (owner-supplied): price within 3 degrees of the aspect; exact aspect within 1 trading day of the report date "
                          "(weekends skipped, holidays not).", style={"color": MUTED, "fontSize": "11px"}),
                 _table(["Planet", "Longitude", "Angle to price", "Nearest aspect", "Off by", "Exact aspect (ET)", "Price", "Time", "Square-out"],
                        [[x["body"], f"{x['lon']} deg", f"{x['angle']} deg", x["aspect"], f"{x['orb']} deg",
                          (x.get("exact_et") or "not within 4 days") + (f" ({x['trading_days']:+d} trading days)" if x.get("trading_days") is not None else ""),
                          "PASS" if x.get("pass_price") else "fail", "PASS" if x.get("pass_time") else "fail",
                          "SQUARE-OUT" if x.get("square_out") else ""] for x in pw["pairs"]]),
                 html.Div("Prices where a planet at the open would aspect the price degree (60, 90, 120, 180): "
                          + (", ".join(f"${x['price']:.2f}" for x in pw["levels"]) or "none in range"), style={"color": WHITE, "fontSize": "12px"}),
                 html.Div("Owner-supplied method. Scored in the master confluence list below, not in the 0.2% list.", style={"color": MUTED, "fontSize": "11px"})]
    fam = {"pivot": "Pivot", "sq9": "Square of 9", "sq144": "Square of 144", "transit": "Planet line", "natal": "Natal planet line",
           "mean": "Mean of Five / Cycle of Eight", "price_aspect": "Price-wheel aspect"}
    kids += [_h("3h. Master confluence (geometric 60%, astrological 40%; a geometric and an astrological level within 0.5%)"),
             _table(["Price", "Range", "Score", "Geometric", "Astrological", "Members"],
                    [[f"${z['price']:.2f}", f"${z['low']:.2f}-${z['high']:.2f}", z["score"], ", ".join(fam[f] for f in z["geometric"]),
                      ", ".join(fam[f] for f in z["astrological"]), "; ".join(z["members"][:5])] for z in p.get("master_zones", [])])
             if p.get("master_zones") else html.Div("None: no geometric level had an astrological level within 0.5%.", style={"color": AMBER, "fontSize": "12px"}),
             html.Div("Score = 100 x (0.6 x share of geometric methods present + 0.4 x share of astrological methods present). Owner-supplied weights.",
                      style={"color": MUTED, "fontSize": "11px"})]
    return kids


def _price_wheel(c: dict, pw: dict):
    sky = c.get("wheel", {}).get("sky", {})
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(theta=list(sky.values()), r=[1.0] * len(sky), mode="markers+text", text=[n[:3] for n in sky],
                                  textposition="top center", name="Sky at the open", marker={"color": AMBER, "size": 8}, textfont={"size": 10, "color": WHITE}))
    fig.add_trace(go.Scatterpolar(theta=[pw["degree"]], r=[0.7], mode="markers+text", text=[f"${pw['price']:.2f}"], textposition="top center",
                                  name="Price degree", marker={"color": GREEN, "size": 12, "symbol": "diamond"}, textfont={"size": 11, "color": WHITE}))
    fig.update_layout(height=380, margin={"l": 30, "r": 30, "t": 20, "b": 20}, paper_bgcolor="rgba(0,0,0,0)", font={"color": WHITE},
                      legend={"orientation": "h"},
                      polar={"bgcolor": "rgba(0,0,0,.2)", "radialaxis": {"visible": False, "range": [0, 1.2]},
                             "angularaxis": {"direction": "counterclockwise", "rotation": 180, "tickvals": list(range(0, 360, 30)),
                                             "gridcolor": BORDER, "linecolor": BORDER}})
    return dcc.Graph(figure=fig, config={"displayModeBar": False})
