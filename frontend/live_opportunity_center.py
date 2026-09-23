# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
frontend/live_opportunity_center.py
-----------------------------------
Live Opportunity Center for Sigmalytic V2.

Replaces the former campaign-centric Status Center as the subscriber-facing
opportunity workspace.  It deliberately reuses the existing, real Weis Radar
universe results and the existing on-demand /api/weis-radar/chart/{symbol}
endpoint.  No synthetic market rows or synthetic chart data are created here.

Current production scope:
- Latest completed full-universe Weis Radar scan is the opportunity source.
- The UI translates current radar events into BUILDING / ARMED / TRIGGERED.
- The backend follow-through engine persists TRIGGERED events and advances
  them to CONFIRMED / INVALIDATED only from later completed-bar evidence.
- Three chart windows are independently configurable for symbol and timeframe.
- Linked mode uses Chart 1's symbol across all three windows.
- Unlinked mode permits any three symbol/timeframe combinations.
- Presets: Alert View, Structure View, Long View, Compare Symbols, Custom.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests as _rq
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dash import ALL, Input, Output, State, callback_context, dcc, html, no_update
from watchlist_radar import build_watchlist_radar, register_watchlist_radar_callbacks

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Brand tokens ──────────────────────────────────────────────────────────────
NAVY = "#081827"
NAVY_CARD = "#0d1b2e"
NAVY_MID = "#0f172a"
NAVY_LIGHT = "#102a44"
TEAL = "#2dd4bf"
GREEN = "#34d399"
RED = "#f87171"
AMBER = "#f59e0b"
YELLOW = "#fde68a"
BLUE = "#60a5fa"
PURPLE = "#a78bfa"
WHITE = "#f8fafc"
MUTED = "#cbd5e1"
SUBTLE = "#94a3b8"
BORDER = "rgba(148,163,184,.20)"
BORDER_T = "rgba(45,212,191,.42)"

TIMEFRAME_OPTIONS = [
    {"label": "1H", "value": "1Hour"},
    {"label": "2H", "value": "2Hour"},
    {"label": "4H", "value": "4Hour"},
    {"label": "Daily", "value": "1Day"},
    {"label": "Weekly", "value": "1Week"},
]

TIMEFRAME_LABELS = {
    "1Hour": "1H",
    "2Hour": "2H",
    "4Hour": "4H",
    "1Day": "Daily",
    "1Week": "Weekly",
}

_CALLBACKS_REGISTERED = False


# ── Data helpers ──────────────────────────────────────────────────────────────
def _get_json(path: str, params=None, timeout: int = 12) -> dict:
    try:
        r = _rq.get(f"{BACKEND_HTTP}{path}", params=params, timeout=timeout)
        if not r.ok:
            return {"ok": False, "error": f"http_{r.status_code}"}
        data = r.json()
        return data if isinstance(data, dict) else {"ok": False, "error": "invalid_payload"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:240]}


def _clean_symbol(value) -> str:
    text = str(value or "").upper().strip()
    return "".join(ch for ch in text if ch.isalnum() or ch in {".", "-", "$"})[:16] or "AAPL"


def _signal_type(hit: dict) -> str:
    return str((hit or {}).get("type") or "").upper().strip()


def _signal_label(signal: str) -> str:
    s = str(signal or "").upper().strip()
    mapping = {
        "SPRING": "Spring / failed breakdown",
        "SPRING_BUILDING": "Spring developing",
        "UPTHRUST": "Upthrust / failed breakout",
        "UPTHRUST_BUILDING": "Upthrust developing",
        "BREAKOUT": "Structural breakout",
        "BREAKDOWN": "Structural breakdown",
        "SIGN_OF_STRENGTH": "Sign of Strength",
        "SIGN_OF_WEAKNESS": "Sign of Weakness",
        "CLIMAX_BUY": "Buying climax",
        "CLIMAX_SELL": "Selling climax",
        "NO_SUPPLY (ABSORPTION)": "Absorption / no supply",
        "NO_DEMAND (DISTRIBUTION)": "Distribution / no demand",
    }
    if s.startswith("3BAR_"):
        return "3-bar " + s.replace("3BAR_", "").replace("_", " ").lower()
    return mapping.get(s, s.replace("_", " ").title() or "Radar event")


def _direction_for_signal(signal: str) -> str:
    s = str(signal or "").upper()
    if (
        s.startswith("SPRING")
        or s == "BREAKOUT"
        or s == "SIGN_OF_STRENGTH"
        or s == "CLIMAX_SELL"
        or s.startswith("NO_SUPPLY")
        or "3BAR_BULL" in s
        or "3BAR_UP" in s
    ):
        return "Bullish"
    if (
        s.startswith("UPTHRUST")
        or s == "BREAKDOWN"
        or s == "SIGN_OF_WEAKNESS"
        or s == "CLIMAX_BUY"
        or s.startswith("NO_DEMAND")
        or "3BAR_BEAR" in s
        or "3BAR_DOWN" in s
    ):
        return "Bearish"
    return "Neutral"


def _stage_for_signal(signal: str) -> str:
    s = str(signal or "").upper()
    if s.endswith("_BUILDING"):
        return "BUILDING"
    if s in {"CLIMAX_BUY", "CLIMAX_SELL"} or s.startswith("NO_SUPPLY") or s.startswith("NO_DEMAND"):
        return "ARMED"
    if (
        s in {"SPRING", "UPTHRUST", "BREAKOUT", "BREAKDOWN", "SIGN_OF_STRENGTH", "SIGN_OF_WEAKNESS"}
        or s.startswith("3BAR_")
    ):
        return "TRIGGERED"
    return "BUILDING"


