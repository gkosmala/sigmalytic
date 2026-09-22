"""
ADDED (2026-08-24): Weis Radar -- scans the full Russell 1000 using
the operator's saved signal, timeframe, lookback, and alert settings.
The eleven available signals reuse the shared, live-tested Weis/Wyckoff
calculation in backend/radar_service.py. Genuinely separate from the existing
"Radar" tab's own composite scoring (get_radar_scores in
radar_service.py) -- deliberately additive, not integrated into that
system, so this carries zero risk to the existing, already-working
Radar/Market Radio/report pipeline.

Same architecture already proven for report generation earlier this
session: runs entirely on the isolated worker process (never the web
backend), on the saved timeframe's schedule, results cached in Redis
for the frontend to read. Fetches bounded 25-symbol chunks with
fetch_bars_batch() and reuses compute_symbol_signals(), the same
calculation used by the live signal-test endpoint.
"""
import json
from datetime import datetime, timezone

import pandas as pd

WEIS_RADAR_RESULTS_KEY = "weis_radar:results"
WEIS_RADAR_JOB_KEY = "weis_radar:job_status"
WEIS_RADAR_JOB_TTL_SECONDS = 3600
WEIS_RADAR_MANUAL_QUEUE_KEY = "weis_radar:manual_scan_queue"
RADAR_CONFIG_REDIS_KEY = "radar:signal_config"

RADAR_CONFIG_DEFAULTS = {
    "display_signals": ["spring", "upthrust", "climaxup", "climaxdown", "3bar"],
    "timeframe": "1Day",
    "lookback": 252,
    "alert_signals": [],
    "sms_enabled": False,
    "email_enabled": False,
}

VALID_SIGNALS = {
    "spring", "upthrust", "climaxup", "climaxdown", "3bar",
    "absorption", "distribution", "sign_of_strength", "sign_of_weakness",
    "breakout", "breakdown",
}
VALID_TIMEFRAMES = {
    "1Min", "5Min", "15Min", "30Min",
    "1Hour", "2Hour", "4Hour", "1Day", "1Week",
}

# Full-universe scans retain one batch's raw bar dictionaries in memory at a
# time. Intraday remains deliberately bounded because those scans can run as
# often as once per minute; daily and weekly history can be meaningfully wider.
RADAR_LOOKBACK_LIMITS = {
    "1Min": 500,
    "5Min": 500,
    "15Min": 500,
    "30Min": 500,
    "1Hour": 5292,  # 7 bars/session * 252 sessions * 3 years
    "2Hour": 3024,  # 4 bars/session * 252 sessions * 3 years
    "4Hour": 1512,  # 2 bars/session * 252 sessions * 3 years
    "1Day": 2520,   # approximately 10 trading years
    "1Week": 1040,  # approximately 20 years
}
WEIS_RADAR_SCAN_CHUNK_SIZE = 25


def _load_radar_config(redis_client) -> dict:
    """Load and defensively normalize the shared admin configuration."""
    config = dict(RADAR_CONFIG_DEFAULTS)
    if redis_client:
        try:
            raw = redis_client.get(RADAR_CONFIG_REDIS_KEY)
            if raw:
                decoded = json.loads(raw)
                if isinstance(decoded, dict):
                    config.update(decoded)
        except Exception:
            pass

    display_signals = [
        str(signal).lower() for signal in (config.get("display_signals") or [])
        if str(signal).lower() in VALID_SIGNALS
    ]
    if not display_signals:
        display_signals = list(RADAR_CONFIG_DEFAULTS["display_signals"])

    alert_signals = [
        str(signal).lower() for signal in (config.get("alert_signals") or [])
        if str(signal).lower() in display_signals
    ]
    timeframe = str(config.get("timeframe") or RADAR_CONFIG_DEFAULTS["timeframe"])
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = RADAR_CONFIG_DEFAULTS["timeframe"]
    try:
        lookback_max = RADAR_LOOKBACK_LIMITS[timeframe]
        lookback = max(10, min(lookback_max, int(config.get("lookback") or 252)))
    except Exception:
        lookback = RADAR_CONFIG_DEFAULTS["lookback"]

    return {
        "display_signals": display_signals,
        "timeframe": timeframe,
        "lookback": lookback,
        "alert_signals": alert_signals,
        "sms_enabled": bool(config.get("sms_enabled", False)),
        "email_enabled": bool(config.get("email_enabled", False)),
    }


