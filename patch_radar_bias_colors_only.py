from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

old = re.search(
    r'def _bias_color\(value\):\n(?:    .+\n)+?(?=\ndef |\n#|\ndef|\n\n)',
    text
)

new = '''def _bias_color(value):
    v = str(value or "").upper().strip()
    if v in {"BULL", "BULLISH"}:
        return TEAL_DIM
    if v in {"NEUTRAL", "WATCH"}:
        return YELLOW_DIM
    if v in {"BEAR", "BEARISH"}:
        return RED_DIM
    return WHITE

'''

if not old:
    raise SystemExit("Could not find _bias_color function. Do not deploy.")

text = text[:old.start()] + new + text[old.end():]

path.write_text(text, encoding="utf-8")
print("BIAS COLOR FUNCTION UPDATED")
