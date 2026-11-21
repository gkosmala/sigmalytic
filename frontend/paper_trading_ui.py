# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Admin Paper Trading (Admin tab only): the simulated $1,000,000 test account that trades the
platform's Trade Finder setups automatically. Shows the Admin Paper Portfolio and Admin Paper
Journal, plus every trading rule as a setting. Nothing here appears in a subscriber's Journal or
Portfolio, and no order is ever sent to a broker.
Backend: /api/admin/paper/* in backend/main.py and backend/paper_trader.py."""
from __future__ import annotations

from datetime import datetime

from dash import Input, Output, State, callback_context, dcc, html, no_update

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover
    go = None

WHITE, MUTED, BORDER = "#f8fafc", "#94a3b8", "rgba(255,255,255,.08)"
GREEN, RED, AMBER, TEAL = "#34d399", "#f87171", "#f59e0b", "#2DD4BF"

_BTN = {"color": WHITE, "border": "none", "borderRadius": "8px", "padding": "9px 14px", "fontSize": "12px",
        "fontWeight": "700", "cursor": "pointer", "marginRight": "8px"}
_INPUT = {"width": "80px", "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}", "borderRadius": "6px",
          "padding": "5px 8px", "color": WHITE, "fontSize": "12px"}
_LABEL = {"fontSize": "12px", "color": WHITE, "fontWeight": "700", "minWidth": "150px", "display": "inline-block"}
_RADIO = {"display": "inline-block", "fontSize": "12px", "color": WHITE}
_HEAD = {"fontSize": "12px", "fontWeight": "800", "color": WHITE, "margin": "16px 0 6px"}

SETTING_IDS = {  # setting key -> component id
    "enabled": "paper-enabled", "direction": "paper-direction", "entry_mode": "paper-entry",
    "sizing": "paper-sizing", "risk_pct": "paper-risk", "fixed_pct": "paper-fixed",
    "max_position_pct": "paper-cap", "max_positions": "paper-maxpos", "exit_mode": "paper-exit",
    "time_limit": "paper-time", "entry_window": "paper-window", "cost_bps": "paper-cost",
}


def _btn(label, id_, bg=TEAL):
    return html.Button(label, id=id_, n_clicks=0, style={**_BTN, "background": bg})


def _row(label, control, note=""):
    return html.Div([html.Span(label, style=_LABEL), control,
                     html.Span(note, style={"fontSize": "11px", "color": MUTED, "marginLeft": "10px"})],
                    style={"marginBottom": "8px"})


def _radio(id_, options, value):
    return dcc.RadioItems(id=id_, value=value, inline=True, options=[{"label": f" {l} ", "value": v} for v, l in options],
                          style=_RADIO, inputStyle={"marginLeft": "10px"})


def _num(id_, value, step=0.1):
    return dcc.Input(id=id_, type="number", value=value, step=step, debounce=True, style=_INPUT)


def build_block(admin_card):
    settings = html.Details([
        html.Summary("Trading rules (your settings)", style={"cursor": "pointer", "fontSize": "12px", "fontWeight": "800",
                                                             "color": TEAL, "marginBottom": "10px"}),
        _row("Auto-trading", _radio("paper-enabled", [(True, "On"), (False, "Off (no buys or sells)")], True)),
        _row("Direction", _radio("paper-direction", [("long", "Longs only"), ("both", "Longs and shorts")], "long")),
        _row("Entry", _radio("paper-entry", [("trigger", "When price reaches the entry trigger (platform rule)"),
                                             ("armed", "As soon as the setup is Armed")], "trigger")),
        _row("Sizing", _radio("paper-sizing", [("risk", "Risk a % of the account per trade"),
                                               ("fixed", "Fixed % of the account per trade")], "risk")),
        _row("Risk per trade", _num("paper-risk", 0.5, 0.05), "% of the account lost if the stop is hit (risk sizing)"),
        _row("Fixed size", _num("paper-fixed", 5.0, 0.5), "% of the account per position (fixed sizing)"),
        _row("Cap per position", _num("paper-cap", 10.0, 1), "% of the account, either sizing"),
        _row("Max open positions", _num("paper-maxpos", 15, 1)),
        _row("Exits", _radio("paper-exit", [("target", "Stop and target (platform rule)"),
                                            ("half_2r", "Stop; half at 2x risk, rest at target"),
                                            ("status", "Stop, or when the radar status changes")], "target")),
        _row("Time limit", dcc.Dropdown(id="paper-time", value=10, clearable=False, searchable=False,
                                        options=[{"label": "5 sessions", "value": 5}, {"label": "10 sessions", "value": 10},
                                                 {"label": "20 sessions", "value": 20}, {"label": "No limit", "value": 0}],
                                        style={"width": "150px", "display": "inline-block", "verticalAlign": "middle",
                                               "fontSize": "12px", "color": "#0f172a"}),
             "close a trade still open after this many sessions"),
        _row("Entry window", _num("paper-window", 10, 1), "sessions a setup may wait for its trigger"),
        _row("Trading cost", _num("paper-cost", 5.0, 0.5), "basis points per side"),
        html.Div([_btn("Save settings", "paper-save-btn")], style={"margin": "6px 0 4px"}),
        html.Div("Changes apply to trades opened from now on; open trades keep the rules they were opened with.",
                 style={"fontSize": "11px", "color": MUTED}),
        html.Div([
            html.Span("Start over: ", style={**_LABEL, "minWidth": "0"}),
            dcc.Input(id="paper-reset-cash", type="number", value=1_000_000, step=1000, debounce=True,
                      style={**_INPUT, "width": "120px"}),
            dcc.Input(id="paper-reset-confirm", type="text", placeholder="type RESET", debounce=False,
                      style={**_INPUT, "width": "110px", "marginLeft": "8px"}),
            _btn("Reset account", "paper-reset-btn", "#7f1d1d"),
            html.Span("Earlier results are kept under their run number.", style={"fontSize": "11px", "color": MUTED}),
        ], style={"marginTop": "14px"}),
    ], open=False, style={"marginBottom": "12px", "padding": "10px 12px", "border": f"1px solid {BORDER}",
                          "borderRadius": "10px"})

    return admin_card([
        html.Div("PAPER TRADING · ADMIN TEST ACCOUNT", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE,
                                                              "marginBottom": "6px"}),
        html.Div("A simulated account that trades the platform's Trade Finder setups automatically, checked every five "
                 "minutes during market hours. Fills are simulated inside Sigmalytic from live market data; no order is "
                 "ever sent to a broker. Results appear only here, never in a subscriber's Journal or Portfolio.",
                 style={"fontSize": "11px", "color": MUTED, "marginBottom": "12px", "lineHeight": "1.6"}),
        settings,
        html.Div([_btn("Refresh", "paper-refresh-btn", "#334155"), _btn("Run a check now", "paper-run-btn", "#1d4ed8")],
                 style={"marginBottom": "10px"}),
        html.Div(id="paper-msg", style={"fontSize": "12px", "color": AMBER, "marginBottom": "8px"}),
        dcc.Interval(id="paper-poll", interval=60000, n_intervals=0),
        dcc.Loading(html.Div(id="paper-summary"), type="dot", color=TEAL),
        html.Div("ADMIN PAPER PORTFOLIO", style=_HEAD),
        html.Div(id="paper-portfolio"),
        html.Div("ADMIN PAPER JOURNAL", style=_HEAD),
        html.Div(id="paper-journal"),
    ], sx={"marginBottom": "16px"})


# ── rendering ────────────────────────────────────────────────────────────────
def _money(v, sign=False):
    if v is None:
        return "–"
    s = f"${abs(v):,.2f}"
    return (("+" if v > 0 else "−") + s) if sign and v else s


def _pct(v):
    return "–" if v is None else f"{v:+.2f}%"


def _when(iso):
    if not iso:
        return "–"
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromisoformat(iso).astimezone(ZoneInfo("America/New_York")).strftime("%b %d %H:%M ET")
    except Exception:
        return iso[:16]


def _table(headers, rows):
    cell = {"padding": "4px 8px", "borderBottom": f"1px solid {BORDER}", "fontSize": "11px", "color": WHITE}
    head = {**cell, "color": MUTED, "fontWeight": "800"}
    out = [html.Tr([html.Th(h, style=head) for h in headers])]
    for r in rows:
        out.append(html.Tr([html.Td(c if not isinstance(c, tuple) else c[0],
                                    style={**cell, **({"color": c[1]} if isinstance(c, tuple) else {})}) for c in r]))
    return html.Table(out, style={"borderCollapse": "collapse", "width": "100%", "marginBottom": "6px"})


def _colored(v, text=None):
    return (text if text is not None else _money(v, True), GREEN if (v or 0) > 0 else RED if (v or 0) < 0 else WHITE)


def _kpi(label, value, color=WHITE):
    return html.Div([html.Div(label, style={"fontSize": "10px", "color": MUTED, "fontWeight": "700"}),
                     html.Div(value, style={"fontSize": "17px", "color": color, "fontWeight": "800"})],
                    style={"padding": "8px 12px", "border": f"1px solid {BORDER}", "borderRadius": "10px",
                           "marginRight": "8px", "marginBottom": "8px", "minWidth": "120px"})


def render_summary(d):
    if not d.get("ok"):
        return html.Div(d.get("error") or "Could not load the paper account.", style={"color": RED})
    st = d["stats"]
    kpis = html.Div([
        _kpi("Equity", _money(d["equity"])),
        _kpi("P&L", _money(d["pnl"], True), GREEN if d["pnl"] > 0 else RED if d["pnl"] < 0 else WHITE),
        _kpi("Return", _pct(d["return_pct"])),
        _kpi("SPY, same period", _pct(d["spy_return_pct"])),
        _kpi("Cash", _money(d["cash"])),
        _kpi("Closed trades", f"{st['closed_trades']}" + (f" · {st['win_rate']}% won" if st["win_rate"] is not None else "")),
        _kpi("Profit factor", "–" if st["profit_factor"] is None else f"{st['profit_factor']:.2f}"),
        _kpi("Average R", "–" if st["avg_r"] is None else f"{st['avg_r']:+.2f}"),
        _kpi("Max drawdown", f"{st['max_drawdown_pct']:.2f}%"),
    ], style={"display": "flex", "flexWrap": "wrap"})
    s = d["settings"]
    status = ("Auto-trading ON" if s.get("enabled") else "Auto-trading OFF") + \
             f" · run {d['run_id']} started {_when(d['started'])} with {_money(d['starting_cash'])}" + \
             f" · last check {_when(d['last_cycle'])}" + (f": {d['last_cycle_note']}" if d.get("last_cycle_note") else "")
    parts = [html.Div(status, style={"fontSize": "11px", "color": GREEN if s.get("enabled") else AMBER,
                                     "marginBottom": "8px"}), kpis]
    curve = d.get("curve") or []
    if go is not None and len(curve) >= 2:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[c["day"] for c in curve], y=[c["equity"] for c in curve], name="Paper account",
                                 line={"color": TEAL, "width": 2}))
        first_spy = next((c["spy"] for c in curve if c["spy"]), None)
        if first_spy:
            fig.add_trace(go.Scatter(x=[c["day"] for c in curve],
                                     y=[d["starting_cash"] * c["spy"] / first_spy if c["spy"] else None for c in curve],
                                     name="SPY, same starting amount", line={"color": MUTED, "width": 1.5, "dash": "dot"}))
        fig.update_layout(height=240, margin={"l": 50, "r": 10, "t": 10, "b": 30}, paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font={"color": WHITE, "size": 11},
                          legend={"orientation": "h", "y": 1.12}, yaxis={"tickprefix": "$", "gridcolor": BORDER},
                          xaxis={"gridcolor": BORDER, "type": "category"})
        parts.append(dcc.Graph(figure=fig, config={"displayModeBar": False}))
    return html.Div(parts)


_EXIT_NAMES = {"target": "Stop/target", "half_2r": "Half at 2R", "status": "Radar status"}


def render_portfolio(d):
    if not d.get("ok"):
        return ""
    rows = []
    for p in d["positions"]:
        rows.append([p["symbol"], p["side"], f"{p['qty']:,}", _money(p["entry_price"]), _money(p["last_price"]),
                     _money(p["value"]), _colored(p["unrealized"]), _money(p["stop"]),
                     _money(p["target"]) if p["target"] else "–",
                     (_money(p["t1_price"]) + (" (done)" if p["t1_done"] else "")) if p["t1_price"] else "–",
                     f"{p['sessions_held']}/{p['time_limit'] or '∞'}", _EXIT_NAMES.get(p["exit_mode"], p["exit_mode"])])
    open_t = _table(["Symbol", "Side", "Shares", "Entry", "Last", "Value", "Open P&L", "Stop", "Target", "2R level",
                     "Sessions", "Exit rule"], rows) if rows else \
        html.Div("No open positions.", style={"fontSize": "11px", "color": MUTED, "marginBottom": "8px"})
    wrows = [[w["symbol"], w["side"], w["test_bar_date"], _money(w["entry_trigger"]), _money(w["stop"]),
              _money(w["target"]), str(w["sessions_waited"])] for w in d["waiting"]]
    wait_t = _table(["Symbol", "Side", "Armed on", "Entry trigger", "Stop", "Target", "Sessions waited"], wrows) if wrows \
        else html.Div("No setups waiting for their trigger.", style={"fontSize": "11px", "color": MUTED})
    return html.Div([open_t, html.Div("Setups waiting for their trigger", style={**_HEAD, "fontSize": "11px",
                                                                               "color": MUTED}), wait_t])


def render_journal(summary, j):
    if not j.get("ok"):
        return html.Div(j.get("error") or "Could not load the journal.", style={"color": RED})
    closed = [[c["symbol"], c["side"], f"{c['qty']:,}", _money(c["entry_price"]), _money(c.get("exit_avg")),
               _when(c["entry_time"]), _when(c["exit_time"]), c["exit_reason"] or "", _colored(c["pnl"]),
               "–" if c["r_multiple"] is None else f"{c['r_multiple']:+.2f}R"] for c in (summary.get("closed") or [])]
    fills = [[_when(f["at"]), f["symbol"], f["action"], f"{f['qty']:,}", _money(f["price"]), _money(f["fee"]),
              _colored(f["pnl"]) if f["pnl"] is not None else "–", f["reason"] or "", _money(f["cash_after"])]
             for f in j["fills"]]
    passed = [[_when(p["seen"]), p["symbol"], p["side"], p["test_bar_date"], p["status"], p["reason"] or ""]
              for p in j["not_taken"]]
    sub = {**_HEAD, "fontSize": "11px", "color": MUTED}
    return html.Div([
        html.Div("Closed trades", style=sub),
        _table(["Symbol", "Side", "Shares", "Entry", "Avg exit", "Opened", "Closed", "Exit reason", "Net P&L", "R"],
               closed) if closed
        else html.Div("No closed trades yet.", style={"fontSize": "11px", "color": MUTED}),
        html.Div("Every fill", style=sub),
        _table(["Time", "Symbol", "Action", "Shares", "Price", "Cost", "P&L", "Reason", "Cash after"], fills) if fills
        else html.Div("No fills yet.", style={"fontSize": "11px", "color": MUTED}),
        html.Div("Setups not taken", style=sub),
        _table(["Seen", "Symbol", "Side", "Armed on", "Outcome", "Why"], passed) if passed
        else html.Div("None.", style={"fontSize": "11px", "color": MUTED}),
    ])


# ── callbacks ────────────────────────────────────────────────────────────────
_KEYS = list(SETTING_IDS)


def register(app, req, backend_http, auth_headers):
    @app.callback(
        [Output("paper-msg", "children"), Output("paper-summary", "children"),
         Output("paper-portfolio", "children"), Output("paper-journal", "children")]
        + [Output(SETTING_IDS[k], "value") for k in _KEYS],
        [Input("paper-refresh-btn", "n_clicks"), Input("paper-run-btn", "n_clicks"),
         Input("paper-save-btn", "n_clicks"), Input("paper-reset-btn", "n_clicks"), Input("paper-poll", "n_intervals")],
        [State(SETTING_IDS[k], "value") for k in _KEYS]
        + [State("paper-reset-cash", "value"), State("paper-reset-confirm", "value"), State("s-session", "data")],
    )
    def _update(n_refresh, n_run, n_save, n_reset, n_poll, *rest):
        values, (reset_cash, confirm, session) = rest[:len(_KEYS)], rest[len(_KEYS):]
        trig = callback_context.triggered_id
        clicked = bool(callback_context.triggered and (callback_context.triggered[0].get("value") or 0))
        headers = auth_headers(session)
        msg = ""
        fill_controls = trig in (None, "paper-refresh-btn", "paper-save-btn", "paper-reset-btn") or n_poll == 0
        try:
            if trig == "paper-save-btn" and clicked:
                body = {k: v for k, v in zip(_KEYS, values)}
                r = req.post(f"{backend_http}/api/admin/paper/settings", json=body, headers=headers, timeout=30)
                msg = "Settings saved." if r.ok else f"Could not save settings (error {r.status_code}): {r.text[:200]}"
            elif trig == "paper-run-btn" and clicked:
                r = req.post(f"{backend_http}/api/admin/paper/run", json={}, headers=headers, timeout=120)
                if r.ok:
                    res = r.json()
                    msg = ("Check finished: " + ("; ".join(res.get("notes") or []) or "no changes")) if res.get("ok") \
                        else f"Check failed: {res.get('error') or res.get('skipped')}"
                else:
                    msg = f"Check failed (error {r.status_code}): {r.text[:200]}"
            elif trig == "paper-reset-btn" and clicked:
                if (confirm or "").strip().upper() != "RESET":
                    msg = "Type RESET in the box first to start the account over."
                else:
                    r = req.post(f"{backend_http}/api/admin/paper/reset", json={"starting_cash": reset_cash},
                                 headers=headers, timeout=30)
                    res = r.json() if r.ok else {}
                    msg = (f"Account reset: run {res.get('run_id')} starts with {_money(res.get('starting_cash'))}."
                           if res.get("ok") else f"Reset failed: {res.get('error') or r.text[:200]}")
            rs = req.get(f"{backend_http}/api/admin/paper/summary", headers=headers, timeout=60)
            if rs.status_code in (401, 403):
                return ["Admin access only. Sign in again if your session expired.", "", "", ""] + [no_update] * len(_KEYS)
            summary = rs.json() if rs.ok else {"ok": False, "error": f"error {rs.status_code}: {rs.text[:200]}"}
            rj = req.get(f"{backend_http}/api/admin/paper/journal", headers=headers, timeout=60)
            journal = rj.json() if rj.ok else {"ok": False, "error": f"error {rj.status_code}"}
        except Exception as exc:
            return [f"Could not reach the backend: {exc}", "", "", ""] + [no_update] * len(_KEYS)
        controls = [no_update] * len(_KEYS)
        if fill_controls and summary.get("ok"):
            controls = [summary["settings"].get(k) for k in _KEYS]
        return [msg, render_summary(summary), render_portfolio(summary), render_journal(summary, journal)] + controls
