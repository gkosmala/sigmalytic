"""
tests/test_gamma_regime.py
---------------------------
Regression coverage for GammaStrikeMatrixEngine._net_gamma_regime().

WHY THIS EXISTS: this function was found (2026-07-30) to classify the
gamma regime from total_gex (an aggregate summed across the entire
options chain) instead of from where spot price actually sits relative
to the computed zero-gamma flip level -- a real, precise mismatch
against the correct definition (dealers are net long gamma ABOVE the
flip, net short gamma BELOW it). Fixed to derive the regime directly
from price-vs-flip-level. These tests pin that exact behavior down so
a future change can't silently reintroduce the aggregate-based
(incorrect) classification.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.gamma.gamma_strike_matrix_engine import GammaStrikeMatrixEngine


def test_price_above_flip_is_positive():
    regime = GammaStrikeMatrixEngine._net_gamma_regime(spot_price=331, zero_gamma_level=330)
    assert regime == "POSITIVE"


def test_price_well_above_flip_is_deep_positive():
    # 2%+ above the flip should escalate to DEEP_POSITIVE
    regime = GammaStrikeMatrixEngine._net_gamma_regime(spot_price=340, zero_gamma_level=330)
    assert regime == "DEEP_POSITIVE"


def test_price_below_flip_is_negative():
    regime = GammaStrikeMatrixEngine._net_gamma_regime(spot_price=329, zero_gamma_level=330)
    assert regime == "NEGATIVE"


def test_price_well_below_flip_is_deep_negative():
    regime = GammaStrikeMatrixEngine._net_gamma_regime(spot_price=320, zero_gamma_level=330)
    assert regime == "DEEP_NEGATIVE"


def test_price_exactly_at_flip_is_neutral():
    regime = GammaStrikeMatrixEngine._net_gamma_regime(spot_price=330, zero_gamma_level=330)
    assert regime == "NEUTRAL"


def test_missing_flip_level_is_neutral_not_a_crash():
    regime = GammaStrikeMatrixEngine._net_gamma_regime(spot_price=330, zero_gamma_level=None)
    assert regime == "NEUTRAL"


def test_regime_is_derived_from_price_vs_flip_not_a_separate_aggregate():
    """
    Locks in the specific bug fix: the function signature itself must
    take (spot_price, zero_gamma_level) -- if a future change reverts
    to taking a single total_gex-style aggregate argument instead, this
    test's call pattern will fail loudly rather than silently
    misclassifying regimes again.
    """
    import inspect
    sig = inspect.signature(GammaStrikeMatrixEngine._net_gamma_regime)
    params = list(sig.parameters.keys())
    assert "spot_price" in params
    assert "zero_gamma_level" in params
