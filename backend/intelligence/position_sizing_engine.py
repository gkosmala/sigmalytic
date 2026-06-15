# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/intelligence/position_sizing_engine.py
-----------------------------------------------
Layer 4 — Position Sizing Engine (Phase 10).

Computes Half-Kelly position sizing for every TIER_1 / TIER_2 campaign
at birth. Implements the ASYM filter that blocks 44.7% of low-quality
Layer A signals before they consume capital.

PHASE 10 VALIDATED PARAMETERS
------------------------------
Layer A (TIER_1):
  Stop:         -10%
  Half-Kelly:   21.2% of available capital per position
  Win rate:     70.62% (mfe90 basis)
  Avg win:      70.62%
  Avg loss:     -10%

Layer B (TIER_2):
  Stop:         -20%
  Half-Kelly:   19.9% of available capital per position
  Win rate:     59.87%
  Avg win:      52.30%
  Avg loss:     -20%

ASYM FILTER
-----------
From Phase 10 research: 44.7% of Layer A failures had asymmetry ratio < 1.0
at signal time. ASYM = mfe20 / abs(mae20).
ASYM < 1.0 → block signal (flag as LOW_QUALITY, do not size).
ASYM >= 1.0 → proceed with Half-Kelly sizing.

PORTFOLIO CONSTRAINT (Phase 11)
--------------------------------
Optimal portfolio: 20-25 simultaneous positions.
Max single position: 5% of total portfolio (hard cap).
Total deployment cap: 95% of available capital.

CLAUDE.md compliance
--------------------
• Credentials via os.environ only.
• Decimal for ALL prices, quantities, and monetary values.
• Full type hints.
• Structured try/except throughout.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN
from typing import Optional

log = logging.getLogger("position_sizing_engine")

# ---------------------------------------------------------------------------
# Phase 10 validated constants — DO NOT change without re-running Phase 10
# ---------------------------------------------------------------------------

# Layer A (TIER_1) parameters
LAYER_A_STOP_PCT:       Decimal = Decimal("-0.10")   # -10%
LAYER_A_WIN_RATE:       Decimal = Decimal("0.7062")  # 70.62%
LAYER_A_AVG_WIN:        Decimal = Decimal("0.7062")  # 70.62% mfe90
LAYER_A_AVG_LOSS:       Decimal = Decimal("0.10")    # 10% loss at stop
LAYER_A_HALF_KELLY:     Decimal = Decimal("0.212")   # 21.2%

# Layer B (TIER_2) parameters
LAYER_B_STOP_PCT:       Decimal = Decimal("-0.20")   # -20%
LAYER_B_WIN_RATE:       Decimal = Decimal("0.5987")  # 59.87%
LAYER_B_AVG_WIN:        Decimal = Decimal("0.5230")  # 52.30% mfe90
LAYER_B_AVG_LOSS:       Decimal = Decimal("0.20")    # 20% loss at stop
LAYER_B_HALF_KELLY:     Decimal = Decimal("0.199")   # 19.9%

# ASYM filter threshold
ASYM_MIN:               Decimal = Decimal("1.0")     # block if below this

# Portfolio constraints
MAX_POSITIONS:          int     = 25
MAX_SINGLE_POSITION_PCT: Decimal = Decimal("0.05")   # 5% hard cap per position
MAX_TOTAL_DEPLOYMENT:   Decimal = Decimal("0.95")    # 95% of available capital

# Campaign duration
CAMPAIGN_DAYS:          int     = 90                 # standard 90-day hold


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------

@dataclass
class SizingResult:
    """Output of the position sizing engine for one signal."""
    symbol:          str
    tier:            str
    layer:           str              # "A" or "B"
    entry_price:     Decimal
    stop_price:      Decimal
    stop_pct:        Decimal          # e.g. Decimal("-0.10")
    shares:          int              # whole shares only
    position_value:  Decimal          # shares × entry_price
    position_pct:    Decimal          # position_value / portfolio_value
    max_loss_value:  Decimal          # shares × entry_price × abs(stop_pct)
    expected_exit:   date             # entry_date + 90 days
    asym_ratio:      Decimal
    asym_passed:     bool
    kelly_fraction:  Decimal
    blocked_reason:  Optional[str]    # None if approved, reason string if blocked

    @property
    def is_approved(self) -> bool:
        return self.blocked_reason is None

    @property
    def summary(self) -> str:
        if not self.is_approved:
            return f"BLOCKED — {self.blocked_reason}"
        return (
            f"{self.symbol} {self.tier} | "
            f"{self.shares} shares @ ${self.entry_price} | "
            f"stop ${self.stop_price} ({self.stop_pct:.0%}) | "
            f"value ${self.position_value:,.0f} ({self.position_pct:.1%}) | "
            f"exit {self.expected_exit}"
        )