def _configured_signal_key(signal_name: str) -> str:
    """Map an engine result label back to the saved configuration key."""
    signal = str(signal_name or "").upper()
    if signal.startswith("3BAR_"):
        return "3bar"
    if signal == "CLIMAX_BUY":
        return "climaxup"
    if signal == "CLIMAX_SELL":
        return "climaxdown"
    if signal.startswith("NO_SUPPLY"):
        return "absorption"
    if signal.startswith("NO_DEMAND"):
        return "distribution"
    return {
        "SPRING": "spring",
        "UPTHRUST": "upthrust",
        "SIGN_OF_STRENGTH": "sign_of_strength",
        "SIGN_OF_WEAKNESS": "sign_of_weakness",
        "BREAKOUT": "breakout",
        "BREAKDOWN": "breakdown",
    }.get(signal, "")


def _normalize_signal_hits(found: list, price: float) -> list:
    """Convert the shared 11-signal engine output to Weis Radar rows."""
    hits = []
    for item in found:
        signal = str(item.get("signal") or "")
        if not signal or signal == "WYCKOFF_ENGINE_ERROR":
            continue
        hit = {"type": signal, "price": round(float(price), 2)}
        if item.get("score") is not None:
            hit["score"] = round(float(item["score"]), 1)
        if isinstance(item.get("detail"), dict):
            hit.update(item["detail"])
        hits.append(hit)
    return hits


def _dispatch_configured_alerts(results: list, config: dict, redis_client) -> int:
    """Send deduplicated operator alerts for the configured signal subset."""
    if not redis_client or not config.get("alert_signals"):
        return 0
    if not config.get("email_enabled") and not config.get("sms_enabled"):
        return 0

    requested = set(config["alert_signals"])
    dispatched = 0
    for row in results:
        symbol = row.get("symbol", "")
        bar_time = str(row.get("last_bar_time") or "unknown")
        for hit in row.get("hits", []):
            signal_key = _configured_signal_key(hit.get("type"))
            if signal_key not in requested:
                continue

            dedupe_key = f"weis_radar:alerted:{symbol}:{signal_key}:{bar_time}"
            try:
                if not redis_client.set(dedupe_key, "1", nx=True, ex=7 * 24 * 60 * 60):
                    continue
            except Exception:
                continue

            signal_label = str(hit.get("type") or signal_key).replace("_", " ")
            price = float(hit.get("price") or 0)
            score = float(hit.get("score") or 0)
            detail = f"{symbol} produced {signal_label} at ${price:,.2f}"
            if score:
                detail += f" with score {score:.0f}"
            detail += f" on the {config['timeframe']} scan."

            if config.get("email_enabled"):
                try:
                    from backend.email_service import send_admin_alert_sync
                    send_admin_alert_sync(
                        f"Weis Radar: {symbol} {signal_label}",
                        detail,
                        alert_key=dedupe_key,
                    )
                except Exception:
                    pass
            if config.get("sms_enabled"):
                try:
                    from backend.sms_alerts import send_signal_sms
                    send_signal_sms(symbol, signal_label, price=price, score=score)
                except Exception:
                    pass
            dispatched += 1
    return dispatched


