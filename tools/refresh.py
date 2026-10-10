#!/usr/bin/env python3
"""Safe snapshot refresh: recrawl -> gate -> atomic swap.

The live site can change (or break) at any time, so this never overwrites a
working snapshot directly. Instead:

  1. crawl into data/.staging (fresh TOC, all pages)
  2. cheap sanity gates     - file presence, page count, char count
  3. protocol gate          - tests/test_mcp.py (53 checks) against staging
  4. retrieval gate         - tests/eval_queries.py, >= N/12 must land top-3
  5. only then swap         - current files backed up to data/.last-good/,
                              then atomically replaced (os.replace)

Any failing gate keeps data/ untouched, staging is removed, exit code 1.
data/.last-good/ always holds the previous working snapshot (one generation).

Per-file replacement is atomic; the three files are swapped in sequence, so a
reader mid-request may see a sub-millisecond cross-file skew (it holds an open
FD to the old DB inode either way). That is acceptable for a read-only server.

Usage:
    python3 tools/refresh.py                 # full refresh
    python3 tools/refresh.py --skip-crawl    # re-run gates on existing staging
    python3 tools/refresh.py --min-eval 11 --min-pages 300
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STAGING = DATA_DIR / ".staging"
BACKUP = DATA_DIR / ".last-good"
FILES = ("toc.json", "pages.jsonl", "handbook.db")
EVAL_RE = re.compile(r"retrieval:\s*(\d+)/(\d+)")

GATES: list[tuple[str, bool]] = []


def log(msg: str) -> None:
    print(f"[refresh] {msg}", flush=True)


def gate(name: str, ok: bool, detail: str = "") -> bool:
    GATES.append((name, ok))
    print(f"  {'PASS' if ok else 'FAIL'}: {name}" + (f"  [{detail}]" if detail else ""),
          flush=True)
    return ok


def run_streaming(cmd: list[str], env: dict | None = None) -> int:
    log("$ " + " ".join(str(c) for c in cmd))
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"    {line}", end="", flush=True)
    return proc.wait()


def run_capture(cmd: list[str], env: dict | None = None) -> tuple[int, str]:
    log("$ " + " ".join(str(c) for c in cmd))
    p = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    out = (p.stdout or "") + (p.stderr or "")
    tail = "\n".join(out.strip().splitlines()[-6:])
    if tail:
        print("    " + tail.replace("\n", "\n    "), flush=True)
    return p.returncode, out


def abort(reason: str) -> int:
    log(f"ABORTED: {reason}")
    log("data/ left untouched (previous snapshot still live).")
    if not ARGS.keep_staging and STAGING.exists():
        shutil.rmtree(STAGING)
        log("staging removed")
    elif STAGING.exists():
        log(f"staging kept at {STAGING}")
    log("gates: " + ", ".join(f"{'ok' if ok else 'FAILED'} ({n})" for n, ok in GATES))
    return 1


def main() -> int:
    global ARGS, DATA_DIR, STAGING
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DATA_DIR), help="live data directory")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--min-pages", type=int, default=290,
                    help="abort unless staging has at least this many pages")
    ap.add_argument("--min-chars", type=int, default=500_000,
                    help="abort unless staging has at least this many extracted chars")
    ap.add_argument("--min-eval", type=int, default=10,
                    help="abort unless retrieval eval scores at least N/12 in top-3")
    ap.add_argument("--skip-crawl", action="store_true",
                    help="run gates against an existing staging dir (no network)")
    ap.add_argument("--keep-staging", action="store_true",
                    help="keep staging on failure for inspection")
    ARGS = ap.parse_args()

    DATA_DIR = Path(ARGS.out)
    STAGING = DATA_DIR / ".staging"

    # --- 1. crawl to staging ------------------------------------------------
    if not ARGS.skip_crawl:
        if STAGING.exists():
            log("removing leftover staging from a previous run")
            shutil.rmtree(STAGING)
        STAGING.mkdir(parents=True)
        rc = run_streaming(
            [sys.executable, "tools/crawl_handbook.py", "--out", str(STAGING),
             "--refresh-toc", "--workers", str(ARGS.workers)])
        if rc != 0:
            return abort(f"crawl failed (exit {rc}) - at least one page fetch failed")
        log("crawl complete")
    else:
        if not STAGING.exists():
            return abort(f"--skip-crawl but {STAGING} does not exist")
        log("reusing existing staging (--skip-crawl)")

    # --- 2. cheap sanity gates ---------------------------------------------
    log("gates: sanity")
    missing = [f for f in FILES if not (STAGING / f).exists()]
    if not gate("staging files present", not missing, f"missing={missing}"):
        return abort("staging incomplete")

    import sqlite3
    con = sqlite3.connect(STAGING / "handbook.db")
    pages, chars = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(LENGTH(markdown)),0) FROM pages WHERE status='ok'"
    ).fetchone()
    con.close()
    gate(f"pages >= {ARGS.min_pages}", pages >= ARGS.min_pages, f"got {pages}")
    gate(f"chars >= {ARGS.min_chars:,}", chars >= ARGS.min_chars, f"got {chars:,}")

    toc = json.loads((STAGING / "toc.json").read_text(encoding="utf-8"))
    gate("toc non-trivial", isinstance(toc, list) and len(toc) >= 1,
         f"roots={len(toc) if isinstance(toc, list) else '?'}")

    if any(not ok for _, ok in GATES):
        return abort("sanity gate failed")

    # --- 3. protocol gate (53 checks against staging) -----------------------
    log("gates: protocol (tests/test_mcp.py)")
    gate_env = {**os.environ, "VU_HANDBOOK_DATA": str(STAGING)}
    rc, out = run_capture([sys.executable, "tests/test_mcp.py"], env=gate_env)
    m = re.search(r"(\d+)/(\d+) checks passed", out)
    detail = f"{m.group(1)}/{m.group(2)}" if m else f"exit {rc}"
    if not gate("protocol suite passes", rc == 0 and (m is None or m.group(1) == m.group(2)),
                detail):
        return abort("protocol gate failed")

    # --- 4. retrieval gate --------------------------------------------------
    log("gates: retrieval (tests/eval_queries.py)")
    rc, out = run_capture([sys.executable, "tests/eval_queries.py"], env=gate_env)
    m = EVAL_RE.search(out)
    if m:
        hits, total = int(m.group(1)), int(m.group(2))
        ok = rc == 0 and hits >= ARGS.min_eval
        if not gate(f"retrieval >= {ARGS.min_eval}/{total}", ok, f"got {hits}/{total}"):
            return abort(f"retrieval gate failed ({hits}/{total} < {ARGS.min_eval}/{total})")
    else:
        if not gate("retrieval eval produced a score", False, f"exit {rc}"):
            return abort("retrieval gate produced no score")

    # --- 5. backup + atomic swap -------------------------------------------
    log("all gates passed - swapping")
    BACKUP.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        if (DATA_DIR / f).exists():
            shutil.copy2(DATA_DIR / f, BACKUP / f)
    for f in FILES:
        os.replace(STAGING / f, DATA_DIR / f)
    shutil.rmtree(STAGING, ignore_errors=True)

    log(f"snapshot updated: {pages} pages, {chars:,} chars")
    log(f"previous snapshot backed up at {BACKUP}")
    log("gates: " + ", ".join(f"ok ({n})" for n, _ in GATES))
    return 0


if __name__ == "__main__":
    ARGS: argparse.Namespace
    raise SystemExit(main())
