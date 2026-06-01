from typing import Any

import numpy as np
from pydantic import BaseModel, field_serializer, field_validator, model_validator

from .political_entities import Party as Party


class Topic(BaseModel):
    id: int
    name: str
    description: str
    embedding: np.ndarray | None = None

    model_config = {"arbitrary_types_allowed": True}

    @field_serializer("embedding", when_used="json")
    def serialize_embedding_to_list(self, v: np.ndarray) -> list[float]:
        """Convert np.ndarray to list for JSON serialization."""
        if v is None:
            return None
        return v.tolist()

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding(cls, v: Any) -> np.ndarray | None:
        if isinstance(v, list):
            return np.array(v, dtype=float)
        return v


class DocumentSegment(BaseModel):
    id: str
    text: str
    start_index: int
    end_index: int
    page: int
    metadata: dict | None = None
    embedding: np.ndarray | None = None
    topic_id: int | None = None
    type: str | None = None
    public_url: str | None = None
    segment_sha256: str | None = None
    source_id: str | None = None
    snapshot_id: str | None = None
    title: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def validate_indices(self) -> "DocumentSegment":
        """Validate that start_index < end_index and page > 0."""
        if self.start_index >= self.end_index:
            raise ValueError(
                f"start_index ({self.start_index}) must be less than end_index ({self.end_index})"
            )
        if self.page <= 0:
            raise ValueError(f"page ({self.page}) must be positive")
        if not self.text.strip():
            raise ValueError("text cannot be empty or whitespace only")
        return self

    @field_serializer("embedding", when_used="json")
    def serialize_embedding_to_list(self, v: np.ndarray) -> list[float]:
        """Convert np.ndarray to list for JSON serialization."""
        if v is None:
            return None
        return v.tolist()

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding_from_list(cls, v: Any) -> np.ndarray | None:
        """Convert list to np.ndarray during deserialization from JSON."""
        if isinstance(v, list):
            return np.array(v, dtype=float)
        # If v is None, or already an np.ndarray (e.g. direct model instantiation),
        # Pydantic's default validation will handle it.
        return v


class Document(BaseModel):
    id: str
    path: str
    raw_content: str
    segments: list[DocumentSegment]
    title: str | None = None
    source_id: str | None = None
    party_id: str | None = None
    source_type: str | None = None
    document_type: str | None = None
    election_year: int | None = None
    public_url: str | None = None
    snapshot_id: str | None = None
    raw_sha256: str | None = None
    canonical_text_sha256: str | None = None
    captured_at: str | None = None
    parser_version: str | None = None
    source_page_url: str | None = None
    download_url: str | None = None
    final_url: str | None = None
    content_type: str | None = None
    byte_size: int | None = None
