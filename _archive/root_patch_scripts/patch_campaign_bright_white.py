from pathlib import Path
import re

files = [
    Path("frontend/campaign_tab.py"),
    Path("frontend/sigmalytic_app_TODAY.py"),
]

changed = []

for path in files:
    if not path.exists():
        print(f"SKIP missing {path}")
        continue

    text = path.read_text(encoding="utf-8")
    original = text

    # Bright white values for muted campaign text.
    text = re.sub(r'MUTED\s*=\s*"#[0-9A-Fa-f]{6}"', 'MUTED = "#f8fafc"', text)
    text = re.sub(r'TEXT\s*=\s*"#[0-9A-Fa-f]{6}"', 'TEXT = "#f8fafc"', text)

    # Replace common hard-coded muted grays used in campaign rows/summaries.
    text = text.replace("#64748b", "#f8fafc")
    text = text.replace("#94a3b8", "#f8fafc")
    text = text.replace("#475569", "#f8fafc")
    text = text.replace("#6b7280", "#f8fafc")
    text = text.replace("#9ca3af", "#f8fafc")

    if text != original:
        path.write_text(text, encoding="utf-8")
        changed.append(str(path))

if not changed:
    raise SystemExit("NO FILES CHANGED — campaign muted colors were not found.")

print("CAMPAIGN BRIGHT WHITE TEXT PATCH OK")
print("Changed:")
for item in changed:
    print(" -", item)
