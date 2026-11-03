"""
backend/platform_review.py
--------------------------
Platform Review (admin only): once a week, Claude reads what the platform recorded about its own results and
writes a findings report with suggested improvements. Nothing here changes the platform: it only reads, analyses
and reports. Every suggestion waits for the administrator's decision.

What it reads (all read-only)
  1. Signal outcomes  -- scoreboard_signals: how signals of each grade and type actually played out
                         (direction correct, target 1 hit, invalidation hit, average MFE / MAE), for the last
                         7 days and for the 28 days before that, so changes are visible.
  2. Grade mix        -- radar_snapshots daily-close grades for the same two windows.
  3. Content Hub runs -- the run log written by record_content_hub_run(): AI vs. template drafts, dropped news
                         sections, numbers that failed the data check, cost.
  4. Assistant log    -- assistant:log: answers shown, rewritten or withheld, and what they cost.

How the report is made
  The four sources are summarised by code into one EVIDENCE object. Claude receives only that object and returns
  findings (finding, evidence, suggestion, expected effect, risk, confidence). Code then checks every number in
  every finding against EVIDENCE, using the same rule as the Content Hub and the Assistant; a finding with a number
  that is not in the evidence is removed and listed as removed. With no AI key, or if the AI reply cannot be used,
  a plain code-written report of the evidence is stored instead.

Schedule and toggle
  Mode "automatic" (default): the cron job sigmalytic-platform-review runs it every Friday at 9:15 pm Eastern time.
  Render schedules in UTC, so the cron fires at 01:15 and 02:15 UTC on Saturday and should_run_scheduled() lets
  only the one that is 9:15 pm in New York through (01:15 UTC in daylight time, 02:15 UTC in standard time).
  Mode "manual": the Friday run is skipped. "Run review now" works in either mode, at any time.

Storage (Redis): platform_review:mode, platform_review:latest, platform_review:history (last 26 reports),
platform_review:lock (one run at a time), platform_review:last_scheduled (date of the last Friday run),
content_hub:log (Content Hub run notes, last 500).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

MODES = ("automatic", "manual")
DEFAULT_MODE = "automatic"
SCHEDULE_WEEKDAY = 4          # Friday (Monday = 0)
SCHEDULE_HOUR, SCHEDULE_MINUTE = 21, 15
SCHEDULE_LABEL = "Fridays at 9:15 pm Eastern"

MODE_KEY = "platform_review:mode"
LATEST_KEY = "platform_review:latest"
HISTORY_KEY = "platform_review:history"
LOCK_KEY = "platform_review:lock"
LAST_SCHEDULED_KEY = "platform_review:last_scheduled"
HISTORY_KEEP = 26
LOCK_SECONDS = 15 * 60

CONTENT_HUB_LOG_KEY = "content_hub:log"
CONTENT_HUB_LOG_KEEP = 500
ASSISTANT_LOG_KEY = "assistant:log"

RECENT_DAYS = 7
BASELINE_DAYS = 28
MAX_FINDINGS = 8
FINDING_FIELDS = ("title", "evidence", "suggestion", "expected_effect", "risk", "confidence")
CONFIDENCE_LEVELS = ("low", "moderate", "high")


# ───────────────────────────── storage ─────────────────────────────

def _redis():
    try:
        from backend.radar_service import _redis_client
        return _redis_client
    except Exception:
        return None


def _get_json(key: str) -> Optional[Any]:
    r = _redis()
    if r is None:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def get_mode() -> str:
    r = _redis()
    if r is None:
        return DEFAULT_MODE
    try:
        raw = r.get(MODE_KEY)
        raw = raw.decode() if isinstance(raw, bytes) else raw
        return raw if raw in MODES else DEFAULT_MODE
    except Exception:
        return DEFAULT_MODE


def set_mode(mode: str) -> Dict[str, Any]:
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        return {"ok": False, "error": "Mode must be 'automatic' or 'manual'."}
    r = _redis()
    if r is None:
        return {"ok": False, "error": "Redis is not configured, so the setting cannot be saved."}
    try:
        r.set(MODE_KEY, mode)
    except Exception as e:
        return {"ok": False, "error": f"Could not save the setting: {str(e)[:120]}"}
    return {"ok": True, "mode": mode}


def record_content_hub_run(symbol: str, package: Dict[str, Any]) -> None:
    """Called by the Content Hub endpoint after each run, so the weekly review can read what happened."""
    r = _redis()
    if r is None or not isinstance(package, dict):
        return
    blog = package.get("blog") or {}
    entry = {"at": datetime.now(timezone.utc).isoformat(), "symbol": symbol,
             "ai_used": bool(package.get("ai_used")), "ai_configured": bool(package.get("ai_configured")),
             "notes": [str(n)[:600] for n in (package.get("notes") or [])],
             "blog_issues": [str(n)[:300] for n in (package.get("blog_issues") or [])],
             "blog_note": str(blog.get("note") or "")[:600], "usage": package.get("usage") or {}}
    try:
        r.lpush(CONTENT_HUB_LOG_KEY, json.dumps(entry, default=str))
        r.ltrim(CONTENT_HUB_LOG_KEY, 0, CONTENT_HUB_LOG_KEEP - 1)
    except Exception:
        pass


def _read_list(key: str, limit: int = 500) -> List[Dict[str, Any]]:
    r = _redis()
    if r is None:
        return []
    out = []
    try:
        for raw in r.lrange(key, 0, limit - 1):
            try:
                out.append(json.loads(raw))
            except Exception:
                continue
    except Exception:
        return []
    return out


# ───────────────────────────── schedule ─────────────────────────────

def next_scheduled_run(now: Optional[datetime] = None) -> datetime:
    """The next Friday 9:15 pm in New York (aware datetime in Eastern time)."""
    et = (now or datetime.now(timezone.utc)).astimezone(ET)
    days = (SCHEDULE_WEEKDAY - et.weekday()) % 7
    cand = (et + timedelta(days=days)).replace(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, second=0, microsecond=0)
    if cand <= et:
        cand += timedelta(days=7)
    return cand


def should_run_scheduled(now: Optional[datetime] = None, mode: Optional[str] = None,
                         last_scheduled: Optional[str] = None) -> Dict[str, Any]:
    """Decides whether a cron call is the Friday 9:15 pm Eastern run. The cron fires twice (01:15 and 02:15 UTC on
    Saturday) so that one of them is 9:15 pm in New York in both daylight and standard time; the other is skipped."""
    et = (now or datetime.now(timezone.utc)).astimezone(ET)
    mode = mode or get_mode()
    if mode != "automatic":
        return {"run": False, "reason": "Mode is manual; the scheduled run is skipped."}
    if et.weekday() != SCHEDULE_WEEKDAY or et.hour != SCHEDULE_HOUR:
        return {"run": False, "reason": f"Not the scheduled time ({et:%A %H:%M} Eastern); this is the other "
                                        f"of the two daylight/standard-time cron calls."}
    if last_scheduled == et.date().isoformat():
        return {"run": False, "reason": "This Friday's review has already run."}
    return {"run": True, "reason": "Friday 9:15 pm Eastern.", "date": et.date().isoformat()}


# ───────────────────────────── evidence ─────────────────────────────

def _pct(n: Any, d: Any) -> Optional[float]:
    try:
        return round(float(n) / float(d) * 100, 1) if d else None
    except (TypeError, ValueError):
        return None


def _num(v: Any, nd: int = 2) -> Optional[float]:
    try:
        return None if v is None else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _db_rows(sql: str, params: tuple) -> List[Dict[str, Any]]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


_OUTCOME_SQL = """
    SELECT grade, signal_type,
           COUNT(*)                                                   AS signals,
           COUNT(*) FILTER (WHERE outcome_price IS NOT NULL)          AS evaluated,
           COUNT(*) FILTER (WHERE direction_correct IS NOT NULL)      AS direction_evaluated,
           COUNT(*) FILTER (WHERE direction_correct = true)           AS direction_correct,
           COUNT(*) FILTER (WHERE hit_target1 = true)                 AS hit_target1,
           COUNT(*) FILTER (WHERE hit_invalidation = true)            AS hit_invalidation,
           AVG(mfe_pct) FILTER (WHERE outcome_price IS NOT NULL)      AS avg_mfe_pct,
           AVG(mae_pct) FILTER (WHERE outcome_price IS NOT NULL)      AS avg_mae_pct
    FROM scoreboard_signals
    WHERE signal_date >= %s AND signal_date < %s
    GROUP BY grade, signal_type
