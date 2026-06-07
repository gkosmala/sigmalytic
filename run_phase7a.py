#!/usr/bin/env python3
"""
Standalone Phase 7A analysis script.
Reads existing qualified_long_signal_rows.csv and runs Phase 7A obstacle
quartile validation without any Alpaca API calls.
"""

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _safe_float(val: Any) -> Optional[float]:
    try:
        v = float(val)
        return v if math.isfinite(v) else None
    except Exception:
        return None


def _safe_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes")


def _is_target_bucket(r: Dict[str, Any]) -> bool:
    try:
        phase = str(r.get("expansion_phase_bucket", ""))
        relvol = str(r.get("rel_volume_bucket", ""))
        dist = _safe_float(r.get("distance_from_252_high_pct"))
        return (
            phase == "EXP_PHASE_LATE"
            and relvol == "RELVOL_2_0_3_0X"
            and dist is not None
            and dist <= -20.0
        )
    except Exception:
        return False


def _compute_obstacle_score(r: Dict[str, Any]) -> float:
    try:
        dist = abs(float(r.get("distance_from_252_high_pct") or 0))
    except Exception:
        dist = 0.0
    try:
        days = float(r.get("p5_days_since_252_high") or 0)
    except Exception:
        days = 0.0
    try:
        trading_range = _safe_bool(r.get("trading_range_detected"))
        rw = float(r.get("range_width_pct") or 0) if trading_range else 0.0
    except Exception:
        rw = 0.0
    days_norm = days / 5.0
    return round(dist + days_norm + rw, 3)


def _classify_behavioral_state(r: Dict[str, Any]) -> Tuple[str, int]:
    spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
    dei = _safe_bool(r.get("w_demand_efficiency_improving"))
    buy = _safe_bool(r.get("w_buoyancy_near_support"))
    up1 = _safe_float(r.get("w_up1_price_eff")) or 0.0

    if up1 >= 3.0:
        return "STATE_4_EXPANSION", 4
    if buy:
        return "STATE_3_CONFIRMING", 3
    if spd and dei:
        return "STATE_2_EMERGING", 2
    if spd and not dei:
        return "STATE_1_EXHAUSTION", 1
    return "STATE_0_NEUTRAL", 0


