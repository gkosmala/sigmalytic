# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
Sigmalytic Decision Engine — Shared Core Logic
Used by both the backend (FastAPI) and frontend (Dash).
Includes behavioral modeling and options bias scoring via Alpaca delayed data.
"""

from __future__ import annotations
import math
import re
import os
import requests
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Literal

Tone = Literal["up", "down", "neutral"]

ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET = os.getenv("ALPACA_API_SECRET", "")
ALPACA_DATA_URL   = "https://data.alpaca.markets"


# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────

@dataclass
class KeyLevels:
    breakout:   float
    prior_high: float
    expansion:  float
    confirm:    float
    trigger:    float
    trap:       float
    fail:       float


@dataclass
class BehavioralScore:
    body_ratio:       float   # candle conviction score 0-100
    rejection_score:  float   # wick rejection strength 0-100
    velocity_score:   float   # price momentum strength 0-100
    herding_index:    float   # crowd directional lean 0-100
    composite:        int     # final blended behavioral score 0-100
    label:            str     # human-readable behavioral label


@dataclass
class Optionsbias:
    put_call_ratio:   float   # >1 = bearish crowd, <1 = bullish crowd
    gamma_level:      float   # dominant gamma strike near price
    iv_skew:          float   # put IV minus call IV — positive = fear
    net_bias:         str     # BULLISH / BEARISH / NEUTRAL
    confidence:       int     # 0-100 confidence in options signal
    source:           str     # LIVE / DELAYED / SYNTHETIC


@dataclass
class Decision:
    status:      str
    bias:        str
    grade:       str
    confidence:  str
    mode:        str
    score:       int
    next_action: str
    behavior:    str


@dataclass
class ConfluenceNode:
    label:        str
    public_label: str
    level:        float
    score:        int
    tone:         Tone


@dataclass
class LiveUpdate:
    type:             str
    symbol:           str
    price:            float
    volume:           int
    timestamp:        str
    sequence:         int
    decision:         Decision
    confluence:       list[ConfluenceNode]
    behavioral_score: BehavioralScore = field(default=None)
    options_bias:     Optionsbias     = field(default=None)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Candle:
    o: float
    h: float
    l: float
    c: float
    t: str = ""


# ─────────────────────────────────────────────
# Pure functions
# ─────────────────────────────────────────────

def sanitize_symbol(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.strip().upper())


def get_key_levels(price: float, count_guide: dict = None) -> KeyLevels:
    """
    FIX (2026-08-09): previously always used a fixed-percentage
    synthetic formula (price * 1.03, price * 0.992, etc.) regardless
    of any real market structure -- confirmed to have no documented
    rationale anywhere in this function's history, genuinely
    leftover, un-upgraded placeholder code.

    Now derives real levels from the Wyckoff Count Guide projection
    (backend's PnFWeisEngine.count_guide_projection()) when provided:
    the actual, currently-relevant PnF consolidation range and its
    genuine upside/downside targets, not arbitrary percentage offsets.
    Falls back to the old synthetic formula ONLY if real data isn't
    available (e.g. backend unreachable, insufficient history) --
    this fallback is intentionally still synthetic math, since some
    real levels are strictly better than none, but every caller
    should be migrated to supply count_guide where possible rather
    than relying on this fallback silently.
    """
    safe = price if math.isfinite(price) and price > 0 else 1.0

    if count_guide and count_guide.get("available"):
        range_high = count_guide.get("range_high", safe)
        range_low = count_guide.get("range_low", safe)
        upside_conservative = count_guide.get("upside_conservative_target", range_high)
        upside_aggressive = count_guide.get("upside_aggressive_target", range_high)
        downside_conservative = count_guide.get("downside_conservative_target", range_low)
        downside_aggressive = count_guide.get("downside_aggressive_target", range_low)
        return KeyLevels(
            breakout=round(upside_aggressive, 4),
            prior_high=round(range_high, 4),
            expansion=round(upside_conservative, 4),
            confirm=round(safe, 4),
            trigger=round(range_low, 4),
            trap=round(downside_conservative, 4),
            fail=round(downside_aggressive, 4),
        )

    return KeyLevels(
        breakout=round(safe * 1.030, 4),
        prior_high=round(safe * 1.022, 4),
        expansion=round(safe * 1.015, 4),
        confirm=round(safe, 4),
        trigger=round(safe * 0.992, 4),
        trap=round(safe * 0.985, 4),
        fail=round(safe * 0.970, 4),
    )


# ─────────────────────────────────────────────
# Behavioral Modeling
# ─────────────────────────────────────────────

def calculate_behavioral_score(candles: list[dict]) -> BehavioralScore:
    """
    Derives market psychology from candle structure.
    Inputs: list of candle dicts with keys o, h, l, c
    """
    if not candles or len(candles) < 3:
        return BehavioralScore(
            body_ratio=50, rejection_score=50, velocity_score=50,
            herding_index=50, composite=50, label="Insufficient Data"
        )

    # ── Candle Body Ratio ──────────────────────────────────────────
    # Measures conviction — high ratio = directional confidence
    body_ratios = []
    for c in candles[-10:]:
        total_range = c["h"] - c["l"]
        if total_range == 0:
            continue
        body = abs(c["c"] - c["o"])
        body_ratios.append(body / total_range)
    body_ratio = round((sum(body_ratios) / len(body_ratios)) * 100, 1) if body_ratios else 50.0

    # ── Rejection Score ────────────────────────────────────────────
    # Long wicks at key levels = institutional rejection signal
    rejection_scores = []
    for c in candles[-10:]:
        total_range = c["h"] - c["l"]
        if total_range == 0:
            continue
        upper_wick = c["h"] - max(c["o"], c["c"])
        lower_wick = min(c["o"], c["c"]) - c["l"]
        # High upper wick on up-candle = rejection of highs (bearish)
        # High lower wick on down-candle = rejection of lows (bullish)
        if c["c"] > c["o"]:
            rejection_scores.append((lower_wick / total_range) * 100)
        else:
            rejection_scores.append((upper_wick / total_range) * 100)
    rejection_score = round(sum(rejection_scores) / len(rejection_scores), 1) if rejection_scores else 50.0

    # ── Velocity Score ─────────────────────────────────────────────
    # Price momentum — how fast and consistently price is moving
    closes = [c["c"] for c in candles[-10:]]
    if len(closes) >= 2:
        moves = [abs(closes[i] - closes[i-1]) / closes[i-1] * 100
                 for i in range(1, len(closes))]
        avg_move = sum(moves) / len(moves)
        # Normalize to 0-100 — 1% average move = 100 score
        velocity_score = round(min(100, avg_move * 100), 1)
    else:
        velocity_score = 50.0

    # ── Herding Index ──────────────────────────────────────────────
    # Consecutive same-direction candles = crowd is leaning one way
    same_direction = 0
    for i in range(1, min(6, len(candles))):
        c = candles[-(i)]
        prev = candles[-(i+1)]
        if (c["c"] > c["o"]) == (prev["c"] > prev["o"]):
            same_direction += 1
        else:
            break
    # Scale: 5 consecutive same-direction = 100 herding
    herding_index = round(min(100, same_direction * 20), 1)

    # ── Composite Score ────────────────────────────────────────────
    composite = int(
        body_ratio      * 0.35 +
        rejection_score * 0.25 +
        velocity_score  * 0.20 +
        herding_index   * 0.20
    )
    composite = max(0, min(100, composite))

    # ── Label ──────────────────────────────────────────────────────
    if composite >= 75:
        label = "Strong Directional Conviction"
    elif composite >= 55:
        label = "Moderate Momentum"
    elif composite >= 40:
        label = "Indecision / Absorption"
    else:
        label = "Exhaustion / Reversal Risk"

    return BehavioralScore(
        body_ratio=body_ratio,
        rejection_score=rejection_score,
        velocity_score=velocity_score,
        herding_index=herding_index,
        composite=composite,
        label=label,
    )


# ─────────────────────────────────────────────
# Options Bias (Alpaca Delayed Data)
# ─────────────────────────────────────────────

def fetch_options_bias(symbol: str, price: float) -> Optionsbias:
    """
    Fetches live options data via GEX engine (Alpaca OPRA).
    Falls back to direct Alpaca call, then synthetic if unavailable.
    """
    # Try GEX engine first — it has live OPRA data
    try:
        from gex_engine import score_gex
        gex = score_gex(symbol, price, [], is_intelligence_layer=False)
        if gex and gex.get("gex_available"):
            regime    = gex.get("gex_regime", "NEUTRAL")
            gex_score = gex.get("gex_score", 50) or 50
            wall      = gex.get("gex_wall") or price
            net_bias  = "BULLISH" if regime == "POSITIVE" else "BEARISH" if regime == "NEGATIVE" else "NEUTRAL"
            confidence= min(100, int(abs(gex_score - 50) * 2))
            pcr       = 0.75 if regime == "POSITIVE" else 1.25 if regime == "NEGATIVE" else 1.0
            return Optionsbias(
                put_call_ratio=round(pcr, 3),
                gamma_level=round(wall, 2),
                iv_skew=round((pcr - 1.0) * 0.05, 4),
                net_bias=net_bias,
                confidence=confidence,
                source="LIVE",
            )
    except Exception:
        pass

    if not ALPACA_API_KEY or not ALPACA_API_SECRET:
        return _synthetic_options_bias(price)

    try:
        headers = {
            "APCA-API-KEY-ID":     ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
        }

        # Fetch options snapshot for symbol
        url = f"{ALPACA_DATA_URL}/v1beta1/options/snapshots/{symbol}"
        params = {"feed": "indicative", "limit": 100}
        resp = requests.get(url, headers=headers, params=params, timeout=3)

        if resp.status_code != 200:
            return _synthetic_options_bias(price)

        data = resp.json()
        snapshots = data.get("snapshots", {})

        if not snapshots:
            return _synthetic_options_bias(price)

        # ── Parse options chain ────────────────────────────────────
        call_volume = 0
        put_volume  = 0
        call_iv_sum = 0.0
        put_iv_sum  = 0.0
        call_count  = 0
        put_count   = 0
        gamma_strikes = {}

        for contract, snap in snapshots.items():
            greeks     = snap.get("greeks", {})
            quote      = snap.get("latestQuote", {})
            trade      = snap.get("latestTrade", {})
            iv         = snap.get("impliedVolatility", 0) or 0
            gamma      = greeks.get("gamma", 0) or 0
            volume     = trade.get("s", 0) or 0  # size = volume proxy

            # Determine call or put from contract name
            # Alpaca contract format: AAPL250117C00150000
            is_call = "C" in contract.split(symbol)[-1][:10]

            if is_call:
                call_volume += volume
                call_iv_sum += iv
                call_count  += 1
            else:
                put_volume  += volume
                put_iv_sum  += iv
                put_count   += 1

            # Track gamma by strike for gamma level detection
            strike_str = contract[-8:]
            try:
                strike = int(strike_str) / 1000
                if abs(strike - price) < price * 0.05:  # within 5% of price
                    gamma_strikes[strike] = gamma_strikes.get(strike, 0) + abs(gamma)
            except Exception:
                pass

        # ── Put/Call Ratio ─────────────────────────────────────────
        total_volume = call_volume + put_volume
        if total_volume == 0:
            return _synthetic_options_bias(price)

        put_call_ratio = round(put_volume / max(call_volume, 1), 3)

        # ── IV Skew ────────────────────────────────────────────────
        avg_call_iv = call_iv_sum / max(call_count, 1)
        avg_put_iv  = put_iv_sum  / max(put_count,  1)
        iv_skew     = round(avg_put_iv - avg_call_iv, 4)

        # ── Gamma Level ────────────────────────────────────────────
        if gamma_strikes:
            gamma_level = max(gamma_strikes, key=gamma_strikes.get)
        else:
            gamma_level = round(price, 2)

        # ── Net Bias ───────────────────────────────────────────────
        if put_call_ratio > 1.2 and iv_skew > 0.02:
            net_bias    = "BEARISH"
            confidence  = min(100, int(put_call_ratio * 40 + iv_skew * 100))
        elif put_call_ratio < 0.8 and iv_skew < -0.02:
            net_bias    = "BULLISH"
            confidence  = min(100, int((1 - put_call_ratio) * 60 + abs(iv_skew) * 100))
        else:
            net_bias    = "NEUTRAL"
            confidence  = 40

        return Optionsbias(
            put_call_ratio=put_call_ratio,
            gamma_level=round(gamma_level, 2),
            iv_skew=iv_skew,
            net_bias=net_bias,
            confidence=confidence,
            source="DELAYED",
        )

    except Exception:
        return _synthetic_options_bias(price)


def _synthetic_options_bias(price: float) -> Optionsbias:
    """
    Fallback synthetic options bias when API is unavailable.
    Derives approximate values from price structure only.
    """
    kl = get_key_levels(price)
    above_confirm = price >= kl.confirm
    put_call_ratio = 0.85 if above_confirm else 1.15
    iv_skew        = -0.01 if above_confirm else 0.02
    net_bias       = "BULLISH" if above_confirm else "BEARISH"
    gamma_level    = round(kl.confirm, 2)
    return Optionsbias(
        put_call_ratio=put_call_ratio,
        gamma_level=gamma_level,
        iv_skew=iv_skew,
        net_bias=net_bias,
        confidence=35,
        source="SYNTHETIC",
    )


# ─────────────────────────────────────────────
# Decision Engine v2
# ─────────────────────────────────────────────

def run_decision(price: float, volume_confirm: bool,
                 behavioral: BehavioralScore = None,
                 options: Optionsbias = None,
                 count_guide: dict = None) -> Decision:
    """
    Enhanced decision engine that blends price, behavioral,
    and options signals into a single scored output.
    """
    kl = get_key_levels(price, count_guide=count_guide)

    # ── Base price score ───────────────────────────────────────────
    if price >= kl.confirm and volume_confirm:
        base_score = 72
    elif price >= kl.trigger:
        base_score = 49
    else:
        base_score = 32

    # ── Behavioral adjustment ──────────────────────────────────────
    behavioral_adj = 0
    if behavioral:
        b = behavioral.composite
        if b >= 70:
            behavioral_adj = +10
        elif b >= 50:
            behavioral_adj = +5
        elif b < 35:
            behavioral_adj = -8

    # ── Options bias adjustment ────────────────────────────────────
    options_adj = 0
    if options:
        if options.net_bias == "BULLISH":
            options_adj = +8
        elif options.net_bias == "BEARISH":
            options_adj = -8
        # Scale by confidence
        options_adj = int(options_adj * (options.confidence / 100))

    # ── Final score ────────────────────────────────────────────────
    score = max(0, min(100, base_score + behavioral_adj + options_adj))

    above_trigger = price >= kl.trigger

    # ── Behavioral label for behavior field ────────────────────────
    beh_label = behavioral.label if behavioral else "STANDARD"

    return Decision(
        status=(
            "A LONG"          if score >= 80 else
            "B TACTICAL LONG" if score >= 55 else
            "C PROBE"         if score >= 40 else
            "STANDDOWN"
        ),
        bias=(
            "LONG"    if score >= 55 else
            "NEUTRAL" if score >= 40 else
            "SHORT BIAS"
        ),
        grade=(
            "A" if score >= 80 else
            "B" if score >= 55 else
            "C" if score >= 40 else
            "D"
        ),
        confidence=(
            "HIGH"   if score >= 80 else
            "MEDIUM" if score >= 55 else
            "LOW"
        ),
        mode=(
            "Expansion Confirmed" if score >= 80 else
            "Retest / Hold Zone"  if score >= 55 else
            "Caution / Digestion"
        ),
        score=score,
        next_action=(
            "Price is above anchor with behavioral confirmation — expansion likely."
            if score >= 80 else
            "Price is above trigger but below full confirmation; protect failure levels."
            if above_trigger else
            "Wait for reclaim above the trigger anchor."
        ),
        behavior=f"ABOVE GAP OPEN ANCHOR · {beh_label}" if above_trigger
                 else f"WAITING / DIGESTION · {beh_label}",
    )


def build_confluence_nodes(price: float,
                            behavioral: BehavioralScore = None,
                            options: Optionsbias = None,
                            count_guide: dict = None) -> list[ConfluenceNode]:
    """
    Enhanced confluence nodes that adjust scores based on
    behavioral and options signals.
    """
    kl = get_key_levels(price, count_guide=count_guide)
    above_trigger = price > kl.trigger


    raw = [
        ConfluenceNode("Expansion Node 1", "Expansion Node",   kl.breakout,   63, "up"),
        ConfluenceNode("Liquidity Retest", "Liquidity Retest", kl.prior_high, 60, "up"),
        ConfluenceNode("Expansion Node 2", "Expansion Node",   kl.expansion,  57, "up"),
        ConfluenceNode("Failure Node",     "Failure Node",     kl.fail,       53, "down"),
    ]

    for node in raw:
        bonus = 0

        # Price position bonus
        if above_trigger and node.tone == "up":
            bonus += 5

        # Behavioral bonus
        if behavioral:
            if behavioral.composite >= 70 and node.tone == "up":
                bonus += 6
            elif behavioral.composite < 35 and node.tone == "down":
                bonus += 6

        # Options bias bonus
        if options:
            if options.net_bias == "BULLISH" and node.tone == "up":
                bonus += int(4 * options.confidence / 100)
            elif options.net_bias == "BEARISH" and node.tone == "down":
                bonus += int(4 * options.confidence / 100)

        node.score = max(35, min(94, node.score + bonus))

    return raw


def create_live_update(
    symbol: str, price: float, volume: int, sequence: int,
    candles: list[dict] = None, count_guide: dict = None,
) -> LiveUpdate:
    """
    Creates a full live update with behavioral and options scoring.
    Pass candles list for behavioral modeling — falls back gracefully if absent.
    Pass count_guide (from the backend's PnFWeisEngine.count_guide_projection())
    for real, structural key levels — falls back to synthetic percentage
    levels only if not provided.
    """
    behavioral = calculate_behavioral_score(candles) if candles else None
    try:
        options = fetch_options_bias(symbol, price)
    except Exception:
        options = _synthetic_options_bias(price)
    decision   = run_decision(price, volume > 1_500_000, behavioral, options, count_guide=count_guide)
    confluence = build_confluence_nodes(price, behavioral, options, count_guide=count_guide)

    return LiveUpdate(
        type="LIVE_UPDATE",
        symbol=symbol,
        price=price,
        volume=volume,
        timestamp=datetime.now(timezone.utc).isoformat(),
        sequence=sequence,
        decision=decision,
        confluence=confluence,
        behavioral_score=behavioral,
        options_bias=options,
    )


def generate_initial_candles(anchor_price: float) -> list[Candle]:
    safe = anchor_price if math.isfinite(anchor_price) and anchor_price > 0 else 100.0
    pattern = [
        -0.018, -0.014, -0.009, -0.004,  0.002,  0.006,  0.010,  0.007,
         0.004, -0.002, -0.006, -0.009, -0.012, -0.007, -0.003,  0.001,
         0.004,  0.007,  0.005,  0.002, -0.001,  0.000,
    ]
    candles = []
    for i, pct in enumerate(pattern):
        prev_pct = pct - 0.002 if i == 0 else pattern[i - 1]
        o   = safe * (1 + prev_pct)
        c   = safe * (1 + pct)
        rng = safe * (0.0025 + (i % 5) * 0.0004)
        candles.append(Candle(
            o=round(o, 2),
            h=round(max(o, c) + rng, 2),
            l=round(min(o, c) - rng, 2),
            c=round(c, 2),
        ))
    return candles