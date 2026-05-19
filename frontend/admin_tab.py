"""
frontend/admin_tab.py
---------------------
Private admin performance monitoring tab.
Only renders when session email == greg.kosmala@gmail.com.

Paste this file into your frontend/ directory,
then follow the integration instructions at the bottom.
"""

from dash import html
import requests as _req

# ── Copy these brand tokens from app.py ──────────────────────────────────────
NAVY      = "#0d1b2e"
NAVY_CARD = "#111f35"
NAVY_MID  = "#0f172a"
NAVY3     = "#1a2744"
TEAL      = "#2d8f6f"
TEAL_DIM  = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"
RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW    = "#f59e0b"
YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"
MUTED     = "#64748b"
TEXT      = "#94a3b8"
WHITE     = "#f1f5f9"
BORDER    = "rgba(255,255,255,.08)"
BORDER_T  = "rgba(45,143,111,.35)"
GOLD      = "#F5C842"

ADMIN_EMAIL = "greg.kosmala@gmail.com"


def is_admin(session: dict) -> bool:
    return (session or {}).get("email","") == ADMIN_EMAIL


def _card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
         "borderRadius": "16px", "padding": "20px",
         "boxShadow": "0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Div(children, style=s)


def _tile(label, value, color=WHITE, sub=None):
    return html.Div([
        html.Div(label, style={"fontSize":"10px","color":TEXT,"fontWeight":"700",
                               "textTransform":"uppercase","letterSpacing":".12em","marginBottom":"6px"}),
        html.Div(value, style={"fontSize":"22px","fontWeight":"900","color":color,"lineHeight":"1"}),
        html.Div(sub,   style={"fontSize":"10px","color":MUTED,"marginTop":"4px"}) if sub else html.Div(),
    ], style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px"})


def _grade_color(grade):
    if not grade: return MUTED
    g = grade.upper()
    if g.startswith("A"):  return TEAL_DIM
    if g.startswith("B"):  return BLUE_DIM
    if g == "C":           return YELLOW_DIM
    if g == "F":           return RED_DIM
    return MUTED


def _severity_color(sev):
    return {"ERROR": RED_DIM, "WARN": YELLOW_DIM, "INFO": BLUE_DIM}.get(sev, TEXT)


def _score_bar(value, width="100%"):
    pct   = max(0, min(100, value))
    color = TEAL_DIM if pct >= 70 else (YELLOW_DIM if pct >= 50 else RED_DIM)
    return html.Div([
        html.Div(style={
            "width": f"{pct}%", "height": "100%",
            "background": f"linear-gradient(90deg,#ef4444,{YELLOW},{TEAL_DIM})",
            "borderRadius": "999px",
        }),
    ], style={"height":"5px","background":"rgba(255,255,255,.08)",
               "borderRadius":"999px","overflow":"hidden","width":width})


def build_admin_tab(session: dict, backend_url: str) -> html.Div:
    """
    Build the full admin monitoring page.
    Returns a 403 message if not admin.
    """
    if not is_admin(session):
        return html.Div([
            html.Div("🔒", style={"fontSize":"48px","marginBottom":"16px"}),
            html.Div("Admin Access Only", style={"fontSize":"18px","fontWeight":"800","color":WHITE}),
            html.Div("This page is only accessible to the system administrator.",
                     style={"fontSize":"13px","color":TEXT,"marginTop":"8px"}),
        ], style={"textAlign":"center","padding":"80px 20px"})

    # ── Fetch report from backend ─────────────────────────────────────────
    try:
        token = session.get("access_token","")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        r = _req.get(f"{backend_url}/api/admin/report", headers=headers, timeout=15)
        data = r.json() if r.ok else {}
    except Exception as e:
        data = {}

    if not data:
        return _card([
            html.Div("⚠️ Could not load admin report.", style={"color":YELLOW_DIM,"fontSize":"14px"}),
            html.Div("Backend may be initializing. Refresh in 30 seconds.",
                     style={"color":TEXT,"fontSize":"12px","marginTop":"8px"}),
        ])

    live          = data.get("live_stats", {})
    accuracy      = data.get("accuracy_stats", {})
    snap_health   = data.get("snapshot_health", {})
    top_scores    = data.get("top_scores", [])
    top_movers    = data.get("top_movers", [])
    anomalies     = data.get("anomalies", [])
    narrative     = data.get("narrative","—")
    daily_grades  = data.get("daily_grades", [])
    regimes       = data.get("regime_distribution", {})
    generated_at  = data.get("generated_at","")

    # Format timestamp
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(generated_at.replace("Z","+00:00"))
        gen_label = dt.strftime("%b %d, %Y  %I:%M %p UTC")
    except:
        gen_label = generated_at

    # ── Header ────────────────────────────────────────────────────────────
    header = _card([
        html.Div([
            html.Div([
                html.Div([
                    html.Span("🔒 ", style={"fontSize":"18px"}),
                    html.Span("ADMIN PERFORMANCE MONITOR",
                              style={"fontSize":"16px","fontWeight":"900","color":GOLD,
                                     "letterSpacing":".08em"}),
                ], style={"display":"flex","alignItems":"center","gap":"8px","marginBottom":"4px"}),
                html.Div("Private · Internal Use Only · Sigmalytic Quant Corporation",
                         style={"fontSize":"11px","color":MUTED,"letterSpacing":".06em"}),
            ]),
            html.Div([
                html.Span(snap_health.get("status","—"), style={
                    "fontSize":"10px","fontWeight":"800",
                    "color": TEAL_DIM if "Active" in snap_health.get("status","") else YELLOW_DIM,
                    "border": f"1px solid {BORDER_T}","borderRadius":"999px",
                    "padding":"4px 12px","background":TEAL_GLOW,
                }),
                html.Div(f"Generated: {gen_label}",
                         style={"fontSize":"10px","color":MUTED,"marginTop":"4px","textAlign":"right"}),
            ]),
        ], style={"display":"flex","justifyContent":"space-between","alignItems":"flex-start"}),
    ], sx={"borderColor": "rgba(245,200,66,.3)", "marginBottom":"16px"})

    # ── Accuracy stats block (mirrors your PDF scoreboard) ───────────────
    hit  = accuracy.get("hit_rate", 0)
    conf = accuracy.get("conf_rate", 0)
    neut = accuracy.get("neutral_rate", 0)
    miss = accuracy.get("miss_rate", 0)
    perf_num = accuracy.get("a_grade",0)
    perf_den = accuracy.get("total",0)

    accuracy_block = _card([
        html.Div("CLOSED-LOOP PERFORMANCE AUDIT",
                 style={"fontSize":"10px","fontWeight":"900","color":GOLD,
                        "letterSpacing":".2em","textTransform":"uppercase","marginBottom":"16px"}),
        html.Div([
            _tile("CONF",  f"{conf:.0f}%", TEAL_DIM,  "A-grade rate"),
            _tile("HIT",   f"{hit:.0f}%",  TEAL_DIM,  "A + B rate"),
            _tile("NEUTRAL",f"{neut:.0f}%",YELLOW_DIM,"C rate"),
            _tile("MISS",  f"{miss:.0f}%", RED_DIM,   "F rate"),
            _tile("PERF",  f"{perf_num}/{perf_den}" if perf_den else "—",
                  GOLD,   "A grades / total"),
            _tile("SYMBOLS",str(live.get("total_symbols",0)), BLUE_DIM, "in universe"),
            _tile("ARMED",  str(live.get("armed",0)),   TEAL_DIM, "live now"),
            _tile("TRIGGERED",str(live.get("triggered",0)),BLUE_DIM,"live now"),
        ], style={"display":"grid","gridTemplateColumns":"repeat(8,1fr)","gap":"10px"}),
    ], sx={"marginBottom":"16px","borderColor":"rgba(245,200,66,.2)"})

    # ── Snapshot writer health ────────────────────────────────────────────
    snap_block = _card([
        html.Div([
            html.Div("📸 SNAPSHOT WRITER", style={"fontSize":"12px","fontWeight":"800",
                      "color":WHITE,"marginBottom":"4px"}),
            html.Div([
                html.Span("Status: ", style={"color":MUTED,"fontSize":"11px"}),
                html.Span(snap_health.get("status","—"),
                          style={"color": TEAL_DIM if "Active" in snap_health.get("status","") else YELLOW_DIM,
                                 "fontWeight":"700","fontSize":"11px"}),
                html.Span("  ·  Last write: ", style={"color":MUTED,"fontSize":"11px","marginLeft":"12px"}),
                html.Span(snap_health.get("last_write","—")[:19] if snap_health.get("last_write") else "—",
                          style={"color":TEXT,"fontSize":"11px"}),
                html.Span("  ·  Writes in last 10 min: ", style={"color":MUTED,"fontSize":"11px","marginLeft":"12px"}),
                html.Span(str(snap_health.get("recent_count",0)),
                          style={"color":TEAL_DIM,"fontWeight":"700","fontSize":"11px"}),
            ]),
        ]),
    ], sx={"marginBottom":"16px","padding":"14px 20px"})

    # ── Narrative block ───────────────────────────────────────────────────
    narrative_block = _card([
        html.Div("REGIME NARRATIVE", style={"fontSize":"10px","fontWeight":"900","color":GOLD,
                  "letterSpacing":".2em","marginBottom":"12px"}),
        html.Div(narrative, style={"fontSize":"14px","color":WHITE,"lineHeight":"1.7",
                                   "fontStyle":"italic"}),

        html.Div(style={"height":"16px"}),

        # Regime distribution pills
        html.Div("REGIME DISTRIBUTION", style={"fontSize":"10px","fontWeight":"700","color":MUTED,
                  "letterSpacing":".16em","marginBottom":"8px"}),
        html.Div([
            html.Div([
                html.Span(regime, style={"fontSize":"11px","fontWeight":"700","color":WHITE,
                                         "marginRight":"6px"}),
                html.Span(f"{count}", style={"fontSize":"11px","color":TEAL_DIM,"fontWeight":"900"}),
            ], style={"background":"rgba(0,0,0,.3)","border":f"1px solid {BORDER}",
                       "borderRadius":"999px","padding":"4px 12px","display":"inline-flex",
                       "alignItems":"center","marginRight":"6px","marginBottom":"4px"})
            for regime, count in sorted(regimes.items(), key=lambda x: x[1], reverse=True)
        ], style={"display":"flex","flexWrap":"wrap"}),
    ], sx={"marginBottom":"16px"})

    # ── Anomaly flags ─────────────────────────────────────────────────────
    anomaly_rows = []
    for a in anomalies:
        sev_color = _severity_color(a.get("severity","INFO"))
        anomaly_rows.append(html.Div([
            html.Span(a.get("severity",""), style={
                "fontSize":"9px","fontWeight":"900","color":sev_color,
                "border":f"1px solid {sev_color}","borderRadius":"4px",
                "padding":"2px 6px","marginRight":"10px","minWidth":"40px",
                "textAlign":"center","display":"inline-block",
            }),
            html.Span(a.get("symbol",""), style={
                "fontSize":"11px","fontWeight":"800","color":WHITE,
                "fontFamily":"monospace","marginRight":"10px","minWidth":"60px",
                "display":"inline-block",
            }),
            html.Span(a.get("message",""), style={"fontSize":"12px","color":TEXT}),
        ], style={"padding":"8px 0","borderBottom":f"1px solid {BORDER}",
                  "display":"flex","alignItems":"center"}))

    anomaly_block = _card([
        html.Div([
            html.Div("🚨 ANOMALY FLAGS", style={"fontSize":"12px","fontWeight":"800","color":WHITE}),
            html.Div(f"{len(anomalies)} issues detected",
                     style={"fontSize":"11px","color": RED_DIM if anomalies else TEAL_DIM}),
        ], style={"display":"flex","justifyContent":"space-between","marginBottom":"12px"}),
        html.Div(anomaly_rows if anomaly_rows else [
            html.Div("✅ No anomalies detected — system running clean.",
                     style={"color":TEAL_DIM,"fontSize":"13px","padding":"12px 0"})
        ]),
    ], sx={"marginBottom":"16px"})

    # ── Top 10 scores table ───────────────────────────────────────────────
    def _sym_row(s):
        score = s.get("composite_score", 0)
        sc    = TEAL_DIM if score >= 70 else (YELLOW_DIM if score >= 50 else RED_DIM)
        chg   = s.get("change_pct", 0)
        return html.Div([
            html.Span(s.get("symbol",""), style={
                "flex":"1","fontWeight":"800","fontSize":"13px","color":WHITE,
                "fontFamily":"monospace",
            }),
            html.Span(f"${s.get('price',0):,.2f}", style={
                "flex":"1","fontSize":"12px","color":TEXT,
            }),
            html.Span(f"{chg:+.2f}%", style={
                "flex":"1","fontSize":"12px","fontWeight":"700",
                "color": TEAL_DIM if chg >= 0 else RED_DIM,
            }),
            html.Div([
                html.Span(f"{score:.0f}", style={"fontSize":"13px","fontWeight":"900","color":sc}),
                _score_bar(score, width="80px"),
            ], style={"flex":"1"}),
            html.Span(f"C:{s.get('confluence',0):.0f} E:{s.get('expansion_node',0):.0f} "
                      f"RS:{s.get('relative_strength',0):.0f} VP:{s.get('volume_pressure',0):.0f} "
                      f"B:{s.get('behavioral',0):.0f}",
                      style={"flex":"2","fontSize":"10px","color":sc,"fontFamily":"monospace"}),
            html.Span(s.get("status",""), style={
                "flex":"1","fontSize":"10px","fontWeight":"700","color":sc,
            }),
            html.Span(s.get("regime",""), style={
                "flex":"1","fontSize":"10px","color":MUTED,
            }),
        ], style={"display":"flex","alignItems":"center","gap":"12px",
                  "padding":"10px 0","borderBottom":f"1px solid {BORDER}"})

    score_table = _card([
        html.Div("🏆 TOP 10 — COMPOSITE SCORE", style={"fontSize":"12px","fontWeight":"800",
                  "color":WHITE,"marginBottom":"12px"}),
        # Header
        html.Div([
            html.Span("Symbol",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Price",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Chg%",     style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Score",    style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Dimensions (C E RS VP B)", style={"flex":"2","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Status",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
            html.Span("Regime",   style={"flex":"1","fontSize":"9px","color":MUTED,"fontWeight":"700","textTransform":"uppercase","letterSpacing":".1em"}),
        ], style={"display":"flex","gap":"12px","paddingBottom":"8px",
                  "borderBottom":f"1px solid {BORDER}","marginBottom":"4px"}),
        html.Div([_sym_row(s) for s in top_scores]),
    ], sx={"marginBottom":"16px"})

    # ── Historical daily grade grid ────────────────────────────────────────
    # Get all unique symbols across all dates
    all_syms_set = set()
    for day in daily_grades:
        all_syms_set.update(day.get("symbols",{}).keys())
    all_syms = sorted(all_syms_set)

    if daily_grades and all_syms:
        # Table header row — dates
        date_headers = [
            html.Th("Symbol", style={"padding":"6px 10px","textAlign":"left",
                                      "fontSize":"9px","color":MUTED,"fontWeight":"700",
                                      "textTransform":"uppercase","letterSpacing":".1em",
                                      "background":NAVY_MID,"position":"sticky","left":0}),
        ] + [
            html.Th(day["date"][5:],  # MM-DD
                    style={"padding":"6px 10px","textAlign":"center","minWidth":"56px",
                           "fontSize":"9px","color":MUTED,"fontWeight":"700",
                           "textTransform":"uppercase","letterSpacing":".06em",
                           "background":NAVY_MID})
            for day in daily_grades
        ]

        # Symbol rows
        table_rows = []
        for sym in all_syms:
            cells = [
                html.Td(sym, style={"padding":"6px 10px","fontWeight":"800","fontSize":"12px",
                                     "color":WHITE,"fontFamily":"monospace",
                                     "background":NAVY_MID,"position":"sticky","left":0,
                                     "borderRight":f"1px solid {BORDER}"}),
            ]
            for day in daily_grades:
                sym_data = day.get("symbols",{}).get(sym)
                if sym_data:
                    grade = sym_data.get("grade","—")
                    gc    = _grade_color(grade)
                    cells.append(html.Td(
                        html.Div([
                            html.Div(grade or "—", style={"fontSize":"12px","fontWeight":"900",
                                                           "color":gc,"lineHeight":"1"}),
                            html.Div(f"{sym_data.get('score',0):.0f}",
                                     style={"fontSize":"9px","color":MUTED,"marginTop":"2px"}),
                        ], style={"textAlign":"center"}),
                        style={"padding":"5px 8px","background":f"{gc}12",
                               "borderLeft":f"1px solid rgba(255,255,255,.04)"},
                    ))
                else:
                    cells.append(html.Td("—", style={"padding":"5px 8px","textAlign":"center",
                                                       "color":MUTED,"fontSize":"11px"}))
            table_rows.append(html.Tr(cells, style={"borderBottom":f"1px solid {BORDER}"}))

        grade_grid = _card([
            html.Div([
                html.Div("📋 CUMULATIVE SCOREBOARD — DAILY GRADE GRID",
                         style={"fontSize":"12px","fontWeight":"800","color":WHITE}),
                html.Div("Grade / Score · A=Full target · B=Partial · C=Neutral · F=Miss",
                         style={"fontSize":"10px","color":MUTED,"marginTop":"4px"}),
            ], style={"marginBottom":"16px"}),
            html.Div([
                html.Table([
                    html.Thead(html.Tr(date_headers,
                               style={"borderBottom":f"1px solid {BORDER}"})),
                    html.Tbody(table_rows),
                ], style={"width":"100%","borderCollapse":"collapse",
                          "fontSize":"12px","color":WHITE}),
            ], style={"overflowX":"auto","maxHeight":"480px","overflowY":"auto",
                      "border":f"1px solid {BORDER}","borderRadius":"10px"}),

            html.Div([
                html.Span("* Starred dates = Pinning Report validation days",
                          style={"fontSize":"10px","color":MUTED,"fontStyle":"italic"}),
            ], style={"marginTop":"12px"}),
        ], sx={"marginBottom":"16px"})
    else:
        grade_grid = _card([
            html.Div("📋 CUMULATIVE SCOREBOARD", style={"fontSize":"12px","fontWeight":"800",
                      "color":WHITE,"marginBottom":"8px"}),
            html.Div("No daily close snapshots yet. The grade grid will populate automatically "
                     "after 4:15 PM ET on the first trading day with the snapshot writer active.",
                     style={"fontSize":"13px","color":TEXT,"lineHeight":"1.7"}),
        ], sx={"marginBottom":"16px"})

    # ── Assemble full page ────────────────────────────────────────────────
    return html.Div([
        header,
        accuracy_block,
        snap_block,
        narrative_block,

        # Two-column row: anomalies + top scores
        html.Div([
            html.Div(anomaly_block, style={"flex":"1","minWidth":"0"}),
        ], style={"marginBottom":"0"}),

        score_table,
        grade_grid,

        # Footer
        html.Div("SIGMALYTIC QUANT CORPORATION  ·  PROPRIETARY & CONFIDENTIAL  ·  INTERNAL USE ONLY",
                 style={"textAlign":"center","fontSize":"9px","color":MUTED,
                        "letterSpacing":".2em","paddingTop":"16px","paddingBottom":"8px"}),
    ])