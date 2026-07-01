from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# V2_FORCE_BRIGHT_WHITE_MUTED_TEXT_ONLY
# Color-only fix. Does not alter callbacks, tabs, options wording, chart logic, or backend.

# 1. Force the main muted/text constants back to bright white.
text = re.sub(
    r'BLUE_DIM\s*=\s*"#[0-9a-fA-F]{6}"\s*;\s*MUTED\s*=\s*"#[0-9a-fA-F]{6}"\s*;\s*TEXT\s*=\s*"#[0-9a-fA-F]{6}"',
    'BLUE_DIM  = "#93c5fd"; MUTED = "#f8fafc"; TEXT = "#f8fafc"',
    text,
    count=1
)

# 2. Replace common slate/gray muted colors that are hard-coded in Radar, Scoreboard, Divergence, and tile text.
for old in [
    "#64748b", "#94a3b8", "#475569", "#334155",
    "rgb(100,116,139)", "rgb(148,163,184)",
    "rgba(100,116,139,.65)", "rgba(100,116,139,.75)",
    "rgba(148,163,184,.55)", "rgba(148,163,184,.65)", "rgba(148,163,184,.75)",
]:
    text = text.replace(old, "#f8fafc")

# 3. Make any low-opacity muted table/card text readable.
text = text.replace('"opacity":".55"', '"opacity":"1"')
text = text.replace('"opacity":".6"', '"opacity":"1"')
text = text.replace('"opacity":".65"', '"opacity":"1"')
text = text.replace('"opacity":"0.55"', '"opacity":"1"')
text = text.replace('"opacity":"0.6"', '"opacity":"1"')
text = text.replace('"opacity":"0.65"', '"opacity":"1"')

path.write_text(text, encoding="utf-8")
print("BRIGHT WHITE MUTED TEXT RESTORED")
