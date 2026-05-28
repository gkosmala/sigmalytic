# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Behavioral Memory Engine (BME)
================================================================================
File    : behavioral_memory.py
Version : 1.0.0
Date    : 2026-05-27

PURPOSE
-------
Tracks, stores, and predicts how market participants will react at specific
price levels based on historical behavior patterns.

Asks: "Who is trapped at this price, and what will they do next?"
Rather than: "What is the price doing?"

ARCHITECTURE
------------
Stage 1: K-Means clustering on high-volume historical bars to automatically
         discover institutional memory zones (unsupervised ML)
Stage 2: Rule-based behavioral scoring at discovered levels using:
         - Retail panic detection (price action + volume)
         - Institutional sweep confirmation (from GEX engine when available)
         - Wyckoff phase alignment
         - Weis Wave signal confirmation

Stage 3 (v1.1): LSTM sequence recognition — placeholder architecture included

MEMORY PERSISTENCE
------------------
Memory bank stored in Supabase behavioral_memory table.
Retrained nightly at 20:00 UTC alongside Wyckoff/Gann recalculation.
In-memory cache serves intraday scoring.

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations

import os
import json
import time
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("behavioral_memory")

# ── Configuration ─────────────────────────────────────────────────────────────
N_MEMORY_CLUSTERS    = 5      # Institutional memory zones per symbol
PROXIMITY_THRESHOLD  = 0.005  # 0.5% — price must be within this % of a level
VOLUME_PERCENTILE    = 0.75   # Top 25% volume bars = institutional activity
MIN_BARS_FOR_TRAINING = 20    # Minimum bars needed to train clusters
MEMORY_DECAY_DAYS    = 90     # Levels older than this decay in significance
SCORE_ACCUMULATION   = 35     # Score boost for confirmed accumulation
SCORE_DISTRIBUTION   = 35     # Score boost for confirmed distribution
SCORE_PROXIMITY_ONLY = 10     # Score boost just for being near a memory level

# ── In-memory bank ────────────────────────────────────────────────────────────
_memory_bank: Dict[str, dict] = {}
_bank_lock = threading.Lock()


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class MemoryZone:
    price_level   : float
    zone_type     : str        # "SUPPORT" | "RESISTANCE" | "NEUTRAL"
    strength      : float      # 0-100 based on volume cluster density
    last_tested   : Optional[datetime]
    touch_count   : int        # How many times price has tested this level
    avg_volume    : float      # Average volume at this level


@dataclass
class BehavioralResult:
    symbol              : str
    nearest_level       : Optional[float]
    distance_pct        : float
    detected_regime     : str   # "ACCUMULATION_TRAP" | "DISTRIBUTION_TRAP" | "NEUTRAL" | "NONE"
    behavioral_score    : float # 0-100
    memory_zones        : List[float]
    retail_sentiment    : str   # "PANIC" | "FOMO" | "NEUTRAL"
    institutional_bias  : str   # "BUYING" | "SELLING" | "NEUTRAL"
    notes               : List[str]
    # ── LSTM placeholder (v1.1) ───────────────────────────────────────────────
    lstm_probability    : Optional[float] = None   # PENDING v1.1
    lstm_regime         : Optional[str]   = None   # PENDING v1.1


# ── Stage 1: K-Means clustering ───────────────────────────────────────────────