"""

_GRADE_MIX_SQL = """
    SELECT grade, COUNT(*) AS n
    FROM radar_snapshots
    WHERE is_daily_close = TRUE AND grade IS NOT NULL AND snapshot_time >= %s AND snapshot_time < %s
    GROUP BY grade
"""


def _outcome_group(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    signals = sum(int(r.get("signals") or 0) for r in rows)
    evaluated = sum(int(r.get("evaluated") or 0) for r in rows)
    d_eval = sum(int(r.get("direction_evaluated") or 0) for r in rows)
    d_ok = sum(int(r.get("direction_correct") or 0) for r in rows)
    t1 = sum(int(r.get("hit_target1") or 0) for r in rows)
    inval = sum(int(r.get("hit_invalidation") or 0) for r in rows)

    def wavg(key: str) -> Optional[float]:
        pairs = [(float(r[key]), int(r.get("evaluated") or 0)) for r in rows if r.get(key) is not None]
        w = sum(n for _, n in pairs)
        return round(sum(v * n for v, n in pairs) / w, 2) if w else None

    return {"signals": signals, "evaluated": evaluated, "direction_correct_pct": _pct(d_ok, d_eval),
            "hit_target1_pct": _pct(t1, evaluated), "hit_invalidation_pct": _pct(inval, evaluated),
            "avg_mfe_pct": wavg("avg_mfe_pct"), "avg_mae_pct": wavg("avg_mae_pct")}


def signal_outcomes(start: datetime, end: datetime, fetch: Callable = _db_rows) -> Dict[str, Any]:
    rows = fetch(_OUTCOME_SQL, (start, end))
    by_grade: Dict[str, List[Dict[str, Any]]] = {}
    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_grade.setdefault(str(r.get("grade") or "ungraded"), []).append(r)
        by_type.setdefault(str(r.get("signal_type") or "unknown"), []).append(r)
    return {"all": _outcome_group(rows),
            "by_grade": {g: _outcome_group(v) for g, v in sorted(by_grade.items())},
            "by_signal_type": {t: _outcome_group(v) for t, v in sorted(by_type.items())}}


def grade_mix(start: datetime, end: datetime, fetch: Callable = _db_rows) -> Dict[str, Any]:
    rows = fetch(_GRADE_MIX_SQL, (start, end))
    total = sum(int(r.get("n") or 0) for r in rows)
    return {"graded": total, "share_pct": {str(r["grade"]): _pct(r.get("n"), total) for r in rows}}


def _in_window(entry: Dict[str, Any], start: datetime, end: datetime) -> bool:
    try:
        at = datetime.fromisoformat(str(entry.get("at")).replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return start <= at < end
    except Exception:
        return False


def _cost(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    costs = [(e.get("usage") or {}).get("cost_usd") for e in entries]
    known = [float(c) for c in costs if isinstance(c, (int, float))]
    return {"total_usd": round(sum(known), 4) if known else None,
            "avg_usd": round(sum(known) / len(known), 4) if known else None}


def content_hub_summary(entries: List[Dict[str, Any]], start: datetime, end: datetime) -> Dict[str, Any]:
    runs = [e for e in entries if _in_window(e, start, end)]
    text = lambda e: " ".join([*(e.get("notes") or []), e.get("blog_note") or ""])  # noqa: E731
    dropped: Dict[str, int] = {}
    for e in runs:
        t = text(e)
        if "News left out:" in t:
            for part in t.split("News left out:", 1)[1].split(".")[0].split(";"):
                head = part.split("(")[0].strip()
                if head:
                    dropped[head] = dropped.get(head, 0) + 1
    return {"runs": len(runs),
            "ai_drafts": sum(1 for e in runs if e.get("ai_used")),
            "template_fallbacks": sum(1 for e in runs if "template used" in text(e).lower()
                                      or (e.get("ai_configured") and not e.get("ai_used"))),
            "runs_with_news_dropped": sum(1 for e in runs if "News left out:" in text(e)),
            "news_sections_dropped": dict(sorted(dropped.items(), key=lambda kv: -kv[1])),
            "runs_with_number_check_failures": sum(1 for e in runs if "not in the" in text(e)
                                                   or any("Numbers not in the data" in i for i in e.get("blog_issues") or [])),
            "runs_with_advice_wording": sum(1 for e in runs if any("Advice wording" in i for i in e.get("blog_issues") or [])),
            "symbols": sorted({str(e.get("symbol")) for e in runs if e.get("symbol")})[:40],
            "cost": _cost(runs)}


def assistant_summary(entries: List[Dict[str, Any]], start: datetime, end: datetime) -> Dict[str, Any]:
    qs = [e for e in entries if _in_window(e, start, end)]
    withheld = [e for e in qs if not e.get("shown")]
    return {"questions": len(qs), "answers_shown": len(qs) - len(withheld), "answers_withheld": len(withheld),
            "withheld_pct": _pct(len(withheld), len(qs)),
            "withheld_questions": [str(e.get("question") or "")[:160] for e in withheld][:10],
            "withheld_reasons": [str((e.get("problems") or [e.get("error") or ""])[0])[:160] for e in withheld][:10],
            "cost": _cost(qs)}


def build_evidence(now: Optional[datetime] = None, fetch: Callable = _db_rows) -> Dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    recent_start = now - timedelta(days=RECENT_DAYS)
    base_start = recent_start - timedelta(days=BASELINE_DAYS)
    ev: Dict[str, Any] = {
        "windows": {"recent": {"from": recent_start.date().isoformat(), "to": now.date().isoformat(),
                               "days": RECENT_DAYS},
                    "baseline": {"from": base_start.date().isoformat(), "to": recent_start.date().isoformat(),
                                 "days": BASELINE_DAYS}},
        "unavailable": []}
    for name, fn in (("signal_outcomes", signal_outcomes), ("grade_mix", grade_mix)):
        try:
            ev[name] = {"recent": fn(recent_start, now, fetch), "baseline": fn(base_start, recent_start, fetch)}
        except Exception as e:
            ev["unavailable"].append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
    hub = _read_list(CONTENT_HUB_LOG_KEY)
    ev["content_hub"] = {"recent": content_hub_summary(hub, recent_start, now),
                         "baseline": content_hub_summary(hub, base_start, recent_start)}
    asst = _read_list(ASSISTANT_LOG_KEY)
    ev["assistant"] = {"recent": assistant_summary(asst, recent_start, now),
                       "baseline": assistant_summary(asst, base_start, recent_start)}
    if not hub:
        ev["unavailable"].append("content_hub: no runs logged yet (logging starts with this release).")
    return ev


# ───────────────────────────── analysis ─────────────────────────────

_SYSTEM = (
    "You are the internal performance reviewer for Sigmalytic Quant Corporation's research platform. You receive "
    "an EVIDENCE JSON object summarising one week of the platform's own results (signal outcomes by grade and "
    "signal type, the daily grade mix, Content Hub runs and AI Assistant answers), with a 28-day baseline for "
    "comparison. Find the patterns that matter and suggest specific improvements to the platform.\n"
    "Rules:\n"
    "- Use ONLY numbers that appear in EVIDENCE. Never compute differences, ratios or new percentages; quote both "
    "values instead (e.g. 'fell from 64.2% to 51.0%').\n"
    "- Every finding must name its evidence. If a sample is small (under 30 evaluated signals), say so and lower "
    "the confidence.\n"
    "- Suggestions are proposals for the administrator to approve or reject. Be specific about what would change "
    "(a threshold, a rule, a setting, a lookup), but do not write code.\n"
    "- Plain, precise, internal language. No hype.\n"
    "- If the evidence is too thin for findings, say so in the summary and return fewer findings.\n"
    "Reply with one JSON object and nothing else:\n"
    '{"summary": "2-4 sentences", "findings": [{"title": "...", "evidence": "...", "suggestion": "...", '
    '"expected_effect": "...", "risk": "...", "confidence": "low|moderate|high"}]}\n'
    f"At most {MAX_FINDINGS} findings, most important first."
)


def check_findings(findings: Any, evidence: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Keeps findings whose every number is in the evidence; the rest are returned as removed, with the reason."""
    from backend.content_hub import numbers_trace_to_facts
    kept, removed = [], []
    for f in (findings if isinstance(findings, list) else [])[:MAX_FINDINGS]:
        if not isinstance(f, dict):
            continue
        item = {k: str(f.get(k) or "").strip() for k in FINDING_FIELDS}
        item["confidence"] = item["confidence"].lower() if item["confidence"].lower() in CONFIDENCE_LEVELS else "low"
        if not item["title"] or not item["suggestion"]:
            continue
        bad = numbers_trace_to_facts(" ".join(item[k] for k in FINDING_FIELDS if k != "confidence"), evidence)
        if bad:
            removed.append({"title": item["title"], "reason": "Numbers not in the evidence: " + ", ".join(bad)})
        else:
            kept.append(item)
    return {"kept": kept, "removed": removed}


