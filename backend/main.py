# STEP76_CONTROLLED_UNIVERSE_INGEST_ROUTER_IMPORT
try:
    from controlled_universe_ingest_api import controlled_universe_ingest_router
except Exception:
    try:
        from backend.controlled_universe_ingest_api import controlled_universe_ingest_router
    except Exception:
        controlled_universe_ingest_router = None

# STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_IMPORT
try:
    from campaign_pipeline_validation_api import campaign_pipeline_validation_router
except Exception:
    from backend.campaign_pipeline_validation_api import campaign_pipeline_validation_router

"""
SAVE AS:
backend/main.py
"""

# test build filter backend
from fastapi import FastAPI, Body, Request, HTTPException
from datetime import datetime, timedelta
import os
import json
import hmac
import requests
import threading
import uuid

from backend.campaign_api import router as campaign_router
from backend.research_api import router as research_router
from backend.intelligence_api import router as intelligence_router
from backend.operator_dominance.operator_dominance_api import router as operator_router

try:
    from backend.admin_api import router as admin_router
except Exception:
    admin_router = None


try:
    from backend.alerts_api import router as alerts_router
except Exception:
    alerts_router = None

try:
    from backend.snapshot_service import snapshot_router
except Exception:
    snapshot_router = None

# === STEP 9C COMMERCIAL ROUTE IMPORTS START ===
# Commercial launch surface routes.
# Billing route mount exposes read/config and Stripe checkout endpoints already
# implemented in backend/billing_router.py. This patch does not create a charge,
# does not execute a payment, and does not write to Supabase by itself.
from backend.billing_router import billing_router
from backend.legal_pages import legal_router
# === STEP 9C COMMERCIAL ROUTE IMPORTS END ===
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


# SIGMALYTIC_ASYNC_NIGHTLY_JOB_TRACKING
# The nightly pipeline can take several minutes to run. Calling it via a
# single blocking HTTP request risks Render's own edge proxy returning a
# 502 before the backend has actually finished -- even though the backend
# keeps working in the background regardless. This tracks jobs in memory
# so the POST route can return immediately, with a separate status route
# for the caller to poll.
# FIX (2026-07-27): job status was stored in a plain in-memory Python
# dict, living inside whichever single process created the job. Real
# production logs showed /api/admin/nightly-status/{job_id} returning
# 404 repeatedly for a job that genuinely existed -- because the status
# check landed on a different process than the one that created the job
# (a worker restart, or more than one worker, breaks this immediately).
# This replaces the in-memory dict with Redis-backed storage, so job
# status is found correctly regardless of which process handles which
# request. Falls back to the original in-memory behavior if Redis isn't
# configured/reachable -- this never becomes a hard dependency.
#
# Verified: a completely separate instance (simulating a different
# worker process) correctly reads a job created by another instance --
# this is the exact cross-process scenario that was failing in
# production, reproduced and confirmed fixed before this was applied.
class _NightlyJobStore:
    def __init__(self, redis_url=None, key_prefix="sigmalytic_nightly_job:", ttl_seconds=86400):
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds
        self._memory_lock = threading.Lock()
        self._memory_store = {}

        self._redis_client = None
        resolved_url = redis_url or os.getenv("REDIS_URL")
        if resolved_url:
            try:
                import redis as _redis_module
                client = _redis_module.from_url(resolved_url, socket_connect_timeout=2, socket_timeout=2)
                client.ping()
                self._redis_client = client
            except Exception:
                self._redis_client = None

    @property
    def backend(self):
        return "redis" if self._redis_client is not None else "memory"

    def create(self, job_id: str, data: dict):
        self._write(job_id, data)

    def update(self, job_id: str, **fields):
        current = self.get(job_id) or {}
        current.update(fields)
        self._write(job_id, current)

    def get(self, job_id: str):
        if self._redis_client is not None:
            try:
                raw = self._redis_client.get(f"{self._key_prefix}{job_id}")
                return json.loads(raw) if raw is not None else None
            except Exception:
                pass
        with self._memory_lock:
            return self._memory_store.get(job_id)

    def _write(self, job_id: str, data: dict):
        if self._redis_client is not None:
            try:
                self._redis_client.set(
                    f"{self._key_prefix}{job_id}", json.dumps(data), ex=self._ttl_seconds
                )
                return
            except Exception:
                pass
        with self._memory_lock:
            self._memory_store[job_id] = data


_NIGHTLY_JOBS = _NightlyJobStore()


def _alert_nightly_job_failure(reason: str):
    """
    Sends an admin alert for a nightly job failure. Wrapped so that any
    problem with the alerting system itself (missing config, network
    issue, import failure) can never affect the job status tracking that
    already happened above this call.
    """
    try:
        from backend.email_service import send_admin_alert_sync
        send_admin_alert_sync(
            subject="Nightly campaign pipeline failed",
            message=f"The nightly campaign refresh job failed.<br><br>Reason: {reason}",
            alert_key="nightly_cron_failure",
        )
    except Exception:
        pass


def _run_nightly_job_in_background(job_id: str, run_kwargs: dict):
    _NIGHTLY_JOBS.update(job_id, status="running")

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
            error_msg = "No runner function found in nightly_campaign_pipeline.py"
            _NIGHTLY_JOBS.update(
                job_id, status="failed", error=error_msg,
                finished_at=datetime.utcnow().isoformat(),
            )
            _alert_nightly_job_failure(error_msg)
            return

        pipeline_result = runner(**run_kwargs)

        _NIGHTLY_JOBS.update(
            job_id, status="completed",
            result={"runner": runner.__name__, "result": pipeline_result},
            finished_at=datetime.utcnow().isoformat(),
        )

    except Exception as e:
        _NIGHTLY_JOBS.update(
            job_id, status="failed", error=str(e),
            finished_at=datetime.utcnow().isoformat(),
        )
        _alert_nightly_job_failure(str(e))


@app.post("/api/admin/run-full-nightly")
def run_full_nightly(request: Request, payload: dict = Body(default=None)):
    payload = payload or {}

    # SIGMALYTIC_RFA11_AUTHENTICATED_NIGHTLY_CRON_START
    # This route is intentionally protected because it can persist refreshed
    # campaign rows through CampaignStore. The cron caller supplies the shared
    # secret in an HTTP header. The token value is never returned or logged.
    cron_enabled = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_ENABLED") or "").strip().lower()
    if cron_enabled not in {"1", "true", "yes", "enabled", "on"}:
        raise HTTPException(
            status_code=403,
            detail={
                "ok": False,
                "error": "nightly_campaign_cron_disabled",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )

    expected_token = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_TOKEN") or "").strip()
    provided_token = (
        request.headers.get("x-sigmalytic-cron-token")
        or request.headers.get("x-render-cron-token")
        or ""
    ).strip()

    if not expected_token:
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "missing_server_cron_token_configuration",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )

    if not provided_token or not hmac.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": "unauthorized_nightly_campaign_cron_request",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )
    # SIGMALYTIC_RFA11_AUTHENTICATED_NIGHTLY_CRON_END

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

    job_id = str(uuid.uuid4())

    started_at = datetime.utcnow().isoformat()
    _NIGHTLY_JOBS.create(job_id, {
        "status": "queued",
        "started_at": started_at,
        "request": {
            "symbols": requested_symbols,
            "max_symbols": payload.get("max_symbols"),
            "bar_limit": payload.get("bar_limit"),
            "timeframe": payload.get("timeframe"),
        },
    })
    # No manual count-based bounding needed anymore -- Redis entries
    # expire on their own after 24 hours (ttl_seconds on _NightlyJobStore).
    # The in-memory fallback path (only used if Redis is unreachable) can
    # grow unbounded for the lifetime of one process, but that's the same
    # degraded-but-functional behavior as before Redis was added.

    thread = threading.Thread(
        target=_run_nightly_job_in_background,
        args=(job_id, run_kwargs),
        daemon=True,
    )
    thread.start()

    # Returns immediately -- this is the whole point. The actual pipeline
    # keeps running in the background regardless of how long it takes,
    # and cannot be interrupted by a proxy-level response timeout since
    # nothing is waiting on this HTTP response.
    return {
        "ok": True,
        "status": "started",
        "job_id": job_id,
        "started_at": started_at,
        "poll_url": f"/api/admin/nightly-status/{job_id}",
    }


@app.get("/api/admin/nightly-status/{job_id}")
def nightly_status(request: Request, job_id: str):
    # Same shared-secret protection as the route that creates jobs --
    # job status can reveal campaign pipeline internals, so this isn't
    # left open.
    expected_token = (os.getenv("SIGMALYTIC_NIGHTLY_CRON_TOKEN") or "").strip()
    provided_token = (
        request.headers.get("x-sigmalytic-cron-token")
        or request.headers.get("x-render-cron-token")
        or ""
    ).strip()

    if not expected_token or not provided_token or not hmac.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=401,
            detail={
                "ok": False,
                "error": "unauthorized_nightly_campaign_cron_request",
                "source": "rfa11_authenticated_nightly_cron_gate",
            },
        )

    job = _NIGHTLY_JOBS.get(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail={"ok": False, "error": "unknown_job_id", "job_id": job_id},
        )

    return {"ok": True, "job_id": job_id, **job}


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
        "change_pct": round(change_pct, 2),
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
        "market_enriched": False,
        "market_price": None,
        "previous_close": None,
        "market_source": "campaign_intelligence",
        "source": "campaign_intelligence",
    }


def _compat_alpaca_headers():
    key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID") or ""
    secret = os.getenv("ALPACA_API_SECRET") or os.getenv("APCA_API_SECRET_KEY") or ""
    if not key or not secret:
        return None
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
    }


