"""Tests for SQLite cache."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from ibmi_docs_mcp.cache import DocsCache


def test_search_and_page_cache_roundtrip(tmp_path: Path) -> None:
    clock = {"t": 1_000.0}

    def now() -> float:
        return clock["t"]

    cache = DocsCache(tmp_path / "cache.db", ttl_days=1, now=now)
    payload = {"total_hits": 1, "hits": [{"title": "T", "href": "ssw_ibm_i_75/x.htm"}]}
    cache.put_search("ssw_ibm_i_75", "HTTP_GET", 5, payload)

    fresh = cache.get_search("ssw_ibm_i_75", "HTTP_GET", 5)
    assert fresh is not None
    assert fresh.fresh is True
    assert fresh.payload["total_hits"] == 1

    clock["t"] += 2 * 24 * 60 * 60
    stale = cache.get_search("ssw_ibm_i_75", "HTTP_GET", 5)
    assert stale is not None
    assert stale.stale is True

    cache.put_page(
        "ssw_ibm_i_75/x.htm",
        "https://www.ibm.com/docs/en/i/7.5.0?topic=x",
        "Title",
        "Body text",
    )
    page = cache.get_page("ssw_ibm_i_75/x.htm")
    assert page is not None
    assert page.payload["text"] == "Body text"
    cache.close()


def test_corrupt_search_json_treated_as_miss(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    cache = DocsCache(db, ttl_days=1)
    cache.close()

    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO search_cache (product_key, query_norm, limit_n, payload_json, fetched_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("ssw_ibm_i_75", "HTTP_GET", 5, "{not-json", 1_000.0),
    )
    conn.commit()
    conn.close()

    cache = DocsCache(db, ttl_days=1)
    assert cache.get_search("ssw_ibm_i_75", "HTTP_GET", 5) is None
    cache.close()


def test_concurrent_puts_do_not_raise(tmp_path: Path) -> None:
    cache = DocsCache(tmp_path / "cache.db", ttl_days=1)

    def writer(i: int) -> None:
        cache.put_search(
            "ssw_ibm_i_75",
            f"Q{i}",
            5,
            {"total_hits": i, "hits": []},
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(writer, range(40)))

    assert cache.get_search("ssw_ibm_i_75", "Q0", 5) is not None
    assert cache.get_search("ssw_ibm_i_75", "Q39", 5) is not None
    cache.close()


@pytest.mark.asyncio
async def test_async_facade_roundtrip(tmp_path: Path) -> None:
    cache = DocsCache(tmp_path / "cache.db", ttl_days=1)
    await cache.aput_search(
        "ssw_ibm_i_75",
        "HTTP_GET",
        5,
        {"total_hits": 1, "hits": []},
    )
    entry = await cache.aget_search("ssw_ibm_i_75", "HTTP_GET", 5)
    assert entry is not None
    assert entry.payload["total_hits"] == 1

    await cache.aput_page(
        "ssw_ibm_i_75/x.htm",
        "https://www.ibm.com/docs/en/i/7.5.0?topic=x",
        "Title",
        "Body",
    )
    page = await cache.aget_page("ssw_ibm_i_75/x.htm")
    assert page is not None
    assert page.payload["text"] == "Body"
    cache.close()
