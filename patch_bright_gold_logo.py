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
        "fontFamily":"Georgia, serif",
        "marginRight":"4px",
        "flexShrink":"0",

        # BRIGHT POLISHED GOLD SIGMA
        "color":"#FFD700",
        "background":"linear-gradient(135deg, #FFF8B5 0%, #FFD700 22%, #FFB000 45%, #FFFFFF 55%, #FFD700 65%, #B8860B 85%, #FFE066 100%)",
        "WebkitBackgroundClip":"text",
        "WebkitTextFillColor":"transparent",
        "textShadow":"0 0 6px rgba(255,215,0,.95), 0 0 12px rgba(255,190,0,.55), 0 1px 0 #7A4A00",
        "filter":"drop-shadow(0 0 5px rgba(255,215,0,.85))",
    }),'''

new_text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit("FAILED: Could not find chr(931) sigma logo block.")

path.write_text(new_text, encoding="utf-8")
print("BRIGHT GOLD SIGMA PATCH OK")
