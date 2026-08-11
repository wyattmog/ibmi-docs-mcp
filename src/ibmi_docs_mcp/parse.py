"""HTML → plain text extraction."""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from bs4 import BeautifulSoup

from ibmi_docs_mcp.models import PageContent

_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "iframe")
_MULTI_NL = re.compile(r"\n{3,}")
_TRUNCATION_MARKER = "[truncated at"


def text_is_truncated(text: str) -> bool:
    """True when plain text includes our truncation suffix."""
    return _TRUNCATION_MARKER in text


def html_to_text(
    html: str,
    *,
    max_chars: int,
    href: str | None = None,
    url: str | None = None,
) -> PageContent:
    """Convert IBM docs content HTML into truncated plain text."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    root = (
        soup.find("article")
        or soup.find(attrs={"role": "main"})
        or soup.find("main")
        or soup.find(id="content")
        or soup.body
        or soup
    )

    title = _extract_title(soup, root, href)
    text = root.get_text(separator="\n", strip=True)
    text = _MULTI_NL.sub("\n\n", text)
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()

    truncated = False
    if max_chars > 0 and len(text) > max_chars:
        truncated = True
        text = (
            text[:max_chars].rstrip()
            + f"\n\n[truncated at {max_chars} chars; refine search or fetch a more specific topic]"
        )

    resolved_url = url or (
        f"https://www.ibm.com/docs/api/v1/content/{href}" if href else ""
    )

    return PageContent(
        title=title,
        url=resolved_url,
        href=href or "",
        text=text,
        truncated=truncated,
        char_count=len(text),
        stale=False,
        warning=None,
    )


def _extract_title(soup: BeautifulSoup, root: object, href: str | None) -> str:
    h1 = getattr(root, "find", lambda *a, **k: None)("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(strip=True)
    if href:
        return PurePosixPath(href).stem
    return ""
