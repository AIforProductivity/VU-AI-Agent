#!/usr/bin/env node
/**
 * Paste ingestion for the VU student support system — JavaScript twin of
 * ingest/ingest.py (parity-tested against it in tests/test_ingest_js.js).
 *
 *   clean(text)      -> { text, stats }
 *   structure(text)  -> vu-paste/1 JSON entry
 *   ingest(raw, opts)-> clean + structure (+ store when opts.session set)
 *
 * CLI:
 *   node ingest.js [--target gradebook] [--session s1] [--url URL] [--no-store] [file|-]
 */
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");

const PACKAGE_DIR = __dirname;
const BOILERPLATE_FILE = path.join(PACKAGE_DIR, "boilerplate.txt");
const SESSIONS_DIR = process.env.VU_PASTE_SESSIONS || path.join(PACKAGE_DIR, "..", "sessions");
const SCHEMA = "vu-paste/1";

/* ---------------- unicode normalization ---------------- */
const ZERO_WIDTH_RE = /[\u200b\u200c\u200d\ufeff\u00ad]/g;
const MOJIBAKE_RE = /Â([\u0080-\u009f])/g;
const SMART_PUNCT = {
  "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
  "\u2013": "-", "\u2014": "-", "\u2026": "...",
};
const CP1252_C1 = {
  "\u0080": "\u20ac", "\u0082": "\u201a", "\u0083": "\u0192", "\u0084": "\u201e",
  "\u0085": "\u2026", "\u0086": "\u2020", "\u0087": "\u2021", "\u0088": "\u02c6",
  "\u0089": "\u2030", "\u008a": "\u0160", "\u008b": "\u2039", "\u008c": "\u0152",
  "\u008e": "\u017d", "\u0091": "\u2018", "\u0092": "\u2019", "\u0093": "\u201c",
  "\u0094": "\u201d", "\u0095": "\u2022", "\u0096": "\u2013", "\u0097": "\u2014",
  "\u0098": "\u02dc", "\u0099": "\u2122", "\u009a": "\u0161", "\u009b": "\u203a",
  "\u009c": "\u0153", "\u009e": "\u017e", "\u009f": "\u0178",
};
const NAMED_ENTITIES = {
  "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'",
  "&nbsp;": " ", "&#39;": "'", "&rsquo;": "'", "&lsquo;": "'",
  "&rdquo;": '"', "&ldquo;": '"', "&mdash": "\u2014", "&ndash;": "\u2013",
  "&hellip;": "\u2026", "&bull;": "\u2022",
};

