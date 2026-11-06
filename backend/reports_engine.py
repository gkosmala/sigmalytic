# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/reports_engine.py
---------------------------
Daily subscriber intelligence report -- generation and storage.

The current report scans dated daily bars from one sector-classified
equity universe. It applies the existing Wyckoff/Weis event detectors,
time-bar volume-climax rules, and Renko-Weis exhaustion screening,
and derives sector breadth from those same bars. Legacy campaign/ODS
results and the radar cache are not report data sources.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

REPORT_TITLE = "Sigmalytic Quant Corporation - Nightly Intelligence Report"
REPORT_SUBTITLE = "Daily market opportunities and sector movement"
COPYRIGHT = "Copyright © 2026 Sigmalytic Quant Corporation. All rights reserved. Confidential and proprietary."

REDIS_REPORT_INDEX_KEY = "reports:index"       # set of available dates
# The report's own breakout/breakdown lifecycle, kept apart from the Weis Radar
# screen's state so radar settings (timeframe, signals, manual scans) never
# change what the dated report says. Same engine: backend.weis_radar_lifecycle.
REPORT_LIFECYCLE_KEY = "report:lifecycle:v1"
CROSSING_SIGNALS = ("BREAKOUT", "BREAKDOWN")


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
table.crossing { font-size: 9.5px; }
table.crossing th { padding: 5px 4px; }
table.crossing td { padding: 4px; }
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
      <p class="note">Largest absolute close-to-close changes among symbols with verified bars
      for the data-through date below. Relative volume compares that day's volume with the preceding
      20 daily bars. These values come from the same historical-bar feed as the candidate tables.</p>
      <table>
        <thead>
          <tr><th>Symbol</th><th class="num">Price</th><th class="num">Change</th><th class="num">Rel. Volume</th><th class="num">Volume</th></tr>
        </thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </section>
    """


def _bar_market_date(bar: Dict[str, Any]) -> Optional[str]:
    """Alpaca daily timestamps are at midnight in New York."""
    try:
        stamp = str(bar.get("t") or "").replace("Z", "+00:00")
        return datetime.fromisoformat(stamp).astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _wave_evidence(waves: List[Any], bars: List[Dict[str, Any]], bearish: bool) -> Dict[str, Any]:
    """Actual inputs to the three binary checks, without altering their scores."""
    opposite_direction = 1 if bearish else -1
    compared = [w for w in waves if w.direction == opposite_direction]
    last_three = compared[-3:]
    recent = compared[-1] if compared else None
    preceding = compared[-2] if len(compared) >= 2 else None
    current = waves[-1] if waves else None
    reference = (recent.cumulative_volume + preceding.cumulative_volume) if preceding else None
    return {
        "progress": [round(w.price_progress, 4) for w in last_three],
        "volumes": [round(w.cumulative_volume) for w in last_three],
        "exhaustion_ratio": (recent.cumulative_volume / preceding.cumulative_volume
                             if preceding and preceding.cumulative_volume > 0 else None),
        "confirmation_ratio": (current.cumulative_volume / reference
                               if current and current.direction == -opposite_direction
                               and reference and reference > 0 else None),
        "current_volume": round(current.cumulative_volume) if current else None,
        "reference_volume": round(reference) if reference is not None else None,
        "current_direction": ("UP" if current.direction == 1 else "DOWN") if current else None,
        "wave_start_date": (_bar_market_date(bars[current.start_index])
                            if current and current.start_index is not None
                            and 0 <= current.start_index < len(bars) else None),
    }


def _market_movers_from_scanned_rows(rows: List[Dict[str, Any]], limit: int = 15) -> List[Dict[str, Any]]:
    available = [r for r in rows if _safe_float(r.get("change_pct")) is not None]
    return sorted(available, key=lambda r: abs(r["change_pct"]), reverse=True)[:limit]


def _run_full_universe_renko_weis_scan() -> List[Dict[str, Any]]:
    """
    Fetch split/dividend-adjusted bars for the Heat Map's classified
    stock universe and compute all report evidence from that snapshot.
    No asynchronous radar cache or legacy campaign score is read.
    """
    from backend.radar_service import fetch_bars_batch, compute_symbol_signals, trim_incomplete_bar
    from backend.weis_radar_scan import _bars_to_dataframe, scan_symbol_for_weis_patterns
    from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
    from backend.heatmap_engine import _load_sector_lookup
    from backend.research_engine.renko_weis_wave_engine import RenkoWeisWaveEngine

    # The sector-identified equity universe used by the actual Heat Map,
    # avoiding the prior 1,500-symbol alphabetic fill with ETF results.
    universe = list(_load_sector_lookup())
    if not universe:
        raise ValueError("Sector reference universe is unavailable")
    bars_map = fetch_bars_batch(universe, timeframe="1Day", limit=252, adjustment="all")

    from backend.radar_service import _redis_client
    from backend.weis_radar_lifecycle import WeisRadarLifecycleTracker

    engine = RenkoWeisWaveEngine()
    wyckoff = WyckoffVerdictEngine()
    # Fixed report profile: daily completed bars, breakouts and breakdowns
    # always detected, tracked with the Weis Radar lifecycle engine.
    tracker = WeisRadarLifecycleTracker(_redis_client, "1Day",
                                        scan_id=datetime.now(timezone.utc).isoformat(),
                                        state_key=REPORT_LIFECYCLE_KEY)
    results: List[Dict[str, Any]] = []
    daily_bars: Dict[str, List[Dict[str, Any]]] = {}
    for sym, bars in bars_map.items():
        bars = trim_incomplete_bar(bars, "1Day")
        daily_bars[sym] = bars
        if not bars or len(bars) < 20:
            continue
        try:
            last_date = _bar_market_date(bars[-1])
            if not last_date:
                continue  # Cannot assert when undated source data was observed.
            waves = engine.build_waves(bars)
            if not waves:
                continue
            verdict = engine.evaluate(bars, symbol=sym, waves=waves)
            result = verdict.to_dict()
            result.update(last_bar_date=last_date, bars_used=len(bars),
                          bullish_evidence=_wave_evidence(waves, bars, bearish=False),
                          bearish_evidence=_wave_evidence(waves, bars, bearish=True))
            close = _safe_float(bars[-1].get("c"))
            prior = _safe_float(bars[-2].get("c"))
            volume = _safe_float(bars[-1].get("v"))
            trailing = [_safe_float(b.get("v")) for b in bars[-21:-1]]
            result.update(price=close, volume=volume,
                          change_pct=((close / prior - 1) * 100 if close is not None and prior and prior > 0 else None),
                          rel_volume=(volume / (sum(trailing) / 20)
                                      if volume is not None and len(trailing) == 20
                                      and all(v is not None for v in trailing) and sum(trailing) > 0 else None))
            crossing_hits = []
            if len(bars) >= 65:
                df = _bars_to_dataframe(bars)
                all_hits = scan_symbol_for_weis_patterns(wyckoff, df)
                crossing_hits = [hit for hit in all_hits if hit.get("type") in CROSSING_SIGNALS]
                result["events"] = [
                    hit for hit in all_hits
                    if hit.get("type") in ("SPRING", "UPTHRUST")
                    or (hit.get("type") in ("BREAKOUT", "BREAKDOWN")
                        and hit.get("days_back", 999) <= 3)
                ]
                # Only near a genuine multi-touch level, still on the
                # unbroken side. This is a watch condition, not a signal.
                prepared = wyckoff._prepare(df)
                idx = len(prepared) - 1
                resistance = wyckoff._find_well_defined_level(prepared, idx, is_support=False)
                support = wyckoff._find_well_defined_level(prepared, idx, is_support=True)
                result["setups"] = []
                if close is not None and resistance and 0 <= (resistance - close) / resistance <= 0.02:
                    result["setups"].append({"side": "Near resistance", "level": resistance,
                                             "distance_pct": 100 * (resistance - close) / resistance})
                if close is not None and support and 0 <= (close - support) / support <= 0.02:
                    result["setups"].append({"side": "Near support", "level": support,
                                             "distance_pct": 100 * (close - support) / support})
            else:
                result["events"], result["setups"] = [], []

            # These use the same live Weis Radar time-bar signal rules,
            # independent of the supplementary Renko heuristic above.
            result["climaxes"] = [
                signal["signal"] for signal in compute_symbol_signals(
                    sym, bars, {"climaxup", "climaxdown"}, "1Day")
                if signal.get("signal") in ("CLIMAX_BUY", "CLIMAX_SELL")
            ]
            if result["climaxes"]:
                from backend.weis_wave import WeisWaveEngine
                from backend.radar_service import weis_wave_threshold_for_timeframe
                time_waves = WeisWaveEngine(weis_wave_threshold_for_timeframe("1Day")).calculate_waves(bars[-60:])
                if len(time_waves) >= 2:
                    result["climax_evidence"] = {
                        "current_volume": round(time_waves[-1].cum_volume),
                        "prior_volume": round(time_waves[-2].cum_volume),
                        "current_progress": round(time_waves[-1].price_range, 4),
                        "prior_progress": round(time_waves[-2].price_range, 4),
                    }
            # Open breakouts/breakdowns are evaluated on every symbol's new
            # bars even when no new crossing is detected today.
            try:
                tracker.process_symbol(sym, bars, crossing_hits)
            except Exception:
                pass
            results.append(result)
        except Exception:
            continue
    by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for event in tracker.events.values():
        if isinstance(event, dict) and event.get("signal_type") in CROSSING_SIGNALS:
            by_symbol.setdefault(event.get("symbol"), []).append(event)
    for result in results:
        result["lifecycle"] = _report_lifecycle_events(by_symbol.get(result.get("symbol"), []),
                                                       result.get("last_bar_date"))
    _enrich_crossing_rows(results, daily_bars, fetch_bars_batch, trim_incomplete_bar)
    try:
        tracker.save()   # after enrichment, so a trend start date found tonight is kept
    except Exception:
        pass
    return results


def _daily_change_by_date(bars: List[Dict[str, Any]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for prev, cur in zip(bars, bars[1:]):
        p, c, d = _safe_float(prev.get("c")), _safe_float(cur.get("c")), _bar_market_date(cur)
        if p and c is not None and d:
            out[d] = (c / p - 1) * 100
    return out


TREND_AVERAGE_BARS = 10
TREND_MIN_CHANGE_PCT = 2.0


def _trend_gate(closes: List[float], i: int, bullish: bool) -> bool:
    """Trend gate on bar i: close beyond its 10-day average, the average moving
    the break's way, and the 10-day change beyond +2% (or -2% for breakdowns)."""
    n = TREND_AVERAGE_BARS
    if i < n or i >= len(closes):
        return False
    avg = sum(closes[i - n + 1:i + 1]) / n
    prev_avg = sum(closes[i - n:i]) / n
    change = (closes[i] / closes[i - n] - 1) * 100 if closes[i - n] else 0.0
    if bullish:
        return closes[i] > avg and avg > prev_avg and change > TREND_MIN_CHANGE_PCT
    return closes[i] < avg and avg < prev_avg and change < -TREND_MIN_CHANGE_PCT


