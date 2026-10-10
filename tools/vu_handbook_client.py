"""HTTP client for the Virtual University of Pakistan Student Handbook.

handbook.vu.edu.pk serves an HTML-frameset site:

    /                          -> frameset (Header.aspx | Menu.aspx | DefaultMain.aspx)
    /Menu.aspx                 -> ASP.NET TreeView ("PermissionTree") holding the full TOC
    /HandBook_Pages/*.htm      -> individual handbook pages

The TOC is only partially rendered on the first load: collapsed branches are
hydrated by an ASP.NET postback (__doPostBack('PermissionTree', 't<path>')).
Once every branch has been expanded, the server switches the tree to
client-side rendering, which inlines *all* nodes. This module performs those
postbacks and then parses the final render into a nested tree.

The site presents an invalid TLS certificate, so verification is disabled.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from html import unescape
from time import sleep
from urllib.parse import urljoin

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

BASE_URL = "https://handbook.vu.edu.pk/"
MENU_URL = urljoin(BASE_URL, "Menu.aspx")

# A collapsed branch: href="javascript:__doPostBack('PermissionTree','t<path>')"
# immediately followed by alt="Expand <title>".
_TOGGLE_RE = re.compile(
    r'href="javascript:__doPostBack\(&#39;PermissionTree&#39;,&#39;t(?P<path>[^&]*?)&#39;\)"'
    r'.*?alt="(?P<alt>(?:Expand|Collapse) [^"]*)"',
    re.S,
)

_TOKEN_RE = re.compile(
    r'<div[^>]*\bid="PermissionTreen(?P<idx>\d+)Nodes"[^>]*>'
    r'|</div>'
    r'|<a[^>]*\bid="PermissionTreet(?P<tid>\d+)"[^>]*>(?P<title>.*?)</a>',
    re.S,
)
_HREF_RE = re.compile(r'\bhref="([^"]*)"')
_CLASS_RE = re.compile(r'\bclass="([^"]*)"')
_HIDDEN_RE = re.compile(
    r'<input type="hidden" name="(?P<n>[^"]+)" id="[^"]*" value="(?P<v>[^"]*)"'
)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Node:
    title: str
    href: str | None
    cls: str
    depth: int
    path: str
    node_id: int
    children: list["Node"] = field(default_factory=list)

    @property
    def is_link(self) -> bool:
        return bool(self.href)


class HandbookClient:
    def __init__(self, timeout: int = 60, retries: int = 5):
        self.s = requests.Session()
        self.s.verify = False
        self.s.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                ),
                "Referer": MENU_URL,
            }
        )
        self.timeout = timeout
        self.retries = retries
        self._form: dict[str, str] = {}

    def _request(self, method: str, url: str, **kw):
        """GET/POST with exponential backoff; the VU server is flaky."""
        last: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                r = self.s.request(method, url, timeout=self.timeout, **kw)
                r.raise_for_status()
                return r
            except Exception as e:  # noqa: BLE001 - retry any transport error
                last = e
                if attempt == self.retries:
                    raise
                sleep(min(2**attempt, 15))
        raise last  # pragma: no cover

    # ------------------------------------------------------------------ menu
    @staticmethod
    def _hidden(html: str) -> dict[str, str]:
        fields = {m.group("n"): unescape(m.group("v")) for m in _HIDDEN_RE.finditer(html)}
        return {k: v for k, v in fields.items() if k.startswith("__") or k == "hfSelected"}

    def get_menu(self) -> str:
        r = self._request("GET", MENU_URL)
        self._form = self._hidden(r.text)
        return r.text

    def toggle(self, path: str) -> str:
        """Expand (or collapse) a TreeView node identified by its '\\' path."""
        data = dict(self._form)
        data["__EVENTTARGET"] = "PermissionTree"
        data["__EVENTARGUMENT"] = f"t{path}"
        r = self._request("POST", MENU_URL, data=data)
        self._form = self._hidden(r.text)
        return r.text

    def expand_all(self, log=print) -> str:
        html = self.get_menu()
        rounds = 0
        while True:
            pending = list(
                dict.fromkeys(
                    unescape(m.group("path").replace("\\\\", "\\"))
                    for m in _TOGGLE_RE.finditer(html)
                    if m.group("alt").startswith("Expand")
                )
            )
            if not pending:
                break
            rounds += 1
            log(f"  round {rounds}: expanding {len(pending)} branch(es)")
            for p in pending:
                html = self.toggle(p)
        return html

    # ------------------------------------------------------------------ pages
    def get_page(self, url: str) -> str:
        return self._request("GET", urljoin(BASE_URL, url)).text

    def get_raw(self, url: str) -> bytes:
        """Fetch exact bytes (PDFs and other non-HTML attachments)."""
        return self._request("GET", urljoin(BASE_URL, url)).content


def parse_tree(html: str) -> list[Node]:
    """Parse the rendered PermissionTree markup into a nested hierarchy.

    Nodes render as flat ``<table>`` rows; a parent's children follow it
    inside ``<div id="PermissionTreen{N}Nodes">``. Indent wrappers introduce
    additional, non-hierarchical ``<div>`` tags, so every ``<div>`` open/close
    is tracked to keep the stack balanced; only the ``...Nodes`` containers
    contribute a real hierarchy level.
    """
    start = html.find('<div id="PermissionTree">')
    if start == -1:
        return []
    body = html[start:]
    stop = body.find("</div><a id=")
    if stop != -1:
        body = body[:stop]

    token_re = re.compile(
        r"<div\b[^>]*>"
        r"|</div>"
        r'|<a[^>]*\bid="PermissionTreet(?P<tid>\d+)"[^>]*>(?P<title>.*?)</a>',
        re.S,
    )
    idx_re = re.compile(r'\bid="PermissionTreen(\d+)Nodes"')

    roots: list[Node] = []
    stack: list[list[Node] | None] = [roots]  # sentinel for the root level
    pending: dict[int, Node] = {}

    def _target() -> list[Node]:
        for level in reversed(stack):
            if level is not None:
                return level
        return roots

    for m in token_re.finditer(body):
        token = m.group(0)
        if token.startswith("<div"):
            hit = idx_re.search(token)
            if hit:
                node = pending.pop(int(hit.group(1)), None)
                stack.append(node.children if node is not None else None)
            else:
                stack.append(None)
        elif token == "</div>":
            if len(stack) > 1:
                stack.pop()
        else:
            raw_cls = _CLASS_RE.search(token)
            raw_href = _HREF_RE.search(token)
            href = raw_href.group(1) if raw_href else ""
            if not href or href.startswith("javascript:"):
                href = None
            else:
                href = urljoin(BASE_URL, unescape(href))
            title = unescape(_TAG_RE.sub("", m.group("title"))).strip()
            tid = int(m.group("tid"))
            node = Node(
                title=title,
                href=href,
                cls=(raw_cls.group(1).split()[0] if raw_cls else ""),
                depth=len(stack) - 1,
                path="",
                node_id=tid,
            )
            _target().append(node)
            pending[tid] = node

    _assign_paths(roots, "")
    return roots


def _assign_paths(nodes: list[Node], prefix: str) -> None:
    for n in nodes:
        n.path = f"{prefix}\\{n.title}" if prefix else n.title
        _assign_paths(n.children, n.path)


def flatten(nodes: list[Node]):
    for n in nodes:
        yield n
        yield from flatten(n.children)
