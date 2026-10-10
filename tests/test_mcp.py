#!/usr/bin/env python3
"""End-to-end test: drive the VU Handbook MCP server over the stdio protocol.

Exercises discovery, navigation, search and retrieval exactly the way an MCP
client (Claude Desktop, LangGraph, a support agent) would.
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
FAILURES: list[str] = []
CHECKS = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}  {detail}")
        FAILURES.append(label)


async def call(s: ClientSession, name: str, args: dict) -> tuple[dict, bool, str]:
    """Return (decoded payload, is_error, raw_text). Never raises."""
    try:
        r = await s.call_tool(name, args)
    except Exception as e:  # noqa: BLE001
        return {}, True, str(e)
    raw = "\n".join(c.text for c in r.content if getattr(c, "type", "") == "text")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {"_raw": raw}
    return payload, bool(r.isError), raw


async def main() -> int:
    # MCP's stdio client sandboxes the child env; forward the data-dir override
    # so gates can run against a staging snapshot (tools/refresh.py).
    child_env = get_default_environment()
    if "VU_HANDBOOK_DATA" in os.environ:
        child_env["VU_HANDBOOK_DATA"] = os.environ["VU_HANDBOOK_DATA"]
    params = StdioServerParameters(
        command=sys.executable, args=[str(ROOT / "mcp_server.py")], cwd=str(ROOT),
        env=child_env,
    )
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # ---- 1. discovery -------------------------------------------
            tools = await s.list_tools()
            names = sorted(t.name for t in tools.tools)
            print("\n[1] tools/list")
            check("6 tools exposed", len(names) == 6, str(names))
            for expected in ("vu_handbook_contents", "vu_handbook_search", "vu_handbook_get",
                             "vu_lms_contents", "vu_lms_search", "vu_lms_get"):
                check(f"tool present: {expected}", expected in names, str(names))
            for t in tools.tools:
                check(f"described: {t.name}", bool(t.description) and len(t.description) > 80)

            res = await s.list_resources()
            rnames = sorted(str(x.uri) for x in res.resources)
            tmpl = await s.list_resource_templates()
            tnames = sorted(str(x.uriTemplate) for x in tmpl.resourceTemplates)
            print("\n[2] resources/list + resources/templates/list")
            check("toc resource", any("://toc" in u for u in rnames), str(rnames))
            check("stats resource", any("stats" in u for u in rnames), str(rnames))
            check("page resource TEMPLATE", any("page/" in u for u in tnames), str(tnames))
            check("lms sections resource", any("vu-lms://sections" in u for u in rnames), str(rnames))
            check("lms guide resource", any("vu-lms://guide" in u for u in rnames), str(rnames))

            # ---- 1b. LMS guide corpus ------------------------------------
            print("\n[1b] LMS guide tools")
            res = await s.call_tool("vu_lms_contents", {})
            data = json.loads(res.content[0].text)
            guide_secs = data["files"].get("VU_LMS_Guide.md", [])
            ops_secs = data["files"].get("OPERATIONAL_NOTES.md", [])
            check("lms contents: both files listed", guide_secs and ops_secs,
                  str(list(data["files"])))
            check("lms contents: >= 15 guide sections", len(guide_secs) >= 15, str(len(guide_secs)))
            check("lms contents: dynamic note present", "DAILY" in data.get("dynamic_note", ""))

            res = await s.call_tool("vu_lms_get", {"section": "Grade Book"})
            data = json.loads(res.content[0].text)
            check("lms get by title", data["section"] == "Grade Book")
            check("lms get: content has real div ids", "StudentGradeBook" in data["content"])

            res = await s.call_tool(
                "vu_lms_get", {"section": "https://vulms.vu.edu.pk/AccountBook/AccountBook.aspx"})
            data = json.loads(res.content[0].text)
            check("lms get by URL", data["section"] == "Account Book", data["section"])

            res = await s.call_tool("vu_lms_get", {"section": "course"})
            check("lms get: ambiguous -> error with candidates", bool(res.isError))

            res = await s.call_tool("vu_lms_get", {"section": "no-such-thing-xyz"})
            check("lms get: unknown -> error", bool(res.isError))

            res = await s.call_tool("vu_lms_search", {"query": "where is semester freeze", "limit": 3})
            data = json.loads(res.content[0].text)
            check("lms search: semester freeze -> Student Services top-3",
                  any(r["title"] == "Student Services" for r in data["results"]),
                  str([r["title"] for r in data["results"]]))

            res = await s.call_tool("vu_lms_search", {"query": "GDB deadline days to attempt"})
            data = json.loads(res.content[0].text)
            check("lms search: GDB windows -> operational notes",
                  any("To Do Calendar" in r["title"] for r in data["results"]),
                  str([r["title"] for r in data["results"]]))

            res = await s.call_tool("vu_lms_search", {"query": "zzzqqqxyz spaceship launch code"})
            data = json.loads(res.content[0].text)
            check("lms search: nonsense -> 0 + escalation note",
                  data["count"] == 0 and bool(data["note"]), str(data["count"]))

            res = await s.read_resource("vu-lms://sections")
            secs = json.loads(res.contents[0].text)
            check("lms sections resource parses", len(secs["sections"]) >= 18,
                  str(len(secs["sections"])))

            # ---- 2. navigation ------------------------------------------
            print("\n[3] vu_handbook_contents()")
            out, err, _ = await call(s, "vu_handbook_contents", {})
            check("no error", not err, _[:200])
            check("source present", out.get("source", "").startswith("Virtual University"), str(out)[:160])
            top = out.get("node", {}).get("children", [])
            check("top-level sections >= 8", len(top) >= 8, f"got {len(top)}")
            titles = [c["title"] for c in top]
            check("Examinations Department present", "Examinations Department" in titles, str(titles))
            check("every top-level child typed", all("type" in c for c in top), str(top[:2]))
            print(f"        top level: {titles}")

            print("\n[4] contents(path='Home > Examinations Department', depth=2)")
            out, err, _ = await call(s, "vu_handbook_contents",
                                     {"path": "Home > Examinations Department", "depth": 2})
            check("resolved node", out.get("node", {}).get("title") == "Examinations Department", str(out)[:200])
            kids = out.get("node", {}).get("children", [])
            check("children returned", len(kids) >= 4, f"got {len(kids)}")
            conduct = next((k for k in kids if k["title"] == "Conduct of Examination"), None)
            check("Conduct of Examination nested", conduct is not None, str([k["title"] for k in kids]))
            check("depth=2 reached grandchildren",
                  isinstance(conduct.get("children"), list) and len(conduct["children"]) > 1,
                  str(conduct.get("children"))[:200] if conduct else "n/a")
            check("no placeholder strings",
                  not any(isinstance(c, str) for k in kids for c in k.get("children", []) or []),
                  str(kids)[:200])

            print("\n[5] contents(path='<node id>')")
            out, err, _ = await call(s, "vu_handbook_contents", {"path": "11", "depth": 1})
            check("numeric id resolves", out.get("node", {}).get("id") == 11, str(out)[:200])

            print("\n[6] unknown path -> error result, not silent success")
            out, err, raw = await call(s, "vu_handbook_contents", {"path": "no-such-branch"})
            check("reports an error", err, f"err={err} raw={raw[:200]}")
            check("structured path_not_found", "path_not_found" in raw, raw[:300])

            # ---- 3. search ------------------------------------------------
            print("\n[7] search: 'deadline semester freeze'")
            out, err, _ = await call(s, "vu_handbook_search",
                                     {"query": "deadline semester freeze", "limit": 5})
            check("no error", not err, str(out)[:200])
            check("results returned", out.get("count", 0) > 0, str(out)[:300])
            r0 = (out.get("results") or [{}])[0]
            check("result has breadcrumb", bool(r0.get("breadcrumb")), str(r0)[:200])
            check("result has id + canonical url",
                  bool(r0.get("id")) and str(r0.get("url", "")).startswith("http"), str(r0)[:200])
            check("snippet present", bool(r0.get("snippet")), str(r0)[:200])
            check("matched terms reported", bool(r0.get("matched_terms")), str(r0)[:200])
            print(f"        top hit: id={r0.get('id')} {r0.get('title')!r} | {r0.get('breadcrumb')}")

            print("\n[8] search: 'using mobile phone in exam is unfair means'")
            out, err, _ = await call(s, "vu_handbook_search",
                                     {"query": "using mobile phone in exam is unfair means", "limit": 5})
            ids = [x["id"] for x in out.get("results", [])]
            check("unfair-means page (id 20) retrieved", 20 in ids, f"ids={ids}")
            print(f"        ids: {ids}")
            for x in out.get("results", [])[:3]:
                print(f"          {x['id']} {x['title']!r} matched={x['matched_terms']}")

            print("\n[9] FTS-hostile query must not error")
            out, err, _ = await call(s, "vu_handbook_search",
                                     {"query": 'fee voucher: (2024) AND "x"* OR {}', "limit": 3})
            check("hostile query handled", (not err) and "results" in out, str(out)[:250])

            print("\n[10] nonsense query -> explicit no-match note")
            out, err, _ = await call(s, "vu_handbook_search",
                                     {"query": "zzzqqqxyz spaceship launch code", "limit": 5})
            check("count 0", out.get("count") == 0, f"count={out.get('count')} "
                  f"titles={[x['title'] for x in out.get('results', [])]}")
            check("escalation note", "Support System" in (out.get("note") or ""), str(out.get("note"))[:180])

            # ---- 4. fetch -------------------------------------------------
            print("\n[11] get by exact title")
            out, err, _ = await call(s, "vu_handbook_get", {"page": "Acts of Unfair Means"})
            check("no error", not err, str(out)[:200])
            check("title resolved", out.get("title") == "Acts of Unfair Means", str(out)[:160])
            check("content present", len(out.get("content", "")) > 400, f"len={len(out.get('content',''))}")
            check("breadcrumb is a list >= 3 deep",
                  isinstance(out.get("breadcrumb"), list) and len(out["breadcrumb"]) >= 3,
                  str(out.get("breadcrumb")))
            check("canonical url", str(out.get("url", "")).startswith("https://handbook.vu.edu.pk/"),
                  str(out.get("url")))
            check("mobile phone covered", "mobile" in out.get("content", "").lower(),
                  out.get("content", "")[:200])
            nav = out.get("navigation", {})
            check("navigation.parent", bool(nav.get("parent")), str(nav)[:200])
            check("navigation.siblings", len(nav.get("siblings", [])) > 0, str(nav)[:200])

            print("\n[12] get by id / URL / int resolve to the same page")
            by_id, _, _ = await call(s, "vu_handbook_get", {"page": 20})
            by_int, _, _ = await call(s, "vu_handbook_get", {"page": 20})
            by_url, _, _ = await call(s, "vu_handbook_get", {"page": out["url"]})
            check("str id == title lookup", by_id.get("id") == out.get("id"), str(by_id.get("id")))
            check("url lookup == title lookup", by_url.get("id") == out.get("id"), str(by_url.get("id")))
            check("int accepted", by_int.get("id") == out.get("id"), str(by_int.get("id")))

            print("\n[13] ambiguous title -> candidates, never a silent wrong page")
            _, err, raw = await call(s, "vu_handbook_get", {"page": "Transcript"})
            check("ambiguous raises", err, f"err={err} raw={raw[:200]}")
            check("offers candidates", "candidates" in raw, raw[:300])

            print("\n[14] PDF attachment fetchable with extracted text")
            out, err, _ = await call(s, "vu_handbook_get", {"page": "VU Plagiarism Policy"})
            check("kind=pdf", out.get("kind") == "pdf", str(out.get("kind")))
            check("pdf text extracted", len(out.get("content", "")) > 1000, f"len={len(out.get('content',''))}")

            print("\n[15] truncation flag is honest")
            out, _, _ = await call(s, "vu_handbook_get", {"page": 1})
            check("small page not truncated", out.get("truncated") is False, str(out.get("truncated")))
            check("content under cap", len(out.get("content", "")) <= 40_000, str(len(out.get("content", ""))))

            # ---- 5. resources --------------------------------------------
            print("\n[16] resources/read")
            rr = await s.read_resource("vu-handbook://stats")
            stats = json.loads(rr.contents[0].text)
            check("stats pages >= 310", stats.get("pages", 0) >= 310, str(stats))
            rr = await s.read_resource("vu-handbook://toc")
            toc = json.loads(rr.contents[0].text)
            check("toc resource shape", isinstance(toc.get("toc"), list) and bool(toc["toc"]), str(toc)[:140])
            rr = await s.read_resource("vu-handbook://page/20")
            check("page resource returns markdown", "Unfair Means" in rr.contents[0].text,
                  str(rr.contents[0].text)[:140])

    print("\n" + "=" * 64)
    print(f"{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    if FAILURES:
        print("FAILED: " + "; ".join(FAILURES))
        return 1
    print("ALL MCP END-TO-END CHECKS PASSED")
    return 0


if __name__ == "__main__":
    import anyio

    raise SystemExit(anyio.run(main))