BOX_CONFIRM_SESSIONS = 3


def _trend_boxes(bars: List[Dict[str, Any]], i0: int, bullish: bool) -> Dict[str, Any]:
    """Trend phases from the crossing bar i0 to the latest bar, as stair steps.

    Bullish (breakdowns are the mirror image, run on negated prices):
    - Sideways: before the trend gate is first crossed.
    - Trending: gate crossed; step 1. Each close above a box top is the next step.
    - Box: once 3 sessions pass with no new high, a box opens. Top = the trend's
      highest high; bottom = the lowest low since, fixed after 3 sessions with no
      new low. It extends right while closes stay inside.
    - Close above the top: trend resumes (next step). Close below a fixed bottom:
      trend broken, until the gate is crossed again (trend 2, step 1).
    Box edges use highs/lows; a close beyond an edge ends the box."""
    sign = 1 if bullish else -1
    hi = [sign * (_safe_float(b.get("h")) if bullish else _safe_float(b.get("l"))) for b in bars]
    lo = [sign * (_safe_float(b.get("l")) if bullish else _safe_float(b.get("h"))) for b in bars]
    cl = [_safe_float(b.get("c")) for b in bars]
    if any(v is None for v in cl):
        return {}
    cl_t = [sign * c for c in cl]
    real = (lambda v: sign * v)
    st: Dict[str, Any] = {"phase": "sideways", "trend": 0, "step": 0, "boxes": []}
    high_i = None
    box = None
    for k in range(i0, len(bars)):
        phase = st["phase"]
        if phase in ("sideways", "broken"):
            if _trend_gate(cl, k, bullish):
                st.update(phase="trending", trend=st["trend"] + 1, step=1,
                          trend_start=k, phase_start=k)
                high_i = max(range(st.get("broken_at", i0) if phase == "broken" else i0, k + 1), key=lambda j: hi[j])
            continue
        if phase == "trending":
            if hi[k] >= hi[high_i]:
                high_i = k
            elif k - high_i >= BOX_CONFIRM_SESSIONS:
                lows = range(high_i + 1, k + 1)
                b_i = min(lows, key=lambda j: lo[j])
                box = {"top": hi[high_i], "bottom": lo[b_i], "bottom_i": b_i, "fixed": k - b_i >= BOX_CONFIRM_SESSIONS,
                       "opened": k, "top_date": _bar_market_date(bars[high_i])}
                st.update(phase="box", phase_start=high_i + 1)   # the pause began after the high
            continue
        if phase == "box":
            if cl_t[k] > box["top"]:
                st["boxes"].append(box)
                st.update(phase="trending", step=st["step"] + 1, phase_start=k)
                high_i, box = k, None
            elif box["fixed"] and cl_t[k] < box["bottom"]:
                st["boxes"].append(box)
                st.update(phase="broken", phase_start=k, broken_at=k, broken_date=_bar_market_date(bars[k]))
                box = None
            elif not box["fixed"]:
                if lo[k] < box["bottom"]:
                    box["bottom"], box["bottom_i"] = lo[k], k
                if k - box["bottom_i"] >= BOX_CONFIRM_SESSIONS:
                    box["fixed"] = True
    last = len(bars) - 1
    st["phase_day"] = last - st.get("phase_start", i0) + 1
    st["trend_start_date"] = _bar_market_date(bars[st["trend_start"]]) if "trend_start" in st else None

    def edges(b):
        a, c = real(b["bottom"]), real(b["top"])
        return {"low": min(a, c), "high": max(a, c), "fixed": b["fixed"], "top_date": b["top_date"]}
    st["box"] = edges(box) if box else None
    st["prior_boxes"] = [edges(b) for b in st.pop("boxes")]
    return st


