from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "frontend" / "app.py"

app = app_path.read_text(encoding="utf-8")
ast.parse(app)

assert "def _journal_entry_no_reset(" in app
assert "def _journal_entry_reset(" in app
assert "def _journal_exit_no_reset(" in app
assert "def _journal_exit_reset(" in app

assert 'Output("jrn-symbol", "value")' in app
assert 'Output("jrn-entry-date", "value")' in app
assert 'Output("jrn-entry-price", "value")' in app
assert 'Output("jrn-shares", "value")' in app
assert 'Output("jrn-direction", "value")' in app
assert 'Output("jrn-tier", "value")' in app
assert 'Output("jrn-notes", "value")' in app
assert 'Output("jrn-portfolio-value", "value")' in app

assert 'Output("jrn-exit-id", "value")' in app
assert 'Output("jrn-exit-date", "value")' in app
assert 'Output("jrn-exit-price", "value")' in app
assert 'Output("jrn-exit-reason", "value")' in app
assert 'Output("jrn-exit-notes", "value")' in app

assert 'return (message, "", None, None, None, "LONG", None, "", 10000)' in app
assert 'return (message, None, None, None, "MANUAL", "")' in app
assert "Form reset. Auto-refreshing journal table." in app
assert "_journal_entry_reset(html.Div([" in app
assert "_journal_exit_reset(html.Div([" in app
assert "_journal_entry_no_reset(note_box(" in app
assert "_journal_exit_no_reset(note_box(" in app

print("JOURNAL_FORM_RESET_STATIC_TEST_PASS")
