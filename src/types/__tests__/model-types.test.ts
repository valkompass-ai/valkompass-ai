import { describe, it, expect } from 'vitest'
import {
  calculateEmbeddingCost,
  calculateLLMCost,
  EMBEDDING_MODELS,
  LLM_MODELS,
  type EmbeddingModelKey,
  type LLMModelKey
} from '../model-types'

describe('Model Cost Calculations', () => {
  describe('calculateEmbeddingCost', () => {
    const embeddingModel: EmbeddingModelKey = 'text-embedding-3-small'

    it('should calculate cost for short text correctly', () => {
      // 100 characters = ~25 tokens = 0.025 * $0.00002 = $0.0000005
      const text = 'a'.repeat(100)
      const cost = calculateEmbeddingCost(embeddingModel, text.length)
      
      expect(cost).toBeCloseTo(0.0000005, 10)
    })

    it('should calculate cost for medium text correctly', () => {
      // 4000 characters = ~1000 tokens = 1.0 * $0.00002 = $0.00002
      const text = 'a'.repeat(4000)
      const cost = calculateEmbeddingCost(embeddingModel, text.length)
      
      expect(cost).toBe(0.00002)
    })

    it('should calculate cost for large text correctly', () => {
      // 40000 characters = ~10000 tokens = 10.0 * $0.00002 = $0.0002
      const text = 'a'.repeat(40000)
      const cost = calculateEmbeddingCost(embeddingModel, text.length)
      
      expect(cost).toBe(0.0002)
    })

    it('should handle empty text', () => {
      const cost = calculateEmbeddingCost(embeddingModel, 0)
      expect(cost).toBe(0)
    })

    it('should handle single character', () => {
      const cost = calculateEmbeddingCost(embeddingModel, 1)
      // 1 character = 0.25 tokens = 0.00025 * $0.00002 = $0.000000005
      expect(cost).toBeCloseTo(0.000000005, 12)
    })

    it('should use correct model pricing from configuration', () => {
      const modelConfig = EMBEDDING_MODELS[embeddingModel]
      const textLength = 4000 // ~1000 tokens
      const expectedCost = (textLength / 4 / 1000) * modelConfig.cost.inputCostPer1KTokens
      
      const actualCost = calculateEmbeddingCost(embeddingModel, textLength)
      expect(actualCost).toBe(expectedCost)
    })
  })

  describe('calculateLLMCost', () => {
    const llmModel: LLMModelKey = 'gemini-1.5-flash-latest'

    describe('Standard pricing (≤128k tokens)', () => {
      it('should calculate cost for small conversation correctly', () => {
        const inputTokens = 1000
        const outputTokens = 500
        
        // Input: 1000/1M * $0.075 = $0.000075
        // Output: 500/1M * $0.30 = $0.00015
        // Total: $0.000225
        const cost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(cost).toBe(0.000225)
      })

      it('should calculate cost for medium conversation correctly', () => {
        const inputTokens = 50000
        const outputTokens = 2000
        
        // Input: 50000/1M * $0.075 = $0.00375
        // Output: 2000/1M * $0.30 = $0.0006
        // Total: $0.00435
        const cost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(cost).toBe(0.00435)
      })

      it('should use standard pricing at exactly 128k tokens', () => {
        const inputTokens = 128000
        const outputTokens = 1000
        
        // Should use standard pricing (≤128k)
        // Input: 128000/1M * $0.075 = $0.0096
        // Output: 1000/1M * $0.30 = $0.0003
        // Total: $0.0099
        const cost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(cost).toBeCloseTo(0.0099, 8)
      })
    })

    describe('Long context pricing (>128k tokens)', () => {
      it('should calculate cost for long context conversation correctly', () => {
        const inputTokens = 200000
        const outputTokens = 1000
        
        // Should use long context pricing (>128k)
        // Input: 200000/1M * $0.15 = $0.03
        // Output: 1000/1M * $0.60 = $0.0006
        // Total: $0.0306
        const cost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(cost).toBe(0.0306)
      })

      it('should use long context pricing at 128k + 1 tokens', () => {
        const inputTokens = 128001
        const outputTokens = 1000
        
        // Should use long context pricing (>128k)
        // Input: 128001/1M * $0.15 = $0.01920015
        // Output: 1000/1M * $0.60 = $0.0006
        // Total: $0.01980015
        const cost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(cost).toBeCloseTo(0.01980015, 8)
      })

      it('should calculate cost for very long context correctly', () => {
        const inputTokens = 500000
        const outputTokens = 5000
        
        // Input: 500000/1M * $0.15 = $0.075
        // Output: 5000/1M * $0.60 = $0.003
        // Total: $0.078
        const cost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(cost).toBe(0.078)
      })
    })

    describe('Edge cases', () => {
      it('should handle zero input tokens', () => {
        const cost = calculateLLMCost(llmModel, 0, 1000)
        // Only output cost: 1000/1M * $0.30 = $0.0003
        expect(cost).toBe(0.0003)
      })

      it('should handle zero output tokens', () => {
        const cost = calculateLLMCost(llmModel, 1000, 0)
        // Only input cost: 1000/1M * $0.075 = $0.000075
        expect(cost).toBe(0.000075)
      })

      it('should handle zero tokens for both input and output', () => {
        const cost = calculateLLMCost(llmModel, 0, 0)
        expect(cost).toBe(0)
      })

      it('should use correct model pricing from configuration', () => {
        const modelConfig = LLM_MODELS[llmModel]
        const inputTokens = 50000
        const outputTokens = 2000
        
        // Should use standard pricing
        const expectedInputCost = (inputTokens / 1_000_000) * modelConfig.cost.inputCostPer1MTokens.standard
        const expectedOutputCost = (outputTokens / 1_000_000) * modelConfig.cost.outputCostPer1MTokens.standard
        const expectedTotal = expectedInputCost + expectedOutputCost
        
        const actualCost = calculateLLMCost(llmModel, inputTokens, outputTokens)
        expect(actualCost).toBe(expectedTotal)
      })
    })
  })

  describe('Model Configuration Validation', () => {
    it('should have valid embedding model configuration', () => {
      const model = EMBEDDING_MODELS['text-embedding-3-small']
      
      expect(model).toBeDefined()
      expect(model.name).toBe('OpenAI Text Embedding 3 Small')
      expect(model.provider).toBe('openai')
      expect(model.model).toBe('text-embedding-3-small')
      expect(model.dimensions).toBe(1536)
      expect(model.maxTokens).toBe(8191)
      expect(model.cost.inputCostPer1KTokens).toBe(0.00002)
      expect(model.cost.outputCostPer1KTokens).toBe(0)
      expect(model.cost.currency).toBe('USD')
      expect(model.cost.sourceUrl).toBe('https://platform.openai.com/docs/pricing')
    })

    it('should have valid LLM model configuration', () => {
      const model = LLM_MODELS['gemini-1.5-flash-latest']
      
      expect(model).toBeDefined()
      expect(model.name).toBe('Google Gemini 1.5 Flash')
      expect(model.provider).toBe('google')
      expect(model.model).toBe('gemini-1.5-flash-latest')
      expect(model.contextWindow).toBe(1_000_000)
      expect(model.maxOutputTokens).toBe(8192)
      expect(model.cost.inputCostPer1MTokens.standard).toBe(0.075)
      expect(model.cost.inputCostPer1MTokens.longContext).toBe(0.15)
      expect(model.cost.outputCostPer1MTokens.standard).toBe(0.30)
      expect(model.cost.outputCostPer1MTokens.longContext).toBe(0.60)
      expect(model.cost.currency).toBe('USD')
      expect(model.cost.sourceUrl).toBe('https://ai.google.dev/gemini-api/docs/pricing')
    })
  })
}) 