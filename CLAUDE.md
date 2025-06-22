# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Valkompass.ai is an open-source Swedish political compass application that leverages AI to analyze official political documents and voting records. The system combines document parsing, semantic search, and RAG (Retrieval-Augmented Generation) to provide evidence-based answers about Swedish political parties' positions.

### Core Components
1. **Next.js Web Application** (`/src`) - React-based chat interface with Gemini 2.5 Flash integration
2. **Python Knowledge Base** (`/knowledge-base`) - Document processing pipeline with Neo4j graph storage
3. **TypeScript Data Pipeline** (`/commands`) - Riksdag API integration for voting data and metadata
4. **Analytics System** - Comprehensive PostHog tracking for LLM performance and user interactions

## Essential Commands

### Development Workflow
```bash
# Start development server (includes KB document preparation)
bun run dev

# Fast development with Turbopack
bun run dev:turbo

# Production build
bun run build

# Linting and type checking
bun run lint

# Start production server
bun run start
```

### Knowledge Base Management
```bash
# Complete pipeline: parse → embed → topic model → graph storage
make process-kb-docs

# Individual pipeline stages
make parse-kb-docs           # Parse PDF/JSON documents into structured format
make embed-kb-docs           # Generate OpenAI embeddings for semantic search
make topic-model-kb-docs     # Run BERTopic clustering on document segments
make graph-kb-docs           # Store data in Neo4j graph database
make graph-kb-clear          # Clear Neo4j database

# Testing and validation
make test-kb                 # Run Python test suite
```

### Political Data Collection
```bash
# Core data fetching pipeline (TypeScript commands)
bun run fetch-politicians    # Extract all Riksdag politician names/IDs
bun run extract-parties      # Map party abbreviations to full names
bun run fetch-votes          # Collect individual voting records (2016-2024)
bun run fetch-voteringar     # Fetch voting session metadata
bun run enrich-voteringar    # Add descriptions and context to voting sessions

# Testing commands (smaller datasets for validation)
bun run test-fetch-votes
bun run test-fetch-voteringar
bun run test-enrich-voteringar
```

## Detailed Architecture

### Frontend Architecture (`/src`)

#### Component Organization
- **Feature-based structure**: `/src/features/chat/` contains all chat-related components
- **Shared components**: `/src/components/` for reusable UI elements
- **Custom hooks**: `useChat` hook manages all chat state and API interactions
- **Type safety**: Strict TypeScript with comprehensive interface definitions

#### Key Components
- **ChatArea**: Main orchestrator component managing message flow and loading states
- **MessageBubble**: Role-based message rendering with markdown support for AI responses
- **ChatInput**: User input with validation and keyboard shortcuts
- **NavBar**: Responsive navigation with active page highlighting

#### State Management Pattern
- **Custom hooks**: Centralized state logic in `useChat` hook
- **Local state**: Form inputs managed locally with `useState`
- **No global state**: Simple prop drilling for component communication
- **Type-safe**: All state transitions validated through TypeScript interfaces

#### Data Flow
```
User Input → ChatInput → useChat → chat-api → /api/chat → Gemini Service → Knowledge Base → Response
```

### Backend Services (`/src/lib`)

#### AI Integration Services
- **`gemini-service.ts`**: Gemini 1.5 Flash integration with RAG context formatting
- **`openai-service.ts`**: OpenAI text-embedding-3-small for semantic search
- **`knowledge-base-service.ts`**: Neo4j vector similarity search and context retrieval
- **`prompt.ts`**: Systematic prompt engineering with Swedish-specific instructions

#### Analytics & Monitoring
- **`posthog.ts`**: Comprehensive LLM performance tracking including:
  - Token usage and cost estimation
  - RAG retrieval metrics (similarity scores, document references)
  - Chat interaction logging (user messages, AI responses, context used)
  - Knowledge base query performance
  - Error tracking and debugging

#### Middleware
- **`analytics.ts`**: Request-level tracking with user identification
- **Error handling**: Graceful degradation with user-friendly error messages

### Knowledge Base System (`/knowledge-base`)

#### Pipeline Architecture
1. **Document Parsing** (`parser/`):
   - **PDF Parser**: Uses pdfplumber + LangChain RecursiveCharacterTextSplitter
   - **JSON Parser**: Processes website content with URL metadata
   - **Chunking Strategy**: 2000 characters with 200 character overlap
   - **Metadata Preservation**: Page numbers, source URLs, character indexing

2. **Embedding Generation** (`analysis/embedding.py`):
   - **AsyncOpenAI**: Batch processing (10 segments/batch) for efficiency
   - **Model**: text-embedding-3-small (1536 dimensions)
   - **Incremental Processing**: Skip already-embedded segments
   - **Memory Efficiency**: Async generators for large datasets

3. **Topic Modeling** (`analysis/topic_modeling.py`):
   - **BERTopic**: Multilingual support (English + Swedish)
   - **Preprocessing**: NLTK stopwords, spaCy lemmatization
   - **Configuration**: min_topic_size=10, top_n_words=10
   - **Language Detection**: Automatic language routing

4. **Graph Storage** (`graph/`):
   - **Neo4j Integration**: Vector indices for similarity search
   - **Schema**: Document → Segment → Topic relationships
   - **Vector Search**: Cosine similarity with 1536-dimensional embeddings
   - **Bulk Operations**: Optimized upsert patterns

