#!/usr/bin/env python3
"""End-to-end tests for the Streamable HTTP transport.

Starts ``mcp_server.py --http`` as a real subprocess, then drives it with the
official MCP HTTP client:
  1. health endpoint
  2. single session: initialize, list tools, search/get/contents
  3. 8 concurrent sessions (isolation + shared read-only state)
  4. DNS-rebinding protection: spoofed Host header must be rejected
  5. database is genuinely read-only at the connection level
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from mcp import ClientSession  # noqa: E402
from mcp.client.streamable_http import streamablehttp_client  # noqa: E402

PORT = int(os.environ.get("VU_HTTP_TEST_PORT", "8123"))
BASE = f"http://127.0.0.1:{PORT}"
EXPECTED_TOOLS = {"vu_handbook_contents", "vu_handbook_search", "vu_handbook_get"}

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f"  [{detail}]" if detail and not ok else ""))


def wait_healthy(timeout: float = 15.0) -> bool:
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/healthz", timeout=2) as r:
                if r.status == 200 and json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            time.sleep(0.25)
    return False


async def session_search(query: str) -> tuple[str | None, int]:
    """One full client session: initialize -> search. Returns (session_id, n_results)."""
    async with streamablehttp_client(f"{BASE}/mcp") as (read, write, get_sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("vu_handbook_search", {"query": query, "limit": 5})
            payload = json.loads(res.content[0].text)
            return get_sid(), len(payload.get("results", []))


async def test_single_session() -> None:
    async with streamablehttp_client(f"{BASE}/mcp") as (read, write, get_sid):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            check("http: initialize", init.serverInfo.name == "vu-handbook", init.serverInfo.name)

            tools = await session.list_tools()
            names = {t.name for t in tools.tools}
            check("http: exactly 3 tools", names == EXPECTED_TOOLS, str(names))

            res = await session.call_tool("vu_handbook_search", {"query": "how to submit assignment", "limit": 5})
            data = json.loads(res.content[0].text)
            n = len(data.get("results", []))
            check("http: search returns results", n > 0, f"n={n}")
            top = data["results"][0]
            check("http: search result has breadcrumb+source",
                  "breadcrumb" in top and "source" in data and "snippet" in top)

            page_id = top["id"]
            res = await session.call_tool("vu_handbook_get", {"page": page_id})
            page = json.loads(res.content[0].text)
            check("http: get page",
                  page.get("id") == page_id
                  and len(page.get("content", "")) > 200
                  and "navigation" in page)

            res = await session.call_tool("vu_handbook_contents", {"path": "", "depth": 1})
            toc = json.loads(res.content[0].text)
            kids = toc["node"].get("children", [])
            check("http: contents navigation (root)", len(kids) >= 3, f"kids={len(kids)}")
            check("http: contents breadcrumb+source", bool(toc.get("breadcrumb")) and "source" in toc)

            res = await session.call_tool("vu_handbook_contents", {"path": "no-such-node-xyz", "depth": 1})
            check("http: unknown path returns tool error", bool(res.isError))


async def test_concurrency() -> None:
    queries = [
        "assignment submission deadline",
        "date sheet of examinations",
        "fee payment voucher",
        "course registration maximum load",
        "rechecking of result",
        "VULMS login problem",
        "attendance policy",
        "scholarship eligibility",
    ]
    out = await asyncio.gather(*(session_search(q) for q in queries), return_exceptions=True)
    ok = [r for r in out if isinstance(r, tuple)]
    errs = [r for r in out if isinstance(r, Exception)]
    check("http: 8 concurrent sessions all succeed", len(ok) == 8, f"errors={[str(e)[:120] for e in errs]}")
    sids = [sid for sid, _ in ok]
    real = [s for s in sids if s]
    check("http: concurrent sessions get distinct session ids", len(set(real)) == len(real) == 8,
          f"sids={len(set(real))}/{len(real)}")
    check("http: every concurrent search returned results", all(n > 0 for _, n in ok),
          f"counts={[n for _, n in ok]}")


def test_host_header_rejection() -> None:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "evil", "version": "0"}}})
    with httpx.Client(base_url=BASE, timeout=10) as c:
        # spoofed Host (DNS-rebinding attempt)
        r = c.post("/mcp", content=body, headers={"Content-Type": "application/json",
                                                   "Accept": "application/json, text/event-stream",
                                                   "Host": "evil.example.com"})
        # MCP SDK rejects bad Host with 421 Misdirected Request, bad Origin with 403
        check("http: spoofed Host rejected (421)", r.status_code == 421, f"status={r.status_code}")

        # spoofed Origin from a foreign site
        r = c.post("/mcp", content=body, headers={"Content-Type": "application/json",
                                                   "Accept": "application/json, text/event-stream",
                                                   "Origin": "https://evil.example.com"})
        check("http: foreign Origin rejected (403)", r.status_code == 403, f"status={r.status_code}")

        # legit localhost healthz still fine
        r = c.get("/healthz")
        check("http: healthz reachable", r.status_code == 200 and r.json()["status"] == "ok")

        # unknown path 404s (no accidental catch-all)
        r = c.get("/nope")
        check("http: unknown path 404", r.status_code == 404, f"status={r.status_code}")


def test_db_readonly() -> None:
    import sqlite3
    import mcp_server

    con = mcp_server._db()
    n = con.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    check("db: read query works on read-only connection", n > 300, f"n={n}")
    try:
        con.execute("UPDATE pages SET title='x' WHERE id=1")
        check("db: write blocked", False, "UPDATE succeeded on read-only connection")
    except sqlite3.OperationalError:
        check("db: write blocked", True)
    try:
        con.execute("CREATE TABLE evil(x)")
        check("db: DDL blocked", False, "CREATE succeeded on read-only connection")
    except sqlite3.OperationalError:
        check("db: DDL blocked", True)


async def main() -> int:
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "mcp_server.py", "--http", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )
    try:
        if not wait_healthy():
            out = proc.stdout.read() if proc.stdout else ""
            print("SERVER FAILED TO START:\n", out[:3000])
            check("http: server starts", False, "healthz never became ready")
            return 1
        check("http: server starts", True)

        await test_single_session()
        await test_concurrency()
        test_host_header_rejection()
        test_db_readonly()
        check("http: server still alive after all tests", proc.poll() is None, f"exit={proc.returncode}")
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)

    failed = [r for r in results if not r[1]]
    print("=" * 60)
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name}  {detail}")
        return 1
    print("ALL HTTP TRANSPORT CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
