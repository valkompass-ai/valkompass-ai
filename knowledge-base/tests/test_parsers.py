import pytest

from model import Document, DocumentSegment
from parser import parse_document
from util.errors import NoSuchDocumentError


def test_parse_pdf():
    """Test parsing a PDF document via parse_document."""
    pdf_path = "documents/socialdemokraterna/socialdemokraterna-valmanifest-2022.pdf"
    document_id = "test-socialdemokraterna-valmanifest"
    document = parse_document(pdf_path, document_id)

    assert document is not None, "The document should not be None."
    assert isinstance(document, Document), (
        "The returned object should be a Document instance."
    )
    assert document.path == pdf_path, "The document path should match the input path."
    assert document.id == document_id, "The document ID should match the input ID."
    assert isinstance(document.raw_content, str), "Raw content should be a string."
    assert len(document.raw_content) > 1000, "Raw content should not be empty."
    assert isinstance(document.segments, list), (
        "Document lines (segments) should be a list."
    )
    assert len(document.segments) > 0, (
        "Document lines (segments) should not be empty for this PDF."
    )
    for segment in document.segments:
        assert isinstance(segment, DocumentSegment), (
            "Each item in document.lines should be a DocumentSegment."
        )


def test_parse_non_existent_file():
    """Test parsing a non-existent file should raise FileNotFoundError."""
    non_existent_path = "path/to/a/completely/non_existent_file.txt"
    document_id = "test-non-existent"
    with pytest.raises(NoSuchDocumentError):
        parse_document(non_existent_path, document_id)
