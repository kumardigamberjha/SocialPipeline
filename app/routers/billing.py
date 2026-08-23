"""
Stripe billing endpoints: checkout, webhook, customer portal.

Handles subscription lifecycle for pro and enterprise tiers.
"""

import asyncio
import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.db import queries
from app.db.session import get_session, session_scope
from app.db.tables import UsageLimit

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


# Redirect targets are built from settings.frontend_url rather than accepted
# from the caller — a caller-supplied URL here is an open redirect off the back
# of a Stripe session.
def _frontend(path: str) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}{path}"


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/checkout", summary="Create a Stripe Checkout Session")
async def create_checkout(
    req: CheckoutRequest,
    user: dict = Depends(get_current_user),
    session_db: AsyncSession = Depends(get_session),
):
    """
    Create a Stripe Checkout Session for upgrading to pro or enterprise.
    Returns the checkout URL for the client to redirect to.
    """
    s = _get_stripe()
    settings = get_settings()
    user_id = user["id"]

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
        usage = await queries.get_usage(session_db, user_id)
        if usage and usage.get("stripe_customer_id"):
            customer_id = usage["stripe_customer_id"]
    except Exception as e:
        logger.warning("Could not fetch existing Stripe customer: %s", e)

    try:
        session_params = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": _frontend("/billing/success") + "?session_id={CHECKOUT_SESSION_ID}",
            "cancel_url": _frontend("/billing/cancel"),
            "metadata": {"user_id": user_id, "tier": req.tier},
            "subscription_data": {
                "metadata": {"user_id": user_id, "tier": req.tier},
            },
        }

        if customer_id:
            session_params["customer"] = customer_id
        else:
            session_params["customer_creation"] = "always"

        # The Stripe SDK is synchronous — this is an outbound HTTPS round trip
        # that would otherwise block the event loop for every other request.
        session = await asyncio.to_thread(s.checkout.Session.create, **session_params)
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
        event = await asyncio.to_thread(
            s.Webhook.construct_event,
            payload, sig_header, settings.stripe_webhook_secret,
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
async def create_portal(
    user: dict = Depends(get_current_user),
    session_db: AsyncSession = Depends(get_session),
):
    """
    Create a Stripe billing portal session for the user to manage their subscription.
    """
    s = _get_stripe()
    user_id = user["id"]

    # Look up the user's Stripe customer ID
    try:
        usage = await queries.get_usage(session_db, user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

    if not usage or not usage.get("stripe_customer_id"):
        raise HTTPException(status_code=404, detail="No Stripe customer found. Subscribe to a plan first.")

    customer_id = usage["stripe_customer_id"]

    try:
        session = await asyncio.to_thread(
            s.billing_portal.Session.create,
            customer=customer_id,
            return_url=_frontend("/dashboard"),
        )
        return {"portal_url": session.url}
    except s.error.StripeError as e:
        logger.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=502, detail=f"Stripe error: {e.user_message or str(e)}")


# ── Internal Handlers ───────────────────────────────────────────────────────


async def _handle_checkout_completed(session_data: dict):
    """Upgrade a user's tier after successful checkout.

    Called from the webhook handler, which is outside the normal request
    cycle, so this opens its own session rather than borrowing one from a
    ``Depends``.
    """
    metadata = session_data.get("metadata", {})
    user_id = metadata.get("user_id")
    tier = metadata.get("tier", "pro")
    customer_id = session_data.get("customer")
    subscription_id = session_data.get("subscription")

    if not user_id:
        logger.error("checkout.session.completed missing user_id in metadata")
        return

    plan_config = PLAN_LIMITS.get(tier, PLAN_LIMITS["pro"])

    try:
        async with session_scope() as db:
            stmt = pg_insert(UsageLimit).values(
                user_id=user_id,
                plan=tier,
                max_runs_per_month=plan_config["max_runs_per_month"],
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            )
            await db.execute(
                stmt.on_conflict_do_update(
                    index_elements=[UsageLimit.user_id],
                    set_={
                        "plan": stmt.excluded.plan,
                        "max_runs_per_month": stmt.excluded.max_runs_per_month,
                        "stripe_customer_id": stmt.excluded.stripe_customer_id,
                        "stripe_subscription_id": stmt.excluded.stripe_subscription_id,
                    },
                )
            )
        logger.info("User %s upgraded to %s", user_id, tier)
    except Exception as e:
        logger.error("Failed to upgrade user %s: %s", user_id, e)


async def _handle_subscription_deleted(subscription_data: dict):
    """Downgrade a user to the free tier when their subscription is cancelled."""
    metadata = subscription_data.get("metadata", {})
    user_id = metadata.get("user_id")
    customer_id = subscription_data.get("customer")

    # Prefer the metadata user_id; fall back to looking up by Stripe customer.
    if not user_id and customer_id:
        try:
            async with session_scope() as db:
                user_id = (
                    await db.execute(
                        select(UsageLimit.user_id)
                        .where(UsageLimit.stripe_customer_id == customer_id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
        except Exception as e:
            logger.error("Failed to find user for customer %s: %s", customer_id, e)
            return

    if user_id:
        await _downgrade_user(user_id)


async def _downgrade_user(user_id: str):
    """Reset a user to the free tier."""
    try:
        async with session_scope() as db:
            await db.execute(
                update(UsageLimit)
                .where(UsageLimit.user_id == user_id)
                .values(
                    plan="free",
                    max_runs_per_month=PLAN_LIMITS["free"]["max_runs_per_month"],
                    stripe_subscription_id=None,
                )
            )
        logger.info("User %s downgraded to free", user_id)
    except Exception as e:
        logger.error("Failed to downgrade user %s: %s", user_id, e)
