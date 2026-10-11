# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Content Hub rendering (Admin tab): turns the /api/admin/content-hub/generate package into Dash components."""
from __future__ import annotations

from dash import dcc, html

WHITE, MUTED, BORDER = "#f8fafc", "#94a3b8", "rgba(255,255,255,.08)"
GREEN, RED, AMBER = "#34d399", "#f87171", "#f59e0b"


def _copy(content: str, label: str = "Copy"):
    return dcc.Clipboard(content=content, title=label, style={"display": "inline-block", "cursor": "pointer",
                                                              "marginLeft": "8px", "color": WHITE, "fontSize": "15px"})


def _pre(text: str):
    return html.Pre(text, style={"whiteSpace": "pre-wrap", "wordBreak": "break-word", "margin": "6px 0",
                                 "background": "rgba(0,0,0,.3)", "border": f"1px solid {BORDER}", "borderRadius": "8px",
                                 "padding": "10px", "fontSize": "12px", "color": WHITE,
                                 "fontFamily": "DM Mono, monospace"})


def _label(text: str):
    return html.Div(text, style={"fontSize": "10px", "fontWeight": "800", "color": MUTED, "letterSpacing": ".12em",
                                 "textTransform": "uppercase", "marginTop": "8px"})


def _teaser_card(d: dict):
    ok = d.get("ok")
    pill = html.Span("Passes checks" if ok else "Needs attention",
                     style={"fontSize": "10px", "fontWeight": "800", "padding": "2px 8px", "borderRadius": "10px",
                            "color": "#0b0f14", "background": GREEN if ok else RED, "marginLeft": "8px"})
    kids = [
        html.Div([html.Span(d["label"], style={"fontWeight": "800", "fontSize": "14px", "color": WHITE}), pill,
                  html.Span(f"{d['chars']}/{d['limit']} characters", style={"fontSize": "11px", "color": MUTED,
                                                                          "marginLeft": "10px"}),
                  html.Span(f"· {d['source']} draft", style={"fontSize": "11px", "color": MUTED, "marginLeft": "6px"})]),
    ]
    if d.get("title"):
        kids += [_label("Title"), html.Div([_pre(d["title"]), _copy(d["title"], "Copy title")])]
    kids += [_label("Post text"), html.Div([_pre(d["text"]), _copy(d["text"], "Copy text")])]
    if d.get("reply"):
        kids += [_label("Reply / first comment (link goes here)"), html.Div([_pre(d["reply"]), _copy(d["reply"], "Copy reply")])]
    if d.get("destination_link"):
        kids += [_label("Pin destination link"), html.Div([_pre(d["destination_link"]), _copy(d["destination_link"])])]
    if d.get("video_script"):
        script = "\n".join(d["video_script"])
        kids += [_label("Video script (about 20 seconds)"), html.Div([_pre(script), _copy(script, "Copy script")])]
    kids += [html.Div(f"Link: {d['link_placement']}  ·  Image: {d['image_spec']}",
                      style={"fontSize": "11px", "color": MUTED, "marginTop": "4px"})]
    for i in d.get("issues") or []:
        kids.append(html.Div("• " + i, style={"fontSize": "12px", "color": RED, "marginTop": "2px"}))
    return html.Div(kids, style={"border": f"1px solid {BORDER}", "borderRadius": "12px", "padding": "12px",
                                 "marginBottom": "12px", "background": "rgba(255,255,255,.02)"})


def render_package(pkg: dict):
    blog = pkg["blog"]
    prov = {"anthropic": "Claude", "openai": "OpenAI"}.get(pkg.get("ai_provider") or "", "AI")
    mode = f"Written by {prov} from your data" if pkg.get("ai_used") else "Template draft built from your data"
    out = [
        html.Div(f"{pkg['symbol']} · data as of {pkg['as_of']} · {mode}",
                 style={"fontSize": "13px", "fontWeight": "800", "color": WHITE, "marginBottom": "4px"}),
    ]
    for n in pkg.get("notes") or []:
        out.append(html.Div(n, style={"fontSize": "11px", "color": AMBER, "marginBottom": "4px"}))
    for i in pkg.get("blog_issues") or []:
        out.append(html.Div("Blog check: " + i, style={"fontSize": "12px", "color": RED}))

    seo = blog.get("seo") or {}
    seo_rows = []
    for c in seo.get("checks") or []:
        ok = c["level"] == "ok"
        seo_rows.append(html.Div([html.Span("✓ " if ok else "! ", style={"color": GREEN if ok else AMBER, "fontWeight": "800"}),
                                  html.Span(c["name"] + ": ", style={"color": WHITE, "fontSize": "12px"}),
                                  html.Span(c["detail"], style={"color": MUTED, "fontSize": "11px"})],
                                 style={"marginBottom": "2px"}))
    out += [
        html.Div("BLOG POST", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE, "margin": "14px 0 4px"}),
        html.Div("Review it, then paste the HTML into the Research & Intelligence page. Copy the head tags into the "
                 "page's SEO/head section so link previews work.", style={"fontSize": "11px", "color": MUTED}),
        html.Iframe(srcDoc=("<body style='font-family:Segoe UI,Arial;max-width:760px;margin:16px auto;line-height:1.55;"
                            "color:#111'>" + blog["html"] + "</body>"),
                    style={"width": "100%", "height": "380px", "border": f"1px solid {BORDER}", "borderRadius": "10px",
                           "background": "#fff", "marginTop": "8px"}),
        html.Div([html.Span("Page URL: ", style={"color": MUTED, "fontSize": "11px"}),
                  html.Span(blog["url"], style={"color": WHITE, "fontSize": "11px"}), _copy(blog["url"], "Copy URL")]),
        html.Div([html.Span("Blog HTML", style={"color": WHITE, "fontSize": "12px", "fontWeight": "700"}),
                  _copy(blog["html"], "Copy blog HTML"),
                  html.Span("  Head tags", style={"color": WHITE, "fontSize": "12px", "fontWeight": "700", "marginLeft": "14px"}),
                  _copy(blog["head_tags"], "Copy head tags"),
                  html.Span("  Markdown", style={"color": WHITE, "fontSize": "12px", "fontWeight": "700", "marginLeft": "14px"}),
                  _copy(blog["markdown"], "Copy markdown")], style={"marginTop": "6px"}),
        html.Div(f"SEO CHECKLIST ({seo.get('warnings', 0)} to fix before publishing)" if seo else "",
                 style={"fontSize": "12px", "fontWeight": "800", "color": WHITE, "margin": "18px 0 6px"}),
        html.Div(seo_rows),
        html.Div("SOCIAL TEASERS", style={"fontSize": "12px", "fontWeight": "800", "color": WHITE, "margin": "18px 0 6px"}),
        html.Div("Drafts only. Nothing is posted. Every link carries tracking tags so you can see which platform "
                 "sends readers.", style={"fontSize": "11px", "color": MUTED, "marginBottom": "8px"}),
    ]
    for p in ("linkedin", "x", "reddit", "pinterest", "facebook", "tiktok"):
        if p in pkg["teasers"]:
            out.append(_teaser_card(pkg["teasers"][p]))
    return html.Div(out)
