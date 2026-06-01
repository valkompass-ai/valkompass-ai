from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

from .models import ExtractedItem
from .url_tools import absolute_url, canonicalize_url, is_allowed_url

BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
SKIP_TAGS = {"script", "style", "noscript", "svg", "form", "header", "nav", "footer"}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    text = unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class LinkAndTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.main_text_parts: list[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "main":
            self._main_depth += 1
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "a":
            for name, value in attrs:
                if name.lower() == "href" and value:
                    self.links.append(value)
        if tag in BLOCK_TAGS and self._skip_depth == 0:
            self._append_text("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS and self._skip_depth == 0:
            self._append_text("\n")
        if tag == "main" and self._main_depth > 0:
            self._main_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data.strip())
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._append_text(stripped)

    def _append_text(self, text: str) -> None:
        self.text_parts.append(text)
        if self._main_depth > 0:
            self.main_text_parts.append(text)

    @property
    def title(self) -> str | None:
        title = normalize_text(" ".join(part for part in self.title_parts if part))
        return title or None

    @property
    def text(self) -> str:
        main_text = normalize_text(" ".join(self.main_text_parts))
        if len(main_text) > 200:
            return main_text
        return normalize_text(" ".join(self.text_parts))


def parse_html(html: str) -> tuple[str | None, str, list[str]]:
    parser = LinkAndTextParser()
    parser.feed(html)
    return parser.title, parser.text, parser.links


def discover_links(
    html: str,
    page_url: str,
    base_host: str,
    allow_paths: list[str],
    deny_paths: list[str],
) -> list[str]:
    _, _, links = parse_html(html)
    discovered: list[str] = []
    seen: set[str] = set()
    for href in links:
        url = absolute_url(page_url, href)
        if url in seen:
            continue
        seen.add(url)
        if is_allowed_url(url, base_host, allow_paths, deny_paths):
            discovered.append(url)
    return discovered


def sitemap_urls(
    xml_text: str, base_host: str, allow_paths: list[str], deny_paths: list[str]
) -> list[str]:
    try:
        root = ET.fromstring(xml_text.lstrip())
    except ET.ParseError:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for loc in root.iter():
        if not loc.tag.endswith("loc") or not loc.text:
            continue
        url = canonicalize_url(loc.text.strip())
        path = urlparse(url).path.lower()
        if path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            continue
        if url in seen:
            continue
        seen.add(url)
        parsed = urlparse(url)
        is_nested_sitemap = parsed.path.endswith(".xml")
        if is_nested_sitemap or is_allowed_url(url, base_host, allow_paths, deny_paths):
            urls.append(url)
    return urls


def extracted_item_from_html(
    *,
    url: str,
    html: str,
    snapshot_id: str,
    raw_sha256: str,
) -> ExtractedItem | None:
    title, content, _ = parse_html(html)
    if len(content) < 200:
        return None
    canonical_url = canonicalize_url(url)
    content_hash = sha256_text(content)
    return ExtractedItem(
        item_id=f"url_sha256_{sha256_text(canonical_url)[:16]}",
        url=canonical_url,
        title=title,
        content=content,
        content_sha256=content_hash,
        snapshot_id=snapshot_id,
        raw_sha256=raw_sha256,
    )