def fallback_summary(ev: Dict[str, Any]) -> str:
    """A plain code-written summary, used when the AI is unavailable."""
    bits = []
    so = ((ev.get("signal_outcomes") or {}).get("recent") or {}).get("all") or {}
    if so:
        bits.append(f"{so.get('signals', 0)} signals logged this week, {so.get('evaluated', 0)} with outcomes; "
                    f"direction correct {so.get('direction_correct_pct')}%.")
    hub = (ev.get("content_hub") or {}).get("recent") or {}
    bits.append(f"Content Hub: {hub.get('runs', 0)} runs, {hub.get('template_fallbacks', 0)} template fallbacks, "
                f"{hub.get('runs_with_news_dropped', 0)} with news sections dropped.")
    a = (ev.get("assistant") or {}).get("recent") or {}
    bits.append(f"Assistant: {a.get('questions', 0)} questions, {a.get('answers_withheld', 0)} answers withheld.")
    return " ".join(bits)


def analyse(ev: Dict[str, Any]) -> Dict[str, Any]:
    from backend import content_hub as ch
    if not ch.ai_available():
        return {"ai_used": False, "summary": fallback_summary(ev), "findings": [], "removed": [],
                "note": "No AI key set (ANTHROPIC_API_KEY); evidence summary written by code, no findings."}
    log: List[Dict[str, Any]] = []
    token = ch._USAGE.set(log)
    try:
        reply = ch._ai_json(_SYSTEM, "EVIDENCE:\n" + json.dumps(ev, default=str), max_tokens=4000)
    except Exception as e:
        return {"ai_used": False, "summary": fallback_summary(ev), "findings": [], "removed": [],
                "usage": ch.summarize_usage(log),
                "note": f"AI analysis could not be used ({str(e)[:160]}); evidence summary written by code."}
    finally:
        ch._USAGE.reset(token)
    checked = check_findings(reply.get("findings"), ev)
    summary = str(reply.get("summary") or "").strip()
    note = None
    if summary and ch.numbers_trace_to_facts(summary, ev):
        summary, note = fallback_summary(ev), "The AI summary used numbers not in the evidence; replaced by code."
    return {"ai_used": True, "summary": summary or fallback_summary(ev), "findings": checked["kept"],
            "removed": checked["removed"], "usage": ch.summarize_usage(log), "note": note}


