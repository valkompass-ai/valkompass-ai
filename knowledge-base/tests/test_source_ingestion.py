import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest
from pydantic import ValidationError

import main as kb_main
from parser import parse_document
from sources.extractors import discover_links, extracted_item_from_html, sitemap_urls
from sources.raw_snapshot_package import (
    assert_safe_member,
    source_manifest_records,
    verify_raw_snapshots,
    verify_sha256_sidecar,
)
from sources.registry import load_registry
from sources.url_tools import canonicalize_url


def write_test_archive(archive_path: Path, entries: dict[str, bytes]) -> str:
    with tarfile.open(archive_path, "w:gz") as tar:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return hashlib.sha256(archive_path.read_bytes()).hexdigest()


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


def test_source_verification_requires_traceability_files(tmp_path, monkeypatch):
    snapshots_dir = tmp_path / "source-snapshots"
    snapshots_dir.mkdir()
    monkeypatch.setattr(kb_main, "SOURCE_SNAPSHOTS_DIR", snapshots_dir)
    monkeypatch.setattr(
        kb_main,
        "RAW_SNAPSHOT_PACKAGE_MANIFEST_PATH",
        snapshots_dir / "raw-snapshots-package.json",
    )
    monkeypatch.setattr(
        kb_main,
        "SOURCE_SNAPSHOT_MANIFEST_PATH",
        snapshots_dir / "manifest.json",
    )

    with pytest.raises(FileNotFoundError, match="traceability files are missing"):
        kb_main.verify_source_snapshot_package_available()


def test_parse_fails_when_any_discovered_document_fails(tmp_path):
    docs_dir = tmp_path / "knowledge-base" / "documents"
    docs_dir.mkdir(parents=True)
    bad_json = docs_dir / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Failed to parse 1 of 1 documents"):
        kb_main.load_and_parse_documents(docs_dir, tmp_path)


def test_sha256_sidecar_is_validated(tmp_path):
    archive = tmp_path / "raw-snapshots.tar.gz"
    archive.write_bytes(b"archive bytes")
    sidecar = tmp_path / "raw-snapshots.tar.gz.sha256"
    sidecar.write_text("bad-hash  raw-snapshots.tar.gz\n", encoding="utf-8")

    with pytest.raises(ValueError, match="sidecar hash mismatch"):
        verify_sha256_sidecar(sidecar, archive)


def test_archive_member_safety_checks_directories():
    unsafe_dir = tarfile.TarInfo("../outside")
    unsafe_dir.type = tarfile.DIRTYPE

    with pytest.raises(ValueError, match="unsafe archive path"):
        assert_safe_member(unsafe_dir)


