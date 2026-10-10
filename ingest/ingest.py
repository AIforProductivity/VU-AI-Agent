#!/usr/bin/env python3
"""Paste ingestion for the VU student support system.

The student copies a logged-in VULMS page (READ-ONLY policy: we never touch
credentials) and pastes it here. This module turns that paste into clean,
structured JSON an agent can reason over:

    clean()      -> noise-free text (HTML/ViewState junk, menu boilerplate,
                    mojibake/smart punctuation, whitespace)
    structure()  -> deterministic JSON: text, blocks, tables, lightweight
                    facts (course codes, grades, credits, CGPA, dates)
    store()      -> session-scoped persistence (sessions/ is gitignored --
                    it contains student data)

"Analyze + respond" is deliberately NOT here: that is the agents' job. Every
rule below is mirrored 1:1 in ingest/ingest.js (parity-tested) so JavaScript
clients can pre-clean locally.

CLI:
    python3 ingest.py [--target gradebook] [--session s1] [--url URL] < paste.txt
"""
from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BOILERPLATE_FILE = PACKAGE_DIR / "boilerplate.txt"
SESSIONS_DIR = Path(os.environ.get("VU_PASTE_SESSIONS", PACKAGE_DIR.parent / "sessions"))

SCHEMA = "vu-paste/1"

# ---------------------------------------------------------------------------
# unicode normalization (mirrored in ingest.js)
# ---------------------------------------------------------------------------
_ZERO_WIDTH = {ord(c): None for c in "\u200b\u200c\u200d\ufeff\u00ad"}
_SMART_PUNCT = {0x2018: "'", 0x2019: "'", 0x201c: '"', 0x201d: '"',
                0x2013: "-", 0x2014: "-", 0x2026: "..."}
_CP1252_C1 = {0x80: "\u20ac", 0x82: "\u201a", 0x83: "\u0192", 0x84: "\u201e",
              0x85: "\u2026", 0x86: "\u2020", 0x87: "\u2021", 0x88: "\u02c6",
              0x89: "\u2030", 0x8a: "\u0160", 0x8b: "\u2039", 0x8c: "\u0152",
              0x8e: "\u017d", 0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c",
              0x94: "\u201d", 0x95: "\u2022", 0x96: "\u2013", 0x97: "\u2014",
              0x98: "\u02dc", 0x99: "\u2122", 0x9a: "\u0161", 0x9b: "\u203a",
              0x9c: "\u0153", 0x9e: "\u017e", 0x9f: "\u0178"}
_MOJIBAKE_RE = re.compile("Â([\u0080-\u009f])")

# ---------------------------------------------------------------------------
# HTML -> text (mirrored in ingest.js)
# ---------------------------------------------------------------------------
_HTML_HINT_RE = re.compile(r"<(html|body|div|table|input|span|head|form|h[1-6]|p|li|br)\b", re.I)
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.I | re.S)
_SCRIPT_RE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.I | re.S)
_HIDDEN_FIELD_RE = re.compile(
    r"<input\b[^>]*\bname\s*=\s*[\"']__"
    r"(VIEWSTATE(?:GENERATOR)?|EVENTVALIDATION|EVENTTARGET|EVENTARGUMENT|REQUESTVERIFYTOKEN)"
    r"[\"'][^>]*>",
    re.I,
)
_BR_RE = re.compile(r"<br\s*/?>\s*", re.I)
_CELL_END_RE = re.compile(r"</(?:td|th)>", re.I)
_ROW_BLOCK_END_RE = re.compile(r"</(?:tr|p|div|li|h[1-6]|table|ul|ol|section|form)>\s*", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(text: str) -> str:
    text = _HEAD_RE.sub(" ", text)
    text = _SCRIPT_RE.sub(" ", text)
    text = _HIDDEN_FIELD_RE.sub(" ", text)
    text = _CELL_END_RE.sub("\t", text)
    text = _BR_RE.sub("\n", text)
    text = _ROW_BLOCK_END_RE.sub("\n", text)
    text = _TAG_RE.sub("", text)
    text = _html.unescape(text)  # entities AFTER tags so &lt; can't fake markup
    # HTML has no blank-line semantics (spacing comes from tags), so collapse
    # every blank run in the HTML path; plain-text pastes keep them.
    return re.sub(r"\n\s*\n+", "\n", text)


def _normalize_unicode(text: str) -> str:
    text = _MOJIBAKE_RE.sub(lambda m: _CP1252_C1.get(ord(m.group(1)), m.group(1)), text)
    text = text.translate(_ZERO_WIDTH)
    text = text.translate(_SMART_PUNCT)
    return text.replace("\u00a0", " ")


# ---------------------------------------------------------------------------
# line-level cleaning (mirrored in ingest.js)
# ---------------------------------------------------------------------------
_JUNK_LINE_RE = re.compile(r"^[\s|._*=\-—~•·#>*<+•\u2500-\u257f]+$")
_SPACE_RUN_RE = re.compile(r" {2,}")


def load_boilerplate(path: Path = BOILERPLATE_FILE) -> set[str]:
    if not path.exists():
        return set()
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line.lower())
    return out


