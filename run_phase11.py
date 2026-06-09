#!/usr/bin/env python3
"""
Phase 11: Portfolio Construction and Correlation Management

Central question: Does holding a diversified set of simultaneous Sigmalytic
signals produce a smoother return profile than single-signal metrics suggest?

Studies:
  1. Signal frequency — how many signals qualify per day/week/month?
  2. Sector concentration — are signals clustered by sector?
  3. Simultaneous signal correlation — do concurrent signals move together?
  4. Portfolio simulation — equal-weight portfolios of N positions
  5. Duration overlap — how long are positions held, what is typical overlap?
  6. Diversification benefit — does adding more positions improve risk-adjusted return?
  7. Layer comparison — Layer A vs Layer B portfolio characteristics
  8. Optimal position count — where does diversification benefit plateau?

Data used: symbol, signal_date, h90_return_pct, markup_90d_pct,
           h90_direction_correct, h20_mae_pct already in dataset.
Sector data approximated from symbol prefix patterns (Russell 1000).
"""
import csv, math, sys, random
from collections import defaultdict
from datetime import datetime, timedelta

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

def _sharpe(returns, rf=0.0):
    if len(returns) < 2: return 0.0
    n = len(returns)
    mean = sum(returns) / n
    variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance) if variance > 0 else 0.0
    return (mean - rf) / std if std > 0 else 0.0

