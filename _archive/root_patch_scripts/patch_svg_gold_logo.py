from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r'html\.(?:Div|Span)\(chr\(931\),\s*style=\{.*?\}\),',
    re.DOTALL
)

replacement = '''html.Svg([
        html.Defs([
            html.LinearGradient([
                html.Stop(offset="0%", stopColor="#7A4A00"),
                html.Stop(offset="22%", stopColor="#D4AF37"),
                html.Stop(offset="42%", stopColor="#FFF2A8"),
                html.Stop(offset="58%", stopColor="#FFD700"),
                html.Stop(offset="78%", stopColor="#B8860B"),
                html.Stop(offset="100%", stopColor="#F7C948"),
            ], id="sigmaGold", x1="0%", y1="0%", x2="100%", y2="100%")
        ]),
        html.Path(
            d="M4 4 H30 V8 H13 L21 16 L13 24 H30 V28 H4 L16 16 Z",
            fill="url(#sigmaGold)",
            stroke="#FFF2A8",
            strokeWidth="1.15",
            strokeLinejoin="round",
        ),
        html.Path(
            d="M7 6 H25",
            stroke="#FFFFFF",
            strokeWidth="1",
            opacity=".45",
            strokeLinecap="round",
        ),
    ],
    width="28",
    height="28",
    viewBox="0 0 34 32",
    style={
        "marginRight":"4px",
        "flexShrink":"0",
        "display":"block",
        "filter":"drop-shadow(0 0 2px rgba(255,215,0,.55))",
    }),'''

new_text, count = pattern.subn(replacement, text, count=1)

if count != 1:
    raise SystemExit("FAILED: Could not find the current chr(931) logo block.")

path.write_text(new_text, encoding="utf-8")
print("SVG GOLD SIGMA PATCH OK")
