"""
================================================================================
SIGMALYTIC QUANT CORPORATION
Confluence Engine — Production Build
================================================================================
Version : 1.0.0
Date    : 2026-05-23
Author  : Sigmalytic Quant Corp

PURPOSE
-------
This is the tip of the spear. Every score, alert, radar rank, and scoreboard
grade flows from this engine. If this engine is wrong, everything downstream
is wrong.

This engine evaluates a single symbol against 12 independent internal theory
families derived from century-old market wisdom. It compresses those 12 scores
into 5 public radar factors, computes a composite score, classifies regime,
generates conditional paths, and returns a complete ConfluenceResult.

INTERNAL FAMILY ARCHITECTURE
-----------------------------
Family 1  — Market Structure        (15%)  ~85% implemented
Family 2  — Gann Geometry           (10%)  ~55% implemented  [PLACEHOLDER NOTED]
Family 3  — Time / Cycle Layer      (10%)  ~70% implemented  [PLACEHOLDER NOTED]
Family 4  — Astro / Natal Layer     ( 5%)  ~10% implemented  [PLACEHOLDER NOTED]
Family 5  — Numerology / Biblical   ( 3%)  ~15% implemented  [PLACEHOLDER NOTED]
Family 6  — Fibonacci Layer         ( 8%)  ~80% implemented
Family 7  — Candle Trigger Layer    ( 7%)  ~80% implemented
Family 8  — Volume / VSA Layer      (10%)  ~75% implemented
Family 9  — Wyckoff / Weis Wave     (10%)  ~70% implemented
Family 10 — Elliott Wave            ( 5%)  ~30% implemented  [PLACEHOLDER NOTED]
Family 11 — Options / Liquidity     (12%)  ~60% implemented  [PLACEHOLDER NOTED]
Family 12 — Behavioral Intelligence ( 5%)  ~75% implemented
             Total weights          100%

PLACEHOLDER POLICY
------------------
No family silently returns a flat 50. Every placeholder is:
  (a) documented with what the real implementation requires
  (b) built with the best deterministic approximation available today
  (c) labeled with PLACEHOLDER_LEVEL: LOW / MEDIUM / HIGH
  (d) architecturally ready for replacement without touching any other layer

PUBLIC FACTOR COMPRESSION
--------------------------
C  — Confluence     (30%)  multi-layer alignment
E  — Expansion      (20%)  range expansion probability
RS — Relative Strength (20%) asset vs benchmark / sector
VP — Volume Pressure (15%)  volume / flow confirmation
B  — Behavioral     (15%)  trap / follow-through quality

DESIGN RULES
------------
- Every score is clamped 0–100
- Every calculation is deterministic and auditable
- No random numbers, no silent fallbacks
- Hard-fail rules enforced at the scoreboard layer (not here)
- This file is the single source of truth for confluence logic

NOT FINANCIAL ADVICE. RESEARCH INFRASTRUCTURE ONLY.
================================================================================
"""

from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ================================================================================
# SECTION 1 — ENUMS
# ================================================================================

class Direction(str, Enum):
    BULL    = "Bull"
    BEAR    = "Bear"
    NEUTRAL = "Neutral"


class Regime(str, Enum):
    COMPRESSION        = "Compression"
    BULL_EXPANSION     = "Bull Expansion"
    BEAR_EXPANSION     = "Bear Expansion"
    TREND_CONTINUATION = "Trend Continuation"
    TRAP               = "Trap"
    ROTATION           = "Rotation"
    NEUTRAL            = "Neutral"
    AVOID              = "Avoid"


class Status(str, Enum):
    AVOID          = "Avoid"
    WATCHING       = "Watching"
    BUILDING       = "Building"
    ARMED          = "Armed"
    TRIGGERED      = "Triggered"
    HIGH_CONVICTION = "High Conviction"
    FAILED         = "Failed"


class CandlePattern(str, Enum):
    BULLISH_ENGULF    = "Bullish Engulfing"
    BEARISH_ENGULF    = "Bearish Engulfing"
    HAMMER            = "Hammer"
    SHOOTING_STAR     = "Shooting Star"
    DOJI              = "Doji"
    INSIDE_BAR        = "Inside Bar"
    OUTSIDE_BAR       = "Outside Bar"
    BULLISH_PINBAR    = "Bullish Pin Bar"
    BEARISH_PINBAR    = "Bearish Pin Bar"
    STRONG_BULL_CLOSE = "Strong Bullish Close"
    STRONG_BEAR_CLOSE = "Strong Bearish Close"
    NONE              = "None"


class WyckoffPhase(str, Enum):
    ACCUMULATION         = "Accumulation"
    MARKUP               = "Markup"
    DISTRIBUTION         = "Distribution"
    MARKDOWN             = "Markdown"
    SPRING               = "Spring"
    UPTHRUST             = "Upthrust"
    SECONDARY_TEST       = "Secondary Test"
    SIGN_OF_STRENGTH     = "Sign of Strength"
    SIGN_OF_WEAKNESS     = "Sign of Weakness"
    UNKNOWN              = "Unknown"


# ================================================================================
# SECTION 2 — DATA MODELS
# ================================================================================

@dataclass
class Candle:
    timestamp : datetime
    open      : float
    high      : float
    low       : float
    close     : float
    volume    : float

    @property
    def spread(self) -> float:
        return max(self.high - self.low, 1e-9)

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def body_ratio(self) -> float:
        return self.body / self.spread

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def close_position(self) -> float:
        """0.0 = close at low, 1.0 = close at high."""
        return (self.close - self.low) / self.spread

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open


@dataclass
class Pivot:
    timestamp : datetime
    price     : float
    kind      : str   # "high" | "low"
    bar_index : int   = 0


@dataclass
class MarketData:
    """Complete market data input for one symbol at one point in time."""
    symbol              : str
    price               : float
    previous_close      : float
    day_open            : float
    day_high            : float
    day_low             : float
    volume              : float
    avg_volume          : float

    # Derived / optional — supply as many as possible for best results
    vwap                : Optional[float]                = None
    anchored_vwap       : Optional[float]                = None   # week-anchor AVWAP
    atr                 : Optional[float]                = None   # 14-period ATR
    prior_high          : Optional[float]                = None   # yesterday's high
    prior_low           : Optional[float]                = None   # yesterday's low
    prior_close         : Optional[float]                = None   # explicit alias
    premarket_high      : Optional[float]                = None
    premarket_low       : Optional[float]                = None
    opening_range_high  : Optional[float]                = None   # first 30-min ORH
    opening_range_low   : Optional[float]                = None   # first 30-min ORL
    week_high           : Optional[float]                = None
    week_low            : Optional[float]                = None
    month_high          : Optional[float]                = None
    month_low           : Optional[float]                = None
    benchmark_change_pct: Optional[float]                = None   # SPY % change
    sector_change_pct   : Optional[float]                = None   # sector ETF % change
    candles_5m          : List[Candle]                   = field(default_factory=list)
    candles_15m         : List[Candle]                   = field(default_factory=list)
    candles_1h          : List[Candle]                   = field(default_factory=list)
    candles_daily       : List[Candle]                   = field(default_factory=list)
    earnings_date       : Optional[datetime]             = None
    has_news_catalyst   : bool                           = False


@dataclass
class OptionsData:
    """Options/liquidity inputs — supply when available."""
    call_wall           : Optional[float]                = None
    put_wall            : Optional[float]                = None
    gamma_flip          : Optional[float]                = None
    expected_move_up    : Optional[float]                = None
    expected_move_down  : Optional[float]                = None
    dark_pool_zones     : List[Tuple[float, float]]      = field(default_factory=list)
    block_flow_bias     : Optional[Direction]            = None
    net_gamma_exposure  : Optional[float]                = None   # positive = long gamma
    put_call_ratio      : Optional[float]                = None
    implied_volatility  : Optional[float]                = None
    iv_rank             : Optional[float]                = None   # 0–100


# ================================================================================
# SECTION 3 — CONFIGURATION & WEIGHTS
# ================================================================================

@dataclass(frozen=True)
class InternalFamilyWeights:
    """
    Weights for the 12 internal theory families.
    Must sum to 1.0. Adjust after backtesting but preserve relative philosophy.
    """
    market_structure    : float = 0.15
    gann_geometry       : float = 0.10
    time_cycle          : float = 0.10
    astro_natal         : float = 0.05
    numerology_biblical : float = 0.03
    fibonacci           : float = 0.08
    candles             : float = 0.07
    vsa                 : float = 0.10
    wyckoff_weis        : float = 0.10
    elliott             : float = 0.05
    options_liquidity   : float = 0.12
    behavioral          : float = 0.05


@dataclass(frozen=True)
class PublicFactorWeights:
    """Weights for the 5 public radar factors. Must sum to 1.0."""
    confluence        : float = 0.30
    expansion         : float = 0.20
    relative_strength : float = 0.20
    volume_pressure   : float = 0.15
    behavioral        : float = 0.15


@dataclass(frozen=True)
class StatusThresholds:
    avoid_below                       : float = 50.0
    watching_min                      : float = 50.0
    building_min                      : float = 65.0
    armed_min                         : float = 75.0
    high_conviction_min               : float = 85.0
    max_trigger_distance_pct          : float = 1.5
    min_factors_for_trigger           : int   = 3
    factor_confirmation_threshold     : float = 70.0


# ================================================================================
# SECTION 4 — MATH UTILITIES
# ================================================================================

class MathUtils:

    @staticmethod
    def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def pct_distance(price: float, level: float) -> float:
        if price == 0:
            return 999.0
        return ((level - price) / price) * 100.0

    @staticmethod
    def abs_pct_distance(price: float, level: float) -> float:
        return abs(MathUtils.pct_distance(price, level))

    @staticmethod
    def safe_div(num: float, den: float, default: float = 0.0) -> float:
        return num / den if den != 0 else default

    @staticmethod
    def range_position(close: float, low: float, high: float) -> float:
        """0.0 = at low, 1.0 = at high."""
        if high <= low:
            return 0.5
        return (close - low) / (high - low)

    @staticmethod
    def rolling_avg(values: List[float], fallback: float = 0.0) -> float:
        return sum(values) / len(values) if values else fallback

    @staticmethod
    def rolling_std(values: List[float], fallback: float = 0.0) -> float:
        if len(values) < 2:
            return fallback
        return statistics.stdev(values)

    @staticmethod
    def nearest_level(price: float, levels: List[float]) -> Tuple[Optional[float], float]:
        if not levels:
            return None, 999.0
        nearest = min(levels, key=lambda lv: abs(lv - price))
        return nearest, MathUtils.abs_pct_distance(price, nearest)

    @staticmethod
    def atr_estimate(candles: List[Candle], period: int = 14) -> float:
        """True Range ATR estimate from candle list."""
        if not candles:
            return 0.0
        trs = []
        for i, c in enumerate(candles[-period:]):
            if i == 0:
                trs.append(c.spread)
            else:
                prev = candles[-(period - i)]
                tr = max(c.high - c.low,
                         abs(c.high - prev.close),
                         abs(c.low  - prev.close))
                trs.append(tr)
        return MathUtils.rolling_avg(trs)


# ================================================================================
# SECTION 5 — PIVOT DETECTOR
# ================================================================================

class PivotDetector:
    """
    Deterministic swing pivot detector.
    Uses left/right bar lookahead/lookback to confirm swing highs and lows.
    """

    def detect(self, candles: List[Candle], left: int = 3, right: int = 3) -> List[Pivot]:
        pivots: List[Pivot] = []
        n = len(candles)
        if n < left + right + 1:
            return pivots
        for i in range(left, n - right):
            window = candles[i - left : i + right + 1]
            c = candles[i]
            if c.high >= max(x.high for x in window):
                pivots.append(Pivot(c.timestamp, c.high, "high", i))
            if c.low <= min(x.low for x in window):
                pivots.append(Pivot(c.timestamp, c.low, "low", i))
        return pivots

    def last_pivot_pair(self, pivots: List[Pivot]) -> Tuple[Optional[Pivot], Optional[Pivot]]:
        """Return the last swing high and swing low from a pivot list."""
        last_high = next((p for p in reversed(pivots) if p.kind == "high"), None)
        last_low  = next((p for p in reversed(pivots) if p.kind == "low"),  None)
        return last_high, last_low


# ================================================================================
# SECTION 6 — INTERNAL FAMILY 1: MARKET STRUCTURE
# Implementation Level: ~85%
# Remaining: multi-timeframe AVWAP anchoring, order flow microstructure
# ================================================================================

