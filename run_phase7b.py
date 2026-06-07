#!/usr/bin/env python3
"""
Phase 7B: Structural Efficiency Ratio
Reads existing qualified_long_signal_rows.csv — no Alpaca calls.

Research question:
  Does progress_score / obstacle_score predict forward returns
  better than either component alone?

Obstacle Score = structural resistance the stock must overcome:
  - distance from 252-day high (absolute)
  - days since 252-day high (normalized)
  - range width (if trading range detected)

Progress Score = evidence of active resolution:
  - recent price trajectory (10-day)
  - recent RS trajectory (10-day)
  - most recent up-wave price efficiency
  - most recent down-wave volume efficiency (sellers absorbed)

Structural Efficiency = progress_score / obstacle_score

Validation threshold: structural efficiency ratio should
produce monotonically improving outcomes at higher tiers.
"""

import csv
import math
import sys
from collections import defaultdict
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
    return str(val).strip().lower() in ("true", "1", "yes")


def _is_target(r: Dict) -> bool:
    try:
        dist = _safe_float(r.get("distance_from_252_high_pct"))
        return (
            r.get("expansion_phase_bucket") == "EXP_PHASE_LATE"
            and r.get("rel_volume_bucket") == "RELVOL_2_0_3_0X"
            and dist is not None and dist <= -20.0
        )
    except Exception:
        return False


def _compute_obstacle_score(r: Dict) -> float:
    """
    Obstacle = structural resistance the stock must overcome.
    Proven directionally significant in Phase 7A.
    """
    dist  = abs(_safe_float(r.get("distance_from_252_high_pct")) or 0.0)
    days  = (_safe_float(r.get("p5_days_since_252_high")) or 0.0) / 5.0
    rw    = (_safe_float(r.get("range_width_pct")) or 0.0) \
            if _safe_bool(r.get("trading_range_detected")) else 0.0
    return max(dist + days + rw, 0.1)   # floor at 0.1 to avoid division by zero


def _compute_progress_score(r: Dict) -> float:
    """
    Progress = evidence that the stock is actively resolving its obstacle.

    Four components, each normalized to a 0-10 scale:

    1. Price trajectory (10-day) — is price rising into the signal?
    2. RS trajectory (10-day)   — is relative strength improving?
    3. Up-wave 1 price efficiency — is the most recent advance fast?
    4. Down-wave 1 volume efficiency — are sellers being absorbed?

    Each component contributes 0-10 points.
    Raw progress score = sum of four components (0-40 max).
    """
    score = 0.0

    # 1. Price trajectory 10-day
    pt = _safe_float(r.get("p5_price_traj_10d_pct")) or 0.0
    if pt >= 5.0:    score += 10.0
    elif pt >= 3.0:  score += 8.0
    elif pt >= 1.0:  score += 5.0
    elif pt >= 0.0:  score += 2.0
    # negative trajectory = 0 points

    # 2. RS trajectory 10-day
    rs = _safe_float(r.get("p5_rs_traj_10d")) or 0.0
    if rs >= 10.0:   score += 10.0
    elif rs >= 3.0:  score += 7.0
    elif rs >= 0.0:  score += 3.0
    # declining RS = 0 points

    # 3. Up-wave 1 price efficiency (speed of most recent advance)
    up1 = _safe_float(r.get("w_up1_price_eff")) or 0.0
    if up1 >= 3.0:   score += 10.0
    elif up1 >= 2.0: score += 8.0
    elif up1 >= 1.0: score += 5.0
    elif up1 >= 0.3: score += 2.0

    # 4. Down-wave 1 volume efficiency (sellers being absorbed)
    dn1 = _safe_float(r.get("w_dn1_vol_eff")) or 0.0
    if dn1 >= 5.0:   score += 10.0
    elif dn1 >= 2.0: score += 6.0
    elif dn1 >= 0.5: score += 3.0

    return score


def _classify_behavioral_state(r: Dict) -> str:
    spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
    dei = _safe_bool(r.get("w_demand_efficiency_improving"))
    buy = _safe_bool(r.get("w_buoyancy_near_support"))
    up1 = _safe_float(r.get("w_up1_price_eff")) or 0.0
    if up1 >= 3.0:        return "STATE_4_EXPANSION"
    if buy:               return "STATE_3_CONFIRMING"
    if spd and dei:       return "STATE_2_EMERGING"
    if spd and not dei:   return "STATE_1_EXHAUSTION"
    return "STATE_0_NEUTRAL"


