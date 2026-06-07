#!/usr/bin/env python3
"""
Sigmalytic Full Russell 1000 Audit — Protected Run
===================================================
Protections built in:
  1. Progress checkpointing every 25 symbols — partial CSV written to disk
  2. Heartbeat timestamps every 25 symbols — visible in Render logs
  3. Completion email with summary stats + CSV + JSON attached to Gmail
  4. Run validation — checks file integrity before sending email
  5. Error email — if run fails, sends error details so you know immediately
  6. Pre-run environment check — validates all credentials before wasting compute

Run from Render Shell:
  python run_full_russell1000.py

Required environment variables:
  ALPACA_API_KEY
  ALPACA_API_SECRET
  GMAIL_USER       (your Gmail address)
  GMAIL_APP_PASSWORD (16-char app password from myaccount.google.com/apppasswords)

Optional:
  ALPACA_FEED=sip (default) or iex
  NOTIFY_EMAIL    (send results to a different address; defaults to GMAIL_USER)
"""

from __future__ import annotations

import csv
import json
import math
import os
import smtplib
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests
except Exception as exc:
    raise SystemExit("pip install requests") from exc


# ─── Configuration ────────────────────────────────────────────────────────────
ALPACA_BASE_URL   = "https://data.alpaca.markets"
SYMBOLS_FILE      = Path("backend/data/russell1000.csv")
OUTPUT_DIR        = Path("backend/audit_outputs")
CHECKPOINT_FILE   = OUTPUT_DIR / "checkpoint_rows.csv"
YEARS             = 2.0
CHECKPOINT_EVERY  = 25      # write partial CSV every N symbols
HORIZONS          = [1, 2, 3, 5, 10, 20, 40, 60, 90]
BENCHMARK         = "SPY"
RS_2H_MIN         = 50.0
RS_DAILY_MIN      = 20.0
RS_2H_LOOKBACK    = 80
RS_DAILY_LOOKBACK = 63
DAILY_SLOPE_BARS  = 5
SYMBOL_PAUSE      = 0.03


# ─── Email ────────────────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _send_email(
    subject: str,
    body: str,
    attachments: List[Path] = None,
) -> bool:
    gmail_user = _env("GMAIL_USER")
    gmail_pass = _env("GMAIL_APP_PASSWORD")
    to_addr    = _env("NOTIFY_EMAIL") or gmail_user

    if not gmail_user or not gmail_pass:
        print("WARN: GMAIL_USER or GMAIL_APP_PASSWORD not set — skipping email")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"]    = gmail_user
        msg["To"]      = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        for path in (attachments or []):
            if not path.exists():
                continue
            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > 20:
                msg.attach(MIMEText(f"\n[{path.name} too large to attach ({size_mb:.1f} MB) — retrieve from server]", "plain"))
                continue
            with open(path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={path.name}")
            msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_addr, msg.as_string())

        print(f"Email sent to {to_addr}: {subject}")
        return True

    except Exception as e:
        print(f"WARN: Email failed: {e}")
        return False


def _send_error_email(error_msg: str, symbols_done: int, signals: int) -> None:
    subject = f"[SIGMALYTIC] Run FAILED after {symbols_done} symbols"
    body = f"""The Sigmalytic full Russell 1000 audit run encountered an error.

Symbols processed before failure: {symbols_done}
Signals collected before failure: {signals}
Time of failure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Error details:
{error_msg}

The partial checkpoint file may still contain usable data at:
  backend/audit_outputs/checkpoint_rows.csv

Check Render logs for full traceback.
"""
    _send_email(subject, body)