def _trend_label(st: Dict[str, Any], day: int, bullish: bool) -> str:
    word = "bullish" if bullish else "bearish"
    prefix = f"Trend {st['trend']}: " if st.get("trend", 0) > 1 else ""
    phase = st.get("phase")
    if phase == "trending":
        return f"{prefix}Trending {word}, step {st['step']} (trend began {st['trend_start_date']})"
    if phase == "box":
        b = st["box"]
        bottom = "" if b["fixed"] else ", bottom still forming"
        return (f"{prefix}In box {st['step']}, day {st['phase_day']}: "
                f"{_fmt(b['low'], 2)}–{_fmt(b['high'], 2)}{bottom}")
    if phase == "broken":
        side = "bottom" if bullish else "top"
        return f"Trend broken {st['broken_date']} (closed beyond box {st['step']} {side}), day {st['phase_day']}"
    return f"Sideways, day {day}"


def _pivot_label(st: Dict[str, Any], bullish: bool) -> str:
    """Box edges as resistance (R) and support (S): the current box, then the prior one."""
    parts = []
    for name, b in (("Box", st.get("box")), ("Prior box", (st.get("prior_boxes") or [None])[-1])):
        if b:
            parts.append(f"{name}: R {_fmt(b['high'], 2)} / S {_fmt(b['low'], 2)}")
    return "; ".join(parts)


def _four_hour_alignment(bars: List[Dict[str, Any]], level: Optional[float], bullish: bool) -> str:
    """Whether the 4-hour chart agrees with the daily break: the latest completed
    4-hour close is beyond the level, and above (bullish) / below (bearish) its
    20-bar average. Both agree = Aligned, both disagree = Against, else Mixed."""
    closes = [c for c in (_safe_float(b.get("c")) for b in bars or []) if c is not None]
    if len(closes) < 20 or not level:
        return "n/a"
    last, avg = closes[-1], sum(closes[-20:]) / 20
    beyond = last > level if bullish else last < level
    trend = last > avg if bullish else last < avg
    return "Aligned" if beyond and trend else "Against" if not beyond and not trend else "Mixed"


def _enrich_crossing_rows(results, daily_bars, fetch_bars_batch, trim_incomplete_bar) -> None:
    """Context the breakout/breakdown sections show for every entry: sector, the
    S&P 500 (SPY) move, relative strength against it, crossing-day relative
    volume, and 4-hour alignment. Each piece is optional: a failed lookup shows
    as n/a rather than stopping the report."""
    from backend.heatmap_engine import _load_sector_lookup
    lookup = _load_sector_lookup()
    spy_change: Dict[str, float] = {}
    try:
        spy = fetch_bars_batch(["SPY"], timeframe="1Day", limit=252, adjustment="all").get("SPY") or []
        spy_change = _daily_change_by_date(trim_incomplete_bar(spy, "1Day"))
    except Exception:
        spy_change = {}

    tracked = [r for r in results if r.get("lifecycle")]
    four_hour: Dict[str, List[Dict[str, Any]]] = {}
    try:
        if tracked:
            raw = fetch_bars_batch([r["symbol"] for r in tracked], timeframe="4Hour", limit=60)
            four_hour = {sym: trim_incomplete_bar(b, "4Hour") for sym, b in (raw or {}).items()}
    except Exception:
        four_hour = {}

    for result in results:
        result["spy_change_pct"] = spy_change.get(result.get("last_bar_date"))
        result["sector"] = (lookup.get(result.get("symbol")) or {}).get("sector") or "—"
        if not result.get("lifecycle"):
            continue
        bars = daily_bars.get(result["symbol"]) or []
        changes = _daily_change_by_date(bars)
        index = {_bar_market_date(b): i for i, b in enumerate(bars)}
        for event in result["lifecycle"]:
            crossed = _event_market_date(event.get("trigger_bar_time"))
            ctx: Dict[str, Any] = {"crossed": crossed}
            i = index.get(crossed)
            if i is not None and i >= 20:
                trailing = [_safe_float(b.get("v")) for b in bars[i - 20:i]]
                vol = _safe_float(bars[i].get("v"))
                if vol is not None and all(v is not None for v in trailing) and sum(trailing) > 0:
                    ctx["crossing_rel_volume"] = vol / (sum(trailing) / 20)
            ctx["crossing_change_pct"] = changes.get(crossed)
            ctx["spy_crossing_change_pct"] = spy_change.get(crossed)
            ctx["four_hour"] = _four_hour_alignment(four_hour.get(result["symbol"]),
                                                    _safe_float(event.get("structure_level")),
                                                    event.get("direction") == "Bullish")
            # Day count: the crossing day is day 1.
            ctx["day"] = int(event.get("bars_observed_after_trigger") or 0) + 1
            # Trend phases (sideways / trending in steps / box / broken),
            # recomputed nightly from the crossing bar. Kept on the event so a
            # crossing older than the fetched bars still shows its last state.
            if event.get("stage") in ("TRIGGERED", "CONFIRMED"):
                if i is not None:
                    state = _trend_boxes(bars, i, event.get("direction") == "Bullish")
                    if state:
                        event["trend_state"] = state
                ctx["trend_state"] = event.get("trend_state")
            event["report_context"] = ctx


def _event_market_date(bar_time: Any) -> Optional[str]:
    return _bar_market_date({"t": bar_time}) if bar_time else None


def _report_lifecycle_events(events: List[Dict[str, Any]], report_date: Optional[str]) -> List[Dict[str, Any]]:
    """Breakout/breakdown events worth showing on this date: everything still
    open (no time limit) plus anything that failed on this date."""
    shown = []
    for event in events:
        stage = event.get("stage")
        if stage in ("TRIGGERED", "CONFIRMED"):
            shown.append(event)
        elif stage == "INVALIDATED" and not _superseded(event, events):
            # Failed attempts stay listed (no time limit) as levels to watch for
            # another attempt, until the same level is crossed again.
            shown.append(event)
    return shown


