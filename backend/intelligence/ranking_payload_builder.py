class RankingPayloadBuilder:
    """
    Normalizes campaign records for ranking tables.
    """

    def build(self, campaigns):
        normalized = []
        for c in campaigns or []:
            normalized.append({
                "symbol": c.get("symbol"),
                "campaign_id": c.get("campaign_id"),
                "campaign_state": c.get("campaign_state", c.get("state")),
                "ucr_score": c.get("ucr_score", c.get("master_score", 0)),
                "tier": c.get("tier", "UNRANKED"),
                "action": c.get("action", c.get("decision", "WATCH")),
            })

        return sorted(normalized, key=lambda x: float(x.get("ucr_score", 0) or 0), reverse=True)