@dataclass
class PortfolioContext:
    """Current portfolio state passed into the sizing engine."""
    total_value:       Decimal    # total portfolio value in USD
    available_capital: Decimal    # uninvested cash
    active_positions:  int        # current number of open positions
    deployed_capital:  Decimal    # capital currently in positions


# ---------------------------------------------------------------------------
# Core Kelly formula
# ---------------------------------------------------------------------------

def _full_kelly(win_rate: Decimal, avg_win: Decimal, avg_loss: Decimal) -> Decimal:
    """
    Full Kelly criterion: f* = (p * b - q) / b
    where p = win_rate, q = 1 - p, b = avg_win / avg_loss
    """
    if avg_loss == Decimal("0"):
        return Decimal("0")
    b = avg_win / avg_loss
    q = Decimal("1") - win_rate
    kelly = (win_rate * b - q) / b
    return max(Decimal("0"), kelly)


def _half_kelly(win_rate: Decimal, avg_win: Decimal, avg_loss: Decimal) -> Decimal:
    """Half-Kelly: 50% of full Kelly for risk management."""
    return _full_kelly(win_rate, avg_win, avg_loss) / Decimal("2")


# ---------------------------------------------------------------------------
# ASYM filter
# ---------------------------------------------------------------------------

def check_asym_filter(asym_ratio: Decimal) -> tuple[bool, Optional[str]]:
    """
    Apply the Phase 10 ASYM filter.

    Returns (passed, blocked_reason).
    passed=True means signal is approved to proceed.
    passed=False means signal is blocked — do not size.
    """
    if asym_ratio < ASYM_MIN:
        return False, (
            f"ASYM filter: ratio {asym_ratio:.2f} < {ASYM_MIN} minimum. "
            f"44.7% of Layer A failures had ASYM < 1.0 at signal time."
        )
    return True, None


# ---------------------------------------------------------------------------
# Portfolio constraint checks
# ---------------------------------------------------------------------------

def check_portfolio_constraints(
    portfolio: PortfolioContext,
    proposed_value: Decimal,
) -> tuple[bool, Optional[str]]:
    """
    Check Phase 11 portfolio constraints before approving a position.

    Returns (approved, blocked_reason).
    """
    # Max positions check
    if portfolio.active_positions >= MAX_POSITIONS:
        return False, (
            f"Portfolio full: {portfolio.active_positions}/{MAX_POSITIONS} "
            f"positions active. Wait for a campaign to close."
        )

    # Max single position size (5% hard cap)
    if portfolio.total_value > Decimal("0"):
        proposed_pct = proposed_value / portfolio.total_value
        if proposed_pct > MAX_SINGLE_POSITION_PCT:
            return False, (
                f"Position too large: {proposed_pct:.1%} exceeds "
                f"{MAX_SINGLE_POSITION_PCT:.0%} single-position cap."
            )

    # Total deployment cap
    if portfolio.total_value > Decimal("0"):
        new_deployed = portfolio.deployed_capital + proposed_value
        deployment_pct = new_deployed / portfolio.total_value
        if deployment_pct > MAX_TOTAL_DEPLOYMENT:
            return False, (
                f"Deployment cap: adding this position would deploy "
                f"{deployment_pct:.1%} of portfolio "
                f"(max {MAX_TOTAL_DEPLOYMENT:.0%})."
            )

    # Insufficient cash
    if proposed_value > portfolio.available_capital:
        return False, (
            f"Insufficient capital: position requires "
            f"${proposed_value:,.0f} but only "
            f"${portfolio.available_capital:,.0f} available."
        )

    return True, None


