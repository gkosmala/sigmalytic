"""
SAVE AS:
backend/main.py
"""

from fastapi import FastAPI, Body
from datetime import datetime
import os
import requests

from backend.campaign_api import router as campaign_router
from backend.research_api import router as research_router
from backend.intelligence_api import router as intelligence_router
from backend.operator_dominance.operator_dominance_api import router as operator_router

try:
    from backend.admin_api import router as admin_router
except Exception:
    admin_router = None


try:
    from backend.snapshot_service import snapshot_router
except Exception:
    snapshot_router = None

app = FastAPI(
    title="Sigmalytic V2",
    version="2.0.0",
)


@app.get("/")
def root():
    return {
        "application": "Sigmalytic V2",
        "status": "online",
        "version": "2.0.0",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.get("/api/health")
def api_health():
    return {"status": "healthy"}




@app.get("/api/stock/{symbol}")
def get_stock_quote(symbol: str):
    """
    Live stock quote endpoint for frontend chart.

    Policy:
    - Alpaca SIP only.
    - No IEX fallback.
    - No synthetic fallback.
    - Does not import radar_service.
    - Does not touch campaign logic.
    """
    sym = (symbol or "").upper().strip()

    if not sym:
        return {
            "ok": False,
            "error": "missing_symbol",
            "source": "none",
            "feed": "sip",
        }

    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")

    if not key or not secret:
        return {
            "ok": False,
            "symbol": sym,
            "error": "missing_alpaca_credentials",
            "source": "alpaca",
            "feed": "sip",
        }

    url = f"{base_url}/v2/stocks/bars/latest"

    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }

    params = {
        "symbols": sym,
        "feed": "sip",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)

        if not r.ok:
            return {
                "ok": False,
                "symbol": sym,
                "error": f"alpaca_sip_http_{r.status_code}",
                "detail": r.text[:300],
                "source": "alpaca",
                "feed": "sip",
            }

        payload = r.json() or {}
        bars = payload.get("bars") or {}
        bar = bars.get(sym)

        if not bar:
            return {
                "ok": False,
                "symbol": sym,
                "error": "no_sip_latest_bar_returned",
                "source": "alpaca",
                "feed": "sip",
            }

        price = bar.get("c")
        volume = bar.get("v")

        if price is None:
            return {
                "ok": False,
                "symbol": sym,
                "error": "sip_bar_missing_close",
                "source": "alpaca",
                "feed": "sip",
            }

        return {
            "ok": True,
            "symbol": sym,
            "price": float(price),
            "volume": int(volume or 0),
            "timestamp": bar.get("t"),
            "source": "alpaca",
            "feed": "sip",
        }

    except Exception as exc:
        return {
            "ok": False,
            "symbol": sym,
            "error": str(exc)[:300],
            "source": "alpaca",
            "feed": "sip",
        }




@app.get("/api/behavior/open-trade/{user_id}")
def get_open_trade(user_id: str):
    """
    Safe placeholder for Command Center active-trade lookup.

    Returns an empty object when no active trade is open.
    This prevents repeated 404 logs without touching campaigns, SIP, Admin, Radar, or scoring.
    """
    return {}


@app.get("/api/admin/engine-status")
def engine_status():
    return {
        "signal_birth_engine": True,
        "wyckoff_verdict_engine": True,
        "livermore_verdict_engine": True,
        "weis_verdict_engine": True,
        "master_campaign_index": True,
        "campaign_pipeline": True,
        "ods_engine": True,
        "analog_engine": True,
        "decay_monitor": True,
        "state_transition": True,
        "campaign_outcome": True,
        "campaign_closure_engine": True,
        "portfolio_intelligence": True,
        "wyckoff_engine": True,
        "gann_engine": True,
        "bme_engine": True,
        "sizing_engine": True,
        "subscriber_alerts": True,
        "campaign_api": True,
        "research_api": True,
        "portfolio_api": True,
        "journal_api": True,
    }


