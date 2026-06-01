import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from parser import parse_document
from sources.extractors import discover_links, extracted_item_from_html, sitemap_urls
from sources.registry import load_registry
from sources.url_tools import canonicalize_url


def test_source_registry_is_valid():
    registry, registry_hash = load_registry(Path("source-registry.json"))

    assert registry.schema_version == 1
    assert registry_hash
    assert {party.party_id for party in registry.parties} >= {
        "S",
        "M",
        "SD",
        "MP",
        "C",
        "L",
        "KD",
        "V",
    }


def test_registry_rejects_seed_host_outside_base_url():
    registry, _ = load_registry(Path("source-registry.json"))
    data = registry.model_dump(mode="json")
    data["parties"][0]["sources"][0]["seed_urls"] = ["https://example.com/politik"]

    with pytest.raises(ValidationError):
        type(registry)(**data)


def test_canonicalize_url_is_stable():
    assert (
        canonicalize_url("HTTPS://Example.COM/a/b?z=2&a=1#fragment")
        == "https://example.com/a/b"
    )


def test_extract_html_text_and_allowed_links():
    html = """
    <html>
      <head><title>Politik A-O</title><script>ignore()</script></head>
      <body>
        <main>
          <h1>Skola</h1>
          <p>Detta är en lång politisk text om skolan som ska extraheras.</p>
          <p>Mer innehåll som gör att texten blir tillräckligt lång för indexering.</p>
          <p>Ännu mer innehåll med sakpolitisk information och tydlig källa.</p>
          <a href="/var-politik/skola">Skola</a>
          <a href="/nyheter/foo">Nyhet</a>
        </main>
      </body>
    </html>
    """
    item = extracted_item_from_html(
        url="https://parti.example/var-politik/",
        html=html,
        snapshot_id="snap_123",
        raw_sha256="abc",
    )
    links = discover_links(
        html,
        "https://parti.example/var-politik/",
        "parti.example",
        ["/var-politik/"],
        ["/nyheter/"],
    )

    assert item is not None
    assert item.title == "Politik A-O"
    assert "ignore" not in item.content
    assert links == ["https://parti.example/var-politik/skola"]


def test_sitemap_discovers_allowed_urls():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://parti.example/var-politik/skola</loc></url>
      <url><loc>https://parti.example/nyheter/foo</loc></url>
    </urlset>
    """

    assert sitemap_urls(xml, "parti.example", ["/var-politik/"], ["/nyheter/"]) == [
        "https://parti.example/var-politik/skola"
    ]


def test_schema_v2_website_json_parses_with_provenance(tmp_path):
    document_path = tmp_path / "source.json"
    document = {
        "schema_version": 2,
        "document_id": "doc_sha256_test",
        "party_id": "S",
        "source_id": "s-politik-a-till-o",
        "source_type": "website_policy_index",
        "election_year": 2026,
        "title": "Politik A till O",
        "public_url": "https://example.test/politik",
        "snapshot_id": "snap_sha256_test",
        "raw_sha256": "raw_hash",
        "canonical_text_sha256": "text_hash",
        "captured_at": "2026-05-31T12:00:00+00:00",
        "items": [
            {
                "item_id": "url_sha256_abc",
                "url": "https://example.test/politik/skola",
                "title": "Skola",
                "content": "Skolpolitik med tillrackligt mycket innehall for ett segment.",
                "content_sha256": "content_hash",
                "snapshot_id": "snap_sha256_test",
                "raw_sha256": "raw_hash",
            }
        ],
    }
    document_path.write_text(json.dumps(document), encoding="utf-8")

    parsed = parse_document(str(document_path), "fallback")

    assert parsed.id == "doc_sha256_test"
    assert parsed.party_id == "S"
    assert parsed.source_id == "s-politik-a-till-o"
    assert parsed.canonical_text_sha256 == "text_hash"
    assert parsed.segments[0].id == "doc_sha256_test-1-url_sha256_abc-1"
    assert parsed.segments[0].segment_sha256 == "content_hash"
    assert parsed.segments[0].snapshot_id == "snap_sha256_test"


def test_schema_v2_website_json_segment_ids_survive_duplicate_item_ids(tmp_path):
    document_path = tmp_path / "source.json"
    duplicate_item = {
        "item_id": "url_sha256_duplicate",
        "url": "https://example.test/politik/personlig-assistans",
        "title": "Personlig assistans",
        "content": "Assistanspolitik med tillrackligt innehall for ett segment.",
        "content_sha256": "content_hash",
        "snapshot_id": "snap_sha256_test",
        "raw_sha256": "raw_hash",
    }
    document = {
        "schema_version": 2,
        "document_id": "doc_sha256_test",
        "party_id": "L",
        "source_id": "l-politik-a-o",
        "source_type": "website_policy_index",
        "election_year": 2026,
        "public_url": "https://example.test/politik",
        "snapshot_id": "snap_sha256_test",
        "raw_sha256": "raw_hash",
        "canonical_text_sha256": "text_hash",
        "captured_at": "2026-05-31T12:00:00+00:00",
        "items": [duplicate_item, duplicate_item],
    }
    document_path.write_text(json.dumps(document), encoding="utf-8")

    parsed = parse_document(str(document_path), "fallback")
    segment_ids = [segment.id for segment in parsed.segments]

    assert len(segment_ids) == 2
    assert len(set(segment_ids)) == 2
    assert segment_ids == [
        "doc_sha256_test-1-url_sha256_duplicate-1",
        "doc_sha256_test-2-url_sha256_duplicate-1",
    ]