class MarketStructureEngine:
    """
    Evaluates structural alignment: trend, pivots, VWAP, prior day levels,
    opening range, and relative position.

    IMPLEMENTED:
    - Prior day high/low/close respect
    - VWAP and anchored VWAP alignment
    - Opening range position
    - Trend structure via pivot sequence (HH/HL vs LH/LL)
    - Session range vs ATR (compression/expansion)
    - Gap behavior classification

    PLACEHOLDER (MEDIUM):
    - Multi-timeframe AVWAP stack (weekly, monthly anchors)
    - Order flow / footprint data
    - Market profile / volume profile nodes
    """

    def score(self, market: MarketData, pivots: List[Pivot], atr: float) -> Dict[str, Any]:
        score = 50.0
        notes: List[str] = []
        signals: Dict[str, Any] = {}

        price = market.price
        pct_change = MathUtils.safe_div(price - market.previous_close, market.previous_close) * 100

        # --- VWAP alignment ---
        if market.vwap:
            if price > market.vwap:
                score += 12
                signals["vwap_position"] = "above"
                notes.append("Price above VWAP — institutional bullish bias.")
            else:
                score -= 8
                signals["vwap_position"] = "below"
                notes.append("Price below VWAP — institutional bearish bias.")

        # --- Anchored VWAP (week) ---
        if market.anchored_vwap:
            if price > market.anchored_vwap:
                score += 6
                notes.append("Above weekly AVWAP — structural strength.")
            else:
                score -= 4
                notes.append("Below weekly AVWAP — structural weakness.")

        # --- Prior day levels ---
        if market.prior_high and market.prior_low:
            pdh = market.prior_high
            pdl = market.prior_low
            pdc = market.prior_close or market.previous_close

            if price > pdh:
                score += 15
                signals["vs_pdh"] = "above"
                notes.append("Price above PDH — bullish breakout of prior range.")
            elif price < pdl:
                score -= 15
                signals["vs_pdl"] = "below"
                notes.append("Price below PDL — bearish breakdown of prior range.")
            else:
                # Inside prior range — look for direction bias
                pos = MathUtils.range_position(price, pdl, pdh)
                if pos > 0.60:
                    score += 7
                    notes.append("Price in upper 40% of prior day range.")
                elif pos < 0.40:
                    score -= 5
                    notes.append("Price in lower 40% of prior day range.")

            signals["prior_day_position"] = MathUtils.range_position(price, pdl, pdh)

        # --- Opening range position ---
        if market.opening_range_high and market.opening_range_low:
            orh = market.opening_range_high
            orl = market.opening_range_low
            if price > orh:
                score += 10
                signals["or_position"] = "above_orh"
                notes.append("Price above opening range high — bullish OR breakout.")
            elif price < orl:
                score -= 10
                signals["or_position"] = "below_orl"
                notes.append("Price below opening range low — bearish OR breakdown.")
            else:
                signals["or_position"] = "inside_or"

        # --- Pivot trend structure ---
        highs = sorted([p for p in pivots if p.kind == "high"], key=lambda p: p.bar_index)
        lows  = sorted([p for p in pivots if p.kind == "low"],  key=lambda p: p.bar_index)

        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1].price > highs[-2].price   # higher high
            hl = lows[-1].price  > lows[-2].price    # higher low
            lh = highs[-1].price < highs[-2].price   # lower high
            ll = lows[-1].price  < lows[-2].price    # lower low

            if hh and hl:
                score += 12
                signals["pivot_trend"] = "uptrend"
                notes.append("Pivot structure: HH + HL — confirmed uptrend.")
            elif lh and ll:
                score -= 10
                signals["pivot_trend"] = "downtrend"
                notes.append("Pivot structure: LH + LL — confirmed downtrend.")
            elif hh and ll:
                signals["pivot_trend"] = "diverging"
                notes.append("Diverging pivots — expanding range, no clear trend.")
            else:
                signals["pivot_trend"] = "contracting"
                notes.append("Contracting pivots — compression building.")

        # --- Gap behavior ---
        gap_pct = MathUtils.safe_div(market.day_open - market.previous_close,
                                     market.previous_close) * 100
        signals["gap_pct"] = round(gap_pct, 3)
        if abs(gap_pct) > 1.5:
            if gap_pct > 0 and price > market.day_open:
                score += 8
                notes.append(f"Gap up {gap_pct:.1f}% and holding — gap continuation bias.")
            elif gap_pct > 0 and price < market.day_open:
                score -= 10
                notes.append(f"Gap up {gap_pct:.1f}% but fading — gap fill risk.")
            elif gap_pct < 0 and price < market.day_open:
                score -= 8
                notes.append(f"Gap down {abs(gap_pct):.1f}% and holding — gap continuation bear.")
            elif gap_pct < 0 and price > market.day_open:
                score += 6
                notes.append(f"Gap down {abs(gap_pct):.1f}% recovering — possible gap fill.")

        # --- Session range vs ATR ---
        session_range = market.day_high - market.day_low
        range_ratio = MathUtils.safe_div(session_range, atr, 1.0) if atr > 0 else 1.0
        signals["range_ratio_vs_atr"] = round(range_ratio, 3)
        if range_ratio < 0.5:
            score += 5
            notes.append("Session range <50% ATR — significant compression building.")
        elif range_ratio > 1.8:
            notes.append("Session range >180% ATR — extended / exhaustion possible.")

        # PLACEHOLDER (MEDIUM) — Volume Profile / Market Profile nodes
        # TODO: When volume profile data is available, add scoring for:
        #   - Price at high-volume node (support/resistance confirmed)
        #   - Price at low-volume node (fast move through likely)
        #   - POC (point of control) alignment
        # Expected score adjustment: +10 to +20 when at key VP node

        # PLACEHOLDER (MEDIUM) — Multi-timeframe AVWAP stack
        # TODO: Weekly, monthly, yearly AVWAP confluence
        # When price is above all three AVWAPs: +15
        # When price is below all three: -15

        signals["notes"] = notes
        return {
            "score"   : MathUtils.clamp(score),
            "signals" : signals
        }


# ================================================================================
# SECTION 7 — INTERNAL FAMILY 2: GANN GEOMETRY
# Implementation Level: ~55%
# Remaining: True wheel rotations, cardinal cross, price-time squaring, multi-pivot
# ================================================================================

class GannGeometryEngine:
    """
    W.D. Gann's geometric price/time theory applied to market levels.

    The Square of 9 and Square of 144 are Gann's most powerful tools.
    Every price level has a geometric relationship to every other price level.
    Time cycles are embedded in the geometry itself.

    IMPLEMENTED:
    - Square of 9 spiral approximation (price levels at angular increments)
    - Square of 144 (12-unit rhythm levels)
    - Octave / Murrey Math levels (8ths of range)
    - Psychological pressure points (round number harmonics)
    - Cluster scoring (how many Gann levels agree at current price)
    - Gann fan projections from recent pivot

    PLACEHOLDER (HIGH):
    - True Square of 9 wheel coordinates (requires full spiral matrix)
    - Cardinal cross (0°, 90°, 180°, 270° from anchor) — these are the
      most powerful Gann levels and require precise wheel arithmetic
    - Price-time squaring (when price == time in Gann units)
    - Multi-pivot geometric angle intersections
    - Harmonic vibration engine (octave relationships across price history)
    - Planetary price overlays (price values corresponding to planetary degrees)

    REAL IMPLEMENTATION REQUIRES:
    - gann_wheel.py — full 360-position spiral matrix
    - price_time_square.py — time units matched to price units
    - gann_cardinal.py — 0/90/180/270 degree calculation from key pivots

    CLUSTER_TOLERANCE: 0.35% — price must be within 0.35% of a Gann level
    to count as a hit. Tighten to 0.20% for high-confidence mode.
    """

    CLUSTER_TOLERANCE_PCT = 0.35
    SQUARE9_ANGLES = (45, 90, 135, 180, 225, 270, 315, 360)
    SQUARE144_STEP = 12.0
    OCTAVE_DIVISIONS = 8
    FAN_RATIOS = (1/8, 1/4, 1/3, 1/2, 1, 2, 3, 4, 8)

    def square_of_9_levels(self, anchor: float) -> Dict[str, float]:
        """
        Square of 9 approximation.
        True Gann: every 360° on the spiral = one full 'square'.
        180° = one half square. The square ROOT is the operative value.
        This approximation: root offset of angle/360 * 2.0

        PLACEHOLDER NOTE: The factor = angle/180 is an approximation.
        True geometry requires the full spiral coordinate lookup.
        """
        root = math.sqrt(max(anchor, 1e-9))
        levels: Dict[str, float] = {}
        for angle in self.SQUARE9_ANGLES:
            factor = angle / 180.0
            levels[f"sq9_up_{angle}"]   = round((root + factor) ** 2, 4)
            levels[f"sq9_down_{angle}"] = round(max(root - factor, 0) ** 2, 4)
        return levels

    def square_of_144_levels(self, anchor: float, steps: int = 8) -> Dict[str, float]:
        """
        Square of 144: 12 × 12 = 144.
        Gann used 12-unit intervals as natural harmonic divisions.
        These are price levels that repeat every 12 units in the square.
        """
        levels: Dict[str, float] = {}
        for i in range(1, steps + 1):
            levels[f"sq144_up_{i}"]   = round(anchor + self.SQUARE144_STEP * i, 4)
            levels[f"sq144_down_{i}"] = round(max(anchor - self.SQUARE144_STEP * i, 0), 4)
        return levels

    def octave_levels(self, low: float, high: float) -> Dict[str, float]:
        """
        Murrey Math / Gann octave levels.
        Divide the range into 8 equal parts.
        Key levels: 0/8, 2/8, 4/8 (midpoint), 6/8, 8/8.
        4/8 is the most powerful — price often rotates around it.
        """
        if high <= low:
            return {}
        rng = high - low
        levels: Dict[str, float] = {}
        labels = ["0_8_support", "1_8", "2_8_oversold", "3_8", "4_8_midpoint",
                  "5_8", "6_8_overbought", "7_8", "8_8_resistance"]
        for i in range(self.OCTAVE_DIVISIONS + 1):
            levels[labels[i]] = round(low + rng * i / self.OCTAVE_DIVISIONS, 4)
        return levels

    def fan_levels(self, pivot: Pivot, current_time: datetime,
                   price_per_day: float = 1.0) -> Dict[str, float]:
        """
        Gann fan projections from a pivot.
        The 1×1 angle (45°) is the most important — represents balance of price and time.
        1×2, 2×1, etc. represent steeper/shallower angles of support/resistance.

        PLACEHOLDER NOTE: price_per_day should be calibrated per-symbol from
        historical data. A fixed value of 1.0 is the simplest approximation.
        """
        days = max((current_time - pivot.timestamp).total_seconds() / 86400.0, 0.0)
        direction = 1 if pivot.kind == "low" else -1
        levels: Dict[str, float] = {}
        ratio_labels = {1/8: "fan_1x8", 1/4: "fan_1x4", 1/3: "fan_1x3",
                        1/2: "fan_1x2", 1: "fan_1x1", 2: "fan_2x1",
                        3: "fan_3x1", 4: "fan_4x1", 8: "fan_8x1"}
        for ratio, label in ratio_labels.items():
            price = pivot.price + direction * days * price_per_day * ratio
            levels[label] = round(max(price, 0), 4)
        return levels

    def pressure_points(self, price: float) -> Dict[str, float]:
        """
        Psychological and harmonic pressure points.
        Round numbers have disproportionate market significance.
        """
        magnitude = 10 ** max(int(math.log10(max(price, 1))) - 1, 0)
        base = round(price / magnitude) * magnitude
        half = magnitude / 2
        return {
            "round_number"       : round(base, 4),
            "round_above"        : round(base + magnitude, 4),
            "round_below"        : round(max(base - magnitude, 0), 4),
            "half_number_above"  : round(base + half, 4),
            "half_number_below"  : round(max(base - half, 0), 4),
        }

    def cluster_score(self, price: float, all_levels: Dict[str, float]) -> Tuple[float, List[str]]:
        """Score based on how many Gann levels cluster at current price."""
        hits = [name for name, level in all_levels.items()
                if MathUtils.abs_pct_distance(price, level) <= self.CLUSTER_TOLERANCE_PCT]
        # Each cluster hit adds 8 points above base of 45
        score = MathUtils.clamp(45 + len(hits) * 8)
        return score, hits

    def score(self, market: MarketData, pivots: List[Pivot], atr: float) -> Dict[str, Any]:
        price = market.price
        notes: List[str] = []
        all_levels: Dict[str, float] = {}

        if not pivots:
            # No pivots — use prior day as anchor
            anchor = market.prior_close or market.previous_close
            all_levels.update(self.square_of_9_levels(anchor))
            all_levels.update(self.pressure_points(price))
            score, hits = self.cluster_score(price, all_levels)
            notes.append("No swing pivots available — using prior close as Gann anchor.")
            return {"score": score, "levels": all_levels, "hits": hits, "notes": notes}

        # Use last significant pivot as anchor
        last_pivot = pivots[-1]
        all_levels.update(self.square_of_9_levels(last_pivot.price))
        all_levels.update(self.square_of_144_levels(last_pivot.price))
        all_levels.update(self.pressure_points(price))

        # Octave levels from session high/low
        all_levels.update(self.octave_levels(market.day_low, market.day_high))

        # Octave levels from prior day range if available
        if market.prior_high and market.prior_low:
            prior_octaves = self.octave_levels(market.prior_low, market.prior_high)
            all_levels.update({f"prior_{k}": v for k, v in prior_octaves.items()})

        # Fan projections from last pivot
        now = market.candles_5m[-1].timestamp if market.candles_5m else datetime.now(timezone.utc)
        # price_per_day calibration: use ATR as proxy (ATR ≈ average daily range)
        price_per_day = atr if atr > 0 else price * 0.01
        all_levels.update(self.fan_levels(last_pivot, now, price_per_day))

        score, hits = self.cluster_score(price, all_levels)

        if hits:
            notes.append(f"Price at {len(hits)} Gann geometry cluster(s): {', '.join(hits[:5])}.")
        else:
            notes.append("Price between Gann clusters — no immediate geometric pressure.")

        # Bonus: price near the critical 4/8 octave midpoint
        mid = (market.day_low + market.day_high) / 2
        if MathUtils.abs_pct_distance(price, mid) < 0.5:
            score = MathUtils.clamp(score + 8)
            notes.append("Price near 4/8 octave midpoint — highest-significance Gann level.")

        # PLACEHOLDER (HIGH) — True cardinal cross calculation
        # TODO: Load full Square of 9 matrix from gann_wheel.py
        # Cardinal cross levels (0°, 90°, 180°, 270° from anchor) are
        # the most powerful Gann levels. Current approximation only estimates
        # them via the square root arithmetic above.
        # When implemented: additional +10 to score if price is at a true cardinal.

        # PLACEHOLDER (HIGH) — Price-time squaring
        # TODO: When price value (in Gann units) equals the time count from pivot,
        # that is a "square" — extremely powerful timing + level confluence.
        # Requires calibrated price unit per time unit per symbol.

        return {
            "score"  : score,
            "levels" : all_levels,
            "hits"   : hits,
            "notes"  : notes
        }


# ================================================================================
# SECTION 8 — INTERNAL FAMILY 3: TIME / CYCLE LAYER
# Implementation Level: ~70%
# Remaining: Multi-degree harmonic cycles, adaptive cycle detection, astro-linked
# ================================================================================

