from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "frontend" / "app.py"
tab_path = ROOT / "frontend" / "trade_journal_tab.py"

app = app_path.read_text(encoding="utf-8")
tab = tab_path.read_text(encoding="utf-8")

ast.parse(app)
ast.parse(tab)

assert 'id="jrn-submit"' in tab
assert 'id="jrn-direction"' in tab
assert 'id="jrn-portfolio-value"' in tab

assert 'def handle_journal_submit(' in app
assert 'Output("jrn-submit-result", "children")' in app
assert 'Input("jrn-submit", "n_clicks")' in app
assert 'State("jrn-symbol", "value")' in app
assert 'State("jrn-entry-date", "value")' in app
assert 'State("jrn-entry-price", "value")' in app
assert 'State("jrn-shares", "value")' in app
assert 'State("jrn-direction", "value")' in app
assert 'State("jrn-tier", "value")' in app
assert 'State("jrn-notes", "value")' in app
assert 'State("jrn-portfolio-value", "value")' in app
assert 'State("s-session", "data")' in app

assert '_post("/api/journal/entry", payload, headers=_auth_headers(session))' in app
assert '"campaign_id": "manual_journal_entry"' in app
assert '"portfolio_value": portfolio_value' in app
assert 'return note_box(f"Journal entry saved for {symbol}.' in app

print("JOURNAL_SUBMIT_CALLBACK_STATIC_TEST_PASS")