def train_memory_bank(symbol: str, bars: List[dict]) -> bool:
    """
    Stage 1: Unsupervised K-Means clustering on high-volume historical bars.
    Automatically discovers institutional memory zones.

    bars: List of daily bar dicts with 'c' (close), 'v' (volume), 'h', 'l', 't'
    """
    if not bars or len(bars) < MIN_BARS_FOR_TRAINING:
        return False

    try:
        from sklearn.cluster import KMeans

        closes  = np.array([float(b.get('c', 0)) for b in bars])
        volumes = np.array([float(b.get('v', 0)) for b in bars])
        highs   = np.array([float(b.get('h', 0)) for b in bars])
        lows    = np.array([float(b.get('l', 0)) for b in bars])

        # Filter for high-volume bars (top 25% = institutional presence)
        vol_threshold = np.percentile(volumes, VOLUME_PERCENTILE * 100)
        institutional_mask = volumes >= vol_threshold

        if institutional_mask.sum() < N_MEMORY_CLUSTERS:
            # Fallback: use all bars if not enough high-volume ones
            institutional_mask = np.ones(len(bars), dtype=bool)

        inst_closes  = closes[institutional_mask]
        inst_volumes = volumes[institutional_mask]

        # K-Means clustering to group price levels
        n_clusters = min(N_MEMORY_CLUSTERS, len(inst_closes))
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        kmeans.fit(inst_closes.reshape(-1, 1))

        cluster_centers = np.sort(kmeans.cluster_centers_.flatten())

        # Calculate strength of each cluster (volume density)
        labels      = kmeans.labels_
        zone_data   = []
        current_price = closes[-1]

        for i, center in enumerate(cluster_centers):
            cluster_mask    = labels == i
            cluster_volumes = inst_volumes[cluster_mask]
            cluster_closes  = inst_closes[cluster_mask]

            avg_vol  = float(np.mean(cluster_volumes)) if len(cluster_volumes) > 0 else 0
            strength = min(100.0, float(avg_vol / (np.mean(volumes) + 1e-10) * 50))

            # Classify zone type based on position relative to current price
            if center < current_price * 0.995:
                zone_type = "SUPPORT"
            elif center > current_price * 1.005:
                zone_type = "RESISTANCE"
            else:
                zone_type = "NEUTRAL"

            zone_data.append({
                "price_level" : round(float(center), 2),
                "zone_type"   : zone_type,
                "strength"    : round(strength, 1),
                "avg_volume"  : round(avg_vol, 0),
                "touch_count" : int(cluster_mask.sum()),
            })

        # Also track recent swing highs/lows as memory levels
        recent = bars[-20:] if len(bars) >= 20 else bars
        swing_high = float(max(b.get('h', 0) for b in recent))
        swing_low  = float(min(b.get('l', float('inf')) for b in recent))

        with _bank_lock:
            _memory_bank[symbol.upper()] = {
                "zones"        : zone_data,
                "cluster_centers": [z["price_level"] for z in zone_data],
                "swing_high"   : round(swing_high, 2),
                "swing_low"    : round(swing_low, 2),
                "current_price": round(current_price, 2),
                "trained_at"   : datetime.now(timezone.utc).isoformat(),
                "bar_count"    : len(bars),
            }

        log.debug(f"BME trained {symbol}: {n_clusters} memory zones discovered")
        return True

    except ImportError:
        # scikit-learn not available — use simple percentile fallback
        return _train_simple_fallback(symbol, bars)
    except Exception as e:
        log.debug(f"BME training error {symbol}: {e}")
        return False


def _train_simple_fallback(symbol: str, bars: List[dict]) -> bool:
    """
    Fallback when scikit-learn unavailable.
    Uses high/low/close percentiles to identify memory zones.
    """
    try:
        closes  = [float(b.get('c', 0)) for b in bars]
        volumes = [float(b.get('v', 0)) for b in bars]

        vol_threshold = np.percentile(volumes, 75)
        inst_closes = [c for c, v in zip(closes, volumes) if v >= vol_threshold]

        if not inst_closes:
            inst_closes = closes

        # Simple percentile-based levels
        levels = [
            np.percentile(inst_closes, 10),
            np.percentile(inst_closes, 25),
            np.percentile(inst_closes, 50),
            np.percentile(inst_closes, 75),
            np.percentile(inst_closes, 90),
        ]

        current = closes[-1]
        zones = []
        for level in levels:
            zone_type = "SUPPORT" if level < current * 0.995 else \
                        "RESISTANCE" if level > current * 1.005 else "NEUTRAL"
            zones.append({
                "price_level": round(float(level), 2),
                "zone_type"  : zone_type,
                "strength"   : 50.0,
                "avg_volume" : 0,
                "touch_count": 1,
            })

        with _bank_lock:
            _memory_bank[symbol.upper()] = {
                "zones"          : zones,
                "cluster_centers": [z["price_level"] for z in zones],
                "swing_high"     : round(max(float(b.get('h',0)) for b in bars[-20:]), 2),
                "swing_low"      : round(min(float(b.get('l',999999)) for b in bars[-20:]), 2),
                "current_price"  : round(current, 2),
                "trained_at"     : datetime.now(timezone.utc).isoformat(),
                "bar_count"      : len(bars),
                "method"         : "fallback",
            }
        return True
    except Exception as e:
        log.debug(f"BME fallback error {symbol}: {e}")
        return False


# ── Stage 2: Behavioral scoring ───────────────────────────────────────────────

