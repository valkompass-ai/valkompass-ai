import { PostHog } from 'posthog-node'

let postHogClient: PostHog | null = null

export function getPostHogClient(): PostHog {
  if (!postHogClient) {
    const apiKey = process.env.POSTHOG_API_KEY || 'phc_IE197mA4DKVyht5ZJCKTqUz7OUpAYCPXXLVUPKjSiSL'
    const host = process.env.POSTHOG_HOST || 'https://eu.i.posthog.com'
    
    postHogClient = new PostHog(
      apiKey,
      {
        host,
        // Flush events every 30 seconds or when 20 events are queued
        flushAt: 20,
        flushInterval: 30000,
      }
    )
  }
  return postHogClient
}

export async function trackEvent(
  distinctId: string,
  event: string,
  properties?: Record<string, unknown>
) {
  try {
    const client = getPostHogClient()
    client.capture({
      distinctId,
      event,
      properties: {
        ...properties,
        timestamp: new Date().toISOString(),
      }
    })
  } catch (error) {
    console.error('PostHog tracking error:', error)
  }
}

export async function trackApiCall(
  distinctId: string,
  endpoint: string,
  method: string,
  statusCode: number,
  duration?: number,
  properties?: Record<string, unknown>
) {
  await trackEvent(distinctId, 'api_call', {
    endpoint,
    method,
    status_code: statusCode,
    duration_ms: duration,
    ...properties
  })
}

// Enhanced tracking for LLM operations
export async function trackLLMCall(
  distinctId: string,
  provider: string,
  model: string,
  operation: string,
  properties?: {
    inputTokens?: number;
    outputTokens?: number;
    totalTokens?: number;
    /** Prompt tokens served from Gemini's context cache, billed at the reduced cache rate. */
    cachedInputTokens?: number;
    cacheHitRate?: number;
    cacheEligible?: boolean;
    thoughtsTokens?: number;
    duration?: number;
    cost?: number;
    /** Cost the call would have had without any cache hit. */
    costWithoutCache?: number;
    cacheSavingsUsd?: number;
    /** True when the primary chat model was out of quota and the fallback model answered. */
    usedFallbackModel?: boolean;
    success?: boolean;
    errorMessage?: string;
    temperature?: number;
    maxTokens?: number;
    messageId?: string;
  }
) {
  await trackEvent(distinctId, 'llm_call', {
    provider,
    model,
    operation,
    input_tokens: properties?.inputTokens,
    output_tokens: properties?.outputTokens,
    total_tokens: properties?.totalTokens,
    cached_input_tokens: properties?.cachedInputTokens,
    cache_hit_rate: properties?.cacheHitRate,
    cache_eligible: properties?.cacheEligible,
    thoughts_tokens: properties?.thoughtsTokens,
    duration_ms: properties?.duration,
    cost_usd: properties?.cost,
    cost_without_cache_usd: properties?.costWithoutCache,
    cache_savings_usd: properties?.cacheSavingsUsd,
    used_fallback_model: properties?.usedFallbackModel,
    success: properties?.success ?? true,
    error_message: properties?.errorMessage,
    temperature: properties?.temperature,
    max_tokens: properties?.maxTokens,
    message_id: properties?.messageId,
    ...properties
  })
}

// Track chat interactions with detailed content and context
export async function trackChatInteraction(
  distinctId: string,
  properties: {
    messageId: string | number;
    userMessage: string;
    aiResponse?: string;
    messageLength: number;
    responseLength?: number;
    duration?: number;
    success?: boolean;
    errorMessage?: string;
    // Knowledge base context
    topicName?: string;
    topicDescription?: string;
    documentsReferenced?: Array<{
      path: string;
      type?: string;
      publicUrl?: string;
    }>;
    segmentsUsed?: Array<{
      documentPath: string;
      text: string;
      page?: number;
      similarityScore: number;
    }>;
    // RAG metrics
    retrievalSuccess?: boolean;
    retrievalDuration?: number;
    numSegmentsRetrieved?: number;
    avgSimilarityScore?: number;
  }
) {
  await trackEvent(distinctId, 'chat_interaction', {
    message_id: properties.messageId,
    user_message: properties.userMessage,
    ai_response: properties.aiResponse,
    message_length: properties.messageLength,
    response_length: properties.responseLength,
    duration_ms: properties.duration,
    success: properties.success ?? true,
    error_message: properties.errorMessage,
    
    // RAG context
    topic_name: properties.topicName,
    topic_description: properties.topicDescription,
    documents_referenced: properties.documentsReferenced,
    segments_used: properties.segmentsUsed,
    
    // RAG metrics
    retrieval_success: properties.retrievalSuccess,
    retrieval_duration_ms: properties.retrievalDuration,
    num_segments_retrieved: properties.numSegmentsRetrieved,
    avg_similarity_score: properties.avgSimilarityScore,
  })
}

// Track embedding operations
export async function trackEmbeddingCall(
  distinctId: string,
  provider: string,
  model: string,
  properties?: {
    textLength?: number;
    dimensions?: number;
    duration?: number;
    success?: boolean;
    errorMessage?: string;
    cost?: number;
    messageId?: string;
  }
) {
  await trackEvent(distinctId, 'embedding_call', {
    provider,
    model,
    text_length: properties?.textLength,
    dimensions: properties?.dimensions,
    duration_ms: properties?.duration,
    success: properties?.success ?? true,
    error_message: properties?.errorMessage,
    cost_usd: properties?.cost,
    message_id: properties?.messageId,
  })
}

// Track knowledge base queries
export async function trackKnowledgeBaseQuery(
  distinctId: string,
  properties: {
    queryType: 'semantic_search' | 'topic_search' | 'document_retrieval';
    success: boolean;
    duration?: number;
    resultsFound?: number;
    topSimilarityScore?: number;
    errorMessage?: string;
    messageId?: string;
  }
) {
  await trackEvent(distinctId, 'knowledge_base_query', {
    query_type: properties.queryType,
    success: properties.success,
    duration_ms: properties.duration,
    results_found: properties.resultsFound,
    top_similarity_score: properties.topSimilarityScore,
    error_message: properties.errorMessage,
    message_id: properties.messageId,
  })
}

// Graceful shutdown
export async function shutdownPostHog() {
  if (postHogClient) {
    await postHogClient.shutdown()
  }
} 