def _stage_priority(stage: str) -> int:
    # Active opportunities sort ahead of terminal lifecycle history.
    return {
        "TRIGGERED": 5,
        "ARMED": 4,
        "BUILDING": 3,
        "CONFIRMED": 2,
        "INVALIDATED": 1,
    }.get(stage, 0)


def _normalize_opportunities(payload: dict) -> list[dict]:
    config = payload.get("config") if isinstance(payload, dict) else {}
    config = config if isinstance(config, dict) else {}
    primary_tf = str(config.get("timeframe") or "1Day")
    by_symbol = {}

    lifecycle = payload.get("lifecycle") if isinstance(payload, dict) else {}
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    lifecycle_events = [
        event for event in (lifecycle.get("events") or [])
        if isinstance(event, dict)
        and str(event.get("stage") or "") in {"TRIGGERED", "CONFIRMED", "INVALIDATED"}
    ]

    lifecycle_by_symbol_signal = {}
    for event in lifecycle_events:
        symbol = _clean_symbol(event.get("symbol"))
        signal = str(event.get("signal_type") or "").upper()
        key = (symbol, str(event.get("timeframe") or primary_tf), signal)
        existing = lifecycle_by_symbol_signal.get(key)
        event_time = str(event.get("status_changed_at") or event.get("detected_at") or "")
        existing_time = str((existing or {}).get("status_changed_at") or (existing or {}).get("detected_at") or "")
        if existing is None or event_time > existing_time:
            lifecycle_by_symbol_signal[key] = event

    raw_rows = payload.get("results") if isinstance(payload, dict) else []
    for raw in raw_rows or []:
        if not isinstance(raw, dict):
            continue
        symbol = _clean_symbol(raw.get("symbol"))
        hits = [h for h in (raw.get("hits") or []) if isinstance(h, dict)]
        if not hits:
            continue

        classified = []
        for hit in hits:
            signal = _signal_type(hit)
            classified.append(
                (
                    _stage_priority(_stage_for_signal(signal)),
                    float(hit.get("score") or 0),
                    signal,
                    hit,
                )
            )
        classified.sort(reverse=True, key=lambda item: (item[0], item[1]))
        _, _, primary_signal, primary_hit = classified[0]
        stage = _stage_for_signal(primary_signal)
        direction = _direction_for_signal(primary_signal)
        life = lifecycle_by_symbol_signal.get((symbol, primary_tf, primary_signal))
        if life:
            stage = str(life.get("stage") or stage)
            direction = str(life.get("direction") or direction)

        scores = [float(h.get("score")) for h in hits if h.get("score") is not None]
        last_price = life.get("last_price") if life else primary_hit.get("price")
        if last_price is None:
            last_price = next((h.get("price") for h in hits if h.get("price") is not None), None)

        by_symbol[symbol] = {
            "symbol": symbol,
            "direction": direction,
            "stage": stage,
            "primary_tf": primary_tf,
            "event": str((life or {}).get("event") or _signal_label(primary_signal)),
            "signal_type": primary_signal,
            "detected": (life or {}).get("detected_at") or raw.get("last_bar_time") or payload.get("generated_at"),
            "price": last_price,
            "score": (life or {}).get("score") if life and life.get("score") is not None else (max(scores) if scores else None),
            "signal_count": len(hits),
            "hits": hits,
            "lifecycle": life,
        }

    # Keep terminal events visible after the original point-in-time signal
    # disappears from the latest Radar results. One row per symbol keeps Dash
    # pattern IDs unique and makes row selection deterministic.
    for event in lifecycle_events:
        symbol = _clean_symbol(event.get("symbol"))
        if not symbol:
            continue
        signal = str(event.get("signal_type") or "").upper()
        candidate = {
            "symbol": symbol,
            "direction": str(event.get("direction") or _direction_for_signal(signal)),
            "stage": str(event.get("stage") or "TRIGGERED"),
            "primary_tf": str(event.get("timeframe") or primary_tf),
            "event": str(event.get("event") or _signal_label(signal)),
            "signal_type": signal,
            "detected": event.get("detected_at"),
            "price": event.get("last_price") if event.get("last_price") is not None else event.get("trigger_price"),
            "score": event.get("score"),
            "signal_count": 1,
            "hits": [event.get("original_hit") or {"type": signal}],
            "lifecycle": event,
        }
        existing = by_symbol.get(symbol)
        if existing is None:
            by_symbol[symbol] = candidate
        else:
            existing_rank = (_stage_priority(existing.get("stage")), str(existing.get("detected") or ""))
            candidate_rank = (_stage_priority(candidate.get("stage")), str(candidate.get("detected") or ""))
            if candidate_rank > existing_rank:
                by_symbol[symbol] = candidate

    rows = list(by_symbol.values())
    rows.sort(
        key=lambda r: (
            -_stage_priority(r["stage"]),
            -(float(r["score"]) if r.get("score") is not None else -1),
            -int(r.get("signal_count") or 0),
            r["symbol"],
        )
    )
    return rows


def _load_opportunity_snapshot() -> dict:
    payload = _get_json("/api/weis-radar/results", timeout=8)
    rows = _normalize_opportunities(payload) if payload.get("ok") else []
    return {
        "rows": rows,
        "config": payload.get("config") if isinstance(payload.get("config"), dict) else {},
        "generated_at": payload.get("generated_at"),
        "scanned": payload.get("scanned"),
        "errors": payload.get("errors"),
        "ok": bool(payload.get("ok")),
        "error": payload.get("error"),
    }


