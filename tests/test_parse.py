"""Tests for HTML → text parsing."""

from pathlib import Path

from ibmi_docs_mcp.parse import html_to_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_http_get_fixture() -> None:
    html = (FIXTURES / "content_http_get.html").read_text(encoding="utf-8")
    page = html_to_text(
        html,
        max_chars=50_000,
        href="ssw_ibm_i_75/db2/rbafzscahttpget.htm",
    )
    assert "HTTP_GET" in page["title"]
    assert "scalar function" in page["text"]
    assert "HTTP_GET" in page["text"]
    assert page["truncated"] is False
    assert page["href"].endswith("rbafzscahttpget.htm")


def test_truncation() -> None:
    html = (FIXTURES / "content_http_get.html").read_text(encoding="utf-8")
    page = html_to_text(html, max_chars=500, href="ssw_ibm_i_75/db2/rbafzscahttpget.htm")
    assert page["truncated"] is True
    assert "truncated at 500 chars" in page["text"]