def _compat_enrich_market_rows(rows):
    """
    Add real Alpaca SIP latest price and previous daily close when available.

    If Alpaca does not return data for a symbol, the row remains usable but
    market_enriched stays false so the frontend/backend can distinguish a
    missing market-change calculation from a real 0.00% change.
    """
    clean_rows = [r for r in rows if isinstance(r, dict) and r.get("symbol")]
    headers = _compat_alpaca_headers()
    if not headers or not clean_rows:
        return {
            "rows": clean_rows,
            "market_enriched_count": 0,
            "market_error": "missing_alpaca_credentials" if not headers else None,
        }

    base_url = (os.getenv("ALPACA_BASE_URL") or "https://data.alpaca.markets").rstrip("/")
    symbols = [str(r.get("symbol")).upper() for r in clean_rows if r.get("symbol")]
    unique_symbols = []
    seen = set()
    for sym in symbols:
        if sym and sym not in seen:
            unique_symbols.append(sym)
            seen.add(sym)

    latest_by_symbol = {}
    prev_close_by_symbol = {}
    market_error = None

    try:
        latest_resp = requests.get(
            f"{base_url}/v2/stocks/bars/latest",
            headers=headers,
            params={"symbols": ",".join(unique_symbols), "feed": "sip"},
            timeout=15,
        )
        if latest_resp.ok:
            payload = latest_resp.json() or {}
            latest_by_symbol = payload.get("bars") or {}
        else:
            market_error = f"latest_http_{latest_resp.status_code}"
    except Exception as exc:
        market_error = f"latest_error_{str(exc)[:120]}"

    try:
        end_dt = datetime.utcnow()
        start_dt = end_dt - timedelta(days=14)
        daily_resp = requests.get(
            f"{base_url}/v2/stocks/bars",
            headers=headers,
            params={
                "symbols": ",".join(unique_symbols),
                "timeframe": "1Day",
                "start": start_dt.isoformat() + "Z",
                "end": end_dt.isoformat() + "Z",
                "limit": max(1000, len(unique_symbols) * 10),
                "adjustment": "raw",
                "feed": "sip",
            },
            timeout=20,
        )
        if daily_resp.ok:
            payload = daily_resp.json() or {}
            daily_bars = payload.get("bars") or {}
            for sym, bars in daily_bars.items():
                if isinstance(bars, list) and bars:
                    ref_bar = bars[-2] if len(bars) >= 2 else bars[-1]
                    prev_close_by_symbol[str(sym).upper()] = _compat_safe_float(ref_bar.get("c"), 0)
        elif market_error is None:
            market_error = f"daily_http_{daily_resp.status_code}"
    except Exception as exc:
        if market_error is None:
            market_error = f"daily_error_{str(exc)[:120]}"

    enriched_count = 0

    for row in clean_rows:
        sym = str(row.get("symbol") or "").upper()
        latest = latest_by_symbol.get(sym) or {}
        latest_price = _compat_safe_float(latest.get("c"), 0)
        previous_close = _compat_safe_float(prev_close_by_symbol.get(sym), 0)

        if latest_price > 0:
            row["price"] = round(latest_price, 4)
            row["market_price"] = round(latest_price, 4)

        if previous_close > 0:
            row["previous_close"] = round(previous_close, 4)

        if latest_price > 0 and previous_close > 0:
            row["change_pct"] = round(((latest_price - previous_close) / previous_close) * 100, 2)
            row["market_enriched"] = True
            row["market_source"] = "alpaca_sip"
            enriched_count += 1
        else:
            row["market_enriched"] = False
            row["market_source"] = "campaign_intelligence"

    return {
        "rows": clean_rows,
        "market_enriched_count": enriched_count,
        "market_error": market_error,
    }


def _compat_scoreboard_summary(entries):
    total_symbols = len(entries)
    armed_states = {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}
    armed = sum(1 for e in entries if str(e.get("status") or "").upper() in armed_states)
    a_grade = sum(1 for e in entries if str(e.get("grade") or "").upper().startswith("A"))
    avg_score = round(
        sum(_compat_safe_float(e.get("composite_score"), 0) for e in entries) / total_symbols,
        2,
    ) if total_symbols else 0

    grade_counts = {}
    state_counts = {}

    for entry in entries:
        grade = entry.get("grade", "—")
        state = entry.get("status", "—")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        state_counts[state] = state_counts.get(state, 0) + 1

    return {
        # Keys expected by the Dash Scoreboard tiles.
        "total_symbols": total_symbols,
        "armed": armed,
        "avg_score": avg_score,
        "a_grade": a_grade,

        # Compatibility/debug keys.
        "total": total_symbols,
        "grade_counts": grade_counts,
        "state_counts": state_counts,
    }


# SIGMALYTIC_STEP100R_W2_BACKEND_RADAR_STALE_WHILE_REVALIDATE
# Backend Radar is served as stale-while-revalidate so the UI does not wait on
# live market enrichment. This is read-only and does not mutate campaigns,
# scores, ranks, probabilities, operator-control state, D3D, Stripe, or Supabase.
import threading as _step100r_w2_threading
import time as _step100r_w2_time
from datetime import datetime as _step100r_w2_datetime

_STEP100R_W2_RADAR_CACHE_LOCK = _step100r_w2_threading.RLock()
_STEP100R_W2_RADAR_CACHE = {
    "payload": None,
    "cached_at_monotonic": 0.0,
    "refreshing": False,
}
_STEP100R_W2_RADAR_CACHE_TTL_SECONDS = 120.0
_STEP100R_W2_RADAR_LIMIT_MAX = 50


def _step100r_w2_normalize_limit(limit: int = 50) -> int:
    try:
        value = int(limit)
    except Exception:
        value = 50
    return max(1, min(value, _STEP100R_W2_RADAR_LIMIT_MAX))


def _step100r_w2_build_base_radar_rows(limit: int = 50):
    value = _step100r_w2_normalize_limit(limit)
    campaigns = _compat_campaigns()
    rows = [_compat_to_frontend_row(c) for c in campaigns]
    rows = [r for r in rows if r.get("symbol")]
    rows.sort(key=lambda r: r.get("composite_score", 0), reverse=True)
    return rows[:value]


def _step100r_w2_build_radar_payload(
    enrich_market: bool = True,
    source: str = "campaign_intelligence_compat",
):
    rows = _step100r_w2_build_base_radar_rows(_STEP100R_W2_RADAR_LIMIT_MAX)

    if enrich_market:
        market = _compat_enrich_market_rows(rows)
        out_rows = list(market.get("rows") or [])
        market_enriched_count = int(market.get("market_enriched_count") or 0)
        market_error = market.get("market_error")
    else:
        out_rows = rows
        market_enriched_count = 0
        market_error = None

    return {
        "ok": True,
        "source": source,
        "generated_at": _step100r_w2_datetime.utcnow().isoformat(),
        "count": len(out_rows),
        "market_enriched_count": market_enriched_count,
        "market_error": market_error,
        "symbols": out_rows,
        "guardrails": {
            "diagnostic_only": True,
            "read_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
        },
    }


def _step100r_w2_slice_payload(payload: dict, limit: int = 50, cache_mode: str = "cache"):
    value = _step100r_w2_normalize_limit(limit)
    cloned = dict(payload or {})
    symbols = list(cloned.get("symbols") or [])[:value]
    cloned["symbols"] = symbols
    cloned["count"] = len(symbols)
    cloned["served_at"] = _step100r_w2_datetime.utcnow().isoformat()
    cloned["cache"] = {
        "mode": cache_mode,
        "served_from_cache": True,
        "ttl_seconds": _STEP100R_W2_RADAR_CACHE_TTL_SECONDS,
    }
    return cloned


def _step100r_w2_refresh_worker():
    try:
        payload = _step100r_w2_build_radar_payload(
            enrich_market=True,
            source="campaign_intelligence_compat_cached_enriched",
        )
        payload["cache"] = {
            "mode": "background_refreshed",
            "served_from_cache": False,
            "ttl_seconds": _STEP100R_W2_RADAR_CACHE_TTL_SECONDS,
        }
        with _STEP100R_W2_RADAR_CACHE_LOCK:
            _STEP100R_W2_RADAR_CACHE["payload"] = payload
            _STEP100R_W2_RADAR_CACHE["cached_at_monotonic"] = _step100r_w2_time.monotonic()
    except Exception as exc:
        try:
            print(f"STEP100R_W2_RADAR_REFRESH_FAILED: {exc}")
        except Exception:
            pass
    finally:
        with _STEP100R_W2_RADAR_CACHE_LOCK:
            _STEP100R_W2_RADAR_CACHE["refreshing"] = False


def _step100r_w2_start_refresh_if_needed():
    with _STEP100R_W2_RADAR_CACHE_LOCK:
        if _STEP100R_W2_RADAR_CACHE.get("refreshing"):
            return
        _STEP100R_W2_RADAR_CACHE["refreshing"] = True

    thread = _step100r_w2_threading.Thread(
        target=_step100r_w2_refresh_worker,
        daemon=True,
    )
    thread.start()


@app.get("/api/radar/scores")
def radar_scores_compat(limit: int = 50):
    value = _step100r_w2_normalize_limit(limit)
    now = _step100r_w2_time.monotonic()

    with _STEP100R_W2_RADAR_CACHE_LOCK:
        cached = _STEP100R_W2_RADAR_CACHE.get("payload")
        cached_at = float(_STEP100R_W2_RADAR_CACHE.get("cached_at_monotonic") or 0.0)
        refreshing = bool(_STEP100R_W2_RADAR_CACHE.get("refreshing"))
        age = now - cached_at if cached else None

    if cached and age is not None and age <= _STEP100R_W2_RADAR_CACHE_TTL_SECONDS:
        return _step100r_w2_slice_payload(
            cached,
            limit=value,
            cache_mode="fresh_backend_cache",
        )

    if not refreshing:
        _step100r_w2_start_refresh_if_needed()

    if cached:
        return _step100r_w2_slice_payload(
            cached,
            limit=value,
            cache_mode="stale_while_revalidate",
        )

    payload = _step100r_w2_build_radar_payload(
        enrich_market=False,
        source="campaign_intelligence_compat_fast_seed",
    )
    payload["cache"] = {
        "mode": "fast_seed_background_refreshing",
        "served_from_cache": False,
        "ttl_seconds": _STEP100R_W2_RADAR_CACHE_TTL_SECONDS,
    }

    with _STEP100R_W2_RADAR_CACHE_LOCK:
        if _STEP100R_W2_RADAR_CACHE.get("payload") is None:
            _STEP100R_W2_RADAR_CACHE["payload"] = payload
            _STEP100R_W2_RADAR_CACHE["cached_at_monotonic"] = _step100r_w2_time.monotonic()

    return _step100r_w2_slice_payload(
        payload,
        limit=value,
        cache_mode="fast_seed_background_refreshing",
    )



@app.get("/api/scoreboard")
def scoreboard_compat(limit: int = 50):
    campaigns = _compat_campaigns()
    entries = [_compat_to_frontend_row(c) for c in campaigns]
    entries = [e for e in entries if e.get("symbol")]
    entries.sort(key=lambda e: e.get("composite_score", 0), reverse=True)

    display_entries = entries[:limit]
    market = _compat_enrich_market_rows(display_entries)

    return {
        "ok": True,
        "source": "campaign_intelligence_compat",
        "generated_at": datetime.utcnow().isoformat(),
        "summary": _compat_scoreboard_summary(entries),
        "market_enriched_count": market["market_enriched_count"],
        "market_error": market["market_error"],
        "entries": market["rows"],
    }
# === LIGHTWEIGHT PRODUCT RADAR COMPAT ROUTES START ===
# Lightweight product compatibility routes.
# These routes intentionally reuse the already-working campaign_intelligence_compat
# source exposed by radar_scores_compat and scoreboard_compat.
#
# These routes DO NOT import backend.radar_service.
# These routes DO NOT mount radar_router.
# These routes DO NOT touch Stripe, checkout, billing, payment processing, webhooks,
# Supabase writes, campaign mutation, D3D execution, operator-control confirmation,
# probability mutation, edge mutation, expected-return mutation, or trade-signal creation.

def _lightweight_radar_scores_payload(limit: int = 50):
    payload = radar_scores_compat(limit=limit)

    if hasattr(payload, "dict"):
        payload = payload.dict()

    if not isinstance(payload, dict):
        payload = {
            "ok": False,
            "source": "lightweight_product_compat",
            "error": "radar_scores_compat returned non-dict payload",
            "symbols": [],
        }

    symbols = payload.get("symbols")
    if symbols is None:
        symbols = payload.get("entries")

    if symbols is None:
        symbols = []

    return payload, symbols


