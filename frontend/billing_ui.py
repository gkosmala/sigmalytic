"""
frontend/billing_ui.py
----------------------
Billing tab UI for Sigmalytic — drop this into app.py.

INTEGRATION STEPS
─────────────────
1. Copy this file to frontend/billing_ui.py
2. In app.py, add this import near the top:
       from billing_ui import build_billing_tab, register_billing_callbacks
3. In build_main_app(), add "Billing" to the nav buttons:
       ("billing", "Billing"),
4. In render_main(), add:
       if tab == "billing": return build_billing_tab(session, perms)
5. After app is defined, call:
       register_billing_callbacks(app)
6. In backend/main.py, add:
       from billing_stub import billing_router
       app.include_router(billing_router)
"""

import requests as _req
from dash import dcc, html, Input, Output, State, no_update, callback_context

# ── Brand tokens (must match app.py) ──────────────────────────────────────────
NAVY      = "#0d1b2e"
NAVY_CARD = "#111f35"
NAVY_MID  = "#0f172a"
TEAL      = "#2d8f6f"
TEAL_DIM  = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"
RED_DIM   = "#f87171"
RED_GLOW  = "rgba(239,68,68,.15)"
YELLOW_DIM= "#fde68a"
BLUE_DIM  = "#93c5fd"
MUTED     = "#64748b"
TEXT      = "#94a3b8"
WHITE     = "#f1f5f9"
BORDER    = "rgba(255,255,255,.08)"
BORDER_T  = "rgba(45,143,111,.35)"

import os
BACKEND_HTTP = os.getenv("BACKEND_URL", "http://localhost:8000")


# ── Helpers (duplicated from app.py for standalone use) ───────────────────────

def _metric(label, value, accent=WHITE):
    return html.Div([
        html.Span(label, style={"display":"block","color":TEXT,"fontSize":"11px",
                                "fontWeight":"600","textTransform":"uppercase",
                                "letterSpacing":".12em","marginBottom":"8px"}),
        html.Strong(value, style={"display":"block","color":accent,
                                  "fontSize":"15px","fontWeight":"800"}),
    ], style={"background":"rgba(0,0,0,.25)","border":f"1px solid {BORDER}",
               "borderRadius":"12px","padding":"14px 16px","minHeight":"64px"})

def _card(children, sx=None):
    s = {"background":NAVY_CARD,"border":f"1px solid {BORDER}","borderRadius":"20px",
         "padding":"20px","boxShadow":"0 8px 32px rgba(0,0,0,.32)"}
    if sx: s.update(sx)
    return html.Section(children, style=s)

def _note(text, variant=""):
    s = {"border":f"1px solid {BORDER}","background":"rgba(0,0,0,.2)","borderRadius":"12px",
         "padding":"12px 14px","color":TEXT,"fontSize":"12px","lineHeight":"1.6"}
    if variant == "yellow": s.update({"borderColor":"rgba(245,158,11,.25)","background":"rgba(245,158,11,.08)","color":"#fef3c7"})
    elif variant == "blue":  s.update({"borderColor":"rgba(59,130,246,.25)","background":"rgba(59,130,246,.08)","color":"#dbeafe"})
    elif variant == "teal":  s.update({"borderColor":BORDER_T,"background":TEAL_GLOW,"color":"#d1fae5"})
    elif variant == "red":   s.update({"borderColor":"rgba(239,68,68,.25)","background":RED_GLOW,"color":"#fee2e2"})
    return html.Div(text, style=s)


# ── Billing tab builder ────────────────────────────────────────────────────────

