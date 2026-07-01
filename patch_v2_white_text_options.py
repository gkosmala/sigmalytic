from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8")

# V2_BRIGHT_WHITE_MUTED_FIX
# Make formerly muted UI text bright white across V2.
text = re.sub(
    r'BLUE_DIM\s*=\s*"#[0-9A-Fa-f]{6}"\s*;\s*MUTED\s*=\s*"#[0-9A-Fa-f]{6}"\s*;\s*TEXT\s*=\s*"#[0-9A-Fa-f]{6}"',
    'BLUE_DIM  = "#93c5fd"; MUTED     = "#f8fafc"; TEXT = "#f8fafc"',
    text,
    count=1,
)

# Remove misleading Synthetic Options wording in Options Matrix.
text = text.replace(
    'html.P("Synthetic intelligence from price, volume, volatility proxy, and decision score.",',
    'html.P("Options intelligence from price, volume, volatility proxy, and decision score.",'
)

text = text.replace(
    'note_box("Synthetic options layer — connect Tradier or CBOE for live institutional flow data.","blue")',
    'note_box("Options intelligence layer — connect Tradier or CBOE for live institutional flow data.","blue")'
)

if "Synthetic options layer" in text:
    raise SystemExit("FAILED: Synthetic options layer wording still exists.")

if "Synthetic intelligence from price, volume, volatility proxy, and decision score." in text:
    raise SystemExit("FAILED: Synthetic intelligence wording still exists.")

if 'MUTED     = "#f8fafc"; TEXT = "#f8fafc"' not in text:
    raise SystemExit("FAILED: MUTED/TEXT bright white constants were not applied.")

path.write_text(text, encoding="utf-8")
print("V2 BRIGHT WHITE / OPTIONS WORDING PATCH OK")
