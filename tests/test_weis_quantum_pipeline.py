"""Checks for complete, unweighted candidate handoff and stable identity."""
from backend.weis_quantum_pipeline import FEATURE_NAMES, handoff, candidate_records


def _plan(symbol, side, exhaustion, ratio, test, climax=False):
    return {"symbol": symbol, "side": side, "timeframe": "1Day",
            "test_bar_time": "2026-09-25", "exhaustion_score": exhaustion,
            "wave_volume_ratio": ratio, "test_score": test,
            "preceding_climax": climax, "reward_risk": 2.5}


def test_candidate_handoff_keeps_identity_and_evidence_without_weights():
    buy = _plan("BUY", "Long", 100, .2, 90, True)
    sell = _plan("SELL", "Short", 0, .6, 70)
    ordered = candidate_records([sell, buy])
    assert [(row["symbol"], row["side"]) for row in ordered] == [("BUY", "Long"), ("SELL", "Short")]
    assert all("classical_evidence_score" not in row for row in ordered)
    assert set(handoff(buy)["features"]) == set(FEATURE_NAMES)
    assert ordered[0]["raw"]["wave_volume_ratio"] == .2


def test_features_clamp_invalid_inputs_without_claiming_trade_probability():
    row = handoff(_plan("X", "Short", 1000, -4, 200))
    assert all(0 <= value <= 1 for value in row["features"].values())
    assert "profit_probability" not in row


def test_validated_event_keeps_trigger_and_invalidation():
    event = {**_plan("ABC", "Short", 100, .5, 100),
             "state": "TRIGGERED", "signals": ["UPTHRUST"],
             "entry_trigger": 100, "invalidation": 105}
    rows = candidate_records([event])
    assert rows[0]["state"] == "TRIGGERED"
    assert rows[0]["signals"] == ["UPTHRUST"]
    assert rows[0]["raw"]["entry_trigger"] == 100
    assert rows[0]["raw"]["invalidation"] == 105
    assert rows[0]["raw"]["risk_pct"] == 5.0


def test_candidate_handoff_has_no_top_ten_cutoff():
    rows = candidate_records([_plan(f"S{i:02d}", "Long", i, .4, 80) for i in range(17)])
    assert len(rows) == 17


def test_missing_climax_still_has_nonzero_kernel_overlap():
    """Regression: a binary zero Climax must not force every result to 0%."""
    import importlib.util
    if importlib.util.find_spec("qiskit") is None:
        return  # the production Python environment runs this circuit check
    from qiskit.quantum_info import Statevector
    from backend.weis_quantum_pipeline import kernel_circuit
    features = {"directional_exhaustion": 1.0, "low_volume_test": .83,
                "level_test": 1.0, "climax_or_absorption": 0.0}
    circuit = kernel_circuit(features).remove_final_measurements(inplace=False)
    probability = Statevector.from_instruction(circuit).probabilities()[0]
    assert 0.25 < probability < 0.75, probability
