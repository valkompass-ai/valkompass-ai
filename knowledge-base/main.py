import argparse
import asyncio
import logging
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

import json

from analysis.embedding import EmbeddingClient
from analysis.topic_modeling import extract_topics, topics_to_pydantic
from graph import SchemaManager
from model import Document, DocumentSegment, Party, Topic
from model.store import (
    load_documents_from_json,
    load_topics_from_json,
    store_document_as_json,
    store_documents_as_json,
    store_topics_as_json,
)
from parser import parse_document
from parser.source_metadata import stable_document_id_for_path
from sources.raw_snapshot_package import verify_raw_snapshots
from util.errors import NoSuchDocumentError

load_dotenv()

# Project root directory
PROJECT_ROOT_DIR = Path(__file__).parent.parent
DOCUMENTS_BASE_DIR_ABS = Path(__file__).parent / "documents"
STRUCTURED_KB_OUTPUT_DIR = Path(__file__).parent / "structured-knowledge-base"
STRUCTURED_DOCS_OUTPUT_DIR = (
    Path(__file__).parent / "structured-knowledge-base" / "documents"
)
SOURCE_SNAPSHOTS_DIR = Path(__file__).parent / "source-snapshots"
SOURCE_REGISTRY_PATH = Path(__file__).parent / "source-registry.json"
SOURCE_SNAPSHOT_MANIFEST_PATH = SOURCE_SNAPSHOTS_DIR / "manifest.json"
RAW_SNAPSHOT_PACKAGE_MANIFEST_PATH = (
    SOURCE_SNAPSHOTS_DIR / "raw-snapshots-package.json"
)
PDF_SOURCE_DOCUMENTS_MANIFEST_PATH = Path(__file__).parent / (
    "source-documents-manifest.json"
)


def clean_structured_documents_dir(output_dir: Path) -> None:
    """Remove generated structured document JSON before a fresh parse."""
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def verify_source_snapshot_package_available() -> None:
    """Verify raw snapshot package/hash when the package metadata is present."""
    package_archive = SOURCE_SNAPSHOTS_DIR / "raw-snapshots.tar.gz"
    if not package_archive.exists() or not RAW_SNAPSHOT_PACKAGE_MANIFEST_PATH.exists():
        logger.warning(
            "Raw source snapshot package is not present; skipping package verification."
        )
        return

    args = argparse.Namespace(
        archive=str(package_archive),
        package_manifest=str(RAW_SNAPSHOT_PACKAGE_MANIFEST_PATH),
        source_manifest=str(SOURCE_SNAPSHOT_MANIFEST_PATH),
        sha256=str(SOURCE_SNAPSHOTS_DIR / "raw-snapshots.tar.gz.sha256"),
    )
    verify_raw_snapshots(args)


def process_party_entities(schema_manager: SchemaManager) -> None:
    """Create party nodes and link them to documents"""
    logger.info("Processing party entities...")

    # Load parties from JSON file
    parties_path = Path("documents/voting/parties.json")
    if not parties_path.exists():
        logger.error(f"Parties file not found at {parties_path}")
        raise FileNotFoundError(f"Parties file not found at {parties_path}")

    with open(parties_path, encoding="utf-8") as f:
        parties_data = json.load(f)

    # Create Party objects
    parties = []
    for abbr, full_name in parties_data["parties"].items():
        if abbr != "-":  # Skip "Partilös" (independent)
            parties.append(Party(abbreviation=abbr, full_name=full_name))

    # Import to Neo4j
    schema_manager.upsert_parties(parties)
    logger.info(f"Created {len(parties)} party nodes")

    # Create relationships between parties and documents
    schema_manager.link_sources_to_parties()
    schema_manager.link_documents_to_parties()
    logger.info("Linked parties to their authored documents")


