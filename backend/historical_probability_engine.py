# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/historical_probability_engine.py
---------------------------------------
Sigmalytic Historical Probability Engine v1.0

Purpose
-------
Convert the multi-timeframe behavioral attribution dataset into a reusable
probability lookup table.

Input
-----
Default:
    backtests/mtf_phase1_50symbols_2years_daily_weekly/mtf_behavioral_observations.csv

Created by:
    backend/multitimeframe_behavioral_backtest.py

Output
------
Default:
    backend/probability_lookup.json
    backend/probability_lookup.csv
    backend/probability_summary.json

The lookup contains historical profiles such as:

    Weekly Regime + Daily Setup + Behavioral Transition
        matches
        favorable_rate
        tradeable_rate
        expected_return
        expected_mfe
        expected_mae
        edge_ratio
        grade
        opportunity_score

Why this matters
----------------
This is the first version of the evidence layer that allows the app to say:

    "This setup matches 2,183 prior observations.
     Historical opportunity rate: 74%.
     Expected 10D return: +4.1%.
     Edge ratio: 2.6."

Usage
-----
From project root / Render shell:

    python backend/historical_probability_engine.py

With custom paths:

    python backend/historical_probability_engine.py \
      --input backtests/mtf_phase1_50symbols_2years_daily_weekly/mtf_behavioral_observations.csv \
      --output-json backend/probability_lookup.json