def _payload(r: Dict) -> Optional[Dict]:
    mfe90 = _safe_float(r.get("markup_90d_pct"))
    if mfe90 is None:
        return None
    mfe20 = _safe_float(r.get("markup_20d_pct")) or 0.0
    mae20 = _safe_float(r.get("h20_mae_pct")) or 0.0
    acc90 = _safe_float(r.get("h90_direction_correct")) or 0.0
    ret90 = _safe_float(r.get("h90_return_pct")) or 0.0
    asym  = (mfe20 / abs(mae20)) if (mfe20 > 0 and mae20 < 0) else 0.0
    return {
        "mfe_20d": mfe20, "mfe_90d": mfe90,
        "acc_90d": acc90, "ret_90d": ret90, "asym_20d": asym,
    }


def _summ(bmap: Dict, min_n: int = 5) -> List[Dict]:
    out = []
    for b, vals in sorted(bmap.items()):
        if len(vals) < min_n:
            continue
        n = len(vals)
        def av(f): return round(sum(v[f] for v in vals) / n, 3)
        asyms = [v["asym_20d"] for v in vals if v["asym_20d"] > 0]
        out.append({
            "bucket": b, "n": n,
            "mfe20":  av("mfe_20d"),
            "mfe90":  av("mfe_90d"),
            "acc90":  round(av("acc_90d") * 100, 2),
            "asym":   round(sum(asyms)/len(asyms), 3) if asyms else 0.0,
        })
    return sorted(out, key=lambda x: x["mfe90"], reverse=True)


def _print_table(title: str, data: Dict, min_n: int = 5) -> None:
    fmt = "{:<68} {:>5}  mfe20={:>7.2f}%  mfe90={:>7.2f}%  acc90={:>6.2f}%  asym={}"
    print(f"\n{'='*112}\n{title}\n{'='*112}")
    rows = _summ(data, min_n=min_n)
    for s in rows:
        print(fmt.format(s["bucket"], s["n"],
                         s["mfe20"], s["mfe90"],
                         s["acc90"], s["asym"]))
    if not rows:
        print("  (no buckets met minimum n)")


