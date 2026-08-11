"""IBM Documentation HTTP client."""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from ibmi_docs_mcp.models import SearchHit, SearchResult

logger = logging.getLogger("ibmi_docs_mcp.client")

_HREF_RE = re.compile(r"^ssw_ibm_i_\d+/[A-Za-z0-9._/-]+\.htm$")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ALLOWED_HOSTS = frozenset({"www.ibm.com", "ibm.com"})
_MAX_REDIRECTS = 5
# Cap HTML before BeautifulSoup to bound memory/CPU on oversized responses.
MAX_HTML_BYTES = 2_000_000


class DocsClientError(Exception):
    """Base client error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class NotFoundError(DocsClientError):
    def __init__(self, message: str) -> None:
        super().__init__("not_found", message)


class InvalidHrefError(DocsClientError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_href", message)


class UpstreamError(DocsClientError):
    def __init__(self, message: str) -> None:
        super().__init__("upstream_unavailable", message)


def normalize_query(query: str) -> str:
    """Strip and collapse whitespace; do not case-fold."""
    return _WS_RE.sub(" ", query.strip())


def strip_html_tags(value: str) -> str:
    return _TAG_RE.sub("", value).strip()


def _hostname_allowed(host: str | None) -> bool:
    if not host:
        return False
    return host.lower().rstrip(".") in _ALLOWED_HOSTS


def resolve_href(url_or_href: str) -> str:
    """Resolve agent input to a content API href. Fail closed."""
    raw = url_or_href.strip()
    if not raw:
        raise InvalidHrefError("href can not be empty")

    parsed = urlparse(raw)
    marker = "/docs/api/v1/content/"

    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in {"http", "https"}:
            raise InvalidHrefError(f"Unsupported URL scheme: {parsed.scheme}")
        if not _hostname_allowed(parsed.hostname):
            raise InvalidHrefError(f"Host not allowed: {parsed.netloc}")
        if marker in parsed.path:
            href = parsed.path.split(marker, 1)[1]
            return _validate_href(href)
        # Human docs URLs (?topic=...) are ambiguous — reject in v1.
        raise InvalidHrefError(
            "Pass href from search_ibm_docs (e.g. ssw_ibm_i_75/db2/....htm)"
        )

    if marker in raw:
        href = raw.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0]
        return _validate_href(href)

    return _validate_href(raw.lstrip("/"))


def _validate_href(href: str) -> str:
    href = href.strip().lstrip("/")
    if ".." in href.split("/"):
        raise InvalidHrefError("Path traversal is not allowed in href")
    if not _HREF_RE.match(href):
        raise InvalidHrefError(
            "Pass href from search_ibm_docs (e.g. ssw_ibm_i_75/db2/....htm)"
        )
    return href


def _decode_html_body(response: httpx.Response) -> str:
    raw = response.content
    if len(raw) > MAX_HTML_BYTES:
        raise UpstreamError(
            f"Content too large ({len(raw)} bytes; max {MAX_HTML_BYTES})"
        )
    encoding = response.charset_encoding or "utf-8"
    return raw.decode(encoding, errors="replace")


class IBMDocsClient:
    def __init__(
        self,
        *,
        base_url: str = "https://www.ibm.com",
        user_agent: str = "ibmi-docs-mcp/0.1 (+local-agent)",
        timeout: float = 20.0,
        max_retries: int = 3,
        max_concurrency: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_retries = max_retries
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = client
        self._owns_client = client is None

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
            # Manual redirect handling enforces the IBM host allowlist.
            follow_redirects=False,
        )

    async def __aenter__(self) -> IBMDocsClient:
        if self._client is None:
            self._client = self._build_client()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._build_client()
            self._owns_client = True
        return self._client

    async def search(self, query: str, product_key: str, limit: int = 5) -> SearchResult:
        params = {
            "query": query,
            "products": product_key,
            "limit": str(limit),
        }
        data = await self._request_json("GET", "/docs/api/v1/search", params=params)
        topics = data.get("topics") or []
        hits: list[SearchHit] = []
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            product = topic.get("product") or {}
            hits.append(
                SearchHit(
                    title=strip_html_tags(str(topic.get("title") or "")),
                    snippet=strip_html_tags(str(topic.get("snippet") or "")),
                    href=str(topic.get("href") or ""),
                    url=str(topic.get("fullurl") or ""),
                    product_key=str(product.get("key") or product_key),
                )
            )
        logger.debug(
            "IBM search HTTP ok query=%r products=%s topics=%s hits=%s",
            query,
            product_key,
            len(hits),
            data.get("hits"),
        )
        return SearchResult(
            total_hits=int(data.get("hits") or 0),
            hits=hits,
        )

    async def fetch_content(self, href: str) -> str:
        safe_href = resolve_href(href)
        response = await self._request(
            "GET",
            f"/docs/api/v1/content/{safe_href}",
            headers={"Accept": "text/html,*/*"},
        )
        if response.status_code == 404:
            raise NotFoundError(f"IBM docs returned 404 for href {safe_href}")
        if response.status_code >= 400:
            raise UpstreamError(
                f"IBM docs content error HTTP {response.status_code} for {safe_href}"
            )
        return _decode_html_body(response)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            method,
            path,
            params=params,
            headers={"Accept": "application/json"},
        )
        if response.status_code >= 400:
            raise UpstreamError(
                f"IBM docs search error HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise UpstreamError(
                f"IBM docs search returned invalid JSON: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise UpstreamError("IBM docs search returned non-object JSON")
        return data

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        client = self._require_client()
        last_error: Exception | None = None
        attempts = max(1, self.max_retries)

        for attempt in range(attempts):
            try:
                async with self._semaphore:
                    response = await self._request_with_redirects(
                        client,
                        method,
                        path,
                        params=params,
                        headers=headers,
                    )
                # Retry transient upstream failures only.
                if response.status_code in {429, 500, 502, 503, 504}:
                    last_error = UpstreamError(
                        f"Transient HTTP {response.status_code} for {path}"
                    )
                    if attempt + 1 < attempts:
                        await self._backoff(attempt)
                        continue
                return response
            except UpstreamError:
                raise
            except httpx.HTTPError as exc:
                last_error = UpstreamError(f"Network error talking to IBM docs: {exc}")
                logger.warning("IBM docs request failed (%s): %s", path, exc)
                if attempt + 1 < attempts:
                    await self._backoff(attempt)
                    continue
                raise last_error from exc

        assert last_error is not None
        raise last_error

    async def _request_with_redirects(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Follow redirects only while the next hop stays on allowed IBM hosts."""
        current_url = url
        current_params = params
        for _ in range(_MAX_REDIRECTS + 1):
            response = await client.request(
                method, current_url, params=current_params, headers=headers
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                return response

            location = response.headers.get("location")
            if not location:
                raise UpstreamError(
                    f"Redirect {response.status_code} missing Location for {current_url}"
                )

            next_url = urljoin(str(response.url), location)
            parsed = urlparse(next_url)
            if parsed.scheme not in {"http", "https"} or not _hostname_allowed(
                parsed.hostname
            ):
                raise UpstreamError(
                    f"Refusing redirect off allowed IBM hosts: {next_url}"
                )

            # Absolute URL for subsequent hops (may leave base_url path context).
            current_url = next_url
            current_params = None
            if response.status_code == 303:
                method = "GET"

        raise UpstreamError(f"Too many redirects for {url}")

    async def _backoff(self, attempt: int) -> None:
        delay = (0.5 * (2**attempt)) + random.uniform(0, 0.25)
        await asyncio.sleep(delay)
