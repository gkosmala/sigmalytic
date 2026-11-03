"""Platform Review: schedule (Friday 9:15 pm Eastern in both daylight and standard time), Automatic/Manual toggle,
evidence summaries, the number check on findings, and the stored report."""
import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from backend import platform_review as pr  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.kv, self.lists = {}, {}

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    def delete(self, k):
        self.kv.pop(k, None)

    def exists(self, k):
        return int(k in self.kv)

    def lpush(self, k, v):
        self.lists.setdefault(k, []).insert(0, v)

    def ltrim(self, k, a, b):
        self.lists[k] = self.lists.get(k, [])[a:b + 1]

    def lrange(self, k, a, b):
        return self.lists.get(k, [])[a:b + 1]


@pytest.fixture
def redis(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(pr, "_redis", lambda: r)
    return r


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


# ── schedule ──

def test_standard_time_runs_at_0215_utc_saturday():
    # Nov 7, 2026 is a Saturday; 02:15 UTC = Friday Nov 6, 9:15 pm EST.
    assert pr.should_run_scheduled(utc(2026, 11, 7, 2, 15), mode="automatic")["run"] is True
    assert pr.should_run_scheduled(utc(2026, 11, 7, 1, 15), mode="automatic")["run"] is False


def test_daylight_time_runs_at_0115_utc_saturday():
    # Jun 6, 2026 is a Saturday; 01:15 UTC = Friday Jun 5, 9:15 pm EDT.
    assert pr.should_run_scheduled(utc(2026, 6, 6, 1, 15), mode="automatic")["run"] is True
    assert pr.should_run_scheduled(utc(2026, 6, 6, 2, 15), mode="automatic")["run"] is False


def test_manual_mode_skips_the_scheduled_run():
    out = pr.should_run_scheduled(utc(2026, 11, 7, 2, 15), mode="manual")
    assert out["run"] is False and "manual" in out["reason"].lower()


def test_same_friday_does_not_run_twice():
    assert pr.should_run_scheduled(utc(2026, 11, 7, 2, 15), mode="automatic",
                                   last_scheduled="2026-11-06")["run"] is False


def test_next_scheduled_run_is_friday_915_pm_eastern():
    nxt = pr.next_scheduled_run(utc(2026, 11, 3, 14, 0))       # Tuesday
    assert (nxt.weekday(), nxt.hour, nxt.minute, nxt.day) == (4, 21, 15, 6)
    after = pr.next_scheduled_run(utc(2026, 11, 7, 2, 30))     # just after Friday's run
    assert after.day == 13


# ── toggle ──

def test_mode_defaults_to_automatic_and_toggles(redis):
    assert pr.get_mode() == "automatic"
    assert pr.set_mode("manual") == {"ok": True, "mode": "manual"}
    assert pr.get_mode() == "manual"
    assert pr.set_mode("sometimes")["ok"] is False
    assert pr.get_mode() == "manual"


def test_manual_mode_still_allows_run_now(redis, monkeypatch):
    pr.set_mode("manual")
    started = []
    monkeypatch.setattr(pr.threading, "Thread", lambda target, **k: type("T", (), {"start": lambda s: started.append(1)})())
    assert pr.start_review("manual", "owner@example.com")["status"] == "started"
    assert started == [1]


def test_only_one_review_at_a_time(redis, monkeypatch):
    monkeypatch.setattr(pr.threading, "Thread", lambda target, **k: type("T", (), {"start": lambda s: None})())
    assert pr.start_review()["status"] == "started"
    assert pr.start_review()["status"] == "running"


def test_scheduled_call_is_skipped_in_manual_mode(redis):
    pr.set_mode("manual")
    assert pr.start_scheduled(utc(2026, 11, 7, 2, 15))["status"] == "skipped"


# ── evidence ──

def _fetch(sql, params):
    if "scoreboard_signals" in sql:
        return [{"grade": "A", "signal_type": "Triggered", "signals": 40, "evaluated": 30, "direction_evaluated": 30,
                 "direction_correct": 21, "hit_target1": 12, "hit_invalidation": 6, "avg_mfe_pct": 2.4, "avg_mae_pct": 1.1},
                {"grade": "C", "signal_type": "Armed", "signals": 20, "evaluated": 10, "direction_evaluated": 10,
                 "direction_correct": 4, "hit_target1": 1, "hit_invalidation": 5, "avg_mfe_pct": 0.9, "avg_mae_pct": 1.8}]
    return [{"grade": "A", "n": 30}, {"grade": "B", "n": 70}]


def test_signal_outcomes_by_grade():
    out = pr.signal_outcomes(utc(2026, 10, 30), utc(2026, 11, 6), _fetch)
    assert out["all"]["signals"] == 60
    assert out["by_grade"]["A"]["direction_correct_pct"] == 70.0
    assert out["by_grade"]["C"]["hit_invalidation_pct"] == 50.0
    assert out["all"]["avg_mfe_pct"] == pytest.approx(2.03, abs=0.01)


def test_content_hub_and_assistant_summaries():
    start, end = utc(2026, 10, 30), utc(2026, 11, 7)
    hub = [{"at": "2026-11-03T11:00:00+00:00", "symbol": "AXON", "ai_used": True, "ai_configured": True,
            "notes": ["News left out: International Developments (only weaker sources, no major source); "
                      "Geopolitical Developments (only weaker sources, no major source)."],
            "usage": {"cost_usd": 0.2352}},
           {"at": "2026-11-04T11:00:00+00:00", "symbol": "TSLA", "ai_used": False, "ai_configured": True,
            "notes": ["AI reply could not be used (401 from Anthropic); template used."], "usage": {}},
           {"at": "2026-09-01T11:00:00+00:00", "symbol": "OLD", "ai_used": True, "notes": []}]
    h = pr.content_hub_summary(hub, start, end)
    assert (h["runs"], h["ai_drafts"], h["template_fallbacks"], h["runs_with_news_dropped"]) == (2, 1, 1, 1)
    assert h["news_sections_dropped"] == {"International Developments": 1, "Geopolitical Developments": 1}
    assert h["cost"]["total_usd"] == 0.2352
    asst = [{"at": "2026-11-05T12:00:00+00:00", "question": "q1", "shown": True, "usage": {"cost_usd": 0.05}},
            {"at": "2026-11-05T13:00:00+00:00", "question": "Options expiry for AAPL?", "shown": False,
             "problems": ["numbers not in lookups"]}]
    a = pr.assistant_summary(asst, start, end)
    assert (a["questions"], a["answers_withheld"], a["withheld_pct"]) == (2, 1, 50.0)
    assert a["withheld_questions"] == ["Options expiry for AAPL?"]


def test_build_evidence_reports_what_is_unavailable(redis):
    def broken(sql, params):
        raise RuntimeError("DATABASE_URL is not set")
    ev = pr.build_evidence(utc(2026, 11, 7, 2, 15), broken)
    assert any("signal_outcomes" in u for u in ev["unavailable"])
    assert ev["content_hub"]["recent"]["runs"] == 0


# ── number check ──

def test_findings_with_numbers_not_in_evidence_are_removed():
    ev = {"x": {"direction_correct_pct": 70.0, "other": 40.0}}
    findings = [
        {"title": "Grade C underperforms", "evidence": "Direction correct 70.0% for A versus 40.0% for C.",
         "suggestion": "Raise the C threshold.", "expected_effect": "Fewer C signals.", "risk": "Fewer signals.",
         "confidence": "Moderate"},
        {"title": "Invented", "evidence": "A gap of 30 points.", "suggestion": "Something.",
         "expected_effect": "", "risk": "", "confidence": "high"},
    ]
    out = pr.check_findings(findings, ev)
    assert [f["title"] for f in out["kept"]] == ["Grade C underperforms"]
    assert out["kept"][0]["confidence"] == "moderate"
    assert out["removed"][0]["title"] == "Invented" and "30" in out["removed"][0]["reason"]


# ── full run ──

def test_run_without_ai_key_stores_a_code_written_report(redis, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    rep = pr.run_review("scheduled", "cron", utc(2026, 11, 7, 2, 15), _fetch)
    assert rep["ai_used"] is False and rep["findings"] == []
    assert "60 signals" in rep["summary"]
    stored = json.loads(redis.get(pr.LATEST_KEY))
    assert stored["id"] == rep["id"] and stored["trigger"] == "scheduled"
    assert redis.get(pr.LAST_SCHEDULED_KEY) == "2026-11-06"
    st = pr.status(utc(2026, 11, 7, 3, 0))
    assert st["latest"]["id"] == rep["id"] and st["mode"] == "automatic" and len(st["history"]) == 1


def test_run_with_ai_keeps_checked_findings_only(redis, monkeypatch):
    from backend import content_hub as ch
    monkeypatch.setattr(ch, "ai_available", lambda: True)
    reply = {"summary": "Grade A direction accuracy was 70.0% this week.",
             "findings": [{"title": "Grade C signals hit invalidation often",
                           "evidence": "Grade C hit invalidation 50.0% of the time on 10 evaluated signals.",
                           "suggestion": "Require more confluence before logging an Armed C signal.",
                           "expected_effect": "Fewer weak signals.", "risk": "Small sample.", "confidence": "low"},
                          {"title": "Made up", "evidence": "Improved by 17.3%.", "suggestion": "x"}]}
    monkeypatch.setattr(ch, "_ai_json", lambda system, user, max_tokens=0: reply)
    rep = pr.run_review("manual", "owner@example.com", utc(2026, 11, 3, 14, 0), _fetch)
    assert rep["ai_used"] is True
    assert [f["title"] for f in rep["findings"]] == ["Grade C signals hit invalidation often"]
    assert rep["removed"][0]["title"] == "Made up"
    assert rep["summary"].startswith("Grade A")


def test_content_hub_run_is_logged(redis):
    pr.record_content_hub_run("AXON", {"ai_used": True, "ai_configured": True, "notes": ["News left out: X (weak)."],
                                       "blog": {"note": "ok"}, "usage": {"cost_usd": 0.2}})
    entry = json.loads(redis.lists[pr.CONTENT_HUB_LOG_KEY][0])
    assert entry["symbol"] == "AXON" and entry["ai_used"] is True


def test_admin_tab_has_the_platform_review_card():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend"))
    os.environ["SIGMALYTIC_ADMIN_EMAILS"] = "owner@example.com"
    import app as dash_app
    page = str(dash_app.build_admin_tab(session={"email": "owner@example.com"}, backend_url="http://x"))
    assert "PLATFORM REVIEW" in page and "platform-review-mode" in page and "platform-review-run-btn" in page
    out = dash_app._render_platform_review({"mode": "manual", "latest": None})
    assert "Manual" in str(out)


def test_backend_routes_are_admin_guarded():
    """Static check of backend/main.py: mode and run need a signed-in admin; status and the cron entry also accept
    the cron secret."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", "main.py")).read()
    for route, guard in (('@app.post("/api/admin/platform-review/mode")', "Depends(require_admin)"),
                         ('@app.post("/api/admin/platform-review/run")', "Depends(require_admin)"),
                         ('@app.get("/api/admin/platform-review/status")', "Depends(require_admin_or_cron)"),
                         ('@app.get("/api/admin/platform-review/scheduled")', "Depends(require_admin_or_cron)")):
        i = src.index(route)
        assert guard in src[i:i + 300], route
    assert "platform_review.record_content_hub_run(symbol, out)" in src
