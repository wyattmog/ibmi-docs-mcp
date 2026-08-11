# ibmi-docs-mcp

FastMCP server that lets agents search and fetch IBM i documentation via IBM Documentation’s public APIs.

## Setup

```bash
uv sync --extra dev
```

## Run (stdio MCP)

```bash
uv run python server.py
```

## Cursor / Bob mcp.json

```json
{
  "mcpServers": {
    "ibmi-docs": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/ibmi-docs-mcp",
        "python",
        "server.py"
      ],
      "env": {
        "IBMI_DOCS_VERSION": "7.5.0"
      }
    }
  }
}
```

## Tools

1. `search_ibm_docs(query, version?, limit?)` — ranked candidates (`title`, `snippet`, `href`, `url`)
2. `fetch_ibm_doc(url_or_href, version?)` — plain-text topic body for a chosen `href`

Typical flow: search `HTTP_GET` → pick best hit → fetch its `href`.

## Env vars

See `.env.example` for tunables (`IBMI_DOCS_VERSION`, `IBMI_DOCS_CACHE_PATH`, `IBMI_DOCS_MAX_CHARS`, `IBMI_DOCS_LOG_LEVEL`, …).

Logs go to **stderr** (never stdout — that is the MCP channel). When Cursor launches the server, check the MCP server output / logs panel for lines like `search cache hit` / `fetch miss → IBM`.

## Tests

```bash
uv run pytest
```

## License

MIT — see [LICENSE](./LICENSE).
