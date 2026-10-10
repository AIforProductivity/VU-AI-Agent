#!/usr/bin/env python3
"""Tests for the paste ingestion pipeline (ingest/ingest.py).

Fixtures are SYNTHETIC pastes that imitate VULMS copy-paste junk; replace or
extend them with real (sanitized) pastes to calibrate the cleaner.

Run:  python3 ingest/tests/test_ingest.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(PKG))
import ingest as ig  # noqa: E402

COURSE_RE = re.compile(r"\b([A-Z]{2,4}\d{3})\b")
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f"  [{detail}]" if detail and not ok else ""))


def no_loss(raw: str, cleaned: str, label: str) -> None:
    """Every course code in the raw paste must survive cleaning."""
    codes = set(COURSE_RE.findall(raw))
    missing = [c for c in codes if c not in cleaned]
    check(f"{label}: no course codes lost", not missing, f"missing={missing}")


def test_gradebook() -> None:
    raw = (FIX / "gradebook_paste.html").read_text(encoding="utf-8")
    c = ig.clean(raw)
    t = c["text"]
    check("gradebook: ViewState gone", "__VIEWSTATE" not in t and "AbCdEf" not in t)
    check("gradebook: head/style/script gone", "<script" not in t and "color:red" not in t and "<title" not in t)
    check("gradebook: menu boilerplate dropped", "My VULMS" not in t and "Logout" not in t)
    check("gradebook: html entities decoded", "Business & Technical English" in t
          and "student's record is final & official." in t)
    check("gradebook: table rows kept as tab-separated", "CS101\tIntroduction to Computing\t85\tA+\t4.00" in t)
    no_loss(raw, t, "gradebook")
    e = ig.structure(t, stats=c["stats"])
    check("gradebook: target detected", e["target"] == "gradebook", e["target"])
    courses = {c["code"]: c for c in e["facts"]["courses"]}
    check("gradebook: course codes found", set(courses) == {"CS101", "MTH301", "ENG201"}, str(set(courses)))
    check("gradebook: grades extracted", courses["CS101"]["grade"] == "A+"
          and courses["MTH301"]["grade"] == "B" and courses["ENG201"]["grade"] == "A",
          str({k: v["grade"] for k, v in courses.items()}))
    check("gradebook: cgpa extracted", e["facts"]["cgpa"]
          and e["facts"]["cgpa"][0]["value"] == 3.42, str(e["facts"]["cgpa"]))
    check("gradebook: credit mention found", any(m["value"] == 9 for m in e["facts"]["credit_mentions"]))
    check("gradebook: one table parsed", len(e["tables"]) == 1
          and e["tables"][0]["rows"][0][:2] == ["Course Code", "Course Title"])
    # exact golden for the cleaned text (determinism guard)
    golden = "\n".join([
        "Welcome, Ali Khan (BC230101234)",
        "Student Grade Book",
        "Course Code\tCourse Title\tMarks\tGrade\tGrade Point",
        "CS101\tIntroduction to Computing\t85\tA+\t4.00",
        "MTH301\tBusiness Mathematics\t62\tB\t3.00",
        "ENG201\tBusiness & Technical English\t71\tA\t4.00",
        "CGPA: 3.42",
        "Total Credits Earned: 9 Credit(s)",
        "The student's record is final & official.",
    ])
    check("gradebook: exact cleaned output", t == golden,
          "\n--- got ---\n" + t + "\n--- want ---\n" + golden)


def test_course_selection() -> None:
    raw = (FIX / "course_selection.txt").read_text(encoding="utf-8")
    c = ig.clean(raw)
    e = ig.structure(c["text"], stats=c["stats"])
    check("courseselection: target detected", e["target"] == "course_selection", e["target"])
    courses = {x["code"]: x for x in e["facts"]["courses"]}
    check("courseselection: codes found", set(courses) == {"CS201", "MGT101", "MTH301"}, str(set(courses)))
    check("courseselection: F grade on failed course", courses["MTH301"]["grade"] == "F",
          str(courses["MTH301"]))
    check("courseselection: credits per course", courses["CS201"]["credits"] == 3
          and courses["MTH301"]["credits"] == 3)
    check("courseselection: credit limits captured", any(m["value"] == 18 for m in e["facts"]["credit_mentions"])
          and any(m["value"] == 9 for m in e["facts"]["credit_mentions"]))
    check("courseselection: section tables parsed", len(e["tables"]) == 2, str(len(e["tables"])))
    no_loss(raw, c["text"], "courseselection")


def test_study_scheme() -> None:
    raw = (FIX / "study_scheme.txt").read_text(encoding="utf-8")
    c = ig.clean(raw)
    e = ig.structure(c["text"], stats=c["stats"])
    check("studyscheme: target detected", e["target"] == "study_scheme", e["target"])
    check("studyscheme: tab table kept", len(e["tables"]) == 1
          and e["tables"][0]["rows"][1] == ["1", "CS101", "Introduction to Computing", "3"],
          str(e["tables"]))
    check("studyscheme: codes found", {x["code"] for x in e["facts"]["courses"]} == {"CS101", "CS201", "MTH301"})
    no_loss(raw, c["text"], "studyscheme")


def test_home_courses() -> None:
    raw = (FIX / "home_courses.txt").read_text(encoding="utf-8")
    c = ig.clean(raw)
    t = c["text"]
    check("homecourses: duplicate line collapsed", t.count("CS101 - Introduction to Computing") == 1,
          str(t.count("CS101 - Introduction to Computing")))
    check("homecourses: boilerplate dropped", "My VULMS" not in t and "Logout" not in t)
    check("homecourses: mojibake repaired", '"PASSED"' in t and "Â" not in t, t[-40:])
    check("homecourses: stats count removals", c["stats"]["duplicates_removed"] == 1
          and c["stats"]["boilerplate_removed"] == 2
          and c["stats"]["mojibake_fixed"] == 2, str(c["stats"]))
    e = ig.structure(t, stats=c["stats"])
    check("homecourses: target detected", e["target"] == "home_courses", e["target"])
    no_loss(raw, t, "homecourses")


def test_datesheet() -> None:
    raw = (FIX / "datesheet.txt").read_text(encoding="utf-8")
    c = ig.clean(raw)
    t = c["text"]
    check("datesheet: smart punctuation folded", '"Creation" window' in t and "12-16 days" in t,
          t.splitlines()[1] if len(t.splitlines()) > 1 else t)
    e = ig.structure(t, stats=c["stats"])
    check("datesheet: target detected", e["target"] == "datesheet", e["target"])
    values = [d["value"] for d in e["facts"]["dates"]]
    check("datesheet: all 3 parseable dates captured", len(values) >= 3, str(values))
    check("datesheet: mixed formats", "15-02-2026" in values and "05/03/2026" in values
          and any(v.startswith("February") for v in values), str(values))


def test_cli_and_store() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "VU_PASTE_SESSIONS": tmp}
        r = subprocess.run([sys.executable, str(PKG / "ingest.py"),
                            "--session", "t1", str(FIX / "gradebook_paste.html")],
                           capture_output=True, text=True, env=env)
        check("cli: exit 0", r.returncode == 0, r.stderr[-200:])
        entry = json.loads(r.stdout)
        check("cli: prints vu-paste/1 json", entry["schema"] == "vu-paste/1")
        check("cli: stored", (Path(tmp) / "t1" / "entries" / "0001.json").exists())
        r2 = subprocess.run([sys.executable, str(PKG / "ingest.py"),
                             "--session", "t1", str(FIX / "datesheet.txt")],
                            capture_output=True, text=True, env=env)
        check("cli: second store numbers 0002", (Path(tmp) / "t1" / "entries" / "0002.json").exists())
        idx = (Path(tmp) / "t1" / "index.jsonl").read_text().splitlines()
        check("cli: index appended", len(idx) == 2, str(len(idx)))


def main() -> int:
    test_gradebook()
    test_course_selection()
    test_study_scheme()
    test_home_courses()
    test_datesheet()
    test_cli_and_store()
    failed = [r for r in results if not r[1]]
    print("=" * 60)
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        for name, _, detail in failed:
            print(f"  FAILED: {name}  {detail}")
        return 1
    print("ALL INGEST CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
