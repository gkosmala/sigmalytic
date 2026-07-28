from pathlib import Path
from datetime import datetime, timezone
import re

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8", errors="replace")

# Insert helpers after _safe_int if they are not already present.
helper = '''
def _is_missing(value):
    return value is None or value == "" or str(value).lower() in {"none", "null", "nan"}

def _fmt_num_or_dash(value, digits=0):
    if _is_missing(value):
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "—"

def _fmt_pct_or_dash(value, digits=0):
    if _is_missing(value):
        return "—"
    try:
        return f"{float(value):.{digits}f}%"
    except Exception:
        return "—"

def _campaign_days(c):
    raw = c.get("campaign_age_days")
    if not _is_missing(raw):
        try:
            val = int(float(raw))
            if val > 0:
                return str(val)
        except Exception:
            pass

    for key in ["state_changed_at", "created_at", "birth_date", "updated_at"]:
        dt_raw = c.get(key)
        if _is_missing(dt_raw):
            continue
        try:
            s = str(dt_raw).replace("Z", "+00:00")
            if "T" not in s and len(s) == 10:
                s = s + "T00:00:00+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return str(max(0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days))
        except Exception:
            continue

    return "—"

'''

if "def _campaign_days(c):" not in text:
    m = re.search(r'def _safe_int\(.*?\n(?:    .*\n)+', text)
    if not m:
        raise SystemExit("FAILED: could not find _safe_int helper.")
    insert_at = m.end()
    text = text[:insert_at] + "\n" + helper + text[insert_at:]

# Replace the exact variable assignments.
text = text.replace(
    'days = _safe_int(c.get("campaign_age_days"), 0)',
    'days = _campaign_days(c)'
)

text = text.replace(
    'decay_score = _safe_float(c.get("decay_score"), 0)',
    'decay_raw = c.get("decay_score")\n    decay_score = _safe_float(decay_raw, 0)\n    decay_display = _fmt_num_or_dash(decay_raw, 0)'
)

text = text.replace(
    'adv = _safe_float(c.get("transition_advance_prob"), 0)\n    fail_transition = _safe_float(c.get("transition_failure_prob"), 0)',
    'adv_raw = c.get("transition_advance_prob")\n    fail_raw = c.get("transition_failure_prob")\n    adv = _safe_float(adv_raw, 0)\n    fail_transition = _safe_float(fail_raw, 0)\n    adv_display = _fmt_pct_or_dash(adv_raw, 0)\n    fail_display = _fmt_pct_or_dash(fail_raw, 0)'
)

# Replace the exact visible strings.
text = text.replace(
    'html.Div(f"Day {days}", style={"fontSize": "10px", "color": MUTED, "marginTop": "3px"})',
    'html.Div(f"Day {days}", style={"fontSize": "10px", "color": MUTED, "marginTop": "3px"})'
)

text = text.replace(
    'html.Div(f"Decay {decay_score:.0f}", style={',
    'html.Div(f"Decay {decay_display}", style={'
)

text = text.replace(
    'html.Div(f"Adv {adv:.0f}% / Fail {fail_transition:.0f}%", style={',
    'html.Div(f"Adv {adv_display} / Fail {fail_display}", style={'
)

# Verify the bad display format is gone.
if 'f"Decay {decay_score:.0f}"' in text:
    raise SystemExit("FAILED: old Decay fake-zero display still exists.")

if 'f"Adv {adv:.0f}% / Fail {fail_transition:.0f}%"' in text:
    raise SystemExit("FAILED: old Adv/Fail fake-zero display still exists.")

if 'days = _safe_int(c.get("campaign_age_days"), 0)' in text:
    raise SystemExit("FAILED: old Day fake-zero assignment still exists.")

path.write_text(text, encoding="utf-8")
print("CAMPAIGN DAY DECAY ADV FAIL DISPLAY PATCH OK")
