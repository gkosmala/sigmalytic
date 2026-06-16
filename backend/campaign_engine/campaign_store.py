# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/campaign_store.py
--------------------------
Layer 2 — Supabase persistence layer for the Campaign Engine.

Matches the raw-requests pattern established in supabase_bars.py.
No supabase-py client used — all calls go directly to the REST API.

Tables consumed (defined in 001_campaign_core_schema.sql +
                              002_campaign_state_machine.sql):
  campaigns               — one row per campaign
  campaign_observations   — one row per campaign per day
  campaign_state_history  — one row per state transition

CLAUDE.md compliance
--------------------
• Credentials via os.environ only — SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
• All numeric values stored/retrieved as Decimal
• Full type hints
• Structured try/except throughout
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import requests

# Campaign domain objects live in the engine layer (Layer 3).
# Imported here only for type hints — no circular dependency because
# campaign_engine imports campaign_store, not the reverse.
from campaign_engine.campaign_state_engine import (
    Campaign,
    CampaignState,
    DailyBar,
    WyckoffSignals,
)

log = logging.getLogger("campaign_store")

# ---------------------------------------------------------------------------
# Supabase connection helpers
# ---------------------------------------------------------------------------

_REQUEST_TIMEOUT: int = 30   # seconds
_BATCH_SIZE:      int = 500  # rows per upsert call


def _supabase_url() -> str:
    url = os.environ.get("SUPABASE_URL", "")
    if not url:
        raise EnvironmentError("SUPABASE_URL is not set")
    return url.rstrip("/")


def _supabase_key() -> str:
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY", "")
    )
    if not key:
        raise EnvironmentError(
            "Neither SUPABASE_SERVICE_ROLE_KEY nor SUPABASE_ANON_KEY is set"
        )
    return key