@app.post("/api/admin/run-full-nightly")
def run_full_nightly(payload: dict = Body(default=None)):
    payload = payload or {}

    requested_symbols = (
        payload.get("symbols")
        or payload.get("tickers")
        or payload.get("symbol")
        or []
    )

    if isinstance(requested_symbols, str):
        requested_symbols = [
            item.strip().upper()
            for item in requested_symbols.split(",")
            if item.strip()
        ]

    run_kwargs = {}

    if requested_symbols:
        run_kwargs["symbols"] = requested_symbols

    if payload.get("max_symbols") is not None:
        run_kwargs["max_symbols"] = payload.get("max_symbols")

    if payload.get("bar_limit") is not None:
        run_kwargs["bar_limit"] = payload.get("bar_limit")

    if payload.get("timeframe") is not None:
        run_kwargs["timeframe"] = payload.get("timeframe")

    results = {
        "ok": True,
        "started_at": datetime.utcnow().isoformat(),
        "request": {
            "symbols": requested_symbols,
            "max_symbols": payload.get("max_symbols"),
            "bar_limit": payload.get("bar_limit"),
            "timeframe": payload.get("timeframe"),
        },
        "steps": {},
    }

    try:
        from backend.campaign_engine import nightly_campaign_pipeline as pipeline

        runner = None

        for name in [
            "run_nightly_campaign_pipeline",
            "run_campaign_pipeline",
            "run_nightly_pipeline",
            "main",
        ]:
            if hasattr(pipeline, name):
                runner = getattr(pipeline, name)
                break

        if runner is None:
            results["ok"] = False
            results["steps"]["campaign_pipeline"] = {
                "status": "failed",
                "error": "No runner function found in nightly_campaign_pipeline.py",
            }
            return results

        pipeline_result = runner(**run_kwargs)

        results["steps"]["campaign_pipeline"] = {
            "status": "completed",
            "runner": runner.__name__,
            "result": pipeline_result,
        }

    except Exception as e:
        results["ok"] = False
        results["steps"]["campaign_pipeline"] = {
            "status": "failed",
            "error": str(e),
        }

    results["finished_at"] = datetime.utcnow().isoformat()
    return results


