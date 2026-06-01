# Knowledge Base

This directory contains the knowledge base processing pipeline for valkompass.ai.

## Quick Setup

```bash
# 1. Set up environment variables
cp .env.dist .env

# 2. Install dependencies
uv sync

# 3. Start database (from project root)
(cd .. && docker compose up -d)

# 4. Process knowledge base (from project root)
(cd .. && make graph-kb-docs)
```

## Running Tests

```bash
# Run all tests (from project root)
make test-kb

# Or directly from knowledge-base directory
cd knowledge-base
uv run pytest

# Run with coverage
uv run pytest --cov=. --cov-report=term-missing

# Run specific test files
uv run pytest tests/test_integration_pipeline.py -v
```

## Available Make Commands

From the project root directory:

```bash
make test-kb              # Run all tests
make validate-source-registry # Validate configured party source registry
make crawl-party-sources  # Crawl configured party website sources
make package-source-snapshots # Package ignored raw crawl snapshots into Git LFS
make unpack-source-snapshots  # Restore ignored raw crawl snapshots from Git LFS
make verify-source-snapshots-package # Verify packaged raw crawl snapshots
make parse-kb-docs        # Verify source package, then parse PDF/JSON documents
make embed-kb-docs        # Generate embeddings
make topic-model-kb-docs  # Run topic modeling
make graph-kb-docs        # Verify source package, then store in Neo4j
make graph-kb-clear       # Clear Neo4j database
make process-kb-docs      # Complete pipeline (verify → parse → embed → topic → graph)
```

## Architecture

The system processes political documents through a pipeline:

1. **Source Ingestion** (`sources/`) - Crawl configured official party sources into committed manifests, run reports, and structured web JSON
2. **Document Parsing** (`parser/`) - Extract text from PDFs and JSON files
3. **Embedding Generation** (`analysis/embedding.py`) - Create vector embeddings using OpenAI
4. **Topic Modeling** (`analysis/topic_modeling.py`) - Cluster content using BERTopic
5. **Graph Storage** (`graph/`) - Store in Neo4j with vector search capabilities

`make process-kb-docs` verifies the packaged raw source snapshots before parsing and before graph import. Parse runs cleanly by default: existing generated JSON under `structured-knowledge-base/documents/` is removed before the current `documents/` tree is transformed, so stale 2022 structured files cannot survive a refresh.

## Source Ingestion

Configured party website sources live in `source-registry.json`. The crawler writes SHA-256 hashes, run reports, and a manifest under `source-snapshots/`, then writes parser-compatible JSON under `documents/{party}/web/`. Raw fetched bytes are a local cache under `source-snapshots/raw/` and are intentionally ignored; the committed manifest keeps the hash, byte size, URL, timestamp, and local cache path needed to verify or reproduce a fetch.

```bash
cd knowledge-base
uv run python -m sources.cli validate-registry
uv run python -m sources.cli crawl --party S
uv run python -m sources.cli crawl --all
```

The crawler is registry-bound: it only follows configured hosts and path prefixes, stores source IDs, capture timestamps, raw byte hashes, and canonical text hashes for traceability.

Raw crawl snapshots under `source-snapshots/raw/` stay ignored during normal development. To preserve the exact raw bytes used by the tracked `source-snapshots/manifest.json`, package them into the Git LFS archive:

```bash
make package-source-snapshots
make unpack-source-snapshots
make verify-source-snapshots-package
```

The package contains only raw files referenced by the source snapshot manifest. Packaging fails if the local ignored raw cache is incomplete; in that case, run `make crawl-party-sources` or unpack an existing package first. `source-snapshots/raw-snapshots-package.json` and `source-snapshots/raw-snapshots.tar.gz.sha256` remain normal text files so the repo shows exactly which raw files, hashes, parties, sources, and URLs are in the LFS archive.

Curated official PDF documents live under `documents/{party}/pdf/` using:

```text
{party}-{year}-{document-type}[-qualifier].pdf
```

Their source pages, download URLs, byte sizes, and SHA-256 hashes are recorded in `source-documents-manifest.json`.

## Testing

The test suite includes comprehensive coverage with mocked API calls:

- **Unit tests**: Individual component testing
- **Integration tests**: End-to-end pipeline validation  
- **Error handling**: Edge cases and failure scenarios

All external dependencies (OpenAI API, Neo4j) are mocked to ensure tests run independently.

## Environment Variables

Required for production:

```bash
OPENAI_API_KEY=<openai_api_key>
NEO4J_URI=<neo4j_connection_string>
NEO4J_USERNAME=<neo4j_username>
NEO4J_PASSWORD=<neo4j_password>
```

## Development

```bash
# Format code
uv run ruff format .

# Check linting  
uv run ruff check .
```