def _headers(prefer: str = "") -> dict[str, str]:
    h = {
        "apikey":        _supabase_key(),
        "Authorization": f"Bearer {_supabase_key()}",
        "Content-Type":  "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _endpoint(table: str) -> str:
    return f"{_supabase_url()}/rest/v1/{table}"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _to_decimal(value: Any) -> Decimal:
    """Safely convert a DB value (str, int, float, None) to Decimal."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _campaign_to_row(campaign: Campaign) -> dict:
    """Serialise a Campaign object to a campaigns-table row dict."""
    return {
        # campaign_id is BIGSERIAL in the DB; omit on insert, include on update.
        # We store the Python UUID in display_label for cross-reference.
        "display_label":        campaign.campaign_id,
        "symbol":               campaign.symbol,
        "timeframe":            "DAILY",
        "birth_date":           campaign.birth_date.isoformat(),
        "campaign_age_days":    campaign.days_open,
        "current_state":        campaign.state.value,
        "state_enum":           campaign.state.value,
        "operator_dominance":   None,   # populated by Operator Dominance Engine later
        "distribution_risk":    None,   # populated by distribution monitor later
        "historical_confidence": campaign.tier,
        "status":               "CLOSED" if campaign.state == CampaignState.CLOSED else "ACTIVE",
        "close_reason":         _map_close_reason(campaign.close_reason),
        "close_notes":          campaign.close_reason,
        "closed_at":            datetime.utcnow().isoformat() if campaign.state == CampaignState.CLOSED else None,
        "updated_at":           datetime.utcnow().isoformat(),
    }


def _row_to_campaign(row: dict) -> Campaign:
    """Deserialise a campaigns-table row back into a Campaign object."""
    state_value = row.get("state_enum") or row.get("current_state") or "BIRTH"
    try:
        state = CampaignState(state_value)
    except ValueError:
        state = CampaignState.BIRTH

    birth_raw = row.get("birth_date", "")
    try:
        birth = date.fromisoformat(str(birth_raw)[:10])
    except (ValueError, TypeError):
        birth = date.today()

    return Campaign(
        campaign_id    = row.get("display_label") or str(row.get("campaign_id", "")),
        symbol         = row.get("symbol", ""),
        birth_date     = birth,
        state          = state,
        entry_price    = _to_decimal(row.get("entry_price")),
        stop_price     = _to_decimal(row.get("stop_price")),
        pnf_target     = _to_decimal(row.get("pnf_target")),
        current_price  = _to_decimal(row.get("current_price")),
        tier           = row.get("historical_confidence") or "TIER_1",
        mfe90_expected = _to_decimal(row.get("mfe90_expected")),
        obstacle_score = _to_decimal(row.get("obstacle_score")),
        progress_score = _to_decimal(row.get("progress_score")),
        d_score        = _to_decimal(row.get("d_score")),
        duration_days  = int(row.get("duration_days") or 0),
        asym_ratio     = _to_decimal(row.get("asym_ratio") or "1"),
        layer          = row.get("layer") or "A",
        close_reason   = row.get("close_notes"),
        days_open      = int(row.get("campaign_age_days") or 0),
        state_history  = [],   # loaded separately if needed
    )


def _map_close_reason(reason: Optional[str]) -> Optional[str]:
    """Map a free-text close reason to the campaign_close_reason enum."""
    if not reason:
        return None
    r = reason.upper()
    if "STOP" in r:
        return "STOP_HIT"
    if "TARGET" in r or "P&F" in r:
        return "TARGET_REACHED"
    if "CHOCH" in r or "OPERATOR" in r:
        return "OPERATOR_EXIT"
    if "EXPIR" in r or "90" in r or "TIMEOUT" in r:
        return "TIMEOUT"
    if "INVALID" in r:
        return "INVALIDATED"
    return "MANUAL"


# ---------------------------------------------------------------------------
# CampaignStore
# ---------------------------------------------------------------------------

class CampaignStore:
    """
    Supabase persistence layer for Campaign objects.

    All methods are async-compatible via asyncio.to_thread when called
    from the async campaign engine.  The underlying HTTP calls use the
    synchronous requests library (same pattern as supabase_bars.py).
    """

    # ------------------------------------------------------------------ #
    #  Single campaign operations                                          #
    # ------------------------------------------------------------------ #

    async def upsert_campaign(self, campaign: Campaign) -> None:
        """
        Insert or update a single campaign row.
        Uses display_label (Python UUID) as the upsert key so the
        BIGSERIAL campaign_id is never overwritten.
        """
        import asyncio
        await asyncio.to_thread(self._upsert_campaign_sync, campaign)

    def _upsert_campaign_sync(self, campaign: Campaign) -> None:
        row = _campaign_to_row(campaign)
        try:
            r = requests.post(
                _endpoint("campaigns"),
                headers=_headers("resolution=merge-duplicates,return=minimal"),
                json=row,
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code not in (200, 201):
                log.error(
                    "upsert_campaign failed for %s: %s %s",
                    campaign.symbol, r.status_code, r.text[:300],
                )
            else:
                log.debug("upsert_campaign OK — %s %s", campaign.symbol, campaign.state.value)
        except requests.RequestException as exc:
            log.error("upsert_campaign request error for %s: %s", campaign.symbol, exc)
            raise

    async def fetch_campaign(self, campaign_id: str) -> Campaign:
        """Fetch a single campaign by its Python UUID (stored in display_label)."""
        import asyncio
        return await asyncio.to_thread(self._fetch_campaign_sync, campaign_id)

    def _fetch_campaign_sync(self, campaign_id: str) -> Campaign:
        try:
            r = requests.get(
                _endpoint("campaigns"),
                headers=_headers(),
                params={
                    "select":        "*",
                    "display_label": f"eq.{campaign_id}",
                    "limit":         "1",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                raise RuntimeError(
                    f"fetch_campaign HTTP {r.status_code}: {r.text[:200]}"
                )
            rows = r.json()
            if not rows:
                raise KeyError(f"Campaign not found: {campaign_id}")
            return _row_to_campaign(rows[0])
        except requests.RequestException as exc:
            log.error("fetch_campaign request error for %s: %s", campaign_id, exc)
            raise

    # ------------------------------------------------------------------ #
    #  Bulk operations (nightly cycle)                                     #
    # ------------------------------------------------------------------ #

    async def fetch_active_campaigns(self) -> list[Campaign]:
        """Return all campaigns with status = ACTIVE."""
        import asyncio
        return await asyncio.to_thread(self._fetch_active_campaigns_sync)

    def _fetch_active_campaigns_sync(self) -> list[Campaign]:
        campaigns: list[Campaign] = []
        page_size = 1000
        offset    = 0

        while True:
            try:
                r = requests.get(
                    _endpoint("campaigns"),
                    headers={
                        **_headers(),
                        "Range-Unit": "items",
                        "Range":      f"{offset}-{offset + page_size - 1}",
                    },
                    params={
                        "select": "*",
                        "status": "eq.ACTIVE",
                        "order":  "campaign_id.asc",
                    },
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code not in (200, 206):
                    log.error(
                        "fetch_active_campaigns HTTP %s: %s",
                        r.status_code, r.text[:200],
                    )
                    break

                batch = r.json()
                if not batch:
                    break

                campaigns.extend(_row_to_campaign(row) for row in batch)
                offset += len(batch)

                if len(batch) < page_size:
                    break

            except requests.RequestException as exc:
                log.error("fetch_active_campaigns request error at offset %d: %s", offset, exc)
                break

        log.info("fetch_active_campaigns — %d active campaigns loaded", len(campaigns))
        return campaigns

    async def bulk_upsert_campaigns(self, campaigns: list[Campaign]) -> int:
        """
        Upsert a list of Campaign objects in batches.
        Returns the total number of rows successfully written.
        """
        import asyncio
        return await asyncio.to_thread(self._bulk_upsert_campaigns_sync, campaigns)

    def _bulk_upsert_campaigns_sync(self, campaigns: list[Campaign]) -> int:
        rows          = [_campaign_to_row(c) for c in campaigns]
        total_written = 0
        errors        = 0

        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i : i + _BATCH_SIZE]
            try:
                r = requests.post(
                    _endpoint("campaigns"),
                    headers=_headers("resolution=merge-duplicates,return=minimal"),
                    json=batch,
                    timeout=_REQUEST_TIMEOUT,
                )
                if r.status_code in (200, 201):
                    total_written += len(batch)
                else:
                    log.error(
                        "bulk_upsert_campaigns batch %d HTTP %s: %s",
                        i // _BATCH_SIZE, r.status_code, r.text[:200],
                    )
                    errors += 1
            except requests.RequestException as exc:
                log.error("bulk_upsert_campaigns batch %d error: %s", i // _BATCH_SIZE, exc)
                errors += 1

        log.info(
            "bulk_upsert_campaigns — %d/%d rows written (%d errors)",
            total_written, len(rows), errors,
        )
        return total_written

    # ------------------------------------------------------------------ #
    #  Daily observations                                                  #
    # ------------------------------------------------------------------ #

    async def insert_observation(
        self,
        campaign:  Campaign,
        db_campaign_id: int,
        signals:   WyckoffSignals,
        bar:       DailyBar,
    ) -> None:
        """
        Write one campaign_observations row for today.
        Called after the FSM has evaluated the day's signals.
        """
        import asyncio
        await asyncio.to_thread(
            self._insert_observation_sync,
            campaign, db_campaign_id, signals, bar,
        )

    def _insert_observation_sync(
        self,
        campaign:       Campaign,
        db_campaign_id: int,
        signals:        WyckoffSignals,
        bar:            DailyBar,
    ) -> None:
        row = {
            "campaign_id":        db_campaign_id,
            "observation_date":   bar.bar_date.isoformat(),
            "state_classification": campaign.state.value,
            "spd_flag":           signals.spd,
            "dei_flag":           signals.dei,
            "wed_score":          str(signals.wed_count),
            "operator_dominance": None,
            "distribution_risk":  None,
            "created_at":         datetime.utcnow().isoformat(),
        }
        try:
            r = requests.post(
                _endpoint("campaign_observations"),
                headers=_headers("return=minimal"),
                json=row,
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code not in (200, 201):
                log.error(
                    "insert_observation HTTP %s for campaign %s: %s",
                    r.status_code, campaign.campaign_id, r.text[:200],
                )
        except requests.RequestException as exc:
            log.error("insert_observation error for %s: %s", campaign.campaign_id, exc)

    # ------------------------------------------------------------------ #
    #  State history                                                       #
    # ------------------------------------------------------------------ #

    async def insert_state_transition(
        self,
        db_campaign_id: int,
        prior_state:    CampaignState,
        new_state:      CampaignState,
        reason:         str,
    ) -> None:
        """Write one campaign_state_history row for a state transition."""
        import asyncio
        await asyncio.to_thread(
            self._insert_state_transition_sync,
            db_campaign_id, prior_state, new_state, reason,
        )

    def _insert_state_transition_sync(
        self,
        db_campaign_id: int,
        prior_state:    CampaignState,
        new_state:      CampaignState,
        reason:         str,
    ) -> None:
        row = {
            "campaign_id":      db_campaign_id,
            "transition_date":  date.today().isoformat(),
            "prior_state":      prior_state.value,
            "new_state":        new_state.value,
            "prior_state_enum": prior_state.value,
            "new_state_enum":   new_state.value,
            "transition_reason": reason,
            "created_at":       datetime.utcnow().isoformat(),
        }
        try:
            r = requests.post(
                _endpoint("campaign_state_history"),
                headers=_headers("return=minimal"),
                json=row,
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code not in (200, 201):
                log.error(
                    "insert_state_transition HTTP %s: %s",
                    r.status_code, r.text[:200],
                )
        except requests.RequestException as exc:
            log.error("insert_state_transition error: %s", exc)

    # ------------------------------------------------------------------ #
    #  Lookup helper — DB integer ID from display_label                   #
    # ------------------------------------------------------------------ #

    async def get_db_id(self, campaign_id: str) -> Optional[int]:
        """
        Return the BIGSERIAL campaign_id from the DB for a given
        Python UUID (display_label).  Returns None if not found.
        """
        import asyncio
        return await asyncio.to_thread(self._get_db_id_sync, campaign_id)

    def _get_db_id_sync(self, campaign_id: str) -> Optional[int]:
        try:
            r = requests.get(
                _endpoint("campaigns"),
                headers=_headers(),
                params={
                    "select":        "campaign_id",
                    "display_label": f"eq.{campaign_id}",
                    "limit":         "1",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            if r.status_code != 200 or not r.json():
                return None
            return int(r.json()[0]["campaign_id"])
        except (requests.RequestException, KeyError, ValueError) as exc:
            log.error("get_db_id error for %s: %s", campaign_id, exc)
            return None

    # ------------------------------------------------------------------ #
    #  Health check                                                        #
    # ------------------------------------------------------------------ #

    def health_check(self) -> dict:
        """Quick connectivity check — used by the /health endpoint."""
        try:
            r = requests.get(
                _endpoint("campaigns"),
                headers={**_headers(), "Prefer": "count=exact"},
                params={"select": "campaign_id", "limit": "1"},
                timeout=10,
            )
            content_range = r.headers.get("Content-Range", "0/0")
            total = int(content_range.split("/")[-1]) if "/" in content_range else 0
            return {
                "connected":        r.status_code == 200,
                "active_campaigns": total,
            }
        except Exception as exc:
            return {"connected": False, "error": str(exc)}
