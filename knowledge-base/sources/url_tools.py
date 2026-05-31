from __future__ import annotations

from urllib.parse import urljoin, urlparse, urlunparse


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


def absolute_url(base_url: str, href: str) -> str:
    return canonicalize_url(urljoin(base_url, href))


def is_allowed_url(
    url: str, base_host: str, allow_paths: list[str], deny_paths: list[str]
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if parsed.netloc.lower() != base_host.lower():
        return False
    path = parsed.path or "/"
    if any(path.startswith(deny) for deny in deny_paths):
        return False
    return any(path.startswith(allow) for allow in allow_paths)


def extension_for_content_type(content_type: str, url: str) -> str:
    lower = content_type.split(";", 1)[0].strip().lower()
    if lower == "application/pdf" or url.lower().split("?", 1)[0].endswith(".pdf"):
        return "pdf"
    if lower in {"application/xml", "text/xml"}:
        return "xml"
    if lower in {"application/json", "text/json"}:
        return "json"
    return "html"
