#!/usr/bin/env python3
"""Retrieval quality eval: realistic VU student questions -> expected pages.

Runs against the MCP server over stdio (the same interface agents use).
Set STRICT=1 to fail on any miss.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent

# (question, expected page title, expected breadcrumb fragment)
CASES = [
    ("How do I apply for semester freeze?",
     "Semester Freeze", "Registrar Office"),
    ("Can I use my mobile phone inside the examination hall?",
     "Acts of Unfair Means", "Unfair Means"),
    ("How do I get my paper re-checked?",
     "Re-Checking of Paper(s)", "Examinations Department"),
    ("How do I apply for course exemption?",
     "Procedure to apply for Course Exemption/Transfer", "Registrar Office"),
    ("What are the fee charges for overseas students?",
     "Fee Structure for Overseas Students", "Directorate of Finance"),
    ("How do I download assignment and submit it?",
     "How to Do Assignments", "How to Study at VU"),
    ("What is the university plagiarism policy?",
     "VU Plagiarism Policy", "Home"),
    ("How do I watch lectures?",
     "How to Take Lectures", "How to Study at VU"),
    ("What is the procedure for admission?",
     "Admission Policy and Regulations", "Home"),
    ("How are scholarships awarded?",
     "Merit based Scholarships", "Directorate of Finance"),
    ("How do I get a transcript?",
     "Final Transcript", "Issuance of Documents"),
    ("What marks are required to qualify a course?",
     "General Criteria for Qualifying a Semester", "Examinations Department"),
]


async def main() -> int:
    child_env = get_default_environment()
    if "VU_HANDBOOK_DATA" in os.environ:
        child_env["VU_HANDBOOK_DATA"] = os.environ["VU_HANDBOOK_DATA"]
    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "mcp_server.py")], cwd=str(ROOT),
        env=child_env,
    )
    strict = os.environ.get("STRICT") == "1"
    hits = misses = 0

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for q, expected, crumb in CASES:
                res = await s.call_tool("vu_handbook_search", {"query": q, "limit": 3})
                raw = "\n".join(c.text for c in res.content if getattr(c, "type", "") == "text")
                data = json.loads(raw)
                results = data.get("results", [])
                titles = [x["title"] for x in results]
                top1 = results[0] if results else {}
                ok = expected in titles
                crumb_ok = crumb in (top1.get("breadcrumb") or "")
                # accept a breadcrumb hit when the page itself is present deeper
                if not ok:
                    ok = any(crumb in (x.get("breadcrumb") or "") and
                             expected.lower() in (x.get("title") or "").lower()
                             for x in results)
                if ok:
                    hits += 1
                    flag = "HIT "
                else:
                    misses += 1
                    flag = "MISS"
                print(f"{flag}  {q}")
                print(f"       expected: {expected!r} in {crumb!r}")
                print(f"       top3    : {titles}")
                if ok and not crumb_ok:
                    print(f"       note    : page found but top-1 breadcrumb was {top1.get('breadcrumb')!r}")

    total = hits + misses
    print("\n" + "=" * 64)
    print(f"retrieval: {hits}/{total} expected pages in top-3 ({100*hits/total:.0f}%)")
    if strict and misses:
        print("STRICT mode: FAILING")
        return 1
    return 0


if __name__ == "__main__":
    import anyio

    raise SystemExit(anyio.run(main))