@app.post("/api/admin/refresh-weis-gamma-evidence")
def refresh_weis_gamma_evidence(payload: dict = Body(default=None)):
    payload = payload or {}

    requested_symbols = (
        payload.get("symbols")
        or payload.get("tickers")
        or payload.get("symbol")
        or []
    )

    if isinstance(requested_symbols, str):
        requested_symbols = [
            item.strip().upper()
            for item in requested_symbols.split(",")
            if item.strip()
        ]
    else:
        requested_symbols = [
            str(item or "").strip().upper()
            for item in requested_symbols
            if str(item or "").strip()
        ]

    timeframe = str(payload.get("timeframe") or "DAILY").upper()
    max_symbols = int(payload.get("max_symbols") or len(requested_symbols) or 10)
    bar_limit = int(payload.get("bar_limit") or 252)

    results = {
        "ok": True,
        "started_at": datetime.utcnow().isoformat(),
        "request": {
            "symbols": requested_symbols,
            "timeframe": timeframe,
            "max_symbols": max_symbols,
            "bar_limit": bar_limit,
        },
        "refreshed": [],
        "skipped": [],
        "errors": [],
    }

    try:
        from backend.campaign_engine.campaign_store import CampaignStore
        from backend.campaign_engine.campaign_discovery_engine import CampaignDiscoveryEngine
        from backend.campaign_engine.campaign_evidence_builder import CampaignEvidenceBuilder

        store = CampaignStore()

        if not store.configured():
            results["ok"] = False
            results["errors"].append({
                "status": "NO_DATABASE",
                "message": "CampaignStore is not configured.",
            })
            results["finished_at"] = datetime.utcnow().isoformat()
            return results

        discovery = CampaignDiscoveryEngine(
            store=store,
            timeframe=timeframe,
            max_symbols=max_symbols,
            bar_limit=bar_limit,
        )

        discovery.option_chain_fetch_count = 0

        active_campaigns = []

        if requested_symbols:
            for symbol in requested_symbols[:max_symbols]:
                active_campaigns.extend(
                    store.get_active_campaigns(symbol=symbol, timeframe=timeframe)
                )
        else:
            active_campaigns = store.get_active_campaigns(timeframe=timeframe)[:max_symbols]

        seen = set()
        unique_campaigns = []

        for campaign in active_campaigns:
            key = (
                str(campaign.get("symbol") or "").upper(),
                str(campaign.get("timeframe") or timeframe).upper(),
            )
            if key in seen:
                continue
            seen.add(key)
            unique_campaigns.append(campaign)

        refresh_symbols = [
            str(campaign.get("symbol") or "").upper()
            for campaign in unique_campaigns
            if str(campaign.get("symbol") or "").strip()
        ]

        bar_records = discovery.build_records_from_universe(symbols=refresh_symbols)

        record_by_symbol = {
            str(record.get("symbol") or "").upper(): record
            for record in (bar_records or [])
            if isinstance(record, dict) and str(record.get("symbol") or "").strip()
        }

        results["bar_record_symbols"] = sorted(record_by_symbol.keys())
        results["bar_diagnostics"] = discovery._json_safe(discovery.diagnostics)

        for campaign in unique_campaigns:
            symbol = str(campaign.get("symbol") or "").upper()
            campaign_timeframe = str(campaign.get("timeframe") or timeframe).upper()

            if not symbol:
                results["skipped"].append({
                    "symbol": symbol,
                    "reason": "Missing symbol.",
                })
                continue

            try:
                bar_record = record_by_symbol.get(symbol) or {}

                df = discovery._load_bars(
                    symbol,
                    campaign_timeframe,
                    record=bar_record,
                )

                if df is None or len(df) == 0:
                    results["skipped"].append({
                        "symbol": symbol,
                        "reason": "No OHLCV bars available.",
                        "bar_record_present": bool(bar_record),
                        "bar_record_symbols": sorted(record_by_symbol.keys()),
                    })
                    continue

                try:
                    current_close = round(float(df["close"].iloc[-1]), 4)
                except Exception:
                    current_close = None

                option_chain_result = discovery._load_option_chain_for_evidence(
                    symbol=symbol,
                    current_close=current_close,
                    should_fetch=True,
                )

                option_chain_data = option_chain_result.get("options_data") or None

                evidence = CampaignEvidenceBuilder.build_from_bars(
                    df,
                    symbol=symbol,
                    timeframe=campaign_timeframe,
                    option_chain=option_chain_data,
                    market_timestamp=discovery._now(),
                    gamma_snapshot_time=option_chain_result.get("fetched_at"),
                )

                if isinstance(evidence, dict):
                    evidence.setdefault("raw_metrics", {})
                    if isinstance(evidence.get("raw_metrics"), dict):
                        evidence["raw_metrics"]["option_chain_status"] = option_chain_result.get("status")
                        evidence["raw_metrics"]["option_chain_rows"] = int(option_chain_result.get("rows") or 0)
                        evidence["raw_metrics"]["option_chain_source"] = option_chain_result.get("source")
                        evidence["raw_metrics"]["option_chain_fetch_enabled"] = bool(discovery.option_chain_enabled)
                        evidence["raw_metrics"]["option_chain_transition_enabled"] = False

                updated_payload = dict(campaign)
                updated_payload["evidence"] = discovery._json_safe(evidence or {})
                updated_payload["evidence_density"] = discovery._safe_float(
                    discovery._evidence_density_score(evidence or {})
                )
                updated_payload["evidence_updated_at"] = discovery._now()

                if current_close is not None:
                    updated_payload["current_price"] = current_close

                store.save_campaign(updated_payload)

                weis_gamma = {}
                gamma_matrix = {}
                gamma_freshness = {}
                fusion = {}
                phase = {}
                ranking = {}

                if isinstance(evidence, dict):
                    weis_gamma = evidence.get("weis_gamma") or {}
                    gamma_matrix = weis_gamma.get("gamma_matrix") or {}
                    gamma_freshness = weis_gamma.get("gamma_freshness") or {}
                    fusion = weis_gamma.get("fusion") or {}
                    phase = weis_gamma.get("phase") or {}
                    ranking = weis_gamma.get("ranking") or {}

                results["refreshed"].append({
                    "symbol": symbol,
                    "campaign_id": campaign.get("campaign_id"),
                    "timeframe": campaign_timeframe,
                    "option_chain_status": option_chain_result.get("status"),
                    "option_chain_rows": int(option_chain_result.get("rows") or 0),
                    "weis_gamma_status": weis_gamma.get("status"),
                    "gamma_status": gamma_matrix.get("status"),
                    "gamma_regime": gamma_matrix.get("net_gamma_regime") or gamma_matrix.get("gamma_regime"),
                    "gamma_router": gamma_freshness.get("router_state"),
                    "gamma_fresh": gamma_freshness.get("gamma_data_fresh"),
                    "fusion_state": fusion.get("fusion_state"),
                    "phase": phase.get("phase"),
                    "rank_bucket": ranking.get("rank_bucket"),
                    "state_transition_enabled": False,
                })

            except Exception as exc:
                results["errors"].append({
                    "symbol": symbol,
                    "campaign_id": campaign.get("campaign_id"),
                    "error": str(exc),
                })

    except Exception as exc:
        results["ok"] = False
        results["errors"].append({
            "status": "ROUTE_ERROR",
            "error": str(exc),
        })

    results["finished_at"] = datetime.utcnow().isoformat()
    return results


