"""Landing page generator tool — builds styled HTML from structured content.

No external API needed. Agents provide headline, body sections, CTA, etc.
and the tool generates a polished HTML page from a built-in template.
Saved to the company's landing_pages/ directory and logged in the database.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_output_dir: Path | None = None
_company_dir: Path | None = None


def set_landing_page_db(db: Database) -> None:
    global _db
    _db = db


def set_landing_page_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def set_landing_page_config(output_dir_name: str) -> None:
    """Set the output directory name (relative to company dir)."""
    global _output_dir
    if _company_dir:
        _output_dir = _company_dir / output_dir_name
        _output_dir.mkdir(parents=True, exist_ok=True)


def set_landing_page_company_dir(company_dir: Path) -> None:
    global _company_dir
    _company_dir = company_dir


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Landing page database not configured.")
    return _db


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "page"


def _escape(text: str) -> str:
    """HTML-escape text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML for body sections (paragraphs, bullets, bold)."""
    lines = text.strip().split("\n")
    html_parts: list[str] = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append("")
            continue

        # Bullet points
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item = stripped[2:]
            # Bold markers
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            html_parts.append(f"<li>{item}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            # Bold markers
            processed = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            html_parts.append(f"<p>{processed}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


_PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0a0a0a; color: #e0e0e0; line-height: 1.6; }}
  .hero {{ text-align: center; padding: 80px 20px 60px;
           background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); }}
  .hero h1 {{ font-size: 2.5rem; font-weight: 700; color: #fff;
              max-width: 700px; margin: 0 auto 16px; }}
  .hero .subtitle {{ font-size: 1.2rem; color: #94a3b8; max-width: 600px;
                     margin: 0 auto 32px; }}
  {price_css}
  .section {{ max-width: 720px; margin: 0 auto; padding: 48px 24px; }}
  .section h2 {{ font-size: 1.5rem; color: #fff; margin-bottom: 20px;
                 border-bottom: 2px solid #1e40af; padding-bottom: 8px; display: inline-block; }}
  .section p {{ margin-bottom: 16px; color: #cbd5e1; }}
  .section ul {{ margin: 16px 0 16px 24px; color: #cbd5e1; }}
  .section li {{ margin-bottom: 8px; }}
  .section strong {{ color: #fff; }}
  .cta-bar {{ text-align: center; padding: 48px 20px;
              background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); }}
  .cta-bar .btn {{ display: inline-block; background: #2563eb; color: #fff;
                   padding: 16px 40px; border-radius: 8px; font-size: 1.1rem;
                   font-weight: 600; text-decoration: none;
                   transition: background 0.2s; }}
  .cta-bar .btn:hover {{ background: #1d4ed8; }}
  .cta-bar .sub {{ color: #64748b; margin-top: 12px; font-size: 0.9rem; }}
  .footer {{ text-align: center; padding: 32px; color: #475569; font-size: 0.8rem; }}
</style>
</head>
<body>
<div class="hero">
  <h1>{headline}</h1>
  <div class="subtitle">{subtitle}</div>
  {price_html}
</div>
{body_html}
<div class="cta-bar">
  <a class="btn" href="#">{cta_text}</a>
  {cta_sub_html}
</div>
<div class="footer">&copy; 2024 {company_name}. All rights reserved.</div>
</body>
</html>
"""

_PRICE_CSS = """\
.price-tag {{ display: inline-block; background: #1e3a5f; color: #38bdf8;
                font-size: 1.8rem; font-weight: 700; padding: 12px 32px;
                border-radius: 12px; margin-top: 8px; }}"""


