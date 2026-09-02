"""
frontend/divergence_tab.py

Intelligence Change Detector tab -- extracted from app.py so it can be
archived from the main navigation without deleting any of its code.
Self-contained, matching the pattern used by campaign_tab.py,
portfolio_tab.py, trade_journal_tab.py, and status_center.py.

To restore this tab later:
1. In app.py, add: from divergence_tab import build_divergence_tab as build_divergence_tab
   (wrapped in the same try/except ImportError pattern used for the other
   extracted tabs, near the top of the file).
2. Add ("divergence", "Intelligence Change Detector") back to ALL_TABS.
3. Add back the `elif tab=="divergence": main = build_divergence_tab(session=session)`
   branch in render_main()'s tab routing.
4. Add back `Input("tab-divergence","n_clicks")` to the set_tab() callback's
   Input list.
No other changes needed -- this file was never modified beyond the
self-contained header below.
"""

import os
from datetime import datetime, timedelta, timezone
from dash import html

try:
    from shared_cache import shared_cache
except Exception:
    shared_cache = None

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

# Brand tokens -- same effective values as app.py's own definitions at
# the time of extraction.
WHITE = "#FFFFFF"
MUTED = WHITE
NAVY_CARD = "#111f35"
TEAL_DIM = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM = "#f87171"
RED_GLOW = "rgba(239,68,68,.15)"
YELLOW_DIM = "#fde68a"
BLUE_DIM = "#93c5fd"
BORDER = "rgba(148,163,184,.24)"
BORDER_T = "rgba(45,212,191,.55)"


def card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}", "borderRadius": "20px",
         "padding": "20px", "boxShadow": "0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Section(children, style=s)


