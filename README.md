# VU Handbook MCP

A Model Context Protocol server that exposes the **Virtual University of
Pakistan Student Handbook** (<https://handbook.vu.edu.pk/>) as a single,
scoped, citable knowledge source for AI agents.

This is **step one** of the multi-agent student support system: the handbook
is the authoritative source for nearly all student guidance, so it gets its
own MCP server that every agent can share.

## Coverage

| | |
|---|---|
| Table-of-contents nodes | 319 (1 root, 27 branches, 310 pages) |
| Pages indexed | 310 / 310 fetched, 0 failures |
| Extracted text | 1,086,576 characters |
| Depth | 5 levels (e.g. Home → Examinations Department → Conduct of Examination → Unfair Means → Acts of Unfair Means) |
| Full-text index | SQLite FTS5, title-weighted BM25 |
| Extras | 1 policy PDF extracted (VU Plagiarism Policy) |

Serve from a local snapshot so agent turns are fast, deterministic, and do not
hammer the VU web server.

## Quick start

```bash
pip install mcp                      # server runtime
python3 mcp_server.py                # stdio transport
python3 mcp_server.py --http         # Streamable HTTP transport
```

### Register with an MCP client

Claude Desktop / any stdio MCP client:

```json
{
  "mcpServers": {
    "vu-handbook": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp_server.py"],
      "cwd": "/absolute/path/to/project"
    }
  }
}
```

From code (LangGraph, OpenAI Agents SDK, plain `mcp` client):

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command="python3", args=["mcp_server.py"])
async with stdio_client(params) as (r, w):
    async with ClientSession(r, w) as s:
        await s.initialize()
        hits = await s.call_tool("vu_handbook_search",
                                 {"query": "how do I apply for semester freeze"})
        page = await s.call_tool("vu_handbook_get", {"page": 64})
```

### Run over HTTP (production)

```bash
python3 mcp_server.py --http --host 0.0.0.0 --port 8000 --allow-host vumcp.example.com
```

| Flag | Meaning |
|---|---|
| `--http` | Streamable HTTP transport instead of stdio |
| `--host` / `--port` | bind address (loopback by default) |
| `--allow-host HOST` | extra allowed `Host` header — **required** for non-loopback binds (repeatable, `host:*` wildcards work) |
| `--allow-origin ORIGIN` | extra allowed `Origin` for browser-based clients (repeatable) |
| `--stateless` | no session ids, for multi-instance / load-balanced deployments |

- **Health probe:** `GET /healthz` → `{"status": "ok"}` (no DB access).
- **DNS-rebinding protection is ON:** requests with a spoofed `Host` are
  rejected with **421 Misdirected Request**, a foreign `Origin` with **403**.
  Loopback (`127.0.0.1`, `localhost`, `[::1]`) always works; anything else
  must be granted via `--allow-host` / `--allow-origin`.
- **Read-only:** the server opens SQLite with `mode=ro`, so an agent bug can
  never mutate the snapshot — only `tools/crawl_handbook.py` writes.
- **Concurrent sessions are safe:** verified by `tests/test_http.py`
  (8 simultaneous sessions, distinct session ids, shared read-only DB).

Connect from code:

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (r, w, sid):
    async with ClientSession(r, w) as s:
        await s.initialize()
        hits = await s.call_tool("vu_handbook_search",
                                 {"query": "how do I apply for semester freeze"})
```

## Tools

### `vu_handbook_contents(path="", depth=2)`
Navigate the table of contents.

- `path` — `""` (top level), a node id (`"11"`), a full URL, or a breadcrumb
  such as `"Home > Examinations Department"` (case-insensitive, `/` also works).
- `depth` — how many levels of children to return (1–6).

Returns each child with `type: "page"` (has content) or `"branch"`, plus
`child_count`. Use it to discover *what the handbook covers* before searching.

### `vu_handbook_search(query, limit=8)`
Full-text search across all 310 pages.

Returns ranked matches with `id`, `title`, `breadcrumb`, `url`, `snippet`,
`matched_terms` and `rank`. Empty `results` carries an explicit
"not covered — escalate to VU Support System" note so an agent never guesses.

### `vu_handbook_get(page)`
Read one page in full. `page` accepts an id (`20`), an exact or unique title
(`"Acts of Unfair Means"`), or a handbook URL.

