"""
SAVE AS:
backend/campaign_engine/campaign_store.py
"""

import os
from typing import Any, Dict, List, Optional

from supabase import Client, create_client

CAMPAIGN_TABLE = "campaigns"


class CampaignStore:
    """
    Campaign persistence layer for Sigmalytic V2.
    """

    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
    ):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = (
            supabase_key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
        )

        self.client: Optional[Client] = None

        if self.supabase_url and self.supabase_key:
            self.client = create_client(
                self.supabase_url,
                self.supabase_key,
            )

    def configured(self) -> bool:
        return self.client is not None

    def save_campaign(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.client:
            return {"status": "NO_DATABASE"}

        return (
            self.client
            .table(CAMPAIGN_TABLE)
            .upsert(
                payload,
                on_conflict="symbol,timeframe",
            )
            .execute()
            .data
        )

    def get_campaign(self, campaign_id: str):
        if not self.client:
            return None

        result = (
            self.client
            .table(CAMPAIGN_TABLE)
            .select("*")
            .eq("campaign_id", campaign_id)
            .limit(1)
            .execute()
        )

        return result.data[0] if result.data else None

    def get_active_campaigns(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.client:
            return []

        query = (
            self.client
            .table(CAMPAIGN_TABLE)
            .select("*")
        )

        if symbol:
            query = query.eq("symbol", symbol.upper())

        if timeframe:
            query = query.eq("timeframe", timeframe.upper())

        query = query.in_(
            "current_state",
            [
                "BIRTH",
                "CONFIRMED",
                "SURVIVING",
                "EXPANDING",
                "MATURING",
                "DISTRIBUTION_RISK",
            ],
        )

        result = query.execute()
        campaigns = result.data or []

        return sorted(
            campaigns,
            key=lambda x: float(
                x.get("ucr_score")
                or x.get("ods_score")
                or 0
            ),
            reverse=True,
        )

    def close_campaign(self, campaign_id: str):
        if not self.client:
            return None

        return (
            self.client
            .table(CAMPAIGN_TABLE)
            .update({"current_state": "CLOSED"})
            .eq("campaign_id", campaign_id)
            .execute()
        )

    def get_top_campaigns(self, limit: int = 100) -> List[Dict[str, Any]]:
        campaigns = self.get_active_campaigns()
        return campaigns[:limit]