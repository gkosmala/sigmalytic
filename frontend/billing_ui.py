"""
frontend/billing_ui.py
----------------------
Sigmalytic — Stripe Billing UI

Shows:
- Current plan + feature flags for logged-in users
- Stripe pricing table for upgrades
- Customer portal link for plan management
- Contact Us for Institutional tier
"""

import os
import requests as _req
from dash import dcc, html, Input, Output, State, no_update

BACKEND_HTTP     = os.getenv("BACKEND_URL",  "https://sigmalytic-backend.onrender.com")
FRONTEND_URL     = os.getenv("FRONTEND_URL", "https://sigmalytic-frontend.onrender.com")
CONTACT_EMAIL    = "support@sigmalytic.com"

# ── Stripe pricing table config ────────────────────────────────────────────────
PRICING_TABLE_ID = "prctbl_1Tc35NDRUJk6Un01beNdvTak"
PUBLISHABLE_KEY  = os.getenv("STRIPE_PUBLISHABLE_KEY",
                             "pk_test_51TO3CQDRUJk6Un01sFsuiZdCp248v1zFUBmLSbzYyQtvaGRbP3agOWAXnTX60gRCqxjOjLyDZeogZuO4dPZhwdhE00hNQoOw1V")

# ── Brand tokens ───────────────────────────────────────────────────────────────
NAVY_CARD = "#111f35"; TEAL = "#2d8f6f"; TEAL_DIM = "#34d399"
TEAL_GLOW = "rgba(45,143,111,.18)"; RED_DIM = "#f87171"
YELLOW_DIM = "#fde68a"; BLUE_DIM = "#93c5fd"; MUTED = "#64748b"
TEXT = "#94a3b8"; WHITE = "#f1f5f9"; BORDER = "rgba(255,255,255,.08)"
BORDER_T = "rgba(45,143,111,.35)"


def _card(children, sx=None):
    s = {"background": NAVY_CARD, "border": f"1px solid {BORDER}",
         "borderRadius": "20px", "padding": "24px",
         "boxShadow": "0 8px 32px rgba(0,0,0,.32)", "marginBottom": "16px"}
    if sx: s.update(sx)
    return html.Section(children, style=s)


def _badge(text, color=TEAL_DIM):
    return html.Span(text, style={
        "background": "rgba(45,143,111,.15)", "border": f"1px solid {BORDER_T}",
        "borderRadius": "20px", "color": color, "fontSize": "11px",
        "fontWeight": "800", "padding": "4px 12px", "letterSpacing": ".08em",
    })


def _feature_row(label, value, enabled=True):
    color = TEAL_DIM if enabled else MUTED
    icon  = "✓" if enabled else "—"
    return html.Div([
        html.Span(f"{icon}  {label}", style={"color": color, "fontSize": "13px"}),
        html.Span(str(value), style={"color": TEXT, "fontSize": "12px", "marginLeft": "8px"}),
    ], style={"padding": "8px 0", "borderBottom": f"1px solid {BORDER}"})


def _metric(label, value, color=WHITE):
    return html.Div([
        html.Div(label, style={"color": MUTED, "fontSize": "10px", "fontWeight": "800",
                               "textTransform": "uppercase", "letterSpacing": ".2em",
                               "marginBottom": "6px"}),
        html.Div(value, style={"color": color, "fontSize": "16px", "fontWeight": "800"}),
    ], style={"background": "rgba(0,0,0,.2)", "border": f"1px solid {BORDER}",
              "borderRadius": "12px", "padding": "14px 16px"})


