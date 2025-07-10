import { describe, it, expect, beforeAll, afterAll } from 'vitest'
import { POST } from '../route'
import { NextRequest } from 'next/server'
import { Message } from '@/types'
import { v7 as uuidv7 } from 'uuid'

const TEST_TIMEOUT = 30000

describe('Chat API Integration Tests', () => {
  beforeAll(() => {
    expect(process.env.GEMINI_API_KEY).toBeDefined()
    expect(process.env.OPENAI_API_KEY).toBeDefined()
    expect(process.env.NEO4J_URI).toBeDefined()
  })

  afterAll(async () => {
    const { closeNeo4jDriver } = await import('@/lib/knowledge-base-service')
    await closeNeo4jDriver()
  })

  describe('Multi-Step Agent Functionality', () => {
    it('should respond to a simple question with single-step approach', async () => {
      const userMessage: Message = {
        id: uuidv7(),
        text: 'Vad är Socialdemokraterna?',
        role: 'user',
        timestamp: new Date(),
      }

      const request = new NextRequest('http://localhost:3000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          message: userMessage,
          agentConfig: { approach: 'single' }
        }),
      })

      const response = await POST(request)
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.message).toBeDefined()
      expect(data.message.role).toBe('ai')
      expect(data.message.text).toBeTruthy()
      expect(data.message.text.length).toBeGreaterThan(50)
    }, TEST_TIMEOUT)

    it('should handle invalid message format', async () => {
      const request = new NextRequest('http://localhost:3000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: { text: 123 } }), // Invalid text type
      })

      const response = await POST(request)
      const data = await response.json()

      expect(response.status).toBe(400)
      expect(data.error).toBe('Invalid message format')
    })

    it('should use multi-step approach for comparative queries', async () => {
      const userMessage: Message = {
        id: uuidv7(),
        text: 'Jämför V och M om kärnkraft',
        role: 'user',
        timestamp: new Date(),
      }

      const request = new NextRequest('http://localhost:3000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          message: userMessage,
          agentConfig: { approach: 'default' }
        }),
      })

      const response = await POST(request)
      const data = await response.json()

      expect(response.status).toBe(200)
      expect(data.message.text).toBeTruthy()
      
      // Multi-step should include information about both parties
      const responseText = data.message.text.toLowerCase()
      expect(responseText).toContain('vänsterpartiet')
      expect(responseText).toContain('moderaterna')
    }, TEST_TIMEOUT)
  })
})