def request_manual_weis_radar_scan() -> dict:
    """
    ADDED (2026-08-24): admin-triggered "run now" -- same queue
    pattern already proven for report generation (start_report_
    generation_job in reports_engine.py). Called from a new admin-
    only endpoint; just enqueues and sets status immediately, never
    runs the actual scan inline here -- same OOM lesson as everything
    else this session, the real work only ever happens on the
    isolated worker process, via process_one_pending_weis_radar_scan().
    """
    from backend.radar_service import _redis_client
    if not _redis_client:
        return {"ok": False, "error": "Redis not configured"}
    try:
        _redis_client.set(WEIS_RADAR_JOB_KEY, json.dumps({
            "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
        }), ex=WEIS_RADAR_JOB_TTL_SECONDS)
        _redis_client.lpush(WEIS_RADAR_MANUAL_QUEUE_KEY, "1")
        return {"ok": True, "status": "started"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def process_one_pending_weis_radar_scan() -> bool:
    """
    Called periodically by the worker's own polling loop (same 15s
    cadence already used for report-generation requests). Pops at
    most one pending manual scan request and runs the real scan if
    found. Returns True if a request was found and processed.
    """
    from backend.radar_service import _redis_client
    if not _redis_client:
        return False
    try:
        request = _redis_client.rpop(WEIS_RADAR_MANUAL_QUEUE_KEY)
    except Exception:
        return False
    if not request:
        return False
    run_weis_radar_scan()
    return True


def get_weis_radar_job_status() -> dict:
    """Read-only -- lets the frontend poll for progress after a manual
    trigger, same pattern as Reports' own status polling."""
    from backend.radar_service import _redis_client
    if not _redis_client:
        return {"status": "unknown"}
    try:
        raw = _redis_client.get(WEIS_RADAR_JOB_KEY)
        return json.loads(raw) if raw else {"status": "unknown"}
    except Exception:
        return {"status": "unknown"}


def _bars_to_dataframe(raw_bars: list, keep_time: bool = False) -> pd.DataFrame:
    """
    Same conversion already used by the live single-symbol
    wyckoff-verdict endpoint -- Alpaca's own o/h/l/c/v field names.

    FIX (2026-08-24): confirmed a real bug -- previously dropped
    Alpaca's own timestamp field ("t") entirely, so the resulting
    DataFrame had only a default 0,1,2... integer index. _scan_for_
    crossing()'s "date" field then read that raw row number (e.g.
    "236") instead of an actual date -- exactly the "crossed 236"
    output reported live. Now keeps the real date, sliced to just the
    calendar date portion of Alpaca's ISO timestamp.

    ADDED (2026-08-26): keep_time=True preserves the full timestamp
    instead of slicing to just the date -- needed once the chart
    endpoint (backend/main.py) became timeframe-selectable, since
    multiple intraday bars share the same calendar date and would
    otherwise collapse to identical, indistinguishable "date" values.
    Defaults to False (unchanged, date-only) so the full-universe
    daily-only scan's own call site (this same file, below) needs no
    changes and its existing table-display formatting is unaffected.
    """
    return pd.DataFrame([
        {"open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"],
         "date": str(b.get("t", "")) if keep_time else str(b.get("t", ""))[:10]}
        for b in raw_bars
    ])


