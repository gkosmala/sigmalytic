# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/broker_bi_tab.py
-------------------------
Broker Behavioural Intelligence tab: five account vaults, each holding the
statements of one broker or adviser, graded A-F with the same behavioural
engine used for the subscriber, plus portfolio, benchmark, fee, cash,
tax-lot and Russell 1000 sections.

Plugs into app.py:
  1. from broker_bi_tab import build_broker_bi_tab, register_broker_bi_callbacks
  2. ALL_TABS: ("broker_bi", "Broker Behavioural Intelligence")
  3. render_main: elif tab == "broker_bi": main = build_broker_bi_tab(session)
  4. register_broker_bi_callbacks(app)  (after `app` is created)
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

import requests as _rq
from dash import ALL, MATCH, Input, Output, State, callback_context, dcc, html, no_update

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")
SLOTS = (1, 2, 3, 4, 5)

NAVY_CARD = "#111f35"
TEAL_DIM = "#34d399"
RED_DIM = "#f87171"
YELLOW_DIM = "#fde68a"
BLUE_DIM = "#93c5fd"
WHITE = "#f1f5f9"
BORDER = "rgba(255,255,255,.08)"
GRADE_COLORS = {"A": TEAL_DIM, "B": BLUE_DIM, "C": YELLOW_DIM, "D": "#f97316", "F": RED_DIM, "N/A": "#94a3b8"}

COMPONENT_LABELS = {
    "execution": "Execution", "discipline": "Discipline",
    "timing": "Timing", "risk_management": "Risk Management",
}


def _headers(session: Optional[dict]) -> Dict[str, str]:
    token = ""
    if isinstance(session, dict):
        token = session.get("access_token") or session.get("supabase_access_token") or session.get("token") or ""
    return {"Authorization": f"Bearer {token}"} if token else {"Authorization": "Bearer demo"}


def _card(children, sx=None):
    base = {"background": NAVY_CARD, "border": f"1px solid {BORDER}", "borderRadius": "16px",
            "padding": "20px", "marginBottom": "16px"}
    if sx:
        base.update(sx)
    return html.Div(children, style=base)


def _section(text):
    return html.Div(text, style={"fontSize": "10px", "fontWeight": "700", "color": WHITE,
                                 "textTransform": "uppercase", "letterSpacing": ".1em", "marginBottom": "10px"})


def _grade_badge(grade: str, size: int = 44) -> html.Div:
    color = GRADE_COLORS.get(grade, GRADE_COLORS["N/A"])
    return html.Div(grade, style={
        "fontSize": f"{int(size * 0.55)}px", "fontWeight": "900", "color": color,
        "border": f"2px solid {color}", "borderRadius": "12px", "width": f"{size}px", "height": f"{size}px",
        "display": "flex", "alignItems": "center", "justifyContent": "center",
        "fontFamily": "DM Mono, monospace", "background": f"{color}14"})


def _note(text: str, color: str = YELLOW_DIM) -> html.Div:
    return html.Div(text, style={"fontSize": "12px", "color": color, "padding": "10px 12px",
                                 "border": f"1px solid {color}55", "borderRadius": "10px",
                                 "background": f"{color}10", "marginBottom": "10px"})


def _insufficient(section: Dict[str, Any], title: str) -> html.Div:
    return _card([_section(title), _note("Not enough data: " + str(section.get("reason", "")))])


def _kv(label: str, value: Any) -> html.Div:
    return html.Div([
        html.Span(label, style={"fontSize": "12px", "color": WHITE, "flex": "1"}),
        html.Span(str(value), style={"fontSize": "13px", "fontWeight": "800", "color": WHITE,
                                     "fontFamily": "DM Mono, monospace"}),
    ], style={"display": "flex", "justifyContent": "space-between", "padding": "4px 0",
              "borderBottom": f"1px solid {BORDER}"})


def _pct(x: Any, digits: int = 1) -> str:
    return "—" if x is None else f"{float(x) * 100:.{digits}f}%"


