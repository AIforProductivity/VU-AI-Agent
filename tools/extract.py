"""Convert legacy handbook HTML into clean, LLM-friendly Markdown.

The handbook pages are circa-2003 FrontPage-era HTML: windows-1252 bytes,
<table> based section headers, <font> tags, and invalid nesting such as a
block-level <table> wrapped in <b> or a <ul> inside a <p>. Browsers recover
from that by implicitly closing <p>; html.parser does not, so we walk the tree
in document order and flush paragraph text whenever a block element appears.

Text nodes are concatenated *without* a separator and only then whitespace-
collapsed, so words split across inline tags stay joined.
"""
from __future__ import annotations

import codecs
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

_HEADER_BG = {"#c0c0c0", "#dcdcdc", "#e8e8e8", "#cccccc"}
_WS = re.compile(r"\s+")
_MULTI_NL = re.compile(r"\n{3,}")
_BLOCK_SKIP = {"script", "style", "noscript"}

# Word/FrontPage export leftovers that survive extraction as literal text.
# "if !supportLists1. endifStudents" must become "1. Students".
_SUPPORTLISTS = re.compile(r"if !supportLists\s*(\S*)\s*endif\s*", re.I)
# Escaped markup that leaked into the source HTML as text.
_RESIDUAL_TAG = re.compile(
    r"</?(?:table|tbody|thead|tr|td|th|p|div|span|font|b|i|u|a|ol|ul|li|br)\b[^>]*>",
    re.I,
)
_INLINE = {"b", "strong", "i", "em", "u", "span", "font", "a", "s", "strike",
           "small", "sup", "sub", "abbr", "code"}
_CONTAINER = {"html", "body", "div", "center", "section", "article", "main",
              "form", "font"}  # font: sometimes used as a wrapper
_PARAGRAPH = {"p", "pre", "blockquote", "dd", "dt", "caption", "legend", "td", "th"}
_LIST = {"ul", "ol"}
_HEADING = {"h1", "h2", "h3", "h4", "h5", "h6"}


# CP1252 interpretation of the C1 control range (0x80-0x9F).
_CP1252_CTRL = {
    0x80: "\u20ac", 0x82: "\u201a", 0x83: "\u0192", 0x84: "\u201e",
    0x85: "\u2026", 0x86: "\u2020", 0x87: "\u2021", 0x88: "\u02c6",
    0x89: "\u2030", 0x8A: "\u0160", 0x8B: "\u2039", 0x8C: "\u0152",
    0x8E: "\u017d", 0x91: "\u2018", 0x92: "\u2019", 0x93: "\u201c",
    0x94: "\u201d", 0x95: "\u2022", 0x96: "\u2013", 0x97: "\u2014",
    0x98: "\u02dc", 0x99: "\u2122", 0x9A: "\u0161", 0x9B: "\u203a",
    0x9C: "\u0153", 0x9E: "\u017e", 0x9F: "\u0178",
}


def _looks_utf16(data: bytes) -> str | None:
    """Detect BOM-less UTF-16 by the density of NUL bytes."""
    sample = data[:4096]
    if len(sample) < 8:
        return None
    return "utf-16-le" if sample.count(b"\x00") > len(sample) // 4 else None


def decode_page(data: bytes) -> str:
    """Decode a handbook page correctly despite mixed source encodings.

    Three encodings appear in the corpus:

    * raw windows-1252 (most prose pages, declaring ``windows-1252``);
    * UTF-8 carrying smart quotes that were produced by latin-1-decoding
      CP1252, leaving C1 controls (U+0080-U+009F) - while still *declaring*
      windows-1252, so honouring the declared charset double-mangles them
      into "Â" + punctuation;
    * UTF-16LE with a BOM (the Course Selection programme pages).

    Letting BeautifulSoup trust the meta charset handles none of these
    correctly, so we detect encoding ourselves and then map any surviving C1
    controls to their CP1252 glyphs.
    """
    text: str | None = None
    if data.startswith(codecs.BOM_UTF32_LE) or data.startswith(codecs.BOM_UTF32_BE):
        text = data.decode("utf-32", errors="replace")
    elif data.startswith(codecs.BOM_UTF16_LE) or data.startswith(codecs.BOM_UTF16_BE):
        text = data.decode("utf-16", errors="replace")
    elif data.startswith(codecs.BOM_UTF8):
        text = data.decode("utf-8-sig", errors="replace")

    if text is None:
        enc = _looks_utf16(data)
        if enc:
            try:
                text = data.decode(enc)
            except UnicodeDecodeError:
                text = None
        if text is None:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("cp1252", errors="replace")

    if any("\x80" <= ch <= "\x9f" for ch in text):
        text = "".join(_CP1252_CTRL.get(ord(ch), ch) for ch in text)
    return text