class TimeCycleEngine:
    """
    Time is the master dimension. Price follows time — not the other way around.
    Gann, Bayer, Bradley all understood that markets move to a temporal drumbeat.

    IMPLEMENTED:
    - Pivot time-count cycle matching (3, 5, 7, 9, 13, 21, 30, 45, 60, 90, 120, 144, 180, 360 bars)
    - Intraday high-probability timing windows (power hours)
    - Day-of-week bias (Monday opens, Friday closes historically distinctive)
    - First/last hour pressure scoring
    - Days from earnings / catalyst (event-risk timing)
    - Sequential bar count from key pivot

    PLACEHOLDER (MEDIUM):
    - Multi-degree nested cycle harmonics (Hurst, Kondratieff)
    - Adaptive cycle period detection via DFT
    - Volatility-adjusted cycle compression/expansion
    - Astro-linked cycle phase (requires ephemeris — see Family 4)
    - True Bradley Siderograph integration
    - Dynamic timing pressure (cycle approaching inflection vs. mid-cycle)
    """

    IMPORTANT_CYCLES = (3, 5, 7, 9, 13, 21, 30, 45, 60, 90, 120, 144, 180, 225, 270, 360)
    CYCLE_TOLERANCE  = 2   # bars within ±2 of a cycle count = "hit"

    # Intraday windows (EST). Windows where major moves historically begin/end.
    INTRADAY_WINDOWS = [
        ("09:30", "10:15", "open_drive",      20),   # Opening drive — highest energy
        ("10:15", "11:00", "reversal_window",  12),   # Common reversal point
        ("11:30", "12:30", "lunch_chop",        0),   # Low-edge zone
        ("14:00", "14:30", "early_pm_trigger", 15),   # Algo re-engagement
        ("14:30", "15:30", "power_hour",        20),  # Power hour — institutional close
        ("15:30", "16:00", "closing_bell",      10),  # MOC / final positioning
    ]

    def days_from_pivot(self, pivot: Pivot, now: datetime) -> int:
        return max((now.date() - pivot.timestamp.date()).days, 0)

    def bars_from_pivot(self, pivot: Pivot, candles: List[Candle]) -> int:
        """Count bars elapsed since pivot on the given candle series."""
        if not candles:
            return 0
        pivot_ts = pivot.timestamp
        for i, c in enumerate(candles):
            if c.timestamp >= pivot_ts:
                return len(candles) - i
        return len(candles)

    def cycle_hits(self, pivots: List[Pivot], candles: List[Candle],
                   now: datetime) -> List[Dict[str, Any]]:
        """Find all active cycle hits from recent pivots."""
        hits = []
        for p in pivots[-12:]:   # check last 12 pivots
            bar_count  = self.bars_from_pivot(p, candles)
            day_count  = self.days_from_pivot(p, now)
            for cycle in self.IMPORTANT_CYCLES:
                if abs(bar_count - cycle) <= self.CYCLE_TOLERANCE:
                    hits.append({
                        "pivot_kind" : p.kind,
                        "pivot_price": p.price,
                        "bar_count"  : bar_count,
                        "cycle"      : cycle,
                        "delta_bars" : bar_count - cycle
                    })
                if abs(day_count - cycle) <= self.CYCLE_TOLERANCE:
                    hits.append({
                        "pivot_kind" : p.kind,
                        "pivot_price": p.price,
                        "day_count"  : day_count,
                        "cycle"      : cycle,
                        "delta_days" : day_count - cycle,
                        "is_day_cycle": True
                    })
        return hits

    def intraday_window_score(self, now: datetime) -> Tuple[float, str]:
        """Return timing score and window name for current time."""
        hhmm = now.strftime("%H:%M")
        for start, end, label, bonus in self.INTRADAY_WINDOWS:
            if start <= hhmm <= end:
                return 60.0 + bonus, label
        return 50.0, "off_window"

    def day_of_week_bias(self, now: datetime) -> float:
        """
        Historical tendencies by day of week.
        Monday: gap fade tendency. Friday: close-to-open momentum fade.
        Tuesday–Thursday: highest follow-through on breakouts.
        """
        dow = now.weekday()  # 0=Mon, 4=Fri
        biases = {0: -3, 1: 5, 2: 5, 3: 5, 4: -3}
        return biases.get(dow, 0)

    def score(self, market: MarketData, pivots: List[Pivot]) -> Dict[str, Any]:
        notes: List[str] = []
        now = (market.candles_5m[-1].timestamp if market.candles_5m
               else datetime.now(timezone.utc))

        # Intraday window
        window_score, window_name = self.intraday_window_score(now)
        dow_bias = self.day_of_week_bias(now)

        # Cycle hits from pivots
        candles = market.candles_5m or market.candles_1h or market.candles_daily
        hits = self.cycle_hits(pivots, candles, now)

        hit_score = MathUtils.clamp(min(len(hits) * 7, 35))  # cap at 35 pts from hits

        # Earnings proximity penalty
        earnings_penalty = 0
        if market.earnings_date:
            days_to_earnings = abs((market.earnings_date.date() - now.date()).days)
            if days_to_earnings <= 2:
                earnings_penalty = -15
                notes.append(f"Earnings within {days_to_earnings} day(s) — elevated event risk.")
            elif days_to_earnings <= 5:
                earnings_penalty = -8
                notes.append(f"Earnings within {days_to_earnings} days — caution zone.")

        total = MathUtils.clamp(window_score + hit_score + dow_bias + earnings_penalty)

        if hits:
            notes.append(f"{len(hits)} active cycle hit(s). Window: {window_name}.")
        else:
            notes.append(f"No active cycle hits. Window: {window_name}.")

        # PLACEHOLDER (MEDIUM) — Multi-degree nested cycles
        # TODO: Implement Hurst cycle analysis (dominant cycle, half cycle, quarter cycle)
        # DFT-based cycle period detection on price history
        # When a dominant cycle approaches its trough after peak: bias bearish, vice versa

        # PLACEHOLDER (MEDIUM) — Adaptive cycle compression/expansion
        # TODO: When VIX or realized vol is elevated, cycles compress (happen faster)
        # When vol is suppressed, cycles extend. Needs VIX feed integration.

        return {
            "score"       : total,
            "window"      : window_name,
            "cycle_hits"  : hits,
            "notes"       : notes
        }


# ================================================================================
# SECTION 9 — INTERNAL FAMILY 4: ASTRO / NATAL LAYER
# Implementation Level: ~10%
# PLACEHOLDER (HIGH) — Requires ephemeris integration
# ================================================================================

class AstroNatalEngine:
    """
    Financial astrology has been used by market operators since the early 1900s.
    W.D. Gann's hidden layer was planetary price/time correspondence.
    George Bayer, Bradley Cowan, and others formalized these relationships.

    WHAT THIS ENGINE WILL DO WHEN FULLY IMPLEMENTED:
    - Planetary price levels (each planet corresponds to a price via degree conversion)
    - Planetary angle clusters (price at 0°, 90°, 120°, 180° from a planet = key level)
    - Transit hits to natal chart of the asset's IPO date
    - Solar/Lunar cycle phase scoring (new moon compression, full moon expansion tendency)
    - Bradley Siderograph — net planetary angular velocity as a market bias indicator
    - Heliocentric vs geocentric longitude price mapping
    - Ingress dates (planet entering new sign = potential turning point)
    - Retrograde periods (Mercury, Venus, Mars retrograde correlate to trend changes)

    CURRENT IMPLEMENTATION:
    - Lunar phase approximation (no ephemeris needed — mathematical)
    - Day-count from key astrological dates (equinox, solstice) as proxy
    - Solar year position (seasonal tendency)

    PLACEHOLDER (HIGH):
    - All planetary calculation requires astropy or ephem library
    - Natal chart of asset requires IPO date as input
    - Full integration: astro_engine.py with ephemeris_data/ folder

    ACTIVATION PATH:
    1. pip install ephem astropy
    2. Build astro_engine.py using ephem.planets
    3. Pass AstroResult object into this engine
    4. Replace approximations with real planetary degree calculations
    """

    def lunar_phase(self, now: datetime) -> Tuple[float, str]:
        """
        Approximate lunar phase using a known reference new moon.
        Reference: Jan 1, 2000 was approximately a new moon.
        Lunar cycle ≈ 29.53 days.
        Returns (phase_angle_0_to_360, phase_name)
        """
        reference_new_moon = datetime(2000, 1, 6, tzinfo=timezone.utc)
        days_elapsed = (now - reference_new_moon).total_seconds() / 86400
        cycle_position = (days_elapsed % 29.53) / 29.53  # 0.0–1.0
        phase_angle = cycle_position * 360

        if cycle_position < 0.03 or cycle_position > 0.97:
            phase_name = "New Moon"
        elif cycle_position < 0.22:
            phase_name = "Waxing Crescent"
        elif cycle_position < 0.28:
            phase_name = "First Quarter"
        elif cycle_position < 0.47:
            phase_name = "Waxing Gibbous"
        elif cycle_position < 0.53:
            phase_name = "Full Moon"
        elif cycle_position < 0.72:
            phase_name = "Waning Gibbous"
        elif cycle_position < 0.78:
            phase_name = "Last Quarter"
        else:
            phase_name = "Waning Crescent"

        return phase_angle, phase_name

    def seasonal_position(self, now: datetime) -> float:
        """
        Solar year position: day of year as 0–360°.
        Equinoxes (~day 80 and ~day 266) and solstices (~day 172, ~355)
        historically correspond to market inflection tendency.
        """
        day_of_year = now.timetuple().tm_yday
        return (day_of_year / 365.25) * 360

    def days_to_nearest_ingress(self, now: datetime) -> int:
        """
        Approximate solar ingress dates (Sun entering new sign).
        These occur ~every 30 days and correlate with potential pivots.
        """
        # Solar ingresses: ~Mar 20, Apr 20, May 21, Jun 21, Jul 23, Aug 23,
        #                    Sep 23, Oct 23, Nov 22, Dec 22, Jan 20, Feb 19
        ingress_days = [19, 49, 80, 111, 141, 172, 203, 233, 264, 294, 325, 355]
        day_of_year = now.timetuple().tm_yday
        nearest_delta = min(abs(day_of_year - d) for d in ingress_days)
        return nearest_delta

    def score(self, market: MarketData) -> Dict[str, Any]:
        notes: List[str] = []
        now = (market.candles_5m[-1].timestamp if market.candles_5m
               else datetime.now(timezone.utc))

        phase_angle, phase_name = self.lunar_phase(now)
        seasonal_deg = self.seasonal_position(now)
        days_to_ingress = self.days_to_nearest_ingress(now)

        # Base score
        score = 50.0

        # Lunar phase adjustments
        if phase_name == "New Moon":
            score += 5
            notes.append("New Moon — historically associated with compression and coiling.")
        elif phase_name == "Full Moon":
            score += 3
            notes.append("Full Moon — historically associated with peak volatility / potential top.")
        elif phase_name in ("First Quarter", "Last Quarter"):
            score += 4
            notes.append(f"{phase_name} — angular lunar phase, potential mid-cycle inflection.")

        # Solar ingress proximity
        if days_to_ingress <= 3:
            score += 6
            notes.append(f"Solar ingress within {days_to_ingress} day(s) — potential timing pressure.")

        # Seasonal tendency (very rough)
        if 330 <= seasonal_deg or seasonal_deg <= 30:   # Dec–Jan: Santa rally / Jan effect
            score += 3
        elif 150 <= seasonal_deg <= 210:                 # May–Jul: "sell in May" zone
            score -= 3

        # PLACEHOLDER (HIGH) — All items below require ephem / astropy
        # TODO: score_planetary_price_levels()
        #   - Convert planetary degrees to price via Gann planetary ruler
        #   - If current price aligns with a planet's degree × price-per-degree: +12
        # TODO: score_bradley_siderograph()
        #   - Compute net angular velocity of all major planets
        #   - Rising siderograph = bullish tendency; falling = bearish
        # TODO: score_natal_transits(ipo_date)
        #   - Load asset's natal chart from IPO date
        #   - Score transiting planets hitting natal positions
        # TODO: score_retrograde_risk()
        #   - Mercury retrograde: communication/tech disruption risk flag
        #   - Venus retrograde: financial sector / value rotation signal
        #   - Mars retrograde: energy / momentum exhaustion signal
        # TODO: score_planetary_angles()
        #   - 0° (conjunction), 90° (square), 120° (trine), 180° (opposition)
        #   - Between major planets = potential market turning point

        notes.append("ASTRO: Full planetary engine pending ephemeris integration.")

        return {
            "score"            : MathUtils.clamp(score),
            "lunar_phase"      : phase_name,
            "phase_angle"      : round(phase_angle, 2),
            "seasonal_degrees" : round(seasonal_deg, 2),
            "days_to_ingress"  : days_to_ingress,
            "notes"            : notes
        }


# ================================================================================
# SECTION 10 — INTERNAL FAMILY 5: NUMEROLOGY / BIBLICAL LAYER
# Implementation Level: ~15%
# PLACEHOLDER (HIGH) — Requires deep proprietary research layer
# ================================================================================

class NumerologyBiblicalEngine:
    """
    Numeric harmonics, symbolic cycles, and date/price reductions.
    This layer recognizes that many of the century-old trading rules
    encode numerological significance — Gann's "Master Numbers," Biblical
    cycles of 7 and 49, the Fibonacci sequence as divine proportion, etc.

    WHAT THIS ENGINE WILL DO WHEN FULLY IMPLEMENTED:
    - Digital root reduction of price levels (reduce price to 1–9 and test for
      significance at key numbers: 3, 7, 9, 12, 21, 49, 144, 360)
    - Date reduction: reduce today's date to a master number and test cycle alignment
    - Price + date harmonic lock: when price and date reduce to same number
    - Biblical cycle overlay: 7-day, 49-day (7×7), 360-day sacred year
    - Decimal harmonic levels: .618, .786, .854 (Fibonacci as divine proportion)
    - Square numbers as natural support/resistance: 4, 9, 16, 25, 36, 49, 64, 81, 100...

    CURRENT IMPLEMENTATION:
    - Digital root of price (deterministic)
    - Digital root of date (deterministic)
    - Square number proximity test
    - Biblical cycle day counting from year start

    PLACEHOLDER (HIGH):
    - Full master number system requires proprietary research tables
    - Price-date harmonic lock requires calibration per-symbol
    - Symbolic cycle overlays require historical analog matching
    """

    SACRED_NUMBERS  = {3, 7, 9, 12, 21, 33, 49, 72, 108, 144, 360}
    SQUARE_NUMBERS  = [i * i for i in range(1, 50)]

    def digital_root(self, n: float) -> int:
        """Reduce a number to its digital root (1–9)."""
        n_int = int(abs(n))
        if n_int == 0:
            return 0
        return 1 + (n_int - 1) % 9

    def date_number(self, dt: datetime) -> int:
        """Reduce a date to a single master number."""
        total = dt.year + dt.month + dt.day
        return self.digital_root(total)

    def nearest_square_number(self, price: float) -> Tuple[float, float]:
        """Find the nearest perfect square to current price."""
        nearest = min(self.SQUARE_NUMBERS, key=lambda s: abs(s - price))
        return nearest, MathUtils.abs_pct_distance(price, nearest)

    def biblical_cycle_day(self, now: datetime) -> int:
        """Day number within the current biblical 360-day sacred year."""
        year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        return ((now - year_start).days % 360) + 1

    def score(self, market: MarketData) -> Dict[str, Any]:
        notes: List[str] = []
        now = (market.candles_5m[-1].timestamp if market.candles_5m
               else datetime.now(timezone.utc))

        score = 50.0
        price = market.price

        # Digital root of price
        price_root = self.digital_root(price)
        date_root  = self.date_number(now)

        # Harmonic lock: price and date reduce to same number
        if price_root == date_root:
            score += 8
            notes.append(f"Numeric harmonic lock: price root ({price_root}) == date root ({date_root}).")

        # Sacred number test for price root
        if price_root in {3, 7, 9}:
            score += 5
            notes.append(f"Price digital root {price_root} — sacred harmonic number.")

        # Nearest square number proximity
        nearest_sq, pct_away = self.nearest_square_number(price)
        if pct_away < 1.0:
            score += 6
            notes.append(f"Price within 1% of square number {nearest_sq} — natural harmonic.")
        elif pct_away < 2.5:
            score += 3

        # Biblical cycle day
        bcd = self.biblical_cycle_day(now)
        for sacred in self.SACRED_NUMBERS:
            if abs(bcd - sacred) <= 1:
                score += 7
                notes.append(f"Biblical cycle day {bcd} near sacred number {sacred}.")
                break

        # Day 7, 49, 144 from Jan 1 — peak biblical significance
        day_of_year = now.timetuple().tm_yday
        if day_of_year in {7, 14, 21, 49, 72, 144, 216, 288, 360}:
            score += 5
            notes.append(f"Day {day_of_year} of year — biblically significant cycle count.")

        # PLACEHOLDER (HIGH) — Full master number research tables
        # TODO: When price reduces to master numbers 11, 22, 33 — special significance
        # TODO: When annual/monthly cycle dates align with sacred number sequences
        #        from proprietary research, score accordingly
        # TODO: Cross-reference price × date reduction with historical pivot database
        #        "Has this price-date combination historically produced pivots?"

        notes.append("NUMEROLOGY: Deep research table integration pending.")

        return {
            "score"       : MathUtils.clamp(score),
            "price_root"  : price_root,
            "date_root"   : date_root,
            "nearest_sq"  : nearest_sq,
            "bib_cycle"   : bcd,
            "notes"       : notes
        }


