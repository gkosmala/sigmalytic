class DashboardPayloadBuilder:
    """
    Builds the unified frontend dashboard response.
    """

    def build(self, rankings=None, status_center=None, opportunities=None, operator_dominance=None, research=None):
        return {
            "campaign_rankings": rankings or [],
            "status_center": status_center or {
                "active_campaigns": 0,
                "birth_candidates": 0,
                "expanding_campaigns": 0,
                "distribution_risk": 0,
            },
            "opportunities": opportunities or [],
            "operator_dominance": operator_dominance or {},
            "research": research or {},
        }

