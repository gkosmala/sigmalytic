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
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

REPORT_TITLE = "Sigmalytic Quant Corporation - Nightly Intelligence Report"
REPORT_SUBTITLE = "V2 Renko-Weis Intelligence - Daily Subscriber Edition"
COPYRIGHT = "Copyright © 2026 Sigmalytic Quant Corporation. All rights reserved. Confidential and proprietary."

REDIS_REPORT_INDEX_KEY = "reports:index"       # set of available dates


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


def _run_full_universe_renko_weis_scan() -> List[Dict[str, Any]]:
    """
    ADDED (2026-09-13): replaces the old campaign-engine data source
    (backend.campaign_full_enrichment_api, archived earlier this
    session) as the report's core content, per explicit direction:
    reports should not be retired, but rebuilt on the new setup --
    Weis Analysis, with Renko.

    Runs the point-in-time, non-repainting Renko-Weis evaluation
    (backend.research_engine.renko_weis_wave_engine.RenkoWeisWaveEngine
    -- already validated and already live behind
    /api/research/renko-weis/{symbol}, just never previously used for
    full-universe reporting) across every symbol in the exact same
    active universe the Weis Radar scan already uses
    (backend.radar_service._build_active_clean_universe()), rather
    than inventing a separate, different universe for this report.

    Uses fetch_bars_batch() for the network-fetch step -- already
    proven this session to parallelize cleanly across symbols
    (ThreadPoolExecutor, max_workers=10; see radar_service.py's own
    comment on why that specific concurrency level was chosen) --
    reusing that existing, tested safety work rather than re-fetching
    bars sequentially or reinventing parallelization here. The actual
    per-symbol Renko-Weis evaluation is pure, fast CPU work over an
    already-fetched bar list with no further network calls, so it
    runs in a plain sequential loop after the parallel fetch
    completes -- no additional concurrency needed for that part.
    """
    from backend.radar_service import fetch_bars_batch, _build_active_clean_universe
    from backend.research_engine.renko_weis_wave_engine import RenkoWeisWaveEngine

    universe = _build_active_clean_universe()
    bars_map = fetch_bars_batch(universe, timeframe="1Day", limit=252)

    engine = RenkoWeisWaveEngine()
    results: List[Dict[str, Any]] = []
    for sym, bars in bars_map.items():
        if not bars or len(bars) < 20:
            continue
        try:
            verdict = engine.evaluate(bars, symbol=sym)
            results.append(verdict.to_dict())
        except Exception:
            continue
    return results


