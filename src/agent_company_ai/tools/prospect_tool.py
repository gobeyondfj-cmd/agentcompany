"""Lead prospecting tool — find leads via web scraping, extract contacts, auto-add to CRM.

Always available (no external API needed). Uses DuckDuckGo HTML search and
httpx for scraping. Rate-limited to prevent abuse.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool
from agent_company_ai.tools.rate_limiter import RateLimiter

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"


def set_prospect_db(db: Database) -> None:
    global _db
    _db = db


def set_prospect_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Prospect database not configured.")
    return _db


# Regex patterns (same as web_search.py)
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div|span)',
    re.DOTALL,
)
_TITLE_RE = re.compile(
    r'class="result__a"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_URL_TEXT_RE = re.compile(
    r'class="result__url"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")

# Contact extraction patterns
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)
_SOCIAL_RE = re.compile(
    r'href="(https?://(?:www\.)?(?:linkedin|twitter|facebook|instagram)\.com/[^"]+)"'
)


def _strip_tags(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = _TAG_RE.sub("", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " ")
    return text.strip()


def _extract_urls(html: str) -> list[str]:
    """Extract clean URLs from DuckDuckGo result__url elements.

    DDG wraps URLs in redirects (//duckduckgo.com/l/?uddg=...).  We first
    try the visible URL text (cleanest), then fall back to decoding the uddg
    query parameter from the href.
    """
    url_texts = _URL_TEXT_RE.findall(html)
    urls: list[str] = []
    for raw in url_texts:
        clean = _strip_tags(raw).strip().rstrip("/")
        if clean and "duckduckgo.com" not in clean:
            if not clean.startswith("http"):
                clean = "https://" + clean
            urls.append(clean)
        else:
            urls.append("")
    return urls


def _strip_scripts(html: str) -> str:
    """Remove script, style, and nav tags from HTML."""
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
    return html


async def _fetch_page(url: str, timeout: int = 10) -> str:
    """Fetch a page and return its HTML, or empty string on failure."""
    import httpx

    headers = {"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.4)"}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.text
    except Exception as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            # Incomplete local cert store — retry without verification
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        return resp.text
            except Exception:
                pass
        # Other connection errors — return empty
    return ""


async def _extract_contacts_from_domain(domain: str) -> dict:
    """Scrape /, /about, /contact, /team pages to extract contact info."""
    base = domain.rstrip("/")
    if not base.startswith("http"):
        base = f"https://{base}"

    pages = [base, f"{base}/about", f"{base}/contact", f"{base}/team"]

    all_emails: set[str] = set()
    all_phones: set[str] = set()
    all_socials: set[str] = set()

    for page_url in pages:
        html = await _fetch_page(page_url)
        if not html:
            continue
        cleaned = _strip_scripts(html)
        all_emails.update(_EMAIL_RE.findall(cleaned))
        all_phones.update(_PHONE_RE.findall(cleaned))
        all_socials.update(_SOCIAL_RE.findall(cleaned))

    return {
        "emails": sorted(all_emails),
        "phones": sorted(all_phones),
        "social_links": sorted(all_socials),
    }


@tool(
    "prospect_search",
    (
        "Search the web for potential leads/prospects in a specific industry. "
        "Returns company names, descriptions, and URLs. Use this to build a "
        "list of potential customers to reach out to."
    ),
    {
        "type": "object",
        "properties": {
            "industry": {
                "type": "string",
                "description": "Industry to search for (e.g. 'SaaS', 'ecommerce', 'healthcare')",
            },
            "keywords": {
                "type": "string",
                "description": "Additional keywords to narrow the search (e.g. 'AI startup', 'B2B software')",
            },
            "location": {
                "type": "string",
                "description": "Geographic location filter (e.g. 'US', 'San Francisco', 'Europe')",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (default: 10, max: 20)",
            },
        },
        "required": ["industry", "keywords"],
    },
)
async def prospect_search(
    industry: str,
    keywords: str,
    location: str = "",
    max_results: int = 10,
) -> str:
    import httpx

    db = _require_db()
    max_results = min(max(1, max_results), 20)

    # Rate limit
    rl = RateLimiter.get()
    if not rl.check("prospect_hourly"):
        return (
            f"Rate limit reached for prospect searches "
            f"({rl.remaining('prospect_hourly')} remaining this hour). Try again later."
        )

    # Build search query
    query_parts = [industry, keywords, "company"]
    if location:
        query_parts.append(location)
    query = " ".join(query_parts)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.4)"},
            )
            resp.raise_for_status()

            html = resp.text
            if not html:
                return f"No prospects found for '{query}'."

            snippets = _SNIPPET_RE.findall(html)
            titles = _TITLE_RE.findall(html)
            urls = _extract_urls(html)

            results = []
            for i in range(min(len(snippets), max_results)):
                title = _strip_tags(titles[i]) if i < len(titles) else ""
                snippet = _strip_tags(snippets[i])
                url = urls[i] if i < len(urls) else ""
                if not snippet:
                    continue
                results.append({
                    "title": title,
                    "description": snippet,
                    "url": url,
                })

    except Exception as e:
        return f"Prospect search failed: {e}"

    # Rate limit + log
    rl.record("prospect_hourly")
    rl.record("prospect_daily")

    await db.execute(
        "INSERT INTO prospect_searches (query, industry, location, results_count, searched_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (query, industry, location, len(results), _current_agent),
    )

    if not results:
        return f"No prospects found for '{query}'."

    lines = [f"Found {len(results)} prospects for '{industry} {keywords}':"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. **{r['title']}**")
        if r["url"]:
            lines.append(f"   URL: {r['url']}")
        lines.append(f"   {r['description']}")

    return "\n".join(lines)


@tool(
    "enrich_contact",
    (
        "Enrich a company's contact information by scraping their website. "
        "Extracts emails, phone numbers, and social media links from the "
        "company's homepage, about page, contact page, and team page."
    ),
    {
        "type": "object",
        "properties": {
            "company_name": {
                "type": "string",
                "description": "Name of the company to research",
            },
            "domain": {
                "type": "string",
                "description": "Company website domain (e.g. 'example.com'). If omitted, will search for it.",
            },
        },
        "required": ["company_name"],
    },
)
async def enrich_contact(
    company_name: str,
    domain: str = "",
) -> str:
    import httpx
    import json

    if not domain:
        # Search for the company's website
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": f"{company_name} official website"},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.4)"},
                )
                resp.raise_for_status()
                urls = _extract_urls(resp.text)
                if urls and urls[0]:
                    # Use the first result's domain
                    from urllib.parse import urlparse
                    parsed = urlparse(urls[0])
                    domain = parsed.netloc or parsed.path.split("/")[0]
        except Exception:
            pass

    if not domain:
        return f"Could not find website for '{company_name}'. Please provide a domain."

    # Clean domain
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        from urllib.parse import urlparse
        domain = urlparse(domain).netloc or domain

    contacts = await _extract_contacts_from_domain(domain)

    result = {
        "company": company_name,
        "domain": domain,
        "emails": contacts["emails"],
        "phones": contacts["phones"],
        "social_links": contacts["social_links"],
    }

    if not contacts["emails"] and not contacts["phones"] and not contacts["social_links"]:
        return (
            f"No contact information found for {company_name} ({domain}). "
            f"The website may block scraping or have no public contact info."
        )

    return json.dumps(result, indent=2)


@tool(
    "prospect_campaign",
    (
        "Run a full prospecting campaign: search for companies, scrape their "
        "contact info, and optionally add them to the CRM. Combines "
        "prospect_search + enrich_contact + CRM insert in one step."
    ),
    {
        "type": "object",
        "properties": {
            "industry": {
                "type": "string",
                "description": "Industry to target (e.g. 'SaaS', 'fintech')",
            },
            "keywords": {
                "type": "string",
                "description": "Search keywords (e.g. 'AI startup Series A')",
            },
            "location": {
                "type": "string",
                "description": "Geographic filter (e.g. 'US', 'New York')",
            },
            "max_prospects": {
                "type": "integer",
                "description": "Maximum prospects to find (default: 5, max: 15)",
            },
            "add_to_crm": {
                "type": "boolean",
                "description": "Whether to add found contacts to the CRM (default: true)",
            },
        },
        "required": ["industry", "keywords"],
    },
)
async def prospect_campaign(
    industry: str,
    keywords: str,
    location: str = "",
    max_prospects: int = 5,
    add_to_crm: bool = True,
) -> str:
    import httpx
    from urllib.parse import urlparse

    db = _require_db()
    max_prospects = min(max(1, max_prospects), 15)

    # Rate limit
    rl = RateLimiter.get()
    if not rl.check("prospect_hourly"):
        return (
            f"Rate limit reached for prospect searches "
            f"({rl.remaining('prospect_hourly')} remaining this hour). Try again later."
        )

    # Step 1: Search for companies
    query_parts = [industry, keywords, "company"]
    if location:
        query_parts.append(location)
    query = " ".join(query_parts)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.4)"},
            )
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        return f"Prospect campaign search failed: {e}"

    snippets = _SNIPPET_RE.findall(html)
    titles = _TITLE_RE.findall(html)
    urls = _extract_urls(html)

    rl.record("prospect_hourly")
    rl.record("prospect_daily")

    # Log the search
    await db.execute(
        "INSERT INTO prospect_searches (query, industry, location, results_count, searched_by) "
        "VALUES (?, ?, ?, ?, ?)",
        (query, industry, location, min(len(snippets), max_prospects), _current_agent),
    )

    # Step 2: Enrich each result
    prospects = []
    contacts_added = 0

    for i in range(min(len(titles), max_prospects)):
        title = _strip_tags(titles[i]) if i < len(titles) else "Unknown"
        url = urls[i] if i < len(urls) else ""

        # Extract domain from URL
        domain = ""
        if url:
            try:
                parsed = urlparse(url if url.startswith("http") else f"https://{url}")
                domain = parsed.netloc or parsed.path.split("/")[0]
            except Exception:
                pass

        prospect = {
            "company": title,
            "url": url,
            "domain": domain,
            "emails": [],
            "phones": [],
        }

        # Try to enrich if we have a domain
        if domain:
            try:
                contacts = await _extract_contacts_from_domain(domain)
                prospect["emails"] = contacts["emails"]
                prospect["phones"] = contacts["phones"]
            except Exception:
                pass

        prospects.append(prospect)

        # Step 3: Add to CRM if requested
        if add_to_crm and prospect["emails"]:
            for email in prospect["emails"][:3]:  # Max 3 contacts per company
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO contacts (email, name, company, phone, status, source, notes, created_by) "
                        "VALUES (?, ?, ?, ?, 'lead', 'prospect_campaign', ?, ?)",
                        (
                            email.lower(),
                            "",
                            title,
                            prospect["phones"][0] if prospect["phones"] else "",
                            f"Found via prospect campaign: {industry} {keywords}",
                            _current_agent,
                        ),
                    )
                    contacts_added += 1
                except Exception:
                    pass

    # Build report
    lines = [
        f"Prospect campaign complete for '{industry} {keywords}':",
        f"  Companies found: {len(prospects)}",
        f"  Contacts added to CRM: {contacts_added}",
        "",
    ]

    for i, p in enumerate(prospects, 1):
        lines.append(f"{i}. **{p['company']}**")
        if p["domain"]:
            lines.append(f"   Domain: {p['domain']}")
        if p["emails"]:
            lines.append(f"   Emails: {', '.join(p['emails'][:5])}")
        if p["phones"]:
            lines.append(f"   Phones: {', '.join(p['phones'][:3])}")
        if not p["emails"] and not p["phones"]:
            lines.append("   (no contact info found)")
        lines.append("")

    return "\n".join(lines)
