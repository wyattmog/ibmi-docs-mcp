"""Stderr-only logging setup."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: int | str = "INFO") -> None:
    """Configure package logging to stderr only (stdout is the MCP channel)."""
    resolved = level if isinstance(level, int) else getattr(logging, str(level).upper(), logging.INFO)

    package = logging.getLogger("ibmi_docs_mcp")
    package.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    package.addHandler(handler)
    package.setLevel(resolved)
    package.propagate = False

    # Ensure child loggers inherit the package level.
    for name in ("ibmi_docs_mcp.tools", "ibmi_docs_mcp.client", "ibmi_docs_mcp.cache"):
        logging.getLogger(name).setLevel(resolved)