@app.post("/api/admin/run-closure-engine")
def run_closure_engine_admin():
    from backend.intelligence.campaign_closure_engine import (
        run_campaign_closure_cycle,
    )

    return run_campaign_closure_cycle()


@app.get("/api/campaigns/active")
def campaigns_active_alias():
    from backend.campaign_api import active_campaigns

    return active_campaigns()


@app.get("/api/campaigns/summary")
def campaigns_summary_alias():
    from backend.campaign_api import status

    return status()


@app.get("/api/radar/top")
def radar_top_alias(limit: int = 8):
    from backend.campaign_api import rankings

    data = rankings()
    campaigns = data.get("campaigns", []) if isinstance(data, dict) else []
    return {"campaigns": campaigns[:limit]}




# ── Frontend compatibility routes: Radar / Scoreboard / Divergence ────────────
# These routes expose campaign-intelligence data in the lightweight shapes the
# Dash frontend already expects. They do not import the legacy radar service and
# do not change SIP, campaigns, Weis-Gamma, Admin, or lifecycle transition logic.

def _compat_safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _compat_safe_int(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _compat_first(campaign, names, default=None):
    if not isinstance(campaign, dict):
        return default
    for name in names:
        value = campaign.get(name)
        if value is not None and value != "":
            return value
    return default


def _compat_campaigns():
    try:
        from backend.campaign_api import active_campaigns

        data = active_campaigns()
        if isinstance(data, dict):
            campaigns = data.get("campaigns") or data.get("items") or []
        elif isinstance(data, list):
            campaigns = data
        else:
            campaigns = []

        return [c for c in campaigns if isinstance(c, dict)]
    except Exception:
        return []


def _compat_score(campaign):
    score = _compat_first(
        campaign,
        [
            "composite_score",
            "score",
            "d_score",
            "decision_score",
            "edge_score",
            "campaign_score",
            "master_score",
        ],
        None,
    )

    if score is None:
        obstacle = _compat_safe_float(campaign.get("obstacle_score"), 0)
        progress = _compat_safe_float(campaign.get("progress_score"), 0)
        if obstacle or progress:
            score = (obstacle + progress) / 2
        else:
            score = 0

    score = _compat_safe_float(score, 0)

    # Some internal scores may be stored as 0.00-1.00.
    if 0 < score <= 1:
        score = score * 100

    return max(0.0, min(100.0, score))


def _compat_grade(score):
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "W"


def _compat_bias(state):
    s = str(state or "").upper()
    if "DISTRIBUTION" in s or "CLOSED" in s:
        return "BEARISH"
    if s in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}:
        return "BULLISH"
    if s == "BIRTH":
        return "WATCH"
    return "NEUTRAL"


def _compat_regime(campaign):
    regime = _compat_first(
        campaign,
        ["regime", "current_regime", "weis_gamma_phase", "phase", "layer"],
        "DISCOVERY",
    )
    return str(regime or "DISCOVERY")