def scan_symbol_for_weis_patterns(engine, df: pd.DataFrame) -> list:
    """
    Runs all four pattern checks on one symbol's already-prepared
    DataFrame, returning a list of hit dicts (empty if none). Mirrors
    the exact logic already validated in the standalone Weis scan
    tool this session -- same thresholds (spring/upthrust >= 70),
    same well-defined-level requirement.

    ADDED (2026-08-25): also checks for a "building" Spring/Upthrust
    -- see WyckoffVerdictEngine.check_building_pattern() for the full
    reasoning -- but only during actual market hours, when the most
    recent bar is genuinely still forming. Reuses the same
    _is_market_hours() already established in backend/
    scoreboard_service.py for consistency.
    """
    if len(df) < 60:
        return []
    df = engine._prepare(df)
    idx = len(df) - 1

    support = engine._find_well_defined_level(df, idx, is_support=True)
    resistance = engine._find_well_defined_level(df, idx, is_support=False)
    spring = engine._score_spring(df, idx, support)
    upthrust = engine._score_upthrust(df, idx, resistance, trend_context="neutral")
    breakout = engine.detect_breakout(df, idx, resistance)
    breakdown = engine.detect_breakdown(df, idx, support)

    hits = []
    price = float(df["close"].iloc[idx])
    if spring >= 70:
        hits.append({"type": "SPRING", "score": spring, "level": round(float(support), 2)})
    if upthrust >= 70:
        hits.append({"type": "UPTHRUST", "score": upthrust, "level": round(float(resistance), 2)})
    if breakout:
        hits.append({"type": "BREAKOUT", **breakout})
    if breakdown:
        hits.append({"type": "BREAKDOWN", **breakdown})

    if spring < 70 and upthrust < 70:
        try:
            from backend.scoreboard_service import _is_market_hours
            market_open_now = _is_market_hours()
        except Exception:
            market_open_now = False
        # FIX (2026-08-25): confirmed a real, systematic bug via live
        # scan data -- check_building_pattern() only checked "is
        # today's low below support," which is ALSO true every single
        # day an already-confirmed, already-resolved Breakdown
        # continues (a stock sitting 20 days below a level it broke
        # weeks ago isn't "building" a Spring -- nothing is attempting
        # to reverse). This produced SPRING_BUILDING on nearly every
        # symbol that already had a confirmed BREAKDOWN, always at the
        # exact same level, and the mirror-image bug for UPTHRUST_
        # BUILDING/BREAKOUT. Now explicitly skipped whenever the
        # corresponding confirmed pattern already exists at this
        # level -- "building" is reserved for a level being tested
        # right now, not one whose test was already resolved.
        if market_open_now and not breakdown and not breakout:
            building = engine.check_building_pattern(df, idx, support, resistance)
            if building == "SPRING_BUILDING":
                hits.append({"type": "SPRING_BUILDING", "level": round(float(support), 2)})
            elif building == "UPTHRUST_BUILDING":
                hits.append({"type": "UPTHRUST_BUILDING", "level": round(float(resistance), 2)})

    return [{"price": round(price, 2), **h} for h in hits] if hits else []