def _money(x: Any) -> str:
    if x is None:
        return "—"
    v = float(x)
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _bullets(items: List[str]) -> html.Ul:
    return html.Ul([html.Li(i, style={"fontSize": "11px", "color": WHITE, "marginBottom": "2px"}) for i in items],
                   style={"margin": "6px 0 0 16px", "padding": 0})


# ---------------------------------------------------------------------------
# Review renderer (pure: dict in, components out)
# ---------------------------------------------------------------------------

def render_review(review: Dict[str, Any]) -> html.Div:
    vault = review.get("vault") or {}
    beh = review.get("behavior") or {}
    title = vault.get("name") or f"Vault {vault.get('slot')}"
    broker = vault.get("broker")
    parts: List[Any] = []

    # Header + overall grade
    parts.append(_card([
        html.Div([
            _grade_badge(beh.get("overall_grade", "N/A"), 64),
            html.Div([
                html.Div(f"{title}" + (f" · {broker}" if broker else ""),
                         style={"fontSize": "18px", "fontWeight": "900", "color": WHITE}),
                html.Div(f"{review.get('executions', 0)} fills from "
                         f"{(review.get('statements') or {}).get('trades', 0)} transaction statement(s) and "
                         f"{(review.get('statements') or {}).get('positions', 0)} holdings statement(s)",
                         style={"fontSize": "11px", "color": WHITE}),
                html.Div(f"Overall behaviour score {beh.get('overall_score')}/100"
                         if beh.get("graded") else "", style={"fontSize": "12px", "color": WHITE}),
            ], style={"marginLeft": "16px"}),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div(beh.get("profile") or "", style={"fontSize": "12px", "color": WHITE, "marginTop": "12px"}),
    ]))

    # Behaviour components
    if beh.get("graded"):
        comps = []
        for key, label in COMPONENT_LABELS.items():
            c = (beh.get("components") or {}).get(key)
            if not c:
                continue
            comps.append(html.Div([
                html.Div([_grade_badge(c["grade"], 34),
                          html.Div([html.Div(label, style={"fontSize": "13px", "fontWeight": "800", "color": WHITE}),
                                    html.Div(f"{c['score']}/100", style={"fontSize": "11px", "color": WHITE})],
                                   style={"marginLeft": "10px"})],
                         style={"display": "flex", "alignItems": "center"}),
                _bullets(c.get("basis") or []),
            ], style={"flex": "1 1 220px", "minWidth": "220px"}))
        parts.append(_card([_section("How the broker behaved (same scoring as your own profile)"),
                            html.Div(comps, style={"display": "flex", "gap": "16px", "flexWrap": "wrap"})]))
        if beh.get("flags"):
            parts.append(_card([_section("Behaviour flags"), _bullets([f.replace("_", " ").title() for f in beh["flags"]])]))
    else:
        parts.append(_card([_section("Behaviour grade"), _note(beh.get("reason", "Not enough data."))]))

    # Results
    res = review.get("results")
    if res:
        parts.append(_card([_section("Results from completed trades"),
                            _kv("Completed trades", res.get("round_trip_trades")),
                            _kv("Win rate", _pct(res.get("win_rate"), 0)),
                            _kv("Realized P&L (after fees)", _money(res.get("realized_pnl"))),
                            _kv("Profit factor", res.get("profit_factor")),
                            _kv("Average win / loss", f"{_money(res.get('average_win'))} / {_money(res.get('average_loss'))}"),
                            _kv("Longest losing streak", res.get("max_losing_streak"))]))

    # Portfolio health + snapshot
    health, snap = review.get("portfolio_health") or {}, review.get("portfolio") or {}
    if snap.get("status") == "ok":
        parts.append(_card([
            html.Div([_grade_badge(health.get("grade", "N/A"), 44),
                      html.Div([html.Div("Portfolio health", style={"fontSize": "14px", "fontWeight": "800", "color": WHITE}),
                                html.Div(f"{health.get('score')}/100", style={"fontSize": "11px", "color": WHITE})],
                               style={"marginLeft": "12px"})], style={"display": "flex", "alignItems": "center"}),
            _bullets(health.get("basis") or []),
            html.Div(style={"height": "10px"}),
            _kv("Total value", _money(snap.get("total_value"))),
            _kv("Cash", f"{_money(snap.get('cash'))} ({_pct(snap.get('cash_pct'), 0)})"),
            _kv("Holdings (effective independent)", f"{snap.get('holdings')} ({snap.get('effective_holdings')})"),
            _kv("Largest positions", ", ".join(f"{p['symbol']} {_pct(p['weight'], 0)}" for p in snap.get("largest_positions", []))),
            _kv("Largest sector", snap.get("largest_sector")),
            _kv("Unrealized P&L", _money(snap.get("unrealized_pnl"))),
            _kv("Share in the Russell 1000", _pct(snap.get("russell_1000_weight"), 0)),
        ]))
    else:
        parts.append(_insufficient(snap, "Portfolio health"))

    bm = review.get("benchmark") or {}
    if bm.get("status") == "ok":
        parts.append(_card([_section(f"Against the benchmark: {bm.get('benchmark')}"),
                            _kv("Account return (after fees)", f"{bm['account_return_pct']:+.2f}%"),
                            _kv("Benchmark return", f"{bm['benchmark_return_pct']:+.2f}%"),
                            _kv("Value added", f"{bm['value_added_pct']:+.2f} points"),
                            _kv("Fees effect", f"{bm['fees_effect_pct']:+.2f}%"),
                            _kv("Max drawdown (account / benchmark)", f"{bm.get('max_drawdown_pct')}% / {bm.get('benchmark_max_drawdown_pct')}%"),
                            html.Div(bm.get("reading", ""), style={"fontSize": "12px", "color": WHITE, "marginTop": "10px"})]))
    else:
        parts.append(_insufficient(bm, "Against the benchmark"))

    fees = review.get("fees") or {}
    if fees.get("status") == "ok":
        parts.append(_card([_section("Fees and costs"),
                            _kv("Total fees", _money(fees.get("total_fees"))),
                            _kv("Per trade", _money(fees.get("fees_per_trade"))),
                            _kv("Of traded value", f"{fees.get('fees_pct_of_traded_value')}%"),
                            _kv("Gross return per dollar of cost", fees.get("gross_return_per_dollar_of_cost")),
                            _kv("Cost as % of assets", fees.get("total_cost_pct_of_assets", "needs a holdings file"))]))
    else:
        parts.append(_insufficient(fees, "Fees and costs"))

    cash = review.get("cash") or {}
    parts.append(_card([_section("Cash"), html.Div(cash["reading"], style={"fontSize": "12px", "color": WHITE})])
                 if cash.get("status") == "ok" else _insufficient(cash, "Cash"))

    tax = review.get("tax_lots") or {}
    if tax.get("status") == "ok":
        parts.append(_card([_section("Tax-lot mix"),
                            _kv("Short-term result", _money(tax["short_term_pnl"])),
                            _kv("Long-term result", _money(tax["long_term_pnl"])),
                            html.Div(tax.get("note", ""), style={"fontSize": "11px", "color": WHITE, "marginTop": "6px"})]))
    else:
        parts.append(_insufficient(tax, "Tax-lot mix"))

    # Russell 1000
    r = review.get("russell_1000") or {}
    if r.get("status") == "ok":
        counts = r.get("alignment_counts") or {}
        rows = [html.Tr([html.Th(h, style={"textAlign": "left", "fontSize": "10px", "color": WHITE, "padding": "4px 8px"})
                         for h in ("Date", "Symbol", "Side", "Sector", "Sigmalytic reading that day", "Setup", "Trade was")])]
        for t in reversed(r.get("trades", [])):
            rd = t.get("sigmalytic_reading") or {}
            al = t.get("alignment", "not read")
            col = TEAL_DIM if al == "with the setup" else RED_DIM if al == "against the setup" else WHITE
            cells = [str(t.get("date", ""))[:10], t.get("symbol"), t.get("side"), t.get("sector"),
                     f"{rd.get('wyckoff_verdict', '—')} / {rd.get('wyckoff_phase', '—')}" if rd else "—",
                     f"{rd.get('setup_side')} {rd.get('setup_grade')}" if rd else "—", al]
            rows.append(html.Tr([html.Td(str(c), style={"fontSize": "11px", "padding": "4px 8px",
                                                         "color": col if i == 6 else WHITE}) for i, c in enumerate(cells)]))
        summary = (f"{r['russell_1000_trades']} of {r['all_trades']} buys and sells are Russell 1000 stocks "
                   f"({_pct(r['share_of_trades'], 0)}). ")
        if counts:
            summary += (f"With a confirmed setup: {counts.get('with the setup', 0)}. "
                        f"Against it: {counts.get('against the setup', 0)}. "
                        f"No confirmed setup: {counts.get('no confirmed setup', 0)}. "
                        f"Not read: {counts.get('not read', 0)}.")
        parts.append(_card([_section("Russell 1000 trades read as of the trade date"),
                            html.Div(summary, style={"fontSize": "12px", "color": WHITE, "marginBottom": "10px"}),
                            html.Div(html.Table(rows, style={"width": "100%", "borderCollapse": "collapse"}),
                                     style={"overflowX": "auto"}),
                            html.Div("Each reading uses only price history up to that date. The 60 most recent index trades are shown.",
                                     style={"fontSize": "10px", "color": WHITE, "marginTop": "8px"})]))
    else:
        parts.append(_insufficient(r, "Russell 1000 trades"))

    return html.Div(parts)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def _vault_card(slot: int, vault: Dict[str, Any]) -> html.Div:
    inp = {"background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}", "borderRadius": "8px",
           "color": WHITE, "fontSize": "12px", "padding": "8px 10px", "width": "100%", "marginBottom": "6px"}
    btn = {"background": "rgba(52,211,153,.12)", "border": "1px solid rgba(52,211,153,.35)", "borderRadius": "8px",
           "color": TEAL_DIM, "fontSize": "12px", "fontWeight": "700", "padding": "8px 12px", "cursor": "pointer"}
    return html.Div([
        html.Div([html.Div(f"Vault {slot}", style={"fontSize": "10px", "fontWeight": "800", "color": WHITE,
                                                    "textTransform": "uppercase", "letterSpacing": ".1em"}),
                  html.Div(id={"type": "bbi-grade", "slot": slot}, children=_grade_badge("N/A", 34))],
                 style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "8px"}),
        dcc.Input(id={"type": "bbi-name", "slot": slot}, type="text", placeholder="Account name (e.g. Schwab IRA)",
                  value=vault.get("name", ""), debounce=False, style=inp, maxLength=60),
        dcc.Input(id={"type": "bbi-broker", "slot": slot}, type="text", placeholder="Broker or adviser",
                  value=vault.get("broker", ""), style=inp, maxLength=60),
        html.Button("Save labels", id={"type": "bbi-save", "slot": slot}, n_clicks=0, style=btn),
        html.Span(id={"type": "bbi-save-msg", "slot": slot}, style={"fontSize": "11px", "color": TEAL_DIM, "marginLeft": "8px"}),
        html.Hr(style={"borderColor": BORDER, "margin": "12px 0"}),
        dcc.RadioItems(id={"type": "bbi-kind", "slot": slot}, value="trades",
                       options=[{"label": " Transactions (buys and sells)", "value": "trades"},
                                {"label": " Holdings (positions and cash)", "value": "positions"}],
                       style={"fontSize": "12px", "color": WHITE, "marginBottom": "8px"},
                       labelStyle={"display": "block", "color": WHITE, "marginBottom": "4px"}),
        dcc.Upload(id={"type": "bbi-upload", "slot": slot}, accept=".csv", multiple=False,
                   children=html.Div("Drop a statement CSV here or click to browse",
                                     style={"fontSize": "12px", "color": WHITE, "textAlign": "center", "padding": "14px"}),
                   style={"border": f"2px dashed {BORDER}", "borderRadius": "12px", "cursor": "pointer"}),
        dcc.Loading(html.Div(id={"type": "bbi-status", "slot": slot},
                             style={"fontSize": "11px", "color": TEAL_DIM, "minHeight": "18px", "marginTop": "6px"}),
                    type="dot", color=TEAL_DIM),
        html.Div(id={"type": "bbi-count", "slot": slot}, style={"fontSize": "11px", "color": WHITE, "margin": "6px 0"}),
        html.Div([
            html.Button("View review", id={"type": "bbi-view", "slot": slot}, n_clicks=0, style=btn),
            dcc.ConfirmDialogProvider(children=html.Button("Empty vault", n_clicks=0, style={**btn, "color": RED_DIM,
                                      "border": "1px solid rgba(248,113,113,.35)", "background": "rgba(248,113,113,.08)",
                                      "marginLeft": "8px"}),
                                      id={"type": "bbi-clear", "slot": slot},
                                      message=f"Delete every statement in vault {slot}? This cannot be undone."),
        ], style={"display": "flex"}),
    ], style={"background": NAVY_CARD, "border": f"1px solid {BORDER}", "borderRadius": "16px", "padding": "16px",
              "flex": "1 1 230px", "minWidth": "230px", "maxWidth": "340px"})


def build_broker_bi_tab(session: Optional[dict] = None) -> html.Div:
    vaults = {}
    note = None
    try:
        r = _rq.get(f"{BACKEND_HTTP}/api/broker-vaults", headers=_headers(session), timeout=15)
        if r.status_code == 403:
            note = "Sign in to use broker vaults. The demo account cannot store statements."
        elif r.ok:
            vaults = {v["slot"]: v for v in r.json().get("vaults", [])}
        elif r.status_code == 503:
            note = "Broker vault storage is not configured on this server yet."
        else:
            note = f"Broker vaults could not be loaded (HTTP {r.status_code})."
    except Exception:
        note = "Broker vaults could not be reached. Try again in a moment."

    return html.Div([
        _card([
            html.Div("Broker Behavioural Intelligence", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE}),
            html.Div("Grade a broker or adviser the same way Sigmalytic grades you. Each vault holds the statements of one "
                     "account. Upload transaction CSVs to grade how the account was traded, and a holdings CSV to add "
                     "portfolio health, cash and benchmark comparison. Grades run from A to F. Sections a statement "
                     "cannot support say so instead of guessing.",
                     style={"fontSize": "12px", "color": WHITE, "marginTop": "6px"}),
        ]),
        _note(note) if note else html.Div(),
        html.Div([_vault_card(n, vaults.get(n, {})) for n in SLOTS],
                 style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "16px"}),
        dcc.Interval(id="bbi-load", interval=300, n_intervals=0, max_intervals=1),
        dcc.Loading(html.Div(id="bbi-review"), type="dot", color=TEAL_DIM),
    ])


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_broker_bi_callbacks(app) -> None:
    @app.callback(
        Output({"type": "bbi-save-msg", "slot": MATCH}, "children"),
        Input({"type": "bbi-save", "slot": MATCH}, "n_clicks"),
        State({"type": "bbi-name", "slot": MATCH}, "value"),
        State({"type": "bbi-broker", "slot": MATCH}, "value"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def save_labels(n, name, broker, session):
        if not n:
            return no_update
        slot = callback_context.triggered_id["slot"]
        try:
            r = _rq.put(f"{BACKEND_HTTP}/api/broker-vaults/{slot}", headers=_headers(session), timeout=15,
                        json={"name": name or "", "broker": broker or ""})
            return "Saved" if r.ok else (r.json().get("detail", "Could not save") if r.headers.get("content-type", "").startswith("application/json") else "Could not save")
        except Exception:
            return "Could not reach the server"

    @app.callback(
        Output({"type": "bbi-status", "slot": MATCH}, "children"),
        Input({"type": "bbi-upload", "slot": MATCH}, "contents"),
        State({"type": "bbi-upload", "slot": MATCH}, "filename"),
        State({"type": "bbi-kind", "slot": MATCH}, "value"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def upload(contents, filename, kind, session):
        if not contents:
            return no_update
        slot = callback_context.triggered_id["slot"]
        try:
            raw = base64.b64decode(contents.split(",", 1)[1])
            r = _rq.post(f"{BACKEND_HTTP}/api/broker-vaults/{slot}/statements", headers=_headers(session), timeout=60,
                         files={"file": (filename or "statement.csv", raw, "text/csv")}, data={"kind": kind or "trades"})
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.ok:
                span = (f" ({body.get('period_start')} to {body.get('period_end')})" if body.get("period_start") else "")
                return f"Added {body.get('rows', 0)} rows from {filename}{span}"
            return f"Upload failed: {body.get('detail', r.text[:160])}"
        except Exception as exc:
            return f"Upload failed: {str(exc)[:160]}"

    @app.callback(
        Output({"type": "bbi-count", "slot": ALL}, "children"),
        Output({"type": "bbi-grade", "slot": ALL}, "children"),
        Input("bbi-load", "n_intervals"),
        Input({"type": "bbi-status", "slot": ALL}, "children"),
        Input({"type": "bbi-save-msg", "slot": ALL}, "children"),
        State("s-session", "data"),
    )
    def refresh_overview(_n, _status, _clear, session):
        empty = [""] * len(SLOTS), [_grade_badge("N/A", 34)] * len(SLOTS)
        try:
            r = _rq.get(f"{BACKEND_HTTP}/api/broker-vaults/compare", headers=_headers(session), timeout=30)
            if not r.ok:
                return empty
            vaults = {v["slot"]: v for v in r.json().get("vaults", [])}
        except Exception:
            return empty
        counts, grades = [], []
        for n in SLOTS:
            v = vaults.get(n, {})
            counts.append(f"{v.get('statements', 0)} statement(s) · {v.get('rows', 0)} rows")
            grades.append(_grade_badge(v.get("grade", "N/A"), 34))
        return counts, grades

    @app.callback(
        Output({"type": "bbi-save-msg", "slot": ALL}, "children", allow_duplicate=True),
        Input({"type": "bbi-clear", "slot": ALL}, "submit_n_clicks"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def clear_vault(clicks, session):
        trig = callback_context.triggered_id
        out = [no_update] * len(SLOTS)
        if not trig or not any(clicks or []):
            return out
        slot = trig["slot"]
        try:
            r = _rq.delete(f"{BACKEND_HTTP}/api/broker-vaults/{slot}", headers=_headers(session), timeout=20)
            out[SLOTS.index(slot)] = "Vault emptied" if r.ok else "Could not empty the vault"
        except Exception:
            out[SLOTS.index(slot)] = "Could not reach the server"
        return out

    @app.callback(
        Output("bbi-review", "children"),
        Input({"type": "bbi-view", "slot": ALL}, "n_clicks"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def show_review(clicks, session):
        trig = callback_context.triggered_id
        if not trig or not any(clicks or []):
            return no_update
        slot = trig["slot"]
        try:
            r = _rq.get(f"{BACKEND_HTTP}/api/broker-vaults/{slot}/review", headers=_headers(session), timeout=120)
        except Exception:
            return _note("The review could not be reached. Try again in a moment.", RED_DIM)
        if r.status_code == 404:
            return _note("This vault has no statements yet. Upload a CSV first.")
        if r.status_code == 403:
            return _note("Sign in to use broker vaults.", RED_DIM)
        if not r.ok:
            return _note(f"The review failed (HTTP {r.status_code}).", RED_DIM)
        return render_review(r.json().get("review") or {})