def clean(raw: str, boilerplate: set[str] | None = None) -> dict:
    if boilerplate is None:
        boilerplate = load_boilerplate()
    stats = {"input_chars": len(raw), "html": False, "mojibake_fixed": 0,
             "lines_in": 0, "lines_out": 0, "blank_collapsed": 0, "junk_removed": 0,
             "boilerplate_removed": 0, "duplicates_removed": 0}

    stats["mojibake_fixed"] = len(_MOJIBAKE_RE.findall(raw))
    text = raw
    if _HTML_HINT_RE.search(text):
        stats["html"] = True
        text = _html_to_text(text)
    text = _normalize_unicode(text)

    lines = text.split("\n")
    stats["lines_in"] = len(lines)

    out: list[str] = []
    prev = None
    blank_run = 0
    for raw_line in lines:
        line = _SPACE_RUN_RE.sub(" ", raw_line.replace("\u00a0", " ")).strip(" \t")
        if not line:
            blank_run += 1
            if blank_run > 1:
                stats["blank_collapsed"] += 1
                continue
            out.append("")
            continue
        blank_run = 0
        if _JUNK_LINE_RE.match(line):
            stats["junk_removed"] += 1
            continue
        if line.lower() in boilerplate:
            stats["boilerplate_removed"] += 1
            continue
        if line == prev:
            stats["duplicates_removed"] += 1
            continue
        out.append(line)
        prev = line

    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    stats["lines_out"] = len(out)
    return {"text": "\n".join(out), "stats": stats}


# ---------------------------------------------------------------------------
# structuring (mirrored in ingest.js)
# ---------------------------------------------------------------------------
TARGET_KEYWORDS = {
    "gradebook": ["grade book", "gradebook", "dmc", "transcript", "cgpa", "gpa"],
    "course_selection": ["course selection", "improvable", "credit limit", "new courses"],
    "study_scheme": ["study scheme", "scheme of study"],
    "datesheet": ["date sheet", "datesheet", "exam schedule", "rescheduling"],
    "home_courses": ["current registered courses", "registered courses", "my courses"],
    "support": ["support system", "support request"],
    "account_book": ["account book", "challan", "payable"],
}

_COURSE_RE = re.compile(r"\b([A-Z]{2,4}\d{3})\b")
_CREDIT_RE = re.compile(
    r"\b(?:(\d{1,2})\s*Credit(?:\s*\(s\))?"
    r"|Credit(?:\s*\(s\))?\s*(?:Hours?)?\s*[:\-]?\s*(\d{1,2}))\b", re.I)


def _credit_value(m: re.Match) -> int:
    return int(m.group(1) or m.group(2))
_CGPA_RE = re.compile(r"\b(CGPA|GPA)\s*[:\-]?\s*(\d\.\d{1,3})\b")
_DATE_RE = re.compile(
    r"\b(\d{1,2}[-/][A-Za-z]{3,9}[-/]\d{2,4}"
    r"|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}"
    r"|\d{4}[-/]\d{1,2}[-/]\d{1,2}"
    r"|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b")
# grade tokens; lookahead avoids matching inside codes like CS101/DMC/GPA
_GRADE_RE = re.compile(r"(?<![A-Za-z])(?:A\+|A|B\+|B|C\+|C|D|F|W|I)(?![A-Za-z0-9])")
_AMOUNT_RE = re.compile(r"\bRs\.?\s*([\d,]+(?:\.\d{1,2})?)")


def detect_target(text: str) -> str:
    low = text.lower()
    best, best_score = "general", 0
    for target, kws in TARGET_KEYWORDS.items():
        score = sum(low.count(kw) for kw in kws)
        if score > best_score:
            best, best_score = target, score
    return best


