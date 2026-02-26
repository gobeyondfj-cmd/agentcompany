"""Unified revenue tracking tools — check, record, and sync revenue.

Provides a single view of all company revenue regardless of source
(Stripe, Gumroad, invoices, crypto, manual entries). Data is stored
in the ``revenue`` table.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

logger = logging.getLogger("agent_company_ai.tools.revenue")

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_stripe_key: str = ""


def set_revenue_db(db: Database) -> None:
    global _db
    _db = db


def set_revenue_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def set_revenue_stripe_key(api_key: str) -> None:
    global _stripe_key
    _stripe_key = api_key


def _require_db() -> Database | None:
    return _db


@tool(
    "check_revenue",
    (
        "Check company revenue summary. Returns total revenue, breakdown by "
        "source (stripe, gumroad, invoice, crypto, manual), and daily totals "
        "for the specified period."
    ),
    {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look back (default 30)",
            },
        },
    },
)
async def check_revenue(days: int = 30) -> str:
    db = _require_db()
    if db is None:
        return "Error: revenue database not configured."

    # Total all-time
    row = await db.fetch_one(
        "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM revenue "
        "WHERE status = 'confirmed'"
    )
    all_time_cents = row["total"] if row else 0

    # Total for period
    row = await db.fetch_one(
        "SELECT COALESCE(SUM(amount_cents), 0) AS total FROM revenue "
        "WHERE status = 'confirmed' "
        "AND created_at >= datetime('now', ?)",
        (f"-{days} days",),
    )
    period_cents = row["total"] if row else 0

    # By source
    sources = await db.fetch_all(
        "SELECT source, COALESCE(SUM(amount_cents), 0) AS total, COUNT(*) AS cnt "
        "FROM revenue WHERE status = 'confirmed' "
        "AND created_at >= datetime('now', ?) "
        "GROUP BY source ORDER BY total DESC",
        (f"-{days} days",),
    )

    # Daily totals (last 7 days max for readability)
    daily = await db.fetch_all(
        "SELECT DATE(created_at) AS day, COALESCE(SUM(amount_cents), 0) AS total "
        "FROM revenue WHERE status = 'confirmed' "
        "AND created_at >= datetime('now', '-7 days') "
        "GROUP BY DATE(created_at) ORDER BY day DESC"
    )

    lines = [
        f"Revenue Summary (last {days} days)",
        f"  All-time total: ${all_time_cents / 100:.2f}",
        f"  Last {days} days: ${period_cents / 100:.2f}",
        "",
        "By Source:",
    ]
    if sources:
        for s in sources:
            lines.append(f"  {s['source']}: ${s['total'] / 100:.2f} ({s['cnt']} transactions)")
    else:
        lines.append("  No revenue recorded yet.")

    lines.append("")
    lines.append("Daily (last 7 days):")
    if daily:
        for d in daily:
            lines.append(f"  {d['day']}: ${d['total'] / 100:.2f}")
    else:
        lines.append("  No revenue in the last 7 days.")

    return "\n".join(lines)


@tool(
    "record_revenue",
    (
        "Manually record a revenue entry (for cash, crypto, or other payments "
        "not automatically tracked). Amount is in dollars."
    ),
    {
        "type": "object",
        "properties": {
            "amount": {
                "type": "number",
                "description": "Revenue amount in dollars (e.g. 150.00)",
            },
            "source": {
                "type": "string",
                "description": "Revenue source: 'manual', 'crypto', 'cash', 'other'",
            },
            "description": {
                "type": "string",
                "description": "Description of the revenue (e.g. 'Consulting session with Acme Corp')",
            },
            "currency": {
                "type": "string",
                "description": "Currency code (default 'usd')",
            },
        },
        "required": ["amount", "source", "description"],
    },
)
async def record_revenue(
    amount: float,
    source: str,
    description: str,
    currency: str = "usd",
) -> str:
    db = _require_db()
    if db is None:
        return "Error: revenue database not configured."

    if amount <= 0:
        return "Error: amount must be positive."
    if not source.strip():
        return "Error: source is required."

    amount_cents = int(round(amount * 100))

    cursor = await db.execute(
        "INSERT INTO revenue (source, amount_cents, currency, description, "
        "recorded_by, status) VALUES (?, ?, ?, ?, ?, 'confirmed')",
        (source.strip(), amount_cents, currency.lower(), description.strip(), _current_agent),
    )

    return (
        f"Revenue recorded (ID: {cursor.lastrowid}).\n"
        f"  Amount: ${amount:.2f} {currency.upper()}\n"
        f"  Source: {source}\n"
        f"  Description: {description}\n"
        f"  Recorded by: {_current_agent}"
    )


@tool(
    "sync_stripe_revenue",
    (
        "Sync recent Stripe charges into the revenue ledger. Pulls the last "
        "50 successful charges from Stripe and inserts any new ones (deduplicates "
        "by charge ID)."
    ),
    {
        "type": "object",
        "properties": {},
    },
)
async def sync_stripe_revenue() -> str:
    db = _require_db()
    if db is None:
        return "Error: revenue database not configured."

    if not _stripe_key:
        return "Error: Stripe is not configured. Set stripe.api_key in config.yaml."

    # Fetch recent charges from Stripe
    url = "https://api.stripe.com/v1/charges"
    params = {"limit": "50", "status": "succeeded"}
    headers = {"Authorization": f"Bearer {_stripe_key}"}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=headers)
        if resp.status_code != 200:
            return f"Error: Stripe API returned {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
    except Exception as e:
        return f"Error fetching Stripe charges: {e}"

    charges = data.get("data", [])
    if not charges:
        return "No recent Stripe charges found."

    inserted = 0
    skipped = 0
    for charge in charges:
        charge_id = charge.get("id", "")
        amount_cents = charge.get("amount", 0)
        currency = charge.get("currency", "usd")
        desc = charge.get("description", "") or charge.get("statement_descriptor", "") or ""

        # Check if already recorded
        existing = await db.fetch_one(
            "SELECT id FROM revenue WHERE source = 'stripe' AND source_id = ?",
            (charge_id,),
        )
        if existing:
            skipped += 1
            continue

        await db.execute(
            "INSERT INTO revenue (source, source_id, amount_cents, currency, "
            "description, recorded_by, status) "
            "VALUES ('stripe', ?, ?, ?, ?, ?, 'confirmed')",
            (charge_id, amount_cents, currency, desc, _current_agent),
        )
        inserted += 1

    return (
        f"Stripe revenue sync complete.\n"
        f"  Charges found: {len(charges)}\n"
        f"  New entries: {inserted}\n"
        f"  Already recorded: {skipped}"
    )
