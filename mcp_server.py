#!/usr/bin/env python3
"""VU Handbook MCP server.

Model Context Protocol server exposing the Virtual University of Pakistan
Student Handbook (https://handbook.vu.edu.pk/) as a scoped, citable knowledge
source for AI agents.

The handbook is crawled ahead of time by ``tools/crawl_handbook.py`` into:

    data/toc.json       nested table of contents (navigation)
    data/pages.jsonl    raw records (portable dump)
    data/handbook.db    SQLite + FTS5 full-text index (search + fetch)

Serving from the local snapshot keeps queries fast and deterministic and avoids
hitting the VU web server on every agent turn. Refresh with::

    python3 tools/crawl_handbook.py --refresh-toc

Run (stdio transport, e.g. for Claude Desktop / any MCP client)::

    python3 mcp_server.py
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SOURCE_NAME = "Virtual University of Pakistan — Student Handbook"
SOURCE_URL = "https://handbook.vu.edu.pk/"

DATA_DIR = Path(os.environ.get("VU_HANDBOOK_DATA", Path(__file__).resolve().parent / "data"))
DB_PATH = DATA_DIR / "handbook.db"
TOC_PATH = DATA_DIR / "toc.json"

MAX_CONTENT_CHARS = 40_000
DEFAULT_SEARCH_LIMIT = 8
MAX_SEARCH_LIMIT = 25

# bm25 column weights: title > breadcrumb > headings > markdown
_BM25_WEIGHTS = "10.0, 6.0, 3.0, 1.0"

mcp = FastMCP(
    "vu-handbook",
    instructions=(
        f"Authoritative source: {SOURCE_NAME} ({SOURCE_URL}). "
        "Use vu_handbook_search to find relevant pages, vu_handbook_contents to "
        "navigate the table of contents, and vu_handbook_get to read a full page. "
        "Always cite the returned 'source' and 'breadcrumb' when answering students. "
        "If the handbook does not cover a question, say so and escalate to VU's "
        "official Support System rather than guessing."
    ),
)


# --------------------------------------------------------------------------
# data access
# --------------------------------------------------------------------------
def _db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Handbook database not found at {DB_PATH}. "
            "Run: python3 tools/crawl_handbook.py"
        )
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _toc() -> list[dict]:
    if not TOC_PATH.exists():
        raise FileNotFoundError(
            f"Handbook TOC not found at {TOC_PATH}. "
            "Run: python3 tools/crawl_handbook.py"
        )
    return json.loads(TOC_PATH.read_text(encoding="utf-8"))


def _expand(node: dict, depth: int) -> dict:
    """Render `node` and up to `depth` levels of its children beneath it."""
    kids = node.get("children", [])
    out = {
        "id": node["id"],
        "title": node["title"],
        "url": node.get("url"),
        "type": "page" if node.get("url") else "branch",
        "child_count": len(kids),
    }
    if kids and depth > 0:
        out["children"] = [_expand(c, depth - 1) for c in kids]
    return out


def _find_node(nodes: list[dict], path: str) -> tuple[list[dict], dict] | None:
    """Resolve a TOC location from an id, a URL, or a breadcrumb string."""
    path = (path or "").strip()
    if not path:
        # The site's root is a single "Home" node; surface its sections
        # directly so callers see the real top level on the first call.
        if len(nodes) == 1:
            return [], nodes[0]
        return [], {"id": 0, "title": SOURCE_NAME, "url": None, "children": nodes}

    # numeric id
    if re.fullmatch(r"\d+", path):
        target = int(path)

        def by_id(ns, crumb):
            for n in ns:
                here = crumb + [n["title"]]
                if n["id"] == target:
                    return here, n
                hit = by_id(n.get("children", []), here)
                if hit:
                    return hit
            return None

        hit = by_id(nodes, [])
        return hit if hit else None

    # URL
    if path.startswith("http"):
        for n, crumb in _walk(nodes, []):
            if n.get("url") == path:
                return crumb, n
        return None

    # breadcrumb: split on '>' or '/', match titles in order (case-insensitive)
    parts = [p.strip() for p in re.split(r"[>/]", path) if p.strip()]
    pool = nodes
    crumb: list[dict] = []
    node: dict | None = None
    matched: list[str] = []
    for part in parts:
        low = part.lower()
        node = next((c for c in pool if c["title"].strip().lower() == low), None)
        if node is None:
            node = next((c for c in pool if low in c["title"].strip().lower()), None)
        if node is None:
            return None
        matched.append(node["title"])
        pool = node.get("children", [])
        node = dict(node, _crumb=matched)
    assert node is not None
    # rebuild breadcrumb as plain titles of ancestors + self
    return matched[:-1], node


def _walk(nodes: list[dict], crumb: list[str]):
    for n in nodes:
        here = crumb + [n["title"]]
        yield here, n
        yield from _walk(n.get("children", []), here)


def _resolve_page(page) -> sqlite3.Row | None:
    """Resolve a page from an id, URL, exact title, or unique title substring."""
    q = str(page).strip()
    with _db() as con:
        if re.fullmatch(r"\d+", q):
            row = con.execute("SELECT * FROM pages WHERE id = ?", (int(q),)).fetchone()
            if row:
                return row
        if q.startswith("http"):
            row = con.execute("SELECT * FROM pages WHERE url = ?", (q,)).fetchone()
            if row:
                return row
            row = con.execute(
                "SELECT * FROM pages WHERE url LIKE ?", (f"%{q}",)
            ).fetchone()
            if row:
                return row
        row = con.execute(
            "SELECT * FROM pages WHERE lower(title) = lower(?)", (q,)
        ).fetchone()
        if row:
            return row
        rows = con.execute(
            "SELECT * FROM pages WHERE instr(lower(title), lower(?)) > 0", (q,)
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            raise LookupError(
                json.dumps(
                    {
                        "error": "ambiguous_title",
                        "query": q,
                        "candidates": [
                            {"id": r["id"], "title": r["title"], "breadcrumb": r["breadcrumb"]}
                            for r in rows[:15]
                        ],
                        "hint": "Call vu_handbook_get again with one of these ids.",
                    },
                    ensure_ascii=False,
                )
            )
        rows = con.execute(
            "SELECT * FROM pages WHERE instr(lower(breadcrumb), lower(?)) > 0 LIMIT 10",
            (q,),
        ).fetchall()
        if rows:
            raise LookupError(
                json.dumps(
                    {
                        "error": "no_title_match",
                        "query": q,
                        "candidates": [
                            {"id": r["id"], "title": r["title"], "breadcrumb": r["breadcrumb"]}
                            for r in rows
                        ],
                    },
                    ensure_ascii=False,
                )
            )
    return None


def _fts_query(query: str) -> list[str]:
    """Build a safe FTS5 MATCH expression; FTS syntax errors otherwise."""
    terms = re.findall(r"[A-Za-z0-9']+", query)
    quoted = [f'"{t}"' for t in terms if t]
    return quoted


# Function words that carry no retrieval signal for student questions.
_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "of", "in",
    "on", "at", "to", "for", "and", "or", "but", "if", "as", "by", "with", "from",
    "it", "its", "this", "that", "these", "those", "there", "here",
    "do", "does", "did", "done", "can", "could", "should", "would", "will", "shall",
    "may", "might", "must", "have", "has", "had",
    "i", "you", "we", "they", "he", "she", "my", "your", "our", "their", "me", "us",
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "not", "no", "yes", "any", "all", "some", "every", "than", "then", "too",
    "very", "just", "also", "into", "about", "up", "out", "so",
    # weak verbs / generic nouns that students add to questions but that
    # discriminate between handbook pages almost as badly as stopwords
    "get", "got", "make", "made", "want", "need", "needs", "take", "give",
    "show", "find", "tell", "know", "see", "look", "go", "come", "keep",
    "let", "try", "ask", "help", "use", "used", "able", "happen", "happens",
    "happened", "occur", "arise", "regarding", "related", "information",
    "details", "detail", "really", "actually", "possible", "procedure_for",
}
CANDIDATE_POOL = 60


def _significant_terms(query: str) -> list[str]:
    """Alphanumeric terms minus stop words, preserving order and uniqueness."""
    out: list[str] = []
    seen: set[str] = set()
    for t in re.findall(r"[a-z0-9']+", query.lower()):
        t = t.strip("'")
        if len(t) < 2 or t in _STOP or t in seen:
            continue
        seen.add(t)
        out.append(t)
    if not out:  # query was entirely stop words - fall back to everything
        out = [t for t in re.findall(r"[a-z0-9']+", query.lower()) if len(t) >= 2]
    return out


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------
@mcp.tool()
def vu_handbook_contents(path: str = "", depth: int = 2) -> dict:
    """Navigate the VU Student Handbook table of contents.

    Args:
        path: Where to look. Empty string = top level. Otherwise a node id
            ("11"), a full page URL, or a breadcrumb such as
            "Home > Examinations Department". Case-insensitive; '/' also works
            as a separator. Unknown segments fall back to substring matching.
        depth: How many levels of children to return (1 = immediate children).

    Returns the node at `path` plus its children. Child objects carry
    "type": "page" (has content, fetch with vu_handbook_get) or "branch".
    Use this to discover what the handbook covers before searching.
    """
    if depth < 1:
        depth = 1
    if depth > 6:
        depth = 6
    toc = _toc()
    hit = _find_node(toc, path)
    if hit is None:
        top = [{"id": n["id"], "title": n["title"], "type": "page" if n.get("url") else "branch"}
               for n in toc]
        raise LookupError(json.dumps(
            {"error": "path_not_found", "path": path, "top_level": top},
            ensure_ascii=False,
        ))
    crumb, node = hit
    node = {k: v for k, v in node.items() if k != "_crumb"}
    return {
        "source": SOURCE_NAME,
        "path": crumb,
        "breadcrumb": " > ".join(crumb + [node["title"]]) if node["id"] else SOURCE_NAME,
        "node": _expand(node, depth),
    }


@mcp.tool()
def vu_handbook_search(query: str, limit: int = DEFAULT_SEARCH_LIMIT) -> dict:
    """Full-text search across the entire VU Student Handbook.

    Args:
        query: Natural-language question or keywords, e.g. "deadline for
            semester freeze" or "how to submit assignment".
        limit: Maximum results (1-25, default 8).

    Returns ranked matches with id, title, breadcrumb (its place in the
    handbook), url and a text snippet. Follow up with vu_handbook_get(id) to
    read a page in full. Empty `results` means the handbook has no match -
    do not infer an answer.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))

    sig = _significant_terms(query)
    if not sig:
        return {
            "source": SOURCE_NAME, "query": query, "count": 0, "results": [],
            "note": "No searchable terms in query.",
        }

    # OR for recall; bm25 (title-weighted) for ordering. Precision comes from
    # requiring each hit to cover ~60% of the query's significant terms
    # (ceil(3n/5)), which stops one or two incidental words from dragging in
    # unrelated pages while still letting a natural question through.
    match = " OR ".join(f'"{t}"' for t in sig)
    n = len(sig)
    need = max(1, (3 * n + 4) // 5)
    pool = min(max(limit * 4, 40), CANDIDATE_POOL)

    sql = """
        SELECT p.id, p.title, p.breadcrumb, p.url, p.kind, p.headings, p.markdown,
               bm25(pages_fts, %s) AS rank,
               snippet(pages_fts, 3, '[', ']', '…', 26) AS snippet
        FROM pages_fts
        JOIN pages p ON p.id = pages_fts.rowid
        WHERE pages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """ % _BM25_WEIGHTS

    with _db() as con:
        try:
            rows = con.execute(sql, (match, pool)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            rows = con.execute(
                """SELECT id, title, breadcrumb, url, kind, headings, markdown,
                          0.0 AS rank, substr(markdown, 1, 200) AS snippet
                   FROM pages
                   WHERE instr(lower(title), lower(?)) > 0
                      OR instr(lower(markdown), lower(?)) > 0
                   ORDER BY id LIMIT ?""",
                (query.strip(), f"%{query.strip()}%", pool),
            ).fetchall()

    scored = []
    for r in rows:
        in_heading = f"{r['title']} {r['breadcrumb']} {r['headings']}".lower()
        body = (r["markdown"] or "").lower()
        hits = [t for t in sig if t in in_heading or t in body]
        if len(hits) < need:
            continue
        title_hits = sum(1 for t in sig if t in r["title"].lower())
        scored.append((title_hits * 2 + len(hits), float(r["rank"] or 0.0), r, hits))
    scored.sort(key=lambda x: (-x[0], x[1]))
    top = scored[:limit]

    return {
        "source": SOURCE_NAME,
        "query": query,
        "match": match,
        "required_terms": need,
        "count": len(top),
        "results": [
            {
                "id": r["id"],
                "title": r["title"],
                "breadcrumb": r["breadcrumb"],
                "url": r["url"],
                "kind": r["kind"],
                "matched_terms": hits,
                "snippet": (r["snippet"] or "").strip(),
                "rank": round(rank, 3),
            }
            for _score, rank, r, hits in top
        ],
        "note": (
            "No match found - the handbook does not cover this. Say so and "
            "escalate to VU's Support System instead of guessing."
            if not top
            else "Call vu_handbook_get(id) to read a page in full."
        ),
    }


@mcp.tool()
def vu_handbook_get(page: str | int) -> dict:
    """Read one handbook page in full.

    Args:
        page: A page id ("20"), an exact/unique title ("Acts of Unfair Means"),
            or a full handbook URL.

    Returns title, breadcrumb, canonical url, headings, the full markdown
    `content`, plus surrounding navigation (parent, children, siblings) so a
    follow-up hop needs no extra lookup. Content longer than 40k characters is
    truncated with `truncated: true`.
    """
    row = _resolve_page(page)
    if row is None:
        raise LookupError(json.dumps(
            {"error": "page_not_found", "query": str(page),
             "hint": "Use vu_handbook_search to locate the page first."},
            ensure_ascii=False,
        ))

    crumb = [c for c in (row["breadcrumb"] or "").split(" > ") if c]
    content = row["markdown"] or ""
    truncated = len(content) > MAX_CONTENT_CHARS
    if truncated:
        content = content[:MAX_CONTENT_CHARS] + "\n\n[... truncated ...]"

    nav = _navigation(row["id"], crumb)
    return {
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "id": row["id"],
        "title": row["title"],
        "breadcrumb": crumb,
        "url": row["url"],
        "kind": row["kind"],
        "headings": [h for h in (row["headings"] or "").split("\n") if h],
        "content": content,
        "truncated": truncated,
        "navigation": nav,
    }


def _navigation(page_id: int, crumb: list[str]) -> dict:
    toc = _toc()
    found: dict | None = None

    def dig(nodes, path):
        nonlocal found
        for n in nodes:
            here = path + [n["title"]]
            if n["id"] == page_id:
                found = {"node": n, "crumb": here}
                return True
            if dig(n.get("children", []), here):
                return True
        return False

    dig(toc, [])
    if not found:
        return {}

    node = found["node"]
    # locate the parent's child list
    def parent_children(nodes, path):
        for n in nodes:
            if any(c["id"] == page_id for c in n.get("children", [])):
                return n.get("children", [])
            here = path + [n["title"]]
            res = parent_children(n.get("children", []), here)
            if res is not None:
                return res
        return None

    siblings = parent_children(toc, []) or []
    return {
        "parent": " > ".join(found["crumb"][:-1]) or SOURCE_NAME,
        "children": [
            {"id": c["id"], "title": c["title"], "type": "page" if c.get("url") else "branch"}
            for c in node.get("children", [])
        ],
        "siblings": [
            {"id": s["id"], "title": s["title"]}
            for s in siblings
            if s["id"] != page_id
        ][:25],
    }


# --------------------------------------------------------------------------
# resources
# --------------------------------------------------------------------------
@mcp.resource("vu-handbook://toc")
def toc_resource() -> str:
    """The complete nested table of contents of the VU Student Handbook."""
    return json.dumps(
        {"source": SOURCE_NAME, "source_url": SOURCE_URL, "toc": _toc()},
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource("vu-handbook://page/{page_id}")
def page_resource(page_id: str) -> str:
    """Raw markdown of a handbook page by id."""
    row = _resolve_page(page_id)
    if row is None:
        raise LookupError(f"no page with id {page_id}")
    return row["markdown"] or ""


@mcp.resource("vu-handbook://stats")
def stats_resource() -> str:
    """Coverage statistics for the local handbook snapshot."""
    with _db() as con:
        pages = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        chars = con.execute("SELECT COALESCE(SUM(LENGTH(markdown)),0) FROM pages").fetchone()[0]
        ok = con.execute("SELECT COUNT(*) FROM pages WHERE status='ok'").fetchone()[0]
    return json.dumps(
        {
            "source": SOURCE_NAME,
            "pages": pages,
            "fully_fetched": ok,
            "total_characters": chars,
            "db": str(DB_PATH),
            "toc": str(TOC_PATH),
            "refresh_command": "python3 tools/crawl_handbook.py --refresh-toc",
        },
        indent=2,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
