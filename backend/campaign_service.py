class CampaignService:
    def evaluate(self, campaign=None):
        campaign = campaign or {}
        return {
            "symbol": campaign.get("symbol"),
            "campaign_state": campaign.get("campaign_state", campaign.get("state", "UNKNOWN")),
            "ucr_score": campaign.get("ucr_score", 0),
            "status": "evaluated"
        }

