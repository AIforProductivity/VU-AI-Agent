#!/usr/bin/env python3
"""Crawl handbook.vu.edu.pk into a local, searchable dataset.

Outputs (under data/):
    toc.json        nested table of contents exactly as the site presents it
    pages.jsonl     one record per reachable page (title, breadcrumb, markdown)
    handbook.db     SQLite + FTS5 full-text index over the same records

Usage:
    python3 tools/crawl_handbook.py [--out data] [--workers 4] [--refresh-toc]
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
# Workspace-local wheels (e.g. pypdf) installed with `pip install --target .deps`.
_DEPS = Path(__file__).resolve().parent.parent / ".deps"
if _DEPS.is_dir():
    sys.path.insert(0, str(_DEPS))

import re  # noqa: E402


def _norm(text: str) -> str:
    """Collapse PDF extraction noise into readable paragraphs."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

from extract import extract  # noqa: E402
from vu_handbook_client import HandbookClient, Node, flatten, parse_tree  # noqa: E402

_tls = threading.local()


def _client() -> HandbookClient:
    if not hasattr(_tls, "client"):
        _tls.client = HandbookClient()
    return _tls.client


def node_to_dict(n: Node) -> dict:
    return {
        "id": n.node_id,
        "title": n.title,
        "url": n.href,
        "depth": n.depth,
        "children": [node_to_dict(c) for c in n.children],
    }


def build_toc(refresh: bool, cache: Path, log=print) -> list[Node]:
    if cache.exists() and not refresh:
        log(f"[toc] using cached {cache}")
        return _load_cached_toc(json.loads(cache.read_text()))
    log("[toc] fetching Menu.aspx and expanding every branch ...")
    client = HandbookClient()
    html = client.expand_all(log=log)
    roots = parse_tree(html)
    log(f"[toc] parsed {sum(1 for _ in flatten(roots))} nodes")
    cache.write_text(json.dumps([node_to_dict(r) for r in roots], indent=2))
    return roots


def _load_cached_toc(data: list[dict]) -> list[Node]:
    def load(d: dict) -> Node:
        node = Node(
            title=d["title"],
            href=d.get("url"),
            cls="",
            depth=d.get("depth", 0),
            path="",
            node_id=d["id"],
        )
        node.children = [load(c) for c in d.get("children", [])]
        return node

    return [load(d) for d in data]


def collect_targets(roots: list[Node]) -> list[tuple[Node, str, list[str]]]:
    """(node, url, breadcrumb) for every tree node that points at a page."""
    targets = []

    def walk(n: Node, crumb: list[str]) -> None:
        here = crumb + [n.title]
        if n.href:
            targets.append((n, n.href, here))
        for c in n.children:
            walk(c, here)

    for r in roots:
        walk(r, [])
    return targets


def fetch_one(node: Node, url: str, crumb: list[str]) -> dict:
    record = {
        "id": node.node_id,
        "title": node.title,
        "url": url,
        "breadcrumb": crumb[:-1],
        "depth": node.depth,
        "kind": "page",
        "markdown": "",
        "headings": [],
        "links": [],
        "status": "ok",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if urlparse(url).path.lower().endswith(".pdf"):
        record["kind"] = "pdf"
        try:
            from io import BytesIO

            from pypdf import PdfReader

            blob = _client().get_raw(url)
            reader = PdfReader(BytesIO(blob))
            record["markdown"] = _norm(
                "\n\n".join((page.extract_text() or "") for page in reader.pages)
            )
        except Exception as e:  # noqa: BLE001 - keep the link even if text fails
            record["status"] = f"pdf-error: {type(e).__name__}: {e}"
        return record

    try:
        # Raw bytes: encoding detection needs the original BOM/charset, and
        # round-tripping through str would destroy it.
        content = _client().get_raw(url)
    except Exception as e:  # noqa: BLE001 - record, never abort the crawl
        record["status"] = f"error: {type(e).__name__}: {e}"
        return record

    try:
        page = extract(content, url)
    except Exception as e:  # noqa: BLE001
        record["status"] = f"extract-error: {type(e).__name__}: {e}"
        return record

    record.update(
        {
            "title": node.title or page["title"],
            "source_title": page["title"],
            "markdown": page["markdown"],
            "headings": page["headings"],
            "links": page["links"],
        }
    )
    return record


def build_db(records: list[dict], db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE pages (
            id          INTEGER PRIMARY KEY,
            title       TEXT NOT NULL,
            url         TEXT NOT NULL,
            breadcrumb  TEXT NOT NULL,
            kind        TEXT NOT NULL,
            status      TEXT NOT NULL,
            headings    TEXT NOT NULL,
            markdown    TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE pages_fts USING fts5(
            title, breadcrumb, headings, markdown,
            content='pages', content_rowid='id'
        );
        """
    )
    for r in records:
        con.execute(
            "INSERT INTO pages (id, title, url, breadcrumb, kind, status, headings, markdown)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                r["id"],
                r["title"],
                r["url"],
                " > ".join(r["breadcrumb"]),
                r["kind"],
                r["status"],
                "\n".join(r["headings"]),
                r["markdown"],
            ),
        )
    con.execute(
        "INSERT INTO pages_fts(rowid, title, breadcrumb, headings, markdown)"
        " SELECT id, title, breadcrumb, headings, markdown FROM pages"
    )
    con.commit()
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data", help="output directory")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--refresh-toc", action="store_true", help="re-fetch the TOC even if cached")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    roots = build_toc(args.refresh_toc, out / "toc.json")
    targets = collect_targets(roots)
    print(f"[crawl] {len(targets)} page targets "
          f"({len({u for _, u, _ in targets})} unique URLs)")

    records: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(fetch_one, n, u, c): (n, u) for n, u, c in targets}
        for fut in as_completed(futures):
            rec = fut.result()
            records.append(rec)
            done += 1
            if done % 25 == 0 or done == len(targets):
                ok = sum(1 for r in records if r["status"] == "ok")
                print(f"  {done}/{len(targets)} fetched, {ok} ok")

    records.sort(key=lambda r: r["id"])
    with (out / "pages.jsonl").open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    build_db(records, out / "handbook.db")

    ok = [r for r in records if r["status"] == "ok"]
    bad = [r for r in records if r["status"] != "ok"]
    empty = [r for r in ok if not r["markdown"].strip() and r["kind"] == "page"]
    total_chars = sum(r["char_count"] if "char_count" in r else len(r["markdown"]) for r in ok)
    print(f"\n[crawl] ok={len(ok)} failed={len(bad)} empty={len(empty)} "
          f"chars={total_chars:,}")
    print(f"[crawl] wrote {out/'toc.json'}, {out/'pages.jsonl'}, {out/'handbook.db'}")
    for r in bad[:20]:
        print(f"   FAILED id={r['id']} {r['title']!r}: {r['status']}")
    for r in empty[:20]:
        print(f"   EMPTY  id={r['id']} {r['title']!r} ({r['url']})")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
