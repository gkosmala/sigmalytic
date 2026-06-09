#!/usr/bin/env python3
"""
Phase 10: Risk Management and Position Sizing
Two-layer analysis:
  Layer A — Core Risk Model: OBS_Q4 + PROG_Q4 + State 1
  Layer B — Premium Signal:  OBS_Q4 + PROG_Q4 + State 1 + DUR_60_120 + ACCUMULATION

Primary question: How much pain does a true winner normally experience
before it becomes obvious? That is the stop-placement question.

Studies:
  1. MAE distribution by layer (20d and 90d)
  2. Stop-out rates at -5%, -8%, -10%, -12%, -15%, -20%
  3. Recovery rate: % of signals that hit a given stop depth but recovered
  4. MFE/MAE asymmetry ratio by layer
  5. Optimal stop: maximizes (winners kept) / (losers stopped)
  6. Position sizing: Kelly fraction by layer
  7. Drawdown simulation: 10/20/30 position portfolios
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
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)

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
        enriched.append((r, o, pr))

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
        if d >= 60: return "DUR_60_120"
        if d >= 20: return "DUR_20_60"
        return "DUR_UNDER_20"

    # ── Collect risk metrics ───────────────────────────────────────────────────
    # For each signal: mfe20, mfe90, mae20, mae90, h90_dir, h20_dir, acc90
    def risk_payload(r):
        mfe90 = _f(r.get("markup_90d_pct"))
        if mfe90 is None: return None
        mfe20 = _f(r.get("markup_20d_pct")) or 0.0
        mfe40 = _f(r.get("markup_40d_pct")) or 0.0
        mfe60 = _f(r.get("markup_60d_pct")) or 0.0
        mae20 = _f(r.get("h20_mae_pct")) or 0.0
        mae90 = _f(r.get("h90_mae_pct")) or 0.0  # using h90 mae as proxy
        h20_dir = _f(r.get("h20_direction_correct")) or 0.0
        h90_dir = _f(r.get("h90_direction_correct")) or 0.0
        h90_ret = _f(r.get("h90_return_pct")) or 0.0
        asym = (mfe20 / abs(mae20)) if (mfe20 > 0 and mae20 < 0) else 0.0
        return {
            "mfe20": mfe20, "mfe90": mfe90, "mfe40": mfe40, "mfe60": mfe60,
            "mae20": mae20, "mae90": mae90,
            "h20_dir": h20_dir, "h90_dir": h90_dir, "h90_ret": h90_ret,
            "asym": asym
        }

    layer_a = []  # OBS_Q4 + PROG_Q4 + State 1
    layer_b = []  # + DUR_60_120 + ACCUMULATION
    universe = []

    for r, o, pr in enriched:
        p = risk_payload(r)
        if p is None: continue
        spd = _b(r.get("w_selling_pressure_diminishing"))
        dei = _b(r.get("w_demand_efficiency_improving"))
        days = _f(r.get("p5_days_since_252_high")) or 0.0
        bhv = str(r.get("behavior_classification", "")).strip()
        is_state1 = spd and not dei
        is_a = (ot(o) == "Q4" and pt(pr) == "Q4" and is_state1)
        is_b = is_a and dur(days) == "DUR_60_120" and bhv == "ACCUMULATION"
        universe.append(p)
        if is_a: layer_a.append(p)
        if is_b: layer_b.append(p)

    print("Layer A (OBS_Q4+PROG_Q4+State1): n=%d" % len(layer_a))
    print("Layer B (+ DUR_60_120+ACCUM):    n=%d" % len(layer_b))
    print("Universe:                         n=%d" % len(universe))

    SEP = "=" * 100

    # ── STUDY 1: MAE Distribution ─────────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 1: MAE DISTRIBUTION — How deep does price go before resolving?")
    print(SEP)
    print("%-30s  %8s  %8s  %8s  %8s  %8s  %8s  %8s" % (
        "Population", "n", "MAE20_med", "MAE20_75p", "MAE20_90p",
        "MAE90_med", "MAE90_75p", "MAE90_90p"))
    print("-" * 100)
    for label, data in [("Universe", universe), ("Layer A", layer_a), ("Layer B", layer_b)]:
        mae20s = [abs(p["mae20"]) for p in data if p["mae20"] < 0]
        mae90s = [abs(p["mae90"]) for p in data if p["mae90"] < 0]
        if not mae20s: continue
        print("%-30s  %8d  %8.2f%%  %8.2f%%  %8.2f%%  %8.2f%%  %8.2f%%  %8.2f%%" % (
            label, len(data),
            _percentile(mae20s, 50), _percentile(mae20s, 75), _percentile(mae20s, 90),
            _percentile(mae90s, 50) if mae90s else 0,
            _percentile(mae90s, 75) if mae90s else 0,
            _percentile(mae90s, 90) if mae90s else 0))

    # ── STUDY 2: Stop-Out Rate Analysis ───────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 2: STOP-OUT RATES — What % of signals hit each stop level?")
    print("         And of those that hit it, what % eventually recovered?")
    print(SEP)
    stops = [3, 5, 8, 10, 12, 15, 20]
    for label, data in [("Layer A (n=%d)" % len(layer_a), layer_a),
                        ("Layer B (n=%d)" % len(layer_b), layer_b)]:
        print("\n  %s" % label)
        print("  %-8s  %-12s  %-15s  %-15s  %-12s" % (
            "Stop%", "Hit Rate", "Recovery Rate", "Avg MFE90 if Hit", "Net Win Rate"))
        print("  " + "-" * 65)
        for stop in stops:
            hit = [p for p in data if abs(p["mae20"]) >= stop]
            hit_rate = len(hit) / len(data) * 100 if data else 0
            # recovery: hit stop but mfe90 > stop (went on to make money)
            recovered = [p for p in hit if p["mfe90"] > stop]
            rec_rate = len(recovered) / len(hit) * 100 if hit else 0
            avg_mfe90_if_hit = sum(p["mfe90"] for p in hit) / len(hit) if hit else 0
            # net win rate: signals that were NOT stopped out AND direction correct
            not_stopped = [p for p in data if abs(p["mae20"]) < stop]
            winners = [p for p in not_stopped if p["h90_dir"] > 0.5]
            net_win = len(winners) / len(data) * 100 if data else 0
            print("  %-8s  %11.1f%%  %14.1f%%  %15.2f%%  %11.1f%%" % (
                "-%d%%" % stop, hit_rate, rec_rate, avg_mfe90_if_hit, net_win))

    # ── STUDY 3: Stop Efficiency Score ────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 3: STOP EFFICIENCY — Optimize (winners kept) vs (losers stopped)")
    print("  Efficiency = Recovery Rate x (1 - Hit Rate)")
    print("  Higher = stop preserves more eventual winners while stopping real losers")
    print(SEP)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        print("\n  %s" % label)
        best_stop = None; best_eff = 0
        for stop in stops:
            hit = [p for p in data if abs(p["mae20"]) >= stop]
            hit_rate = len(hit) / len(data) if data else 0
            recovered = [p for p in hit if p["mfe90"] > stop]
            rec_rate = len(recovered) / len(hit) if hit else 0
            # true losers stopped: hit stop AND never recovered AND h90 direction wrong
            true_losers = [p for p in hit if p["mfe90"] <= stop and p["h90_dir"] < 0.5]
            loser_stop_rate = len(true_losers) / len(hit) if hit else 0
            efficiency = rec_rate * (1 - hit_rate) + loser_stop_rate * hit_rate
            flag = " <-- OPTIMAL" if efficiency > best_eff else ""
            print("  Stop -%d%%:  HitRate=%5.1f%%  RecoveryRate=%5.1f%%  Efficiency=%.3f%s" % (
                stop, hit_rate*100, rec_rate*100, efficiency, flag))
            if efficiency > best_eff:
                best_eff = efficiency
                best_stop = stop
        print("  Recommended stop for %s: -%s%%" % (label, str(best_stop) if best_stop else "N/A"))

    # ── STUDY 4: MFE/MAE Asymmetry ────────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 4: MFE/MAE ASYMMETRY — Reward-to-risk by population")
    print(SEP)
    for label, data in [("Universe", universe), ("Layer A", layer_a), ("Layer B", layer_b)]:
        asyms = [p["asym"] for p in data if p["asym"] > 0 and p["asym"] < 100]
        mfe20s = [p["mfe20"] for p in data]
        mae20s = [abs(p["mae20"]) for p in data if p["mae20"] < 0]
        if not asyms: continue
        print("%-30s  n=%5d  AsymMed=%5.2f  Asym75p=%5.2f  MFE20med=%5.2f%%  MAE20med=%5.2f%%" % (
            label, len(data),
            _percentile(asyms, 50), _percentile(asyms, 75),
            _percentile(mfe20s, 50),
            _percentile(mae20s, 50) if mae20s else 0))

    # ── STUDY 5: Asymmetry as Stop Predictor ──────────────────────────────────
    print("\n" + SEP)
    print("STUDY 5: ASYMMETRY TIERS — Do high-asym signals tolerate wider stops?")
    print(SEP)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        print("\n  %s" % label)
        tiers = [("ASYM_5PLUS", [p for p in data if p["asym"] >= 5]),
                 ("ASYM_3_5",   [p for p in data if 3 <= p["asym"] < 5]),
                 ("ASYM_1_3",   [p for p in data if 1 <= p["asym"] < 3]),
                 ("ASYM_UNDER1",[p for p in data if p["asym"] < 1])]
        print("  %-15s  %6s  %9s  %9s  %9s  %9s" % (
            "Asym Tier", "n", "MAE20_med", "MAE20_90p", "MFE90_med", "WinRate90"))
        print("  " + "-" * 65)
        for tier_name, tier_data in tiers:
            if len(tier_data) < 5: continue
            mae20s = [abs(p["mae20"]) for p in tier_data if p["mae20"] < 0]
            mfe90s = [p["mfe90"] for p in tier_data]
            win90 = sum(1 for p in tier_data if p["h90_dir"] > 0.5) / len(tier_data) * 100
            print("  %-15s  %6d  %9.2f%%  %9.2f%%  %9.2f%%  %9.1f%%" % (
                tier_name, len(tier_data),
                _percentile(mae20s, 50) if mae20s else 0,
                _percentile(mae20s, 90) if mae20s else 0,
                _percentile(mfe90s, 50),
                win90))

    # ── STUDY 6: Position Sizing — Kelly Criterion ────────────────────────────
    print("\n" + SEP)
    print("STUDY 6: POSITION SIZING — Kelly Criterion by layer")
    print("  Kelly = W - (1-W)/R  where W=win rate, R=win/loss ratio")
    print("  Half-Kelly recommended for live trading")
    print(SEP)
    for label, data in [("Universe", universe), ("Layer A", layer_a), ("Layer B", layer_b)]:
        wins = [p for p in data if p["h90_dir"] > 0.5]
        losses = [p for p in data if p["h90_dir"] <= 0.5]
        if not wins or not losses: continue
        W = len(wins) / len(data)
        avg_win = sum(p["h90_ret"] for p in wins) / len(wins)
        avg_loss = abs(sum(p["h90_ret"] for p in losses) / len(losses))
        R = avg_win / avg_loss if avg_loss > 0 else 0
        kelly = W - (1 - W) / R if R > 0 else 0
        half_kelly = kelly / 2
        print("%-30s  n=%5d  WinRate=%5.1f%%  AvgWin=%6.2f%%  AvgLoss=%6.2f%%  R=%5.2f  Kelly=%5.1f%%  HalfKelly=%5.1f%%" % (
            label, len(data), W*100, avg_win, avg_loss, R,
            kelly*100, half_kelly*100))

    # ── STUDY 7: Drawdown Simulation ──────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 7: DRAWDOWN SIMULATION — Portfolio of N simultaneous positions")
    print("  Assumes positions are independent (correlation=0 conservative estimate)")
    print("  Uses realized h90_return_pct for each signal")
    print(SEP)
    import random
    random.seed(42)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        rets = [p["h90_ret"] for p in data]
        if len(rets) < 30: continue
        print("\n  %s" % label)
        print("  %-15s  %10s  %10s  %10s  %10s" % (
            "Portfolio Size", "Avg Return", "Med Return", "Max Drawdown", "Win Rate"))
        print("  " + "-" * 55)
        for n_pos in [10, 20, 30]:
            n_sims = 1000
            port_returns = []
            max_dds = []
            for _ in range(n_sims):
                sample = random.choices(rets, k=n_pos)
                port_ret = sum(sample) / n_pos
                port_returns.append(port_ret)
                # simple max drawdown: worst single position
                max_dds.append(min(sample))
            avg_ret = sum(port_returns) / len(port_returns)
            med_ret = _percentile(sorted(port_returns), 50)
            avg_dd = sum(max_dds) / len(max_dds)
            win_rate = sum(1 for r in port_returns if r > 0) / len(port_returns) * 100
            print("  %-15d  %9.2f%%  %9.2f%%  %9.2f%%  %9.1f%%" % (
                n_pos, avg_ret, med_ret, avg_dd, win_rate))

    # ── STUDY 8: Winners-Only MAE — True Pain Before Resolution ──────────────
    print("\n" + SEP)
    print("STUDY 8: WINNERS-ONLY MAE — Normal MAE for signals that ACTUALLY resolved")
    print("  Filters to h90_direction_correct=1 only.")
    print("  This is the true expected drawdown a patient holder experiences.")
    print(SEP)
    print("%-30s  %8s  %8s  %8s  %8s  %8s" % (
        "Population", "n_winners", "MAE20_med", "MAE20_75p", "MAE20_90p", "MAE20_max"))
    print("-" * 75)
    for label, data in [("Universe (winners only)", universe),
                        ("Layer A (winners only)", layer_a),
                        ("Layer B (winners only)", layer_b)]:
        winners = [p for p in data if p["h90_dir"] > 0.5]
        if not winners: continue
        mae20s = [abs(p["mae20"]) for p in winners if p["mae20"] < 0]
        if not mae20s: continue
        print("%-30s  %8d  %8.2f%%  %8.2f%%  %8.2f%%  %8.2f%%" % (
            label, len(winners),
            _percentile(mae20s, 50),
            _percentile(mae20s, 75),
            _percentile(mae20s, 90),
            max(mae20s)))

    # Compare winners vs losers MAE
    print("\n  Winner vs Loser MAE Comparison (separates signal from noise):")
    print("%-30s  %8s  %8s  %8s" % ("Population", "n", "MAE20_med", "MAE20_90p"))
    print("-" * 55)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        winners = [p for p in data if p["h90_dir"] > 0.5]
        losers  = [p for p in data if p["h90_dir"] <= 0.5]
        for sublabel, subset in [("  Winners", winners), ("  Losers", losers)]:
            if not subset: continue
            mae20s = [abs(p["mae20"]) for p in subset if p["mae20"] < 0]
            if not mae20s: continue
            print("%-30s  %8d  %8.2f%%  %8.2f%%" % (
                "%s (%s)" % (label, sublabel.strip()),
                len(subset),
                _percentile(mae20s, 50),
                _percentile(mae20s, 90)))

    # Stop survival rate for winners only
    print("\n  Stop survival: what % of WINNERS would survive each stop level?")
    print("  (These are the signals a stop would incorrectly eliminate)")
    print("%-15s  %-20s  %-20s" % ("Stop Level", "Layer A Winners Killed", "Layer B Winners Killed"))
    print("-" * 58)
    a_winners = [p for p in layer_a if p["h90_dir"] > 0.5]
    b_winners = [p for p in layer_b if p["h90_dir"] > 0.5]
    for stop in [3, 5, 8, 10, 12, 15, 20]:
        a_killed = sum(1 for p in a_winners if abs(p["mae20"]) >= stop)
        b_killed = sum(1 for p in b_winners if abs(p["mae20"]) >= stop)
        a_pct = a_killed / len(a_winners) * 100 if a_winners else 0
        b_pct = b_killed / len(b_winners) * 100 if b_winners else 0
        print("%-15s  %6d (%5.1f%%)          %6d (%5.1f%%)" % (
            "-%d%%" % stop, a_killed, a_pct, b_killed, b_pct))

    # ── STUDY 9: Failure Analysis ─────────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 9: FAILURE ANALYSIS — What causes Layer A signals to fail?")
    print("  Profiles losing signals across all available dimensions.")
    print(SEP)
    from collections import Counter
    elite_winners = []; elite_losers = []
    for r in rows:
        mfe90v = _f(r.get("markup_90d_pct"))
        if mfe90v is None: continue
        o9 = _obs(r); pr9 = _prog(r)
        spd9 = _b(r.get("w_selling_pressure_diminishing"))
        dei9 = _b(r.get("w_demand_efficiency_improving"))
        days9 = _f(r.get("p5_days_since_252_high")) or 0.0
        bhv9 = str(r.get("behavior_classification", "")).strip()
        is_state1_9 = spd9 and not dei9
        is_a9 = (ot(o9) == "Q4" and pt(pr9) == "Q4" and is_state1_9)
        if not is_a9: continue
        if not is_a: continue

        h90_ret = _f(r.get("h90_return_pct")) or 0.0
        h90_dir = _f(r.get("h90_direction_correct")) or 0.0
        mae20   = _f(r.get("h20_mae_pct")) or 0.0
        rs      = _f(r.get("rs_daily")) or 0.0
        rv      = str(r.get("rel_volume_bucket", "")).strip()
        date    = str(r.get("signal_date", ""))
        sym     = str(r.get("symbol", ""))

        record = {
            "h90_ret": h90_ret, "h90_dir": h90_dir, "mfe90": mfe90v,
            "mae20": mae20, "bhv": bhv9, "days": days9, "rs": rs,
            "rv": rv, "date": date, "sym": sym,
            "obs": o9, "prog": pr9,
        }
        if h90_dir > 0.5:
            elite_winners.append(record)
        else:
            elite_losers.append(record)

    print("\n  Layer A population breakdown:")
    print("    Winners (h90_dir=1): %d (%.1f%%)" % (
        len(elite_winners),
        len(elite_winners)/(len(elite_winners)+len(elite_losers))*100 if elite_winners or elite_losers else 0))
    print("    Losers  (h90_dir=0): %d (%.1f%%)" % (
        len(elite_losers),
        len(elite_losers)/(len(elite_winners)+len(elite_losers))*100 if elite_winners or elite_losers else 0))

    if elite_losers and elite_winners:
        print("\n  FAILURE PROFILE — How do losers differ from winners?")

        # Duration
        print("\n  A. Duration Distribution:")
        def dur_label(d):
            if d >= 180: return "DUR_180+"
            if d >= 120: return "DUR_120_180"
            if d >= 60:  return "DUR_60_120"
            if d >= 20:  return "DUR_20_60"
            return "DUR_UNDER_20"
        from collections import Counter
        w_dur = Counter(dur_label(r["days"]) for r in elite_winners)
        l_dur = Counter(dur_label(r["days"]) for r in elite_losers)
        all_durs = ["DUR_60_120","DUR_120_180","DUR_180+","DUR_20_60","DUR_UNDER_20"]
        print("  %-20s  %10s  %10s  %12s" % ("Duration", "Winners%", "Losers%", "Loser Ratio"))
        for d in all_durs:
            wp = w_dur.get(d,0)/len(elite_winners)*100
            lp = l_dur.get(d,0)/len(elite_losers)*100
            ratio = lp/wp if wp > 0 else 0
            flag = "  <-- OVERREPRESENTED IN FAILURES" if ratio > 1.5 else ""
            print("  %-20s  %9.1f%%  %9.1f%%  %11.2fx%s" % (d, wp, lp, ratio, flag))

        # Behavioral Classification
        print("\n  B. Behavioral Classification:")
        w_bhv = Counter(r["bhv"] for r in elite_winners)
        l_bhv = Counter(r["bhv"] for r in elite_losers)
        for b in sorted(set(list(w_bhv.keys())+list(l_bhv.keys()))):
            wp = w_bhv.get(b,0)/len(elite_winners)*100
            lp = l_bhv.get(b,0)/len(elite_losers)*100
            ratio = lp/wp if wp > 0 else 0
            flag = "  <-- OVERREPRESENTED IN FAILURES" if ratio > 1.5 else ""
            print("  %-20s  Winners:%5.1f%%  Losers:%5.1f%%  Ratio:%.2fx%s" % (b, wp, lp, ratio, flag))

        # RS Daily
        print("\n  C. RS Daily Distribution (winners vs losers):")
        def rs_label(v):
            if v >= 90: return "RS_90+"
            if v >= 70: return "RS_70_90"
            if v >= 50: return "RS_50_70"
            if v >= 30: return "RS_30_50"
            return "RS_UNDER_30"
        w_rs = Counter(rs_label(r["rs"]) for r in elite_winners)
        l_rs = Counter(rs_label(r["rs"]) for r in elite_losers)
        for rslabel in ["RS_90+","RS_70_90","RS_50_70","RS_30_50","RS_UNDER_30"]:
            wp = w_rs.get(rslabel,0)/len(elite_winners)*100
            lp = l_rs.get(rslabel,0)/len(elite_losers)*100
            ratio = lp/wp if wp > 0 else 0
            flag = "  <-- OVERREPRESENTED IN FAILURES" if ratio > 1.5 else ""
            print("  %-15s  Winners:%5.1f%%  Losers:%5.1f%%  Ratio:%.2fx%s" % (rslabel, wp, lp, ratio, flag))

        # Relative Volume
        print("\n  D. Relative Volume at Signal:")
        w_rv = Counter(r["rv"] for r in elite_winners)
        l_rv = Counter(r["rv"] for r in elite_losers)
        all_rvs = sorted(set(list(w_rv.keys())+list(l_rv.keys())))
        for rv in all_rvs:
            if not rv: continue
            wp = w_rv.get(rv,0)/len(elite_winners)*100
            lp = l_rv.get(rv,0)/len(elite_losers)*100
            ratio = lp/wp if wp > 0 else 0
            flag = "  <-- OVERREPRESENTED IN FAILURES" if ratio > 1.5 else ""
            print("  %-25s  Winners:%5.1f%%  Losers:%5.1f%%  Ratio:%.2fx%s" % (rv, wp, lp, ratio, flag))

        # MAE of losers — were they deeper drawdowns?
        print("\n  E. MAE Profile of Losers vs Winners:")
        w_maes = [abs(r["mae20"]) for r in elite_winners if r["mae20"] < 0]
        l_maes = [abs(r["mae20"]) for r in elite_losers if r["mae20"] < 0]
        if w_maes and l_maes:
            print("    Winners MAE20 median:  %.2f%%" % _percentile(sorted(w_maes), 50))
            print("    Losers  MAE20 median:  %.2f%%" % _percentile(sorted(l_maes), 50))
            print("    Winners MAE20 90th:    %.2f%%" % _percentile(sorted(w_maes), 90))
            print("    Losers  MAE20 90th:    %.2f%%" % _percentile(sorted(l_maes), 90))

        # Date clustering — are failures concentrated in time?
        print("\n  F. Date Clustering — Are failures concentrated in specific periods?")
        l_months = Counter(r["date"][:7] for r in elite_losers if r["date"])
        w_months = Counter(r["date"][:7] for r in elite_winners if r["date"])
        all_months = sorted(set(list(l_months.keys())+list(w_months.keys())))
        print("  Month        Winners  Losers  Loss Rate")
        print("  " + "-" * 40)
        for m in all_months:
            w = w_months.get(m, 0)
            l = l_months.get(m, 0)
            total = w + l
            if total < 3: continue
            loss_rate = l / total * 100
            flag = "  *** HIGH FAILURE RATE" if loss_rate > 60 else ""
            print("  %-12s  %7d  %6d  %8.1f%%%s" % (m, w, l, loss_rate, flag))

        # Summary of failure causes
        print("\n  G. FAILURE CAUSE SUMMARY")
        print("  Based on the above analysis, elite signal failures are most likely caused by:")
        # Find the most overrepresented factors
        factors = []
        for d in all_durs:
            wp = w_dur.get(d,0)/len(elite_winners)*100 if elite_winners else 0
            lp = l_dur.get(d,0)/len(elite_losers)*100 if elite_losers else 0
            if wp > 0 and lp/wp > 1.5:
                factors.append(("Duration: %s" % d, lp/wp))
        for b in set(list(w_bhv.keys())+list(l_bhv.keys())):
            wp = w_bhv.get(b,0)/len(elite_winners)*100 if elite_winners else 0
            lp = l_bhv.get(b,0)/len(elite_losers)*100 if elite_losers else 0
            if wp > 0 and lp/wp > 1.5:
                factors.append(("Behavioral: %s" % b, lp/wp))
        for rsl in ["RS_90+","RS_70_90","RS_50_70","RS_30_50","RS_UNDER_30"]:
            wp = w_rs.get(rsl,0)/len(elite_winners)*100 if elite_winners else 0
            lp = l_rs.get(rsl,0)/len(elite_losers)*100 if elite_losers else 0
            if wp > 0 and lp/wp > 1.5:
                factors.append(("RS Zone: %s" % rsl, lp/wp))
        if factors:
            for factor, ratio in sorted(factors, key=lambda x: -x[1]):
                print("    %s (%.1fx overrepresented in failures)" % (factor, ratio))
        else:
            print("    No single factor dominates failure rate — failures appear randomly distributed.")
            print("    This suggests failures are driven by macro/regime factors rather than signal characteristics.")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print("\n" + SEP)
    print("PHASE 10 SUMMARY — Risk Model Recommendations")
    print(SEP)
    print("\n  LAYER A — Core Signal (OBS_Q4 + PROG_Q4 + State 1)")
    a_mae20s = [abs(p["mae20"]) for p in layer_a if p["mae20"] < 0]
    if a_mae20s:
        print("    Median MAE20:        %.2f%%" % _percentile(a_mae20s, 50))
        print("    75th pct MAE20:      %.2f%%" % _percentile(a_mae20s, 75))
        print("    90th pct MAE20:      %.2f%%" % _percentile(a_mae20s, 90))
    a_wins = [p for p in layer_a if p["h90_dir"] > 0.5]
    print("    Win Rate (90d):      %.1f%%" % (len(a_wins)/len(layer_a)*100 if layer_a else 0))
    print("    Median MFE90:        %.2f%%" % _percentile(sorted([p["mfe90"] for p in layer_a]), 50))
    print("\n  LAYER B — Premium Signal (+ DUR_60_120 + ACCUMULATION)")
    b_mae20s = [abs(p["mae20"]) for p in layer_b if p["mae20"] < 0]
    if b_mae20s:
        print("    Median MAE20:        %.2f%%" % _percentile(b_mae20s, 50))
        print("    75th pct MAE20:      %.2f%%" % _percentile(b_mae20s, 75))
        print("    90th pct MAE20:      %.2f%%" % _percentile(b_mae20s, 90))
    b_wins = [p for p in layer_b if p["h90_dir"] > 0.5]
    print("    Win Rate (90d):      %.1f%%" % (len(b_wins)/len(layer_b)*100 if layer_b else 0))
    print("    Median MFE90:        %.2f%%" % _percentile(sorted([p["mfe90"] for p in layer_b]), 50))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