def _context_triplet(primary_tf: str) -> tuple[str, str, str]:
    tf = str(primary_tf or "2Hour")
    if tf == "1Hour":
        return ("1Hour", "2Hour", "4Hour")
    if tf == "2Hour":
        return ("1Hour", "2Hour", "4Hour")
    if tf == "4Hour":
        return ("2Hour", "4Hour", "1Day")
    if tf == "1Day":
        return ("4Hour", "1Day", "1Week")
    if tf == "1Week":
        return ("4Hour", "1Day", "1Week")
    return ("2Hour", "4Hour", "1Day")


# ── UI helpers ────────────────────────────────────────────────────────────────
def _pill(text: str, color: str, bg=None):
    return html.Span(
        text,
        style={
            "display": "inline-block",
            "fontSize": "10px",
            "fontWeight": "900",
            "letterSpacing": ".04em",
            "padding": "4px 9px",
            "borderRadius": "999px",
            "color": color,
            "background": bg or f"{color}18",
            "border": f"1px solid {color}50",
            "whiteSpace": "nowrap",
        },
    )


def _stage_color(stage: str) -> str:
    return {
        "BUILDING": SUBTLE,
        "ARMED": BLUE,
        "TRIGGERED": AMBER,
        "CONFIRMED": GREEN,
        "INVALIDATED": RED,
    }.get(stage, SUBTLE)


def _direction_color(direction: str) -> str:
    return GREEN if direction == "Bullish" else RED if direction == "Bearish" else YELLOW


def _fmt_ts(value) -> str:
    if not value:
        return "—"
    text = str(value).replace("T", " ").replace("Z", " UTC")
    if "+" in text:
        text = text.split("+", 1)[0] + " UTC"
    if "." in text:
        text = text.split(".", 1)[0] + (" UTC" if "UTC" in text else "")
    return text[:24]


def _lifecycle_strip(rows: list[dict]):
    counts = {name: 0 for name in ["BUILDING", "ARMED", "TRIGGERED", "CONFIRMED", "INVALIDATED"]}
    for row in rows or []:
        stage = row.get("stage")
        if stage in counts:
            counts[stage] += 1

    cards = []
    descriptions = {
        "BUILDING": "Early development",
        "ARMED": "Conditions met",
        "TRIGGERED": "Event detected",
        "CONFIRMED": "Follow-through",
        "INVALIDATED": "Setup failed",
    }
    for stage in ["BUILDING", "ARMED", "TRIGGERED", "CONFIRMED", "INVALIDATED"]:
        color = _stage_color(stage)
        count_text = str(counts[stage])
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(stage, style={"fontSize": "11px", "fontWeight": "900", "color": color}),
                            html.Span(count_text, style={"fontSize": "17px", "fontWeight": "900", "color": WHITE}),
                        ],
                        style={"display": "flex", "justifyContent": "space-between", "gap": "10px"},
                    ),
                    html.Div(
                        descriptions[stage],
                        style={"fontSize": "9px", "color": MUTED, "marginTop": "4px"},
                    ),
                ],
                style={
                    "background": f"{color}0f",
                    "border": f"1px solid {color}55",
                    "borderRadius": "12px",
                    "padding": "10px 12px",
                    "flex": "1",
                    "minWidth": "120px",
                },
            )
        )
    return html.Div(cards, style={"display": "flex", "gap": "8px", "flexWrap": "wrap"})


def _opportunity_table(rows: list[dict]):
    header_style = {
        "fontSize": "9px",
        "fontWeight": "800",
        "color": SUBTLE,
        "textTransform": "uppercase",
        "letterSpacing": ".06em",
    }
    grid = "56px 84px 110px 76px minmax(180px,2fr) 130px 72px"
    header = html.Div(
        [
            html.Div("Symbol", style=header_style),
            html.Div("Direction", style=header_style),
            html.Div("Stage", style=header_style),
            html.Div("Primary TF", style=header_style),
            html.Div("Event", style=header_style),
            html.Div("Detected", style=header_style),
            html.Div("Signals", style=header_style),
        ],
        style={
            "display": "grid",
            "gridTemplateColumns": grid,
            "gap": "10px",
            "padding": "0 12px 9px",
            "borderBottom": f"1px solid {BORDER}",
            "alignItems": "center",
        },
    )

    if not rows:
        return html.Div(
            [
                header,
                html.Div(
                    "No current opportunities were returned by the latest completed Weis Radar universe scan.",
                    style={"padding": "24px 12px", "color": MUTED, "fontSize": "12px"},
                ),
            ]
        )

    body = []
    for row in rows[:60]:
        stage = row["stage"]
        direction = row["direction"]
        body.append(
            html.Div(
                [
                    html.Div(row["symbol"], style={"fontWeight": "900", "color": WHITE, "fontFamily": "DM Mono, monospace"}),
                    html.Div(direction, style={"fontSize": "11px", "fontWeight": "800", "color": _direction_color(direction)}),
                    html.Div(_pill(stage, _stage_color(stage))),
                    html.Div(TIMEFRAME_LABELS.get(row["primary_tf"], row["primary_tf"]), style={"fontSize": "11px", "color": WHITE}),
                    html.Div(row["event"], style={"fontSize": "11px", "color": WHITE, "overflow": "hidden", "textOverflow": "ellipsis"}),
                    html.Div(_fmt_ts(row.get("detected")), style={"fontSize": "10px", "color": MUTED}),
                    html.Div(str(row.get("signal_count") or 0), style={"fontSize": "11px", "fontWeight": "800", "color": WHITE}),
                ],
                id={"type": "loc-opportunity-row", "symbol": row["symbol"]},
                n_clicks=0,
                title=f"Open {row['symbol']} across the three-chart workspace",
                style={
                    "display": "grid",
                    "gridTemplateColumns": grid,
                    "gap": "10px",
                    "alignItems": "center",
                    "padding": "10px 12px",
                    "borderBottom": f"1px solid {BORDER}",
                    "cursor": "pointer",
                    "background": "rgba(15,23,42,.28)",
                },
            )
        )
    return html.Div([header, *body], style={"maxHeight": "480px", "overflowY": "auto"})


