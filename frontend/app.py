"""
Run from your sigmalytic root:
    python fix_auth.py
"""
import re, sys

path = "frontend/app.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

changes = 0

# Fix 1: Add signup-section and signup-btn inside the auth overlay
# Find the goto-signup-btn and add signup form after the closing div
old_goto = '''                    html.Button("Sign Up", id="goto-signup-btn", n_clicks=0,
                        style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px",
                               "fontWeight":"700","cursor":"pointer","padding":"0"}),
                ], style={"textAlign":"center"}),

            ], style={"background":NAVY_CARD,'''

new_goto = '''                    html.Button("Sign Up", id="goto-signup-btn", n_clicks=0,
                        style={"background":"none","border":"none","color":TEAL_DIM,"fontSize":"12px",
                               "fontWeight":"700","cursor":"pointer","padding":"0"}),
                ], style={"textAlign":"center"}),

                # Signup section (hidden initially — shown when Sign Up clicked)
                html.Div(id="signup-section", style={"display":"none"}, children=[
                    html.H2("Create Account", style={"fontSize":"18px","fontWeight":"800","color":WHITE,"marginBottom":"20px","textAlign":"center","marginTop":"24px"}),
                    html.Div([
                        html.Label("Email", style={"fontSize":"11px","fontWeight":"700","color":"#64748b","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="signup-email", type="email", placeholder="you@example.com",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":"1px solid rgba(255,255,255,.08)",
                                         "borderRadius":"8px","padding":"12px 16px","color":"#f1f5f9","fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"16px"}),
                    html.Div([
                        html.Label("Password", style={"fontSize":"11px","fontWeight":"700","color":"#64748b","textTransform":"uppercase","letterSpacing":".1em","marginBottom":"6px","display":"block"}),
                        dcc.Input(id="signup-password", type="password", placeholder="Min 6 characters",
                                  style={"width":"100%","background":"rgba(0,0,0,.3)","border":"1px solid rgba(255,255,255,.08)",
                                         "borderRadius":"8px","padding":"12px 16px","color":"#f1f5f9","fontSize":"14px",
                                         "outline":"none","fontFamily":"DM Sans, sans-serif"}),
                    ], style={"marginBottom":"20px"}),
                    html.Div(id="signup-error", style={"color":"#f87171","fontSize":"12px","marginBottom":"12px","textAlign":"center"}),
                    html.Button("Create Account", id="signup-btn", n_clicks=0,
                        style={"width":"100%","background":"#2d8f6f","color":"white","border":"none",
                               "borderRadius":"8px","padding":"14px","fontSize":"14px","fontWeight":"700","cursor":"pointer","marginBottom":"16px"}),
                    html.Div([
                        html.Span("Already have an account? ", style={"color":"#64748b","fontSize":"12px"}),
                        html.Button("Sign In", id="goto-login-btn", n_clicks=0,
                            style={"background":"none","border":"none","color":"#34d399","fontSize":"12px",
                                   "fontWeight":"700","cursor":"pointer","padding":"0"}),
                    ], style={"textAlign":"center"}),
                ]),

            ], style={"background":NAVY_CARD,'''

if old_goto in src:
    src = src.replace(old_goto, new_goto)
    changes += 1
    print("✅ Added signup-section with signup-btn and goto-login-btn")
else:
    print("❌ Could not find goto-signup-btn block to patch")
    sys.exit(1)

# Fix 2: Add toggle callback before handle_auth
old_handle = "@app.callback(Output(\"s-session\",\"data\"),Output(\"s-page\",\"data\"),"

new_handle = """@app.callback(Output("login-section","style"), Output("signup-section","style"),
              Input("goto-signup-btn","n_clicks"), Input("goto-login-btn","n_clicks"),
              prevent_initial_call=True)
def toggle_auth_section(to_signup, to_login):
    ctx = callback_context
    if not ctx.triggered: return no_update, no_update
    trigger = ctx.triggered[0]["prop_id"].split(".")[0]
    if trigger == "goto-signup-btn":
        return {"display":"none"}, {"display":"block"}
    return {"display":"block"}, {"display":"none"}

@app.callback(Output("s-session","data"),Output("s-page","data"),"""

if old_handle in src and "toggle_auth_section" not in src:
    src = src.replace(old_handle, new_handle, 1)
    changes += 1
    print("✅ Added toggle_auth_section callback")
else:
    print("⚠️  toggle_auth_section already present or handle_auth not found")

# Fix 3: Add signup-btn to handle_auth inputs if missing
if '"signup-btn","n_clicks"' not in src:
    old_inputs = 'Input("login-btn","n_clicks"),Input("demo-btn","n_clicks"),'
    new_inputs = 'Input("login-btn","n_clicks"),Input("demo-btn","n_clicks"),Input("signup-btn","n_clicks"),'
    if old_inputs in src:
        src = src.replace(old_inputs, new_inputs, 1)
        changes += 1
        print("✅ Added signup-btn to handle_auth inputs")

        # Also update function signature
        old_sig = "def handle_auth(login_clicks, demo_clicks,"
        new_sig = "def handle_auth(login_clicks, demo_clicks, signup_clicks,"
        src = src.replace(old_sig, new_sig, 1)

        # Add signup handling before final return
        old_return = "    return no_update, no_update\n\n# ── Main app callbacks"
        new_return = """    if trigger == "signup-btn":
        if not signup_email or not signup_password: return no_update, no_update
        import requests as _req
        try:
            r = _req.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers={"apikey":SUPABASE_ANON_KEY,"Content-Type":"application/json"},
                json={"email":signup_email,"password":signup_password}, timeout=10,
            )
            if r.ok:
                data = r.json()
                user = data.get("user",{})
                return {"user_id":user.get("id",""),"email":user.get("email",""),
                        "access_token":data.get("access_token",""),"is_demo":False}, "app"
        except Exception:
            pass
        return no_update, no_update

    return no_update, no_update

# ── Main app callbacks"""
        if old_return in src:
            src = src.replace(old_return, new_return, 1)
            print("✅ Added signup handling to handle_auth")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)

print(f"\n✅ Done — {changes} changes applied.")
print("Now run: git add frontend/app.py && git commit -m 'Fix auth signup' && git push origin main")