def _superseded(event: Dict[str, Any], events: List[Dict[str, Any]]) -> bool:
    """A later attempt at the same level (within 1%) replaces a failed one."""
    level = _safe_float(event.get("structure_level"))
    if not level:
        return False
    for other in events:
        if other is event or other.get("signal_type") != event.get("signal_type"):
            continue
        o = _safe_float(other.get("structure_level"))
        if o and abs(o / level - 1) <= 0.01 and str(other.get("trigger_bar_time") or "") > str(event.get("trigger_bar_time") or ""):
            return True
    return False


def _pct(value: Any, signed: bool = True) -> str:
    v = _safe_float(value)
    if v is None:
        return "n/a"
    v = 0.0 if abs(v) < 0.005 else v   # no "-0.00%"
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _lifecycle_sections(rows: List[Dict[str, Any]], report_date: str, signal: str) -> Dict[str, List[Dict[str, Any]]]:
    """Breakout or breakdown entries grouped by lifecycle stage, with the
    measurements each table row shows."""
    out: Dict[str, List[Dict[str, Any]]] = {"new": [], "confirmed": [], "holding": [], "failed": [], "retry": []}
    for row in rows:
        price = _safe_float(row.get("price"))
        today = _safe_float(row.get("change_pct"))
        spy_today = _safe_float(row.get("spy_change_pct"))
        for event in row.get("lifecycle") or []:
            if event.get("signal_type") != signal:
                continue
            ctx = event.get("report_context") or {}
            stage = event.get("stage")
            bullish = event.get("direction") == "Bullish"
            sign = 1 if bullish else -1
            level = _safe_float(event.get("structure_level"))
            crossed = ctx.get("crossed") or _event_market_date(event.get("trigger_bar_time")) or "?"
            sessions = int(event.get("bars_observed_after_trigger") or 0)
            failed_on = _event_market_date(event.get("terminal_bar_time")) if stage == "INVALIDATED" else None
            if stage == "INVALIDATED":
                bucket = "failed" if failed_on == report_date else "retry"
            elif crossed == report_date:
                bucket = "new"
            elif stage == "CONFIRMED":
                bucket = "confirmed"
            else:
                bucket = "holding"
            cc, sc = _safe_float(ctx.get("crossing_change_pct")), _safe_float(ctx.get("spy_crossing_change_pct"))
            confirm_word = "above" if bullish else "below"
            if bucket == "failed":
                status = "Failed after confirmation" if event.get("failed_after_confirmation") else "Failed before confirming"
            elif bucket == "retry":
                status = f"Failed {failed_on}; watching for attempt {int(event.get('attempt') or 1) + 1}"
            elif stage == "CONFIRMED":
                status = f"Confirmed {_event_market_date(event.get('confirmed_bar_time'))}"
            else:
                status = f"Needs a close {confirm_word} {_fmt(event.get('confirmation_level'), 2)} to confirm"
            out[bucket].append(dict(
                symbol=row.get("symbol", ""),
                direction=(f"{'Bullish breakout' if bullish else 'Bearish breakdown'}, day {ctx.get('day') or sessions + 1}"),
                trend=("" if stage == "INVALIDATED" else
                       _trend_label(ctx.get("trend_state") or {}, ctx.get("day") or sessions + 1, bullish)),
                trend_phase=("" if stage == "INVALIDATED" else (ctx.get("trend_state") or {}).get("phase", "sideways")),
                pivots=("" if stage == "INVALIDATED" else _pivot_label(ctx.get("trend_state") or {}, bullish)),
                close=price,
                sector=row.get("sector") or "—",
                level=level,
                attempt=int(event.get("attempt") or 1),
                crossed=crossed,
                sessions=sessions,
                today=today,
                today_vs_spy=(today - spy_today) if today is not None and spy_today is not None else None,
                crossing_vs_spy=(cc - sc) if cc is not None and sc is not None else None,
                beyond=(sign * (price / level - 1) * 100) if price and level else None,
                # Both stored in the break's direction (positive = moving the way it broke),
                # matching Beyond level.
                since=_safe_float(event.get("pct_since_trigger")),
                best=_safe_float(event.get("best_pct_since_trigger")),
                rel_volume=ctx.get("crossing_rel_volume"),
                four_hour=ctx.get("four_hour") or "n/a",
                status=status,
                priority=sessions,
            ))
    for items in out.values():
        items.sort(key=lambda i: (i["priority"], i["symbol"]))
    return out


_CROSSING_HEADERS = ["Symbol", "Breakout / breakdown", "Close", "Sector", "Trend", "Pivots (box edges)", "Level (attempt)", "Crossed",
                     "Today (vs S&P)", "Crossing day vs S&P", "Beyond level", "Since crossing (best)",
                     "Crossing-day volume", "4-hour", "Status"]


def _crossing_row(i: Dict[str, Any]) -> str:
    crossed = i["crossed"] + (f" ({i['sessions']} sessions ago)" if i["sessions"] > 1
                              else " (1 session ago)" if i["sessions"] == 1 else "")
    volume = "n/a" if i["rel_volume"] is None else f"{float(i['rel_volume']):.1f}x 20-day avg"
    cells = [i["direction"], _fmt(i["close"], 2), i["sector"], i.get("trend") or "", i.get("pivots") or "",
             f"{_fmt(i['level'], 2)} (#{i['attempt']})",
             crossed, f"{_pct(i['today'])} ({_pct(i['today_vs_spy'])})", _pct(i["crossing_vs_spy"]),
             _pct(i["beyond"]), f"{_pct(i['since'])} ({_pct(i['best'])})", volume, i["four_hour"], i["status"]]
    return (f"<tr><td><strong>{_esc(i['symbol'])}</strong></td>"
            + "".join(f"<td>{_esc(c)}</td>" for c in cells) + "</tr>")


