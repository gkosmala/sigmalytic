# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
import dash
from dash import html, dcc, Input, Output, State
import dash_bootstrap_components as dbc

def layout():
    return html.Div([
        html.Div([
            # Header
            html.Div([
                html.Div([
                    html.Span("Î£", style={
                        "fontSize": "24px",
                        "fontWeight": "700",
                        "color": "#00E5B4",
                        "fontFamily": "monospace",
                        "marginRight": "10px"
                    }),
                    html.Div([
                        html.Div("SIGMALYTIC", style={
                            "fontSize": "14px",
                            "fontWeight": "700",
                            "color": "#FFFFFF",
                            "letterSpacing": "3px"
                        }),
                        html.Div("QUANT CORPORATION", style={
                            "fontSize": "8px",
                            "color": "#00E5B4",
                            "letterSpacing": "2px"
                        })
                    ])
                ], style={"display": "flex", "alignItems": "center"})
            ], style={
                "padding": "20px 40px",
                "borderBottom": "1px solid rgba(0, 229, 180, 0.2)",
                "backgroundColor": "#0A0F1E"
            }),

            # Main content
            html.Div([
                html.Div([
                    # Left side - info
                    html.Div([
                        html.Div("SMS ALERT ENROLLMENT", style={
                            "fontSize": "11px",
                            "color": "#00E5B4",
                            "letterSpacing": "3px",
                            "marginBottom": "12px"
                        }),
                        html.H1("Stay Ahead of\nEvery Signal", style={
                            "fontSize": "36px",
                            "fontWeight": "700",
                            "color": "#FFFFFF",
                            "lineHeight": "1.2",
                            "marginBottom": "20px",
                            "whiteSpace": "pre-line"
                        }),
                        html.P(
                            "Receive real-time SMS notifications when Sigmalytic detects armed and triggered market setups for premium subscribers.",
                            style={
                                "color": "#8892A4",
                                "fontSize": "15px",
                                "lineHeight": "1.7",
                                "marginBottom": "32px"
                            }
                        ),
                        # Feature bullets
                        html.Div([
                            html.Div([
                                html.Div("â†’", style={"color": "#00E5B4", "marginRight": "12px", "fontWeight": "700"}),
                                html.Span("Armed & Triggered setup alerts", style={"color": "#CBD5E1", "fontSize": "14px"})
                            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
                            html.Div([
                                html.Div("â†’", style={"color": "#00E5B4", "marginRight": "12px", "fontWeight": "700"}),
                                html.Span("GEX regime change notifications", style={"color": "#CBD5E1", "fontSize": "14px"})
                            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
                            html.Div([
                                html.Div("â†’", style={"color": "#00E5B4", "marginRight": "12px", "fontWeight": "700"}),
                                html.Span("Daily radar summary at market close", style={"color": "#CBD5E1", "fontSize": "14px"})
                            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),
                            html.Div([
                                html.Div("â†’", style={"color": "#00E5B4", "marginRight": "12px", "fontWeight": "700"}),
                                html.Span("Elite Trader & Trader plan subscribers", style={"color": "#CBD5E1", "fontSize": "14px"})
                            ], style={"display": "flex", "alignItems": "center"})
                        ]),
                    ], style={"flex": "1", "paddingRight": "60px"}),

                    # Right side - form
                    html.Div([
                        html.Div([
                            html.H2("Subscribe to SMS Alerts", style={
                                "fontSize": "20px",
                                "fontWeight": "600",
                                "color": "#FFFFFF",
                                "marginBottom": "24px"
                            }),

                            # Full Name
                            html.Div([
                                html.Label("Full Name", style={
                                    "display": "block",
                                    "fontSize": "12px",
                                    "color": "#8892A4",
                                    "letterSpacing": "1px",
                                    "marginBottom": "8px"
                                }),
                                dcc.Input(
                                    id="sms-name",
                                    type="text",
                                    placeholder="Type your full name",
                                    style={
                                        "width": "100%",
                                        "padding": "12px 16px",
                                        "backgroundColor": "#0D1426",
                                        "border": "1px solid rgba(0,229,180,0.2)",
                                        "borderRadius": "6px",
                                        "color": "#FFFFFF",
                                        "fontSize": "14px",
                                        "outline": "none",
                                        "boxSizing": "border-box"
                                    }
                                )
                            ], style={"marginBottom": "16px"}),

                            # Email
                            html.Div([
                                html.Label([
                                    "Email ",
                                    html.Span("*", style={"color": "#00E5B4"})
                                ], style={
                                    "display": "block",
                                    "fontSize": "12px",
                                    "color": "#8892A4",
                                    "letterSpacing": "1px",
                                    "marginBottom": "8px"
                                }),
                                dcc.Input(
                                    id="sms-email",
                                    type="email",
                                    placeholder="Enter your email",
                                    style={
                                        "width": "100%",
                                        "padding": "12px 16px",
                                        "backgroundColor": "#0D1426",
                                        "border": "1px solid rgba(0,229,180,0.2)",
                                        "borderRadius": "6px",
                                        "color": "#FFFFFF",
                                        "fontSize": "14px",
                                        "outline": "none",
                                        "boxSizing": "border-box"
                                    }
                                )
                            ], style={"marginBottom": "16px"}),

                            # Phone
                            html.Div([
                                html.Label("Phone Number", style={
                                    "display": "block",
                                    "fontSize": "12px",
                                    "color": "#8892A4",
                                    "letterSpacing": "1px",
                                    "marginBottom": "8px"
                                }),
                                dcc.Input(
                                    id="sms-phone",
                                    type="tel",
                                    placeholder="Enter your phone number here",
                                    style={
                                        "width": "100%",
                                        "padding": "12px 16px",
                                        "backgroundColor": "#0D1426",
                                        "border": "1px solid rgba(0,229,180,0.2)",
                                        "borderRadius": "6px",
                                        "color": "#FFFFFF",
                                        "fontSize": "14px",
                                        "outline": "none",
                                        "boxSizing": "border-box"
                                    }
                                )
                            ], style={"marginBottom": "20px"}),

                            # Consent checkbox 1 - Trading alerts (non-marketing)
                            html.Div([
                                html.Label([
                                    dcc.Checklist(
                                        id="consent-alerts",
                                        options=[{"label": "", "value": "agreed"}],
                                        value=[],
                                        style={"display": "inline-block", "marginRight": "10px"}
                                    ),
                                    html.Span(
                                        "I consent to receive non-marketing text messages from Sigmalytic Quant Corporation about real-time trading alerts, armed and triggered market setup notifications, and account updates at the phone number provided. Message & data rates may apply. Text HELP for assistance, reply STOP to opt out.",
                                        style={"color": "#8892A4", "fontSize": "12px", "lineHeight": "1.6"}
                                    )
                                ], style={"display": "flex", "alignItems": "flex-start"})
                            ], style={"marginBottom": "16px"}),

                            # Consent checkbox 2 - Marketing
                            html.Div([
                                html.Label([
                                    dcc.Checklist(
                                        id="consent-marketing",
                                        options=[{"label": "", "value": "agreed"}],
                                        value=[],
                                        style={"display": "inline-block", "marginRight": "10px"}
                                    ),
                                    html.Span(
                                        "I consent to receive marketing text messages from Sigmalytic Quant Corporation at the phone number provided. Frequency may vary. Message & data rates may apply. Text HELP for assistance, reply STOP to opt out.",
                                        style={"color": "#8892A4", "fontSize": "12px", "lineHeight": "1.6"}
                                    )
                                ], style={"display": "flex", "alignItems": "flex-start"})
                            ], style={"marginBottom": "20px"}),

                            # Terms links
                            html.Div([
                                html.A("Terms of Service", href="/terms", style={
                                    "color": "#00E5B4",
                                    "fontSize": "12px",
                                    "textDecoration": "none"
                                }),
                                html.Span(" & ", style={"color": "#8892A4", "fontSize": "12px"}),
                                html.A("Privacy Policy", href="/privacy", style={
                                    "color": "#00E5B4",
                                    "fontSize": "12px",
                                    "textDecoration": "none"
                                })
                            ], style={"marginBottom": "20px"}),

                            # Submit button
                            html.Button(
                                "Submit",
                                id="sms-submit",
                                style={
                                    "width": "100%",
                                    "padding": "14px",
                                    "backgroundColor": "#00E5B4",
                                    "color": "#0A0F1E",
                                    "border": "none",
                                    "borderRadius": "6px",
                                    "fontSize": "14px",
                                    "fontWeight": "700",
                                    "letterSpacing": "1px",
                                    "cursor": "pointer"
                                }
                            ),

                            # Success/error message
                            html.Div(id="sms-submit-result", style={"marginTop": "16px"})

                        ], style={
                            "backgroundColor": "#0D1426",
                            "border": "1px solid rgba(0,229,180,0.15)",
                            "borderRadius": "12px",
                            "padding": "32px"
                        })
                    ], style={"width": "420px", "flexShrink": "0"})

                ], style={
                    "display": "flex",
                    "alignItems": "flex-start",
                    "maxWidth": "1100px",
                    "margin": "0 auto",
                    "padding": "60px 40px"
                }),

                # Footer compliance note
                html.Div([
                    html.P(
                        "Sigmalytic Quant Corporation Â· alerts@sigmalyticquantcorp.com Â· +1 (844) 643-6847",
                        style={"color": "#4A5568", "fontSize": "12px", "textAlign": "center", "margin": "0"}
                    ),
                    html.P(
                        "SMS alerts are available to Elite Trader and Trader plan subscribers only. You can manage your alert preferences at any time from the Preferences tab after logging in.",
                        style={"color": "#4A5568", "fontSize": "11px", "textAlign": "center", "margin": "8px 0 0 0"}
                    )
                ], style={
                    "borderTop": "1px solid rgba(0,229,180,0.1)",
                    "padding": "20px 40px",
                    "backgroundColor": "#0A0F1E"
                })

            ], style={"backgroundColor": "#0A0F1E", "minHeight": "calc(100vh - 65px)"})

        ], style={"backgroundColor": "#0A0F1E", "minHeight": "100vh"})
    ])


