from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
tab_path = ROOT / "frontend" / "trade_journal_tab.py"
app_path = ROOT / "frontend" / "app.py"

tab = tab_path.read_text(encoding="utf-8")
app = app_path.read_text(encoding="utf-8")

ast.parse(tab)
ast.parse(app)

assert "def _current_user_id(session=None)" in tab
assert "def _auth_headers(session=None)" in tab

assert 'user_id = "demo_user_001"  # replaced with real user_id when auth is wired' not in tab
assert "user_id = _current_user_id(session)" in tab

assert 'headers={"Authorization": "Bearer demo"}' not in tab
assert "headers=_auth_headers(session)" in tab

assert 'shared_cache.get_or_fetch(f"/api/journal/trades:{user_id}"' in tab
assert 'shared_cache.get_or_fetch(f"/api/journal/profile:{user_id}"' in tab

assert "main = build_trade_journal_tab(session=session)" in app

print("JOURNAL_FRONTEND_IDENTITY_STATIC_TEST_PASS")
