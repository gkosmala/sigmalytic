from pathlib import Path
import re

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8", errors="replace")

# HARD_REPAIR_CAMPAIGN_QUALITY_SCOPE
# This prevents "quality not associated with a value" regardless of later display code.

pattern = re.compile(
    r'(def\s+_campaign_row\s*\(\s*c\s*\)\s*:\s*\n)',
    re.MULTILINE
)

repair = '''\\1    # HARD_REPAIR_CAMPAIGN_QUALITY_SCOPE
    quality = "—"
    quality_score = 0
    quality_score_display = "—"

'''

text, count = pattern.subn(repair, text, count=1)

if count != 1:
    raise SystemExit("FAILED: could not find def _campaign_row(c):")

# Remove the broken undefined name completely.
text = text.replace("quality_raw", "quality")

# Make label lookup safe.
text = text.replace(
    "_QUALITY_LABELS.get(quality, quality)",
    "_QUALITY_LABELS.get(str(quality).upper(), quality)"
)

path.write_text(text, encoding="utf-8")
print("CAMPAIGN QUALITY SCOPE HARD REPAIR OK")
