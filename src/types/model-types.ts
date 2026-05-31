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

export interface LLMModelConfig {
  name: string;
  provider: 'google';
  model: string;
  contextWindow: number;
  maxOutputTokens: number;
  cost: {
    inputCostPer1MTokens: {
      standard: number;
      longContext: number;
    };
    outputCostPer1MTokens: {
      standard: number;
      longContext: number;
    };
    currency: 'USD';
    lastUpdated: string;
    sourceUrl: string;
  };
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
  'gemini-3.1-flash-lite': {
    name: 'Google Gemini 3.1 Flash-Lite',
    provider: 'google',
    model: 'gemini-3.1-flash-lite',
    contextWindow: 1_048_576,
    maxOutputTokens: 65_536,
    cost: {
      inputCostPer1MTokens: {
        standard: 0.25,
        longContext: 0.25,
      },
      outputCostPer1MTokens: {
        standard: 1.50,
        longContext: 1.50,
      },
      currency: 'USD',
      lastUpdated: '2026-05-31',
      sourceUrl: 'https://ai.google.dev/gemini-api/docs/pricing',
    },
  },
  'gemini-3.5-flash': {
    name: 'Google Gemini 3.5 Flash',
    provider: 'google',
    model: 'gemini-3.5-flash',
    contextWindow: 1_048_576,
    maxOutputTokens: 65_536,
    cost: {
      inputCostPer1MTokens: {
        standard: 1.50,
        longContext: 1.50,
      },
      outputCostPer1MTokens: {
        standard: 9.00,
        longContext: 9.00,
      },
      currency: 'USD',
      lastUpdated: '2026-05-31',
      sourceUrl: 'https://ai.google.dev/gemini-api/docs/pricing',
    },
  },
} as const satisfies Record<string, LLMModelConfig>;

export type EmbeddingModelKey = keyof typeof EMBEDDING_MODELS;
export type LLMModelKey = keyof typeof LLM_MODELS;

export const DEFAULT_EMBEDDING_MODEL_KEY: EmbeddingModelKey = 'text-embedding-3-small';
export const DEFAULT_CHAT_MODEL_KEY: LLMModelKey = 'gemini-3.1-flash-lite';
export const DEFAULT_QUERY_MODEL_KEY: LLMModelKey = 'gemini-3.1-flash-lite';

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
    throw new Error(`Unknown Gemini model key: ${resolvedKey}`);
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

export function calculateLLMCost(
  modelKey: LLMModelKey,
  inputTokens: number,
  outputTokens: number
): number {
  const model = LLM_MODELS[modelKey];
  const isLongContext = inputTokens > 128_000;
  const inputRate = isLongContext
    ? model.cost.inputCostPer1MTokens.longContext
    : model.cost.inputCostPer1MTokens.standard;
  const outputRate = isLongContext
    ? model.cost.outputCostPer1MTokens.longContext
    : model.cost.outputCostPer1MTokens.standard;

  return (inputTokens / 1_000_000) * inputRate + (outputTokens / 1_000_000) * outputRate;
}