def _compat_to_frontend_row(campaign):
    symbol = str(_compat_first(campaign, ["symbol", "ticker"], "") or "").upper()
    state = str(_compat_first(campaign, ["current_state", "state", "status"], "BIRTH") or "BIRTH")
    score = _compat_score(campaign)
    price = _compat_safe_float(
        _compat_first(campaign, ["current_price", "price", "last_price", "close"], 0),
        0,
    )

    progress = _compat_safe_float(campaign.get("progress_score"), score)
    obstacle = _compat_safe_float(campaign.get("obstacle_score"), score)
    change_pct = _compat_safe_float(
        _compat_first(campaign, ["change_pct", "pct_change", "return_pct"], 0),
        0,
    )

    return {
        "campaign_id": campaign.get("campaign_id"),
        "symbol": symbol,
        "price": price,
        "change_pct": change_pct,
        "composite_score": round(score, 2),
        "score": round(score, 2),
        "grade": _compat_grade(score),
        "status": state,
        "regime": _compat_regime(campaign),
        "bias": _compat_bias(state),
        "timeframe": str(_compat_first(campaign, ["timeframe"], "DAILY") or "DAILY"),
        "layer": str(_compat_first(campaign, ["layer"], "DISCOVERY") or "DISCOVERY"),
        "obstacle_score": round(obstacle, 2),
        "progress_score": round(progress, 2),
        "duration_days": _compat_safe_int(campaign.get("duration_days"), 0),
        "source": "campaign_intelligence",
    }


@app.get("/api/radar/scores")
def radar_scores_compat(limit: int = 50):
    campaigns = _compat_campaigns()
    rows = [_compat_to_frontend_row(c) for c in campaigns]
    rows = [r for r in rows if r.get("symbol")]
    rows.sort(key=lambda r: r.get("composite_score", 0), reverse=True)

    return {
        "ok": True,
        "source": "campaign_intelligence_compat",
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(rows[:limit]),
        "symbols": rows[:limit],
    }


@app.get("/api/scoreboard")
def scoreboard_compat(limit: int = 50):
    campaigns = _compat_campaigns()
    entries = [_compat_to_frontend_row(c) for c in campaigns]
    entries = [e for e in entries if e.get("symbol")]
    entries.sort(key=lambda e: e.get("composite_score", 0), reverse=True)

    grade_counts = {}
    state_counts = {}

    for entry in entries:
        grade = entry.get("grade", "—")
        state = entry.get("status", "—")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        state_counts[state] = state_counts.get(state, 0) + 1

    return {
        "ok": True,
        "source": "campaign_intelligence_compat",
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "total": len(entries),
            "grade_counts": grade_counts,
            "state_counts": state_counts,
        },
        "entries": entries[:limit],
    }


@app.get("/api/admin/divergence-watchlist")
def divergence_watchlist_compat(limit: int = 50):
    campaigns = _compat_campaigns()
    rows = []

    for campaign in campaigns:
        row = _compat_to_frontend_row(campaign)
        if not row.get("symbol"):
            continue

        score = _compat_safe_float(row.get("score"), 0)
        behavioral_score = _compat_safe_float(
            _compat_first(campaign, ["progress_score", "evidence_density", "obstacle_score"], score),
            score,
        )

        if 0 < behavioral_score <= 1:
            behavioral_score = behavioral_score * 100

        delta = round(score - behavioral_score, 2)

        if delta >= 10:
            direction = "BULLISH"
        elif delta <= -10:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        rows.append({
            "symbol": row["symbol"],
            "price": row["price"],
            "score": round(score, 2),
            "behavioral_score": round(behavioral_score, 2),
            "delta": delta,
            "direction": direction,
            "regime": row["regime"],
            "status": row["status"],
            "source": "campaign_intelligence",
        })

    rows.sort(key=lambda r: abs(_compat_safe_float(r.get("delta"), 0)), reverse=True)

    return {
        "ok": True,
        "source": "campaign_intelligence_compat",
        "last_audit": datetime.utcnow().isoformat(),
        "count": len(rows[:limit]),
        "items": rows[:limit],
    }


app.include_router(campaign_router)
app.include_router(research_router)
app.include_router(intelligence_router)
app.include_router(operator_router)

if snapshot_router is not None:
    app.include_router(snapshot_router)

if admin_router is not None:
    app.include_router(admin_router)
