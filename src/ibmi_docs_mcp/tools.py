"""FastMCP tool registration."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

from ibmi_docs_mcp.cache import DocsCache
from ibmi_docs_mcp.client import (
    DocsClientError,
    IBMDocsClient,
    InvalidHrefError,
    NotFoundError,
    UpstreamError,
    normalize_query,
    resolve_href,
)
from ibmi_docs_mcp.config import Settings
from ibmi_docs_mcp.models import tool_error
from ibmi_docs_mcp.parse import html_to_text, text_is_truncated
from ibmi_docs_mcp.versioning import UnknownVersionError, version_to_product_key

logger = logging.getLogger("ibmi_docs_mcp.tools")


def register_tools(
    mcp: FastMCP,
    settings: Settings,
    *,
    client: IBMDocsClient | None = None,
    cache: DocsCache | None = None,
) -> None:
    docs_client = client or IBMDocsClient(
        base_url=settings.base_url,
        user_agent=settings.user_agent,
        timeout=settings.http_timeout,
        max_retries=settings.max_retries,
        max_concurrency=settings.max_concurrency,
    )
    docs_cache = cache or DocsCache(settings.cache_path, ttl_days=settings.ttl_days)

    @mcp.tool
    async def search_ibm_docs(
        query: str,
        version: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Search IBM i documentation (IBM's own docs search index).

        Prefer short object/command names (e.g. HTTP_GET, WRKACTJOB, CHGJRN) over long
        prose. Results are ranked by IBM relevance — read titles/snippets and pick the
        best match; do not assume hit #1 is always right. Next step: call fetch_ibm_doc
        with the chosen result's href.
        """
        query_norm = normalize_query(query)
        if not query_norm:
            return tool_error("empty_query", "Query string can not be empty")

        limit_n = max(1, min(int(limit), 20))
        version_str = version or settings.version
        try:
            product_key = version_to_product_key(version_str)
        except UnknownVersionError as exc:
            return tool_error("version_unknown", str(exc))

        cached = False
        stale = False
        warning: str | None = None
        entry = await docs_cache.aget_search(product_key, query_norm, limit_n)

        if entry is not None and entry.fresh:
            payload = entry.payload
            cached = True
            logger.info(
                "search cache hit query=%r product=%s limit=%s hits=%s",
                query_norm,
                product_key,
                limit_n,
                payload.get("total_hits"),
            )
        else:
            try:
                logger.info(
                    "search miss → IBM query=%r product=%s limit=%s",
                    query_norm,
                    product_key,
                    limit_n,
                )
                result = await docs_client.search(query_norm, product_key, limit_n)
                payload = {
                    "total_hits": result["total_hits"],
                    "hits": result["hits"],
                }
                await docs_cache.aput_search(product_key, query_norm, limit_n, payload)
                logger.info(
                    "search ok query=%r returned=%s total_hits=%s",
                    query_norm,
                    len(result["hits"]),
                    result["total_hits"],
                )
            except UpstreamError as exc:
                if entry is not None:
                    payload = entry.payload
                    cached = True
                    stale = True
                    warning = f"Serving stale search cache: {exc.message}"
                    logger.warning(warning)
                else:
                    logger.exception("search_ibm_docs upstream failure")
                    return tool_error("upstream_unavailable", exc.message, stale=False)
            except DocsClientError as exc:
                logger.exception("search_ibm_docs client error")
                return tool_error(exc.code, exc.message)  # type: ignore[arg-type]

        results = []
        for idx, hit in enumerate(payload.get("hits") or [], start=1):
            results.append(
                {
                    "rank": idx,
                    "title": hit.get("title", ""),
                    "snippet": hit.get("snippet", ""),
                    "href": hit.get("href", ""),
                    "url": hit.get("url", ""),
                }
            )

        out: dict[str, Any] = {
            "version": version_str,
            "product_key": product_key,
            "query": query_norm,
            "total_hits": payload.get("total_hits", len(results)),
            "cached": cached,
            "stale": stale,
            "results": results,
        }
        if warning:
            out["warning"] = warning
        return out

    @mcp.tool
    async def fetch_ibm_doc(
        url_or_href: str,
        version: str | None = None,  # noqa: ARG001 — reserved for future allowlist/context
    ) -> dict[str, Any]:
        """Fetch one IBM i documentation topic as plain text.

        Pass the href (or content API URL) from search_ibm_docs. Returns title, url,
        text, and truncated/stale flags. Prefer search first so you pick the right page.
        """
        try:
            href = resolve_href(url_or_href)
        except InvalidHrefError as exc:
            return tool_error("invalid_href", exc.message)

        entry = await docs_cache.aget_page(href)
        if entry is not None and entry.fresh:
            page = entry.payload
            text = page["text"]
            logger.info(
                "fetch cache hit href=%s chars=%s",
                href,
                len(text),
            )
            return {
                "title": page["title"],
                "url": page["url"],
                "href": page["href"],
                "text": text,
                "truncated": text_is_truncated(text),
                "char_count": len(text),
                "stale": False,
                "warning": None,
                "cached": True,
            }

        try:
            logger.info("fetch miss → IBM href=%s", href)
            html = await docs_client.fetch_content(href)
            # Prefer cached human URL if we somehow only have href.
            known_url = entry.payload["url"] if entry is not None else None
            parsed = html_to_text(
                html,
                max_chars=settings.max_chars,
                href=href,
                url=known_url or None,
            )
            await docs_cache.aput_page(
                href=parsed["href"],
                url=parsed["url"],
                title=parsed["title"],
                text=parsed["text"],
            )
            logger.info(
                "fetch ok href=%s title=%r chars=%s truncated=%s",
                href,
                parsed["title"],
                parsed["char_count"],
                parsed["truncated"],
            )
            return {
                **parsed,
                "cached": False,
            }
        except NotFoundError as exc:
            return tool_error("not_found", exc.message)
        except UpstreamError as exc:
            if entry is not None:
                page = entry.payload
                text = page["text"]
                return {
                    "title": page["title"],
                    "url": page["url"],
                    "href": page["href"],
                    "text": text,
                    "truncated": text_is_truncated(text),
                    "char_count": len(text),
                    "stale": True,
                    "warning": f"Serving stale page cache: {exc.message}",
                    "cached": True,
                }
            logger.exception("fetch_ibm_doc upstream failure")
            return tool_error("upstream_unavailable", exc.message, stale=False)
        except DocsClientError as exc:
            logger.exception("fetch_ibm_doc client error")
            return tool_error(exc.code, exc.message)  # type: ignore[arg-type]
