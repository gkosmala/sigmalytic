#!/usr/bin/env python3
"""
Phase 13B: cause_score Calibration Study
Compares Sigmalytic cause_scores against algorithmic P&F horizontal counts
on completed campaigns to validate and calibrate the target projection formula.

Method:
1. Select 100 qualifying completed winner campaigns from dataset
2. Fetch full daily bar history from Alpaca for each
3. Build P&F chart algorithmically (box=0.5*ATR14, 3-box reversal)
4. Count horizontal columns across accumulation base
5. Compare P&F projected move vs cause_score projected move vs actual move
6. Derive calibration factor

Output:
- Calibration factor: cause_score -> P&F column equivalent
- Validated target formula
- Accuracy comparison: P&F vs cause_score vs actual
"""
import csv, math, sys, os, time, json
from collections import defaultdict

# ── Helpers ──────────────────────────────────────────────────────────────────

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

def _env(key, default=None):
    return os.environ.get(key, default)

# ── Alpaca bar fetcher ────────────────────────────────────────────────────────

def fetch_bars(symbol, start_date, end_date):
    """Fetch daily bars from Alpaca for a symbol between two dates."""
    try:
        import requests
    except ImportError:
        raise SystemExit("requests not installed")

    key    = _env("ALPACA_API_KEY") or _env("APCA_API_KEY_ID")
    secret = _env("ALPACA_API_SECRET") or _env("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("Missing Alpaca credentials")

    url = "https://data.alpaca.markets/v2/stocks/{}/bars".format(symbol)
    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
    bars = []
    page_token = None

    while True:
        params = {
            "timeframe": "1Day",
            "start": start_date,
            "end": end_date,
            "limit": 1000,
            "feed": _env("ALPACA_FEED", "iex"),
            "adjustment": "split",
        }
        if page_token:
            params["page_token"] = page_token

        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(2)
            continue
        if r.status_code != 200:
            return []

        data = r.json()
        for b in data.get("bars", []):
            bars.append({
                "date": b["t"][:10],
                "o": float(b["o"]),
                "h": float(b["h"]),
                "l": float(b["l"]),
                "c": float(b["c"]),
                "v": int(b.get("v", 0)),
            })

        page_token = data.get("next_page_token")
        if not page_token:
            break

    return sorted(bars, key=lambda x: x["date"])

# ── P&F Chart Builder ─────────────────────────────────────────────────────────

def build_pnf_chart(bars, box_size, reversal=3):
    """
    Build a Point and Figure chart from daily bars.
    Returns list of columns: each column is {'direction': 'X'|'O', 'start': price, 'end': price, 'count': int}
    """
    if not bars or box_size <= 0:
        return []

    def round_to_box(price):
        return math.floor(price / box_size) * box_size

    columns = []
    current_col = None
    current_dir = None
    current_price = round_to_box(bars[0]["c"])

    for bar in bars[1:]:
        high = bar["h"]
        low  = bar["l"]

        if current_dir is None:
            # Initialize
            if high >= current_price + box_size:
                current_dir = "X"
                new_price = round_to_box(high)
                count = round((new_price - current_price) / box_size)
                if count > 0:
                    current_col = {"direction": "X", "start": current_price,
                                   "end": new_price, "count": count}
                    current_price = new_price
            elif low <= current_price - box_size:
                current_dir = "O"
                new_price = round_to_box(low)
                count = round((current_price - new_price) / box_size)
                if count > 0:
                    current_col = {"direction": "O", "start": current_price,
                                   "end": new_price, "count": count}
                    current_price = new_price
        elif current_dir == "X":
            # In X column — check continuation or reversal
            if high >= current_price + box_size:
                new_price = round_to_box(high)
                count = round((new_price - current_price) / box_size)
                current_col["end"] = new_price
                current_col["count"] += count
                current_price = new_price
            elif low <= current_price - box_size * reversal:
                # Reversal — save current column, start O column
                if current_col:
                    columns.append(current_col)
                new_price = round_to_box(low)
                count = round((current_price - new_price) / box_size)
                current_col = {"direction": "O", "start": current_price,
                               "end": new_price, "count": max(count, reversal)}
                current_dir = "O"
                current_price = new_price
        elif current_dir == "O":
            # In O column — check continuation or reversal
            if low <= current_price - box_size:
                new_price = round_to_box(low)
                count = round((current_price - new_price) / box_size)
                current_col["end"] = new_price
                current_col["count"] += count
                current_price = new_price
            elif high >= current_price + box_size * reversal:
                # Reversal — save current column, start X column
                if current_col:
                    columns.append(current_col)
                new_price = round_to_box(high)
                count = round((new_price - current_price) / box_size)
                current_col = {"direction": "X", "start": current_price,
                               "end": new_price, "count": max(count, reversal)}
                current_dir = "X"
                current_price = new_price

    if current_col:
        columns.append(current_col)

    return columns

def count_horizontal_columns(columns, base_start_idx, base_end_idx):
    """
    Count horizontal columns across the accumulation base.
    base_start_idx and base_end_idx are indices into the columns list.
    """
    base_cols = columns[base_start_idx:base_end_idx+1]
    return len(base_cols)

def find_accumulation_base(columns, bars, signal_date):
    """
    Identify the accumulation base in the P&F chart.
    The base is the sideways consolidation preceding the signal date.
    Returns (start_idx, end_idx) of columns within the base.
    """
    if not columns:
        return 0, 0

    # Find price range during accumulation (approx 120 bars before signal)
    base_bars = bars[-120:] if len(bars) >= 120 else bars
    if not base_bars:
        return 0, max(0, len(columns)-2)

    base_high = max(b["h"] for b in base_bars)
    base_low  = min(b["l"] for b in base_bars)
    base_range = base_high - base_low

    if base_range <= 0:
        return 0, max(0, len(columns)-2)

    # Find columns that fall within the base price range (within 20% tolerance)
    tolerance = base_range * 0.20
    range_lo = base_low - tolerance
    range_hi = base_high + tolerance

    in_base = []
    for i, col in enumerate(columns):
        col_lo = min(col["start"], col["end"])
        col_hi = max(col["start"], col["end"])
        if col_lo >= range_lo and col_hi <= range_hi:
            in_base.append(i)

    if not in_base:
        return 0, max(0, len(columns)-2)

    return in_base[0], in_base[-1]

# ── Main Analysis ─────────────────────────────────────────────────────────────

def run(csv_path, max_campaigns=80):
    rows = []
    with open(csv_path, newline="", errors="ignore") as f:
        for row in csv.DictReader(f): rows.append(row)
    print("Loaded {:,} rows from {}".format(len(rows), csv_path))

    # ── Select qualifying completed winner campaigns ───────────────────────
    # Requirements:
    # - Has cause_score > 0
    # - Has entry_close and atr_14 (new fields) OR we can estimate
    # - Has markup_90d_pct (confirmed completed)
    # - h90_direction_correct = 1 (winner)
    # - Has signal_date and symbol

    candidates = []
    for r in rows:
        cs = _f(r.get("cause_score"))
        if not cs or cs <= 0: continue
        ec = _f(r.get("entry_close"))
        if not ec or ec <= 0: continue
        mfe90 = _f(r.get("markup_90d_pct"))
        if mfe90 is None: continue
        h90d = _f(r.get("h90_direction_correct"))
        if not h90d or h90d < 0.5: continue
        atr14 = _f(r.get("atr_14"))
        high252 = _f(r.get("high_252"))
        date = r.get("signal_date", "")
        sym = r.get("symbol", "")
        if not date or not sym: continue

        candidates.append({
            "symbol": sym,
            "signal_date": date,
            "cause_score": cs,
            "entry_close": ec,
            "atr_14": atr14,
            "high_252": high252,
            "mfe90": mfe90,
            "mfe40": _f(r.get("markup_40d_pct")) or 0.0,
        })

    # Sort by cause_score descending — test highest-cause signals first
    # Also diversify by symbol — max 3 per symbol
    sym_count = defaultdict(int)
    selected = []
    for c in sorted(candidates, key=lambda x: -x["cause_score"]):
        if sym_count[c["symbol"]] >= 3: continue
        sym_count[c["symbol"]] += 1
        selected.append(c)
        if len(selected) >= max_campaigns: break

    print("Selected {:,} campaigns for calibration".format(len(selected)))
    print("Unique symbols: {:,}".format(len(sym_count)))

    SEP = "=" * 100

    # ── Run calibration for each campaign ─────────────────────────────────
    results = []
    skipped = 0

    for i, camp in enumerate(selected):
        sym = camp["symbol"]
        sig_date = camp["signal_date"]
        cs = camp["cause_score"]
        ec = camp["entry_close"]
        atr14 = camp["atr_14"]
        mfe90 = camp["mfe90"]

        # Estimate ATR if not in dataset (older signals before field was added)
        if not atr14 or atr14 <= 0:
            atr14 = ec * 0.02  # fallback: 2% of price

        box_size_conservative = 0.5 * atr14
        box_size_aggressive   = 1.0 * atr14

        if box_size_conservative <= 0:
            skipped += 1
            continue

        # Fetch bars: go back 200 days from signal date for full base
        try:
            from datetime import datetime, timedelta
            sig_dt = datetime.strptime(sig_date[:10], "%Y-%m-%d")
            start_dt = sig_dt - timedelta(days=300)
            start_str = start_dt.strftime("%Y-%m-%d")
            end_str = sig_date[:10]

            bars = fetch_bars(sym, start_str, end_str)
            time.sleep(0.15)  # rate limit courtesy
        except Exception as e:
            skipped += 1
            continue

        if len(bars) < 60:
            skipped += 1
            continue

        # Build P&F chart
        pnf_cols = build_pnf_chart(bars, box_size_conservative, reversal=3)
        if not pnf_cols:
            skipped += 1
            continue

        # Find accumulation base and count columns
        base_start, base_end = find_accumulation_base(pnf_cols, bars, sig_date)
        pnf_horizontal_count = count_horizontal_columns(pnf_cols, base_start, base_end)

        if pnf_horizontal_count < 2:
            skipped += 1
            continue

        # P&F projected move
        pnf_projected_pct_cons = (pnf_horizontal_count * box_size_conservative * 3) / ec * 100
        pnf_projected_pct_agg  = (pnf_horizontal_count * box_size_aggressive * 3) / ec * 100

        # Cause_score projected move (pre-calibration)
        cs_projected_pct_cons = (cs * box_size_conservative * 3) / ec * 100
        cs_projected_pct_agg  = (cs * box_size_aggressive * 3) / ec * 100

        # Calibration factor: how many P&F columns does cause_score represent?
        calib_factor = pnf_horizontal_count / cs if cs > 0 else None

        # Accuracy: how close did each method get to actual mfe90?
        pnf_error_cons = abs(pnf_projected_pct_cons - mfe90)
        cs_error_cons  = abs(cs_projected_pct_cons - mfe90)

        results.append({
            "symbol": sym,
            "signal_date": sig_date,
            "cause_score": cs,
            "entry_close": ec,
            "atr_14": atr14,
            "mfe90": mfe90,
            "pnf_col_count": pnf_horizontal_count,
            "pnf_projected_cons": round(pnf_projected_pct_cons, 2),
            "pnf_projected_agg": round(pnf_projected_pct_agg, 2),
            "cs_projected_cons": round(cs_projected_pct_cons, 2),
            "cs_projected_agg": round(cs_projected_pct_agg, 2),
            "calib_factor": round(calib_factor, 4) if calib_factor else None,
            "pnf_error_cons": round(pnf_error_cons, 2),
            "cs_error_cons": round(cs_error_cons, 2),
            "box_size_cons": round(box_size_conservative, 4),
            "total_pnf_cols": len(pnf_cols),
        })

        if (i+1) % 10 == 0:
            print("  Processed {}/{} campaigns ({} skipped)...".format(
                i+1, len(selected), skipped))

    print("\nCompleted: {:,} campaigns analyzed, {:,} skipped".format(
        len(results), skipped))

    if not results:
        print("No results — check Alpaca credentials and data availability")
        return

    # ── Analysis ──────────────────────────────────────────────────────────
    print("\n" + SEP)
    print("PHASE 13B: CAUSE_SCORE CALIBRATION RESULTS")
    print(SEP)

    # Study 1: P&F column count distribution
    print("\nSTUDY 1: P&F HORIZONTAL COLUMN COUNT DISTRIBUTION")
    col_counts = [r["pnf_col_count"] for r in results]
    cs_vals    = [r["cause_score"] for r in results]
    calib_vals = [r["calib_factor"] for r in results if r["calib_factor"]]

    print("  P&F column count — median: {:.1f}  mean: {:.1f}  min: {}  max: {}".format(
        _percentile(sorted(col_counts), 50),
        sum(col_counts)/len(col_counts),
        min(col_counts), max(col_counts)))
    print("  cause_score      — median: {:.1f}  mean: {:.1f}  min: {:.0f}  max: {:.0f}".format(
        _percentile(sorted(cs_vals), 50),
        sum(cs_vals)/len(cs_vals),
        min(cs_vals), max(cs_vals)))

    # Study 2: Calibration factor
    print("\nSTUDY 2: CALIBRATION FACTOR (P&F columns per cause_score unit)")
    if calib_vals:
        med_calib = _percentile(sorted(calib_vals), 50)
        mean_calib = sum(calib_vals)/len(calib_vals)
        p25_calib = _percentile(sorted(calib_vals), 25)
        p75_calib = _percentile(sorted(calib_vals), 75)
        print("  Median calibration factor:  {:.4f}".format(med_calib))
        print("  Mean calibration factor:    {:.4f}".format(mean_calib))
        print("  25th-75th pct:             {:.4f} to {:.4f}".format(p25_calib, p75_calib))
        print("\n  INTERPRETATION:")
        print("  cause_score × {:.4f} = estimated P&F horizontal column count".format(med_calib))
        print("  Adjusted target formula:")
        print("    move = cause_score × {:.4f} × box_size × 3".format(med_calib))
        print("    conservative target = entry_price + move × 0.6")
        print("    aggressive target   = entry_price + move")

    # Study 3: Projection accuracy comparison
    print("\nSTUDY 3: PROJECTION ACCURACY vs ACTUAL mfe90")
    print("  (Lower error = better projection)")
    pnf_errors = [r["pnf_error_cons"] for r in results]
    cs_errors  = [r["cs_error_cons"] for r in results]
    print("  %-30s  %10s  %10s  %10s" % ("Method", "Med Error", "Mean Error", "75th pct"))
    print("  " + "-" * 65)
    print("  %-30s  %9.1f%%  %9.1f%%  %9.1f%%" % (
        "P&F count (conservative)",
        _percentile(sorted(pnf_errors), 50),
        sum(pnf_errors)/len(pnf_errors),
        _percentile(sorted(pnf_errors), 75)))
    print("  %-30s  %9.1f%%  %9.1f%%  %9.1f%%" % (
        "cause_score (pre-calibration)",
        _percentile(sorted(cs_errors), 50),
        sum(cs_errors)/len(cs_errors),
        _percentile(sorted(cs_errors), 75)))

    # Study 4: Calibration by cause_score tier
    print("\nSTUDY 4: CALIBRATION FACTOR BY CAUSE_SCORE TIER")
    tiers = [
        ("CS_HIGH (>= 75)", [r for r in results if r["cause_score"] >= 75]),
        ("CS_MED  (50-74)", [r for r in results if 50 <= r["cause_score"] < 75]),
        ("CS_LOW  (25-49)", [r for r in results if 25 <= r["cause_score"] < 50]),
        ("CS_MIN  (< 25)",  [r for r in results if r["cause_score"] < 25]),
    ]
    print("  %-20s  %6s  %12s  %12s  %12s" % (
        "Tier", "n", "Med P&F Cols", "Med CS", "Med Calib"))
    print("  " + "-" * 67)
    for tier_name, tier_data in tiers:
        if not tier_data: continue
        tier_cols = [r["pnf_col_count"] for r in tier_data]
        tier_cs   = [r["cause_score"] for r in tier_data]
        tier_cf   = [r["calib_factor"] for r in tier_data if r["calib_factor"]]
        print("  %-20s  %6d  %12.1f  %12.1f  %12.4f" % (
            tier_name, len(tier_data),
            _percentile(sorted(tier_cols), 50),
            _percentile(sorted(tier_cs), 50),
            _percentile(sorted(tier_cf), 50) if tier_cf else 0))

    # Study 5: Top 20 individual campaign results
    print("\nSTUDY 5: SAMPLE CAMPAIGN RESULTS (top 20 by cause_score)")
    fmt = "  {:<8} {:<12} {:>6} {:>8} {:>10} {:>10} {:>10} {:>8} {:>8}"
    print(fmt.format("Symbol","Date","CS","ATR14","P&F Proj%","CS Proj%","Actual%","P&F Err","CS Err"))
    print("  " + "-" * 95)
    for r in sorted(results, key=lambda x: -x["cause_score"])[:20]:
        print(fmt.format(
            r["symbol"], r["signal_date"],
            int(r["cause_score"]),
            round(r["atr_14"], 2),
            "{}%".format(r["pnf_projected_cons"]),
            "{}%".format(r["cs_projected_cons"]),
            "{}%".format(round(r["mfe90"], 1)),
            "{}%".format(r["pnf_error_cons"]),
            "{}%".format(r["cs_error_cons"])))

    # Study 6: Calibrated target formula validation
    print("\nSTUDY 6: CALIBRATED FORMULA VALIDATION")
    if calib_vals:
        med_calib = _percentile(sorted(calib_vals), 50)
        calibrated_errors = []
        for r in results:
            cal_move_pct = (r["cause_score"] * med_calib * r["box_size_cons"] * 3) / r["entry_close"] * 100
            cal_cons_pct = cal_move_pct * 0.6
            cal_agg_pct  = cal_move_pct
            # How often does actual mfe90 fall between conservative and aggressive?
            within_range = r["mfe90"] >= cal_cons_pct * 0.5 and r["mfe90"] <= cal_agg_pct * 2.0
            calibrated_errors.append({
                "cal_cons": cal_cons_pct,
                "cal_agg": cal_agg_pct,
                "actual": r["mfe90"],
                "within": within_range,
                "error": abs(cal_cons_pct - r["mfe90"]),
            })

        within_count = sum(1 for e in calibrated_errors if e["within"])
        cal_errs = [e["error"] for e in calibrated_errors]
        print("  Calibrated formula (using median calibration factor {:.4f}):".format(med_calib))
        print("  Signals where actual fell within target range: {}/{} ({:.1f}%)".format(
            within_count, len(calibrated_errors),
            within_count/len(calibrated_errors)*100))
        print("  Calibrated median error: {:.1f}%".format(_percentile(sorted(cal_errs), 50)))
        print("  Calibrated mean error:   {:.1f}%".format(sum(cal_errs)/len(cal_errs)))

    # Final summary
    print("\n" + SEP)
    print("PHASE 13B CALIBRATION SUMMARY")
    print(SEP)
    if calib_vals:
        med_calib = _percentile(sorted(calib_vals), 50)
        print("\n  Campaigns analyzed:      {:,}".format(len(results)))
        print("  Calibration factor:      {:.4f}  (cause_score units per P&F column)".format(1/med_calib if med_calib > 0 else 0))
        print("  Inverse (cols per CS):   {:.4f}".format(med_calib))
        print("\n  VALIDATED TARGET FORMULA:")
        print("  ─────────────────────────────────────────────────────────")
        print("  box_size        = 0.5 × ATR_14")
        print("  reversal        = 3")
        print("  calib_factor    = {:.4f}  (from this study)".format(med_calib))
        print("  projected_move  = cause_score × calib_factor × box_size × reversal")
        print("  cons_target     = entry_close + projected_move × 0.6")
        print("  agg_target      = entry_close + projected_move")
        print("  ─────────────────────────────────────────────────────────")
        print("\n  Example (AAPL: CS=45, ATR=3.97, entry=$207.82):")
        ex_cs = 45; ex_atr = 3.97; ex_entry = 207.82
        ex_box = 0.5 * ex_atr
        ex_move = ex_cs * med_calib * ex_box * 3
        ex_cons = ex_entry + ex_move * 0.6
        ex_agg  = ex_entry + ex_move
        print("    box_size       = ${:.2f}".format(ex_box))
        print("    projected_move = ${:.2f}  ({:.1f}%)".format(ex_move, ex_move/ex_entry*100))
        print("    cons_target    = ${:.2f}  (+{:.1f}%)".format(ex_cons, (ex_cons-ex_entry)/ex_entry*100))
        print("    agg_target     = ${:.2f}  (+{:.1f}%)".format(ex_agg, (ex_agg-ex_entry)/ex_entry*100))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
               "backend/audit_outputs/qualified_long_signal_rows.csv"
    max_campaigns = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    run(csv_path, max_campaigns)
