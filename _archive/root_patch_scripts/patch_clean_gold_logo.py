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

        # CLEAN BRIGHT POLISHED GOLD SIGMA — no blur, no green
        "color":"#F7C948",
        "textShadow":"0 0 1px #FFF4B8, 0 0 3px rgba(247,201,72,.65), 0 1px 0 #8A5A00",
    }),'''

new_text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit("FAILED: Could not find chr(931) sigma logo block.")

path.write_text(new_text, encoding="utf-8")
print("CLEAN GOLD SIGMA PATCH OK")
