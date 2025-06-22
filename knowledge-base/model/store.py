import json
from pathlib import Path

from tqdm import tqdm

from . import (
    Document,
    Topic,
)  # Assuming Document and Topic are in __init__.py in the same package


def store_documents_as_json(documents: list[Document], output_dir: Path):
    """
    Serializes a list of Document objects to pretty-printed JSON files.
    Each document's path attribute is assumed to be relative to the project root.

    Args:
        documents: A list of Document objects to serialize.
        output_dir: The directory where JSON files will be stored.
    """
    if not documents:
        print("No documents to store.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Storing {len(documents)} documents as JSON in {output_dir}...")

    for doc in tqdm(documents, desc="Storing JSON documents", unit="doc"):
        original_path = Path(doc.path)
        # Use a consistent naming convention, e.g., based on the original stem
        # and potentially adding a suffix if it's an intermediate or final version.
        json_filename = original_path.stem + ".json"
        output_filepath = output_dir / json_filename
        # Pydantic's model_dump_json handles np.ndarray by converting to list
        json_string = doc.model_dump_json(indent=2)
        with open(output_filepath, "w", encoding="utf-8") as f:
            f.write(json_string)

    print(f"Successfully stored documents in {output_dir}.")


def store_document_as_json(document: Document, output_dir: Path):
    """
    Serializes a single Document object to a pretty-printed JSON file.
    The document's path attribute is assumed to be relative to the project root.

    Args:
        document: The Document object to serialize.
        output_dir: The directory where the JSON file will be stored.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    original_path = Path(document.path)
    json_filename = original_path.stem + ".json"
    output_filepath = output_dir / json_filename

    # Pydantic's model_dump_json handles np.ndarray by converting to list
    json_string = document.model_dump_json(indent=2)
    with open(output_filepath, "w", encoding="utf-8") as f:
        f.write(json_string)


def load_documents_from_json(input_dir: Path) -> list[Document]:
    """
    Loads Document objects from JSON files in a specified directory.

    Args:
        input_dir: The directory to scan for JSON files.

    Returns:
        A list of loaded Document objects.
    """
    json_files = list(input_dir.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in {input_dir}.")
        return []

    loaded_documents: list[Document] = []
    print(f"Loading {len(json_files)} documents from JSON in {input_dir}...")

    for json_file_path in tqdm(json_files, desc="Loading JSON documents", unit="doc"):
        with open(json_file_path, encoding="utf-8") as f:
            data = json.load(f)
            # Pydantic will attempt to convert list back to np.ndarray for 'embedding'
            # if DocumentSegment's embedding field is type-hinted as np.ndarray
            document_obj = Document(**data)
            loaded_documents.append(document_obj)

    print(f"Successfully loaded {len(loaded_documents)} documents from {input_dir}.")
    return loaded_documents


def store_topics_as_json(
    topics: list[Topic], output_dir: Path, filename: str = "topics.json"
):
    """
    Serializes a list of Topic objects to a single JSON file.

    Args:
        topics: A list of Topic objects to serialize.
        output_dir: The directory where the JSON file will be stored.
        filename: The name of the JSON file.
    """
    if not topics:
        print("No topics to store.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    output_filepath = output_dir / filename

    # Convert list of Pydantic models to a list of dicts, then dump to JSON
    topics_data = [topic.model_dump(mode="json") for topic in topics]
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(topics_data, f, indent=2, ensure_ascii=False)
    print(f"Successfully stored {len(topics)} topics in {output_filepath}.")


def load_topics_from_json(
    input_dir: Path, filename: str = "topics.json"
) -> list[Topic]:
    """
    Loads Topic objects from a JSON file in a specified directory.

    Args:
        input_dir: The directory containing the JSON file.
        filename: The name of the JSON file.

    Returns:
        A list of loaded Topic objects.
    """
    input_filepath = input_dir / filename
    if not input_filepath.exists():
        print(f"Topics file not found: {input_filepath}")
        return []

    loaded_topics: list[Topic] = []
    print(f"Loading topics from {input_filepath}...")

    with open(input_filepath, encoding="utf-8") as f:
        topics_data = json.load(f)
        for topic_data in tqdm(topics_data, desc="Loading JSON topics", unit="topic"):
            # Pydantic will use field_validator for 'embedding' to convert list to np.ndarray
            topic_obj = Topic(**topic_data)
            loaded_topics.append(topic_obj)

    print(f"Successfully loaded {len(loaded_topics)} topics from {input_filepath}.")
    return loaded_topics
