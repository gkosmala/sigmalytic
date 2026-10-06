# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/readiness_impact.py
---------------------------
READ-ONLY admin diagnostic. Measures what the radar's readiness score and
opportunity state would be if the five factor fields (confluence,
expansion_node, relative_strength, volume_pressure, behavioral) were passed
to the behavioural transition engine, versus how it behaves today, where those
fields are missing and read as 0.

For a sample of live symbols it takes today's snapshot and daily bars, runs the
real score_symbol(), and evaluates the real engine twice per stage:

  stage 1  inside score_symbol, cached, used to SORT the radar
           shipped: no factors, no composite_score
           restored: generic factors + generic composite
  stage 2  recomputed for the page users see
           shipped: live Weis composite_score, no factors
           restored: same Weis composite_score + the factors

Nothing is written, cached, scored or alerted. No scan state is touched.

    GET /api/admin/readiness-impact?limit=60     (admin only)
"""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, Header

try:
    from backend import behavioral_transition_engine as bte
except Exception:  # run from inside backend/
    import behavioral_transition_engine as bte

FACTOR_KEYS = ("expansion_node", "relative_strength", "volume_pressure", "behavioral", "confluence")
MAX_SAMPLE = 150


def _eval(row: Dict[str, Any]) -> Dict[str, Any]:
    r = bte.evaluate_behavioral_transition(row)
    return {"readiness": r["readiness_score"], "state": r["opportunity_state"], "side": r["side"]}


def compare_readiness(result: Dict[str, Any], weis_composite: float) -> Dict[str, Any]:
    """
    `result` is score_symbol(..., _return_factors=True). `weis_composite` is the
    composite_score the live radar cache holds for the symbol (Weis-based).
    """
    factors = dict(result.get("_factors") or {})
    base = {k: v for k, v in result.items() if k != "_factors"}
    fac = {k: factors.get(k, 0) for k in FACTOR_KEYS}

    s1_now = _eval(dict(base))                                             # as shipped, sort basis
    s1_fix = _eval(dict(base, composite_score=factors.get("composite", 0), **fac))
    s2_now = _eval(dict(base, composite_score=weis_composite))             # as shipped, page shown
    s2_fix = _eval(dict(base, composite_score=weis_composite, **fac))

    return {
        "symbol": base.get("symbol"),
        "side": s2_now["side"],
        "weis_composite": weis_composite,
        "factors": {k: round(float(fac[k] or 0), 1) for k in FACTOR_KEYS},
        "stage1": {"now": s1_now, "restored": s1_fix, "delta": round(s1_fix["readiness"] - s1_now["readiness"], 1)},
        "stage2": {"now": s2_now, "restored": s2_fix, "delta": round(s2_fix["readiness"] - s2_now["readiness"], 1)},
    }


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"symbols": len(rows)}
    for stage in ("stage1", "stage2"):
        block: Dict[str, Any] = {}
        for side in ("Long", "Short"):
            mine = [r for r in rows if r["side"] == side]
            if not mine:
                continue
            deltas = [r[stage]["delta"] for r in mine]
            changes = Counter((r[stage]["now"]["state"], r[stage]["restored"]["state"])
                              for r in mine if r[stage]["now"]["state"] != r[stage]["restored"]["state"])
            block[side] = {
                "n": len(mine),
                "mean_delta": round(statistics.mean(deltas), 1),
                "median_delta": round(statistics.median(deltas), 1),
                "min_delta": min(deltas),
                "max_delta": max(deltas),
                "state_changes": sum(changes.values()),
                "transitions": [{"from": a, "to": b, "count": c} for (a, b), c in changes.most_common()],
            }
        out[stage] = block
    out["states_now"] = dict(Counter(f"{r['side']}/{r['stage2']['now']['state']}" for r in rows))
    out["states_restored"] = dict(Counter(f"{r['side']}/{r['stage2']['restored']['state']}" for r in rows))
    return out


def pick_sample(symbols: List[str], limit: int) -> List[str]:
    """Evenly spaced through the sorted universe, so the sample is not just A's."""
    syms = sorted(set(symbols))
    limit = max(1, min(int(limit), MAX_SAMPLE, len(syms) or 1))
    if len(syms) <= limit:
        return syms
    step = len(syms) / limit
    return [syms[int(i * step)] for i in range(limit)]


def run_diagnostic(cache: Dict[str, dict], limit: int,
                   fetch_snapshots: Callable, fetch_bars: Callable, score_symbol: Callable) -> Dict[str, Any]:
    sample = pick_sample(list(cache.keys()), limit)
    snaps = fetch_snapshots(sample) or {}
    bars_by = fetch_bars(sample) or {}
    rows, skipped = [], []
    for sym in sample:
        snap, bars = snaps.get(sym), bars_by.get(sym) or []
        if not snap or len(bars) < 20:
            skipped.append({"symbol": sym, "reason": "no snapshot" if not snap else f"{len(bars)} bars"})
            continue
        try:
            res = score_symbol(sym, snap, bars, _return_factors=True)
        except Exception as exc:
            skipped.append({"symbol": sym, "reason": f"score error: {str(exc)[:80]}"})
            continue
        if not res:
            skipped.append({"symbol": sym, "reason": "score_symbol rejected the data"})
            continue
        wc = float((cache.get(sym) or {}).get("composite_score") or 0)
        rows.append(compare_readiness(res, wc))
    return {"summary": summary_or_empty(rows), "rows": rows, "skipped": skipped,
            "note": ("Read-only. Bars are the last ~280 days of daily bars, fetched fresh; the live scanner "
                     "uses its own cached bars, so small differences are expected.")}


def summary_or_empty(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return summarize(rows) if rows else {"symbols": 0}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _admin_dependency():
    try:
        from backend.main import require_admin
    except Exception:  # pragma: no cover
        from main import require_admin
    return require_admin


def _admin(authorization: str = Header(default="")) -> str:
    return _admin_dependency()(authorization)


readiness_router = APIRouter(prefix="/api/admin", tags=["admin"])


@readiness_router.get("/readiness-impact")
def readiness_impact(limit: int = 60, _admin_email: str = Depends(_admin)):
    try:
        from backend import radar_service as rsvc
        from backend.snapshot_service import _load_radar_cache_for_admin_report
    except Exception:  # pragma: no cover
        import radar_service as rsvc
        from snapshot_service import _load_radar_cache_for_admin_report
    cache = _load_radar_cache_for_admin_report()
    return run_diagnostic(cache, limit, rsvc.fetch_snapshots, rsvc.fetch_bars_multi, rsvc.score_symbol)
