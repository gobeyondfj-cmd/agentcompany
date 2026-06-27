"""Webhook tool -- send HTTP webhooks to Zapier, Make.com, n8n, Slack, Discord."""
from __future__ import annotations
import json
from agent_company_ai.tools.registry import tool

_ALLOWED_METHODS = set(["POST", "GET", "PUT", "PATCH"])
_MAX_PAYLOAD_BYTES = 65536

def _truncate(s: str, max_len: int = 200) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


_SEND_WEBHOOK_SCHEMA = dict(
    type="object",
    properties=dict(
        url=dict(type="string", description="The full webhook URL to POST to"),
        payload=dict(type="object", description="JSON payload to send as the request body"),
        method=dict(type="string", enum=["POST","GET","PUT","PATCH"], description="HTTP method (default: POST)"),
        headers=dict(type="object", description="Optional extra HTTP headers as key-value pairs"),
        timeout=dict(type="integer", description="Request timeout in seconds (default: 15, max: 60)"),
    ),
    required=["url", "payload"],
)


@tool(
    "send_webhook",
    (
        "Send an HTTP webhook to any URL -- Zapier, Make.com, n8n, custom APIs, etc. "
        "Sends a JSON payload via POST (default) or another method. "
        "Use this to trigger external automation workflows, notify services, "
        "or push data to third-party systems."
    ),
    _SEND_WEBHOOK_SCHEMA,
)
async def send_webhook(
    url: str,
    payload: dict,
    method: str = "POST",
    headers: dict | None = None,
    timeout: int = 15,
) -> str:
    import httpx

    method = method.upper()
    if method not in _ALLOWED_METHODS:
        allowed = ", ".join(sorted(_ALLOWED_METHODS))
        return f"Error: method not allowed. Allowed: {allowed}"

    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"

    timeout = min(max(1, timeout), 60)

    body = json.dumps(payload)
    if len(body.encode()) > _MAX_PAYLOAD_BYTES:
        sz = len(body.encode())
        return f"Error: payload too large ({sz} bytes, max {_MAX_PAYLOAD_BYTES})"

    req_headers = dict()
    req_headers["Content-Type"] = "application/json"
    req_headers["User-Agent"] = "AgentCompanyAI/0.5"
    if headers:
        for k, v in headers.items():
            req_headers[str(k)] = str(v)

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            if method == "GET":
                resp = await client.get(url, params=payload, headers=req_headers)
            else:
                resp = await client.request(method, url, content=body, headers=req_headers)

        status = resp.status_code
        preview = _truncate(resp.text.strip(), 300) if resp.text.strip() else "(empty response)"

        if 200 <= status < 300:
            return (
                f"Webhook sent successfully.\n"
                f"  Status: {status}\n"
                f"  URL: {url}\n"
                f"  Method: {method}\n"
                f"  Response: {preview}"
            )
        return (
            f"Webhook returned non-success status {status}.\n"
            f"  URL: {url}\n"
            f"  Response: {preview}"
        )

    except Exception as exc:
        return f"Webhook failed: {exc}"


_SLACK_SCHEMA = dict(
    type="object",
    properties=dict(
        webhook_url=dict(type="string", description="Slack Incoming Webhook URL (hooks.slack.com/services/...)"),
        message=dict(type="string", description="Main message text (supports Slack mrkdwn: *bold*, _italic_)"),
        header=dict(type="string", description="Optional header title shown above the message"),
        context=dict(type="string", description="Optional footer context line in smaller text"),
        emoji=dict(type="string", description="Optional emoji prefix e.g. :rocket: or :white_check_mark:"),
    ),
    required=["webhook_url", "message"],
)