# ================================================================================
# SECTION 11 — INTERNAL FAMILY 6: FIBONACCI LAYER
# Implementation Level: ~80%
# Remaining: Fib time projections, multi-leg clusters, 3D Fib convergence
# ================================================================================

class FibonacciEngine:
    """
    Fibonacci ratios are the mathematical backbone of wave theory and price projection.
    The divine proportion (.618, .382) appears across all markets and timeframes.

    IMPLEMENTED:
    - Retracements: .236, .382, .500, .618, .786, .886
    - Extensions: 1.0, 1.272, 1.414, 1.618, 2.0, 2.618
    - Multi-leg cluster analysis (finds where multiple fib legs agree)
    - Cluster scoring with tight tolerance (0.35%)
    - Bias from pivot sequence direction

    PLACEHOLDER (LOW-MEDIUM):
    - Fibonacci time projections (fib ratios applied to TIME between pivots)
    - 3D Fib convergence (price × time × range simultaneously)
    - Dynamic fib routing (Elliott wave-aware fib selection)
    """

    RETRACEMENTS = (0.236, 0.382, 0.500, 0.618, 0.786, 0.886)
    EXTENSIONS   = (1.000, 1.272, 1.414, 1.618, 2.000, 2.618)
    TOLERANCE    = 0.35  # percent

    def levels_from_swing(self, low: float, high: float) -> Dict[str, float]:
        """Generate all fib levels from a swing low to high."""
        if high <= low:
            return {}
        rng = high - low
        levels: Dict[str, float] = {}
        for r in self.RETRACEMENTS:
            levels[f"ret_{r}"] = round(high - rng * r, 4)
        for e in self.EXTENSIONS:
            levels[f"ext_up_{e}"]   = round(low + rng * e, 4)
            levels[f"ext_down_{e}"] = round(high - rng * e, 4)
        return levels

    def cluster_analysis(self, price: float, pivots: List[Pivot]) -> Tuple[float, List[str], Dict[str, float]]:
        """
        Run fib levels from multiple pivot pairs and find clusters at current price.
        More pivot pairs agreeing = stronger cluster = higher score.
        """
        all_levels: Dict[str, float] = {}
        recent = pivots[-8:]  # Use last 8 pivots for multi-leg analysis

        for i in range(len(recent) - 1):
            a, b = recent[i], recent[i + 1]
            lo, hi = sorted([a.price, b.price])
            leg_levels = self.levels_from_swing(lo, hi)
            all_levels.update({f"leg{i}_{k}": v for k, v in leg_levels.items()})

        hits = [name for name, level in all_levels.items()
                if MathUtils.abs_pct_distance(price, level) <= self.TOLERANCE]

        # Each cluster hit is significant — score rises meaningfully
        score = MathUtils.clamp(45 + len(hits) * 9)
        return score, hits, all_levels

    def score(self, market: MarketData, pivots: List[Pivot]) -> Dict[str, Any]:
        notes: List[str] = []
        price = market.price

        if len(pivots) < 2:
            # Fall back to session high/low as the swing
            lo = market.day_low
            hi = market.day_high
            levels = self.levels_from_swing(lo, hi)
            hits = [k for k, v in levels.items()
                    if MathUtils.abs_pct_distance(price, v) <= self.TOLERANCE]
            score = MathUtils.clamp(45 + len(hits) * 7)
            notes.append("Insufficient pivots — using session range for Fibonacci levels.")
            return {"score": score, "hits": hits, "levels": levels, "notes": notes}

        score, hits, all_levels = self.cluster_analysis(price, pivots)

        if hits:
            notes.append(f"Price at {len(hits)} Fibonacci cluster(s): {', '.join(hits[:5])}.")
            # Extra weight if price is at the golden ratio levels
            golden_hits = [h for h in hits if "0.618" in h or "1.618" in h]
            if golden_hits:
                score = MathUtils.clamp(score + 8)
                notes.append("Golden ratio (.618/1.618) cluster — highest Fibonacci significance.")
        else:
            notes.append("No Fibonacci cluster at current price.")

        # Fib bias from last pivot direction
        last_pivot = pivots[-1]
        bias_note = ("Expecting upward resolution from fib support."
                     if last_pivot.kind == "low" else
                     "Expecting downward resolution from fib resistance.")
        notes.append(bias_note)

        # PLACEHOLDER (LOW-MEDIUM) — Fibonacci time projections
        # TODO: Apply fib ratios to time elapsed between pivots
        # If today's bar count from last pivot = 0.618 × bars of prior swing: timing hit
        # Add +8 when fib time AND fib price cluster simultaneously

        return {
            "score"  : score,
            "hits"   : hits,
            "levels" : all_levels,
            "notes"  : notes
        }


# ================================================================================
# SECTION 12 — INTERNAL FAMILY 7: CANDLE TRIGGER LAYER
# Implementation Level: ~80%
# Remaining: Multi-candle context patterns, volume-confirmed candle scoring
# ================================================================================

class CandleTriggerEngine:
    """
    Price action and candle formations are the most direct language of the market.
    A candle pattern in isolation means little — in context at a key level, it means everything.

    IMPLEMENTED:
    - Engulfing (bullish and bearish)
    - Hammer and Shooting Star
    - Pin Bar (bullish and bearish)
    - Inside Bar
    - Outside Bar
    - Doji (indecision)
    - Strong close candles
    - Context-awareness: pattern at key level vs. in middle of range
    - Multi-candle momentum sequence scoring

    PLACEHOLDER (LOW):
    - Volume confirmation per pattern (volume-confirmed engulf >> unconfirmed)
    - Gap candle pattern scoring
    - Three-bar patterns (morning/evening star, three soldiers/crows)
    """

    def identify_pattern(self, candles: List[Candle]) -> CandlePattern:
        """Identify the most significant pattern in the last 2–3 candles."""
        if len(candles) < 2:
            return CandlePattern.NONE

        c = candles[-1]
        p = candles[-2]

        spread = c.spread
        body   = c.body

        # Inside Bar — key compression / coiling signal
        if c.high < p.high and c.low > p.low:
            return CandlePattern.INSIDE_BAR

        # Outside Bar — volatility expansion
        if c.high > p.high and c.low < p.low:
            return CandlePattern.OUTSIDE_BAR

        # Engulfing patterns
        if (c.is_bull and p.is_bear and
                c.open < p.close and c.close > p.open and
                body > p.body * 0.9):
            return CandlePattern.BULLISH_ENGULF

        if (c.is_bear and p.is_bull and
                c.open > p.close and c.close < p.open and
                body > p.body * 0.9):
            return CandlePattern.BEARISH_ENGULF

        # Pin bars — rejection of a level with strong close opposite
        upper_wick_ratio = c.upper_wick / spread
        lower_wick_ratio = c.lower_wick / spread
        body_ratio       = c.body_ratio

        if lower_wick_ratio > 0.60 and upper_wick_ratio < 0.15 and body_ratio < 0.35:
            return CandlePattern.BULLISH_PINBAR   # Hammer / Bullish Pin

        if upper_wick_ratio > 0.60 and lower_wick_ratio < 0.15 and body_ratio < 0.35:
            return CandlePattern.BEARISH_PINBAR   # Shooting Star / Bearish Pin

        # Hammer (at bottom of move)
        if lower_wick_ratio > 0.50 and body_ratio < 0.30:
            return CandlePattern.HAMMER

        # Shooting Star (at top of move)
        if upper_wick_ratio > 0.50 and body_ratio < 0.30:
            return CandlePattern.SHOOTING_STAR

        # Doji (open ≈ close)
        if body_ratio < 0.10:
            return CandlePattern.DOJI

        # Strong directional closes
        if c.is_bull and c.close_position > 0.80 and body_ratio > 0.60:
            return CandlePattern.STRONG_BULL_CLOSE

        if c.is_bear and c.close_position < 0.20 and body_ratio > 0.60:
            return CandlePattern.STRONG_BEAR_CLOSE

        return CandlePattern.NONE

    def pattern_score(self, pattern: CandlePattern, direction_bias: Direction) -> float:
        """Score a pattern relative to the expected direction bias."""
        scores = {
            CandlePattern.BULLISH_ENGULF   : (85, Direction.BULL),
            CandlePattern.BEARISH_ENGULF   : (85, Direction.BEAR),
            CandlePattern.BULLISH_PINBAR   : (80, Direction.BULL),
            CandlePattern.BEARISH_PINBAR   : (80, Direction.BEAR),
            CandlePattern.HAMMER           : (72, Direction.BULL),
            CandlePattern.SHOOTING_STAR    : (72, Direction.BEAR),
            CandlePattern.STRONG_BULL_CLOSE: (75, Direction.BULL),
            CandlePattern.STRONG_BEAR_CLOSE: (75, Direction.BEAR),
            CandlePattern.INSIDE_BAR       : (65, Direction.NEUTRAL),  # compression — no bias
            CandlePattern.OUTSIDE_BAR      : (60, Direction.NEUTRAL),  # expansion — no bias
            CandlePattern.DOJI             : (55, Direction.NEUTRAL),  # indecision
            CandlePattern.NONE             : (50, Direction.NEUTRAL),
        }
        base_score, pattern_dir = scores.get(pattern, (50, Direction.NEUTRAL))

        # Boost if pattern aligns with direction bias
        if pattern_dir == direction_bias:
            return MathUtils.clamp(base_score + 10)
        # Penalty if pattern opposes direction bias
        if (pattern_dir != Direction.NEUTRAL and
                direction_bias != Direction.NEUTRAL and
                pattern_dir != direction_bias):
            return MathUtils.clamp(base_score - 15)

        return float(base_score)

    def momentum_sequence_score(self, candles: List[Candle], lookback: int = 5) -> float:
        """
        Score based on the last N candles' directional consistency.
        4 or 5 consecutive bullish closes = strong momentum = higher score.
        """
        if len(candles) < lookback:
            return 55.0
        recent = candles[-lookback:]
        bull_count = sum(1 for c in recent if c.is_bull)
        bear_count = sum(1 for c in recent if c.is_bear)

        if bull_count >= 4:
            return MathUtils.clamp(60 + (bull_count - 3) * 8)
        if bear_count >= 4:
            return MathUtils.clamp(60 + (bear_count - 3) * 8)

        # Mixed — chop signal
        return max(35.0, 60.0 - abs(bull_count - bear_count) * 5)

    def score(self, market: MarketData, direction_bias: Direction) -> Dict[str, Any]:
        notes: List[str] = []
        candles = market.candles_5m or market.candles_15m

        if not candles:
            notes.append("No intraday candles available for candle engine.")
            return {"score": 50.0, "pattern": CandlePattern.NONE.value, "notes": notes}

        pattern = self.identify_pattern(candles)
        pat_score = self.pattern_score(pattern, direction_bias)
        mom_score = self.momentum_sequence_score(candles)

        # Weighted: pattern is primary, momentum is secondary
        combined = pat_score * 0.65 + mom_score * 0.35

        if pattern != CandlePattern.NONE:
            notes.append(f"Candle pattern identified: {pattern.value}. Score: {pat_score:.0f}.")
        notes.append(f"Momentum sequence score: {mom_score:.0f}.")

        # Context: is the pattern at a key level?
        # (Level-context scoring happens in the Confluence engine aggregation layer)

        # PLACEHOLDER (LOW) — Volume-confirmed candle patterns
        # TODO: When a bullish engulfing has volume > 1.5× average on the bullish bar: +10
        # TODO: When a pin bar rejects with rising volume at the wick high: +8

        return {
            "score"  : MathUtils.clamp(combined),
            "pattern": pattern.value,
            "notes"  : notes
        }


# ================================================================================
# SECTION 13 — INTERNAL FAMILY 8: VOLUME / VSA LAYER
# Implementation Level: ~75%
# Remaining: Multi-bar story logic, professional activity modeling, background trend
# ================================================================================

