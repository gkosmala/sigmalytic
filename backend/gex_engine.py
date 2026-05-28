# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
GEX / Options Flow / Market Tide Engine
================================================================================
File    : gex_engine.py
Version : 1.0.0
Date    : 2026-05-27

PURPOSE
-------
Institutional-grade confluence engine combining:
  1. Gamma Exposure (GEX) — dealer hedging regime detection
  2. Options Flow — ask-side sweep direction (call vs put premium)
  3. SOT + GEX confluence scoring
  4. IV Rank — dynamic strategy selection
  5. Market Tide — broad market macro filter (SPY/QQQ/IWM aggregate)
  6. Automated stop-loss calculation

OPTIONS FEED INTEGRATION
------------------------
Currently runs in PLACEHOLDER mode — outputs neutral scores.
To activate, set the appropriate env vars and uncomment the feed section:

  ALPACA options feed:
    ALPACA_API_KEY, ALPACA_API_SECRET — already in your env
    Activate: set OPTIONS_FEED = "alpaca" in env

  Unusual Whales feed:
    UNUSUAL_WHALES_API_KEY — add to Render env vars
    Activate: set OPTIONS_FEED = "unusual_whales" in env

ARCHITECTURE
------------
- Intelligence Layer (14 symbols): full GEX + Market Tide every 5 min
- Russell 1,000: GEX only when signal already detected (lazy evaluation)
- Redis cache: 60-second TTL per symbol (prevents rate limit hits)
- All raw data processed server-side — only proprietary scores exposed

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations

import os
import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("gex_engine")

# ── Feed configuration ────────────────────────────────────────────────────────
OPTIONS_FEED          = os.getenv("OPTIONS_FEED", "placeholder")   # "alpaca" | "unusual_whales" | "placeholder"
ALPACA_API_KEY        = os.getenv("ALPACA_API_KEY", "")
ALPACA_API_SECRET     = os.getenv("ALPACA_API_SECRET", "")
ALPACA_BASE_URL       = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")
UNUSUAL_WHALES_KEY    = os.getenv("UNUSUAL_WHALES_API_KEY", "")
UNUSUAL_WHALES_URL    = "https://api.unusualwhales.com"

# ── Redis cache (reuses existing Redis setup) ─────────────────────────────────
_redis_client = None
try:
    import redis as _redis
    _redis_url = os.getenv("REDIS_URL", "")
    if _redis_url:
        _redis_client = _redis.from_url(_redis_url, decode_responses=True)
except Exception:
    pass

GEX_CACHE_TTL = 60   # seconds


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class GexResult:
    symbol              : str
    net_gex             : float          # Total net GEX across all strikes
    regime              : str            # "POSITIVE" | "NEGATIVE" | "NEUTRAL"
    nearest_wall        : Optional[float] # Nearest positive GEX strike (market maker floor)
    ask_call_premium    : float          # Aggressive call sweep premium ($)
    ask_put_premium     : float          # Aggressive put sweep premium ($)
    iv_rank             : float          # 0-100 IV rank
    sweep_bias          : str            # "BULLISH" | "BEARISH" | "NEUTRAL"
    gex_score           : float          # 0-100 proprietary GEX score
    options_available   : bool           # False if in placeholder mode


@dataclass
class MarketTideResult:
    net_premium_usd     : float          # Aggregate market-wide net premium
    trend               : str            # "RISING" | "FALLING" | "FLAT"
    is_bullish          : bool
    is_bearish          : bool
    tide_score          : float          # 0-100


@dataclass
class GexConfluenceResult:
    symbol              : str
    status              : str            # "SUCCESS" | "REJECTED" | "PLACEHOLDER"
    proprietary_score   : float          # 0-100
    system_tier         : str            # PROP_ALPHA_MAX_CONFLUENCE etc.
    invalidation_level  : Optional[float]
    suggested_strategy  : str
    macro_aligned       : bool
    gex_regime          : str
    sot_signal          : str            # "BULLISH_SOT" | "BEARISH_SOT" | "NONE"
    notes               : List[str]      = field(default_factory=list)


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_get(key: str) -> Optional[dict]:
    if _redis_client:
        try:
            raw = _redis_client.get(key)
            return json.loads(raw) if raw else None
        except Exception:
            pass
    return None


def _cache_set(key: str, data: dict, ttl: int = GEX_CACHE_TTL):
    if _redis_client:
        try:
            _redis_client.setex(key, ttl, json.dumps(data))
        except Exception:
            pass


