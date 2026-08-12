# Tool / API reference

Install and Cursor wiring: [README.md](../README.md).

Both tools return JSON objects as MCP tool results. Errors are structured payloads (not thrown exceptions) when possible.

## Workflow

1. Call `search_ibm_docs` with a short command or object name.
2. Read `title` / `snippet`; pick the best hit (do not assume rank 1).
3. Call `fetch_ibm_doc` with that hit’s `href`.

---

## `search_ibm_docs`

Search IBM i documentation using IBM’s public docs search index.

### Parameters

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `query` | string | required | Prefer short names (`HTTP_GET`, `WRKACTJOB`, `CHGJRN`). Whitespace is normalized; blank → `empty_query` |
| `version` | string \| null | server default (`IBMI_DOCS_VERSION`) | See [supported versions](../README.md#supported-versions) |
| `limit` | int | `5` | Clamped to **1..20**; passed through to IBM as `&limit=` |

### Success response

```json
{
  "version": "7.5.0",
  "product_key": "ssw_ibm_i_75",
  "query": "HTTP_GET",
  "total_hits": 7,
  "cached": false,
  "stale": false,
  "results": [
    {
      "rank": 1,
      "title": "HTTP_GET and HTTP_GET_BLOB",
      "snippet": "The HTTP_GET or HTTP_GET_BLOB scalar function...",
      "href": "ssw_ibm_i_75/db2/rbafzscahttpget.htm",
      "url": "https://www.ibm.com/docs/en/i/7.5.0?topic=functions-http-get-http-get-blob"
    }
  ]
}
```

| Field | Meaning |
|-------|---------|
| `version` | Version string used for this call |
| `product_key` | IBM product key (e.g. `ssw_ibm_i_75`) |
| `query` | Normalized query |
| `total_hits` | IBM total hit count (may exceed `results.length`) |
| `cached` | Served from SQLite cache |
| `stale` | Cache past TTL, used because upstream failed |
| `results` | Ranked hits for this page (`limit` sized) |
| `warning` | Optional; present when serving stale cache |

`results: []` with `total_hits: 0` is a **success** (no matches), not an error.

Titles and snippets have HTML highlight tags stripped.

---

## `fetch_ibm_doc`

Fetch one topic as plain text.

### Parameters

| Name | Type | Default | Notes |
|------|------|---------|-------|
| `url_or_href` | string | required | Prefer `href` from search. Also accepts a content API URL |
| `version` | string \| null | unused in v1 | Reserved; product is usually embedded in `href` |

### Accepted `url_or_href` forms

| Accepted | Example |
|----------|---------|
| Relative href | `ssw_ibm_i_75/db2/rbafzscahttpget.htm` |
| Content API URL | `https://www.ibm.com/docs/api/v1/content/ssw_ibm_i_75/db2/rbafzscahttpget.htm` |

| Rejected | Why |
|----------|-----|
| Human docs URL (`?topic=…`) | Ambiguous in v1; pass search `href` instead |
| Other hosts / schemes | Fail closed (`invalid_href`) |
| Path traversal (`..`) | Fail closed |

### Success response

```json
{
  "title": "HTTP_GET and HTTP_GET_BLOB",
  "url": "https://www.ibm.com/docs/en/i/7.5.0?topic=functions-http-get-http-get-blob",
  "href": "ssw_ibm_i_75/db2/rbafzscahttpget.htm",
  "text": "The HTTP_GET or HTTP_GET_BLOB scalar function...",
  "truncated": true,
  "char_count": 12150,
  "stale": false,
  "warning": null,
  "cached": false
}
```

| Field | Meaning |
|-------|---------|
| `title` | Topic title |
| `url` | Human docs URL when known; otherwise content API URL |
| `href` | Content path used for fetch/cache |
| `text` | Plain text body (may include a truncation suffix) |
| `truncated` | `true` if text was cut at `IBMI_DOCS_MAX_CHARS` |
| `char_count` | Length of returned `text` |
| `stale` | Past-TTL cache served after upstream failure |
| `warning` | Optional message (e.g. stale reason) |
| `cached` | Served from SQLite cache |

When truncated, `text` ends with a marker like:

```text
[truncated at 12000 chars; refine search or fetch a more specific topic]
```

---

## Errors

Structured error shape:

```json
{
  "error": "invalid_href",
  "message": "Pass href from search_ibm_docs (e.g. ssw_ibm_i_75/db2/....htm)"
}
```

| Code | When |
|------|------|
| `empty_query` | Blank / whitespace-only search query (no HTTP) |
| `invalid_href` | Bad scheme, disallowed host, human `?topic=` URL, traversal, or malformed href (no HTTP) |
| `not_found` | IBM content API returned 404 |
| `upstream_unavailable` | Network / 5xx after retries; includes `"stale": false` when no cache to fall back on |
| `version_unknown` | Unsupported or unrecognized version string |

### Stale-on-outage

If IBM is unreachable but a cache row exists (even past TTL), tools may still return success data with:

- `stale: true`
- `cached: true`
- `warning` describing the upstream failure

Only when there is **no** usable cache row do you get `upstream_unavailable`.

---

## Example session

**1. Search**

```text
search_ibm_docs(query="HTTP_GET", version="7.5.0", limit=5)
```

Pick the scalar-function topic, e.g.:

```text
href = "ssw_ibm_i_75/db2/rbafzscahttpget.htm"
```

**2. Fetch**

```text
fetch_ibm_doc(url_or_href="ssw_ibm_i_75/db2/rbafzscahttpget.htm")
```

**3. Read the body**

- Confirm `title` / `text` match the topic you wanted.
- If `truncated` is `true`, raise `IBMI_DOCS_MAX_CHARS` or search for a narrower topic.
