#!/usr/bin/env node
/**
 * Cross-language parity: ingest.js must produce IDENTICAL output to
 * ingest.py on every fixture (everything except captured_at timestamps).
 *
 * Run:  node ingest/tests/test_ingest_js.js
 */
"use strict";
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const PKG = path.join(__dirname, "..");
const FIX = path.join(__dirname, "fixtures");
// env must be set BEFORE require: SESSIONS_DIR is read at module load
const tmp = fs.mkdtempSync(path.join(require("os").tmpdir(), "vu-js-"));
process.env.VU_PASTE_SESSIONS = tmp;
const py = require(path.join(PKG, "ingest.js"));

let pass = 0, fail = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}` + (!ok && detail ? `  [${detail}]` : ""));
  ok ? pass++ : fail++;
}

const fixtures = fs.readdirSync(FIX).sort();
for (const name of fixtures) {
  const raw = fs.readFileSync(path.join(FIX, name), "utf-8");
  const expected = JSON.parse(execFileSync(
    "python3", [path.join(PKG, "ingest.py"), "--no-store", path.join(FIX, name)],
    { encoding: "utf-8" }));
  const { entry } = py.ingest(raw);

  for (const key of ["text", "target", "title", "blocks", "tables", "facts", "stats", "char_counts"]) {
    const a = JSON.stringify(expected[key]);
    const b = JSON.stringify(entry[key]);
    check(`parity ${name}: ${key}`, a === b,
      a === b ? "" : `\n  py: ${a}\n  js: ${b}`);
  }
  check(`parity ${name}: schema`, expected.schema === entry.schema);
}

// JS store round-trip (tmp dir created above)
const raw = fs.readFileSync(path.join(FIX, "gradebook_paste.html"), "utf-8");
const { storedAt } = py.ingest(raw, { session: "js1" });
check("js store: file written", fs.existsSync(storedAt), storedAt);
check("js store: index appended",
  fs.readFileSync(path.join(tmp, "js1", "index.jsonl"), "utf-8").trim().split("\n").length === 1);

console.log("=".repeat(60));
console.log(`${pass}/${pass + fail} parity checks passed`);
if (fail) { console.log("PARITY FAILURES"); process.exit(1); }
console.log("ALL JS PARITY CHECKS PASSED");