def _clean(text: str) -> str:
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


def _is_section_header(table: Tag) -> bool:
    """Detect the one-cell grey table the handbook uses as a section heading."""
    cells = table.find_all("td")
    if not cells or len(cells) > 3:
        return False
    text = _clean(table.get_text(" "))
    if not text or len(text) > 160:
        return False
    bg = (cells[0].get("bgcolor") or "").lower()
    if bg in _HEADER_BG:
        return True
    return (
        not bg
        and cells[0].find("b") is not None
        and cells[0].find("table") is None
        and len(text) < 80
    )


def _table_rows(table: Tag) -> list[str]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append("| " + " | ".join(cells) + " |")
    return rows


def extract(content: bytes, page_url: str) -> dict:
    """Return a page record: title, markdown body, headings and outbound links."""
    soup = BeautifulSoup(decode_page(content), "html.parser")

    title = _clean(soup.title.get_text()) if soup.title else ""
    for tag in soup.find_all(list(_BLOCK_SKIP)):
        tag.decompose()

    # Promote grey section-header tables to real headings before rendering.
    for table in list(soup.find_all("table")):
        if _is_section_header(table):
            h = soup.new_tag("h2")
            h.string = _clean(table.get_text(" "))
            table.replace_with(h)

    out: list[str] = []
    headings: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            text = _clean("".join(buf))
            if text:
                out.append(text)
            buf.clear()

    def walk(node: Tag) -> None:
        for child in node.children:
            if isinstance(child, NavigableString):
                buf.append(str(child))
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name

            if name == "br":
                buf.append("\n")
            elif name == "table":
                flush()
                rows = _table_rows(child)
                if rows:
                    out.append("\n".join(rows))
            elif name in _LIST:
                flush()
                items = []
                for li in child.find_all("li", recursive=False):
                    local: list[str] = []
                    _collect_inline(li, local)
                    text = _clean("".join(local))
                    if text:
                        items.append(f"- {text}")
                if items:
                    out.append("\n".join(items))
                flush()
            elif name in _HEADING:
                flush()
                text = _clean(child.get_text(" "))
                if text:
                    out.append(f"{'#' * int(name[1])} {text}")
                    headings.append(text)
            elif name in _PARAGRAPH:
                flush()
                walk(child)
                flush()
            elif name in _CONTAINER or name in _INLINE:
                walk(child)
            else:
                flush()
                walk(child)
                flush()

    def _collect_inline(node: Tag, acc: list[str]) -> None:
        """Gather only inline text of an <li>, skipping nested blocks."""
        for child in node.children:
            if isinstance(child, NavigableString):
                acc.append(str(child))
            elif isinstance(child, Tag):
                if child.name in _LIST:
                    for li in child.find_all("li", recursive=False):
                        acc.append(" ")
                        _collect_inline(li, acc)
                elif child.name == "table":
                    continue
                elif child.name in _HEADING:
                    acc.append(_clean(child.get_text(" ")))
                else:
                    _collect_inline(child, acc)

    body = soup.body or soup
    walk(body)
    flush()

    links = []
    for a in body.find_all("a"):
        href = a.get("href") or ""
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        text = _clean(a.get_text(" "))
        if text:
            links.append({"text": text, "url": urljoin(page_url, href)})

    md = "\n\n".join(out)
    md = _SUPPORTLISTS.sub(r"\1 ", md)
    md = _RESIDUAL_TAG.sub(" ", md)
    md = re.sub(r"[ \t]{2,}", " ", md)
    md = _MULTI_NL.sub("\n\n", md).strip()
    if not title:
        title = headings[0] if headings else (out[0].strip() if out else "")

    return {
        "title": title,
        "markdown": md,
        "headings": headings,
        "links": links,
        "char_count": len(md),
    }