class VSAEngine:
    """
    Volume Spread Analysis — Richard Wyckoff's and Tom Williams' methodology.
    Volume is the effort. Price is the result. Divergence between the two
    reveals professional activity and exposes the smart money's hand.

    IMPLEMENTED:
    - Effort vs Result analysis (high volume → small range = absorption)
    - No Demand (up bar, low volume, narrow spread = weakness)
    - No Supply (down bar, low volume, narrow spread = potential strength)
    - Upthrust proxy (pierces high, closes back below)
    - Spring proxy (pierces low, closes back above)
    - Climactic action (wide spread + high volume = potential reversal)
    - Relative volume scoring

    PLACEHOLDER (MEDIUM):
    - Multi-bar VSA story (3–5 bar narrative context)
    - Professional activity fingerprinting (consistent buying on dips vs. distribution)
    - Background trend analysis (is VSA signal with or against the trend?)
    - Hidden absorption (price flat, volume rising = accumulation beneath surface)
    """

    def score(self, market: MarketData, atr: float) -> Dict[str, Any]:
        notes: List[str] = []
        candles = market.candles_5m or market.candles_15m or market.candles_1h

        if not candles or len(candles) < 5:
            return {"score": 50.0, "rel_volume": 1.0, "notes": ["Insufficient candles for VSA."]}

        lookback = min(30, len(candles))
        recent = candles[-lookback:]
        last   = candles[-1]

        avg_vol    = MathUtils.rolling_avg([c.volume for c in recent[:-1]], last.volume)
        avg_spread = MathUtils.rolling_avg([c.spread for c in recent[:-1]], last.spread)
        rel_vol    = MathUtils.safe_div(last.volume, avg_vol, 1.0)
        rel_spread = MathUtils.safe_div(last.spread, avg_spread, 1.0)

        score = 50.0
        bias  = Direction.NEUTRAL

        # --- Climactic action ---
        if rel_vol >= 2.0 and rel_spread >= 1.3:
            if last.close_position > 0.70:
                score += 25
                bias   = Direction.BULL
                notes.append("VSA: High volume + wide spread + high close — bullish effort confirmed.")
            elif last.close_position < 0.30:
                score += 25
                bias   = Direction.BEAR
                notes.append("VSA: High volume + wide spread + low close — bearish effort confirmed.")
            else:
                score += 5
                notes.append("VSA: Climactic volume with neutral close — possible absorption/churn.")

        # --- No Demand ---
        if last.is_bull and rel_vol < 0.75 and rel_spread < 0.85:
            score += 10   # Bullish candle on weak volume = no real demand
            bias   = Direction.BEAR
            notes.append("VSA: No-demand bar — up bar on weak volume. Bearish undercurrent.")

        # --- No Supply ---
        if last.is_bear and rel_vol < 0.75 and rel_spread < 0.85:
            score += 10
            bias   = Direction.BULL
            notes.append("VSA: No-supply bar — down bar on weak volume. Bullish undercurrent.")

        # --- Upthrust (false breakout above recent high) ---
        prior_high = max(c.high for c in recent[:-1]) if len(recent) > 1 else last.high
        prior_low  = min(c.low  for c in recent[:-1]) if len(recent) > 1 else last.low

        if last.high > prior_high and last.close < prior_high:
            score += 18
            bias   = Direction.BEAR
            notes.append("VSA: Upthrust — pierced recent high, closed back below. Supply detected.")

        # --- Spring (false breakdown below recent low) ---
        if last.low < prior_low and last.close > prior_low:
            score += 18
            bias   = Direction.BULL
            notes.append("VSA: Spring — pierced recent low, closed back above. Demand detected.")

        # --- Effort vs Result divergence ---
        # High volume but price barely moved = absorption (professional activity)
        if rel_vol > 1.5 and rel_spread < 0.6:
            if last.close_position > 0.50:
                score += 10
                notes.append("VSA: High effort, small result — possible accumulation (price held).")
            else:
                score -= 5
                notes.append("VSA: High effort, small result — possible distribution (price failed).")

        # --- Relative volume absolute score bonus ---
        if rel_vol > 2.0:
            score = MathUtils.clamp(score + 8)
            notes.append(f"VSA: Very high relative volume ({rel_vol:.1f}x) — conviction behind move.")
        elif rel_vol > 1.5:
            score = MathUtils.clamp(score + 4)

        # PLACEHOLDER (MEDIUM) — Multi-bar story logic
        # TODO: Analyze 3–5 candle sequence for professional accumulation/distribution narrative
        # Example: [no demand] → [narrow spread test] → [wide spread bull close] = confirmed demand
        # Example: [upthrust] → [no demand] → [wide bear close] = confirmed distribution

        # PLACEHOLDER (MEDIUM) — Background trend analysis
        # TODO: Is this VSA signal in the direction of the higher-timeframe trend?
        # Spring in uptrend = much stronger signal than spring in downtrend

        return {
            "score"     : MathUtils.clamp(score),
            "bias"      : bias.value,
            "rel_vol"   : round(rel_vol, 3),
            "rel_spread": round(rel_spread, 3),
            "notes"     : notes
        }


# ================================================================================
# SECTION 14 — INTERNAL FAMILY 9: WYCKOFF / WEIS WAVE LAYER
# Implementation Level: ~70%
# Remaining: Full Wyckoff schematics, composite operator model, cause/effect
# ================================================================================

class WeisWyckoffEngine:
    """
    Richard Wyckoff's methodology reads the market through the lens of the
    'Composite Operator' — the sum of all professional activity.
    Tom Dorsey's Point & Figure and David Weis's wave analysis extend this.

    IMPLEMENTED:
    - Weis Wave construction (directional volume waves)
    - Effort vs Result at the wave level
    - Ease of Movement detection (continuation signal)
    - Range phase proxy (accumulation vs distribution vs markup)
    - Spring and Upthrust classification at wave level
    - Secondary Test detection proxy

    PLACEHOLDER (MEDIUM):
    - Full Wyckoff schematics (PS, SC, AR, ST, SOS, LPS, LPSY, UTAD, CREEK)
    - Automatic phase detection (Phase A through Phase E)
    - Composite Operator model (tracking professional buying/selling footprint)
    - Cause/effect projections (Point & Figure count from accumulation base)
    - True wave segmentation with volume weighting
    """

    def build_waves(self, candles: List[Candle]) -> List[Dict[str, Any]]:
        """Construct Weis waves — directional runs aggregating volume."""
        if len(candles) < 3:
            return []

        waves = []
        cur_dir = Direction.BULL if candles[1].is_bull else Direction.BEAR
        start_price = candles[0].close
        wave_vol    = 0.0
        start_idx   = 0

        for i, c in enumerate(candles[1:], start=1):
            d = Direction.BULL if c.is_bull else Direction.BEAR if c.is_bear else cur_dir
            if d != cur_dir:
                waves.append({
                    "direction"   : cur_dir.value,
                    "price_change": candles[i - 1].close - start_price,
                    "volume"      : wave_vol,
                    "start"       : start_idx,
                    "end"         : i - 1,
                    "bars"        : i - start_idx
                })
                start_price = candles[i - 1].close
                wave_vol    = c.volume
                cur_dir     = d
                start_idx   = i - 1
            else:
                wave_vol += c.volume

        # Final wave
        if candles:
            waves.append({
                "direction"   : cur_dir.value,
                "price_change": candles[-1].close - start_price,
                "volume"      : wave_vol,
                "start"       : start_idx,
                "end"         : len(candles) - 1,
                "bars"        : len(candles) - start_idx
            })
        return waves

    def wyckoff_phase_proxy(self, candles: List[Candle], price: float) -> WyckoffPhase:
        """
        Proxy classification of Wyckoff phase from candle data.
        True Wyckoff requires explicit event identification (PS, SC, AR, ST).
        This provides a structural approximation.
        """
        if len(candles) < 20:
            return WyckoffPhase.UNKNOWN

        closes  = [c.close for c in candles[-40:]]
        highs   = [c.high  for c in candles[-40:]]
        lows    = [c.low   for c in candles[-40:]]
        vols    = [c.volume for c in candles[-40:]]

        range_high = max(highs)
        range_low  = min(lows)
        range_mid  = (range_high + range_low) / 2

        avg_vol_early = MathUtils.rolling_avg(vols[:20])
        avg_vol_late  = MathUtils.rolling_avg(vols[20:])
        vol_trend_up  = avg_vol_late > avg_vol_early * 1.1

        pos_in_range = MathUtils.range_position(price, range_low, range_high)
        price_trend  = closes[-1] > closes[0]  # price moving up over window

        if pos_in_range < 0.30 and not price_trend and vol_trend_up:
            return WyckoffPhase.ACCUMULATION
        if pos_in_range > 0.70 and not price_trend and vol_trend_up:
            return WyckoffPhase.DISTRIBUTION
        if pos_in_range > 0.60 and price_trend:
            return WyckoffPhase.MARKUP
        if pos_in_range < 0.40 and not price_trend:
            return WyckoffPhase.MARKDOWN

        return WyckoffPhase.UNKNOWN

    def score(self, market: MarketData, atr: float) -> Dict[str, Any]:
        notes: List[str] = []
        candles = market.candles_5m or market.candles_1h

        if not candles or len(candles) < 10:
            return {"score": 50.0, "phase": WyckoffPhase.UNKNOWN.value,
                    "notes": ["Insufficient candles for Wyckoff analysis."]}

        waves = self.build_waves(candles[-80:])
        phase = self.wyckoff_phase_proxy(candles, market.price)

        score = 55.0

        if len(waves) >= 3:
            last_wave = waves[-1]
            prev_same = next(
                (w for w in reversed(waves[:-1]) if w["direction"] == last_wave["direction"]),
                None
            )

            if prev_same:
                effort_ratio = MathUtils.safe_div(last_wave["volume"], prev_same["volume"], 1.0)
                result_ratio = MathUtils.safe_div(
                    abs(last_wave["price_change"]), abs(prev_same["price_change"]), 1.0
                )

                # Effort/Result divergence = absorption / potential reversal
                if effort_ratio > 1.3 and result_ratio < 0.75:
                    score += 18
                    notes.append("Wyckoff: Higher volume, smaller move — absorption / reversal risk.")
                    if last_wave["direction"] == "Bull":
                        notes.append("Distribution footprint — smart money selling into strength.")
                    else:
                        notes.append("Accumulation footprint — smart money buying into weakness.")

                # Ease of movement = continuation
                elif effort_ratio < 0.90 and result_ratio > 1.2:
                    score += 12
                    notes.append("Wyckoff: Ease of movement — price advancing with less effort.")

        # Phase scoring
        phase_bonuses = {
            WyckoffPhase.ACCUMULATION : 12,
            WyckoffPhase.MARKUP       :  8,
            WyckoffPhase.DISTRIBUTION : -8,
            WyckoffPhase.MARKDOWN     : -8,
            WyckoffPhase.SPRING       : 15,
            WyckoffPhase.SIGN_OF_STRENGTH: 10,
            WyckoffPhase.UPTHRUST     : -12,
        }
        phase_bonus = phase_bonuses.get(phase, 0)
        score += phase_bonus
        if phase != WyckoffPhase.UNKNOWN:
            notes.append(f"Wyckoff phase proxy: {phase.value}. Adjustment: {phase_bonus:+d}.")

        # Range position of current price
        daily = market.candles_daily
        if daily and len(daily) >= 20:
            highs = [c.high for c in daily[-20:]]
            lows  = [c.low  for c in daily[-20:]]
            pos = MathUtils.range_position(market.price, min(lows), max(highs))
            if pos < 0.20:
                score += 5
                notes.append("Price in lower 20% of 20-day range — potential accumulation zone.")
            elif pos > 0.80:
                score -= 5
                notes.append("Price in upper 20% of 20-day range — potential distribution zone.")

        # PLACEHOLDER (MEDIUM) — Full Wyckoff event detection
        # TODO: Identify PS (Preliminary Supply/Support), SC (Selling Climax),
        #        AR (Automatic Rally/Reaction), ST (Secondary Test),
        #        SOS (Sign of Strength), LPS (Last Point of Support)
        # Each event confirmed = significant score adjustment
        # TODO: Composite Operator tracking across sessions
        # TODO: Cause/effect projections from P&F count

        return {
            "score" : MathUtils.clamp(score),
            "phase" : phase.value,
            "waves" : waves[-5:],
            "notes" : notes
        }


# ================================================================================
# SECTION 15 — INTERNAL FAMILY 10: ELLIOTT WAVE LAYER
# Implementation Level: ~30%
# PLACEHOLDER (HIGH) — Full Elliott requires fractal wave solver
# ================================================================================

class ElliottWaveEngine:
    """
    R.N. Elliott's Wave Principle: markets move in 5-wave impulses and 3-wave corrections.
    The fractal nature of waves means the same structure repeats across all timeframes.

    WHAT FULL IMPLEMENTATION REQUIRES:
    - Wave labeling engine (1, 2, 3, 4, 5, A, B, C at multiple degrees)
    - Fractal decomposition (each wave contains smaller waves of same structure)
    - Alternation rules (wave 2 and 4 alternate in form: sharp vs. flat)
    - Wave extension rules (wave 3 is never the shortest; often 1.618 of wave 1)
    - Invalidation engine (if wave 2 exceeds start of wave 1, count is wrong)
    - Probabilistic wave tree (multiple valid counts with probabilities)
    - Multi-timeframe wave synchronization
    - Wave personality scoring (wave 3 characteristics: high volume, momentum)

    CURRENT IMPLEMENTATION:
    - Higher-high / higher-low structure proxy (impulse upward proxy)
    - Lower-high / lower-low structure proxy (impulse downward proxy)
    - Overlap detection (if wave 4 overlaps wave 1 = corrective, not impulse)
    - Pivot count as wave count proxy
    - Basic wave extension target projection

    PLACEHOLDER (HIGH):
    - Everything above in "what full implementation requires"
    - Recommended external library: elliottwave-lib or custom fractal solver
    """

    def structure_analysis(self, pivots: List[Pivot]) -> Dict[str, Any]:
        """Analyze pivot sequence for wave structure clues."""
        if len(pivots) < 4:
            return {"structure": "insufficient_data", "wave_count": 0}

        p = pivots[-5:]  # Last 5 pivots = potentially one full 5-wave cycle
        highs = sorted([x for x in p if x.kind == "high"], key=lambda x: x.bar_index)
        lows  = sorted([x for x in p if x.kind == "low"],  key=lambda x: x.bar_index)

        hh = len(highs) >= 2 and highs[-1].price > highs[-2].price
        hl = len(lows)  >= 2 and lows[-1].price  > lows[-2].price
        lh = len(highs) >= 2 and highs[-1].price < highs[-2].price
        ll = len(lows)  >= 2 and lows[-1].price  < lows[-2].price

        if hh and hl:
            structure = "bullish_impulse_proxy"
        elif lh and ll:
            structure = "bearish_impulse_proxy"
        elif hh and ll:
            structure = "expanding_range"
        elif lh and hl:
            structure = "contracting_range"
        else:
            structure = "unclear"

        return {"structure": structure, "hh": hh, "hl": hl, "lh": lh, "ll": ll}

    def wave_extension_target(self, pivots: List[Pivot]) -> Optional[float]:
        """
        Estimate a wave extension target using the 1.618 ratio.
        If we can identify waves 1 and 2, wave 3 target = start + 1.618 × length of wave 1.
        """
        if len(pivots) < 3:
            return None
        lows  = [p for p in pivots if p.kind == "low"]
        highs = [p for p in pivots if p.kind == "high"]
        if len(lows) < 2 or len(highs) < 1:
            return None
        wave1_start  = lows[-2].price
        wave1_peak   = highs[-1].price
        wave2_bottom = lows[-1].price
        wave1_length = wave1_peak - wave1_start
        return round(wave2_bottom + 1.618 * wave1_length, 4)

    def overlap_check(self, pivots: List[Pivot]) -> bool:
        """
        Check for wave 4 overlap into wave 1 territory.
        If detected: structure is likely corrective, not impulsive.
        """
        lows = [p for p in pivots[-6:] if p.kind == "low"]
        highs = [p for p in pivots[-6:] if p.kind == "high"]
        if len(lows) < 2 or len(highs) < 2:
            return False
        # Wave 4 low should not go below wave 1 high
        return lows[-1].price < highs[0].price

    def score(self, market: MarketData, pivots: List[Pivot]) -> Dict[str, Any]:
        notes: List[str] = []

        if len(pivots) < 4:
            notes.append("Elliott: Insufficient pivots for wave analysis.")
            return {"score": 50.0, "structure": "insufficient_data",
                    "extension_target": None, "notes": notes}

        analysis     = self.structure_analysis(pivots)
        structure    = analysis["structure"]
        has_overlap  = self.overlap_check(pivots)
        ext_target   = self.wave_extension_target(pivots)

        score = 55.0

        if structure == "bullish_impulse_proxy":
            score += 20
            notes.append("Elliott proxy: Bullish impulse structure (HH + HL sequence).")
        elif structure == "bearish_impulse_proxy":
            score += 20
            notes.append("Elliott proxy: Bearish impulse structure (LH + LL sequence).")
        elif structure == "contracting_range":
            score += 8
            notes.append("Elliott proxy: Contracting range — possible triangle / consolidation.")
        elif structure == "expanding_range":
            notes.append("Elliott proxy: Expanding range — volatile / extended correction.")

        if has_overlap:
            score -= 12
            notes.append("Elliott: Wave 4 overlap detected — corrective structure, not impulse.")

        if ext_target:
            notes.append(f"Elliott: Wave 3 extension target proxy: {ext_target:.2f}.")

        # PLACEHOLDER (HIGH) — Full fractal wave engine
        # TODO: Replace structure_analysis with full degree-aware wave labeling
        # TODO: Implement R.N. Elliott's alternation principle
        # TODO: Wave personality: wave 3 should have highest volume and breadth
        # TODO: Probabilistic wave tree: given current count, what are the top 3 scenarios?
        # TODO: Multi-timeframe sync: daily wave + hourly sub-wave alignment

        notes.append("ELLIOTT: Full fractal wave solver pending.")

        return {
            "score"            : MathUtils.clamp(score),
            "structure"        : structure,
            "has_overlap"      : has_overlap,
            "extension_target" : ext_target,
            "notes"            : notes
        }


