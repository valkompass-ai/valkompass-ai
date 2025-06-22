from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from analysis.embedding import EmbeddingClient
from model import Document, DocumentSegment


@pytest.fixture
def embedding_client():
    return EmbeddingClient()


@pytest.mark.asyncio
async def test_embed_documents_empty_list(embedding_client: EmbeddingClient):
    """Test embedding an empty list of documents."""
    documents = []
    updated_documents_generator = embedding_client.embed_documents(documents)
    updated_documents = [doc async for doc in updated_documents_generator]

    assert updated_documents == []


@pytest.mark.asyncio
async def test_embed_documents_no_segments(embedding_client: EmbeddingClient):
    """Test embedding a document with no segments."""
    documents = [
        Document(
            id="test-doc",
            raw_content="test content",
            path="test.txt",
            segments=[],
        )
    ]

    updated_documents_generator = embedding_client.embed_documents(documents)
    updated_documents = [doc async for doc in updated_documents_generator]

    assert len(updated_documents) == 1
    assert len(updated_documents[0].segments) == 0


@pytest.mark.asyncio
async def test_get_embedding_success(embedding_client: EmbeddingClient):
    """Test successful embedding generation with mocked API calls."""
    text = "Test text for actual embedding"
    text2 = "This is a much longer piece of text that is intended to be completely different from the first text. It should have a distinct meaning and structure to ensure that the generated embeddings are significantly different."

    # Mock different embeddings for different texts
    mock_embedding_1 = np.random.rand(1536).tolist()
    mock_embedding_2 = np.random.rand(1536).tolist()

    documents = [
        Document(
            id="test-doc",
            raw_content="",
            path="test.txt",
            segments=[
                DocumentSegment(
                    id="test-segment-1",
                    text=text,
                    start_index=0,
                    end_index=len(text),
                    page=1,
                ),
                DocumentSegment(
                    id="test-segment-2",
                    text=text2,
                    start_index=0,
                    end_index=len(text2),
                    page=1,
                ),
            ],
        )
    ]

    # Mock the OpenAI API call to return different embeddings
    with patch("openai.AsyncOpenAI") as mock_openai:
        mock_client = AsyncMock()
        mock_openai.return_value = mock_client

        # Mock embeddings response with different values for each text
        mock_client.embeddings.create = AsyncMock()
        mock_client.embeddings.create.side_effect = [
            AsyncMock(data=[AsyncMock(embedding=mock_embedding_1)]),
            AsyncMock(data=[AsyncMock(embedding=mock_embedding_2)]),
        ]

        updated_documents_generator = embedding_client.embed_documents(documents)
        updated_documents = [doc async for doc in updated_documents_generator]

    assert updated_documents is not None
    assert isinstance(updated_documents, list)
    assert len(updated_documents) == 1
    assert updated_documents[0].segments[0].embedding is not None
    assert updated_documents[0].segments[1].embedding is not None

    # Verify embeddings are different (converted to numpy arrays)
    embedding_1 = updated_documents[0].segments[0].embedding
    embedding_2 = updated_documents[0].segments[1].embedding
    assert not np.array_equal(embedding_1, embedding_2)
    assert len(embedding_1) == 1536
    assert len(embedding_2) == 1536