def _crossing_table(items: List[Dict[str, Any]], title: str, note: str, limit: int) -> str:
    """Breakout/breakdown table. Symbol, direction and close come first so the
    Content Hub reader (symbols_from_report_html) parses it like other tables."""
    shown = items[:limit]
    body = "".join(_crossing_row(i) for i in shown)
    head = "".join(f"<th>{_esc(h)}</th>" for h in _CROSSING_HEADERS)
    return f"""<section class="section"><h2>{_esc(title)} ({len(items)})</h2>
      <p class="note">{_esc(note)}</p>
      {(f'<table class="crossing"><thead><tr>{head}</tr></thead><tbody>' + body + '</tbody></table>')
       if body else '<p class="muted">No symbols met this rule on the dated bars in this report.</p>'}
      {f'<p class="note">Showing {limit} of {len(items)}.</p>' if len(items) > limit else ''}
    </section>"""


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
    # These scores have only a handful of possible values. A tie does not
    # imply one candidate is better; sort tied rows alphabetically rather
    # than presenting a random fetch-completion order as an assessment.
    shown = sorted(rows, key=lambda r: (-(_safe_float(r.get(score_key)) or 0), str(r.get("symbol") or "")))[:limit]
    if not shown:
        return f"""
        <section class="section">
          <h2>{_esc(title)}</h2>
          <p class="muted">No rows met this section's criteria in today's review.</p>
        </section>
        """
    body = []
    for row in shown:
        evidence = row.get("bearish_evidence" if bearish else "bullish_evidence") or {}
        progress = evidence.get("progress") or []
        volumes = evidence.get("volumes") or []
        progress_text = " / ".join(_fmt(p, 2) for p in progress) if len(progress) == 3 else "insufficient waves"
        volume_text = " / ".join(_fmt(v, 0) for v in volumes) if len(volumes) == 3 else "insufficient waves"
        ratio = evidence.get("exhaustion_ratio")
        confirm = evidence.get("confirmation_ratio")
        side = "Up" if bearish else "Down"
        evidence_html = (
            f"{side} waves, oldest to newest: price progress {_esc(progress_text)}; "
            f"estimated wave volume {_esc(volume_text)}.<br>"
            f"Newest / prior volume: {_fmt(ratio, 2)} (exhaustion rule &lt; 0.60). "
            f"Current / last two opposite-wave volume: {_fmt(confirm, 2)} "
            f"(confirmation rule &gt; 1.25).<br>"
            f"Latest wave: {_esc(evidence.get('current_direction'))}, "
            f"started {_esc(evidence.get('wave_start_date'))}."
        )
        body.append(f"""
        <tr>
          <td><strong>{_esc(row.get("symbol"))}</strong></td>
          <td>{_esc(_readable_label(row.get(verdict_key)))}</td>
          <td class="num">{_fmt(row.get(score_key), 1)}</td>
          <td class="num">{_fmt(row.get("bars_used"), 0)} / {_fmt(row.get("wave_count"), 0)}</td>
          <td>{_esc(row.get("last_bar_date"))}</td>
          <td>{evidence_html}</td>
        </tr>
        """)
    return f"""
    <section class="section">
      <h2>{_esc(title)}</h2>
      {f'<p class="note">{_esc(note)}</p>' if note else ''}
      <table>
        <thead>
          <tr>
            <th>Symbol</th><th>Screening label</th><th class="num">Score</th>
            <th class="num">Bars / waves</th><th>Last bar</th><th>Measured evidence</th>
          </tr>
        </thead>
        <tbody>{''.join(body)}</tbody>
      </table>
    </section>
    """


# Breakouts and Breakdowns are listed in full (up to this many each) rather than capped at 20 like other sections.
BREAKOUT_LIST_LIMIT = int(os.getenv("REPORT_BREAKOUT_LIST_LIMIT", "100") or 100)


def _opportunity_table(items: List[Dict[str, Any]], title: str, note: str, limit: int = 12) -> str:
    entries = sorted(items, key=lambda item: (item.get("priority", 0), item.get("symbol", "")))[:limit]
    body = "".join(
        f"<tr><td><strong>{_esc(item['symbol'])}</strong></td>"
        f"<td>{_esc(item['label'])}</td><td class='num'>{_fmt(item.get('price'), 2)}</td>"
        f"<td>{_esc(item['date'])}</td><td>{_esc(item['evidence'])}</td></tr>"
        for item in entries
    )
    return f"""<section class="section"><h2>{_esc(title)} ({len(items)})</h2>
      <p class="note">{_esc(note)}</p>
      {('<table><thead><tr><th>Symbol</th><th>Observation</th><th>Close</th><th>Bar date</th><th>Measured evidence</th></tr></thead><tbody>' + body + '</tbody></table>')
       if body else '<p class="muted">No symbols met this rule on the dated bars in this report.</p>'}
      {f'<p class="note">Showing {limit} of {len(items)} observations.</p>' if len(items) > limit else ''}
    </section>"""


def _sector_heatmap_html(rows: List[Dict[str, Any]]) -> str:
    from backend.heatmap_engine import _load_sector_lookup

    sectors: Dict[str, List[float]] = {}
    lookup = _load_sector_lookup()
    for row in rows:
        sector = (lookup.get(row.get("symbol")) or {}).get("sector")
        change = _safe_float(row.get("change_pct"))
        if sector and sector != "Unknown" and change is not None:
            sectors.setdefault(sector, []).append(change)
    entries = []
    for sector, changes in sectors.items():
        avg = sum(changes) / len(changes)
        up = sum(change > 0 for change in changes)
        down = sum(change < 0 for change in changes)
        # Colors represent the measured equal-weight return, not an
        # unverified claim about institutional sector rotation.
        color = "#c8efdb" if avg >= 0.5 else "#e7f6ec" if avg > 0 else "#fae4e4" if avg > -0.5 else "#f7caca"
        entries.append((sector, avg, len(changes), up, down, color))
    entries.sort(key=lambda item: item[1], reverse=True)
    body = "".join(
        f'<tr style="background:{color}"><td><strong>{_esc(sector)}</strong></td>'
        f'<td class="num">{avg:+.2f}%</td><td class="num">{up} / {down}</td>'
        f'<td class="num">{count}</td></tr>'
        for sector, avg, count, up, down, color in entries
    )
    return f"""<section class="section"><h2>Sector Heat Map</h2>
      <p class="note">Equal-weight average of close-to-close daily changes in the dated
      sector-classified sample. Up / down counts exclude unchanged symbols; coverage
      shows symbols with usable data. Green is positive and red is negative.</p>
      <table><thead><tr><th>Sector</th><th class="num">Average change</th>
      <th class="num">Up / down</th><th class="num">Coverage</th></tr></thead><tbody>{body}</tbody></table>
    </section>"""


def _crossing_window_html(breakouts, breakouts_new, breakouts_holding,
                          breakdowns, breakdowns_new, breakdowns_holding, report_date: str) -> str:
    """Breakout/breakdown lists from the crossing window alone (no lifecycle)."""
    def total(items, word):
        return f"{len(items)} {word}{'s' if len(items) != 1 else ''} in total"
    return (
        _opportunity_table(breakouts_new, "Breakouts: New Today", f"Closed above a multi-touch resistance level for the first time on {report_date}. {total(breakouts, 'breakout')}; the rest are listed under Still Holding. An observed crossing, not a forecast.", BREAKOUT_LIST_LIMIT)
        + _opportunity_table(breakouts_holding, "Breakouts: Still Holding", "Crossed above a multi-touch resistance level on one of the three sessions before the report date and has closed above it every session since. Sorted most recent crossing first. An observed crossing, not a forecast.", BREAKOUT_LIST_LIMIT)
        + _opportunity_table(breakdowns_new, "Breakdowns: New Today", f"Closed below a multi-touch support level for the first time on {report_date}. {total(breakdowns, 'breakdown')}; the rest are listed under Still Holding. An observed crossing, not a forecast.", BREAKOUT_LIST_LIMIT)
        + _opportunity_table(breakdowns_holding, "Breakdowns: Still Holding", "Crossed below a multi-touch support level on one of the three sessions before the report date and has closed below it every session since. Sorted most recent crossing first. An observed crossing, not a forecast.", BREAKOUT_LIST_LIMIT)
    )


