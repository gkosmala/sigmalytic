# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""Content Hub rendering (Admin tab): turns the /api/admin/content-hub/generate package into Dash components."""
from __future__ import annotations

from dash import dcc, html
import base64
import json

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


def _share_card(img):
    if not img:
        return html.Div()
    src = "data:image/png;base64," + img["png_b64"]
    return html.Div([
        html.Div("SHARE IMAGE (for link previews and social posts)", style={"fontSize": "12px", "fontWeight": "800",
                                                                          "color": WHITE, "marginBottom": "4px"}),
        html.Div(f"{img['width']} x {img['height']} PNG drawn from this report's own data. Download it, then upload it in "
                 "GoDaddy as this post's social/share image. Its fixed text uses only numbers from the report.",
                 style={"fontSize": "11px", "color": MUTED, "marginBottom": "6px"}),
        html.Img(src=src, style={"width": "100%", "maxWidth": "900px", "borderRadius": "10px", "border": f"1px solid {BORDER}"}),
        html.Div(html.A("Download share image", href=src, download=img["filename"],
                        style={"color": WHITE, "fontWeight": "700", "fontSize": "12px"}), style={"marginTop": "6px"}),
    ], style={"marginTop": "14px"})


def _raw_data_card(pkg):
    """The exact numbers the report was built from, so they can be compared with another source."""
    facts, bars = pkg.get("facts") or {}, pkg.get("daily_bars") or []
    sym = pkg.get("symbol", "symbol").lower()
    js = json.dumps(facts, indent=2, default=str)
    csv = "date,open,high,low,close,volume\n" + "\n".join(",".join(str(x) for x in b) for b in bars)
    link = lambda txt, name, body, mime: html.A(txt, href=f"data:{mime};base64," + base64.b64encode(body.encode()).decode(),
                                                 download=name, style={"color": WHITE, "fontWeight": "700", "fontSize": "12px",
                                                                       "marginRight": "16px"})
    return html.Div([
        html.Div("RAW DATA USED (for checking against another source)", style={"fontSize": "12px", "fontWeight": "800",
                                                                              "color": WHITE, "marginBottom": "4px"}),
        html.Div("Every figure the report was built from: all timeframes, levels, averages and volume ratios, plus the daily "
                 "bars behind the chart. Source and bar dates are listed in the data.",
                 style={"fontSize": "11px", "color": MUTED, "marginBottom": "6px"}),
        html.Div([link("Download computed data (JSON)", f"{sym}-{pkg.get('as_of')}-data.json", js, "application/json"),
                  link(f"Download daily bars (CSV, {len(bars)} rows)", f"{sym}-{pkg.get('as_of')}-daily-bars.csv", csv, "text/csv"),
                  _copy(js, "Copy JSON")]),
        html.Details([html.Summary("Show computed data", style={"color": WHITE, "fontSize": "12px", "cursor": "pointer"}), _pre(js)],
                     style={"marginTop": "6px"}),
    ], style={"border": f"1px solid {BORDER}", "borderRadius": "10px", "padding": "10px", "marginTop": "14px"})


def _raw_card(raw):
    if not raw:
        return html.Div()
    return html.Div([
        html.Div("UNPROCESSED AI TEXT (the reply could not be turned into a report; you were billed for it, so it is kept here)",
                 style={"fontSize": "12px", "fontWeight": "800", "color": RED, "marginBottom": "4px"}),
        _copy(raw, "Copy AI text"), _pre(raw)],
        style={"border": f"1px dashed {RED}", "borderRadius": "10px", "padding": "10px", "marginTop": "14px"})


def _private_card(p):
    if not p:
        return html.Div()
    rows = [html.Div("PRIVATE EDITORIAL ASSESSMENT (not part of the published report)",
                     style={"fontSize": "12px", "fontWeight": "800", "color": AMBER, "marginBottom": "4px"})]
    names = {"A": "A. Institutional accumulation", "B": "B. Distribution / exhaustion risk", "C": "C. High-volatility squeeze"}
    for k in ("A", "B", "C"):
        v = p.get(k) or {}
        ok = bool(v.get("supported"))
        rows.append(html.Div([html.Span(("SUPPORTED  " if ok else "Not supported  "),
                                        style={"color": GREEN if ok else MUTED, "fontWeight": "800", "fontSize": "11px"}),
                              html.Span(names[k] + ": ", style={"color": WHITE, "fontSize": "12px"}),
                              html.Span(v.get("reasoning") or "", style={"color": MUTED, "fontSize": "11px"})],
                             style={"marginBottom": "3px"}))
    sel = p.get("selected")
    rows.append(html.Div("Headline used: " + (f"Option {sel}" if sel in ("A", "B", "C") else "alternative headline (no option sufficiently supported)"),
                         style={"color": WHITE, "fontSize": "12px", "marginTop": "4px"}))
    rows.append(html.Div(p.get("data_limits") or "", style={"color": MUTED, "fontSize": "11px", "marginTop": "2px"}))
    return html.Div(rows, style={"border": f"1px dashed {AMBER}", "borderRadius": "10px", "padding": "10px", "marginTop": "14px"})


def render_package(pkg: dict):
    blog = pkg["blog"]
    prov = {"anthropic": "Claude", "openai": "OpenAI"}.get(pkg.get("ai_provider") or "", "AI")
    mode = f"Written by {prov} from your data" if pkg.get("ai_used") else "Template draft built from your data"
    out = [
        html.Div(f"{pkg['symbol']} · data as of {pkg['as_of']} · {mode}",
                 style={"fontSize": "13px", "fontWeight": "800", "color": WHITE, "marginBottom": "4px"}),
    ]
    u = pkg.get("usage") or {}
    if u.get("calls"):
        cost = f"${u['cost_usd']:.4f}" if u.get("cost_usd") is not None else "price for this model is not in the table"
        extra = f" (including {u['reasoning_tokens']:,} reasoning tokens)" if u.get("reasoning_tokens") else ""
        srch = f", {u['searches']} web searches" if u.get("searches") else ""
        out.append(html.Div(f"AI usage this run: {u['calls']} calls{srch}, {u['input_tokens']:,} tokens in, "
                            f"{u['output_tokens']:,} out{extra}. Cost: {cost}. Model: {', '.join(u['models'])}.",
                            style={"fontSize": "11px", "color": MUTED, "marginBottom": "4px"}))
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
        _share_card(pkg.get("share_image")),
        _raw_data_card(pkg),
        _raw_card(blog.get("raw_ai_text")),
        _private_card(blog.get("private")),
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
