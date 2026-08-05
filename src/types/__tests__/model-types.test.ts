import { describe, it, expect } from 'vitest'
import {
  DEFAULT_CHAT_MODEL_KEY,
  DEFAULT_EMBEDDING_MODEL_KEY,
  DEFAULT_QUERY_MODEL_KEY,
  EMBEDDING_MODELS,
  LLM_MODELS,
  calculateEmbeddingCost,
  calculateLLMCost,
  getEmbeddingModelConfig,
  getLLMModelConfig,
  type EmbeddingModelKey,
  type LLMModelKey,
} from '../model-types'

describe('Model configuration', () => {
  const embeddingModel: EmbeddingModelKey = 'text-embedding-3-small'
  const llmModel: LLMModelKey = 'gpt-5.6-luna'

  it('uses current default model keys', () => {
    expect(DEFAULT_EMBEDDING_MODEL_KEY).toBe('text-embedding-3-small')
    expect(DEFAULT_CHAT_MODEL_KEY).toBe('gpt-5.6-luna')
    expect(DEFAULT_QUERY_MODEL_KEY).toBe('gpt-5.6-luna')
  })

  it('has only current embedding model configuration', () => {
    expect(Object.keys(EMBEDDING_MODELS)).toEqual(['text-embedding-3-small'])

    const model = EMBEDDING_MODELS[embeddingModel]
    expect(model.name).toBe('OpenAI Text Embedding 3 Small')
    expect(model.provider).toBe('openai')
    expect(model.model).toBe('text-embedding-3-small')
    expect(model.dimensions).toBe(1536)
    expect(model.maxTokens).toBe(8192)
    expect(model.cost.inputCostPer1KTokens).toBe(0.00002)
    expect(model.cost.outputCostPer1KTokens).toBe(0)
  })

  it('has only current Gemini model configurations', () => {
    expect(Object.keys(LLM_MODELS)).toEqual(['gpt-5.6-luna'])

    const luna = LLM_MODELS['gpt-5.6-luna']
    expect(luna.provider).toBe('openai')
    expect(luna.model).toBe('gpt-5.6-luna')
    expect(luna.contextWindow).toBe(400_000)
    expect(luna.maxOutputTokens).toBe(32_768)
    expect(luna.reasoningEffort).toBe('max')
    expect(luna.cost.inputCostPer1MTokens.standard).toBe(0.2)
    expect(luna.cost.outputCostPer1MTokens.standard).toBe(1.2)
    expect(luna.cost.cachedInputCostPer1MTokens).toBe(0.02)
  })

  it('prices cached prompt tokens at the cache rate', () => {
    const flash = LLM_MODELS['gpt-5.6-luna']
    // Cached tokens are part of promptTokenCount, so they are discounted, not added on top.
    expect(flash.cost.cachedInputCostPer1MTokens).toBeLessThan(flash.cost.inputCostPer1MTokens.standard)

    const promptTokens = 20_000
    const cachedTokens = 15_000
    const outputTokens = 500

    const expected =
      ((promptTokens - cachedTokens) / 1_000_000) * 0.2 +
      (cachedTokens / 1_000_000) * 0.02 +
      (outputTokens / 1_000_000) * 1.2

    expect(calculateLLMCost('gpt-5.6-luna', promptTokens, outputTokens, cachedTokens)).toBeCloseTo(
      expected,
      12
    )

    const uncached = calculateLLMCost('gpt-5.6-luna', promptTokens, outputTokens)
    expect(calculateLLMCost('gpt-5.6-luna', promptTokens, outputTokens, cachedTokens)).toBeLessThan(
      uncached
    )
  })

  it('clamps cached tokens to the prompt size', () => {
    expect(calculateLLMCost('gpt-5.6-luna', 1_000, 0, 5_000)).toBe(
      calculateLLMCost('gpt-5.6-luna', 1_000, 0, 1_000)
    )
    expect(calculateLLMCost('gpt-5.6-luna', 1_000, 0, -5)).toBe(
      calculateLLMCost('gpt-5.6-luna', 1_000, 0, 0)
    )
  })

  it('documents an implicit cache minimum for every chat model', () => {
    for (const config of Object.values(LLM_MODELS)) {
      expect(config.implicitCacheMinTokens).toBeGreaterThan(0)
    }
  })

  it('calculates embedding cost from configured pricing', () => {
    const textLength = 4000
    const expectedCost = (textLength / 4 / 1000) * EMBEDDING_MODELS[embeddingModel].cost.inputCostPer1KTokens

    expect(calculateEmbeddingCost(embeddingModel, textLength)).toBe(expectedCost)
  })

  it('calculates LLM cost from configured pricing', () => {
    const inputTokens = 1000
    const outputTokens = 500
    const expectedCost = (inputTokens / 1_000_000) * 0.2 + (outputTokens / 1_000_000) * 1.2

    expect(calculateLLMCost(llmModel, inputTokens, outputTokens)).toBe(expectedCost)
  })

  it('resolves configured model keys', () => {
    expect(getEmbeddingModelConfig(undefined).key).toBe(DEFAULT_EMBEDDING_MODEL_KEY)
    expect(getEmbeddingModelConfig(embeddingModel).config.model).toBe('text-embedding-3-small')
    expect(getLLMModelConfig(undefined).key).toBe(DEFAULT_CHAT_MODEL_KEY)
    expect(getLLMModelConfig('gpt-5.6-luna').config.model).toBe('gpt-5.6-luna')
  })

  it('rejects unknown configured model keys', () => {
    expect(() => getEmbeddingModelConfig('unsupported-embedding-model')).toThrow(
      'Unknown embedding model key'
    )
    expect(() => getLLMModelConfig('unsupported-llm-model')).toThrow('Unknown LLM model key')
  })
})