def _send_success_email(
    signals: int,
    processed: int,
    skipped: int,
    duration_min: float,
    target_n: int,
    state1_q4_n: int,
    state1_q4_mfe90: float,
    output_files: List[Path],
) -> None:
    subject = f"[SIGMALYTIC] Run COMPLETE — {signals:,} signals | target n={target_n}"
    body = f"""The Sigmalytic full Russell 1000 audit completed successfully.

Run Summary
-----------
Symbols processed:  {processed}
Symbols skipped:    {skipped}
Total signals:      {signals:,}
Run duration:       {duration_min:.1f} minutes
Completed at:       {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Key Result: Phase 7A/7C Winning Combination
--------------------------------------------
Target bucket (Late + 20%+ Off High + RelVol 2-3x): n = {target_n}
OBS_Q4 + PROG_Q4 + SPD=Y|DEI=N:                     n = {state1_q4_n}
OBS_Q4 + PROG_Q4 + SPD=Y|DEI=N mfe90:               {state1_q4_mfe90:.2f}%

Output files are attached or available on the server at:
  backend/audit_outputs/

Files produced:
{chr(10).join(f'  {p.name} ({p.stat().st_size/1024:.0f} KB)' for p in output_files if p.exists())}

Next step: run the standalone analysis scripts (run_phase7a.py, run_phase7b.py,
run_phase7c.py) against the new qualified_long_signal_rows.csv to validate
that the winning combination holds on the full universe.
"""
    _send_email(subject, body, attachments=output_files)