def _scan_meta(snapshot: dict):
    if not snapshot.get("ok"):
        return html.Span(
            f"Radar snapshot unavailable: {snapshot.get('error') or 'unknown error'}",
            style={"color": RED, "fontSize": "11px"},
        )
    config = snapshot.get("config") or {}
    tf = TIMEFRAME_LABELS.get(str(config.get("timeframe") or ""), str(config.get("timeframe") or "—"))
    rows = snapshot.get("rows") or []
    scanned = snapshot.get("scanned")
    return html.Span(
        f"Latest completed universe scan · {scanned if scanned is not None else '—'} symbols scanned · "
        f"{len(rows)} symbols with current events · scan timeframe {tf} · {_fmt_ts(snapshot.get('generated_at'))}",
        style={"color": MUTED, "fontSize": "10px"},
    )


def _detail_panel(row: dict | None, config: dict | None = None):
    config = config or {}
    if not row:
        return html.Div(
            [
                html.Div("Select an opportunity", style={"fontSize": "18px", "fontWeight": "900", "color": WHITE}),
                html.Div(
                    "Click a universe event to load that symbol into the linked three-chart workspace.",
                    style={"fontSize": "12px", "color": MUTED, "lineHeight": "1.6", "marginTop": "8px"},
                ),
            ]
        )

    stage = row.get("stage", "BUILDING")
    direction = row.get("direction", "Neutral")
    color = _stage_color(stage)
    price = row.get("price")
    score = row.get("score")
    hit_labels = [_signal_label(_signal_type(h)) for h in (row.get("hits") or [])]
    if not hit_labels:
        hit_labels = [row.get("event") or "Radar event"]
    lifecycle = row.get("lifecycle") if isinstance(row.get("lifecycle"), dict) else {}

    if stage == "CONFIRMED":
        headline = "FOLLOW-THROUGH CONFIRMED"
        sub = "A later completed bar crossed the event's confirmation threshold."
    elif stage == "INVALIDATED":
        headline = "SETUP INVALIDATED"
        sub = "A later completed bar crossed the event's invalidation threshold."
    elif stage == "TRIGGERED":
        headline = "TRADE ABOUT TO HAPPEN"
        sub = "A material structural event has been detected. Watch for follow-through."
    elif stage == "ARMED":
        headline = "SETUP ARMED"
        sub = "Supporting conditions are present; a structural trigger has not been confirmed by this feed."
    else:
        headline = "OPPORTUNITY BUILDING"
        sub = "Early structural behavior is developing."

    email_on = bool(config.get("email_enabled"))
    sms_on = bool(config.get("sms_enabled"))

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(row.get("symbol", "—"), style={"fontSize": "24px", "fontWeight": "900", "color": WHITE}),
                            html.Div(
                                f"{direction} · {TIMEFRAME_LABELS.get(row.get('primary_tf'), row.get('primary_tf','—'))}",
                                style={"fontSize": "11px", "color": _direction_color(direction), "fontWeight": "800"},
                            ),
                        ]
                    ),
                    html.Div(
                        f"{float(price):,.2f}" if price is not None else "—",
                        style={"fontSize": "18px", "fontWeight": "900", "color": WHITE, "fontFamily": "DM Mono, monospace"},
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "gap": "12px", "alignItems": "start"},
            ),
            html.Div(
                [
                    html.Div(headline, style={"fontSize": "14px", "fontWeight": "900", "color": color}),
                    html.Div(sub, style={"fontSize": "11px", "color": MUTED, "marginTop": "4px", "lineHeight": "1.5"}),
                ],
                style={
                    "marginTop": "14px",
                    "padding": "12px",
                    "borderRadius": "12px",
                    "border": f"1px solid {color}55",
                    "background": f"{color}0f",
                },
            ),
            html.Div(
                [
                    html.Div("What changed?", style={"fontSize": "10px", "fontWeight": "900", "color": BLUE, "marginBottom": "5px"}),
                    html.Div(" · ".join(hit_labels), style={"fontSize": "11px", "color": WHITE, "lineHeight": "1.55"}),
                ],
                style={"padding": "14px 0", "borderBottom": f"1px solid {BORDER}"},
            ),
            html.Div(
                [
                    html.Div("Evidence", style={"fontSize": "10px", "fontWeight": "900", "color": TEAL, "marginBottom": "5px"}),
                    html.Div(
                        [
                            html.Span(f"Stage: {stage}", style={"marginRight": "12px"}),
                            html.Span(f"Signals: {row.get('signal_count') or 0}", style={"marginRight": "12px"}),
                            html.Span(f"Signal score: {score:.0f}" if score is not None else "Signal score: —"),
                        ],
                        style={"fontSize": "11px", "color": WHITE},
                    ),
                ],
                style={"padding": "14px 0", "borderBottom": f"1px solid {BORDER}"},
            ),
            html.Div(
                (
                    [
                        html.Div("Follow-through", style={"fontSize": "10px", "fontWeight": "900", "color": GREEN, "marginBottom": "7px"}),
                        html.Div(
                            lifecycle.get("reason") or "Trigger is being monitored on later completed bars.",
                            style={"fontSize": "10px", "color": WHITE, "lineHeight": "1.55", "marginBottom": "6px"},
                        ),
                        html.Div(
                            f"Confirmation: {lifecycle.get('confirmation_rule') or '—'}",
                            style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.55"},
                        ),
                        html.Div(
                            f"Invalidation: {lifecycle.get('invalidation_rule') or '—'}",
                            style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.55"},
                        ),
                        html.Div(
                            f"Later completed bars observed: {int(lifecycle.get('bars_observed_after_trigger') or 0)}",
                            style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.55"},
                        ),
                    ]
                    if lifecycle
                    else
                    [
                        html.Div("Follow-through", style={"fontSize": "10px", "fontWeight": "900", "color": GREEN, "marginBottom": "5px"}),
                        html.Div(
                            "BUILDING and ARMED conditions remain point-in-time Radar observations. "
                            "Once a structural trigger occurs, the backend lifecycle engine persists it and monitors later completed bars.",
                            style={"fontSize": "10px", "color": MUTED, "lineHeight": "1.55"},
                        ),
                    ]
                ),
                style={"padding": "14px 0", "borderBottom": f"1px solid {BORDER}"},
            ),
            html.Div(
                [
                    html.Div("Alert Delivery", style={"fontSize": "10px", "fontWeight": "900", "color": TEAL, "marginBottom": "8px"}),
                    html.Div(
                        [
                            _pill("IN-APP ON", GREEN),
                            _pill("EMAIL ON" if email_on else "EMAIL OFF", GREEN if email_on else SUBTLE),
                            _pill("SMS ON" if sms_on else "SMS OFF", GREEN if sms_on else SUBTLE),
                        ],
                        style={"display": "flex", "gap": "6px", "flexWrap": "wrap"},
                    ),
                ],
                style={"paddingTop": "14px"},
            ),
        ]
    )


