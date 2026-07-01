from pathlib import Path

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# V2_PREF_ADMIN_CLICK_DIRECT_ONLY
# Only changes Preferences/Admin click behavior inside set_tab.
# Other tabs/screens are left alone.

needle = '''    tab = ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")

    fast_shell = html.Div(['''

insert = '''    tab = ctx.triggered[0]["prop_id"].replace(".n_clicks","").replace("tab-","")

    if tab == "preferences":
        try:
            pref_view = build_preferences_tab(user_id=USER_ID, session=None)
        except Exception as e:
            pref_view = html.Div([
                html.Div("Preferences tab error", style={"color":"#f87171","fontWeight":"800","marginBottom":"8px"}),
                html.Div(str(e), style={"color":WHITE,"fontSize":"12px","fontFamily":"monospace"}),
            ], style={"padding":"60px","textAlign":"center"})
        return tab, pref_view, {"display":"none"}, no_update, no_update

    if tab == "admin":
        try:
            admin_view = build_admin_tab(session={"email": ADMIN_EMAIL}, backend_url=BACKEND_HTTP)
        except Exception as e:
            admin_view = html.Div([
                html.Div("Admin tab error", style={"color":"#f87171","fontWeight":"800","marginBottom":"8px"}),
                html.Div(str(e), style={"color":WHITE,"fontSize":"12px","fontFamily":"monospace"}),
            ], style={"padding":"60px","textAlign":"center"})
        return tab, admin_view, {"display":"none"}, no_update, no_update

    fast_shell = html.Div(['''

if needle not in text:
    raise SystemExit("Did not find the 5-output fast set_tab callback. Do not deploy. Upload current sigmalytic_app_TODAY.py.")

text = text.replace(needle, insert, 1)

path.write_text(text, encoding="utf-8")
print("PREFERENCES / ADMIN DIRECT CLICK FIX APPLIED")
