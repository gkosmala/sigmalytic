from pathlib import Path

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

# 1) Replace set_tab so tab clicks immediately paint the page with a fast shell.
start = text.find('@app.callback(\n    Output("s-tab","data"),')
if start == -1:
    start = text.find('@app.callback(\n    Output("s-tab", "data"),')
if start == -1:
    raise SystemExit("FAILED: could not find set_tab callback start.")

end = text.find('@app.callback(\n    Output("s-live","data")', start)
if end == -1:
    end = text.find('@app.callback(\n    Output("s-live", "data")', start)
if end == -1:
    raise SystemExit("FAILED: could not find tick callback after set_tab.")

new_set_tab = '''@app.callback(
    Output("s-tab","data"),
    Output("main-content","children", allow_duplicate=True),
    Output("trade-panels-row","style", allow_duplicate=True),
    Output("trade-plan-panel","children", allow_duplicate=True),
    Output("active-trade-panel","children", allow_duplicate=True),
    Input("tab-status","n_clicks"),       Input("tab-command","n_clicks"),
    Input("tab-feed","n_clicks"),         Input("tab-performance","n_clicks"),
    Input("tab-behavior","n_clicks"),     Input("tab-campaigns","n_clicks"),
    Input("tab-portfolio","n_clicks"),    Input("tab-journal","n_clicks"),
    Input("tab-import","n_clicks"),       Input("tab-radar","n_clicks"),
    Input("tab-scoreboard","n_clicks"),   Input("tab-divergence","n_clicks"),
    Input("tab-billing","n_clicks"),      Input("tab-preferences","n_clicks"),
    Input("tab-admin","n_clicks"),        Input("tab-setup","n_clicks"),
    prevent_initial_call=True,
)
def set_tab(*_):
    ctx = callback_context
    if not ctx.triggered:
        return no_update, no_update, no_update, no_update, no_update

    tab = ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")

    fast_shell = html.Div([
        html.Div("Loading " + tab.replace("_"," ").title() + "…",
                 style={"color":WHITE,"fontSize":"15px","fontWeight":"800","marginBottom":"8px"}),
        html.Div("Preparing view.",
                 style={"color":MUTED,"fontSize":"12px"}),
    ], style={
        "background":NAVY_CARD,
        "border":f"1px solid {BORDER}",
        "borderRadius":"20px",
        "padding":"28px",
        "minHeight":"160px",
        "boxShadow":"0 8px 32px rgba(0,0,0,.32)",
    })

    return tab, fast_shell, {"display":"none"}, no_update, no_update


'''

text = text[:start] + new_set_tab + text[end:]


# 2) Make render_main fire from tab changes only, not live ticks / candles / clock.
start = text.find('@app.callback(\n    Output("main-content"')
if start == -1:
    raise SystemExit("FAILED: could not find render_main callback start.")

def_start = text.find('def render_main(', start)
if def_start == -1:
    raise SystemExit("FAILED: could not find render_main function.")

def_end = text.find('):', def_start)
if def_end == -1:
    raise SystemExit("FAILED: could not find render_main signature end.")
def_end += 2

new_render_header = '''@app.callback(
    Output("main-content",       "children"),
    Output("trade-panels-row",   "style"),
    Output("trade-plan-panel",   "children"),
    Output("active-trade-panel", "children"),
    Input("s-tab","data"),
    State("s-live","data"),
    State("s-candles","data"),
    State("s-live-mode","data"),
    State("s-symbol","data"),
    State("s-tf","data"),
)
def render_main(tab, live, candles, live_mode, symbol, tf, session=None):'''

text = text[:start] + new_render_header + text[def_end:]

path.write_text(text, encoding="utf-8")
print("FAST TAB RESPONSE PATCH OK")
