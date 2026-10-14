"""Run Scan Now: when the scan finishes the Weis Radar page reloads the latest results by itself."""
import os
import sys

from dash import no_update

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
import app as dash_app  # noqa: E402


class _Resp:
    ok = True

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def _poll(monkeypatch, payload, n=3):
    monkeypatch.setattr(dash_app.req, "get", lambda *a, **k: _Resp(payload))
    return dash_app.poll_weis_radar_status(n, {"email": "x@y.com"})


def test_done_triggers_a_refresh_and_stops_polling(monkeypatch):
    msg, disabled, refresh = _poll(monkeypatch, {"status": "done", "hits": 7, "scanned": 1000})
    assert disabled is True and "7 hits out of 1000" in msg and "updated" in msg
    assert refresh["note"] == msg and refresh["ts"] > 0


def test_running_and_error_do_not_refresh(monkeypatch):
    msg, disabled, refresh = _poll(monkeypatch, {"status": "running"})
    assert "Scanning" in msg and disabled is no_update and refresh is no_update
    msg, disabled, refresh = _poll(monkeypatch, {"status": "error", "error": "boom"})
    assert "boom" in msg and disabled is True and refresh is no_update


def test_the_radar_page_shows_the_scan_note(monkeypatch):
    monkeypatch.setenv("SIGMALYTIC_ADMIN_EMAILS", "x@y.com")
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    page = dash_app.build_weis_radar_tab({"email": "x@y.com"}, scan_note="Scan complete -- done")
    assert "Scan complete -- done" in str(page)


def test_the_refresh_store_feeds_render_main():
    assert "s-weis-radar-refresh" in str(dash_app.app.layout)
    spec = dash_app.app.callback_map["..main-content.children...trade-panels-row.style...trade-plan-panel.children...active-trade-panel.children.."]
    assert any(i["id"] == "s-weis-radar-refresh" for i in spec["inputs"])
