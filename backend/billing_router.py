"""
backend/billing_router.py
--------------------------
Sigmalytic — Full Stripe Billing Integration

Endpoints:
  GET  /api/v1/billing/{user_id}           — get user subscription state
  POST /api/v1/billing/{user_id}/portal    — create Stripe customer portal session
  POST /api/v1/billing/webhook             — handle Stripe webhook events

Plans:
  free          — $0, limited access
  trader        — $49/month
  elite_trader  — $129/month
  institutional — contact us

Supabase table: user_subscriptions
"""

from __future__ import annotations
import os
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import stripe
import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

log = logging.getLogger("billing")

# ── Stripe config ──────────────────────────────────────────────────────────────
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
DATABASE_URL           = os.getenv("DATABASE_URL", "")
FRONTEND_URL           = os.getenv("FRONTEND_URL", "https://sigmalytic-frontend.onrender.com")

# ── Plan mapping (Stripe price IDs → internal tier names) ─────────────────────
# Fill these in from your Stripe dashboard → Products → Price ID
PRICE_TO_TIER = {
    "price_1Tc2DvDRUJk6Un01MwT2Z1l0": "trader",
    "price_1Tc2IQDRUJk6Un01l7qEuD0l": "elite_trader",
}

TIER_FEATURES = {
    "free": {
        "name"          : "Free",
        "price"         : "$0",
        "radar_limit"   : 50,
        "live_data"     : False,
        "alerts"        : False,
        "intelligence"  : False,
        "sms_limit"     : 0,
    },
    "trader": {
        "name"          : "Trader",
        "price"         : "$49/mo",
        "radar_limit"   : 1403,
        "live_data"     : True,
        "alerts"        : True,
        "intelligence"  : False,
        "sms_limit"     : 20,
    },
    "elite_trader": {
        "name"          : "Elite Trader",
        "price"         : "$129/mo",
        "radar_limit"   : 1403,
        "live_data"     : True,
        "alerts"        : True,
        "intelligence"  : True,
        "sms_limit"     : -1,  # unlimited
    },
    "institutional": {
        "name"          : "Institutional",
        "price"         : "Contact Us",
        "radar_limit"   : 1403,
        "live_data"     : True,
        "alerts"        : True,
        "intelligence"  : True,
        "sms_limit"     : -1,
    },
}

billing_router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _get_conn():
    if not DATABASE_URL:
        raise HTTPException(503, "Database not configured")
    return psycopg2.connect(DATABASE_URL)


def _get_subscription(user_id: str) -> dict:
    """Get user subscription from Supabase. Returns free tier if not found."""
    default = {
        "user_id"              : user_id,
        "tier"                 : "free",
        "stripe_customer_id"   : None,
        "stripe_subscription_id": None,
        "status"               : "active",
        "current_period_end"   : None,
        "cancel_at_period_end" : False,
    }
    if not DATABASE_URL:
        return default
    try:
        conn = _get_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT * FROM user_subscriptions WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else default
    except Exception as e:
        log.warning(f"Get subscription error: {e}")
        return default


