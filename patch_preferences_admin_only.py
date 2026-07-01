from pathlib import Path
import re

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# V2_FIX_PREF_ADMIN_ONLY
# Only fixes Preferences/Admin tab loading. Does not touch other tabs/screens.

# 1. Add safe imports if missing.
insert_after = '''try:
    from trade_journal_tab import build_trade_journal_tab
    _JOURNAL_TAB_AVAILABLE = True
except Exception as _jt:
    _JOURNAL_TAB_AVAILABLE = False
    print(f"TRADE_JOURNAL_TAB: FAILED'''
    
if "from preferences_tab import build_preferences_tab" not in text:
    marker = 'BACKEND_HTTP = os.getenv("BACKEND_URL"'
    imports = '''
try:
    from preferences_tab import build_preferences_tab
    _PREFERENCES_TAB_AVAILABLE = True
except Exception as _ptab:
    _PREFERENCES_TAB_AVAILABLE = False
    print(f"PREFERENCES_TAB: FAILED - {_ptab}", flush=True)

try:
    from admin_tab import build_admin_tab
    _ADMIN_TAB_AVAILABLE = True
except Exception as _atab:
    _ADMIN_TAB_AVAILABLE = False
    print(f"ADMIN_TAB: FAILED - {_atab}", flush=True)

'''
    if marker not in text:
        raise SystemExit("Could not find import insertion marker. Do not deploy.")
    text = text.replace(marker, imports + marker, 1)

# 2. Replace only the Preferences branch.
pref_old_patterns = [
    'elif tab=="preferences": main = build_preferences_tab(user_id="", session=None)',
]

pref_new = '''elif tab=="preferences":
        if _PREFERENCES_TAB_AVAILABLE:
            try:
                main = build_preferences_tab(user_id=USER_ID, session=None)
            except Exception as e:
                main = html.Div([
                    html.Div("Preferences tab error", style={"color":"#f87171","fontWeight":"800","marginBottom":"8px"}),
                    html.Div(str(e), style={"color":WHITE,"fontSize":"12px","fontFamily":"monospace"}),
                ], style={"padding":"60px","textAlign":"center"})
        else:
            main = html.Div("Preferences tab unavailable - check frontend/preferences_tab.py import.", style={"color":WHITE,"padding":"60px","textAlign":"center"})'''

if pref_old_patterns[0] in text:
    text = text.replace(pref_old_patterns[0], pref_new, 1)
else:
    text = re.sub(
        r'elif tab=="preferences":\n\s+try:\n\s+main = build_preferences_tab\(.*?\)\n\s+except Exception as e:\n\s+main = card\(\[.*?\]\)',
        pref_new,
        text,
        count=1,
        flags=re.DOTALL
    )

# 3. Replace only the Admin branch.
admin_new = '''elif tab=="admin":
        if _ADMIN_TAB_AVAILABLE:
            try:
                main = build_admin_tab(session={"email": ADMIN_EMAIL}, backend_url=BACKEND_HTTP)
            except Exception as e:
                main = html.Div([
                    html.Div("Admin tab error", style={"color":"#f87171","fontWeight":"800","marginBottom":"8px"}),
                    html.Div(str(e), style={"color":WHITE,"fontSize":"12px","fontFamily":"monospace"}),
                ], style={"padding":"60px","textAlign":"center"})
        else:
            main = html.Div("Admin tab unavailable - check frontend/admin_tab.py import.", style={"color":WHITE,"padding":"60px","textAlign":"center"})'''

# Replace common one-line admin branch.
text = re.sub(
    r'elif tab=="admin":\s+main = build_admin_tab\(.*?\)',
    admin_new,
    text,
    count=1,
    flags=re.DOTALL
)

# Replace try-wrapped admin branch if present.
text = re.sub(
    r'elif tab=="admin":\n\s+try:\n\s+main = build_admin_tab\(.*?\)\n\s+except Exception as e:\n\s+main = html\.Div\(\[.*?\], style=\{"padding":"60px","textAlign":"center"\}\)',
    admin_new,
    text,
    count=1,
    flags=re.DOTALL
)

path.write_text(text, encoding="utf-8")
print("PREFERENCES / ADMIN ONLY FIX APPLIED")