# ---------------------------------------------------------------------------
# Main sizing function
# ---------------------------------------------------------------------------

def compute_position_size(
    symbol:       str,
    tier:         str,
    entry_price:  Decimal,
    asym_ratio:   Decimal,
    portfolio:    PortfolioContext,
    entry_date:   Optional[date] = None,
) -> SizingResult:
    """
    Compute the Half-Kelly position size for a signal.

    Parameters
    ----------
    symbol:      Ticker symbol.
    tier:        "TIER_1" or "TIER_2".
    entry_price: Market-on-open fill price (Decimal).
    asym_ratio:  ASYM ratio at signal time (mfe20 / abs(mae20)).
    portfolio:   Current portfolio state.
    entry_date:  Signal entry date (defaults to today).

    Returns
    -------
    SizingResult — check .is_approved before placing order.
    """
    if entry_date is None:
        entry_date = date.today()

    expected_exit = entry_date + timedelta(days=CAMPAIGN_DAYS)

    # ── Determine layer parameters ────────────────────────────────────────
    if tier == "TIER_1":
        layer        = "A"
        stop_pct     = LAYER_A_STOP_PCT
        win_rate     = LAYER_A_WIN_RATE
        avg_win      = LAYER_A_AVG_WIN
        avg_loss     = LAYER_A_AVG_LOSS
        kelly_preset = LAYER_A_HALF_KELLY
    else:
        layer        = "B"
        stop_pct     = LAYER_B_STOP_PCT
        win_rate     = LAYER_B_WIN_RATE
        avg_win      = LAYER_B_AVG_WIN
        avg_loss     = LAYER_B_AVG_LOSS
        kelly_preset = LAYER_B_HALF_KELLY

    stop_price = entry_price * (Decimal("1") + stop_pct)

    # ── ASYM filter ───────────────────────────────────────────────────────
    asym_passed, asym_reason = check_asym_filter(asym_ratio)
    if not asym_passed:
        log.warning("ASYM filter blocked %s %s: %s", symbol, tier, asym_reason)
        return SizingResult(
            symbol         = symbol,
            tier           = tier,
            layer          = layer,
            entry_price    = entry_price,
            stop_price     = stop_price,
            stop_pct       = stop_pct,
            shares         = 0,
            position_value = Decimal("0"),
            position_pct   = Decimal("0"),
            max_loss_value = Decimal("0"),
            expected_exit  = expected_exit,
            asym_ratio     = asym_ratio,
            asym_passed    = False,
            kelly_fraction = kelly_preset,
            blocked_reason = asym_reason,
        )

    # ── Compute Half-Kelly position size ──────────────────────────────────
    # Validate the preset against live Kelly formula
    computed_kelly = _half_kelly(win_rate, avg_win, avg_loss)
    # Use the research-validated preset (more conservative than live compute
    # to account for real-world slippage and signal decay)
    kelly_fraction = min(kelly_preset, computed_kelly + Decimal("0.02"))

    # Apply Kelly to available capital
    raw_position_value = portfolio.available_capital * kelly_fraction

    # Hard cap at 5% of total portfolio
    max_by_cap = portfolio.total_value * MAX_SINGLE_POSITION_PCT
    position_value = min(raw_position_value, max_by_cap)

    # Round down to whole shares
    if entry_price <= Decimal("0"):
        shares = 0
    else:
        shares = int((position_value / entry_price).to_integral_value(rounding=ROUND_DOWN))

    # Recalculate exact position value from whole shares
    actual_position_value = Decimal(str(shares)) * entry_price
    position_pct = (
        actual_position_value / portfolio.total_value
        if portfolio.total_value > Decimal("0") else Decimal("0")
    )
    max_loss_value = actual_position_value * abs(stop_pct)

    # ── Portfolio constraint check ────────────────────────────────────────
    approved, constraint_reason = check_portfolio_constraints(
        portfolio, actual_position_value
    )

    if not approved:
        log.warning("Portfolio constraint blocked %s %s: %s", symbol, tier, constraint_reason)

    blocked_reason = constraint_reason if not approved else None

    result = SizingResult(
        symbol         = symbol,
        tier           = tier,
        layer          = layer,
        entry_price    = entry_price,
        stop_price     = stop_price.quantize(Decimal("0.01")),
        stop_pct       = stop_pct,
        shares         = shares if approved else 0,
        position_value = actual_position_value if approved else Decimal("0"),
        position_pct   = position_pct if approved else Decimal("0"),
        max_loss_value = max_loss_value if approved else Decimal("0"),
        expected_exit  = expected_exit,
        asym_ratio     = asym_ratio,
        asym_passed    = True,
        kelly_fraction = kelly_fraction,
        blocked_reason = blocked_reason,
    )

    if result.is_approved:
        log.info(
            "Position sized | %s %s | %d shares @ $%s | "
            "value $%s (%.1f%%) | stop $%s | exit %s",
            symbol, tier, shares, entry_price,
            f"{actual_position_value:,.0f}",
            float(position_pct * 100),
            result.stop_price,
            expected_exit,
        )

    return result


