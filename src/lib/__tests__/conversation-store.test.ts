import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  CONVERSATION_TTL_MS,
  MAX_CHARS_PER_CONVERSATION,
  MAX_CONVERSATIONS,
  MAX_TURNS_PER_CONVERSATION,
  appendConversationTurn,
  clearAllConversations,
  clearConversation,
  getConversationCount,
  getConversationTurns,
} from '../conversation-store'

describe('conversation store', () => {
  beforeEach(() => {
    clearAllConversations()
  })

  afterEach(() => {
    vi.useRealTimers()
    clearAllConversations()
  })

  it('returns no history for an unknown or missing conversation', () => {
    expect(getConversationTurns(undefined)).toEqual([])
    expect(getConversationTurns('never-seen')).toEqual([])
  })

  it('stores the prompt verbatim so the next request keeps the cacheable prefix', () => {
    const prompt = 'Context:\nRelevant Topic: Energi\n\nUser Question: Vad tycker M?\n\nAnswer:'
    appendConversationTurn('conv-1', prompt, 'Moderaterna vill ...')

    const turns = getConversationTurns('conv-1')
    expect(turns).toEqual([
      { role: 'user', parts: [{ text: prompt }] },
      { role: 'model', parts: [{ text: 'Moderaterna vill ...' }] },
    ])
  })

  it('grows history so turn N replays every earlier turn in order', () => {
    appendConversationTurn('conv-1', 'prompt-1', 'answer-1')
    appendConversationTurn('conv-1', 'prompt-2', 'answer-2')

    expect(getConversationTurns('conv-1').map((turn) => turn.parts[0].text)).toEqual([
      'prompt-1',
      'answer-1',
      'prompt-2',
      'answer-2',
    ])
  })

  it('keeps conversations isolated from each other', () => {
    appendConversationTurn('conv-1', 'prompt-1', 'answer-1')
    appendConversationTurn('conv-2', 'other-prompt', 'other-answer')

    expect(getConversationTurns('conv-1').map((turn) => turn.parts[0].text)).toEqual([
      'prompt-1',
      'answer-1',
    ])
    expect(getConversationTurns('conv-2').map((turn) => turn.parts[0].text)).toEqual([
      'other-prompt',
      'other-answer',
    ])
  })

  it('returns a copy so callers cannot mutate stored turns', () => {
    appendConversationTurn('conv-1', 'prompt-1', 'answer-1')

    const turns = getConversationTurns('conv-1')
    turns[0].parts[0].text = 'tampered'
    turns.push({ role: 'user', parts: [{ text: 'injected' }] })

    expect(getConversationTurns('conv-1').map((turn) => turn.parts[0].text)).toEqual([
      'prompt-1',
      'answer-1',
    ])
  })

  it('trims to whole exchanges so history never starts on a model turn', () => {
    for (let i = 1; i <= MAX_TURNS_PER_CONVERSATION; i++) {
      appendConversationTurn('conv-1', `prompt-${i}`, `answer-${i}`)
    }

    const turns = getConversationTurns('conv-1')
    expect(turns).toHaveLength(MAX_TURNS_PER_CONVERSATION)
    expect(turns[0].role).toBe('user')
    expect(turns[turns.length - 1].role).toBe('model')
    // Oldest exchanges dropped, newest kept.
    expect(turns[turns.length - 2].parts[0].text).toBe(`prompt-${MAX_TURNS_PER_CONVERSATION}`)
  })

  it('ignores writes without a conversation id or without content', () => {
    appendConversationTurn(undefined, 'prompt', 'answer')
    appendConversationTurn('conv-1', '', 'answer')
    appendConversationTurn('conv-1', 'prompt', '')

    expect(getConversationCount()).toBe(0)
  })

  it('drops a conversation once it goes idle past the TTL', () => {
    vi.useFakeTimers()
    appendConversationTurn('conv-1', 'prompt-1', 'answer-1')

    vi.advanceTimersByTime(CONVERSATION_TTL_MS + 1)

    expect(getConversationTurns('conv-1')).toEqual([])
    expect(getConversationCount()).toBe(0)
  })

  it('evicts the least recently used conversation past the cap', () => {
    for (let i = 0; i < MAX_CONVERSATIONS; i++) {
      appendConversationTurn(`conv-${i}`, 'prompt', 'answer')
    }
    // Touch the oldest so it is no longer the LRU entry.
    appendConversationTurn('conv-0', 'prompt-2', 'answer-2')
    appendConversationTurn('conv-overflow', 'prompt', 'answer')

    expect(getConversationCount()).toBe(MAX_CONVERSATIONS)
    expect(getConversationTurns('conv-0')).not.toEqual([])
    expect(getConversationTurns('conv-1')).toEqual([])
    expect(getConversationTurns('conv-overflow')).not.toEqual([])
  })

  it('drops the oldest exchanges once a conversation exceeds its character budget', () => {
    const big = 'x'.repeat(MAX_CHARS_PER_CONVERSATION / 3)

    appendConversationTurn('conv-1', `first-${big}`, 'answer-1')
    appendConversationTurn('conv-1', `second-${big}`, 'answer-2')
    appendConversationTurn('conv-1', `third-${big}`, 'answer-3')

    const turns = getConversationTurns('conv-1')
    const chars = turns.reduce((total, turn) => total + turn.parts[0].text.length, 0)

    expect(chars).toBeLessThanOrEqual(MAX_CHARS_PER_CONVERSATION)
    // Trimming keeps whole exchanges and keeps the newest.
    expect(turns.length % 2).toBe(0)
    expect(turns[0].role).toBe('user')
    expect(turns.at(-1)!.parts[0].text).toBe('answer-3')
    expect(turns.some((turn) => turn.parts[0].text.startsWith('first-'))).toBe(false)
  })

  it('never trims below the most recent exchange', () => {
    const huge = 'x'.repeat(MAX_CHARS_PER_CONVERSATION * 2)
    appendConversationTurn('conv-1', huge, 'answer')

    expect(getConversationTurns('conv-1')).toHaveLength(2)
  })

  it('clears a single conversation', () => {
    appendConversationTurn('conv-1', 'prompt-1', 'answer-1')
    clearConversation('conv-1')

    expect(getConversationTurns('conv-1')).toEqual([])
  })
})
