# 01. Model Platform

## Research

- Runtime LLM model selection is centralized in `src/types/model-types.ts`.
- Chat and query generation both use OpenAI `gpt-5.6-luna` at `max` reasoning effort.
- Model pricing includes the cached-input rate so context cache savings can be measured.
- Embeddings use `text-embedding-3-small` with 1536 dimensions.

References:

- OpenAI models: https://developers.openai.com/api/docs/models
- OpenAI pricing: https://developers.openai.com/api/docs/pricing

## Plan

1. Add the latest OpenAI chat models to `src/types/model-types.ts`.
2. Make chat and query generation use the shared model registry.
3. Make model selection configurable through environment variables.
4. Remove stale runtime model usage.
5. Add tests for configured model keys.