@app.get("/api/radar/intelligence")
def radar_intelligence_lightweight_compat(limit: int = 50):
    payload, score_symbols = _lightweight_radar_scores_payload(limit=limit)

    campaign_rows = []
    campaign_source_error = None

    try:
        campaigns = _compat_campaigns()
        for campaign in (campaigns or [])[:limit]:
            row = _compat_to_frontend_row(campaign)
            if row.get("symbol"):
                campaign_rows.append(row)
    except Exception as exc:
        campaign_source_error = str(exc)

    source_symbols = campaign_rows if campaign_rows else score_symbols
    working_symbols = []

    for raw in (source_symbols or [])[:limit]:
        row = dict(raw) if isinstance(raw, dict) else {"symbol": raw}

        symbol = row.get("symbol") or row.get("ticker") or row.get("name") or "UNKNOWN"
        status = row.get("status") or row.get("campaign_state") or row.get("state") or "REVIEW"
        regime = row.get("regime") or row.get("market_regime") or row.get("behavioral_regime") or "UNSPECIFIED"
        score = row.get("score") or row.get("composite_score") or row.get("radar_score")

        row["working_app_evidence"] = {
            "purpose": "Expose Wyckoff, Weis, Livermore, history, lifecycle, and explanation evidence to the live app without mutating campaigns.",
            "symbol": symbol,
            "campaign_status": status,
            "campaign_regime": regime,
            "score_context": score,
            "wyckoff": {
                "available": True,
                "principles": [
                    "accumulation",
                    "distribution",
                    "absorption",
                    "supply_demand_test",
                    "spring_or_secondary_test_review",
                    "sign_of_strength_review",
                ],
                "review_mode": "read_only_campaign_evidence_surface",
            },
            "weis": {
                "available": True,
                "principles": [
                    "effort_vs_result",
                    "volume_wave_review",
                    "progress_vs_effort",
                    "absorption_or_non_confirmation_review",
                ],
                "review_mode": "read_only_campaign_evidence_surface",
            },
            "livermore": {
                "available": True,
                "principles": [
                    "pivotal_point_review",
                    "line_of_least_resistance",
                    "natural_reaction_review",
                    "campaign_continuation_or_failure_review",
                ],
                "review_mode": "read_only_campaign_evidence_surface",
            },
            "history": {
                "available": True,
                "mode": "current_snapshot_and_campaign_context_review",
                "generated_at": payload.get("generated_at"),
                "append_only_evidence_ledger_required_for_longitudinal_review": True,
                "mutates_campaigns": False,
            },
            "explanation": {
                "available": True,
                "rationale": "This payload explains the campaign through Wyckoff structure, Weis effort-versus-result behavior, Livermore pivotal behavior, lifecycle status, and historical review context.",
                "why": "Users need the principle-level evidence surface to understand why a campaign is forming, surviving, improving, failing, or maturing.",
                "not_a_trade_signal": True,
            },
        }

        working_symbols.append(row)

    return {
        "ok": True,
        "source": "working_app_campaign_intelligence_compat" if campaign_rows else "working_app_lightweight_product_compat",
        "compatibility_route": "/api/radar/intelligence",
        "derived_from": [
            "/api/radar/scores",
            "campaign_intelligence_compat" if campaign_rows else "radar_scores_compat",
        ],
        "generated_at": payload.get("generated_at"),
        "count": len(working_symbols),
        "market_enriched_count": payload.get("market_enriched_count"),
        "market_error": payload.get("market_error"),
        "campaign_source_available": bool(campaign_rows),
        "campaign_source_error": campaign_source_error,
        "working_app_evidence_contract": {
            "wyckoff": True,
            "weis": True,
            "livermore": True,
            "history": True,
            "lifecycle": True,
            "explanation": True,
            "read_only": True,
            "mutates_campaigns": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
        },
        "symbols": working_symbols,
        "guardrails": {
            "read_only": True,
            "diagnostic_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
        },
    }



# === PHASE 12.17 CONTROLLED TRANSITION PREVIEW START ===
# Read-only transition preview route.
# This route calculates proposed campaign lifecycle transitions for operator review only.
# It does not write to Supabase, mutate campaigns, authorize D3D, confirm operator control,
# create trade signals, send alerts, or touch Stripe/billing.
def _phase12_17_normalize_campaign_state(value):
    raw = str(value or "BIRTH").strip().upper().replace(" ", "_").replace("-", "_")
    allowed = {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
        "EXPANDING",
        "MATURING",
        "DISTRIBUTION_RISK",
        "CLOSED",
    }
    return raw if raw in allowed else "BIRTH"


def _phase12_17_safe_score(row, keys, default=0.0):
    for key in keys:
        try:
            value = row.get(key)
            if value is not None and value != "":
                return float(value)
        except Exception:
            continue
    return float(default)


def _phase12_17_transition_preview_for_row(row):
    symbol = row.get("symbol") or row.get("ticker") or row.get("name") or "UNKNOWN"
    current_state = _phase12_17_normalize_campaign_state(
        row.get("status") or row.get("campaign_state") or row.get("state") or row.get("current_state")
    )

    score = _phase12_17_safe_score(row, ["score", "composite_score", "radar_score"], 0.0)
    progress = _phase12_17_safe_score(row, ["progress_score", "behavioral_score", "score"], score)
    obstacle = _phase12_17_safe_score(row, ["obstacle_score", "resistance_score", "risk_score"], 0.0)

    regime = str(row.get("regime") or row.get("market_regime") or row.get("behavioral_regime") or "").upper()
    contrary_failure = (
        "DISTRIBUTION" in regime
        or "FAILURE" in regime
        or "EXHAUSTION" in regime and progress < obstacle
    )

    proposed_state = current_state
    rationale = []

    if current_state == "BIRTH":
        if score >= 70 or progress >= 70:
            proposed_state = "CONFIRMED"
            rationale.append("BIRTH can preview CONFIRMED when campaign score/progress reaches confirmation threshold.")
        else:
            rationale.append("BIRTH remains BIRTH until confirmation threshold is visible.")

    elif current_state == "CONFIRMED":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("CONFIRMED previews DISTRIBUTION_RISK when contrary failure/regime pressure is visible.")
        elif progress >= 65:
            proposed_state = "SURVIVING"
            rationale.append("CONFIRMED previews SURVIVING when campaign progress persists.")
        else:
            rationale.append("CONFIRMED remains CONFIRMED until survival evidence strengthens.")

    elif current_state == "SURVIVING":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("SURVIVING previews DISTRIBUTION_RISK when contrary failure appears.")
        elif progress >= 75 and score >= 70:
            proposed_state = "EXPANDING"
            rationale.append("SURVIVING previews EXPANDING when progress and score both remain strong.")
        else:
            rationale.append("SURVIVING remains SURVIVING pending stronger expansion evidence.")

    elif current_state == "EXPANDING":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("EXPANDING previews DISTRIBUTION_RISK when distribution/failure pressure appears.")
        elif progress >= 85 or score >= 85:
            proposed_state = "MATURING"
            rationale.append("EXPANDING previews MATURING when campaign strength becomes extended.")
        else:
            rationale.append("EXPANDING remains EXPANDING while extension evidence is not mature.")

    elif current_state == "MATURING":
        if contrary_failure:
            proposed_state = "DISTRIBUTION_RISK"
            rationale.append("MATURING previews DISTRIBUTION_RISK when late-cycle contrary failure appears.")
        else:
            rationale.append("MATURING remains MATURING while no contrary failure is visible.")

    elif current_state == "DISTRIBUTION_RISK":
        if score <= 35 or progress <= 35:
            proposed_state = "CLOSED"
            rationale.append("DISTRIBUTION_RISK previews CLOSED when score/progress collapses.")
        else:
            rationale.append("DISTRIBUTION_RISK remains active until closure evidence is stronger.")

    elif current_state == "CLOSED":
        proposed_state = "CLOSED"
        rationale.append("CLOSED remains CLOSED.")

    transition_required = proposed_state != current_state

    return {
        "symbol": symbol,
        "current_state": current_state,
        "proposed_next_state": proposed_state,
        "transition_required": transition_required,
        "score_context": score,
        "progress_context": progress,
        "obstacle_context": obstacle,
        "regime_context": regime,
        "rationale": rationale,
        "review_only": True,
        "writes_to_supabase": False,
        "mutates_campaigns": False,
        "changes_states": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
    }





# === PHASE 12.29A CONTROLLED AUDIT TABLE SCHEMA CREATION START ===
# Controlled audit-table schema creation route.
# This route is schema-write capable only after an explicit confirmation phrase.
# It creates only public.campaign_state_transition_audit_events and its indexes/RLS/policy.
# It does not mutate campaigns, does not change campaign states, does not authorize D3D,
# does not confirm operator control, does not create trade signals, does not send alerts,
# and does not touch Stripe/billing.
def _phase12_29a_get_database_connection_info():
    import os

    candidates = [
        "SUPABASE_DB_URL",
        "DATABASE_URL",
        "POSTGRES_URL",
        "POSTGRES_PRISMA_URL",
        "POSTGRESQL_URL",
        "RENDER_POSTGRES_URL",
    ]

    for name in candidates:
        value = os.environ.get(name)
        if value:
            return value, name

    return None, None


def _phase12_29a_schema_sql_statements():
    return [
        """
        create table if not exists public.campaign_state_transition_audit_events (
            id bigserial primary key,
            created_at timestamptz not null default now(),

            source text not null default 'phase12_controlled_campaign_state_mutation',
            mode text not null default 'APPEND_ONLY_CAMPAIGN_STATE_TRANSITION_AUDIT',

            symbol text not null,
            campaign_id text null,

            before_state text not null,
            after_state text not null,
            transition_required boolean not null default true,

            lifecycle_field text not null default 'current_state',
            evidence_source text not null,
            rationale jsonb not null default '[]'::jsonb,

            guardrails jsonb not null default '{}'::jsonb,
            request_payload jsonb not null default '{}'::jsonb,
            response_payload jsonb not null default '{}'::jsonb,

            operator_control_confirmed boolean not null default false,
            authorizes_d3d boolean not null default false,
            not_a_trade_signal boolean not null default true,

            writes_to_supabase boolean not null default true,
            mutates_campaigns boolean not null default false,
            changes_states boolean not null default false,

            alert_send_execution boolean not null default false,
            stripe_touched boolean not null default false,
            billing_touched boolean not null default false,

            constraint campaign_state_transition_audit_events_before_state_check
                check (before_state in (
                    'BIRTH',
                    'CONFIRMED',
                    'SURVIVING',
                    'EXPANDING',
                    'MATURING',
                    'DISTRIBUTION_RISK',
                    'CLOSED'
                )),

            constraint campaign_state_transition_audit_events_after_state_check
                check (after_state in (
                    'BIRTH',
                    'CONFIRMED',
                    'SURVIVING',
                    'EXPANDING',
                    'MATURING',
                    'DISTRIBUTION_RISK',
                    'CLOSED'
                )),

            constraint campaign_state_transition_audit_events_lifecycle_field_check
                check (lifecycle_field = 'current_state'),

            constraint campaign_state_transition_audit_events_no_operator_control_check
                check (operator_control_confirmed = false),

            constraint campaign_state_transition_audit_events_no_d3d_authorization_check
                check (authorizes_d3d = false),

            constraint campaign_state_transition_audit_events_not_trade_signal_check
                check (not_a_trade_signal = true),

            constraint campaign_state_transition_audit_events_no_alert_send_check
                check (alert_send_execution = false),

            constraint campaign_state_transition_audit_events_no_stripe_touch_check
                check (stripe_touched = false),

            constraint campaign_state_transition_audit_events_no_billing_touch_check
                check (billing_touched = false)
        )
        """,
        """
        create index if not exists idx_campaign_state_transition_audit_events_symbol_created_at
            on public.campaign_state_transition_audit_events (symbol, created_at desc)
        """,
        """
        create index if not exists idx_campaign_state_transition_audit_events_campaign_id_created_at
            on public.campaign_state_transition_audit_events (campaign_id, created_at desc)
        """,
        """
        create index if not exists idx_campaign_state_transition_audit_events_before_after_state
            on public.campaign_state_transition_audit_events (before_state, after_state)
        """,
        """
        alter table public.campaign_state_transition_audit_events enable row level security
        """,
        """
        drop policy if exists campaign_state_transition_audit_events_select_authenticated
            on public.campaign_state_transition_audit_events
        """,
        """
        create policy campaign_state_transition_audit_events_select_authenticated
            on public.campaign_state_transition_audit_events
            for select
            to authenticated
            using (true)
        """,
    ]


