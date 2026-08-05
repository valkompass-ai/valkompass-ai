import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { Message } from '@/types'

/**
 * Structural guarantee behind the Gemini context cache: request N must be a byte-exact prefix
 * extension of request N-1. Gemini's implicit cache is best-effort, so a live hit rate is not a
 * sound regression signal, but the prefix property is entirely ours to keep and is tested here
 * against a stubbed SDK.
 */

interface RecordedRequest {
  history: { role: string; parts: { text: string }[] }[]
  prompt: string
}

const recordedRequests: RecordedRequest[] = []
let answerCounter = 0

const usageMetadata = {
  promptTokenCount: 12_000,
  candidatesTokenCount: 100,
  cachedContentTokenCount: 9_000,
  thoughtsTokenCount: 50,
  totalTokenCount: 12_150,
}

vi.mock('@google/generative-ai', () => ({
  GoogleGenerativeAI: class {
    getGenerativeModel() {
      return {
        startChat: (chatConfig: { history: RecordedRequest['history'] }) => ({
          sendMessage: async (prompt: string) => {
            recordedRequests.push({ history: chatConfig.history, prompt })
            answerCounter += 1
            const text = `Svar nummer ${answerCounter}`
            return { response: { text: () => text, usageMetadata } }
          },
        }),
        generateContent: async () => ({ response: { text: () => '{"queries":[]}' } }),
      }
    }
  },
}))

vi.mock('../openai-service', () => ({
  getOpenAIEmbedding: async () => [0.1, 0.2, 0.3],
}))

vi.mock('../knowledge-base-service', () => ({
  getContextFromKB: async () => ({
    topicName: 'Energipolitik',
    topicDescription: 'Partiernas syn på energi',
    segments: [
      {
        segmentText: 'Partiet vill bygga ut kärnkraften.',
        documentPath: 'moderaterna/valmanifest.pdf',
        segmentPage: 4,
        similarityScore: 0.91,
        partyAbbreviation: 'M',
        publicUrl: '/kb-documents/moderaterna/valmanifest.pdf',
        documentSourceType: 'pdf',
      },
    ],
    retrievalDuration: 12,
    totalSegmentsFound: 1,
    avgSimilarityScore: 0.91,
    documentsReferenced: [{ path: 'moderaterna/valmanifest.pdf' }],
  }),
}))

vi.mock('../posthog', () => ({
  trackLLMCall: vi.fn(),
  trackChatInteraction: vi.fn(),
}))

const { getGeminiChatResponse } = await import('../gemini-service')
const { clearAllConversations } = await import('../conversation-store')
const { SYSTEM_INSTRUCTION } = await import('../prompt')

const userMessage = (text: string, history?: string): Message => ({
  id: `msg-${text}`,
  text,
  role: 'user',
  timestamp: new Date('2026-08-05T10:00:00Z'),
  history,
})

/** What Gemini actually receives, in order: the prior turns, then the new turn. */
const serializeRequest = (request: RecordedRequest): string =>
  [
    ...request.history.map((turn) => `${turn.role}:${turn.parts.map((part) => part.text).join('')}`),
    `user:${request.prompt}`,
  ].join('\n')

describe('Gemini chat request shape for context caching', () => {
  beforeEach(() => {
    recordedRequests.length = 0
    answerCounter = 0
    clearAllConversations()
  })

  it('leaves the prompt itself unchanged, system instruction included', async () => {
    await getGeminiChatResponse(userMessage('Vad tycker M om kärnkraft?'), 'user-1', { type: 'single' }, {
      conversationId: 'conv-a',
    })

    expect(recordedRequests[0].prompt.startsWith(SYSTEM_INSTRUCTION)).toBe(true)
    expect(recordedRequests[0].prompt).toContain('User Question: Vad tycker M om kärnkraft?')
  })

  it('makes each follow-up request a strict prefix extension of the previous one', async () => {
    const options = { conversationId: 'conv-a' }

    await getGeminiChatResponse(userMessage('Vad tycker M om kärnkraft?'), 'user-1', { type: 'single' }, options)
    await getGeminiChatResponse(userMessage('Och vad tycker S?'), 'user-1', { type: 'single' }, options)
    await getGeminiChatResponse(userMessage('Vilken skillnad är störst?'), 'user-1', { type: 'single' }, options)

    expect(recordedRequests).toHaveLength(3)

    const [first, second, third] = recordedRequests.map(serializeRequest)
    expect(second.startsWith(first)).toBe(true)
    expect(third.startsWith(second)).toBe(true)
    // The extension carries real content, i.e. the prefix match is not the whole request.
    expect(second.length).toBeGreaterThan(first.length)
  })

  it('replays the earlier prompt with its retrieved context, not just the question', async () => {
    const options = { conversationId: 'conv-a' }

    await getGeminiChatResponse(userMessage('Vad tycker M om kärnkraft?'), 'user-1', { type: 'single' }, options)
    await getGeminiChatResponse(userMessage('Och vad tycker S?'), 'user-1', { type: 'single' }, options)

    const history = recordedRequests[1].history
    expect(history).toHaveLength(2)
    expect(history[0].role).toBe('user')
    expect(history[0].parts[0].text).toBe(recordedRequests[0].prompt)
    expect(history[0].parts[0].text).toContain('Partiet vill bygga ut kärnkraften.')
    expect(history[1].parts[0].text).toBe('Svar nummer 1')
  })

  it('keeps conversations apart so one user never inherits another prefix', async () => {
    await getGeminiChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' }, { conversationId: 'conv-a' })
    await getGeminiChatResponse(userMessage('Fråga B'), 'user-2', { type: 'single' }, { conversationId: 'conv-b' })

    expect(recordedRequests[1].history).toHaveLength(0)
  })

  it('starts cold when no conversation id is supplied', async () => {
    await getGeminiChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' })
    await getGeminiChatResponse(userMessage('Fråga B'), 'user-1', { type: 'single' })

    expect(recordedRequests[0].history).toHaveLength(0)
    expect(recordedRequests[1].history).toHaveLength(0)
  })

  it('reports cached tokens and the resulting saving', async () => {
    const usages: { cachedPromptTokens: number; cost: number; costWithoutCache: number }[] = []

    await getGeminiChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' }, {
      conversationId: 'conv-a',
      onUsage: (usage) => {
        usages.push(usage)
      },
    })

    expect(usages).toHaveLength(1)
    expect(usages[0].cachedPromptTokens).toBe(usageMetadata.cachedContentTokenCount)
    expect(usages[0].cost).toBeLessThan(usages[0].costWithoutCache)
  })

})
