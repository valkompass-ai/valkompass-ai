import pytest

from analysis.embedding import EmbeddingClient
from analysis.topic_modeling import BERTopic, extract_topics
from model import (
    DocumentSegment,
)


async def get_sample_documents() -> list[DocumentSegment]:
    """Provides a few sample DocumentSegment objects for testing."""
    embedding_client = EmbeddingClient()
    documents = [
        DocumentSegment(
            id="seg1",
            text="This is about cats and dogs.",
            start_index=0,
            end_index=28,
            page=1,
        ),
        DocumentSegment(
            id="seg2",
            text="The best pets are cats, not dogs.",
            start_index=29,
            end_index=63,
            page=1,
        ),
        DocumentSegment(
            id="seg3", text="I love my pet cat.", start_index=64, end_index=81, page=1
        ),
        DocumentSegment(
            id="seg4",
            text="A discussion about programming languages, like Python and Java.",
            start_index=82,
            end_index=152,
            page=1,
        ),
        DocumentSegment(
            id="seg5",
            text="Python is great for data science. Java is good for enterprise apps.",
            start_index=153,
            end_index=224,
            page=1,
        ),
        DocumentSegment(
            id="seg6",
            text="What is your favorite programming language? Mine is Python.",
            start_index=225,
            end_index=290,
            page=1,
        ),
        DocumentSegment(
            id="seg7",
            text="This is a very short and possibly outlier text.",
            start_index=291,
            end_index=338,
            page=2,
        ),
    ]
    # Ensure all segments get an ID and embedding for consistent testing
    for i, doc in enumerate(documents):
        if not doc.id:  # Assign if not already set (though above they are)
            doc.id = f"test_seg_{i + 1}"
        if doc.embedding is None:  # Simulate embedding if not present
            doc.embedding = await embedding_client.get_embedding(doc.text)
    return documents


@pytest.fixture
def segments_empty() -> list[DocumentSegment]:
    return []


@pytest.mark.asyncio
async def segments_one_topic() -> list[DocumentSegment]:
    embedding_client = EmbeddingClient()
    segments = [
        DocumentSegment(
            id="topic_seg1",
            text="Topic modeling is fun.",
            start_index=0,
            end_index=24,
            page=1,
        ),
        DocumentSegment(
            id="topic_seg2",
            text="Fun topic modeling helps analyze text.",
            start_index=25,
            end_index=63,
            page=1,
        ),
        DocumentSegment(
            id="topic_seg3",
            text="Analyzing text with topic models is useful.",
            start_index=64,
            end_index=109,
            page=1,
        ),
    ]
    for seg in segments:  # Ensure embeddings for these segments too
        seg.embedding = await embedding_client.get_embedding(seg.text)
    return segments


# --- Tests for extract_topics ---


@pytest.mark.asyncio
async def test_extract_topics_basic():
    sample_segments = await get_sample_documents()
    """Test basic functionality of extract_topics."""
    if not sample_segments:
        pytest.skip("Sample segments are empty, skipping test.")

    # Filter for segments that would be processed (have text and embedding)
    # In this test setup, all segments from get_sample_documents should be valid
    valid_segments_for_modeling = [
        seg
        for seg in sample_segments
        if seg.text and seg.text.strip() and seg.embedding is not None
    ]
    if not valid_segments_for_modeling:
        pytest.skip("No valid segments with text and embeddings for modeling.")

    # Using small min_topic_size to increase chance of topics with few docs
    topic_model, segment_topic_map = extract_topics(sample_segments, min_topic_size=2)

    assert isinstance(topic_model, BERTopic), (
        "topic_model should be a BERTopic instance."
    )
    assert isinstance(segment_topic_map, dict), (
        "segment_topic_map should be a dictionary."
    )

    # Check that the map contains IDs of the segments that were actually processed
    # and that topic IDs are integers
    for seg_id, topic_id in segment_topic_map.items():
        assert isinstance(seg_id, str), "Segment ID in map should be a string."
        assert isinstance(topic_id, int), "Topic ID in map should be an integer."
        assert seg_id in [s.id for s in valid_segments_for_modeling], (
            f"Segment ID {seg_id} from map not in original valid segments."
        )

    # Simulate assigning topic_ids back to segments and check
    for seg in sample_segments:
        if seg.id in segment_topic_map:
            seg.topic_id = segment_topic_map[seg.id]

    # Verify that segments that were part of modeling now have a topic_id
    # and that it's an integer (or None if it was an outlier or not processed)
    for seg in valid_segments_for_modeling:
        if seg.id in segment_topic_map:  # Only check those that were mapped
            assert isinstance(seg.topic_id, int), (
                f"Segment {seg.id} should have an integer topic_id after assignment."
            )
        # If a segment was valid but its ID is not in the map, it's an issue with extract_topics
        # or it was filtered out by BERTopic (e.g. became an outlier and BERTopic assigned -1,
        # which is a valid int).
        # The check `seg_id in [s.id for s in valid_segments_for_modeling]` above covers this.

    # Check if the model is somewhat fitted (has some topics)
    topic_info = topic_model.get_topic_info()
    assert not topic_info.empty, (
        "Topic model should have generated some topic information."
    )
    # Further checks on topic_info could be added if specific topic outputs were expected,
    # but this is generally hard to do without fixed seeds and very stable data/embeddings.
