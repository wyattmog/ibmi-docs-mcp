"""IBM i version string → product key mapping."""

from __future__ import annotations

import re

_PRODUCT_KEY_RE = re.compile(r"^ssw_ibm_i_(\d+)$")
_VERSION_RE = re.compile(
    r"^(?:(\d+)\.(\d+)(?:\.(\d+))?|(\d{2,}))$"
)

# Verified product keys (SPEC §5.2).
_SUPPORTED_MINOR = {4, 5, 6}


class UnknownVersionError(ValueError):
    """Raised when a version string cannot be mapped to a product key."""


def version_to_product_key(version: str) -> str:
    """Map an IBM i version string to ``ssw_ibm_i_XX``.

    Accepts ``7.5``, ``7.5.0``, ``75``, or a raw product key ``ssw_ibm_i_75``.
    """
    raw = version.strip()
    if not raw:
        raise UnknownVersionError("Version string can not be empty")

    product_match = _PRODUCT_KEY_RE.match(raw)
    if product_match:
        minor = int(product_match.group(1))
        # Keys are like 74, 75, 76 — two-digit VRM encoding (7*10+minor for 7.x).
        if minor // 10 == 7 and (minor % 10) in _SUPPORTED_MINOR:
            return raw
        # Also allow exact known forms even if encoding looks odd, if listed.
        if raw in {f"ssw_ibm_i_7{m}" for m in _SUPPORTED_MINOR}:
            return raw
        raise UnknownVersionError(f"Unsupported product key: {raw}")

    match = _VERSION_RE.match(raw)
    if not match:
        raise UnknownVersionError(f"Unrecognized version: {version}")

    if match.group(4):
        # Short form like "75"
        code = int(match.group(4))
        major, minor = divmod(code, 10)
        if major != 7 or minor not in _SUPPORTED_MINOR:
            raise UnknownVersionError(f"Unsupported version: {version}")
        return f"ssw_ibm_i_{code}"

    major = int(match.group(1))
    minor = int(match.group(2))
    if major != 7 or minor not in _SUPPORTED_MINOR:
        raise UnknownVersionError(f"Unsupported version: {version}")
    return f"ssw_ibm_i_{major}{minor}"


def product_key_to_version(product_key: str) -> str:
    """Best-effort reverse map for tool responses (e.g. ssw_ibm_i_75 → 7.5.0)."""
    match = _PRODUCT_KEY_RE.match(product_key.strip())
    if not match:
        raise UnknownVersionError(f"Unrecognized product key: {product_key}")
    code = int(match.group(1))
    major, minor = divmod(code, 10)
    return f"{major}.{minor}.0"
