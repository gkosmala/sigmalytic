from pathlib import Path

path = Path("frontend/sigmalytic_app_TODAY.py")
text = path.read_text(encoding="utf-8", errors="replace")

# V2_PREF_ADMIN_EXTERNAL_WIRING_ONLY
# Proven issue:
# sigmalytic_app_TODAY.py imports preferences_tab/admin_tab,
# but later defines duplicate build_preferences_tab/build_admin_tab functions.
# Python uses the later duplicate definitions.
# This aliases the imports and calls the external fixed modules directly.

text = text.replace(
    "from preferences_tab import build_preferences_tab",
    "from preferences_tab import build_preferences_tab as build_preferences_tab_external"
)

text = text.replace(
    "from admin_tab import build_admin_tab",
    "from admin_tab import build_admin_tab as build_admin_tab_external"
)

text = text.replace(
    "main = build_preferences_tab(user_id=USER_ID, session=None)",
    "main = build_preferences_tab_external(user_id=USER_ID, session=None)"
)

text = text.replace(
    "main = build_admin_tab(session={\"email\": ADMIN_EMAIL}, backend_url=BACKEND_HTTP)",
    "main = build_admin_tab_external(session={\"email\": ADMIN_EMAIL}, backend_url=BACKEND_HTTP)"
)

path.write_text(text, encoding="utf-8")
print("PREFERENCES / ADMIN EXTERNAL WIRING FIX APPLIED")