def _dropdown_style():
    return {
        "width": "104px",
        "fontSize": "11px",
        "color": "#111827",
    }


def _symbol_input(component_id: str, value: str):
    return dcc.Input(
        id=component_id,
        type="text",
        value=value,
        debounce=True,
        maxLength=16,
        style={
            "width": "86px",
            "height": "34px",
            "borderRadius": "8px",
            "border": f"1px solid {BORDER_T}",
            "background": NAVY_MID,
            "color": WHITE,
            "fontFamily": "DM Mono, monospace",
            "fontSize": "12px",
            "fontWeight": "800",
            "padding": "0 9px",
        },
    )


def _chart_card(index: int, symbol: str, timeframe: str, linked: bool):
    linked_label_style = {
        "display": "block" if linked and index > 1 else "none",
        "color": TEAL,
        "fontSize": "10px",
        "fontWeight": "800",
        "padding": "9px 4px",
    }
    symbol_control_style = {"display": "none" if linked and index > 1 else "block"}
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                f"CHART {index}",
                                style={"fontSize": "9px", "color": SUBTLE, "fontWeight": "900", "letterSpacing": ".1em"},
                            ),
                            html.Div(
                                _symbol_input(f"loc-symbol-{index}", symbol),
                                id=f"loc-symbol-control-{index}",
                                style=symbol_control_style,
                            ),
                            html.Div(
                                "Linked to Chart 1",
                                id=f"loc-linked-label-{index}",
                                style=linked_label_style,
                            ) if index > 1 else html.Div(),
                        ],
                        style={"display": "flex", "gap": "8px", "alignItems": "center"},
                    ),
                    dcc.Dropdown(
                        id=f"loc-tf-{index}",
                        options=TIMEFRAME_OPTIONS,
                        value=timeframe,
                        clearable=False,
                        searchable=False,
                        style=_dropdown_style(),
                    ),
                ],
                style={"display": "flex", "justifyContent": "space-between", "gap": "8px", "alignItems": "center", "marginBottom": "8px"},
            ),
            dcc.Loading(
                dcc.Graph(
                    id=f"loc-chart-{index}",
                    figure=_empty_figure("Waiting for chart data"),
                    config={"displaylogo": False, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
                    style={"height": "330px"},
                ),
                type="dot",
            ),
        ],
        style={
            "background": NAVY_CARD,
            "border": f"1px solid {BORDER}",
            "borderRadius": "14px",
            "padding": "12px",
            "minWidth": "0",
            "flex": "1",
        },
    )


def _empty_figure(message: str):
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=NAVY_CARD,
        plot_bgcolor=NAVY_CARD,
        font={"color": WHITE, "family": "DM Sans"},
        margin={"l": 20, "r": 20, "t": 36, "b": 20},
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[
            {
                "text": message,
                "x": 0.5,
                "y": 0.5,
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {"color": MUTED, "size": 12},
            }
        ],
    )
    return fig


def _chart_limit_for_tf(tf: str) -> int:
    return {"1Hour": 180, "2Hour": 180, "4Hour": 180, "1Day": 180, "1Week": 156}.get(tf, 180)


def _fetch_chart_payload(symbol: str, timeframe: str) -> dict:
    clean = _clean_symbol(symbol)
    return _get_json(
        f"/api/weis-radar/chart/{clean}",
        params={"timeframe": timeframe, "limit": _chart_limit_for_tf(timeframe)},
        timeout=20,
    )


