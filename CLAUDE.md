# Valkompass.ai Agent Guide

This file is shared agent guidance for this repository. Keep it concise, factual, and current; it is loaded into agent context on every session. `AGENTS.md` should point to this file.

## Project Snapshot

Valkompass.ai is a Swedish political Q&A app. Users ask questions about Swedish parties, and the app answers from official political material using retrieval-augmented generation.

Primary parts:
- `src/`: Next.js 15 / React 19 web app with the chat UI and API routes.
- `src/lib/`: AI, retrieval, analytics, prompt, and service code.
- `knowledge-base/`: Python document pipeline for PDFs and website JSON.
- `commands/`: Bun/TypeScript scripts for collecting Riksdag voting data.
- `knowledge-base/documents/`: raw source data, including party documents and voting data.
- `knowledge-base/structured-knowledge-base/`: processed JSON that is loaded into Neo4j.

## Runtime Flow

Chat flow:

```text
ChatInput -> useChat -> /api/chat -> gemini-service -> OpenAI embeddings -> Neo4j vector search -> Gemini answer
```

Important runtime files:
- `src/app/api/chat/route.ts`: validates requests and selects single-step or multi-step retrieval.
- `src/lib/gemini-service.ts`: orchestrates retrieval, prompt construction, Gemini calls, retries, and analytics.
- `src/lib/multi-step-agent-service.ts`: generates multiple targeted search queries and aggregates retrieved context.
- `src/lib/knowledge-base-service.ts`: queries Neo4j `topic_embedding_idx` and `segment_embedding_idx`.
- `src/lib/openai-service.ts`: creates `text-embedding-3-small` embeddings with 1536 dimensions.
- `src/lib/prompt.ts`: source-grounding, citation, Swedish-politics scope, and language rules.

Current app model settings live in `src/types/model-types.ts`. As of this guide, chat and local query generation default to `gemini-3.1-flash-lite`; `gemini-3.5-flash` is available as the higher-quality Flash option. Embeddings use `text-embedding-3-small` with 1536 dimensions.

## Package Managers

Use Bun for JavaScript/TypeScript work. Do not switch to npm or pnpm.

```bash
bun install
bun run <script>
bunx <tool>
```

Use `uv` for Python work in `knowledge-base/`.

```bash
cd knowledge-base
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Common Commands

App:

```bash
bun run dev          # copies public KB PDFs, then starts Next.js
bun run dev:turbo    # starts Next.js with Turbopack, without prepare-kb-documents
bun run build        # copies public KB PDFs, then builds
bun run start
bun run test:run
bun run test:coverage
```

Knowledge base:

```bash
make test-kb
make parse-kb-docs
make embed-kb-docs
make topic-model-kb-docs
make process-kb-docs
```

Neo4j:

```bash
docker compose up -d
make graph-kb-docs
make graph-kb-clear
```

Voting/data collection:

```bash
bun run fetch-politicians
bun run extract-parties
bun run fetch-votes
bun run fetch-voteringar
bun run enrich-voteringar
```

Prefer targeted tests for the area changed. Full integration tests may require real `GEMINI_API_KEY`, `OPENAI_API_KEY`, and Neo4j credentials.

## Environment

Root app env:

```bash
GEMINI_API_KEY=
OPENAI_API_KEY=
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=
NEO4J_PASSWORD=
POSTHOG_API_KEY=
POSTHOG_HOST=https://eu.i.posthog.com
APP_DOMAIN=
```

Knowledge-base env is in `knowledge-base/.env` and needs `OPENAI_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, and `NEO4J_PASSWORD`. Never commit secrets. `.env.local`, `.env`, and test env files may exist locally; treat them as private.

## Knowledge Base Pipeline

Pipeline stages:

```text
raw PDFs / website JSON -> parsed Document/DocumentSegment JSON -> embeddings -> BERTopic topics -> Neo4j graph
```

Important implementation details:
- PDF parsing uses `pdfplumber` and LangChain `RecursiveCharacterTextSplitter`.
- Website policy JSON files become one segment per item with `public_url` preserved.
- The parser intentionally excludes `knowledge-base/documents/voting/` from the document parsing pipeline.
- Neo4j nodes are `Topic`, `Document`, `DocumentSegment`, and `Party`.
- Parties are linked to documents from folder names via `SchemaManager.link_documents_to_parties()`.

Safety:
- `make graph-kb-docs` runs the `graph` action, which clears the Neo4j database before applying schema and re-importing data.
- `make graph-kb-clear` deletes graph data, constraints, and indexes.
- Do not run graph-clearing commands unless the user asked for KB rebuild/reset work or you have confirmed the database is disposable.

## Code Conventions

TypeScript/React:
- Keep chat-related UI under `src/features/chat/`.
- Keep shared components under `src/components/`.
- Keep service logic under `src/lib/`.
- Use existing `Message` and model config types instead of creating parallel shapes.
- Preserve the source-grounded answer contract in `src/lib/prompt.ts`.
- Use `react-markdown` with sanitization patterns already present for AI-rendered Markdown.

Python:
- Keep Pydantic models in `knowledge-base/model/`.
- Let unexpected pipeline failures surface; do not hide bad documents, missing embeddings, or graph write errors behind silent `None` returns.
- If a skip is intentional for a known bad input, log enough context to find the source file.
- Preserve incremental writes in embedding steps so long runs can resume.

Data/scripts:
- Riksdag scripts in `commands/` write into `knowledge-base/documents/voting/`.
- Network collection scripts can be long-running and produce many files; use test scripts first when changing fetch logic.
- Avoid reformatting generated or large JSON data unless the task requires regenerating it.

## Product Rules

- The UI is Swedish-first.
- AI answers must stay scoped to Swedish politics.
- Answers should cite retrieved source URLs or document/page metadata when context is available.
- If retrieved context cannot answer the question, the assistant should say so rather than inventing facts.
- Preserve public transparency: raw and structured data should remain inspectable under `knowledge-base/`.

## Known Pitfalls

- `src/lib/gemini-service.ts` has module-level `chatHistory`; this can leak context across server requests in a long-lived process. Be careful when changing conversation handling.
- The docs and README may lag model changes; trust `src/types/model-types.ts` and service code for current model IDs.
- `bun run dev:turbo` does not run `prepare-kb-documents`; use `bun run dev` if PDF public links need to exist locally.
- `next lint` is still listed as `bun run lint`; verify before relying on it because Next.js lint behavior has changed across versions.
- `PostHog` has default fallback config in `src/lib/posthog.ts`; avoid logging sensitive user content beyond the existing analytics contract.

## Maintenance Rules For This File

- Prefer specific commands and paths over general advice.
- Remove stale architecture claims when code changes.
- Keep this under roughly 200 lines; split rare or path-specific guidance into separate docs only if agents need it.
- Do not duplicate README content unless it changes how an agent should work.
