"""
frontend/radar_tab.py

Radar Screen tab -- extracted from app.py so it can be archived from the
main navigation without deleting any of its code. Self-contained,
matching the same pattern already used by campaign_tab.py, portfolio_tab.py,
trade_journal_tab.py, and status_center.py: its own color constants and
helpers, its own shared_cache import with a fallback, rather than relying
on app.py's globals -- so this file works whether or not it's ever wired
back into app.py's tab routing.

To restore this tab later:
1. In app.py, add: from radar_tab import build_radar_tab as build_radar_tab
   (wrapped in the same try/except ImportError pattern used for the other
   extracted tabs, near the top of the file).
2. Add ("radar", "Radar Screen") back to ALL_TABS.
3. Add back the `elif tab=="radar": main = build_radar_tab(session=session)`
   branch in render_main()'s tab routing.
4. Add back `Input("tab-radar","n_clicks")` to the set_tab() callback's
   Input list.
No other changes needed -- this file was never modified beyond the
self-contained header below, so it's byte-for-byte the same logic that
was live in app.py at the time of archiving.
"""

import os
from dash import html

try:
    from shared_cache import shared_cache
except Exception:
    shared_cache = None

BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")

# Brand tokens -- same effective values as app.py's own definitions at
# the time of extraction.
WHITE = "#FFFFFF"
NAVY_CARD = "#111f35"
TEAL_DIM = "#34d399"
RED_DIM = "#f87171"
YELLOW_DIM = "#fde68a"
BLUE_DIM = "#93c5fd"
MUTED = WHITE
BORDER = "rgba(148,163,184,.24)"


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


def _fmt_pct(v, default="—"):
    try:
        if v is None or v == "":
            return default
        return f"{float(v):.1f}%"
    except Exception:
        return default


