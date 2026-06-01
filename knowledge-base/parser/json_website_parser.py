import hashlib
import json
import logging
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from model import DocumentSegment
from util.errors import NoSuchDocumentError

logger = logging.getLogger(__name__)
PARSER_VERSION = "json-website-parser@2"
TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=2000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""],
    length_function=len,
    is_separator_regex=False,
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_with_offsets(text: str) -> list[tuple[str, int, int]]:
    chunks = TEXT_SPLITTER.split_text(text)
    if not chunks and text.strip():
        chunks = [text]

    chunks_with_offsets: list[tuple[str, int, int]] = []
    cursor = 0
    for chunk in chunks:
        if not chunk.strip():
            continue
        start = text.find(chunk, cursor)
        if start == -1:
            start = text.find(chunk)
        if start == -1:
            raise ValueError("Unable to locate JSON text chunk in source content.")
        end = start + len(chunk)
        chunks_with_offsets.append((chunk, start, end))
        cursor = end
    return chunks_with_offsets


def load_json_metadata(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict) or data.get("schema_version") != 2:
        return {}

    return {
        "id": data.get("document_id"),
        "source_id": data.get("source_id"),
        "party_id": data.get("party_id"),
        "source_type": data.get("source_type"),
        "election_year": data.get("election_year"),
        "public_url": data.get("public_url"),
        "snapshot_id": data.get("snapshot_id"),
        "raw_sha256": data.get("raw_sha256"),
        "canonical_text_sha256": data.get("canonical_text_sha256"),
        "captured_at": data.get("captured_at"),
        "parser_version": PARSER_VERSION,
    }


def parse_json(path: str, document_id: str) -> tuple[str, list[DocumentSegment]]:
    """
    Parses a JSON file where each item represents a webpage.

    Each JSON object is expected to have 'url' and 'content' keys.
    The 'content' becomes the text of a DocumentSegment, and 'url' is stored in metadata.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise NoSuchDocumentError(f"File not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON from file: {path} - {e}") from e

    if isinstance(data, dict) and data.get("schema_version") == 2:
        return _parse_schema_v2(data, document_id, path)

    if not isinstance(data, list):
        raise ValueError(
            f"JSON data in {path} is neither a legacy list nor schema_version=2."
        )

    raw_parts = []
    segments: list[DocumentSegment] = []
    current_char_offset = 0

    segment_index = 1
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "content" not in item or "url" not in item:
            logger.warning(f"Skipping invalid item at index {i} in {path}: {item}")
            continue

        content = item.get("content", "")
        url = item.get("url", "")

        # Add to raw_parts for later concatenation
        raw_parts.append(content)

        # Calculate start and end index for the segment based on future raw_content
        # This will be done after all parts are collected.
        # For now, placeholder values, or calculate based on current_char_offset
        # which is simpler for now.

        for chunk_index, (chunk, start, end) in enumerate(_split_with_offsets(content)):
            segments.append(
                DocumentSegment(
                    id=f"{document_id}-{i + 1}-{chunk_index + 1}",
                    text=chunk,
                    start_index=current_char_offset + start,
                    end_index=current_char_offset + end,
                    page=segment_index,
                    metadata={"url": url, "chunk_index": chunk_index},
                    type="website",
                    public_url=url,
                )
            )
            segment_index += 1
        current_char_offset += len(content)
        if i < len(data) - 1:  # Add separator length if not the last item
            current_char_offset += 2  # For "\\n\\n" separator

    raw_content = "\\n\\n".join(raw_parts)

    return raw_content, segments


def _parse_schema_v2(
    data: dict[str, Any], document_id: str, path: str
) -> tuple[str, list[DocumentSegment]]:
    items = data.get("items", [])
    if not isinstance(items, list):
        raise ValueError(f"JSON data in {path} has invalid 'items' field.")

    source_id = data.get("source_id")
    snapshot_id = data.get("snapshot_id")
    document_public_url = data.get("public_url")
    raw_sha256 = data.get("raw_sha256")

    raw_parts = []
    segments: list[DocumentSegment] = []
    current_char_offset = 0

    segment_index = 1
    for i, item in enumerate(items):
        if not isinstance(item, dict) or "content" not in item or "url" not in item:
            logger.warning(f"Skipping invalid item at index {i} in {path}: {item}")
            continue

        content = item.get("content", "")
        url = item.get("url", document_public_url or "")
        title = item.get("title")
        item_id = item.get("item_id") or f"item_{i + 1}"
        item_sequence_id = f"{i + 1}-{item_id}"
        segment_hash = item.get("content_sha256") or _sha256_text(content)

        if not content.strip():
            continue

        raw_parts.append(content)

        chunks = _split_with_offsets(content)
        for chunk_index, (chunk, start, end) in enumerate(chunks):
            chunk_hash = segment_hash if len(chunks) == 1 else _sha256_text(chunk)
            segments.append(
                DocumentSegment(
                    id=f"{document_id}-{item_sequence_id}-{chunk_index + 1}",
                    text=chunk,
                    start_index=current_char_offset + start,
                    end_index=current_char_offset + end,
                    page=segment_index,
                    metadata={
                        "url": url,
                        "title": title,
                        "source_id": source_id,
                        "snapshot_id": item.get("snapshot_id") or snapshot_id,
                        "raw_sha256": item.get("raw_sha256") or raw_sha256,
                        "content_sha256": segment_hash,
                        "segment_sha256": chunk_hash,
                        "item_id": item_id,
                        "item_index": i,
                        "chunk_index": chunk_index,
                    },
                    type="website",
                    public_url=url,
                    segment_sha256=chunk_hash,
                    source_id=source_id,
                    snapshot_id=item.get("snapshot_id") or snapshot_id,
                    title=title,
                )
            )
            segment_index += 1
        current_char_offset += len(content)
        if i < len(items) - 1:
            current_char_offset += 2

    return "\n\n".join(raw_parts), segments
