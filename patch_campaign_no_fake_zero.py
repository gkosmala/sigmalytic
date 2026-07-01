from pathlib import Path
import re

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8")

# CAMPAIGN_NO_FAKE_ZERO_FIX
# Add missing-value helpers.
helper = '''
def _has_real_value(value):
    return value is not None and value != ""

def _fmt_pct_or_dash(value, digits=0):
    if not _has_real_value(value):
        return "—"
    try:
        return f"{float(value):.{digits}f}%"
    except Exception:
        return "—"

def _fmt_num_or_dash(value, digits=0):
    if not _has_real_value(value):
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "—"

'''

if "def _fmt_pct_or_dash" not in text:
    marker = "def _safe_float"
    idx = text.find(marker)
    if idx == -1:
        raise SystemExit("FAILED: could not find helper insertion point before _safe_float.")
    text = text[:idx] + helper + text[idx:]

# Replace common fake-zero renderings for campaign row fields.
replacements = {
    'f"Day {int(_safe_float(c.get(\'campaign_age_days\'), 0))}"': 'f"Day {_fmt_num_or_dash(c.get(\'campaign_age_days\'), 0)}"',
    'f"Day {int(_safe_float(c.get(\'duration_days\'), 0))}"': 'f"Day {_fmt_num_or_dash(c.get(\'duration_days\'), 0)}"',
    'f"Decay {int(_safe_float(c.get(\'decay_score\'), 0))}"': 'f"Decay {_fmt_num_or_dash(c.get(\'decay_score\'), 0)}"',
    'f"Adv {_safe_float(c.get(\'transition_advance_prob\'), 0):.0f}% / Fail {_safe_float(c.get(\'transition_failure_prob\'), 0):.0f}%"': 'f"Adv {_fmt_pct_or_dash(c.get(\'transition_advance_prob\'), 0)} / Fail {_fmt_pct_or_dash(c.get(\'transition_failure_prob\'), 0)}"',
}

for old, new in replacements.items():
    text = text.replace(old, new)

# Regex fallback for equivalent formatting patterns.
text = re.sub(
    r'_safe_float\(c\.get\("transition_advance_prob"\),\s*0\):\.0f\}%',
    r'_fmt_pct_or_dash(c.get("transition_advance_prob"), 0)}',
    text
)
text = re.sub(
    r'_safe_float\(c\.get\("transition_failure_prob"\),\s*0\):\.0f\}%',
    r'_fmt_pct_or_dash(c.get("transition_failure_prob"), 0)}',
    text
)
text = re.sub(
    r'int\(_safe_float\(c\.get\("decay_score"\),\s*0\)\)',
    r'_fmt_num_or_dash(c.get("decay_score"), 0)',
    text
)
text = re.sub(
    r'int\(_safe_float\(c\.get\("campaign_age_days"\),\s*0\)\)',
    r'_fmt_num_or_dash(c.get("campaign_age_days"), 0)',
    text
)
text = re.sub(
    r'int\(_safe_float\(c\.get\("duration_days"\),\s*0\)\)',
    r'_fmt_num_or_dash(c.get("duration_days"), 0)',
    text
)

path.write_text(text, encoding="utf-8")
print("CAMPAIGN NO FAKE ZERO PATCH OK")