def _detect_retail_sentiment(bars_5m: List[dict], current_price: float) -> str:
    """
    Detects retail sentiment from recent 5m price action.
    PANIC: Consecutive red bars with accelerating volume
    FOMO : Consecutive green bars with accelerating volume chasing highs
    """
    if not bars_5m or len(bars_5m) < 3:
        return "NEUTRAL"

    try:
        recent = bars_5m[-5:]
        closes  = [float(b.get('c', 0)) for b in recent]
        opens   = [float(b.get('o', 0)) for b in recent]
        volumes = [float(b.get('v', 0)) for b in recent]

        red_bars   = sum(1 for c, o in zip(closes, opens) if c < o)
        green_bars = sum(1 for c, o in zip(closes, opens) if c > o)
        vol_trend  = volumes[-1] > volumes[0] * 1.2 if volumes[0] > 0 else False

        if red_bars >= 3 and vol_trend:
            return "PANIC"
        elif green_bars >= 3 and vol_trend and closes[-1] > closes[0]:
            return "FOMO"
        return "NEUTRAL"
    except Exception:
        return "NEUTRAL"


def evaluate(symbol: str,
             current_price: float,
             bars_5m: List[dict],
             weis_signal: str = "NONE",
             wyckoff_phase: str = "",
             gex_regime: str = "NEUTRAL",
             whale_sweeping: bool = False) -> Dict[str, Any]:
    """
    Main behavioral evaluation function.
    Called by confluence_bridge.py on every symbol scan.

    Returns proprietary behavioral score and detected regime.
    """
    ticker = symbol.upper()
    notes: List[str] = []

    # Check if memory bank has been trained for this symbol
    with _bank_lock:
        memory = _memory_bank.get(ticker)

    if not memory:
        return {
            "bme_score"   : 50.0,
            "bme_regime"  : "NO_MEMORY",
            "bme_level"   : None,
            "bme_distance": None,
            "bme_sentiment": "NEUTRAL",
            "bme_notes"   : ["Behavioral memory not yet trained for this symbol."],
            "bme_zones"   : [],
        }

    cluster_centers = memory.get("cluster_centers", [])
    if not cluster_centers:
        return {
            "bme_score"   : 50.0,
            "bme_regime"  : "NO_ZONES",
            "bme_level"   : None,
            "bme_distance": None,
            "bme_sentiment": "NEUTRAL",
            "bme_notes"   : ["No memory zones available."],
            "bme_zones"   : [],
        }

    # Find nearest memory level
    nearest = min(cluster_centers, key=lambda x: abs(x - current_price))
    distance_pct = abs(current_price - nearest) / nearest if nearest > 0 else 1.0

    # Retail sentiment
    retail_sentiment = _detect_retail_sentiment(bars_5m, current_price)

    # Institutional bias from available signals
    inst_bias = "NEUTRAL"
    if whale_sweeping or gex_regime == "POSITIVE":
        inst_bias = "BUYING"
    elif gex_regime == "NEGATIVE":
        inst_bias = "SELLING"

    # Score calculation
    score = 50.0
    regime = "NONE"

    if distance_pct <= PROXIMITY_THRESHOLD:
        score += SCORE_PROXIMITY_ONLY
        notes.append(f"BME: Price within 0.5% of memory zone ${nearest:.2f}.")

        zones = memory.get("zones", [])
        zone_at_level = next(
            (z for z in zones if abs(z["price_level"] - nearest) < 0.01), None
        )
        zone_type = zone_at_level["zone_type"] if zone_at_level else "NEUTRAL"

        # ── BEHAVIORAL SCENARIO A: INSTITUTIONAL SPRING ───────────────────────
        if zone_type == "SUPPORT":
            if retail_sentiment == "PANIC" and inst_bias == "BUYING":
                score = min(100.0, score + SCORE_ACCUMULATION)
                regime = "ACCUMULATION_TRAP"
                notes.append("BME: Retail panic-selling into institutional support. Spring setup likely.")
            elif retail_sentiment == "PANIC":
                score = min(100.0, score + 15)
                regime = "POTENTIAL_SPRING"
                notes.append("BME: Retail panic at support zone — awaiting institutional confirmation.")
            elif weis_signal in ("SPRING", "SOT_BULLISH", "CLIMAX_SELL"):
                score = min(100.0, score + 20)
                regime = "WEIS_CONFIRMED_SPRING"
                notes.append(f"BME: Weis Wave {weis_signal} at memory support ${nearest:.2f}.")

        # ── BEHAVIORAL SCENARIO B: INSTITUTIONAL UPTHRUST ────────────────────
        elif zone_type == "RESISTANCE":
            if retail_sentiment == "FOMO" and inst_bias == "SELLING":
                score = min(100.0, score + SCORE_DISTRIBUTION)
                regime = "DISTRIBUTION_TRAP"
                notes.append("BME: Retail FOMO-buying into institutional resistance. Upthrust setup likely.")
            elif retail_sentiment == "FOMO":
                score = min(100.0, score + 15)
                regime = "POTENTIAL_UPTHRUST"
                notes.append("BME: Retail FOMO at resistance zone — awaiting institutional confirmation.")
            elif weis_signal in ("UPTHRUST", "SOT_BEARISH", "CLIMAX_BUY"):
                score = min(100.0, score + 20)
                regime = "WEIS_CONFIRMED_UPTHRUST"
                notes.append(f"BME: Weis Wave {weis_signal} at memory resistance ${nearest:.2f}.")

        # Wyckoff phase alignment bonus
        if wyckoff_phase:
            if "accum" in wyckoff_phase.lower() and regime in ("ACCUMULATION_TRAP", "POTENTIAL_SPRING", "WEIS_CONFIRMED_SPRING"):
                score = min(100.0, score + 10)
                notes.append(f"BME: Wyckoff phase '{wyckoff_phase}' aligns with accumulation regime.")
            elif "distrib" in wyckoff_phase.lower() and regime in ("DISTRIBUTION_TRAP", "POTENTIAL_UPTHRUST", "WEIS_CONFIRMED_UPTHRUST"):
                score = min(100.0, score + 10)
                notes.append(f"BME: Wyckoff phase '{wyckoff_phase}' aligns with distribution regime.")

    elif distance_pct <= 0.015:
        # Approaching a memory zone (within 1.5%)
        score += 5
        notes.append(f"BME: Approaching memory zone ${nearest:.2f} ({distance_pct*100:.1f}% away).")
    else:
        notes.append(f"BME: No active memory zone nearby. Nearest: ${nearest:.2f} ({distance_pct*100:.1f}% away).")

    # ── LSTM PLACEHOLDER (v1.1) ────────────────────────────────────────────────
    # When LSTM is implemented, it will evaluate the sequence of bars leading
    # up to the memory level and output a trap probability (0-1).
    # lstm_prob = lstm_model.predict(bars_5m[-20:], nearest, regime)
    # if lstm_prob > 0.75: score = min(100, score + 15)
    # ── END PLACEHOLDER ───────────────────────────────────────────────────────

    return {
        "bme_score"    : round(score, 1),
        "bme_regime"   : regime,
        "bme_level"    : round(nearest, 2),
        "bme_distance" : round(distance_pct * 100, 3),
        "bme_sentiment": retail_sentiment,
        "bme_inst_bias": inst_bias,
        "bme_notes"    : notes,
        "bme_zones"    : cluster_centers,
        "bme_trained"  : memory.get("trained_at", ""),
    }



