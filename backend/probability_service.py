# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/probability_service.py
------------------------------
Sigmalytic Live Historical Probability Service v1.1

Purpose:
    Attach historical probability profiles to live radar opportunities.

Reads:
    backend/probability_lookup.json

Created by:
    backend/historical_probability_engine.py

Adds trader-facing fields:
    historical_success
    expected_return
    expected_mfe
    expected_mae
    edge_ratio
    historical_matches
    probability_grade
    expected_opportunity_score
    probability_confidence
    probability_match_type
    probability_profile_key

v1.1 Fix:
    Live radar rows may not include useful setup_type or weekly_regime.
    If missing, blank, Unknown, or Insufficient Data, this service now infers:

        probability_setup_type
        probability_weekly_regime

    from available live fields before matching the historical lookup.

This prevents every symbol from falling back to:
    transition_only
    48.6%
    440 matches

and allows more specific matches like:
    weekly_setup_transition
    setup_transition
    weekly_setup
"""

from __future__ import annotations

import os
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional


_LOOKUP_CACHE: Optional[dict] = None
_LOOKUP_MTIME: Optional[float] = None
_LOOKUP_PATH = Path(os.getenv("PROBABILITY_LOOKUP_PATH", "backend/probability_lookup.json"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


def _clean(x: Any, default: str = "Unknown") -> str:
    if x is None:
        return default
    s = str(x).strip()
    return s if s else default


def _bad_field(x: Any) -> bool:
    s = _clean(x).lower()
    return s in {
        "",
        "unknown",
        "none",
        "null",
        "n/a",
        "na",
        "insufficient data",
        "insufficient weekly data",
        "not available",
    }


def _bucket_readiness(score: float) -> str:
    if score >= 90:
        return "90+ Elite"
    if score >= 80:
        return "80-89 High"
    if score >= 70:
        return "70-79 Qualified"
    if score >= 60:
        return "60-69 Developing"
    return "<60 Low"


def _profile_key(parts: list) -> str:
    return " | ".join(_clean(p) for p in parts)


def _confidence_label(matches: int) -> str:
    if matches >= 500:
        return "Institutional"
    if matches >= 250:
        return "High"
    if matches >= 100:
        return "Good"
    if matches >= 50:
        return "Moderate"
    if matches >= 25:
        return "Low"
    if matches >= 10:
        return "Very Low"
    return "Insufficient"


def _unrated(reason: str = "Probability lookup unavailable") -> dict:
    return {
        "probability_available": False,
        "probability_reason": reason,
        "probability_match_type": "none",
        "probability_profile_key": None,

        "historical_matches": 0,
        "historical_success": None,
        "historical_favorable_rate": None,
        "expected_return": None,
        "expected_mfe": None,
        "expected_mae": None,
        "edge_ratio": None,

        "expected_opportunity_score": None,
        "probability_grade": "Unrated",
        "probability_confidence": "Insufficient",

        "probability_setup_type": None,
        "probability_weekly_regime": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Live inference
# ─────────────────────────────────────────────────────────────────────────────

def infer_live_setup_type(row: dict) -> str:
    """
    Infer setup_type from live radar fields when setup_type is missing or bad.

    This intentionally mirrors the daily attribution categories:
        Trend Continuation
        Momentum Leader
        Compression Breakout Candidate
        Volatility Expansion Candidate
        Breakdown Risk
        Distribution
        Low Edge — Avoid
        Monitoring
    """
    existing = row.get("setup_type")
    if not _bad_field(existing):
        return _clean(existing)

    status = _clean(row.get("status")).lower()
    regime = _clean(row.get("regime")).lower()
    behavioral_state = _clean(row.get("behavioral_state")).lower()
    transition = _clean(row.get("transition_candidate")).lower()

    price = _f(row.get("price"))
    change_pct = _f(row.get("change_pct"))
    rel_volume = _f(row.get("rel_volume"), 1.0)
    expansion = _f(row.get("expansion_node"))
    rs = _f(row.get("relative_strength"))
    volume_pressure = _f(row.get("volume_pressure"))
    readiness = _f(row.get("readiness_score"))
    composite = _f(row.get("composite_score", row.get("score")))

    trigger = _f(row.get("trigger"))
    trigger_distance = None
    if price > 0 and trigger > 0:
        trigger_distance = (trigger - price) / price * 100.0

    # Direct bearish classifications.
    if "short" in status or "breakdown" in transition or "markdown" in transition:
        return "Breakdown Risk"

    if "distribution" in status or "distribution" in regime or "distribution" in behavioral_state:
        return "Distribution"

    # Trend continuation / momentum.
    if (
        "bull expansion" in regime
        and readiness >= 80
        and composite >= 70
        and rs >= 65
        and volume_pressure >= 60
    ):
        if change_pct >= 1.0 or rel_volume >= 1.2:
            return "Trend Continuation"

    if (
        "markup" in transition
        or "markup" in behavioral_state
        or "bull expansion" in regime
    ):
        if readiness >= 75 and rs >= 60:
            return "Momentum Leader"

    # Compression / expansion candidates.
    if (
        "compression" in transition
        or "compression" in behavioral_state
        or "compression" in status
        or "compression" in regime
    ):
        if trigger_distance is not None and -0.5 <= trigger_distance <= 3.0:
            return "Compression Breakout Candidate"
        return "Volatility Expansion Candidate"

    if expansion >= 65 and readiness >= 70:
        if trigger_distance is not None and -0.5 <= trigger_distance <= 3.0:
            return "Compression Breakout Candidate"
        return "Volatility Expansion Candidate"

    if readiness < 55 and composite < 60:
        return "Low Edge — Avoid"

    return "Monitoring"


def infer_live_weekly_regime(row: dict) -> str:
    """
    Approximate weekly regime from live daily/radar fields.

    This is a bridge until radar_service.py calculates true weekly OHLCV regime.
    It allows the probability engine to avoid transition-only fallback.
    """
    existing = row.get("weekly_regime")
    if not _bad_field(existing):
        return _clean(existing)

    regime = _clean(row.get("regime")).lower()
    status = _clean(row.get("status")).lower()
    behavioral_state = _clean(row.get("behavioral_state")).lower()
    transition = _clean(row.get("transition_candidate")).lower()

    change_pct = _f(row.get("change_pct"))
    rel_volume = _f(row.get("rel_volume"), 1.0)
    readiness = _f(row.get("readiness_score"))
    composite = _f(row.get("composite_score", row.get("score")))
    rs = _f(row.get("relative_strength"))
    volume_pressure = _f(row.get("volume_pressure"))

    if "bear expansion" in regime or "markdown" in transition or "markdown" in behavioral_state:
        if rel_volume >= 1.4 and change_pct <= -3:
            return "Weekly Capitulation / Markdown"
        return "Weekly Markdown"

    if "bear rally" in regime:
        return "Weekly Bear Rally / Recovery Attempt"

    if "distribution" in regime or "distribution" in status or "upthrust" in transition:
        return "Weekly Distribution Risk"

    if (
        "bull expansion" in regime
        and rel_volume >= 1.3
        and change_pct >= 2.0
        and readiness >= 80
    ):
        return "Weekly FOMO / Expansion"

    if "bull expansion" in regime or "markup" in transition or "markup" in behavioral_state:
        return "Weekly Markup"

    if "bull pullback" in regime:
        return "Weekly Pullback Within Markup"

    if readiness >= 85 and composite >= 75 and rs >= 65 and volume_pressure >= 60:
        return "Weekly Markup"

    return "Weekly Neutral"


def enrich_live_probability_keys(row: dict) -> dict:
    """
    Return a copy of row with inferred lookup keys added.
    """
    out = dict(row or {})
    out["probability_setup_type"] = infer_live_setup_type(out)
    out["probability_weekly_regime"] = infer_live_weekly_regime(out)

    # If setup_type / weekly_regime are missing/bad, populate them for downstream use.
    if _bad_field(out.get("setup_type")):
        out["setup_type"] = out["probability_setup_type"]

    if _bad_field(out.get("weekly_regime")):
        out["weekly_regime"] = out["probability_weekly_regime"]

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Lookup loading
# ─────────────────────────────────────────────────────────────────────────────

def load_probability_lookup(force: bool = False) -> dict:
    global _LOOKUP_CACHE, _LOOKUP_MTIME

    try:
        path = _LOOKUP_PATH
        if not path.exists():
            alt = Path(__file__).resolve().parent / "probability_lookup.json"
            if alt.exists():
                path = alt
            else:
                return {}

        mtime = path.stat().st_mtime
        if not force and _LOOKUP_CACHE is not None and _LOOKUP_MTIME == mtime:
            return _LOOKUP_CACHE

        with path.open("r", encoding="utf-8") as f:
            _LOOKUP_CACHE = json.load(f)

        _LOOKUP_MTIME = mtime
        return _LOOKUP_CACHE or {}

    except Exception:
        return {}


def probability_status() -> dict:
    lookup = load_probability_lookup()
    meta = lookup.get("metadata", {}) if isinstance(lookup, dict) else {}
    profiles = lookup.get("profiles_by_type", {}) if isinstance(lookup, dict) else {}
    return {
        "available": bool(lookup),
        "path": str(_LOOKUP_PATH),
        "rows_loaded": meta.get("rows_loaded"),
        "window_days": meta.get("window_days"),
        "profile_counts": {k: len(v or []) for k, v in profiles.items()},
        "loaded_at": time.time(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Matching
# ─────────────────────────────────────────────────────────────────────────────

def _find_profile(row: dict, lookup: dict) -> dict:
    if not lookup:
        return {}

    row = enrich_live_probability_keys(row)

    profiles_by_type = lookup.get("profiles_by_type", {})
    readiness_bucket = _bucket_readiness(_f(row.get("readiness_score")))

    weekly = _clean(row.get("weekly_regime"))
    setup = _clean(row.get("setup_type"))
    transition = _clean(row.get("transition_candidate"))
    opportunity_state = _clean(row.get("opportunity_state"))

    candidates = [
        (
            "strict_weekly_setup_transition_readiness",
            [weekly, setup, transition, readiness_bucket],
        ),
        (
            "weekly_setup_transition",
            [weekly, setup, transition],
        ),
        (
            "weekly_setup",
            [weekly, setup],
        ),
        (
            "setup_transition",
            [setup, transition],
        ),
        (
            "weekly_regime_only",
            [weekly],
        ),
        (
            "transition_only",
            [transition],
        ),
        (
            "setup_only",
            [setup],
        ),
        (
            "opportunity_state",
            [opportunity_state],
        ),
        (
            "readiness_bucket",
            [readiness_bucket],
        ),
    ]

    attempted = []
    for profile_type, parts in candidates:
        key = _profile_key(parts)
        attempted.append(f"{profile_type}: {key}")
        for p in profiles_by_type.get(profile_type, []) or []:
            if p.get("key") == key:
                out = dict(p)
                out["lookup_match_type"] = profile_type
                out["lookup_attempted_keys"] = attempted[:]
                out["inferred_setup_type"] = setup
                out["inferred_weekly_regime"] = weekly
                return out

    return {
        "lookup_attempted_keys": attempted,
        "inferred_setup_type": setup,
        "inferred_weekly_regime": weekly,
    }


def get_probability_profile(row: dict) -> dict:
    try:
        enriched_row = enrich_live_probability_keys(row or {})

        lookup = load_probability_lookup()
        if not lookup:
            unrated = _unrated("probability_lookup.json not found")
            unrated["probability_setup_type"] = enriched_row.get("probability_setup_type")
            unrated["probability_weekly_regime"] = enriched_row.get("probability_weekly_regime")
            return unrated

        profile = _find_profile(enriched_row, lookup)
        if not profile or not profile.get("key"):
            unrated = _unrated("no matching historical profile")
            unrated["probability_setup_type"] = enriched_row.get("probability_setup_type")
            unrated["probability_weekly_regime"] = enriched_row.get("probability_weekly_regime")
            unrated["probability_attempted_keys"] = profile.get("lookup_attempted_keys") if profile else []
            return unrated

        matches = int(_f(profile.get("matches"), 0))
        confidence = _confidence_label(matches)

        return {
            "probability_available": True,
            "probability_reason": "matched historical profile",
            "probability_match_type": profile.get("lookup_match_type", profile.get("profile_type")),
            "probability_profile_type": profile.get("profile_type"),
            "probability_profile_key": profile.get("key"),

            "historical_matches": matches,
            "historical_success": profile.get("tradeable_rate"),
            "historical_favorable_rate": profile.get("favorable_rate"),
            "expected_return": profile.get("expected_return"),
            "expected_mfe": profile.get("expected_mfe"),
            "expected_mae": profile.get("expected_mae"),
            "edge_ratio": profile.get("edge_ratio"),

            "expected_opportunity_score": profile.get("opportunity_score"),
            "probability_grade": profile.get("grade", "Unrated"),
            "probability_confidence": confidence,

            "probability_window_days": profile.get("window_days"),
            "sample_confidence": profile.get("sample_confidence"),

            "probability_setup_type": enriched_row.get("probability_setup_type"),
            "probability_weekly_regime": enriched_row.get("probability_weekly_regime"),
            "probability_attempted_keys": profile.get("lookup_attempted_keys", []),

            "historical_probability_profile": profile,
        }

    except Exception as e:
        return _unrated(f"probability service error: {e}")


def attach_probability_profile(row: dict) -> dict:
    if not row or not isinstance(row, dict):
        return row

    out = enrich_live_probability_keys(row)
    out.update(get_probability_profile(out))
    return out
