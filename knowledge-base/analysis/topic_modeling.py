import nltk
import numpy as np
import spacy
from bertopic import BERTopic
from langdetect import LangDetectException, detect
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import CountVectorizer

from model import DocumentSegment, Topic

# Ensure NLTK data is available
try:
    nltk.data.find("corpora/stopwords")
except LookupError:  # Catch LookupError if resource not found
    nltk.download("stopwords", quiet=True)

# Prepare combined stopword list for English & Swedish
SW_STOPWORDS = list(stopwords.words("swedish"))
EN_STOPWORDS = list(stopwords.words("english"))
COMBINED_STOPWORDS = list(
    set(SW_STOPWORDS) | set(EN_STOPWORDS)
)  # Use set union for unique words


# Load spaCy models for English and Swedish (download if missing)
try:
    nlp_en = spacy.load("en_core_web_sm", disable=["parser", "ner"])
except OSError:
    spacy.cli.download("en_core_web_sm")
    nlp_en = spacy.load("en_core_web_sm", disable=["parser", "ner"])

try:
    nlp_sv = spacy.load("sv_core_news_sm", disable=["parser", "ner"])
except OSError:
    spacy.cli.download("sv_core_news_sm")
    nlp_sv = spacy.load("sv_core_news_sm", disable=["parser", "ner"])


def lemmatize_and_tokenize(doc: str) -> list[str]:
    """
    Detect language of `doc`, run through the appropriate spaCy pipeline,
    extract lemmas for alphabetic, non-stopword tokens, and return as a token list.
    """
    text = doc.lower().strip()
    # Fallback to English if detection fails
    try:
        lang = detect(text)
    except LangDetectException:
        lang = "en"
    # Choose pipeline
    nlp = nlp_sv if lang.startswith("sv") else nlp_en
    spacy_doc = nlp(text)
    lemmas = [
        token.lemma_
        for token in spacy_doc
        if token.is_alpha and token.lemma_ not in COMBINED_STOPWORDS
    ]
    return lemmas


def extract_topics(
    segments: list[DocumentSegment],
    nr_topics: int | None = None,
    min_topic_size: int = 10,
    top_n_words: int = 10,
) -> tuple[BERTopic, dict[str, int]]:
    """
    Extracts topics from a list of DocumentSegment objects and returns the fitted BERTopic model
    along with a mapping of segment IDs to their assigned topic IDs.
    Only segments with non-empty text and existing embeddings are used for topic modeling.
    """
    # Filter segments that have text and embeddings
    valid_segments = [
        seg
        for seg in segments
        if seg.text and seg.text.strip() and seg.embedding is not None
    ]

    if not valid_segments:
        raise ValueError(
            "No valid segments (with text and embeddings) to analyze. Topic modeling requires textual input and embeddings."
        )

    texts = [seg.text for seg in valid_segments]
    # Ensure embeddings is a 2D array
    embeddings = np.array(
        [seg.embedding for seg in valid_segments if seg.embedding is not None]
    )
    if embeddings.ndim == 1:  # Should not happen if embeddings are correctly generated
        print(
            f"Warning: Embeddings array is 1D, attempting to reshape. Shape: {embeddings.shape}"
        )
        if embeddings.shape[0] > 0 and embeddings.shape[0] % len(valid_segments) == 0:
            # This is a heuristic, assuming all embeddings have the same known dimension if it was flattened
            try:
                # Attempt to infer embedding dimension, e.g. 1536 for text-embedding-3-small
                # This part is risky without knowing the exact embedding dimension used.
                # For now, we'll rely on UMAP/PCA to handle it or error out if incompatible.
                # A better fix would be to ensure embeddings are always stored/retrieved as 2D.
                pass  # PCA might handle it or fail gracefully.
            except Exception as e:
                print(
                    f"Could not reshape embeddings, proceeding with 1D array which might fail: {e}"
                )

    print("Vectorizing...")
    vectorizer = CountVectorizer(
        tokenizer=lemmatize_and_tokenize,
        token_pattern=None,  # disable default pattern so tokenizer is used
        ngram_range=(1, 2),
        max_df=0.90,
        min_df=0.05,
        max_features=2_000,
    )

    print("Fitting BERTopic...")
    topic_model = BERTopic(
        nr_topics=nr_topics,
        vectorizer_model=vectorizer,
        min_topic_size=min_topic_size,
        top_n_words=top_n_words,
        low_memory=True,
        language="multilingual",
    )

    # Fit using reduced embeddings
    topic_assignments, _ = topic_model.fit_transform(texts, embeddings)
    print("Fitted BERTopic.")

    # Create a map from segment ID to topic ID
    segment_id_to_topic_id_map: dict[str, int] = {}
    for segment, topic_id in zip(valid_segments, topic_assignments, strict=False):
        if (
            segment.id is None
        ):  # Should ideally not happen if DocumentSegment.id is always set
            print(
                f"Warning: Segment encountered without an ID during topic assignment: {segment.text[:50]}..."
            )
            continue
        segment_id_to_topic_id_map[segment.id] = int(topic_id)
        # segment.topic_id = int(topic_id) # REMOVED in-place modification

    return topic_model, segment_id_to_topic_id_map


