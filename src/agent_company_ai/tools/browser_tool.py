"""Browser automation tool — scrape websites, extract data, and submit forms.

Always available (no external API needed). Uses httpx for HTTP requests
and regex for data extraction. Rate-limited to prevent abuse.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool
from agent_company_ai.tools.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"


def set_browser_db(db: Database) -> None:
    global _db
    _db = db


def set_browser_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Browser database not configured.")
    return _db


# Extraction patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)
_LINK_RE = re.compile(r'<a[^>]+href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
_META_RE = re.compile(
    r'<meta\s+(?:name|property)="([^"]*)"[^>]*content="([^"]*)"', re.IGNORECASE
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)
_FORM_RE = re.compile(r"<form[^>]*>(.*?)</form>", re.DOTALL | re.IGNORECASE)
_INPUT_RE = re.compile(
    r'<(?:input|textarea|select)[^>]*(?:name|id)="([^"]*)"[^>]*>', re.IGNORECASE
)
_FORM_ACTION_RE = re.compile(r'<form[^>]*action="([^"]*)"', re.IGNORECASE)
_FORM_METHOD_RE = re.compile(r'<form[^>]*method="([^"]*)"', re.IGNORECASE)
_SOCIAL_RE = re.compile(
    r'href="(https?://(?:www\.)?(?:linkedin|twitter|facebook|instagram|github)\.com/[^"]+)"'
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = _TAG_RE.sub("", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " ")
    return text.strip()


def _strip_scripts(html: str) -> str:
    """Remove script, style, and nav tags from HTML."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
    return html


async def _fetch_page(url: str, timeout: int = 15) -> tuple[str, int]:
    """Fetch a URL and return (html, status_code). Returns ('', 0) on failure."""
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.4)"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            return resp.text, resp.status_code
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            # Incomplete local cert store — retry without verification
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                    resp = await client.get(url, headers=headers)
                    return resp.text, resp.status_code
            except Exception:
                return "", 0
        return "", 0


@tool(
    "browse_page",
    (
        "Browse a web page and extract information. Can extract text content, "
        "links, emails, meta tags, or forms from any public URL. Useful for "
        "research, competitive analysis, and lead generation."
    ),
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to browse",
            },
            "extract": {
                "type": "string",
                "description": "What to extract: text, links, emails, meta, forms, or all (default: all)",
                "enum": ["text", "links", "emails", "meta", "forms", "all"],
            },
        },
        "required": ["url"],
    },
)
async def browse_page(
    url: str,
    extract: str = "all",
) -> str:
    db = _require_db()

    if not url.strip():
        return "Error: url is required."

    # Normalize URL
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # Rate limit
    rl = RateLimiter.get()
    if not rl.check("browse_hourly"):
        return (
            f"Rate limit reached for browsing "
            f"({rl.remaining('browse_hourly')} remaining this hour). Try again later."
        )
    if not rl.check("browse_daily"):
        return (
            f"Daily browse rate limit reached "
            f"({rl.remaining('browse_daily')} remaining today). Try again later."
        )

    html, status_code = await _fetch_page(url)

    if not html:
        return f"Failed to fetch {url} (status: {status_code or 'connection error'})."

    rl.record("browse_hourly")
    rl.record("browse_daily")

    cleaned = _strip_scripts(html)
    result_parts: list[str] = [f"Browsed: {url} (status: {status_code})"]

    extracted_emails: list[str] = []
    extracted_links: list[str] = []

    if extract in ("text", "all"):
        text = _strip_tags(cleaned)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Truncate to ~5000 chars
        if len(text) > 5000:
            text = text[:5000] + "... (truncated)"
        result_parts.append(f"\n--- Text Content ---\n{text}")

    if extract in ("links", "all"):
        links = _LINK_RE.findall(cleaned)
        unique_links = []
        seen = set()
        for href, link_text in links:
            if href and href not in seen and not href.startswith("#") and not href.startswith("javascript:"):
                seen.add(href)
                clean_text = _strip_tags(link_text).strip()[:80]
                unique_links.append(f"  {clean_text or '(no text)'}: {href}")
                extracted_links.append(href)
        if unique_links:
            result_parts.append(f"\n--- Links ({len(unique_links)}) ---")
            result_parts.extend(unique_links[:50])  # Cap at 50 links

    if extract in ("emails", "all"):
        emails = list(set(_EMAIL_RE.findall(cleaned)))
        extracted_emails = emails
        if emails:
            result_parts.append(f"\n--- Emails ({len(emails)}) ---")
            for email in sorted(emails)[:20]:
                result_parts.append(f"  {email}")

    if extract in ("meta", "all"):
        title_match = _TITLE_RE.search(html)
        title = _strip_tags(title_match.group(1)) if title_match else "(no title)"
        metas = _META_RE.findall(html)
        result_parts.append(f"\n--- Meta ---\n  Title: {title}")
        for name, content in metas[:20]:
            result_parts.append(f"  {name}: {content}")

    if extract in ("forms", "all"):
        forms = _FORM_RE.findall(html)
        if forms:
            result_parts.append(f"\n--- Forms ({len(forms)}) ---")
            for i, form_html in enumerate(forms[:5], 1):
                action = _FORM_ACTION_RE.search(f"<form>{form_html}")
                method = _FORM_METHOD_RE.search(f"<form>{form_html}")
                fields = _INPUT_RE.findall(form_html)
                result_parts.append(
                    f"  Form {i}: action={action.group(1) if action else '(none)'} "
                    f"method={method.group(1) if method else 'GET'} "
                    f"fields={fields}"
                )

    # Log to DB
    await db.execute(
        "INSERT INTO browse_log (url, status_code, extract_mode, extracted_emails_count, extracted_links_count, browsed_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (url, status_code, extract, len(extracted_emails), len(extracted_links), _current_agent),
    )

    return "\n".join(result_parts)