def _upsert_subscription(data: dict):
    """Write subscription state to Supabase."""
    if not DATABASE_URL:
        return
    try:
        conn = _get_conn()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO user_subscriptions
            (user_id, tier, stripe_customer_id, stripe_subscription_id,
             status, current_period_end, cancel_at_period_end, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO UPDATE SET
                tier                    = EXCLUDED.tier,
                stripe_customer_id      = EXCLUDED.stripe_customer_id,
                stripe_subscription_id  = EXCLUDED.stripe_subscription_id,
                status                  = EXCLUDED.status,
                current_period_end      = EXCLUDED.current_period_end,
                cancel_at_period_end    = EXCLUDED.cancel_at_period_end,
                updated_at              = EXCLUDED.updated_at
        """, (
            data["user_id"],
            data.get("tier", "free"),
            data.get("stripe_customer_id"),
            data.get("stripe_subscription_id"),
            data.get("status", "active"),
            data.get("current_period_end"),
            data.get("cancel_at_period_end", False),
            datetime.now(timezone.utc),
        ))
        conn.commit()
        cur.close()
        conn.close()
        log.info(f"Subscription updated: {data['user_id']} → {data.get('tier')}")
    except Exception as e:
        log.warning(f"Upsert subscription error: {e}")


def _get_user_id_by_customer(stripe_customer_id: str) -> Optional[str]:
    """Look up user_id from stripe_customer_id."""
    if not DATABASE_URL:
        return None
    try:
        conn = _get_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT user_id FROM user_subscriptions WHERE stripe_customer_id = %s",
            (stripe_customer_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def _tier_from_price_id(price_id: str) -> str:
    """Map Stripe price ID to internal tier name."""
    return PRICE_TO_TIER.get(price_id, "trader")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@billing_router.get("/{user_id}")
def get_billing(user_id: str):
    """Returns subscription state + feature flags for a user."""
    sub     = _get_subscription(user_id)
    tier    = sub.get("tier", "free")
    features= TIER_FEATURES.get(tier, TIER_FEATURES["free"])

    period_end = sub.get("current_period_end")
    if period_end and hasattr(period_end, 'strftime'):
        period_end = period_end.strftime("%Y-%m-%d")
    elif isinstance(period_end, (int, float)):
        period_end = datetime.fromtimestamp(period_end).strftime("%Y-%m-%d")

    return {
        "user_id"              : user_id,
        "tier"                 : tier,
        "plan_name"            : features["name"],
        "plan_price"           : features["price"],
        "status"               : sub.get("status", "active"),
        "current_period_end"   : period_end,
        "cancel_at_period_end" : sub.get("cancel_at_period_end", False),
        "stripe_customer_id"   : sub.get("stripe_customer_id"),
        # Feature flags
        "features"             : features,
        "radar_limit"          : features["radar_limit"],
        "live_data"            : features["live_data"],
        "alerts_enabled"       : features["alerts"],
        "intelligence_enabled" : features["intelligence"],
        "sms_limit"            : features["sms_limit"],
        # Publishable key for frontend
        "publishable_key"      : STRIPE_PUBLISHABLE_KEY,
    }


@billing_router.post("/{user_id}/portal")
def create_portal_session(user_id: str):
    """Creates a Stripe Customer Portal session for plan management."""
    if not stripe.api_key:
        raise HTTPException(503, "Stripe not configured")

    sub = _get_subscription(user_id)
    customer_id = sub.get("stripe_customer_id")

    if not customer_id:
        raise HTTPException(404, "No Stripe customer found — subscribe first")

    try:
        session = stripe.billing_portal.Session.create(
            customer   = customer_id,
            return_url = f"{FRONTEND_URL}",
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        raise HTTPException(400, str(e))


@billing_router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Handles Stripe webhook events.
    Updates user_subscriptions in Supabase on subscription changes.
    """
    payload   = await request.body()
    sig_header= request.headers.get("stripe-signature", "")

    if not STRIPE_WEBHOOK_SECRET:
        log.warning("Webhook received but STRIPE_WEBHOOK_SECRET not set")
        return Response(status_code=200)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except stripe.SignatureVerificationError:
        log.warning("Webhook signature verification failed")
        raise HTTPException(400, "Invalid signature")
    except Exception as e:
        raise HTTPException(400, str(e))

    event_type = event["type"]
    data       = event["data"]["object"]

    log.info(f"Stripe webhook: {event_type}")

    # ── checkout.session.completed ────────────────────────────────────────────
    if event_type == "checkout.session.completed":
        customer_id   = data.get("customer")
        subscription_id = data.get("subscription")
        client_ref_id = data.get("client_reference_id")  # user_id passed at checkout

        if client_ref_id and customer_id:
            # Get subscription details
            try:
                sub_obj  = stripe.Subscription.retrieve(subscription_id)
                price_id = sub_obj["items"]["data"][0]["price"]["id"]
                tier     = _tier_from_price_id(price_id)
                _upsert_subscription({
                    "user_id"              : client_ref_id,
                    "tier"                 : tier,
                    "stripe_customer_id"   : customer_id,
                    "stripe_subscription_id": subscription_id,
                    "status"               : sub_obj["status"],
                    "current_period_end"   : sub_obj["current_period_end"],
                    "cancel_at_period_end" : sub_obj["cancel_at_period_end"],
                })
                log.info(f"Checkout complete: {client_ref_id} → {tier}")
            except Exception as e:
                log.warning(f"Checkout subscription lookup error: {e}")

    # ── customer.subscription.created / updated ───────────────────────────────
    elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
        customer_id     = data.get("customer")
        subscription_id = data.get("id")
        status          = data.get("status")
        period_end      = data.get("current_period_end")
        cancel_at_end   = data.get("cancel_at_period_end", False)

        try:
            price_id = data["items"]["data"][0]["price"]["id"]
            tier     = _tier_from_price_id(price_id)
        except Exception:
            tier = "trader"

        # If subscription is past_due or canceled, downgrade
        if status in ("past_due", "unpaid"):
            tier = "free"
        elif status == "canceled":
            tier = "free"

        user_id = _get_user_id_by_customer(customer_id)
        if user_id:
            _upsert_subscription({
                "user_id"              : user_id,
                "tier"                 : tier,
                "stripe_customer_id"   : customer_id,
                "stripe_subscription_id": subscription_id,
                "status"               : status,
                "current_period_end"   : period_end,
                "cancel_at_period_end" : cancel_at_end,
            })

    # ── customer.subscription.deleted ────────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        user_id     = _get_user_id_by_customer(customer_id)
        if user_id:
            _upsert_subscription({
                "user_id"              : user_id,
                "tier"                 : "free",
                "stripe_customer_id"   : customer_id,
                "stripe_subscription_id": None,
                "status"               : "canceled",
                "current_period_end"   : None,
                "cancel_at_period_end" : False,
            })
            log.info(f"Subscription canceled: {user_id} → free")

    return Response(status_code=200)
