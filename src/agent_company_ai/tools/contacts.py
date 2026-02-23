"""CRM contacts tool — SQLite-backed contact management.

Always available (no external API needed). Agents can add, search, and
update contacts to build a customer pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"


def set_contacts_db(db: Database) -> None:
    global _db
    _db = db


def set_contacts_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Contacts database not configured.")
    return _db


@tool(
    "add_contact",
    "Add a new contact to the CRM. Returns the contact ID on success.",
    {
        "type": "object",
        "properties": {
            "email": {
                "type": "string",
                "description": "Contact email address (required, must be unique)",
            },
            "name": {
                "type": "string",
                "description": "Full name of the contact",
            },
            "company": {
                "type": "string",
                "description": "Company or organization name",
            },
            "phone": {
                "type": "string",
                "description": "Phone number",
            },
            "status": {
                "type": "string",
                "description": "Contact status: lead, prospect, customer, churned. Default: lead",
                "enum": ["lead", "prospect", "customer", "churned"],
            },
            "source": {
                "type": "string",
                "description": "How the contact was acquired (e.g. 'website', 'referral', 'cold outreach')",
            },
            "notes": {
                "type": "string",
                "description": "Free-text notes about the contact",
            },
            "tags": {
                "type": "string",
                "description": "Comma-separated tags (e.g. 'vip,enterprise,q1-target')",
            },
        },
        "required": ["email"],
    },
)
async def add_contact(
    email: str,
    name: str = "",
    company: str = "",
    phone: str = "",
    status: str = "lead",
    source: str = "",
    notes: str = "",
    tags: str = "",
) -> str:
    db = _require_db()
    email = email.strip().lower()
    if not email:
        return "Error: email is required."

    # Check for duplicate
    existing = await db.fetch_one(
        "SELECT id FROM contacts WHERE email = ?", (email,)
    )
    if existing:
        return f"Error: contact with email '{email}' already exists (ID: {existing['id']}). Use update_contact to modify."

    cursor = await db.execute(
        "INSERT INTO contacts (email, name, company, phone, status, source, notes, tags, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (email, name, company, phone, status, source, notes, tags, _current_agent),
    )
    contact_id = cursor.lastrowid
    return f"Contact added (ID: {contact_id}): {name or email} — {status}"


@tool(
    "list_contacts",
    "Search and list contacts from the CRM.",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "description": "Filter by status: lead, prospect, customer, churned. Leave empty for all.",
            },
            "search": {
                "type": "string",
                "description": "Search term to match against name, email, company, or notes.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum contacts to return (default: 25, max: 100).",
            },
        },
        "required": [],
    },
)
async def list_contacts(
    status: str = "",
    search: str = "",
    limit: int = 25,
) -> str:
    db = _require_db()
    limit = min(max(1, limit), 100)

    conditions: list[str] = []
    params: list[str | int] = []

    if status.strip():
        conditions.append("status = ?")
        params.append(status.strip().lower())

    if search.strip():
        like = f"%{search.strip()}%"
        conditions.append(
            "(name LIKE ? OR email LIKE ? OR company LIKE ? OR notes LIKE ?)"
        )
        params.extend([like, like, like, like])

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    rows = await db.fetch_all(
        f"SELECT * FROM contacts {where} ORDER BY created_at DESC LIMIT ?",
        tuple(params + [limit]),
    )

    if not rows:
        return "No contacts found."

    lines = [f"Contacts ({len(rows)} results):"]
    for r in rows:
        tags_str = f" [{r['tags']}]" if r["tags"] else ""
        lines.append(
            f"  #{r['id']} {r['name'] or '(no name)'} <{r['email']}> "
            f"| {r['status']} | {r['company'] or '-'}{tags_str}"
        )
        if r["notes"]:
            lines.append(f"      Notes: {r['notes'][:100]}")
    return "\n".join(lines)


@tool(
    "update_contact",
    "Update an existing contact in the CRM. Prefix notes with '+' to append instead of replace.",
    {
        "type": "object",
        "properties": {
            "contact_id": {
                "type": "integer",
                "description": "The ID of the contact to update",
            },
            "name": {"type": "string", "description": "New name"},
            "company": {"type": "string", "description": "New company"},
            "phone": {"type": "string", "description": "New phone"},
            "status": {
                "type": "string",
                "description": "New status: lead, prospect, customer, churned",
                "enum": ["lead", "prospect", "customer", "churned"],
            },
            "notes": {
                "type": "string",
                "description": "New notes. Prefix with '+' to append (e.g. '+Called, interested in premium plan')",
            },
            "tags": {
                "type": "string",
                "description": "New comma-separated tags (replaces existing)",
            },
        },
        "required": ["contact_id"],
    },
)
async def update_contact(
    contact_id: int,
    name: str = "",
    company: str = "",
    phone: str = "",
    status: str = "",
    notes: str = "",
    tags: str = "",
) -> str:
    db = _require_db()

    existing = await db.fetch_one(
        "SELECT * FROM contacts WHERE id = ?", (contact_id,)
    )
    if not existing:
        return f"Error: no contact with ID {contact_id}."

    updates: list[str] = []
    params: list[str | int] = []

    if name:
        updates.append("name = ?")
        params.append(name)
    if company:
        updates.append("company = ?")
        params.append(company)
    if phone:
        updates.append("phone = ?")
        params.append(phone)
    if status:
        updates.append("status = ?")
        params.append(status)
    if tags:
        updates.append("tags = ?")
        params.append(tags)
    if notes:
        if notes.startswith("+"):
            # Append mode
            old_notes = existing["notes"] or ""
            separator = "\n" if old_notes else ""
            new_notes = old_notes + separator + notes[1:].strip()
            updates.append("notes = ?")
            params.append(new_notes)
        else:
            updates.append("notes = ?")
            params.append(notes)

    if not updates:
        return "No fields to update."

    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(contact_id)

    await db.execute(
        f"UPDATE contacts SET {', '.join(updates)} WHERE id = ?",
        tuple(params),
    )
    return f"Contact #{contact_id} updated."
