# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/reports_engine.py
---------------------------
Daily subscriber intelligence report -- generation and storage.

WHY THIS EXISTS (2026-07-30): a complete, working nightly report
generator (tools/generate_nightly_intelligence_report_v2.py, 623 lines,
producing real HTML/Markdown/PDF output from the live full-universe
enriched campaign data) was found sitting in this codebase, fully
built, but never actually scheduled or wired into anything -- the same
"fully built, never activated" pattern found repeatedly earlier the
same night (the radar scanner scheduler, the divergence Redis bridge).

This reuses that same proven HTML-generation logic (the table/card
builders and document structure are functionally the same), adapted to:
  - call the enrichment endpoint directly, in-process (no HTTP
    round-trip to itself, unlike the original tools/ script)
  - return an HTML string instead of writing files to local disk
  - store that HTML in Redis, keyed by date, so it survives across
    this service's own process restarts and is readable by the
    frontend (a separate service) -- the same Redis-bridging pattern
    already proven correct for RADAR_CACHE and DIVERGENCE_WATCHLIST
    earlier the same night.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

REPORT_TITLE = "Sigmalytic Quant Corporation - Nightly Intelligence Report"
REPORT_SUBTITLE = "V2 Campaign Intelligence - Daily Subscriber Edition"
COPYRIGHT = "Copyright © 2026 Sigmalytic Quant Corporation. All rights reserved. Confidential and proprietary."

REDIS_REPORT_TTL_SECONDS = 90 * 24 * 60 * 60  # 90 days
REDIS_REPORT_INDEX_KEY = "reports:index"       # sorted set of available dates


# ── Shared helpers (same logic as tools/generate_nightly_intelligence_report_v2.py) ──

def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except Exception:
        return None


def _fmt(value: Any, digits: int = 2) -> str:
    v = _safe_float(value)
    if v is None:
        return "—"
    return f"{v:,.{digits}f}"


