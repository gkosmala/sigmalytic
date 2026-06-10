#!/usr/bin/env python3
"""
Phase 13C: Enhanced Signal Output
For each qualifying signal produces four outputs:
  1. Potential Target (P&F derived, frozen calibration factor 0.6656)
  2. Realization Probability (layer validation lookup)
  3. Campaign Health (ODS proxy from existing metrics)
  4. Historical Analog (matched signals from 168k dataset)

This is the live signal display template for the Command Center.
"""
import csv, math, sys
from collections import defaultdict

def _f(val):
    try:
        v = float(val)
        return v if math.isfinite(v) else None
    except: return None

def _b(val):
    if isinstance(val, bool): return val
    return str(val).strip().lower() in ("true", "1", "yes")

def _percentile(vals, p):
    if not vals: return 0.0
    s = sorted(vals)
    idx = (len(s) - 1) * p / 100.0
    lo = int(idx); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)

def _obs(r):
    dist = abs(_f(r.get("distance_from_252_high_pct")) or 0.0)
    days = (_f(r.get("p5_days_since_252_high")) or 0.0) / 5.0
    rw = (_f(r.get("range_width_pct")) or 0.0) if _b(r.get("trading_range_detected")) else 0.0
    return max(dist + days + rw, 0.1)

def _prog(r):
    s = 0.0
    pt = _f(r.get("p5_price_traj_10d_pct")) or 0.0
    if pt >= 5: s += 10
    elif pt >= 3: s += 8
    elif pt >= 1: s += 5
    elif pt >= 0: s += 2
    rs = _f(r.get("p5_rs_traj_10d")) or 0.0
    if rs >= 10: s += 10
    elif rs >= 3: s += 7
    elif rs >= 0: s += 3
    u1 = _f(r.get("w_up1_price_eff")) or 0.0
    if u1 >= 3: s += 10
    elif u1 >= 2: s += 8
    elif u1 >= 1: s += 5
    elif u1 >= 0.3: s += 2
    d1 = _f(r.get("w_dn1_vol_eff")) or 0.0
    if d1 >= 5: s += 10
    elif d1 >= 2: s += 6
    elif d1 >= 0.5: s += 3
    return s

def _d_score(r):
    score = 0
    if _b(r.get("w_failure_to_follow_through")): score += 2
    va = _f(r.get("vol_asymmetry_ratio")) or 0.0
    if va >= 2.0: score += 2
    elif va >= 1.0: score += 1
    rc = _f(r.get("range_contraction_pct")) or 0.0
    if rc >= 30: score += 2
    elif rc >= 15: score += 1
    if _b(r.get("demand_dominant")): score += 1
    if _b(r.get("w_springboard_present")): score += 1
    c = _f(r.get("cause_score")) or 0.0
    if c >= 75: score += 1
    if str(r.get("behavior_classification", "")).strip() == "ACCUMULATION": score += 2
    return score

# ── Realization Probability Lookup ───────────────────────────────────────────
# Derived from validated research (Phases 7-9)
# Layer → (win_rate_pct, median_mfe90_pct, description)

LAYER_PROFILES = {
    5: (76.7, 247.18, "D_2_3|ACCUM|D1_N — Highest conviction entry"),
    4: (59.6, 156.36, "H1_DOWN|H3_DOWN|ACCUM — Weakness entry confirmed"),
    3: (59.0, 109.39, "ACCUMULATION + DUR_60_120 — Behavioral confirmed"),
    2: (59.0,  78.85, "DUR_60_120 — Duration-optimal window"),
    1: (58.7,  38.45, "OBS_Q4+PROG_Q4+State1 — Core signal"),
}

def classify_layer(r, ot_fn, pt_fn, dur_fn):
    """Classify signal into validated entry layer (1-5)."""
    spd = _b(r.get("w_selling_pressure_diminishing"))
    dei = _b(r.get("w_demand_efficiency_improving"))
    days = _f(r.get("p5_days_since_252_high")) or 0.0
    bhv = str(r.get("behavior_classification", "")).strip()
    o = _obs(r); pr = _prog(r)
    ds = _d_score(r)
    ftft = not _b(r.get("w_failure_to_follow_through"))  # D1_N
    h1r = _f(r.get("h1_return_pct")) or 0.0
    h3r = _f(r.get("h3_return_pct")) or 0.0

    is_state1 = spd and not dei
    is_l1 = (ot_fn(o) == "Q4" and pt_fn(pr) == "Q4" and is_state1)
    if not is_l1: return 0

    is_l2 = dur_fn(days) == "DUR_60_120"
    is_l3 = is_l2 and bhv == "ACCUMULATION"
    is_l4 = is_l3 and h1r < 0 and h3r < 0
    is_l5 = is_l3 and (2 <= ds <= 3) and ftft

    if is_l5: return 5
    if is_l4: return 4
    if is_l3: return 3
    if is_l2: return 2
    return 1

