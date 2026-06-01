from __future__ import annotations

import argparse
import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from .extractors import (
    discover_links,
    extracted_item_from_html,
    sha256_text,
    sitemap_urls,
)
from .fetcher import SourceFetcher
from .manifest import load_manifest, upsert_snapshot, write_manifest, write_report
from .models import CrawlFailure, CrawlReport, ExtractedItem
from .registry import iter_enabled_sources, load_registry
from .url_tools import canonicalize_url, extension_for_content_type, is_allowed_url

KB_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = KB_DIR.parent
REGISTRY_PATH = KB_DIR / "source-registry.json"
SNAPSHOT_DIR = KB_DIR / "source-snapshots"
DOCUMENTS_DIR = KB_DIR / "documents"


def stable_document_id(source_id: str, items: list[ExtractedItem]) -> str:
    content = "\n\n".join(item.content for item in items)
    return f"doc_sha256_{sha256_text(source_id + ':' + content)[:24]}"


def write_extracted_document(
    *,
    party_folder: str,
    party_id: str,
    source_id: str,
    source_type: str,
    election_year: int,
    priority: str,
    items: list[ExtractedItem],
) -> Path | None:
    if not items:
        return None
    first = items[0]
    canonical_text = "\n\n".join(item.content for item in items)
    document = {
        "schema_version": 2,
        "document_id": stable_document_id(source_id, items),
        "party_id": party_id,
        "source_id": source_id,
        "source_type": source_type,
        "election_year": election_year,
        "priority": priority,
        "title": first.title or source_id,
        "public_url": first.url,
        "snapshot_id": first.snapshot_id,
        "raw_sha256": first.raw_sha256,
        "canonical_text_sha256": sha256_text(canonical_text),
        "captured_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "items": [item.model_dump() for item in items],
    }
    output_path = DOCUMENTS_DIR / party_folder / "web" / f"{source_id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output_path


def crawl(args: argparse.Namespace) -> None:
    registry, registry_sha256 = load_registry(REGISTRY_PATH)
    selected = iter_enabled_sources(
        registry, party_id=args.party, source_id=args.source
    )
    if not selected:
        raise SystemExit("No enabled sources matched the requested filters.")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report = CrawlReport(
        run_id=run_id,
        registry_sha256=registry_sha256,
        parties=sorted({party.party_id for party, _ in selected}),
        sources=sorted({source.source_id for _, source in selected}),
    )
    manifest_path = SNAPSHOT_DIR / "manifest.json"
    manifest = load_manifest(manifest_path)
    fetcher = SourceFetcher(
        output_dir=SNAPSHOT_DIR,
        user_agent=registry.default_user_agent,
        requests_per_second=registry.default_rate_limit.requests_per_second,
        registry_sha256=registry_sha256,
    )

    for party, source in selected:
        base_host = urlparse(str(source.base_url)).netloc.lower()
        queue = deque((canonicalize_url(str(url)), 0) for url in source.seed_urls)
        seen: set[str] = set()
        extracted: list[ExtractedItem] = []

        while queue and len(seen) < source.max_pages:
            url, depth = queue.popleft()
            if url in seen:
                continue
            seen.add(url)

            if not is_allowed_url(
                url, base_host, source.allow_paths, source.deny_paths
            ):
                # Explicit sitemap seeds are allowed to bootstrap discovery.
                if not urlparse(url).path.endswith(".xml"):
                    report.skipped.append(
                        f"{source.source_id}: outside allowlist {url}"
                    )
                    continue

            try:
                result = fetcher.fetch(
                    url=url,
                    source_id=source.source_id,
                    party_id=party.party_id,
                    party_folder=party.document_folder,
                )
            except RuntimeError as exc:
                report.failures.append(
                    CrawlFailure(
                        source_id=source.source_id,
                        party_id=party.party_id,
                        url=url,
                        error=str(exc),
                    )
                )
                continue

            if upsert_snapshot(manifest, result.record):
                report.fetched += 1
            else:
                report.unchanged += 1

            if result.record.content_type not in source.include_media_types:
                report.skipped.append(
                    f"{source.source_id}: unsupported media type {result.record.content_type} {result.record.final_url}"
                )
                continue

            extension = extension_for_content_type(result.record.content_type, url)
            if extension == "pdf":
                continue

            text = result.body.decode("utf-8", errors="replace")
            if extension == "xml" or urlparse(result.record.final_url).path.endswith(
                ".xml"
            ):
                for discovered in sitemap_urls(
                    text, base_host, source.allow_paths, source.deny_paths
                ):
                    if discovered not in seen:
                        queue.append(discovered)
                continue

            item = extracted_item_from_html(
                url=result.record.final_url,
                html=text,
                snapshot_id=result.record.snapshot_id,
                raw_sha256=result.record.raw_sha256,
            )
            if item:
                extracted.append(item)

            if depth < source.max_link_depth and (
                "links" in source.discovery or "pdf_links" in source.discovery
            ):
                for discovered in discover_links(
                    text,
                    result.record.final_url,
                    base_host,
                    source.allow_paths,
                    source.deny_paths,
                ):
                    if discovered not in seen:
                        queue.append((discovered, depth + 1))

        output_path = write_extracted_document(
            party_folder=party.document_folder,
            party_id=party.party_id,
            source_id=source.source_id,
            source_type=source.source_type,
            election_year=source.election_year,
            priority=source.priority,
            items=extracted,
        )
        if output_path:
            report.extracted_documents += 1
            report.extracted_items += len(extracted)

    write_manifest(manifest_path, manifest)
    write_report(report, SNAPSHOT_DIR)
    print(f"Wrote crawl report {SNAPSHOT_DIR / 'reports' / (run_id + '.md')}")


def validate_registry(_: argparse.Namespace) -> None:
    registry, registry_sha256 = load_registry(REGISTRY_PATH)
    sources = sum(len(party.sources) for party in registry.parties if party.enabled)
    print(
        f"Registry valid: {len(registry.parties)} parties, {sources} enabled sources, sha256={registry_sha256}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Source ingestion CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-registry")
    validate.set_defaults(func=validate_registry)

    crawl_cmd = subparsers.add_parser("crawl")
    crawl_cmd.add_argument("--party", help="Party ID to crawl")
    crawl_cmd.add_argument("--source", help="Source ID to crawl")
    crawl_cmd.add_argument(
        "--all", action="store_true", help="Crawl all enabled sources"
    )
    crawl_cmd.set_defaults(func=crawl)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