def build_billing_tab(session=None, perms=None):
    """
    Renders the billing page based on the user's current tier.
    Called from render_main() in app.py.
    """
    user_id = (session or {}).get("user_id", "demo_user_001")

    # Fetch billing state from backend
    try:
        r = _req.get(f"{BACKEND_HTTP}/api/v1/billing/{user_id}", timeout=5)
        billing = r.json() if r.ok else {}
    except Exception:
        billing = {}

    tier     = billing.get("tier", "free_trial")
    plan     = billing.get("plan_name", "—")
    renews   = billing.get("current_period_end", "—")
    owed     = billing.get("amount_due", 0.00)
    is_beta  = billing.get("is_beta_account", True)

    # ── Alert banner ───────────────────────────────────────────────────────────
    if tier == "past_due":
        alert = _note("⚠️  Action Required — Your simulated account balance is past due. "
                      "Click below to retry payment.", "red")
    elif tier == "free_trial":
        alert = _note("ℹ️  You are on a limited Beta Free Tier. Upgrade to unlock full access.", "blue")
    else:
        alert = _note("✅  Your account is active on the Full Beta Premium Tier. "
                      "All features are unlocked.", "teal")

    # ── Subscription details card ──────────────────────────────────────────────
    details_card = _card([
        html.H2("Subscription Details",
                style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 16px"}),
        html.Div([
            _metric("Current Plan",  plan,            BLUE_DIM),
            _metric("Renews On",     renews,          TEXT),
            _metric("Balance Due",   f"${owed:.2f}",  RED_DIM if owed > 0 else TEAL_DIM),
            _metric("Account Type",  "Beta" if is_beta else "Standard", YELLOW_DIM),
        ], style={"display":"grid","gridTemplateColumns":"repeat(4,1fr)","gap":"12px"}),
    ], sx={"marginBottom":"16px"})

    # ── Action card — changes by tier ──────────────────────────────────────────
    if tier == "premium_beta":
        action_card = _card([
            html.H2("Plan Management",
                    style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
            html.Button("Manage Plan (Disabled During Beta)", disabled=True,
                style={"background":"rgba(100,116,139,.2)","color":MUTED,"border":f"1px solid {BORDER}",
                       "borderRadius":"10px","padding":"12px 24px","fontSize":"13px",
                       "fontWeight":"700","cursor":"not-allowed","marginBottom":"12px"}),
            _note("Full plan management (cancel, downgrade, invoice history) will be available "
                  "when Stripe integration goes live.", "blue"),
        ])

    elif tier == "free_trial":
        action_card = _card([
            html.H2("Upgrade to Premium Beta",
                    style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
            html.Div([
                html.Div([
                    html.Div("✓  Full CSV behavioral analysis",  style={"color":TEAL_DIM,"fontSize":"13px","marginBottom":"6px"}),
                    html.Div("✓  Advanced performance metrics",  style={"color":TEAL_DIM,"fontSize":"13px","marginBottom":"6px"}),
                    html.Div("✓  Radar screen (coming soon)",    style={"color":TEAL_DIM,"fontSize":"13px","marginBottom":"6px"}),
                    html.Div("✓  Paper trading (coming soon)",   style={"color":TEAL_DIM,"fontSize":"13px","marginBottom":"6px"}),
                ], style={"marginBottom":"16px"}),
                html.Button("Simulate Upgrade to Premium Beta",
                    id="btn-billing-upgrade", n_clicks=0,
                    style={"background":TEAL,"color":WHITE,"border":"none","borderRadius":"10px",
                           "padding":"14px 28px","fontSize":"14px","fontWeight":"800",
                           "cursor":"pointer","width":"100%","marginBottom":"12px"}),
                html.Div(id="billing-upgrade-status", style={"fontSize":"13px","minHeight":"20px"}),
            ]),
            _note("Beta pricing: $0 — all charges waived during the beta period. "
                  "Stripe integration coming in production.", "yellow"),
        ])

    else:  # past_due
        action_card = _card([
            html.H2("Payment Required",
                    style={"fontSize":"15px","fontWeight":"800","color":WHITE,"margin":"0 0 14px"}),
            html.Button("Simulate Retry Payment",
                id="btn-billing-upgrade", n_clicks=0,
                style={"background":"#b45309","color":WHITE,"border":"none","borderRadius":"10px",
                       "padding":"14px 28px","fontSize":"14px","fontWeight":"800",
                       "cursor":"pointer","width":"100%","marginBottom":"12px"}),
            html.Div(id="billing-upgrade-status", style={"fontSize":"13px","minHeight":"20px"}),
            _note("This is a simulated past-due state for beta testing. "
                  "No real payment is required.", "red"),
        ])

    return html.Div([
        _card([
            html.H2("💳 Account Billing",
                    style={"fontSize":"16px","fontWeight":"800","color":WHITE,"margin":"0 0 6px"}),
            html.P("Manage your Sigmalytic subscription. All charges are waived during the beta period.",
                   style={"fontSize":"12px","color":TEXT,"marginBottom":"16px"}),
            alert,
        ], sx={"marginBottom":"16px"}),
        details_card,
        action_card,
        # Hidden store for billing state refresh
        dcc.Store(id="billing-tier-store", data=tier),
    ])


# ── Callbacks ──────────────────────────────────────────────────────────────────

def register_billing_callbacks(app, backend_http=None):
    """Call this once after `app` is defined in app.py."""
    _backend = backend_http or BACKEND_HTTP

    @app.callback(
        Output("billing-upgrade-status", "children"),
        Input("btn-billing-upgrade", "n_clicks"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def handle_upgrade(n_clicks, session):
        if not n_clicks:
            return no_update
        user_id = (session or {}).get("user_id", "demo_user_001")
        tier    = "premium_beta"
        try:
            r = _req.post(
                f"{_backend}/api/v1/billing/{user_id}/upgrade",
                json={"requested_tier": tier},
                timeout=5,
            )
            if r.ok:
                return html.Div([
                    html.Span("✅ Simulated upgrade successful! ", style={"color":TEAL_DIM,"fontWeight":"800"}),
                    html.Span("Refresh the page to see your updated plan.",  style={"color":TEXT}),
                ])
            return html.Span(f"❌ Backend error: {r.status_code}", style={"color":RED_DIM})
        except Exception as e:
            return html.Span(f"❌ Error: {str(e)[:200]}", style={"color":RED_DIM})
