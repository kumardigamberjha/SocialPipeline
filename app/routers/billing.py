"""
Stripe billing endpoints: checkout, webhook, customer portal.

Handles subscription lifecycle for pro and enterprise tiers.
"""

import logging

import stripe
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import get_settings
from app.db import queries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

PLAN_LIMITS = {
    "free":       {"max_runs_per_month": 10},
    "pro":        {"max_runs_per_month": 100},
    "enterprise": {"max_runs_per_month": 999999},
}


def _get_stripe():
    """Configure and return the stripe module with the secret key."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe is not configured")
    stripe.api_key = settings.stripe_secret_key
    return stripe


# ── Models ──────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    tier: str  # "pro" or "enterprise"
    user_id: str
    success_url: str = "http://localhost:3000/billing/success"
    cancel_url: str = "http://localhost:3000/billing/cancel"


class PortalRequest(BaseModel):
    user_id: str
    return_url: str = "http://localhost:3000/dashboard"


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/checkout", summary="Create a Stripe Checkout Session")
async def create_checkout(req: CheckoutRequest):
    """
    Create a Stripe Checkout Session for upgrading to pro or enterprise.
    Returns the checkout URL for the client to redirect to.
    """
    s = _get_stripe()
    settings = get_settings()

    if req.tier == "pro":
        price_id = settings.stripe_pro_price_id
    elif req.tier == "enterprise":
        price_id = settings.stripe_enterprise_price_id
    else:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {req.tier}. Use 'pro' or 'enterprise'.")

    if not price_id:
        raise HTTPException(status_code=500, detail=f"Stripe price ID not configured for tier: {req.tier}")

    # Check if user already has a Stripe customer ID
    customer_id = None
    try:
        usage = queries.get_usage(req.user_id)
        if usage and usage.get("stripe_customer_id"):
            customer_id = usage["stripe_customer_id"]
    except Exception as e:
        logger.warning("Could not fetch existing Stripe customer from SQLite: %s", e)

    try:
        session_params = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": req.success_url + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": req.cancel_url,
            "metadata": {"user_id": req.user_id, "tier": req.tier},
            "subscription_data": {
                "metadata": {"user_id": req.user_id, "tier": req.tier},
            },
        }

        if customer_id:
            session_params["customer"] = customer_id
        else:
            session_params["customer_creation"] = "always"

        session = s.checkout.Session.create(**session_params)
        return {"checkout_url": session.url, "session_id": session.id}

    except s.error.StripeError as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message or str(e)}")


@router.post("/webhook", summary="Stripe webhook handler")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events for subscription lifecycle.

    Events handled:
        - checkout.session.completed  → upgrade user tier
        - customer.subscription.created → confirm subscription
        - invoice.paid               → confirm payment
        - customer.subscription.deleted → downgrade to free
    """
    s = _get_stripe()
    settings = get_settings()

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature")

    try:
        event = s.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except s.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    event_type = event["type"]
    data = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data)

    elif event_type == "customer.subscription.created":
        logger.info("Subscription created: %s", data.get("id"))

    elif event_type == "invoice.paid":
        logger.info("Invoice paid: %s", data.get("id"))

    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data)

    elif event_type == "invoice.payment_failed":
        logger.warning("Payment failed for subscription: %s", data.get("subscription"))

    return {"status": "ok"}


@router.get("/portal", summary="Create Stripe Customer Portal session")
async def create_portal(user_id: str, return_url: str = "http://localhost:3000/dashboard"):
    """
    Create a Stripe billing portal session for the user to manage their subscription.
    """
    s = _get_stripe()

    # Look up the user's Stripe customer ID
    try:
        usage = queries.get_usage(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not usage or not usage.get("stripe_customer_id"):
        raise HTTPException(status_code=404, detail="No Stripe customer found. Subscribe to a plan first.")

    customer_id = usage["stripe_customer_id"]

    try:
        session = s.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"portal_url": session.url}
    except s.error.StripeError as e:
        logger.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message or str(e)}")


# ── Internal Handlers ───────────────────────────────────────────────────────


async def _handle_checkout_completed(session_data: dict):
    """Upgrade user tier after successful checkout in SQLite."""
    metadata = session_data.get("metadata", {})
    user_id = metadata.get("user_id")
    tier = metadata.get("tier", "pro")
    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")

    if not user_id:
        logger.error("checkout.session.completed missing user_id in metadata")
        return

    plan_config = PLAN_LIMITS.get(tier, PLAN_LIMITS["pro"])

    from app.db.database import get_db
    try:
        db = get_db()
        db.execute(
            """
            INSERT INTO usage_limits (user_id, plan, max_runs_per_month, stripe_customer_id, stripe_subscription_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan = excluded.plan,
                max_runs_per_month = excluded.max_runs_per_month,
                stripe_customer_id = excluded.stripe_customer_id,
                stripe_subscription_id = excluded.stripe_subscription_id
            """,
            (user_id, tier, plan_config["max_runs_per_month"], customer_id, subscription_id)
        )
        db.commit()
        logger.info("User %s upgraded to %s in SQLite", user_id, tier)
    except Exception as e:
        logger.error("Failed to upgrade user %s in SQLite: %s", user_id, e)


async def _handle_subscription_deleted(subscription_data: dict):
    """Downgrade user to free tier when subscription is cancelled."""
    metadata = subscription_data.get("metadata", {})
    user_id = metadata.get("user_id")
    customer_id = subscription_data.get("customer")

    # Try to find user by metadata first, then by customer_id
    if user_id:
        _downgrade_user(user_id)
    elif customer_id:
        from app.db.database import get_db
        try:
            db = get_db()
            cursor = db.execute("SELECT user_id FROM usage_limits WHERE stripe_customer_id = ? LIMIT 1", (customer_id,))
            row = cursor.fetchone()
            if row:
                _downgrade_user(row["user_id"])
        except Exception as e:
            logger.error("Failed to find user for customer %s: %s", customer_id, e)


def _downgrade_user(user_id: str):
    """Reset a user to the free tier in SQLite."""
    from app.db.database import get_db
    try:
        db = get_db()
        db.execute(
            "UPDATE usage_limits SET plan = 'free', max_runs_per_month = 10, stripe_subscription_id = NULL WHERE user_id = ?",
            (user_id,)
        )
        db.commit()
        logger.info("User %s downgraded to free in SQLite", user_id)
    except Exception as e:
        logger.error("Failed to downgrade user %s in SQLite: %s", user_id, e)
