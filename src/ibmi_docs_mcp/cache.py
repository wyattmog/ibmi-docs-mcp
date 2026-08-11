"""SQLite search/page cache."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("ibmi_docs_mcp.cache")


@dataclass
class CacheEntry:
    payload: Any
    fetched_at: float
    fresh: bool
    stale: bool


class DocsCache:
    def __init__(
        self,
        path: Path,
        *,
        ttl_days: int = 30,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.path = Path(path)
        self.ttl_seconds = ttl_days * 24 * 60 * 60
        self._now = now or time.time
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS search_cache (
              product_key  TEXT NOT NULL,
              query_norm   TEXT NOT NULL,
              limit_n      INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              fetched_at   REAL NOT NULL,
              PRIMARY KEY (product_key, query_norm, limit_n)
            );

            CREATE TABLE IF NOT EXISTS page_cache (
              href         TEXT PRIMARY KEY,
              url          TEXT,
              title        TEXT,
              text         TEXT NOT NULL,
              fetched_at   REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_search_fetched ON search_cache(fetched_at);
            CREATE INDEX IF NOT EXISTS idx_page_fetched ON page_cache(fetched_at);
            """
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _age_flags(self, fetched_at: float) -> tuple[bool, bool]:
        age = self._now() - fetched_at
        fresh = age < self.ttl_seconds
        return fresh, not fresh

    def get_search(
        self, product_key: str, query_norm: str, limit: int
    ) -> CacheEntry | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json, fetched_at
                FROM search_cache
                WHERE product_key = ? AND query_norm = ? AND limit_n = ?
                """,
                (product_key, query_norm, limit),
            ).fetchone()
            if row is None:
                return None
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                logger.warning(
                    "Corrupt search cache row product=%s query=%r; treating as miss",
                    product_key,
                    query_norm,
                )
                return None
            fresh, stale = self._age_flags(row["fetched_at"])
            return CacheEntry(
                payload=payload,
                fetched_at=row["fetched_at"],
                fresh=fresh,
                stale=stale,
            )

    def put_search(
        self,
        product_key: str,
        query_norm: str,
        limit: int,
        payload: object,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO search_cache (product_key, query_norm, limit_n, payload_json, fetched_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(product_key, query_norm, limit_n) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  fetched_at = excluded.fetched_at
                """,
                (product_key, query_norm, limit, json.dumps(payload), self._now()),
            )
            self._conn.commit()

    def get_page(self, href: str) -> CacheEntry | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT href, url, title, text, fetched_at
                FROM page_cache
                WHERE href = ?
                """,
                (href,),
            ).fetchone()
            if row is None:
                return None
            fresh, stale = self._age_flags(row["fetched_at"])
            return CacheEntry(
                payload={
                    "href": row["href"],
                    "url": row["url"],
                    "title": row["title"],
                    "text": row["text"],
                },
                fetched_at=row["fetched_at"],
                fresh=fresh,
                stale=stale,
            )

    def put_page(self, href: str, url: str, title: str, text: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO page_cache (href, url, title, text, fetched_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(href) DO UPDATE SET
                  url = excluded.url,
                  title = excluded.title,
                  text = excluded.text,
                  fetched_at = excluded.fetched_at
                """,
                (href, url, title, text, self._now()),
            )
            self._conn.commit()

    # Async facades: run sync SQLite off the event loop (tools should await these).

    async def aget_search(
        self, product_key: str, query_norm: str, limit: int
    ) -> CacheEntry | None:
        return await asyncio.to_thread(self.get_search, product_key, query_norm, limit)

    async def aput_search(
        self,
        product_key: str,
        query_norm: str,
        limit: int,
        payload: object,
    ) -> None:
        await asyncio.to_thread(self.put_search, product_key, query_norm, limit, payload)

    async def aget_page(self, href: str) -> CacheEntry | None:
        return await asyncio.to_thread(self.get_page, href)

    async def aput_page(self, href: str, url: str, title: str, text: str) -> None:
        await asyncio.to_thread(self.put_page, href, url, title, text)
