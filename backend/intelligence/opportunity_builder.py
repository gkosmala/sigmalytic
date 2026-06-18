class OpportunityBuilder:
    """
    Converts scored campaign records into frontend opportunity rows.
    """

    def build(self, campaigns):
        rows = []
        for c in campaigns or []:
            rows.append({
                "symbol": c.get("symbol"),
                "ucr_score": c.get("ucr_score", c.get("master_score", 0)),
                "confidence": c.get("confidence", "MEDIUM"),
                "conservative_target": c.get("conservative_target", 0),
                "aggressive_target": c.get("aggressive_target", 0),
                "campaign_state": c.get("campaign_state", c.get("state")),
            })
        return rows
