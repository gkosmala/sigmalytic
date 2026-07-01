from pathlib import Path
import re

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8", errors="replace")

# FIX_UNDEFINED_QUALITY_RAW

# Replace any use of quality_raw in the pill with the already-existing quality variable.
text = text.replace(
    '_pill(_QUALITY_LABELS.get(quality_raw, quality_raw), quality_color)',
    '_pill(_QUALITY_LABELS.get(quality, quality), quality_color)'
)

text = text.replace(
    '_pill(_QUALITY_LABELS.get(quality_raw, quality), quality_color)',
    '_pill(_QUALITY_LABELS.get(quality, quality), quality_color)'
)

text = text.replace(
    '_pill(_QUALITY_LABELS.get(quality, quality_raw), quality_color)',
    '_pill(_QUALITY_LABELS.get(quality, quality), quality_color)'
)

# If quality_raw is still referenced anywhere, define it safely right before quality assignment.
if "quality_raw" in text and "quality_raw = c.get(\"outcome_quality\")" not in text:
    text = text.replace(
        'quality = str(c.get("outcome_quality") or "UNKNOWN").upper()',
        'quality_raw = c.get("outcome_quality")\n    quality = _label_dash(quality_raw)'
    )

# Final safety: no unresolved quality_raw should remain except its assignment.
bad_refs = []
for line_no, line in enumerate(text.splitlines(), start=1):
    if "quality_raw" in line and "quality_raw =" not in line and "_label_dash(quality_raw)" not in line:
        bad_refs.append(f"{line_no}: {line}")

if bad_refs:
    print("BAD quality_raw refs remain:")
    print("\n".join(bad_refs))
    raise SystemExit(1)

path.write_text(text, encoding="utf-8")
print("QUALITY RAW ERROR FIX OK")