@tool(
    "create_landing_page",
    (
        "Create a professional landing page from structured content. "
        "Provide headline, subtitle, body sections, and a call-to-action. "
        "The tool generates a polished HTML page automatically."
    ),
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Page title (used in browser tab)",
            },
            "headline": {
                "type": "string",
                "description": "Main hero headline (1 sentence, compelling)",
            },
            "subtitle": {
                "type": "string",
                "description": "Subtitle under the headline (1-2 sentences explaining the value)",
            },
            "body_sections": {
                "type": "string",
                "description": (
                    "Main page content. Use markdown: separate sections with blank lines, "
                    "use '## Section Title' for headings, '- item' for bullet points, "
                    "and '**bold**' for emphasis. Example:\n"
                    "## What You'll Learn\n"
                    "- **AI Strategy**: Build a roadmap\n"
                    "- **Implementation**: Hands-on frameworks\n\n"
                    "## Who Should Attend\n"
                    "C-suite leaders driving digital transformation."
                ),
            },
            "cta_text": {
                "type": "string",
                "description": "Call-to-action button text (e.g. 'Book a Session', 'Get Started')",
            },
            "cta_subtext": {
                "type": "string",
                "description": "Small text under the CTA button (e.g. 'Limited spots available')",
            },
            "price": {
                "type": "string",
                "description": "Price to display prominently (e.g. '$5,000/session'). Omit to hide price.",
            },
            "slug": {
                "type": "string",
                "description": "URL-friendly slug for filename. Auto-generated from title if omitted.",
            },
        },
        "required": ["title", "headline", "body_sections"],
    },
)
async def create_landing_page(
    title: str,
    headline: str,
    body_sections: str,
    subtitle: str = "",
    cta_text: str = "Get Started",
    cta_subtext: str = "",
    price: str = "",
    slug: str = "",
) -> str:
    db = _require_db()

    if not title.strip():
        return "Error: title is required."
    if not headline.strip():
        return "Error: headline is required."

    slug = slug.strip() if slug else _slugify(title)

    # Parse body sections — split on "## " headings
    sections_raw = re.split(r"(?m)^## ", body_sections.strip())
    body_parts: list[str] = []
    for sec in sections_raw:
        sec = sec.strip()
        if not sec:
            continue
        # First line is heading (if split on ##), rest is body
        lines = sec.split("\n", 1)
        if len(lines) == 2 and not sec.startswith("<"):
            heading = lines[0].strip()
            content = _md_to_html(lines[1])
            body_parts.append(
                f'<div class="section"><h2>{_escape(heading)}</h2>\n{content}</div>'
            )
        else:
            # No heading — just content
            content = _md_to_html(sec)
            body_parts.append(f'<div class="section">\n{content}</div>')

    body_html = "\n".join(body_parts)

    # Price display
    price_html = ""
    price_css = ""
    if price.strip():
        price_html = f'<div class="price-tag">{_escape(price)}</div>'
        price_css = _PRICE_CSS

    cta_sub_html = f'<div class="sub">{_escape(cta_subtext)}</div>' if cta_subtext else ""

    # Build from hardcoded company name or fallback
    company_name = "Apex Strategy Group"

    html_content = _PAGE_TEMPLATE.format(
        title=_escape(title),
        headline=_escape(headline),
        subtitle=_escape(subtitle),
        body_html=body_html,
        cta_text=_escape(cta_text),
        cta_sub_html=cta_sub_html,
        price_html=price_html,
        price_css=price_css,
        company_name=_escape(company_name),
    )

    # Determine output path
    if _output_dir:
        out_dir = _output_dir
    elif _company_dir:
        out_dir = _company_dir / "landing_pages"
    else:
        return "Error: landing page output directory not configured."

    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{slug}.html"
    file_path.write_text(html_content, encoding="utf-8")

    # Upsert: update if slug exists, insert otherwise
    existing = await db.fetch_one(
        "SELECT id FROM landing_pages WHERE slug = ?", (slug,)
    )
    if existing:
        await db.execute(
            "UPDATE landing_pages SET title = ?, html_content = ?, file_path = ?, "
            "created_by = ?, updated_at = CURRENT_TIMESTAMP WHERE slug = ?",
            (title, html_content, str(file_path), _current_agent, slug),
        )
        page_id = existing["id"]
        verb = "updated"
    else:
        cursor = await db.execute(
            "INSERT INTO landing_pages (title, slug, html_content, file_path, status, created_by) "
            "VALUES (?, ?, ?, ?, 'active', ?)",
            (title, slug, html_content, str(file_path), _current_agent),
        )
        page_id = cursor.lastrowid
        verb = "created"

    return (
        f"Landing page {verb} (ID: {page_id}).\n"
        f"  Title: {title}\n"
        f"  Slug: {slug}\n"
        f"  File: {file_path}\n"
        f"  HTML size: {len(html_content)} bytes\n"
        f"  Status: active"
    )