#### Data Models (Pydantic)
```python
class Document:
    path: str
    title: str
    content: str
    segments: List[DocumentSegment]

class DocumentSegment:
    text: str
    start_char: int
    end_char: int
    page: Optional[int]
    embedding: Optional[np.ndarray]  # Auto-serialized to/from JSON
    topic_id: Optional[int]

class Topic:
    topic_id: int
    name: str
    description: str
    embedding: Optional[np.ndarray]
```

### Data Collection System (`/commands`)

#### Riksdag API Integration
- **Politicians**: Scrapes HTML select elements from Riksdag website
- **Voting Records**: Comprehensive 2016-2024 dataset (9 parliamentary sessions)
- **Concurrency**: 10 concurrent sessions per politician for performance
- **Rate Limiting**: Respects API limits with batched processing
- **Metadata Enrichment**: Voting session descriptions and context

#### File Organization
```
knowledge-base/documents/
├── voting/
│   ├── politicians.json              # All Riksdag politicians
│   ├── parties.json                  # Party name mappings
│   └── by-politician-year/           # Individual voting records
│       ├── {politician}-{party}-{year}.json
└── {party}/                          # Party manifestos and documents
    ├── {party}-valmanifest-2022.pdf
    └── web-page-policies/
        └── {party}-webpolicies.json
```

## Development Patterns & Conventions

### Code Style & Architecture
- **TypeScript**: Strict mode with comprehensive type safety
- **ESLint**: Next.js recommended configuration with TypeScript rules
- **Component Design**: Feature-based organization with clear separation of concerns
- **Error Handling**: Comprehensive error boundaries with user-friendly messages
- **Performance**: Lazy loading, memo optimization, and efficient re-rendering patterns

### Package Management (Critical)
Always use **Bun** instead of npm per project conventions:
```bash
bun install          # NOT npm install
bun run <script>     # NOT npm run <script>
bunx <command>       # NOT npx <command>
```

### Styling System
- **Tailwind CSS v4**: Utility-first with custom design tokens
- **Design System**: Consistent glassmorphism effects (`bg-white/40`)
- **Responsive Design**: Mobile-first with `sm:` breakpoints
- **Typography**: Geist Sans/Mono fonts with gradient text effects
- **Components**: ShadCN/UI integration ready (components.json configured)

### Python Development (Knowledge Base)
- **Package Manager**: Use `uv` for dependency management
- **Exception Handling**: **CRITICAL - NO SILENT FAILURES ALLOWED**
  - **NEVER** catch exceptions and return `None` or silently fail
  - **ALWAYS** let exceptions propagate to discover errors early
  - The knowledge base pipeline must run without errors - silent failures hide bugs
  - **BAD EXAMPLE** (DO NOT DO THIS):
    ```python
    try:
        response = await self.client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed: {e}")
        return None  # SILENT FAILURE - NOT ALLOWED
    ```
  - **CORRECT EXAMPLE**:
    ```python
    response = await self.client.embeddings.create(input=[text], model=model)
    return response.data[0].embedding  # Let exceptions propagate
    ```
- **Testing**: Comprehensive pytest suite with async support
- **Performance**: Async patterns for I/O operations, batch processing

### Environment Configuration
Required environment variables:
```bash
# AI Services
GEMINI_API_KEY=<google_gemini_api_key>
OPENAI_API_KEY=<openai_api_key>

# Database
NEO4J_URI=<neo4j_connection_string>
NEO4J_USERNAME=<neo4j_username>
NEO4J_PASSWORD=<neo4j_password>

# Analytics (Optional)
POSTHOG_API_KEY=<posthog_api_key>
POSTHOG_HOST=<posthog_host_url>

# Application
APP_DOMAIN=<base_url_for_pdf_links>
```

## Localization & Content
- **Primary Language**: Swedish throughout the interface
- **AI Responses**: Automatically match user's question language
- **Political Focus**: Strictly Swedish politics with evidence-based responses
- **Source Attribution**: Comprehensive citation with document names and page numbers

## Performance & Monitoring
- **Token Tracking**: Real-time cost estimation for Gemini and OpenAI calls
- **RAG Metrics**: Similarity scores, retrieval latency, and document usage analytics
- **Error Monitoring**: Detailed error tracking with contextual information
- **User Analytics**: Chat interaction patterns and AI performance insights

## Development Workflow

### Initial Setup
```bash
# 1. Install dependencies
bun install
cd knowledge-base && uv sync

# 2. Set up environment variables
# Copy and configure .env files

# 3. Start database
docker compose up -d

# 4. Collect political data (optional - data already exists)
bun run fetch-politicians
bun run fetch-votes  # Long-running process

# 5. Process knowledge base
make process-kb-docs

# 6. Start development
bun run dev
```

### Testing Strategy
```bash
# Frontend
bun run lint          # TypeScript + ESLint validation
bun run build         # Production build verification

# Knowledge base
make test-kb          # Python test suite

# Data pipeline
bun run test-fetch-votes     # Validate API integration
```

This architecture provides a robust, scalable foundation for AI-powered political analysis with comprehensive monitoring, evidence-based responses, and maintainable code patterns.