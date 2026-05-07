"""
Sigmalytic Decision Engine — Shared Core Logic
Used by both the backend (FastAPI) and frontend (Dash).
"""

from __future__ import annotations
import math
import re
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from typing import Literal

Tone = Literal["up", "down", "neutral"]


# ─────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────

@dataclass
class KeyLevels:
    breakout:  float
    prior_high: float
    expansion: float
    confirm:   float
    trigger:   float
    trap:      float
    fail:      float


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
    type:       str
    symbol:     str
    price:      float
    volume:     int
    timestamp:  str
    sequence:   int
    decision:   Decision
    confluence: list[ConfluenceNode]

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class Candle:
    o: float
    h: float
    l: float
    c: float
    t: str = ""   # ISO timestamp, optional


# ─────────────────────────────────────────────
# Pure functions
# ─────────────────────────────────────────────

def sanitize_symbol(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.strip().upper())


def get_key_levels(price: float) -> KeyLevels:
    safe = price if math.isfinite(price) and price > 0 else 1.0
    return KeyLevels(
        breakout=round(safe * 1.030, 4),
        prior_high=round(safe * 1.022, 4),
        expansion=round(safe * 1.015, 4),
        confirm=round(safe, 4),
        trigger=round(safe * 0.992, 4),
        trap=round(safe * 0.985, 4),
        fail=round(safe * 0.970, 4),
    )


def run_decision(price: float, volume_confirm: bool) -> Decision:
    kl = get_key_levels(price)

    if price >= kl.confirm and volume_confirm:
        score = 82
    elif price >= kl.trigger:
        score = 49
    else:
        score = 38

    above_trigger = price >= kl.trigger
    return Decision(
        status="A LONG" if score >= 80 else ("B TACTICAL LONG" if score >= 45 else "STANDDOWN"),
        bias="LONG" if score >= 45 else "NEUTRAL",
        grade="A" if score >= 80 else ("B" if score >= 45 else "C"),
        confidence="HIGH" if score >= 80 else ("MEDIUM" if score >= 45 else "LOW"),
        mode="Expansion Confirmed" if score >= 80 else "Retest / Hold Zone",
        score=score,
        next_action=(
            "Price is above the anchor but below full confirmation; protect failure levels."
            if above_trigger
            else "Wait for reclaim above the trigger anchor."
        ),
        behavior="ABOVE GAP OPEN ANCHOR" if above_trigger else "WAITING / DIGESTION",
    )


def build_confluence_nodes(price: float) -> list[ConfluenceNode]:
    kl = get_key_levels(price)
    above_trigger = price > kl.trigger
    raw = [
        ConfluenceNode("Expansion Node 1", "Expansion Node",  kl.breakout,   63, "up"),
        ConfluenceNode("Liquidity Retest", "Liquidity Retest", kl.prior_high, 60, "up"),
        ConfluenceNode("Expansion Node 2", "Expansion Node",  kl.expansion,  57, "up"),
        ConfluenceNode("Failure Node",     "Failure Node",    kl.fail,       53, "down"),
    ]
    for node in raw:
        bonus = 5 if above_trigger and node.tone == "up" else 0
        node.score = max(35, min(94, node.score + bonus))
    return raw


def create_live_update(
    symbol: str, price: float, volume: int, sequence: int
) -> LiveUpdate:
    decision   = run_decision(price, volume > 1_500_000)
    confluence = build_confluence_nodes(price)
    return LiveUpdate(
        type="LIVE_UPDATE",
        symbol=symbol,
        price=price,
        volume=volume,
        timestamp=datetime.now(timezone.utc).isoformat(),
        sequence=sequence,
        decision=decision,
        confluence=confluence,
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
