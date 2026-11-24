"""Admin page stays light (2026-11-24): long tables are capped with a "Showing X of Y" note."""
import json

import plotly.utils

from frontend import imbalance_tab as I
from frontend import paper_trading_ui as P


def _s(c):
    return json.dumps(c, cls=plotly.utils.PlotlyJSONEncoder)


def test_paper_tables_are_capped_with_a_note():
    fills = [{"at": None, "symbol": "X", "action": "buy", "qty": 1, "price": 1.0, "fee": 0.0, "pnl": None,
              "reason": "", "cash_after": 1.0}] * 300
    out = _s(P.render_journal({"closed": [], "stats": {}}, {"ok": True, "fills": fills, "not_taken": []}))
    assert "Showing 25 of 300." in out
    assert out.count('"type": "Tr"') <= 30


def test_short_tables_have_no_note():
    out = _s(P._table(["a"], [["x"], ["y"]]))
    assert "Showing" not in out


def test_imbalance_readings_capped_fired_first():
    rd = [{"symbol": f"S{i:03d}", "pillars": {}, "fired": i == 399, "at": "2026-11-24T14:00"} for i in range(400)]
    out = _s(I.render_readings(rd))
    assert "Showing 50 of 400" in out and out.index("S399") < out.index("S000")
