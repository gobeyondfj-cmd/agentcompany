"""Social media draft tools — saves drafts for human review.

Drafts are stored in SQLite. Nothing is auto-posted; all posts require
human review before publishing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"

# Platform character limits
PLATFORM_LIMITS: dict[str, int] = {
    "twitter": 280,
    "linkedin": 3000,
    "facebook": 63206,
    "instagram": 2200,
    "threads": 500,
}


def set_social_db(db: Database) -> None:
    global _db
    _db = db


def set_social_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Social media database not configured.")
    return _db


@tool(
    "draft_social_post",
    (
        "Create a social media post draft for human review. "
        "NOT auto-posted — the draft is saved for manual publishing."
    ),
    {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "Target platform",
                "enum": ["twitter", "linkedin", "facebook", "instagram", "threads"],
            },
            "content": {
                "type": "string",
                "description": "The post text content",
            },
            "hashtags": {
                "type": "string",
                "description": "Comma-separated hashtags (without # prefix, e.g. 'ai,startup,saas')",
            },
        },
        "required": ["platform", "content"],
    },
)
async def draft_social_post(
    platform: str,
    content: str,
    hashtags: str = "",
) -> str:
    db = _require_db()
    platform = platform.strip().lower()

    if platform not in PLATFORM_LIMITS:
        return f"Error: unsupported platform '{platform}'. Use: {', '.join(PLATFORM_LIMITS)}"

    # Check character limit
    char_limit = PLATFORM_LIMITS[platform]
    # Include hashtags in character count for platforms that embed them
    full_text = content
    if hashtags:
        tag_str = " " + " ".join(f"#{t.strip()}" for t in hashtags.split(",") if t.strip())
        full_text = content + tag_str

    if len(full_text) > char_limit:
        return (
            f"Error: content is {len(full_text)} characters but {platform} "
            f"limit is {char_limit}. Please shorten the post."
        )

    cursor = await db.execute(
        "INSERT INTO social_drafts (platform, content, hashtags, status, created_by) "
        "VALUES (?, ?, ?, 'draft', ?)",
        (platform, content, hashtags, _current_agent),
    )
    draft_id = cursor.lastrowid
    return (
        f"Social draft saved (ID: {draft_id}) for {platform}.\n"
        f"  Content: {content[:100]}{'...' if len(content) > 100 else ''}\n"
        f"  Hashtags: {hashtags or '(none)'}\n"
        f"  Status: draft (awaiting human review)"
    )


@tool(
    "list_social_drafts",
    "List saved social media post drafts.",
    {
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "description": "Filter by platform. Leave empty for all.",
            },
            "status": {
                "type": "string",
                "description": "Filter by status: draft, approved, posted, rejected. Leave empty for all.",
            },
        },
        "required": [],
    },
)
async def list_social_drafts(
    platform: str = "",
    status: str = "",
) -> str:
    db = _require_db()

    conditions: list[str] = []
    params: list[str] = []

    if platform.strip():
        conditions.append("platform = ?")
        params.append(platform.strip().lower())
    if status.strip():
        conditions.append("status = ?")
        params.append(status.strip().lower())

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    rows = await db.fetch_all(
        f"SELECT * FROM social_drafts {where} ORDER BY created_at DESC LIMIT 50",
        tuple(params),
    )

    if not rows:
        return "No social drafts found."

    lines = [f"Social drafts ({len(rows)}):"]
    for r in rows:
        tags = f" #{r['hashtags'].replace(',', ' #')}" if r["hashtags"] else ""
        lines.append(
            f"  #{r['id']} [{r['platform']}] ({r['status']}) "
            f"{r['content'][:80]}{'...' if len(r['content']) > 80 else ''}{tags}"
        )
    return "\n".join(lines)