def build_billing_tab(session=None, perms=None):
    user_id = (session or {}).get("user_id", "")
    email   = (session or {}).get("email", "")

    # Fetch billing state
    billing = {}
    if user_id:
        try:
            r = _req.get(f"{BACKEND_HTTP}/api/v1/billing/{user_id}", timeout=5)
            if r.ok:
                billing = r.json()
        except Exception:
            pass

    tier        = billing.get("tier", "free")
    plan_name   = billing.get("plan_name", "Free")
    plan_price  = billing.get("plan_price", "$0")
    status      = billing.get("status", "active")
    period_end  = billing.get("current_period_end", "—")
    cancel_end  = billing.get("cancel_at_period_end", False)
    features    = billing.get("features", {})
    has_customer= bool(billing.get("stripe_customer_id"))

    # ── Status banner ──────────────────────────────────────────────────────────
    if status == "past_due":
        banner_color = RED_DIM
        banner_bg    = "rgba(239,68,68,.08)"
        banner_border= "rgba(239,68,68,.25)"
        banner_text  = "⚠️ Payment past due — please update your payment method to restore full access."
    elif cancel_end:
        banner_color = YELLOW_DIM
        banner_bg    = "rgba(245,158,11,.08)"
        banner_border= "rgba(245,158,11,.25)"
        banner_text  = f"⚠️ Your plan is set to cancel on {period_end}. Reactivate anytime below."
    elif tier == "free":
        banner_color = BLUE_DIM
        banner_bg    = "rgba(59,130,246,.08)"
        banner_border= "rgba(59,130,246,.25)"
        banner_text  = "You are on the Free plan. Upgrade to unlock live data, alerts, and intelligence scoring."
    else:
        banner_color = TEAL_DIM
        banner_bg    = TEAL_GLOW
        banner_border= BORDER_T
        banner_text  = f"✅ {plan_name} — Active. All features unlocked."

    banner = html.Div(banner_text, style={
        "background": banner_bg, "border": f"1px solid {banner_border}",
        "borderRadius": "12px", "color": banner_color,
        "fontSize": "13px", "padding": "14px 18px", "marginBottom": "16px",
    })

    # ── Current plan card (only if logged in and subscribed) ──────────────────
    plan_card = _card([
        html.Div([
            html.Div([
                html.H2(plan_name, style={"color": WHITE, "fontSize": "20px",
                                          "fontWeight": "900", "margin": "0 0 4px"}),
                html.Div(plan_price, style={"color": TEAL_DIM, "fontSize": "24px",
                                            "fontWeight": "900", "marginBottom": "12px"}),
                _badge("ACTIVE" if status == "active" else status.upper()),
            ]),
        ], style={"marginBottom": "20px"}),

        html.Div([
            _metric("Status",     status.title(),          TEAL_DIM if status=="active" else RED_DIM),
            _metric("Renews",     period_end or "—",        TEXT),
            _metric("Radar",      f"{features.get('radar_limit', 50)} symbols", WHITE),
            _metric("SMS Alerts", "Unlimited" if features.get("sms_limit",-1)==-1
                                  else f"{features.get('sms_limit',0)}/day"
                                  if features.get("sms_limit",0) > 0 else "None", WHITE),
        ], style={"display": "grid", "gridTemplateColumns": "repeat(4,1fr)",
                  "gap": "12px", "marginBottom": "20px"}),

        html.Div([
            _feature_row("Live Market Data",        "SIP Feed",    features.get("live_data", False)),
            _feature_row("Radar Screen",            f"{features.get('radar_limit',50)} symbols", True),
            _feature_row("Status Alerts",           "Armed / Triggered", features.get("alerts", False)),
            _feature_row("Intelligence Layer",      "GEX · BME · Hurst · VSA", features.get("intelligence", False)),
            _feature_row("Weis Wave + 3-Bar",       "All 1,403 symbols", True),
            _feature_row("Divergence Watchlist",    "EOD Audit",   features.get("intelligence", False)),
            _feature_row("SMS Alerts",              "Via Twilio",  features.get("sms_limit", 0) != 0),
        ], style={"marginBottom": "20px"}),

        # Manage plan button (only if has Stripe customer)
        html.Div([
            html.Button("Manage Plan / Cancel",
                id="btn-manage-plan",
                n_clicks=0,
                style={
                    "background": "rgba(0,0,0,.2)", "border": f"1px solid {BORDER}",
                    "borderRadius": "10px", "color": TEXT, "cursor": "pointer",
                    "fontFamily": "DM Sans, sans-serif", "fontSize": "13px",
                    "fontWeight": "700", "padding": "10px 20px",
                } if has_customer else {
                    "display": "none"
                }
            ),
            html.Div(id="billing-portal-status", style={"fontSize": "12px",
                     "color": MUTED, "marginTop": "8px"}),
        ]) if tier != "free" else html.Div(),
    ]) if user_id else html.Div()

    # ── Stripe pricing table ───────────────────────────────────────────────────
    pricing_section = _card([
        html.H2("Choose Your Plan", style={"color": WHITE, "fontSize": "18px",
                                            "fontWeight": "900", "marginBottom": "8px"}),
        html.P("Upgrade or change your plan anytime. Cancel anytime.",
               style={"color": TEXT, "fontSize": "13px", "marginBottom": "24px"}),

        # Stripe pricing table embedded via iframe/HTML component
        html.Iframe(
            srcDoc=f"""
                <script async src="https://js.stripe.com/v3/pricing-table.js"></script>
                <stripe-pricing-table
                    pricing-table-id="{PRICING_TABLE_ID}"
                    publishable-key="{PUBLISHABLE_KEY}"
                    client-reference-id="{user_id}"
                    customer-email="{email}">
                </stripe-pricing-table>
            """,
            style={
                "width": "100%", "border": "none",
                "minHeight": "600px", "background": "transparent",
            },
        ),

        # Institutional contact
        html.Div([
            html.Div("🏛️ Institutional", style={"color": WHITE, "fontSize": "16px",
                                                  "fontWeight": "800", "marginBottom": "8px"}),
            html.Div("Custom universe · API access · Priority support · Dedicated onboarding",
                     style={"color": TEXT, "fontSize": "13px", "marginBottom": "16px"}),
            html.A("Contact Us →",
                   href=f"mailto:{CONTACT_EMAIL}?subject=Sigmalytic Institutional Inquiry",
                   style={
                       "background": TEAL_GLOW, "border": f"1px solid {BORDER_T}",
                       "borderRadius": "10px", "color": TEAL_DIM, "cursor": "pointer",
                       "display": "inline-block", "fontSize": "14px", "fontWeight": "800",
                       "padding": "12px 24px", "textDecoration": "none",
                   }),
        ], style={
            "background": "rgba(0,0,0,.2)", "border": f"1px solid {BORDER}",
            "borderRadius": "16px", "marginTop": "24px", "padding": "24px",
            "textAlign": "center",
        }),
    ])

    return html.Div([
        # Header
        _card([
            html.H2("💳 Billing & Plans", style={"color": WHITE, "fontSize": "18px",
                                                   "fontWeight": "900", "margin": "0 0 6px"}),
            html.P("Manage your Sigmalytic subscription.",
                   style={"color": TEXT, "fontSize": "13px", "margin": "0"}),
        ], sx={"marginBottom": "16px", "padding": "20px"}),

        banner,
        plan_card,
        pricing_section,
    ], style={"maxWidth": "900px", "margin": "0 auto", "padding": "24px 16px"})


def register_billing_callbacks(app):

    @app.callback(
        Output("billing-portal-status", "children"),
        Input("btn-manage-plan", "n_clicks"),
        State("s-session", "data"),
        prevent_initial_call=True,
    )
    def open_portal(n, session):
        if not n:
            return no_update
        user_id = (session or {}).get("user_id", "")
        if not user_id:
            return "Please log in first."
        try:
            r = _req.post(f"{BACKEND_HTTP}/api/v1/billing/{user_id}/portal", timeout=8)
            if r.ok:
                url = r.json().get("url", "")
                if url:
                    # Return a clickable link
                    return html.A("Click here to manage your plan →",
                                  href=url, target="_blank",
                                  style={"color": TEAL_DIM, "fontSize": "13px"})
            return html.Span(f"Error: {r.status_code}", style={"color": RED_DIM})
        except Exception as e:
            return html.Span(f"Error: {str(e)[:100]}", style={"color": RED_DIM})