Then later radar_service.py can attach this profile to live radar rows.
"""

from __future__ import annotations

import csv
import json
import math
import argparse
import statistics
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def _b(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in {"true", "1", "yes", "y"}


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


def _bucket_composite(score: float) -> str:
    if score >= 80:
        return "80+ Strong"
    if score >= 70:
        return "70-79 Qualified"
    if score >= 60:
        return "60-69 Developing"
    return "<60 Weak"


def _safe_mean(values: List[float]) -> float:
    values = [v for v in values if v is not None and not math.isnan(v)]
    return statistics.mean(values) if values else 0.0


def _safe_median(values: List[float]) -> float:
    values = [v for v in values if v is not None and not math.isnan(v)]
    return statistics.median(values) if values else 0.0


def _sample_confidence(n: int) -> float:
    """
    0-100 sample confidence.
    Full confidence around 500+ matches.
    """
    return max(0.0, min(100.0, n / 500.0 * 100.0))


def _grade_from_score(score: float) -> str:
    if score >= 92:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 78:
        return "A-"
    if score >= 70:
        return "B+"
    if score >= 62:
        return "B"
    if score >= 54:
        return "B-"
    if score >= 46:
        return "C"
    if score >= 38:
        return "D"
    return "Avoid"


def _opportunity_score(
    tradeable_rate: float,
    expected_return: float,
    edge_ratio: float,
    sample_confidence: float,
    favorable_rate: float,
) -> float:
    """
    Composite public-facing opportunity score.

    Weighted to avoid misleading users with only one attractive metric:
      40% tradeable opportunity rate
      25% expected return
      20% edge ratio
      10% favorable rate
      5% sample confidence

    Normalizations:
      tradeable_rate, favorable_rate are already 0-100.
      expected_return: +4% over 10D roughly maps near max.
      edge_ratio: 2.5+ maps near max.
    """
    return_score = max(0.0, min(100.0, (expected_return / 4.0) * 100.0))
    edge_score = max(0.0, min(100.0, (edge_ratio / 2.5) * 100.0))

    score = (
        tradeable_rate * 0.40 +
        return_score * 0.25 +
        edge_score * 0.20 +
        favorable_rate * 0.10 +
        sample_confidence * 0.05
    )
    return round(max(0.0, min(100.0, score)), 1)


def _profile_key(parts: List[str]) -> str:
    return " | ".join(_clean(p) for p in parts)


# ─────────────────────────────────────────────────────────────────────────────
# Load observations
# ─────────────────────────────────────────────────────────────────────────────

def load_rows(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Profile building
# ─────────────────────────────────────────────────────────────────────────────

def build_profile(
    rows: List[dict],
    group_name: str,
    key_fields: List[str],
    window: int = 10,
    min_count: int = 20,
) -> List[dict]:
    """
    Build probability profiles by grouping rows on key_fields.
    """
    groups: Dict[str, List[dict]] = {}

    for r in rows:
        if r.get(f"return_{window}d") in (None, ""):
            continue

        key_parts = []
        for field in key_fields:
            if field == "readiness_bucket":
                key_parts.append(_bucket_readiness(_f(r.get("readiness_score"))))
            elif field == "composite_bucket":
                key_parts.append(_bucket_composite(_f(r.get("composite_score"))))
            else:
                key_parts.append(_clean(r.get(field)))

        key = _profile_key(key_parts)
        groups.setdefault(key, []).append(r)

    profiles = []

    for key, items in groups.items():
        n = len(items)
        if n < min_count:
            continue

        returns = [_f(x.get(f"return_{window}d")) for x in items]
        mfes = [_f(x.get(f"mfe_{window}d")) for x in items]
        maes = [_f(x.get(f"mae_{window}d")) for x in items]

        favorable = sum(1 for x in items if _b(x.get(f"favorable_{window}d")))
        tradeable = sum(1 for x in items if _b(x.get(f"tradeable_{window}d")))

        favorable_rate = round(favorable / n * 100.0, 1)
        tradeable_rate = round(tradeable / n * 100.0, 1)

        avg_return = round(_safe_mean(returns), 3)
        median_return = round(_safe_median(returns), 3)
        avg_mfe = round(_safe_mean(mfes), 3)
        avg_mae = round(_safe_mean(maes), 3)
        edge_ratio = round(avg_mfe / max(avg_mae, 0.01), 2)
        sample_conf = round(_sample_confidence(n), 1)

        score = _opportunity_score(
            tradeable_rate=tradeable_rate,
            expected_return=avg_return,
            edge_ratio=edge_ratio,
            sample_confidence=sample_conf,
            favorable_rate=favorable_rate,
        )
        grade = _grade_from_score(score)

        profile = {
            "profile_type": group_name,
            "key": key,
            "key_fields": key_fields,
            "window_days": window,
            "matches": n,

            "favorable_rate": favorable_rate,
            "tradeable_rate": tradeable_rate,
            "expected_return": avg_return,
            "median_return": median_return,
            "expected_mfe": avg_mfe,
            "expected_mae": avg_mae,
            "edge_ratio": edge_ratio,
            "sample_confidence": sample_conf,

            "opportunity_score": score,
            "grade": grade,
        }

        # Include exact field values for easier lookup later.
        for i, field in enumerate(key_fields):
            values = key.split(" | ")
            profile[field] = values[i] if i < len(values) else "Unknown"

        profiles.append(profile)

    profiles.sort(
        key=lambda x: (
            x["opportunity_score"],
            x["tradeable_rate"],
            x["expected_return"],
            x["matches"],
        ),
        reverse=True,
    )
    return profiles


def build_all_profiles(rows: List[dict], window: int, min_count: int) -> Dict[str, Any]:
    """
    Build several levels of probability lookup.

    The lookup is hierarchical:
      1. Strict profile:
         weekly_regime + setup_type + transition_candidate + readiness_bucket
      2. Setup profile:
         weekly_regime + setup_type + transition_candidate
      3. Broader profile:
         weekly_regime + setup_type
      4. Transition only:
         transition_candidate
      5. Readiness bucket:
         readiness_bucket
    """
    definitions = [
        (
            "strict_weekly_setup_transition_readiness",
            ["weekly_regime", "setup_type", "transition_candidate", "readiness_bucket"],
        ),
        (
            "weekly_setup_transition",
            ["weekly_regime", "setup_type", "transition_candidate"],
        ),
        (
            "weekly_setup",
            ["weekly_regime", "setup_type"],
        ),
        (
            "setup_transition",
            ["setup_type", "transition_candidate"],
        ),
        (
            "transition_only",
            ["transition_candidate"],
        ),
        (
            "setup_only",
            ["setup_type"],
        ),
        (
            "weekly_regime_only",
            ["weekly_regime"],
        ),
        (
            "readiness_bucket",
            ["readiness_bucket"],
        ),
        (
            "opportunity_state",
            ["opportunity_state"],
        ),
    ]

    profiles_by_type = {}
    all_profiles = []

    for profile_type, fields in definitions:
        # Strict groups need lower min count or almost nothing will appear.
        local_min = min_count
        if profile_type == "strict_weekly_setup_transition_readiness":
            local_min = max(10, min_count // 2)

        profiles = build_profile(
            rows=rows,
            group_name=profile_type,
            key_fields=fields,
            window=window,
            min_count=local_min,
        )
        profiles_by_type[profile_type] = profiles
        all_profiles.extend(profiles)

    best_profiles = sorted(
        all_profiles,
        key=lambda x: (x["opportunity_score"], x["tradeable_rate"], x["matches"]),
        reverse=True,
    )[:100]

    return {
        "metadata": {
            "engine": "Sigmalytic Historical Probability Engine",
            "version": "1.0",
            "rows_loaded": len(rows),
            "window_days": window,
            "min_count": min_count,
            "profile_types": list(profiles_by_type.keys()),
            "definition": {
                "tradeable_rate": "Percent of historical setups where MFE met threshold and exceeded MAE.",
                "favorable_rate": "Percent of historical setups with positive forward return.",
                "expected_return": f"Average forward return over {window} trading days.",
                "expected_mfe": f"Average maximum favorable excursion over {window} trading days.",
                "expected_mae": f"Average maximum adverse excursion over {window} trading days.",
                "edge_ratio": "Expected MFE divided by expected MAE.",
                "opportunity_score": "Composite 0-100 score based on tradeable rate, expected return, edge ratio, favorable rate, and sample confidence.",
            },
        },
        "profiles_by_type": profiles_by_type,
        "best_profiles": best_profiles,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Lookup helper for live integration
# ─────────────────────────────────────────────────────────────────────────────

def find_best_profile_for_row(row: dict, lookup: dict) -> dict:
    """
    This helper is intended for radar_service.py later.

    It tries strict profile first, then broader fallbacks.
    """
    profiles_by_type = lookup.get("profiles_by_type", {})

    readiness_bucket = _bucket_readiness(_f(row.get("readiness_score")))
    candidates = [
        (
            "strict_weekly_setup_transition_readiness",
            [
                _clean(row.get("weekly_regime")),
                _clean(row.get("setup_type")),
                _clean(row.get("transition_candidate")),
                readiness_bucket,
            ],
        ),
        (
            "weekly_setup_transition",
            [
                _clean(row.get("weekly_regime")),
                _clean(row.get("setup_type")),
                _clean(row.get("transition_candidate")),
            ],
        ),
        (
            "weekly_setup",
            [
                _clean(row.get("weekly_regime")),
                _clean(row.get("setup_type")),
            ],
        ),
        (
            "setup_transition",
            [
                _clean(row.get("setup_type")),
                _clean(row.get("transition_candidate")),
            ],
        ),
        (
            "transition_only",
            [_clean(row.get("transition_candidate"))],
        ),
        (
            "setup_only",
            [_clean(row.get("setup_type"))],
        ),
        (
            "readiness_bucket",
            [readiness_bucket],
        ),
    ]

    for profile_type, parts in candidates:
        key = _profile_key(parts)
        profiles = profiles_by_type.get(profile_type, [])
        for p in profiles:
            if p.get("key") == key:
                out = dict(p)
                out["lookup_match_type"] = profile_type
                return out

    return {
        "lookup_match_type": "none",
        "matches": 0,
        "tradeable_rate": None,
        "favorable_rate": None,
        "expected_return": None,
        "expected_mfe": None,
        "expected_mae": None,
        "edge_ratio": None,
        "opportunity_score": None,
        "grade": "Unrated",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Write outputs
# ─────────────────────────────────────────────────────────────────────────────

def write_lookup_csv(path: Path, profiles: List[dict]):
    if not profiles:
        path.write_text("", encoding="utf-8")
        return

    fields = sorted(set().union(*(p.keys() for p in profiles)))
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for p in profiles:
            w.writerow(p)


def write_outputs(lookup: dict, output_json: Path, output_csv: Path, summary_json: Path):
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary_json.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(lookup, indent=2), encoding="utf-8")

    all_profiles = []
    for profiles in lookup.get("profiles_by_type", {}).values():
        all_profiles.extend(profiles)
    write_lookup_csv(output_csv, all_profiles)

    summary = {
        "metadata": lookup.get("metadata", {}),
        "profile_counts": {
            k: len(v) for k, v in lookup.get("profiles_by_type", {}).items()
        },
        "best_profiles": lookup.get("best_profiles", [])[:25],
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def run(args):
    input_path = Path(args.input)
    output_json = Path(args.output_json)
    output_csv = Path(args.output_csv)
    summary_json = Path(args.summary_json)

    print("Starting Historical Probability Engine")
    print(f"Input:       {input_path}")
    print(f"Output JSON: {output_json}")
    print(f"Output CSV:  {output_csv}")
    print(f"Summary:     {summary_json}")
    print(f"Window:      {args.window}D")
    print(f"Min count:   {args.min_count}")
    print("-" * 80)

    rows = load_rows(input_path)
    print(f"Rows loaded: {len(rows)}")

    lookup = build_all_profiles(
        rows=rows,
        window=args.window,
        min_count=args.min_count,
    )

    write_outputs(lookup, output_json, output_csv, summary_json)

    print("-" * 80)
    print("Probability lookup created.")
    print("Profile counts:")
    for k, v in lookup.get("profiles_by_type", {}).items():
        print(f"  {k}: {len(v)}")

    print("\nBest profiles preview:")
    print(json.dumps(lookup.get("best_profiles", [])[:10], indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="backtests/mtf_phase1_50symbols_2years_daily_weekly/mtf_behavioral_observations.csv",
    )
    parser.add_argument(
        "--output-json",
        default="backend/probability_lookup.json",
    )
    parser.add_argument(
        "--output-csv",
        default="backend/probability_lookup.csv",
    )
    parser.add_argument(
        "--summary-json",
        default="backend/probability_summary.json",
    )
    parser.add_argument("--window", type=int, default=10)
    parser.add_argument("--min-count", type=int, default=20)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