# ───────────────────────────── running ─────────────────────────────

def _acquire_lock() -> bool:
    r = _redis()
    if r is None:
        return True
    try:
        return bool(r.set(LOCK_KEY, "1", nx=True, ex=LOCK_SECONDS))
    except Exception:
        return True


def _release_lock() -> None:
    r = _redis()
    if r is not None:
        try:
            r.delete(LOCK_KEY)
        except Exception:
            pass


def is_running() -> bool:
    r = _redis()
    if r is None:
        return False
    try:
        return bool(r.exists(LOCK_KEY))
    except Exception:
        return False


def run_review(trigger: str = "manual", requested_by: str = "", now: Optional[datetime] = None,
               fetch: Callable = _db_rows) -> Dict[str, Any]:
    """Builds the evidence, asks for the analysis, stores the report. Read-only on platform data."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ev = build_evidence(now, fetch)
    result = analyse(ev)
    report = {"id": "rev_" + uuid.uuid4().hex[:12], "generated_at": now.isoformat(),
              "generated_at_et": now.astimezone(ET).strftime("%A, %B %-d, %Y, %-I:%M %p ET"),
              "trigger": trigger, "requested_by": requested_by, **result, "evidence": ev}
    r = _redis()
    if r is not None:
        try:
            r.set(LATEST_KEY, json.dumps(report, default=str))
            r.lpush(HISTORY_KEY, json.dumps({k: report.get(k) for k in
                                             ("id", "generated_at", "generated_at_et", "trigger", "ai_used",
                                              "summary")}, default=str))
            r.ltrim(HISTORY_KEY, 0, HISTORY_KEEP - 1)
            if trigger == "scheduled":
                r.set(LAST_SCHEDULED_KEY, now.astimezone(ET).date().isoformat())
        except Exception:
            pass
    return report


def start_review(trigger: str = "manual", requested_by: str = "") -> Dict[str, Any]:
    """Starts a review in the background (one at a time) and returns at once."""
    if not _acquire_lock():
        return {"ok": True, "status": "running", "message": "A review is already running."}

    def _go():
        try:
            run_review(trigger, requested_by)
        finally:
            _release_lock()

    threading.Thread(target=_go, daemon=True, name="platform-review").start()
    return {"ok": True, "status": "started"}


def start_scheduled(now: Optional[datetime] = None) -> Dict[str, Any]:
    r = _redis()
    last = None
    if r is not None:
        try:
            raw = r.get(LAST_SCHEDULED_KEY)
            last = raw.decode() if isinstance(raw, bytes) else raw
        except Exception:
            last = None
    decision = should_run_scheduled(now, last_scheduled=last)
    if not decision["run"]:
        return {"ok": True, "status": "skipped", "reason": decision["reason"]}
    return {**start_review("scheduled", "cron"), "reason": decision["reason"]}


def status(now: Optional[datetime] = None) -> Dict[str, Any]:
    mode = get_mode()
    latest = _get_json(LATEST_KEY)
    nxt = next_scheduled_run(now)
    return {"ok": True, "mode": mode, "schedule": SCHEDULE_LABEL, "running": is_running(),
            "next_run_et": nxt.strftime("%A, %B %-d, %Y, %-I:%M %p ET") if mode == "automatic" else None,
            "latest": latest, "history": _read_list(HISTORY_KEY, HISTORY_KEEP)}
