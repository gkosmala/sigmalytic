# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_engine/nightly_campaign_pipeline.py

Phase 13D — Campaign Enrichment Layer
-------------------------------------
Runs after signal birth. For every ACTIVE campaign it:

1. Reads latest campaign rows from Supabase.
2. Pulls cached bars/prices from radar_service when available.
3. Computes lightweight Wyckoff lifecycle flags.
4. Advances the campaign state machine.
5. Enriches the campaign row:
   - entry_price
   - current_price
   - stop_price
   - pnf_target
   - return_pct
   - distance_to_target_pct
   - pnf_progress_pct
   - mfe90_expected
   - campaign_age_days
   - duration_days
   - days_in_state
   - state_changed_at
6. Writes campaign observations and state history when those optional tables exist.

This file is schema-tolerant except for the Phase 13D columns. Run the
included SQL migration before deploying this replacement file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from campaign_engine.campaign_state_engine import (
    CampaignState,
    WyckoffSignals,
    default_pnf_target,
    transition_campaign_state,
)
from campaign_engine.campaign_store import (
    get_active_campaigns,
    insert_campaign_observation,
    insert_campaign_state_history,
    update_campaign,
    utc_now_iso,
)

log = logging.getLogger("nightly_campaign_pipeline")

_CAMPAIGN_PIPELINE_AVAILABLE = True


# ---------------------------------------------------------------------------
# Safe parsing helpers
# ---------------------------------------------------------------------------

def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _days_since(value: Any) -> int:
    dt = _parse_dt(value)
    if not dt:
        return 0
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _extract_close(bar: dict[str, Any]) -> float:
    return _float(bar.get("c") or bar.get("close") or bar.get("price"))


def _extract_high(bar: dict[str, Any]) -> float:
    return _float(bar.get("h") or bar.get("high") or _extract_close(bar))


def _extract_low(bar: dict[str, Any]) -> float:
    return _float(bar.get("l") or bar.get("low") or _extract_close(bar))


def _extract_open(bar: dict[str, Any]) -> float:
    return _float(bar.get("o") or bar.get("open") or _extract_close(bar))


def _extract_volume(bar: dict[str, Any]) -> int:
    return _int(bar.get("v") or bar.get("volume"))


# ---------------------------------------------------------------------------
# Price / bar source
# ---------------------------------------------------------------------------

def _get_cached_bars_and_price(symbol: str) -> tuple[list[dict[str, Any]], Optional[float]]:
    """
    Uses radar_service caches if present. This avoids extra provider calls.
    """
    bars: list[dict[str, Any]] = []
    price: Optional[float] = None

    try:
        from radar_service import RADAR_CACHE, _historical_bars  # type: ignore

        raw_bars = _historical_bars.get(symbol) or _historical_bars.get(symbol.upper()) or []
        if isinstance(raw_bars, list):
            bars = raw_bars

        cached = RADAR_CACHE.get(symbol) or RADAR_CACHE.get(symbol.upper()) or {}
        if isinstance(cached, dict):
            price = _float(cached.get("price") or cached.get("current_price"), 0.0) or None
    except Exception as exc:
        log.warning("Radar cache unavailable for %s: %s", symbol, exc)

    if not price and bars:
        price = _extract_close(bars[-1]) or None

    return bars, price


# ---------------------------------------------------------------------------
# Wyckoff proxy signal extraction
# ---------------------------------------------------------------------------

def _compute_wed_from_bars(bars: list[dict[str, Any]]) -> int:
    if len(bars) < 6:
        return 0

    down_eff: list[float] = []
    for bar in bars[-12:]:
        o = _extract_open(bar)
        c = _extract_close(bar)
        v = max(_extract_volume(bar), 1)
        if c < o:
            down_eff.append(abs(c - o) / v)

    if len(down_eff) < 2:
        return 0

    wed = 0
    for i in range(1, len(down_eff)):
        if down_eff[i] < down_eff[i - 1]:
            wed += 1
        else:
            break
    return wed


