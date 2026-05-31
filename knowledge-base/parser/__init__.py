import os

from model import Document
from util.errors import NoSuchDocumentError

from .json_website_parser import load_json_metadata, parse_json
from .pdf_parser import parse_pdf


def parse_document(path: str, document_id: str) -> Document:
    # Check if file exists first
    if not os.path.exists(path):
        raise NoSuchDocumentError(f"File not found: {path}")

    raw_content: str = ""
    segments: list = []

    _, file_extension = os.path.splitext(path)

    metadata = {}

    if file_extension.lower() == ".pdf":
        try:
            raw_content, segments = parse_pdf(path, document_id)
        except NoSuchDocumentError:
            raise

    elif file_extension.lower() == ".json":
        try:
            metadata = load_json_metadata(path)
            document_id = metadata.get("id") or document_id
            raw_content, segments = parse_json(path, document_id)
        except NoSuchDocumentError:
            raise

    else:
        print(
            f"Unsupported file type: {file_extension} for document {document_id} at {path}"
        )
        return Document(id=document_id, path=path, raw_content="", segments=[])

    return Document(
        id=document_id,
        path=path,
        raw_content=raw_content,
        segments=segments,
        source_id=metadata.get("source_id"),
        party_id=metadata.get("party_id"),
        source_type=metadata.get("source_type"),
        election_year=metadata.get("election_year"),
        public_url=metadata.get("public_url"),
        snapshot_id=metadata.get("snapshot_id"),
        raw_sha256=metadata.get("raw_sha256"),
        canonical_text_sha256=metadata.get("canonical_text_sha256"),
        captured_at=metadata.get("captured_at"),
        parser_version=metadata.get("parser_version"),
    )
