"""Imbalance tab: admin-only 'Scan now' button that runs one scan and reloads the log and track record."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
os.environ["SIGMALYTIC_ADMIN_EMAILS"] = "owner@example.com"
import app as dash_app  # noqa: E402
import imbalance_tab as it  # noqa: E402

RESULT = {"scanned": 13, "fired": [{"symbol": "AAPL", "direction": "LONG", "tier": "STRONG", "emailed": True}],
          "skipped": [{"symbol": "MU", "reason": "cooldown"}], "errors": [{"symbol": "ORCL", "error": "no data"}]}


def test_result_summarises_fired_skipped_errors():
    t = str(it.render_scan_result(RESULT))
    assert "Scanned 13 symbols: 1 alert(s) fired, 1 skipped, 1 error(s)." in t
    assert "AAPL LONG (STRONG)" in t and "MU (cooldown)" in t and "ORCL: no data" in t


def test_result_says_nothing_fired():
    t = str(it.render_scan_result({"scanned": 13, "fired": [], "skipped": [], "errors": []}))
    assert "Nothing fired" in t


def test_admin_page_has_button_result_and_panels(monkeypatch):
    monkeypatch.setattr(it, "_get", lambda path, s: {"symbols": ["SPY"], "live": False, "scan_enabled": True,
                                                    "admin_preview": True, "alerts": [], "by_horizon": {}, "alerts_n": 0})
    t = str(it.build_imbalance_tab({"email": "owner@example.com"}, admin=True))
    assert "imbalance-scan-btn" in t and "imbalance-scan-result" in t and "imbalance-panels" in t


def test_guest_page_has_no_button():
    assert "imbalance-scan-btn" not in str(it.build_imbalance_tab(None, admin=False))


def test_callback_refuses_non_admin_and_does_not_post(monkeypatch):
    monkeypatch.setattr(it, "_post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not post")))
    msg, panels = dash_app.handle_imbalance_scan_now(1, {"email": "guest@example.com"})
    assert "Admin access only" in msg


def test_callback_runs_scan_for_admin(monkeypatch):
    monkeypatch.setattr(it, "_post", lambda path, s, timeout=180: RESULT)
    monkeypatch.setattr(it, "build_panels", lambda s: ["panels"])
    out, panels = dash_app.handle_imbalance_scan_now(1, {"email": "owner@example.com"})
    assert "Scanned 13 symbols" in str(out) and panels == ["panels"]


def test_callback_reports_backend_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("/api/imbalance/scan returned 500")
    monkeypatch.setattr(it, "_post", boom)
    out, panels = dash_app.handle_imbalance_scan_now(1, {"email": "owner@example.com"})
    assert "Scan could not run" in str(out)