def _tables(lines: list[str]) -> list[dict]:
    tables: list[dict] = []
    cur: list[list[str]] = []
    for line in lines + [""]:
        if "\t" in line and line.strip("\t "):
            cells = [c.strip() for c in line.split("\t")]
            cur.append(cells)  # keep empty cells so columns stay aligned
        else:
            if len(cur) >= 1 and all(len(r) >= 2 and any(r) for r in cur):
                tables.append({"rows": cur})
            cur = []
    return tables


def _amount_value(m: re.Match):
    v = float(m.group(1).replace(",", ""))
    return int(v) if v.is_integer() else v


def _facts(lines: list[str]) -> dict:
    courses: dict[str, dict] = {}
    cgpa: list[dict] = []
    dates: list[dict] = []
    credit_mentions: list[dict] = []
    amounts: list[dict] = []
    for line in lines:
        for m in _COURSE_RE.finditer(line):
            entry = courses.setdefault(
                m.group(1),
                {"code": m.group(1), "grade": None, "credits": None, "context": line[:200]})
            g = _GRADE_RE.search(line)
            if g and entry["grade"] is None:
                entry["grade"] = g.group(0)
            c = _CREDIT_RE.search(line)
            if c and entry["credits"] is None:
                entry["credits"] = _credit_value(c)
        c = _CREDIT_RE.search(line)
        if c:
            credit_mentions.append({"value": _credit_value(c), "context": line[:160]})
        for m in _AMOUNT_RE.finditer(line):
            amounts.append({"value": _amount_value(m), "context": line[:160]})
        for m in _CGPA_RE.finditer(line):
            cgpa.append({"label": m.group(1), "value": float(m.group(2)), "context": line[:160]})
        for m in _DATE_RE.finditer(line):
            start = max(0, m.start() - 30)
            dates.append({"value": m.group(1), "context": line[start:m.end() + 30]})
    return {"courses": list(courses.values()), "cgpa": cgpa, "dates": dates,
            "credit_mentions": credit_mentions, "amounts": amounts}


def structure(cleaned_text: str, target: str = "auto", url: str | None = None,
              stats: dict | None = None, raw_chars: int | None = None) -> dict:
    lines = cleaned_text.split("\n")
    nonempty = [l for l in lines if l]
    blocks: list[str] = []
    cur: list[str] = []
    for line in lines + [""]:
        if line:
            cur.append(line)
        elif cur:
            blocks.append("\n".join(cur))
            cur = []
    title = nonempty[0][:120] if nonempty and len(nonempty[0]) <= 120 else None
    return {
        "schema": SCHEMA,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": detect_target(cleaned_text) if target in (None, "", "auto") else target,
        "url": url,
        "title": title,
        "stats": stats or {},
        "char_counts": {"raw": raw_chars, "clean": len(cleaned_text)},
        "text": cleaned_text,
        "blocks": blocks,
        "tables": _tables(lines),
        "facts": _facts(lines),
    }


# ---------------------------------------------------------------------------
# session store (mirrored in ingest.js)
# ---------------------------------------------------------------------------
def store(entry: dict, session: str = "default") -> Path:
    sdir = SESSIONS_DIR / session
    (sdir / "entries").mkdir(parents=True, exist_ok=True)
    n = len(list((sdir / "entries").glob("*.json"))) + 1
    fname = f"{n:04d}.json"
    (sdir / "entries" / fname).write_text(
        json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8")
    with (sdir / "index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"file": fname, "target": entry["target"],
                             "captured_at": entry["captured_at"]}) + "\n")
    return sdir / "entries" / fname


def ingest(raw: str, target: str = "auto", url: str | None = None,
           session: str | None = None) -> tuple[dict, Path | None]:
    cleaned = clean(raw)
    entry = structure(cleaned["text"], target=target, url=url,
                      stats=cleaned["stats"], raw_chars=len(raw))
    path = store(entry, session) if session else None
    return entry, path


def main() -> int:
    ap = argparse.ArgumentParser(description="Clean, structure and store a VULMS paste.")
    ap.add_argument("file", nargs="?", default="-", help="paste file, or - for stdin")
    ap.add_argument("--target", default="auto",
                    choices=["auto", *TARGET_KEYWORDS, "general"])
    ap.add_argument("--url", default=None, help="page URL the paste came from")
    ap.add_argument("--session", default=None,
                    help="store under sessions/<session>/ (contains student data)")
    ap.add_argument("--no-store", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    entry, path = ingest(raw, target=args.target, url=args.url,
                         session=None if args.no_store else args.session)
    if path:
        entry["stored_at"] = str(path)
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