def metric_tile(label, value, accent=WHITE, sub=None):
    return html.Div([
        html.Span(label, style={"display":"block","color":WHITE,"fontSize":"11px","fontWeight":"600",
                                "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"6px"}),
        html.Strong(value, style={"display":"block","color":accent,"fontSize":"15px","fontWeight":"800"}),
        *([html.Span(sub, style={"fontSize":"10px","color":WHITE,"marginTop":"2px","display":"block"})] if sub else []),
    ], style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px","minHeight":"64px"})


def note_box(text, variant=""):
    s = {"border": f"1px solid {BORDER}", "background": "rgba(0,0,0,.2)", "borderRadius": "12px",
         "padding": "12px 14px", "color": WHITE, "fontSize": "12px", "lineHeight": "1.6"}
    if variant == "yellow": s.update({"borderColor": "rgba(245,158,11,.25)", "background": "rgba(245,158,11,.08)", "color": "#fef3c7"})
    elif variant == "blue":  s.update({"borderColor": "rgba(59,130,246,.25)", "background": "rgba(59,130,246,.08)", "color": "#dbeafe"})
    elif variant == "teal":  s.update({"borderColor": BORDER_T, "background": TEAL_GLOW, "color": "#d1fae5"})
    elif variant == "red":   s.update({"borderColor": "rgba(239,68,68,.25)", "background": RED_GLOW, "color": "#fecaca"})
    elif variant == "purple":s.update({"borderColor": "rgba(167,139,250,.25)", "background": "rgba(167,139,250,.15)", "color": "#ede9fe"})
    return html.Div(text, style=s)


def classify_transition(old_status, new_status, delta):
    """
    Intelligence Change Detector transition classifier.

    Delta is calculated as:
        deep_score - composite_score

    Positive delta = deeper intelligence is stronger than surface composite.
    Negative delta = deeper intelligence is weaker than surface composite.

    State transition has priority over delta:
    - Building -> Watching = Improving / upgrade
    - Watching -> Watching = Monitor
    - Watching -> Avoid = Major downgrade
    """
    old_status_l = str(old_status or "").strip().lower()
    new_status_l = str(new_status or "").strip().lower()

    # Normalize common backend labels.
    upgrade_states = ("watching", "armed", "triggered", "opportunity")
    high_states = ("armed", "triggered", "opportunity")

    # No state change should remain a monitor, even if the score delta is negative.
    # This prevents Watching -> Watching rows from being counted as downgrades.
    if old_status_l == new_status_l and old_status_l:
        return "MONITOR", "yellow"

    # Explicit improvement transitions first.
    if old_status_l == "building" and new_status_l == "watching":
        return "IMPROVING", "teal"

    if old_status_l == "building" and new_status_l in high_states:
        return "STRONG UPGRADE", "teal"

    if old_status_l == "avoid" and new_status_l in upgrade_states:
        return "UPGRADE", "teal"

    if old_status_l == "watching" and new_status_l in high_states:
        return "STRONG UPGRADE", "teal"

    # Explicit deterioration transitions.
    if old_status_l in high_states and new_status_l == "watching":
        return "DOWNGRADE", "red"

    if old_status_l in ("building", "watching", "armed", "triggered", "opportunity") and new_status_l == "avoid":
        return "MAJOR DOWNGRADE", "red"

    # Score-delta interpretation only applies when the state transition is not definitive.
    if delta >= 20:
        return "INTELLIGENCE LEAD", "teal"

    if delta >= 10:
        return "MODEST UPGRADE", "teal"

    if delta <= -20:
        return "INTELLIGENCE WARNING", "red"

    if delta <= -10:
        return "MODEST DOWNGRADE", "red"

    return "MONITOR", "yellow"

def build_divergence_tab(session=None):
    """
    Intelligence Change Detector.

    This page uses the actual backend divergence endpoint fields:
    symbol, composite_score, deep_score, delta, old_status, new_status,
    regime, price, audited_at.
    """
    import requests as _rq

    try:
        def _do_fetch_divergence():
            r = _rq.get(f"{BACKEND_HTTP}/api/radar/divergence", timeout=15)
            return r.json() if r.ok else {}

        data = (
            shared_cache.get_or_fetch("/api/radar/divergence", _do_fetch_divergence, ttl_seconds=90)
            if shared_cache is not None
            else _do_fetch_divergence()
        )
    except Exception:
        data = {}

    raw_symbols = data.get("symbols", []) if isinstance(data, dict) else []
    audit_raw = (
        data.get("last_audit")
        or data.get("audited_at")
    ) if isinstance(data, dict) else None

    try:
        if audit_raw:
            audit_dt = datetime.fromtimestamp(
                float(audit_raw),
                tz=timezone.utc
            ).astimezone(
                timezone(timedelta(hours=-4))
            )

            audit_label = audit_dt.strftime(
                "%b %d, %Y %I:%M %p ET"
            )
        else:
            audit_label = "Pending — runs nightly after the EOD audit"

    except Exception:
        audit_label = str(audit_raw) if audit_raw else "Pending — runs nightly after the EOD audit"

    def _num(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    items = []
    for s in (raw_symbols if isinstance(raw_symbols, list) else []):
        if not isinstance(s, dict):
            continue

        composite = _num(s.get("composite_score"), 0)
        deep = _num(s.get("deep_score"), 0)

        # Use intuitive displayed delta: deep intelligence minus surface composite.
        # Example: Composite 62.5, Deep 34.85 = -27.65 = deeper engine downgraded it.
        delta = round(deep - composite, 2)

        old_status = s.get("old_status") or "—"
        new_status = s.get("new_status") or s.get("status") or "—"
        transition, tone = classify_transition(old_status, new_status, delta)

        items.append({
            "symbol": s.get("symbol", ""),
            "price": _num(s.get("price"), 0),
            "composite_score": composite,
            "deep_score": deep,
            "delta": delta,
            "old_status": old_status,
            "new_status": new_status,
            "transition": transition,
            "tone": tone,
            "regime": s.get("regime") or "—",
            "audited_at": s.get("audited_at") or audit_label,
        })

    # Largest intelligence gap first.
    items = sorted(items, key=lambda d: abs(d.get("delta", 0)), reverse=True)

    upgrades = sum(1 for d in items if d["tone"] == "teal")
    downgrades = sum(1 for d in items if d["tone"] == "red")
    monitoring = sum(1 for d in items if d["tone"] == "yellow")

    best_upgrade = max(items, key=lambda d: d["delta"], default=None)
    best_downgrade = min(items, key=lambda d: d["delta"], default=None)

    def _tone_color(tone):
        if tone == "teal":
            return TEAL_DIM
        if tone == "red":
            return RED_DIM
        if tone == "yellow":
            return YELLOW_DIM
        return MUTED

    def _state_badge(value, tone="gray"):
        color = _tone_color(tone)
        bg = TEAL_GLOW if tone == "teal" else RED_GLOW if tone == "red" else "rgba(245,158,11,.10)" if tone == "yellow" else "rgba(100,116,139,.12)"
        border = BORDER_T if tone == "teal" else "rgba(239,68,68,.35)" if tone == "red" else "rgba(245,158,11,.35)" if tone == "yellow" else "rgba(100,116,139,.25)"
        return html.Span(
            str(value),
            style={
                "display": "inline-block",
                "borderRadius": "999px",
                "border": f"1px solid {border}",
                "background": bg,
                "color": color,
                "fontSize": "10px",
                "fontWeight": "900",
                "letterSpacing": ".06em",
                "padding": "4px 9px",
                "textTransform": "uppercase",
                "whiteSpace": "nowrap",
            }
        )

    summary_card = card([
        html.Div([
            html.Div([
                html.H2(
                    "Intelligence Change Detector",
                    style={"color": WHITE, "fontSize": "20px", "fontWeight": "900", "margin": "0 0 4px"}
                ),
                html.P(
                    "Detects where the deeper intelligence engine disagrees with the surface radar score.",
                    style={"color": WHITE, "fontSize": "13px", "margin": "0"}
                ),
            ]),
            _state_badge(f"{len(items)} Symbols Audited", "gray"),
        ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start", "gap": "16px", "marginBottom": "16px"}),

        html.Div([
            metric_tile("Upgrades", str(upgrades), TEAL_DIM),
            metric_tile("Monitoring", str(monitoring), YELLOW_DIM),
            metric_tile("Downgrades", str(downgrades), RED_DIM),
            metric_tile("Last Audit", str(audit_label)[:22], BLUE_DIM),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(4,1fr)", "gap": "10px", "marginBottom": "14px"}),

        html.Div([
            note_box(
                f"Strongest Upgrade: {(best_upgrade or {}).get('symbol','—')} "
                f"({(best_upgrade or {}).get('delta',0):+.1f})",
                "teal"
            ),
            note_box(
                f"Strongest Downgrade: {(best_downgrade or {}).get('symbol','—')} "
                f"({(best_downgrade or {}).get('delta',0):+.1f})",
                "red"
            ),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "10px"}),
    ], sx={"marginBottom": "16px"})

    def _row(d):
        delta = d.get("delta", 0)
        tone = d.get("tone", "gray")
        color = _tone_color(tone)
        delta_color = TEAL_DIM if delta > 0 else (RED_DIM if delta < 0 else MUTED)

        return html.Div([
            html.Span(
                d.get("symbol", ""),
                style={
                    "flex": "0.75",
                    "fontWeight": "900",
                    "fontSize": "14px",
                    "color": WHITE,
                    "fontFamily": "DM Mono, monospace",
                }
            ),
            html.Span(
                f"${d.get('price', 0):,.2f}",
                style={"flex": "0.85", "fontSize": "13px", "color": WHITE, "fontFamily": "DM Mono, monospace"}
            ),
            html.Span(
                f"{d.get('composite_score', 0):.1f}",
                style={"flex": "0.75", "fontSize": "13px", "fontWeight": "800", "color": YELLOW_DIM}
            ),
            html.Span(
                f"{d.get('deep_score', 0):.1f}",
                style={"flex": "0.75", "fontSize": "13px", "fontWeight": "800", "color": BLUE_DIM}
            ),
            html.Span(
                f"{delta:+.1f}",
                style={"flex": "0.75", "fontSize": "13px", "fontWeight": "900", "color": delta_color}
            ),
            html.Span(
                d.get("old_status", "—"),
                style={"flex": "0.9", "fontSize": "12px", "fontWeight": "700", "color": WHITE}
            ),
            html.Span(
                d.get("new_status", "—"),
                style={"flex": "0.9", "fontSize": "12px", "fontWeight": "900", "color": color}
            ),
            html.Span(
                d.get("transition", "—"),
                style={"flex": "1.65", "fontSize": "11px", "fontWeight": "900", "color": color}
            ),
            html.Span(
                d.get("regime", "—"),
                style={"flex": "0.95", "fontSize": "11px", "color": WHITE}
            ),
        ], style={
            "display": "flex",
            "alignItems": "center",
            "gap": "12px",
            "padding": "12px 0",
            "borderBottom": f"1px solid {BORDER}",
        })

    header = html.Div([
        html.Span("Symbol", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Price", style={"flex": "0.85", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Composite", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Deep Score", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Delta", style={"flex": "0.75", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Previous", style={"flex": "0.9", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Current", style={"flex": "0.9", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Transition", style={"flex": "1.65", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
        html.Span("Regime", style={"flex": "0.95", "fontSize": "9px", "color": WHITE, "fontWeight": "800", "textTransform": "uppercase", "letterSpacing": ".1em"}),
    ], style={
        "display": "flex",
        "gap": "12px",
        "paddingBottom": "8px",
        "borderBottom": f"1px solid {BORDER}",
        "marginBottom": "4px",
    })

    table_card = card([
        html.Div([
            html.H3(
                "Intelligence Transitions",
                style={"color": WHITE, "fontSize": "16px", "fontWeight": "900", "margin": "0"}
            ),
            html.P(
                "Positive delta = deeper intelligence stronger than radar. Negative delta = deeper intelligence weaker than radar.",
                style={"color": WHITE, "fontSize": "12px", "margin": "4px 0 0"}
            ),
        ], style={"marginBottom": "14px"}),

        header,

        html.Div([_row(d) for d in items] if items else [
            html.Div(
                "No intelligence changes yet. The detector populates after the EOD audit.",
                style={"color": WHITE, "fontSize": "13px", "padding": "24px 0", "textAlign": "center"}
            )
        ]),
    ])

    return html.Div([summary_card, table_card])