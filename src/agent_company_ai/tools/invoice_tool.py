"""Invoice generator tool — create, send, and manage invoices.

No external API needed. Generates HTML invoices from a built-in template,
saves to the company's invoices/ directory, and uses the existing email
tool for sending.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from agent_company_ai.tools.rate_limiter import RateLimiter
from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

logger = logging.getLogger("agent_company_ai.tools.invoice")

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_company_dir: Path | None = None
_enabled: bool = False
_company_name: str = ""
_company_address: str = ""
_payment_instructions: str = ""
_default_currency: str = "USD"


def set_invoice_config(
    company_name: str,
    company_address: str = "",
    payment_instructions: str = "",
    currency: str = "USD",
) -> None:
    global _enabled, _company_name, _company_address, _payment_instructions, _default_currency
    _company_name = company_name
    _company_address = company_address
    _payment_instructions = payment_instructions
    _default_currency = currency
    _enabled = bool(company_name)


def set_invoice_db(db: Database) -> None:
    global _db
    _db = db


def set_invoice_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def set_invoice_company_dir(company_dir: Path) -> None:
    global _company_dir
    _company_dir = company_dir


def _require_configured() -> str | None:
    if not _enabled:
        return (
            "Invoice not configured. Set integrations.invoice.enabled: true "
            "and integrations.invoice.company_name in config.yaml."
        )
    return None


def _escape(text: str) -> str:
    """HTML-escape text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _generate_invoice_number() -> str:
    """Generate a unique invoice number: INV-YYYYMMDD-XXXX."""
    date_part = datetime.now().strftime("%Y%m%d")
    hex_part = uuid.uuid4().hex[:4].upper()
    return f"INV-{date_part}-{hex_part}"