def _esc(value: Any) -> str:
    if value is None:
        return "—"
    text = str(value)
    return (
        text.replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


def _subscriber_state(value):
    return value if value else "—"


def _row_symbol(row: Dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "—")


def _is_bullish(row: Dict[str, Any]) -> bool:
    bias = str(row.get("bias") or row.get("watch_bias") or "").upper()
    return bias in ("LONG", "BULLISH")


# FIX (2026-07-31): user pointed out several report readability issues.
# The app itself already relabels the backend's "BIRTH" lifecycle state
# as "SPARK" everywhere in the UI (frontend/campaign_tab.py's
# _STATE_ICONS mapping) -- the report wasn't applying that same
# relabeling, showing the raw backend value instead.
_STATE_LABELS = {
    "BIRTH": "SPARK",
    "CONFIRMED": "CONFIRMED",
    "SURVIVING": "SURVIVING",
    "EXPANDING": "EXPANDING",
    "MATURING": "MATURING",
    "DISTRIBUTION_RISK": "RISK",
    "CLOSED": "CLOSED",
}


def _state_label(value: Any) -> str:
    text = str(value or "").upper()
    return _STATE_LABELS.get(text, text or "—")


def _readable_label(value: Any) -> str:
    """
    Converts backend-style ALL_CAPS_WITH_UNDERSCORES enum values (e.g.
    "PENDING_INCOMPLETE_7YR_EVIDENCE") into readable text
    ("Pending Incomplete 7yr Evidence") -- user reported the raw form
    was hard to read.
    """
    if not value:
        return "—"
    words = str(value).replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def _cohort_label(value: Any) -> str:
    """
    Strips the redundant "COHORT_" prefix -- user pointed out the
    column header already says "Cohort", so repeating it in every
    value is redundant.
    """
    text = str(value or "")
    if text.upper().startswith("COHORT_"):
        text = text[len("COHORT_"):]
    return _readable_label(text) if text else "—"


def _readable_missing_components(row: Dict[str, Any]) -> str:
    """
    User reported this column showed a raw Python list repr (brackets,
    quotes, underscores) and asked for either "0" or a plain statement
    of what's missing.
    """
    items = _missing_components(row)
    if not items:
        return "0"
    return ", ".join(_readable_label(i) for i in items)


def _missing_components(row: Dict[str, Any]) -> List[str]:
    return row.get("ods_missing_components") or []


def _component_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for r in rows:
        for c in _missing_components(r):
            counts[c] = counts.get(c, 0) + 1
    return counts


def _top_rows(rows: List[Dict[str, Any]], n: int = 20) -> List[Dict[str, Any]]:
    return rows[:n]


def _table_html(rows: List[Dict[str, Any]], title: str, note: str = "", limit: int = 25) -> str:
    shown = rows[:limit]
    if not shown:
        return f"""
        <section class="section">
          <h2>{_esc(title)}</h2>
          <p class="muted">No rows met this section's criteria in today's review.</p>
        </section>
        """
    body = []
    for row in shown:
        body.append(f"""
        <tr>
          <td><strong>{_esc(_row_symbol(row))}</strong></td>
          <td>{_esc(_state_label(row.get("state")) or row.get("status"))}</td>
          <td>{_esc(row.get("bias") or row.get("watch_bias"))}</td>
          <td>{_esc(row.get("ods_status"))}</td>
          <td>{_esc(_readable_label(row.get("ods_label")))}</td>
          <td class="num">{_fmt(row.get("ods_score"), 0)}</td>
          <td>{_esc(row.get("lifecycle_maturity"))}</td>
          <td>{_esc(_cohort_label(row.get("cohort_status")))}</td>
          <td class="num">{_fmt(row.get("expected_return_pct"), 2)}</td>
          <td class="num">{_fmt(row.get("target_1_price"), 2)}</td>
          <td class="num">{_fmt(row.get("failure_price"), 2)}</td>
          <td>{_esc(_readable_missing_components(row))}</td>
        </tr>
        """)
    return f"""
    <section class="section">
      <h2>{_esc(title)}</h2>
      {f'<p class="note">{_esc(note)}</p>' if note else ''}
      <table>
        <thead>
          <tr>
            <th>Symbol</th><th>State</th><th>Bias</th><th>ODS</th><th>ODS Label</th>
            <th class="num">ODS Score</th><th>Lifecycle</th><th>Cohort</th><th class="num">Exp. Ret.</th>
            <th class="num">Target 1</th><th class="num">Failure</th><th>Missing ODS Evidence</th>
          </tr>
        </thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </section>
    """


def _card_grid(rows: List[Dict[str, Any]], title: str, note: str = "", limit: int = 12) -> str:
    shown = rows[:limit]
    if not shown:
        return f"""
        <section class="section">
          <h2>{_esc(title)}</h2>
          <p class="muted">No rows met this section's criteria in today's review.</p>
        </section>
        """
    cards = []
    for row in shown:
        cards.append(f"""
        <div class="card">
          <div class="card-title">{_esc(_row_symbol(row))} <span>{_esc(row.get("ods_status"))}</span></div>
          <div class="card-line">Bias: {_esc(row.get("bias") or row.get("watch_bias"))} | Score: {_fmt(row.get("ods_score"), 0)}</div>
          <div class="card-line">Expected Return: {_fmt(row.get("expected_return_pct"), 2)}%</div>
          <p>{_esc(row.get("why_this_trade") or row.get("summary") or "")}</p>
        </div>
        """)
    return f"""
    <section class="section">
      <h2>{_esc(title)}</h2>
      {f'<p class="note">{_esc(note)}</p>' if note else ''}
      <div class="grid">{''.join(cards)}</div>
    </section>
    """


_CSS = """
body { font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 0; background: #f3f4f6; }
.page { max-width: 1120px; margin: 0 auto; background: white; padding: 40px 46px; }
.cover { border-bottom: 4px solid #111827; padding-bottom: 24px; margin-bottom: 28px; }
h1 { font-size: 30px; margin: 0 0 2px 0; letter-spacing: -0.02em; }
.sigma { color: #0F766E; }
.corp-subtitle { font-size: 12px; font-weight: bold; letter-spacing: 0.12em; color: #0F766E; margin-bottom: 10px; }
h2 { font-size: 21px; margin: 24px 0 10px 0; border-bottom: 1px solid #d1d5db; padding-bottom: 6px; }
.subtitle { font-size: 15px; color: #374151; margin-bottom: 16px; }
.meta { display: grid; grid-template-columns: 210px 1fr; gap: 6px 14px; font-size: 13px; }
.label { color: #6b7280; font-weight: bold; }
.section { margin: 26px 0; }
.summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }
.metric { border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; background: #f9fafb; }
.metric .num { font-size: 24px; font-weight: bold; }
.metric .txt { color: #4b5563; font-size: 12px; }
.note { color: #374151; font-size: 13px; }
.muted { color: #6b7280; }
table { width: 100%; table-layout: fixed; border-collapse: collapse; font-size: 11px; margin-top: 10px; }
th { background: #111827; color: white; text-align: left; padding: 7px; }
td { border-bottom: 1px solid #e5e7eb; padding: 6px; vertical-align: top; word-wrap: break-word; overflow-wrap: break-word; }
.num { text-align: center; }
.grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.card { border: 1px solid #d1d5db; border-radius: 8px; padding: 12px; }
.card-title { font-size: 15px; font-weight: bold; display: flex; justify-content: space-between; }
.card-title span { font-size: 11px; color: #374151; }
.card-line { font-size: 12px; margin-top: 5px; }
.card p { font-size: 12px; color: #374151; line-height: 1.35; }
.footer { margin-top: 34px; border-top: 1px solid #d1d5db; padding-top: 14px; font-size: 11px; color: #4b5563; }
"""


def _fetch_market_movers(limit: int = 15) -> List[Dict[str, Any]]:
    """
    "What Happened in the Market Today" -- surfaces the largest price
    moves across the full radar-scanned universe (not just tracked
    campaigns or top-ranked setups), sorted purely by raw |% change|,
    so a big move can't be silently excluded just because it doesn't
    score well as a "quality" setup.

    NOTE (2026-08-02): this reflects the most recent market data
    available at the moment the report is generated -- not
    necessarily a precise historical snapshot of the report's own
    labeled date. A same-day report (generated by the nightly cron
    right after that day's close) reflects that day accurately. A
    report regenerated later, for a past date, will show whatever the
    market looked like at regeneration time instead -- which is why
    regenerating two different dates close together in time can show
    similar or identical movers. A true per-date historical version
    was attempted and reverted after it introduced significant
    reliability problems; this simpler, honest version is deliberately
    preferred over a more "precise" one that doesn't work reliably.

    FIX (2026-08-04): this used get_radar_scores(limit=1500), but that
    function silently hard-caps its limit to 250 internally (a
    deliberate performance safeguard for its own paginated, enriched
    list view -- confirmed directly in radar_service.py during an
    earlier, related bug fix that day). That cap wasn't just
    incomplete data -- it could produce an entirely empty movers list
    if, at generation time, the top-250 slice by whatever sort order
    was active happened not to include enough symbols with a
    change_pct set, triggering the "Market movers data unavailable"
    fallback despite the radar cache genuinely having live data.
    Reading directly from RADAR_CACHE (same Redis fallback
    get_radar_scores() itself uses) is both more reliable and more
    correct here -- true market movers should consider the FULL
    tracked universe (~900+ symbols), not an arbitrary 250-symbol cap.
    """
    from backend.radar_service import RADAR_CACHE, _redis_client

    try:
        symbols = list(RADAR_CACHE.values())
        if not symbols and _redis_client:
            import json as _movers_json
            raw = _redis_client.get("radar:cache")
            if raw:
                full_cache = _movers_json.loads(raw)
                symbols = list(full_cache.values())
    except Exception:
        return []

    movers = [
        s for s in symbols
        if isinstance(s, dict) and s.get("change_pct") is not None
    ]
    movers.sort(key=lambda s: abs(_safe_float(s.get("change_pct")) or 0), reverse=True)
    return movers[:limit]


def _movers_table(movers: List[Dict[str, Any]]) -> str:
    if not movers:
        return """
        <section class="section">
          <h2>What Happened in the Market Today</h2>
          <p class="muted">Market movers data unavailable for this report.</p>
        </section>
        """
    rows_html = []
    for m in movers:
        chg = _safe_float(m.get("change_pct")) or 0
        color = "#166534" if chg >= 0 else "#991b1b"
        rows_html.append(f"""
        <tr>
          <td><strong>{_esc(m.get("symbol"))}</strong></td>
          <td class="num">{_esc(_fmt(m.get("price"), 2))}</td>
          <td class="num" style="color:{color}; font-weight:bold;">{chg:+.2f}%</td>
          <td class="num">{_esc(_fmt(m.get("rel_volume"), 2))}x</td>
          <td class="num">{_esc(f'{int(m.get("volume")):,}' if m.get("volume") else "—")}</td>
        </tr>
        """)
    return f"""
    <section class="section">
      <h2>What Happened in the Market Today</h2>
      <p class="note">The largest price moves across the full scanned universe, by raw percentage
      change and relative volume -- independent of setup-quality ranking, so a dramatic move is never
      silently excluded just because it doesn't score as a high-quality bullish setup. Reflects market
      data as of when this report was generated.</p>
      <table>
        <thead>
          <tr><th>Symbol</th><th class="num">Price</th><th class="num">Change</th><th class="num">Rel. Volume</th><th class="num">Volume</th></tr>
        </thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </section>
    """


def build_report_html(report_date_str: str) -> str:
    """
    Builds the full HTML report document for a given date, using the
    full-universe enriched campaign table as of when this is called.
    Calls the endpoint's underlying function directly (in-process),
    rather than an HTTP round-trip, since this runs inside the same
    backend service that already serves that endpoint.
    """
    from backend.campaign_full_enrichment_api import full_universe_enriched_campaign_table

    payload = full_universe_enriched_campaign_table(limit=100)
    rows = [r for r in (payload.get("rows") or []) if isinstance(r, dict)]
    market = payload.get("market_data_status") or {}

    confirmed = [r for r in rows if r.get("ods_status") == "CONFIRMED"]
    pending = [r for r in rows if r.get("ods_status") == "PENDING"]
    not_confirmed = [r for r in rows if r.get("ods_status") == "NOT_CONFIRMED"]
    long_watch = [r for r in rows if _is_bullish(r)]
    neutral_watch = [r for r in rows if not _is_bullish(r)]
    mature = [r for r in rows if r.get("lifecycle_maturity") in ("MATURE", "LONG_MATURE")]
    cohort_ready = [r for r in rows if r.get("cohort_status") == "COHORT_READY"]
    risk_watch = [
        r for r in rows
        if r.get("ods_status") in ("PENDING", "NOT_CONFIRMED")
        and (
            "demand_support_validation" in _missing_components(r)
            or "structurally_meaningful_location" in _missing_components(r)
            or r.get("ods_status") == "NOT_CONFIRMED"
        )
    ]
    missing_counts = _component_counts(pending)
    missing_html = "".join(
        f"<tr><td>{_esc(k)}</td><td class='num'>{v}</td></tr>"
        for k, v in missing_counts.items()
    ) or "<tr><td>No missing components recorded</td><td class='num'>0</td></tr>"

    try:
        display_date = datetime.strptime(report_date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        display_date = report_date_str

    movers = _fetch_market_movers(limit=15)
    movers_html = _movers_table(movers)

    executive = f"""
    <section class="section">
      <h2>Executive Market Review</h2>
      <p>
        Today's V2 review uses the live full-universe Campaign Engine source: up to 100 ranked campaign rows,
        formal ODS evidence evaluation, lifecycle maturity, cohort readiness, target/failure levels, and
        risk/reward context. The review identified {len(confirmed)} formally ODS-confirmed campaigns,
        {len(pending)} ODS-pending campaigns with specific missing evidence components, and
        {len(cohort_ready)} cohort-ready names.
      </p>
      <p>
        ODS pending does not mean missing data. It means the historical record was evaluated but one or more
        required operator-control evidence components was absent.
      </p>
    </section>
    """

    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{_esc(REPORT_TITLE)} - {_esc(display_date)}</title>
  <!-- generated_at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} -->
  <style>{_CSS}</style>
</head>
<body>
  <div class="page">
    <div class="cover">
      <h1><span class="sigma">&Sigma;</span> SIGMALYTIC</h1>
      <div class="corp-subtitle">QUANT CORPORATION</div>
      <div class="subtitle">{_esc(REPORT_SUBTITLE)}</div>
      <div class="meta">
        <div class="label">Report date</div><div>{_esc(display_date)}</div>
        <div class="label">Application</div><div>Sigmalytic Quant Corporation - Version 2</div>
        <div class="label">Audience</div><div>Subscribers, trial users, and market-intelligence readers</div>
        <div class="label">Important boundary</div><div>Stock-intelligence review and decision support only; not personalized financial advice.</div>
      </div>
    </div>

    {executive}

    {movers_html}

    <section class="section">
      <h2>Coverage Summary</h2>
      <div class="summary">
        <div class="metric"><div class="num">{len(rows)}</div><div class="txt">Campaign rows reviewed</div></div>
        <div class="metric"><div class="num">{_esc(market.get("history_years"))}</div><div class="txt">Years of daily history</div></div>
        <div class="metric"><div class="num">{_esc(market.get("total_bars"))}</div><div class="txt">Daily bars evaluated</div></div>
        <div class="metric"><div class="num">{len(cohort_ready)}</div><div class="txt">Cohort-ready names</div></div>
      </div>
      <table>
        <thead><tr><th>Metric</th><th>Value</th></tr></thead>
        <tbody>
          <tr><td>Symbols with bars</td><td>{_esc(market.get("symbols_with_bars"))}</td></tr>
          <tr><td>ODS confirmed</td><td>{len(confirmed)}</td></tr>
          <tr><td>ODS pending with missing evidence detail</td><td>{len(pending)}</td></tr>
          <tr><td>ODS not confirmed</td><td>{len(not_confirmed)}</td></tr>
          <tr><td>Mature or long-mature campaigns</td><td>{len(mature)}</td></tr>
        </tbody>
      </table>
    </section>

    <section class="section">
      <h2>ODS Pending by Missing Evidence Component</h2>
      <p class="note">Formal ODS confirmation requires tested supply exhaustion, active demand/support validation, structurally meaningful location, and absence of contrary failure.</p>
      <table>
        <thead><tr><th>Missing Evidence Component</th><th>Rows</th></tr></thead>
        <tbody>{missing_html}</tbody>
      </table>
    </section>

    {_table_html(_top_rows(confirmed, 20), "Formal ODS Confirmed Campaigns", "Confirmed only when all formal evidence components are present.", 20)}
    {_card_grid(_top_rows(long_watch, 20), "Long Watchlist", "Bullish watch candidates from the full-universe source.", 12)}
    {_table_html(_top_rows(neutral_watch, 25), "Neutral / Watch-Only Universe", "Rows not classified as bullish in the current source.", 25)}
    {_table_html(_top_rows(mature, 25), "Mature Campaign Leaders", "Campaigns with mature or long-mature lifecycle status.", 25)}
    {_table_html(_top_rows(cohort_ready, 25), "Cohort-Ready Campaigns", "Rows where historical structural analogs were sufficient for cohort readiness.", 25)}
    {_table_html(_top_rows(risk_watch, 25), "Deterioration / Risk Watch", "Rows with missing demand/support validation, structural location, or explicit non-confirmation.", 25)}
    {_table_html(_top_rows(rows, 20), "Tomorrow Focus List", "Highest-priority names by ODS/campaign evidence, lifecycle, and cohort context.", 20)}

    <section class="section">
      <h2>Important Subscriber Notes</h2>
      <p>
        This report is a daily stock-intelligence review generated from Sigmalytic V2 campaign, formal ODS,
        lifecycle, cohort, and market-structure evidence. The long, short, neutral, pending, and confirmed
        classifications are watchlist categories, not personalized investment advice.
      </p>
    </section>

    <div class="footer">
      {_esc(COPYRIGHT)}<br>
      Sigmalytic Quant Corporation | V2 Campaign Intelligence | Daily Intelligence Report
    </div>
  </div>
</body>
</html>
"""
    return html_doc


def generate_and_store_report(report_date_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Generates the report for the given date (defaults to today, UTC)
    and stores it in Redis, keyed by date, plus adds that date to the
    report index so the frontend can list what's available.
    """
    from backend.radar_service import _redis_client

    if report_date_str is None:
        report_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    html_doc = build_report_html(report_date_str)

    if not _redis_client:
        return {"ok": False, "error": "Redis not configured", "date": report_date_str}

    try:
        _redis_client.set(f"report:{report_date_str}", html_doc, ex=REDIS_REPORT_TTL_SECONDS)
        _redis_client.sadd(REDIS_REPORT_INDEX_KEY, report_date_str)
        _redis_client.expire(REDIS_REPORT_INDEX_KEY, REDIS_REPORT_TTL_SECONDS)
        return {"ok": True, "date": report_date_str, "length": len(html_doc)}
    except Exception as e:
        return {"ok": False, "error": str(e), "date": report_date_str}


def list_available_reports() -> List[str]:
    from backend.radar_service import _redis_client

    if not _redis_client:
        return []
    try:
        dates = _redis_client.smembers(REDIS_REPORT_INDEX_KEY)
        return sorted(dates, reverse=True)
    except Exception:
        return []


def get_report_html(report_date_str: str) -> Optional[str]:
    from backend.radar_service import _redis_client

    if not _redis_client:
        return None
    try:
        return _redis_client.get(f"report:{report_date_str}")
    except Exception:
        return None


REPORT_JOB_KEY_PREFIX = "report_job:"
REPORT_JOB_TTL_SECONDS = 60 * 60  # 1 hour -- long enough to poll to completion, short enough not to accumulate stale job records


def start_report_generation_job(report_date_str: str) -> Dict[str, Any]:
    """
    FIX (2026-08-20): confirmed root cause of "Generate Report" freezing
    for 3+ minutes then failing with a raw 502 -- generate_and_store_report()
    was being called synchronously, inline, inside the HTTP request/response
    cycle. Its underlying computation (full_universe_enriched_campaign_table,
    100 symbols x 7 years of history) is cached, but only for 10 minutes --
    on a cold cache (the common case for a manual click), and after several
    real feature additions stacked onto that same function over time (PnF,
    Gamma, divergence, doctrine, and deterioration-risk overlays, all wired
    in July), the cold-path computation now regularly exceeds both the
    frontend's 180s client timeout and this service's own worker timeout --
    the worker dies mid-request, and Render's proxy returns a 502 with no
    chance for this codebase's own error handling to ever run.

    Same fix pattern already proven for the Weis Analysis tab's identical
    class of problem (Section 2.3.4 of the Aug 15 investigation record):
    move the heavy work into a background thread, decoupled from the
    request/response cycle, and let the frontend poll for the result
    instead of holding the connection open and hoping it finishes in time.

    Job status lives in Redis (report_job:{date}), not in-process memory,
    since this service runs multiple worker processes -- an in-memory dict
    would only be visible to whichever worker happened to handle a given
    request, exactly the kind of bug already caught once this session
    (the frontend cache-key collision) from assuming single-process state
    where multiple processes are actually involved.

    FIX (2026-08-20): the background-thread version above (still true as
    written) genuinely decoupled this from the request/response cycle,
    but running the heavy computation in a THREAD ON THIS SAME BACKEND
    PROCESS didn't decouple it from this process's own memory budget --
    confirmed by a real, repeated 502 (this whole service, including
    the lightweight status-check endpoint, becoming unresponsive) even
    after fixing a separate, real concurrency bug in shared_cache's own
    locking. A single run of the underlying 100-symbol/7-year
    computation, competing with this process's own normal live traffic,
    is apparently enough on its own -- no concurrency needed.

    Reducing symbol count was considered and explicitly rejected
    (report scope must stay at 100). The real fix: don't run this
    computation on the web-facing process's memory budget AT ALL.
    Mirrors the exact, already-proven pattern used for the radar
    scanner itself (tools/render_radar_scanner_worker.py) -- push the
    request onto a Redis queue instead of a local thread; the
    separate, already-isolated worker service (which already runs
    continuously, with its own independent memory, specifically
    because sharing memory with this process caused real OOM crashes
    once before) picks it up and does the actual work in ITS OWN
    process, genuinely off this one's memory budget. See
    run_queued_report_job() and the worker's own polling loop for the
    other half of this.
    """
    from backend.radar_service import _redis_client

    if not _redis_client:
        return {"ok": False, "error": "Redis not configured"}

    job_key = f"{REPORT_JOB_KEY_PREFIX}{report_date_str}"
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        _redis_client.set(job_key, json.dumps({"status": "running", "started_at": started_at}),
                           ex=REPORT_JOB_TTL_SECONDS)
        _redis_client.lpush(REPORT_QUEUE_KEY, report_date_str)
    except Exception as e:
        return {"ok": False, "error": f"Could not start job: {e}"}

    return {"ok": True, "status": "started", "date": report_date_str}


REPORT_QUEUE_KEY = "report_generation_queue"


def run_queued_report_job(report_date_str: str) -> None:
    """
    The actual generation-plus-status-recording logic, extracted so it
    can run wherever a caller wants it to -- specifically, from the
    separate radar-scanner worker process's own polling loop (see that
    file), not this backend service. Genuinely the same logic
    start_report_generation_job()'s old background thread used to run
    inline; only WHERE this executes has changed, not what it does.
    """
    from backend.radar_service import _redis_client
    if not _redis_client:
        return

    job_key = f"{REPORT_JOB_KEY_PREFIX}{report_date_str}"
    started_at = datetime.now(timezone.utc).isoformat()

    try:
        result = generate_and_store_report(report_date_str)
        if result.get("ok"):
            _redis_client.set(job_key, json.dumps({"status": "done", "started_at": started_at,
                                                     "finished_at": datetime.now(timezone.utc).isoformat()}),
                               ex=REPORT_JOB_TTL_SECONDS)
        else:
            _redis_client.set(job_key, json.dumps({"status": "error", "started_at": started_at,
                                                     "error": result.get("error", "unknown error"),
                                                     "finished_at": datetime.now(timezone.utc).isoformat()}),
                               ex=REPORT_JOB_TTL_SECONDS)
    except Exception as e:
        try:
            _redis_client.set(job_key, json.dumps({"status": "error", "started_at": started_at,
                                                     "error": str(e)[:500],
                                                     "finished_at": datetime.now(timezone.utc).isoformat()}),
                               ex=REPORT_JOB_TTL_SECONDS)
        except Exception:
            pass


def process_one_pending_report_job() -> bool:
    """
    Called periodically by the separate radar-scanner worker process
    (not this backend service) -- pops at most one pending report
    request off the queue and runs it, in that worker's own process
    and memory space. Returns True if a job was found and processed,
    False if the queue was empty (so the caller's own loop knows
    whether to check again immediately or wait for its next tick).
    """
    from backend.radar_service import _redis_client
    if not _redis_client:
        return False

    try:
        report_date_str = _redis_client.rpop(REPORT_QUEUE_KEY)
    except Exception:
        return False

    if not report_date_str:
        return False

    run_queued_report_job(report_date_str)
    return True


def get_report_generation_status(report_date_str: str) -> Dict[str, Any]:
    from backend.radar_service import _redis_client

    if not _redis_client:
        return {"status": "unknown", "error": "Redis not configured"}

    job_key = f"{REPORT_JOB_KEY_PREFIX}{report_date_str}"
    try:
        raw = _redis_client.get(job_key)
        if raw is None:
            return {"status": "unknown"}
        return json.loads(raw)
    except Exception as e:
        return {"status": "unknown", "error": str(e)[:200]}


def delete_report(report_date_str: str) -> Dict[str, Any]:
    """
    Removes a stored report: both the actual HTML content (report:{date})
    and the date's entry in the index set (reports:index) -- without
    also removing it from the index, list_available_reports() would
    keep showing the date even after its content was gone, and
    get_report_html() would then return None for a date the UI still
    listed as available.
    """
    from backend.radar_service import _redis_client

    if not _redis_client:
        return {"ok": False, "error": "Redis not configured", "date": report_date_str}

    try:
        existed = _redis_client.exists(f"report:{report_date_str}") or \
            _redis_client.sismember(REDIS_REPORT_INDEX_KEY, report_date_str)
        _redis_client.delete(f"report:{report_date_str}")
        _redis_client.srem(REDIS_REPORT_INDEX_KEY, report_date_str)
        return {"ok": True, "date": report_date_str, "existed": bool(existed)}
    except Exception as e:
        return {"ok": False, "error": str(e), "date": report_date_str}
