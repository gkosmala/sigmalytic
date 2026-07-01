from pathlib import Path

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8", errors="replace")

# CAMPAIGN_QUALITY_VARIABLE_REPAIR
# Remove broken leftover variable name.
text = text.replace("quality_raw", "quality_value")

# Remove known broken assignment pattern if it exists.
text = text.replace(
'''quality = c.get("outcome_quality")
    quality = _label_dash(quality)''',
'''quality_value = c.get("outcome_quality")
    quality = "—" if quality_value is None or quality_value == "" or str(quality_value).upper() in {"UNKNOWN", "NONE", "NULL", "NAN"} else str(quality_value).upper()'''
)

# Insert a guaranteed quality block immediately after transition bias is assigned.
needle = 'bias = str(c.get("transition_bias") or "UNKNOWN").upper()\n'
repair = '''bias = str(c.get("transition_bias") or "UNKNOWN").upper()

    # CAMPAIGN_QUALITY_VARIABLE_REPAIR
    quality_value = c.get("outcome_quality")
    if quality_value is None or quality_value == "" or str(quality_value).upper() in {"UNKNOWN", "NONE", "NULL", "NAN"}:
        quality = "—"
    else:
        quality = str(quality_value).upper()

    quality_score_value = c.get("outcome_quality_score")
    quality_score = _safe_float(quality_score_value, 0)
    if quality_score_value is None or quality_score_value == "" or str(quality_score_value).upper() in {"UNKNOWN", "NONE", "NULL", "NAN"}:
        quality_score_display = "—"
    else:
        quality_score_display = f"{quality_score:.0f}"
'''

if needle not in text:
    raise SystemExit("FAILED: could not find transition bias assignment line.")

# Avoid duplicate repair block.
if "# CAMPAIGN_QUALITY_VARIABLE_REPAIR" not in text:
    text = text.replace(needle, repair, 1)
else:
    # If marker already exists from a prior failed patch, still ensure the repair block is present after bias.
    if "quality_score_display = f\"{quality_score:.0f}\"" not in text:
        text = text.replace(needle, repair, 1)

# Make all quality pill calls use the guaranteed quality variable.
text = text.replace("_QUALITY_LABELS.get(quality_value, quality_value)", "_QUALITY_LABELS.get(quality, quality)")
text = text.replace("_QUALITY_LABELS.get(quality_value, quality)", "_QUALITY_LABELS.get(quality, quality)")
text = text.replace("_QUALITY_LABELS.get(quality, quality_value)", "_QUALITY_LABELS.get(quality, quality)")

# Safety check.
if "quality_raw" in text:
    raise SystemExit("FAILED: quality_raw still exists.")

path.write_text(text, encoding="utf-8")
print("CAMPAIGN QUALITY VARIABLE REPAIR OK")
