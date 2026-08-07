from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "frontend" / "app.py"
tab_path = ROOT / "frontend" / "trade_journal_tab.py"

app = app_path.read_text(encoding="utf-8")
tab = tab_path.read_text(encoding="utf-8")

ast.parse(app)
ast.parse(tab)

assert "def _exit_trade_form(" in tab
assert "jrn-exit-id" in tab
assert "jrn-exit-date" in tab
assert "jrn-exit-price" in tab
assert "jrn-exit-reason" in tab
assert "jrn-exit-notes" in tab
assert "jrn-exit-result" in tab
assert "jrn-exit-submit" in tab
assert "_card([_exit_trade_form(open_trades)])" in tab

assert "def handle_journal_exit(" in app
assert 'Output("jrn-exit-result", "children")' in app
assert 'Input("jrn-exit-submit", "n_clicks")' in app
assert 'State("jrn-exit-id", "value")' in app
assert 'State("jrn-exit-date", "value")' in app
assert 'State("jrn-exit-price", "value")' in app
assert 'State("jrn-exit-reason", "value")' in app
assert 'State("jrn-exit-notes", "value")' in app
assert 'State("s-session", "data")' in app

assert 'f"{BACKEND_HTTP}/api/journal/exit/{journal_id}"' in app
assert '"exit_date": exit_date' in app
assert '"exit_price": exit_price' in app
assert '"exit_reason": exit_reason' in app
assert "timeout=20" in app
assert "Journal exit saved for {journal_id}" in app
assert "HTTP {r.status_code}" in app

print("JOURNAL_EXIT_CALLBACK_STATIC_TEST_PASS")
