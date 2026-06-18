class SignalBirthEngine:
    """
    Identifies early birth of a research signal before full campaign confirmation.
    """

    def evaluate(self, obstacle_score=0.0, progress_score=0.0, spd=False, ods_score=0.0, mta_score=0.0):
        score = (
            float(obstacle_score or 0) * 0.30
            + float(progress_score or 0) * 0.25
            + (100.0 if spd else 0.0) * 0.20
            + float(ods_score or 0) * 100.0 * 0.15
            + ((float(mta_score or 0) + 1.0) / 2.0) * 100.0 * 0.10
        )

        born = (
            float(obstacle_score or 0) >= 70
            and float(progress_score or 0) >= 60
            and bool(spd)
            and float(ods_score or 0) >= 0.35
        )

        return {
            "signal_birth": born,
            "signal_birth_score": round(score, 2),
            "classification": "SIGNAL_BIRTH" if born else "NO_SIGNAL_BIRTH",
        }
