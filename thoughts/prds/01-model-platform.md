# 01. Model Platform

## Research

- Runtime Gemini model selection is centralized in `src/types/model-types.ts`.
- Chat and query generation default to `gemini-3.1-flash-lite`.
- `gemini-3.5-flash` is available as the higher-quality Flash option.
- Embeddings use `text-embedding-3-small` with 1536 dimensions.

References:

- Gemini models: https://ai.google.dev/gemini-api/docs/models
- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing

## Plan

1. Add the latest Gemini Flash and Flash-Lite models to `src/types/model-types.ts`.
2. Make chat and query generation use the shared model registry.
3. Make model selection configurable through environment variables.
4. Remove stale runtime model usage.
5. Add tests for configured model keys.
