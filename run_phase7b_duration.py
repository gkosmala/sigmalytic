#!/usr/bin/env python3
"""
Phase 7B (Revised): SPD Duration Study
Reads existing qualified_long_signal_rows.csv — no Alpaca calls.

Research question:
  Does the length of time a stock has been in State 1 Exhaustion
  (SPD=Y | DEI=N) predict the magnitude of the forward move?

The feather's weight concept is fundamentally temporal.
A stock where selling pressure first diminished yesterday is
different from a stock where sellers have been progressively
exhausting themselves for 20+ bars.

Duration is computed from p5_days_since_252_high and the
wave efficiency variables already in the CSV. Specifically:

  SPD_DURATION approximation:
    - w_selling_pressure_diminishing = True (current bar)
    - w_up2_vol_eff, w_dn2_vol_eff (prior wave metrics)
    - Use the ratio of dn1 to dn2 wave metrics to infer
      how long the exhaustion sequence has been building

  Primary duration proxy: p5_days_since_252_high bucketed
  into exhaustion duration tiers (days stock has been
  building cause = proxy for how long State 1 has persisted)

  Secondary: wave sequence deterioration score
  (how many successive down-waves show diminishing effort)

Pass condition:
  Duration 20+ bars (180+ day proxy) produces mfe90
  materially above Duration 0-5 bars (under 60 day proxy)
  inside OBS_Q4 + PROG_Q4.
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


def _obstacle(r: Dict) -> float:
    dist  = abs(_safe_float(r.get("distance_from_252_high_pct")) or 0.0)
    days  = (_safe_float(r.get("p5_days_since_252_high")) or 0.0) / 5.0
    rw    = (_safe_float(r.get("range_width_pct")) or 0.0) \
            if _safe_bool(r.get("trading_range_detected")) else 0.0
    return max(dist + days + rw, 0.1)


def _progress(r: Dict) -> float:
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


def _wave_exhaustion_depth(r: Dict) -> int:
    """
    Measure how many successive down-wave pairs show
    deteriorating effort (sellers working less each wave).
    This is the wave-based proxy for SPD duration.

    Score 0-3:
      +1 if dn1 volume ratio < dn2 volume ratio (dn1 lighter than dn2)
      +1 if dn1 price efficiency < dn2 price efficiency
      +1 if dn1 duration < dn2 duration (dn1 shorter)
    """
    score = 0
    dn1_vol = _safe_float(r.get("w_dn1_vol_ratio")) or 0.0
    dn2_vol = _safe_float(r.get("w_dn2_vol_ratio")) or 0.0
    dn1_eff = abs(_safe_float(r.get("w_dn1_price_eff")) or 0.0)
    dn2_eff = abs(_safe_float(r.get("w_dn2_price_eff")) or 0.0)
    dn1_dur = _safe_float(r.get("w_dn1_duration")) or 0.0
    dn2_dur = _safe_float(r.get("w_dn2_duration")) or 0.0

    if dn2_vol > 0 and dn1_vol < dn2_vol:  score += 1
    if dn2_eff > 0 and dn1_eff < dn2_eff:  score += 1
    if dn2_dur > 0 and dn1_dur < dn2_dur:  score += 1
    return score


def _up_wave_acceleration(r: Dict) -> int:
    """
    Measure whether up-waves are improving (demand beginning to emerge).
    Score 0-2:
      +1 if up1 price efficiency > up2 price efficiency
      +1 if up1 return > up2 return
    """
    score = 0
    up1_eff = _safe_float(r.get("w_up1_price_eff")) or 0.0
    up2_eff = _safe_float(r.get("w_up2_price_eff")) or 0.0
    up1_ret = _safe_float(r.get("w_up1_return_pct")) or 0.0
    up2_ret = _safe_float(r.get("w_up2_return_pct")) or 0.0

    if up2_eff > 0 and up1_eff > up2_eff:  score += 1
    if up2_ret > 0 and up1_ret > up2_ret:  score += 1
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
    asym  = (mfe20 / abs(mae20)) if (mfe20 > 0 and mae20 < 0) else 0.0
    return {
        "mfe_20d": mfe20, "mfe_90d": mfe90,
        "acc_90d": acc90, "asym_20d": asym,
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
            "mfe20": av("mfe_20d"),
            "mfe90": av("mfe_90d"),
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

    # Compute scores and quartiles
    obs_all, prog_all, enriched = [], [], []
    for r in rows:
        p = _payload(r)
        if p is None:
            continue
        obs   = _obstacle(r)
        prog  = _progress(r)
        state = _classify_state(r)
        wed   = _wave_exhaustion_depth(r)
        uwa   = _up_wave_acceleration(r)
        obs_all.append(obs)
        prog_all.append(prog)
        enriched.append((r, p, obs, prog, state, wed, uwa))

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

    # ── Study groups ──────────────────────────────────────────────────────
    # Primary duration proxy: days since 252-day high
    # Rationale: the longer the stock has been off its high,
    # the longer the supply absorption process has been running.
    # This is the best available proxy for SPD duration in the existing CSV.

    g_dur           = defaultdict(list)   # A: duration tier alone
    g_dur_x_obs     = defaultdict(list)   # B: duration x obstacle
    g_dur_x_state   = defaultdict(list)   # C: duration x state
    g_wed_alone     = defaultdict(list)   # D: wave exhaustion depth alone
    g_wed_x_obs     = defaultdict(list)   # E: wave exhaustion x obstacle
    g_wed_x_dur     = defaultdict(list)   # F: wave exhaustion x duration
    g_uwa_alone     = defaultdict(list)   # G: up-wave acceleration alone
    g_full_combo    = defaultdict(list)   # H: dur x wed x obs (state1 only)
    g_target_dur    = defaultdict(list)   # I: target bucket x duration
    g_win_dur       = defaultdict(list)   # J: winning combo x duration
    g_seq_combo     = defaultdict(list)   # K: duration x WED x UWA

    for r, p, obs, prog, state, wed, uwa in enriched:
        ot = obs_tier(obs)
        pt = prog_tier(prog)
        is_tgt = _is_target(r)
        spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
        dei = _safe_bool(r.get("w_demand_efficiency_improving"))
        days = _safe_float(r.get("p5_days_since_252_high")) or 0.0
        bhv  = str(r.get("behavior_classification", "NEUTRAL"))

        # Duration buckets (days since 252-day high = cause duration proxy)
        if days >= 180:   dur = "DUR_180_PLUS"
        elif days >= 120: dur = "DUR_120_180"
        elif days >= 60:  dur = "DUR_60_120"
        elif days >= 20:  dur = "DUR_20_60"
        else:             dur = "DUR_UNDER_20"

        # Wave exhaustion depth buckets
        if wed == 3:      wed_b = "WED_3_FULL"
        elif wed == 2:    wed_b = "WED_2_STRONG"
        elif wed == 1:    wed_b = "WED_1_PARTIAL"
        else:             wed_b = "WED_0_NONE"

        # Up-wave acceleration buckets
        if uwa == 2:      uwa_b = "UWA_2_BOTH"
        elif uwa == 1:    uwa_b = "UWA_1_PARTIAL"
        else:             uwa_b = "UWA_0_NONE"

        # A: duration alone
        g_dur[dur].append(p)

        # B: duration x obstacle
        g_dur_x_obs[f"{dur}|{ot}"].append(p)

        # C: duration x state
        g_dur_x_state[f"{dur}|{state}"].append(p)

        # D: wave exhaustion depth alone
        g_wed_alone[wed_b].append(p)

        # E: wave exhaustion x obstacle
        g_wed_x_obs[f"{wed_b}|{ot}"].append(p)

        # F: wave exhaustion x duration
        g_wed_x_dur[f"{wed_b}|{dur}"].append(p)

        # G: up-wave acceleration alone
        g_uwa_alone[uwa_b].append(p)

        # H: State 1 only — full combo
        if spd and not dei:
            g_full_combo[f"{dur}|{wed_b}|{ot}"].append(p)
            g_seq_combo[f"{dur}|{wed_b}|{uwa_b}"].append(p)

        # I: target bucket x duration
        if is_tgt:
            g_target_dur[f"{dur}|{state}"].append(p)

        # J: winning combo (OBS_Q4+PROG_Q4+State1) x duration
        if ot == "OBS_Q4" and pt == "PROG_Q4" and spd and not dei:
            g_win_dur[dur].append(p)

    # ── Print results ──────────────────────────────────────────────────────
    print(f"\n{'='*112}")
    print("Phase 7B (Revised): SPD Duration Study")
    print("  Primary proxy: days since 252-day high = cause duration = SPD duration proxy")
    print("  Secondary: wave exhaustion depth (WED) = how many successive down-waves deteriorate")
    print("  Pass condition: DUR_180_PLUS produces mfe90 materially above DUR_UNDER_20")
    print(f"{'='*112}")

    _pt("PRIMARY TEST A: Duration Tier Alone\n"
        "  PASS = DUR_180_PLUS > DUR_120_180 > DUR_60_120 > DUR_20_60 > DUR_UNDER_20",
        g_dur)

    _pt("Study B: Duration x Obstacle Quartile\n"
        "  Key question: does duration amplify obstacle?",
        g_dur_x_obs)

    _pt("Study C: Duration x Behavioral State\n"
        "  Does duration interact differently with each state?",
        g_dur_x_state)

    _pt("Study D: Wave Exhaustion Depth (WED) Alone\n"
        "  WED_3 = all three down-wave pairs deteriorating (full seller exhaustion sequence)",
        g_wed_alone)

    _pt("Study E: Wave Exhaustion Depth x Obstacle\n"
        "  Does full seller exhaustion sequence inside high obstacle produce best outcomes?",
        g_wed_x_obs)

    _pt("Study F: Wave Exhaustion Depth x Duration\n"
        "  Does long duration + full exhaustion sequence compound?",
        g_wed_x_dur)

    _pt("Study G: Up-Wave Acceleration Alone\n"
        "  UWA_2 = both up-wave metrics improving (early demand emergence)",
        g_uwa_alone)

    _pt("Study H: State 1 Only \u2014 Duration x WED x Obstacle\n"
        "  The complete temporal signal: how long + how deep + how large the obstacle",
        g_full_combo, min_n=3)

    _pt("Study K: State 1 Only \u2014 Duration x WED x Up-Wave Acceleration\n"
        "  Supply exhaustion depth + demand emergence timing",
        g_seq_combo, min_n=3)

    _pt("Study I: TARGET BUCKET \u2014 Duration x State\n"
        "  Late + 20%+ Off High + RelVol 2\u20133x",
        g_target_dur, min_n=3)

    _pt("Study J: WINNING COMBO (OBS_Q4+PROG_Q4+State1) x Duration\n"
        "  PRIMARY PASS CONDITION: DUR_180_PLUS mfe90 materially above DUR_UNDER_20",
        g_win_dur, min_n=3)

    # Summary verdict
    win_dur = _summ(g_win_dur, min_n=3)
    print(f"\n{'='*112}")
    print("VERDICT: Phase 7B Duration Pass/Fail")
    print(f"{'='*112}")
    if win_dur:
        best  = win_dur[0]
        worst = win_dur[-1]
        spread = round(best["mfe90"] - worst["mfe90"], 2)
        print(f"  Best duration bucket:   {best['bucket']:30} mfe90={best['mfe90']:7.2f}%  n={best['n']}")
        print(f"  Worst duration bucket:  {worst['bucket']:30} mfe90={worst['mfe90']:7.2f}%  n={worst['n']}")
        print(f"  Spread:                 {spread:.2f}%")
        if spread >= 10.0:
            print(f"  RESULT: PASS \u2014 Duration adds {spread:.1f} points of mfe90 inside the winning combination")
        elif spread >= 5.0:
            print(f"  RESULT: MARGINAL \u2014 Duration adds {spread:.1f} points, borderline significant")
        else:
            print(f"  RESULT: FAIL \u2014 Duration spread of {spread:.1f}% is insufficient")
    else:
        print("  RESULT: INSUFFICIENT DATA \u2014 increase minimum n threshold")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