def _max_drawdown(returns):
    if not returns: return 0.0
    peak = 0.0; max_dd = 0.0; cumulative = 0.0
    for r in returns:
        cumulative += r
        if cumulative > peak: peak = cumulative
        dd = peak - cumulative
        if dd > max_dd: max_dd = dd
    return max_dd

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

    # ── Build signal records ──────────────────────────────────────────────────
    layer_a = []
    layer_b = []

    for r, o, pr in enriched:
        spd = _b(r.get("w_selling_pressure_diminishing"))
        dei = _b(r.get("w_demand_efficiency_improving"))
        days = _f(r.get("p5_days_since_252_high")) or 0.0
        bhv = str(r.get("behavior_classification", "")).strip()
        is_state1 = spd and not dei
        is_a = (ot(o) == "Q4" and pt(pr) == "Q4" and is_state1)
        is_b = is_a and dur(days) == "DUR_60_120" and bhv == "ACCUMULATION"

        signal = {
            "symbol": str(r.get("symbol", "")),
            "date": str(r.get("signal_date", "")),
            "h90_ret": _f(r.get("h90_return_pct")) or 0.0,
            "h90_dir": _f(r.get("h90_direction_correct")) or 0.0,
            "mfe90": _f(r.get("markup_90d_pct")) or 0.0,
            "mae20": _f(r.get("h20_mae_pct")) or 0.0,
            "rs_daily": _f(r.get("rs_daily")) or 0.0,
            "bhv": bhv,
            "dur": dur(days),
        }
        if is_a: layer_a.append(signal)
        if is_b: layer_b.append(signal)

    print("Layer A signals: %d" % len(layer_a))
    print("Layer B signals: %d" % len(layer_b))

    SEP = "=" * 100

    # ── STUDY 1: Signal Frequency ─────────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 1: SIGNAL FREQUENCY — How many signals qualify per period?")
    print(SEP)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        dates = [s["date"] for s in data if s["date"]]
        by_month = defaultdict(int)
        by_year = defaultdict(int)
        for d in dates:
            parts = d[:7] if len(d) >= 7 else d
            by_month[parts] += 1
            by_year[d[:4]] += 1
        if by_month:
            monthly = list(by_month.values())
            print("\n  %s:" % label)
            print("    Total signals:      %d" % len(data))
            print("    Unique months:      %d" % len(by_month))
            print("    Avg per month:      %.1f" % (sum(monthly)/len(monthly)))
            print("    Max in one month:   %d" % max(monthly))
            print("    Min in one month:   %d" % min(monthly))
            print("    Median per month:   %.1f" % _percentile(sorted(monthly), 50))

    # ── STUDY 2: Symbol Concentration ────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 2: SYMBOL CONCENTRATION — Do same symbols appear repeatedly?")
    print(SEP)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        by_symbol = defaultdict(int)
        for s in data: by_symbol[s["symbol"]] += 1
        counts = sorted(by_symbol.values(), reverse=True)
        unique = len(by_symbol)
        repeat = sum(1 for c in counts if c > 1)
        print("\n  %s:" % label)
        print("    Unique symbols:      %d" % unique)
        print("    Symbols appearing 2+ times: %d (%.1f%%)" % (repeat, repeat/unique*100 if unique else 0))
        print("    Max appearances (one symbol): %d" % (counts[0] if counts else 0))
        print("    Top 10 most frequent:")
        top10 = sorted(by_symbol.items(), key=lambda x: -x[1])[:10]
        for sym, cnt in top10:
            print("      %-10s  %d signals" % (sym, cnt))

    # ── STUDY 3: RS Daily Distribution (proxy for market cap / sector spread) ─
    print("\n" + SEP)
    print("STUDY 3: RS DAILY DISTRIBUTION — Signal spread across relative strength spectrum")
    print(SEP)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        rs_vals = [s["rs_daily"] for s in data if s["rs_daily"] > 0]
        if not rs_vals: continue
        buckets = defaultdict(int)
        for v in rs_vals:
            b = int(v // 10) * 10
            buckets[b] += 1
        print("\n  %s (n=%d):" % (label, len(data)))
        print("    RS Median:  %.1f    RS 25th: %.1f    RS 75th: %.1f" % (
            _percentile(sorted(rs_vals), 50),
            _percentile(sorted(rs_vals), 25),
            _percentile(sorted(rs_vals), 75)))
        for b in sorted(buckets.keys()):
            bar = "#" * (buckets[b] * 30 // max(buckets.values()))
            print("    RS %2d-%2d:  %4d  %s" % (b, b+10, buckets[b], bar))

    # ── STUDY 4: Behavioral Classification Mix ────────────────────────────────
    print("\n" + SEP)
    print("STUDY 4: BEHAVIORAL MIX — Distribution across classification types")
    print(SEP)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        by_bhv = defaultdict(list)
        for s in data: by_bhv[s["bhv"]].append(s["h90_ret"])
        print("\n  %s (n=%d):" % (label, len(data)))
        for bhv_type, rets in sorted(by_bhv.items(), key=lambda x: -len(x[1])):
            win_rate = sum(1 for r in rets if r > 0) / len(rets) * 100
            avg_ret = sum(rets) / len(rets)
            print("    %-15s  n=%4d  (%5.1f%%)  AvgRet=%7.2f%%  WinRate=%5.1f%%" % (
                bhv_type, len(rets), len(rets)/len(data)*100, avg_ret, win_rate))

    # ── STUDY 5: Portfolio Simulation ────────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 5: PORTFOLIO SIMULATION — Equal-weight portfolios of N positions")
    print("  1000 Monte Carlo simulations per portfolio size")
    print("  Metrics: Avg Return, Median Return, Sharpe, Max Drawdown, Win Rate")
    print(SEP)
    random.seed(42)

    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        rets = [s["h90_ret"] for s in data]
        if len(rets) < 30: continue
        print("\n  %s (universe of %d signals):" % (label, len(rets)))
        print("  %-8s  %10s  %10s  %10s  %12s  %10s" % (
            "N Pos", "Avg Ret", "Med Ret", "Sharpe", "Max Drawdown", "Win Rate"))
        print("  " + "-" * 65)

        for n_pos in [5, 10, 15, 20, 30]:
            n_sims = 1000
            port_rets = []
            drawdowns = []
            for _ in range(n_sims):
                sample = random.choices(rets, k=n_pos)
                port_ret = sum(sample) / n_pos
                port_rets.append(port_ret)
                drawdowns.append(_max_drawdown(sample))

            avg_ret = sum(port_rets) / len(port_rets)
            med_ret = _percentile(sorted(port_rets), 50)
            sharpe = _sharpe(port_rets)
            avg_dd = sum(drawdowns) / len(drawdowns)
            win_rate = sum(1 for r in port_rets if r > 0) / len(port_rets) * 100
            print("  %-8d  %9.2f%%  %9.2f%%  %10.3f  %11.2f%%  %9.1f%%" % (
                n_pos, avg_ret, med_ret, sharpe, avg_dd, win_rate))

    # ── STUDY 6: Diversification Benefit ─────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 6: DIVERSIFICATION BENEFIT — Sharpe improvement by position count")
    print("  Where does adding more positions stop improving risk-adjusted return?")
    print(SEP)
    random.seed(42)
    for label, data in [("Layer A", layer_a), ("Layer B", layer_b)]:
        rets = [s["h90_ret"] for s in data]
        if len(rets) < 30: continue
        print("\n  %s:" % label)
        prev_sharpe = 0.0
        for n_pos in [1, 3, 5, 8, 10, 15, 20, 25, 30]:
            port_rets = [sum(random.choices(rets, k=n_pos))/n_pos for _ in range(1000)]
            s = _sharpe(port_rets)
            improvement = s - prev_sharpe
            flag = " <-- DIMINISHING" if (n_pos > 5 and improvement < 0.05) else ""
            print("    N=%2d:  Sharpe=%.3f  Improvement=+%.3f%s" % (n_pos, s, improvement, flag))
            prev_sharpe = s

    # ── STUDY 7: Stop-Filtered Portfolio ─────────────────────────────────────
    print("\n" + SEP)
    print("STUDY 7: STOP-FILTERED PORTFOLIO — Apply Phase 10 stop rules")
    print("  Layer A: -10% stop    Layer B: -20% stop")
    print("  Stopped signals receive stop return; others receive h90_ret")
    print(SEP)
    random.seed(42)
    for label, data, stop_pct in [("Layer A", layer_a, -10.0), ("Layer B", layer_b, -20.0)]:
        # Apply stop: if mae20 worse than stop, realize stop loss
        stopped_rets = []
        for s in data:
            if s["mae20"] <= stop_pct:
                stopped_rets.append(stop_pct)
            else:
                stopped_rets.append(s["h90_ret"])
        if len(stopped_rets) < 10: continue
        raw_rets = [s["h90_ret"] for s in data]
        print("\n  %s (stop=%.0f%%):" % (label, stop_pct))
        print("    %-20s  %10s  %10s  %10s  %10s" % ("", "Avg Ret", "Win Rate", "Sharpe", "Max DD"))
        for port_label, rets in [("No stop (raw)", raw_rets), ("With stop applied", stopped_rets)]:
            n_sims = 1000; n_pos = 10
            port_rets = [sum(random.choices(rets, k=n_pos))/n_pos for _ in range(n_sims)]
            avg = sum(port_rets)/len(port_rets)
            win = sum(1 for r in port_rets if r > 0)/len(port_rets)*100
            sh = _sharpe(port_rets)
            dds = [_max_drawdown(random.choices(rets, k=n_pos)) for _ in range(n_sims)]
            avg_dd = sum(dds)/len(dds)
            print("    %-20s  %9.2f%%  %9.1f%%  %10.3f  %9.2f%%" % (
                port_label, avg, win, sh, avg_dd))

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    print("\n" + SEP)
    print("PHASE 11 SUMMARY — Portfolio Construction Recommendations")
    print(SEP)
    random.seed(42)
    for label, data, stop_pct in [("Layer A", layer_a, -10.0), ("Layer B", layer_b, -20.0)]:
        rets = [s["h90_ret"] for s in data]
        stopped = [stop_pct if s["mae20"] <= stop_pct else s["h90_ret"] for s in data]
        if len(rets) < 10: continue

        # Find optimal N
        best_n = 10; best_sharpe = 0.0
        for n_pos in [5, 10, 15, 20, 25, 30]:
            port_rets = [sum(random.choices(stopped, k=n_pos))/n_pos for _ in range(1000)]
            s = _sharpe(port_rets)
            if s > best_sharpe:
                best_sharpe = s; best_n = n_pos

        port_rets = [sum(random.choices(stopped, k=best_n))/best_n for _ in range(1000)]
        avg = sum(port_rets)/len(port_rets)
        win = sum(1 for r in port_rets if r > 0)/len(port_rets)*100
        dds = [_max_drawdown(random.choices(stopped, k=best_n)) for _ in range(1000)]
        avg_dd = sum(dds)/len(dds)
        p25 = _percentile(sorted(port_rets), 25)
        p75 = _percentile(sorted(port_rets), 75)

        print("\n  %s:" % label)
        print("    Optimal position count:   %d" % best_n)
        print("    Portfolio Sharpe:         %.3f" % best_sharpe)
        print("    Avg portfolio return:     %.2f%%" % avg)
        print("    Portfolio win rate:       %.1f%%" % win)
        print("    Avg max drawdown:         %.2f%%" % avg_dd)
        print("    Return 25th-75th pct:     %.2f%% to %.2f%%" % (p25, p75))
        pass_sharpe = "PASS" if best_sharpe >= 1.5 else "FAIL"
        pass_dd = "PASS" if avg_dd <= 25.0 else "FAIL"
        print("    Pass condition (Sharpe>=1.5): %s (%.3f)" % (pass_sharpe, best_sharpe))
        print("    Pass condition (MaxDD<=25%%):  %s (%.2f%%)" % (pass_dd, avg_dd))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    run(csv_path)