def test_source_manifest_rejects_duplicate_raw_paths(tmp_path):
    raw_path = "knowledge-base/source-snapshots/raw/party/source/sha256-abc.html"
    source_manifest = tmp_path / "manifest.json"
    snapshot = {
        "snapshot_id": "snap_abc",
        "source_id": "source",
        "party_id": "P",
        "requested_url": "https://example.test",
        "final_url": "https://example.test",
        "canonical_url": "https://example.test/",
        "retrieved_at": "2026-06-01T00:00:00+00:00",
        "http_status": 200,
        "content_type": "text/html",
        "raw_path": raw_path,
        "raw_sha256": "abc",
        "raw_bytes": 10,
        "fetcher_version": "test",
        "registry_sha256": "registry",
    }
    source_manifest.write_text(
        json.dumps({"schema_version": 1, "snapshots": [snapshot, snapshot]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate raw_path"):
        source_manifest_records(source_manifest)


def test_verify_package_does_not_require_unpacked_raw_cache(tmp_path, capsys):
    raw_path = "knowledge-base/source-snapshots/raw/party/source/sha256-abc.html"
    raw_content = b"raw bytes"
    raw_hash = hashlib.sha256(raw_content).hexdigest()

    archive = tmp_path / "raw-snapshots.tar.gz"
    archive_hash = write_test_archive(archive, {raw_path: raw_content})
    sidecar = tmp_path / "raw-snapshots.tar.gz.sha256"
    sidecar.write_text(f"{archive_hash}  raw-snapshots.tar.gz\n", encoding="utf-8")

    source_manifest = tmp_path / "manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshots": [
                    {
                        "snapshot_id": "snap_abc",
                        "source_id": "source",
                        "party_id": "P",
                        "requested_url": "https://example.test",
                        "final_url": "https://example.test",
                        "canonical_url": "https://example.test/",
                        "retrieved_at": "2026-06-01T00:00:00+00:00",
                        "http_status": 200,
                        "content_type": "text/html",
                        "raw_path": raw_path,
                        "raw_sha256": raw_hash,
                        "raw_bytes": len(raw_content),
                        "fetcher_version": "test",
                        "registry_sha256": "registry",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source_manifest_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    package_manifest = tmp_path / "raw-snapshots-package.json"
    package_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "archive_path": "knowledge-base/source-snapshots/raw-snapshots.tar.gz",
                "archive_sha256": archive_hash,
                "archive_bytes": archive.stat().st_size,
                "source_manifest_path": "knowledge-base/source-snapshots/manifest.json",
                "source_manifest_sha256": source_manifest_hash,
                "raw_file_count": 1,
                "raw_total_bytes": len(raw_content),
                "snapshot_count": 1,
                "files": [
                    {
                        "raw_path": raw_path,
                        "raw_sha256": raw_hash,
                        "raw_bytes": len(raw_content),
                        "snapshot_id": "snap_abc",
                        "source_id": "source",
                        "party_id": "P",
                        "canonical_url": "https://example.test/",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "archive": str(archive),
            "package_manifest": str(package_manifest),
            "source_manifest": str(source_manifest),
            "sha256": str(sidecar),
            "require_unpacked_raw": False,
        },
    )()

    verify_raw_snapshots(args)

    assert "raw snapshots are not unpacked locally" in capsys.readouterr().out

    args.require_unpacked_raw = True
    with pytest.raises(ValueError, match="Raw snapshot verification failed"):
        verify_raw_snapshots(args)


def test_verify_package_rejects_stale_source_manifest_metadata(tmp_path):
    raw_path = "knowledge-base/source-snapshots/raw/party/source/sha256-abc.html"
    raw_content = b"raw bytes"
    raw_hash = hashlib.sha256(raw_content).hexdigest()

    archive = tmp_path / "raw-snapshots.tar.gz"
    archive_hash = write_test_archive(archive, {raw_path: raw_content})
    sidecar = tmp_path / "raw-snapshots.tar.gz.sha256"
    sidecar.write_text(f"{archive_hash}  raw-snapshots.tar.gz\n", encoding="utf-8")

    source_manifest = tmp_path / "manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshots": [
                    {
                        "snapshot_id": "snap_abc",
                        "source_id": "source",
                        "party_id": "P",
                        "requested_url": "https://example.test",
                        "final_url": "https://example.test",
                        "canonical_url": "https://example.test/",
                        "retrieved_at": "2026-06-01T00:00:00+00:00",
                        "http_status": 200,
                        "content_type": "text/html",
                        "raw_path": raw_path,
                        "raw_sha256": raw_hash,
                        "raw_bytes": len(raw_content),
                        "fetcher_version": "test",
                        "registry_sha256": "registry",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source_manifest_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    package_manifest = tmp_path / "raw-snapshots-package.json"
    package_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "archive_path": "knowledge-base/source-snapshots/raw-snapshots.tar.gz",
                "archive_sha256": archive_hash,
                "archive_bytes": archive.stat().st_size,
                "source_manifest_path": "knowledge-base/source-snapshots/manifest.json",
                "source_manifest_sha256": source_manifest_hash,
                "raw_file_count": 1,
                "raw_total_bytes": len(raw_content),
                "snapshot_count": 1,
                "files": [
                    {
                        "raw_path": raw_path,
                        "raw_sha256": "stale-hash",
                        "raw_bytes": len(raw_content),
                        "snapshot_id": "snap_abc",
                        "source_id": "source",
                        "party_id": "P",
                        "canonical_url": "https://example.test/",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "archive": str(archive),
            "package_manifest": str(package_manifest),
            "source_manifest": str(source_manifest),
            "sha256": str(sidecar),
            "require_unpacked_raw": False,
        },
    )()

    with pytest.raises(ValueError, match="metadata does not match source manifest"):
        verify_raw_snapshots(args)


def test_verify_package_rejects_archive_members_that_do_not_match_manifest(tmp_path):
    raw_path = "knowledge-base/source-snapshots/raw/party/source/sha256-abc.html"
    expected_raw_content = b"expected raw bytes"
    expected_raw_hash = hashlib.sha256(expected_raw_content).hexdigest()

    archive = tmp_path / "raw-snapshots.tar.gz"
    archive_hash = write_test_archive(archive, {raw_path: b"different raw bytes"})
    sidecar = tmp_path / "raw-snapshots.tar.gz.sha256"
    sidecar.write_text(f"{archive_hash}  raw-snapshots.tar.gz\n", encoding="utf-8")

    source_manifest = tmp_path / "manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "snapshots": [
                    {
                        "snapshot_id": "snap_abc",
                        "source_id": "source",
                        "party_id": "P",
                        "requested_url": "https://example.test",
                        "final_url": "https://example.test",
                        "canonical_url": "https://example.test/",
                        "retrieved_at": "2026-06-01T00:00:00+00:00",
                        "http_status": 200,
                        "content_type": "text/html",
                        "raw_path": raw_path,
                        "raw_sha256": expected_raw_hash,
                        "raw_bytes": len(expected_raw_content),
                        "fetcher_version": "test",
                        "registry_sha256": "registry",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    source_manifest_hash = hashlib.sha256(source_manifest.read_bytes()).hexdigest()
    package_manifest = tmp_path / "raw-snapshots-package.json"
    package_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "archive_path": "knowledge-base/source-snapshots/raw-snapshots.tar.gz",
                "archive_sha256": archive_hash,
                "archive_bytes": archive.stat().st_size,
                "source_manifest_path": "knowledge-base/source-snapshots/manifest.json",
                "source_manifest_sha256": source_manifest_hash,
                "raw_file_count": 1,
                "raw_total_bytes": len(expected_raw_content),
                "snapshot_count": 1,
                "files": [
                    {
                        "raw_path": raw_path,
                        "raw_sha256": expected_raw_hash,
                        "raw_bytes": len(expected_raw_content),
                        "snapshot_id": "snap_abc",
                        "source_id": "source",
                        "party_id": "P",
                        "canonical_url": "https://example.test/",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "archive": str(archive),
            "package_manifest": str(package_manifest),
            "source_manifest": str(source_manifest),
            "sha256": str(sidecar),
            "require_unpacked_raw": False,
        },
    )()

    with pytest.raises(ValueError, match="Archive members do not match"):
        verify_raw_snapshots(args)
