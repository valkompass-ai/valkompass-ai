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
  const llmModel: LLMModelKey = 'gemini-3.1-flash-lite'

  it('uses current default model keys', () => {
    expect(DEFAULT_EMBEDDING_MODEL_KEY).toBe('text-embedding-3-small')
    expect(DEFAULT_CHAT_MODEL_KEY).toBe('gemini-3.6-flash')
    expect(DEFAULT_QUERY_MODEL_KEY).toBe('gemini-3.1-flash-lite')
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
    expect(Object.keys(LLM_MODELS)).toEqual(['gemini-3.1-flash-lite', 'gemini-3.6-flash'])

    const flashLite = LLM_MODELS['gemini-3.1-flash-lite']
    expect(flashLite.model).toBe('gemini-3.1-flash-lite')
    expect(flashLite.contextWindow).toBe(1_048_576)
    expect(flashLite.maxOutputTokens).toBe(65_536)
    expect(flashLite.cost.inputCostPer1MTokens.standard).toBe(0.25)
    expect(flashLite.cost.outputCostPer1MTokens.standard).toBe(1.5)
    expect(flashLite.cost.cachedInputCostPer1MTokens).toBe(0.025)

    const flash = LLM_MODELS['gemini-3.6-flash']
    expect(flash.model).toBe('gemini-3.6-flash')
    expect(flash.contextWindow).toBe(1_048_576)
    expect(flash.maxOutputTokens).toBe(65_536)
    expect(flash.cost.inputCostPer1MTokens.standard).toBe(1.5)
    expect(flash.cost.outputCostPer1MTokens.standard).toBe(7.5)
    expect(flash.cost.cachedInputCostPer1MTokens).toBe(0.15)
  })

  it('prices cached prompt tokens at the cache rate', () => {
    const flash = LLM_MODELS['gemini-3.6-flash']
    // Cached tokens are part of promptTokenCount, so they are discounted, not added on top.
    expect(flash.cost.cachedInputCostPer1MTokens).toBeLessThan(flash.cost.inputCostPer1MTokens.standard)

    const promptTokens = 20_000
    const cachedTokens = 15_000
    const outputTokens = 500

    const expected =
      ((promptTokens - cachedTokens) / 1_000_000) * 1.5 +
      (cachedTokens / 1_000_000) * 0.15 +
      (outputTokens / 1_000_000) * 7.5

    expect(calculateLLMCost('gemini-3.6-flash', promptTokens, outputTokens, cachedTokens)).toBeCloseTo(
      expected,
      12
    )

    const uncached = calculateLLMCost('gemini-3.6-flash', promptTokens, outputTokens)
    expect(calculateLLMCost('gemini-3.6-flash', promptTokens, outputTokens, cachedTokens)).toBeLessThan(
      uncached
    )
  })

  it('clamps cached tokens to the prompt size', () => {
    expect(calculateLLMCost('gemini-3.6-flash', 1_000, 0, 5_000)).toBe(
      calculateLLMCost('gemini-3.6-flash', 1_000, 0, 1_000)
    )
    expect(calculateLLMCost('gemini-3.6-flash', 1_000, 0, -5)).toBe(
      calculateLLMCost('gemini-3.6-flash', 1_000, 0, 0)
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
    const expectedCost = (inputTokens / 1_000_000) * 0.25 + (outputTokens / 1_000_000) * 1.5

    expect(calculateLLMCost(llmModel, inputTokens, outputTokens)).toBe(expectedCost)
  })

  it('resolves configured model keys', () => {
    expect(getEmbeddingModelConfig(undefined).key).toBe(DEFAULT_EMBEDDING_MODEL_KEY)
    expect(getEmbeddingModelConfig(embeddingModel).config.model).toBe('text-embedding-3-small')
    expect(getLLMModelConfig(undefined).key).toBe(DEFAULT_CHAT_MODEL_KEY)
    expect(getLLMModelConfig('gemini-3.6-flash').config.model).toBe('gemini-3.6-flash')
  })

  it('rejects unknown configured model keys', () => {
    expect(() => getEmbeddingModelConfig('unsupported-embedding-model')).toThrow(
      'Unknown embedding model key'
    )
    expect(() => getLLMModelConfig('unsupported-gemini-model')).toThrow('Unknown Gemini model key')
  })
})