def _build_chart_figure(payload: dict, symbol: str, timeframe: str, primary_tf: str):
    if not payload.get("ok"):
        return _empty_figure(f"{_clean_symbol(symbol)} {TIMEFRAME_LABELS.get(timeframe, timeframe)} · {payload.get('error') or 'data unavailable'}")

    bars = [b for b in (payload.get("bars") or []) if isinstance(b, dict)]
    if not bars:
        return _empty_figure(f"{_clean_symbol(symbol)} · no bars returned")

    x = [b.get("date") for b in bars]
    opens = [b.get("open") for b in bars]
    highs = [b.get("high") for b in bars]
    lows = [b.get("low") for b in bars]
    closes = [b.get("close") for b in bars]
    vols = [b.get("volume") or 0 for b in bars]
    vol_colors = [GREEN if float(c or 0) >= float(o or 0) else RED for o, c in zip(opens, closes)]

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.76, 0.24],
    )
    fig.add_trace(
        go.Candlestick(
            x=x,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="Price",
            increasing={"line": {"color": GREEN}, "fillcolor": GREEN},
            decreasing={"line": {"color": RED}, "fillcolor": RED},
        ),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Bar(x=x, y=vols, name="Volume", marker_color=vol_colors, opacity=0.62),
        row=2,
        col=1,
    )

    for key, label, color in [
        ("call_wall", "CALL WALL", GREEN),
        ("gamma_flip", "GAMMA FLIP", AMBER),
        ("put_wall", "PUT WALL", RED),
    ]:
        value = payload.get(key)
        if value is None:
            continue
        try:
            value = float(value)
        except Exception:
            continue
        fig.add_hline(
            y=value,
            line_color=color,
            line_dash="dash",
            line_width=1.4,
            opacity=0.75,
            annotation_text=f"{label} {value:,.2f}",
            annotation_position="top left",
            row=1,
            col=1,
        )

    hits = [h for h in (payload.get("hits") or []) if isinstance(h, dict)]
    if hits:
        labels = ", ".join(_signal_label(_signal_type(h)) for h in hits[:3])
        try:
            last_x = x[-1]
            last_y = float(closes[-1])
            fig.add_annotation(
                x=last_x,
                y=last_y,
                text=labels,
                showarrow=True,
                arrowhead=2,
                ax=-35,
                ay=-42,
                bgcolor="rgba(8,24,39,.90)",
                bordercolor=AMBER,
                font={"color": WHITE, "size": 9},
                row=1,
                col=1,
            )
        except Exception:
            pass

    is_primary = timeframe == primary_tf
    title_suffix = " · PRIMARY ALERT TIMEFRAME" if is_primary else ""
    fig.update_layout(
        title={
            "text": f"{_clean_symbol(symbol)} · {TIMEFRAME_LABELS.get(timeframe, timeframe)}{title_suffix}",
            "x": 0.01,
            "xanchor": "left",
            "font": {"size": 12, "color": AMBER if is_primary else WHITE},
        },
        paper_bgcolor=NAVY_CARD,
        plot_bgcolor=NAVY,
        font={"color": WHITE, "family": "DM Sans", "size": 10},
        margin={"l": 42, "r": 16, "t": 40, "b": 24},
        showlegend=False,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        xaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,.05)", "showticklabels": False},
        xaxis2={"showgrid": True, "gridcolor": "rgba(255,255,255,.05)", "tickfont": {"size": 8, "color": SUBTLE}},
        yaxis={"showgrid": True, "gridcolor": "rgba(255,255,255,.06)", "side": "right", "tickfont": {"size": 8}},
        yaxis2={"showgrid": True, "gridcolor": "rgba(255,255,255,.04)", "side": "right", "tickfont": {"size": 8}},
    )
    return fig


