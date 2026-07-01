from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r'LOGO\s*=\s*html\.Div\(\[\s*'
    r'html\.Div\([^,]+,\s*style=\{.*?\}\),\s*'
    r'html\.Div\(\[\s*'
    r'html\.Span\("SIGMALYTIC"',
    re.DOTALL
)

replacement = '''LOGO = html.Div([
    html.Div(chr(931), style={
        "fontSize":"28px",
        "fontWeight":"900",
        "color":"#B8860B",
        "lineHeight":"1",
        "fontFamily":"Georgia, serif",
        "marginRight":"4px",
        "flexShrink":"0",
        "textShadow":"0 0 4px rgba(184,134,11,.45), 0 1px 0 #6E4700",
    }),
    html.Div([
        html.Span("SIGMALYTIC"'''

new_text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit("LOGO PATCH FAILED: could not find the LOGO/SIGMALYTIC block.")

path.write_text(new_text, encoding="utf-8")
print("LOGO PATCH OK")