def _signals_from_bars(campaign: dict[str, Any], bars: list[dict[str, Any]], price: Optional[float]) -> WyckoffSignals:
    """
    Lightweight daily proxy until full Weis/Wyckoff research metrics are wired.
    """
    if not bars or len(bars) < 25 or not price:
        return WyckoffSignals()

    recent = bars[-25:]
    last = bars[-1]

    closes = [_extract_close(b) for b in recent if _extract_close(b) > 0]
    highs = [_extract_high(b) for b in recent[:-1] if _extract_high(b) > 0]
    lows = [_extract_low(b) for b in recent[:-1] if _extract_low(b) > 0]
    volumes = [_extract_volume(b) for b in recent if _extract_volume(b) > 0]

    if not closes or not highs or not lows or not volumes:
        return WyckoffSignals()

    avg_vol = sum(volumes) / len(volumes)
    last_vol = _extract_volume(last)
    last_open = _extract_open(last)
    last_close = _extract_close(last)
    last_high = _extract_high(last)
    last_low = _extract_low(last)

    max_prev_high = max(highs)
    min_prev_low = min(lows)
    ma10 = sum(closes[-10:]) / min(len(closes), 10)
    ma20 = sum(closes[-20:]) / min(len(closes), 20)

    sos = last_close > max_prev_high and last_vol >= avg_vol * 1.05
    jac = sos
    spring = last_low < min_prev_low and last_close > min_prev_low

    down_bars = [b for b in recent[-10:] if _extract_close(b) < _extract_open(b)]
    spd = False
    if len(down_bars) >= 2:
        prev = down_bars[-2]
        cur = down_bars[-1]
        prev_range = abs(_extract_close(prev) - _extract_open(prev))
        cur_range = abs(_extract_close(cur) - _extract_open(cur))
        spd = _extract_volume(cur) >= _extract_volume(prev) and cur_range <= prev_range

    dei = last_close >= ma10 >= ma20 and last_close >= last_open
    bu = (last_low >= ma20 * 0.98 and last_close >= ma10 and spd) or (last_close > ma20 and dei)
    lps = bu

    upthrust = last_high > max_prev_high and last_close < max_prev_high and last_vol >= avg_vol * 1.10
    choch = last_close < ma20 * 0.97 or upthrust

    wed = _compute_wed_from_bars(recent)
    if wed >= 2 and last_close < ma10:
        choch = True

    if choch or upthrust:
        behavior = "DISTRIBUTION"
    elif spring or sos or spd or dei:
        behavior = "ACCUMULATION"
    else:
        behavior = "AMBIGUOUS"

    return WyckoffSignals(
        sos_detected=sos,
        jac_detected=jac,
        bu_detected=bu,
        lps_detected=lps,
        choch_detected=choch,
        spring_detected=spring,
        upthrust_detected=upthrust,
        spd=spd,
        dei=dei,
        wed_count=wed,
        behavioral_state=behavior,
    )


# ---------------------------------------------------------------------------
# Phase 13D enrichment
# ---------------------------------------------------------------------------

def _mfe90_expected_for_tier(tier: str) -> float:
    tier = str(tier or "").upper()
    if tier == "TIER_1":
        return 25.0
    if tier == "TIER_2":
        return 15.0
    if tier == "TIER_3":
        return 8.0
    return 10.0


def _fallback_stop_price(entry: float, tier: str) -> Optional[float]:
    if entry <= 0:
        return None
    tier = str(tier or "").upper()
    risk = 0.08 if tier == "TIER_1" else 0.10 if tier == "TIER_2" else 0.12
    return round(entry * (1.0 - risk), 4)


