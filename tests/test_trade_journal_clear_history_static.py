from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

service = (ROOT / "backend" / "trade_journal_service.py").read_text(encoding="utf-8")
api = (ROOT / "backend" / "trade_journal_api.py").read_text(encoding="utf-8")
tab = (ROOT / "frontend" / "trade_journal_tab.py").read_text(encoding="utf-8")
app = (ROOT / "frontend" / "app.py").read_text(encoding="utf-8")

ast.parse(service)
ast.parse(api)
ast.parse(tab)
ast.parse(app)

assert "def clear_journal_history(user_id: str)" in service
assert 'sb.table("trade_journal").delete().eq("user_id", user_id).execute()' in service
assert 'sb.table("trader_profile").delete().eq("user_id", user_id).execute()' in service
assert '"deleted": deleted_count' in service

assert "clear_journal_history" in api
assert '@journal_router.post("/clear")' in api
assert "user_id = get_user_id_from_request(request)" in api
assert "result = clear_journal_history(user_id)" in api

assert "def _clear_history_form(" in tab
assert "jrn-clear-history-submit" in tab
assert "jrn-clear-history-result" in tab
assert "_card([_clear_history_form()])" in tab

assert "def handle_journal_clear_history(" in app
assert 'Output("jrn-clear-history-result", "children")' in app
assert 'Input("jrn-clear-history-submit", "n_clicks")' in app
assert 'f"{BACKEND_HTTP}/api/journal/clear"' in app
assert "Journal history cleared. Deleted {deleted} rows." in app
assert "jrn-clear-auto-refresh" in app
assert 'Input("jrn-clear-auto-refresh", "n_intervals")' in app
assert "entry > 0 || exit > 0 || clear > 0" in app

print("JOURNAL_CLEAR_HISTORY_STATIC_TEST_PASS")