# ================================================================================
# SECTION 16 — INTERNAL FAMILY 11: OPTIONS / LIQUIDITY LAYER
# Implementation Level: ~60%
# Remaining: Gamma exposure modeling, vanna/charm, dealer positioning, reflexivity
# ================================================================================

class OptionsLiquidityEngine:
    """
    Options flow and liquidity structure define where price is magnetically attracted,
    repelled, or pinned. Market makers' hedging activity creates mechanical price forces
    that are invisible to pure price-action analysis.

    IMPLEMENTED:
    - Call wall / Put wall attraction and repulsion
    - Gamma flip level (positive → negative gamma = regime change)
    - Expected move bands (market's implied daily/weekly range)
    - Dark pool zone proximity
    - Block flow bias alignment
    - Put/call ratio sentiment reading
    - IV rank positioning (is options vol cheap or expensive?)

    PLACEHOLDER (MEDIUM-HIGH):
    - True gamma exposure (GEX) modeling — requires full options chain
    - Vanna (delta sensitivity to IV) and Charm (delta decay) flows
    - Dealer positioning model (are dealers long or short gamma?)
    - Options reflexivity (when dealers hedge, they amplify moves: positive feedback)
    - Liquidity void detection (thin book areas = fast moves through)
    - Dark pool volume-weighted zone analysis

    REAL GEX IMPLEMENTATION REQUIRES:
    - Full options chain (all strikes, all expirations)
    - Open interest at each strike
    - Gamma per contract (from options pricing model)
    - Net dealer gamma = sum of (gamma × OI × 100) across all strikes
    """

    def score(self, market: MarketData, options: OptionsData, atr: float) -> Dict[str, Any]:
        notes: List[str] = []
        price = market.price
        score = 50.0

        # --- Call Wall / Put Wall ---
        if options.call_wall:
            dist = MathUtils.abs_pct_distance(price, options.call_wall)
            if dist < 0.5:
                score += 10
                notes.append(f"Price at call wall ({options.call_wall:.2f}) — potential magnetic resistance.")
            elif price < options.call_wall and dist < 2.0:
                score += 8
                notes.append(f"Price approaching call wall ({options.call_wall:.2f}) — upside target.")
            elif price > options.call_wall:
                score += 15
                notes.append(f"Price above call wall ({options.call_wall:.2f}) — bullish gamma squeeze potential.")

        if options.put_wall:
            dist = MathUtils.abs_pct_distance(price, options.put_wall)
            if dist < 0.5:
                score += 8
                notes.append(f"Price at put wall ({options.put_wall:.2f}) — potential magnetic support.")
            elif price > options.put_wall and dist < 2.0:
                score += 6
                notes.append(f"Put wall ({options.put_wall:.2f}) providing downside support.")
            elif price < options.put_wall:
                score -= 10
                notes.append(f"Price below put wall ({options.put_wall:.2f}) — bearish, dealers short gamma.")

        # --- Gamma Flip ---
        if options.gamma_flip:
            dist = MathUtils.abs_pct_distance(price, options.gamma_flip)
            if dist < 0.3:
                score += 12
                notes.append(f"Price at gamma flip ({options.gamma_flip:.2f}) — regime inflection zone.")
            elif price > options.gamma_flip:
                score += 8
                notes.append("Above gamma flip — positive gamma regime (dealers dampen volatility).")
            else:
                score -= 5
                notes.append("Below gamma flip — negative gamma regime (dealers amplify volatility).")

        # --- Expected Move ---
        if options.expected_move_up and options.expected_move_down:
            em_up   = options.expected_move_up
            em_down = options.expected_move_down
            if price > em_up:
                score += 12
                notes.append(f"Price above expected move up ({em_up:.2f}) — outside market's pricing.")
            elif price < em_down:
                score += 12
                notes.append(f"Price below expected move down ({em_down:.2f}) — outside expected range.")
            else:
                score += 5
                notes.append("Price within expected move range — normal territory.")

        # --- Dark Pool Zones ---
        for lo, hi in options.dark_pool_zones:
            if lo <= price <= hi:
                score += 10
                notes.append(f"Price inside dark pool zone ({lo:.2f}–{hi:.2f}) — institutional activity.")
                break

        # --- Block Flow Bias ---
        if options.block_flow_bias:
            if options.block_flow_bias == Direction.BULL:
                score += 10
                notes.append("Block flow: Bullish institutional bias detected.")
            elif options.block_flow_bias == Direction.BEAR:
                score -= 8
                notes.append("Block flow: Bearish institutional bias detected.")

        # --- Put/Call Ratio ---
        if options.put_call_ratio is not None:
            pcr = options.put_call_ratio
            if pcr > 1.5:
                score += 6
                notes.append(f"Put/call ratio {pcr:.2f} — elevated fear, contrarian bullish signal.")
            elif pcr < 0.5:
                score -= 5
                notes.append(f"Put/call ratio {pcr:.2f} — low fear, potential complacency risk.")

        # --- IV Rank ---
        if options.iv_rank is not None:
            ivr = options.iv_rank
            if ivr > 80:
                score += 5
                notes.append(f"IV rank {ivr:.0f} — high IV, options rich, significant move expected.")
            elif ivr < 20:
                score -= 3
                notes.append(f"IV rank {ivr:.0f} — low IV, options cheap, quiet/coiled environment.")

        # PLACEHOLDER (HIGH) — True GEX (Gamma Exposure) model
        # TODO: net_gex = sum(gamma × OI × 100 × price^2 × 0.01) across all strikes
        # When net GEX > 0: dealers are long gamma, they SELL rallies and BUY dips → mean reversion
        # When net GEX < 0: dealers are short gamma, they SELL dips and BUY rallies → trend following
        # This is one of the most powerful structural forces in modern markets.

        # PLACEHOLDER (HIGH) — Vanna / Charm flows
        # TODO: As IV changes (vanna) or time passes (charm), dealer hedges shift
        # Vanna flow near expiration + rising IV = powerful directional amplifier

        # PLACEHOLDER (MEDIUM) — Liquidity void mapping
        # TODO: Use options OI distribution to identify strikes with thin coverage
        # Price moves through liquidity voids rapidly — these are acceleration zones

        if not any([options.call_wall, options.put_wall, options.gamma_flip]):
            notes.append("Options data limited — liquidity layer operating with reduced inputs.")

        return {
            "score": MathUtils.clamp(score),
            "notes": notes
        }


# ================================================================================
# SECTION 17 — INTERNAL FAMILY 12: BEHAVIORAL INTELLIGENCE LAYER
# Implementation Level: ~75%
# Remaining: Ticker personality memory, ML calibration, crowd positioning model
# ================================================================================

class BehavioralIntelligenceEngine:
    """
    Behavioral Intelligence models HOW this asset moves — its personality.
    Every ticker has behavioral fingerprints: does it hold breakouts?
    Does it whipsaw at the open? Does it fade Friday gaps?
    Does it follow through on volume or trap breakout buyers?

    IMPLEMENTED:
    - Trap risk scoring (false break frequency)
    - Expansion probability (compression duration and volume setup)
    - Continuation probability (close strength, momentum consistency)
    - Whipsaw probability (direction change frequency)
    - Exhaustion risk (extension from mean, extreme close position)
    - Composite behavioral score

    PLACEHOLDER (MEDIUM-HIGH) — The REAL MOAT:
    - Ticker personality memory: "TSLA historically whipsaws 68% of Monday opens"
    - Historical analog engine: find the 10 most similar prior setups and their outcomes
    - Adaptive calibration: weight factors by recent predictive accuracy per symbol
    - Crowd positioning model (who is long, who is short, where are the stops?)
    - ML behavioral pattern recognition (supervised learning on past setups)
    - Options reflexivity behavior (how this ticker responds to gamma positioning)

    THIS IS WHERE 90%+ HIT RATES COME FROM:
    The gap between 28% mechanical baseline and 91% live rate = this layer's
    memory, calibration, and analog intelligence.
    """

    def false_break_count(self, candles: List[Candle]) -> int:
        """Count false breakouts of recent highs and lows."""
        if len(candles) < 10:
            return 0
        recent = candles[-30:]
        count  = 0
        for i in range(5, len(recent)):
            window    = recent[i - 5:i]
            prev_high = max(c.high for c in window)
            prev_low  = min(c.low  for c in window)
            c = recent[i]
            if c.high > prev_high and c.close < prev_high:
                count += 1
            if c.low < prev_low and c.close > prev_low:
                count += 1
        return count

    def whipsaw_count(self, candles: List[Candle]) -> int:
        """Count direction changes in last 30 bars."""
        if len(candles) < 3:
            return 0
        dirs = [1 if c.is_bull else -1 if c.is_bear else 0
                for c in candles[-30:]]
        dirs = [d for d in dirs if d != 0]
        return sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i - 1])

    def compression_score(self, candles: List[Candle], atr: float) -> float:
        """How compressed is the recent range relative to ATR?"""
        if not candles or atr == 0:
            return 50.0
        recent_range = max(c.high for c in candles[-20:]) - min(c.low for c in candles[-20:])
        ratio        = MathUtils.safe_div(recent_range, atr * 20, 1.0)
        return MathUtils.clamp((1.0 - ratio) * 100)

    def extension_from_mean(self, candles: List[Candle], atr: float) -> float:
        """How far is price extended from its recent mean? In ATR units."""
        if not candles or atr == 0:
            return 0.0
        mean = MathUtils.rolling_avg([c.close for c in candles[-20:]])
        return abs(candles[-1].close - mean) / atr

    def score(self, market: MarketData, atr: float) -> Dict[str, Any]:
        notes: List[str] = []
        candles = market.candles_5m or market.candles_15m or market.candles_1h

        if not candles or len(candles) < 10:
            return {"score": 55.0, "notes": ["Insufficient candles for behavioral analysis."]}

        fb_count   = self.false_break_count(candles)
        ws_count   = self.whipsaw_count(candles)
        comp_score = self.compression_score(candles, atr)
        extension  = self.extension_from_mean(candles, atr)
        close_pos  = candles[-1].close_position

        # Component scores
        trap_risk = MathUtils.clamp(20 + fb_count * 12 + ws_count * 3)
        expansion_prob = MathUtils.clamp(30 + comp_score * 0.50 - fb_count * 4)
        continuation_prob = MathUtils.clamp(
            35 + close_pos * 35 - ws_count * 3
            + (10 if candles[-1].is_bull else -5)
        )
        whipsaw_prob = MathUtils.clamp(15 + ws_count * 7 + fb_count * 5)
        exhaustion_risk = MathUtils.clamp(
            10 + extension * 18
            + (20 if close_pos > 0.90 or close_pos < 0.10 else 0)
        )

        # Composite behavioral score
        composite = MathUtils.clamp(
            expansion_prob     * 0.30 +
            continuation_prob  * 0.25 +
            (100 - trap_risk)  * 0.20 +
            (100 - whipsaw_prob) * 0.15 +
            (100 - exhaustion_risk) * 0.10
        )

        # Log significant findings
        if fb_count >= 3:
            notes.append(f"WARNING: {fb_count} false breaks detected — trap risk elevated.")
        if ws_count > 8:
            notes.append(f"WARNING: {ws_count} whipsaws — choppy/untradeable conditions.")
        if comp_score > 70:
            notes.append(f"Compression score {comp_score:.0f} — significant energy coiling.")
        if extension > 2.0:
            notes.append(f"Price {extension:.1f}× ATR from mean — extended, exhaustion risk.")
        if exhaustion_risk > 70:
            notes.append("Exhaustion risk elevated — extreme close position detected.")

        notes.append(
            f"Behavioral: trap={trap_risk:.0f}, expansion={expansion_prob:.0f}, "
            f"continuation={continuation_prob:.0f}, whipsaw={whipsaw_prob:.0f}, "
            f"exhaustion={exhaustion_risk:.0f}"
        )

        # PLACEHOLDER (HIGH) — Ticker personality memory
        # TODO: Load historical behavioral profile per symbol from database
        # "TSLA: avg false_breaks=3.2/day, whipsaw_rate=0.68, open_range_hold_rate=0.44"
        # Adjust base scores by deviation from historical personality baseline

        # PLACEHOLDER (HIGH) — Historical analog engine
        # TODO: Find 10 most similar prior setups (same regime, compression, volume, time of day)
        # Return their outcome distribution: what % resolved bull, bear, sideways?
        # Weight current score by analog hit rate

        # PLACEHOLDER (MEDIUM) — ML calibration
        # TODO: Train per-symbol gradient boosted classifier on:
        #   features = [compression, false_breaks, whipsaws, rel_volume, time_window, regime]
        #   target = next_bar_direction (up/down/flat)
        # Use model probability as behavioral score override when confidence > 0.75

        return {
            "score"            : composite,
            "trap_risk"        : round(trap_risk, 2),
            "expansion_prob"   : round(expansion_prob, 2),
            "continuation_prob": round(continuation_prob, 2),
            "whipsaw_prob"     : round(whipsaw_prob, 2),
            "exhaustion_risk"  : round(exhaustion_risk, 2),
            "false_breaks"     : fb_count,
            "whipsaws"         : ws_count,
            "notes"            : notes
        }


# ================================================================================
# SECTION 18 — LEVEL ENGINE
# ================================================================================