def _weis_verdict_table_html(rows: List[Dict[str, Any]], title: str, note: str = "", limit: int = 25, bearish: bool = False) -> str:
    """
    ADDED (2026-09-13): the Renko-Weis counterpart to _table_html()
    above -- that function's columns are entirely campaign-specific
    (ODS status, lifecycle, cohort, target/failure prices) and don't
    apply to this genuinely different data shape, so this is a new,
    parallel function rather than a forced adaptation of the old one.
    Set bearish=True to sort/display by the bearish side of the
    verdict (weis_score_bearish/verdict_bearish) instead of the
    bullish side -- the same row dict carries both, since the engine
    always evaluates a symbol both ways.
    """
    score_key = "weis_score_bearish" if bearish else "weis_score"
    verdict_key = "verdict_bearish" if bearish else "verdict"
    shown = sorted(rows, key=lambda r: r.get(score_key) or 0, reverse=True)[:limit]
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
          <td><strong>{_esc(row.get("symbol"))}</strong></td>
          <td>{_esc(row.get(verdict_key))}</td>
          <td class="num">{_fmt(row.get(score_key), 1)}</td>
          <td class="num">{_fmt(row.get("wave_count"), 0)}</td>
          <td>{_esc(row.get("explanation"))}</td>
        </tr>
        """)
    return f"""
    <section class="section">
      <h2>{_esc(title)}</h2>
      {f'<p class="note">{_esc(note)}</p>' if note else ''}
      <table>
        <thead>
          <tr>
            <th>Symbol</th><th>Verdict</th><th class="num">Weis Score</th>
            <th class="num">Wave Count</th><th>Explanation</th>
          </tr>
        </thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </section>
    """


def build_report_html(report_date_str: str) -> str:
    """
    Builds the full HTML report document for a given date.

    REBUILT (2026-09-13): previously used the live full-universe
    enriched campaign table (backend.campaign_full_enrichment_api),
    which was archived earlier this session along with the rest of
    Campaign Intelligence. Per explicit direction, this report is not
    retired -- rebuilt instead on the new setup: a full-universe scan
    using the Renko-Weis engine (_run_full_universe_renko_weis_scan()
    above), the same "pure Weis" analysis already live and validated
    behind /api/research/renko-weis/{symbol}, now run across the full
    active universe rather than one symbol at a time.
    """
    rows = _run_full_universe_renko_weis_scan()

    bullish_rows = [r for r in rows if (r.get("weis_score") or 0) > 0]
    bearish_rows = [r for r in rows if (r.get("weis_score_bearish") or 0) > 0]
    neutral_rows = [r for r in rows if (r.get("weis_score") or 0) <= 0 and (r.get("weis_score_bearish") or 0) <= 0]

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
        Today's review uses the live, full-universe Renko-Weis engine: a point-in-time,
        non-repainting Renko brick reconstruction with David Weis's own Wave Volume
        methodology mapped onto that brick structure, evaluated across {len(rows)} symbols with
        sufficient trading history. The review identified {len(bullish_rows)} symbols with an active
        bullish Weis signal and {len(bearish_rows)} symbols with an active bearish Weis signal.
      </p>
      <p>
        A Weis score reflects Sign-of-Thrust, volume exhaustion, effort-without-reward, and
        wave-confirmation evidence on non-repainting Renko brick structure -- it describes what the
        Renko/Weis structure currently shows, not a prediction or personalized recommendation.
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
        <div class="metric"><div class="num">{len(rows)}</div><div class="txt">Symbols evaluated</div></div>
        <div class="metric"><div class="num">{len(bullish_rows)}</div><div class="txt">Active bullish signals</div></div>
        <div class="metric"><div class="num">{len(bearish_rows)}</div><div class="txt">Active bearish signals</div></div>
        <div class="metric"><div class="num">{len(neutral_rows)}</div><div class="txt">No active signal</div></div>
      </div>
    </section>

    {_weis_verdict_table_html(bullish_rows, "Top Bullish Weis Candidates", "Ranked by Weis score on non-repainting Renko brick structure.", 25, bearish=False)}
    {_weis_verdict_table_html(bearish_rows, "Top Bearish Weis Candidates", "Ranked by Weis score (bearish side) on non-repainting Renko brick structure.", 25, bearish=True)}

    <section class="section">
      <h2>Important Subscriber Notes</h2>
      <p>
        This report is a daily stock-intelligence review generated from Sigmalytic V2's
        Renko-Weis analysis. Bullish and bearish classifications describe current Renko/Weis
        structure and are watchlist categories, not personalized investment advice.
      </p>
    </section>

    <div class="footer">
      {_esc(COPYRIGHT)}<br>
      Sigmalytic Quant Corporation | V2 Renko-Weis Intelligence | Daily Intelligence Report
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
        # Reports are an archive: they must not vanish after 90 days.
        _redis_client.set(f"report:{report_date_str}", html_doc)
        _redis_client.sadd(REDIS_REPORT_INDEX_KEY, report_date_str)
        _redis_client.persist(REDIS_REPORT_INDEX_KEY)  # clear any old 90-day expiry
        if (_redis_client.get(f"report:{report_date_str}") != html_doc
                or not _redis_client.sismember(REDIS_REPORT_INDEX_KEY, report_date_str)):
            return {"ok": False, "error": "Report write could not be verified", "date": report_date_str}
    except Exception as e:
        return {"ok": False, "error": str(e), "date": report_date_str}

    # ADDED (2026-09-19): independent backup to Supabase, a completely
    # separate system from Redis -- built after a confirmed Redis
    # persistence incident wiped every previously-stored report with
    # no way to recover them. Deliberately best-effort and non-fatal:
    # a backup failure must never fail report generation itself, since
    # the Redis copy (already saved above) is still what the app
    # actually serves moment-to-moment.
    backup_ok = True
    try:
        _backup_report_to_supabase(report_date_str, html_doc)
    except Exception as backup_exc:
        backup_ok = False
        print(f"[REPORT_BACKUP] Failed to back up {report_date_str} to Supabase: {backup_exc}", flush=True)

    return {"ok": True, "date": report_date_str, "length": len(html_doc), "backup_ok": backup_ok}


def _report_archive_credentials():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    # report_backups has RLS enabled and no anon policies. Using the anon
    # key here silently returns an empty archive or fails writes.
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("Report archive is not configured on this service")
    return url, key


def _report_archive_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _backup_report_to_supabase(report_date_str: str, html_doc: str) -> None:
    """
    Upserts one report's HTML into public.report_backups (see
    supabase/migrations/20260919_create_report_backups.sql). Uses the
    same direct-REST-call pattern already proven in
    backend/supabase_bars.py, rather than adding a new client library
    dependency for a single table.
    """
    import requests

    url, key = _report_archive_credentials()

    resp = requests.post(
        f"{url}/rest/v1/report_backups",
        headers={
            **_report_archive_headers(key),
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",  # upsert on the report_date primary key
        },
        json={"report_date": report_date_str, "html_content": html_doc},
        timeout=15,
    )
    resp.raise_for_status()


def _archived_report_dates() -> List[str]:
    import requests
    url, key = _report_archive_credentials()
    resp = requests.get(
        f"{url}/rest/v1/report_backups",
        headers=_report_archive_headers(key),
        params={"select": "report_date", "order": "report_date.desc"},
        timeout=10,
    )
    resp.raise_for_status()
    return [row["report_date"] for row in resp.json() if row.get("report_date")]


def _archived_report_html(report_date_str: str) -> Optional[str]:
    import requests
    from datetime import date as _date
    # Keep the PostgREST filter bounded to a real ISO calendar date.
    if _date.fromisoformat(report_date_str).isoformat() != report_date_str:
        return None
    url, key = _report_archive_credentials()
    resp = requests.get(
        f"{url}/rest/v1/report_backups",
        headers=_report_archive_headers(key),
        params={"select": "html_content", "report_date": f"eq.{report_date_str}", "limit": "1"},
        timeout=15,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0].get("html_content") if rows else None


def restore_reports_from_supabase_backup() -> Dict[str, Any]:
    """
    ADDED (2026-09-19): the recovery half of the backup above. Reads
    every backed-up report from Supabase and re-populates Redis's
    report:{date} keys and the reports:index set -- intended to be
    called once, manually, via a new admin endpoint, specifically for
    situations like the one that motivated this: Redis was reset and
    lost everything Supabase still has a copy of.
    """
    import requests
    from backend.radar_service import _redis_client

    if not _redis_client:
        return {"ok": False, "error": "Redis not configured"}

    try:
        url, key = _report_archive_credentials()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    resp = requests.get(
        f"{url}/rest/v1/report_backups",
        headers=_report_archive_headers(key),
        params={"select": "report_date,html_content"},
        timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()

    restored = []
    for row in rows:
        date_str = row.get("report_date")
        html_doc = row.get("html_content")
        if not date_str or not html_doc:
            continue
        if not _redis_client.exists(f"report:{date_str}"):
            _redis_client.set(f"report:{date_str}", html_doc)
        _redis_client.sadd(REDIS_REPORT_INDEX_KEY, date_str)
        restored.append(date_str)

    if restored:
        _redis_client.persist(REDIS_REPORT_INDEX_KEY)

    return {"ok": True, "restored_dates": sorted(restored), "count": len(restored)}


def report_catalog() -> Dict[str, Any]:
    from backend.radar_service import _redis_client

    redis_dates = set()
    try:
        if _redis_client is not None:
            redis_dates = set(_redis_client.smembers(REDIS_REPORT_INDEX_KEY))
    except Exception as exc:
        print(f"[REPORT_LIST] Redis index unavailable: {exc}", flush=True)

    try:
        archived_dates = _archived_report_dates()
        return {"ok": True, "dates": sorted(redis_dates | set(archived_dates), reverse=True)}
    except Exception as exc:
        print(f"[REPORT_LIST] Supabase archive unavailable: {exc}", flush=True)
        if redis_dates:
            return {"ok": True, "dates": sorted(redis_dates, reverse=True),
                    "warning": "Report history may be incomplete; archive unavailable"}
        return {"ok": False, "dates": [],
                "error": "Report storage is unavailable; cannot verify report history"}


def list_available_reports() -> List[str]:
    return report_catalog()["dates"]


def get_report_html(report_date_str: str) -> Optional[str]:
    from backend.radar_service import _redis_client

    try:
        if _redis_client is not None:
            html_doc = _redis_client.get(f"report:{report_date_str}")
            if html_doc:
                return html_doc
    except Exception as exc:
        print(f"[REPORT_GET] Redis unavailable: {exc}", flush=True)

    try:
        html_doc = _archived_report_html(report_date_str)
    except Exception as exc:
        print(f"[REPORT_GET] Supabase archive unavailable: {exc}", flush=True)
        return None
    if html_doc and _redis_client is not None:
        try:
            _redis_client.set(f"report:{report_date_str}", html_doc)
            _redis_client.sadd(REDIS_REPORT_INDEX_KEY, report_date_str)
            _redis_client.persist(REDIS_REPORT_INDEX_KEY)
        except Exception as exc:
            print(f"[REPORT_GET] Redis restore unavailable: {exc}", flush=True)
    return html_doc


REPORT_JOB_KEY_PREFIX = "report_job:"
REPORT_JOB_TTL_SECONDS = 60 * 60  # 1 hour -- long enough to poll to completion, short enough not to accumulate stale job records


def deliver_saved_report(report_date_str: str) -> Dict[str, int]:
    """Email the archived report only to verified accounts with explicit opt-in.

    Called only for the scheduled nightly job, after the independent archive
    write succeeds. A manual regeneration never broadcasts the report.
    """
    import requests
    from backend.radar_service import _redis_client

    url, key = _report_archive_credentials()
    html_doc = _archived_report_html(report_date_str)
    if not html_doc:
        raise RuntimeError("Saved archive content is missing; no email sent")
    counts = {"email_sent": 0, "email_failed": 0}
    offset = 0
    sender_key = os.environ.get("RESEND_API_KEY", "")
    while True:
        response = requests.get(
            f"{url}/rest/v1/user_preferences", headers=_report_archive_headers(key),
            params={"select": "user_id,alert_types", "order": "user_id.asc",
                    "limit": "500", "offset": str(offset)}, timeout=15,
        )
        response.raise_for_status()
        batch = response.json()
        recipients = [p for p in batch if isinstance(p.get("alert_types"), dict)
                      and p["alert_types"].get("daily_report_email") is True]
        if recipients and not sender_key:
            raise RuntimeError("RESEND_API_KEY missing; no report emails sent")
        for pref in recipients:
            user_id = pref.get("user_id")
            if not user_id or user_id == "demo_user_001":
                continue
            # Never trust the editable email in user_preferences. Only the
            # email of this Supabase auth account may receive the report.
            auth = requests.get(f"{url}/auth/v1/admin/users/{user_id}",
                                headers=_report_archive_headers(key), timeout=15)
            if auth.status_code == 404:
                continue
            auth.raise_for_status()
            account = auth.json()
            email = account.get("email") if account.get("email_confirmed_at") else None
            if not email:
                continue
            sent_key = f"report_email_sent:{report_date_str}:{user_id}"
            # Claim before sending so overlapping nightly runs do not broadcast
            # twice. A failed send releases the claim for the next attempt.
            if not _redis_client.set(sent_key, "sending", nx=True, ex=120):
                continue
            try:
                sent = requests.post(
                    "https://api.resend.com/emails",
                    headers={"Authorization": f"Bearer {sender_key}",
                             "Content-Type": "application/json"},
                    json={"from": os.environ.get("ALERT_FROM_EMAIL", "alerts@sigmalytic.com"),
                          "to": [email],
                          "subject": f"Sigmalytic Daily Intelligence Report - {report_date_str}",
                          "html": html_doc}, timeout=20,
                )
                sent.raise_for_status()
                _redis_client.set(sent_key, "sent")
                counts["email_sent"] += 1
            except Exception as exc:
                _redis_client.delete(sent_key)
                counts["email_failed"] += 1
                print(f"[REPORT_EMAIL] Delivery failed for report {report_date_str}: {exc}", flush=True)
        if len(batch) < 500:
            return counts
        offset += len(batch)


def start_report_generation_job(report_date_str: str, deliver_email: bool = False) -> Dict[str, Any]:
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
        _redis_client.lpush(REPORT_QUEUE_KEY, json.dumps({"date": report_date_str,
                                                         "deliver_email": deliver_email}))
    except Exception as e:
        return {"ok": False, "error": f"Could not start job: {e}"}

    return {"ok": True, "status": "started", "date": report_date_str}


REPORT_QUEUE_KEY = "report_generation_queue"


def run_queued_report_job(report_date_str: str, deliver_email: bool = False) -> None:
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
            delivery = {"email_sent": 0, "email_failed": 0}
            if deliver_email and result.get("backup_ok"):
                try:
                    delivery = deliver_saved_report(report_date_str)
                except Exception as exc:
                    delivery = {"email_sent": 0, "email_failed": 0,
                                "email_error": str(exc)[:300]}
            elif deliver_email:
                delivery["email_error"] = "Report archive backup failed; emails withheld"
            _redis_client.set(job_key, json.dumps({"status": "done", "started_at": started_at,
                                                     "finished_at": datetime.now(timezone.utc).isoformat(),
                                                     "backup_ok": result.get("backup_ok", False),
                                                     **delivery}),
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

    try:
        job = json.loads(report_date_str)
        date_str = job["date"] if isinstance(job, dict) else report_date_str
        email_requested = isinstance(job, dict) and job.get("deliver_email") is True
    except (ValueError, TypeError, KeyError):
        # The previous queue format used a bare ISO date.
        date_str, email_requested = report_date_str, False
    run_queued_report_job(date_str, deliver_email=email_requested)
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
        # A Redis-only delete would make the report reappear immediately
        # through the new archive read path. Remove the durable copy first.
        import requests
        from datetime import date as _date
        if _date.fromisoformat(report_date_str).isoformat() != report_date_str:
            return {"ok": False, "error": "Invalid report date", "date": report_date_str}
        url, key = _report_archive_credentials()
        archive_resp = requests.delete(
            f"{url}/rest/v1/report_backups",
            headers=_report_archive_headers(key),
            params={"report_date": f"eq.{report_date_str}"}, timeout=15,
        )
        archive_resp.raise_for_status()
        existed = _redis_client.exists(f"report:{report_date_str}") or \
            _redis_client.sismember(REDIS_REPORT_INDEX_KEY, report_date_str)
        _redis_client.delete(f"report:{report_date_str}")
        _redis_client.srem(REDIS_REPORT_INDEX_KEY, report_date_str)
        return {"ok": True, "date": report_date_str, "existed": bool(existed)}
    except Exception as e:
        return {"ok": False, "error": str(e), "date": report_date_str}