# ── Options chain fetchers ────────────────────────────────────────────────────

def _fetch_alpaca_options(symbol: str, current_price: float) -> dict:
    """
    Fetches options chain from Alpaca and calculates GEX.
    ACTIVATE: set OPTIONS_FEED=alpaca in Render env vars.
    Requires Alpaca options data subscription.
    """
    import requests as _req
    try:
        r = _req.get(
            f"{ALPACA_BASE_URL}/v1beta1/options/snapshots/{symbol}",
            headers={
                "APCA-API-KEY-ID"    : ALPACA_API_KEY,
                "APCA-API-SECRET-KEY": ALPACA_API_SECRET,
            },
            params={"feed": "opra", "limit": 200},
            timeout=10,
        )
        if r.status_code != 200:
            log.debug(f"Alpaca options {symbol} status {r.status_code}: {r.text[:200]}")
            return {}
        chain = r.json().get("snapshots", {})
        if not chain:
            return {}

        gex_profile = []
        sweeps = []
        total_call_vol = 0
        total_put_vol = 0

        for contract_id, snap in chain.items():
            greeks  = snap.get("greeks", {}) or {}
            quote   = snap.get("latestQuote", {}) or {}
            details = snap.get("details", {}) or {}

            strike   = float(details.get("strike_price", 0) or 0)
            opt_type = details.get("type", "call").lower()
            gamma    = float(greeks.get("gamma", 0) or 0)
            oi       = float(snap.get("openInterest", 0) or 0)
            volume   = float((snap.get("dailyBar", {}) or {}).get("v", 0) or 0)
            ask      = float(quote.get("ap", 0) or 0)
            bid      = float(quote.get("bp", 0) or 0)
            mid      = (ask + bid) / 2 if ask and bid else 0

            if strike > 0 and gamma >= 0:
                gex_profile.append({
                    "strike": strike, "type": opt_type,
                    "gamma": gamma, "open_interest": oi,
                })

            premium = volume * mid * 100
            if opt_type == "call":
                total_call_vol += premium
            else:
                total_put_vol += premium

            if volume > 100 and ask > 0 and mid >= ask * 0.95:
                sweeps.append({
                    "condition": "SWEEP",
                    "position_side": "ASK",
                    "type": opt_type,
                    "premium": premium,
                })

        ivs = [float((chain[c].get("greeks", {}) or {}).get("impliedVolatility", 0) or 0)
               for c in chain if chain[c].get("greeks")]
        iv_rank = _calc_iv_rank([v for v in ivs if v > 0])

        return {
            "gex_profile"              : gex_profile,
            "recent_sweeps"            : sweeps,
            "net_market_gex"           : 0,
            "iv_rank"                  : iv_rank,
            "option_bid_ask_spread_pct": 0.02,
        }
    except Exception as e:
        log.debug(f"Alpaca options fetch error {symbol}: {e}")
        return {}


def _fetch_unusual_whales(symbol: str, current_price: float) -> dict:
    """
    Fetches GEX profile and options flow from Unusual Whales API.
    ACTIVATE: set OPTIONS_FEED=unusual_whales and UNUSUAL_WHALES_API_KEY in Render env.
    """
    # ── PLACEHOLDER — uncomment when Unusual Whales API key is available ──────
    # import requests as _req
    # try:
    #     headers = {
    #         "Authorization": f"Bearer {UNUSUAL_WHALES_KEY}",
    #         "Content-Type": "application/json",
    #     }
    #     # GEX profile
    #     gex_r = _req.get(
    #         f"{UNUSUAL_WHALES_URL}/api/stock/{symbol}/gamma-exposure",
    #         headers=headers, timeout=8
    #     )
    #     gex_data = gex_r.json() if gex_r.status_code == 200 else {}
    #
    #     # Options flow (sweeps)
    #     flow_r = _req.get(
    #         f"{UNUSUAL_WHALES_URL}/api/stock/{symbol}/options-flow",
    #         headers=headers,
    #         params={"min_premium": 100000, "limit": 50},
    #         timeout=8,
    #     )
    #     flow_data = flow_r.json() if flow_r.status_code == 200 else {}
    #
    #     return {
    #         "gex_profile"              : gex_data.get("strikes", []),
    #         "recent_sweeps"            : flow_data.get("data", []),
    #         "net_market_gex"           : gex_data.get("net_gex", 0),
    #         "iv_rank"                  : gex_data.get("iv_rank", 35),
    #         "option_bid_ask_spread_pct": 0.02,
    #     }
    # except Exception as e:
    #     log.debug(f"Unusual Whales fetch error {symbol}: {e}")
    #     return {}
    # ── END PLACEHOLDER ───────────────────────────────────────────────────────
    return {}


