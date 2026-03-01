"""Content generation tool — create blog posts, email sequences, and digital products.

Always available (no external API needed). Converts agent-provided markdown
into styled HTML files. Logs content pieces to the database.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from agent_company_ai.tools.registry import tool

if TYPE_CHECKING:
    from agent_company_ai.storage.database import Database

# Module-level state, set at runtime by Company
_db: Database | None = None
_current_agent: str = "unknown"
_company_dir: Path | None = None
_company_name: str = "My AI Company"


def set_content_db(db: Database) -> None:
    global _db
    _db = db


def set_content_agent(name: str) -> None:
    global _current_agent
    _current_agent = name


def set_content_company_dir(path: Path) -> None:
    global _company_dir
    _company_dir = path


def set_content_company_name(name: str) -> None:
    global _company_name
    _company_name = name


def _require_db() -> Database:
    if _db is None:
        raise RuntimeError("Content database not configured.")
    return _db


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "content"


def _escape(text: str) -> str:
    """HTML-escape text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _md_to_html(text: str) -> str:
    """Minimal markdown-to-HTML (paragraphs, bullets, bold, headings)."""
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

        # Headings
        if stripped.startswith("### "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            heading = stripped[4:]
            heading = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", heading)
            html_parts.append(f"<h3>{heading}</h3>")
            continue
        if stripped.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            heading = stripped[3:]
            heading = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", heading)
            html_parts.append(f"<h2>{heading}</h2>")
            continue

        # Bullet points
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            item = stripped[2:]
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            html_parts.append(f"<li>{item}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            processed = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            html_parts.append(f"<p>{processed}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


_BLOG_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{meta_description}">
<meta name="keywords" content="{keywords}">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0a0a0a; color: #e0e0e0; line-height: 1.8; }}
  .header {{ text-align: center; padding: 60px 20px 40px;
             background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); }}
  .header h1 {{ font-size: 2.2rem; font-weight: 700; color: #fff;
                max-width: 700px; margin: 0 auto 12px; }}
  .header .meta {{ color: #94a3b8; font-size: 0.9rem; }}
  .content {{ max-width: 720px; margin: 0 auto; padding: 48px 24px; }}
  .content h2 {{ font-size: 1.5rem; color: #fff; margin: 32px 0 16px;
                 border-bottom: 2px solid #1e40af; padding-bottom: 8px; display: inline-block; }}
  .content h3 {{ font-size: 1.2rem; color: #e2e8f0; margin: 24px 0 12px; }}
  .content p {{ margin-bottom: 16px; color: #cbd5e1; }}
  .content ul {{ margin: 16px 0 16px 24px; color: #cbd5e1; }}
  .content li {{ margin-bottom: 8px; }}
  .content strong {{ color: #fff; }}
  .footer {{ text-align: center; padding: 32px; color: #475569; font-size: 0.8rem;
             border-top: 1px solid #1e293b; margin-top: 48px; }}
</style>
</head>
<body>
<div class="header">
  <h1>{title}</h1>
  <div class="meta">By {author} | {company_name}</div>
</div>
<div class="content">
{body_html}
</div>
<div class="footer">&copy; {company_name}. All rights reserved.</div>
</body>
</html>
"""


_EBOOK_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: #0a0a0a; color: #e0e0e0; line-height: 1.8; }}
  .cover {{ text-align: center; padding: 80px 20px 60px;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); }}
  .cover h1 {{ font-size: 2.5rem; font-weight: 700; color: #fff;
               max-width: 700px; margin: 0 auto 16px; }}
  .cover .author {{ color: #94a3b8; font-size: 1.1rem; }}
  .cover .price {{ display: inline-block; background: #1e3a5f; color: #38bdf8;
                   font-size: 1.4rem; font-weight: 700; padding: 8px 24px;
                   border-radius: 8px; margin-top: 16px; }}
  .toc {{ max-width: 720px; margin: 0 auto; padding: 48px 24px; }}
  .toc h2 {{ font-size: 1.5rem; color: #fff; margin-bottom: 20px; }}
  .toc ul {{ list-style: none; padding: 0; }}
  .toc li {{ margin-bottom: 8px; }}
  .toc a {{ color: #60a5fa; text-decoration: none; }}
  .toc a:hover {{ text-decoration: underline; }}
  .chapter {{ max-width: 720px; margin: 0 auto; padding: 48px 24px;
              border-top: 1px solid #1e293b; }}
  .chapter h2 {{ font-size: 1.5rem; color: #fff; margin-bottom: 20px;
                 border-bottom: 2px solid #1e40af; padding-bottom: 8px; display: inline-block; }}
  .chapter h3 {{ font-size: 1.2rem; color: #e2e8f0; margin: 24px 0 12px; }}
  .chapter p {{ margin-bottom: 16px; color: #cbd5e1; }}
  .chapter ul {{ margin: 16px 0 16px 24px; color: #cbd5e1; }}
  .chapter li {{ margin-bottom: 8px; }}
  .chapter strong {{ color: #fff; }}
  .footer {{ text-align: center; padding: 32px; color: #475569; font-size: 0.8rem;
             border-top: 1px solid #1e293b; margin-top: 48px; }}
</style>
</head>
<body>
<div class="cover">
  <h1>{title}</h1>
  <div class="author">By {author}</div>
  {price_html}
</div>
<div class="toc">
  <h2>Table of Contents</h2>
  <ul>
{toc_html}
  </ul>
</div>
{chapters_html}
<div class="footer">&copy; {company_name}. All rights reserved.</div>
</body>
</html>
"""


@tool(
    "create_blog_post",
    (
        "Create a styled blog post from markdown content. Generates a polished "
        "HTML page saved to the content/blog/ directory. Perfect for SEO content, "
        "thought leadership, and inbound marketing."
    ),
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Blog post title",
            },
            "body": {
                "type": "string",
                "description": (
                    "Blog post body in markdown. Use '## Heading' for sections, "
                    "'- item' for bullet points, '**bold**' for emphasis."
                ),
            },
            "meta_description": {
                "type": "string",
                "description": "SEO meta description (1-2 sentences, ~160 chars)",
            },
            "keywords": {
                "type": "string",
                "description": "Comma-separated SEO keywords",
            },
            "author": {
                "type": "string",
                "description": "Author name (defaults to agent name)",
            },
            "slug": {
                "type": "string",
                "description": "URL-friendly slug. Auto-generated from title if omitted.",
            },
        },
        "required": ["title", "body"],
    },
)
async def create_blog_post(
    title: str,
    body: str,
    meta_description: str = "",
    keywords: str = "",
    author: str = "",
    slug: str = "",
) -> str:
    db = _require_db()

    if not title.strip():
        return "Error: title is required."
    if not body.strip():
        return "Error: body is required."

    slug = slug.strip() if slug else _slugify(title)
    author = author.strip() if author else _current_agent

    body_html = _md_to_html(body)
    word_count = len(body.split())

    html_content = _BLOG_TEMPLATE.format(
        title=_escape(title),
        meta_description=_escape(meta_description),
        keywords=_escape(keywords),
        author=_escape(author),
        body_html=body_html,
        company_name=_escape(_company_name),
    )

    # Save file
    if not _company_dir:
        return "Error: company directory not configured."

    out_dir = _company_dir / "content" / "blog"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{slug}.html"
    file_path.write_text(html_content, encoding="utf-8")

    # Upsert in DB
    existing = await db.fetch_one(
        "SELECT id FROM content_pieces WHERE slug = ? AND content_type = 'blog_post'", (slug,)
    )
    if existing:
        await db.execute(
            "UPDATE content_pieces SET title = ?, html_content = ?, file_path = ?, "
            "word_count = ?, created_by = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE slug = ? AND content_type = 'blog_post'",
            (title, html_content, str(file_path), word_count, _current_agent, slug),
        )
        piece_id = existing["id"]
        verb = "updated"
    else:
        cursor = await db.execute(
            "INSERT INTO content_pieces (content_type, title, slug, file_path, html_content, status, word_count, created_by) "
            "VALUES ('blog_post', ?, ?, ?, ?, 'published', ?, ?)",
            (title, slug, str(file_path), html_content, word_count, _current_agent),
        )
        piece_id = cursor.lastrowid
        verb = "created"

    return (
        f"Blog post {verb} (ID: {piece_id}).\n"
        f"  Title: {title}\n"
        f"  Slug: {slug}\n"
        f"  File: {file_path}\n"
        f"  Word count: {word_count}\n"
        f"  Author: {author}\n"
        f"  Status: published"
    )


@tool(
    "create_email_sequence",
    (
        "Create an email marketing sequence (drip campaign). Provide a JSON "
        "array of emails with subject and body. Stored in the database for "
        "use with the email sending tool."
    ),
    {
        "type": "object",
        "properties": {
            "purpose": {
                "type": "string",
                "description": "Purpose of the sequence",
                "enum": ["onboarding", "sales", "follow_up", "nurture", "launch"],
            },
            "product_name": {
                "type": "string",
                "description": "Product or service this sequence is for",
            },
            "emails_json": {
                "type": "string",
                "description": (
                    'JSON array of emails: [{"subject": "...", "body": "..."}, ...]. '
                    "Each email should have a subject line and body text."
                ),
            },
            "sequence_name": {
                "type": "string",
                "description": "Name for this sequence (auto-generated if omitted)",
            },
        },
        "required": ["purpose", "product_name", "emails_json"],
    },
)
async def create_email_sequence(
    purpose: str,
    product_name: str,
    emails_json: str,
    sequence_name: str = "",
) -> str:
    db = _require_db()

    if purpose not in ("onboarding", "sales", "follow_up", "nurture", "launch"):
        return "Error: purpose must be one of: onboarding, sales, follow_up, nurture, launch"

    # Parse and validate JSON
    try:
        emails = json.loads(emails_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in emails_json: {e}"

    if not isinstance(emails, list) or not emails:
        return "Error: emails_json must be a non-empty JSON array."

    for i, email in enumerate(emails):
        if not isinstance(email, dict):
            return f"Error: email #{i + 1} must be a JSON object."
        if "subject" not in email or "body" not in email:
            return f"Error: email #{i + 1} must have 'subject' and 'body' fields."

    sequence_name = sequence_name.strip() if sequence_name else f"{purpose}-{_slugify(product_name)}"
    slug = _slugify(sequence_name)
    title = f"{purpose.replace('_', ' ').title()} Sequence: {product_name}"
    word_count = sum(len(e.get("body", "").split()) for e in emails)

    # Upsert
    existing = await db.fetch_one(
        "SELECT id FROM content_pieces WHERE slug = ? AND content_type = 'email_sequence'", (slug,)
    )
    if existing:
        await db.execute(
            "UPDATE content_pieces SET title = ?, json_content = ?, "
            "word_count = ?, created_by = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE slug = ? AND content_type = 'email_sequence'",
            (title, json.dumps(emails), word_count, _current_agent, slug),
        )
        piece_id = existing["id"]
        verb = "updated"
    else:
        cursor = await db.execute(
            "INSERT INTO content_pieces (content_type, title, slug, json_content, status, word_count, created_by) "
            "VALUES ('email_sequence', ?, ?, ?, 'draft', ?, ?)",
            (title, slug, json.dumps(emails), word_count, _current_agent),
        )
        piece_id = cursor.lastrowid
        verb = "created"

    lines = [
        f"Email sequence {verb} (ID: {piece_id}).",
        f"  Name: {sequence_name}",
        f"  Purpose: {purpose}",
        f"  Product: {product_name}",
        f"  Emails: {len(emails)}",
        f"  Total word count: {word_count}",
        "",
        "Sequence outline:",
    ]
    for i, email in enumerate(emails, 1):
        lines.append(f"  {i}. {email['subject']}")

    return "\n".join(lines)


@tool(
    "create_digital_product",
    (
        "Create a digital product (ebook/guide) from structured content. "
        "Provide a JSON array of sections/chapters and the tool builds a "
        "multi-chapter HTML document with a table of contents."
    ),
    {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Product title",
            },
            "sections_json": {
                "type": "string",
                "description": (
                    'JSON array of sections: [{"title": "Chapter Title", "content": "markdown..."}, ...]. '
                    "Each section has a title and markdown content."
                ),
            },
            "author": {
                "type": "string",
                "description": "Author name (defaults to agent name)",
            },
            "price_suggestion": {
                "type": "string",
                "description": "Suggested price (e.g. '$29', '$49.99')",
            },
            "slug": {
                "type": "string",
                "description": "URL-friendly slug. Auto-generated from title if omitted.",
            },
        },
        "required": ["title", "sections_json"],
    },
)
async def create_digital_product(
    title: str,
    sections_json: str,
    author: str = "",
    price_suggestion: str = "",
    slug: str = "",
) -> str:
    db = _require_db()

    if not title.strip():
        return "Error: title is required."

    # Parse and validate JSON
    try:
        sections = json.loads(sections_json)
    except json.JSONDecodeError as e:
        return f"Error: invalid JSON in sections_json: {e}"

    if not isinstance(sections, list) or not sections:
        return "Error: sections_json must be a non-empty JSON array."

    for i, section in enumerate(sections):
        if not isinstance(section, dict):
            return f"Error: section #{i + 1} must be a JSON object."
        if "title" not in section or "content" not in section:
            return f"Error: section #{i + 1} must have 'title' and 'content' fields."

    slug = slug.strip() if slug else _slugify(title)
    author = author.strip() if author else _current_agent

    # Build TOC
    toc_lines = []
    for i, section in enumerate(sections, 1):
        section_id = f"chapter-{i}"
        toc_lines.append(
            f'    <li><a href="#{section_id}">Chapter {i}: {_escape(section["title"])}</a></li>'
        )
    toc_html = "\n".join(toc_lines)

    # Build chapters
    chapter_parts = []
    total_words = 0
    for i, section in enumerate(sections, 1):
        section_id = f"chapter-{i}"
        content_html = _md_to_html(section["content"])
        total_words += len(section["content"].split())
        chapter_parts.append(
            f'<div class="chapter" id="{section_id}">\n'
            f"  <h2>Chapter {i}: {_escape(section['title'])}</h2>\n"
            f"  {content_html}\n"
            f"</div>"
        )
    chapters_html = "\n".join(chapter_parts)

    # Price display
    price_html = ""
    if price_suggestion.strip():
        price_html = f'<div class="price">Suggested Price: {_escape(price_suggestion)}</div>'

    html_content = _EBOOK_TEMPLATE.format(
        title=_escape(title),
        author=_escape(author),
        price_html=price_html,
        toc_html=toc_html,
        chapters_html=chapters_html,
        company_name=_escape(_company_name),
    )

    # Save file
    if not _company_dir:
        return "Error: company directory not configured."

    out_dir = _company_dir / "content" / "products"
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / f"{slug}.html"
    file_path.write_text(html_content, encoding="utf-8")

    # Upsert
    existing = await db.fetch_one(
        "SELECT id FROM content_pieces WHERE slug = ? AND content_type = 'digital_product'", (slug,)
    )
    if existing:
        await db.execute(
            "UPDATE content_pieces SET title = ?, html_content = ?, json_content = ?, "
            "file_path = ?, word_count = ?, created_by = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE slug = ? AND content_type = 'digital_product'",
            (title, html_content, sections_json, str(file_path), total_words, _current_agent, slug),
        )
        piece_id = existing["id"]
        verb = "updated"
    else:
        cursor = await db.execute(
            "INSERT INTO content_pieces (content_type, title, slug, file_path, html_content, json_content, status, word_count, created_by) "
            "VALUES ('digital_product', ?, ?, ?, ?, ?, 'draft', ?, ?)",
            (title, slug, str(file_path), html_content, sections_json, total_words, _current_agent),
        )
        piece_id = cursor.lastrowid
        verb = "created"

    return (
        f"Digital product {verb} (ID: {piece_id}).\n"
        f"  Title: {title}\n"
        f"  Slug: {slug}\n"
        f"  File: {file_path}\n"
        f"  Chapters: {len(sections)}\n"
        f"  Total word count: {total_words}\n"
        f"  Author: {author}\n"
        f"  Price suggestion: {price_suggestion or 'not set'}\n"
        f"  Status: draft"
    )