@tool(
    "send_slack_notification",
    (
        "Send a notification message to a Slack channel via an Incoming Webhook URL. "
        "Supports plain text and optional header/footer blocks. "
        "Set up a Slack Incoming Webhook at api.slack.com/apps and paste the URL here."
    ),
    _SLACK_SCHEMA,
)
async def send_slack_notification(
    webhook_url: str,
    message: str,
    header: str = "",
    context: str = "",
    emoji: str = "",
) -> str:
    import httpx

    if not webhook_url.startswith("https://hooks.slack.com/"):
        return (
            "Error: webhook_url must be a Slack Incoming Webhook URL "
            "(starts with https://hooks.slack.com/services/...)."
        )

    text = (emoji + " " + message).strip() if emoji else message
    blocks: list[dict] = []

    if header:
        blk = dict()
        blk["type"] = "header"
        blk_txt = dict()
        blk_txt["type"] = "plain_text"
        blk_txt["text"] = header[:150]
        blk_txt["emoji"] = True
        blk["text"] = blk_txt
        blocks.append(blk)

    sec = dict()
    sec["type"] = "section"
    sec_txt = dict()
    sec_txt["type"] = "mrkdwn"
    sec_txt["text"] = text[:3000]
    sec["text"] = sec_txt
    blocks.append(sec)

    if context:
        ctx = dict()
        ctx["type"] = "context"
        ctx_el = dict()
        ctx_el["type"] = "mrkdwn"
        ctx_el["text"] = context[:300]
        ctx["elements"] = [ctx_el]
        blocks.append(ctx)

    payload = dict()
    payload["text"] = text[:3000]
    payload["blocks"] = blocks
    body = json.dumps(payload)

    req_headers = dict()
    req_headers["Content-Type"] = "application/json"
    req_headers["User-Agent"] = "AgentCompanyAI/0.5"

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(webhook_url, content=body, headers=req_headers)

        if resp.status_code == 200 and resp.text.strip() == "ok":
            return f"Slack notification sent. Message: {_truncate(text, 100)}"
        return (
            f"Slack webhook returned status {resp.status_code}. "
            f"Response: {_truncate(resp.text.strip(), 200)}"
        )

    except Exception as exc:
        return f"Slack notification failed: {exc}"


_DISCORD_SCHEMA = dict(
    type="object",
    properties=dict(
        webhook_url=dict(type="string", description="Discord webhook URL (discord.com/api/webhooks/...)"),
        message=dict(type="string", description="The message text to send (max 2000 characters)"),
        username=dict(type="string", description="Optional display name override (default: Agent Company AI)"),
        embed_title=dict(type="string", description="Optional embed title -- triggers a rich embed card"),
        embed_color=dict(type="integer", description="Embed color as decimal int (5763719=green, 15548997=red)"),
    ),
    required=["webhook_url", "message"],
)


@tool(
    "send_discord_notification",
    (
        "Send a notification message to a Discord channel via a webhook URL. "
        "Supports username override and optional rich embed with title/color. "
        "Create a Discord webhook in channel Settings -> Integrations -> Webhooks."
    ),
    _DISCORD_SCHEMA,
)
async def send_discord_notification(
    webhook_url: str,
    message: str,
    username: str = "Agent Company AI",
    embed_title: str = "",
    embed_color: int = 5763719,
) -> str:
    import httpx

    if not webhook_url.startswith("https://discord.com/api/webhooks/"):
        return (
            "Error: webhook_url must be a Discord webhook URL "
            "(starts with https://discord.com/api/webhooks/...)."
        )

    payload = dict()
    payload["content"] = message[:2000]
    payload["username"] = (username or "Agent Company AI")[:80]

    if embed_title:
        emb = dict()
        emb["title"] = embed_title[:256]
        emb["description"] = message[:4096]
        emb["color"] = max(0, min(embed_color, 16777215))
        payload["embeds"] = [emb]
        payload["content"] = ""

    body = json.dumps(payload)

    req_headers = dict()
    req_headers["Content-Type"] = "application/json"
    req_headers["User-Agent"] = "AgentCompanyAI/0.5"

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.post(webhook_url, content=body, headers=req_headers)

        if resp.status_code in (200, 204):
            return f"Discord notification sent. Message: {_truncate(message, 100)}"
        return (
            f"Discord webhook returned status {resp.status_code}. "
            f"Response: {_truncate(resp.text.strip(), 200)}"
        )

    except Exception as exc:
        return f"Discord notification failed: {exc}"

