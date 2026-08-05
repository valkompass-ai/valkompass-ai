import { describe, it, expect, vi } from 'vitest'
import type { Message } from '@/types'
import type { ChatUsage } from '../gemini-service'

/**
 * Live measurement of Gemini context caching over a multi-turn conversation.
 *
 * Opt-in: it calls the real API and costs tokens.
 *
 *   RUN_LIVE_GEMINI_CACHE_TEST=1 bun run test:run -- src/lib/__tests__/gemini-cache.live.test.ts
 *
 * What is asserted here is only what the app controls: each follow-up request replays the previous
 * ones verbatim, the prompt is large enough to be cache eligible, and a reported cache hit really
 * does lower the cost. The hit rate itself is logged, not asserted — Gemini's implicit cache is
 * best-effort and misses under load. The deterministic prefix guarantee lives in
 * gemini-service.cache.test.ts.
 */

const LIVE = process.env.RUN_LIVE_GEMINI_CACHE_TEST === '1'

// Retrieval is stubbed so this needs no Neo4j and no embeddings: caching depends on prompt size and
// byte stability, not on where the text came from. The segment count and length mirror what
// multi-step retrieval returns in production, well above the model's implicit cache minimum.
const SEGMENTS = Array.from({ length: 25 }, (_, index) => ({
  segmentText: `Avsnitt ${index + 1}: ${'Partiet vill utveckla svensk energipolitik, skola och sjukvård med långsiktig hållbarhet och rättvis fördelning som utgångspunkt. '.repeat(12)}`,
  documentPath: `parti-${index % 8}/valmanifest.pdf`,
  segmentPage: index % 40,
  similarityScore: 0.9 - index * 0.01,
  partyAbbreviation: ['S', 'M', 'C', 'L', 'V', 'MP', 'KD', 'SD'][index % 8],
  publicUrl: `/kb-documents/parti-${index % 8}/valmanifest.pdf`,
  documentSourceType: 'pdf',
}))

vi.mock('../openai-service', () => ({
  getOpenAIEmbedding: async () => new Array(1536).fill(0.01),
}))

vi.mock('../knowledge-base-service', () => ({
  getContextFromKB: async () => ({
    topicName: 'Svensk politik',
    topicDescription: 'Partiernas ståndpunkter',
    segments: SEGMENTS,
    retrievalDuration: 10,
    totalSegmentsFound: SEGMENTS.length,
    avgSimilarityScore: 0.8,
    documentsReferenced: [{ path: 'parti-0/valmanifest.pdf' }],
  }),
}))

vi.mock('../posthog', () => ({
  trackLLMCall: vi.fn(),
  trackChatInteraction: vi.fn(),
}))

const { getGeminiChatResponseStream } = await import('../gemini-service')

const TURNS = [
  'Vad tycker partierna om kärnkraft och energipolitik?',
  'Och hur skiljer sig deras syn på skolan?',
  'Vilken av dessa ståndpunkter är mest konkret?',
]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** The API returns 503 under load; retry so a busy model does not read as a caching regression. */
const runTurn = async (
  conversationId: string,
  message: Message,
  attempts = 6
): Promise<ChatUsage> => {
  for (let attempt = 0; attempt < attempts; attempt++) {
    let usage: ChatUsage | undefined
    await getGeminiChatResponseStream(message, undefined, { type: 'single' }, {
      conversationId,
      onUsage: (reported) => {
        usage = reported
      },
    })

    if (usage) {
      return usage
    }

    await sleep(5_000 * (attempt + 1))
  }

  throw new Error(`Gemini did not answer "${message.text}" after ${attempts} attempts`)
}

describe.skipIf(!LIVE)('Gemini context cache (live)', () => {
  it('replays a growing cacheable prefix and prices cache hits lower', async () => {
    const conversationId = `live-cache-${Date.now()}`
    const usages: ChatUsage[] = []

    for (const [index, text] of TURNS.entries()) {
      usages.push(
        await runTurn(conversationId, {
          id: `live-${index}`,
          text,
          role: 'user',
          timestamp: new Date(),
        })
      )
      // Roughly the pace of a reading user.
      await sleep(3_000)
    }

    console.log(
      usages
        .map(
          (usage, index) =>
            `turn ${index + 1}: prompt=${usage.promptTokens} cached=${usage.cachedPromptTokens} ` +
            `hit=${(usage.cacheHitRate * 100).toFixed(1)}% cost=$${usage.cost.toFixed(5)} ` +
            `(uncached $${usage.costWithoutCache.toFixed(5)})`
        )
        .join('\n')
    )

    // Every prompt is large enough for the model to cache at all.
    for (const usage of usages) {
      expect(usage.cacheEligible).toBe(true)
    }

    // Follow-ups carry the earlier turns verbatim, so the prompt grows monotonically. This is the
    // shared prefix the cache can serve; without it a hit is impossible.
    expect(usages[1].promptTokens).toBeGreaterThan(usages[0].promptTokens)
    expect(usages[2].promptTokens).toBeGreaterThan(usages[1].promptTokens)

    // A reported hit must actually reduce what we pay.
    for (const usage of usages.filter((candidate) => candidate.cachedPromptTokens > 0)) {
      expect(usage.cost).toBeLessThan(usage.costWithoutCache)
    }
  }, 900_000)
})
