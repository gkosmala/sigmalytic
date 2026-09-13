"""
SAVE AS:
backend/intelligence_api.py

Unified Intelligence API

Lightweight product compatibility implementation.

This module exposes read-only product endpoints for:
- /api/intelligence/dashboard
- /api/intelligence/rankings
- /api/intelligence/status-center
- /api/intelligence/opportunities

Guardrails:
- Does not import or mount backend.radar_service.
- Does not touch Stripe, checkout, billing, payment processing, or webhooks.
- Does not write to Supabase.
- Does not mutate campaigns.
- Does not execute or authorize D3D.
- Does not confirm operator control.
- Does not create trade signals.
"""

from collections import Counter
from datetime import datetime
from fastapi import APIRouter


router = APIRouter(
    prefix="/api/intelligence",
    tags=["intelligence"],
)


def _now():
    return datetime.utcnow().isoformat()


def _guardrails():
    return {
        "read_only": True,
        "diagnostic_only": True,
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
        "d3d_execution_recommendation": "DO_NOT_EXECUTE_D3D",
    }


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _first(source, names, default=None):
    if not isinstance(source, dict):
        return default

    for name in names:
        value = source.get(name)
        if value is not None and value != "":
            return value

    return default


def _load_active_campaigns():
    try:
        from backend.campaign_api import active_campaigns

        payload = active_campaigns()

        if isinstance(payload, dict):
            campaigns = payload.get("campaigns") or payload.get("items") or []
        elif isinstance(payload, list):
            campaigns = payload
        else:
            campaigns = []

        return [item for item in campaigns if isinstance(item, dict)], None

    except Exception as exc:
        return [], f"active_campaigns_error_{str(exc)[:160]}"


def _load_campaign_summary():
    try:
        from backend.campaign_api import status

        payload = status()
        if isinstance(payload, dict):
            return payload, None

        return {}, "campaign_summary_returned_non_dict"

    except Exception as exc:
        return {}, f"campaign_summary_error_{str(exc)[:160]}"


def _load_campaign_rankings():
    try:
        from backend.campaign_api import rankings

        payload = rankings()
        if isinstance(payload, dict):
            campaigns = payload.get("campaigns") or payload.get("items") or []
        elif isinstance(payload, list):
            campaigns = payload
        else:
            campaigns = []

        return [item for item in campaigns if isinstance(item, dict)], None

    except Exception as exc:
        return [], f"campaign_rankings_error_{str(exc)[:160]}"


