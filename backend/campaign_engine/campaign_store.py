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
        # FIX (2026-07-29): user-reported production OOM crashes, traced
        # (via live memory instrumentation) to this. Previously called
        # get_active_campaigns() with NO limit at all -- fetching every
        # column (including the bulky evidence blob) for every single
        # active campaign (all ~280 of them), over the network, fully
        # deserialized into Python objects, THEN sliced down to the
        # requested `limit` client-side afterward, after already paying
        # the full cost for all ~280.
        #
        # Simply pushing .limit() into the query instead would have been
        # a correctness bug: campaigns aren't sorted by score at the
        # database level, so an unordered LIMIT would return an arbitrary
        # ~100 rows, not the true top 100 by score -- silently wrong
        # "rankings" data, not just a performance fix.
        #
        # Correct fix: two-step fetch. First, a lightweight query for
        # only the columns needed to rank (excluding evidence and other
        # bulky fields) across the FULL active set -- cheap, since it
        # skips the large blob entirely. Determine the true top `limit`
        # campaign_ids from that. Then a second, targeted query fetching
        # full data (including evidence, genuinely needed as input for
        # the weis-gamma summary computation) for ONLY those `limit`
        # campaign_ids, instead of all ~280.
        if not self.client:
            return []

        try:
            light_result = (
                self.client
                .table(CAMPAIGN_TABLE)
                .select("campaign_id,ucr_score,ods_score")
                .in_(
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
                .execute()
            )
        except Exception:
            # If the lightweight query fails for any reason (e.g. a
            # column name mismatch on some deployment), fall back to the
            # previous, safe-but-heavier behavior rather than returning
            # nothing.
            return self.get_active_campaigns()[:limit]

        light_rows = light_result.data or []

        if not light_rows:
            return []

        ranked_ids = [
            row.get("campaign_id")
            for row in sorted(
                light_rows,
                key=lambda x: float(x.get("ucr_score") or x.get("ods_score") or 0),
                reverse=True,
            )[:limit]
            if row.get("campaign_id") is not None
        ]

        if not ranked_ids:
            return []

        full_result = (
            self.client
            .table(CAMPAIGN_TABLE)
            .select("*")
            .in_("campaign_id", ranked_ids)
            .execute()
        )
        full_rows = full_result.data or []

        # Preserve the exact ranked order determined above -- the second
        # query's row order isn't guaranteed to match ranked_ids' order.
        by_id = {row.get("campaign_id"): row for row in full_rows}
        return [by_id[cid] for cid in ranked_ids if cid in by_id]