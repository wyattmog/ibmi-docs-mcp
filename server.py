"""FastMCP stdio entrypoint for IBM i docs tools."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from ibmi_docs_mcp.config import load_settings
from ibmi_docs_mcp.logging_setup import setup_logging
from ibmi_docs_mcp.tools import register_tools

settings = load_settings()
setup_logging(settings.log_level)
logger = logging.getLogger("ibmi_docs_mcp")

mcp = FastMCP("ibmi-docs")
register_tools(mcp, settings)
logger.info(
    "ibmi-docs ready version=%s cache=%s max_chars=%s",
    settings.version,
    settings.cache_path,
    settings.max_chars,
)

if __name__ == "__main__":
    mcp.run()