# ── Main layout ───────────────────────────────────────────────────────────────
def build_live_opportunity_center(session=None):
    snapshot = _load_opportunity_snapshot()
    rows = snapshot.get("rows") or []
    selected = rows[0] if rows else None
    master_symbol = selected.get("symbol") if selected else "AAPL"
    primary_tf = selected.get("primary_tf") if selected else str((snapshot.get("config") or {}).get("timeframe") or "2Hour")
    tf1, tf2, tf3 = _context_triplet(primary_tf)

    control_button = {
        "height": "34px",
        "borderRadius": "9px",
        "border": f"1px solid {BORDER}",
        "background": NAVY_MID,
        "color": WHITE,
        "fontSize": "10px",
        "fontWeight": "800",
        "padding": "0 11px",
        "cursor": "pointer",
    }

    return html.Div(
        [
            dcc.Store(id="loc-opportunity-store", data=snapshot),
            dcc.Store(id="loc-selected-opportunity", data=selected),
            dcc.Store(id="loc-link-mode", data=True),
            dcc.Store(id="loc-primary-tf", data=primary_tf),

            # Header
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Live Opportunity Center", style={"fontSize": "25px", "fontWeight": "900", "color": WHITE}),
                            html.Div(
                                "Universe-wide market-structure alerts with a linked multi-timeframe workspace.",
                                style={"fontSize": "12px", "color": MUTED, "marginTop": "3px"},
                            ),
                        ]
                    ),
                    html.Button("Refresh Opportunities", id="loc-refresh", n_clicks=0, style={**control_button, "borderColor": BORDER_T, "color": TEAL}),
                ],
                style={"display": "flex", "justifyContent": "space-between", "gap": "16px", "alignItems": "center", "marginBottom": "10px"},
            ),
            html.Div(_scan_meta(snapshot), id="loc-scan-meta", style={"marginBottom": "14px"}),

            # Lifecycle
            html.Div(_lifecycle_strip(rows), id="loc-lifecycle-strip", style={"marginBottom": "14px"}),

            # Subscriber Watchlist Radar
            build_watchlist_radar(snapshot, master_symbol),

            # Universe list + detail
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Div("Universe Opportunities", style={"fontSize": "13px", "fontWeight": "900", "color": WHITE}),
                                    html.Div(
                                        "Click any row to load that symbol into the three-chart workspace.",
                                        style={"fontSize": "10px", "color": MUTED},
                                    ),
                                ],
                                style={"padding": "14px 14px 10px"},
                            ),
                            html.Div(_opportunity_table(rows), id="loc-opportunity-table"),
                        ],
                        style={
                            "background": NAVY_CARD,
                            "border": f"1px solid {BORDER}",
                            "borderRadius": "14px",
                            "overflow": "hidden",
                            "minWidth": "0",
                            "flex": "2.2",
                        },
                    ),
                    html.Div(
                        _detail_panel(selected, snapshot.get("config")),
                        id="loc-detail-panel",
                        style={
                            "background": NAVY_CARD,
                            "border": f"1px solid {BORDER_T}",
                            "borderRadius": "14px",
                            "padding": "16px",
                            "minWidth": "300px",
                            "flex": "1",
                        },
                    ),
                ],
                style={"display": "flex", "gap": "14px", "alignItems": "stretch", "marginBottom": "14px", "flexWrap": "wrap"},
            ),

            # Workspace controls
            html.Div(
                [
                    html.Div(
                        [
                            html.Div("Three-Chart Workspace", style={"fontSize": "14px", "fontWeight": "900", "color": WHITE}),
                            html.Div(
                                "One symbol / three timeframes, three symbols / one timeframe, or any mix-and-match combination.",
                                style={"fontSize": "10px", "color": MUTED, "marginTop": "2px"},
                            ),
                        ]
                    ),
                    html.Div(
                        [
                            html.Button("Alert View", id="loc-preset-alert", n_clicks=0, style=control_button),
                            html.Button("Structure View", id="loc-preset-structure", n_clicks=0, style=control_button),
                            html.Button("Long View", id="loc-preset-long", n_clicks=0, style=control_button),
                            html.Button("Compare Symbols", id="loc-preset-compare", n_clicks=0, style=control_button),
                            html.Button("Custom", id="loc-preset-custom", n_clicks=0, style=control_button),
                            html.Button(
                                "LINKED",
                                id="loc-link-toggle",
                                n_clicks=0,
                                style={**control_button, "borderColor": BORDER_T, "background": "rgba(45,212,191,.12)", "color": TEAL},
                            ),
                        ],
                        style={"display": "flex", "gap": "7px", "flexWrap": "wrap", "justifyContent": "flex-end"},
                    ),
                ],
                style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "gap": "12px",
                    "alignItems": "center",
                    "marginBottom": "10px",
                    "padding": "12px 14px",
                    "background": NAVY_CARD,
                    "border": f"1px solid {BORDER}",
                    "borderRadius": "14px",
                    "flexWrap": "wrap",
                },
            ),

            html.Div(
                [
                    _chart_card(1, master_symbol, tf1, True),
                    _chart_card(2, master_symbol, tf2, True),
                    _chart_card(3, master_symbol, tf3, True),
                ],
                style={"display": "flex", "gap": "12px", "alignItems": "stretch", "flexWrap": "wrap"},
            ),

            html.Div(
                "Research and market-structure intelligence only. The Live Opportunity Center surfaces evidence; the subscriber makes the trading decision.",
                style={"fontSize": "9px", "color": SUBTLE, "textAlign": "center", "marginTop": "12px"},
            ),
        ],
        style={"width": "100%", "color": WHITE},
    )


# Backward-compatible name so the app router can transition without a wide edit.
build_status_center = build_live_opportunity_center


