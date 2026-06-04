# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/probability_service.py
------------------------------
Sigmalytic Live Historical Probability Service v1.0

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

This file is safe:
    - If probability_lookup.json is missing, it returns an unrated profile.
    - It never crashes radar_service.py.
    - It can reload when the JSON file changes.
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
    """
    Trader-facing sample confidence.

    This is intentionally separate from the opportunity grade.
    A setup can have excellent early results but low sample confidence.
    """
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
    }


def load_probability_lookup(force: bool = False) -> dict:
    """
    Load and cache the probability lookup JSON.
    Reloads automatically if the file changes.
    """
    global _LOOKUP_CACHE, _LOOKUP_MTIME

    try:
        path = _LOOKUP_PATH
        if not path.exists():
            # Try relative to this file's directory as fallback.
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


def _find_profile(row: dict, lookup: dict) -> dict:
    """
    Strict-to-broad fallback matching.

    Important:
        Live radar may not yet contain weekly_regime. When missing, the service
        falls back to setup + transition, transition only, setup only, and
        readiness bucket.
    """
    if not lookup:
        return {}

    profiles_by_type = lookup.get("profiles_by_type", {})
    readiness_bucket = _bucket_readiness(_f(row.get("readiness_score")))

    weekly = _clean(row.get("weekly_regime"))
    setup = _clean(row.get("setup_type"))
    transition = _clean(row.get("transition_candidate"))
    opportunity_state = _clean(row.get("opportunity_state"))

    candidates = []

    # Only use weekly-specific keys if live row actually has weekly regime.
    if weekly != "Unknown":
        candidates.extend([
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
                "weekly_regime_only",
                [weekly],
            ),
        ])

    candidates.extend([
        (
            "setup_transition",
            [setup, transition],
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
    ])

    for profile_type, parts in candidates:
        key = _profile_key(parts)
        for p in profiles_by_type.get(profile_type, []) or []:
            if p.get("key") == key:
                out = dict(p)
                out["lookup_match_type"] = profile_type
                return out

    return {}


def get_probability_profile(row: dict) -> dict:
    """
    Public entry point.

    Returns normalized trader-facing probability fields.
    """
    try:
        lookup = load_probability_lookup()
        if not lookup:
            return _unrated("probability_lookup.json not found")

        profile = _find_profile(row or {}, lookup)
        if not profile:
            return _unrated("no matching historical profile")

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

            # Keep the full profile available for detail cards.
            "historical_probability_profile": profile,
        }

    except Exception as e:
        return _unrated(f"probability service error: {e}")


def attach_probability_profile(row: dict) -> dict:
    """
    Convenience helper:
    Return row + probability fields.
    """
    if not row or not isinstance(row, dict):
        return row

    out = dict(row)
    out.update(get_probability_profile(out))
    return out
