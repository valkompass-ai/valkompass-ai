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
make parse-kb-docs        # Parse PDF/JSON documents  
make embed-kb-docs        # Generate embeddings
make topic-model-kb-docs  # Run topic modeling
make graph-kb-docs        # Store in Neo4j
make graph-kb-clear       # Clear Neo4j database
make process-kb-docs      # Complete pipeline (parse → embed → topic → graph)
```

## Architecture

The system processes political documents through a pipeline:

1. **Document Parsing** (`parser/`) - Extract text from PDFs and JSON files
2. **Embedding Generation** (`analysis/embedding.py`) - Create vector embeddings using OpenAI
3. **Topic Modeling** (`analysis/topic_modeling.py`) - Cluster content using BERTopic
4. **Graph Storage** (`graph/`) - Store in Neo4j with vector search capabilities

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