def _score(campaign):
    value = _first(
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

    if value is None:
        obstacle = _safe_float(campaign.get("obstacle_score"), 0)
        progress = _safe_float(campaign.get("progress_score"), 0)
        value = (obstacle + progress) / 2 if obstacle or progress else 0

    value = _safe_float(value, 0)

    if 0 < value <= 1:
        value = value * 100

    return max(0.0, min(100.0, value))


def _grade(score):
    if score >= 85:
        return "A+"
    if score >= 75:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "W"


def _bias(state):
    state_text = str(state or "").upper()

    if "DISTRIBUTION" in state_text or "CLOSED" in state_text:
        return "BEARISH"

    if state_text in {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}:
        return "BULLISH"

    if state_text == "BIRTH":
        return "WATCH"

    return "NEUTRAL"


def _regime(campaign):
    return str(
        _first(
            campaign,
            ["regime", "current_regime", "weis_gamma_phase", "phase", "layer"],
            "DISCOVERY",
        )
        or "DISCOVERY"
    )


def _campaign_row(campaign):
    symbol = str(_first(campaign, ["symbol", "ticker"], "") or "").upper()
    state = str(_first(campaign, ["current_state", "state", "status"], "BIRTH") or "BIRTH")
    score = _score(campaign)
    price = _safe_float(
        _first(campaign, ["current_price", "price", "last_price", "close"], 0),
        0,
    )
    progress = _safe_float(campaign.get("progress_score"), score)
    obstacle = _safe_float(campaign.get("obstacle_score"), score)

    return {
        "campaign_id": campaign.get("campaign_id"),
        "display_label": campaign.get("display_label"),
        "symbol": symbol,
        "timeframe": str(_first(campaign, ["timeframe"], "DAILY") or "DAILY"),
        "state": state,
        "status": state,
        "bias": _bias(state),
        "regime": _regime(campaign),
        "layer": str(_first(campaign, ["layer"], "DISCOVERY") or "DISCOVERY"),
        "price": round(price, 4),
        "current_price": round(price, 4),
        "composite_score": round(score, 2),
        "score": round(score, 2),
        "grade": _grade(score),
        "obstacle_score": round(obstacle, 2),
        "progress_score": round(progress, 2),
        "duration_days": _safe_int(campaign.get("duration_days"), 0),
        "campaign_age_days": _safe_int(campaign.get("campaign_age_days"), 0),
        "source": "campaign_intelligence_compat",
    }


def _rows_from_campaigns(campaigns):
    rows = [_campaign_row(campaign) for campaign in campaigns]
    rows = [row for row in rows if row.get("symbol")]
    rows.sort(key=lambda row: row.get("composite_score", 0), reverse=True)
    return rows


def _summary_from_rows(rows):
    states = Counter(str(row.get("status") or "UNKNOWN") for row in rows)
    grades = Counter(str(row.get("grade") or "UNKNOWN") for row in rows)

    armed_states = {"CONFIRMED", "SURVIVING", "EXPANDING", "MATURING"}
    armed = sum(1 for row in rows if str(row.get("status") or "").upper() in armed_states)

    avg_score = (
        round(sum(_safe_float(row.get("composite_score"), 0) for row in rows) / len(rows), 2)
        if rows
        else 0
    )

    return {
        "total_campaigns": len(rows),
        "armed": armed,
        "avg_score": avg_score,
        "grade_counts": dict(grades),
        "state_counts": dict(states),
    }


def _active_and_ranked_rows():
    campaigns, active_error = _load_active_campaigns()
    rows = _rows_from_campaigns(campaigns)

    if rows:
        return campaigns, rows, active_error

    ranked_campaigns, ranking_error = _load_campaign_rankings()
    ranked_rows = _rows_from_campaigns(ranked_campaigns)

    combined_error = active_error or ranking_error
    return ranked_campaigns, ranked_rows, combined_error


def _opportunity_rows(rows, limit):
    preferred_states = {"EXPANDING", "SURVIVING", "CONFIRMED", "MATURING"}

    selected = [
        row for row in rows
        if str(row.get("status") or "").upper() in preferred_states
    ]

    if not selected:
        selected = rows

    return selected[:limit]


@router.get("/health")
def health():
    return {
        "ok": True,
        "status": "ok",
        "service": "intelligence_api",
        "source": "lightweight_intelligence_compat",
        "generated_at": _now(),
        "guardrails": _guardrails(),
    }


@router.get("/dashboard")
def dashboard(limit: int = 10):
    campaigns, rows, feed_error = _active_and_ranked_rows()
    campaign_summary, summary_error = _load_campaign_summary()

    return {
        "ok": True,
        "source": "lightweight_intelligence_compat",
        "compatibility_route": "/api/intelligence/dashboard",
        "generated_at": _now(),
        "derived_from": [
            "backend.campaign_api.active_campaigns",
            "backend.campaign_api.status",
        ],
        "campaign_summary": campaign_summary,
        "dashboard": _summary_from_rows(rows),
        "top_campaigns": rows[:limit],
        "campaign_count": len(campaigns),
        "row_count": len(rows),
        "errors": {
            "feed_error": feed_error,
            "summary_error": summary_error,
        },
        "guardrails": _guardrails(),
    }


@router.get("/rankings")
def rankings(limit: int = 50):
    ranked_campaigns, ranking_error = _load_campaign_rankings()
    rows = _rows_from_campaigns(ranked_campaigns)

    if not rows:
        _, rows, fallback_error = _active_and_ranked_rows()
        ranking_error = ranking_error or fallback_error

    return {
        "ok": True,
        "source": "lightweight_intelligence_compat",
        "compatibility_route": "/api/intelligence/rankings",
        "generated_at": _now(),
        "derived_from": "backend.campaign_api.rankings",
        "count": len(rows[:limit]),
        "rankings": rows[:limit],
        "error": ranking_error,
        "guardrails": _guardrails(),
    }


@router.get("/status-center")
def status_center(limit: int = 25):
    _, rows, feed_error = _active_and_ranked_rows()
    campaign_summary, summary_error = _load_campaign_summary()

    return {
        "ok": True,
        "source": "lightweight_intelligence_compat",
        "compatibility_route": "/api/intelligence/status-center",
        "generated_at": _now(),
        "derived_from": [
            "backend.campaign_api.status",
            "backend.campaign_api.active_campaigns",
        ],
        "campaign_summary": campaign_summary,
        "status_center": {
            "summary": _summary_from_rows(rows),
            "weis_gamma_status_center": campaign_summary.get("weis_gamma_status_center")
            if isinstance(campaign_summary, dict)
            else None,
            "sample_campaigns": rows[:limit],
        },
        "errors": {
            "feed_error": feed_error,
            "summary_error": summary_error,
        },
        "guardrails": _guardrails(),
    }


@router.get("/opportunities")
def opportunities(limit: int = 25):
    _, rows, feed_error = _active_and_ranked_rows()
    selected = _opportunity_rows(rows, limit)

    return {
        "ok": True,
        "source": "lightweight_intelligence_compat",
        "compatibility_route": "/api/intelligence/opportunities",
        "generated_at": _now(),
        "derived_from": "backend.campaign_api.active_campaigns",
        "count": len(selected),
        "selection_note": (
            "Read-only product opportunities view. This is not a trade signal, "
            "not D3D authorization, and not operator-control confirmation."
        ),
        "opportunities": selected,
        "error": feed_error,
        "guardrails": _guardrails(),
    }
