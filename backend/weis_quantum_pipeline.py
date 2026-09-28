"""Reproducible Weis candidate ranking and quantum kernel handoff.

The zero-state fraction is a circuit overlap, not a calibrated probability
of a profitable trade or proof of institutional activity.
"""
from __future__ import annotations

import math


FEATURE_NAMES = ("directional_exhaustion", "low_volume_test", "level_test", "climax_or_absorption")
REFERENCE = (1.0, 1.0, 1.0, 1.0)


def _unit(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return 0.0
    return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.0


def handoff(plan):
    """Keep direction and raw evidence beside normalized, bounded features."""
    exhaustion = _unit(plan.get("exhaustion_score", 0) / 100)
    friction = _unit(plan.get("effort_without_reward_score", 0) / 100)
    climax = bool(plan.get("preceding_climax"))
    features = (
        exhaustion,
        1 - _unit(plan.get("wave_volume_ratio", 1)),
        _unit(plan.get("test_score", 0) / 100),
        max(friction, float(climax)),
    )
    return {"symbol": plan["symbol"], "side": plan["side"],
            "state": plan.get("state", "WATCH"), "signals": list(plan.get("signals") or []),
            "test_bar_time": plan["test_bar_time"], "timeframe": plan["timeframe"],
            "features": dict(zip(FEATURE_NAMES, features)),
            "raw": {key: plan.get(key) for key in (
                "sot_score", "exhaustion_score", "effort_without_reward_score",
                "wave_volume_ratio", "test_score", "preceding_climax",
                "entry_trigger", "invalidation", "target", "reward_risk")}}


def classical_rank(plan):
    """Explicit evidence order; a result has no historical success probability."""
    row = handoff(plan)
    f = row["features"]
    score = round(40 * f["directional_exhaustion"] +
                  25 * f["low_volume_test"] + 20 * f["level_test"] +
                  15 * f["climax_or_absorption"], 2)
    return {**row, "classical_evidence_score": score,
            "score_definition": "40% exhaustion, 25% light-volume wave, 20% Radar pattern, 15% climax/absorption"}


def rank_candidates(plans, limit=10):
    rows = [classical_rank(p) for p in plans]
    rows.sort(key=lambda r: (-r["classical_evidence_score"],
                             -float(r["raw"]["reward_risk"] or 0), r["symbol"], r["side"]))
    return rows[:limit]


def radar_candidates(symbol, timeframe, bar_time, hits, wave, wave_volume_ratio, armed=None):
    """Create directional watch candidates from actual Radar and Weis evidence.

    A pattern hit is a Radar signal, not confirmation of a structural level
    sweep. The ARMED flag comes only from the separate strict trade finder.
    """
    names = {hit.get("type") for hit in hits}
    output = []
    for side, pattern, climax, sot_key, exhaustion_key, friction_key in (
        ("Long", "SPRING", "CLIMAX_SELL", "sot_downwaves", "volume_exhaustion", "effort_without_reward"),
        ("Short", "UPTHRUST", "CLIMAX_BUY", "sot_upwaves", "buying_exhaustion", "buying_effort_without_reward"),
    ):
        sot = _unit(wave.get(sot_key, 0) / 100)
        exhaustion = _unit(wave.get(exhaustion_key, 0) / 100)
        friction = _unit(wave.get(friction_key, 0) / 100)
        if not ({pattern, climax} & names or sot or exhaustion or friction or
                (armed and armed.get("side") == side)):
            continue
        is_armed = bool(armed and armed.get("side") == side)
        output.append({
            "symbol": symbol, "side": side, "timeframe": timeframe,
            "test_bar_time": str(bar_time or ""), "state": "ARMED" if is_armed else "WATCH",
            "sot_score": wave.get(sot_key, 0), "exhaustion_score": wave.get(exhaustion_key, 0),
            "effort_without_reward_score": wave.get(friction_key, 0),
            "wave_volume_ratio": wave_volume_ratio,
            "test_score": 100 if pattern in names else 0,
            "preceding_climax": climax in names,
            "reward_risk": armed.get("reward_risk") if is_armed else None,
            "entry_trigger": armed.get("entry_trigger") if is_armed else None,
            "invalidation": armed.get("invalidation") if is_armed else None,
            "target": armed.get("target") if is_armed else None,
            "signals": sorted(name for name in (pattern, climax) if name in names),
        })
    return output


def kernel_circuit(features):
    """Four-feature overlap with a fixed least-risk reference archetype.

    The reference is a declared modeling choice, not a learned institution
    label. Interaction gates encode relationships between adjacent features.
    """
    from qiskit import QuantumCircuit
    values = tuple(_unit(features[name]) for name in FEATURE_NAMES)
    circuit = QuantumCircuit(4)

    def feature_map(vector):
        for index, value in enumerate(vector):
            circuit.ry(math.pi * value, index)
        for index in range(3):
            circuit.cx(index, index + 1)
            circuit.rz(math.pi * vector[index] * vector[index + 1], index + 1)
            circuit.cx(index, index + 1)

    def inverse_map(vector):
        for index in reversed(range(3)):
            circuit.cx(index, index + 1)
            circuit.rz(-math.pi * vector[index] * vector[index + 1], index + 1)
            circuit.cx(index, index + 1)
        for index in reversed(range(4)):
            circuit.ry(-math.pi * vector[index], index)

    feature_map(values)
    inverse_map(REFERENCE)
    circuit.measure_all()
    return circuit


def execute(rows, *, mode="local", shots=4096, backend_name=None):
    """Run an identical circuit on local StatevectorSampler or IBM hardware."""
    if mode not in {"local", "ibm"} or not 1 <= shots <= 100_000:
        raise ValueError("mode must be local or ibm, and shots must be 1..100000")
    if not rows:
        return {"mode": mode, "results": [], "job_id": None}
    circuits = [kernel_circuit(row["features"]) for row in rows]
    backend_used = None
    if mode == "local":
        from qiskit.primitives import StatevectorSampler
        job = StatevectorSampler(default_shots=shots).run(circuits)
    else:
        from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
        from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
        service = QiskitRuntimeService(channel="ibm_quantum_platform")
        backend = (service.backend(backend_name) if backend_name else
                   service.least_busy(simulator=False, operational=True))
        if backend.configuration().simulator:
            raise ValueError("IBM mode requires a physical backend")
        backend_used = backend.name
        pm = generate_preset_pass_manager(optimization_level=1, backend=backend)
        circuits = [pm.run(circuit) for circuit in circuits]
        job = SamplerV2(mode=backend).run(circuits, shots=shots)
    result = job.result()
    completed = []
    for row, pub in zip(rows, result):
        counts = pub.data.meas.get_counts()
        total = sum(counts.values())
        completed.append({**row, "counts": counts, "shots": total,
                          "kernel_similarity": counts.get("0000", 0) / total if total else None,
                          "measurement": "P(0000) overlap with declared reference; not trade probability"})
    completed.sort(key=lambda row: (-(row["kernel_similarity"] or 0),
                                    -row["classical_evidence_score"], row["symbol"]))
    return {"mode": mode, "backend": backend_used,
            "job_id": job.job_id() if mode == "ibm" else None,
            "shots_requested": shots, "reference": dict(zip(FEATURE_NAMES, REFERENCE)),
            "results": completed}
