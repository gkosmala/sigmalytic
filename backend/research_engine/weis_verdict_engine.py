"""
SAVE AS:
backend/research_engine/weis_verdict_engine.py

Sigmalytic V2
David Weis Emerging Campaign Verdict Engine

Measures:
- Shortening Of Thrust (SOT)
- Wave Volume Exhaustion
- Explosive Up-Wave Confirmation

Purpose:
Measure campaign emergence using Weis Wave
effort-versus-result principles.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any

import pandas as pd
import numpy as np


@dataclass
class WeisVerdict:
    symbol: str
    weis_score: float
    verdict: str
    birth_eligible: bool

    sot_downwaves: float
    volume_exhaustion: float
    upwave_confirmation: float

    explanation: str
    as_of: str

    def to_dict(self):
        return asdict(self)


class WeisVerdictEngine:

    def __init__(self,
                 vol_period: int = 20,
                 zigzag_percent: float = 1.5):

        self.vol_period = vol_period
        self.zigzag_percent = zigzag_percent

    def _prepare(self, df: pd.DataFrame):

        df = df.copy()

        df["vol_sma"] = (
            df["volume"]
            .rolling(self.vol_period)
            .mean()
        )

        return df

    def build_waves(self, df):

        waves = []

        current_dir = (
            -1 if df["close"].iloc[1] <= df["close"].iloc[0]
            else 1
        )

        current_volume = df["volume"].iloc[0]
        current_start = df["close"].iloc[0]

        wave_volume = np.zeros(len(df))
        wave_direction = np.zeros(len(df))

        for i in range(1, len(df)):

            prev_close = df["close"].iloc[i - 1]

            if prev_close == 0:
                continue

            diff = df["close"].iloc[i] - prev_close

            pct = (
                abs(diff)
                / prev_close
                * 100
            )

            if pct >= self.zigzag_percent:

                new_dir = 1 if diff > 0 else -1

                if new_dir != current_dir:

                    waves.append({
                        "dir": current_dir,
                        "vol": current_volume,
                        "delta": abs(
                            df["close"].iloc[i - 1]
                            - current_start
                        )
                    })

                    current_dir = new_dir
                    current_volume = 0
                    current_start = df["close"].iloc[i - 1]

            current_volume += df["volume"].iloc[i]

            wave_volume[i] = current_volume
            wave_direction[i] = current_dir

        return waves, wave_volume, wave_direction

    def shortening_of_thrust_score(self, waves):

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 3:
            return 0.0

        w1, w2, w3 = down[-3:]

        if w3["delta"] < w2["delta"] < w1["delta"]:
            return 100.0

        return 0.0

    def volume_exhaustion_score(self, waves):

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 2:
            return 0.0

        w2 = down[-2]
        w3 = down[-1]

        if w3["vol"] < (0.60 * w2["vol"]):
            return 100.0

        return 0.0

    def upwave_confirmation_score(
        self,
        waves,
        wave_volume,
        wave_direction
    ):

        down = [w for w in waves if w["dir"] == -1]

        if len(down) < 2:
            return 0.0

        last_two = (
            down[-1]["vol"]
            +
            down[-2]["vol"]
        )

        current_green = wave_volume[-1]

        current_dir = wave_direction[-1]

        if (
            current_dir == 1
            and
            current_green > (1.25 * last_two)
        ):
            return 100.0

        return 0.0

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str = ""
    ) -> Dict[str, Any]:

        df = self._prepare(df)

        waves, wave_volume, wave_direction = (
            self.build_waves(df)
        )

        sot = self.shortening_of_thrust_score(waves)

        exhaustion = (
            self.volume_exhaustion_score(waves)
        )

        confirmation = (
            self.upwave_confirmation_score(
                waves,
                wave_volume,
                wave_direction
            )
        )

        score = (
            sot * 0.30
            +
            exhaustion * 0.30
            +
            confirmation * 0.40
        )

        if score >= 90:
            verdict = "PRIMARY_CAMPAIGN_LAUNCH"

        elif score >= 60:
            verdict = "ABSORPTION_WARNING"

        elif score >= 30:
            verdict = "WATCH"

        else:
            verdict = "NO_WEIS_SIGNAL"

        return WeisVerdict(
            symbol=symbol,
            weis_score=round(score, 2),
            verdict=verdict,
            birth_eligible=(
                verdict
                in [
                    "PRIMARY_CAMPAIGN_LAUNCH",
                    "ABSORPTION_WARNING"
                ]
            ),
            sot_downwaves=round(sot, 2),
            volume_exhaustion=round(exhaustion, 2),
            upwave_confirmation=round(
                confirmation,
                2
            ),
            explanation=(
                f"SOT={sot:.1f}, "
                f"Exhaustion={exhaustion:.1f}, "
                f"Confirmation={confirmation:.1f}"
            ),
            as_of=datetime.now(
                timezone.utc
            ).isoformat()
        ).to_dict()


def run_weis_verdict(
    record: Dict[str, Any]
):

    bars = record.get(
        "bars",
        []
    )

    symbol = record.get(
        "symbol",
        ""
    )

    return (
        WeisVerdictEngine()
        .evaluate(
            pd.DataFrame(bars),
            symbol=symbol
        )
    )