# ── Callbacks ─────────────────────────────────────────────────────────────────
def register_live_opportunity_center_callbacks(app):
    global _CALLBACKS_REGISTERED
    if _CALLBACKS_REGISTERED:
        return
    _CALLBACKS_REGISTERED = True

    # Register the subscriber Watchlist Radar callbacks once against the same Dash app.
    register_watchlist_radar_callbacks(app)

    @app.callback(
        Output("loc-opportunity-store", "data"),
        Output("loc-opportunity-table", "children"),
        Output("loc-scan-meta", "children"),
        Output("loc-lifecycle-strip", "children"),
        Input("loc-refresh", "n_clicks"),
        prevent_initial_call=True,
    )
    def _refresh_opportunities(_):
        snapshot = _load_opportunity_snapshot()
        rows = snapshot.get("rows") or []
        return snapshot, _opportunity_table(rows), _scan_meta(snapshot), _lifecycle_strip(rows)

    @app.callback(
        Output("loc-link-mode", "data"),
        Output("loc-symbol-1", "value"),
        Output("loc-symbol-2", "value"),
        Output("loc-symbol-3", "value"),
        Output("loc-tf-1", "value"),
        Output("loc-tf-2", "value"),
        Output("loc-tf-3", "value"),
        Output("loc-primary-tf", "data"),
        Output("loc-selected-opportunity", "data"),
        Input("loc-link-toggle", "n_clicks"),
        Input("loc-preset-alert", "n_clicks"),
        Input("loc-preset-structure", "n_clicks"),
        Input("loc-preset-long", "n_clicks"),
        Input("loc-preset-compare", "n_clicks"),
        Input("loc-preset-custom", "n_clicks"),
        Input({"type": "loc-opportunity-row", "symbol": ALL}, "n_clicks"),
        State("loc-opportunity-store", "data"),
        State("loc-link-mode", "data"),
        State("loc-symbol-1", "value"),
        State("loc-symbol-2", "value"),
        State("loc-symbol-3", "value"),
        State("loc-tf-1", "value"),
        State("loc-tf-2", "value"),
        State("loc-tf-3", "value"),
        State("loc-primary-tf", "data"),
        State("loc-selected-opportunity", "data"),
        prevent_initial_call=True,
    )
    def _workspace_controls(
        _link_clicks,
        _alert_clicks,
        _structure_clicks,
        _long_clicks,
        _compare_clicks,
        _custom_clicks,
        _row_clicks,
        snapshot,
        linked,
        s1,
        s2,
        s3,
        tf1,
        tf2,
        tf3,
        primary_tf,
        selected,
    ):
        trigger = callback_context.triggered_id
        current = [linked, s1, s2, s3, tf1, tf2, tf3, primary_tf, selected]

        if isinstance(trigger, dict) and trigger.get("type") == "loc-opportunity-row":
            symbol = _clean_symbol(trigger.get("symbol"))
            row = next((r for r in ((snapshot or {}).get("rows") or []) if r.get("symbol") == symbol), None)
            event_tf = str((row or {}).get("primary_tf") or ((snapshot or {}).get("config") or {}).get("timeframe") or "2Hour")
            a, b, c = _context_triplet(event_tf)
            return True, symbol, symbol, symbol, a, b, c, event_tf, row

        if trigger == "loc-link-toggle":
            return (not bool(linked), s1, s2, s3, tf1, tf2, tf3, primary_tf, selected)

        if trigger == "loc-preset-alert":
            return True, s1, s1, s1, "1Hour", "2Hour", "4Hour", "2Hour", selected

        if trigger == "loc-preset-structure":
            return True, s1, s1, s1, "2Hour", "4Hour", "1Day", "4Hour", selected

        if trigger == "loc-preset-long":
            return True, s1, s1, s1, "4Hour", "1Day", "1Week", "1Day", selected

        if trigger == "loc-preset-compare":
            base_tf = primary_tf if primary_tf in TIMEFRAME_LABELS else "2Hour"
            return False, s1, s2, s3, base_tf, base_tf, base_tf, base_tf, selected

        if trigger == "loc-preset-custom":
            return False, s1, s2, s3, tf1, tf2, tf3, primary_tf, selected

        return tuple(no_update for _ in current)

    @app.callback(
        Output("loc-symbol-2", "value", allow_duplicate=True),
        Output("loc-symbol-3", "value", allow_duplicate=True),
        Input("loc-symbol-1", "value"),
        State("loc-link-mode", "data"),
        prevent_initial_call=True,
    )
    def _sync_linked_symbols(master_symbol, linked):
        if not linked:
            return no_update, no_update
        clean = _clean_symbol(master_symbol)
        return clean, clean

    @app.callback(
        Output("loc-link-toggle", "children"),
        Output("loc-link-toggle", "style"),
        Output("loc-symbol-control-2", "style"),
        Output("loc-symbol-control-3", "style"),
        Output("loc-linked-label-2", "style"),
        Output("loc-linked-label-3", "style"),
        Input("loc-link-mode", "data"),
    )
    def _link_mode_ui(linked):
        base_button = {
            "height": "34px",
            "borderRadius": "9px",
            "fontSize": "10px",
            "fontWeight": "800",
            "padding": "0 11px",
            "cursor": "pointer",
        }
        if linked:
            button = {**base_button, "border": f"1px solid {BORDER_T}", "background": "rgba(45,212,191,.12)", "color": TEAL}
            symbol_style = {"display": "none"}
            linked_style = {"display": "block", "color": TEAL, "fontSize": "10px", "fontWeight": "800", "padding": "9px 4px"}
            return "LINKED", button, symbol_style, symbol_style, linked_style, linked_style
        button = {**base_button, "border": f"1px solid {BORDER}", "background": NAVY_MID, "color": WHITE}
        symbol_style = {"display": "block"}
        linked_style = {"display": "none"}
        return "UNLINKED", button, symbol_style, symbol_style, linked_style, linked_style

    @app.callback(
        Output("loc-detail-panel", "children"),
        Input("loc-selected-opportunity", "data"),
        State("loc-opportunity-store", "data"),
    )
    def _render_detail(selected, snapshot):
        return _detail_panel(selected, (snapshot or {}).get("config") or {})

    @app.callback(
        Output("loc-chart-1", "figure"),
        Output("loc-chart-2", "figure"),
        Output("loc-chart-3", "figure"),
        Input("loc-link-mode", "data"),
        Input("loc-symbol-1", "value"),
        Input("loc-symbol-2", "value"),
        Input("loc-symbol-3", "value"),
        Input("loc-tf-1", "value"),
        Input("loc-tf-2", "value"),
        Input("loc-tf-3", "value"),
        Input("loc-primary-tf", "data"),
    )
    def _update_three_charts(linked, s1, s2, s3, tf1, tf2, tf3, primary_tf):
        master = _clean_symbol(s1)
        symbols = [master, master if linked else _clean_symbol(s2), master if linked else _clean_symbol(s3)]
        timeframes = [
            tf1 if tf1 in TIMEFRAME_LABELS else "1Hour",
            tf2 if tf2 in TIMEFRAME_LABELS else "2Hour",
            tf3 if tf3 in TIMEFRAME_LABELS else "4Hour",
        ]

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(_fetch_chart_payload, symbol, timeframe)
                for symbol, timeframe in zip(symbols, timeframes)
            ]
            payloads = [future.result() for future in futures]

        return tuple(
            _build_chart_figure(payload, symbol, timeframe, primary_tf)
            for payload, symbol, timeframe in zip(payloads, symbols, timeframes)
        )
