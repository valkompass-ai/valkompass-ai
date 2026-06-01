from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = PROJECT_ROOT / "knowledge-base"
PDF_MANIFEST_PATH = KB_DIR / "source-documents-manifest.json"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_document_id_for_path(path: str | Path) -> str:
    path_obj = Path(path)
    if path_obj.is_absolute():
        try:
            relative_path = path_obj.relative_to(PROJECT_ROOT)
        except ValueError:
            relative_path = path_obj
    else:
        relative_path = path_obj
    return f"doc_path_sha256_{sha256_text(relative_path.as_posix())[:24]}"


def _normalize_manifest_path(path: str | Path) -> str:
    path_obj = Path(path)
    if path_obj.is_absolute():
        try:
            return path_obj.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path_obj.as_posix()
    path_text = path_obj.as_posix()
    if path_text.startswith("knowledge-base/"):
        return path_text
    return f"knowledge-base/{path_text}"


def load_pdf_source_manifest(
    manifest_path: Path = PDF_MANIFEST_PATH,
) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    records: dict[str, dict[str, Any]] = {}
    for record in data.get("documents", []):
        path = record.get("path")
        if isinstance(path, str):
            records[path] = record
    return records


def load_pdf_metadata(path: str | Path) -> dict[str, Any]:
    records = load_pdf_source_manifest()
    record = records.get(_normalize_manifest_path(path))
    if not record:
        return {
            "parser_version": "pdf-parser@2",
            "source_id": Path(path).stem,
        }

    return {
        "title": record.get("title"),
        "source_id": Path(record["path"]).stem,
        "party_id": record.get("party_id"),
        "source_type": record.get("document_type"),
        "document_type": record.get("document_type"),
        "election_year": record.get("year"),
        "public_url": record.get("public_path"),
        "raw_sha256": record.get("sha256"),
        "canonical_text_sha256": None,
        "captured_at": record.get("retrieved_at"),
        "parser_version": "pdf-parser@2",
        "source_page_url": record.get("source_page_url"),
        "download_url": record.get("download_url"),
        "final_url": record.get("final_url"),
        "content_type": record.get("content_type"),
        "byte_size": record.get("bytes"),
    }
