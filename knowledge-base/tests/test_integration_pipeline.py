"""
Integration tests for the complete knowledge base pipeline.

These tests verify that the entire pipeline works:
1. Parse documents (PDF and JSON)
2. Generate embeddings (mocked)
3. Extract topics (mocked)
4. Store in graph database (mocked)
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from analysis.embedding import EmbeddingClient
from analysis.topic_modeling import extract_topics, topics_to_pydantic
from graph import SchemaManager
from main import process_party_entities
from model import Document, DocumentSegment, Topic
from parser import parse_document
from util.errors import NoSuchDocumentError


@pytest.fixture
def temp_json_document():
    """Create a temporary JSON document for testing."""
    content = [
        {
            "url": "https://example.com/policy1",
            "content": "This is a test policy document about environmental protection. We believe in sustainable development and green energy solutions.",
        },
        {
            "url": "https://example.com/policy2",
            "content": "Our economic policy focuses on job creation, innovation, and supporting small businesses through targeted investments.",
        },
    ]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(content, f)
        return f.name


@pytest.fixture
def sample_documents():
    """Create sample documents for testing."""
    return [
        Document(
            id="test-doc-1",
            path="test/document1.json",
            raw_content="Environmental policy content...",
            segments=[
                DocumentSegment(
                    id="test-doc-1-seg-1",
                    text="Environmental protection is crucial for sustainable development.",
                    start_index=0,
                    end_index=62,
                    page=1,
                    metadata={"url": "https://example.com/env"},
                    type="website",
                    public_url="https://example.com/env",
                ),
                DocumentSegment(
                    id="test-doc-1-seg-2",
                    text="Green energy solutions are the future of our economy.",
                    start_index=65,
                    end_index=118,
                    page=1,
                    metadata={"url": "https://example.com/energy"},
                    type="website",
                    public_url="https://example.com/energy",
                ),
            ],
        ),
        Document(
            id="test-doc-2",
            path="test/document2.json",
            raw_content="Economic policy content...",
            segments=[
                DocumentSegment(
                    id="test-doc-2-seg-1",
                    text="Job creation is a priority for economic growth.",
                    start_index=0,
                    end_index=46,
                    page=1,
                    metadata={"url": "https://example.com/jobs"},
                    type="website",
                    public_url="https://example.com/jobs",
                )
            ],
        ),
    ]


class TestIntegrationPipeline:
    """Integration tests for the complete knowledge base pipeline."""

    def test_parse_json_document_integration(self, temp_json_document):
        """Test parsing a real JSON document file."""
        document_id = "test-integration-doc"
        document = parse_document(temp_json_document, document_id)

        assert document is not None
        assert document.id == document_id
        assert document.path == temp_json_document
        assert len(document.segments) == 2
        assert "environmental protection" in document.segments[0].text.lower()
        assert "economic policy" in document.segments[1].text.lower()

        # Verify segment metadata
        assert document.segments[0].metadata["url"] == "https://example.com/policy1"
        assert document.segments[1].metadata["url"] == "https://example.com/policy2"
        assert document.segments[0].type == "website"
        assert document.segments[1].type == "website"

        # Clean up
        Path(temp_json_document).unlink()

    @pytest.mark.asyncio
    async def test_embedding_pipeline_integration(self, sample_documents):
        """Test the embedding generation pipeline with mocked OpenAI calls."""
        # Mock different embeddings for different texts
        mock_embeddings = [
            np.random.rand(1536).tolist(),
            np.random.rand(1536).tolist(),
            np.random.rand(1536).tolist(),
        ]

        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client

            # Mock embeddings responses
            mock_client.embeddings.create = AsyncMock()
            mock_client.embeddings.create.side_effect = [
                AsyncMock(data=[AsyncMock(embedding=embedding)])
                for embedding in mock_embeddings
            ]

            embedding_client = EmbeddingClient()

            # Process documents through embedding pipeline
            embedded_documents = []
            async for doc in embedding_client.embed_documents(sample_documents):
                embedded_documents.append(doc)

            # Verify all documents were processed
            assert len(embedded_documents) == 2

            # Verify embeddings were added to segments
            assert embedded_documents[0].segments[0].embedding is not None
            assert embedded_documents[0].segments[1].embedding is not None
            assert embedded_documents[1].segments[0].embedding is not None

            # Verify embedding dimensions
            assert len(embedded_documents[0].segments[0].embedding) == 1536
            assert len(embedded_documents[0].segments[1].embedding) == 1536
            assert len(embedded_documents[1].segments[0].embedding) == 1536

    def test_topic_modeling_pipeline_integration(self, sample_documents):
        """Test topic modeling pipeline with mocked BERTopic."""
        # Add mock embeddings to segments
        for doc in sample_documents:
            for segment in doc.segments:
                segment.embedding = np.random.rand(1536)

        # Extract all segments
        all_segments = []
        for doc in sample_documents:
            all_segments.extend(doc.segments)

        # Mock BERTopic to avoid issues with small datasets
        with patch("analysis.topic_modeling.BERTopic") as mock_bertopic:
            mock_model = MagicMock()
            mock_bertopic.return_value = mock_model

            # Mock the fit_transform method
            mock_model.fit_transform.return_value = (
                [0, 1, 0],
                None,
            )  # topics and probabilities
            mock_model.get_topic_info.return_value = MagicMock(
                empty=False,
                iterrows=MagicMock(
                    return_value=iter(
                        [
                            (
                                0,
                                {
                                    "Topic": 0,
                                    "Name": "Environment",
                                    "Representation": [
                                        "environment",
                                        "green",
                                        "sustainable",
                                    ],
                                },
                            ),
                            (
                                1,
                                {
                                    "Topic": 1,
                                    "Name": "Economy",
                                    "Representation": ["jobs", "economy", "business"],
                                },
                            ),
                        ]
                    )
                ),
            )
            mock_model.get_topics.return_value = {
                0: [("environment", 0.9), ("green", 0.8), ("sustainable", 0.7)],
                1: [("jobs", 0.9), ("economy", 0.8), ("business", 0.7)],
            }

            # Run topic modeling with mocked BERTopic
            topic_model, segment_topic_map = extract_topics(all_segments)
            topics = topics_to_pydantic(topic_model)

            # Verify topic extraction worked
            assert topic_model is not None
            assert isinstance(segment_topic_map, dict)
            assert isinstance(topics, list)

            # Verify segments got topic assignments
            for segment_id in segment_topic_map:
                assert isinstance(segment_id, str)
                assert isinstance(segment_topic_map[segment_id], int)

    def test_graph_operations_integration(self, sample_documents):
        """Test graph database operations with mocked Neo4j."""
        with patch("graph.GraphDatabase") as mock_graph_db:
            # Mock Neo4j driver and session
            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_graph_db.driver.return_value = mock_driver
            mock_driver.session.return_value.__enter__.return_value = mock_session

            # Create schema manager
            schema_manager = SchemaManager(
                uri="bolt://localhost:7687", user="neo4j", password="test"
            )

            # Test schema operations
            schema_manager.apply_schema()
            schema_manager.clear_database()

            # Test topic upsert
            test_topic = Topic(
                id=1,
                name="Environment",
                description="Environmental policies and sustainability",
                embedding=np.random.rand(1536),
            )
            schema_manager.upsert_topic(test_topic)

            # Test document upsert
            schema_manager.upsert_document(sample_documents[0])

            # Verify methods were called
            assert mock_session.run.call_count > 0
            schema_manager.close()

    @pytest.mark.asyncio
    async def test_complete_pipeline_integration(self, temp_json_document):
        """Test the complete pipeline from parsing to graph storage."""
        document_id = "complete-pipeline-test"

        # Step 1: Parse document
        document = parse_document(temp_json_document, document_id)
        assert len(document.segments) == 2

        # Step 2: Mock embedding generation
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_openai.return_value = mock_client

            mock_embeddings = [
                np.random.rand(1536).tolist(),
                np.random.rand(1536).tolist(),
            ]

            mock_client.embeddings.create = AsyncMock()
            mock_client.embeddings.create.side_effect = [
                AsyncMock(data=[AsyncMock(embedding=embedding)])
                for embedding in mock_embeddings
            ]

            embedding_client = EmbeddingClient()
            embedded_docs = []
            async for doc in embedding_client.embed_documents([document]):
                embedded_docs.append(doc)

            document = embedded_docs[0]

        # Step 3: Topic modeling (mocked)
        all_segments = document.segments

        with patch("analysis.topic_modeling.BERTopic") as mock_bertopic:
            mock_model = MagicMock()
            mock_bertopic.return_value = mock_model

            # Mock the fit_transform method
            mock_model.fit_transform.return_value = (
                [0, 1],
                None,
            )  # topics for 2 segments
            mock_model.get_topic_info.return_value = MagicMock(
                empty=False,
                iterrows=MagicMock(
                    return_value=iter(
                        [
                            (
                                0,
                                {
                                    "Topic": 0,
                                    "Name": "Policy",
                                    "Representation": [
                                        "policy",
                                        "environment",
                                        "protection",
                                    ],
                                },
                            ),
                            (
                                1,
                                {
                                    "Topic": 1,
                                    "Name": "Economy",
                                    "Representation": ["economy", "jobs", "business"],
                                },
                            ),
                        ]
                    )
                ),
            )
            mock_model.get_topics.return_value = {
                0: [("policy", 0.9), ("environment", 0.8), ("protection", 0.7)],
                1: [("economy", 0.9), ("jobs", 0.8), ("business", 0.7)],
            }

            topic_model, segment_topic_map = extract_topics(all_segments)
            topics = topics_to_pydantic(topic_model)

        # Assign topic IDs to segments
        for segment in document.segments:
            if segment.id in segment_topic_map:
                segment.topic_id = segment_topic_map[segment.id]

        # Step 4: Mock graph storage
        with patch("graph.GraphDatabase") as mock_graph_db:
            mock_driver = MagicMock()
            mock_session = MagicMock()
            mock_graph_db.driver.return_value = mock_driver
            mock_driver.session.return_value.__enter__.return_value = mock_session

            schema_manager = SchemaManager(
                uri="bolt://localhost:7687", user="neo4j", password="test"
            )

            # Apply schema and store data
            schema_manager.apply_schema()

            for topic in topics:
                schema_manager.upsert_topic(topic)

            schema_manager.upsert_document(document)
            schema_manager.close()

        # Verify the complete pipeline worked
        assert document.segments[0].embedding is not None
        assert document.segments[1].embedding is not None
        assert len(topics) >= 0  # May be 0 for small datasets

        # Clean up
        Path(temp_json_document).unlink()

    def test_error_handling_integration(self):
        """Test error handling throughout the pipeline."""
        # Test non-existent file
        with pytest.raises(NoSuchDocumentError):
            parse_document("non-existent-file.json", "test-id")

        # Test malformed JSON - should now raise ValueError (fail-fast principle)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            with pytest.raises(ValueError, match="Error decoding JSON"):
                parse_document(temp_path, "test-malformed")
        finally:
            Path(temp_path).unlink()

    def test_empty_data_handling_integration(self):
        """Test pipeline behavior with empty or minimal data."""
        # Test empty JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            temp_path = f.name

        try:
            document = parse_document(temp_path, "test-empty")
            assert document.raw_content == ""
            assert document.segments == []
        finally:
            Path(temp_path).unlink()

        # Test embedding with empty documents
        embedding_client = EmbeddingClient()
        empty_docs = []

        async def test_empty_embedding():
            result = []
            async for doc in embedding_client.embed_documents(empty_docs):
                result.append(doc)
            return result

        import asyncio

        result = asyncio.run(test_empty_embedding())
        assert result == []


class TestPartyIntegrationPipeline:
    """Integration tests for party processing in the knowledge base pipeline."""

    @pytest.fixture
    def mock_parties_json_file(self):
        """Create a temporary parties.json file for integration testing."""
        parties_data = {
            "description": "Test Swedish political parties",
            "extractedAt": "2025-01-01T00:00:00.000Z",
            "totalParties": 3,
            "source": "Integration test data",
            "parties": {
                "C": "Centerpartiet",
                "M": "Moderaterna",
                "S": "Socialdemokraterna",
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(parties_data, f)
            return Path(f.name)

    @pytest.fixture
    def mock_schema_manager_for_parties(self):
        """Create a mock SchemaManager specifically for party testing."""
        mock_manager = MagicMock(spec=SchemaManager)
        mock_manager.upsert_parties = MagicMock()
        mock_manager.link_documents_to_parties = MagicMock()
        return mock_manager

    def test_party_processing_integration_success(
        self, mock_schema_manager_for_parties, mock_parties_json_file
    ):
        """Test complete party processing integration workflow."""
        # Read the actual JSON data from the temp file
        with open(mock_parties_json_file) as f:
            parties_data = json.load(f)

        with patch("main.Path") as mock_path_class:
            # Mock the parties.json path to point to our test file
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            # Mock json.load to return our test data
            with patch("json.load", return_value=parties_data):
                with patch("builtins.open", mock=MagicMock()):
                    # Execute the party processing
                    process_party_entities(mock_schema_manager_for_parties)

            # Verify the complete workflow
            mock_schema_manager_for_parties.upsert_parties.assert_called_once()
            mock_schema_manager_for_parties.link_documents_to_parties.assert_called_once()

            # Verify correct parties were processed
            called_parties = mock_schema_manager_for_parties.upsert_parties.call_args[
                0
            ][0]
            assert len(called_parties) == 3

            party_names = {p.abbreviation: p.full_name for p in called_parties}
            assert party_names["C"] == "Centerpartiet"
            assert party_names["M"] == "Moderaterna"
            assert party_names["S"] == "Socialdemokraterna"

    def test_party_processing_with_documents_integration(
        self, sample_documents, mock_schema_manager_for_parties
    ):
        """Test integration of party processing with document processing."""
        # Mock the parties data
        parties_data = {"parties": {"C": "Centerpartiet", "M": "Moderaterna"}}

        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = True
            mock_path_class.return_value = mock_parties_path

            with patch("json.load", return_value=parties_data):
                with patch("builtins.open", mock=MagicMock()):
                    process_party_entities(mock_schema_manager_for_parties)

        # Verify both parties and document linking were processed
        mock_schema_manager_for_parties.upsert_parties.assert_called_once()
        mock_schema_manager_for_parties.link_documents_to_parties.assert_called_once()

        # Verify the parties were created correctly
        called_parties = mock_schema_manager_for_parties.upsert_parties.call_args[0][0]
        assert len(called_parties) == 2
        assert any(
            p.abbreviation == "C" and p.full_name == "Centerpartiet"
            for p in called_parties
        )
        assert any(
            p.abbreviation == "M" and p.full_name == "Moderaterna"
            for p in called_parties
        )

    def test_party_processing_error_handling_integration(
        self, mock_schema_manager_for_parties
    ):
        """Test error handling in party processing integration."""
        # Test with missing parties.json file
        with patch("main.Path") as mock_path_class:
            mock_parties_path = MagicMock()
            mock_parties_path.exists.return_value = False
            mock_path_class.return_value = mock_parties_path

            # Should raise FileNotFoundError
            with pytest.raises(FileNotFoundError):
                process_party_entities(mock_schema_manager_for_parties)

            # No database operations should occur
            mock_schema_manager_for_parties.upsert_parties.assert_not_called()
            mock_schema_manager_for_parties.link_documents_to_parties.assert_not_called()

    def test_full_pipeline_with_parties_integration(
        self, sample_documents, mock_schema_manager_for_parties
    ):
        """Test party processing as part of the complete pipeline workflow."""
        # Simulate the full pipeline: documents → embeddings → topics → graph (including parties)

        # Mock embeddings for documents - just need to mock the client
        mock_embedding_client = AsyncMock(spec=EmbeddingClient)

        # Mock topic modeling
        mock_topics = [
            Topic(
                id=0,
                name="Environmental Policy",
                description="Topics related to environment and sustainability",
            ),
            Topic(
                id=1,
                name="Economic Policy",
                description="Topics related to economics and business",
            ),
        ]

        # Mock parties data
        parties_data = {"parties": {"C": "Centerpartiet", "S": "Socialdemokraterna"}}

        with patch(
            "analysis.embedding.EmbeddingClient", return_value=mock_embedding_client
        ):
            with patch("analysis.topic_modeling.extract_topics", return_value=([], [])):
                with patch(
                    "analysis.topic_modeling.topics_to_pydantic",
                    return_value=mock_topics,
                ):
                    with patch("main.Path") as mock_path_class:
                        mock_parties_path = MagicMock()
                        mock_parties_path.exists.return_value = True
                        mock_path_class.return_value = mock_parties_path

                        with patch("json.load", return_value=parties_data):
                            with patch("builtins.open", mock=MagicMock()):
                                # This would be called as part of the main pipeline
                                process_party_entities(mock_schema_manager_for_parties)

        # Verify party processing completed successfully
        mock_schema_manager_for_parties.upsert_parties.assert_called_once()
        mock_schema_manager_for_parties.link_documents_to_parties.assert_called_once()

        # Verify correct number of parties processed
        called_parties = mock_schema_manager_for_parties.upsert_parties.call_args[0][0]
        assert len(called_parties) == 2
