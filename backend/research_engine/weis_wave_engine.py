
"""SAVE AS: campaign_engine/weis_wave_engine.py"""

class WeisWaveEngine:

    def efficiency(
        self,
        price_progress: float,
        wave_volume: float,
    ) -> float:

        if wave_volume <= 0:
            return 0.0

        return price_progress / wave_volume

    def spd(
        self,
        w1: float,
        w2: float,
        w3: float,
    ) -> bool:

        return w1 < w2 < w3

