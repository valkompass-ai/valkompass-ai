import os

from model import Document
from util.errors import NoSuchDocumentError

from .json_website_parser import parse_json
from .pdf_parser import parse_pdf


def parse_document(path: str, document_id: str) -> Document:
    # Check if file exists first
    if not os.path.exists(path):
        raise NoSuchDocumentError(f"File not found: {path}")

    raw_content: str = ""
    segments: list = []

    _, file_extension = os.path.splitext(path)

    if file_extension.lower() == ".pdf":
        try:
            raw_content, segments = parse_pdf(path, document_id)
        except NoSuchDocumentError:
            raise

    elif file_extension.lower() == ".json":
        try:
            raw_content, segments = parse_json(path, document_id)
        except NoSuchDocumentError:
            raise

    else:
        print(
            f"Unsupported file type: {file_extension} for document {document_id} at {path}"
        )
        return Document(id=document_id, path=path, raw_content="", segments=[])

    return Document(
        id=document_id, path=path, raw_content=raw_content, segments=segments
    )
