"""Alert emails, the daily summary and SMS carry the Weis setup state only: no composite score,
trigger or projection paths, and the minimum-score setting does not gate them."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend import radar_alerts, sms_alerts, email_service

ROW = {
    "symbol": "XOM", "price": 158.36, "change_pct": 0.3, "status": "Armed", "status_direction": "long",
    "status_reason": "Spring: the break closed back inside the line", "status_stop": 154.1, "status_target": 165.8,
    # old-engine fields that must not appear
    "composite_score": 77, "trigger": 999.11, "invalidation": 888.22, "target1": 777.33, "target2": 666.44,
    "regime": "OLDREGIME", "setup_type": "OLDSETUP", "trigger_proximity": 4.2,
}
OLD_MARKERS = ["77", "999.11", "888.22", "777.33", "666.44", "OLDREGIME", "OLDSETUP", "Score", "Projection", "Bull Path"]


def test_status_email_is_weis_only():
    html = radar_alerts._build_status_change_email_html(ROW, "Setting Up", "Armed")
    for m in ["XOM", "Armed", "Long (spring)", "$154.10", "$165.80", "Spring: the break closed back inside the line"]:
        assert m in html
    for m in OLD_MARKERS:
        assert m not in html, m


def test_sms_is_weis_only():
    body = sms_alerts._build_sms(ROW, "Armed")
    assert "Long (spring)" in body and "$154.10" in body and "$165.80" in body
    for m in ["77", "999.11", "888.22", "777.33", "Score", "trigger"]:
        assert m not in body, m


def test_alert_statuses_are_weis_armed_states():
    assert radar_alerts.ALERT_STATUSES == {"Armed", "Short Armed"}


def test_daily_summary_lists_weis_states_in_order(monkeypatch):
    captured = {}

    class FakeThread:
        def __init__(self, target, daemon=None):
            self.target = target
        def start(self):
            pass

    async def fake_dispatch(alert, subject, html_body, background_tasks=None):
        captured["alert"], captured["html"] = alert, html_body

    monkeypatch.setattr(radar_alerts, "dispatch_alert_to_all_users", fake_dispatch)
    import threading
    monkeypatch.setattr(threading, "Thread", FakeThread)
    rows = [
        dict(ROW, symbol="BBB", status="Watching", composite_score=99),
        dict(ROW, symbol="AAA", status="Armed", composite_score=1),
        dict(ROW, symbol="CCC", status="Avoid", composite_score=90),
        dict(ROW, symbol="DDD", status="Setting Up", composite_score=50),
    ]
    sent = {}
    orig_start = FakeThread.start
    def run_target(self):
        self.target()
    monkeypatch.setattr(FakeThread, "start", run_target)
    assert radar_alerts.send_daily_summary(rows) is True
    html = captured["html"]
    assert html.index("AAA") < html.index("DDD") < html.index("BBB")
    assert "CCC" not in html
    assert "Score" not in html and "99" not in html
    assert captured["alert"]["weis_state"] is True


def test_daily_summary_with_no_weis_setups_sends_nothing():
    assert radar_alerts.send_daily_summary([dict(ROW, status="Avoid")]) is False


def test_min_score_does_not_gate_weis_alerts():
    from datetime import datetime, timezone
    ts = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)  # Wednesday, market hours
    prefs = {"min_score": 90, "market_hours_only": True}
    assert email_service.user_wants_alert(prefs, {"symbol": "X", "alert_type": "ab_score", "score": 0, "timestamp": ts}) is False
    assert email_service.user_wants_alert(prefs, {"symbol": "X", "alert_type": "ab_score", "score": 0, "weis_state": True, "timestamp": ts}) is True
