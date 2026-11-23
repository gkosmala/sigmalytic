# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Top Companies Report Pack (Admin tab): picks the largest U.S. companies by market cap (you choose how many, 1 to 100)
and builds one PDF of public reports.
Backend: /api/admin/report-pack/* in backend/main.py and backend/report_pack.py."""
from __future__ import annotations

import base64
from datetime import datetime

from dash import Input, Output, State, callback_context, dcc, html, no_update

WHITE, MUTED, BORDER = "#f8fafc", "#94a3b8", "rgba(255,255,255,.08)"
GREEN, RED, AMBER, TEAL = "#34d399", "#f87171", "#f59e0b", "#2DD4BF"
STATE_COLORS = {"done": GREEN, "building": TEAL, "queued": MUTED, "failed": RED, "blocked": RED}

_BTN = {"color": WHITE, "border": "none", "borderRadius": "8px", "padding": "9px 14px", "fontSize": "12px",
        "fontWeight": "700", "cursor": "pointer", "marginRight": "8px"}


def _btn(label, id_, bg=TEAL):
    return html.Button(label, id=id_, n_clicks=0, style={**_BTN, "background": bg})


def build_block(admin_card):
    return admin_card([
        html.Div("TOP COMPANIES REPORT PACK", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE, "marginBottom": "6px"}),
        html.Div("Builds one public market-structure report for each of the largest U.S. companies by market "
                 "capitalization and combines them into one PDF: a cover page with contents, then each report with its "
                 "chart, key levels, recent news and the disclaimer. The analysis is written from the platform's data at no "
                 "cost. News is scanned free from SEC filings, Alpaca/Benzinga headlines (sorted into company, international "
                 "and geopolitical news) and FRED economic data; Claude Haiku then writes the short news paragraphs "
                 "(about a tenth of a cent per report). "
                 "The reports never name the platform's methods; any report that still contains a blocked word is left "
                 "out of the PDF. About a minute per report (so 50 reports take roughly 25 to 50 minutes); it keeps "
                 "running if you leave this page, and reports already finished today are reused at no new cost, so "
                 "going from 25 to 50 only builds the 25 new ones.",
                 style={"fontSize": "11px", "color": MUTED, "marginBottom": "12px", "lineHeight": "1.6"}),
        html.Div([
            html.Span("How many companies: ", style={"fontSize": "12px", "color": WHITE, "fontWeight": "700"}),
            dcc.Input(id="report-pack-size", type="number", value=25, min=1, max=100, step=1, debounce=True,
                      style={"width": "70px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}",
                             "borderRadius": "6px", "padding": "5px 8px", "color": WHITE, "fontSize": "12px"}),
            html.Span(" 1 to 100 (use the arrows or type a number; 3 makes a quick sample)",
                      style={"fontSize": "11px", "color": MUTED, "marginLeft": "6px"}),
            dcc.Checklist(id="report-pack-ai", value=["y"],
                          options=[{"label": " Haiku writes the news paragraphs (otherwise headlines are listed, $0)", "value": "y"}],
                          style={"display": "inline-block", "marginLeft": "18px", "fontSize": "11px", "color": MUTED}),
        ], style={"marginBottom": "10px"}),
        html.Div([
            _btn("Show today's list", "report-pack-load-btn", "#334155"),
            _btn("Generate PDF pack", "report-pack-start-btn"),
            _btn("Retry failed", "report-pack-retry-btn", "#475569"),
            _btn("Start over (new reports)", "report-pack-restart-btn", "#7f1d1d"),
            _btn("Download PDF", "report-pack-download-btn", "#1d4ed8"),
        ], style={"marginBottom": "12px"}),
        dcc.Download(id="report-pack-download"),
        dcc.Interval(id="report-pack-poll", interval=30000, n_intervals=0, disabled=False),
        dcc.Loading(html.Div(id="report-pack-list", style={"fontSize": "12px", "color": WHITE}), type="dot", color=TEAL),
        dcc.Loading(html.Div(id="report-pack-status", style={"fontSize": "12px", "color": WHITE, "marginTop": "10px"}),
                    type="dot", color=TEAL),
        html.Div(id="report-pack-download-msg", style={"fontSize": "11px", "color": AMBER, "marginTop": "6px"}),
    ], sx={"marginBottom": "16px"})


def _cap(v):
    v = float(v or 0)
    return f"${v / 1e12:,.2f}T" if v >= 1e12 else f"${v / 1e9:,.0f}B"


def _size(v):
    try:
        return max(1, min(100, int(v or 25)))
    except (TypeError, ValueError):
        return 25


def render_list(d, size=25):
    if not d.get("ok"):
        return html.Div(d.get("error") or "Could not build the list.", style={"color": RED})
    cell = {"padding": "3px 8px", "borderBottom": f"1px solid {BORDER}", "fontSize": "11px", "color": WHITE}
    head = {**cell, "color": MUTED, "fontWeight": "800"}
    rows = [html.Tr([html.Th(h, style=head) for h in ("#", "Symbol", "Company", "Est. market cap", "Price", "Shares as of")])]
    top = d.get("top") or []
    chosen, rest = top[:size], top[size:]
    for r in chosen:
        rows.append(html.Tr([html.Td(r["rank"], style=cell), html.Td(r["symbol"], style={**cell, "fontWeight": "700"}),
                             html.Td(r.get("name") or "", style=cell), html.Td(_cap(r["market_cap"]), style=cell),
                             html.Td(f"${r['price']:,.2f}", style=cell), html.Td(r.get("shares_as_of") or "", style=cell)]))
    nxt = ", ".join(f"{r['symbol']} ({_cap(r['market_cap'])})" for r in (rest or d.get("next") or [])[:5])
    skipped = d.get("skipped") or []
    return html.Div([
        html.Div(f"List computed {d.get('computed_at', '')[:16].replace('T', ' ')} UTC from {d.get('candidates')} candidates. "
                 f"{d.get('method', '')} Showing the top {len(chosen)}. Estimates are for choosing the companies only; "
                 f"they are not printed in the PDF.",
                 style={"fontSize": "11px", "color": MUTED, "marginBottom": "6px"}),
        html.Table(rows, style={"borderCollapse": "collapse", "width": "100%", "maxWidth": "820px"}),
        html.Div("Next in line: " + nxt, style={"fontSize": "11px", "color": MUTED, "marginTop": "6px"}) if nxt else html.Div(),
        html.Div("Skipped: " + "; ".join(f"{x['symbol']} ({x['reason']})" for x in skipped[:8]),
                 style={"fontSize": "11px", "color": AMBER, "marginTop": "4px"}) if skipped else html.Div(),
    ])


def render_status(s):
    state = s.get("state")
    if state == "none":
        return html.Div("No pack has been started today. Press Generate PDF pack.", style={"color": MUTED, "fontSize": "11px"})
    if not s.get("ok", True):
        return html.Div(s.get("error") or "Error.", style={"color": RED})
    c = s.get("counts") or {}
    total = s.get("total") or 0
    finished = c.get("done", 0) + c.get("failed", 0) + c.get("blocked", 0)
    head_txt = {"running": f"Building reports: {finished} of {total} finished",
                "stopped": "Stopped: " + str(s.get("error") or ""),
                "assembling": "All reports finished; putting the PDF together",
                "done": f"PDF ready: {c.get('done', 0)} of {total} reports included",
                "failed": "The pack stopped: " + str(s.get("error") or "")}.get(state, str(state))
    extra = []
    if c.get("failed"):
        extra.append(f"{c['failed']} failed")
    if c.get("blocked"):
        extra.append(f"{c['blocked']} blocked")
    cost = s.get("cost_usd")
    kids = [html.Div(head_txt + (f" ({', '.join(extra)})" if extra else "") + f" · AI cost so far ${float(cost or 0):,.4f}",
                     style={"fontSize": "13px", "fontWeight": "800",
                            "color": GREEN if state == "done" else (RED if state in ("stopped", "failed") else WHITE)})]
    if state == "stopped":
        kids.append(html.Div("Add credits at platform.claude.com/settings/billing (Claude Console, Billing), then press "
                             "Generate PDF pack again. Finished reports are kept.", style={"fontSize": "11px", "color": AMBER}))
    if s.get("resumed"):
        kids.append(html.Div("The server restarted during the run; it resumed from the reports already saved.",
                             style={"fontSize": "11px", "color": AMBER}))
    if state == "done":
        kids.append(html.Div("Press Download PDF to save it.", style={"fontSize": "11px", "color": MUTED, "marginBottom": "4px"}))
    items = s.get("items") or {}
    for sym in s.get("symbols") or []:
        it = items.get(sym) or {}
        st = it.get("state", "queued")
        detail = []
        if st == "done":
            detail.append(f"{it.get('news_written', 0)} news paragraphs written, {it.get('news_listed', 0)} listed as headlines")
            if it.get("cost_usd"):
                detail.append(f"${float(it['cost_usd']):,.4f}")
        if it.get("note"):
            detail.append(str(it["note"]))
        kids.append(html.Div([
            html.Span(f"{sym:<6}", style={"fontFamily": "DM Mono, monospace", "color": WHITE, "fontWeight": "700",
                                           "display": "inline-block", "width": "64px"}),
            html.Span(st, style={"color": STATE_COLORS.get(st, MUTED), "fontWeight": "800", "display": "inline-block",
                                 "width": "74px", "fontSize": "11px"}),
            html.Span(" · ".join(detail), style={"color": MUTED, "fontSize": "11px"}),
        ], style={"marginTop": "2px"}))
    return html.Div(kids, style={"border": f"1px solid {BORDER}", "borderRadius": "10px", "padding": "10px"})


def register(app, req, backend_http, auth_headers):
    @app.callback(Output("report-pack-list", "children"),
                  Input("report-pack-load-btn", "n_clicks"),
                  State("report-pack-size", "value"),
                  State("s-session", "data"),
                  prevent_initial_call=True)
    def _load(n, size, session):
        try:
            r = req.get(f"{backend_http}/api/admin/report-pack/top", headers=auth_headers(session), timeout=180)
            if r.status_code in (401, 403):
                return "Admin access only. Sign in again if your session expired."
            if not r.ok:
                return f"Could not load the list (error {r.status_code}): {r.text[:200]}"
            return render_list(r.json(), _size(size))
        except Exception as exc:
            return f"Could not reach the backend: {exc}"

    @app.callback(Output("report-pack-status", "children"),
                  Output("report-pack-poll", "disabled"),
                  Input("report-pack-start-btn", "n_clicks"),
                  Input("report-pack-retry-btn", "n_clicks"),
                  Input("report-pack-restart-btn", "n_clicks"),
                  Input("report-pack-poll", "n_intervals"),
                  State("report-pack-size", "value"),
                  State("report-pack-ai", "value"),
                  State("s-session", "data"))
    def _status(n_start, n_retry, n_restart, n_poll, size, ai, session):
        trig = callback_context.triggered_id
        clicked = bool(callback_context.triggered and (callback_context.triggered[0].get("value") or 0))
        try:
            if trig in ("report-pack-start-btn", "report-pack-retry-btn", "report-pack-restart-btn") and clicked:
                body = {"use_ai": "y" in (ai or []), "size": _size(size), "retry_failed": trig == "report-pack-retry-btn",
                        "restart": trig == "report-pack-restart-btn"}
                r = req.post(f"{backend_http}/api/admin/report-pack/start", json=body, headers=auth_headers(session), timeout=200)
            else:
                r = req.get(f"{backend_http}/api/admin/report-pack/status", headers=auth_headers(session), timeout=30)
            if r.status_code in (401, 403):
                return "Admin access only. Sign in again if your session expired.", True
            if not r.ok:
                return f"Could not get the pack status (error {r.status_code}): {r.text[:200]}", False
            s = r.json()
            return render_status(s), s.get("state") not in ("running", "assembling")
        except Exception as exc:
            return f"Could not reach the backend: {exc}", False

    @app.callback(Output("report-pack-download", "data"),
                  Output("report-pack-download-msg", "children"),
                  Input("report-pack-download-btn", "n_clicks"),
                  State("s-session", "data"),
                  prevent_initial_call=True)
    def _download(n, session):
        try:
            r = req.get(f"{backend_http}/api/admin/report-pack/pdf", headers=auth_headers(session), timeout=120)
            if r.status_code == 404:
                return no_update, "No finished PDF for today yet."
            if r.status_code in (401, 403):
                return no_update, "Admin access only. Sign in again if your session expired."
            if not r.ok:
                return no_update, f"Could not download (error {r.status_code}): {r.text[:200]}"
            name = f"Sigmalytic_Top_Companies_Report_Pack_{datetime.now().strftime('%Y-%m-%d')}.pdf"
            return {"content": base64.b64encode(r.content).decode("ascii"), "filename": name, "base64": True,
                    "type": "application/pdf"}, ""
        except Exception as exc:
            return no_update, f"Could not reach the backend: {exc}"