@tool(
    "extract_contacts_from_url",
    (
        "Extract contact information (emails, phones, social links) from a "
        "website. Automatically checks the main page plus /contact and /about "
        "pages for comprehensive results."
    ),
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The website URL to extract contacts from",
            },
        },
        "required": ["url"],
    },
)
async def extract_contacts_from_url(
    url: str,
) -> str:
    db = _require_db()

    if not url.strip():
        return "Error: url is required."

    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # Rate limit
    rl = RateLimiter.get()
    if not rl.check("browse_hourly"):
        return (
            f"Rate limit reached for browsing "
            f"({rl.remaining('browse_hourly')} remaining this hour). Try again later."
        )

    # Determine base URL and pages to check
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    pages = [url]
    contact_url = f"{base}/contact"
    about_url = f"{base}/about"
    if contact_url != url:
        pages.append(contact_url)
    if about_url != url:
        pages.append(about_url)

    all_emails: set[str] = set()
    all_phones: set[str] = set()
    all_socials: set[str] = set()
    pages_checked = 0

    for page_url in pages[:3]:  # Max 3 pages
        html, status = await _fetch_page(page_url)
        if not html or status != 200:
            continue
        pages_checked += 1
        cleaned = _strip_scripts(html)
        all_emails.update(_EMAIL_RE.findall(cleaned))
        all_phones.update(_PHONE_RE.findall(cleaned))
        all_socials.update(_SOCIAL_RE.findall(cleaned))

    rl.record("browse_hourly")
    rl.record("browse_daily")

    # Log
    await db.execute(
        "INSERT INTO browse_log (url, status_code, extract_mode, extracted_emails_count, extracted_links_count, browsed_by) "
        "VALUES (?, ?, 'contacts', ?, ?, ?)",
        (url, 200 if pages_checked > 0 else 0, len(all_emails), len(all_socials), _current_agent),
    )

    if not all_emails and not all_phones and not all_socials:
        return (
            f"No contact information found on {url} "
            f"(checked {pages_checked} pages). The site may block scraping."
        )

    result = {
        "url": url,
        "pages_checked": pages_checked,
        "emails": sorted(all_emails),
        "phones": sorted(all_phones),
        "social_links": sorted(all_socials),
    }

    return json.dumps(result, indent=2)


@tool(
    "submit_form",
    (
        "Submit a form to a URL via POST or GET. Useful for signing up for "
        "newsletters, submitting contact forms, or interacting with web services."
    ),
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to submit the form to",
            },
            "form_data": {
                "type": "string",
                "description": 'JSON string of form fields: {"name": "...", "email": "..."}',
            },
            "method": {
                "type": "string",
                "description": "HTTP method: POST or GET (default: POST)",
                "enum": ["POST", "GET"],
            },
        },
        "required": ["url", "form_data"],
    },
)
async def submit_form(
    url: str,
    form_data: str,
    method: str = "POST",
) -> str:
    import httpx

    db = _require_db()

    if not url.strip():
        return "Error: url is required."

    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://{url}"

    # Parse form data
    try:
        data = json.loads(form_data)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in form_data: {e}"

    if not isinstance(data, dict):
        return "Error: form_data must be a JSON object."

    method = method.upper()
    if method not in ("POST", "GET"):
        return "Error: method must be POST or GET."

    # Rate limit
    rl = RateLimiter.get()
    if not rl.check("browse_hourly"):
        return (
            f"Rate limit reached for browsing "
            f"({rl.remaining('browse_hourly')} remaining this hour). Try again later."
        )

    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.4)"}
            if method == "POST":
                resp = await client.post(url, data=data, headers=headers)
            else:
                resp = await client.get(url, params=data, headers=headers)
    except Exception as e:
        return f"Form submission failed: {e}"

    rl.record("browse_hourly")
    rl.record("browse_daily")

    # Log
    await db.execute(
        "INSERT INTO browse_log (url, status_code, extract_mode, extracted_emails_count, extracted_links_count, browsed_by) "
        "VALUES (?, ?, 'form_submit', 0, 0, ?)",
        (url, resp.status_code, _current_agent),
    )

    # Truncate response body
    body_preview = resp.text[:2000] if resp.text else "(empty response)"
    body_preview = _strip_tags(body_preview).strip()[:1000]

    return (
        f"Form submitted to {url}\n"
        f"  Method: {method}\n"
        f"  Status: {resp.status_code}\n"
        f"  Response preview: {body_preview}"
    )
