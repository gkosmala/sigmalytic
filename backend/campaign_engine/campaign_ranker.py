
class CampaignRanker:
    """
    Sigmalytic V2 Campaign Ranking Engine

    Ranking Priority:
    1. UCR Score
    2. ODS Score
    3. Survival Score
    4. MTA Score
    5. Campaign State Bonus
    """

    STATE_BONUS = {
        "BIRTH": 5,
        "CONFIRMED": 10,
        "SURVIVING": 15,
        "EXPANDING": 20,
        "MATURING": 10,
        "DISTRIBUTION_RISK": -20,
        "FAILED": -50,
        "CLOSED": -100,
    }

    def rank(self, campaigns):
        ranked = []

        for campaign in campaigns:
            ucr = float(campaign.get("ucr_score", 0))
            ods = float(campaign.get("ods_score", 0)) * 100.0
            survival = float(campaign.get("csd_score", 0)) * 100.0
            mta = float(campaign.get("mta_score", 0))
            mta = ((max(-1.0, min(1.0, mta)) + 1.0) / 2.0) * 100.0

            state = str(
                campaign.get("campaign_state", campaign.get("state", "UNKNOWN"))
            ).upper()

            state_bonus = self.STATE_BONUS.get(state, 0)

            composite_score = round(
                (ucr * 0.50)
                + (ods * 0.20)
                + (survival * 0.15)
                + (mta * 0.15)
                + state_bonus,
                2,
            )

            record = dict(campaign)
            record["composite_rank_score"] = composite_score
            ranked.append(record)

        ranked.sort(
            key=lambda x: x.get("composite_rank_score", 0),
            reverse=True,
        )

        for idx, row in enumerate(ranked, start=1):
            row["rank"] = idx

        return ranked
