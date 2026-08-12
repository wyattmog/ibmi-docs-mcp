# ibmi-docs-mcp

FastMCP server that lets agents search and fetch IBM i documentation via IBM Documentation’s public APIs.

Typical flow: **search** → pick the best hit’s `href` → **fetch** that topic as plain text.

Full tool contracts (parameters, response JSON, errors): [docs/TOOLS.md](docs/TOOLS.md).

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## Setup

```bash
uv sync --extra dev
```

## Run (stdio MCP)

```bash
uv run python server.py
```

Or: `uv run python -m ibmi_docs_mcp`

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

Prefer short object/command names (e.g. `HTTP_GET`, `WRKACTJOB`). Results are IBM-ranked; do not assume hit #1 is always correct.

See [docs/TOOLS.md](docs/TOOLS.md) for response shapes and error codes.

## Supported versions

IBM i **7.4**, **7.5**, and **7.6**. Accepted forms include:

| Form | Example |
|------|---------|
| Semantic | `7.5`, `7.5.0` |
| Short | `75` |
| Product key | `ssw_ibm_i_75` |

Default is `IBMI_DOCS_VERSION=7.5.0` (or pass `version` per tool call).

## Env vars

Set via `.env` or the MCP host `env` block. Defaults match [`.env.example`](.env.example).

| Variable | Default | Purpose |
|----------|---------|---------|
| `IBMI_DOCS_VERSION` | `7.5.0` | Default IBM i version for search |
| `IBMI_DOCS_CACHE_PATH` | `~/.cache/ibmi-docs-mcp/docs_cache.db` | SQLite cache file (`~` expanded) |
| `IBMI_DOCS_TTL_DAYS` | `30` | Soft TTL; stale rows may still be served on outage |
| `IBMI_DOCS_MAX_CHARS` | `12000` | Max plain-text chars returned by fetch |
| `IBMI_DOCS_HTTP_TIMEOUT` | `20` | HTTP timeout (seconds) |
| `IBMI_DOCS_MAX_RETRIES` | `3` | Retries for transient upstream failures |
| `IBMI_DOCS_MAX_CONCURRENCY` | `2` | Max concurrent IBM HTTP requests |
| `IBMI_DOCS_USER_AGENT` | `ibmi-docs-mcp/0.1 (+local-agent)` | User-Agent sent to IBM |
| `IBMI_DOCS_BASE_URL` | `https://www.ibm.com` | IBM docs API base |
| `IBMI_DOCS_LOG_LEVEL` | `INFO` | Log level (stderr only) |

## Logging

Logs go to **stderr** only (stdout is the MCP channel). In Cursor, open the MCP server output / logs panel for lines like `search cache hit` or `fetch miss → IBM`.

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `empty_query` | Pass a non-blank `query` |
| `invalid_href` | Use an `href` from `search_ibm_docs` (e.g. `ssw_ibm_i_75/db2/….htm`). Human URLs with `?topic=` are rejected |
| `version_unknown` | Use 7.4 / 7.5 / 7.6 (or `74` / `75` / `76` / `ssw_ibm_i_7x`) |
| `truncated: true` on fetch | Raise `IBMI_DOCS_MAX_CHARS`, or fetch a more specific topic |
| `upstream_unavailable` | Check network; warm cache may still return with `stale: true` + `warning` |
| Cache location | Default `~/.cache/ibmi-docs-mcp/docs_cache.db`, or set `IBMI_DOCS_CACHE_PATH` |

## Tests

```bash
uv run pytest
```

## License

MIT — see [LICENSE](./LICENSE).