def topics_to_pydantic(topic_model: BERTopic) -> list[Topic]:
    """
    Converts topics from a fitted BERTopic model to a list of Pydantic Topic models.
    Builds a human-readable name and description for each topic
    based on its top keywords.
    Skips the outlier topic (ID -1).
    Assigns topic embeddings from the model.
    """
    pydantic_topics: list[Topic] = []
    if not hasattr(topic_model, "get_topic_info") or not hasattr(
        topic_model, "get_topic"
    ):
        print(
            "Warning: Topic model does not seem to be fitted or is a dummy model. Returning empty topics."
        )
        return pydantic_topics

    topic_embeddings_available = (
        hasattr(topic_model, "topic_embeddings_")
        and topic_model.topic_embeddings_ is not None
    )
    if not topic_embeddings_available:
        print(
            "Warning: topic_model.topic_embeddings_ is not available. Topics will be created without embeddings."
        )

    topic_info_df = topic_model.get_topic_info()
    if topic_info_df.empty:
        return pydantic_topics

    for df_idx, row in topic_info_df.iterrows():  # df_idx is the DataFrame index
        tid = row["Topic"]
        if tid == -1:  # Skip outlier topic
            continue

        kw_scores = topic_model.get_topic(tid)
        if not kw_scores:
            # This case might occur if a topic ID exists in get_topic_info but not in get_topic
            # Or if it's an empty topic.
            print(f"Warning: No keywords found for topic {tid}. Skipping.")
            continue

        # Filter out empty or whitespace-only strings from keywords
        keywords = [word for word, _ in kw_scores[:5] if word and word.strip()]

        if len(keywords) >= 2:
            name = " / ".join(keywords[:2])
        elif len(keywords) == 1:
            name = keywords[0]
        else:
            name = f"Topic {tid}"

        description = "Keywords: " + ", ".join(keywords)
        if not keywords:
            description = "No keywords found for this topic."  # Should be rare due to earlier continue

        topic_embedding = None
        if topic_embeddings_available:
            # The df_idx from iterrows() on get_topic_info() corresponds to the
            # row index in topic_embeddings_ because topics are sorted.
            if 0 <= df_idx < len(topic_model.topic_embeddings_):
                topic_embedding = topic_model.topic_embeddings_[df_idx]
            else:
                print(
                    f"Warning: DataFrame index {df_idx} is out of bounds for topic_embeddings_ (len {len(topic_model.topic_embeddings_)}). Topic {tid} will not have an embedding."
                )

        pydantic_topics.append(
            Topic(
                id=int(tid),
                name=name,
                description=description,
                embedding=topic_embedding,
            )
        )

    return pydantic_topics