# ─── Pre-run validation ───────────────────────────────────────────────────────
def validate_environment() -> bool:
    """
    Check all required credentials and files before starting the run.
    Better to fail fast in 5 seconds than after 3 hours.
    """
    print("=" * 70)
    print("PRE-RUN VALIDATION")
    print("=" * 70)
    ok = True

    # Alpaca credentials
    key    = _env("ALPACA_API_KEY") or _env("APCA_API_KEY_ID")
    secret = _env("ALPACA_API_SECRET") or _env("APCA_API_SECRET_KEY")
    if not key or not secret:
        print("FAIL: ALPACA_API_KEY and ALPACA_API_SECRET not set")
        ok = False
    else:
        print(f"OK:   Alpaca credentials present (key={key[:8]}...)")

    # Test Alpaca connectivity
    try:
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        r = requests.get(
            f"{ALPACA_BASE_URL}/v2/stocks/SPY/bars",
            headers=headers,
            params={"timeframe": "1Day", "start": "2026-01-01", "end": "2026-01-02",
                    "feed": "sip", "limit": 1},
            timeout=10
        )
        if r.status_code == 200:
            print("OK:   Alpaca API connectivity confirmed")
        else:
            print(f"FAIL: Alpaca API returned {r.status_code}: {r.text[:100]}")
            ok = False
    except Exception as e:
        print(f"FAIL: Alpaca API connection error: {e}")
        ok = False

    # Gmail credentials
    gmail_user = _env("GMAIL_USER")
    gmail_pass = _env("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_pass:
        print("WARN: GMAIL_USER or GMAIL_APP_PASSWORD not set — no email notifications")
    else:
        # Test email connectivity
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
                server.login(gmail_user, gmail_pass)
            print(f"OK:   Gmail credentials valid ({gmail_user})")
            # Send test email
            _send_email(
                "[SIGMALYTIC] Run Starting",
                f"The full Russell 1000 audit run has started.\n\n"
                f"Estimated completion: 3-4 hours from now.\n"
                f"You will receive a completion email with results attached.\n\n"
                f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            print(f"WARN: Gmail login failed: {e}")
            print("      Email notifications will not work.")
            print("      Check GMAIL_USER and GMAIL_APP_PASSWORD in Render environment.")

    # Symbols file
    if not SYMBOLS_FILE.exists():
        print(f"FAIL: Symbols file not found: {SYMBOLS_FILE}")
        ok = False
    else:
        with open(SYMBOLS_FILE) as f:
            symbol_count = sum(1 for _ in f) - 1  # minus header
        print(f"OK:   Symbols file found: {symbol_count} symbols")

    # Output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"OK:   Output directory ready: {OUTPUT_DIR}")

    print("=" * 70)
    if ok:
        print("VALIDATION PASSED — starting run in 5 seconds")
        print("=" * 70)
        time.sleep(5)
    else:
        print("VALIDATION FAILED — fix the issues above before running")
        print("=" * 70)

    return ok


# ─── Import core audit functions from existing file ───────────────────────────
# Rather than duplicating all the audit code, we import from the existing file.
# This ensures consistency with the validated codebase.

sys.path.insert(0, str(Path("backend").absolute()))

try:
    # Import everything we need from the existing audit script
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit", "backend/qualified_long_signal_audit.py"
    )
    audit_mod = importlib.util.load_from_spec(spec)
    spec.loader.exec_module(audit_mod)

    fetch_bars           = audit_mod.fetch_bars
    load_symbols_from_file = audit_mod.load_symbols_from_file
    bars_by_date         = audit_mod.bars_by_date
    last_2h_rs_by_date   = audit_mod.last_2h_rs_by_date
    percentile_score     = audit_mod.percentile_score
    sma                  = audit_mod.sma
    calc_rel_volume      = audit_mod.calc_rel_volume
    forward_metrics      = audit_mod.forward_metrics
    classify_setup       = audit_mod.classify_setup
    classify_expansion_subtype = audit_mod.classify_expansion_subtype
    classify_volatility_dna_score = audit_mod.classify_volatility_dna_score
    grade_from_signal    = audit_mod.grade_from_signal
    grade_at_least       = audit_mod.grade_at_least
    setup_is_long        = audit_mod.setup_is_long
    _atr_pct             = audit_mod._atr_pct
    _effort_bucket       = audit_mod._effort_bucket
    _result_bucket       = audit_mod._result_bucket
    _er_interpretation   = audit_mod._er_interpretation
    _absorption_persistence_tier = audit_mod._absorption_persistence_tier
    _count_absorption_candidates_in_window = audit_mod._count_absorption_candidates_in_window
    _compute_wave_variables = audit_mod._compute_wave_variables
    _identify_swing_points  = audit_mod._identify_swing_points
    _build_waves_from_swings = audit_mod._build_waves_from_swings
    calc_atr             = audit_mod.calc_atr
    Bar                  = audit_mod.Bar
    _env_audit           = audit_mod._env
    _headers             = audit_mod._headers

    print("OK: Imported audit functions from backend/qualified_long_signal_audit.py")

except Exception as e:
    print(f"FAIL: Could not import audit module: {e}")
    traceback.print_exc()
    sys.exit(1)


# ─── Obstacle and Progress scores for real-time validation email ──────────────
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


def _compute_winning_combo_stats(signal_rows: List[Dict]) -> Tuple[int, int, float]:
    """Quick real-time stats for the email: target_n, state1_q4_n, state1_q4_mfe90."""
    obs_scores = [_obstacle(r) for r in signal_rows if _safe_float(r.get("markup_90d_pct")) is not None]
    if not obs_scores:
        return 0, 0, 0.0

    s = sorted(obs_scores)
    n = len(s)
    q3 = s[3 * n // 4]

    prog_scores = [_progress(r) for r in signal_rows if _safe_float(r.get("markup_90d_pct")) is not None]
    ps = sorted(prog_scores)
    pq3 = ps[3 * len(ps) // 4]

    target_n = sum(1 for r in signal_rows if _is_target(r))

    state1_q4 = []
    for r in signal_rows:
        mfe90 = _safe_float(r.get("markup_90d_pct"))
        if mfe90 is None:
            continue
        spd = _safe_bool(r.get("w_selling_pressure_diminishing"))
        dei = _safe_bool(r.get("w_demand_efficiency_improving"))
        obs = _obstacle(r)
        prog = _progress(r)
        if spd and not dei and obs > q3 and prog > pq3:
            state1_q4.append(mfe90)

    mfe90_avg = round(sum(state1_q4) / len(state1_q4), 2) if state1_q4 else 0.0
    return target_n, len(state1_q4), mfe90_avg


# ─── Checkpoint writer ────────────────────────────────────────────────────────
FLAT_FIELDS = [
    "symbol", "signal_date", "entry_close", "setup_type", "setup_subtype",
    "grade", "audit_score", "rs_2h", "rs_daily", "daily_rs_slope_pct",
    "rel_volume", "rel_volume_bucket", "er_atr20_pct",
    "er1_return_pct", "er1_norm_result", "er1_effort_bucket",
    "er1_result_bucket", "er1_interpretation",
    "er5_return_pct", "er5_rel_effort", "er5_norm_result",
    "er5_effort_bucket", "er5_result_bucket", "er5_interpretation",
    "abs1_count_20", "abs1_count_40", "abs1_count_60",
    "abs1_tier_20", "abs1_tier_40", "abs1_tier_60",
    "abs5_count_20", "abs5_count_40", "abs5_count_60",
    "abs5_tier_20", "abs5_tier_40", "abs5_tier_60",
    "high_252", "distance_from_252_high_pct",
    "expansion_phase_bucket", "volatility_dna_score", "volatility_dna_tier",
    "trading_range_detected", "range_width_pct", "support_level",
    "resistance_level", "apex_detected", "spring_detected", "spring_quality",
    "upthrust_detected", "behavior_classification",
    "accumulation_score", "distribution_score",
    "p5_price_traj_10d_pct", "p5_price_traj_bucket",
    "p5_vol_trend_ratio", "p5_vol_trend_bucket",
    "p5_rs_traj_10d", "p5_rs_traj_bucket",
    "p5_days_since_252_high", "p5_days_since_high_bucket",
    "w_up1_return_pct", "w_up1_duration", "w_up1_vol_ratio",
    "w_up1_price_eff", "w_up1_vol_eff",
    "w_up2_return_pct", "w_up2_duration", "w_up2_vol_ratio",
    "w_up2_price_eff", "w_up2_vol_eff",
    "w_up3_return_pct", "w_up3_duration", "w_up3_vol_ratio",
    "w_up3_price_eff", "w_up3_vol_eff",
    "w_dn1_return_pct", "w_dn1_duration", "w_dn1_vol_ratio",
    "w_dn1_price_eff", "w_dn1_vol_eff",
    "w_dn2_return_pct", "w_dn2_duration", "w_dn2_vol_ratio",
    "w_dn2_price_eff", "w_dn2_vol_eff",
    "w_dn3_return_pct", "w_dn3_duration", "w_dn3_vol_ratio",
    "w_dn3_price_eff", "w_dn3_vol_eff",
    "w_thrust_shortening", "w_thrust_shortening_ratio",
    "w_selling_pressure_diminishing", "w_demand_efficiency_improving",
    "w_springboard_present", "w_buoyancy_near_support",
    "w_failure_to_follow_through", "w_wave_efficiency_score",
    "w_wave_efficiency_bucket",
    "markup_20d_pct", "markup_40d_pct", "markup_60d_pct", "markup_90d_pct",
    "ma20", "ma50",
]
for h in HORIZONS:
    FLAT_FIELDS += [
        f"h{h}_direction_correct", f"h{h}_return_pct",
        f"h{h}_mfe_pct", f"h{h}_mae_pct"
    ]


def _write_checkpoint(signal_rows: List[Dict], path: Path) -> None:
    """Write all signal rows to CSV checkpoint. Safe to call repeatedly."""
    try:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FLAT_FIELDS)
            writer.writeheader()
            for r in signal_rows:
                writer.writerow({k: r.get(k, "") for k in FLAT_FIELDS})
    except Exception as e:
        print(f"WARN: Checkpoint write failed: {e}")


# ─── Main run ─────────────────────────────────────────────────────────────────
def run() -> None:
    start_wall = time.time()

    if not validate_environment():
        sys.exit(1)

    feed = _env("ALPACA_FEED") or "sip"
    end_dt   = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=int(YEARS * 365) + 120)
    start    = start_dt.strftime("%Y-%m-%d")
    end      = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
    max_horizon = max(HORIZONS)

    symbols = load_symbols_from_file(SYMBOLS_FILE)
    symbols = [s for s in sorted(set(symbols)) if s]
    if BENCHMARK not in symbols:
        symbols_with_bench = [BENCHMARK] + symbols
    else:
        symbols_with_bench = symbols

    print(f"\nRun configuration:")
    print(f"  Symbols:   {len(symbols)}")
    print(f"  Benchmark: {BENCHMARK}")
    print(f"  Feed:      {feed}")
    print(f"  Period:    {start} to {end}")
    print(f"  Horizons:  {HORIZONS}")
    print(f"  Checkpoint every {CHECKPOINT_EVERY} symbols")
    print()

    # Fetch benchmark
    print(f"Fetching benchmark {BENCHMARK}...")
    bench_daily = fetch_bars(BENCHMARK, "1Day", start, end, feed)
    bench_2h    = fetch_bars(BENCHMARK, "2Hour", start, end, feed)
    if len(bench_daily) < 100 or len(bench_2h) < 100:
        msg = f"Benchmark history too thin: daily={len(bench_daily)} 2h={len(bench_2h)}"
        _send_error_email(msg, 0, 0)
        raise SystemExit(msg)
    bench_daily_by_date = bars_by_date(bench_daily)
    print(f"Benchmark fetched: {len(bench_daily)} daily bars, {len(bench_2h)} 2h bars")

    signal_rows: List[Dict] = []
    processed = 0
    skipped   = 0

    for idx_sym, symbol in enumerate(symbols, start=1):
        if symbol == BENCHMARK:
            continue

        ts_start = datetime.now().strftime("%H:%M:%S")
        try:
            daily = fetch_bars(symbol, "1Day", start, end, feed)
            twoh  = fetch_bars(symbol, "2Hour", start, end, feed)

            if len(daily) < max(80, max_horizon + 60) or len(twoh) < 80:
                skipped += 1
                continue

            ratios = []
            for b in daily:
                bb = bench_daily_by_date.get(b.date)
                ratios.append((b.c / bb.c) if bb and bb.c > 0 else None)

            ratio_values = [float(x) if x is not None else float("nan") for x in ratios]
            rs_2h_by_date = last_2h_rs_by_date(twoh, bench_2h, RS_2H_LOOKBACK)
            closes = [b.c for b in daily]

            for i in range(60, len(daily) - max_horizon):
                ratio = ratio_values[i]
                if not math.isfinite(ratio):
                    continue
                daily_rs = percentile_score(ratio_values, i, RS_DAILY_LOOKBACK)
                if daily_rs is None or daily_rs < RS_DAILY_MIN:
                    continue
                slope_idx = i - DAILY_SLOPE_BARS
                if slope_idx < 0 or not math.isfinite(ratio_values[slope_idx]) or ratio_values[slope_idx] <= 0:
                    continue
                daily_slope_pct = ((ratio - ratio_values[slope_idx]) / ratio_values[slope_idx]) * 100
                if daily_slope_pct <= 0:
                    continue
                rs_2h = rs_2h_by_date.get(daily[i].date)
                if rs_2h is None or rs_2h < RS_2H_MIN:
                    continue
                setup = classify_setup(daily, i)
                if not setup_is_long(setup):
                    continue

                ma20 = sma(closes, i, 20) or daily[i].c
                ma50 = sma(closes, i, 50) or ma20
                rel_vol = calc_rel_volume(daily, i, 20)
                high_252 = max(b.h for b in daily[max(0, i - 251): i + 1])
                setup_subtype = classify_expansion_subtype(
                    setup=setup, daily_slope_pct=daily_slope_pct,
                    rel_vol=rel_vol, price=daily[i].c, high_252=high_252
                )
                distance_from_252_high_pct = ((daily[i].c - high_252) / high_252 * 100) if high_252 > 0 else None

                if daily_slope_pct < 1.0:   expansion_phase_bucket = "EXP_PHASE_EARLY"
                elif daily_slope_pct < 3.0: expansion_phase_bucket = "EXP_PHASE_MID"
                else:                        expansion_phase_bucket = "EXP_PHASE_LATE"

                if rel_vol < 0.8:    rel_volume_bucket = "RELVOL_UNDER_0_8X"
                elif rel_vol < 1.0:  rel_volume_bucket = "RELVOL_0_8_1_0X"
                elif rel_vol < 1.5:  rel_volume_bucket = "RELVOL_1_0_1_5X"
                elif rel_vol < 2.0:  rel_volume_bucket = "RELVOL_1_5_2_0X"
                elif rel_vol < 3.0:  rel_volume_bucket = "RELVOL_2_0_3_0X"
                else:                rel_volume_bucket = "RELVOL_3X_PLUS"

                atr20_pct = _atr_pct(daily, i, 20) or 0.0
                prev_close = daily[i - 1].c if i > 0 else daily[i].o
                er1_return_pct = ((daily[i].c - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
                er1_norm_result = (er1_return_pct / atr20_pct) if atr20_pct > 0 else 0.0
                er1_effort_bucket = _effort_bucket(rel_vol)
                er1_result_bucket = _result_bucket(er1_norm_result)
                er1_interpretation = _er_interpretation(er1_effort_bucket, er1_result_bucket, distance_from_252_high_pct)

                if i >= 5:
                    five_start_close = daily[i - 5].c
                    er5_return_pct = ((daily[i].c - five_start_close) / five_start_close * 100.0) if five_start_close > 0 else 0.0
                    recent_vol = sum(b.v for b in daily[i - 4:i + 1])
                    prior_start = max(0, i - 24)
                    prior_vols = [b.v for b in daily[prior_start:i - 4]]
                    avg_prior_vol = (sum(prior_vols) / len(prior_vols)) if prior_vols else max(daily[i].v, 1.0)
                    er5_rel_effort = recent_vol / max(avg_prior_vol * 5.0, 1.0)
                    er5_norm_result = (er5_return_pct / (atr20_pct * math.sqrt(5))) if atr20_pct > 0 else 0.0
                else:
                    er5_return_pct = er1_return_pct
                    er5_rel_effort = rel_vol
                    er5_norm_result = er1_norm_result
                er5_effort_bucket = _effort_bucket(er5_rel_effort)
                er5_result_bucket = _result_bucket(er5_norm_result)
                er5_interpretation = _er_interpretation(er5_effort_bucket, er5_result_bucket, distance_from_252_high_pct)

                abs1_count_20 = _count_absorption_candidates_in_window(daily, i, 20, "single")
                abs1_count_40 = _count_absorption_candidates_in_window(daily, i, 40, "single")
                abs1_count_60 = _count_absorption_candidates_in_window(daily, i, 60, "single")
                abs5_count_20 = _count_absorption_candidates_in_window(daily, i, 20, "five")
                abs5_count_40 = _count_absorption_candidates_in_window(daily, i, 40, "five")
                abs5_count_60 = _count_absorption_candidates_in_window(daily, i, 60, "five")

                volatility_dna_score, volatility_dna_tier = classify_volatility_dna_score(
                    setup=setup, setup_subtype=setup_subtype, rs_daily=daily_rs,
                    rs_2h=rs_2h, rel_vol=rel_vol,
                    distance_from_252_high_pct=distance_from_252_high_pct,
                    expansion_phase_bucket=expansion_phase_bucket
                )
                grade, audit_score = grade_from_signal(
                    rs_2h=rs_2h, rs_daily=daily_rs, daily_slope_pct=daily_slope_pct,
                    setup=setup, rel_vol=rel_vol, price=daily[i].c, ma20=ma20, ma50=ma50
                )
                if not grade_at_least(grade, "C"):
                    continue

                # Phase 4 juncture fields (safe defaults if not present in module)
                trading_range_detected = getattr(audit_mod, '_detect_trading_range', lambda *a: (False, 0, 0, 0))(daily, i)[0] if hasattr(audit_mod, '_detect_trading_range') else False

                # Wave variables
                _ww_avg_vol = sma([b.v for b in daily], i, 20) or 1.0
                _ww_atr = calc_atr(daily, i, 14) or max(daily[i].h - daily[i].l, daily[i].c * 0.01)
                _ww = _compute_wave_variables(
                    bars=daily, idx=i, support_level=0.0,
                    avg_vol_20=_ww_avg_vol, atr=_ww_atr, lookback=60
                )

                # Price trajectory (Phase 5)
                if i >= 10:
                    pt10 = ((daily[i].c - daily[i-10].c) / daily[i-10].c * 100) if daily[i-10].c > 0 else 0.0
                else:
                    pt10 = 0.0

                # RS trajectory
                rs_slope_10 = 0.0
                if i >= 10 and math.isfinite(ratio_values[i-10]) and ratio_values[i-10] > 0:
                    rs_slope_10 = ((ratio_values[i] - ratio_values[i-10]) / ratio_values[i-10]) * 100

                # Days since 252-day high
                high_252_idx = max(0, i - 251)
                high_252_val = max(b.h for b in daily[high_252_idx: i + 1])
                days_since_high = 0
                for back in range(i, high_252_idx - 1, -1):
                    if daily[back].h >= high_252_val * 0.999:
                        days_since_high = i - back
                        break

                row: Dict[str, Any] = {
                    "symbol": symbol,
                    "signal_date": daily[i].date,
                    "entry_close": round(daily[i].c, 4),
                    "setup_type": setup,
                    "setup_subtype": setup_subtype,
                    "grade": grade,
                    "audit_score": audit_score,
                    "rs_2h": round(rs_2h, 2),
                    "rs_daily": round(daily_rs, 2),
                    "daily_rs_slope_pct": round(daily_slope_pct, 3),
                    "rel_volume": round(rel_vol, 3),
                    "rel_volume_bucket": rel_volume_bucket,
                    "er_atr20_pct": round(atr20_pct, 3),
                    "er1_return_pct": round(er1_return_pct, 3),
                    "er1_norm_result": round(er1_norm_result, 3),
                    "er1_effort_bucket": er1_effort_bucket,
                    "er1_result_bucket": er1_result_bucket,
                    "er1_interpretation": er1_interpretation,
                    "er5_return_pct": round(er5_return_pct, 3),
                    "er5_rel_effort": round(er5_rel_effort, 3),
                    "er5_norm_result": round(er5_norm_result, 3),
                    "er5_effort_bucket": er5_effort_bucket,
                    "er5_result_bucket": er5_result_bucket,
                    "er5_interpretation": er5_interpretation,
                    "abs1_count_20": abs1_count_20,
                    "abs1_count_40": abs1_count_40,
                    "abs1_count_60": abs1_count_60,
                    "abs1_tier_20": _absorption_persistence_tier(abs1_count_20),
                    "abs1_tier_40": _absorption_persistence_tier(abs1_count_40),
                    "abs1_tier_60": _absorption_persistence_tier(abs1_count_60),
                    "abs5_count_20": abs5_count_20,
                    "abs5_count_40": abs5_count_40,
                    "abs5_count_60": abs5_count_60,
                    "abs5_tier_20": _absorption_persistence_tier(abs5_count_20),
                    "abs5_tier_40": _absorption_persistence_tier(abs5_count_40),
                    "abs5_tier_60": _absorption_persistence_tier(abs5_count_60),
                    "high_252": round(high_252, 4),
                    "distance_from_252_high_pct": round(distance_from_252_high_pct, 3) if distance_from_252_high_pct is not None else "",
                    "expansion_phase_bucket": expansion_phase_bucket,
                    "volatility_dna_score": volatility_dna_score,
                    "volatility_dna_tier": volatility_dna_tier,
                    "trading_range_detected": False,
                    "range_width_pct": 0.0,
                    "support_level": 0.0,
                    "resistance_level": 0.0,
                    "apex_detected": False,
                    "spring_detected": False,
                    "spring_quality": 0,
                    "upthrust_detected": False,
                    "behavior_classification": "NEUTRAL",
                    "accumulation_score": 0,
                    "distribution_score": 0,
                    "p5_price_traj_10d_pct": round(pt10, 3),
                    "p5_price_traj_bucket": "TRAJ_RISING_STRONG_3PCT_PLUS" if pt10 >= 3 else "TRAJ_FLAT_NEG1_TO_POS1PCT",
                    "p5_vol_trend_ratio": 1.0,
                    "p5_vol_trend_bucket": "VOL_TREND_FLAT_0_9_1_1X",
                    "p5_rs_traj_10d": round(rs_slope_10, 3),
                    "p5_rs_traj_bucket": "RS_TRAJ_RISING_STRONG_10PT_PLUS" if rs_slope_10 >= 10 else "RS_TRAJ_FLAT_NEG3_TO_POS3PT",
                    "p5_days_since_252_high": days_since_high,
                    "p5_days_since_high_bucket": "DAYS_SINCE_HIGH_180_PLUS" if days_since_high >= 180 else "DAYS_SINCE_HIGH_UNDER_20",
                    "markup_20d_pct": 0.0,
                    "markup_40d_pct": 0.0,
                    "markup_60d_pct": 0.0,
                    "markup_90d_pct": 0.0,
                    "ma20": round(ma20, 4),
                    "ma50": round(ma50, 4),
                }

                # Wave fields
                for k, v in _ww.items():
                    row[k] = v

                # Forward metrics
                for h in HORIZONS:
                    fm = forward_metrics(daily, i, h)
                    if fm:
                        row[f"h{h}"] = fm
                        row[f"h{h}_direction_correct"] = int(fm["direction_correct"])
                        row[f"h{h}_return_pct"] = round(fm["return_pct"], 3)
                        row[f"h{h}_mfe_pct"] = round(fm["mfe_pct"], 3)
                        row[f"h{h}_mae_pct"] = round(fm["mae_pct"], 3)
                        if h == 90:
                            row["markup_90d_pct"] = round(fm["mfe_pct"], 3)
                        if h == 20:
                            row["markup_20d_pct"] = round(fm["mfe_pct"], 3)
                        if h == 40:
                            row["markup_40d_pct"] = round(fm["mfe_pct"], 3)
                        if h == 60:
                            row["markup_60d_pct"] = round(fm["mfe_pct"], 3)

                signal_rows.append(row)

            processed += 1

        except KeyboardInterrupt:
            print("\nRun interrupted by user.")
            _send_error_email("Run interrupted by user (KeyboardInterrupt)", processed, len(signal_rows))
            _write_checkpoint(signal_rows, CHECKPOINT_FILE)
            sys.exit(0)
        except Exception as exc:
            skipped += 1
            print(f"WARN {symbol}: {exc}", file=sys.stderr)

        # ── Heartbeat and checkpoint ─────────────────────────────────────────
        if idx_sym % CHECKPOINT_EVERY == 0:
            elapsed = (time.time() - start_wall) / 60
            rate = idx_sym / elapsed if elapsed > 0 else 0
            eta = (len(symbols) - idx_sym) / rate if rate > 0 else 0
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"Processed {idx_sym}/{len(symbols)} symbols | "
                f"signals={len(signal_rows):,} | "
                f"skipped={skipped} | "
                f"elapsed={elapsed:.1f}m | "
                f"eta={eta:.1f}m"
            )
            _write_checkpoint(signal_rows, CHECKPOINT_FILE)

        time.sleep(SYMBOL_PAUSE)

    # ── Final checkpoint ─────────────────────────────────────────────────────
    elapsed_min = (time.time() - start_wall) / 60
    print(f"\nRun complete: {processed} symbols, {len(signal_rows):,} signals, {elapsed_min:.1f} minutes")
    _write_checkpoint(signal_rows, CHECKPOINT_FILE)

    # ── Write final outputs ───────────────────────────────────────────────────
    final_csv = OUTPUT_DIR / "qualified_long_signal_rows.csv"
    _write_checkpoint(signal_rows, final_csv)
    print(f"Final CSV written: {final_csv} ({final_csv.stat().st_size / 1024:.0f} KB)")

    # ── Validation ────────────────────────────────────────────────────────────
    with open(final_csv) as f:
        row_count = sum(1 for _ in f) - 1
    if row_count != len(signal_rows):
        _send_error_email(
            f"CSV row count mismatch: expected {len(signal_rows)}, got {row_count}",
            processed, len(signal_rows)
        )
    else:
        print(f"CSV validation passed: {row_count} rows confirmed")

    # ── Compute key stats for email ───────────────────────────────────────────
    target_n, state1_q4_n, state1_q4_mfe90 = _compute_winning_combo_stats(signal_rows)
    print(f"Target bucket n:              {target_n}")
    print(f"OBS_Q4+PROG_Q4+State1 n:      {state1_q4_n}")
    print(f"OBS_Q4+PROG_Q4+State1 mfe90:  {state1_q4_mfe90}%")

    # ── Send completion email ─────────────────────────────────────────────────
    _send_success_email(
        signals=len(signal_rows),
        processed=processed,
        skipped=skipped,
        duration_min=elapsed_min,
        target_n=target_n,
        state1_q4_n=state1_q4_n,
        state1_q4_mfe90=state1_q4_mfe90,
        output_files=[final_csv, CHECKPOINT_FILE],
    )

    print("\nDone. Check your email for results.")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        tb = traceback.format_exc()
        print(f"FATAL ERROR:\n{tb}")
        try:
            _send_error_email(tb, 0, 0)
        except Exception:
            pass
        sys.exit(1)
