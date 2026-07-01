from pathlib import Path
import re

path = Path("frontend/campaign_tab.py")
text = path.read_text(encoding="utf-8", errors="replace")

# CAMPAIGN_OUTCOME_NO_FAKE_ZERO_FIX

# Ensure formatting helpers exist.
helper = '''
def _missing(value):
    return value is None or value == "" or str(value).lower() in {"none", "null", "nan"}

def _pct_dash(value, digits=1, signed=False):
    if _missing(value):
        return "—"
    try:
        v = float(value)
        sign = "+" if signed and v >= 0 else ""
        return f"{sign}{v:.{digits}f}%"
    except Exception:
        return "—"

def _num_dash(value, digits=0):
    if _missing(value):
        return "—"
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "—"

def _label_dash(value):
    if _missing(value):
        return "—"
    v = str(value).strip().upper()
    return "—" if v in {"UNKNOWN", "NONE", "NULL", "NAN"} else v

'''

if "def _pct_dash(value" not in text:
    marker = "def _safe_float"
    idx = text.find(marker)
    if idx == -1:
        raise SystemExit("FAILED: could not find helper insertion point.")
    text = text[:idx] + helper + "\n" + text[idx:]

# Replace outcome assignments that force missing values to zero.
repls = {
    'quality = str(c.get("outcome_quality") or "UNKNOWN").upper()':
        'quality_raw = c.get("outcome_quality")\n    quality = _label_dash(quality_raw)',
    'quality_score = _safe_float(c.get("outcome_quality_score"), 0)':
        'quality_score_raw = c.get("outcome_quality_score")\n    quality_score = _safe_float(quality_score_raw, 0)\n    quality_score_display = _num_dash(quality_score_raw, 0)',
    'exp_return = _safe_float(c.get("outcome_expected_return"), 0)':
        'exp_return_raw = c.get("outcome_expected_return")\n    exp_return = _safe_float(exp_return_raw, 0)\n    exp_return_display = _pct_dash(exp_return_raw, 1, signed=True)',
    'exp_mfe = _safe_float(c.get("outcome_expected_mfe"), 0)':
        'exp_mfe_raw = c.get("outcome_expected_mfe")\n    exp_mfe = _safe_float(exp_mfe_raw, 0)\n    exp_mfe_display = _pct_dash(exp_mfe_raw, 1, signed=True)',
    'exp_mae = _safe_float(c.get("outcome_expected_mae"), 0)':
        'exp_mae_raw = c.get("outcome_expected_mae")\n    exp_mae = _safe_float(exp_mae_raw, 0)\n    exp_mae_display = _pct_dash(exp_mae_raw, 1, signed=True)',
    'exp_days = _safe_int(c.get("outcome_expected_duration_days"), 0)':
        'exp_days_raw = c.get("outcome_expected_duration_days")\n    exp_days = _safe_int(exp_days_raw, 0)\n    exp_days_display = _num_dash(exp_days_raw, 0)',
    't1 = _safe_float(c.get("outcome_target1_prob"), 0)':
        't1_raw = c.get("outcome_target1_prob")\n    t1 = _safe_float(t1_raw, 0)\n    t1_display = _pct_dash(t1_raw, 0)',
    't2 = _safe_float(c.get("outcome_target2_prob"), 0)':
        't2_raw = c.get("outcome_target2_prob")\n    t2 = _safe_float(t2_raw, 0)\n    t2_display = _pct_dash(t2_raw, 0)',
    'fail = _safe_float(c.get("outcome_failure_prob"), 0)':
        'fail_raw = c.get("outcome_failure_prob")\n    fail = _safe_float(fail_raw, 0)\n    fail_display = _pct_dash(fail_raw, 0)',
    'rr = _safe_float(c.get("outcome_risk_reward"), 0)':
        'rr_raw = c.get("outcome_risk_reward")\n    rr = _safe_float(rr_raw, 0)\n    rr_display = _num_dash(rr_raw, 2)',
}

for old, new in repls.items():
    text = text.replace(old, new)

# Replace common visible fake-zero renderings.
visible_repls = {
    'f"Score {quality_score:.0f}"': 'f"Score {quality_score_display}"',
    'f"{exp_days}d"': 'f"{exp_days_display}d" if exp_days_display != "—" else "—"',
    'f"{exp_return:+.1f}%"': 'exp_return_display',
    'f"{exp_mfe:+.1f}%"': 'exp_mfe_display',
    'f"{exp_mae:+.1f}%"': 'exp_mae_display',
    'f"{t1:.0f}%"': 't1_display',
    'f"{t2:.0f}%"': 't2_display',
    'f"{fail:.0f}%"': 'fail_display',
    'f"{rr:.2f}"': 'rr_display',
}

for old, new in visible_repls.items():
    text = text.replace(old, new)

# Safety checks.
bad_patterns = [
    'outcome_expected_return"), 0)',
    'outcome_expected_mfe"), 0)',
    'outcome_expected_mae"), 0)',
    'outcome_target1_prob"), 0)',
    'outcome_target2_prob"), 0)',
    'outcome_failure_prob"), 0)',
    'outcome_risk_reward"), 0)',
    'f"{exp_return:+.1f}%"',
    'f"{exp_mfe:+.1f}%"',
    'f"{exp_mae:+.1f}%"',
    'f"{t1:.0f}%"',
    'f"{t2:.0f}%"',
    'f"{fail:.0f}%"',
    'f"{rr:.2f}"',
]

remaining = [p for p in bad_patterns if p in text]
if remaining:
    print("WARNING: some fake-zero patterns remain:")
    for item in remaining:
        print(" -", item)

path.write_text(text, encoding="utf-8")
print("CAMPAIGN OUTCOME NO FAKE ZERO PATCH OK")
