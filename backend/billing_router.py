# Copyright (c) 2026 Sigmalytic Quant Corporation. All rights reserved.
"""
backend/billing_router.py
--------------------------
Full Stripe billing backend.
Replaces billing_stub.py entirely.

Endpoints:
  POST /api/v1/billing/webhook           — Stripe webhook receiver
  GET  /api/v1/billing/{user_id}         — fetch billing state from Supabase
  POST /api/v1/billing/{user_id}/upgrade — create Stripe checkout session
  POST /api/billing/portal               — customer portal session
  GET  /api/billing/config               — public Stripe config
"""

import os
import logging
import stripe
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger("billing_router")

# ── Stripe config ──────────────────────────────────────────────────────────────
stripe.api_key         = os.getenv("STRIPE_SECRET_KEY",   "")
STRIPE_WEBHOOK_SECRET  = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")

PRICE_TRADER       = os.getenv("STRIPE_PRICE_TRADER",       "price_1Tc2DvDRUJk6Un01MwT2Z1l0")
PRICE_ELITE_TRADER = os.getenv("STRIPE_PRICE_ELITE_TRADER", "price_1Tc2IQDRUJk6Un01l7qEuD0l")

PRICE_TO_TIER = {
    PRICE_TRADER:       "trader",
    PRICE_ELITE_TRADER: "elite_trader",
}

FRONTEND_URL = os.getenv("FRONTEND_URL", "https://sigmalytic-frontend.onrender.com")

# ── Tier definitions ───────────────────────────────────────────────────────────
TIER_NAMES = {
    "free":          "Free",
    "trader":        "Trader",
    "elite_trader":  "Elite Trader",
    "institutional": "Institutional",
}

TIER_PRICES = {
    "free":          "$0",
    "trader":        "$49/mo",
    "elite_trader":  "$129/mo",
    "institutional": "Contact Us",
}

TIER_FEATURES = {
    "free": {
        "live_data":    False,
        "alerts":       False,
        "intelligence": False,
        "radar_limit":  50,
        "sms_limit":    0,
    },
    "trader": {
        "live_data":    True,
        "alerts":       True,
        "intelligence": False,
        "radar_limit":  1403,
        "sms_limit":    20,
    },
    "elite_trader": {
        "live_data":    True,
        "alerts":       True,
        "intelligence": True,
        "radar_limit":  1403,
        "sms_limit":    -1,
    },
    "institutional": {
        "live_data":    True,
        "alerts":       True,
        "intelligence": True,
        "radar_limit":  1403,
        "sms_limit":    -1,
    },
}

# ── Supabase client ────────────────────────────────────────────────────────────
def _get_supabase():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)

# ── Router ─────────────────────────────────────────────────────────────────────
billing_router = APIRouter(tags=["billing"])

class UpgradeRequest(BaseModel):
    price_id:   str
    user_id:    str
    user_email: str

class PortalRequest(BaseModel):
    user_id: str

# ── Helpers ────────────────────────────────────────────────────────────────────
def _upsert_subscription(user_id: str, data: dict):
    try:
        sb = _get_supabase()
        data["user_id"]    = user_id
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        sb.table("user_subscriptions").upsert(data, on_conflict="user_id").execute()
        log.info(f"[BILLING] Upserted {user_id}: {data}")
    except Exception as e:
        log.error(f"[BILLING] Supabase upsert failed for {user_id}: {e}")


def _get_subscription(user_id: str) -> dict:
    try:
        sb = _get_supabase()
        r  = sb.table("user_subscriptions").select("*").eq("user_id", user_id).single().execute()
        return r.data or {}
    except Exception:
        return {}


# ── GET /api/v1/billing/{user_id} ─────────────────────────────────────────────
@billing_router.get("/api/v1/billing/{user_id}")
async def get_billing(user_id: str):
    data = _get_subscription(user_id)
    tier = data.get("tier", "free") if data else "free"

    period_end = data.get("current_period_end") if data else None

    return {
        "user_id":              user_id,
        "tier":                 tier,
        "plan_name":            TIER_NAMES.get(tier, "Free"),
        "plan_price":           TIER_PRICES.get(tier, "$0"),
        "features":             TIER_FEATURES.get(tier, TIER_FEATURES["free"]),
        "status":               data.get("status", "active") if data else "active",
        "current_period_end":   period_end,
        "cancel_at_period_end": data.get("cancel_at_period_end", False) if data else False,
        "stripe_customer_id":   data.get("stripe_customer_id") if data else None,
        "publishable_key":      STRIPE_PUBLISHABLE_KEY,
    }


