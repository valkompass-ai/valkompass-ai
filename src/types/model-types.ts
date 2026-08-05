export interface EmbeddingModelConfig {
  name: string;
  provider: 'openai';
  model: string;
  dimensions: number;
  maxTokens: number;
  cost: {
    inputCostPer1KTokens: number;
    outputCostPer1KTokens: number;
    currency: 'USD';
    lastUpdated: string;
    sourceUrl: string;
  };
}

export type ReasoningEffort = 'low' | 'medium' | 'high' | 'max';

export interface LLMModelConfig {
  name: string;
  provider: 'openai';
  model: string;
  contextWindow: number;
  maxOutputTokens: number;
  /** Reasoning models spend output tokens on thinking, so this must leave room for both. */
  reasoningEffort: ReasoningEffort;
  cost: {
    inputCostPer1MTokens: {
      standard: number;
      longContext: number;
    };
    outputCostPer1MTokens: {
      standard: number;
      longContext: number;
    };
    /** Price for prompt tokens served from the prompt cache. */
    cachedInputCostPer1MTokens: number;
    currency: 'USD';
    lastUpdated: string;
    sourceUrl: string;
  };
  /**
   * Minimum prompt size before the model is eligible for prompt caching.
   * Requests below this never report cached tokens, regardless of prefix reuse.
   */
  implicitCacheMinTokens: number;
}

export const EMBEDDING_MODELS = {
  'text-embedding-3-small': {
    name: 'OpenAI Text Embedding 3 Small',
    provider: 'openai',
    model: 'text-embedding-3-small',
    dimensions: 1536,
    maxTokens: 8192,
    cost: {
      inputCostPer1KTokens: 0.00002,
      outputCostPer1KTokens: 0,
      currency: 'USD',
      lastUpdated: '2026-05-31',
      sourceUrl: 'https://platform.openai.com/docs/models/text-embedding-3-small',
    },
  },
} as const satisfies Record<string, EmbeddingModelConfig>;

export const LLM_MODELS = {
  'gpt-5.6-luna': {
    name: 'OpenAI GPT-5.6 Luna',
    provider: 'openai',
    model: 'gpt-5.6-luna',
    contextWindow: 400_000,
    maxOutputTokens: 32_768,
    reasoningEffort: 'max',
    cost: {
      inputCostPer1MTokens: {
        standard: 0.20,
        longContext: 0.20,
      },
      outputCostPer1MTokens: {
        standard: 1.20,
        longContext: 1.20,
      },
      cachedInputCostPer1MTokens: 0.02,
      currency: 'USD',
      lastUpdated: '2026-08-05',
      sourceUrl: 'https://developers.openai.com/api/docs/pricing',
    },
    // OpenAI caches prompt prefixes from 1024 tokens upward.
    implicitCacheMinTokens: 1024,
  },
} as const satisfies Record<string, LLMModelConfig>;

export type EmbeddingModelKey = keyof typeof EMBEDDING_MODELS;
export type LLMModelKey = keyof typeof LLM_MODELS;

export const DEFAULT_EMBEDDING_MODEL_KEY: EmbeddingModelKey = 'text-embedding-3-small';
export const DEFAULT_CHAT_MODEL_KEY: LLMModelKey = 'gpt-5.6-luna';
export const DEFAULT_QUERY_MODEL_KEY: LLMModelKey = 'gpt-5.6-luna';

export function isEmbeddingModelKey(modelKey: string): modelKey is EmbeddingModelKey {
  return modelKey in EMBEDDING_MODELS;
}

export function isLLMModelKey(modelKey: string): modelKey is LLMModelKey {
  return modelKey in LLM_MODELS;
}

export function getEmbeddingModelConfig(modelKey: string | undefined): {
  key: EmbeddingModelKey;
  config: EmbeddingModelConfig;
} {
  const resolvedKey = modelKey || DEFAULT_EMBEDDING_MODEL_KEY;

  if (!isEmbeddingModelKey(resolvedKey)) {
    throw new Error(`Unknown embedding model key: ${resolvedKey}`);
  }

  return {
    key: resolvedKey,
    config: EMBEDDING_MODELS[resolvedKey],
  };
}

export function getLLMModelConfig(
  modelKey: string | undefined,
  fallbackKey: LLMModelKey = DEFAULT_CHAT_MODEL_KEY
): {
  key: LLMModelKey;
  config: LLMModelConfig;
} {
  const resolvedKey = modelKey || fallbackKey;

  if (!isLLMModelKey(resolvedKey)) {
    throw new Error(`Unknown LLM model key: ${resolvedKey}`);
  }

  return {
    key: resolvedKey,
    config: LLM_MODELS[resolvedKey],
  };
}

export function calculateEmbeddingCost(
  modelKey: EmbeddingModelKey,
  textLength: number
): number {
  const model = EMBEDDING_MODELS[modelKey];
  const estimatedTokens = textLength / 4;
  return (estimatedTokens / 1000) * model.cost.inputCostPer1KTokens;
}

/**
 * Cost for one LLM call.
 *
 * `inputTokens` is the full prompt size (the API's `input_tokens`, which already includes cached
 * tokens). `cachedInputTokens` is the share of that prompt served from the prompt cache
 * (`input_tokens_details.cached_tokens`); it is billed at the much lower cache rate.
 */
export function calculateLLMCost(
  modelKey: LLMModelKey,
  inputTokens: number,
  outputTokens: number,
  cachedInputTokens: number = 0
): number {
  const model = LLM_MODELS[modelKey];
  const isLongContext = inputTokens > 128_000;
  const inputRate = isLongContext
    ? model.cost.inputCostPer1MTokens.longContext
    : model.cost.inputCostPer1MTokens.standard;
  const outputRate = isLongContext
    ? model.cost.outputCostPer1MTokens.longContext
    : model.cost.outputCostPer1MTokens.standard;

  const cachedTokens = Math.min(Math.max(cachedInputTokens, 0), inputTokens);
  const uncachedTokens = inputTokens - cachedTokens;

  return (
    (uncachedTokens / 1_000_000) * inputRate +
    (cachedTokens / 1_000_000) * model.cost.cachedInputCostPer1MTokens +
    (outputTokens / 1_000_000) * outputRate
  );
}
