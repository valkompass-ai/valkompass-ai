import { describe, it, expect, beforeEach, vi } from 'vitest'
import { NextRequest } from 'next/server'

/**
 * The conversation id decides whose earlier turns are replayed into a prompt, so the route must
 * not hand it to the chat service as sent. These tests pin the two properties that keep one
 * visitor's history out of another's answer.
 */

const chatCalls: { conversationId?: string; userAgent?: string }[] = []

vi.mock('@/lib/chat-service', () => ({
  getChatResponse: async (
    _message: unknown,
    _distinctId: string,
    _approach: unknown,
    options: { conversationId?: string }
  ) => {
    chatCalls.push({ conversationId: options?.conversationId })
    return 'svar'
  },
  getChatResponseStream: async () => 'svar',
}))

vi.mock('@/lib/posthog', () => ({
  trackEvent: vi.fn(),
  trackApiCall: vi.fn(),
  trackLLMCall: vi.fn(),
  trackChatInteraction: vi.fn(),
}))

const { POST } = await import('../route')

const post = (conversationId: unknown, userAgent = 'test-agent') =>
  POST(
    new NextRequest('http://localhost:3000/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'user-agent': userAgent },
      body: JSON.stringify({
        message: { id: 'm1', text: 'Vad tycker M?', role: 'user', timestamp: new Date() },
        agentConfig: { approach: 'single' },
        conversationId,
      }),
    })
  )

const VALID_ID = '0195e2a7-1c4d-7a3b-8f21-9c1de2b45a77'

describe('conversation id handling in the chat route', () => {
  beforeEach(() => {
    chatCalls.length = 0
  })

  it('namespaces the conversation per requester', async () => {
    await post(VALID_ID, 'browser-a')
    await post(VALID_ID, 'browser-b')

    expect(chatCalls).toHaveLength(2)
    expect(chatCalls[0].conversationId).toContain(VALID_ID)
    // Same client-supplied id, different visitors: the keys must not collide.
    expect(chatCalls[0].conversationId).not.toBe(chatCalls[1].conversationId)
  })

  it('is stable for the same requester so follow-ups keep their history', async () => {
    await post(VALID_ID, 'browser-a')
    await post(VALID_ID, 'browser-a')

    expect(chatCalls[0].conversationId).toBe(chatCalls[1].conversationId)
  })

  it.each([
    ['not-a-uuid', 'not-a-uuid'],
    ['empty', ''],
    ['a traversal-ish value', '../../other-user'],
    ['a number', 42],
    ['an object', { id: VALID_ID }],
    ['an over-long string', 'a'.repeat(5000)],
  ])('ignores %s instead of using it as a lookup key', async (_label, value) => {
    await post(value)

    expect(chatCalls[0].conversationId).toBeUndefined()
  })

  it('starts cold when no conversation id is sent', async () => {
    await post(undefined)

    expect(chatCalls[0].conversationId).toBeUndefined()
  })
})