def run_weis_radar_scan() -> dict:
    """
    The actual full-universe scan -- called from the worker's own
    scheduled job, never from the web backend. Real, meaningful
    compute cost (1,023 symbols), same lesson as the report generation
    fix earlier this session: this must never run on the web-facing
    process's memory budget.
    """
    from backend.radar_service import (
        _redis_client,
        compute_symbol_signals,
        fetch_bars_batch,
        load_russell1000,
        min_bars_required_for,
        trim_incomplete_bar,
    )
    from backend.research_engine.wyckoff_verdict_engine import WyckoffVerdictEngine
    from backend.weis_radar_lifecycle import WeisRadarLifecycleTracker

    started_at = datetime.now(timezone.utc).isoformat()
    if _redis_client:
        try:
            _redis_client.set(WEIS_RADAR_JOB_KEY, json.dumps({"status": "running", "started_at": started_at}),
                               ex=WEIS_RADAR_JOB_TTL_SECONDS)
        except Exception:
            pass

    config = _load_radar_config(_redis_client)
    requested_signals = set(config["display_signals"])
    minimum_bars = min_bars_required_for(requested_signals)
    effective_lookback = max(config["lookback"], minimum_bars)

    engine = WyckoffVerdictEngine()
    lifecycle = WeisRadarLifecycleTracker(
        _redis_client,
        timeframe=config["timeframe"],
        scan_id=started_at,
    )
    symbols = load_russell1000()
    results = []
    errors = 0
    scanned = 0

    # Process the universe in bounded chunks. Previously one fetch retained
    # every symbol's complete history at once: 2,520 daily bars across roughly
    # 1,000 symbols meant more than 2.5 million Python dictionaries resident at
    # the same time. Keeping only 25 symbols' bars live makes long daily/weekly
    # lookbacks practical without moving that memory pressure to the web app.
    for chunk_start in range(0, len(symbols), WEIS_RADAR_SCAN_CHUNK_SIZE):
        symbol_chunk = symbols[chunk_start:chunk_start + WEIS_RADAR_SCAN_CHUNK_SIZE]
        bars_map = fetch_bars_batch(
            symbol_chunk,
            timeframe=config["timeframe"],
            limit=effective_lookback + 1,
            min_bars_floor=minimum_bars,
        )
        scanned += len(bars_map)

        for symbol, raw_bars in bars_map.items():
            try:
                bars = trim_incomplete_bar(raw_bars, config["timeframe"])
                if len(bars) < minimum_bars:
                    errors += 1
                    continue
                found = compute_symbol_signals(
                    symbol,
                    bars,
                    requested_signals,
                    config["timeframe"],
                    wyckoff_engine=engine,
                )
                hits = _normalize_signal_hits(found, bars[-1]["c"])

                # Persist and evaluate lifecycle state on the SAME completed
                # bars already fetched for the universe scan. No second market
                # data request is introduced here.
                lifecycle.process_symbol(symbol, bars, hits)

                if hits:
                    results.append({
                        "symbol": symbol,
                        "hits": hits,
                        "last_bar_time": bars[-1].get("t"),
                    })
            except Exception:
                errors += 1

        if _redis_client:
            try:
                _redis_client.set(WEIS_RADAR_JOB_KEY, json.dumps({
                    "status": "running",
                    "started_at": started_at,
                    "processed": min(chunk_start + len(symbol_chunk), len(symbols)),
                    "total_symbols": len(symbols),
                    "scanned": scanned,
                    "errors": errors,
                }), ex=WEIS_RADAR_JOB_TTL_SECONDS)
            except Exception:
                pass

    lifecycle_snapshot = lifecycle.save()
    results.sort(key=lambda r: len(r["hits"]), reverse=True)
    alerts_dispatched = _dispatch_configured_alerts(results, config, _redis_client)
    payload = {
        "ok": True,
        "scanned": scanned,
        "hits": len(results),
        "errors": errors,
        "alerts_dispatched": alerts_dispatched,
        "config": {**config, "effective_lookback": effective_lookback},
        "results": results,
        "lifecycle": lifecycle_snapshot,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    if _redis_client:
        try:
            _redis_client.set(WEIS_RADAR_RESULTS_KEY, json.dumps(payload))
            _redis_client.set(WEIS_RADAR_JOB_KEY, json.dumps({
                "status": "done", "started_at": started_at,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "hits": len(results), "scanned": scanned, "errors": errors,
                "alerts_dispatched": alerts_dispatched,
            }), ex=WEIS_RADAR_JOB_TTL_SECONDS)
        except Exception:
            pass

    return payload


def get_weis_radar_results() -> dict:
    """Read-only -- called from the web backend's own API endpoint to
    serve whatever the worker's last scan produced. Never runs the
    scan itself."""
    from backend.radar_service import _redis_client

    if not _redis_client:
        return {"ok": False, "error": "Redis not configured"}
    try:
        raw = _redis_client.get(WEIS_RADAR_RESULTS_KEY)
        if raw is None:
            return {"ok": True, "results": [], "generated_at": None,
                     "note": "No scan has completed yet."}
        payload = json.loads(raw)
        # Backward-compatible: a cached scan created before lifecycle support
        # still receives the currently persisted lifecycle snapshot.
        if "lifecycle" not in payload:
            from backend.weis_radar_lifecycle import get_lifecycle_snapshot
            payload["lifecycle"] = get_lifecycle_snapshot(_redis_client)
        return payload
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}
