import json
import logging

from model import DocumentSegment
from util.errors import NoSuchDocumentError

logger = logging.getLogger(__name__)


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

    if not isinstance(data, list):
        raise ValueError(f"JSON data in {path} is not a list as expected.")

    raw_parts = []
    segments: list[DocumentSegment] = []
    current_char_offset = 0

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

        start_index = current_char_offset
        end_index = current_char_offset + len(content)

        segments.append(
            DocumentSegment(
                id=f"{document_id}-{i + 1}",  # 1-indexed segment id
                text=content,
                start_index=start_index,
                end_index=end_index,
                page=i + 1,  # Using index as page number (1-indexed)
                metadata={"url": url},
                type="website",
                public_url=url,
            )
        )
        current_char_offset += len(content)
        if i < len(data) - 1:  # Add separator length if not the last item
            current_char_offset += 2  # For "\\n\\n" separator

    raw_content = "\\n\\n".join(raw_parts)

    return raw_content, segments
