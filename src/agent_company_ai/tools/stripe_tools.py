"""Stripe payment tools — create payment links and check revenue.

Uses Stripe's REST API directly via httpx (no stripe SDK dependency).
Rate-limited and logged to the database.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from agent_company_ai.tools.rate_limiter import RateLimiter
from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

logger = logging.getLogger("agent_company_ai.tools.stripe")

STRIPE_API_BASE = "https://api.stripe.com/v1"

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_api_key: str = ""
_enabled: bool = False
_max_amount_usd: float = 500.0


def set_stripe_config(api_key: str) -> None:
    global _api_key, _enabled
    _api_key = api_key
    _enabled = bool(api_key)


def set_stripe_db(db: Database) -> None:
    global _db
    _db = db


def set_stripe_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def set_stripe_rate_limits(max_amount_usd: float) -> None:
    global _max_amount_usd
    _max_amount_usd = max_amount_usd


def _require_configured() -> None:
    if not _enabled:
        raise RuntimeError(
            "Stripe not configured. Set integrations.stripe.enabled: true "
            "and integrations.stripe.api_key in config.yaml."
        )


def _stripe_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


@tool(
    "create_payment_link",
    (
        "Create a Stripe payment link for a product. Creates a Product, Price, "
        "and PaymentLink in one step. Returns the shareable URL."
    ),
    {
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "Name of the product or service",
            },
            "amount": {
                "type": "number",
                "description": "Price amount in dollars (e.g. 29.99)",
            },
            "description": {
                "type": "string",
                "description": "Product description shown on the checkout page",
            },
            "currency": {
                "type": "string",
                "description": "Three-letter currency code (default: usd)",
            },
        },
        "required": ["product_name", "amount"],
    },
)
async def create_payment_link(
    product_name: str,
    amount: float,
    description: str = "",
    currency: str = "usd",
) -> str:
    _require_configured()

    if not product_name.strip():
        return "Error: product_name is required."
    if amount <= 0:
        return "Error: amount must be positive."
    if amount > _max_amount_usd:
        return (
            f"Error: amount ${amount:.2f} exceeds maximum allowed "
            f"${_max_amount_usd:.2f}. Adjust integrations.rate_limits.max_payment_amount_usd "
            f"in config.yaml if needed."
        )

    currency = currency.strip().lower() or "usd"

    # Rate limit check
    limiter = RateLimiter.get()
    if not limiter.check("payment_links_daily"):
        return "Rate limit exceeded: daily payment link limit reached. Try again later."

    amount_cents = int(round(amount * 100))

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

            # 2. Create Price
            price_resp = await client.post(
                f"{STRIPE_API_BASE}/prices",
                headers=_stripe_headers(),
                data={
                    "product": product["id"],
                    "unit_amount": str(amount_cents),
                    "currency": currency,
                },
                timeout=30.0,
            )
            if price_resp.status_code >= 400:
                return f"Error creating Stripe price: {price_resp.json()}"
            price = price_resp.json()

            # 3. Create Payment Link
            link_resp = await client.post(
                f"{STRIPE_API_BASE}/payment_links",
                headers=_stripe_headers(),
                data={
                    "line_items[0][price]": price["id"],
                    "line_items[0][quantity]": "1",
                },
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

    # Log to database
    stripe_url = link.get("url", "")
    if _db:
        await _db.execute(
            "INSERT INTO payment_links "
            "(stripe_url, stripe_price_id, stripe_payment_link_id, product_name, amount_cents, currency, status, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (stripe_url, price["id"], link["id"], product_name, amount_cents, currency, _current_agent),
        )

    logger.info(f"Payment link created: {stripe_url}")
    remaining = limiter.remaining("payment_links_daily")
    return (
        f"Payment link created successfully!\n"
        f"  Product: {product_name}\n"
        f"  Price: ${amount:.2f} {currency.upper()}\n"
        f"  URL: {stripe_url}\n"
        f"  Stripe Price ID: {price['id']}\n"
        f"  Payment links remaining today: {remaining}"
    )


@tool(
    "check_payments",
    "Check recent Stripe payments/charges and revenue totals.",
    {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of recent charges to retrieve (default: 10, max: 100)",
            },
        },
        "required": [],
    },
)
async def check_payments(limit: int = 10) -> str:
    _require_configured()

    limit = min(max(1, limit), 100)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STRIPE_API_BASE}/charges",
                headers=_stripe_headers(),
                params={"limit": limit},
                timeout=30.0,
            )
        if resp.status_code >= 400:
            return f"Error fetching charges: {resp.json()}"
        data = resp.json()
    except Exception as e:
        logger.error(f"Stripe API error: {e}")
        return f"Error communicating with Stripe: {e}"

    charges = data.get("data", [])
    if not charges:
        return "No charges found."

    total_cents = 0
    successful = 0
    lines = [f"Recent charges ({len(charges)}):"]

    for c in charges:
        amount = c.get("amount", 0)
        currency = c.get("currency", "usd").upper()
        status = c.get("status", "unknown")
        desc = c.get("description") or c.get("statement_descriptor") or "(no description)"

        amount_str = f"${amount / 100:.2f} {currency}"
        lines.append(f"  {amount_str} | {status} | {desc[:50]}")

        if status == "succeeded":
            total_cents += amount
            successful += 1

    lines.append(f"\nTotal revenue (succeeded): ${total_cents / 100:.2f} ({successful} charges)")
    return "\n".join(lines)
