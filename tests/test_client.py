"""Tests for IBM docs HTTP client."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from ibmi_docs_mcp.client import (
    MAX_HTML_BYTES,
    IBMDocsClient,
    InvalidHrefError,
    NotFoundError,
    UpstreamError,
    normalize_query,
    resolve_href,
)

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://www.ibm.com"


def test_normalize_query() -> None:
    assert normalize_query("  HTTP_GET   extras  ") == "HTTP_GET extras"


def test_resolve_href_good() -> None:
    assert (
        resolve_href("ssw_ibm_i_75/db2/rbafzscahttpget.htm")
        == "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    )
    assert (
        resolve_href(
            "https://www.ibm.com/docs/api/v1/content/ssw_ibm_i_75/db2/rbafzscahttpget.htm"
        )
        == "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    )
    assert (
        resolve_href(
            "https://www.ibm.com:443/docs/api/v1/content/ssw_ibm_i_75/db2/rbafzscahttpget.htm"
        )
        == "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "https://www.ibm.com/docs/en/i/7.5.0?topic=functions-http-get-http-get-blob",
        "https://evil.example/docs/api/v1/content/ssw_ibm_i_75/db2/x.htm",
        "ssw_ibm_i_75/../secret.htm",
        "javascript:alert(1)",
    ],
)
def test_resolve_href_rejects(bad: str) -> None:
    with pytest.raises(InvalidHrefError):
        resolve_href(bad)


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_fixture_fields() -> None:
    payload = json.loads((FIXTURES / "search_http_get.json").read_text(encoding="utf-8"))
    route = respx.get(f"{BASE}/docs/api/v1/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        result = await client.search("HTTP_GET", "ssw_ibm_i_75", limit=5)

    assert route.called
    assert "products" in route.calls.last.request.url.params
    assert "product" not in route.calls.last.request.url.params
    assert route.calls.last.request.url.params["products"] == "ssw_ibm_i_75"
    assert route.calls.last.request.url.params["limit"] == "5"
    assert result["total_hits"] == 7
    assert result["hits"][0]["title"] == "HTTP_GET and HTTP_GET_BLOB"
    assert "<b>" not in result["hits"][0]["title"]
    assert result["hits"][0]["href"] == "ssw_ibm_i_75/db2/rbafzscahttpget.htm"


@pytest.mark.asyncio
@respx.mock
async def test_search_empty_fixture() -> None:
    payload = json.loads((FIXTURES / "search_empty.json").read_text(encoding="utf-8"))
    respx.get(f"{BASE}/docs/api/v1/search").mock(return_value=httpx.Response(200, json=payload))
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        result = await client.search("zzzznotatopic999", "ssw_ibm_i_75", limit=5)
    assert result["total_hits"] == 0
    assert result["hits"] == []


@pytest.mark.asyncio
@respx.mock
async def test_fetch_content_404() -> None:
    href = "ssw_ibm_i_75/db2/does-not-exist.htm"
    respx.get(f"{BASE}/docs/api/v1/content/{href}").mock(
        return_value=httpx.Response(404, text="<html><h1>missing</h1></html>")
    )
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        with pytest.raises(NotFoundError):
            await client.fetch_content(href)


@pytest.mark.asyncio
@respx.mock
async def test_search_invalid_json_raises_upstream() -> None:
    respx.get(f"{BASE}/docs/api/v1/search").mock(
        return_value=httpx.Response(200, text="not-json", headers={"content-type": "application/json"})
    )
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        with pytest.raises(UpstreamError, match="invalid JSON"):
            await client.search("HTTP_GET", "ssw_ibm_i_75", limit=5)


@pytest.mark.asyncio
@respx.mock
async def test_redirect_stays_on_ibm_host() -> None:
    href = "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    final = f"{BASE}/docs/api/v1/content/{href}"
    respx.get(f"{BASE}/docs/api/v1/content/{href}").mock(
        side_effect=[
            httpx.Response(302, headers={"Location": final}),
            httpx.Response(200, text="<html><article><h1>OK</h1></article></html>"),
        ]
    )
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        text = await client.fetch_content(href)
    assert "OK" in text


@pytest.mark.asyncio
@respx.mock
async def test_redirect_off_ibm_host_refused() -> None:
    href = "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    respx.get(f"{BASE}/docs/api/v1/content/{href}").mock(
        return_value=httpx.Response(
            302, headers={"Location": "https://evil.example/steal"}
        )
    )
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        with pytest.raises(UpstreamError, match="Refusing redirect"):
            await client.fetch_content(href)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_content_rejects_oversized_body() -> None:
    href = "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
    huge = b"x" * (MAX_HTML_BYTES + 1)
    respx.get(f"{BASE}/docs/api/v1/content/{href}").mock(
        return_value=httpx.Response(200, content=huge, headers={"content-type": "text/html"})
    )
    async with IBMDocsClient(base_url=BASE, max_retries=1) as client:
        with pytest.raises(UpstreamError, match="Content too large"):
            await client.fetch_content(href)
