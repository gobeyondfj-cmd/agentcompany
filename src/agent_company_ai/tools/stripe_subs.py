"""Stripe subscription tools — create recurring payment links and check MRR.

Reuses the existing StripeConfig (same API key). Creates Product + recurring
Price + PaymentLink in one step, following the same pattern as stripe_tools.py.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from agent_company_ai.tools.rate_limiter import RateLimiter
from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

logger = logging.getLogger("agent_company_ai.tools.stripe_subs")

STRIPE_API_BASE = "https://api.stripe.com/v1"

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_api_key: str = ""
_enabled: bool = False


def set_stripe_subs_config(api_key: str) -> None:
    global _api_key, _enabled
    _api_key = api_key
    _enabled = bool(api_key)


def set_stripe_subs_db(db: Database) -> None:
    global _db
    _db = db


def set_stripe_subs_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_configured() -> str | None:
    if not _enabled:
        return (
            "Stripe subscriptions not configured. Set integrations.stripe.enabled: true "
            "and integrations.stripe.api_key in config.yaml."
        )
    return None


def _stripe_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


@tool(
    "create_subscription_link",
    (
        "Create a Stripe subscription payment link for recurring revenue. "
        "Creates a Product with a monthly recurring Price and a PaymentLink. "
        "Returns the shareable subscription URL."
    ),
    {
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "Name of the subscription product",
            },
            "monthly_price": {
                "type": "number",
                "description": "Monthly price in dollars (e.g. 29.99)",
            },
            "description": {
                "type": "string",
                "description": "Product description shown on the checkout page",
            },
            "currency": {
                "type": "string",
                "description": "Three-letter currency code (default: usd)",
            },
            "trial_days": {
                "type": "integer",
                "description": "Free trial days before first charge (default: 0)",
            },
        },
        "required": ["product_name", "monthly_price"],
    },
)
async def create_subscription_link(
    product_name: str,
    monthly_price: float,
    description: str = "",
    currency: str = "usd",
    trial_days: int = 0,
) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not product_name.strip():
        return "Error: product_name is required."
    if monthly_price <= 0:
        return "Error: monthly_price must be positive."

    currency = currency.strip().lower() or "usd"
    trial_days = max(0, trial_days)

    # Rate limit check — reuses payment_links_daily bucket
    limiter = RateLimiter.get()
    if not limiter.check("payment_links_daily"):
        return "Rate limit exceeded: daily payment link limit reached. Try again later."

    amount_cents = int(round(monthly_price * 100))

    try:
        async with httpx.AsyncClient() as client:
            # 1. Create Product
            prod_resp = await client.post(
                f"{STRIPE_API_BASE}/products",
                headers=_stripe_headers(),
                data={
                    "name": product_name,
                    "description": description,
                },
                timeout=30.0,
            )
            if prod_resp.status_code >= 400:
                return f"Error creating Stripe product: {prod_resp.json()}"
            product = prod_resp.json()

            # 2. Create recurring Price
            price_data: dict = {
                "product": product["id"],
                "unit_amount": str(amount_cents),
                "currency": currency,
                "recurring[interval]": "month",
            }
            price_resp = await client.post(
                f"{STRIPE_API_BASE}/prices",
                headers=_stripe_headers(),
                data=price_data,
                timeout=30.0,
            )
            if price_resp.status_code >= 400:
                return f"Error creating Stripe recurring price: {price_resp.json()}"
            price = price_resp.json()

            # 3. Create Payment Link
            link_data: dict = {
                "line_items[0][price]": price["id"],
                "line_items[0][quantity]": "1",
            }
            if trial_days > 0:
                link_data["subscription_data[trial_period_days]"] = str(trial_days)

            link_resp = await client.post(
                f"{STRIPE_API_BASE}/payment_links",
                headers=_stripe_headers(),
                data=link_data,
                timeout=30.0,
            )
            if link_resp.status_code >= 400:
                return f"Error creating Stripe payment link: {link_resp.json()}"
            link = link_resp.json()

    except Exception as e:
        logger.error(f"Stripe API error: {e}")
        return f"Error communicating with Stripe: {e}"

    # Record rate limit usage
    limiter.record("payment_links_daily")

    stripe_url = link.get("url", "")

    # Log to database
    if _db:
        await _db.execute(
            "INSERT INTO subscription_links "
            "(stripe_url, stripe_price_id, stripe_payment_link_id, product_name, "
            "monthly_amount_cents, currency, trial_days, status, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)",
            (stripe_url, price["id"], link["id"], product_name,
             amount_cents, currency, trial_days, _current_agent),
        )

    logger.info(f"Subscription link created: {stripe_url}")
    remaining = limiter.remaining("payment_links_daily")
    trial_note = f"\n  Free trial: {trial_days} days" if trial_days > 0 else ""
    return (
        f"Subscription link created successfully!\n"
        f"  Product: {product_name}\n"
        f"  Monthly price: ${monthly_price:.2f}/mo {currency.upper()}\n"
        f"  URL: {stripe_url}\n"
        f"  Stripe Price ID: {price['id']}{trial_note}\n"
        f"  Payment links remaining today: {remaining}"
    )


@tool(
    "list_subscribers",
    "List active Stripe subscriptions.",
    {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of subscriptions to retrieve (default: 10)",
            },
        },
        "required": [],
    },
)
async def list_subscribers(limit: int = 10) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    limit = min(max(1, limit), 100)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STRIPE_API_BASE}/subscriptions",
                headers=_stripe_headers(),
                params={"status": "active", "limit": limit},
                timeout=30.0,
            )
        if resp.status_code >= 400:
            return f"Error fetching subscriptions: {resp.json()}"
        data = resp.json()
    except Exception as e:
        logger.error(f"Stripe API error: {e}")
        return f"Error communicating with Stripe: {e}"

    subs = data.get("data", [])
    if not subs:
        return "No active subscriptions found."

    lines = [f"Active subscriptions ({len(subs)}):"]
    total_mrr_cents = 0
    for s in subs:
        items = s.get("items", {}).get("data", [])
        plan_name = "(unknown)"
        amount = 0
        currency = "usd"
        for item in items:
            price = item.get("price", {})
            plan_name = price.get("product", plan_name)
            amount = price.get("unit_amount", 0)
            currency = price.get("currency", "usd")
            total_mrr_cents += amount

        customer = s.get("customer", "")
        status = s.get("status", "")
        lines.append(
            f"  ${amount / 100:.2f}/mo {currency.upper()} | {status} | customer: {customer}"
        )

    lines.append(f"\nEstimated MRR: ${total_mrr_cents / 100:.2f}")
    return "\n".join(lines)


@tool(
    "check_subscription_revenue",
    "Calculate Monthly Recurring Revenue (MRR) from active subscriptions.",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def check_subscription_revenue() -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    try:
        async with httpx.AsyncClient() as client:
            # Fetch all active subscriptions (paginate if needed)
            all_subs = []
            has_more = True
            starting_after = None

            while has_more:
                params: dict = {"status": "active", "limit": 100}
                if starting_after:
                    params["starting_after"] = starting_after

                resp = await client.get(
                    f"{STRIPE_API_BASE}/subscriptions",
                    headers=_stripe_headers(),
                    params=params,
                    timeout=30.0,
                )
                if resp.status_code >= 400:
                    return f"Error fetching subscriptions: {resp.json()}"

                data = resp.json()
                subs = data.get("data", [])
                all_subs.extend(subs)
                has_more = data.get("has_more", False)
                if subs:
                    starting_after = subs[-1]["id"]

    except Exception as e:
        logger.error(f"Stripe API error: {e}")
        return f"Error communicating with Stripe: {e}"

    if not all_subs:
        return "No active subscriptions. MRR: $0.00"

    total_mrr_cents = 0
    for s in all_subs:
        items = s.get("items", {}).get("data", [])
        for item in items:
            price = item.get("price", {})
            amount = price.get("unit_amount", 0)
            interval = price.get("recurring", {}).get("interval", "month")
            # Normalize to monthly
            if interval == "year":
                total_mrr_cents += amount // 12
            elif interval == "week":
                total_mrr_cents += amount * 4
            else:
                total_mrr_cents += amount

    return (
        f"Subscription Revenue Summary\n"
        f"  Active subscriptions: {len(all_subs)}\n"
        f"  Monthly Recurring Revenue (MRR): ${total_mrr_cents / 100:.2f}\n"
        f"  Annual Run Rate (ARR): ${total_mrr_cents * 12 / 100:.2f}"
    )
