"""Cal.com booking tools — create paid event types and check bookings.

Uses Cal.com's v2 REST API via httpx with Bearer token auth.
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

logger = logging.getLogger("agent_company_ai.tools.booking")

CALCOM_API_BASE = "https://api.cal.com/v2"

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_api_key: str = ""
_enabled: bool = False
_default_duration: int = 30


def set_booking_config(api_key: str, default_duration: int = 30) -> None:
    global _api_key, _enabled, _default_duration
    _api_key = api_key
    _enabled = bool(api_key)
    _default_duration = default_duration


def set_booking_db(db: Database) -> None:
    global _db
    _db = db


def set_booking_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_configured() -> str | None:
    if not _enabled:
        return (
            "Cal.com not configured. Set integrations.calcom.enabled: true "
            "and integrations.calcom.api_key in config.yaml."
        )
    return None


def _calcom_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key}",
        "Content-Type": "application/json",
        "cal-api-version": "2024-08-13",
    }


@tool(
    "create_booking_link",
    (
        "Create a booking/consultation event type on Cal.com. "
        "Returns a booking URL that clients can use to schedule. "
        "Note: payment collection requires Cal.com payment app setup in the dashboard — "
        "the price is recorded locally for revenue tracking but must be configured in Cal.com to charge clients."
    ),
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event type title (e.g. '1-on-1 Consultation')",
            },
            "price": {
                "type": "number",
                "description": "Price per booking in dollars (e.g. 150.00)",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Duration of the booking in minutes (default: from config, usually 30)",
            },
            "description": {
                "type": "string",
                "description": "Description of the event type",
            },
            "currency": {
                "type": "string",
                "description": "Three-letter currency code (default: usd)",
            },
        },
        "required": ["title", "price"],
    },
)
async def create_booking_link(
    title: str,
    price: float,
    duration_minutes: int = 0,
    description: str = "",
    currency: str = "usd",
) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not title.strip():
        return "Error: title is required."
    if price <= 0:
        return "Error: price must be positive."

    duration = duration_minutes if duration_minutes > 0 else _default_duration
    currency = currency.strip().lower() or "usd"
    price_cents = int(round(price * 100))

    # Rate limit check
    limiter = RateLimiter.get()
    if not limiter.check("bookings_daily"):
        return "Rate limit exceeded: daily booking link limit reached. Try again later."

    try:
        async with httpx.AsyncClient() as client:
            payload: dict = {
                "title": title,
                "slug": title.lower().replace(" ", "-")[:50],
                "lengthInMinutes": duration,
                "description": description,
            }

            resp = await client.post(
                f"{CALCOM_API_BASE}/event-types",
                headers=_calcom_headers(),
                json=payload,
                timeout=30.0,
            )
            if resp.status_code >= 400:
                return f"Error creating Cal.com event type: {resp.text}"
            data = resp.json()
    except Exception as e:
        logger.error(f"Cal.com API error: {e}")
        return f"Error communicating with Cal.com: {e}"

    event_data = data.get("data", data)
    event_id = str(event_data.get("id", ""))
    booking_url = event_data.get("url", "") or event_data.get("link", "")

    # Record rate limit usage
    limiter.record("bookings_daily")

    # Log to database
    if _db:
        await _db.execute(
            "INSERT INTO booking_links "
            "(calcom_event_id, title, duration_minutes, price_cents, currency, booking_url, status, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (event_id, title, duration, price_cents, currency, booking_url, _current_agent),
        )

    logger.info(f"Booking link created: {title} at ${price:.2f}")
    remaining = limiter.remaining("bookings_daily")
    return (
        f"Booking link created successfully!\n"
        f"  Title: {title}\n"
        f"  Price: ${price:.2f} {currency.upper()}\n"
        f"  Duration: {duration} minutes\n"
        f"  URL: {booking_url}\n"
        f"  Cal.com Event ID: {event_id}\n"
        f"  Booking links remaining today: {remaining}"
    )


@tool(
    "list_bookings",
    "List Cal.com bookings, optionally filtered by status.",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by status: upcoming, past, cancelled (optional)",
            },
            "limit": {
                "type": "integer",
                "description": "Number of bookings to retrieve (default: 10)",
            },
        },
        "required": [],
    },
)
async def list_bookings(status: str = "", limit: int = 10) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    limit = min(max(1, limit), 100)

    try:
        params: dict = {"limit": limit}
        if status.strip():
            params["status"] = status.strip()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{CALCOM_API_BASE}/bookings",
                headers=_calcom_headers(),
                params=params,
                timeout=30.0,
            )
        if resp.status_code >= 400:
            return f"Error fetching bookings: {resp.text}"
        data = resp.json()
    except Exception as e:
        logger.error(f"Cal.com API error: {e}")
        return f"Error communicating with Cal.com: {e}"

    bookings_data = data.get("data", data.get("bookings", []))
    if isinstance(bookings_data, dict):
        bookings_data = bookings_data.get("bookings", [])
    if not bookings_data:
        return "No bookings found."

    bookings = bookings_data[:limit]
    lines = [f"Bookings ({len(bookings)}):"]
    for b in bookings:
        title = b.get("title", "(untitled)")
        start = b.get("startTime", b.get("start", ""))[:16]
        b_status = b.get("status", "")
        attendees = b.get("attendees", [])
        attendee_str = attendees[0].get("email", "") if attendees else ""
        lines.append(f"  {title} | {start} | {b_status} | {attendee_str}")

    return "\n".join(lines)


@tool(
    "check_booking_revenue",
    "Show booking link pricing summary from local records. Note: this shows configured prices, not actual collected revenue.",
    {
        "type": "object",
        "properties": {},
        "required": [],
    },
)
async def check_booking_revenue() -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not _db:
        return "Error: database not configured."

    # Aggregate from local booking_links table
    rows = await _db.fetch_all(
        "SELECT title, price_cents, currency FROM booking_links WHERE status = 'active'"
    )

    if not rows:
        return "No booking links found. Revenue: $0.00"

    total_cents = 0
    lines = ["Booking Links & Estimated Revenue:"]
    for r in rows:
        title = r.get("title", "")
        price_cents = r.get("price_cents", 0)
        currency = r.get("currency", "usd")
        lines.append(f"  {title} | ${price_cents / 100:.2f} {currency.upper()}/booking")
        total_cents += price_cents

    lines.append(
        f"\nActive booking links: {len(rows)}\n"
        f"Average price per booking: ${total_cents / len(rows) / 100:.2f}\n"
        f"Note: Actual revenue depends on number of bookings completed."
    )
    return "\n".join(lines)
