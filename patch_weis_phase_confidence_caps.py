from pathlib import Path

path = Path("backend/campaign_engine/weis_phase_engine.py")
text = path.read_text(encoding="utf-8")

old = '''        phase_confidence = cls._confidence(
            base=base_confidence,
            fusion_confidence=fusion_confidence,
            coherence=coherence,
            phase_permission=phase_permission,
        )

        if not gamma_data_fresh and weis_phase not in {"WEIS_ONLY_GAMMA_STALE", "WEIS_DATA_BLOCKED"}:
'''

new = '''        phase_confidence = cls._confidence(
            base=base_confidence,
            fusion_confidence=fusion_confidence,
            coherence=coherence,
            phase_permission=phase_permission,
        )

        # Phase-specific confidence caps.
        # These prevent early, stale, pinned, or risk phases from being treated
        # as equal to confirmed Weis-Gamma expansion.
        phase_confidence_caps = {
            "NO_WEIS_STRUCTURE": 0.00,
            "WEIS_DATA_BLOCKED": 0.00,
            "WEIS_BASELINE": 0.45,
            "WEIS_ABSORPTION": 0.88,
            "WEIS_TEST": 0.78,
            "WEIS_TURN": 0.82,
            "WEIS_EXPANSION": 0.90,
            "WEIS_GAMMA_EXPANSION": 1.00,
            "WEIS_GAMMA_PINNED": 0.80,
            "WEIS_GAMMA_COLLAPSE": 0.95,
            "WEIS_EXHAUSTION": 0.85,
            "WEIS_THETA_FLUSH_RISK": 0.90,
            "WEIS_FAILED_CAMPAIGN": 0.50,
            "WEIS_ONLY_GAMMA_STALE": 0.45,
        }

        phase_confidence = round(
            min(phase_confidence, phase_confidence_caps.get(weis_phase, 1.0)),
            4,
        )

        if not gamma_data_fresh and weis_phase not in {"WEIS_ONLY_GAMMA_STALE", "WEIS_DATA_BLOCKED"}:
'''

if old not in text:
    raise SystemExit("Could not find phase confidence block.")

text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")

print("Patched Weis phase confidence caps.")
