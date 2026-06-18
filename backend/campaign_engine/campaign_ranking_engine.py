
"""
SAVE AS:
campaign_engine/campaign_ranking_engine.py
"""

from typing import Any, Dict, List


class CampaignRankingEngine:
    """
    Unified Campaign Ranking Engine (UCR)

    Combines:
    - MTA
    - ODS
    - WWE
    - CSD

    into a single institutional ranking score.
    """

    def __init__(
        self,
        alpha: float = 0.30,
        beta: float = 0.35,
        gamma: float = 0.20,
        delta: float = 0.15,
    ):
        total = alpha + beta + gamma + delta

        self.alpha = alpha / total
        self.beta = beta / total
        self.gamma = gamma / total
        self.delta = delta / total

    def compute_ucr(
        self,
        mta: float,
        ods: float,
        wwe_ratio: float,
        csd: float,
    ) -> Dict[str, Any]:

        mta = max(-1.0, min(1.0, float(mta)))
        ods = max(0.0, min(1.0, float(ods)))
        wwe_ratio = max(0.0, min(1.0, float(wwe_ratio)))
        csd = max(0.0, min(1.0, float(csd)))

        mta_normalized = (mta + 1.0) / 2.0

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

    def rank_campaigns(
        self,
        campaigns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        ranked = []

        for campaign in campaigns:

            ranking = self.compute_ucr(
                mta=campaign.get("mta_score", 0),
                ods=campaign.get("ods_score", 0),
                wwe_ratio=campaign.get("wwe_ratio", 0),
                csd=campaign.get("csd_score", 0),
            )

            campaign["ucr_score"] = ranking["ucr_score"]
            campaign["tier"] = ranking["tier"]
            campaign["action"] = ranking["action"]

            ranked.append(campaign)

        ranked.sort(
            key=lambda x: x["ucr_score"],
            reverse=True,
        )

        return ranked