def load_and_parse_documents(
    documents_dir_abs: Path = DOCUMENTS_BASE_DIR_ABS,
    project_root: Path = PROJECT_ROOT_DIR,
) -> list[Document]:
    """
    Scans a directory for documents, parses them, and returns a list of Document objects
    with paths relative to the project root.

    Supported file types are those handled by the `parse_document` function (e.g., .pdf, .txt).
    Uses tqdm to display a progress bar.

    Args:
        documents_dir_abs: The directory to scan for documents.
        project_root: The project root directory for making paths relative.

    Returns:
        A list of Document objects.
    """
    doc_paths_abs: list[Path] = []
    # Recursively find all files in the documents_dir
    # Add more extensions here if needed, e.g., "*.txt", "*.docx"
    supported_extensions = ["*.pdf", "*.json"]
    for ext in supported_extensions:
        doc_paths_abs.extend(list(documents_dir_abs.rglob(ext)))

    # Remove generated voting data and the legacy website-policy dump format.
    # Current website policy sources live under documents/{party}/web/ and carry
    # source-registry snapshot metadata.
    doc_paths_abs = [
        path
        for path in doc_paths_abs
        if "voting" not in str(path).lower()
        and "web-page-policies" not in str(path).lower()
    ]

    if not doc_paths_abs:
        print(
            f"No documents found in {documents_dir_abs} with extensions: {supported_extensions}"
        )
        return []

    parsed_documents: list[Document] = []
    print(f"Found {len(doc_paths_abs)} documents. Starting parsing...")

    for doc_path_abs in tqdm(doc_paths_abs, desc="Parsing documents", unit="doc"):
        try:
            # Parse document using a stable path-derived ID so structured JSON and
            # graph nodes remain stable across re-runs.
            document_obj = parse_document(
                str(doc_path_abs), stable_document_id_for_path(doc_path_abs)
            )

            relative_path = doc_path_abs.relative_to(project_root)
            document_obj.path = str(
                relative_path
            )  # Update the path in the Document object

            parsed_documents.append(document_obj)
        except NoSuchDocumentError as e:
            logger.warning(f"Skipping (not found): {doc_path_abs}. Error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error parsing {doc_path_abs}: {e}")

    logger.info(
        f"Successfully parsed {len(parsed_documents)} out of {len(doc_paths_abs)} documents."
    )
    return parsed_documents