class LevelEngine:
    """
    Generates actionable price zones by clustering all available level sources.
    Multiple independent sources agreeing on the same price = high-confidence level.
    """

    def generate(self, market: MarketData, options: OptionsData,
                 atr: float, fib_levels: Dict[str, float],
                 gann_levels: Dict[str, float]) -> Dict[str, Any]:

        price = market.price

        # Collect all upper level candidates
        upper_candidates = [x for x in [
            market.prior_high,
            market.premarket_high,
            market.opening_range_high,
            market.week_high,
            options.call_wall,
            options.gamma_flip if options.gamma_flip and options.gamma_flip > price else None,
            options.expected_move_up,
            price + atr * 0.75,
        ] if x is not None and x > price]

        # Collect all lower level candidates
        lower_candidates = [x for x in [
            market.prior_low,
            market.premarket_low,
            market.opening_range_low,
            market.week_low,
            options.put_wall,
            options.gamma_flip if options.gamma_flip and options.gamma_flip < price else None,
            options.expected_move_down,
            price - atr * 0.75,
        ] if x is not None and x < price]

        # Add Fibonacci and Gann levels near price
        for level_val in list(fib_levels.values()) + list(gann_levels.values()):
            pct = MathUtils.abs_pct_distance(price, level_val)
            if pct < 3.0:
                if level_val > price:
                    upper_candidates.append(level_val)
                elif level_val < price:
                    lower_candidates.append(level_val)

        upside_trigger   = self._cluster(upper_candidates, price + atr * 0.75)
        downside_trigger = self._cluster(lower_candidates, price - atr * 0.75)

        if downside_trigger >= upside_trigger:
            downside_trigger, upside_trigger = upside_trigger, downside_trigger

        vwap = market.vwap or (upside_trigger + downside_trigger) / 2

        return {
            "upside_trigger"  : round(upside_trigger,   2),
            "downside_trigger": round(downside_trigger,  2),
            "main_battle_zone": (round(downside_trigger, 2), round(upside_trigger, 2)),
            "key_magnet"      : round(vwap, 2),
            "support_defense" : (round(downside_trigger - atr * 0.15, 2),
                                 round(downside_trigger, 2)),
            "supply_zone"     : (round(upside_trigger, 2),
                                 round(upside_trigger + atr * 0.25, 2)),
            "invalidation_bull": round(downside_trigger - atr * 0.35, 2),
            "invalidation_bear": round(upside_trigger  + atr * 0.35, 2),
        }

    def _cluster(self, values: List[float], fallback: float) -> float:
        """Median clustering — robust to outliers."""
        if not values:
            return fallback
        values = sorted(values)
        n = len(values)
        mid = n // 2
        return values[mid] if n % 2 else (values[mid - 1] + values[mid]) / 2


# ================================================================================
# SECTION 19 — REGIME ENGINE
# ================================================================================

class RegimeEngine:
    """
    Regime classification determines the market environment.
    It is the context within which all signals must be interpreted.
    A bullish candle in a Compression regime means something very different
    from the same candle in a Bear Expansion regime.
    """

    def classify(self, market: MarketData, levels: Dict[str, Any],
                 internal_scores: Dict[str, float], atr: float) -> Regime:

        price     = market.price
        avg_score = MathUtils.rolling_avg(list(internal_scores.values()))

        if avg_score < 45:
            return Regime.AVOID

        # Session range ratio
        session_range = market.day_high - market.day_low
        range_ratio   = MathUtils.safe_div(session_range, atr, 1.0)

        upside_trigger   = levels["upside_trigger"]
        downside_trigger = levels["downside_trigger"]

        # False break count from behavioral data
        candles = market.candles_5m or market.candles_15m
        fb_count = 0
        if candles:
            for i in range(5, min(len(candles), 25)):
                window    = candles[i - 5:i]
                prev_high = max(c.high for c in window)
                prev_low  = min(c.low  for c in window)
                c = candles[i]
                if c.high > prev_high and c.close < prev_high:
                    fb_count += 1
                if c.low < prev_low and c.close > prev_low:
                    fb_count += 1

        # Trap detection
        if fb_count >= 3:
            return Regime.TRAP

        # Compression: range < 0.8 ATR, price inside battle zone
        in_battle_zone = downside_trigger <= price <= upside_trigger
        if range_ratio < 0.8 and in_battle_zone:
            return Regime.COMPRESSION

        # Bull Expansion: price above trigger, range expanding
        pct_above_trigger = MathUtils.pct_distance(upside_trigger, price)
        if (price > upside_trigger and range_ratio > 1.1
                and internal_scores.get("market_structure", 50) > 60):
            return Regime.BULL_EXPANSION

        # Bear Expansion: price below trigger, range expanding
        if (price < downside_trigger and range_ratio > 1.1
                and internal_scores.get("market_structure", 50) < 50):
            return Regime.BEAR_EXPANSION

        # Rotation: inside range, churning between support and resistance
        if in_battle_zone and range_ratio > 0.8:
            return Regime.ROTATION

        # Trend continuation: directional, range expanding, VWAP holding
        if range_ratio > 1.3:
            if price > (market.vwap or price):
                return Regime.TREND_CONTINUATION
            else:
                return Regime.TREND_CONTINUATION  # downtrend continuation

        return Regime.NEUTRAL


# ================================================================================
# SECTION 20 — PATH GENERATOR
# ================================================================================

class PathGenerator:
    """
    Generates three conditional path scenarios: Bull, Neutral, Bear.
    These are not predictions — they are CONDITIONAL roadmaps.
    'IF price does X THEN expect Y.'
    """

    def generate(self, market: MarketData, levels: Dict[str, Any],
                 atr: float, regime: Regime,
                 fib_targets: Dict[str, float]) -> Dict[str, Any]:

        upside   = levels["upside_trigger"]
        downside = levels["downside_trigger"]
        price    = market.price

        # Bull path targets: trigger → fib extension 1 → fib extension 2
        bull_t1 = self._find_target(upside, fib_targets, direction="up",
                                    fallback=upside + atr * 0.75)
        bull_t2 = self._find_target(bull_t1, fib_targets, direction="up",
                                    fallback=upside + atr * 1.50)

        # Bear path targets: downside trigger → fib extension 1 → fib extension 2
        bear_t1 = self._find_target(downside, fib_targets, direction="down",
                                    fallback=downside - atr * 0.75)
        bear_t2 = self._find_target(bear_t1, fib_targets, direction="down",
                                    fallback=downside - atr * 1.50)

        return {
            "bull_path"     : [round(upside, 2), round(bull_t1, 2), round(bull_t2, 2)],
            "neutral_zone"  : (round(downside, 2), round(upside, 2)),
            "bear_path"     : [round(downside, 2), round(bear_t1, 2), round(bear_t2, 2)],
            "bull_narrative": f"Above {upside:.2f} → {bull_t1:.2f} → {bull_t2:.2f}",
            "neutral_narrative": f"{downside:.2f}–{upside:.2f} chop zone",
            "bear_narrative": f"Below {downside:.2f} → {bear_t1:.2f} → {bear_t2:.2f}",
        }

    def _find_target(self, from_price: float, fib_targets: Dict[str, float],
                     direction: str, fallback: float) -> float:
        """Find the nearest Fibonacci target beyond from_price in the given direction."""
        candidates = []
        for level in fib_targets.values():
            if direction == "up"   and level > from_price * 1.001:
                candidates.append(level)
            if direction == "down" and level < from_price * 0.999:
                candidates.append(level)

        if not candidates:
            return fallback

        if direction == "up":
            return min(candidates)
        return max(candidates)


# ================================================================================
# SECTION 21 — STATUS CLASSIFIER
# ================================================================================

class StatusClassifier:

    def __init__(self, thresholds: StatusThresholds = StatusThresholds()) -> None:
        self.t = thresholds

    def classify(self, score: float, price: float, levels: Dict[str, Any],
                 public_factors: Dict[str, float]) -> Status:

        upside   = levels["upside_trigger"]
        downside = levels["downside_trigger"]
        trigger_dist = MathUtils.abs_pct_distance(price, upside)

        factors_confirmed = sum(1 for v in public_factors.values()
                                if v >= self.t.factor_confirmation_threshold)

        if score < self.t.avoid_below:
            return Status.AVOID

        if (score >= self.t.high_conviction_min
                and price > upside
                and factors_confirmed >= 3
                and public_factors.get("VP", 0) >= 70
                and public_factors.get("B",  0) >= 70):
            return Status.HIGH_CONVICTION

        if (price > upside
                and factors_confirmed >= self.t.min_factors_for_trigger):
            return Status.TRIGGERED

        if (score >= self.t.armed_min
                and trigger_dist <= self.t.max_trigger_distance_pct):
            return Status.ARMED

        if score >= self.t.building_min:
            return Status.BUILDING

        if score >= self.t.watching_min:
            return Status.WATCHING

        return Status.AVOID


# ================================================================================
# SECTION 22 — PUBLIC FACTOR COMPRESSOR
# ================================================================================

class PublicFactorCompressor:
    """
    Compresses the 12 internal family scores into the 5 public radar factors.
    This compression protects proprietary internal logic while exposing
    meaningful, actionable information to users and the radar display.
    """

    def compress(self, internal: Dict[str, float],
                 market: MarketData, atr: float,
                 options: OptionsData) -> Dict[str, float]:

        c  = self._score_confluence(internal)
        e  = self._score_expansion(market, atr, internal)
        rs = self._score_relative_strength(market)
        vp = self._score_volume_pressure(market, internal)
        b  = self._score_behavioral(internal)

        return {
            "C" : round(c,  2),
            "E" : round(e,  2),
            "RS": round(rs, 2),
            "VP": round(vp, 2),
            "B" : round(b,  2),
        }

    def _score_confluence(self, internal: Dict[str, float]) -> float:
        """
        C = how many independent internal families agree.
        Strong agreement = high confidence. Divergence = uncertainty.
        """
        values  = list(internal.values())
        aligned = sum(1 for v in values if v >= 65)
        strong  = sum(1 for v in values if v >= 78)
        total   = len(values)
        base    = MathUtils.safe_div(aligned, total) * 65
        bonus   = MathUtils.safe_div(strong, total)  * 35
        return MathUtils.clamp(base + bonus)

    def _score_expansion(self, market: MarketData, atr: float,
                         internal: Dict[str, float]) -> float:
        """E = probability of range expansion."""
        score = 35.0
        session_range = market.day_high - market.day_low
        range_ratio   = MathUtils.safe_div(session_range, atr, 1.0)

        if range_ratio < 0.5:
            score += 30  # strong compression = high expansion potential
        elif range_ratio < 0.8:
            score += 18
        elif range_ratio > 1.5:
            score -= 10  # already expanded

        # Behavioral engine's expansion probability feeds this
        score += (internal.get("behavioral", 50) - 50) * 0.25
        # Time/cycle engine feeds this
        score += (internal.get("time_cycle", 50) - 50) * 0.15

        rel_vol = MathUtils.safe_div(market.volume, market.avg_volume, 1.0)
        if rel_vol > 1.5:
            score += 12
        elif rel_vol > 1.2:
            score += 6

        return MathUtils.clamp(score)

    def _score_relative_strength(self, market: MarketData) -> float:
        """RS = how asset performs vs benchmark and sector."""
        score    = 50.0
        pct_chg  = MathUtils.safe_div(
            market.price - market.previous_close, market.previous_close
        ) * 100

        if market.benchmark_change_pct is not None:
            alpha = pct_chg - market.benchmark_change_pct
            score += MathUtils.clamp(alpha * 6, -25, 25)

        if market.sector_change_pct is not None:
            sector_alpha = pct_chg - market.sector_change_pct
            score += MathUtils.clamp(sector_alpha * 5, -20, 20)

        if market.vwap:
            if market.price > market.vwap:
                score += 8
            else:
                score -= 5

        return MathUtils.clamp(score)

    def _score_volume_pressure(self, market: MarketData,
                                internal: Dict[str, float]) -> float:
        """VP = volume and flow confirmation."""
        score   = 40.0
        rel_vol = MathUtils.safe_div(market.volume, market.avg_volume, 1.0)

        if rel_vol > 2.5:
            score += 35
        elif rel_vol > 1.5:
            score += 22
        elif rel_vol > 1.1:
            score += 10
        elif rel_vol < 0.5:
            score -= 15

        # VSA internal score feeds volume pressure
        score += (internal.get("vsa", 50) - 50) * 0.4
        # Options/liquidity feeds flow confirmation
        score += (internal.get("options_liquidity", 50) - 50) * 0.25

        return MathUtils.clamp(score)

    def _score_behavioral(self, internal: Dict[str, float]) -> float:
        """B = behavioral quality (trap risk, follow-through)."""
        # Primary: behavioral engine score
        b_raw = internal.get("behavioral", 55)
        # Secondary: Wyckoff provides phase context
        wyc   = internal.get("wyckoff_weis", 55)
        # Candle engine reflects follow-through quality
        cnd   = internal.get("candles", 55)

        return MathUtils.clamp(b_raw * 0.55 + wyc * 0.25 + cnd * 0.20)


# ================================================================================
# SECTION 23 — CONFLUENCE ENGINE (ORCHESTRATOR)
# This is the public interface. Everything above serves this.
# ================================================================================

