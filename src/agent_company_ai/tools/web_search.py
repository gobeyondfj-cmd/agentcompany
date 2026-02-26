"""Web search tool using httpx."""

import re

from agent_company_ai.tools.registry import tool

# Regex patterns for DuckDuckGo HTML result extraction
_SNIPPET_RE = re.compile(
    r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div|span)',
    re.DOTALL,
)
_TITLE_RE = re.compile(
    r'class="result__a"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = _TAG_RE.sub("", html)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#x27;", "'").replace("&nbsp;", " ")
    return text.strip()


@tool(
    "web_search",
    "Search the web for information. Returns a summary of search results.",
    {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
)
async def web_search(query: str) -> str:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Use DuckDuckGo HTML search (no API key needed)
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; AgentCompanyAI/0.3)"},
            )
            resp.raise_for_status()

            html = resp.text
            if not html:
                return f"No results found for '{query}'."

            # Extract snippets using regex (resilient to minor HTML changes)
            snippets = _SNIPPET_RE.findall(html)
            titles = _TITLE_RE.findall(html)

            results = []
            for i, snippet in enumerate(snippets[:5]):
                clean_snippet = _strip_tags(snippet)
                if not clean_snippet:
                    continue
                title = _strip_tags(titles[i]) if i < len(titles) else ""
                if title:
                    results.append(f"**{title}**\n{clean_snippet}")
                else:
                    results.append(clean_snippet)

            if results:
                return f"Search results for '{query}':\n" + "\n---\n".join(results)
            return f"No results found for '{query}'."
    except Exception as e:
        return f"Search failed: {e}"