def run(csv_path: str) -> None:
    rows = []
    with open(csv_path, newline="", errors="ignore") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"Loaded {len(rows)} rows from {csv_path}")

    # ── Compute scores ────────────────────────────────────────────────────────
    enriched = []
    obs_scores = []
    prog_scores = []
    eff_scores = []

    for r in rows:
        p = _payload(r)
        if p is None:
            continue
        obs  = _compute_obstacle_score(r)
        prog = _compute_progress_score(r)
        eff  = round(prog / obs, 4)
        state = _classify_behavioral_state(r)
        obs_scores.append(obs)
        prog_scores.append(prog)
        eff_scores.append(eff)
        enriched.append((r, p, obs, prog, eff, state))

    # ── Quartile thresholds ───────────────────────────────────────────────────
    def quartiles(vals):
        s = sorted(vals); n = len(s)
        return s[n//4], s[n//2], s[3*n//4]

    oq1, oq2, oq3 = quartiles(obs_scores)
    pq1, pq2, pq3 = quartiles(prog_scores)
    eq1, eq2, eq3 = quartiles(eff_scores)

    def obs_tier(v):
        if v <= oq1: return "OBS_Q1_LOW"
        if v <= oq2: return "OBS_Q2_MID_LOW"
        if v <= oq3: return "OBS_Q3_MID_HIGH"
        return "OBS_Q4_HIGH"

    def prog_tier(v):
        if v <= pq1: return "PROG_Q1_LOW"
        if v <= pq2: return "PROG_Q2_MID_LOW"
        if v <= pq3: return "PROG_Q3_MID_HIGH"
        return "PROG_Q4_HIGH"

    def eff_tier(v):
        if v <= eq1: return "EFF_Q1_LOW"
        if v <= eq2: return "EFF_Q2_MID_LOW"
        if v <= eq3: return "EFF_Q3_MID_HIGH"
        return "EFF_Q4_HIGH"

    print(f"\nObstacle score quartiles:   Q1<={oq1:.2f}  Q2<={oq2:.2f}  Q3<={oq3:.2f}")
    print(f"Progress score quartiles:   Q1<={pq1:.2f}  Q2<={pq2:.2f}  Q3<={pq3:.2f}")
    print(f"Efficiency score quartiles: Q1<={eq1:.4f}  Q2<={eq2:.4f}  Q3<={eq3:.4f}")

    # ── Study groups ──────────────────────────────────────────────────────────
    g_eff          = defaultdict(list)   # PRIMARY: efficiency tier alone
    g_obs          = defaultdict(list)   # obstacle tier alone (replication of 7A)
    g_prog         = defaultdict(list)   # progress tier alone
    g_eff_x_state  = defaultdict(list)   # efficiency x behavioral state
    g_obs_x_prog   = defaultdict(list)   # obstacle x progress quadrant
    g_state1_eff   = defaultdict(list)   # State 1 x efficiency tier (key test)
    g_target_eff   = defaultdict(list)   # target bucket x efficiency tier
    g_target_full  = defaultdict(list)   # target bucket: obs x prog x eff
    g_eff_x_bhv    = defaultdict(list)   # efficiency x behavioral classification
    g_high_eff_dur = defaultdict(list)   # high efficiency x duration

    for r, p, obs, prog, eff, state in enriched:
        ot = obs_tier(obs)
        pt = prog_tier(prog)
        et = eff_tier(eff)
        is_tgt = _is_target(r)
        bhv = str(r.get("behavior_classification", "NEUTRAL"))
        days = _safe_float(r.get("p5_days_since_252_high")) or 0.0
        spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
        dei = _safe_bool(r.get("w_demand_efficiency_improving"))

        if days >= 180:   dur = "DUR_180_PLUS"
        elif days >= 120: dur = "DUR_120_180"
        elif days >= 60:  dur = "DUR_60_120"
        elif days >= 20:  dur = "DUR_20_60"
        else:             dur = "DUR_UNDER_20"

        g_eff[et].append(p)
        g_obs[ot].append(p)
        g_prog[pt].append(p)
        g_eff_x_state[f"{et}|{state}"].append(p)
        g_obs_x_prog[f"{ot}|{pt}"].append(p)
        g_eff_x_bhv[f"{et}|{bhv}"].append(p)

        if spd and not dei:  # State 1
            g_state1_eff[et].append(p)

        if et == "EFF_Q4_HIGH":
            g_high_eff_dur[f"{state}|{dur}"].append(p)

        if is_tgt:
            g_target_eff[et].append(p)
            g_target_full[f"{et}|{ot}|{pt}"].append(p)

    # ── Print results ─────────────────────────────────────────────────────────
    print(f"\n{'='*112}")
    print("Phase 7B: Structural Efficiency Ratio")
    print("  PRIMARY VALIDATION: Does efficiency tier produce monotonically")
    print("  improving mfe90 from EFF_Q1 → EFF_Q4?")
    print("  PASS = EFF_Q4 > EFF_Q3 > EFF_Q2 > EFF_Q1")
    print(f"{'='*112}")

    _print_table(
        "PRIMARY TEST: Structural Efficiency Tier (Progress / Obstacle)\n"
        "  PASS = EFF_Q4 > EFF_Q3 > EFF_Q2 > EFF_Q1",
        g_eff
    )
    _print_table("Obstacle Tier Alone (Phase 7A Replication)", g_obs)
    _print_table("Progress Tier Alone", g_prog)
    _print_table("State 1 (SPD=Y|DEI=N) x Efficiency Tier — Key Interaction", g_state1_eff, min_n=3)
    _print_table("Efficiency Tier x Behavioral State", g_eff_x_state)
    _print_table("Obstacle x Progress Quadrant", g_obs_x_prog)
    _print_table("Efficiency Tier x Behavioral Classification (Phase 4)", g_eff_x_bhv)
    _print_table("High Efficiency (Q4) x State x Duration", g_high_eff_dur, min_n=3)
    _print_table("TARGET BUCKET: Efficiency Tier", g_target_eff, min_n=3)
    _print_table("TARGET BUCKET: Efficiency x Obstacle x Progress", g_target_full, min_n=3)

    # ── Comparison summary ────────────────────────────────────────────────────
    print(f"\n{'='*112}")
    print("COMPARISON: Does Efficiency Ratio outperform components alone?")
    print("  Compare spread between Q1 and Q4 for each metric.")
    print(f"{'='*112}")
    for label, data in [
        ("Efficiency (Progress/Obstacle)", g_eff),
        ("Obstacle alone",                g_obs),
        ("Progress alone",                g_prog),
    ]:
        rows_s = _summ(data, min_n=5)
        if len(rows_s) >= 2:
            best  = rows_s[0]["mfe90"]
            worst = rows_s[-1]["mfe90"]
            spread = round(best - worst, 3)
            print(f"  {label:<40}  best={best:>7.2f}%  worst={worst:>7.2f}%  spread={spread:>7.2f}%")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