@app.post("/api/campaigns/create-state-mutation-audit-table")
def phase12_29a_create_state_mutation_audit_table(payload: dict):
    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()
    dry_run = bool(payload.get("dry_run", False))

    required_phrase = "CONFIRM CREATE APPEND ONLY CAMPAIGN STATE TRANSITION AUDIT TABLE"

    if confirmation_phrase != required_phrase:
        return {
            "ok": False,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_REJECTED",
            "schema_write_executed": False,
            "failure": "MISSING_EXPLICIT_SCHEMA_CREATION_CONFIRMATION_PHRASE",
            "required_confirmation_phrase": required_phrase,
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }

    statements = _phase12_29a_schema_sql_statements()

    if dry_run:
        return {
            "ok": True,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_DRY_RUN",
            "schema_write_executed": False,
            "statement_count": len(statements),
            "target_table": "public.campaign_state_transition_audit_events",
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()

    if not database_url:
        return {
            "ok": False,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_BLOCKED_NO_DB_URL",
            "schema_write_executed": False,
            "failure": "MISSING_DATABASE_URL_FOR_DDL_EXECUTION",
            "accepted_env_names": [
                "SUPABASE_DB_URL",
                "DATABASE_URL",
                "POSTGRES_URL",
                "POSTGRES_PRISMA_URL",
                "POSTGRESQL_URL",
                "RENDER_POSTGRES_URL",
            ],
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }

    executed = []
    try:
        try:
            import psycopg
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    for statement in statements:
                        cur.execute(statement)
                        executed.append(statement.strip().splitlines()[0].strip())
                conn.commit()
        except Exception as psycopg_exc:
            try:
                import psycopg2
                conn = psycopg2.connect(database_url)
                try:
                    cur = conn.cursor()
                    try:
                        for statement in statements:
                            cur.execute(statement)
                            executed.append(statement.strip().splitlines()[0].strip())
                        conn.commit()
                    finally:
                        cur.close()
                finally:
                    conn.close()
            except Exception as psycopg2_exc:
                return {
                    "ok": False,
                    "source": "phase12_29a_create_state_mutation_audit_table",
                    "mode": "CONTROLLED_SCHEMA_CREATION_DRIVER_FAILED",
                    "schema_write_executed": False,
                    "database_url_env_name": database_url_env_name,
                    "failure": "POSTGRES_DRIVER_OR_EXECUTION_FAILED",
                    "psycopg_error": str(psycopg_exc)[:600],
                    "psycopg2_error": str(psycopg2_exc)[:600],
                    "guardrails": {
                        "read_only": False,
                        "schema_creation_only": True,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                        "executes_d3d": False,
                        "authorizes_d3d": False,
                        "operator_control_confirmed": False,
                        "not_a_trade_signal": True,
                        "alert_send_execution": False,
                        "stripe_touched": False,
                        "billing_touched": False,
                    },
                }

        return {
            "ok": True,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_EXECUTED",
            "schema_write_executed": True,
            "target_table": "public.campaign_state_transition_audit_events",
            "database_url_env_name": database_url_env_name,
            "executed_statement_count": len(executed),
            "executed_statement_starts": executed,
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": True,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "source": "phase12_29a_create_state_mutation_audit_table",
            "mode": "CONTROLLED_SCHEMA_CREATION_UNHANDLED_FAILURE",
            "schema_write_executed": False,
            "failure": str(exc)[:700],
            "guardrails": {
                "read_only": False,
                "schema_creation_only": True,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
                "executes_d3d": False,
                "authorizes_d3d": False,
                "operator_control_confirmed": False,
                "not_a_trade_signal": True,
                "alert_send_execution": False,
                "stripe_touched": False,
                "billing_touched": False,
            },
        }
# === PHASE 12.29A CONTROLLED AUDIT TABLE SCHEMA CREATION END ===

# === PHASE 12.30A CONTROLLED CAMPAIGN STATE MUTATION EXECUTION ROUTE START ===
# Corrected in Phase 12.30A-R2:
# The campaign lifecycle field is public.campaigns.current_state.
# public.campaigns.status is operational status such as active/inactive and SHALL NOT be mutated as lifecycle state.
# This route performs no D3D authorization, no operator-control confirmation, no trade-signal creation,
# no alert send, and no Stripe/billing action.
# Execution requires an explicit confirmation phrase and an exact campaign row/current_state match.
def _phase12_30a_valid_campaign_lifecycle_states():
    return {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
        "EXPANDING",
        "MATURING",
        "DISTRIBUTION_RISK",
        "CLOSED",
    }


def _phase12_30a_allowed_campaign_lifecycle_transitions():
    return {
        "BIRTH": {"CONFIRMED", "CLOSED"},
        "CONFIRMED": {"SURVIVING", "DISTRIBUTION_RISK", "CLOSED"},
        "SURVIVING": {"EXPANDING", "DISTRIBUTION_RISK", "CLOSED"},
        "EXPANDING": {"MATURING", "DISTRIBUTION_RISK", "CLOSED"},
        "MATURING": {"DISTRIBUTION_RISK", "CLOSED"},
        "DISTRIBUTION_RISK": {"CLOSED"},
        "CLOSED": set(),
    }


def _phase12_30a_normalize_state(value):
    return str(value or "").strip().upper()


def _phase12_30a_safe_json_value(value, fallback):
    import json

    try:
        json.dumps(value)
        return value
    except Exception:
        return fallback


def _phase12_30a_connect_database(database_url):
    try:
        import psycopg

        conn = psycopg.connect(database_url)
        return conn, "psycopg"
    except Exception as psycopg_exc:
        try:
            import psycopg2

            conn = psycopg2.connect(database_url)
            return conn, "psycopg2"
        except Exception as psycopg2_exc:
            raise RuntimeError(
                "POSTGRES_DRIVER_OR_CONNECTION_FAILED | "
                + "psycopg_error="
                + str(psycopg_exc)[:400]
                + " | psycopg2_error="
                + str(psycopg2_exc)[:400]
            )


def _phase12_30a_select_campaign_row(cursor, campaign_id, symbol):
    cursor.execute(
        """
        select
            campaign_id::text as id,
            symbol::text as symbol,
            status::text as status,
            current_state::text as current_state
        from public.campaigns
        where campaign_id::text = %s
          and symbol::text = %s
        limit 1
        """,
        (str(campaign_id), str(symbol).strip().upper()),
    )
    return cursor.fetchone()


def _phase12_30a_insert_transition_audit_event(
    cursor,
    symbol,
    campaign_id,
    before_state,
    after_state,
    evidence_source,
    rationale,
    request_payload,
    response_payload,
):
    import json

    guardrails = {
        "read_only": False,
        "controlled_state_mutation": True,
        "append_only_audit_event_first": True,
        "lifecycle_field": "current_state",
        "writes_to_supabase": True,
        "mutates_campaigns": True,
        "changes_states": True,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    cursor.execute(
        """
        insert into public.campaign_state_transition_audit_events (
            source,
            mode,
            symbol,
            campaign_id,
            before_state,
            after_state,
            transition_required,
            lifecycle_field,
            evidence_source,
            rationale,
            guardrails,
            request_payload,
            response_payload,
            operator_control_confirmed,
            authorizes_d3d,
            not_a_trade_signal,
            writes_to_supabase,
            mutates_campaigns,
            changes_states,
            alert_send_execution,
            stripe_touched,
            billing_touched
        )
        values (
            %s, %s, %s, %s, %s, %s, true, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
            false, false, true, true, true, true, false, false, false
        )
        returning id::text
        """,
        (
            "phase12_30a_r2_controlled_campaign_current_state_mutation",
            "APPEND_ONLY_AUDIT_EVENT_BEFORE_CAMPAIGN_CURRENT_STATE_UPDATE",
            str(symbol).strip().upper(),
            str(campaign_id),
            before_state,
            after_state,
            "current_state",
            str(evidence_source or "controlled_transition_preview"),
            json.dumps(_phase12_30a_safe_json_value(rationale, [])),
            json.dumps(guardrails),
            json.dumps(_phase12_30a_safe_json_value(request_payload, {})),
            json.dumps(_phase12_30a_safe_json_value(response_payload, {})),
        ),
    )
    row = cursor.fetchone()
    return str(row[0]) if row else None


@app.post("/api/campaigns/controlled-state-mutation-execution")
def phase12_30a_controlled_state_mutation_execution(payload: dict):
    required_phrase = "CONFIRM EXECUTE ONE CONTROLLED CAMPAIGN STATE MUTATION"

    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()
    dry_run = bool(payload.get("dry_run", True))

    symbol = str(payload.get("symbol") or "").strip().upper()
    campaign_id = str(payload.get("campaign_id") or "").strip()
    expected_before_state = _phase12_30a_normalize_state(payload.get("expected_before_state"))
    requested_after_state = _phase12_30a_normalize_state(payload.get("requested_after_state"))
    evidence_source = str(payload.get("evidence_source") or "controlled_transition_preview").strip()
    rationale = payload.get("rationale")
    if rationale is None:
        rationale = []

    valid_states = _phase12_30a_valid_campaign_lifecycle_states()
    allowed_transitions = _phase12_30a_allowed_campaign_lifecycle_transitions()

    base_guardrails = {
        "read_only": False,
        "controlled_state_mutation": True,
        "append_only_audit_event_first": True,
        "lifecycle_field": "current_state",
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    if confirmation_phrase != required_phrase:
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_REJECTED",
            "failure": "MISSING_EXPLICIT_STATE_MUTATION_CONFIRMATION_PHRASE",
            "required_confirmation_phrase": required_phrase,
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }

    validation_failures = []

    if not symbol:
        validation_failures.append("MISSING_SYMBOL")
    if not campaign_id:
        validation_failures.append("MISSING_CAMPAIGN_ID")
    if expected_before_state not in valid_states:
        validation_failures.append("INVALID_EXPECTED_BEFORE_STATE")
    if requested_after_state not in valid_states:
        validation_failures.append("INVALID_REQUESTED_AFTER_STATE")
    if expected_before_state == requested_after_state:
        validation_failures.append("NO_STATE_CHANGE_REQUESTED")
    if requested_after_state not in allowed_transitions.get(expected_before_state, set()):
        validation_failures.append("DISALLOWED_LIFECYCLE_TRANSITION")
    if not evidence_source:
        validation_failures.append("MISSING_EVIDENCE_SOURCE")
    if not isinstance(rationale, list) or len(rationale) == 0:
        validation_failures.append("MISSING_RATIONALE_LIST")

    if validation_failures:
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_VALIDATION_FAILED",
            "validation_failures": validation_failures,
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "received": {
                "symbol": symbol,
                "campaign_id": campaign_id,
                "expected_before_state": expected_before_state,
                "requested_after_state": requested_after_state,
                "evidence_source": evidence_source,
            },
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()
    if not database_url:
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_BLOCKED_NO_DB_URL",
            "failure": "MISSING_DATABASE_URL_FOR_CONTROLLED_MUTATION",
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }

    conn = None
    try:
        conn, driver_name = _phase12_30a_connect_database(database_url)
        cur = conn.cursor()

        try:
            selected = _phase12_30a_select_campaign_row(cur, campaign_id, symbol)
            if not selected:
                return {
                    "ok": False,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_TARGET_NOT_FOUND",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": False,
                    "campaign_update_executed": False,
                    "target": {
                        "symbol": symbol,
                        "campaign_id": campaign_id,
                    },
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                    },
                }

            selected_id = str(selected[0])
            selected_symbol = str(selected[1]).upper()
            selected_status = str(selected[2])
            selected_current_state = _phase12_30a_normalize_state(selected[3])

            if selected_current_state != expected_before_state:
                return {
                    "ok": False,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_BEFORE_STATE_MISMATCH",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": False,
                    "campaign_update_executed": False,
                    "expected_before_state": expected_before_state,
                    "actual_status": selected_status,
                    "actual_current_state": selected_current_state,
                    "target": {
                        "symbol": selected_symbol,
                        "campaign_id": selected_id,
                    },
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                    },
                }

            response_plan = {
                "symbol": selected_symbol,
                "campaign_id": selected_id,
                "operational_status": selected_status,
                "before_current_state": selected_current_state,
                "after_current_state": requested_after_state,
                "lifecycle_field": "current_state",
                "audit_table": "public.campaign_state_transition_audit_events",
                "campaign_table": "public.campaigns",
                "execution_order": [
                    "insert append-only audit event",
                    "update public.campaigns.current_state with exact campaign_id/symbol/before-current-state match",
                ],
            }

            if dry_run:
                return {
                    "ok": True,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_DRY_RUN",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": False,
                    "campaign_update_executed": False,
                    "plan": response_plan,
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": False,
                        "mutates_campaigns": False,
                        "changes_states": False,
                        "would_insert_audit_event": True,
                        "would_mutate_campaign": True,
                        "would_change_state": True,
                    },
                }

            audit_response_payload = {
                "planned_after_current_state": requested_after_state,
                "selected_operational_status": selected_status,
                "selected_before_current_state": selected_current_state,
                "controlled_execution": True,
            }

            audit_event_id = _phase12_30a_insert_transition_audit_event(
                cur,
                selected_symbol,
                selected_id,
                selected_current_state,
                requested_after_state,
                evidence_source,
                rationale,
                payload,
                audit_response_payload,
            )
            conn.commit()

            cur.execute(
                """
                update public.campaigns
                set current_state = %s
                where campaign_id::text = %s
                  and symbol::text = %s
                  and current_state::text = %s
                returning campaign_id::text, symbol::text, current_state::text
                """,
                (
                    requested_after_state,
                    selected_id,
                    selected_symbol,
                    selected_current_state,
                ),
            )
            updated = cur.fetchone()
            conn.commit()

            if not updated:
                return {
                    "ok": False,
                    "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                    "mode": "CONTROLLED_STATE_MUTATION_UPDATE_NO_ROWS_AFTER_AUDIT",
                    "database_url_env_name": database_url_env_name,
                    "driver_name": driver_name,
                    "state_mutation_executed": False,
                    "audit_event_inserted": True,
                    "audit_event_id": audit_event_id,
                    "campaign_update_executed": False,
                    "failure": "CAMPAIGN_CURRENT_STATE_UPDATE_RETURNED_NO_ROWS_AFTER_AUDIT_INSERT",
                    "target": response_plan,
                    "guardrails": {
                        **base_guardrails,
                        "writes_to_supabase": True,
                        "mutates_campaigns": False,
                        "changes_states": False,
                    },
                }

            return {
                "ok": True,
                "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
                "mode": "CONTROLLED_STATE_MUTATION_EXECUTED",
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "state_mutation_executed": True,
                "audit_event_inserted": True,
                "audit_event_id": audit_event_id,
                "campaign_update_executed": True,
                "target": {
                    "campaign_id": str(updated[0]),
                    "symbol": str(updated[1]).upper(),
                    "before_state": selected_current_state,
                    "after_state": str(updated[2]).upper(),
                    "lifecycle_field": "current_state",
                },
                "guardrails": {
                    **base_guardrails,
                    "writes_to_supabase": True,
                    "mutates_campaigns": True,
                    "changes_states": True,
                },
            }
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "source": "phase12_30a_r2_controlled_current_state_mutation_execution",
            "mode": "CONTROLLED_STATE_MUTATION_UNHANDLED_FAILURE",
            "failure": str(exc)[:900],
            "state_mutation_executed": False,
            "audit_event_inserted": False,
            "campaign_update_executed": False,
            "guardrails": {
                **base_guardrails,
                "writes_to_supabase": False,
                "mutates_campaigns": False,
                "changes_states": False,
            },
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
# === PHASE 12.30A CONTROLLED CAMPAIGN STATE MUTATION EXECUTION ROUTE END ===

