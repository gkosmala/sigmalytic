from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

old = '''@app.callback(
    Output("main-content",       "children"),
    Output("trade-panels-row",   "style"),
    Output("trade-plan-panel",   "children"),
    Output("active-trade-panel", "children"),
    Input("s-live","data"), Input("s-candles","data"), Input("s-tab","data"),
    Input("s-live-mode","data"), Input("i-clock","n_intervals"),
    State("s-symbol","data"), State("s-tf","data"),
)
def render_main(live,candles,tab,live_mode,_clock,symbol,tf):'''

new = '''@app.callback(
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
def render_main(tab, live, candles, live_mode, symbol, tf):'''

if old not in text:
    raise SystemExit("Could not find the slow render_main callback block. Do not deploy. Upload the current file.")

text = text.replace(old, new, 1)

# Remove the old clock-only guard because i-clock is no longer an input to render_main.
text = re.sub(
    r'\n    # Static tabs: only skip rebuild when clock fires AND tab hasn\'t changed\n'
    r'    _STATIC_TABS = \{.*?\}\n'
    r'    triggered = \[t\["prop_id"\] for t in dash\.callback_context\.triggered\]\n'
    r'    tab_changed = any\("s-tab" in t for t in triggered\)\n'
    r'    clock_only = all\("i-clock" in t for t in triggered\)\n'
    r'    if clock_only and tab in _STATIC_TABS and not tab_changed:\n'
    r'        return no_update, no_update, no_update, no_update\n',
    '\n    _STATIC_TABS = {"campaigns","portfolio","journal","scoreboard","divergence",\n'
    '                    "billing","preferences","admin","setup","behavior","import","radar","status"}\n',
    text,
    count=1,
    flags=re.DOTALL
)

path.write_text(text, encoding="utf-8")
print("FAST TAB CALLBACK RESTORED")
