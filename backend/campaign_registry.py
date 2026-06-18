
"""
SAVE AS:
campaign_engine/campaign_registry.py

Central registry for active campaign tracking.
"""

from typing import Dict, List, Optional


class CampaignRegistry:

    def __init__(self):
        self._campaigns: Dict[str, dict] = {}

    def register(
        self,
        campaign_id: str,
        campaign_payload: dict,
    ) -> None:

        self._campaigns[campaign_id] = campaign_payload

    def exists(
        self,
        campaign_id: str,
    ) -> bool:

        return campaign_id in self._campaigns

    def get(
        self,
        campaign_id: str,
    ) -> Optional[dict]:

        return self._campaigns.get(campaign_id)

    def remove(
        self,
        campaign_id: str,
    ) -> None:

        self._campaigns.pop(
            campaign_id,
            None,
        )

    def all_campaigns(
        self,
    ) -> List[dict]:

        return list(
            self._campaigns.values()
        )

    def active_campaigns(
        self,
    ) -> List[dict]:

        active = []

        for campaign in self._campaigns.values():

            state = str(
                campaign.get(
                    "campaign_state",
                    ""
                )
            ).upper()

            if state not in [
                "FAILED",
                "CLOSED",
            ]:
                active.append(campaign)

        return active

    def count(self) -> int:

        return len(
            self._campaigns
        )