def _fetch_market_tide() -> dict:
    """
    Fetches broad market aggregate net premium (SPY/QQQ/IWM).
    This is the Market Tide macro filter.
    ACTIVATE: same feed as OPTIONS_FEED.
    """
    # ── PLACEHOLDER ───────────────────────────────────────────────────────────
    # When options feed is active, sum net call - put premium across
    # SPY, QQQ, IWM options chains to get market-wide tide direction.
    #
    # Unusual Whales endpoint:
    # GET /api/market/tide
    # Returns: { "net_premium_usd": float, "trend": "RISING"|"FALLING"|"FLAT" }
    #
    # Alpaca approach:
    # Fetch SPY + QQQ + IWM chains, sum (call_premium - put_premium)
    # Trend = compare to 5-minute rolling average
    # ── END PLACEHOLDER ───────────────────────────────────────────────────────
    return {"net_market_premium_usd": 0.0, "tide_trend": "FLAT"}


def _calc_iv_rank(iv_values: List[float]) -> float:
    """Calculates IV rank (0-100) from a list of IV values."""
    if not iv_values or len(iv_values) < 2:
        return 35.0
    iv_min = min(iv_values)
    iv_max = max(iv_values)
    current = iv_values[-1]
    if iv_max == iv_min:
        return 50.0
    return round((current - iv_min) / (iv_max - iv_min) * 100, 1)


# ── Core GEX calculation ──────────────────────────────────────────────────────

def _calculate_gex(gex_profile: List[dict], spot_price: float) -> tuple:
    """
    GEX formula: Gamma × OI × 100 × Spot² × 0.01
    Puts = negative GEX (dealers short gamma on puts)
    Returns (net_gex, strike_gex_map, nearest_wall)
    """
    net_gex = 0.0
    strike_map: Dict[float, float] = {}

    for strike in gex_profile:
        s      = float(strike.get("strike", 0))
        gamma  = float(strike.get("gamma", 0))
        oi     = float(strike.get("open_interest", 0))
        s_type = strike.get("type", "call").lower()

        gex_val = gamma * oi * 100 * (spot_price ** 2) * 0.01
        if s_type == "put":
            gex_val *= -1

        net_gex += gex_val
        strike_map[s] = strike_map.get(s, 0.0) + gex_val

    # Find nearest positive GEX wall (market maker support floor)
    positive_strikes = {k: v for k, v in strike_map.items() if v > 0}
    nearest_wall = None
    if positive_strikes:
        nearest_wall = min(positive_strikes, key=lambda k: abs(k - spot_price))

    return net_gex, strike_map, nearest_wall


def _parse_sweeps(sweeps: List[dict]) -> tuple:
    """Returns (ask_call_premium, ask_put_premium)"""
    call_prem = 0.0
    put_prem  = 0.0
    for s in sweeps:
        if s.get("condition") == "SWEEP" and s.get("position_side") == "ASK":
            if s.get("type") == "call":
                call_prem += float(s.get("premium", 0))
            elif s.get("type") == "put":
                put_prem += float(s.get("premium", 0))
    return call_prem, put_prem


# ── Main engine ───────────────────────────────────────────────────────────────