# ---------------------------------------------------------------------------
# Batch sizing — called by signal birth engine at campaign birth
# ---------------------------------------------------------------------------

def size_campaign_batch(
    signals:   list[dict],
    portfolio: PortfolioContext,
) -> list[SizingResult]:
    """
    Size a batch of signals in priority order (TIER_1 first, then by D-Score).

    Signals are consumed in order until the portfolio is full or capital
    is exhausted. Returns a list of SizingResults — check .is_approved.

    Parameters
    ----------
    signals:
        List of dicts with keys: symbol, tier, entry_price, asym_ratio, d_score.
    portfolio:
        Current portfolio state.
    """
    # Sort: TIER_1 first, then TIER_2, then by D-Score descending
    def _priority(s: dict) -> tuple:
        tier_n = 0 if s.get("tier") == "TIER_1" else 1
        d_score = float(s.get("d_score", 0))
        return (tier_n, -d_score)

    sorted_signals = sorted(signals, key=_priority)
    results: list[SizingResult] = []

    # Track running portfolio state as positions are added
    remaining_capital  = portfolio.available_capital
    remaining_deployed = portfolio.deployed_capital
    active_count       = portfolio.active_positions

    for sig in sorted_signals:
        try:
            entry_price = Decimal(str(sig.get("entry_price", 0)))
            asym_ratio  = Decimal(str(sig.get("asym_ratio", 1)))
            tier        = sig.get("tier", "TIER_2")
            symbol      = sig.get("symbol", "")

            # Build updated portfolio context for this signal
            current_portfolio = PortfolioContext(
                total_value       = portfolio.total_value,
                available_capital = remaining_capital,
                active_positions  = active_count,
                deployed_capital  = remaining_deployed,
            )

            result = compute_position_size(
                symbol      = symbol,
                tier        = tier,
                entry_price = entry_price,
                asym_ratio  = asym_ratio,
                portfolio   = current_portfolio,
            )

            results.append(result)

            # Update running state if approved
            if result.is_approved:
                remaining_capital  -= result.position_value
                remaining_deployed += result.position_value
                active_count       += 1

        except Exception as exc:
            log.error("Sizing error for %s: %s", sig.get("symbol", "?"), exc)

    approved = sum(1 for r in results if r.is_approved)
    blocked  = len(results) - approved
    log.info(
        "Batch sizing complete: %d approved, %d blocked from %d signals",
        approved, blocked, len(signals),
    )

    return results


# ---------------------------------------------------------------------------
# API helper — serialize SizingResult for JSON response
# ---------------------------------------------------------------------------

def sizing_result_to_dict(r: SizingResult) -> dict:
    return {
        "symbol":          r.symbol,
        "tier":            r.tier,
        "layer":           r.layer,
        "approved":        r.is_approved,
        "blocked_reason":  r.blocked_reason,
        "entry_price":     str(r.entry_price),
        "stop_price":      str(r.stop_price),
        "stop_pct":        str(r.stop_pct),
        "shares":          r.shares,
        "position_value":  str(r.position_value),
        "position_pct":    str(r.position_pct),
        "max_loss_value":  str(r.max_loss_value),
        "expected_exit":   r.expected_exit.isoformat(),
        "asym_ratio":      str(r.asym_ratio),
        "asym_passed":     r.asym_passed,
        "kelly_fraction":  str(r.kelly_fraction),
        "summary":         r.summary,
    }
