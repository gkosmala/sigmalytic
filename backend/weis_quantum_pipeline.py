"""Send actual Weis setup evidence to a local or IBM quantum sampler.

Measurements are raw circuit output, not a setup rank or trade probability.
"""
from __future__ import annotations

import math


FEATURE_NAMES = ("directional_exhaustion", "low_volume_test", "level_test", "climax_or_absorption")


def _unit(value):
    try:
        number = float(value)
    except (ValueError, TypeError):
        return 0.0
    return max(0.0, min(1.0, number)) if math.isfinite(number) else 0.0


def handoff(plan):
    """Keep direction and raw evidence beside normalized, bounded features."""
    behavior = plan.get("wave_behavior") or {}
    exhaustion = max(_unit(plan.get("exhaustion_score", 0) / 100),
                     float(bool(behavior.get("diminished_volume_new_extreme"))))
    friction = _unit(plan.get("effort_without_reward_score", 0) / 100)
    climax = bool(plan.get("preceding_climax"))
    features = (
        exhaustion,
        1 - _unit(plan["wave_volume_ratio"]) if plan.get("wave_volume_ratio") is not None else 0.0,
        _unit(plan.get("test_score", 0) / 100),
        max(friction, float(climax), float(bool(behavior.get("effort_without_result")))),
    )
    entry, stop = plan.get("entry_trigger"), plan.get("invalidation")
    risk_pct = abs(entry - stop) / entry * 100 if entry and stop and entry > 0 else None
    raw = {key: plan.get(key) for key in (
        "sot_score", "exhaustion_score", "effort_without_reward_score",
        "wave_volume_ratio", "test_score", "preceding_climax",
        "entry_trigger", "invalidation", "target", "reward_risk",
        "structure_level", "low_volume_test", "wave_behavior", "wave_sequence", "armed")}
    raw["risk_pct"] = round(risk_pct, 4) if risk_pct is not None else None
    raw["prior_wave_evidence"] = [label for condition, label in (
        (_unit(plan.get("exhaustion_score", 0) / 100) > 0, "exhaustion"),
        (_unit(plan.get("effort_without_reward_score", 0) / 100) > 0, "effort without result"),
        (climax, "climax"),
    ) if condition]
    raw["test_wave_evidence"] = [label for condition, label in (
        (plan.get("low_volume_test"), "low volume"),
        (behavior.get("effort_without_result"), "effort without result"),
        (behavior.get("diminished_volume_new_extreme"), "diminished-volume extreme"),
    ) if condition]
    return {"symbol": plan["symbol"], "side": plan["side"],
            "state": plan.get("state", "TRIGGERED"), "signals": list(plan.get("signals") or []),
            "test_bar_time": plan["test_bar_time"], "timeframe": plan["timeframe"],
            "features": dict(zip(FEATURE_NAMES, features)), "raw": raw}


def candidate_records(plans):
    """Expose all validated events with measured evidence; no chosen weights."""
    rows = [handoff(plan) for plan in plans]
    rows.sort(key=lambda row: (row["symbol"], row["side"]))
    return rows


def kernel_circuit(features):
    """Encode one actual setup; no reference state or candidate comparison."""
    from qiskit import QuantumCircuit
    values = tuple(_unit(features[name]) for name in FEATURE_NAMES)
    circuit = QuantumCircuit(4)

    def feature_map(vector):
        for index, value in enumerate(vector):
            # A half-turn over the full [0, 1] feature range avoids making
            # a missing binary Climax feature orthogonal to the reference.
            circuit.ry((math.pi / 2) * value, index)
        for index in range(3):
            circuit.cx(index, index + 1)
            circuit.rz((math.pi / 4) * vector[index] * vector[index + 1], index + 1)
            circuit.cx(index, index + 1)

    feature_map(values)
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
                          "measurement": "Raw encoded-setup counts; no ranking or trade probability"})
    return {"mode": mode, "backend": backend_used,
            "job_id": job.job_id() if mode == "ibm" else None,
            "shots_requested": shots,
            "results": completed}
