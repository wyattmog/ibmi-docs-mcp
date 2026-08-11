"""Tests for version → product key mapping."""

import pytest

from ibmi_docs_mcp.versioning import UnknownVersionError, version_to_product_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7.5.0", "ssw_ibm_i_75"),
        ("7.5", "ssw_ibm_i_75"),
        ("75", "ssw_ibm_i_75"),
        ("ssw_ibm_i_75", "ssw_ibm_i_75"),
        ("7.4.0", "ssw_ibm_i_74"),
        ("7.6", "ssw_ibm_i_76"),
    ],
)
def test_version_to_product_key(raw: str, expected: str) -> None:
    assert version_to_product_key(raw) == expected


@pytest.mark.parametrize("raw", ["", "8.1", "7.9", "ssw_ibm_i_99", "nope"])
def test_unknown_version(raw: str) -> None:
    with pytest.raises(UnknownVersionError):
        version_to_product_key(raw)
