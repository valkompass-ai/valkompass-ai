import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { Message } from '@/types'
import { DEFAULT_CHAT_FALLBACK_MODEL_KEY, DEFAULT_CHAT_MODEL_KEY } from '@/types/model-types'

/**
 * When the primary chat model is out of quota, answers must keep flowing from the fallback model
 * instead of surfacing an error to the user.
 */

const calls: { model: string; streamed: boolean }[] = []
/** Model names that should reject, and with what. */
const failures = new Map<string, string>()

const QUOTA_ERROR =
  '[GoogleGenerativeAI Error]: Error fetching from ' +
  'https://generativelanguage.googleapis.com/v1beta/models/x:generateContent: ' +
  '[429 Too Many Requests] You exceeded your current quota. Quota exceeded for metric: ' +
  'generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20'

const usageMetadata = {
  promptTokenCount: 12_000,
  candidatesTokenCount: 100,
  cachedContentTokenCount: 0,
  thoughtsTokenCount: 0,
  totalTokenCount: 12_100,
}

vi.mock('@google/generative-ai', () => ({
  GoogleGenerativeAI: class {
    getGenerativeModel({ model }: { model: string }) {
      const guard = (streamed: boolean) => {
        calls.push({ model, streamed })
        const failure = failures.get(model)
        if (failure) {
          throw new Error(failure)
        }
      }

      return {
        startChat: () => ({
          sendMessage: async (prompt: string) => {
            guard(false)
            return { response: { text: () => `Svar från ${model}: ${prompt.length}`, usageMetadata } }
          },
          sendMessageStream: async () => {
            guard(true)
            const text = `Strömmat svar från ${model}`
            return {
              stream: (async function* () {
                yield { text: () => text }
              })(),
              response: Promise.resolve({ text: () => text, usageMetadata }),
            }
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

const { getGeminiChatResponse, getGeminiChatResponseStream } = await import('../gemini-service')
const { clearAllConversations } = await import('../conversation-store')

const PRIMARY = DEFAULT_CHAT_MODEL_KEY
const FALLBACK = DEFAULT_CHAT_FALLBACK_MODEL_KEY

const userMessage = (text: string): Message => ({
  id: `msg-${text}`,
  text,
  role: 'user',
  timestamp: new Date('2026-08-05T10:00:00Z'),
})

describe('Chat model fallback when resources are exhausted', () => {
  beforeEach(() => {
    calls.length = 0
    failures.clear()
    clearAllConversations()
  })

  it('uses the primary model while it has quota', async () => {
    const answer = await getGeminiChatResponse(userMessage('Fråga'), 'user-1')

    expect(calls.map((call) => call.model)).toEqual([PRIMARY])
    expect(answer).toContain(PRIMARY)
  })

  it('falls back when the primary reports exhausted quota', async () => {
    failures.set(PRIMARY, QUOTA_ERROR)

    const answer = await getGeminiChatResponse(userMessage('Fråga'), 'user-1')

    expect(calls.map((call) => call.model)).toEqual([PRIMARY, FALLBACK])
    expect(answer).toContain(FALLBACK)
  })

  it('falls back while streaming, before any text reaches the client', async () => {
    failures.set(PRIMARY, QUOTA_ERROR)
    const deltas: string[] = []

    const answer = await getGeminiChatResponseStream(userMessage('Fråga'), 'user-1', { type: 'single' }, {
      onAnswerDelta: (text) => {
        deltas.push(text)
      },
    })

    expect(calls.map((call) => call.model)).toEqual([PRIMARY, FALLBACK])
    expect(answer).toContain(FALLBACK)
    expect(deltas.join('')).toBe(answer)
  })

  it('prices and reports the model that actually answered', async () => {
    failures.set(PRIMARY, QUOTA_ERROR)
    const usages: { modelKey: string; usedFallbackModel: boolean; cost: number }[] = []

    await getGeminiChatResponse(userMessage('Fråga'), 'user-1', { type: 'single' }, {
      onUsage: (usage) => {
        usages.push(usage)
      },
    })

    expect(usages).toHaveLength(1)
    expect(usages[0].modelKey).toBe(FALLBACK)
    expect(usages[0].usedFallbackModel).toBe(true)
    expect(usages[0].cost).toBeGreaterThan(0)
  })

  it('stores the fallback answer so the conversation stays cacheable', async () => {
    failures.set(PRIMARY, QUOTA_ERROR)
    const options = { conversationId: 'conv-fallback' }

    const first = await getGeminiChatResponse(userMessage('Fråga 1'), 'user-1', { type: 'single' }, options)
    await getGeminiChatResponse(userMessage('Fråga 2'), 'user-1', { type: 'single' }, options)

    const { getConversationTurns } = await import('../conversation-store')
    const turns = getConversationTurns('conv-fallback')
    expect(turns).toHaveLength(4)
    expect(turns[1].parts[0].text).toBe(first)
  })

  it('does not fall back on errors that are not resource exhaustion', async () => {
    failures.set(PRIMARY, '[GoogleGenerativeAI Error]: [400 Bad Request] invalid argument')

    const answer = await getGeminiChatResponse(userMessage('Fråga'), 'user-1')

    expect(calls.every((call) => call.model === PRIMARY)).toBe(true)
    expect(answer).toContain('Sorry, I encountered an error')
  })

  it('gives up gracefully when the fallback is exhausted too', async () => {
    failures.set(PRIMARY, QUOTA_ERROR)
    failures.set(FALLBACK, QUOTA_ERROR)

    const answer = await getGeminiChatResponse(userMessage('Fråga'), 'user-1')

    expect(calls.map((call) => call.model)).toEqual([PRIMARY, FALLBACK, FALLBACK])
    expect(answer).toContain('Sorry')
  })
})
