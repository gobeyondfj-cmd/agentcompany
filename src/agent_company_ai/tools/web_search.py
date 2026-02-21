"""Web search tool using httpx."""

from agent_company_ai.tools.registry import tool


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
                headers={"User-Agent": "AgentCompanyAI/0.1"},
            )
            resp.raise_for_status()

            # Extract text snippets from result divs
            html = resp.text
            results = []
            # Simple extraction of result snippets
            parts = html.split('class="result__snippet"')
            for part in parts[1:6]:  # Top 5 results
                end = part.find("</a>")
                if end == -1:
                    end = part.find("</td>")
                snippet = part[:end] if end != -1 else part[:300]
                # Strip HTML tags
                clean = ""
                in_tag = False
                for ch in snippet:
                    if ch == "<":
                        in_tag = True
                    elif ch == ">":
                        in_tag = False
                    elif not in_tag:
                        clean += ch
                clean = clean.strip()
                if clean:
                    results.append(clean)

            if results:
                return f"Search results for '{query}':\n" + "\n---\n".join(results)
            return f"No results found for '{query}'."
    except Exception as e:
        return f"Search failed: {e}"
