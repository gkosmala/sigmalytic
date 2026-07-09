#!/usr/bin/env python3
"""
Sigmalytic V2 Step 5 — Campaign pipeline data coverage audit.

Purpose:
    Detect incomplete universe/bar coverage, silent Alpaca pagination truncation,
    and insufficient bar counts before campaign evidence is trusted.

Mode:
    Local JSON audit only.
    No Supabase write.
    No campaign mutation.
    No D3D.
    No operator-control confirmation.
    No trade signal.
    No Stripe.

Usage:
    py -B 05_pipeline_coverage_audit.py --snapshot nightly_snapshot.json --min-bars 120
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError("snapshot root must be a JSON object")
    return payload


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--min-bars", type=int, default=120)
    args = parser.parse_args()

    path = Path(args.snapshot)
    if not path.exists():
        raise SystemExit(f"FAIL: snapshot not found: {path}")

    data = load_json_object(path)

    requested = as_list(data.get("symbols_requested"))
    bars_by_symbol = as_dict(data.get("bars_by_symbol"))
    warnings = as_list(data.get("pagination_warnings"))
    universe_count = data.get("universe_count", "unknown")

    print("=" * 72)
    print("SIGMALYTIC V2 — PIPELINE COVERAGE AUDIT")
    print("MODE: READ-ONLY / LOCAL SNAPSHOT ONLY")
    print("=" * 72)

    missing = [symbol for symbol in requested if symbol not in bars_by_symbol]

    insufficient: dict[str, int] = {}
    invalid_bar_counts: dict[str, Any] = {}

    for symbol, raw_count in bars_by_symbol.items():
        try:
            count = int(raw_count or 0)
        except Exception:
            invalid_bar_counts[str(symbol)] = raw_count
            continue

        if count < args.min_bars:
            insufficient[str(symbol)] = count

    print(f"Snapshot file: {path}")
    print(f"Universe count reported: {universe_count}")
    print(f"Symbols requested: {len(requested)}")
    print(f"Symbols with bars: {len(bars_by_symbol)}")
    print(f"Missing symbols: {len(missing)}")
    print(f"Symbols below {args.min_bars} bars: {len(insufficient)}")
    print(f"Invalid bar-count values: {len(invalid_bar_counts)}")
    print(f"Pagination warnings: {len(warnings)}")

    if missing[:20]:
        print("FIRST MISSING SYMBOLS:", ", ".join(str(s) for s in missing[:20]))

    if insufficient:
        print("FIRST INSUFFICIENT SYMBOLS:", list(insufficient.items())[:20])

    if invalid_bar_counts:
        print("FIRST INVALID BAR COUNTS:", list(invalid_bar_counts.items())[:20])

    if warnings:
        print("PAGINATION WARNINGS:")
        for warning in warnings[:20]:
            print("  ", warning)

    ok = (
        bool(requested)
        and bool(bars_by_symbol)
        and not missing
        and not insufficient
        and not invalid_bar_counts
        and not warnings
    )

    if ok:
        print("=" * 72)
        print("PASS: coverage appears complete for supplied snapshot.")
        print("PASS: no silent truncation detected in supplied snapshot.")
        print("=" * 72)
        return 0

    print("=" * 72)
    print("FAIL: coverage gaps exist or snapshot is incomplete.")
    print("DO NOT treat campaign discovery as complete from this snapshot.")
    print("=" * 72)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
