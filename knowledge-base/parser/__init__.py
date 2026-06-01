import os

from model import Document
from util.errors import NoSuchDocumentError

from .json_website_parser import load_json_metadata, parse_json
from .pdf_parser import parse_pdf
from .source_metadata import load_pdf_metadata, sha256_text


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
            metadata = load_pdf_metadata(path)
            raw_content, segments = parse_pdf(path, document_id)
            public_url = metadata.get("public_url")
            source_id = metadata.get("source_id")
            title = metadata.get("title")
            raw_sha256 = metadata.get("raw_sha256")
            for segment in segments:
                segment.public_url = public_url or segment.public_url
                segment.source_id = source_id
                segment.title = title
                segment.segment_sha256 = sha256_text(segment.text)
                segment.metadata = {
                    "source_id": source_id,
                    "party_id": metadata.get("party_id"),
                    "document_type": metadata.get("document_type"),
                    "title": title,
                    "public_url": segment.public_url,
                    "source_page_url": metadata.get("source_page_url"),
                    "download_url": metadata.get("download_url"),
                    "final_url": metadata.get("final_url"),
                    "raw_sha256": raw_sha256,
                    "content_sha256": segment.segment_sha256,
                }
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
        title=metadata.get("title"),
        source_id=metadata.get("source_id"),
        party_id=metadata.get("party_id"),
        source_type=metadata.get("source_type"),
        document_type=metadata.get("document_type"),
        election_year=metadata.get("election_year"),
        public_url=metadata.get("public_url"),
        snapshot_id=metadata.get("snapshot_id"),
        raw_sha256=metadata.get("raw_sha256"),
        canonical_text_sha256=metadata.get("canonical_text_sha256"),
        captured_at=metadata.get("captured_at"),
        parser_version=metadata.get("parser_version"),
        source_page_url=metadata.get("source_page_url"),
        download_url=metadata.get("download_url"),
        final_url=metadata.get("final_url"),
        content_type=metadata.get("content_type"),
        byte_size=metadata.get("byte_size"),
    )