Returns `title`, `breadcrumb`, `url`, `headings`, `content` (markdown,
capped at 40 000 chars with `truncated`), and `navigation` (`parent`,
`children`, `siblings`) so follow-up hops need no extra lookup.

An ambiguous title raises an error listing candidate ids rather than silently
returning the wrong page.

## Resources

| URI | Contents |
|---|---|
| `vu-handbook://toc` | Complete nested table of contents |
| `vu-handbook://page/{page_id}` | Raw markdown of one page |
| `vu-handbook://stats` | Snapshot coverage statistics |

## Rebuilding the snapshot

```bash
pip install --target .deps pypdf        # PDF text extraction (workspace-local)
python3 tools/crawl_handbook.py --refresh-toc --workers 4
python3 tests/test_mcp.py               # 53 end-to-end protocol checks (stdio)
python3 tests/test_http.py              # 20 HTTP transport checks (spawns server)
python3 tests/eval_queries.py           # retrieval quality on real questions
```

Outputs land in `data/`:

```
data/toc.json       nested TOC (navigation)
data/pages.jsonl    raw records (portable dump)
data/handbook.db    SQLite + FTS5 index (search + fetch)
```

Point the server at another directory with `VU_HANDBOOK_DATA=/path/to/data`.

## How the crawl works

`handbook.vu.edu.pk` is a 2003-era ASP.NET frameset site with an invalid TLS
certificate. Three things are worth knowing:

1. **The TOC is server-side collapsed.** Only ~23 of 319 nodes render on first
   load; the rest are hydrated by `__doPostBack('PermissionTree', 't<path>')`.
   `tools/vu_handbook_client.py` replays those postbacks until every branch is
   expanded, then parses the final client-side render, tracking
   `PermissionTreen{N}Nodes` containers to recover the exact hierarchy. No
   `__VIEWSTATE` binary decoding required.
2. **Three encodings live in one corpus.** Most pages are raw windows-1252;
   some are UTF-8 carrying latin-1-decoded CP1252 smart quotes (C1 controls)
   while still *declaring* `windows-1252`; the Course Selection pages are
   UTF-16LE with a BOM. Trusting the declared charset double-mangles the second
   group into `Â“` and turns the third into ~59 000 NUL bytes per page.
   `extract.decode_page()` detects BOM → UTF-16, else UTF-8, else CP1252, then
   maps surviving C1 controls to their CP1252 glyphs.
3. **Invalid HTML needs a tolerant renderer.** Tables wrapped in `<b>`, lists
   inside `<p>`, and Word `if !supportLists` markers. `tools/extract.py` walks
   the tree in document order, promotes the grey section-header tables to `##`
   headings, and scrubs export leftovers.

## Search ranking

`OR` over the query's significant terms (stop words removed) for recall, BM25
with title > breadcrumb > headings > body weighting for ordering, then a
precision filter: a page must contain at least **60% of the query's
significant terms** (`ceil(3n/5)`).

Measured on `tests/eval_queries.py` — 12 realistic student questions:

```
retrieval: 12/12 expected pages in top-3 (100%)
```

Measured failure mode: a nonsense query (`zzzqqqxyz spaceship launch code`)
returns 0 results plus the escalation note rather than a lucky single hit.

## Known limitations

- **Lexical, not semantic.** Retrieval matches words, not meaning. A question
  phrased very differently from the handbook's wording can miss — e.g. the
  handbook says "awarded an F grade… repeat the course" and never says
  "fail". Add embeddings later if that matters.
- **Static snapshot.** The handbook changes; re-run the crawler to refresh.
  VU also publishes dated announcements and FAQs outside the handbook — those
  are separate sources for later agents.
- **Informational only.** This server has no access to student records and
  performs no actions. Account-specific questions must be escalated to VU's
  official Support System (<https://www.vu.edu.pk/supportsystem/>).

## Layout

```
mcp_server.py                 the MCP server (stdio + Streamable HTTP)
tools/vu_handbook_client.py   TOC expansion + page fetch (postbacks, retries)
tools/extract.py              HTML/PDF -> markdown, encoding handling
tools/crawl_handbook.py       build data/ snapshot
tests/test_mcp.py             end-to-end protocol tests, stdio (53 checks)
tests/test_http.py            HTTP transport tests (20 checks)
tests/eval_queries.py         retrieval quality eval (12 questions)
data/                         generated snapshot
```
