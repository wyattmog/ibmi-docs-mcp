"""Shared DTOs / models."""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class SearchHit(TypedDict):
    title: str
    snippet: str
    href: str
    url: str
    product_key: str


class SearchResult(TypedDict):
    total_hits: int
    hits: list[SearchHit]


class PageContent(TypedDict):
    title: str
    url: str
    href: str
    text: str
    truncated: bool
    char_count: int
    stale: bool
    warning: str | None


ErrorCode = Literal[
    "empty_query",
    "invalid_href",
    "not_found",
    "upstream_unavailable",
    "version_unknown",
]


class ToolError(TypedDict, total=False):
    error: ErrorCode
    message: str
    stale: bool


def tool_error(code: ErrorCode, message: str, **extra: Any) -> ToolError:
    payload: ToolError = {"error": code, "message": message}
    payload.update(extra)  # type: ignore[typeddict-item]
    return payload
