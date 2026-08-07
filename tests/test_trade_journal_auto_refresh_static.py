from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
app_path = ROOT / "frontend" / "app.py"
tab_path = ROOT / "frontend" / "trade_journal_tab.py"

app = app_path.read_text(encoding="utf-8")
tab = tab_path.read_text(encoding="utf-8")

ast.parse(app)
ast.parse(tab)

assert 'id="jrn-auto-refresh-dummy"' in tab
assert 'ttl_seconds=1' in tab
assert tab.count('ttl_seconds=1') >= 2
assert 'ttl_seconds=15' not in tab

assert "JOURNAL_AUTO_REFRESH_CLIENTSIDE_CALLBACK" in app
assert "jrn-entry-auto-refresh" in app
assert "jrn-exit-auto-refresh" in app
assert "dcc.Interval" in app
assert "interval=1500" in app
assert "max_intervals=1" in app
assert "app.clientside_callback" in app
assert "window.location.reload()" in app
assert 'Output("jrn-auto-refresh-dummy", "children")' in app
assert 'Input("jrn-entry-auto-refresh", "n_intervals")' in app
assert 'Input("jrn-exit-auto-refresh", "n_intervals")' in app
assert "Auto-refreshing journal table" in app

assert "Refresh the Journal tab to reload the table" not in app

print("JOURNAL_AUTO_REFRESH_STATIC_TEST_PASS")