# ── Supabase Persistence ──────────────────────────────────────────────────────

def _get_supabase():
    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        return None

def save_memory_to_supabase() -> bool:
    """Saves the full in-memory bank to Supabase for restart persistence."""
    try:
        sb = _get_supabase()
        if not sb:
            return False
        with _bank_lock:
            bank_snapshot = dict(_memory_bank)
        if not bank_snapshot:
            return False
        payload = {
            "id":         "bme_bank",
            "data":       json.dumps(bank_snapshot),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count":      len(bank_snapshot),
        }
        sb.table("bme_memory_bank").upsert(payload, on_conflict="id").execute()
        log.info(f"BME saved {len(bank_snapshot)} symbols to Supabase")
        return True
    except Exception as e:
        log.warning(f"BME Supabase save failed: {e}")
        return False

def load_memory_from_supabase() -> int:
    """Loads memory bank from Supabase on startup. Returns symbols loaded."""
    try:
        sb = _get_supabase()
        if not sb:
            return 0
        r = sb.table("bme_memory_bank").select("data,count").eq("id", "bme_bank").single().execute()
        if not r.data:
            return 0
        bank = json.loads(r.data["data"])
        with _bank_lock:
            _memory_bank.update(bank)
        count = len(bank)
        log.info(f"BME loaded {count} symbols from Supabase cache")
        return count
    except Exception as e:
        log.warning(f"BME Supabase load failed (will retrain): {e}")
        return 0

# ── Batch training ────────────────────────────────────────────────────────────

def train_batch(symbol_bars: Dict[str, List[dict]]) -> int:
    """
    Trains memory bank for multiple symbols at once.
    Called on startup and nightly recalculation.
    Returns count of successfully trained symbols.
    Saves to Supabase after training for restart persistence.
    """
    trained = 0
    for symbol, bars in symbol_bars.items():
        if train_memory_bank(symbol, bars):
            trained += 1
    log.info(f"BME batch training complete: {trained}/{len(symbol_bars)} symbols")
    # Persist to Supabase so restarts don't wipe the bank
    if trained > 0:
        save_memory_to_supabase()
    return trained


def get_memory_status() -> Dict[str, Any]:
    """Returns current memory bank status."""
    with _bank_lock:
        return {
            "symbols_trained": len(_memory_bank),
            "symbols"        : list(_memory_bank.keys()),
        }

