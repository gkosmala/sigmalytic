from pathlib import Path

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

start = text.find("html.Svg([")
if start == -1:
    raise SystemExit("FAILED: html.Svg block not found.")

marker = 'html.Div([\n        html.Span("SIGMALYTIC"'
end = text.find(marker, start)
if end == -1:
    raise SystemExit("FAILED: could not find SIGMALYTIC text block after html.Svg.")

replacement = '''html.Img(
        src="data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='34' height='32' viewBox='0 0 34 32'><defs><linearGradient id='g' x1='0%25' y1='0%25' x2='100%25' y2='100%25'><stop offset='0%25' stop-color='%237A4A00'/><stop offset='22%25' stop-color='%23D4AF37'/><stop offset='42%25' stop-color='%23FFF2A8'/><stop offset='58%25' stop-color='%23FFD700'/><stop offset='78%25' stop-color='%23B8860B'/><stop offset='100%25' stop-color='%23F7C948'/></linearGradient></defs><path d='M4 4 H30 V8 H13 L21 16 L13 24 H30 V28 H4 L16 16 Z' fill='url(%23g)' stroke='%23FFF2A8' stroke-width='1.15' stroke-linejoin='round'/><path d='M7 6 H25' stroke='%23FFFFFF' stroke-width='1' opacity='.45' stroke-linecap='round'/></svg>",
        style={
            "width":"28px",
            "height":"28px",
            "marginRight":"4px",
            "flexShrink":"0",
            "display":"block",
            "filter":"drop-shadow(0 0 2px rgba(255,215,0,.55))",
        }
    ),
    '''

text = text[:start] + replacement + text[end:]

path.write_text(text, encoding="utf-8")
print("DASH-SAFE GOLD SIGMA IMG PATCH OK")
