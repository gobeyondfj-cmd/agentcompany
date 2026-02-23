"""Async SQLite database layer for Agent Company AI.

Uses ``aiosqlite`` for non-blocking database access with WAL mode and
dictionary-style row results.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import aiosqlite


class Database:
    """Thin async wrapper around an SQLite database.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file.  The file (and any
        intermediate directories) will be created automatically on
        :meth:`connect` if they do not already exist.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the database connection, enable WAL mode, and run migrations."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.db_path))

        # Enable WAL mode for better concurrent read performance.
        await self._conn.execute("PRAGMA journal_mode=WAL;")

        # Return rows as ``sqlite3.Row`` so we can convert to dicts easily.
        self._conn.row_factory = sqlite3.Row

        # Enable foreign key enforcement.
        await self._conn.execute("PRAGMA foreign_keys=ON;")

        await self._migrate()

    async def close(self) -> None:
        """Close the database connection gracefully."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    async def execute(self, sql: str, params: tuple = ()) -> aiosqlite.Cursor:
        """Execute a SQL statement and commit.

        Returns the raw ``aiosqlite.Cursor`` so callers can inspect
        ``lastrowid``, ``rowcount``, etc.
        """
        assert self._conn is not None, "Database not connected. Call connect() first."
        cursor = await self._conn.execute(sql, params)
        await self._conn.commit()
        return cursor

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Execute a query and return the first row as a dict, or ``None``."""
        assert self._conn is not None, "Database not connected. Call connect() first."
        cursor = await self._conn.execute(sql, params)
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a query and return all rows as a list of dicts."""
        assert self._conn is not None, "Database not connected. Call connect() first."
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Migrations
    # ------------------------------------------------------------------

    async def _migrate(self) -> None:
        """Create all required tables if they do not already exist."""
        assert self._conn is not None

        await self._conn.executescript(
            """\
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL,
                provider TEXT,
                model TEXT,
                config_json TEXT DEFAULT '{}',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                assignee_id TEXT,
                status TEXT DEFAULT 'pending',
                priority INTEGER DEFAULT 0,
                parent_id TEXT,
                result TEXT,
                artifacts_json TEXT DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (assignee_id) REFERENCES agents(id),
                FOREIGN KEY (parent_id) REFERENCES tasks(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                from_agent TEXT,
                to_agent TEXT,
                content TEXT NOT NULL,
                topic TEXT,
                metadata_json TEXT DEFAULT '{}',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                agent_id TEXT,
                name TEXT NOT NULL,
                content TEXT,
                artifact_type TEXT DEFAULT 'text',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id),
                FOREIGN KEY (agent_id) REFERENCES agents(id)
            );

            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS wallets (
                id TEXT PRIMARY KEY,
                address TEXT NOT NULL,
                keystore_path TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS payment_queue (
                id TEXT PRIMARY KEY,
                to_address TEXT NOT NULL,
                amount TEXT NOT NULL,
                token TEXT DEFAULT 'ETH',
                chain TEXT DEFAULT 'ethereum',
                reason TEXT DEFAULT '',
                requested_by TEXT,
                status TEXT DEFAULT 'pending',
                tx_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                executed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT DEFAULT '',
                company TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                status TEXT DEFAULT 'lead',
                source TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                custom_fields TEXT DEFAULT '{}',
                created_by TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS email_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                to_address TEXT NOT NULL,
                from_address TEXT DEFAULT '',
                subject TEXT DEFAULT '',
                body_text TEXT DEFAULT '',
                body_html TEXT DEFAULT '',
                status TEXT DEFAULT 'sent',
                provider_message_id TEXT DEFAULT '',
                contact_id INTEGER,
                sent_by TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            );

            CREATE TABLE IF NOT EXISTS payment_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stripe_url TEXT DEFAULT '',
                stripe_price_id TEXT DEFAULT '',
                stripe_payment_link_id TEXT DEFAULT '',
                product_name TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT DEFAULT 'usd',
                status TEXT DEFAULT 'active',
                contact_id INTEGER,
                created_by TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contact_id) REFERENCES contacts(id)
            );

            CREATE TABLE IF NOT EXISTS landing_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                html_content TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                created_by TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS social_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                content TEXT NOT NULL,
                media_urls TEXT DEFAULT '',
                hashtags TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                scheduled_for TIMESTAMP,
                created_by TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await self._conn.commit()


# ------------------------------------------------------------------
# Convenience factory
# ------------------------------------------------------------------

def get_database(company_dir: Path) -> Database:
    """Return a :class:`Database` instance pointing at ``company_dir/company.db``.

    The caller is responsible for calling :meth:`Database.connect` before
    using the returned instance.
    """
    return Database(Path(company_dir) / "company.db")
