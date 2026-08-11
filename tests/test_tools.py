"""Tests for MCP tools."""

from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import FastMCP

from ibmi_docs_mcp.cache import DocsCache
from ibmi_docs_mcp.client import IBMDocsClient
from ibmi_docs_mcp.config import Settings
from ibmi_docs_mcp.tools import register_tools

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://www.ibm.com"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        version="7.5.0",
        cache_path=tmp_path / "cache.db",
        ttl_days=30,
        max_chars=12000,
        base_url=BASE,
        max_retries=1,
    )


async def _call_tool(mcp: FastMCP, name: str, arguments: dict):
    tools = await mcp.list_tools()
    assert any(t.name == name for t in tools)
    # FastMCP call API varies; use tool functions via _tool_manager when needed.
    tool = await mcp.get_tool(name)
    return await tool.run(arguments)


@pytest.mark.asyncio
@respx.mock
async def test_search_then_fetch(settings: Settings, tmp_path: Path) -> None:
    search_payload = (FIXTURES / "search_http_get.json").read_text(encoding="utf-8")
    html = (FIXTURES / "content_http_get.html").read_text(encoding="utf-8")
    respx.get(f"{BASE}/docs/api/v1/search").mock(
        return_value=httpx.Response(200, text=search_payload, headers={"content-type": "application/json"})
    )
    href = "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    content_route = respx.get(f"{BASE}/docs/api/v1/content/{href}").mock(
        return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )

    mcp = FastMCP("test")
    client = IBMDocsClient(base_url=BASE, max_retries=1)
    cache = DocsCache(tmp_path / "cache.db", ttl_days=30)
    register_tools(mcp, settings, client=client, cache=cache)

    search = await _call_tool(mcp, "search_ibm_docs", {"query": "HTTP_GET", "limit": 5})
    data = search.data if hasattr(search, "data") else search
    if hasattr(data, "model_dump"):
        data = data.model_dump()
    # ToolResult may wrap structured content
    if isinstance(data, dict) and "result" in data and "error" not in data:
        # unwrap unlikely
        pass
    # FastMCP 3 ToolResult: .structured_content or .content
    payload = getattr(search, "structured_content", None) or getattr(search, "data", None) or search
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    assert isinstance(payload, dict)
    assert payload["product_key"] == "ssw_ibm_i_75"
    assert payload["results"][0]["href"] == href

    fetched = await _call_tool(mcp, "fetch_ibm_doc", {"url_or_href": href})
    page = getattr(fetched, "structured_content", None) or getattr(fetched, "data", None) or fetched
    if hasattr(page, "model_dump"):
        page = page.model_dump()
    assert "HTTP_GET" in page["title"]
    assert "scalar function" in page["text"]
    assert content_route.call_count == 1

    # Second fetch should hit cache (no extra HTTP).
    fetched2 = await _call_tool(mcp, "fetch_ibm_doc", {"url_or_href": href})
    page2 = getattr(fetched2, "structured_content", None) or getattr(fetched2, "data", None) or fetched2
    if hasattr(page2, "model_dump"):
        page2 = page2.model_dump()
    assert page2.get("cached") is True
    assert content_route.call_count == 1

    await client.aclose()
    cache.close()


@pytest.mark.asyncio
async def test_empty_query(settings: Settings, tmp_path: Path) -> None:
    mcp = FastMCP("test")
    register_tools(
        mcp,
        settings,
        client=IBMDocsClient(base_url=BASE, max_retries=1),
        cache=DocsCache(tmp_path / "cache.db"),
    )
    result = await _call_tool(mcp, "search_ibm_docs", {"query": "   "})
    payload = getattr(result, "structured_content", None) or getattr(result, "data", None) or result
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    assert payload["error"] == "empty_query"


def _unwrap(result):
    payload = getattr(result, "structured_content", None) or getattr(result, "data", None) or result
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    return payload


@pytest.mark.asyncio
@respx.mock
async def test_stale_fetch_preserves_truncated_flag(
    settings: Settings, tmp_path: Path
) -> None:
    href = "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    truncated_text = (
        "body\n\n[truncated at 12 chars; refine search or fetch a more specific topic]"
    )
    cache = DocsCache(tmp_path / "cache.db", ttl_days=0)
    cache.put_page(
        href,
        f"{BASE}/docs/en/i/7.5.0?topic=x",
        "HTTP_GET",
        truncated_text,
    )

    respx.get(f"{BASE}/docs/api/v1/content/{href}").mock(
        return_value=httpx.Response(503, text="unavailable")
    )

    mcp = FastMCP("test")
    client = IBMDocsClient(base_url=BASE, max_retries=1)
    register_tools(mcp, settings, client=client, cache=cache)

    fetched = await _call_tool(mcp, "fetch_ibm_doc", {"url_or_href": href})
    page = _unwrap(fetched)
    assert page["stale"] is True
    assert page["truncated"] is True
    assert page["cached"] is True

    await client.aclose()
    cache.close()
