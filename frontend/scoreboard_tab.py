"""
frontend/scoreboard_tab.py

Scoreboard tab -- extracted from app.py so it can be archived from the
main navigation without deleting any of its code. Self-contained,
matching the pattern used by campaign_tab.py, portfolio_tab.py,
trade_journal_tab.py, and status_center.py.

To restore this tab later:
1. In app.py, add: from scoreboard_tab import build_scoreboard_tab as build_scoreboard_tab
   (wrapped in the same try/except ImportError pattern used for the other
   extracted tabs, near the top of the file).
2. Add ("scoreboard", "Scoreboard") back to ALL_TABS.
3. Add back the `elif tab=="scoreboard": main = build_scoreboard_tab(session=session)`
   branch in render_main()'s tab routing.
4. Add back `Input("tab-scoreboard","n_clicks")` to the set_tab() callback's
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
TEXT = WHITE
MUTED = WHITE
NAVY_CARD = "#111f35"
TEAL_DIM = "#34d399"
RED_DIM = "#f87171"
YELLOW_DIM = "#fde68a"
BLUE_DIM = "#93c5fd"
PURPLE = "#a78bfa"
PURPLE_GLOW = "rgba(167,139,250,.15)"
BORDER = "rgba(148,163,184,.24)"
BORDER_T = "rgba(45,212,191,.55)"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_GLOW = "rgba(239,68,68,.15)"


def card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}", "borderRadius": "20px",
         "padding": "20px", "boxShadow": "0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Section(children, style=s)


def badge(text, color="teal"):
    p = {"teal":(TEAL_DIM,TEAL_GLOW,BORDER_T),"blue":(BLUE_DIM,"rgba(59,130,246,.12)","rgba(96,165,250,.35)"),
         "yellow":(YELLOW_DIM,"rgba(245,158,11,.12)","rgba(245,158,11,.35)"),
         "red":(RED_DIM,RED_GLOW,"rgba(239,68,68,.35)"),"gray":(TEXT,"rgba(100,116,139,.12)","rgba(100,116,139,.25)"),
         "purple":(PURPLE,PURPLE_GLOW,"rgba(167,139,250,.35)")}
    fg,bg,bdr = p.get(color, p["teal"])
    return html.Span(text, style={"borderRadius":"999px","border":f"1px solid {bdr}",
        "padding":"4px 12px","fontSize":"11px","fontWeight":"800","letterSpacing":".06em",
        "color":fg,"background":bg,"whiteSpace":"nowrap","textTransform":"uppercase"})


def note_box(text, variant=""):
    s = {"border": f"1px solid {BORDER}", "background": "rgba(0,0,0,.2)", "borderRadius": "12px",
         "padding": "12px 14px", "color": WHITE, "fontSize": "12px", "lineHeight": "1.6"}
    if variant == "yellow": s.update({"borderColor": "rgba(245,158,11,.25)", "background": "rgba(245,158,11,.08)", "color": "#fef3c7"})
    elif variant == "blue":  s.update({"borderColor": "rgba(59,130,246,.25)", "background": "rgba(59,130,246,.08)", "color": "#dbeafe"})
    elif variant == "teal":  s.update({"borderColor": "rgba(45,212,191,.55)", "background": "rgba(45,143,111,.18)", "color": "#d1fae5"})
    elif variant == "red":   s.update({"borderColor": "rgba(239,68,68,.25)", "background": "rgba(239,68,68,.15)", "color": "#fecaca"})
    elif variant == "purple":s.update({"borderColor": "rgba(167,139,250,.25)", "background": "rgba(167,139,250,.15)", "color": "#ede9fe"})
    return html.Div(text, style=s)


def _fmt_pct(v, default="—"):
    try:
        if v is None or v == "":
            return default
        return f"{float(v):.1f}%"
    except Exception:
        return default


def build_scoreboard_tab(session=None):
    """Scoreboard — live outcome analytics from /api/scoreboard."""
    import requests as _rq

    try:
        def _do_fetch_scoreboard():
            r = _rq.get(f"{BACKEND_HTTP}/api/scoreboard", timeout=15)
            return r.json() if r.ok else {}

        board = (
            shared_cache.get_or_fetch("/api/scoreboard", _do_fetch_scoreboard, ttl_seconds=120)
            if shared_cache is not None
            else _do_fetch_scoreboard()
        )
    except Exception:
        board = {}

    entries = board.get("recent_signals", [])
    if not isinstance(entries, list):
        entries = []

    agreement_buckets = board.get("agreement_buckets", [])
    if not isinstance(agreement_buckets, list):
        agreement_buckets = []

    agreement_thresholds = board.get("agreement_thresholds", [])
    if not isinstance(agreement_thresholds, list):
        agreement_thresholds = []

    attribution_report = board.get("attribution_report", {})
    if not isinstance(attribution_report, dict):
        attribution_report = {}

    generated = datetime.now(timezone(timedelta(hours=-4))).strftime("%b %d, %Y %I:%M %p ET")

    def _safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    def _safe_int(value, default=0):
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except Exception:
            return default

    def _fmt_pct(value, digits=1, signed=False):
        if value is None or value == "":
            return "—"
        try:
            v = float(value)
            sign = "+" if signed and v > 0 else ""
            return f"{sign}{v:.{digits}f}%"
        except Exception:
            return "—"

    def _fmt_money(value):
        if value is None or value == "":
            return "—"
        try:
            return f"${float(value):,.2f}"
        except Exception:
            return "—"

    total_signals = _safe_int(board.get("total_signals"))
    with_outcomes = _safe_int(board.get("with_outcomes"))
    pending_outcomes = _safe_int(board.get("pending_outcomes"))
    direction_evaluated = _safe_int(board.get("direction_evaluated"))
    direction_correct_rate = _safe_float(board.get("direction_correct_rate"))
    avg_mfe_pct = _safe_float(board.get("avg_mfe_pct"))
    avg_mae_pct = _safe_float(board.get("avg_mae_pct"))
    edge_ratio = _safe_float(board.get("edge_ratio"))
    hit_target1_rate = _safe_float(board.get("hit_target1_rate"))
    hit_target2_rate = _safe_float(board.get("hit_target2_rate"))
    outcome_window_hours = _safe_int(board.get("outcome_window_hours"))

    def _metric(label, value, color=WHITE, sub=None):
        return html.Div([
            html.Div(label, style={
                "fontSize":"10px","color":WHITE,"fontWeight":"800",
                "textTransform":"uppercase","letterSpacing":".12em",
                "marginBottom":"5px"
            }),
            html.Div(value, style={
                "fontSize":"22px","fontWeight":"900","color":color,
                "fontFamily":"DM Mono, monospace" if any(ch.isdigit() for ch in str(value)) else "inherit"
            }),
            html.Div(sub or "", style={
                "fontSize":"10px","color":WHITE,"marginTop":"3px",
                "minHeight":"14px"
            }),
        ], style={
            "background":"rgba(0,0,0,.22)",
            "border":f"1px solid {BORDER}",
            "borderRadius":"14px",
            "padding":"14px 16px",
            "minHeight":"86px"
        })

    def _entry_row(e, rank):
        symbol = e.get("symbol", "—")
        signal_type = e.get("signal_type", e.get("status", "—"))
        score = _safe_float(e.get("score", e.get("composite_score", 0)))
        setup_type = e.get("setup_type", "—")
        regime = e.get("regime", "—")
        grade = str(e.get("grade", "—") or "—")
        entry_price = e.get("entry_price", e.get("price"))
        outcome_pct = e.get("outcome_pct")
        mfe_pct = e.get("mfe_pct")
        mae_pct = e.get("mae_pct")
        direction_correct = e.get("direction_correct")
        hit_t1 = e.get("hit_t1")
        hit_t2 = e.get("hit_t2")
        agreement_score = e.get("agreement_score")
        intelligence_delta = e.get("intelligence_delta")
        agreement_bucket = e.get("agreement_bucket") or "—"
        delta_quality_label = e.get("delta_quality_label") or "—"
        delta_action = e.get("delta_action") or "—"

        score_color = TEAL_DIM if score >= 75 else (YELLOW_DIM if score >= 60 else RED_DIM)
        grade_color = (
            TEAL_DIM if grade.startswith("A")
            else BLUE_DIM if grade.startswith("B")
            else YELLOW_DIM if grade.startswith("C")
            else RED_DIM if grade.startswith(("W", "F"))
            else MUTED
        )

        if outcome_pct is None or outcome_pct == "":
            outcome_color = MUTED
        else:
            outcome_color = TEAL_DIM if _safe_float(outcome_pct) >= 0 else RED_DIM

        if direction_correct is True:
            dir_text, dir_color = "", TEAL_DIM
        elif direction_correct is False:
            dir_text, dir_color = "", RED_DIM
        else:
            dir_text, dir_color = "—", MUTED

        target_text = "T2" if hit_t2 else ("T1" if hit_t1 else "—")
        target_color = TEAL_DIM if hit_t2 else (YELLOW_DIM if hit_t1 else MUTED)

        agreement_value = _safe_float(agreement_score, -1)
        agreement_color = TEAL_DIM if agreement_value >= 90 else (BLUE_DIM if agreement_value >= 80 else (YELLOW_DIM if agreement_value >= 70 else RED_DIM))

        return html.Div([
            html.Span(f"#{rank}", style={"flex":"0 0 34px","fontSize":"11px","color":WHITE,"fontWeight":"800"}),
            html.Span(symbol, style={
                "flex":"0 0 68px","fontWeight":"900","fontSize":"14px",
                "color":WHITE,"fontFamily":"DM Mono, monospace"
            }),
            html.Span(signal_type, style={"flex":"0 0 92px","fontSize":"11px","color":score_color,"fontWeight":"800"}),
            html.Span(f"{score:.1f}", style={"flex":"0 0 58px","fontSize":"15px","fontWeight":"900","color":score_color}),
            html.Span(grade, style={"flex":"0 0 42px","fontSize":"15px","fontWeight":"900","color":grade_color}),
            html.Span(_fmt_money(entry_price), style={"flex":"0 0 84px","fontSize":"12px","color":WHITE,"fontFamily":"DM Mono, monospace"}),
            html.Span(_fmt_pct(outcome_pct, 2, signed=True), style={"flex":"0 0 74px","fontSize":"12px","fontWeight":"800","color":outcome_color}),
            html.Span(_fmt_pct(mfe_pct, 2), style={"flex":"0 0 62px","fontSize":"12px","color":TEAL_DIM if mfe_pct not in (None, "") else MUTED}),
            html.Span(_fmt_pct(mae_pct, 2), style={"flex":"0 0 62px","fontSize":"12px","color":RED_DIM if mae_pct not in (None, "") else MUTED}),
            html.Span(dir_text, style={"flex":"0 0 36px","fontSize":"14px","fontWeight":"900","color":dir_color,"textAlign":"center"}),
            html.Span(target_text, style={"flex":"0 0 42px","fontSize":"12px","fontWeight":"900","color":target_color,"textAlign":"center"}),
            html.Span(
                "—" if agreement_score in (None, "") else f"{float(agreement_score):.1f}",
                style={"flex":"0 0 74px","fontSize":"12px","fontWeight":"900","color":agreement_color,"textAlign":"center"}
            ),
            html.Span(
                "—" if intelligence_delta in (None, "") else f"{float(intelligence_delta):+.1f}",
                style={"flex":"0 0 62px","fontSize":"12px","fontWeight":"800","color":agreement_color,"textAlign":"center"}
            ),
            html.Span(delta_quality_label, style={"flex":"0 0 104px","fontSize":"10px","fontWeight":"900","color":agreement_color,"textAlign":"center"}),
            html.Span(delta_action, style={"flex":"0 0 118px","fontSize":"10px","fontWeight":"900","color":agreement_color,"textAlign":"center"}),
            html.Span(agreement_bucket.replace(" Confirmation", ""), style={"flex":"0 0 150px","fontSize":"10px","color":agreement_color}),
            html.Span(regime, style={"flex":"0 0 115px","fontSize":"11px","color":WHITE}),
            html.Span(setup_type, style={"flex":"1","fontSize":"11px","color":WHITE,"minWidth":"160px"}),
        ], style={
            "display":"flex",
            "alignItems":"center",
            "gap":"10px",
            "padding":"11px 0",
            "borderBottom":f"1px solid {BORDER}",
            "minWidth":"1620px"
        })

    header = html.Div([
        html.Span("#",       style={"flex":"0 0 34px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Symbol",  style={"flex":"0 0 68px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Signal",  style={"flex":"0 0 92px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Score",   style={"flex":"0 0 58px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Grade",   style={"flex":"0 0 42px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Entry",   style={"flex":"0 0 84px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Outcome", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("MFE",     style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("MAE",     style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Dir",     style={"flex":"0 0 36px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Tgt",     style={"flex":"0 0 42px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Agree",   style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Delta",   style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("D-Quality", style={"flex":"0 0 104px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("D-Action", style={"flex":"0 0 118px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","textAlign":"center"}),
        html.Span("Bucket",  style={"flex":"0 0 150px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Regime",  style={"flex":"0 0 115px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em"}),
        html.Span("Setup",   style={"flex":"1","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","letterSpacing":".1em","minWidth":"160px"}),
    ], style={
        "display":"flex",
        "gap":"10px",
        "paddingBottom":"8px",
        "borderBottom":f"1px solid {BORDER}",
        "marginBottom":"4px",
        "minWidth":"1620px"
    })

    def _bucket_card(b):
        bucket = b.get("bucket", "—")
        total = _safe_int(b.get("total_signals"))
        evaluated = _safe_int(b.get("with_outcomes"))
        acc = _safe_float(b.get("direction_correct_rate"))
        edge = _safe_float(b.get("edge_ratio"))
        mfe = _safe_float(b.get("avg_mfe_pct"))
        mae = _safe_float(b.get("avg_mae_pct"))
        color = TEAL_DIM if bucket.startswith("90") else (BLUE_DIM if bucket.startswith("80") else (YELLOW_DIM if bucket.startswith("70") else RED_DIM))
        return html.Div([
            html.Div(bucket, style={"fontSize":"11px","fontWeight":"900","color":color,"marginBottom":"8px"}),
            html.Div([
                html.Div([html.Span("Signals", style={"color":WHITE,"fontSize":"10px"}), html.Strong(str(total), style={"color":WHITE})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("Evaluated", style={"color":WHITE,"fontSize":"10px"}), html.Strong(str(evaluated), style={"color":WHITE})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("Accuracy", style={"color":WHITE,"fontSize":"10px"}), html.Strong(f"{acc:.1f}%", style={"color":color})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("Edge", style={"color":WHITE,"fontSize":"10px"}), html.Strong(f"{edge:.2f}", style={"color":color})], style={"display":"flex","justifyContent":"space-between"}),
                html.Div([html.Span("MFE / MAE", style={"color":WHITE,"fontSize":"10px"}), html.Strong(f"{mfe:.2f}% / {mae:.2f}%", style={"color":WHITE})], style={"display":"flex","justifyContent":"space-between"}),
            ], style={"display":"grid","gap":"5px"})
        ], style={
            "border":f"1px solid {BORDER}",
            "background":"rgba(0,0,0,.2)",
            "borderRadius":"14px",
            "padding":"14px",
            "minHeight":"134px"
        })

    def _threshold_row(t):
        threshold = _safe_int(t.get("threshold"))
        total = _safe_int(t.get("total_signals"))
        evaluated = _safe_int(t.get("with_outcomes"))
        acc = _safe_float(t.get("direction_correct_rate"))
        edge = _safe_float(t.get("edge_ratio"))
        outcome = _safe_float(t.get("avg_outcome_pct"))
        color = TEAL_DIM if threshold >= 90 else (BLUE_DIM if threshold >= 80 else (YELLOW_DIM if threshold >= 70 else TEXT))
        return html.Div([
            html.Span(f">= {threshold}", style={"flex":"0 0 70px","fontWeight":"900","color":color}),
            html.Span(str(total), style={"flex":"0 0 70px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(str(evaluated), style={"flex":"0 0 80px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(f"{acc:.1f}%", style={"flex":"0 0 90px","color":color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{edge:.2f}", style={"flex":"0 0 80px","color":color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{outcome:+.2f}%", style={"flex":"0 0 90px","color":TEAL_DIM if outcome >= 0 else RED_DIM,"fontWeight":"900","textAlign":"center"}),
        ], style={
            "display":"flex",
            "gap":"10px",
            "alignItems":"center",
            "padding":"9px 0",
            "borderBottom":f"1px solid {BORDER}",
        })


    def _attribution_row(row):
        group = row.get("group", "—")
        n = _safe_int(row.get("total_signals"))
        evaluated = _safe_int(row.get("with_outcomes"))
        direction = _safe_float(row.get("direction_accuracy_rate"))
        edge_acc = _safe_float(row.get("edge_accuracy_rate"))
        tradeable = _safe_float(row.get("tradeable_mfe_rate"))
        strong = _safe_float(row.get("strong_mfe_rate"))
        edge = _safe_float(row.get("edge_ratio"))
        mfe = _safe_float(row.get("avg_mfe_pct"))
        mae = _safe_float(row.get("avg_mae_pct"))
        outcome = _safe_float(row.get("avg_outcome_pct"))

        edge_color = TEAL_DIM if edge >= 1.5 else (YELLOW_DIM if edge >= 1 else RED_DIM)

        return html.Div([
            html.Span(group, style={"flex":"1.4","fontSize":"11px","fontWeight":"900","color":WHITE,"minWidth":"150px"}),
            html.Span(str(n), style={"flex":"0 0 54px","fontSize":"11px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(str(evaluated), style={"flex":"0 0 54px","fontSize":"11px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(f"{direction:.1f}%", style={"flex":"0 0 74px","fontSize":"11px","color":BLUE_DIM,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{edge_acc:.1f}%", style={"flex":"0 0 74px","fontSize":"11px","color":edge_color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{tradeable:.1f}%", style={"flex":"0 0 78px","fontSize":"11px","color":TEAL_DIM if tradeable >= 40 else YELLOW_DIM,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{strong:.1f}%", style={"flex":"0 0 72px","fontSize":"11px","color":PURPLE,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{edge:.2f}", style={"flex":"0 0 64px","fontSize":"11px","color":edge_color,"fontWeight":"900","textAlign":"center"}),
            html.Span(f"{mfe:.2f}%/{mae:.2f}%", style={"flex":"0 0 94px","fontSize":"11px","color":WHITE,"fontWeight":"800","textAlign":"center"}),
            html.Span(f"{outcome:+.2f}%", style={"flex":"0 0 76px","fontSize":"11px","color":TEAL_DIM if outcome >= 0 else RED_DIM,"fontWeight":"900","textAlign":"center"}),
        ], style={
            "display":"flex",
            "gap":"8px",
            "alignItems":"center",
            "padding":"8px 0",
            "borderBottom":f"1px solid {BORDER}",
            "minWidth":"900px"
        })

    def _attribution_table(title, rows):
        rows = rows if isinstance(rows, list) else []
        return html.Div([
            html.Div(title, style={
                "fontSize":"12px","fontWeight":"900","color":WHITE,
                "textTransform":"uppercase","letterSpacing":".08em",
                "marginBottom":"8px"
            }),
            html.Div([
                html.Span("Group", style={"flex":"1.4","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","minWidth":"150px"}),
                html.Span("Sig", style={"flex":"0 0 54px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Eval", style={"flex":"0 0 54px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Dir", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Edge Acc", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Tradeable", style={"flex":"0 0 78px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Strong", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Edge", style={"flex":"0 0 64px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("MFE/MAE", style={"flex":"0 0 94px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                html.Span("Outcome", style={"flex":"0 0 76px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
            ], style={
                "display":"flex","gap":"8px","paddingBottom":"7px",
                "borderBottom":f"1px solid {BORDER}",
                "minWidth":"900px"
            }),
            html.Div([_attribution_row(r) for r in rows[:10]] if rows else [
                html.Div("No attribution data yet.", style={"fontSize":"12px","color":WHITE,"padding":"10px 0"})
            ]),
        ], style={
            "border":f"1px solid {BORDER}",
            "background":"rgba(0,0,0,.15)",
            "borderRadius":"14px",
            "padding":"14px",
            "overflowX":"auto"
        })


    if edge_ratio >= 1.2 and with_outcomes > 0:
        edge_note = "Positive path edge: average favorable movement is larger than average adverse movement."
        edge_variant = "teal"
    elif with_outcomes > 0:
        edge_note = "Path edge is not yet confirmed. Continue collecting outcomes before relying on this metric."
        edge_variant = "yellow"
    else:
        edge_note = "Outcome statistics populate after signals have enough forward price data."
        edge_variant = "blue"

    return html.Div([
        card([
            html.Div([
                html.Div([
                    html.H2("Scoreboard", style={
                        "color":WHITE,"fontSize":"18px","fontWeight":"900",
                        "margin":"0 0 4px"
                    }),
                    html.P(
                        f"Live outcome validation · {outcome_window_hours}h window · backend /api/scoreboard",
                        style={"color":WHITE,"fontSize":"13px","margin":"0"}
                    ),
                ]),
                badge("LIVE BACKEND", "teal" if board else "red"),
            ], style={
                "display":"flex",
                "justifyContent":"space-between",
                "alignItems":"start",
                "gap":"16px",
                "marginBottom":"16px"
            }),

            html.Div([
                _metric("Total Signals", f"{total_signals}", WHITE, "All logged signals"),
                _metric("Evaluated", f"{with_outcomes}", TEAL_DIM, "Signals with outcomes"),
                _metric("Pending", f"{pending_outcomes}", YELLOW_DIM if pending_outcomes else MUTED, "Awaiting outcome window"),
                _metric("Direction Accuracy", _fmt_pct(direction_correct_rate, 1), TEAL_DIM if direction_correct_rate >= 50 else YELLOW_DIM, f"{direction_evaluated} evaluated signals"),
                _metric("Avg MFE", _fmt_pct(avg_mfe_pct, 2), TEAL_DIM, "Favorable excursion"),
                _metric("Avg MAE", _fmt_pct(avg_mae_pct, 2), RED_DIM, "Adverse excursion"),
                _metric("Edge Ratio", f"{edge_ratio:.2f}", TEAL_DIM if edge_ratio >= 1.2 else YELLOW_DIM, "MFE ÷ MAE"),
                _metric("Targets", f"T1 {hit_target1_rate:.1f}% / T2 {hit_target2_rate:.1f}%", BLUE_DIM, "Hit-rate snapshot"),
            ], style={
                "display":"grid",
                "gridTemplateColumns":"repeat(4,1fr)",
                "gap":"12px",
                "marginBottom":"16px"
            }),

            note_box(edge_note, edge_variant),

            html.Div(style={"height":"16px"}),

            html.Div([
                html.Div([
                    html.H3("Intelligence Agreement Validation", style={
                        "fontSize":"15px","fontWeight":"900","color":WHITE,"margin":"0 0 4px"
                    }),
                    html.Div("Shows whether deeper intelligence agreement improves direction accuracy and path edge.",
                             style={"fontSize":"11px","color":WHITE}),
                ]),
            ], style={"marginBottom":"12px"}),

            html.Div(
                [_bucket_card(b) for b in agreement_buckets] if agreement_buckets else [
                    note_box("Agreement buckets are waiting for repaired or newly logged signals.", "yellow")
                ],
                style={
                    "display":"grid",
                    "gridTemplateColumns":"repeat(4,1fr)",
                    "gap":"12px",
                    "marginBottom":"16px"
                }
            ),

            html.Div([
                html.Div("Minimum Agreement Filter", style={
                    "fontSize":"12px","fontWeight":"900","color":WHITE,
                    "textTransform":"uppercase","letterSpacing":".08em",
                    "marginBottom":"8px"
                }),
                html.Div([
                    html.Span("Filter", style={"flex":"0 0 70px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase"}),
                    html.Span("Signals", style={"flex":"0 0 70px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Eval", style={"flex":"0 0 80px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Accuracy", style={"flex":"0 0 90px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Edge", style={"flex":"0 0 80px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                    html.Span("Outcome", style={"flex":"0 0 90px","fontSize":"9px","color":WHITE,"fontWeight":"800","textTransform":"uppercase","textAlign":"center"}),
                ], style={"display":"flex","gap":"10px","borderBottom":f"1px solid {BORDER}","paddingBottom":"7px"}),
                html.Div([_threshold_row(t) for t in agreement_thresholds] if agreement_thresholds else [
                    html.Div("No agreement threshold data yet.", style={"fontSize":"12px","color":WHITE,"padding":"12px 0"})
                ]),
            ], style={
                "border":f"1px solid {BORDER}",
                "background":"rgba(0,0,0,.15)",
                "borderRadius":"14px",
                "padding":"14px",
                "marginBottom":"18px",
                "maxWidth":"620px"
            }),

            html.Div(style={"height":"16px"}),

            html.Div([
                html.Div([
                    html.H3("Live Performance Attribution", style={
                        "fontSize":"15px","fontWeight":"900","color":WHITE,"margin":"0 0 4px"
                    }),
                    html.Div("Ranks which parts of the engine are producing direction, edge, and tradeable opportunity.",
                             style={"fontSize":"11px","color":WHITE}),
                ]),
            ], style={"marginBottom":"12px"}),

            html.Div([
                _attribution_table("Agreement Bucket", attribution_report.get("by_agreement_bucket", [])),
                _attribution_table("Delta Bucket", attribution_report.get("by_delta_bucket", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}),

            html.Div([
                _attribution_table("Regime", attribution_report.get("by_regime", [])),
                _attribution_table("Setup Type", attribution_report.get("by_setup_type", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}),

            html.Div([
                _attribution_table("Grade", attribution_report.get("by_grade", [])),
                _attribution_table("Signal Type", attribution_report.get("by_signal_type", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"12px"}),

            html.Div([
                _attribution_table("Delta Quality", attribution_report.get("by_delta_quality", [])),
                _attribution_table("Delta Action", attribution_report.get("by_delta_action", [])),
            ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"12px","marginBottom":"18px"}),

            html.Div([
                html.Div([
                    html.Div("Recent Signal Outcomes", style={
                        "fontSize":"12px","fontWeight":"900","color":WHITE,
                        "textTransform":"uppercase","letterSpacing":".08em"
                    }),
                    html.Div("Pending rows show dashes until MFE / MAE / direction fields are populated.",
                             style={"fontSize":"11px","color":WHITE,"marginTop":"3px"}),
                ]),
            ], style={"marginBottom":"12px"}),

            html.Div([
                header,
                html.Div([_entry_row(e, i+1) for i, e in enumerate(entries)] if entries else [
                    html.Div(
                        "Scoreboard data not yet available. Backend returned no recent_signals.",
                        style={"color":WHITE,"fontSize":"13px","padding":"24px 0","textAlign":"center"}
                    )
                ]),
            ], style={
                "overflowX":"auto",
                "border":f"1px solid {BORDER}",
                "borderRadius":"14px",
                "padding":"12px",
                "background":"rgba(0,0,0,.14)"
            }),

            html.Div(f"Last updated: {generated}", style={
                "fontSize":"10px","color":WHITE,"marginTop":"12px"
            }),
        ]),
    ])