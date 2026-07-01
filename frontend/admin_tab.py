# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
admin_tab.py - Sigmalytic Quant
Clean ASCII-safe Admin tab.

This file only controls the Admin tab.
"""

from __future__ import annotations

from datetime import datetime
from dash import html
import requests as _req

NAVY_CARD = "#111f35"
NAVY_MID = "#0f172a"
TEAL_DIM = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM = "#f87171"
YELLOW = "#f59e0b"
YELLOW_DIM = "#fde68a"
BLUE_DIM = "#93c5fd"
MUTED = "#f8fafc"
TEXT = "#f8fafc"
WHITE = "#f8fafc"
BORDER = "rgba(255,255,255,.08)"
BORDER_T = "rgba(45,143,111,.35)"
GOLD = "#F5C842"

ADMIN_EMAIL = "greg.kosmala@gmail.com"


def is_admin(session: dict) -> bool:
    return (session or {}).get("email", "") == ADMIN_EMAIL


def _card(children, sx=None):
    style = {
        "background": NAVY_CARD,
        "border": f"1px solid {BORDER}",
        "borderRadius": "16px",
        "padding": "20px",
        "boxShadow": "0 8px 32px rgba(0,0,0,.32)",
    }
    if sx:
        style.update(sx)
    return html.Div(children, style=style)


def _tile(label, value, color=WHITE, sub=None):
    return html.Div(
        [
            html.Div(
                label,
                style={
                    "fontSize": "10px",
                    "color": WHITE,
                    "fontWeight": "700",
                    "textTransform": "uppercase",
                    "letterSpacing": ".12em",
                    "marginBottom": "6px",
                },
            ),
            html.Div(
                value,
                style={
                    "fontSize": "22px",
                    "fontWeight": "900",
                    "color": color,
                    "lineHeight": "1",
                },
            ),
            html.Div(sub, style={"fontSize": "10px", "color": WHITE, "marginTop": "4px"}) if sub else html.Div(),
        ],
        style={
            "background": "rgba(0,0,0,.3)",
            "border": f"1px solid {BORDER}",
            "borderRadius": "12px",
            "padding": "14px 16px",
        },
    )


def _score_bar(value, width="100%"):
    try:
        pct = max(0, min(100, float(value)))
    except Exception:
        pct = 0
    color = TEAL_DIM if pct >= 70 else (YELLOW_DIM if pct >= 50 else RED_DIM)
    return html.Div(
        [
            html.Div(
                style={
                    "width": f"{pct}%",
                    "height": "100%",
                    "background": color,
                    "borderRadius": "999px",
                }
            )
        ],
        style={
            "height": "5px",
            "background": "rgba(255,255,255,.08)",
            "borderRadius": "999px",
            "overflow": "hidden",
            "width": width,
        },
    )


def _status_card(title, message, tone="yellow"):
    color = YELLOW_DIM if tone == "yellow" else (RED_DIM if tone == "red" else TEAL_DIM)
    return _card(
        [
            html.Div(title, style={"color": color, "fontSize": "14px", "fontWeight": "800"}),
            html.Div(message, style={"color": WHITE, "fontSize": "12px", "marginTop": "8px"}),
        ]
    )


def _get_json(url, headers=None, timeout=12):
    try:
        response = _req.get(url, headers=headers or {}, timeout=timeout)
        if response.ok:
            return response.json(), None
        return None, f"HTTP {response.status_code}"
    except Exception as exc:
        return None, str(exc)


def _load_admin_data(session, backend_url):
    token = (session or {}).get("access_token", "")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    report, report_error = _get_json(f"{backend_url}/api/admin/report", headers=headers, timeout=15)
    if report:
        return report, None, "admin_report"

    # Fallback: render a usable admin status page from live public endpoints.
    scores, scores_error = _get_json(f"{backend_url}/api/radar/scores", timeout=10)
    campaigns, campaigns_error = _get_json(f"{backend_url}/api/campaigns/summary", timeout=10)

    fallback = {
        "live_stats": {},
        "accuracy_stats": {},
        "snapshot_health": {
            "status": "Fallback status",
            "last_write": "",
            "recent_count": 0,
        },
        "top_scores": [],
        "anomalies": [],
        "narrative": "Admin report endpoint did not return data. Showing fallback live system status from radar/campaign endpoints.",
        "daily_grades": [],
        "regime_distribution": {},
        "generated_at": datetime.utcnow().isoformat(),
        "_admin_report_error": report_error,
        "_fallback_errors": {
            "radar_scores": scores_error,
            "campaign_summary": campaigns_error,
        },
    }

    if isinstance(scores, dict):
        items = scores.get("scores") or scores.get("symbols") or scores.get("data") or []
        if isinstance(items, list):
            fallback["top_scores"] = items[:20]
            fallback["live_stats"]["total_symbols"] = len(items)
            fallback["live_stats"]["armed"] = len([x for x in items if str(x.get("status", "")).upper() in {"ARMED", "SURVIVING", "CONFIRMED"}])
            fallback["live_stats"]["triggered"] = len([x for x in items if str(x.get("status", "")).upper() == "TRIGGERED"])
        fallback["accuracy_stats"]["total"] = len(fallback["top_scores"])

    if isinstance(campaigns, dict):
        fallback["live_stats"]["active_campaigns"] = campaigns.get("active_campaigns") or campaigns.get("total_campaigns") or campaigns.get("active") or 0
        states = campaigns.get("states") or campaigns.get("by_state") or {}
        if isinstance(states, dict):
            fallback["regime_distribution"] = states

    if not fallback["top_scores"] and not fallback["live_stats"].get("active_campaigns"):
        return None, f"Admin report failed: {report_error}; radar failed: {scores_error}; campaigns failed: {campaigns_error}", "none"

    return fallback, report_error, "fallback"


def _grade_color(grade):
    if not grade:
        return WHITE
    grade = str(grade).upper()
    if grade.startswith("A"):
        return TEAL_DIM
    if grade.startswith("B"):
        return BLUE_DIM
    if grade == "C":
        return YELLOW_DIM
    if grade == "F":
        return RED_DIM
    return WHITE


def _severity_color(severity):
    return {"ERROR": RED_DIM, "WARN": YELLOW_DIM, "INFO": BLUE_DIM}.get(str(severity).upper(), WHITE)


def _sym_row(symbol_data):
    score = symbol_data.get("composite_score", symbol_data.get("score", 0))
    try:
        score_float = float(score)
    except Exception:
        score_float = 0
    score_color = TEAL_DIM if score_float >= 70 else (YELLOW_DIM if score_float >= 50 else RED_DIM)
    change = symbol_data.get("change_pct", 0) or 0

    return html.Div(
        [
            html.Span(
                symbol_data.get("symbol", ""),
                style={"flex": "1", "fontWeight": "800", "fontSize": "13px", "color": WHITE, "fontFamily": "monospace"},
            ),
            html.Span(
                f"${symbol_data.get('price', 0):,.2f}",
                style={"flex": "1", "fontSize": "12px", "color": WHITE},
            ),
            html.Span(
                f"{change:+.2f}%",
                style={"flex": "1", "fontSize": "12px", "fontWeight": "700", "color": TEAL_DIM if change >= 0 else RED_DIM},
            ),
            html.Div(
                [
                    html.Span(f"{score_float:.0f}", style={"fontSize": "13px", "fontWeight": "900", "color": score_color}),
                    _score_bar(score_float, width="80px"),
                ],
                style={"flex": "1"},
            ),
            html.Span(
                str(symbol_data.get("status", "")),
                style={"flex": "1", "fontSize": "10px", "fontWeight": "700", "color": score_color},
            ),
            html.Span(
                str(symbol_data.get("regime", "")),
                style={"flex": "1", "fontSize": "10px", "color": WHITE},
            ),
        ],
        style={"display": "flex", "alignItems": "center", "gap": "12px", "padding": "10px 0", "borderBottom": f"1px solid {BORDER}"},
    )


def build_admin_tab(session: dict, backend_url: str) -> html.Div:
    if not is_admin(session):
        return html.Div(
            [
                html.Div("Admin Access Only", style={"fontSize": "18px", "fontWeight": "800", "color": WHITE}),
                html.Div("This page is only accessible to the system administrator.", style={"fontSize": "13px", "color": WHITE, "marginTop": "8px"}),
            ],
            style={"textAlign": "center", "padding": "80px 20px"},
        )

    data, load_error, source = _load_admin_data(session, backend_url)

    if not data:
        return _status_card("Could not load admin data", load_error or "No response from backend.", "red")

    live = data.get("live_stats", {})
    accuracy = data.get("accuracy_stats", {})
    snapshot = data.get("snapshot_health", {})
    top_scores = data.get("top_scores", [])
    anomalies = data.get("anomalies", [])
    narrative = data.get("narrative", "No narrative returned.")
    regimes = data.get("regime_distribution", {})
    generated_at = data.get("generated_at", "")

    try:
        generated_label = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00")).strftime("%b %d, %Y %I:%M %p UTC")
    except Exception:
        generated_label = str(generated_at)

    hit = accuracy.get("hit_rate", 0)
    conf = accuracy.get("conf_rate", accuracy.get("a_grade", 0))
    neutral = accuracy.get("neutral_rate", 0)
    miss = accuracy.get("miss_rate", 0)
    perf_total = accuracy.get("total", len(top_scores))

    header = _card(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("ADMIN PERFORMANCE MONITOR", style={"fontSize": "16px", "fontWeight": "900", "color": GOLD, "letterSpacing": ".08em"}),
                            html.Div(
                                "Private - Internal Use Only - Sigmalytic Quant Corporation",
                                style={"fontSize": "11px", "color": WHITE, "letterSpacing": ".06em"},
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Span(
                                "LIVE REPORT" if source == "admin_report" else "FALLBACK STATUS",
                                style={
                                    "fontSize": "10px",
                                    "fontWeight": "800",
                                    "color": TEAL_DIM if source == "admin_report" else YELLOW_DIM,
                                    "border": f"1px solid {BORDER_T}",
                                    "borderRadius": "999px",
                                    "padding": "4px 12px",
                                    "background": TEAL_GLOW,
                                },
                            ),
                            html.Div(
                                f"Generated: {generated_label}",
                                style={"fontSize": "10px", "color": WHITE, "marginTop": "4px", "textAlign": "right"},
                            ),
                        ]
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"},
            )
        ],
        sx={"borderColor": "rgba(245,200,66,.3)", "marginBottom": "16px"},
    )

    if source != "admin_report":
        warning = _status_card(
            "Admin report endpoint did not return data",
            "The tab is working. It is showing fallback live system status until /api/admin/report returns data.",
            "yellow",
        )
    else:
        warning = html.Div()

    tiles = _card(
        [
            html.Div(
                "CLOSED-LOOP PERFORMANCE AUDIT",
                style={"fontSize": "10px", "fontWeight": "900", "color": GOLD, "letterSpacing": ".2em", "textTransform": "uppercase", "marginBottom": "16px"},
            ),
            html.Div(
                [
                    _tile("CONF", f"{conf:.0f}%" if isinstance(conf, (int, float)) else str(conf), TEAL_DIM, "A-grade rate"),
                    _tile("HIT", f"{hit:.0f}%" if isinstance(hit, (int, float)) else str(hit), TEAL_DIM, "A + B rate"),
                    _tile("NEUTRAL", f"{neutral:.0f}%" if isinstance(neutral, (int, float)) else str(neutral), YELLOW_DIM, "C rate"),
                    _tile("MISS", f"{miss:.0f}%" if isinstance(miss, (int, float)) else str(miss), RED_DIM, "F rate"),
                    _tile("TOTAL", str(perf_total), GOLD, "records"),
                    _tile("SYMBOLS", str(live.get("total_symbols", live.get("active_campaigns", 0))), BLUE_DIM, "universe/campaigns"),
                    _tile("ARMED", str(live.get("armed", 0)), TEAL_DIM, "live now"),
                    _tile("TRIGGERED", str(live.get("triggered", 0)), BLUE_DIM, "live now"),
                ],
                style={"display": "grid", "gridTemplateColumns": "repeat(8,1fr)", "gap": "10px"},
            ),
        ],
        sx={"marginBottom": "16px", "borderColor": "rgba(245,200,66,.2)"},
    )

    snapshot_block = _card(
        [
            html.Div("SNAPSHOT / SYSTEM HEALTH", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE, "marginBottom": "4px"}),
            html.Div(
                [
                    html.Span("Status: ", style={"color": WHITE, "fontSize": "11px"}),
                    html.Span(str(snapshot.get("status", "Unknown")), style={"color": TEAL_DIM if source == "admin_report" else YELLOW_DIM, "fontWeight": "700", "fontSize": "11px"}),
                    html.Span(" - Last write: ", style={"color": WHITE, "fontSize": "11px", "marginLeft": "12px"}),
                    html.Span(str(snapshot.get("last_write", "-"))[:19] if snapshot.get("last_write") else "-", style={"color": WHITE, "fontSize": "11px"}),
                    html.Span(" - Writes in last 10 min: ", style={"color": WHITE, "fontSize": "11px", "marginLeft": "12px"}),
                    html.Span(str(snapshot.get("recent_count", 0)), style={"color": TEAL_DIM, "fontWeight": "700", "fontSize": "11px"}),
                ]
            ),
        ],
        sx={"marginBottom": "16px", "padding": "14px 20px"},
    )

    narrative_block = _card(
        [
            html.Div("REGIME NARRATIVE", style={"fontSize": "10px", "fontWeight": "900", "color": GOLD, "letterSpacing": ".2em", "marginBottom": "12px"}),
            html.Div(narrative, style={"fontSize": "14px", "color": WHITE, "lineHeight": "1.7", "fontStyle": "italic"}),
            html.Div(style={"height": "16px"}),
            html.Div("REGIME DISTRIBUTION", style={"fontSize": "10px", "fontWeight": "700", "color": WHITE, "letterSpacing": ".16em", "marginBottom": "8px"}),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(str(regime), style={"fontSize": "11px", "fontWeight": "700", "color": WHITE, "marginRight": "6px"}),
                            html.Span(str(count), style={"fontSize": "11px", "color": TEAL_DIM, "fontWeight": "900"}),
                        ],
                        style={
                            "background": "rgba(0,0,0,.3)",
                            "border": f"1px solid {BORDER}",
                            "borderRadius": "999px",
                            "padding": "4px 12px",
                            "display": "inline-flex",
                            "alignItems": "center",
                            "marginRight": "6px",
                            "marginBottom": "4px",
                        },
                    )
                    for regime, count in sorted(regimes.items(), key=lambda item: item[1], reverse=True)
                ],
                style={"display": "flex", "flexWrap": "wrap"},
            ),
        ],
        sx={"marginBottom": "16px"},
    )

    anomaly_rows = [
        html.Div(
            [
                html.Span(str(item.get("severity", "")), style={"fontSize": "9px", "fontWeight": "900", "color": _severity_color(item.get("severity", "INFO")), "marginRight": "10px", "minWidth": "40px"}),
                html.Span(str(item.get("symbol", "")), style={"fontSize": "11px", "fontWeight": "800", "color": WHITE, "fontFamily": "monospace", "marginRight": "10px", "minWidth": "60px"}),
                html.Span(str(item.get("message", "")), style={"fontSize": "12px", "color": WHITE}),
            ],
            style={"padding": "8px 0", "borderBottom": f"1px solid {BORDER}", "display": "flex", "alignItems": "center"},
        )
        for item in anomalies
    ]

    anomalies_block = _card(
        [
            html.Div(
                [
                    html.Div("ANOMALY FLAGS", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE}),
                    html.Div(f"{len(anomalies)} issues detected", style={"fontSize": "11px", "color": RED_DIM if anomalies else TEAL_DIM}),
                ],
                style={"display": "flex", "justifyContent": "space-between", "marginBottom": "12px"},
            ),
            html.Div(anomaly_rows if anomaly_rows else [html.Div("No anomalies detected - system running clean.", style={"color": TEAL_DIM, "fontSize": "13px", "padding": "12px 0"})]),
        ],
        sx={"marginBottom": "16px"},
    )

    table_header = html.Div(
        [
            html.Span("Symbol", style={"flex": "1", "fontSize": "9px", "color": WHITE, "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em"}),
            html.Span("Price", style={"flex": "1", "fontSize": "9px", "color": WHITE, "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em"}),
            html.Span("Chg%", style={"flex": "1", "fontSize": "9px", "color": WHITE, "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em"}),
            html.Span("Score", style={"flex": "1", "fontSize": "9px", "color": WHITE, "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em"}),
            html.Span("Status", style={"flex": "1", "fontSize": "9px", "color": WHITE, "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em"}),
            html.Span("Regime", style={"flex": "1", "fontSize": "9px", "color": WHITE, "fontWeight": "700", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        ],
        style={"display": "flex", "gap": "12px", "paddingBottom": "8px", "borderBottom": f"1px solid {BORDER}", "marginBottom": "4px"},
    )

    score_table = _card(
        [
            html.Div("TOP SCORES - COMPOSITE SCORE", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE, "marginBottom": "12px"}),
            table_header,
            html.Div([_sym_row(item) for item in top_scores] if top_scores else [html.Div("No score rows returned.", style={"color": WHITE, "fontSize": "13px", "padding": "12px 0"})]),
        ],
        sx={"marginBottom": "16px"},
    )

    return html.Div(
        [
            header,
            warning,
            tiles,
            snapshot_block,
            narrative_block,
            anomalies_block,
            score_table,
            html.Div(
                "SIGMALYTIC QUANT CORPORATION - PROPRIETARY & CONFIDENTIAL - INTERNAL USE ONLY",
                style={"textAlign": "center", "fontSize": "9px", "color": WHITE, "letterSpacing": ".2em", "paddingTop": "16px", "paddingBottom": "8px"},
            ),
        ]
    )
