import { describe, it, expect, beforeEach, vi } from 'vitest'
import type { Message } from '@/types'

/**
 * Structural guarantee behind OpenAI's prompt cache: request N must be a byte-exact prefix
 * extension of request N-1. Whether the cache actually fires is the provider's business, but the
 * prefix property is entirely ours to keep and is tested here against a stubbed SDK.
 */

interface RecordedRequest {
  input: { role: string; content: string }[]
  promptCacheKey?: string
}

const recordedRequests: RecordedRequest[] = []
let answerCounter = 0
/** Set to simulate a run where reasoning consumed the whole output budget. */
let emptyAnswer = false

const usage = {
  input_tokens: 12_000,
  output_tokens: 150,
  total_tokens: 12_150,
  input_tokens_details: { cached_tokens: 9_000 },
  output_tokens_details: { reasoning_tokens: 50 },
}

vi.mock('openai', () => ({
  default: class {
    responses = {
      create: async (params: {
        input: RecordedRequest['input'] | string
        prompt_cache_key?: string
      }) => {
        if (typeof params.input === 'string') {
          // Query generation, which sends a bare string rather than a turn list.
          return { output_text: '{"queries":[]}', usage }
        }

        recordedRequests.push({ input: params.input, promptCacheKey: params.prompt_cache_key })
        answerCounter += 1
        if (emptyAnswer) {
          return { output_text: '', status: 'incomplete', incomplete_details: { reason: 'max_output_tokens' }, usage }
        }
        return { output_text: `Svar nummer ${answerCounter}`, usage }
      },
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

const { getChatResponse } = await import('../chat-service')
const { clearAllConversations } = await import('../conversation-store')
const { SYSTEM_INSTRUCTION } = await import('../prompt')

const userMessage = (text: string, history?: string): Message => ({
  id: `msg-${text}`,
  text,
  role: 'user',
  timestamp: new Date('2026-08-05T10:00:00Z'),
  history,
})

/** What the model actually receives, in order: the prior turns, then the new turn. */
const serializeRequest = (request: RecordedRequest): string =>
  request.input.map((turn) => `${turn.role}:${turn.content}`).join('\n')

describe('Gemini chat request shape for context caching', () => {
  beforeEach(() => {
    recordedRequests.length = 0
    answerCounter = 0
    emptyAnswer = false
    clearAllConversations()
  })

  it('leaves the prompt itself unchanged, system instruction included', async () => {
    await getChatResponse(userMessage('Vad tycker M om kärnkraft?'), 'user-1', { type: 'single' }, {
      conversationId: 'conv-a',
    })

    const firstPrompt = recordedRequests[0].input.at(-1)!.content
    expect(firstPrompt.startsWith(SYSTEM_INSTRUCTION)).toBe(true)
    expect(firstPrompt).toContain('User Question: Vad tycker M om kärnkraft?')
  })

  it('makes each follow-up request a strict prefix extension of the previous one', async () => {
    const options = { conversationId: 'conv-a' }

    await getChatResponse(userMessage('Vad tycker M om kärnkraft?'), 'user-1', { type: 'single' }, options)
    await getChatResponse(userMessage('Och vad tycker S?'), 'user-1', { type: 'single' }, options)
    await getChatResponse(userMessage('Vilken skillnad är störst?'), 'user-1', { type: 'single' }, options)

    expect(recordedRequests).toHaveLength(3)

    const [first, second, third] = recordedRequests.map(serializeRequest)
    expect(second.startsWith(first)).toBe(true)
    expect(third.startsWith(second)).toBe(true)
    // The extension carries real content, i.e. the prefix match is not the whole request.
    expect(second.length).toBeGreaterThan(first.length)
  })

  it('replays the earlier prompt with its retrieved context, not just the question', async () => {
    const options = { conversationId: 'conv-a' }

    await getChatResponse(userMessage('Vad tycker M om kärnkraft?'), 'user-1', { type: 'single' }, options)
    await getChatResponse(userMessage('Och vad tycker S?'), 'user-1', { type: 'single' }, options)

    const input = recordedRequests[1].input
    expect(input).toHaveLength(3)
    expect(input[0].role).toBe('user')
    expect(input[0].content).toBe(recordedRequests[0].input.at(-1)!.content)
    expect(input[0].content).toContain('Partiet vill bygga ut kärnkraften.')
    expect(input[1].role).toBe('assistant')
    expect(input[1].content).toBe('Svar nummer 1')
  })

  it('keeps conversations apart so one user never inherits another prefix', async () => {
    await getChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' }, { conversationId: 'conv-a' })
    await getChatResponse(userMessage('Fråga B'), 'user-2', { type: 'single' }, { conversationId: 'conv-b' })

    expect(recordedRequests[1].input).toHaveLength(1)
  })

  it('starts cold when no conversation id is supplied', async () => {
    await getChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' })
    await getChatResponse(userMessage('Fråga B'), 'user-1', { type: 'single' })

    expect(recordedRequests[0].input).toHaveLength(1)
    expect(recordedRequests[1].input).toHaveLength(1)
  })

  it('reports a failure instead of a blank answer when reasoning eats the output budget', async () => {
    emptyAnswer = true

    const answer = await getChatResponse(userMessage('Fråga'), 'user-1', { type: 'single' }, {
      conversationId: 'conv-empty',
    })

    expect(answer).toContain('Sorry')
    // A blank turn must never enter the history, or every later prompt replays it.
    const { getConversationTurns } = await import('../conversation-store')
    expect(getConversationTurns('conv-empty')).toEqual([])
  })

  it('tags requests with the conversation id so they share a cache shard', async () => {
    await getChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' }, { conversationId: 'conv-a' })
    await getChatResponse(userMessage('Fråga B'), 'user-1', { type: 'single' })

    expect(recordedRequests[0].promptCacheKey).toBe('conv-a')
    expect(recordedRequests[1].promptCacheKey).toBeUndefined()
  })

  it('reports cached tokens and the resulting saving', async () => {
    const usages: { cachedPromptTokens: number; cost: number; costWithoutCache: number }[] = []

    await getChatResponse(userMessage('Fråga A'), 'user-1', { type: 'single' }, {
      conversationId: 'conv-a',
      onUsage: (usage) => {
        usages.push(usage)
      },
    })

    expect(usages).toHaveLength(1)
    expect(usages[0].cachedPromptTokens).toBe(usage.input_tokens_details.cached_tokens)
    expect(usages[0].cost).toBeLessThan(usages[0].costWithoutCache)
  })

})
