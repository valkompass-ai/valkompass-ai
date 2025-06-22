import os

import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model import DocumentSegment
from util.errors import NoSuchDocumentError


def parse_pdf(path: str, document_id: str) -> tuple[str, list[DocumentSegment]]:
    return __parse_and_segment_langchain(path, document_id)


# TODO: Optimize this?
def __parse_and_segment_langchain(
    path: str,
    document_id: str,
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> tuple[str, list[DocumentSegment]]:
    # Check if file exists first
    if not os.path.exists(path):
        raise NoSuchDocumentError(f"PDF file not found: {path}")

    # 1) Extract text page by page and prepare for full raw text concatenation
    page_data_list = []  # Stores dicts of {"text": str, "page_number": int}
    with pdfplumber.open(path) as pdf:
        if not pdf.pages:
            raise ValueError(f"PDF file has no pages: {path}")
        for page in pdf.pages:
            page_data_list.append(
                {"text": page.extract_text() or "", "page_number": page.page_number}
            )

    if not page_data_list:
        raise ValueError(f"No pages could be extracted from PDF: {path}")

    # 2) Construct the full raw text and track character offsets for each page start
    raw_parts = []
    page_char_start_map = []  # List of tuples: (character_offset_in_raw, page_number)
    current_char_offset = 0

    for i, p_data in enumerate(page_data_list):
        page_text = p_data["text"]
        page_number = p_data["page_number"]

        page_char_start_map.append((current_char_offset, page_number))
        raw_parts.append(page_text)

        current_char_offset += len(page_text)
        if i < len(page_data_list) - 1:  # If not the last page, add separator length
            current_char_offset += 2  # For "\\n\\n"

    raw = "\\n\\n".join(raw_parts)

    # 3) Configure text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\\n\\n", "\\n", " ", ""],
        length_function=len,
        is_separator_regex=False,
    )

    # 4) Split the raw text into chunks
    split_texts = text_splitter.split_text(raw)

    # 5) Build DocumentSegment objects, now with page numbers
    segments: list[DocumentSegment] = []
    current_search_cursor = 0

    # Construct the public URL for the PDF
    pdf_filename = os.path.basename(path)
    # Get the parent directory name (e.g., "liberalerna")
    party_name = os.path.basename(os.path.dirname(path))
    pdf_public_url = f"/kb-documents/{party_name}/{pdf_filename}"

    for i, text_chunk in enumerate(split_texts):
        # Skip chunks that are empty or contain only whitespace (e.g., "\n", "  ", "\t\n ")
        s_text_chunk = text_chunk.strip()
        if not s_text_chunk or s_text_chunk == "\\n":
            continue

        chunk_start_index = raw.find(text_chunk, current_search_cursor)

        if chunk_start_index == -1:
            # Fallback: try searching from beginning if not found with cursor
            chunk_start_index_fallback = raw.find(text_chunk)
            if chunk_start_index_fallback != -1:
                chunk_start_index = chunk_start_index_fallback
            else:  # Still not found, this chunk is problematic
                # Assign a default page (e.g., first page if available, or 0) and log.
                page_for_lost_chunk = (
                    page_char_start_map[0][1] if page_char_start_map else 0
                )
                print(
                    f"Warning: Text chunk not found in raw PDF text. Page assigned: {page_for_lost_chunk}. Chunk: '{text_chunk[:100]}...'"
                )
                # Decide whether to skip or create a segment with potentially inaccurate data.
                # For now, skipping problematic chunks:
                continue

        chunk_end_index = chunk_start_index + len(text_chunk)

        # Determine the page number for this chunk
        assigned_page_number = 0  # Default if no pages or error
        if page_char_start_map:
            # Iterate backwards through page start markers.
            # The first one (i.e., largest page number) whose start offset is <= chunk's start is the correct page.
            for offset, page_num in reversed(page_char_start_map):
                if chunk_start_index >= offset:
                    assigned_page_number = page_num
                    break

        segments.append(
            DocumentSegment(
                id=f"{document_id}-{i}",
                text=text_chunk,
                start_index=chunk_start_index,
                end_index=chunk_end_index,
                page=assigned_page_number,
                metadata=None,
                type="pdf",
                public_url=pdf_public_url,
            )
        )

        # Update cursor to search for the next chunk after the end of the current one
        current_search_cursor = chunk_end_index

    return raw, segments
