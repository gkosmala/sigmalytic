# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/probability_service.py
------------------------------
Sigmalytic Live Historical Probability Service v1.3 — Strict Probability Matching

Key Fix:
    Render container storage is temporary. probability_lookup.json may disappear
    after restart/redeploy.

    This version automatically rebuilds the probability lookup when missing.

What it does:
    1. Looks for backend/probability_lookup.json
    2. If missing, looks for the attribution CSV
    3. If CSV is missing, runs:
         python backend/multitimeframe_behavioral_backtest.py --symbols-file backend/backtest_symbols_50.txt --years 2
    4. Then runs:
         python backend/historical_probability_engine.py
    5. Loads backend/probability_lookup.json
"""

from __future__ import annotations

import os
import json
import time
import sys
import subprocess
from pathlib import Path
from typing import Any, Optional


_LOOKUP_CACHE: Optional[dict] = None
_LOOKUP_MTIME: Optional[float] = None
_BUILD_ATTEMPTED = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = Path(__file__).resolve().parent

_LOOKUP_PATH = Path(os.getenv("PROBABILITY_LOOKUP_PATH", str(BACKEND_DIR / "probability_lookup.json")))
_OBSERVATIONS_PATH = Path(os.getenv(
    "PROBABILITY_OBSERVATIONS_PATH",
    str(PROJECT_ROOT / "backtests/mtf_phase1_50symbols_2years_daily_weekly/mtf_behavioral_observations.csv")
))
_SYMBOLS_FILE = Path(os.getenv("PROBABILITY_SYMBOLS_FILE", str(BACKEND_DIR / "backtest_symbols_50.txt")))
_AUTO_BUILD = os.getenv("PROBABILITY_AUTO_BUILD", "1").strip().lower() not in {"0", "false", "no"}


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
    return s in {"", "unknown", "none", "null", "n/a", "na", "insufficient data", "insufficient weekly data", "not available"}


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



def _bucket_rs(score: float) -> str:
    if score >= 80:
        return "RS80+"
    if score >= 70:
        return "RS70-79"
    if score >= 60:
        return "RS60-69"
    return "RS<60"


def _bucket_expansion(score: float) -> str:
    if score >= 80:
        return "EXP80+"
    if score >= 70:
        return "EXP70-79"
    if score >= 60:
        return "EXP60-69"
    return "EXP<60"


def _bucket_volume(score: float) -> str:
    if score >= 80:
        return "VOL80+"
    if score >= 70:
        return "VOL70-79"
    if score >= 60:
        return "VOL60-69"
    return "VOL<60"


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



def _sigmalytic_edge_score(profile: dict) -> int:
    score = (
        _f(profile.get("opportunity_score")) * 0.40
        + min(_f(profile.get("edge_ratio")) * 12.0, 25.0)
        + min(_f(profile.get("expected_return")) * 4.0, 20.0)
        + min(_f(profile.get("sample_confidence")) * 2.0, 15.0)
    )
    return int(max(0, min(round(score), 100)))


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
        "edge_score": None,
    }


def _run_cmd(cmd: list[str], timeout: int = 600) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        output = (p.stdout or "") + "\n" + (p.stderr or "")
        return p.returncode == 0, output[-4000:]
    except Exception as e:
        return False, str(e)


def ensure_probability_lookup() -> dict:
    global _BUILD_ATTEMPTED

    if _LOOKUP_PATH.exists():
        return {"created": False, "available": True, "reason": "lookup exists"}

    if not _AUTO_BUILD:
        return {"created": False, "available": False, "reason": "auto build disabled"}

    if _BUILD_ATTEMPTED:
        return {"created": False, "available": _LOOKUP_PATH.exists(), "reason": "build already attempted"}

    _BUILD_ATTEMPTED = True

    if not _OBSERVATIONS_PATH.exists():
        if not _SYMBOLS_FILE.exists():
            return {"created": False, "available": False, "reason": f"symbols file missing: {_SYMBOLS_FILE}"}

        ok, out = _run_cmd([
            sys.executable,
            str(BACKEND_DIR / "multitimeframe_behavioral_backtest.py"),
            "--symbols-file",
            str(_SYMBOLS_FILE),
            "--years",
            os.getenv("PROBABILITY_BACKTEST_YEARS", "2"),
        ], timeout=int(os.getenv("PROBABILITY_BACKTEST_TIMEOUT", "900")))

        if not ok:
            return {"created": False, "available": False, "reason": f"backtest rebuild failed: {out}"}

    ok, out = _run_cmd([
        sys.executable,
        str(BACKEND_DIR / "historical_probability_engine.py"),
        "--input",
        str(_OBSERVATIONS_PATH),
        "--output-json",
        str(_LOOKUP_PATH),
        "--output-csv",
        str(BACKEND_DIR / "probability_lookup.csv"),
        "--summary-json",
        str(BACKEND_DIR / "probability_summary.json"),
    ], timeout=int(os.getenv("PROBABILITY_ENGINE_TIMEOUT", "300")))

    if not ok:
        return {"created": False, "available": False, "reason": f"probability engine failed: {out}"}

    return {"created": True, "available": _LOOKUP_PATH.exists(), "reason": "lookup rebuilt automatically"}


def infer_live_setup_type(row: dict) -> str:
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

    if "short" in status or "breakdown" in transition or "markdown" in transition:
        return "Breakdown Risk"

    if "distribution" in status or "distribution" in regime or "distribution" in behavioral_state:
        return "Distribution"

    if "bull expansion" in regime and readiness >= 80 and composite >= 70 and rs >= 65 and volume_pressure >= 60:
        if change_pct >= 1.0 or rel_volume >= 1.2:
            return "Trend Continuation"

    if ("markup" in transition or "markup" in behavioral_state or "bull expansion" in regime) and readiness >= 75 and rs >= 60:
        return "Momentum Leader"

    if "compression" in transition or "compression" in behavioral_state or "compression" in status or "compression" in regime:
        if trigger_distance is not None and -0.5 <= trigger_distance <= 3.0:
            return "Compression Breakout Candidate"
        return "Volatility Expansion Candidate"

    if expansion >= 65 and readiness >= 70:
        if trigger_distance is not None and -0.5 <= trigger_distance <= 3.0:
            return "Compression Breakout Candidate"
        return "Volatility Expansion Candidate"

    if readiness < 55 and composite < 60:
        return "Low Edge - Avoid"

    return "Monitoring"


def infer_live_weekly_regime(row: dict) -> str:
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

    if "bull expansion" in regime and rel_volume >= 1.3 and change_pct >= 2.0 and readiness >= 80:
        return "Weekly FOMO / Expansion"

    if "bull expansion" in regime or "markup" in transition or "markup" in behavioral_state:
        return "Weekly Markup"

    if "bull pullback" in regime:
        return "Weekly Pullback Within Markup"

    if readiness >= 85 and composite >= 75 and rs >= 65 and volume_pressure >= 60:
        return "Weekly Markup"

    return "Weekly Neutral"


def enrich_live_probability_keys(row: dict) -> dict:
    out = dict(row or {})
    out["probability_setup_type"] = infer_live_setup_type(out)
    out["probability_weekly_regime"] = infer_live_weekly_regime(out)

    if _bad_field(out.get("setup_type")):
        out["setup_type"] = out["probability_setup_type"]

    if _bad_field(out.get("weekly_regime")):
        out["weekly_regime"] = out["probability_weekly_regime"]

    return out


def load_probability_lookup(force: bool = False) -> dict:
    global _LOOKUP_CACHE, _LOOKUP_MTIME

    try:
        if not _LOOKUP_PATH.exists():
            ensure_probability_lookup()

        if not _LOOKUP_PATH.exists():
            return {}

        mtime = _LOOKUP_PATH.stat().st_mtime
        if not force and _LOOKUP_CACHE is not None and _LOOKUP_MTIME == mtime:
            return _LOOKUP_CACHE

        with _LOOKUP_PATH.open("r", encoding="utf-8") as f:
            _LOOKUP_CACHE = json.load(f)

        _LOOKUP_MTIME = mtime
        return _LOOKUP_CACHE or {}

    except Exception:
        return {}


def probability_status() -> dict:
    ensure = ensure_probability_lookup()
    lookup = load_probability_lookup()
    meta = lookup.get("metadata", {}) if isinstance(lookup, dict) else {}
    profiles = lookup.get("profiles_by_type", {}) if isinstance(lookup, dict) else {}

    return {
        "available": bool(lookup),
        "path": str(_LOOKUP_PATH),
        "observations_path": str(_OBSERVATIONS_PATH),
        "auto_build": _AUTO_BUILD,
        "ensure": ensure,
        "rows_loaded": meta.get("rows_loaded"),
        "window_days": meta.get("window_days"),
        "profile_counts": {k: len(v or []) for k, v in profiles.items()},
        "loaded_at": time.time(),
    }


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

    rs_bucket = _bucket_rs(_f(row.get("relative_strength")))
    expansion_bucket = _bucket_expansion(_f(row.get("expansion_node")))
    volume_bucket = _bucket_volume(_f(row.get("volume_pressure")))

    candidates = [
        # STRICT MATCH ONLY.
        #
        # This prevents broad probability profiles such as:
        #   Weekly Markup | Momentum Leader
        #   Weekly Neutral
        #   Weekly Neutral | Volatility Expansion Candidate
        # from being assigned to unrelated symbols.
        #
        # A live symbol must match the full 7-part historical profile:
        # weekly regime + setup + transition + readiness + RS + expansion + volume.
        # If no strict profile exists, the symbol remains Unrated.
        (
            "strict_weekly_setup_transition_readiness",
            [
                weekly,
                setup,
                transition,
                readiness_bucket,
                rs_bucket,
                expansion_bucket,
                volume_bucket,
            ],
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

                # Safety control:
                # Strict matches may keep the historical profile as-is.
                # Controlled fallback matches are useful context, but they are
                # not specific enough to display as institutional-grade edge.
                # This prevents broad profiles like:
                #   Weekly Markup | Momentum Leader
                # from assigning identical high probability / expected return
                # / edge values to many unrelated live symbols.
                if profile_type in {"weekly_setup_transition", "setup_transition"}:
                    out["broad_match_warning"] = True
                    out["probability_context_only"] = True

                    # Downgrade confidence on broad contextual matches.
                    out["sample_confidence"] = min(_f(out.get("sample_confidence")), 45.0)

                    # Cap broad fallback outputs so they cannot look like an
                    # elite strict historical profile. The original profile is
                    # preserved in historical_probability_profile for audit.
                    out["expected_return"] = min(_f(out.get("expected_return")), 65.0)
                    out["expected_mfe"] = min(_f(out.get("expected_mfe")), 65.0)
                    out["edge_ratio"] = min(_f(out.get("edge_ratio")), 3.0)

                    # Keep matches but prevent match count from creating an
                    # "Institutional" confidence label for broad context.
                    out["matches"] = min(int(_f(out.get("matches"), 0)), 99)

                    # Conservative grade for broad contextual matches.
                    out["grade"] = "B" if _f(out.get("favorable_rate")) >= 0.60 else "C"

                return out

    return {"lookup_attempted_keys": attempted, "inferred_setup_type": setup, "inferred_weekly_regime": weekly}


def get_probability_profile(row: dict) -> dict:
    try:
        enriched_row = enrich_live_probability_keys(row or {})
        lookup = load_probability_lookup()

        if not lookup:
            unrated = _unrated("probability_lookup.json not found and auto-build failed")
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
            "probability_context_only": profile.get("probability_context_only", False),
            "broad_match_warning": profile.get("broad_match_warning", False),
            "historical_probability_profile": profile,
            "edge_score": _sigmalytic_edge_score(profile),
        }

    except Exception as e:
        return _unrated(f"probability service error: {e}")


def attach_probability_profile(row: dict) -> dict:
    if not row or not isinstance(row, dict):
        return row

    out = enrich_live_probability_keys(row)
    out.update(get_probability_profile(out))
    return out

