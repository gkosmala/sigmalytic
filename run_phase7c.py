#!/usr/bin/env python3
"""
Phase 7C: Three-Way Combination Test
Reads existing qualified_long_signal_rows.csv — no Alpaca calls.

Research question:
  Does OBS_Q4 AND PROG_Q4 AND STATE_1_EXHAUSTION produce the
  cleanest asymmetric outcome in the dataset?

Phase 7B proved:
  - Efficiency ratio (progress/obstacle) fails — inverted
  - Obstacle alone: 13.66% spread
  - Progress alone: 18.92% spread
  - OBS_Q4|PROG_Q4 interaction: mfe90=43.78% (best quadrant)

Phase 7C tests:
  A. The three-way combination: OBS x PROG x STATE
  B. All 5 states inside OBS_Q4|PROG_Q4 (which state wins?)
  C. The combination inside the target bucket
  D. Duration inside the winning combination
  E. Behavioral classification inside the winning combination
  F. The full state lifecycle inside OBS_Q4|PROG_Q4
     (confirms sequence: State 1 → State 2 → State 4)
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
    dist  = abs(_safe_float(r.get("distance_from_252_high_pct")) or 0.0)
    days  = (_safe_float(r.get("p5_days_since_252_high")) or 0.0) / 5.0
    rw    = (_safe_float(r.get("range_width_pct")) or 0.0) \
            if _safe_bool(r.get("trading_range_detected")) else 0.0
    return max(dist + days + rw, 0.1)


def _compute_progress_score(r: Dict) -> float:
    score = 0.0
    pt = _safe_float(r.get("p5_price_traj_10d_pct")) or 0.0
    if pt >= 5.0:    score += 10.0
    elif pt >= 3.0:  score += 8.0
    elif pt >= 1.0:  score += 5.0
    elif pt >= 0.0:  score += 2.0

    rs = _safe_float(r.get("p5_rs_traj_10d")) or 0.0
    if rs >= 10.0:   score += 10.0
    elif rs >= 3.0:  score += 7.0
    elif rs >= 0.0:  score += 3.0

    up1 = _safe_float(r.get("w_up1_price_eff")) or 0.0
    if up1 >= 3.0:   score += 10.0
    elif up1 >= 2.0: score += 8.0
    elif up1 >= 1.0: score += 5.0
    elif up1 >= 0.3: score += 2.0

    dn1 = _safe_float(r.get("w_dn1_vol_eff")) or 0.0
    if dn1 >= 5.0:   score += 10.0
    elif dn1 >= 2.0: score += 6.0
    elif dn1 >= 0.5: score += 3.0

    return score


def _classify_state(r: Dict) -> str:
    spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
    dei = _safe_bool(r.get("w_demand_efficiency_improving"))
    buy = _safe_bool(r.get("w_buoyancy_near_support"))
    up1 = _safe_float(r.get("w_up1_price_eff")) or 0.0
    if up1 >= 3.0:      return "STATE_4_EXPANSION"
    if buy:             return "STATE_3_CONFIRMING"
    if spd and dei:     return "STATE_2_EMERGING"
    if spd and not dei: return "STATE_1_EXHAUSTION"
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
            "mfe20": av("mfe_20d"), "mfe90": av("mfe_90d"),
            "acc90": round(av("acc_90d") * 100, 2),
            "asym":  round(sum(asyms)/len(asyms), 3) if asyms else 0.0,
        })
    return sorted(out, key=lambda x: x["mfe90"], reverse=True)


def _pt(title: str, data: Dict, min_n: int = 5) -> None:
    fmt = "{:<72} {:>5}  mfe20={:>7.2f}%  mfe90={:>7.2f}%  acc90={:>6.2f}%  asym={}"
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
    print(f"Loaded {len(rows)} rows")

    # Compute scores and quartile thresholds
    obs_all, prog_all, enriched = [], [], []
    for r in rows:
        p = _payload(r)
        if p is None:
            continue
        obs  = _compute_obstacle_score(r)
        prog = _compute_progress_score(r)
        state = _classify_state(r)
        obs_all.append(obs)
        prog_all.append(prog)
        enriched.append((r, p, obs, prog, state))

    def quartiles(vals):
        s = sorted(vals); n = len(s)
        return s[n//4], s[n//2], s[3*n//4]

    oq1, oq2, oq3 = quartiles(obs_all)
    pq1, pq2, pq3 = quartiles(prog_all)

    def obs_tier(v):
        if v <= oq1: return "OBS_Q1"
        if v <= oq2: return "OBS_Q2"
        if v <= oq3: return "OBS_Q3"
        return "OBS_Q4"

    def prog_tier(v):
        if v <= pq1: return "PROG_Q1"
        if v <= pq2: return "PROG_Q2"
        if v <= pq3: return "PROG_Q3"
        return "PROG_Q4"

    print(f"Obstacle quartiles:  Q1<={oq1:.2f}  Q2<={oq2:.2f}  Q3<={oq3:.2f}")
    print(f"Progress quartiles:  Q1<={pq1:.2f}  Q2<={pq2:.2f}  Q3<={pq3:.2f}")

    # Study groups
    g_3way          = defaultdict(list)  # A: OBS x PROG x STATE
    g_state_in_q4q4 = defaultdict(list)  # B: all states inside OBS_Q4|PROG_Q4
    g_target_3way   = defaultdict(list)  # C: target bucket 3-way
    g_dur_win       = defaultdict(list)  # D: duration inside winning combo
    g_bhv_win       = defaultdict(list)  # E: behavioral class inside winning combo
    g_seq_q4q4      = defaultdict(list)  # F: state sequence inside OBS_Q4|PROG_Q4
    g_obs_x_prog    = defaultdict(list)  # reference: OBS x PROG only
    g_rs_win        = defaultdict(list)  # RS daily inside winning combo
    g_vol_win       = defaultdict(list)  # rel volume inside winning combo

    for r, p, obs, prog, state in enriched:
        ot = obs_tier(obs)
        pt = prog_tier(prog)
        is_tgt = _is_target(r)
        bhv = str(r.get("behavior_classification", "NEUTRAL"))
        days = _safe_float(r.get("p5_days_since_252_high")) or 0.0
        rs_d = _safe_float(r.get("rs_daily")) or 0.0
        spd  = _safe_bool(r.get("w_selling_pressure_diminishing"))
        dei  = _safe_bool(r.get("w_demand_efficiency_improving"))

        if days >= 180:   dur = "DUR_180_PLUS"
        elif days >= 120: dur = "DUR_120_180"
        elif days >= 60:  dur = "DUR_60_120"
        elif days >= 20:  dur = "DUR_20_60"
        else:             dur = "DUR_UNDER_20"

        if rs_d < 30:     rs_bucket = "RS_UNDER_30"
        elif rs_d < 40:   rs_bucket = "RS_30_40"
        elif rs_d < 50:   rs_bucket = "RS_40_50"
        elif rs_d < 60:   rs_bucket = "RS_50_60"
        elif rs_d < 70:   rs_bucket = "RS_60_70"
        elif rs_d < 80:   rs_bucket = "RS_70_80"
        elif rs_d < 90:   rs_bucket = "RS_80_90"
        else:             rs_bucket = "RS_90_100"

        relvol = str(r.get("rel_volume_bucket", "UNKNOWN"))

        # Study A: three-way combination
        g_3way[f"{ot}|{pt}|{state}"].append(p)

        # Study B & F: inside OBS_Q4|PROG_Q4
        if ot == "OBS_Q4" and pt == "PROG_Q4":
            g_state_in_q4q4[state].append(p)
            g_seq_q4q4[f"SPD={'Y' if spd else 'N'}|DEI={'Y' if dei else 'N'}"].append(p)

        # OBS x PROG reference
        g_obs_x_prog[f"{ot}|{pt}"].append(p)

        # Winning combo = OBS_Q4 + PROG_Q4 + STATE_1_EXHAUSTION
        if ot == "OBS_Q4" and pt == "PROG_Q4" and state == "STATE_1_EXHAUSTION":
            g_dur_win[dur].append(p)
            g_bhv_win[bhv].append(p)
            g_rs_win[rs_bucket].append(p)
            g_vol_win[relvol].append(p)

        # Study C: target bucket
        if is_tgt:
            g_target_3way[f"{ot}|{pt}|{state}"].append(p)

    # Print results
    print(f"\n{'='*112}")
    print("Phase 7C: Three-Way Combination Test")
    print("  Core question: Does OBS_Q4 + PROG_Q4 + STATE_1_EXHAUSTION")
    print("  produce the cleanest asymmetric outcome in the dataset?")
    print(f"{'='*112}")

    _pt("Study A: OBS x PROG x STATE — Full Three-Way (top 30)", 
        {k: v for k, v in list(g_3way.items())}, min_n=20)

    _pt("Study B: All States inside OBS_Q4 + PROG_Q4\n"
        "  Which state produces best outcome in highest-quality structural environment?",
        g_state_in_q4q4, min_n=5)

    _pt("Study F: SPD x DEI Sequence inside OBS_Q4 + PROG_Q4\n"
        "  Confirms lifecycle ordering within the winning structural environment",
        g_seq_q4q4, min_n=5)

    _pt("OBS x PROG Reference (Phase 7B replication)", g_obs_x_prog, min_n=20)

    _pt("Study D: Duration inside Winning Combo (OBS_Q4 + PROG_Q4 + STATE_1)\n"
        "  How long in exhaustion before resolution?",
        g_dur_win, min_n=3)

    _pt("Study E: Behavioral Classification inside Winning Combo\n"
        "  Does Phase 4 accumulation classification add precision?",
        g_bhv_win, min_n=3)

    _pt("RS Daily inside Winning Combo (OBS_Q4 + PROG_Q4 + STATE_1)\n"
        "  Confirms RS 30-40 finding from Phase 5",
        g_rs_win, min_n=3)

    _pt("Relative Volume inside Winning Combo (OBS_Q4 + PROG_Q4 + STATE_1)",
        g_vol_win, min_n=3)

    _pt("Study C: TARGET BUCKET — Three-Way Combination\n"
        "  Late + 20%+ Off High + RelVol 2-3x",
        g_target_3way, min_n=3)

    # Summary
    print(f"\n{'='*112}")
    print("SUMMARY: Top combinations by mfe90")
    print(f"{'='*112}")
    all_3way = _summ(g_3way, min_n=20)
    fmt = "{:<72} {:>5}  mfe20={:>7.2f}%  mfe90={:>7.2f}%  acc90={:>6.2f}%  asym={}"
    for s in all_3way[:15]:
        print(fmt.format(s["bucket"], s["n"],
                         s["mfe20"], s["mfe90"],
                         s["acc90"], s["asym"]))


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