# === PHASE 12.30C-R2 AUDIT LIFECYCLE CONSTRAINT CORRECTION ROUTE START ===
# Controlled schema repair route for the append-only campaign state transition audit table.
# The lifecycle field for campaign mutation is public.campaigns.current_state.
# This route may repair only the audit table lifecycle_field default/check constraint.
# It must not mutate campaigns, change campaign states, authorize D3D, confirm operator control,
# create trade signals, send alerts, or touch Stripe/billing.
@app.post("/api/campaigns/repair-state-mutation-audit-lifecycle-field-constraint")
def phase12_30c_r2_repair_state_mutation_audit_lifecycle_field_constraint(payload: dict):
    required_phrase = "CONFIRM REPAIR CAMPAIGN STATE TRANSITION AUDIT LIFECYCLE FIELD CONSTRAINT"

    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()
    dry_run = bool(payload.get("dry_run", True))

    base_guardrails = {
        "read_only": False,
        "controlled_schema_repair": True,
        "target_table": "public.campaign_state_transition_audit_events",
        "target_constraint": "campaign_state_transition_audit_events_lifecycle_field_check",
        "target_lifecycle_field_value": "current_state",
        "writes_to_supabase": False,
        "schema_write_executed": False,
        "mutates_campaigns": False,
        "changes_states": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    if confirmation_phrase != required_phrase:
        return {
            "ok": False,
            "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
            "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_REJECTED",
            "failure": "MISSING_EXPLICIT_SCHEMA_REPAIR_CONFIRMATION_PHRASE",
            "required_confirmation_phrase": required_phrase,
            "constraint_repaired": False,
            "guardrails": base_guardrails,
        }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()
    if not database_url:
        return {
            "ok": False,
            "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
            "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_BLOCKED_NO_DB_URL",
            "failure": "MISSING_DATABASE_URL_FOR_CONTROLLED_SCHEMA_REPAIR",
            "constraint_repaired": False,
            "guardrails": base_guardrails,
        }

    conn = None
    try:
        conn, driver_name = _phase12_30a_connect_database(database_url)
        cur = conn.cursor()

        try:
            cur.execute(
                """
                select count(*)::int
                from public.campaign_state_transition_audit_events
                where lifecycle_field is distinct from 'current_state'
                """
            )
            non_current_state_count_row = cur.fetchone()
            non_current_state_count = int(non_current_state_count_row[0]) if non_current_state_count_row else 0

            cur.execute(
                """
                select count(*)::int
                from public.campaign_state_transition_audit_events
                """
            )
            total_rows_row = cur.fetchone()
            total_rows = int(total_rows_row[0]) if total_rows_row else 0

            cur.execute(
                """
                select pg_get_constraintdef(c.oid)
                from pg_constraint c
                join pg_class t on t.oid = c.conrelid
                join pg_namespace n on n.oid = t.relnamespace
                where n.nspname = 'public'
                  and t.relname = 'campaign_state_transition_audit_events'
                  and c.conname = 'campaign_state_transition_audit_events_lifecycle_field_check'
                limit 1
                """
            )
            before_constraint_row = cur.fetchone()
            before_constraint = str(before_constraint_row[0]) if before_constraint_row else ""

            plan = {
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "target_table": "public.campaign_state_transition_audit_events",
                "target_constraint": "campaign_state_transition_audit_events_lifecycle_field_check",
                "before_constraint": before_constraint,
                "total_audit_rows": total_rows,
                "non_current_state_audit_rows": non_current_state_count,
                "repair_steps": [
                    "drop existing lifecycle_field check constraint",
                    "set lifecycle_field default to current_state",
                    "add lifecycle_field check constraint requiring current_state",
                ],
            }

            if non_current_state_count != 0:
                return {
                    "ok": False,
                    "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
                    "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_BLOCKED_BY_EXISTING_ROWS",
                    "failure": "EXISTING_AUDIT_ROWS_HAVE_NON_CURRENT_STATE_LIFECYCLE_FIELD",
                    "constraint_repaired": False,
                    "plan": plan,
                    "guardrails": base_guardrails,
                }

            if dry_run:
                return {
                    "ok": True,
                    "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
                    "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_DRY_RUN",
                    "constraint_repaired": False,
                    "plan": plan,
                    "guardrails": {
                        **base_guardrails,
                        "would_write_to_supabase": True,
                        "would_execute_schema_write": True,
                    },
                }

            cur.execute(
                """
                alter table public.campaign_state_transition_audit_events
                drop constraint if exists campaign_state_transition_audit_events_lifecycle_field_check
                """
            )
            cur.execute(
                """
                alter table public.campaign_state_transition_audit_events
                alter column lifecycle_field set default 'current_state'
                """
            )
            cur.execute(
                """
                alter table public.campaign_state_transition_audit_events
                add constraint campaign_state_transition_audit_events_lifecycle_field_check
                check (lifecycle_field = 'current_state')
                """
            )
            conn.commit()

            cur.execute(
                """
                select pg_get_constraintdef(c.oid)
                from pg_constraint c
                join pg_class t on t.oid = c.conrelid
                join pg_namespace n on n.oid = t.relnamespace
                where n.nspname = 'public'
                  and t.relname = 'campaign_state_transition_audit_events'
                  and c.conname = 'campaign_state_transition_audit_events_lifecycle_field_check'
                limit 1
                """
            )
            after_constraint_row = cur.fetchone()
            after_constraint = str(after_constraint_row[0]) if after_constraint_row else ""

            repaired = "current_state" in after_constraint and "status" not in after_constraint

            return {
                "ok": repaired,
                "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
                "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_EXECUTED" if repaired else "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_EXECUTED_BUT_NOT_VERIFIED",
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "schema_write_executed": True,
                "constraint_repaired": repaired,
                "target_table": "public.campaign_state_transition_audit_events",
                "target_constraint": "campaign_state_transition_audit_events_lifecycle_field_check",
                "before_constraint": before_constraint,
                "after_constraint": after_constraint,
                "total_audit_rows": total_rows,
                "non_current_state_audit_rows": non_current_state_count,
                "guardrails": {
                    **base_guardrails,
                    "writes_to_supabase": True,
                    "schema_write_executed": True,
                    "mutates_campaigns": False,
                    "changes_states": False,
                },
            }
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return {
            "ok": False,
            "source": "phase12_30c_r2_audit_lifecycle_constraint_repair",
            "mode": "AUDIT_LIFECYCLE_CONSTRAINT_REPAIR_UNHANDLED_FAILURE",
            "failure": str(exc)[:900],
            "schema_write_executed": False,
            "constraint_repaired": False,
            "guardrails": base_guardrails,
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
# === PHASE 12.30C-R2 AUDIT LIFECYCLE CONSTRAINT CORRECTION ROUTE END ===

# === PHASE 12.30D-R2 CONTROLLED STATE MUTATION READBACK ROUTE START ===
# Read-only post-mutation closure route.
# Verifies the append-only audit event and campaign current_state readback.
# This route performs SELECT-only database reads.
# It must not write schema, mutate campaigns, change states, authorize D3D,
# confirm operator control, create trade signals, send alerts, or touch Stripe/billing.
@app.get("/api/campaigns/controlled-state-mutation-readback")
def phase12_30d_r2_controlled_state_mutation_readback(
    audit_event_id: str = "2",
    campaign_id: str = "635",
    symbol: str = "CDC",
    expected_before_state: str = "BIRTH",
    expected_after_state: str = "CONFIRMED",
):
    target_symbol = str(symbol or "").strip().upper()
    target_campaign_id = str(campaign_id or "").strip()
    target_audit_event_id = str(audit_event_id or "").strip()
    target_before_state = str(expected_before_state or "").strip().upper()
    target_after_state = str(expected_after_state or "").strip().upper()

    guardrails = {
        "read_only": True,
        "select_only": True,
        "writes_to_supabase": False,
        "schema_write_executed": False,
        "mutates_campaigns": False,
        "changes_states": False,
        "executes_d3d": False,
        "authorizes_d3d": False,
        "operator_control_confirmed": False,
        "not_a_trade_signal": True,
        "alert_send_execution": False,
        "stripe_touched": False,
        "billing_touched": False,
    }

    database_url, database_url_env_name = _phase12_29a_get_database_connection_info()
    if not database_url:
        return {
            "ok": False,
            "source": "phase12_30d_r2_controlled_state_mutation_readback",
            "mode": "READBACK_BLOCKED_NO_DB_URL",
            "readback_verified": False,
            "failure": "MISSING_DATABASE_URL_FOR_READ_ONLY_READBACK",
            "guardrails": guardrails,
        }

    conn = None
    try:
        conn, driver_name = _phase12_30a_connect_database(database_url)
        cur = conn.cursor()

        try:
            cur.execute(
                """
                select
                    id::text,
                    created_at::text,
                    source::text,
                    mode::text,
                    symbol::text,
                    campaign_id::text,
                    before_state::text,
                    after_state::text,
                    transition_required,
                    lifecycle_field::text,
                    evidence_source::text,
                    operator_control_confirmed,
                    authorizes_d3d,
                    not_a_trade_signal,
                    writes_to_supabase,
                    mutates_campaigns,
                    changes_states,
                    alert_send_execution,
                    stripe_touched,
                    billing_touched
                from public.campaign_state_transition_audit_events
                where id::text = %s
                  and campaign_id::text = %s
                  and symbol::text = %s
                limit 1
                """,
                (target_audit_event_id, target_campaign_id, target_symbol),
            )
            audit_row = cur.fetchone()

            cur.execute(
                """
                select
                    campaign_id::text,
                    symbol::text,
                    status::text,
                    current_state::text
                from public.campaigns
                where campaign_id::text = %s
                  and symbol::text = %s
                limit 1
                """,
                (target_campaign_id, target_symbol),
            )
            campaign_row = cur.fetchone()

            cur.execute(
                """
                select count(*)::int
                from public.campaign_state_transition_audit_events
                where campaign_id::text = %s
                  and symbol::text = %s
                  and before_state::text = %s
                  and after_state::text = %s
                  and lifecycle_field::text = 'current_state'
                  and mode::text = 'APPEND_ONLY_AUDIT_EVENT_BEFORE_CAMPAIGN_CURRENT_STATE_UPDATE'
                """,
                (
                    target_campaign_id,
                    target_symbol,
                    target_before_state,
                    target_after_state,
                ),
            )
            count_row = cur.fetchone()
            exact_transition_audit_event_count = int(count_row[0]) if count_row else 0

            audit_event = None
            if audit_row:
                audit_event = {
                    "id": str(audit_row[0]),
                    "created_at": str(audit_row[1]),
                    "source": str(audit_row[2]),
                    "mode": str(audit_row[3]),
                    "symbol": str(audit_row[4]).upper(),
                    "campaign_id": str(audit_row[5]),
                    "before_state": str(audit_row[6]).upper(),
                    "after_state": str(audit_row[7]).upper(),
                    "transition_required": bool(audit_row[8]),
                    "lifecycle_field": str(audit_row[9]),
                    "evidence_source": str(audit_row[10]),
                    "operator_control_confirmed": bool(audit_row[11]),
                    "authorizes_d3d": bool(audit_row[12]),
                    "not_a_trade_signal": bool(audit_row[13]),
                    "writes_to_supabase": bool(audit_row[14]),
                    "mutates_campaigns": bool(audit_row[15]),
                    "changes_states": bool(audit_row[16]),
                    "alert_send_execution": bool(audit_row[17]),
                    "stripe_touched": bool(audit_row[18]),
                    "billing_touched": bool(audit_row[19]),
                }

            campaign = None
            if campaign_row:
                campaign = {
                    "campaign_id": str(campaign_row[0]),
                    "symbol": str(campaign_row[1]).upper(),
                    "status": str(campaign_row[2]),
                    "current_state": str(campaign_row[3]).upper(),
                }

            audit_verified = (
                audit_event is not None
                and audit_event["id"] == target_audit_event_id
                and audit_event["campaign_id"] == target_campaign_id
                and audit_event["symbol"] == target_symbol
                and audit_event["before_state"] == target_before_state
                and audit_event["after_state"] == target_after_state
                and audit_event["lifecycle_field"] == "current_state"
                and audit_event["operator_control_confirmed"] is False
                and audit_event["authorizes_d3d"] is False
                and audit_event["not_a_trade_signal"] is True
                and audit_event["alert_send_execution"] is False
                and audit_event["stripe_touched"] is False
                and audit_event["billing_touched"] is False
            )

            campaign_verified = (
                campaign is not None
                and campaign["campaign_id"] == target_campaign_id
                and campaign["symbol"] == target_symbol
                and campaign["status"] == "active"
                and campaign["current_state"] == target_after_state
            )

            duplicate_safe = exact_transition_audit_event_count == 1
            readback_verified = audit_verified and campaign_verified and duplicate_safe

            return {
                "ok": readback_verified,
                "source": "phase12_30d_r2_controlled_state_mutation_readback",
                "mode": "READ_ONLY_POST_MUTATION_AUDIT_READBACK",
                "database_url_env_name": database_url_env_name,
                "driver_name": driver_name,
                "readback_verified": readback_verified,
                "audit_verified": audit_verified,
                "campaign_verified": campaign_verified,
                "duplicate_safe": duplicate_safe,
                "exact_transition_audit_event_count": exact_transition_audit_event_count,
                "target": {
                    "audit_event_id": target_audit_event_id,
                    "campaign_id": target_campaign_id,
                    "symbol": target_symbol,
                    "expected_before_state": target_before_state,
                    "expected_after_state": target_after_state,
                    "lifecycle_field": "current_state",
                    "campaign_key": "campaign_id",
                },
                "audit_event": audit_event,
                "campaign": campaign,
                "guardrails": guardrails,
            }
        finally:
            try:
                cur.close()
            except Exception:
                pass
    except Exception as exc:
        return {
            "ok": False,
            "source": "phase12_30d_r2_controlled_state_mutation_readback",
            "mode": "READBACK_UNHANDLED_FAILURE",
            "readback_verified": False,
            "failure": str(exc)[:900],
            "guardrails": guardrails,
        }
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
# === PHASE 12.30D-R2 CONTROLLED STATE MUTATION READBACK ROUTE END ===




# === PHASE 12.27-R2 LIVE-BACKED SCHEMA READINESS START ===
# Read-only live backend schema readiness route.
# This route exists because local development shells may not have Supabase credentials,
# while the deployed backend does. It performs SELECT-only schema checks.
# It never writes to Supabase, never mutates campaigns, never changes states,
# never authorizes D3D, never confirms operator control, never creates trade signals,
# never sends alerts, and never touches Stripe/billing.
def _phase12_27_r2_get_supabase_client():
    import os

    url = (
        os.environ.get("SUPABASE_URL")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
        or os.environ.get("VITE_SUPABASE_URL")
    )

    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )

    if not url or not key:
        return None, {
            "has_supabase_url": bool(url),
            "has_supabase_key": bool(key),
            "error": "MISSING_SUPABASE_URL_OR_KEY",
        }

    try:
        from supabase import create_client
        return create_client(url, key), {
            "has_supabase_url": True,
            "has_supabase_key": True,
            "error": None,
        }
    except Exception as exc:
        return None, {
            "has_supabase_url": bool(url),
            "has_supabase_key": bool(key),
            "error": "SUPABASE_CLIENT_IMPORT_OR_CREATE_FAILED: " + str(exc)[:400],
        }


def _phase12_27_r2_select_check(client, table_name, select_expr="*"):
    try:
        response = client.table(table_name).select(select_expr).limit(1).execute()
        data = getattr(response, "data", None)
        return {
            "ok": isinstance(data, list),
            "table": table_name,
            "select": select_expr,
            "row_count_sample": len(data or []) if isinstance(data, list) else None,
            "sample_keys": sorted(list((data[0] or {}).keys())) if isinstance(data, list) and data else [],
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "table": table_name,
            "select": select_expr,
            "row_count_sample": None,
            "sample_keys": [],
            "error": str(exc)[:700],
        }


@app.get("/api/campaigns/state-mutation-schema-readiness")
def phase12_27_r2_live_backed_state_mutation_schema_readiness():
    client, client_status = _phase12_27_r2_get_supabase_client()

    checks = {
        "client": client_status,
        "campaigns_table": None,
        "campaigns_status_field": None,
        "campaigns_current_state_field": None,
        "campaigns_campaign_state_field": None,
        "campaign_state_transition_audit_events_table": None,
    }

    if client is not None:
        checks["campaigns_table"] = _phase12_27_r2_select_check(client, "campaigns", "*")
        checks["campaigns_status_field"] = _phase12_27_r2_select_check(client, "campaigns", "status")
        checks["campaigns_current_state_field"] = _phase12_27_r2_select_check(client, "campaigns", "current_state")
        checks["campaigns_campaign_state_field"] = _phase12_27_r2_select_check(client, "campaigns", "campaign_state")
        checks["campaign_state_transition_audit_events_table"] = _phase12_27_r2_select_check(
            client,
            "campaign_state_transition_audit_events",
            "*",
        )

    has_campaigns_table = bool(checks["campaigns_table"] and checks["campaigns_table"].get("ok") is True)
    has_status_field = bool(checks["campaigns_status_field"] and checks["campaigns_status_field"].get("ok") is True)
    has_current_state_field = bool(checks["campaigns_current_state_field"] and checks["campaigns_current_state_field"].get("ok") is True)
    has_campaign_state_field = bool(checks["campaigns_campaign_state_field"] and checks["campaigns_campaign_state_field"].get("ok") is True)
    has_audit_table = bool(
        checks["campaign_state_transition_audit_events_table"]
        and checks["campaign_state_transition_audit_events_table"].get("ok") is True
    )

    schema_ready_for_controlled_mutation = (
        has_campaigns_table
        and has_status_field
        and has_audit_table
    )

    return {
        "ok": True,
        "source": "phase12_27_r2_live_backed_state_mutation_schema_readiness",
        "mode": "READ_ONLY_LIVE_BACKED_SCHEMA_READINESS",
        "schema_ready_for_controlled_mutation": schema_ready_for_controlled_mutation,
        "resolved_lifecycle_field": "status" if has_status_field else None,
        "required_audit_table": "campaign_state_transition_audit_events",
        "checks": checks,
        "classification": {
            "has_campaigns_table": has_campaigns_table,
            "has_status_field": has_status_field,
            "has_current_state_field": has_current_state_field,
            "has_campaign_state_field": has_campaign_state_field,
            "has_campaign_state_transition_audit_events_table": has_audit_table,
        },
        "guardrails": {
            "read_only": True,
            "schema_check_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "changes_states": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
            "stripe_touched": False,
            "billing_touched": False,
        },
    }
# === PHASE 12.27-R2 LIVE-BACKED SCHEMA READINESS END ===

# === PHASE 12.25 CONTROLLED CAMPAIGN STATE MUTATION PREFLIGHT START ===
# Controlled production mutation preflight route.
# This validates a proposed campaign lifecycle-state mutation plan only.
# It does not write to Supabase, does not mutate campaigns, does not change states,
# does not authorize D3D, does not confirm operator control, does not create trade signals,
# does not send alerts, and does not touch Stripe/billing.
def _phase12_25_allowed_campaign_state(value):
    normalized = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    allowed = {
        "BIRTH",
        "CONFIRMED",
        "SURVIVING",
        "EXPANDING",
        "MATURING",
        "DISTRIBUTION_RISK",
        "CLOSED",
    }
    return normalized if normalized in allowed else None


def _phase12_25_bool(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


@app.post("/api/campaigns/controlled-state-mutation-preflight")
def phase12_25_controlled_campaign_state_mutation_preflight(payload: dict):
    symbol = str(payload.get("symbol") or "").strip().upper()
    campaign_id = payload.get("campaign_id") or payload.get("id")
    current_state = _phase12_25_allowed_campaign_state(payload.get("current_state"))
    proposed_next_state = _phase12_25_allowed_campaign_state(payload.get("proposed_next_state"))
    transition_required = _phase12_25_bool(payload.get("transition_required"))
    rationale = payload.get("rationale") or []
    evidence_source = str(payload.get("evidence_source") or "phase12_transition_preview").strip()
    confirmation_phrase = str(payload.get("confirmation_phrase") or "").strip()

    failures = []

    if not symbol:
        failures.append("MISSING_SYMBOL")

    if current_state is None:
        failures.append("INVALID_CURRENT_STATE")

    if proposed_next_state is None:
        failures.append("INVALID_PROPOSED_NEXT_STATE")

    if current_state is not None and proposed_next_state is not None and current_state == proposed_next_state:
        failures.append("NO_STATE_CHANGE_REQUESTED")

    if transition_required is not True:
        failures.append("TRANSITION_REQUIRED_NOT_TRUE")

    if not rationale:
        failures.append("MISSING_RATIONALE")

    if not evidence_source:
        failures.append("MISSING_EVIDENCE_SOURCE")

    if confirmation_phrase != "CONFIRM CONTROLLED CAMPAIGN STATE MUTATION PREFLIGHT":
        failures.append("MISSING_EXPLICIT_PREFLIGHT_CONFIRMATION_PHRASE")

    preflight_passed = len(failures) == 0

    audit_event_plan = {
        "table": "campaign_state_transition_audit_events",
        "operation": "insert",
        "append_only": True,
        "would_write": False,
        "payload": {
            "symbol": symbol,
            "campaign_id": campaign_id,
            "before_state": current_state,
            "after_state": proposed_next_state,
            "transition_required": transition_required,
            "rationale": rationale,
            "evidence_source": evidence_source,
            "source": "phase12_25_controlled_campaign_state_mutation_preflight",
            "operator_control_confirmed": False,
            "authorizes_d3d": False,
            "not_a_trade_signal": True,
        },
    }

    campaign_update_plan = {
        "table": "campaigns",
        "operation": "update",
        "field": "status",
        "would_write": False,
        "where": {
            "symbol": symbol,
            "campaign_id": campaign_id,
        },
        "set": {
            "status": proposed_next_state,
        },
        "prohibited_fields": [
            "score",
            "rank",
            "probability",
            "edge",
            "operator_control_confirmed",
            "composite_operator_control_confirmed",
            "authorizes_d3d",
            "executes_d3d",
            "trade_signal",
            "alert_send_execution",
            "stripe_touched",
            "billing_touched",
        ],
    }

    return {
        "ok": True,
        "source": "phase12_25_controlled_campaign_state_mutation_preflight",
        "mode": "CONTROLLED_STATE_MUTATION_PREFLIGHT_NO_WRITE",
        "preflight_passed": preflight_passed,
        "failures": failures,
        "symbol": symbol,
        "campaign_id": campaign_id,
        "current_state": current_state,
        "proposed_next_state": proposed_next_state,
        "transition_required": transition_required,
        "audit_event_plan": audit_event_plan,
        "campaign_update_plan": campaign_update_plan,
        "guardrails": {
            "read_only": True,
            "preflight_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "changes_states": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
            "stripe_touched": False,
            "billing_touched": False,
        },
    }
# === PHASE 12.25 CONTROLLED CAMPAIGN STATE MUTATION PREFLIGHT END ===

@app.get("/api/campaigns/transition-preview")
def phase12_17_controlled_transition_preview(limit: int = 50):
    rows = []
    source_error = None

    try:
        campaigns = _compat_campaigns()
        for campaign in (campaigns or [])[:limit]:
            row = _compat_to_frontend_row(campaign)
            if row.get("symbol"):
                rows.append(row)
    except Exception as exc:
        source_error = str(exc)

    previews = [_phase12_17_transition_preview_for_row(row) for row in rows[:limit]]

    return {
        "ok": True,
        "source": "phase12_17_controlled_transition_preview",
        "mode": "READ_ONLY_TRANSITION_PREVIEW",
        "count": len(previews),
        "source_error": source_error,
        "transitions": previews,
        "guardrails": {
            "read_only": True,
            "review_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "changes_states": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "alert_send_execution": False,
            "stripe_touched": False,
            "billing_touched": False,
        },
    }
# === PHASE 12.17 CONTROLLED TRANSITION PREVIEW END ===

@app.get("/api/radar/probability-status")
def radar_probability_status_lightweight_compat(limit: int = 50):
    payload, symbols = _lightweight_radar_scores_payload(limit=limit)

    return {
        "ok": True,
        "source": "lightweight_product_compat",
        "compatibility_route": "/api/radar/probability-status",
        "derived_from": "/api/radar/scores",
        "generated_at": payload.get("generated_at"),
        "campaign_feed_available": True,
        "campaign_feed_count": len(symbols),
        "market_enriched_count": payload.get("market_enriched_count"),
        "probability_engine": {
            "available": False,
            "status": "NOT_ENABLED_IN_LIGHTWEIGHT_COMPAT",
            "reason": "This endpoint reports product availability only. It does not generate probability, edge, expected return, trade signals, D3D authorization, or operator-control confirmation.",
        },
        "guardrails": {
            "read_only": True,
            "diagnostic_only": True,
            "writes_to_supabase": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "changes_scores": False,
            "changes_ranks": False,
            "changes_states": False,
            "changes_probabilities": False,
            "changes_edge": False,
        },
    }
# === LIGHTWEIGHT PRODUCT RADAR COMPAT ROUTES END ===


@app.get("/api/admin/divergence-watchlist")
def divergence_watchlist_compat(limit: int = 50):
    campaigns = _compat_campaigns()
    rows = []

    for campaign in campaigns:
        row = _compat_to_frontend_row(campaign)
        if not row.get("symbol"):
            continue

        score = _compat_safe_float(row.get("score"), 0)
        progress = _compat_safe_float(row.get("progress_score"), score)
        obstacle = _compat_safe_float(row.get("obstacle_score"), score)
        delta = round(progress - obstacle, 2)

        state = str(row.get("status") or "").upper()
        regime = str(row.get("regime") or "").upper()

        if "DISTRIBUTION" in state or "DISTRIBUTION" in regime:
            direction = "BEARISH"
        elif "EXHAUSTION" in regime and progress < obstacle:
            direction = "BEARISH"
        elif state in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"} and progress >= obstacle:
            direction = "BULLISH"
        elif state in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}:
            direction = "WATCH"
        else:
            direction = "WATCH"

        rows.append({
            "symbol": row["symbol"],
            "price": row["price"],
            "score": round(score, 2),
            "behavioral_score": round(progress, 2),
            "delta": delta,
            "direction": direction,
            "regime": row["regime"],
            "status": row["status"],
            "source": "campaign_intelligence",
        })

    direction_rank = {"BULLISH": 0, "BEARISH": 1, "WATCH": 2}
    rows.sort(
        key=lambda r: (
            direction_rank.get(str(r.get("direction")), 9),
            -abs(_compat_safe_float(r.get("delta"), 0)),
            -_compat_safe_float(r.get("score"), 0),
        )
    )

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

if alerts_router is not None:
    app.include_router(alerts_router)

if snapshot_router is not None:
    app.include_router(snapshot_router)

if admin_router is not None:
    app.include_router(admin_router)
# === STEP 9C COMMERCIAL ROUTE MOUNTS START ===
# Commercial launch surface mounts.
# These mounts expose:
#   GET  /api/billing/config
#   GET  /privacy
#   GET  /terms
# This patch only mounts existing routers. It does not execute Stripe checkout,
# does not process a webhook, does not create a subscription, and does not write
# to Supabase.
app.include_router(billing_router)
app.include_router(legal_router)
# === STEP 9C COMMERCIAL ROUTE MOUNTS END ===

# ============================================================
# D3E.5 - CONTROLLED APPEND-ONLY AUDIT WRITE ROUTE HARD BLOCK
# Mode: route shell only. No Supabase write. No D3D. No Stripe.
# ============================================================
try:
    from typing import Any, Dict, Optional

    from backend.alerts.controlled_append_only_audit_write_route import (
        build_controlled_append_only_audit_write_route_payload,
    )

    @app.get("/api/alerts/read-only/controlled-append-only-audit-write-route")
    async def d3e5_controlled_append_only_audit_write_route_readiness():
        return build_controlled_append_only_audit_write_route_payload(
            {
                "request_method": "GET",
                "dry_run": True,
                "source": "read_only_route_readiness",
            }
        )

    @app.post("/api/alerts/controlled/append-only-audit-write")
    async def d3e5_controlled_append_only_audit_write_route(
        payload: Optional[Dict[str, Any]] = None,
    ):
        return build_controlled_append_only_audit_write_route_payload(payload or {})

except Exception as _d3e5_route_mount_error:
    _D3E5_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e5_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-append-only-audit-write-route")
    async def d3e5_controlled_append_only_audit_write_route_mount_error():
        return {
            "ok": False,
            "d3e_phase": "D3E.5",
            "route_status": "CONTROLLED_APPEND_ONLY_AUDIT_WRITE_ROUTE_MOUNT_ERROR",
            "mount_error_excerpt": _D3E5_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.6 - CONTROLLED ONE-ROW APPEND-ONLY AUDIT INSERT
# Mode: build route only unless exact D3E.6 execution phrase is supplied.
# No campaign mutation. No D3D. No operator-control confirmation. No Stripe.
# ============================================================
try:
    from typing import Any, Dict, Optional

    from backend.alerts.controlled_one_row_append_only_audit_insert import (
        build_d3e6_readiness_payload,
        execute_d3e6_controlled_one_row_insert,
    )

    @app.get("/api/alerts/read-only/controlled-one-row-append-only-audit-insert-readiness")
    async def d3e6_controlled_one_row_append_only_audit_insert_readiness():
        return build_d3e6_readiness_payload()

    @app.post("/api/alerts/controlled/one-row-append-only-audit-insert")
    async def d3e6_controlled_one_row_append_only_audit_insert(
        payload: Optional[Dict[str, Any]] = None,
    ):
        return execute_d3e6_controlled_one_row_insert(payload or {})

except Exception as _d3e6_route_mount_error:
    _D3E6_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e6_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-one-row-append-only-audit-insert-readiness")
    async def d3e6_controlled_one_row_append_only_audit_insert_mount_error():
        return {
            "ok": False,
            "d3e_phase": "D3E.6",
            "route_status": "D3E6_CONTROLLED_ONE_ROW_APPEND_ONLY_AUDIT_INSERT_MOUNT_ERROR",
            "mount_error_excerpt": _D3E6_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.7A - CONTROLLED POST-WRITE READBACK ROUTE MOUNT REPAIR
# Mode: read-only Supabase readback. No write. No D3D. No Stripe.
# ============================================================
try:
    from backend.alerts.controlled_post_write_readback_verification import (
        build_d3e7_post_write_readback_verification_payload,
    )

    @app.get("/api/alerts/read-only/controlled-post-write-readback-verification")
    async def d3e7_controlled_post_write_readback_verification():
        return build_d3e7_post_write_readback_verification_payload(execute_live_read=True)

except Exception as _d3e7a_route_mount_error:
    _D3E7A_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e7a_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-post-write-readback-verification")
    async def d3e7a_controlled_post_write_readback_verification_mount_error():
        return {
            "ok": False,
            "d3e_phase": "D3E.7A",
            "route_status": "D3E7A_POST_WRITE_READBACK_VERIFICATION_MOUNT_ERROR",
            "mount_error_excerpt": _D3E7A_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.8 - CONTROLLED PERSISTENCE POST-WRITE CLOSURE SWEEP
# Mode: read-only Supabase closure sweep. No write. No D3D. No Stripe.
# ============================================================
try:
    from backend.alerts.controlled_persistence_post_write_closure_sweep import (
        build_d3e8_post_persistence_closure_sweep_payload,
    )

    @app.get("/api/alerts/read-only/controlled-persistence-post-write-closure-sweep")
    async def d3e8_controlled_persistence_post_write_closure_sweep():
        return build_d3e8_post_persistence_closure_sweep_payload(execute_live_read=True)

except Exception as _d3e8_route_mount_error:
    _D3E8_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e8_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-persistence-post-write-closure-sweep")
    async def d3e8_controlled_persistence_post_write_closure_sweep_mount_error():
        return {
            "ok": False,
            "d3e_phase": "D3E.8",
            "route_status": "D3E8_POST_PERSISTENCE_CLOSURE_SWEEP_MOUNT_ERROR",
            "mount_error_excerpt": _D3E8_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# ============================================================
# D3E.9 - FINAL CONTROLLED PERSISTENCE LIFECYCLE REGRESSION SWEEP
# Mode: read-only final lifecycle sweep. No write. No D3D. No Stripe.
# ============================================================
try:
    from backend.alerts.controlled_persistence_final_lifecycle_regression_sweep import (
        build_d3e9_final_lifecycle_regression_sweep_payload,
    )

    @app.get("/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep")
    async def d3e9_controlled_persistence_final_lifecycle_regression_sweep():
        return build_d3e9_final_lifecycle_regression_sweep_payload(execute_live_read=True)

except Exception as _d3e9_route_mount_error:
    _D3E9_ROUTE_MOUNT_ERROR_EXCERPT = str(_d3e9_route_mount_error)[:500]

    @app.get("/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep")
    async def d3e9_controlled_persistence_final_lifecycle_regression_sweep_mount_error():
        return {
            "ok": False,
            "d3e_phase": "D3E.9",
            "route_status": "D3E9_FINAL_LIFECYCLE_REGRESSION_SWEEP_MOUNT_ERROR",
            "mount_error_excerpt": _D3E9_ROUTE_MOUNT_ERROR_EXCERPT,
            "writes_to_supabase": False,
            "supabase_write_authorized": False,
            "persistence_write_authorized": False,
            "mutates_campaigns": False,
            "executes_d3d": False,
            "authorizes_d3d": False,
            "operator_control_confirmed": False,
            "composite_operator_control_confirmed": False,
            "not_a_trade_signal": True,
            "touches_stripe": False,
        }

# STEP76_CONTROLLED_UNIVERSE_INGEST_ROUTER_INCLUDE
if controlled_universe_ingest_router is not None:
    app.include_router(controlled_universe_ingest_router)

# STEP28B_CAMPAIGN_PIPELINE_VALIDATION_ROUTER_INCLUDE
if campaign_pipeline_validation_router is not None:
    app.include_router(campaign_pipeline_validation_router)

# SIGMALYTIC_STEP85D_IMPORT_HISTORY_RESTORE_ROUTER_START
# Isolated brokerage import-history restoration lane.
# This router is intentionally scoped away from campaign mutation, universe ingest,
# D3D authorization, operator-control confirmation, trade signals, and billing.
try:
    from backend.import_history_restore_api import router as import_history_restore_router
except Exception:
    from import_history_restore_api import router as import_history_restore_router

app.include_router(import_history_restore_router)
# SIGMALYTIC_STEP85D_IMPORT_HISTORY_RESTORE_ROUTER_END


# === SIGMALYTIC CONTROLLED EMAIL ALERT TEST ROUTER START ===
try:
    from backend.email_alert_controlled_test_api import router as email_alert_controlled_test_router
    app.include_router(email_alert_controlled_test_router)
except Exception as _sig_email_alert_test_router_exc:
    print(f"[sigmalytic] controlled email alert test router not mounted: {_sig_email_alert_test_router_exc}")
# === SIGMALYTIC CONTROLLED EMAIL ALERT TEST ROUTER END ===

# SIGMALYTIC_STEP87B_R2_READ_ONLY_ENRICHED_CAMPAIGN_TABLE_INCLUDE
try:
    from campaign_enriched_table_api import router as sig87b_r2_enriched_campaign_table_router
except ImportError:
    from backend.campaign_enriched_table_api import router as sig87b_r2_enriched_campaign_table_router

app.include_router(sig87b_r2_enriched_campaign_table_router)
# END_SIGMALYTIC_STEP87B_R2_READ_ONLY_ENRICHED_CAMPAIGN_TABLE_INCLUDE


# SIGMALYTIC_STEP90B_FULL_CAMPAIGN_UNIVERSE_ENRICHMENT_ENGINE_INCLUDE
try:
    from backend.campaign_full_enrichment_api import router as campaign_full_enrichment_router
    app.include_router(campaign_full_enrichment_router)
except Exception as _sig_step90b_full_enrichment_include_error:
    print("STEP90B full campaign universe enrichment include failed:", _sig_step90b_full_enrichment_include_error)
# END_SIGMALYTIC_STEP90B_FULL_CAMPAIGN_UNIVERSE_ENRICHMENT_ENGINE_INCLUDE

# === R4-R14F STRICT WLW MAIN ROUTE BRIDGE START ===
# Directly exposes the R4-R14C strict WLW event-date fact route through the mounted FastAPI app.
# This bridge delegates to backend.campaign_api.r4_r14c_strict_wlw_event_date_facts.
# Boundary: read-only market-data GET only; no Supabase write; no campaign mutation;
# no D3D authorization; no operator-control confirmation; no trade signal; Gamma overlay only.
@app.get("/api/reports/strict-wlw/event-date-facts")
def r4_r14f_strict_wlw_event_date_facts_main_bridge(
    symbols: str = "",
    lookback_days: int = 730,
    upthrust_trigger_price: str = "",
    upthrust_reference_resistance: str = "",
    spring_trigger_price: str = "",
    spring_reference_support: str = "",
    livermore_long_pivot_price: str = "",
    livermore_short_risk_pivot_price: str = "",
):
    try:
        from backend.campaign_api import r4_r14c_strict_wlw_event_date_facts as _r4_r14c_event_date_facts
    except Exception:
        from campaign_api import r4_r14c_strict_wlw_event_date_facts as _r4_r14c_event_date_facts

    return _r4_r14c_event_date_facts(
        symbols=symbols,
        lookback_days=lookback_days,
        upthrust_trigger_price=upthrust_trigger_price,
        upthrust_reference_resistance=upthrust_reference_resistance,
        spring_trigger_price=spring_trigger_price,
        spring_reference_support=spring_reference_support,
        livermore_long_pivot_price=livermore_long_pivot_price,
        livermore_short_risk_pivot_price=livermore_short_risk_pivot_price,
    )
# === R4-R14F STRICT WLW MAIN ROUTE BRIDGE END ===