# ── Campaign Health Score ─────────────────────────────────────────────────────
# ODS proxy from existing metrics — scores 0-100

def campaign_health(r):
    score = 0

    # Wave efficiency (operator vs retail behavior)
    u1pe = _f(r.get("w_up1_price_eff")) or 0.0
    d1pe = _f(r.get("w_dn1_price_eff")) or 0.0
    if u1pe > 0 and d1pe > 0:
        ratio = u1pe / d1pe
        if ratio >= 3: score += 20
        elif ratio >= 2: score += 15
        elif ratio >= 1.5: score += 10
        elif ratio >= 1: score += 5

    # Volume acceptance
    va = _f(r.get("vol_asymmetry_ratio")) or 0.0
    if va >= 2.0: score += 20
    elif va >= 1.0: score += 12
    elif va >= 0.5: score += 5

    # Range compression
    rc = _f(r.get("range_contraction_pct")) or 0.0
    if rc >= 30: score += 15
    elif rc >= 15: score += 10
    elif rc >= 5: score += 5

    # Demand dominant
    if _b(r.get("demand_dominant")): score += 10

    # Failure to follow through (sellers giving up)
    if _b(r.get("w_failure_to_follow_through")): score += 10

    # Springboard
    if _b(r.get("w_springboard_present")): score += 10

    # Cause score (structural)
    cs = _f(r.get("cause_score")) or 0.0
    if cs >= 75: score += 15
    elif cs >= 50: score += 10
    elif cs >= 25: score += 5

    return min(score, 100)

def health_label(score):
    if score >= 75: return "STRONG"
    if score >= 55: return "HEALTHY"
    if score >= 35: return "MODERATE"
    return "WEAK"

# ── Potential Target ──────────────────────────────────────────────────────────
CALIB_FACTOR = 0.6656  # Frozen from Phase 13B — pending quality-tier refinement

def potential_target(r):
    """Compute P&F-derived potential target."""
    cs = _f(r.get("cause_score"))
    ec = _f(r.get("entry_close"))
    atr14 = _f(r.get("atr_14"))

    if not cs or not ec or ec <= 0: return None, None, None
    if not atr14 or atr14 <= 0:
        atr14 = ec * 0.02  # fallback

    box_size = 0.5 * atr14
    projected_move = cs * CALIB_FACTOR * box_size * 3
    cons_target = ec + projected_move * 0.6
    agg_target  = ec + projected_move
    cons_pct = (cons_target - ec) / ec * 100
    agg_pct  = (agg_target  - ec) / ec * 100
    return round(cons_target, 2), round(agg_target, 2), (round(cons_pct, 1), round(agg_pct, 1))

# ── Historical Analog Finder ──────────────────────────────────────────────────

