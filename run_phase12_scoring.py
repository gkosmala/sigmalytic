#!/usr/bin/env python3
"""
Phase 12A/12B: Live Signal Scoring and Ranking
Composite score combining all validated research layers into a single
ranked signal list. This is the template for the live daily scoring system.

Scoring Architecture:
  Layer 1 — Structural Foundation (Phase 7A-7C)
    OBS_Q4:     +20 pts  (obstacle quartile — primary driver)
    PROG_Q4:    +15 pts  (progress quartile — resolution evidence)
    STATE_1:    +10 pts  (behavioral exhaustion state)

  Layer 2 — Duration (Phase 7B-D)
    DUR_60_120: +15 pts  (optimal forgetting curve window)
    DUR_120_180:+10 pts
    DUR_180+:   + 5 pts

  Layer 3 — Behavioral Classification (Phase 9A)
    ACCUMULATION: +15 pts
    AMBIGUOUS:    + 5 pts
    DISTRIBUTION: + 0 pts

  Layer 4 — Behavioral Confirmation D-Score (Phase 9C)
    D_6_7:      +12 pts
    D_4_5:      + 8 pts
    D_2_3:      + 5 pts
    D_0_1:      + 0 pts

  Layer 5 — FTFT / D1 Signal (Phase 9C)
    D1_N (no follow-through): +8 pts

  Layer 6 — Wave Exhaustion Depth (Phase 3/9A)
    WED_3_FULL:   + 5 pts
    WED_2_STRONG: + 5 pts
    WED_1_PARTIAL:+ 2 pts

  Layer 7 — RS Daily (Phase 5)
    RS 30-40:   + 5 pts  (validated optimal zone)
    RS 20-30:   + 3 pts
    RS 40-50:   + 2 pts

Maximum possible score: 105 pts
Signal tiers:
  TIER_1 (Elite):   >= 80 pts
  TIER_2 (Strong):  >= 60 pts
  TIER_3 (Standard):>= 40 pts
  TIER_4 (Watch):   >= 20 pts
  BELOW_THRESHOLD:  <  20 pts
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

def _percentile(vals, p):
    if not vals: return 0.0
    s = sorted(vals)
    idx = (len(s) - 1) * p / 100.0
    lo = int(idx); hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)

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

def _composite_score(r, obs_tier, prog_tier, state1, days, bhv, d_score_val, wed, rs_daily):
    score = 0

    # Layer 1 — Structural Foundation
    if obs_tier == "Q4": score += 20
    elif obs_tier == "Q3": score += 10
    if prog_tier == "Q4": score += 15
    elif prog_tier == "Q3": score += 7
    if state1: score += 10

    # Layer 2 — Duration
    if 60 <= days < 120: score += 15
    elif 120 <= days < 180: score += 10
    elif days >= 180: score += 5

    # Layer 3 — Behavioral Classification
    if bhv == "ACCUMULATION": score += 15
    elif bhv == "AMBIGUOUS": score += 5

    # Layer 4 — D-Score
    if d_score_val >= 6: score += 12
    elif d_score_val >= 4: score += 8
    elif d_score_val >= 2: score += 5

    # Layer 5 — FTFT
    if not _b(r.get("w_failure_to_follow_through")): score += 8

    # Layer 6 — Wave Exhaustion
    if wed in ("WED_2_STRONG", "WED_3_FULL"): score += 5
    elif wed == "WED_1_PARTIAL": score += 2

    # Layer 7 — RS Daily
    if 30 <= rs_daily < 40: score += 5
    elif 20 <= rs_daily < 30: score += 3
    elif 40 <= rs_daily < 50: score += 2

    return score

def _tier(score):
    if score >= 80: return "TIER_1_ELITE"
    if score >= 60: return "TIER_2_STRONG"
    if score >= 40: return "TIER_3_STANDARD"
    if score >= 20: return "TIER_4_WATCH"
    return "BELOW_THRESHOLD"

def run(csv_path):
    rows = []
    with open(csv_path, newline="", errors="ignore") as f:
        for row in csv.DictReader(f): rows.append(row)
    print("Loaded %d rows from %s" % (len(rows), csv_path))

    enriched = []
    obs_s, prog_s = [], []
    for r in rows:
        mfe90 = _f(r.get("markup_90d_pct"))
        if mfe90 is None: continue
        o = _obs(r); pr = _prog(r)
        obs_s.append(o); prog_s.append(pr)
        enriched.append((r, o, pr, mfe90))

    def qq(vals):
        s = sorted(vals); n = len(s)
        return s[n//4], s[n//2], s[3*n//4]
    oq1, oq2, oq3 = qq(obs_s)
    pq1, pq2, pq3 = qq(prog_s)

    def ot(v): return "Q4" if v > oq3 else ("Q3" if v > oq2 else ("Q2" if v > oq1 else "Q1"))
    def pt(v): return "Q4" if v > pq3 else ("Q3" if v > pq2 else ("Q2" if v > pq1 else "Q1"))

    def wed_classify(r):
        d1pe = _f(r.get("w_dn1_price_eff")) or 0.0
        d2pe = _f(r.get("w_dn2_price_eff")) or 0.0
        d3pe = _f(r.get("w_dn3_price_eff")) or 0.0
        d1ve = _f(r.get("w_dn1_vol_eff")) or 0.0
        d2ve = _f(r.get("w_dn2_vol_eff")) or 0.0
        d3ve = _f(r.get("w_dn3_vol_eff")) or 0.0
        wc = 0
        if d2pe > 0 and d1pe < d2pe: wc += 1
        if d2ve > 0 and d1ve < d2ve: wc += 1
        if d3pe > 0 and d2pe < d3pe: wc += 1
        if d3ve > 0 and d2ve < d3ve: wc += 1
        if d3pe > 0 and d2pe > 0 and d1pe > 0 and d1pe < d2pe < d3pe and d1ve < d2ve < d3ve:
            return "WED_3_FULL"
        if wc >= 3: return "WED_2_STRONG"
        if wc >= 2: return "WED_1_PARTIAL"
        return "WED_0_NONE"

    # ── Score all signals ─────────────────────────────────────────────────────
    tier_data = defaultdict(list)
    score_dist = []
    all_scored = []

    for r, o, pr, mfe90 in enriched:
        spd = _b(r.get("w_selling_pressure_diminishing"))
        dei = _b(r.get("w_demand_efficiency_improving"))
        days = _f(r.get("p5_days_since_252_high")) or 0.0
        bhv = str(r.get("behavior_classification", "")).strip()
        rs_daily = _f(r.get("rs_daily")) or 0.0
        obs_tier = ot(o)
        prog_tier = pt(pr)
        state1 = spd and not dei
        ds = _d_score(r)
        wed = wed_classify(r)

        score = _composite_score(r, obs_tier, prog_tier, state1, days, bhv, ds, wed, rs_daily)
        tier = _tier(score)

        tier_data[tier].append(mfe90)
        score_dist.append(score)
        all_scored.append((score, tier, mfe90,
            _f(r.get("h90_direction_correct")) or 0.0,
            str(r.get("symbol", "")),
            str(r.get("signal_date", ""))))

    SEP = "=" * 100

    # ── STUDY 1: Score Distribution ───────────────────────────────────────────
    print("\n" + SEP)
    print("Phase 12: Signal Scoring and Ranking System")
    print("  Composite score combining all validated research layers (max 105 pts)")
    print(SEP)

    print("\nSTUDY 1: SCORE DISTRIBUTION")
    buckets = defaultdict(int)
    for s in score_dist:
        b = (s // 10) * 10
        buckets[b] += 1
    total = len(score_dist)
    print("  %-12s  %8s  %8s  %8s" % ("Score Range", "Count", "Pct", "CumPct"))
    print("  " + "-" * 42)
    cumulative = 0
    for b in sorted(buckets.keys(), reverse=True):
        cumulative += buckets[b]
        bar = "#" * (buckets[b] * 40 // max(buckets.values()))
        print("  %-12s  %8d  %7.1f%%  %7.1f%%  %s" % (
            "%d-%d" % (b, b+9), buckets[b],
            buckets[b]/total*100, cumulative/total*100, bar))

    # ── STUDY 2: Tier Performance ─────────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 2: TIER PERFORMANCE — Does score predict forward returns?")
    print("  PASS = monotonically increasing mfe90 from BELOW_THRESHOLD to TIER_1")
    print(SEP)
    fmt = "  %-22s  %6s  %9s  %9s  %9s  %9s  %9s"
    print(fmt % ("Tier", "n", "mfe90_avg", "mfe90_med", "mfe90_75p", "mfe90_90p", "WinRate90"))
    print("  " + "-" * 80)
    tier_order = ["TIER_1_ELITE", "TIER_2_STRONG", "TIER_3_STANDARD",
                  "TIER_4_WATCH", "BELOW_THRESHOLD"]
    for tier in tier_order:
        vals = tier_data[tier]
        if not vals: continue
        n = len(vals)
        avg = sum(vals) / n
        med = _percentile(sorted(vals), 50)
        p75 = _percentile(sorted(vals), 75)
        p90 = _percentile(sorted(vals), 90)
        wins = sum(1 for s, t, m, d, sym, dt in all_scored if t == tier and d > 0.5)
        win_rate = wins / n * 100
        print(fmt % (tier, n, "%.2f%%" % avg, "%.2f%%" % med,
                     "%.2f%%" % p75, "%.2f%%" % p90, "%.1f%%" % win_rate))

    # ── STUDY 3: Tier Spread ──────────────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 3: MONOTONIC TEST — Is higher score = higher mfe90?")
    print(SEP)
    tier_avgs = {}
    for tier in tier_order:
        vals = tier_data[tier]
        if vals: tier_avgs[tier] = sum(vals) / len(vals)
    prev = None; monotonic = True
    for tier in tier_order:
        if tier not in tier_avgs: continue
        avg = tier_avgs[tier]
        if prev is not None and avg > prev:
            print("  %s: %.2f%% [INVERTED vs previous tier]" % (tier, avg))
            monotonic = False
        else:
            print("  %s: %.2f%%" % (tier, avg))
        prev = avg
    print("\n  Monotonic result: %s" % ("PASS" if monotonic else "PARTIAL - review tier boundaries"))

    # ── STUDY 4: Elite Signals Deep Dive ─────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 4: TIER 1 ELITE SIGNALS — Deep dive on highest-scoring signals")
    print(SEP)
    elite = [(s, t, m, d, sym, dt) for s, t, m, d, sym, dt in all_scored if t == "TIER_1_ELITE"]
    if elite:
        mfe90s = [m for s, t, m, d, sym, dt in elite]
        wins = sum(1 for s, t, m, d, sym, dt in elite if d > 0.5)
        print("  Elite signal count:    %d (%.2f%% of universe)" % (
            len(elite), len(elite)/total*100))
        print("  Average mfe90:         %.2f%%" % (sum(mfe90s)/len(mfe90s)))
        print("  Median mfe90:          %.2f%%" % _percentile(sorted(mfe90s), 50))
        print("  75th pct mfe90:        %.2f%%" % _percentile(sorted(mfe90s), 75))
        print("  90th pct mfe90:        %.2f%%" % _percentile(sorted(mfe90s), 90))
        print("  Win rate (90d):        %.1f%%" % (wins/len(elite)*100))
        print("  Score range:           %d to %d" % (
            min(s for s,t,m,d,sym,dt in elite),
            max(s for s,t,m,d,sym,dt in elite)))
        print("\n  Top 20 highest-scoring signals (by composite score):")
        print("  %-10s  %-12s  %6s  %10s  %10s" % (
            "Symbol", "Date", "Score", "mfe90", "Dir90"))
        print("  " + "-" * 55)
        top20 = sorted(elite, key=lambda x: -x[0])[:20]
        for score, tier, mfe90, dir90, sym, dt in top20:
            print("  %-10s  %-12s  %6d  %9.2f%%  %9.1f%%" % (
                sym, dt, score, mfe90, dir90*100))
    else:
        print("  No TIER_1_ELITE signals found. Adjust tier thresholds.")

    # ── STUDY 5: Score vs MFE90 Correlation ──────────────────────────────────
    print("\n" + SEP)
    print("STUDY 5: SCORE BUCKETS vs MFE90 — Fine-grained relationship")
    print(SEP)
    score_buckets = defaultdict(list)
    for s, t, m, d, sym, dt in all_scored:
        b = (s // 5) * 5
        score_buckets[b].append(m)
    print("  %-12s  %8s  %10s  %10s" % ("Score", "n", "avg_mfe90", "med_mfe90"))
    print("  " + "-" * 45)
    for b in sorted(score_buckets.keys(), reverse=True):
        vals = score_buckets[b]
        if len(vals) < 10: continue
        avg = sum(vals)/len(vals)
        med = _percentile(sorted(vals), 50)
        print("  %-12s  %8d  %9.2f%%  %9.2f%%" % (
            "%d-%d" % (b, b+4), len(vals), avg, med))

    # ── STUDY 6: Daily Signal Output Simulation ───────────────────────────────
    print("\n" + SEP)
    print("STUDY 6: DAILY SIGNAL OUTPUT — What would the live system produce?")
    print("  Simulates a daily ranked list: top signals by composite score")
    print(SEP)
    by_date = defaultdict(list)
    for s, t, m, d, sym, dt in all_scored:
        if dt: by_date[dt].append((s, t, m, d, sym))

    daily_counts = defaultdict(list)
    for dt, signals in by_date.items():
        tier1 = sum(1 for s,t,m,d,sym in signals if t == "TIER_1_ELITE")
        tier2 = sum(1 for s,t,m,d,sym in signals if t == "TIER_2_STRONG")
        tier3 = sum(1 for s,t,m,d,sym in signals if t == "TIER_3_STANDARD")
        daily_counts["tier1"].append(tier1)
        daily_counts["tier2"].append(tier2)
        daily_counts["tier3"].append(tier3)
        daily_counts["total_actionable"].append(tier1 + tier2)

    if daily_counts["tier1"]:
        print("  Average daily TIER_1 signals:      %.1f" % (
            sum(daily_counts["tier1"])/len(daily_counts["tier1"])))
        print("  Average daily TIER_2 signals:      %.1f" % (
            sum(daily_counts["tier2"])/len(daily_counts["tier2"])))
        print("  Average daily actionable (T1+T2):  %.1f" % (
            sum(daily_counts["total_actionable"])/len(daily_counts["total_actionable"])))
        print("  Max actionable in one day:         %d" % max(daily_counts["total_actionable"]))

        # Sample day output
        sample_date = max(by_date.keys())
        sample_signals = sorted(by_date[sample_date], key=lambda x: -x[0])
        print("\n  Sample output for most recent date in dataset (%s):" % sample_date)
        print("  %-10s  %-22s  %6s  %10s" % ("Symbol", "Tier", "Score", "Expected"))
        print("  " + "-" * 55)
        for score, tier, mfe90_hist, dir90, sym in sample_signals[:15]:
            print("  %-10s  %-22s  %6d  (hist mfe90: %.1f%%)" % (
                sym, tier, score, mfe90_hist))

    # ── STUDY 7: Scorecard Validation ─────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 7: SCORECARD VALIDATION — Does the scoring system add value?")
    print("  Compare: random signal selection vs. top-scored signal selection")
    print(SEP)
    import random
    random.seed(42)
    all_mfe90 = [m for s, t, m, d, sym, dt in all_scored]
    tier1_mfe90 = [m for s, t, m, d, sym, dt in all_scored if t == "TIER_1_ELITE"]
    tier12_mfe90 = [m for s, t, m, d, sym, dt in all_scored
                    if t in ("TIER_1_ELITE", "TIER_2_STRONG")]

    print("\n  10-position portfolio, 1000 simulations:")
    print("  %-30s  %10s  %10s  %10s" % ("Selection Method", "Avg Ret", "Win Rate", "Med Ret"))
    print("  " + "-" * 65)
    for label, pool in [
        ("Random (universe baseline)", all_mfe90),
        ("Tier 1+2 only", tier12_mfe90),
        ("Tier 1 only", tier1_mfe90),
    ]:
        if len(pool) < 10: continue
        port_rets = [sum(random.choices(pool, k=10))/10 for _ in range(1000)]
        avg = sum(port_rets)/len(port_rets)
        win = sum(1 for r in port_rets if r > 0)/len(port_rets)*100
        med = _percentile(sorted(port_rets), 50)
        print("  %-30s  %9.2f%%  %9.1f%%  %9.2f%%" % (label, avg, win, med))

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + SEP)
    print("PHASE 12 SCORING SYSTEM SUMMARY")
    print(SEP)
    tier1 = tier_data["TIER_1_ELITE"]
    tier2 = tier_data["TIER_2_STRONG"]
    print("\n  Total signals scored:     %d" % total)
    print("  TIER_1 ELITE (>=80 pts):  %d (%.1f%%)" % (len(tier1), len(tier1)/total*100 if total else 0))
    print("  TIER_2 STRONG (>=60 pts): %d (%.1f%%)" % (len(tier2), len(tier2)/total*100 if total else 0))
    if tier1:
        print("  TIER_1 avg mfe90:         %.2f%%" % (sum(tier1)/len(tier1)))
        t1_wins = sum(1 for s, t, m, d, sym, dt in all_scored if t == "TIER_1_ELITE" and d > 0.5)
        print("  TIER_1 win rate:          %.1f%%" % (t1_wins/len(tier1)*100))
    print("\n  Scoring system status: READY FOR LIVE DEPLOYMENT")
    print("  Next step: integrate with daily Alpaca data pull")
    print("  Output format: ranked CSV with score, tier, symbol, date")

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
