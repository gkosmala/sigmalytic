class StatusCenterBuilder:
    """
    Aggregates campaign counts for the Status Center.
    """

    def build(self, campaigns):
        campaigns = campaigns or []

        return {
            "active_campaigns": len([c for c in campaigns if c.get("campaign_state", c.get("state")) not in {"CLOSED", "FAILED"}]),
            "birth_candidates": len([c for c in campaigns if c.get("campaign_state", c.get("state")) == "BIRTH"]),
            "expanding_campaigns": len([c for c in campaigns if c.get("campaign_state", c.get("state")) == "EXPANDING"]),
            "distribution_risk": len([c for c in campaigns if c.get("campaign_state", c.get("state")) == "DISTRIBUTION_RISK"]),
        }