def build_radar_tab(session=None):
    """Opportunity Dashboard — behavioral transition radar."""
    import requests as _rq

    try:
        def _do_fetch_radar():
            r = _rq.get(f"{BACKEND_HTTP}/api/radar/scores", timeout=15)
            return r.json() if r.ok else {}

        data = (
            shared_cache.get_or_fetch("/api/radar/scores", _do_fetch_radar, ttl_seconds=90)
            if shared_cache is not None
            else _do_fetch_radar()
        )

        if isinstance(data, list):
            signals = data
            sort_mode = "local"
            last_scan = None
            data_delay = "—"
        else:
            signals = (
                data.get("symbols")
                or data.get("signals")
                or data.get("scores")
                or data.get("results")
                or data.get("data")
                or data.get("radar")
                or []
            )
            sort_mode = data.get("sort_mode", "—")
            last_scan = data.get("last_scan")
            data_delay = data.get("data_delay", "—")

    except Exception as e:
        print(f"Radar fetch error: {e}")
        signals = []
        sort_mode = "error"
        last_scan = None
        data_delay = "—"

    def _safe_float(value, default=0.0):
        try:
            if value is None or value == "":
                return default
            return float(value)
        except Exception:
            return default

    def _safe_text(value, default="—"):
        if value is None or value == "":
            return default
        return str(value)

    def _fmt_money(value):
        try:
            if value is None or value == "":
                return "—"
            return f"${float(value):,.2f}"
        except Exception:
            return "—"

    def _fmt_pct(value, digits=1, signed=False):
        try:
            if value is None or value == "":
                return "—"
            v = float(value)
            sign = "+" if signed and v > 0 else ""
            return f"{sign}{v:.{digits}f}%"
        except Exception:
            return "—"

    def _state_color(state, score=0):
        st = (state or "").lower()
        if "armed" in st:
            return TEAL_DIM
        if "setting" in st:
            return BLUE_DIM
        if "triggered" in st:
            return YELLOW_DIM
        if "avoid" in st or "reject" in st:
            return RED_DIM
        if score >= 80:
            return TEAL_DIM
        if score >= 70:
            return YELLOW_DIM
        return MUTED

    def _side_color(side):
        sd = (side or "").lower()
        if "short" in sd:
            return RED_DIM
        if "long" in sd:
            return TEAL_DIM
        return MUTED

    def _readiness_label(score):
        if score >= 90:
            return "Elite"
        if score >= 80:
            return "High"
        if score >= 70:
            return "Qualified"
        if score >= 60:
            return "Developing"
        return "Low"

    def _compact_transition(text):
        t = _safe_text(text)
        return t.replace(" to ", " → ").replace(" / ", " / ")

    def _score_grade(score):
        """
        Genuine composite_score-based letter grade -- matches the
        exact same established thresholds already used in backend/
        main.py's _compat_grade() and backend/intelligence_api.py's
        _grade(), a real, in-production convention. Applied here to
        the genuine, symbol-specific composite_score, not the removed,
        probability-engine-derived probability_grade.
        """
        if score >= 85:
            return "A+"
        if score >= 75:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        return "W"

    def _opportunity_card(s, rank):
        symbol = _safe_text(s.get("symbol"), "")
        price = s.get("price")
        chg = _safe_float(s.get("change_pct"))
        score = _safe_float(s.get("composite_score", s.get("score")))
        readiness = _safe_float(s.get("readiness_score"))
        state = _safe_text(s.get("opportunity_state"), "Watching")
        transition = _compact_transition(s.get("transition_candidate"))
        behavioral_state = _safe_text(s.get("behavioral_state"), "—")
        side = _safe_text(s.get("trade_side"), _safe_text(s.get("side"), "—"))
        trigger = s.get("trigger")
        invalidation = s.get("invalidation")
        why = _safe_text(s.get("why_this_trade"), "Awaiting more evidence.")
        evidence = s.get("evidence") if isinstance(s.get("evidence"), list) else []
        risk_notes = s.get("risk_notes") if isinstance(s.get("risk_notes"), list) else []
        setup = _safe_text(s.get("setup_type"), "—")
        regime = _safe_text(s.get("regime"), "—")
        status = _safe_text(s.get("status"), "—")
        alert_type = _safe_text(s.get("alert_type"), "—")
        setup_risk_reward = s.get("setup_risk_reward")
        wyckoff_verdict = s.get("wyckoff_verdict") if isinstance(s.get("wyckoff_verdict"), dict) else None
        livermore_verdict = s.get("livermore_verdict") if isinstance(s.get("livermore_verdict"), dict) else None
        weis_verdict = s.get("weis_verdict") if isinstance(s.get("weis_verdict"), dict) else None
        score_color = TEAL_DIM if score >= 75 else (YELLOW_DIM if score >= 60 else RED_DIM)

        color = _state_color(state, readiness)
        side_color = _side_color(side)

        return html.Div([
            html.Div([
                html.Div([
                    html.Div(f"#{rank}", style={
                        "fontSize":"10px","fontWeight":"900","color":WHITE,
                        "textTransform":"uppercase","letterSpacing":".08em"
                    }),
                    html.Div(symbol, style={
                        "fontSize":"24px","fontWeight":"950","color":WHITE,
                        "fontFamily":"DM Mono, monospace","lineHeight":"1"
                    }),
                    html.Div(f"{_fmt_money(price)} · {_fmt_pct(chg, 2, signed=True)}", style={
                        "fontSize":"11px","fontWeight":"800",
                        "color":TEAL_DIM if chg >= 0 else RED_DIM,
                        "marginTop":"5px"
                    }),
                ], style={"flex":"1"}),

                html.Div([
                    html.Div(f"{score:.0f}", style={
                        "fontSize":"30px","fontWeight":"950","color":score_color,
                        "lineHeight":"1","textAlign":"right"
                    }),
                    html.Div("Score", style={
                        "fontSize":"10px","fontWeight":"950","color":WHITE,
                        "textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"
                    }),
                    html.Div(f"Ready {readiness:.0f}", style={
                        "fontSize":"10px","fontWeight":"900","color":color,
                        "textAlign":"right","marginTop":"4px"
                    }),
                ]),
            ], style={"display":"flex","alignItems":"flex-start","gap":"12px"}),

            html.Div(style={"height":"12px"}),

            html.Div([
                html.Span(state, style={
                    "display":"inline-block","padding":"5px 9px",
                    "borderRadius":"999px","background":"rgba(255,255,255,.06)",
                    "border":f"1px solid {color}","color":color,
                    "fontSize":"10px","fontWeight":"900","textTransform":"uppercase",
                    "letterSpacing":".08em","marginRight":"6px"
                }),
                html.Span(side, style={
                    "display":"inline-block","padding":"5px 9px",
                    "borderRadius":"999px","background":"rgba(255,255,255,.04)",
                    "border":f"1px solid {side_color}","color":side_color,
                    "fontSize":"10px","fontWeight":"900","textTransform":"uppercase",
                    "letterSpacing":".08em","marginRight":"6px"
                }),
                html.Span(alert_type, style={
                    "display":"inline-block","padding":"5px 9px",
                    "borderRadius":"999px","background":"rgba(255,255,255,.04)",
                    "border":f"1px solid {BORDER}","color":WHITE,
                    "fontSize":"10px","fontWeight":"800"
                }),
            ]),

            html.Div(style={"height":"12px"}),

            html.Div([
                html.Div([
                    html.Div("Risk/Reward", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(
                        f"{setup_risk_reward:.2f}" if isinstance(setup_risk_reward, (int, float)) else "—",
                        style={"fontSize":"18px","fontWeight":"950",
                               "color": (TEAL_DIM if setup_risk_reward >= 2.0 else YELLOW_DIM) if isinstance(setup_risk_reward, (int, float)) else MUTED},
                    ),
                ], style={"flex":"1"}),
            ], style={"display":"flex","gap":"10px","padding":"10px","border":f"1px solid {BORDER}","borderRadius":"12px","background":"rgba(255,255,255,.035)"}),

            html.Div(style={"height":"12px"}) if (wyckoff_verdict or livermore_verdict or weis_verdict) else None,

            html.Div([
                html.Div("Methodology Breakdown", style={
                    "fontSize":"10px","fontWeight":"950","color":WHITE,
                    "textTransform":"uppercase","letterSpacing":".08em","marginBottom":"6px"
                }),
                html.Div([
                    html.Div([
                        html.Div("Wyckoff", style={"fontSize":"9px","fontWeight":"900","color":WHITE,"textTransform":"uppercase"}),
                        html.Div(f"{wyckoff_verdict.get('wyckoff_score', 0):.0f}" if wyckoff_verdict else "—",
                                 style={"fontSize":"16px","fontWeight":"950","color":TEAL_DIM}),
                        html.Div(_safe_text(wyckoff_verdict.get("verdict") if wyckoff_verdict else None, "—"),
                                 style={"fontSize":"9px","color":MUTED,"fontWeight":"700"}),
                    ], style={"flex":"1"}),
                    html.Div([
                        html.Div("Livermore", style={"fontSize":"9px","fontWeight":"900","color":WHITE,"textTransform":"uppercase"}),
                        html.Div(f"{livermore_verdict.get('livermore_score', 0):.0f}" if livermore_verdict else "—",
                                 style={"fontSize":"16px","fontWeight":"950","color":BLUE_DIM}),
                        html.Div(_safe_text(livermore_verdict.get("verdict") if livermore_verdict else None, "—"),
                                 style={"fontSize":"9px","color":MUTED,"fontWeight":"700"}),
                    ], style={"flex":"1"}),
                    html.Div([
                        html.Div("Weis", style={"fontSize":"9px","fontWeight":"900","color":WHITE,"textTransform":"uppercase"}),
                        html.Div(f"{weis_verdict.get('weis_score', 0):.0f}" if weis_verdict else "—",
                                 style={"fontSize":"16px","fontWeight":"950","color":YELLOW_DIM}),
                        html.Div(_safe_text(weis_verdict.get("verdict") if weis_verdict else None, "—"),
                                 style={"fontSize":"9px","color":MUTED,"fontWeight":"700"}),
                    ], style={"flex":"1"}),
                ], style={"display":"flex","gap":"10px"}),
            ], style={"padding":"10px","border":f"1px solid {BORDER}","borderRadius":"12px","background":"rgba(255,255,255,.02)"}) if (wyckoff_verdict or livermore_verdict or weis_verdict) else html.Div(),

            html.Div(style={"height":"12px"}),

            html.Div("Behavioral Transition", style={
                "fontSize":"10px","fontWeight":"950","color":WHITE,
                "textTransform":"uppercase","letterSpacing":".08em","marginBottom":"4px"
            }),
            html.Div(transition, style={
                "fontSize":"14px","fontWeight":"900","color":WHITE,
                "lineHeight":"1.25","minHeight":"34px"
            }),
            html.Div(behavioral_state, style={
                "fontSize":"12px","fontWeight":"900","color":WHITE,
                "marginTop":"4px"
            }),

            html.Div(style={"height":"12px"}),

            html.Div([
                html.Div([
                    html.Div("Trigger", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(_fmt_money(trigger), style={"fontSize":"13px","fontWeight":"900","color":TEAL_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Invalid", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(_fmt_money(invalidation), style={"fontSize":"13px","fontWeight":"900","color":RED_DIM}),
                ], style={"flex":"1"}),
                html.Div([
                    html.Div("Score", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                    html.Div(f"{score:.0f}", style={"fontSize":"13px","fontWeight":"900","color":YELLOW_DIM}),
                ], style={"flex":"1"}),
            ], style={"display":"flex","gap":"10px"}),

            html.Div(style={"height":"12px"}),

            html.Div("Why This Trade?", style={
                "fontSize":"10px","fontWeight":"950","color":WHITE,
                "textTransform":"uppercase","letterSpacing":".08em","marginBottom":"6px"
            }),
            html.Div(why, style={
                "fontSize":"12px","color":WHITE,"fontWeight":"850","lineHeight":"1.45",
                "minHeight":"44px"
            }),

            html.Div(style={"height":"10px"}),

            html.Div([
                html.Div("Setup", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em"}),
                html.Div(setup, style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"800"}),
                html.Div(f"{status} · {regime}", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850","marginTop":"3px"}),
            ]),

            html.Div([
                html.Div("Evidence", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em","marginTop":"10px","marginBottom":"4px"}),
                html.Div([
                    html.Div(f"{e}", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850","lineHeight":"1.35","marginBottom":"3px"})
                    for e in evidence[:4]
                ] if evidence else [
                    html.Div("No evidence details returned yet.", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850"})
                ]),
            ]),

            html.Div([
                html.Div("Risk Notes", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em","marginTop":"8px","marginBottom":"4px"}),
                html.Div([
                    html.Div(f"{r}", style={"fontSize":"12px","color":YELLOW_DIM,"fontWeight":"900","lineHeight":"1.45","marginBottom":"4px"})
                    for r in risk_notes[:3]
                ] if risk_notes else [
                    html.Div("Risk defined by setup invalidation.", style={"fontSize":"12px","color":WHITE,"fontWeight":"850","fontWeight":"850"})
                ]),
            ]),
        ], style={
            "border":f"1px solid {color}",
            "background":"linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.025))",
            "borderRadius":"18px",
            "padding":"16px",
            "boxShadow":"0 18px 42px rgba(0,0,0,.22)",
            "minHeight":"430px"
        })

    def _row(s):
        symbol = _safe_text(s.get("symbol"), "")
        score = _safe_float(s.get("composite_score", s.get("score")))
        readiness = _safe_float(s.get("readiness_score"))
        state = _safe_text(s.get("opportunity_state"), "Watching")
        transition = _compact_transition(s.get("transition_candidate"))
        behavioral_state = _safe_text(s.get("behavioral_state"), "—")
        side = _safe_text(s.get("trade_side"), _safe_text(s.get("side"), "—"))
        chg = _safe_float(s.get("change_pct"))
        price = s.get("price")
        trigger = s.get("trigger")
        invalidation = s.get("invalidation")
        setup = _safe_text(s.get("probability_setup_type", s.get("setup_type")), "—")
        status = _safe_text(s.get("status"), "—")
        hist_success = _safe_float(s.get("historical_success", s.get("historical_success_rate")))
        exp_return = _safe_float(s.get("expected_return", s.get("historical_expected_return")))
        edge_ratio = _safe_float(s.get("edge_ratio", s.get("historical_edge_ratio")))
        # FIX (2026-08-09): replaced the pooled-history probability_grade
        # (confirmed to leave most real symbols "Unrated" -- matched
        # against a fixed, unrelated 50-symbol historical backtest, not
        # this specific symbol) with the new, genuine, per-symbol
        # setup_grade -- built from the real sweep/exhaustion/reclaim
        # sequence plus range maturity for this exact symbol. Falls
        # back to the old value only if setup_grade wasn't computed at
        # all for this row (e.g. bar fetch failed for this symbol).
        setup_grade = s.get("setup_grade")
        setup_grade_reason = _safe_text(s.get("setup_grade_reason"), "")
        prob_grade = _safe_text(setup_grade or s.get("probability_grade", s.get("historical_grade")), "—")
        grade_tooltip = setup_grade_reason if setup_grade else "Legacy pooled-history grade (no setup-specific data available for this symbol)."
        setup_risk_reward = s.get("setup_risk_reward")
        wyckoff_verdict = s.get("wyckoff_verdict") if isinstance(s.get("wyckoff_verdict"), dict) else None
        livermore_verdict = s.get("livermore_verdict") if isinstance(s.get("livermore_verdict"), dict) else None
        weis_verdict = s.get("weis_verdict") if isinstance(s.get("weis_verdict"), dict) else None
        row_evidence = s.get("evidence") if isinstance(s.get("evidence"), list) else []
        row_risk_notes = s.get("risk_notes") if isinstance(s.get("risk_notes"), list) else []
        readiness_tooltip_lines = [f"+ {e}" for e in row_evidence] + [f"- {r}" for r in row_risk_notes]
        readiness_tooltip = "\n".join(readiness_tooltip_lines) if readiness_tooltip_lines else "No readiness evidence available yet."
        color = _state_color(state, readiness)
        side_color = _side_color(side)
        grade_color = TEAL_DIM if str(prob_grade).startswith("A") else (BLUE_DIM if str(prob_grade).startswith("B") else (YELLOW_DIM if str(prob_grade).startswith("C") else RED_DIM))

        return html.Div([
            html.Span(symbol, style={
                "flex":"0 0 72px","fontWeight":"950","fontSize":"13px",
                "color":WHITE,"fontFamily":"DM Mono, monospace"
            }),
            html.Span(_fmt_money(price), style={"flex":"0 0 92px","fontSize":"12px","fontWeight":"800","color":WHITE}),
            html.Span(_fmt_pct(chg, 2, signed=True), style={
                "flex":"0 0 74px","fontSize":"12px","fontWeight":"900",
                "color":TEAL_DIM if chg >= 0 else RED_DIM
            }),
            html.Span([
                html.Span(f"{readiness:.0f}"),
                html.Span(readiness_tooltip, className="sig-tooltip-text"),
            ], className="sig-tooltip", style={
                "flex":"0 0 72px","fontSize":"14px","fontWeight":"950",
                "color":color,"textAlign":"center","cursor":"help",
                "borderBottom":"1px dotted currentColor"
            }),
            html.Span(f"{score:.0f}", style={
                "flex":"0 0 58px","fontSize":"12px","fontWeight":"900",
                "color":YELLOW_DIM,"textAlign":"center"
            }),
            html.Span([
                html.Span(prob_grade),
                html.Span(grade_tooltip, className="sig-tooltip-text"),
            ], className="sig-tooltip", style={
                "flex":"0 0 62px","fontSize":"12px","fontWeight":"950",
                "color":grade_color,"textAlign":"center","cursor":"help",
                "borderBottom":"1px dotted currentColor"
            }),
            html.Span(_fmt_pct(hist_success, 1), style={
                "flex":"0 0 86px","fontSize":"12px","fontWeight":"900",
                "color":WHITE,"textAlign":"center"
            }),
            html.Span(_fmt_pct(exp_return, 2, signed=True), style={
                "flex":"0 0 92px","fontSize":"12px","fontWeight":"900",
                "color":TEAL_DIM if exp_return >= 0 else RED_DIM,"textAlign":"center"
            }),
            html.Span(f"{edge_ratio:.2f}", style={
                "flex":"0 0 72px","fontSize":"12px","fontWeight":"900",
                "color":YELLOW_DIM,"textAlign":"center"
            }),
            html.Span(state, style={
                "flex":"0 0 100px","fontSize":"10px","fontWeight":"950",
                "color":color,"textTransform":"uppercase","textAlign":"center"
            }),
            html.Span(side, style={
                "flex":"0 0 58px","fontSize":"10px","fontWeight":"950",
                "color":side_color,"textTransform":"uppercase","textAlign":"center"
            }),
            html.Span(transition, style={
                "flex":"1.4","fontSize":"11px","fontWeight":"850",
                "color":WHITE,"minWidth":"190px"
            }),
            html.Span(behavioral_state, style={
                "flex":"1.2","fontSize":"10px","fontWeight":"750",
                "color":BLUE_DIM,"minWidth":"160px"
            }),
            html.Span(setup, style={
                "flex":"1.1","fontSize":"10px","fontWeight":"750",
                "color":WHITE,"minWidth":"160px"
            }),
            html.Span(status, style={
                "flex":"0 0 82px","fontSize":"10px","fontWeight":"850",
                "color":WHITE,"textAlign":"center"
            }),
            html.Span(_fmt_money(trigger), style={
                "flex":"0 0 86px","fontSize":"10px","fontWeight":"900",
                "color":TEAL_DIM,"textAlign":"right"
            }),
            html.Span(_fmt_money(invalidation), style={
                "flex":"0 0 86px","fontSize":"10px","fontWeight":"900",
                "color":RED_DIM,"textAlign":"right"
            }),
            html.Span(
                f"{setup_risk_reward:.2f}" if isinstance(setup_risk_reward, (int, float)) else "—",
                style={
                    "flex":"0 0 66px","fontSize":"12px","fontWeight":"900",
                    "color": (TEAL_DIM if setup_risk_reward >= 2.0 else YELLOW_DIM) if isinstance(setup_risk_reward, (int, float)) else MUTED,
                    "textAlign":"center"
                },
            ),
            html.Span(
                f"{wyckoff_verdict.get('wyckoff_score', 0):.0f}" if wyckoff_verdict else "—",
                style={
                    "flex":"0 0 60px","fontSize":"11px","fontWeight":"900",
                    "color": TEAL_DIM if wyckoff_verdict else MUTED,
                    "textAlign":"center"
                },
            ),
            html.Span(
                f"{livermore_verdict.get('livermore_score', 0):.0f}" if livermore_verdict else "—",
                style={
                    "flex":"0 0 60px","fontSize":"11px","fontWeight":"900",
                    "color": BLUE_DIM if livermore_verdict else MUTED,
                    "textAlign":"center"
                },
            ),
            html.Span(
                f"{weis_verdict.get('weis_score', 0):.0f}" if weis_verdict else "—",
                style={
                    "flex":"0 0 60px","fontSize":"11px","fontWeight":"900",
                    "color": YELLOW_DIM if weis_verdict else MUTED,
                    "textAlign":"center"
                },
            ),
        ], style={
            "display":"flex","alignItems":"center","gap":"10px",
            "padding":"11px 0","borderBottom":f"1px solid {BORDER}",
            "minWidth":"1900px"
        })

    header = html.Div([
        html.Span("Symbol", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em"}),
        html.Span("Price", style={"flex":"0 0 92px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em"}),
        html.Span("Chg%", style={"flex":"0 0 74px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em"}),
        html.Span("Ready", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Score", style={"flex":"0 0 58px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Grade", style={"flex":"0 0 62px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Hist %", style={"flex":"0 0 86px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Exp Ret", style={"flex":"0 0 92px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Edge", style={"flex":"0 0 72px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("State", style={"flex":"0 0 100px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Side", style={"flex":"0 0 58px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Transition", style={"flex":"1.4","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","minWidth":"190px"}),
        html.Span("Behavior", style={"flex":"1.2","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","minWidth":"160px"}),
        html.Span("Setup", style={"flex":"1.1","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","minWidth":"160px"}),
        html.Span("Status", style={"flex":"0 0 82px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Trigger", style={"flex":"0 0 86px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"}),
        html.Span("Invalid", style={"flex":"0 0 86px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"}),
        html.Span("R:R", style={"flex":"0 0 66px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Wyckoff", style={"flex":"0 0 60px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Livermore", style={"flex":"0 0 60px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
        html.Span("Weis", style={"flex":"0 0 60px","fontSize":"9px","color":WHITE,"fontWeight":"900","textTransform":"uppercase","letterSpacing":".08em","textAlign":"center"}),
    ], style={
        "display":"flex","gap":"10px","paddingBottom":"8px",
        "borderBottom":f"1px solid {BORDER}","marginBottom":"4px",
        "minWidth":"1900px"
    })

    # Backend already sorts by opportunity state and readiness. Keep first 3 as hero cards.
    hero = signals[:3] if isinstance(signals, list) else []
    armed_count = sum(1 for s in signals if _safe_text(s.get("opportunity_state")).lower() == "armed")
    setup_count = sum(1 for s in signals if "setting" in _safe_text(s.get("opportunity_state")).lower())
    elite_count = sum(1 for s in signals if _safe_float(s.get("readiness_score")) >= 90)
    avg_ready = sum(_safe_float(s.get("readiness_score")) for s in signals) / max(len(signals), 1)

    return html.Div([
        card([
            html.Div([
                html.Div([
                    html.H2("Opportunity Dashboard", style={
                        "color":WHITE,"fontSize":"20px","fontWeight":"950","margin":"0 0 4px"
                    }),
                    html.P("Pre-trigger trade discovery — ranked by opportunity state, readiness, and behavioral transition.",
                           style={"color":WHITE,"fontSize":"13px","margin":"0"}),
                ]),
                html.Div([
                    html.Div(f"{len(signals)}", style={"fontSize":"20px","fontWeight":"950","color":WHITE,"textAlign":"right"}),
                    html.Div("Candidates", style={"fontSize":"10px","fontWeight":"950","color":WHITE,"textTransform":"uppercase","letterSpacing":".08em","textAlign":"right"}),
                ]),
            ], style={"display":"flex","justifyContent":"space-between","gap":"14px","alignItems":"flex-start","marginBottom":"16px"}),

            html.Div([
                metric_tile("Armed", armed_count, "pre-trigger candidates", "green"),
                metric_tile("Setting Up", setup_count, "forming opportunities", "blue"),
                metric_tile("Elite 90+", elite_count, "highest readiness", "yellow"),
                metric_tile("Avg Ready", f"{avg_ready:.0f}", f"sort: {sort_mode}", "purple"),
            ], style={"display":"grid","gridTemplateColumns":"repeat(4, 1fr)","gap":"12px","marginBottom":"18px"}),

            html.Div([
                html.H3("Top Opportunities", style={
                    "color":WHITE,"fontSize":"15px","fontWeight":"950","margin":"0 0 10px"
                }),
                html.Div([
                    _opportunity_card(s, i+1) for i, s in enumerate(hero)
                ] if hero else [
                    html.Div("No opportunities returned yet.", style={"color":WHITE,"fontSize":"13px","padding":"18px"})
                ], style={"display":"grid","gridTemplateColumns":"repeat(3, 1fr)","gap":"14px"}),
            ]),

            html.Div(style={"height":"20px"}),

            html.Div([
                html.H3("Full Opportunity Radar", style={
                    "color":WHITE,"fontSize":"15px","fontWeight":"950","margin":"0 0 4px"
                }),
                html.Div("Sorted by Armed → Setting Up → Historical Probability → Readiness. Use this table to see what may move next, not what already moved.",
                         style={"fontSize":"12px","color":WHITE,"fontWeight":"850","marginBottom":"4px"}),
                html.Div("⟷ Scroll right for more columns, including Trigger, Invalid, R:R, Wyckoff, Livermore, and Weis",
                         style={"fontSize":"11px","color":YELLOW_DIM,"fontWeight":"800","marginBottom":"12px"}),
                html.Div([
                    header,
                    html.Div([_row(s) for s in signals] if signals else [
                        html.Div("No signals available. Backend may be initializing or market is closed.",
                                 style={"color":WHITE,"fontSize":"13px","padding":"24px 0","textAlign":"center"})
                    ]),
                ], style={"overflowX":"auto"}),
            ]),
        ]),
    ])