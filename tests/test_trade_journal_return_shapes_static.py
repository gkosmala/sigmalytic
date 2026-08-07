from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "frontend" / "app.py").read_text(encoding="utf-8")
ast.parse(app)

assert "if not n_clicks:\n        return _journal_entry_no_reset(no_update)\n\n    symbol =" in app
assert 'return _journal_entry_no_reset(note_box("Journal entry blocked: direction must be LONG or SHORT.", "yellow"))' in app
assert 'return _journal_entry_no_reset(note_box("Journal entry blocked: entry price must be greater than zero.", "yellow"))' in app
assert 'return _journal_entry_no_reset(note_box("Journal entry blocked: shares must be greater than zero.", "yellow"))' in app
assert "Journal entry failed: request exception" in app
assert "return _journal_entry_no_reset(note_box(\n            f\"Journal entry failed: request exception:" in app

assert "if not n_clicks:\n        return _journal_exit_no_reset(no_update)\n\n    journal_id =" in app

print("JOURNAL_FORM_RESET_RETURN_SHAPE_TEST_PASS")
