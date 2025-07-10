// Model configuration types with cost parameters
// Based on current models used in the project

export interface EmbeddingModelConfig {
  name: string;
  provider: 'openai';
  model: string;
  dimensions: number;
  maxTokens: number;
  cost: {
    inputCostPer1KTokens: number; // USD per 1K tokens
    outputCostPer1KTokens: number; // USD per 1K tokens (typically 0 for embeddings)
    currency: 'USD';
    lastUpdated: string; // ISO date string
    sourceUrl: string; // URL to pricing source
  };
}

export interface LLMModelConfig {
  name: string;
  provider: 'google';
  model: string;
  contextWindow: number; // max input tokens
  maxOutputTokens: number;
  cost: {
    // Different pricing tiers based on input length
    inputCostPer1MTokens: {
      standard: number; // For prompts <= 128k tokens
      longContext: number; // For prompts > 128k tokens
    };
    outputCostPer1MTokens: {
      standard: number; // For prompts <= 128k tokens  
      longContext: number; // For prompts > 128k tokens
    };
    currency: 'USD';
    lastUpdated: string; // ISO date string
    sourceUrl: string; // URL to pricing source
  };
}

// Current embedding models used in the project
export const EMBEDDING_MODELS: Record<string, EmbeddingModelConfig> = {
  'text-embedding-3-small': {
    name: 'OpenAI Text Embedding 3 Small',
    provider: 'openai',
    model: 'text-embedding-3-small',
    dimensions: 1536,
    maxTokens: 8191,
    cost: {
      inputCostPer1KTokens: 0.00002, // $0.00002 per 1K tokens
      outputCostPer1KTokens: 0, // No output cost for embeddings
      currency: 'USD',
      lastUpdated: '2024-12-30',
      sourceUrl: 'https://platform.openai.com/docs/pricing'
    }
  }
} as const;

// Current LLM models used in the project  
export const LLM_MODELS: Record<string, LLMModelConfig> = {
  'gemini-1.5-flash-latest': {
    name: 'Google Gemini 1.5 Flash',
    provider: 'google',
    model: 'gemini-1.5-flash-latest',
    contextWindow: 1_000_000, // 1M tokens
    maxOutputTokens: 8192,
    cost: {
      inputCostPer1MTokens: {
        standard: 0.075, // $0.075 per 1M tokens for prompts <= 128k
        longContext: 0.15  // $0.15 per 1M tokens for prompts > 128k
      },
      outputCostPer1MTokens: {
        standard: 0.30, // $0.30 per 1M tokens for prompts <= 128k
        longContext: 0.60  // $0.60 per 1M tokens for prompts > 128k
      },
      currency: 'USD',
      lastUpdated: '2024-12-30',
      sourceUrl: 'https://ai.google.dev/gemini-api/docs/pricing'
    }
  }
} as const;

// Helper functions to get cost calculations
export function calculateEmbeddingCost(
  modelKey: keyof typeof EMBEDDING_MODELS,
  textLength: number
): number {
  const model = EMBEDDING_MODELS[modelKey];
  // Rough approximation: 1 token ≈ 4 characters
  const estimatedTokens = textLength / 4;
  return (estimatedTokens / 1000) * model.cost.inputCostPer1KTokens;
}

export function calculateLLMCost(
  modelKey: keyof typeof LLM_MODELS,
  inputTokens: number,
  outputTokens: number
): number {
  const model = LLM_MODELS[modelKey];
  
  // Determine if long context pricing applies (> 128k tokens)
  const isLongContext = inputTokens > 128_000;
  
  const inputCost = (inputTokens / 1_000_000) * 
    (isLongContext ? model.cost.inputCostPer1MTokens.longContext : model.cost.inputCostPer1MTokens.standard);
    
  const outputCost = (outputTokens / 1_000_000) * 
    (isLongContext ? model.cost.outputCostPer1MTokens.longContext : model.cost.outputCostPer1MTokens.standard);
    
  return inputCost + outputCost;
}

// Type exports for use throughout the application
export type EmbeddingModelKey = keyof typeof EMBEDDING_MODELS;
export type LLMModelKey = keyof typeof LLM_MODELS; 