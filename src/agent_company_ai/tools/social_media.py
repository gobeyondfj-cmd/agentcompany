"""Social media draft and publishing tools.

Drafts are stored in SQLite. ``publish_social_post`` publishes a draft to
Twitter/X via the v2 API using OAuth 1.0a (stdlib only — no extra deps).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse
from typing import TYPE_CHECKING

import httpx

from agent_company_ai.tools.registry import tool
from agent_company_ai.tools.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"

# Twitter config state
_twitter_api_key: str = ""
_twitter_api_secret: str = ""
_twitter_access_token: str = ""
_twitter_access_token_secret: str = ""
_twitter_enabled: bool = False

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


def set_twitter_config(
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
) -> None:
    global _twitter_api_key, _twitter_api_secret
    global _twitter_access_token, _twitter_access_token_secret, _twitter_enabled
    _twitter_api_key = api_key
    _twitter_api_secret = api_secret
    _twitter_access_token = access_token
    _twitter_access_token_secret = access_token_secret
    _twitter_enabled = True


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Social media database not configured.")
    return _db


def _require_twitter() -> None:
    if not _twitter_enabled:
        raise RuntimeError(
            "Twitter not configured. Set twitter.enabled: true and provide "
            "API keys in your config.yaml integrations section."
        )


# ---------------------------------------------------------------------------
# OAuth 1.0a helpers (stdlib only)
# ---------------------------------------------------------------------------

def _percent_encode(s: str) -> str:
    """RFC 5849 percent-encode."""
    return urllib.parse.quote(s, safe="")


def _oauth1_header(
    method: str,
    url: str,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
) -> str:
    """Build an OAuth 1.0a Authorization header value.

    For JSON-body requests (like Twitter v2), only the oauth params go into
    the signature base string — the request body is excluded.
    """
    nonce = secrets.token_hex(16)
    timestamp = str(int(time.time()))

    oauth_params = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_token": token,
        "oauth_version": "1.0",
    }

    # Signature base string
    sorted_params = "&".join(
        f"{_percent_encode(k)}={_percent_encode(v)}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = (
        f"{method.upper()}&{_percent_encode(url)}&{_percent_encode(sorted_params)}"
    )

    signing_key = f"{_percent_encode(consumer_secret)}&{_percent_encode(token_secret)}"
    sig = hmac.new(
        signing_key.encode(), base_string.encode(), hashlib.sha1
    ).digest()
    oauth_params["oauth_signature"] = base64.b64encode(sig).decode()

    header_parts = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


async def _publish_to_twitter(text: str) -> str:
    """POST a tweet via Twitter API v2. Returns the tweet ID."""
    url = "https://api.twitter.com/2/tweets"
    auth_header = _oauth1_header(
        method="POST",
        url=url,
        consumer_key=_twitter_api_key,
        consumer_secret=_twitter_api_secret,
        token=_twitter_access_token,
        token_secret=_twitter_access_token_secret,
    )
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, headers=headers, json={"text": text})
    if resp.status_code not in (200, 201):
        raise RuntimeError(
            f"Twitter API error {resp.status_code}: {resp.text}"
        )
    data = resp.json()
    return data["data"]["id"]


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


@tool(
    "publish_social_post",
    (
        "Publish a saved social media draft to its platform. "
        "Currently supports Twitter/X. The draft must exist and have status 'draft'."
    ),
    {
        "type": "object",
        "properties": {
            "draft_id": {
                "type": "integer",
                "description": "ID of the social draft to publish (from draft_social_post or list_social_drafts)",
            },
        },
        "required": ["draft_id"],
    },
)
async def publish_social_post(draft_id: int) -> str:
    db = _require_db()

    # 1. Fetch draft
    row = await db.fetch_one(
        "SELECT * FROM social_drafts WHERE id = ?", (draft_id,)
    )
    if not row:
        return f"Error: no social draft with ID {draft_id}."

    # 2. Validate status
    if row["status"] == "published":
        pub_id = row.get("published_id", "")
        return (
            f"Error: draft {draft_id} is already published"
            f"{f' (tweet ID: {pub_id})' if pub_id else ''}."
        )
    if row["status"] != "draft":
        return f"Error: draft {draft_id} has status '{row['status']}', expected 'draft'."

    # 3. Validate platform
    platform = row["platform"]
    if platform != "twitter":
        return (
            f"Error: publish_social_post currently supports Twitter only. "
            f"Draft {draft_id} targets '{platform}'."
        )

    # 4. Check Twitter config
    try:
        _require_twitter()
    except RuntimeError as e:
        return f"Error: {e}"

    # 5. Rate limit
    rl = RateLimiter.get()
    if not rl.check("tweets_daily"):
        remaining = rl.remaining("tweets_daily")
        return (
            f"Error: Twitter daily rate limit reached ({remaining} remaining). "
            f"Try again later."
        )

    # 6. Build tweet text
    text = row["content"]
    if row["hashtags"]:
        tags = " ".join(f"#{t.strip()}" for t in row["hashtags"].split(",") if t.strip())
        text = f"{text} {tags}"

    # 7. Publish
    try:
        tweet_id = await _publish_to_twitter(text)
    except RuntimeError as e:
        return f"Error publishing to Twitter: {e}"

    # 8. Record rate limit + update DB
    rl.record("tweets_daily")
    await db.execute(
        "UPDATE social_drafts SET status = 'published', published_id = ?, "
        "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (tweet_id, draft_id),
    )

    tweet_url = f"https://x.com/i/status/{tweet_id}"
    return (
        f"Tweet published successfully!\n"
        f"  Draft ID: {draft_id}\n"
        f"  Tweet ID: {tweet_id}\n"
        f"  URL: {tweet_url}\n"
        f"  Remaining today: {rl.remaining('tweets_daily')}"
    )