class GexEngine:
    """
    Main GEX + Options Flow + Market Tide confluence engine.
    Runs in placeholder mode until options feed is configured.
    """

    MAX_SPREAD_PCT = 0.05   # Liquidity gate — reject if spread > 5%

    def _fetch_raw(self, symbol: str, price: float) -> dict:
        """Fetches raw options data from configured feed with Redis caching."""
        cache_key = f"gex:{symbol}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

        if OPTIONS_FEED == "alpaca":
            data = _fetch_alpaca_options(symbol, price)
        elif OPTIONS_FEED == "unusual_whales":
            data = _fetch_unusual_whales(symbol, price)
        else:
            data = {}   # placeholder mode

        if data:
            _cache_set(cache_key, data, GEX_CACHE_TTL)
        return data

    def score(self, symbol: str, price: float,
              bars_5m: List[dict],
              is_intelligence_layer: bool = False) -> Dict[str, Any]:
        """
        Main scoring function. Called by confluence_bridge.py.
        Returns proprietary scores only — no raw data exposed.
        """
        notes: List[str] = []

        # Placeholder mode — return neutral until feed configured
        if OPTIONS_FEED == "placeholder":
            return {
                "gex_score"          : 50.0,
                "gex_regime"         : "PLACEHOLDER",
                "gex_wall"           : None,
                "gex_sweep_bias"     : "NEUTRAL",
                "gex_iv_rank"        : 35.0,
                "gex_macro_aligned"  : None,
                "gex_strategy"       : "PENDING_OPTIONS_FEED",
                "gex_invalidation"   : None,
                "gex_system_tier"    : "PENDING_OPTIONS_FEED",
                "gex_sot"            : "NONE",
                "gex_notes"          : ["GEX engine in placeholder mode. Set OPTIONS_FEED env var to activate."],
                "gex_available"      : False,
            }

        # Fetch raw options data (cached)
        raw = self._fetch_raw(symbol, price)
        if not raw:
            return {
                "gex_score": 50.0, "gex_regime": "NO_DATA",
                "gex_available": False,
                "gex_notes": ["Options data unavailable."],
            }

        # Liquidity gate
        spread_pct = raw.get("option_bid_ask_spread_pct", 0.02)
        if spread_pct > self.MAX_SPREAD_PCT:
            return {
                "gex_score": 0, "gex_regime": "REJECTED",
                "gex_available": False,
                "gex_notes": [f"Liquidity gate: spread {spread_pct:.1%} too wide."],
            }

        # GEX calculation
        gex_profile = raw.get("gex_profile", [])
        net_gex, strike_map, nearest_wall = _calculate_gex(gex_profile, price)
        regime = "POSITIVE" if net_gex > 0 else "NEGATIVE" if net_gex < 0 else "NEUTRAL"

        # Sweeps
        sweeps = raw.get("recent_sweeps", [])
        call_prem, put_prem = _parse_sweeps(sweeps)
        sweep_bias = "NEUTRAL"
        if call_prem > put_prem * 2:
            sweep_bias = "BULLISH"
        elif put_prem > call_prem * 2:
            sweep_bias = "BEARISH"

        iv_rank = float(raw.get("iv_rank", 35))

        # SOT detection on 5m bars
        sot = self._detect_sot(bars_5m)

        # Market Tide (Intelligence Layer only to save API calls)
        tide_data = _fetch_market_tide() if is_intelligence_layer else {"net_market_premium_usd": 0, "tide_trend": "FLAT"}
        tide = self._parse_tide(tide_data)

        # Confluence scoring
        result = self._score_confluence(
            symbol, price, sot, net_gex, nearest_wall,
            call_prem, put_prem, iv_rank, tide, bars_5m, notes
        )

        return {
            "gex_score"        : result.proprietary_score,
            "gex_regime"       : result.gex_regime,
            "gex_wall"         : nearest_wall,
            "gex_sweep_bias"   : sweep_bias,
            "gex_iv_rank"      : iv_rank,
            "gex_macro_aligned": result.macro_aligned,
            "gex_strategy"     : result.suggested_strategy,
            "gex_invalidation" : result.invalidation_level,
            "gex_system_tier"  : result.system_tier,
            "gex_sot"          : result.sot_signal,
            "gex_notes"        : result.notes,
            "gex_available"    : True,
        }

    def _detect_sot(self, bars: List[dict]) -> str:
        """Detects SOT pattern from 5m bars."""
        if not bars or len(bars) < 3:
            return "NONE"
        try:
            c1, c2, c3 = bars[-3], bars[-2], bars[-1]
            o1,cl1 = float(c1.get('o',0)), float(c1.get('c',0))
            o2,cl2 = float(c2.get('o',0)), float(c2.get('c',0))
            o3,cl3 = float(c3.get('o',0)), float(c3.get('c',0))
            v2, v3 = float(c2.get('v',0)), float(c3.get('v',0))

            # Bearish SOT
            if cl1>o1 and cl2>o2 and cl3>o3:
                t1, t2 = cl2-cl1, cl3-cl2
                if t1>0 and t2>0 and t2<t1*0.6 and v3>=v2*0.9:
                    return "BEARISH_SOT"

            # Bullish SOT
            if cl1<o1 and cl2<o2 and cl3<o3:
                t1, t2 = cl1-cl2, cl2-cl3
                if t1>0 and t2>0 and t2<t1*0.6 and v3>=v2*0.9:
                    return "BULLISH_SOT"
        except Exception:
            pass
        return "NONE"

    def _parse_tide(self, tide_data: dict) -> MarketTideResult:
        net = float(tide_data.get("net_market_premium_usd", 0))
        trend = tide_data.get("tide_trend", "FLAT")
        return MarketTideResult(
            net_premium_usd = net,
            trend           = trend,
            is_bullish      = net > 10_000_000 and trend == "RISING",
            is_bearish      = net < -10_000_000 and trend == "FALLING",
            tide_score      = min(100, max(0, 50 + net / 1_000_000)),
        )

    def _score_confluence(self, symbol, price, sot, net_gex, nearest_wall,
                          call_prem, put_prem, iv_rank, tide,
                          bars_5m, notes) -> GexConfluenceResult:
        score = 50.0
        regime = "POSITIVE" if net_gex > 0 else "NEGATIVE" if net_gex < 0 else "NEUTRAL"
        strategy = "NO_PLAY"
        invalidation = None
        macro_aligned = False
        tier = "PROP_ALPHA_NEUTRAL"

        if sot == "BULLISH_SOT":
            # Stop-loss: 1 tick below 3-candle low
            if bars_5m and len(bars_5m) >= 3:
                low3 = min(float(b.get('l', price)) for b in bars_5m[-3:])
                invalidation = round(low3 - 0.01, 2)

            score += 10  # SOT technical

            if call_prem > put_prem * 2.0:
                score += 15
                notes.append("GEX: Call sweeps dominating — institutional accumulation.")
            if net_gex > 0:
                score += 10
                notes.append(f"GEX: Positive regime ({net_gex:,.0f}) — market makers buying dips.")
            if nearest_wall and nearest_wall <= price * 1.01:
                score += 5
                notes.append(f"GEX: Market maker wall at {nearest_wall:.2f} — floor confirmed.")
            if tide.is_bullish:
                score += 15
                macro_aligned = True
                notes.append("Market Tide: Macro bullish — broad market tailwind confirmed.")
            else:
                score -= 20
                notes.append("Market Tide: Macro mismatch — penalizing bullish SOT.")

            strategy = "SELL_OTM_CREDIT_PUT_SPREADS" if iv_rank > 65 else "BUY_ITM_LONG_CALLS"

        elif sot == "BEARISH_SOT":
            if bars_5m and len(bars_5m) >= 3:
                high3 = max(float(b.get('h', price)) for b in bars_5m[-3:])
                invalidation = round(high3 + 0.01, 2)

            score += 10

            if put_prem > call_prem * 2.0:
                score += 15
                notes.append("GEX: Put sweeps dominating — institutional distribution.")
            if net_gex < 0:
                score += 10
                notes.append(f"GEX: Negative regime ({net_gex:,.0f}) — volatility accelerating.")
            if tide.is_bearish:
                score += 15
                macro_aligned = True
                notes.append("Market Tide: Macro bearish — broad market headwind confirmed.")
            else:
                score -= 20
                notes.append("Market Tide: Macro mismatch — penalizing bearish SOT.")

            strategy = "SELL_OTM_CREDIT_CALL_SPREADS" if iv_rank > 65 else "BUY_ITM_LONG_PUTS"

        else:
            notes.append("GEX: No SOT pattern detected — baseline GEX scoring only.")
            if net_gex > 0:
                score += 5
            elif net_gex < 0:
                score -= 5

        score = max(0.0, min(100.0, score))

        if score >= 85:
            tier = "PROP_ALPHA_MAX_CONFLUENCE"
        elif score >= 65:
            tier = "PROP_ALPHA_QUALIFIED_ENTRY"
        elif score >= 50:
            tier = "PROP_ALPHA_NEUTRAL"
        else:
            tier = "PROP_ALPHA_LOW_CONFLUENCE"

        return GexConfluenceResult(
            symbol=symbol, status="SUCCESS",
            proprietary_score=round(score, 1),
            system_tier=tier,
            invalidation_level=invalidation,
            suggested_strategy=strategy,
            macro_aligned=macro_aligned,
            gex_regime=regime,
            sot_signal=sot,
            notes=notes,
        )


# ── Module-level singleton ────────────────────────────────────────────────────
_gex_engine = GexEngine()


def score_gex(symbol: str, price: float,
              bars_5m: List[dict],
              is_intelligence_layer: bool = False) -> Dict[str, Any]:
    """Public interface for confluence_bridge.py"""
    try:
        return _gex_engine.score(symbol, price, bars_5m, is_intelligence_layer)
    except Exception as e:
        return {
            "gex_score"    : 50.0,
            "gex_regime"   : "ERROR",
            "gex_available": False,
            "gex_notes"    : [f"GEX engine error: {e}"],
        }