def find_analogs(signal, all_signals, layer, bhv, dur_bucket, max_analogs=500):
    """
    Find historical signals matching the current signal's profile.
    Match on: layer, behavioral classification, duration bucket.
    Returns dict with n, win_rate, median_mfe90, p75_mfe90, p90_mfe90.
    """
    matches = []
    for s in all_signals:
        if s is signal: continue
        if s.get("_layer") != layer: continue
        if str(s.get("behavior_classification","")).strip() != bhv: continue
        mfe90 = _f(s.get("markup_90d_pct"))
        if mfe90 is None: continue
        h90d = _f(s.get("h90_direction_correct")) or 0.0
        matches.append({"mfe90": mfe90, "win": h90d > 0.5})

    if not matches:
        # Broaden to layer + behavioral only
        for s in all_signals:
            if s is signal: continue
            if s.get("_layer") != layer: continue
            mfe90 = _f(s.get("markup_90d_pct"))
            if mfe90 is None: continue
            h90d = _f(s.get("h90_direction_correct")) or 0.0
            matches.append({"mfe90": mfe90, "win": h90d > 0.5})

    if not matches:
        return None

    mfe90s = sorted([m["mfe90"] for m in matches])
    win_rate = sum(1 for m in matches if m["win"]) / len(matches) * 100

    return {
        "n": len(matches),
        "win_rate": round(win_rate, 1),
        "median_mfe90": round(_percentile(mfe90s, 50), 1),
        "p75_mfe90": round(_percentile(mfe90s, 75), 1),
        "p90_mfe90": round(_percentile(mfe90s, 90), 1),
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def run(csv_path, top_n=20):
    rows = []
    with open(csv_path, newline="", errors="ignore") as f:
        for row in csv.DictReader(f): rows.append(row)
    print("Loaded {:,} rows".format(len(rows)))

    # Compute quartile thresholds
    obs_s = []; prog_s = []
    for r in rows:
        if _f(r.get("markup_90d_pct")) is None: continue
        obs_s.append(_obs(r)); prog_s.append(_prog(r))

    def qq(vals):
        s = sorted(vals); n = len(s)
        return s[n//4], s[n//2], s[3*n//4]
    oq1, oq2, oq3 = qq(obs_s)
    pq1, pq2, pq3 = qq(prog_s)

    def ot(v): return "Q4" if v > oq3 else ("Q3" if v > oq2 else ("Q2" if v > oq1 else "Q1"))
    def pt(v): return "Q4" if v > pq3 else ("Q3" if v > pq2 else ("Q2" if v > pq1 else "Q1"))
    def dur(d):
        if d >= 180: return "DUR_180+"
        if d >= 120: return "DUR_120_180"
        if d >= 60:  return "DUR_60_120"
        if d >= 20:  return "DUR_20_60"
        return "DUR_UNDER_20"

    # Classify all signals into layers
    for r in rows:
        r["_layer"] = classify_layer(r, ot, pt, dur)

    # Collect all Layer 1+ signals for analog matching
    layer_signals = [r for r in rows if r["_layer"] >= 1]
    print("Layer 1+ signals: {:,}".format(len(layer_signals)))

    # Build output for all Layer 1+ signals sorted by layer then cause_score
    qualified = sorted(
        [r for r in rows if r["_layer"] >= 1 and _f(r.get("entry_close"))],
        key=lambda x: (-x["_layer"], -(_f(x.get("cause_score")) or 0))
    )

    SEP = "=" * 110

    print("\n" + SEP)
    print("PHASE 13C: ENHANCED SIGNAL OUTPUT — Potential + Realization + Health + Analog")
    print("Showing top {:,} signals by layer then cause_score".format(top_n))
    print(SEP)

    # ── Study 1: Layer population breakdown ───────────────────────────────────
    print("\nSTUDY 1: LAYER POPULATION BREAKDOWN")
    layer_counts = defaultdict(int)
    for r in rows:
        layer_counts[r["_layer"]] += 1
    for layer in range(6):
        if layer == 0:
            print("  Layer 0 (below threshold):  {:,}".format(layer_counts[0]))
        else:
            prof = LAYER_PROFILES[layer]
            print("  Layer {:d} ({:<45}) {:>6,} signals".format(
                layer, prof[2][:45], layer_counts[layer]))

    # ── Study 2: Realization probability by layer ─────────────────────────────
    print("\nSTUDY 2: REALIZATION PROBABILITY BY LAYER (from validated research)")
    print("  {:>7}  {:>15}  {:>12}  {:>12}  {}".format(
        "Layer", "Win Rate", "Median mfe90", "Description", ""))
    print("  " + "-" * 80)
    for layer in range(1, 6):
        prof = LAYER_PROFILES[layer]
        print("  Layer {:d}  {:>14.1f}%  {:>11.2f}%  {}".format(
            layer, prof[0], prof[1], prof[2][:50]))

    # ── Study 3: Campaign health distribution ─────────────────────────────────
    print("\nSTUDY 3: CAMPAIGN HEALTH DISTRIBUTION (ODS Proxy)")
    health_buckets = defaultdict(list)
    for r in layer_signals:
        h = campaign_health(r)
        mfe90 = _f(r.get("markup_90d_pct"))
        if mfe90 is not None:
            health_buckets[health_label(h)].append(mfe90)
    for label in ["STRONG", "HEALTHY", "MODERATE", "WEAK"]:
        vals = health_buckets[label]
        if not vals: continue
        print("  {:10}  n={:5,}  med_mfe90={:7.2f}%  avg_mfe90={:7.2f}%".format(
            label, len(vals),
            _percentile(sorted(vals), 50),
            sum(vals)/len(vals)))

    # ── Study 4: Full enhanced signal output for top N ────────────────────────
    print("\nSTUDY 4: ENHANCED SIGNAL OUTPUT (Top {:,} signals)".format(top_n))

    for i, r in enumerate(qualified[:top_n]):
        layer = r["_layer"]
        prof = LAYER_PROFILES.get(layer, (0, 0, "Unknown"))
        bhv = str(r.get("behavior_classification", "")).strip()
        days = _f(r.get("p5_days_since_252_high")) or 0.0
        dur_b = dur(days)
        cs = _f(r.get("cause_score")) or 0
        ec = _f(r.get("entry_close")) or 0
        atr14 = _f(r.get("atr_14")) or 0
        high252 = _f(r.get("high_252")) or 0
        h_score = campaign_health(r)
        h_label = health_label(h_score)
        cons_t, agg_t, pcts = potential_target(r)
        analog = find_analogs(r, layer_signals, layer, bhv, dur_b)
        mfe90_actual = _f(r.get("markup_90d_pct"))

        print("\n" + "─" * 80)
        print("  {:10}  {}  Layer {:d}  CS={:.0f}".format(
            r.get("symbol",""), r.get("signal_date",""), layer, cs))
        print("  ─" * 40)
        print("  Entry Close:        ${:.2f}".format(ec))
        print("  Resistance (252H):  ${:.2f}  ({:.1f}% above)".format(
            high252, (high252-ec)/ec*100 if ec > 0 else 0))
        print("  ATR_14:             ${:.2f}".format(atr14))
        print("  Cause Score:        {:.0f}".format(cs))
        print("  Behavioral:         {}".format(bhv))
        print("  Duration:           {}".format(dur_b))
        print("")
        if cons_t:
            print("  POTENTIAL TARGET (P&F, calib=0.6656, indicative):")
            print("    Conservative:     ${:.2f}  (+{:.1f}%)".format(cons_t, pcts[0]))
            print("    Aggressive:       ${:.2f}  (+{:.1f}%)".format(agg_t, pcts[1]))
        print("")
        print("  REALIZATION PROBABILITY (Layer {:d}):".format(layer))
        print("    Win Rate:         {:.1f}%".format(prof[0]))
        print("    Median mfe90:     {:.1f}%".format(prof[1]))
        print("    Trigger:          {}".format(prof[2][:60]))
        print("")
        print("  CAMPAIGN HEALTH:    {} ({}/100)".format(h_label, h_score))
        print("")
        if analog:
            print("  HISTORICAL ANALOG:")
            print("    Matches:          {:,}".format(analog["n"]))
            print("    Win Rate:         {:.1f}%".format(analog["win_rate"]))
            print("    Median mfe90:     {:.1f}%".format(analog["median_mfe90"]))
            print("    75th pct mfe90:   {:.1f}%".format(analog["p75_mfe90"]))
            print("    90th pct mfe90:   {:.1f}%".format(analog["p90_mfe90"]))
        if mfe90_actual is not None:
            print("")
            print("  ACTUAL mfe90:       {:.1f}%  (historical outcome)".format(mfe90_actual))

    # ── Study 5: Aggregate validation ─────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 5: POTENTIAL TARGET ACCURACY BY LAYER")
    print("  Tests whether P&F targets bracket actual mfe90")
    print(SEP)
    print("  {:>7}  {:>6}  {:>12}  {:>12}  {:>15}  {:>15}".format(
        "Layer", "n", "Med Actual%", "Med Cons Tgt%", "Within Range%", "Med Error%"))
    print("  " + "-" * 75)

    for layer in range(1, 6):
        layer_rows = [r for r in layer_signals if r["_layer"] == layer
                      and _f(r.get("entry_close")) and _f(r.get("atr_14"))
                      and _f(r.get("cause_score"))]
        if not layer_rows: continue

        actuals = []; cons_pcts = []; within = []; errors = []
        for r in layer_rows:
            mfe90 = _f(r.get("markup_90d_pct"))
            if mfe90 is None: continue
            cons_t, agg_t, pcts = potential_target(r)
            if not cons_t: continue
            actuals.append(mfe90)
            cons_pcts.append(pcts[0])
            # Within range = actual between 50% of cons and 150% of agg
            w = (mfe90 >= pcts[0] * 0.5) and (mfe90 <= pcts[1] * 1.5)
            within.append(w)
            errors.append(abs(pcts[0] - mfe90))

        if not actuals: continue
        print("  Layer {:d}  {:>6,}  {:>11.1f}%  {:>12.1f}%  {:>14.1f}%  {:>14.1f}%".format(
            layer, len(actuals),
            _percentile(sorted(actuals), 50),
            _percentile(sorted(cons_pcts), 50),
            sum(within)/len(within)*100,
            _percentile(sorted(errors), 50)))

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + SEP)
    print("PHASE 13C SUMMARY")
    print(SEP)
    total_l1plus = sum(layer_counts[l] for l in range(1,6))
    print("\n  Total Layer 1+ signals:    {:,}".format(total_l1plus))
    for layer in range(1, 6):
        print("  Layer {:d}:                  {:,}".format(layer, layer_counts[layer]))
    print("\n  Calibration factor used:   {:.4f} (frozen — pending quality-tier refinement)".format(
        CALIB_FACTOR))
    print("  Potential target note:     Indicative until quality-tier calibration complete")
    print("  Realization probabilities: From validated Phase 9 research (Phases 9A-9C)")
    print("  Campaign health:           ODS proxy from 7 existing metrics")
    print("  Historical analog:         Matched from {:,}-row dataset".format(len(rows)))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    run(csv_path, top_n)