def _crossing_summary_html(rows: List[Dict[str, Any]], report_date: str,
                           outs: Dict[str, Dict[str, List[Dict[str, Any]]]]) -> str:
    """Market context, counts by stage, crossings by date (clusters) and by sector."""
    spy = next((_safe_float(r.get("spy_change_pct")) for r in rows if r.get("spy_change_pct") is not None), None)
    up = sum(1 for r in rows if (_safe_float(r.get("change_pct")) or 0) > 0)
    down = sum(1 for r in rows if (_safe_float(r.get("change_pct")) or 0) < 0)
    stages = [("new", "New today"), ("confirmed", "Confirmed and holding"), ("holding", "Holding, not yet confirmed"),
              ("failed", "Failed today"), ("retry", "Failed earlier, watching for another attempt")]
    count_rows = "".join(
        f"<tr><td>{label}</td><td class='num'>{len(outs['BREAKOUT'][k])}</td><td class='num'>{len(outs['BREAKDOWN'][k])}</td></tr>"
        for k, label in stages)
    for phase, label in (("trending", "Active: trending"), ("box", "Active: pausing in a box"),
                         ("broken", "Active: trend broken"), ("sideways", "Active: sideways, trend not started")):
        n = [sum(1 for k in ("new", "confirmed", "holding") for i in outs[sig][k] if i.get("trend_phase") == phase)
             for sig in CROSSING_SIGNALS]
        count_rows += (f"<tr><td><strong>{label}</strong></td><td class='num'>{n[0]}</td>"
                       f"<td class='num'>{n[1]}</td></tr>")

    by_date: Dict[str, Dict[str, Any]] = {}
    by_sector: Dict[str, List[int]] = {}
    for signal, col in (("BREAKOUT", 0), ("BREAKDOWN", 1)):
        for k in ("new", "confirmed", "holding"):
            for i in outs[signal][k]:
                d = by_date.setdefault(i["crossed"], {"n": [0, 0], "spy": None})
                d["n"][col] += 1
                by_sector.setdefault(i["sector"], [0, 0])[col] += 1
    for row in rows:   # S&P move on each crossing date, from the stored crossing context
        for event in row.get("lifecycle") or []:
            ctx = event.get("report_context") or {}
            if ctx.get("crossed") in by_date and ctx.get("spy_crossing_change_pct") is not None:
                by_date[ctx["crossed"]]["spy"] = ctx["spy_crossing_change_pct"]
    dates = sorted(by_date, reverse=True)
    date_rows = "".join(
        f"<tr><td>{_esc(d)}</td><td class='num'>{by_date[d]['n'][0]}</td><td class='num'>{by_date[d]['n'][1]}</td>"
        f"<td class='num'>{_pct(by_date[d]['spy'])}</td></tr>" for d in dates)
    sector_rows = "".join(
        f"<tr><td>{_esc(sec)}</td><td class='num'>{n[0]}</td><td class='num'>{n[1]}</td></tr>"
        for sec, n in sorted(by_sector.items(), key=lambda kv: (-(kv[1][0] + kv[1][1]), kv[0])))
    active_bo = sum(by_date[d]["n"][0] for d in dates)
    cluster = ""
    if active_bo:
        top = max(dates, key=lambda d: by_date[d]["n"][0])
        share = by_date[top]["n"][0] / active_bo * 100
        cluster = (f"<p class='note'>Largest cluster: {by_date[top]['n'][0]} of {active_bo} active breakouts "
                   f"({share:.0f}%) crossed on {_esc(top)}, when the S&P 500 moved {_pct(by_date[top]['spy'])}. "
                   "When many crossings share one date, a market-wide move is the likely common cause, "
                   "so treat them as one event rather than independent signals.</p>")
    return f"""<section class="section"><h2>Breakouts and Breakdowns: Summary</h2>
      <p class="note">S&P 500 (SPY) on {_esc(report_date)}: {_pct(spy)}. Universe breadth: {up} up, {down} down.
      Breakouts and breakdowns are separate lists. Each is followed from the day it crossed a multi-touch
      level, with no time limit, until a daily close back through that level. A stock that only falls less
      than the market is showing relative strength, not a breakout; every entry below closed beyond its level.</p>
      <div class="grid">
        <div><table><thead><tr><th>Stage</th><th>Breakouts</th><th>Breakdowns</th></tr></thead><tbody>{count_rows}</tbody></table></div>
        <div><table><thead><tr><th>Sector (active)</th><th>Breakouts</th><th>Breakdowns</th></tr></thead><tbody>{sector_rows or "<tr><td colspan='3' class='muted'>None</td></tr>"}</tbody></table></div>
      </div>
      <table><thead><tr><th>Crossing date (active)</th><th>Breakouts</th><th>Breakdowns</th><th>S&P 500 that day</th></tr></thead>
      <tbody>{date_rows or "<tr><td colspan='4' class='muted'>None</td></tr>"}</tbody></table>
      {cluster}
      <p class="note">Each entry is named a bullish breakout or bearish breakdown with its day count (the crossing
      day is day 1) and keeps that name until a daily close back through the level. Trend shows Sideways with its day
      count until the trend gate is first crossed: close above its 10-day average, the average rising, and the 10-day change above
      +2% (for breakdowns: below a falling average and below -2%). The trend then moves in steps. When a bullish trend
      goes 3 sessions without a new high, a box opens: its top is the trend's high, its bottom the lowest low since,
      fixed after 3 sessions without a new low. The box extends while closes stay inside it. A close above the top is
      the next step; a close below the fixed bottom breaks the trend until the gate is crossed again (trend 2).
      Breakdowns mirror this. Pivots lists the current and prior box edges as resistance (R) and support (S).</p>
      <p class="note">Columns in the lists below: Today (vs S&P) is the day's change and its difference from the
      S&P 500; Crossing day vs S&P is the stock's move on the day it crossed minus the S&P 500's; Beyond level is
      how far the close is past the level in the break's direction; Since crossing (best) is the move from the
      crossing close in the break's direction, with the best close so far; Crossing-day volume is volume on the
      crossing day against its 20-day average; 4-hour is Aligned when the latest completed 4-hour close is past the
      level and on the break's side of its 20-bar average, Against when neither, Mixed otherwise.</p>
    </section>"""