# ── POST /api/v1/billing/webhook ──────────────────────────────────────────────
@billing_router.post("/api/v1/billing/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()

    if not STRIPE_WEBHOOK_SECRET:
        log.warning("[BILLING] STRIPE_WEBHOOK_SECRET not set")
        return JSONResponse({"status": "ok"})

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as e:
        log.error(f"[BILLING] Webhook signature failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")

    import json as _json
    raw       = _json.loads(payload)
    data      = raw["data"]["object"]
    event_type= event["type"]
    log.info(f"[BILLING] Webhook: {event_type}")

    if event_type == "checkout.session.completed":
        metadata    = data.get("metadata") or {}
        user_id     = dict(metadata).get("user_id", "") or data.get("client_reference_id", "")
        customer_id = data.get("customer", "")
        sub_id      = data.get("subscription", "")

        if not user_id:
            log.error(f"[BILLING] No user_id for checkout — customer: {customer_id}")
            return JSONResponse({"status": "ok", "warning": "no user_id"})

        if sub_id:
            try:
                sub        = stripe.Subscription.retrieve(sub_id)
                price_id   = sub["items"]["data"][0]["price"]["id"]
                period_end = datetime.fromtimestamp(sub["current_period_end"], tz=timezone.utc).isoformat()
                tier       = PRICE_TO_TIER.get(price_id, "trader")
                _upsert_subscription(user_id, {
                    "tier": tier, "stripe_customer_id": customer_id,
                    "stripe_subscription_id": sub_id, "status": "active",
                    "current_period_end": period_end, "cancel_at_period_end": False,
                })
                log.info(f"[BILLING] Activated: {user_id} -> {tier}")
            except Exception as e:
                log.error(f"[BILLING] Sub lookup failed: {e}")

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer", "")
        price_id    = data["items"]["data"][0]["price"]["id"]
        period_end  = datetime.fromtimestamp(data["current_period_end"], tz=timezone.utc).isoformat()
        tier        = PRICE_TO_TIER.get(price_id, "trader")
        try:
            sb      = _get_supabase()
            r       = sb.table("user_subscriptions").select("user_id").eq("stripe_customer_id", customer_id).single().execute()
            user_id = r.data.get("user_id", "") if r.data else ""
        except Exception:
            user_id = ""
        if user_id:
            _upsert_subscription(user_id, {
                "tier": tier, "stripe_customer_id": customer_id,
                "stripe_subscription_id": data.get("id", ""),
                "status": data.get("status", "active"),
                "current_period_end": period_end,
                "cancel_at_period_end": data.get("cancel_at_period_end", False),
            })

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer", "")
        try:
            sb      = _get_supabase()
            r       = sb.table("user_subscriptions").select("user_id").eq("stripe_customer_id", customer_id).single().execute()
            user_id = r.data.get("user_id", "") if r.data else ""
        except Exception:
            user_id = ""
        if user_id:
            _upsert_subscription(user_id, {"tier": "free", "status": "cancelled", "stripe_customer_id": customer_id})

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer", "")
        try:
            sb      = _get_supabase()
            r       = sb.table("user_subscriptions").select("user_id").eq("stripe_customer_id", customer_id).single().execute()
            user_id = r.data.get("user_id", "") if r.data else ""
        except Exception:
            user_id = ""
        if user_id:
            _upsert_subscription(user_id, {"status": "past_due", "stripe_customer_id": customer_id})

    return JSONResponse({"status": "ok"})


# ── POST /api/v1/billing/{user_id}/upgrade ────────────────────────────────────
@billing_router.post("/api/v1/billing/{user_id}/upgrade")
async def create_checkout(user_id: str, payload: UpgradeRequest):
    if not stripe.api_key:
        raise HTTPException(status_code=500, detail="Stripe not configured")
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": payload.price_id, "quantity": 1}],
            customer_email=payload.user_email,
            metadata={"user_id": user_id},
            success_url=f"{FRONTEND_URL}?billing=success",
            cancel_url=f"{FRONTEND_URL}?billing=cancelled",
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── POST /api/billing/portal ──────────────────────────────────────────────────
@billing_router.post("/api/billing/portal")
async def customer_portal(payload: PortalRequest):
    data        = _get_subscription(payload.user_id)
    customer_id = data.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=404, detail="No Stripe customer found")
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{FRONTEND_URL}?billing=portal_return",
        )
        return {"portal_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── GET /api/billing/config ───────────────────────────────────────────────────
@billing_router.get("/api/billing/config")
async def billing_config():
    return {
        "publishable_key":    STRIPE_PUBLISHABLE_KEY,
        "price_trader":       PRICE_TRADER,
        "price_elite_trader": PRICE_ELITE_TRADER,
    }
