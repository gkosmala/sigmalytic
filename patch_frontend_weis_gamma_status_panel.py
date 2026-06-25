from pathlib import Path

path = Path("frontend/app.py")
text = path.read_text(encoding="utf-8")

helper = '''
# Weis-Gamma Status Center display cache.
_WEIS_GAMMA_STATUS_CACHE = {
    "as_of": None,
    "data": None,
}


def _cached_campaign_summary(ttl_seconds: int = 30):
    now = datetime.now(timezone.utc)
    cached_at = _WEIS_GAMMA_STATUS_CACHE.get("as_of")

    if cached_at is not None:
        try:
            age = (now - cached_at).total_seconds()
            if age < ttl_seconds and isinstance(_WEIS_GAMMA_STATUS_CACHE.get("data"), dict):
                return _WEIS_GAMMA_STATUS_CACHE.get("data") or {}
        except Exception:
            pass

    data = _get("/api/campaigns/summary")

    if not isinstance(data, dict) or not data:
        data = _get("/api/campaign/status")

    if isinstance(data, dict):
        _WEIS_GAMMA_STATUS_CACHE["as_of"] = now
        _WEIS_GAMMA_STATUS_CACHE["data"] = data
        return data

    return {}


def _wg_metric_card(label, value, color=WHITE):
    return html.Div([
        html.Div(str(label), style={
            "fontSize": "11px",
            "color": WHITE,
            "fontWeight": "800",
            "letterSpacing": ".08em",
            "textTransform": "uppercase",
            "opacity": ".85",
        }),
        html.Div(str(value), style={
            "fontSize": "24px",
            "lineHeight": "1.1",
            "color": color,
            "fontWeight": "900",
            "marginTop": "6px",
        }),
    ], style={
        "background": "rgba(8,24,39,.72)",
        "border": f"1px solid {BORDER}",
        "borderRadius": "14px",
        "padding": "12px",
        "minHeight": "76px",
    })


def _wg_counts_text(counts):
    if not isinstance(counts, dict) or not counts:
        return "-"

    parts = []
    for key, value in counts.items():
        parts.append(f"{key}: {value}")

    return " | ".join(parts)


def build_weis_gamma_status_center_panel():
    summary = _cached_campaign_summary()
    wg = summary.get("weis_gamma_status_center") or {}

    if not wg:
        return html.Div([
            html.Div("Weis-Gamma Status Center", style={
                "fontSize": "14px",
                "fontWeight": "900",
                "color": WHITE,
                "marginBottom": "6px",
            }),
            html.Div("Waiting for Weis-Gamma status data from backend.", style={
                "fontSize": "12px",
                "color": WHITE,
                "opacity": ".85",
            }),
        ], style={
            "border": f"1px solid {BORDER}",
            "background": "rgba(8,24,39,.60)",
            "borderRadius": "18px",
            "padding": "16px",
            "marginBottom": "16px",
        })

    total = wg.get("total_campaigns", summary.get("active_campaigns", 0))
    present = wg.get("weis_gamma_present", 0)
    missing = wg.get("weis_gamma_missing", 0)
    transition_enabled = wg.get("transition_enabled", 0)
    no_option_chain = wg.get("gamma_no_option_chain", 0)
    stale = wg.get("gamma_stale_or_unconfirmed", 0)

    phase_counts = wg.get("phase_counts") or {}
    rank_counts = wg.get("rank_bucket_counts") or {}
    gamma_counts = wg.get("gamma_status_counts") or {}
    fusion_counts = wg.get("fusion_state_counts") or {}

    safety_color = TEAL_DIM if int(transition_enabled or 0) == 0 else RED_DIM

    return html.Div([
        html.Div([
            html.Div([
                html.Div("Weis-Gamma Status Center", style={
                    "fontSize": "16px",
                    "fontWeight": "900",
                    "color": WHITE,
                }),
                html.Div("Read-only intelligence overlay. Lifecycle transitions remain disabled.", style={
                    "fontSize": "12px",
                    "color": WHITE,
                    "opacity": ".85",
                    "marginTop": "4px",
                }),
            ]),
            html.Div("TRANSITIONS OFF", style={
                "fontSize": "11px",
                "fontWeight": "900",
                "color": safety_color,
                "border": f"1px solid {safety_color}",
                "borderRadius": "999px",
                "padding": "6px 10px",
            }),
        ], style={
            "display": "flex",
            "justifyContent": "space-between",
            "gap": "12px",
            "alignItems": "center",
            "marginBottom": "14px",
        }),

        html.Div([
            _wg_metric_card("Total Campaigns", total, WHITE),
            _wg_metric_card("Weis-Gamma Present", present, TEAL_DIM),
            _wg_metric_card("Missing", missing, YELLOW_DIM),
            _wg_metric_card("Transition Enabled", transition_enabled, safety_color),
            _wg_metric_card("No Option Chain", no_option_chain, YELLOW_DIM),
            _wg_metric_card("Stale / Unconfirmed", stale, RED_DIM),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))",
            "gap": "10px",
        }),

        html.Div([
            html.Div([
                html.Div("Phase Counts", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(phase_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Rank Buckets", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(rank_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Gamma Status", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(gamma_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Fusion State", style={"fontSize": "11px", "fontWeight": "900", "color": WHITE}),
                html.Div(_wg_counts_text(fusion_counts), style={"fontSize": "12px", "color": WHITE, "marginTop": "4px"}),
            ]),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fit, minmax(220px, 1fr))",
            "gap": "10px",
            "marginTop": "12px",
        }),
    ], style={
        "border": "1px solid rgba(45,212,191,.30)",
        "background": "rgba(8,24,39,.72)",
        "borderRadius": "18px",
        "padding": "16px",
        "marginBottom": "16px",
        "boxShadow": "0 0 0 1px rgba(45,212,191,.08) inset",
    })
'''

if "def build_weis_gamma_status_center_panel" not in text:
    marker = "\ndef _post(path, body):"
    if marker not in text:
        raise SystemExit("Could not find _post insertion marker.")
    text = text.replace(marker, "\n" + helper + marker, 1)

old_command = '''        return (build_command_tab(live, candles or _init_candles, symbol, tf),
                SHOWN, trade_plan, active_pane)'''

new_command = '''        return (html.Div([
                    build_weis_gamma_status_center_panel(),
                    build_command_tab(live, candles or _init_candles, symbol, tf),
                ], style={"display":"flex","flexDirection":"column","gap":"16px"}),
                SHOWN, trade_plan, active_pane)'''

if old_command not in text:
    raise SystemExit("Could not find command tab return block.")

text = text.replace(old_command, new_command, 1)

old_admin = '''    elif tab=="admin":       main = build_admin_tab(session={}, backend_url=BACKEND_HTTP)'''

new_admin = '''    elif tab=="admin":
        main = html.Div([
            build_weis_gamma_status_center_panel(),
            build_admin_tab(session={}, backend_url=BACKEND_HTTP),
        ], style={"display":"flex","flexDirection":"column","gap":"16px"})'''

if old_admin not in text:
    raise SystemExit("Could not find admin tab block.")

text = text.replace(old_admin, new_admin, 1)

path.write_text(text, encoding="utf-8")

print("Patched frontend/app.py with Weis-Gamma Status Center panel.")