def _lifecycle_sections_html(rows: List[Dict[str, Any]], report_date: str) -> str:
    """Breakouts and breakdowns followed with the Weis Radar lifecycle engine."""
    outs = {sig: _lifecycle_sections(rows, report_date, sig) for sig in CROSSING_SIGNALS}
    parts = [_crossing_summary_html(rows, report_date, outs)]
    for signal, plural, side, level_word, extreme in (("BREAKOUT", "Breakouts", "above", "resistance", "high"),
                                                      ("BREAKDOWN", "Breakdowns", "below", "support", "low")):
        back = "below" if side == "above" else "above"
        sec = outs[signal]
        parts += [
            _crossing_table(sec["new"], f"{plural}: New Today",
                            f"Closed {side} a multi-touch {level_word} level on {report_date}. Confirms on a later close "
                            f"beyond the crossing day's {extreme}. An observed crossing, not a forecast.", BREAKOUT_LIST_LIMIT),
            _crossing_table(sec["confirmed"], f"{plural}: Confirmed and Holding",
                            f"A later close went beyond the crossing day's {extreme}, and every close since has stayed {side} "
                            "the level. Still watched, with no time limit, until a close back through the level.", BREAKOUT_LIST_LIMIT),
            _crossing_table(sec["holding"], f"{plural}: Holding, Not Yet Confirmed",
                            f"Still closing {side} the level, but no close beyond the crossing day's {extreme} yet "
                            "(moving sideways). Watched with no time limit.", BREAKOUT_LIST_LIMIT),
            _crossing_table(sec["failed"], f"{plural}: Failed Today",
                            f"Closed back {back} the level on {report_date}, ending this attempt. It moves to the "
                            "watch list below in the next report.", BREAKOUT_LIST_LIMIT),
            _crossing_table(sec["retry"], f"{plural}: Failed Earlier, Watching for Another Attempt",
                            f"Earlier attempts that closed back {back} their level. Each stays listed, with no time limit, "
                            "until the same level is crossed again; that new crossing appears above as the next numbered attempt. "
                            "Beyond level is negative while price is back on the wrong side.", BREAKOUT_LIST_LIMIT),
        ]
    return "".join(parts)


def build_report_html(report_date_str: str) -> str:
    """One dated daily-bar snapshot; fail rather than mislabel cached or old bars."""
    from backend.heatmap_engine import _load_sector_lookup

    report_date = datetime.strptime(report_date_str, "%Y-%m-%d").date().isoformat()
    observed = _run_full_universe_renko_weis_scan()
    latest_dates = [r.get("last_bar_date") for r in observed if r.get("last_bar_date")]
    if not latest_dates:
        raise ValueError("No dated daily bars were returned; no report or subscriber email was generated")
    latest_date = max(latest_dates)
    if latest_date != report_date:
        raise ValueError(f"Requested report date {report_date} differs from latest market bar {latest_date}; no report emailed")
    rows = [r for r in observed if r.get("last_bar_date") == report_date]
    excluded = len(observed) - len(rows)
    display_date = datetime.strptime(report_date, "%Y-%m-%d").strftime("%B %d, %Y")
    worker_commit = os.getenv("RENDER_GIT_COMMIT") or "unavailable (check worker deployment)"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    universe_size = len(_load_sector_lookup())
    if len(rows) < max(1, int(0.70 * universe_size)):
        raise ValueError(f"Only {len(rows)} of {universe_size} sector-universe symbols have current bars; report withheld")

    confirmed, setups, exhaustion, climaxes = [], [], [], []
    for row in rows:
        symbol, price = row.get("symbol", ""), row.get("price")
        for event in row.get("events") or []:
            kind = event.get("type", "")
            event_date = event.get("date") or report_date
            level = _fmt(event.get("level"), 2)
            detail = f"Level {level}"
            if kind in ("BREAKOUT", "BREAKDOWN"):
                detail += f"; close {abs(float(event.get('pct_beyond') or 0)):.2f}% beyond; "
                detail += f"crossed {event_date}; held to latest close"
            else:
                detail += f"; existing multi-touch level; detector score {_fmt(event.get('score'), 0)}"
            confirmed.append(dict(symbol=symbol, price=price, date=report_date,
                                  label=_readable_label(kind), evidence=detail,
                                  priority=int(event.get("days_back", 0))))
        if not row.get("events"):
            for setup in row.get("setups") or []:
                setups.append(dict(symbol=symbol, price=price, date=report_date,
                                   label=setup["side"], priority=setup["distance_pct"],
                                   evidence=f"Close {_fmt(setup['distance_pct'], 2)}% from multi-touch level "
                                            f"{_fmt(setup['level'], 2)}; no crossing detected"))
        for bearish, field, label in ((False, "volume_exhaustion", "Selling exhaustion"),
                                      (True, "buying_exhaustion", "Buying exhaustion")):
            if (row.get(field) or 0) >= 100:
                evidence = row.get("bearish_evidence" if bearish else "bullish_evidence") or {}
                ratio = evidence.get("exhaustion_ratio")
                price_steps = " / ".join(_fmt(p, 2) for p in evidence.get("progress") or [])
                wave_volumes = " / ".join(_fmt(v, 0) for v in evidence.get("volumes") or [])
                exhaustion.append(dict(symbol=symbol, price=price, date=report_date,
                                       label=label, priority=ratio if ratio is not None else 1,
                                       evidence=f"Three comparable wave price moves: {price_steps}; "
                                                f"estimated volumes: {wave_volumes}. "
                                                f"Latest / prior volume {_fmt(ratio, 2)} (rule < 0.60); "
                                                f"current wave {evidence.get('current_direction') or 'unknown'}"))
        for climax in row.get("climaxes") or []:
            detail = row.get("climax_evidence") or {}
            climaxes.append(dict(symbol=symbol, price=price, date=report_date,
                                 label="Buying climax" if climax == "CLIMAX_BUY" else "Selling climax",
                                 evidence=f"Time-bar wave volume {_fmt(detail.get('current_volume'), 0)} vs "
                                          f"prior {_fmt(detail.get('prior_volume'), 0)}; price progress "
                                          f"{_fmt(detail.get('current_progress'), 2)} vs "
                                          f"prior {_fmt(detail.get('prior_progress'), 2)}"))

    # Breakouts and breakdowns get their own full lists; springs and upthrusts keep the shared section.
    breakouts = [i for i in confirmed if i["label"] == "Breakout"]
    breakdowns = [i for i in confirmed if i["label"] == "Breakdown"]
    # Split each list by when the level was crossed: on the report's own bar
    # (priority = days_back = 0) or on one of the three sessions before it and
    # still held. A long "Breakouts" list on a down day is usually mostly the
    # second kind, which a single combined count hides.
    breakouts_new = [i for i in breakouts if i.get("priority", 0) == 0]
    breakouts_holding = [i for i in breakouts if i.get("priority", 0) > 0]
    breakdowns_new = [i for i in breakdowns if i.get("priority", 0) == 0]
    breakdowns_holding = [i for i in breakdowns if i.get("priority", 0) > 0]
    if any("lifecycle" in row for row in rows):
        crossing_html = _lifecycle_sections_html(rows, report_date)
    else:  # scan output without lifecycle tracking (older data): crossing-window lists
        crossing_html = _crossing_window_html(breakouts, breakouts_new, breakouts_holding,
                                              breakdowns, breakdowns_new, breakdowns_holding, report_date)
    reversals = [i for i in confirmed if i["label"] not in ("Breakout", "Breakdown")]
    movers_html = _movers_table(_market_movers_from_scanned_rows(rows))
    html_doc = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{_esc(REPORT_TITLE)} - {_esc(display_date)}</title>
  <style>{_CSS}</style>