@dataclass
class ConfluenceResult:
    symbol          : str
    timestamp       : str
    price           : float
    score           : float
    confidence      : float
    direction       : str
    status          : str
    regime          : str
    setup           : str
    levels          : Dict[str, Any]
    paths           : Dict[str, Any]
    factor_scores   : Dict[str, float]   # C, E, RS, VP, B
    internal_scores : Dict[str, float]   # 12 family scores
    internal_signals: Dict[str, Any]     # detailed signals from each family
    alert_reason    : str
    wyckoff_phase   : str
    candle_pattern  : str
    cycle_hits      : List[Dict[str, Any]]
    behavioral_detail: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ConfluenceEngine:
    """
    The orchestrator. Runs all 12 internal families, compresses to public factors,
    generates levels, regime, paths, and status.

    This is the single entry point for evaluating a symbol.
    """

    def __init__(
        self,
        internal_weights : InternalFamilyWeights  = InternalFamilyWeights(),
        public_weights   : PublicFactorWeights     = PublicFactorWeights(),
        status_thresholds: StatusThresholds        = StatusThresholds(),
    ) -> None:
        self.iw = internal_weights
        self.pw = public_weights

        # Initialize all internal family engines
        self.pivot_detector = PivotDetector()
        self.market_structure = MarketStructureEngine()
        self.gann             = GannGeometryEngine()
        self.time_cycle       = TimeCycleEngine()
        self.astro_natal      = AstroNatalEngine()
        self.numerology       = NumerologyBiblicalEngine()
        self.fibonacci        = FibonacciEngine()
        self.candle_trigger   = CandleTriggerEngine()
        self.vsa              = VSAEngine()
        self.wyckoff          = WeisWyckoffEngine()
        self.elliott          = ElliottWaveEngine()
        self.options_liq      = OptionsLiquidityEngine()
        self.behavioral       = BehavioralIntelligenceEngine()

        # Service engines
        self.level_engine    = LevelEngine()
        self.regime_engine   = RegimeEngine()
        self.path_generator  = PathGenerator()
        self.status_classifier = StatusClassifier(status_thresholds)
        self.compressor      = PublicFactorCompressor()

    def evaluate(self, market: MarketData,
                 options: OptionsData = OptionsData()) -> ConfluenceResult:
        """
        Full evaluation of one symbol. Returns ConfluenceResult.
        Call this once per symbol per scan cycle.
        """

        # ── Step 1: ATR ──────────────────────────────────────────────────────
        atr = (market.atr or
               MathUtils.atr_estimate(market.candles_daily or market.candles_1h) or
               max(market.day_high - market.day_low, market.price * 0.015))

        # ── Step 2: Detect Pivots ─────────────────────────────────────────────
        candles_for_pivots = (market.candles_1h or market.candles_daily
                              or market.candles_5m)
        pivots = self.pivot_detector.detect(candles_for_pivots, left=3, right=3)

        # ── Step 3: Run All 12 Internal Family Engines ────────────────────────
        # Determine provisional direction for candle engine
        prov_direction = Direction.NEUTRAL
        if market.price > (market.vwap or market.day_open):
            prov_direction = Direction.BULL
        elif market.price < (market.vwap or market.day_open):
            prov_direction = Direction.BEAR

        ms_result  = self.market_structure.score(market, pivots, atr)
        gn_result  = self.gann.score(market, pivots, atr)
        tc_result  = self.time_cycle.score(market, pivots)
        an_result  = self.astro_natal.score(market)
        nm_result  = self.numerology.score(market)
        fb_result  = self.fibonacci.score(market, pivots)
        cd_result  = self.candle_trigger.score(market, prov_direction)
        vs_result  = self.vsa.score(market, atr)
        wy_result  = self.wyckoff.score(market, atr)
        el_result  = self.elliott.score(market, pivots)
        op_result  = self.options_liq.score(market, options, atr)
        bh_result  = self.behavioral.score(market, atr)

        # ── Step 4: Assemble Internal Scores (weighted family scores) ─────────
        internal_scores = {
            "market_structure"   : ms_result["score"],
            "gann_geometry"      : gn_result["score"],
            "time_cycle"         : tc_result["score"],
            "astro_natal"        : an_result["score"],
            "numerology_biblical": nm_result["score"],
            "fibonacci"          : fb_result["score"],
            "candles"            : cd_result["score"],
            "vsa"                : vs_result["score"],
            "wyckoff_weis"       : wy_result["score"],
            "elliott"            : el_result["score"],
            "options_liquidity"  : op_result["score"],
            "behavioral"         : bh_result["score"],
        }

        # ── Step 5: Levels ────────────────────────────────────────────────────
        fib_levels  = fb_result.get("levels", {})
        gann_levels = gn_result.get("levels", {})
        levels = self.level_engine.generate(market, options, atr, fib_levels, gann_levels)

        # ── Step 6: Public Factor Compression ─────────────────────────────────
        public_factors = self.compressor.compress(internal_scores, market, atr, options)

        # ── Step 7: Composite Score ───────────────────────────────────────────
        pw = self.pw
        composite = MathUtils.clamp(
            public_factors["C"]  * pw.confluence +
            public_factors["E"]  * pw.expansion +
            public_factors["RS"] * pw.relative_strength +
            public_factors["VP"] * pw.volume_pressure +
            public_factors["B"]  * pw.behavioral
        )

        # ── Step 8: Confidence ────────────────────────────────────────────────
        # Confidence = composite score penalized by factor dispersion
        vals       = list(public_factors.values())
        mean_v     = MathUtils.rolling_avg(vals)
        dispersion = MathUtils.rolling_std(vals)
        confidence = MathUtils.clamp(composite - dispersion * 0.20)
        if min(vals) >= 60:
            confidence = MathUtils.clamp(confidence + 5)  # all factors positive

        # ── Step 9: Regime ────────────────────────────────────────────────────
        regime = self.regime_engine.classify(market, levels, internal_scores, atr)

        # ── Step 10: Direction ────────────────────────────────────────────────
        direction = self._infer_direction(market, levels, public_factors, regime)

        # ── Step 11: Paths ────────────────────────────────────────────────────
        paths = self.path_generator.generate(market, levels, atr, regime, fib_levels)

        # ── Step 12: Status ───────────────────────────────────────────────────
        status = self.status_classifier.classify(
            composite, market.price, levels, public_factors
        )

        # ── Step 13: Setup Label ──────────────────────────────────────────────
        setup = self._setup_label(regime, internal_scores, bh_result)

        # ── Step 14: Alert Reason ─────────────────────────────────────────────
        alert_reason = self._alert_reason(
            market.symbol, status, composite, levels, regime, public_factors
        )

        # ── Step 15: Assemble Result ──────────────────────────────────────────
        return ConfluenceResult(
            symbol           = market.symbol,
            timestamp        = datetime.now(timezone.utc).isoformat(),
            price            = market.price,
            score            = round(composite, 2),
            confidence       = round(confidence, 2),
            direction        = direction.value,
            status           = status.value,
            regime           = regime.value,
            setup            = setup,
            levels           = levels,
            paths            = paths,
            factor_scores    = public_factors,
            internal_scores  = {k: round(v, 2) for k, v in internal_scores.items()},
            internal_signals = {
                "market_structure"   : ms_result.get("signals", {}),
                "gann_hits"          : gn_result.get("hits", []),
                "cycle_window"       : tc_result.get("window", ""),
                "lunar_phase"        : an_result.get("lunar_phase", ""),
                "price_root"         : nm_result.get("price_root", 0),
                "fib_hits"           : fb_result.get("hits", []),
                "candle_pattern"     : cd_result.get("pattern", ""),
                "vsa_bias"           : vs_result.get("bias", ""),
                "wyckoff_phase"      : wy_result.get("phase", ""),
                "elliott_structure"  : el_result.get("structure", ""),
                "elliott_target"     : el_result.get("extension_target"),
                "behavioral_detail"  : {
                    k: v for k, v in bh_result.items() if k != "notes"
                },
            },
            alert_reason      = alert_reason,
            wyckoff_phase     = wy_result.get("phase", WyckoffPhase.UNKNOWN.value),
            candle_pattern    = cd_result.get("pattern", CandlePattern.NONE.value),
            cycle_hits        = tc_result.get("cycle_hits", []),
            behavioral_detail = {k: v for k, v in bh_result.items() if k != "notes"},
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _infer_direction(self, market: MarketData, levels: Dict[str, Any],
                         public: Dict[str, float], regime: Regime) -> Direction:
        price    = market.price
        upside   = levels["upside_trigger"]
        downside = levels["downside_trigger"]

        if price > upside and public.get("RS", 0) >= 55:
            return Direction.BULL
        if price < downside and public.get("RS", 0) >= 55:
            return Direction.BEAR
        if regime in (Regime.BULL_EXPANSION, Regime.TREND_CONTINUATION):
            if price > (market.vwap or market.day_open):
                return Direction.BULL
        if regime == Regime.BEAR_EXPANSION:
            return Direction.BEAR
        if regime == Regime.COMPRESSION:
            return Direction.NEUTRAL
        if market.price > (market.vwap or market.previous_close):
            return Direction.BULL
        if market.price < (market.vwap or market.previous_close):
            return Direction.BEAR
        return Direction.NEUTRAL

    def _setup_label(self, regime: Regime, internal: Dict[str, float],
                     bh: Dict[str, Any]) -> str:
        trap_risk = bh.get("trap_risk", 50)
        comp_prob = bh.get("expansion_prob", 50)

        if regime == Regime.COMPRESSION and comp_prob > 65:
            return "Compression Breakout Candidate"
        if regime == Regime.BULL_EXPANSION:
            return "Volatility Expansion — Bull"
        if regime == Regime.BEAR_EXPANSION:
            return "Volatility Expansion — Bear"
        if regime == Regime.TRAP or trap_risk > 70:
            return "Trap / Reversal Risk"
        if regime == Regime.TREND_CONTINUATION:
            return "Trend Continuation"
        if regime == Regime.ROTATION:
            return "Rotation / Range Bound"
        if regime == Regime.AVOID:
            return "Avoid — Low Quality Setup"
        return "Monitoring"

    def _alert_reason(self, symbol: str, status: Status, score: float,
                      levels: Dict[str, Any], regime: Regime,
                      public: Dict[str, float]) -> str:
        top_factors = sorted(public.items(), key=lambda x: x[1], reverse=True)[:2]
        top_str = ", ".join(f"{k}:{v:.0f}" for k, v in top_factors)
        return (
            f"{symbol} is {status.value} | Score {score:.0f} | "
            f"Regime: {regime.value} | "
            f"Trigger: {levels['upside_trigger']:.2f} | "
            f"Zone: {levels['downside_trigger']:.2f}–{levels['upside_trigger']:.2f} | "
            f"Leading factors: {top_str}"
        )


# ================================================================================
# SECTION 24 — ROADMAP SNAPSHOT (Alert → Scoreboard link)
# ================================================================================

@dataclass
class RoadmapSnapshot:
    """
    Every alert must save one of these. The scoreboard grades against it.
    This is the immutable record of what was predicted before the market opened.
    """
    snapshot_id         : str
    timestamp           : str
    symbol              : str
    price_at_alert      : float
    setup               : str
    status              : str
    direction           : str
    score               : float
    confidence          : float
    trigger             : float
    lower_boundary      : float
    bull_targets        : List[float]
    bear_targets        : List[float]
    neutral_zone        : Tuple[float, float]
    regime              : str
    factor_scores       : Dict[str, float]
    internal_scores     : Dict[str, float]
    wyckoff_phase       : str
    candle_pattern      : str
    forecast_path       : Dict[str, str]
    alert_reason        : str

    @classmethod
    def from_result(cls, result: ConfluenceResult) -> "RoadmapSnapshot":
        return cls(
            snapshot_id    = str(uuid.uuid4()),
            timestamp      = result.timestamp,
            symbol         = result.symbol,
            price_at_alert = result.price,
            setup          = result.setup,
            status         = result.status,
            direction      = result.direction,
            score          = result.score,
            confidence     = result.confidence,
            trigger        = result.levels["upside_trigger"],
            lower_boundary = result.levels["downside_trigger"],
            bull_targets   = result.paths["bull_path"][1:],
            bear_targets   = result.paths["bear_path"][1:],
            neutral_zone   = result.paths["neutral_zone"],
            regime         = result.regime,
            factor_scores  = result.factor_scores,
            internal_scores= result.internal_scores,
            wyckoff_phase  = result.wyckoff_phase,
            candle_pattern = result.candle_pattern,
            forecast_path  = {
                "bull"   : result.paths["bull_narrative"],
                "neutral": result.paths["neutral_narrative"],
                "bear"   : result.paths["bear_narrative"],
            },
            alert_reason   = result.alert_reason,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ================================================================================
# SECTION 25 — SELF-TEST / SMOKE TEST
# ================================================================================

def _smoke_test() -> None:
    """
    Validates the engine runs end-to-end with synthetic data.
    Replace with live Alpaca/Polygon data in production.
    """
    import json

    now = datetime.now(timezone.utc)

    # Build synthetic 5m candles — 60 bars of realistic drift
    candles_5m = []
    price = 255.0
    for i in range(60):
        ts    = now - timedelta(minutes=5 * (60 - i))
        drift = 0.04 if i > 35 else -0.02
        wave  = math.sin(i / 5.0) * 0.15
        op    = price
        cl    = price + drift + wave
        hi    = max(op, cl) + 0.30
        lo    = min(op, cl) - 0.20
        vol   = 80_000 + (i % 8) * 15_000
        candles_5m.append(Candle(ts, op, hi, lo, cl, vol))
        price = cl

    # Build 20 daily candles
    candles_daily = []
    dp = 240.0
    for i in range(20):
        ts = now - timedelta(days=20 - i)
        op = dp
        cl = dp + (0.8 if i % 3 != 0 else -0.5)
        candles_daily.append(Candle(ts, op, cl + 1.2, cl - 0.8, cl, 1_200_000))
        dp = cl

    market = MarketData(
        symbol              = "ZBRA",
        price               = price,
        previous_close      = 242.25,
        day_open            = 249.50,
        day_high            = max(c.high for c in candles_5m),
        day_low             = min(c.low  for c in candles_5m),
        volume              = 1_400_000,
        avg_volume          = 950_000,
        vwap                = 253.75,
        atr                 = 9.50,
        prior_high          = 258.40,
        prior_low           = 243.92,
        prior_close         = 242.25,
        premarket_high      = 257.20,
        premarket_low       = 245.00,
        opening_range_high  = 256.00,
        opening_range_low   = 249.00,
        week_high           = 261.00,
        week_low            = 238.00,
        benchmark_change_pct= 0.65,
        sector_change_pct   = 1.10,
        candles_5m          = candles_5m,
        candles_daily       = candles_daily,
    )

    options = OptionsData(
        call_wall        = 258.40,
        put_wall         = 243.92,
        gamma_flip       = 255.00,
        expected_move_up = 263.00,
        expected_move_down = 242.00,
        block_flow_bias  = Direction.BULL,
        put_call_ratio   = 1.1,
        iv_rank          = 55.0,
    )

    engine = ConfluenceEngine()
    result = engine.evaluate(market, options)

    print("\n" + "=" * 72)
    print(f"  SIGMALYTIC CONFLUENCE ENGINE — {result.symbol}")
    print("=" * 72)
    print(f"  Price     : ${result.price:.2f}")
    print(f"  Score     : {result.score:.1f} / 100")
    print(f"  Confidence: {result.confidence:.1f}")
    print(f"  Direction : {result.direction}")
    print(f"  Status    : {result.status}")
    print(f"  Regime    : {result.regime}")
    print(f"  Setup     : {result.setup}")
    print()
    print("  ── Public Factors ──────────────────────────────")
    for k, v in result.factor_scores.items():
        bar = "█" * int(v / 5)
        print(f"  {k:>3}  {v:5.1f}  {bar}")
    print()
    print("  ── Internal Family Scores ──────────────────────")
    for k, v in result.internal_scores.items():
        bar = "█" * int(v / 5)
        print(f"  {k:<25} {v:5.1f}  {bar}")
    print()
    print("  ── Levels ──────────────────────────────────────")
    print(f"  Upside Trigger    : ${result.levels['upside_trigger']:.2f}")
    print(f"  Downside Trigger  : ${result.levels['downside_trigger']:.2f}")
    print(f"  Key Magnet        : ${result.levels['key_magnet']:.2f}")
    print()
    print("  ── Paths ───────────────────────────────────────")
    print(f"  BULL  : {result.paths['bull_narrative']}")
    print(f"  NEUTRAL: {result.paths['neutral_narrative']}")
    print(f"  BEAR  : {result.paths['bear_narrative']}")
    print()
    print(f"  Wyckoff Phase   : {result.wyckoff_phase}")
    print(f"  Candle Pattern  : {result.candle_pattern}")
    print(f"  Cycle Hits      : {len(result.cycle_hits)}")
    print()
    print(f"  Alert: {result.alert_reason}")
    print("=" * 72)

    snapshot = RoadmapSnapshot.from_result(result)
    print(f"\n  Snapshot ID: {snapshot.snapshot_id}")
    print("  Snapshot ready for Supabase storage and scoreboard grading.")
    print("=" * 72)


if __name__ == "__main__":
    _smoke_test()
