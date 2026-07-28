from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r'html\.Div\(chr\(931\),\s*style=\{.*?\}\),',
    re.DOTALL
)

replacement = '''html.Div(chr(931), style={
        "fontSize":"28px",
        "fontWeight":"900",
        "lineHeight":"1",
        "fontFamily":"Times New Roman, Georgia, serif",
        "marginRight":"4px",
        "flexShrink":"0",
        "display":"inline-block",

        # POLISHED METALLIC GOLD SIGMA — crisp, bright, no blur
        "color":"#FFD700",
        "background":"linear-gradient(135deg, #7A4A00 0%, #B8860B 18%, #FFD700 36%, #FFF4B8 48%, #D4AF37 58%, #9A6A00 74%, #FFD700 100%)",
        "WebkitBackgroundClip":"text",
        "backgroundClip":"text",
        "WebkitTextFillColor":"transparent",
        "textShadow":"0 1px 0 #5C3A00, 0 0 1px rgba(255,244,184,.85)",
    }),'''

new_text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit("FAILED: Could not find chr(931) sigma logo block.")

path.write_text(new_text, encoding="utf-8")
print("POLISHED GOLD SIGMA PATCH OK")
