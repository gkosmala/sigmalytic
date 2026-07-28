from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# Make sure helper exists and has the requested colors.
helper = '''def _bias_color(value):
    v = str(value or "").upper().strip()
    if v in {"BULL", "BULLISH"}:
        return TEAL_DIM
    if v in {"NEUTRAL", "WATCH"}:
        return YELLOW_DIM
    if v in {"BEAR", "BEARISH"}:
        return RED_DIM
    return WHITE

'''

m = re.search(r'def _bias_color\(value\):\n(?:    .+\n)+?\n', text)
if m:
    text = text[:m.start()] + helper + text[m.end():]
else:
    marker = 'def _btn('
    if marker not in text:
        raise SystemExit("Could not find place to insert _bias_color.")
    text = text.replace(marker, helper + marker, 1)

# Replace hardcoded Bias column color in Radar row.
text = text.replace(
    'html.Span(s.get("bias","—"), style={"flex":"1","fontSize":"11px","color":BLUE_DIM})',
    'html.Span(s.get("bias","—"), style={"flex":"1","fontSize":"11px","fontWeight":"800","color":_bias_color(s.get("bias","—"))})'
)

text = text.replace(
    'html.Span(s.get("bias","â€”"), style={"flex":"1","fontSize":"11px","color":BLUE_DIM})',
    'html.Span(s.get("bias","—"), style={"flex":"1","fontSize":"11px","fontWeight":"800","color":_bias_color(s.get("bias","—"))})'
)

# More flexible replacement in case spacing changed.
text = re.sub(
    r'html\.Span\(s\.get\("bias",\s*["\'][^"\']*["\']\),\s*style=\{([^{}]*?)"color"\s*:\s*BLUE_DIM([^{}]*?)\}\)',
    r'html.Span(s.get("bias","—"), style={\1"fontWeight":"800","color":_bias_color(s.get("bias","—"))\2})',
    text
)

path.write_text(text, encoding="utf-8")
print("RADAR BIAS COLUMN COLOR WIRING UPDATED")