_INVOICE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Invoice {invoice_number}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #fff; color: #1a1a1a; line-height: 1.6; padding: 40px; max-width: 800px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 40px;
             border-bottom: 3px solid #2563eb; padding-bottom: 20px; }}
  .header h1 {{ font-size: 2rem; color: #2563eb; }}
  .header .company {{ text-align: right; color: #6b7280; font-size: 0.9rem; }}
  .meta {{ display: flex; justify-content: space-between; margin-bottom: 32px; }}
  .meta .bill-to {{ flex: 1; }}
  .meta .invoice-info {{ text-align: right; }}
  .meta h3 {{ font-size: 0.8rem; text-transform: uppercase; color: #6b7280; margin-bottom: 4px; }}
  .meta p {{ margin-bottom: 2px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
  th {{ background: #f3f4f6; text-align: left; padding: 10px 12px; font-size: 0.85rem;
       text-transform: uppercase; color: #6b7280; border-bottom: 2px solid #e5e7eb; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; }}
  td.amount {{ text-align: right; }}
  th.amount {{ text-align: right; }}
  .totals {{ display: flex; justify-content: flex-end; margin-bottom: 32px; }}
  .totals table {{ width: 280px; }}
  .totals td {{ border: none; padding: 6px 12px; }}
  .totals .total-row td {{ font-weight: 700; font-size: 1.1rem; border-top: 2px solid #1a1a1a; padding-top: 10px; }}
  .notes {{ background: #f9fafb; border-radius: 8px; padding: 16px; margin-bottom: 24px; }}
  .notes h3 {{ font-size: 0.85rem; color: #6b7280; margin-bottom: 8px; }}
  .payment {{ background: #eff6ff; border-radius: 8px; padding: 16px; border-left: 4px solid #2563eb; }}
  .payment h3 {{ font-size: 0.85rem; color: #2563eb; margin-bottom: 8px; }}
  .footer {{ text-align: center; color: #9ca3af; font-size: 0.8rem; margin-top: 40px;
             border-top: 1px solid #e5e7eb; padding-top: 16px; }}
</style>
</head>
<body>
<div class="header">
  <h1>INVOICE</h1>
  <div class="company">
    <strong>{company_name}</strong><br>
    {company_address_html}
  </div>
</div>
<div class="meta">
  <div class="bill-to">
    <h3>Bill To</h3>
    <p><strong>{client_name}</strong></p>
    <p>{client_email}</p>
  </div>
  <div class="invoice-info">
    <h3>Invoice Details</h3>
    <p><strong>{invoice_number}</strong></p>
    <p>Date: {issue_date}</p>
    <p>Due: {due_date}</p>
    <p>Currency: {currency}</p>
  </div>
</div>
<table>
  <thead>
    <tr><th>Description</th><th class="amount">Qty</th><th class="amount">Unit Price</th><th class="amount">Amount</th></tr>
  </thead>
  <tbody>
    {items_html}
  </tbody>
</table>
<div class="totals">
  <table>
    <tr><td>Subtotal</td><td class="amount">{subtotal}</td></tr>
    {tax_row}
    <tr class="total-row"><td>Total</td><td class="amount">{total}</td></tr>
  </table>
</div>
{notes_html}
{payment_html}
<div class="footer">Thank you for your business.</div>
</body>
</html>
"""


def _build_invoice_html(
    invoice_number: str,
    client_name: str,
    client_email: str,
    items: list[dict],
    subtotal_cents: int,
    tax_cents: int,
    total_cents: int,
    currency: str,
    due_date: str,
    notes: str,
    payment_instructions: str,
) -> str:
    """Build the HTML invoice from structured data."""
    items_html_parts = []
    for item in items:
        desc = _escape(item.get("description", ""))
        qty = item.get("quantity", 1)
        unit_price_cents = item.get("unit_price_cents", 0)
        amount_cents = qty * unit_price_cents
        items_html_parts.append(
            f"<tr><td>{desc}</td>"
            f"<td class=\"amount\">{qty}</td>"
            f"<td class=\"amount\">${unit_price_cents / 100:.2f}</td>"
            f"<td class=\"amount\">${amount_cents / 100:.2f}</td></tr>"
        )

    company_address_html = _escape(_company_address).replace("\n", "<br>") if _company_address else ""

    notes_html = ""
    if notes.strip():
        notes_html = f'<div class="notes"><h3>Notes</h3><p>{_escape(notes)}</p></div>'

    payment_html = ""
    if payment_instructions.strip():
        payment_html = f'<div class="payment"><h3>Payment Instructions</h3><p>{_escape(payment_instructions)}</p></div>'

    tax_row = ""
    if tax_cents > 0:
        tax_row = f'<tr><td>Tax</td><td class="amount">${tax_cents / 100:.2f}</td></tr>'

    return _INVOICE_TEMPLATE.format(
        invoice_number=_escape(invoice_number),
        company_name=_escape(_company_name),
        company_address_html=company_address_html,
        client_name=_escape(client_name),
        client_email=_escape(client_email),
        issue_date=datetime.now().strftime("%Y-%m-%d"),
        due_date=_escape(due_date),
        currency=_escape(currency),
        items_html="\n    ".join(items_html_parts),
        subtotal=f"${subtotal_cents / 100:.2f}",
        tax_row=tax_row,
        total=f"${total_cents / 100:.2f}",
        notes_html=notes_html,
        payment_html=payment_html,
    )


@tool(
    "create_invoice",
    (
        "Create an invoice for a client. Generates a professional HTML invoice "
        "and saves it to disk. Use send_invoice to email it."
    ),
    {
        "type": "object",
        "properties": {
            "client_name": {
                "type": "string",
                "description": "Name of the client being billed",
            },
            "client_email": {
                "type": "string",
                "description": "Client's email address",
            },
            "items_json": {
                "type": "string",
                "description": (
                    'JSON array of line items. Each item: {"description": "...", '
                    '"quantity": 1, "unit_price_cents": 5000}. '
                    "unit_price_cents is in cents (5000 = $50.00)."
                ),
            },
            "due_days": {
                "type": "integer",
                "description": "Days until payment is due (default: 30)",
            },
            "notes": {
                "type": "string",
                "description": "Optional notes to include on the invoice",
            },
            "currency": {
                "type": "string",
                "description": "Currency code (default: from config, usually USD)",
            },
        },
        "required": ["client_name", "client_email", "items_json"],
    },
)
async def create_invoice(
    client_name: str,
    client_email: str,
    items_json: str,
    due_days: int = 30,
    notes: str = "",
    currency: str = "",
) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not client_name.strip():
        return "Error: client_name is required."
    if not client_email.strip() or "@" not in client_email:
        return "Error: valid client_email is required."

    # Parse items
    try:
        items = json.loads(items_json)
        if not isinstance(items, list) or not items:
            return "Error: items_json must be a non-empty JSON array."
    except json.JSONDecodeError as e:
        return f"Error: invalid items_json: {e}"

    # Rate limit check
    limiter = RateLimiter.get()
    if not limiter.check("invoices_daily"):
        return "Rate limit exceeded: daily invoice limit reached. Try again later."

    currency = (currency.strip() or _default_currency).upper()
    due_date = (datetime.now() + timedelta(days=max(1, due_days))).strftime("%Y-%m-%d")
    payment_instructions = _payment_instructions

    # Calculate totals
    subtotal_cents = 0
    for item in items:
        qty = item.get("quantity", 1)
        unit_price = item.get("unit_price_cents", 0)
        subtotal_cents += qty * unit_price

    tax_cents = 0  # Tax can be added as a line item or future feature
    total_cents = subtotal_cents + tax_cents

    invoice_number = _generate_invoice_number()

    html_content = _build_invoice_html(
        invoice_number=invoice_number,
        client_name=client_name,
        client_email=client_email,
        items=items,
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=total_cents,
        currency=currency,
        due_date=due_date,
        notes=notes,
        payment_instructions=payment_instructions,
    )

    # Save to disk
    file_path = ""
    if _company_dir:
        invoices_dir = _company_dir / "invoices"
        invoices_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(invoices_dir / f"{invoice_number}.html")
        Path(file_path).write_text(html_content, encoding="utf-8")

    # Record rate limit usage
    limiter.record("invoices_daily")

    # Log to database
    if _db:
        await _db.execute(
            "INSERT INTO invoices "
            "(invoice_number, client_name, client_email, items_json, "
            "subtotal_cents, tax_cents, total_cents, currency, status, "
            "due_date, notes, payment_instructions, html_content, file_path, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)",
            (
                invoice_number, client_name, client_email, items_json,
                subtotal_cents, tax_cents, total_cents, currency,
                due_date, notes, payment_instructions, html_content, file_path,
                _current_agent,
            ),
        )

    logger.info(f"Invoice {invoice_number} created for {client_name}: ${total_cents / 100:.2f}")
    remaining = limiter.remaining("invoices_daily")

    # Get the DB ID so the agent can chain create -> send
    db_id = ""
    if _db:
        row = await _db.fetch_one(
            "SELECT id FROM invoices WHERE invoice_number = ?", (invoice_number,)
        )
        if row:
            db_id = str(row["id"])

    return (
        f"Invoice created successfully!\n"
        f"  Invoice ID: {db_id}\n"
        f"  Invoice #: {invoice_number}\n"
        f"  Client: {client_name} ({client_email})\n"
        f"  Total: ${total_cents / 100:.2f} {currency}\n"
        f"  Due: {due_date}\n"
        f"  File: {file_path}\n"
        f"  Status: draft\n"
        f"  Invoices remaining today: {remaining}\n"
        f"\nUse send_invoice with invoice_id={db_id} to email this invoice."
    )


@tool(
    "send_invoice",
    (
        "Send an invoice to the client via email. "
        "Requires email integration to be configured."
    ),
    {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "integer",
                "description": "Database ID of the invoice to send",
            },
        },
        "required": ["invoice_id"],
    },
)
async def send_invoice(invoice_id: int) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not _db:
        return "Error: database not configured."

    # Fetch invoice
    row = await _db.fetch_one(
        "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
    )
    if not row:
        return f"Error: no invoice with ID {invoice_id}."

    client_email = row.get("client_email", "")
    if not client_email or "@" not in client_email:
        return "Error: invoice has no valid client email address."

    invoice_number = row.get("invoice_number", "")
    total_cents = row.get("total_cents", 0)
    currency = row.get("currency", "USD")
    html_content = row.get("html_content", "")

    if not html_content:
        return "Error: invoice has no HTML content."

    # Use the existing email tool
    from agent_company_ai.tools.email_tool import send_email

    subject = f"Invoice {invoice_number} - ${total_cents / 100:.2f} {currency}"
    result = await send_email(
        to=client_email,
        subject=subject,
        body=html_content,
        is_html=True,
    )

    if result.startswith("Error"):
        return f"Failed to send invoice: {result}"

    # Update invoice status
    await _db.execute(
        "UPDATE invoices SET status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?",
        (invoice_id,),
    )

    logger.info(f"Invoice {invoice_number} sent to {client_email}")
    return (
        f"Invoice sent successfully!\n"
        f"  Invoice #: {invoice_number}\n"
        f"  Sent to: {client_email}\n"
        f"  Total: ${total_cents / 100:.2f} {currency}\n"
        f"  Status: sent"
    )


@tool(
    "list_invoices",
    "List invoices, optionally filtered by status.",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by status: draft, sent, paid, overdue (optional)",
            },
            "limit": {
                "type": "integer",
                "description": "Number of invoices to retrieve (default: 25)",
            },
        },
        "required": [],
    },
)
async def list_invoices(status: str = "", limit: int = 25) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not _db:
        return "Error: database not configured."

    limit = min(max(1, limit), 100)

    if status.strip():
        rows = await _db.fetch_all(
            "SELECT * FROM invoices WHERE status = ? ORDER BY created_at DESC LIMIT ?",
            (status.strip().lower(), limit),
        )
    else:
        rows = await _db.fetch_all(
            "SELECT * FROM invoices ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    if not rows:
        return "No invoices found."

    total_cents = 0
    lines = [f"Invoices ({len(rows)}):"]
    for r in rows:
        inv_num = r.get("invoice_number", "")
        client = r.get("client_name", "")
        amount = r.get("total_cents", 0)
        cur = r.get("currency", "USD")
        st = r.get("status", "draft")
        due = r.get("due_date", "")
        lines.append(f"  #{r['id']} | {inv_num} | {client} | ${amount / 100:.2f} {cur} | {st} | due {due}")
        total_cents += amount

    lines.append(f"\nTotal value: ${total_cents / 100:.2f} ({len(rows)} invoices)")
    return "\n".join(lines)


@tool(
    "mark_invoice_paid",
    "Mark an invoice as paid.",
    {
        "type": "object",
        "properties": {
            "invoice_id": {
                "type": "integer",
                "description": "Database ID of the invoice to mark as paid",
            },
        },
        "required": ["invoice_id"],
    },
)
async def mark_invoice_paid(invoice_id: int) -> str:
    err = _require_configured()
    if err:
        return f"Error: {err}"

    if not _db:
        return "Error: database not configured."

    row = await _db.fetch_one(
        "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
    )
    if not row:
        return f"Error: no invoice with ID {invoice_id}."

    await _db.execute(
        "UPDATE invoices SET status = 'paid', paid_at = CURRENT_TIMESTAMP WHERE id = ?",
        (invoice_id,),
    )

    invoice_number = row.get("invoice_number", "")
    total_cents = row.get("total_cents", 0)
    currency = row.get("currency", "USD")

    logger.info(f"Invoice {invoice_number} marked as paid")
    return (
        f"Invoice marked as paid!\n"
        f"  Invoice #: {invoice_number}\n"
        f"  Amount: ${total_cents / 100:.2f} {currency}\n"
        f"  Status: paid"
    )