</head>
<body>
  <div class="page">
    <div class="cover">
      <h1><span class="sigma">&Sigma;</span> SIGMALYTIC</h1>
      <div class="corp-subtitle">QUANT CORPORATION</div>
      <div class="subtitle">Observed setups, completed-bar events, wave-volume readings, and sector movement</div>
      <div class="meta">
        <div class="label">Data through</div><div>{_esc(display_date)} (latest completed daily bar)</div>
        <div class="label">Generated</div><div>{generated_at}</div>
        <div class="label">Market data</div><div>Alpaca daily stock bars, feed {_esc(os.getenv('ALPACA_FEED', 'iex'))}, corporate-action adjustment all, up to 252 bars per symbol</div>
        <div class="label">Actual scoring engines</div><div>Sigmalytic Quant Algorithm.
          No legacy campaign/ODS or user-selected radar timeframe.</div>
        <div class="label">Worker code revision</div><div>{_esc(worker_commit)}</div>
      </div>
    </div>
    <section class="section">
      <h2>Market Overview</h2>
      <p>{len(rows)} of {universe_size} sector-classified symbols had usable completed bars for
      {report_date}. {excluded} otherwise usable symbol(s) were excluded because their bars ended
      on a different date. Sections can overlap: a symbol can meet multiple independent rules.</p>
      <div class="summary">
        <div class="metric"><div class="num">{len(rows)}</div><div class="txt">Dated symbols</div></div>
        <div class="metric"><div class="num">{len(set(i['symbol'] for i in setups))}</div><div class="txt">Near tested levels</div></div>
        <div class="metric"><div class="num">{len(set(i['symbol'] for i in confirmed))}</div><div class="txt">Observed events</div></div>
        <div class="metric"><div class="num">{len(set(i['symbol'] for i in exhaustion + climaxes))}</div><div class="txt">Wave-volume flags</div></div>
      </div>
    </section>
    {_sector_heatmap_html(rows)}
    {_opportunity_table(setups, "Setting Up: Near Tested Levels", "Close is within 2% of a multi-touch support or resistance level without a confirmed crossing. A watch condition, not a trade trigger.", 15)}
    {crossing_html}
    {_opportunity_table(reversals, "Observed Springs and Upthrusts", "Detector rules met on completed daily bars: a spring dips below support and recovers; an upthrust pushes above resistance and fails. This does not validate subsequent performance.", 20)}
    {_opportunity_table(exhaustion, "Buying and Selling Exhaustion", "Renko-Weis screening rule: shrinking volume on comparable waves after three progressively shorter thrusts. Approximate volume is apportioned across Renko bricks.", 15)}
    {_opportunity_table(climaxes, "Buying and Selling Climaxes", "Existing daily time-bar Weis Radar rule: current wave volume > 2x previous wave, while its price progress < half the previous wave. Rules describe observed volume and price, not a future move.", 15)}
    {movers_html}
    <section class="section"><h2>How to Read This Report</h2>
      <p>All observations use the dated bars shown above. "Setting up" means proximity
      to a tested level; "observed event" means a programmed condition was met.
      A Renko-Weis score is a binary screening heuristic, not a success probability.
      The sections are not ranked by forecast return and have not been independently
      validated here as profitable trading signals.</p></section>

    <div class="footer">
      {_esc(COPYRIGHT)}<br>
      Sigmalytic Quant Corporation | Dated Market Intelligence | Daily Intelligence Report
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
        report_date_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

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
                    json={"from": os.environ.get("ALERT_FROM_EMAIL", "alerts@sigmalyticquantcorp.com"),
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
                detail = ""
                if isinstance(exc, requests.HTTPError) and exc.response is not None:
                    try:
                        provider_error = exc.response.json()
                        if isinstance(provider_error, dict):
                            name = str(provider_error.get("name", ""))[:60]
                            message = str(provider_error.get("message", ""))[:240]
                            detail = f"; Resend {name}: {message}"
                    except (ValueError, TypeError):
                        pass
                print(f"[REPORT_EMAIL] Delivery failed for report {report_date_str}: {exc}{detail}", flush=True)
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


# ── Daily report -> Content Hub (Admin) ─────────────────────────────────────
_SECTION_RE = re.compile(r"<h2>(.*?)</h2>(.*?)(?=<h2>|</body>)", re.S)
_ROW_RE = re.compile(r"<tr>\s*<td><strong>([^<]+)</strong></td>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def symbols_from_report_html(html_doc: str) -> List[Dict[str, Any]]:
    """
    Sections of a stored daily report that list symbols, in report order:
    [{"title": "...", "symbols": [{"symbol": "AAPL", "detail": "Selling exhaustion", "price": "231.40"}]}].
    Reads the saved HTML, so it works for every archived report without regenerating it.
    """
    out: List[Dict[str, Any]] = []
    for title, body in _SECTION_RE.findall(html_doc or ""):
        seen, syms = set(), []
        for sym, rest in _ROW_RE.findall(body):
            sym = html.unescape(sym).strip().upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", sym) or sym in seen:
                continue
            seen.add(sym)
            cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in _CELL_RE.findall(rest)]
            if cells and re.fullmatch(r"[-\d.,]+|—", cells[0]):        # movers table: price, change %
                detail, price = (cells[1] if len(cells) > 1 else ""), cells[0]
            else:                                                     # opportunity tables: observation, close
                detail, price = (cells[0] if cells else ""), (cells[1] if len(cells) > 1 else "")
            syms.append({"symbol": sym, "detail": detail, "price": price})
        if syms:
            out.append({"title": html.unescape(re.sub(r"<[^>]+>", "", title)).strip(), "symbols": syms})
    return out


def report_symbols(report_date_str: Optional[str] = None) -> Dict[str, Any]:
    """Symbols in one stored report (the newest when no date is given), plus recent report dates for a picker."""
    catalog = report_catalog()
    dates = catalog.get("dates") or []
    date = report_date_str or (dates[0] if dates else None)
    if not date:
        return {"ok": False, "error": catalog.get("error") or "No stored daily reports found.", "dates": []}
    html_doc = get_report_html(date)
    if not html_doc:
        return {"ok": False, "error": f"No stored report for {date}.", "dates": dates[:60]}
    return {"ok": True, "date": date, "dates": dates[:60], "sections": symbols_from_report_html(html_doc)}
