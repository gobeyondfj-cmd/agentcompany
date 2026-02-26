"""Gumroad digital product tools — create products and check sales.

Uses Gumroad's REST API directly via httpx.
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

logger = logging.getLogger("agent_company_ai.tools.gumroad")

GUMROAD_API_BASE = "https://api.gumroad.com/v2"

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_access_token: str = ""
_enabled: bool = False


def set_gumroad_config(access_token: str) -> None:
    global _access_token, _enabled
    _access_token = access_token
    _enabled = bool(access_token)


def set_gumroad_db(db: Database) -> None:
    global _db
    _db = db


def set_gumroad_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_configured() -> str | None:
    if not _enabled:
        return (
            "Gumroad not configured. Set integrations.gumroad.enabled: true "
            "and integrations.gumroad.access_token in config.yaml."
        )
    return None


def _gumroad_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_access_token}"}


@tool(
    "create_gumroad_product",
    (
        "Create a digital product on Gumroad. Returns the product URL. "
        "Price minimum is $0.99."
    ),
    {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Product name",
            },
            "price_cents": {
                "type": "integer",
                "description": "Price in cents (e.g. 999 for $9.99). Minimum 99.",
            },
            "description": {
                "type": "string",
                "description": "Product description shown to buyers",
            },
            "url": {
                "type": "string",
                "description": "Custom URL slug for the product (optional)",
            },
        },
        "required": ["name", "price_cents"],
    },
)
async def create_gumroad_product(
    name: str,
    price_cents: int,
    description: str = "",
    url: str = "",
) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not name.strip():
        return "Error: name is required."
    if price_cents < 99:
        return "Error: price_cents must be at least 99 ($0.99)."

    # Rate limit check
    limiter = RateLimiter.get()
    if not limiter.check("gumroad_daily"):
        return "Rate limit exceeded: daily Gumroad product limit reached. Try again later."

    try:
        async with httpx.AsyncClient() as client:
            data: dict = {
                "name": name,
                "price": str(price_cents),
                "description": description,
            }
            if url.strip():
                data["url"] = url.strip()

            resp = await client.post(
                f"{GUMROAD_API_BASE}/products",
                headers=_gumroad_headers(),
                data=data,
                timeout=30.0,
            )
            if resp.status_code >= 400:
                return f"Error creating Gumroad product: {resp.text}"
            result = resp.json()
    except Exception as e:
        logger.error(f"Gumroad API error: {e}")
        return f"Error communicating with Gumroad: {e}"

    product = result.get("product", {})
    gumroad_id = product.get("id", "")
    product_url = product.get("short_url", "") or product.get("url", "")

    # Record rate limit usage
    limiter.record("gumroad_daily")

    # Log to database
    if _db:
        await _db.execute(
            "INSERT INTO gumroad_products "
            "(gumroad_id, name, price_cents, description, url, status, created_by) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?)",
            (gumroad_id, name, price_cents, description, product_url, _current_agent),
        )

    logger.info(f"Gumroad product created: {name} at ${price_cents / 100:.2f}")
    remaining = limiter.remaining("gumroad_daily")
    return (
        f"Gumroad product created successfully!\n"
        f"  Name: {name}\n"
        f"  Price: ${price_cents / 100:.2f}\n"
        f"  URL: {product_url}\n"
        f"  Gumroad ID: {gumroad_id}\n"
        f"  Products remaining today: {remaining}"
    )


@tool(
    "list_gumroad_products",
    "List your Gumroad products.",
    {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of products to retrieve (default: 10)",
            },
        },
        "required": [],
    },
)
async def list_gumroad_products(limit: int = 10) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    limit = min(max(1, limit), 100)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GUMROAD_API_BASE}/products",
                headers=_gumroad_headers(),
                timeout=30.0,
            )
        if resp.status_code >= 400:
            return f"Error fetching products: {resp.text}"
        data = resp.json()
    except Exception as e:
        logger.error(f"Gumroad API error: {e}")
        return f"Error communicating with Gumroad: {e}"

    products = data.get("products", [])[:limit]
    if not products:
        return "No Gumroad products found."

    lines = [f"Gumroad products ({len(products)}):"]
    for p in products:
        name = p.get("name", "(unnamed)")
        price = p.get("price", 0)
        sales_count = p.get("sales_count", 0)
        url = p.get("short_url", "")
        lines.append(f"  {name} | ${price / 100:.2f} | {sales_count} sales | {url}")

    return "\n".join(lines)


@tool(
    "check_gumroad_sales",
    "Check recent Gumroad sales and revenue.",
    {
        "type": "object",
        "properties": {
            "product_id": {
                "type": "string",
                "description": "Gumroad product ID to filter by (optional)",
            },
            "limit": {
                "type": "integer",
                "description": "Number of sales to retrieve (default: 10)",
            },
        },
        "required": [],
    },
)
async def check_gumroad_sales(product_id: str = "", limit: int = 10) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    limit = min(max(1, limit), 100)

    try:
        async with httpx.AsyncClient() as client:
            params: dict = {}
            if product_id.strip():
                params["product_id"] = product_id.strip()

            resp = await client.get(
                f"{GUMROAD_API_BASE}/sales",
                headers=_gumroad_headers(),
                params=params,
                timeout=30.0,
            )
        if resp.status_code >= 400:
            return f"Error fetching sales: {resp.text}"
        data = resp.json()
    except Exception as e:
        logger.error(f"Gumroad API error: {e}")
        return f"Error communicating with Gumroad: {e}"

    sales = data.get("sales", [])[:limit]
    if not sales:
        return "No Gumroad sales found."

    total_cents = 0
    lines = [f"Recent Gumroad sales ({len(sales)}):"]
    for s in sales:
        product_name = s.get("product_name", "(unknown)")
        price = s.get("price", 0)
        email = s.get("email", "(no email)")
        created_at = s.get("created_at", "")[:10]
        lines.append(f"  {product_name} | ${price / 100:.2f} | {email} | {created_at}")
        total_cents += price

    lines.append(f"\nTotal revenue: ${total_cents / 100:.2f} ({len(sales)} sales)")
    return "\n".join(lines)