function unescapeEntities(text) {
  return text
    .replace(/&#(\d+);?/g, (_, d) => String.fromCodePoint(parseInt(d, 10)))
    .replace(/&[a-zA-Z]+;?/g, (m) => NAMED_ENTITIES[m] ?? NAMED_ENTITIES[m + ";"] ?? m);
}

function normalizeUnicode(text) {
  text = text.replace(MOJIBAKE_RE, (m, c) => CP1252_C1[c] ?? c);
  text = text.replace(ZERO_WIDTH_RE, "");
  for (const [k, v] of Object.entries(SMART_PUNCT)) text = text.split(k).join(v);
  return text.replace(/\u00a0/g, " ");
}

/* ---------------- HTML -> text ---------------- */
const HTML_HINT_RE = /<(html|body|div|table|input|span|head|form|h[1-6]|p|li|br)\b/i;
const HEAD_RE = /<head\b[^>]*>[\s\S]*?<\/head>/gi;
const SCRIPT_RE = /<(script|style|noscript)\b[^>]*>[\s\S]*?<\/\1>/gi;
const HIDDEN_FIELD_RE =
  /<input\b[^>]*\bname\s*=\s*["']__(VIEWSTATE(?:GENERATOR)?|EVENTVALIDATION|EVENTTARGET|EVENTARGUMENT|REQUESTVERIFYTOKEN)["'][^>]*>/gi;
const BR_RE = /<br\s*\/?>\s*/gi;
const CELL_END_RE = /<\/(?:td|th)>/gi;
const ROW_BLOCK_END_RE = /<\/(?:tr|p|div|li|h[1-6]|table|ul|ol|section|form)>\s*/gi;
const TAG_RE = /<[^>]+>/g;

function htmlToText(text) {
  text = text.replace(HEAD_RE, " ");
  text = text.replace(SCRIPT_RE, " ");
  text = text.replace(HIDDEN_FIELD_RE, " ");
  text = text.replace(CELL_END_RE, "\t");
  text = text.replace(BR_RE, "\n");
  text = text.replace(ROW_BLOCK_END_RE, "\n");
  text = text.replace(TAG_RE, "");
  text = unescapeEntities(text);
  // HTML has no blank-line semantics; collapse blank runs (parity with .py)
  return text.replace(/\n\s*\n+/g, "\n");
}

/* ---------------- line-level cleaning ---------------- */
const JUNK_LINE_RE = /^[\s|._*=\-—~•·#>*<+•\u2500-\u257f]+$/;
const SPACE_RUN_RE = / {2,}/g;

function loadBoilerplate(file = BOILERPLATE_FILE) {
  if (!fs.existsSync(file)) return new Set();
  return new Set(
    fs.readFileSync(file, "utf-8")
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith("#"))
      .map((l) => l.toLowerCase())
  );
}

function clean(raw, boilerplate = null) {
  const bp = boilerplate ?? loadBoilerplate();
  const stats = {
    input_chars: raw.length, html: false, mojibake_fixed: 0,
    lines_in: 0, lines_out: 0, blank_collapsed: 0, junk_removed: 0,
    boilerplate_removed: 0, duplicates_removed: 0,
  };

  stats.mojibake_fixed = (raw.match(/Â[\u0080-\u009f]/g) ?? []).length;
  let text = raw;
  if (HTML_HINT_RE.test(text)) {
    stats.html = true;
    text = htmlToText(text);
  }
  text = normalizeUnicode(text);

  const lines = text.split("\n");
  stats.lines_in = lines.length;

  const out = [];
  let prev = null;
  let blankRun = 0;
  for (const rawLine of lines) {
    const line = rawLine.replace(/\u00a0/g, " ").replace(SPACE_RUN_RE, " ").replace(/^[ \t]+|[ \t]+$/g, "");
    if (!line) {
      blankRun += 1;
      if (blankRun > 1) { stats.blank_collapsed += 1; continue; }
      out.push("");
      continue;
    }
    blankRun = 0;
    if (JUNK_LINE_RE.test(line)) { stats.junk_removed += 1; continue; }
    if (bp.has(line.toLowerCase())) { stats.boilerplate_removed += 1; continue; }
    if (line === prev) { stats.duplicates_removed += 1; continue; }
    out.push(line);
    prev = line;
  }
  while (out.length && out[0] === "") out.shift();
  while (out.length && out[out.length - 1] === "") out.pop();
  stats.lines_out = out.length;
  return { text: out.join("\n"), stats };
}

/* ---------------- structuring ---------------- */
const TARGET_KEYWORDS = {
  gradebook: ["grade book", "gradebook", "dmc", "transcript", "cgpa", "gpa"],
  course_selection: ["course selection", "improvable", "credit limit", "new courses"],
  study_scheme: ["study scheme", "scheme of study"],
  datesheet: ["date sheet", "datesheet", "exam schedule", "rescheduling"],
  home_courses: ["current registered courses", "registered courses", "my courses"],
  support: ["support system", "support request"],
  account_book: ["account book", "challan", "payable"],
};

const COURSE_RE = /\b([A-Z]{2,4}\d{3})\b/g;
const COURSE_RE_ONE = /\b([A-Z]{2,4}\d{3})\b/;
const CREDIT_RE = /\b(?:(\d{1,2})\s*Credit(?:\s*\(s\))?|Credit(?:\s*\(s\))?\s*(?:Hours?)?\s*[:\-]?\s*(\d{1,2}))\b/gi;
const CGPA_RE = /\b(CGPA|GPA)\s*[:\-]?\s*(\d\.\d{1,3})\b/g;
const DATE_RE = /\b(\d{1,2}[-\/][A-Za-z]{3,9}[-\/]\d{2,4}|\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4}|\d{4}[-\/]\d{1,2}[-\/]\d{1,2}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\b/g;
const GRADE_RE = /(?<![A-Za-z])(?:A\+|A|B\+|B|C\+|C|D|F|W|I)(?![A-Za-z0-9])/g;
const AMOUNT_RE = /\bRs\.?\s*([\d,]+(?:\.\d{1,2})?)/g;

function detectTarget(text) {
  const low = text.toLowerCase();
  let best = "general", bestScore = 0;
  for (const [target, kws] of Object.entries(TARGET_KEYWORDS)) {
    let score = 0;
    for (const kw of kws) score += low.split(kw).length - 1;
    if (score > bestScore) { best = target; bestScore = score; }
  }
  return best;
}

function tablesOf(lines) {
  const tables = [];
  let cur = [];
  for (const line of [...lines, ""]) {
    if (line.includes("\t") && line.replace(/[\t ]/g, "").length) {
      const cells = line.split("\t").map((c) => c.trim());
      cur.push(cells); // keep empty cells so columns stay aligned (parity with .py)
    } else {
      if (cur.length >= 1 && cur.every((r) => r.length >= 2 && r.some((c) => c))) tables.push({ rows: cur });
      cur = [];
    }
  }
  return tables;
}

function amountValue(m) {
  const v = parseFloat(m[1].replace(/,/g, ""));
  return Number.isInteger(v) ? v : v;
}

function factsOf(lines) {
  const courses = new Map();
  const cgpa = [], dates = [], creditMentions = [], amounts = [];
  for (const line of lines) {
    for (const m of line.matchAll(COURSE_RE)) {
      if (!courses.has(m[1])) courses.set(m[1], { code: m[1], grade: null, credits: null, context: line.slice(0, 200) });
      const entry = courses.get(m[1]);
      GRADE_RE.lastIndex = 0;
      const g = GRADE_RE.exec(line);
      if (g && entry.grade === null) entry.grade = g[0];
      CREDIT_RE.lastIndex = 0;
      const c = CREDIT_RE.exec(line);
      if (c && entry.credits === null) entry.credits = parseInt(c[1] ?? c[2], 10);
    }
    CREDIT_RE.lastIndex = 0;
    const c = CREDIT_RE.exec(line);
    if (c) creditMentions.push({ value: parseInt(c[1] ?? c[2], 10), context: line.slice(0, 160) });
    for (const m of line.matchAll(AMOUNT_RE)) {
      amounts.push({ value: amountValue(m), context: line.slice(0, 160) });
    }
    for (const m of line.matchAll(CGPA_RE)) {
      cgpa.push({ label: m[1], value: parseFloat(m[2]), context: line.slice(0, 160) });
    }
    for (const m of line.matchAll(DATE_RE)) {
      const start = Math.max(0, m.index - 30);
      dates.push({ value: m[1], context: line.slice(start, m.index + m[0].length + 30) });
    }
  }
  return {
    courses: [...courses.values()],
    cgpa,
    dates,
    credit_mentions: creditMentions,
    amounts,
  };
}

function structure(cleanedText, { target = "auto", url = null, stats = {}, rawChars = null } = {}) {
  const lines = cleanedText.split("\n");
  const nonempty = lines.filter((l) => l);
  const blocks = [];
  let cur = [];
  for (const line of [...lines, ""]) {
    if (line) cur.push(line);
    else if (cur.length) { blocks.push(cur.join("\n")); cur = []; }
  }
  const title = nonempty.length && nonempty[0].length <= 120 ? nonempty[0].slice(0, 120) : null;
  return {
    schema: SCHEMA,
    captured_at: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00").replace("T", "T"),
    target: target === "auto" || !target ? detectTarget(cleanedText) : target,
    url,
    title,
    stats,
    char_counts: { raw: rawChars, clean: cleanedText.length },
    text: cleanedText,
    blocks,
    tables: tablesOf(lines),
    facts: factsOf(lines),
  };
}

/* ---------------- session store ---------------- */
function store(entry, session = "default") {
  const sdir = path.join(SESSIONS_DIR, session);
  const entriesDir = path.join(sdir, "entries");
  fs.mkdirSync(entriesDir, { recursive: true });
  const n = fs.readdirSync(entriesDir).filter((f) => f.endsWith(".json")).length + 1;
  const fname = String(n).padStart(4, "0") + ".json";
  fs.writeFileSync(path.join(entriesDir, fname), JSON.stringify(entry, null, 2), "utf-8");
  fs.appendFileSync(path.join(sdir, "index.jsonl"),
    JSON.stringify({ file: fname, target: entry.target, captured_at: entry.captured_at }) + "\n", "utf-8");
  return path.join(entriesDir, fname);
}

function ingest(raw, { target = "auto", url = null, session = null } = {}) {
  const { text, stats } = clean(raw);
  const entry = structure(text, { target, url, stats, rawChars: raw.length });
  const storedAt = session ? store(entry, session) : null;
  return { entry, storedAt };
}

/* ---------------- CLI ---------------- */
function main(argv) {
  const opts = { target: "auto", url: null, session: null };
  let file = "-";
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--target") opts.target = argv[++i];
    else if (a === "--url") opts.url = argv[++i];
    else if (a === "--session") opts.session = argv[++i];
    else if (a === "--no-store") opts.session = null;
    else if (!a.startsWith("--")) file = a;
  }
  const raw = file === "-" ? fs.readFileSync(0, "utf-8") : fs.readFileSync(file, "utf-8");
  const { entry, storedAt } = ingest(raw, opts);
  if (storedAt) entry.stored_at = storedAt;
  process.stdout.write(JSON.stringify(entry, null, 2) + "\n");
  return 0;
}

if (require.main === module) process.exit(main(process.argv.slice(2)));

module.exports = { clean, structure, ingest, store, detectTarget, loadBoilerplate, TARGET_KEYWORDS, SCHEMA };
