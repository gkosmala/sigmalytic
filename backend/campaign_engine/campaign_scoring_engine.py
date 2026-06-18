
"""
SAVE AS:
campaign_engine/campaign_scoring_engine.py

Sigmalytic V2
Campaign Scoring Engine

Official V2 Baseline Implementation:
- MTA
- ODS
- WWE
- CSD
- UCR
"""

from typing import Dict, Any, List


class CampaignScoringEngine:

    def __init__(
        self,
        alpha: float = 0.30,
        beta: float = 0.35,
        gamma: float = 0.20,
        delta: float = 0.15,
    ):
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.delta = delta

    # ---------------------------------------------------------
    # MTA
    # ---------------------------------------------------------

    def calculate_mta(
        self,
        macro_states: List[Dict[str, Any]],
    ) -> float:

        if not macro_states:
            return 0.0

        total = 0.0

        for state in macro_states:

            direction = str(
                state.get("state", "")
            ).upper()

            weight = float(
                state.get("weight", 0)
            )

            if direction in [
                "ACCUMULATION",
                "MARKUP",
                "EXPANDING",
                "SURVIVING",
            ]:
                total += weight

            elif direction in [
                "DISTRIBUTION",
                "MARKDOWN",
                "FAILED",
            ]:
                total -= weight

        return round(
            max(-1.0, min(total, 1.0)),
            4,
        )

    # ---------------------------------------------------------
    # ODS
    # ---------------------------------------------------------

    def calculate_ods(
        self,
        total_volume: float,
        institutional_volume: float,
    ) -> float:

        if total_volume <= 0:
            return 0.0

        return round(
            institutional_volume / total_volume,
            4,
        )

    # ---------------------------------------------------------
    # WWE
    # ---------------------------------------------------------

    def calculate_wwe(
        self,
        price_progress: float,
        wave_volume: float,
    ) -> float:

        if wave_volume <= 0:
            return 0.0

        return round(
            price_progress / wave_volume,
            8,
        )

    def calculate_wwe_ratio(
        self,
        current_wwe: float,
        prior_wwe: float,
    ) -> float:

        if prior_wwe <= 0:
            return 0.0

        ratio = current_wwe / prior_wwe

        return round(
            max(0.0, min(ratio, 1.0)),
            4,
        )

    # ---------------------------------------------------------
    # CSD
    # ---------------------------------------------------------

    def calculate_csd(
        self,
        csd_score: float,
    ) -> float:

        return round(
            max(0.0, min(csd_score, 1.0)),
            4,
        )

    # ---------------------------------------------------------
    # UCR
    # ---------------------------------------------------------

    def calculate_ucr(
        self,
        mta: float,
        ods: float,
        wwe_ratio: float,
        csd: float,
    ) -> Dict[str, Any]:

        mta_normalized = (
            mta + 1.0
        ) / 2.0

        score = (
            (self.alpha * mta_normalized)
            + (self.beta * ods)
            + (self.gamma * wwe_ratio)
            + (self.delta * csd)
        ) * 100.0

        score = round(score, 2)

        if score >= 80:
            tier = "TIER_1_INSTITUTIONAL_ALPHA"
            action = "ARMED"

        elif score >= 50:
            tier = "TIER_2_STABLE_RETENTION"
            action = "WATCH"

        else:
            tier = "TIER_3_LIQUIDATION_VOID"
            action = "LOCKOUT"

        return {
            "ucr_score": score,
            "tier": tier,
            "action": action,
        }

    # ---------------------------------------------------------
    # MASTER ENTRYPOINT
    # ---------------------------------------------------------

    def score_campaign(
        self,
        mta: float,
        ods: float,
        wwe_ratio: float,
        csd: float,
    ) -> Dict[str, Any]:

        return self.calculate_ucr(
            mta=mta,
            ods=ods,
            wwe_ratio=wwe_ratio,
            csd=csd,
        )
