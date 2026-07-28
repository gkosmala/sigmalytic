from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

# V2_RADAR_BIAS_COLOR_FIX
helper = '''
def _bias_color(value):
    v = str(value or "").upper().strip()
    if v == "BULLISH":
        return TEAL_DIM
    if v == "BEARISH":
        return RED_DIM
    if v == "WATCH":
        return YELLOW_DIM
    return WHITE

'''

if "def _bias_color(value):" not in text:
    marker = "def _btn(label, id_, color=TEAL_DIM, bg=TEAL_GLOW, border=BORDER_T, extra=None):"
    if marker not in text:
        raise SystemExit("FAILED: Could not find insertion point for _bias_color helper.")
    text = text.replace(marker, helper + marker, 1)

# Replace Radar bias cell color when it is currently hardcoded to BLUE_DIM, TEXT, MUTED, or WHITE.
# This targets cells that render row.get("bias") / item.get("bias") / r.get("bias").
patterns = [
    r'html\.Td\(([^)]*?\.get\("bias"[^)]*?\)[^)]*?),\s*style=\{([^{}]*?)"color"\s*:\s*(?:BLUE_DIM|TEXT|MUTED|WHITE)([^{}]*?)\}\)',
    r'html\.Div\(([^)]*?\.get\("bias"[^)]*?\)[^)]*?),\s*style=\{([^{}]*?)"color"\s*:\s*(?:BLUE_DIM|TEXT|MUTED|WHITE)([^{}]*?)\}\)',
    r'html\.Span\(([^)]*?\.get\("bias"[^)]*?\)[^)]*?),\s*style=\{([^{}]*?)"color"\s*:\s*(?:BLUE_DIM|TEXT|MUTED|WHITE)([^{}]*?)\}\)',
]

total = 0
for pat in patterns:
    def repl(m):
        global total
        expr = m.group(1)
        before = m.group(2)
        after = m.group(3)
        # Pull the same bias expression into _bias_color()
        return f'html.Td({expr}, style={{ {before}"color":_bias_color({expr}){after}}})' if "html\\.Td" in pat else \
               f'html.Div({expr}, style={{ {before}"color":_bias_color({expr}){after}}})' if "html\\.Div" in pat else \
               f'html.Span({expr}, style={{ {before}"color":_bias_color({expr}){after}}})'
    text, count = re.subn(pat, repl, text, flags=re.DOTALL)
    total += count

# Direct fallback for the common radar line:
text = text.replace(
    '"color":BLUE_DIM,"fontWeight":"800","padding":"10px 12px","fontSize":"12px"',
    '"color":_bias_color(row.get("bias")),"fontWeight":"800","padding":"10px 12px","fontSize":"12px"',
    1
)

if "_bias_color" not in text:
    raise SystemExit("FAILED: _bias_color helper missing.")

path.write_text(text, encoding="utf-8")
print("RADAR BIAS COLOR PATCH OK")
