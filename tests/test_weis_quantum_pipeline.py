"""Checks for deterministic candidate selection and stable handoff identity."""
from backend.weis_quantum_pipeline import FEATURE_NAMES, handoff, rank_candidates


def _plan(symbol, side, exhaustion, ratio, test, climax=False):
    return {"symbol": symbol, "side": side, "timeframe": "1Day",
            "test_bar_time": "2026-09-25", "exhaustion_score": exhaustion,
            "wave_volume_ratio": ratio, "test_score": test,
            "preceding_climax": climax, "reward_risk": 2.5}


def test_directional_ranking_keeps_identity_and_evidence():
    buy = _plan("BUY", "Long", 100, .2, 90, True)
    sell = _plan("SELL", "Short", 0, .6, 70)
    ordered = rank_candidates([sell, buy])
    assert [(row["symbol"], row["side"]) for row in ordered] == [("BUY", "Long"), ("SELL", "Short")]
    assert ordered[0]["classical_evidence_score"] > ordered[1]["classical_evidence_score"]
    assert set(handoff(buy)["features"]) == set(FEATURE_NAMES)
    assert ordered[0]["raw"]["wave_volume_ratio"] == .2


def test_features_clamp_invalid_inputs_without_claiming_trade_probability():
    row = handoff(_plan("X", "Short", 1000, -4, 200))
    assert all(0 <= value <= 1 for value in row["features"].values())
    assert "profit_probability" not in row
