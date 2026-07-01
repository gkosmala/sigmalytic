from pathlib import Path
import re

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8", errors="replace")

# FINAL_CAMPAIGN_QUALITY_STABILIZER
# Insert safe defaults before the campaign row starts reading fields.

if "FINAL_CAMPAIGN_QUALITY_STABILIZER" not in text:
    pattern = re.compile(r'(\n\s*symbol\s*=\s*c\.get\("symbol",.*?\)\n)', re.DOTALL)

    insert = '''
    # FINAL_CAMPAIGN_QUALITY_STABILIZER
    quality = "—"
    quality_score = 0
    quality_score_display = "—"
    quality_value = c.get("outcome_quality")
    if quality_value is not None and quality_value != "" and str(quality_value).upper() not in {"UNKNOWN", "NONE", "NULL", "NAN"}:
        quality = str(quality_value).upper()

    quality_score_value = c.get("outcome_quality_score")
    if quality_score_value is not None and quality_score_value != "" and str(quality_score_value).upper() not in {"UNKNOWN", "NONE", "NULL", "NAN"}:
        try:
            quality_score = float(quality_score_value)
            quality_score_display = f"{quality_score:.0f}"
        except Exception:
            quality_score = 0
            quality_score_display = "—"

'''

    text, count = pattern.subn(insert + r'\1', text, count=1)

    if count != 1:
        raise SystemExit("FAILED: could not find campaign row symbol assignment.")

# Remove broken undefined names.
text = text.replace("quality_raw", "quality_value")

# Make quality label lookup safe if prior patches changed it.
text = text.replace("_QUALITY_LABELS.get(quality_value, quality_value)", "_QUALITY_LABELS.get(quality, quality)")
text = text.replace("_QUALITY_LABELS.get(quality_value, quality)", "_QUALITY_LABELS.get(quality, quality)")
text = text.replace("_QUALITY_LABELS.get(quality, quality_value)", "_QUALITY_LABELS.get(quality, quality)")

path.write_text(text, encoding="utf-8")
print("FINAL CAMPAIGN QUALITY STABILIZER OK")