async def main():
    """Main entry point for the knowledge-base processing script."""
    parser = argparse.ArgumentParser(description="Knowledge-base processing CLI.")
    parser.add_argument(
        "--actions",
        nargs="+",
        choices=[
            "verify-sources",
            "parse",
            "embed",
            "topicmodel",
            "graph",
            "graph-clear",
        ],
        default=["parse", "embed", "topicmodel", "graph"],
        help="Specify a list of actions: parse, embed, topicmodel, graph. Default is parse then embed.",
    )
    parser.add_argument(
        "--docs-dir",
        type=str,
        default=str(DOCUMENTS_BASE_DIR_ABS),
        help=f"Absolute path to the directory containing raw documents for parsing. Default: {DOCUMENTS_BASE_DIR_ABS}",
    )
    parser.add_argument(
        "--structured-output-dir",
        type=str,
        default=str(STRUCTURED_DOCS_OUTPUT_DIR),
        help=f"Directory to store/load structured JSON documents. Default: {STRUCTURED_DOCS_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--no-clean-structured-output",
        action="store_true",
        help="Do not remove existing structured document JSON before parsing.",
    )
    # Add more arguments as needed, e.g., for embedding model selection

    args = parser.parse_args()

    documents: list[Document] = []
    topics: list[Topic] = []
    processed_something = False

    # Convert string paths from args to Path objects
    docs_dir_abs = Path(args.docs_dir)
    structured_output_dir = Path(args.structured_output_dir)

    if "verify-sources" in args.actions:
        verify_source_snapshot_package_available()
        processed_something = True

    if "parse" in args.actions:
        print(f"Starting document parsing from: {docs_dir_abs}...")
        if not args.no_clean_structured_output:
            print(f"Cleaning structured documents in {structured_output_dir}...")
            clean_structured_documents_dir(structured_output_dir)
        documents = load_and_parse_documents(
            documents_dir_abs=docs_dir_abs, project_root=PROJECT_ROOT_DIR
        )
        print(f"Successfully parsed {len(documents)} documents.")
        print(f"Storing parsed documents to {structured_output_dir}...")
        store_documents_as_json(documents, structured_output_dir)
        processed_something = True

    if "embed" in args.actions:
        if not documents:
            print(f"Loading documents from {structured_output_dir} for embedding...")
            documents = load_documents_from_json(structured_output_dir)
            if not documents:
                print(
                    f"No documents found in {structured_output_dir}. Cannot proceed with embedding."
                )
                return

        print(f"Starting embedding for {len(documents)} documents...")
        embedding_client = EmbeddingClient()
        processed_docs_count = 0
        # Wrap the documents list with tqdm for a top-level progress bar
        async for doc in async_tqdm(
            embedding_client.embed_documents(documents),
            total=len(documents),
            desc="Embedding and Storing Documents",
        ):
            store_document_as_json(doc, structured_output_dir)
            processed_docs_count += 1

        print(
            f"Successfully embedded and stored {processed_docs_count} documents incrementally."
        )
        # No need to store all documents again at the end, as it's done incrementally
        processed_something = True

    if "topicmodel" in args.actions:
        if not documents:
            print(
                f"Loading documents from {structured_output_dir} for topic modeling..."
            )
            documents = load_documents_from_json(structured_output_dir)
            if not documents:
                print(
                    f"No documents found in {structured_output_dir}. Cannot proceed with topic modeling."
                )
                return

        print(f"Starting topic modeling for segments in {len(documents)} documents...")
        all_segments: list[DocumentSegment] = []
        for doc in documents:
            all_segments.extend(doc.segments)

        if not all_segments:
            print(
                "No segments found in the loaded documents. Cannot perform topic modeling."
            )
            return

        print(
            f"Performing topic modeling on {len(all_segments)} segments with embeddings..."
        )
        # extract_topics modifies segments in-place by adding topic_id
        topic_model_bertopic, segment_topic_map = extract_topics(
            all_segments
        )  # Pass only segments with embeddings

        topics = topics_to_pydantic(topic_model_bertopic)

        if topics:
            print(f"Generated {len(topics)} topics.")
            store_topics_as_json(topics, STRUCTURED_KB_OUTPUT_DIR, "topics.json")
        else:
            print("No topics were generated (excluding outliers).")

        # After topic IDs are assigned to segments, documents need to be re-saved
        print(
            f"Assigning topic IDs to segments and storing updated documents back to {structured_output_dir}..."
        )
        updated_doc_count = 0
        for doc in tqdm(documents, desc="Storing Documents with Topics", unit="doc"):
            for segment in doc.segments:
                if segment.id in segment_topic_map:
                    segment.topic_id = segment_topic_map[segment.id]
            store_document_as_json(doc, structured_output_dir)
            updated_doc_count += 1
        print(f"Successfully stored {updated_doc_count} documents with topic IDs.")
        processed_something = True

    if "graph" in args.actions:
        if not topics:
            print(f"Loading topics from {STRUCTURED_KB_OUTPUT_DIR}...")
            topics = load_topics_from_json(STRUCTURED_KB_OUTPUT_DIR)

        if not documents:
            print(f"Loading documents from {structured_output_dir}...")
            documents = load_documents_from_json(structured_output_dir)

        print("Starting graph operations...")
        schema_manager = SchemaManager(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USERNAME"),
            password=os.getenv("NEO4J_PASSWORD"),
        )
        schema_manager.clear_database()
        schema_manager.apply_schema()
        print("Schema applied successfully.")

        print("Upserting source provenance manifests...")
        schema_manager.upsert_source_registry(SOURCE_REGISTRY_PATH)
        schema_manager.upsert_source_snapshots(SOURCE_SNAPSHOT_MANIFEST_PATH)
        schema_manager.upsert_raw_snapshot_package(RAW_SNAPSHOT_PACKAGE_MANIFEST_PATH)
        schema_manager.upsert_pdf_source_documents(PDF_SOURCE_DOCUMENTS_MANIFEST_PATH)
        print("Source provenance manifests upserted successfully.")

        print("Upserting topics...")
        for topic in tqdm(topics, desc="Upserting topics", unit="topic"):
            schema_manager.upsert_topic(topic)
        print("Topics upserted successfully.")

        print("Upserting documents...")
        for doc in tqdm(documents, desc="Upserting documents", unit="doc"):
            schema_manager.upsert_document(doc)
        print("Documents upserted successfully.")

        # Process party entities
        print("Processing party entities...")
        process_party_entities(schema_manager)
        print("Party entities processed successfully.")

    if "graph-clear" in args.actions:
        schema_manager = SchemaManager(
            uri=os.getenv("NEO4J_URI"),
            user=os.getenv("NEO4J_USERNAME"),
            password=os.getenv("NEO4J_PASSWORD"),
        )
        print("Starting graph operations...")
        schema_manager.clear_database()

    if not processed_something:
        print(
            "No actions were performed. Please specify --actions parse or --actions embed."
        )
    else:
        print("Knowledge base processing complete.")


if __name__ == "__main__":
    asyncio.run(main())  # Modified to run async main