def _build_payload(r: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Build outcome payload from flat CSV row."""
    mfe20 = _safe_float(r.get("markup_20d_pct"))
    mfe90 = _safe_float(r.get("markup_90d_pct"))
    if mfe90 is None:
        return None

    mfe20v = mfe20 if mfe20 is not None else 0.0
    mae20 = _safe_float(r.get("h20_mae_pct")) or 0.0
    acc20 = _safe_float(r.get("h20_direction_correct")) or 0.0
    acc90 = _safe_float(r.get("h90_direction_correct")) or 0.0
    ret90 = _safe_float(r.get("h90_return_pct")) or 0.0
    mae90 = _safe_float(r.get("h90_mae_pct")) or 0.0

    asym = (mfe20v / abs(mae20)) if (mfe20v > 0 and mae20 < 0) else 0.0

    return {
        "acc_20d":  acc20,
        "mfe_20d":  mfe20v,
        "mae_20d":  mae20,
        "asym_20d": asym,
        "acc_90d":  acc90,
        "ret_90d":  ret90,
        "mfe_90d":  mfe90,
        "mae_90d":  mae90,
    }


def _summ(bucket_map: Dict[str, List], min_n: int = 5) -> List[Dict[str, Any]]:
    out = []
    for bucket, vals in sorted(bucket_map.items()):
        if len(vals) < min_n:
            continue
        n = len(vals)
        def avg(f): return round(sum(v[f] for v in vals) / n, 3)
        asym_vals = [v["asym_20d"] for v in vals if v["asym_20d"] > 0]
        out.append({
            "bucket":          bucket,
            "signals":         n,
            "acc_20d_pct":     round(avg("acc_20d") * 100, 2),
            "avg_mfe_20d_pct": avg("mfe_20d"),
            "avg_mae_20d_pct": avg("mae_20d"),
            "avg_asym_20d":    round(sum(asym_vals)/len(asym_vals), 3) if asym_vals else None,
            "acc_90d_pct":     round(avg("acc_90d") * 100, 2),
            "avg_ret_90d_pct": avg("ret_90d"),
            "avg_mfe_90d_pct": avg("mfe_90d"),
            "avg_mae_90d_pct": avg("mae_90d"),
        })
    out.sort(key=lambda x: x["avg_mfe_90d_pct"], reverse=True)
    return out


def run(csv_path: str) -> None:
    rows = []
    with open(csv_path, newline="", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"Loaded {len(rows)} rows from {csv_path}")

    # Compute obstacle scores and quartile thresholds
    all_scores = []
    enriched = []
    for r in rows:
        p = _build_payload(r)
        if p is None:
            continue
        obs = _compute_obstacle_score(r)
        state_label, state_num = _classify_behavioral_state(r)
        all_scores.append(obs)
        enriched.append((r, p, obs, state_label, state_num))

    all_scores_sorted = sorted(all_scores)
    n_total = len(all_scores_sorted)
    q1 = all_scores_sorted[n_total // 4]
    q2 = all_scores_sorted[n_total // 2]
    q3 = all_scores_sorted[3 * n_total // 4]

    def obs_q(score):
        if score <= q1: return "OBS_Q1_LOW"
        if score <= q2: return "OBS_Q2_MID_LOW"
        if score <= q3: return "OBS_Q3_MID_HIGH"
        return "OBS_Q4_HIGH"

    print(f"Obstacle score thresholds: Q1<={q1}  Q2<={q2}  Q3<={q3}  Q4>{q3}")

    groups = {
        "state1_x_obstacle":       defaultdict(list),
        "state_baseline":          defaultdict(list),
        "obstacle_baseline":       defaultdict(list),
        "all_states_x_obstacle":   defaultdict(list),
        "duration_x_state":        defaultdict(list),
        "state_x_behavior":        defaultdict(list),
        "obstacle_x_behavior":     defaultdict(list),
        "target_state_x_obstacle": defaultdict(list),
        "spd_dei_x_obstacle":      defaultdict(list),
    }

    for r, p, obs, state_label, state_num in enriched:
        oq = obs_q(obs)
        is_target = _is_target_bucket(r)
        bhv = str(r.get("behavior_classification", "NEUTRAL"))
        days = _safe_float(r.get("p5_days_since_252_high")) or 0.0
        spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
        dei = _safe_bool(r.get("w_demand_efficiency_improving"))

        if days >= 180:   dur = "DUR_180_PLUS"
        elif days >= 120: dur = "DUR_120_180"
        elif days >= 60:  dur = "DUR_60_120"
        elif days >= 20:  dur = "DUR_20_60"
        else:             dur = "DUR_UNDER_20"

        if spd and not dei:
            groups["state1_x_obstacle"][oq].append(p)

        groups["state_baseline"][state_label].append(p)
        groups["obstacle_baseline"][oq].append(p)
        groups["all_states_x_obstacle"][f"{state_label}|{oq}"].append(p)
        groups["duration_x_state"][f"{state_label}|{dur}"].append(p)
        groups["state_x_behavior"][f"{state_label}|{bhv}"].append(p)
        groups["obstacle_x_behavior"][f"{oq}|{bhv}"].append(p)
        groups["spd_dei_x_obstacle"][f"SPD={'Y' if spd else 'N'}|DEI={'Y' if dei else 'N'}|{oq}"].append(p)

        if is_target:
            groups["target_state_x_obstacle"][f"{state_label}|{oq}"].append(p)

    fmt = "{:<65} {:>6}  mfe20={:>7.3f}%  mfe90={:>7.3f}%  acc90={:>6.2f}%  asym={}"

    def print_table(title, data, min_n=5):
        print(f"\n{title}")
        print("-" * 112)
        rows_out = _summ(data, min_n=min_n)
        for s in rows_out:
            print(fmt.format(
                s["bucket"], s["signals"],
                s["avg_mfe_20d_pct"], s["avg_mfe_90d_pct"],
                s["acc_90d_pct"], str(s["avg_asym_20d"])
            ))
        if not rows_out:
            print("  (no buckets met minimum n)")

    print(f"\n{'='*112}")
    print("Phase 7A: Obstacle Quartile Validation")
    print("  Validation: Does mfe90 rise monotonically OBS_Q1 → OBS_Q4")
    print("  when behavioral signal held constant at State 1 (SPD=Y|DEI=N)?")
    print("  PASS = OBS_Q4 > OBS_Q3 > OBS_Q2 > OBS_Q1")
    print(f"{'='*112}")

    print_table(
        "PRIMARY TEST: State 1 (SPD=Y|DEI=N) x Obstacle Quartile — MONOTONIC TEST",
        {k: v for k, v in groups["state1_x_obstacle"].items()},
        min_n=3
    )
    print_table("Behavioral State Baseline (Universe)", groups["state_baseline"])
    print_table("Obstacle Quartile Baseline (No Behavioral Filter)", groups["obstacle_baseline"])
    print_table("All States x Obstacle Quartile", groups["all_states_x_obstacle"])
    print_table("SPD x DEI x Obstacle Quartile", groups["spd_dei_x_obstacle"], min_n=3)
    print_table("Duration (Days Since High) x State", groups["duration_x_state"])
    print_table("State x Behavioral Classification", groups["state_x_behavior"])
    print_table("Obstacle Quartile x Behavioral Classification", groups["obstacle_x_behavior"])
    print_table("TARGET BUCKET: State x Obstacle", groups["target_state_x_obstacle"], min_n=3)


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