def _build_updates(
    campaign: dict[str, Any],
    price: Optional[float],
    new_state: str,
    state_changed: bool,
) -> dict[str, Any]:
    tier = str(campaign.get("historical_confidence") or "")
    now_iso = utc_now_iso()

    birth_date = campaign.get("birth_date") or campaign.get("created_at")
    state_changed_at_existing = campaign.get("state_changed_at") or campaign.get("created_at") or birth_date

    entry = (
        _float(campaign.get("entry_price"))
        or _float(campaign.get("current_price"))
        or _float(price)
    )

    current = _float(price) or _float(campaign.get("current_price")) or entry
    pnf_target = _float(campaign.get("pnf_target")) or (default_pnf_target(entry, tier) or 0.0)
    stop = _float(campaign.get("stop_price")) or (_fallback_stop_price(entry, tier) or 0.0)

    return_pct = 0.0
    if entry > 0 and current > 0:
        return_pct = ((current - entry) / entry) * 100.0

    distance_to_target_pct = 0.0
    if current > 0 and pnf_target > 0:
        distance_to_target_pct = ((pnf_target - current) / current) * 100.0

    pnf_progress_pct = 0.0
    if entry > 0 and pnf_target > entry and current > 0:
        pnf_progress_pct = ((current - entry) / (pnf_target - entry)) * 100.0
        pnf_progress_pct = _clamp(pnf_progress_pct, 0.0, 100.0)

    state_changed_at = now_iso if state_changed else state_changed_at_existing
    days_in_state = 0 if state_changed else _days_since(state_changed_at_existing)

    age_days = _days_since(birth_date)

    updates: dict[str, Any] = {
        "current_state": new_state,
        "state_enum": new_state,
        "campaign_age_days": age_days,
        "duration_days": age_days,
        "days_in_state": days_in_state,
        "state_changed_at": state_changed_at,
        "return_pct": round(return_pct, 2),
        "distance_to_target_pct": round(distance_to_target_pct, 2),
        "pnf_progress_pct": round(pnf_progress_pct, 1),
        "mfe90_expected": round(_float(campaign.get("mfe90_expected")) or _mfe90_expected_for_tier(tier), 2),
    }

    if current > 0:
        updates["current_price"] = round(float(current), 4)

    if entry > 0:
        updates["entry_price"] = round(float(entry), 4)

    if pnf_target > 0:
        updates["pnf_target"] = round(float(pnf_target), 4)

    if stop > 0:
        updates["stop_price"] = round(float(stop), 4)

    return updates


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_nightly_campaign_pipeline() -> dict[str, Any]:
    """
    Entrypoint called by backend/main.py nightly scheduler and manual admin API.
    """
    log.info("CAMPAIGN PIPELINE: starting nightly lifecycle/enrichment run")

    try:
        campaigns = get_active_campaigns(limit=2000)
    except Exception as exc:
        log.error("CAMPAIGN PIPELINE: failed to load active campaigns — %s", exc)
        return {"ok": False, "error": str(exc), "processed": 0}

    processed = 0
    changed = 0
    errors = 0
    enriched = 0

    for campaign in campaigns:
        campaign_id = campaign.get("campaign_id")
        symbol = str(campaign.get("symbol") or "").upper().strip()

        if not campaign_id or not symbol:
            continue

        try:
            bars, price = _get_cached_bars_and_price(symbol)
            signals = _signals_from_bars(campaign, bars, price)

            transition = transition_campaign_state(campaign, signals, current_price=price)
            updates = _build_updates(
                campaign,
                price,
                transition.new_state.value,
                transition.changed,
            )

            update_campaign(campaign_id, updates)
            enriched += 1

            insert_campaign_observation({
                "campaign_id": campaign_id,
                "symbol": symbol,
                "state": transition.new_state.value,
                "current_state": transition.new_state.value,
                "price": round(float(price), 4) if price else updates.get("current_price"),
                "current_price": round(float(price), 4) if price else updates.get("current_price"),
                "return_pct": updates.get("return_pct"),
                "pnf_progress_pct": updates.get("pnf_progress_pct"),
                "distance_to_target_pct": updates.get("distance_to_target_pct"),
                "sos_detected": signals.sos_detected,
                "jac_detected": signals.jac_detected,
                "bu_detected": signals.bu_detected,
                "lps_detected": signals.lps_detected,
                "choch_detected": signals.choch_detected,
                "spring_detected": signals.spring_detected,
                "upthrust_detected": signals.upthrust_detected,
                "spd": signals.spd,
                "dei": signals.dei,
                "wed_count": signals.wed_count,
                "behavioral_state": signals.behavioral_state,
                "notes": transition.reason,
            })

            if transition.changed:
                changed += 1
                insert_campaign_state_history({
                    "campaign_id": campaign_id,
                    "symbol": symbol,
                    "old_state": transition.old_state.value,
                    "new_state": transition.new_state.value,
                    "reason": transition.reason,
                    "confidence": transition.confidence,
                })

            processed += 1
            log.info(
                "CAMPAIGN PIPELINE: %s campaign_id=%s %s→%s changed=%s return=%s%% pnf=%s%% reason=%s",
                symbol,
                campaign_id,
                transition.old_state.value,
                transition.new_state.value,
                transition.changed,
                updates.get("return_pct"),
                updates.get("pnf_progress_pct"),
                transition.reason,
            )

        except Exception as exc:
            errors += 1
            log.error("CAMPAIGN PIPELINE: error on %s campaign_id=%s — %s", symbol, campaign_id, exc)

    result = {
        "ok": errors == 0,
        "processed": processed,
        "enriched": enriched,
        "changed": changed,
        "errors": errors,
        "as_of": utc_now_iso(),
    }

    log.info(
        "CAMPAIGN PIPELINE: complete processed=%s enriched=%s changed=%s errors=%s",
        processed,
        enriched,
        changed,
        errors,
    )
    return result
