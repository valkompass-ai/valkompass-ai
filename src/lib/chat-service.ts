import OpenAI from "openai";
import { getOpenAIEmbedding } from "./openai-service";
import { getContextFromKB, RetrievedContext, RetrievedSegment } from "./knowledge-base-service";
import { getMultiStepContext, MultiStepAgentConfig, MultiStepRetrievalResult } from "./multi-step-agent-service";
import { SYSTEM_INSTRUCTION, SYSTEM_INSTRUCTION_NO_CONTEXT } from "./prompt";
import { appendConversationTurn, getConversationTurns } from "./conversation-store";
import { trackLLMCall, trackChatInteraction } from "./posthog";
import { ChatTrace, ChatTraceQuery, ChatTraceSource, Message } from "@/types";
import {
  DEFAULT_QUERY_MODEL_KEY,
  ReasoningEffort,
  calculateLLMCost,
  getLLMModelConfig,
} from "@/types/model-types";

const API_KEY = process.env.OPENAI_API_KEY;

if (!API_KEY) {
  throw new Error("OPENAI_API_KEY is not set in environment variables.");
}

const openai = new OpenAI({ apiKey: API_KEY });

const { key: LLM_MODEL_KEY, config: LLM_CONFIG } = getLLMModelConfig(process.env.CHAT_MODEL_KEY);
const { config: LLM_CONFIG_QUERY } = getLLMModelConfig(
  process.env.QUERY_MODEL_KEY,
  DEFAULT_QUERY_MODEL_KEY
);
const MODEL_NAME = LLM_CONFIG.model;

const asReasoningEffort = (value: string | undefined, fallback: ReasoningEffort): ReasoningEffort =>
  value === 'low' || value === 'medium' || value === 'high' || value === 'max' ? value : fallback;

/**
 * The Responses API accepts and echoes back `effort: "max"` on gpt-5.6-luna, but the pinned SDK's
 * union stops at "xhigh". Cast at this single boundary rather than downgrading the effort.
 */
type SdkReasoning = { effort: 'low' | 'medium' | 'high' };
const toSdkReasoning = (effort: ReasoningEffort): SdkReasoning => ({ effort }) as unknown as SdkReasoning;

const REASONING_EFFORT = asReasoningEffort(process.env.CHAT_REASONING_EFFORT, LLM_CONFIG.reasoningEffort);
/**
 * Query generation is a small JSON task on the critical path of every question. It defaults to the
 * model's effort like chat does, but is separately tunable because reasoning time is latency here.
 */
const QUERY_REASONING_EFFORT = asReasoningEffort(
  process.env.QUERY_REASONING_EFFORT,
  LLM_CONFIG_QUERY.reasoningEffort
);

const generationConfig = {
  temperature: 0.7, // Slightly lower temperature for more factual RAG responses
  maxOutputTokens: LLM_CONFIG.maxOutputTokens,
  reasoningEffort: REASONING_EFFORT,
};

// Token estimation, only used as a fallback when the API reports no usage metadata
const estimateTokens = (text: string): number => {
  // Very rough approximation: 1 token ≈ 4 characters for English text
  return Math.ceil(text.length / 4);
};

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1000;

const delay = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

export interface AgentApproach {
  type: 'single' | 'multi-step';
  config?: MultiStepAgentConfig;
}

/** Token accounting for one chat completion, read from the API's reported usage. */
export interface ChatUsage {
  /** Full prompt size. Cached tokens are counted inside this number as well. */
  promptTokens: number;
  /** Share of the prompt served from the context cache, billed at the reduced cache rate. */
  cachedPromptTokens: number;
  outputTokens: number;
  /** Tokens the model spent thinking. Billed at the output rate. */
  reasoningTokens: number;
  totalTokens: number;
  /** cachedPromptTokens / promptTokens, 0 when nothing was cached. */
  cacheHitRate: number;
  /** Whether the prompt was large enough for the model to be cache eligible at all. */
  cacheEligible: boolean;
  cost: number;
  /** What the same call would have cost with no cache hit, for measuring the saving. */
  costWithoutCache: number;
}

export interface ChatOptions {
  /**
   * Groups the turns of one chat. The previous turns are replayed verbatim, which is what lets
   * OpenAI serve the shared prefix from its prompt cache on follow-up questions.
   */
  conversationId?: string;
  onUsage?: (usage: ChatUsage) => void | Promise<void>;
}

export interface ChatStreamCallbacks extends ChatOptions {
  onTraceUpdate?: (trace: ChatTrace) => void | Promise<void>;
  onAnswerDelta?: (text: string) => void | Promise<void>;
}

interface OpenAIUsage {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  input_tokens_details?: { cached_tokens?: number };
  output_tokens_details?: { reasoning_tokens?: number };
}

const buildUsage = (
  usage: OpenAIUsage | undefined,
  promptText: string,
  answerText: string
): ChatUsage => {
  const promptTokens = usage?.input_tokens ?? estimateTokens(promptText);
  const reasoningTokens = usage?.output_tokens_details?.reasoning_tokens ?? 0;
  // OpenAI counts reasoning tokens inside output_tokens.
  const billedOutputTokens = usage?.output_tokens ?? estimateTokens(answerText);
  const outputTokens = Math.max(billedOutputTokens - reasoningTokens, 0);
  const cachedPromptTokens = Math.min(usage?.input_tokens_details?.cached_tokens ?? 0, promptTokens);

  return {
    promptTokens,
    cachedPromptTokens,
    outputTokens,
    reasoningTokens,
    totalTokens: usage?.total_tokens ?? promptTokens + billedOutputTokens,
    cacheHitRate: promptTokens > 0 ? cachedPromptTokens / promptTokens : 0,
    cacheEligible: promptTokens >= LLM_CONFIG.implicitCacheMinTokens,
    cost: calculateLLMCost(LLM_MODEL_KEY, promptTokens, billedOutputTokens, cachedPromptTokens),
    costWithoutCache: calculateLLMCost(LLM_MODEL_KEY, promptTokens, billedOutputTokens, 0),
  };
};

const usageTrackingProperties = (usage: ChatUsage) => ({
  inputTokens: usage.promptTokens,
  outputTokens: usage.outputTokens,
  totalTokens: usage.totalTokens,
  cachedInputTokens: usage.cachedPromptTokens,
  cacheHitRate: usage.cacheHitRate,
  cacheEligible: usage.cacheEligible,
  reasoningTokens: usage.reasoningTokens,
  cost: usage.cost,
  costWithoutCache: usage.costWithoutCache,
  cacheSavingsUsd: usage.costWithoutCache - usage.cost,
});

const formatContextForPrompt = (context: RetrievedContext, isMultiStep: boolean = false): string => {
  let formattedContext = `Relevant Topic: ${context.topicName}\nDescription: ${context.topicDescription}\n\n`;
  
  if (context.segments.length > 0) {
    formattedContext += "Relevant Segments from Documents:\n";
    context.segments.forEach((seg, index) => {
      const partyInfo = seg.partyAbbreviation ? ` (Party: ${seg.partyAbbreviation})` : '';
      const sourceInfo = seg.publicUrl 
        ? `(Source URL: ${seg.publicUrl}, Document: ${seg.documentPath}, Page: ${seg.segmentPage || 'N/A'}${partyInfo})` 
        : `(Source Document: ${seg.documentPath}, Page: ${seg.segmentPage || 'N/A'}${partyInfo})`;
      formattedContext += `  ${index + 1}. Text: "${seg.segmentText}" ${sourceInfo}\n`;
    });
  }
  
  if (isMultiStep) {
    formattedContext += `\nNote: This context was gathered using multiple targeted searches to provide comprehensive information.\n`;
  }
  
  return formattedContext;
};

const buildPrompt = (
  message: Message,
  retrievedContext: RetrievedContext | null,
  agentApproach: AgentApproach
): {
  fullPrompt: string;
  systemInstruction: string;
} => {
  let promptForModel = "";
  let systemInstruction = SYSTEM_INSTRUCTION;

  const historyContext = message.history && message.history.trim()
    ? `\nRecent Chat History:\n${message.history}\n\n`
    : '';

  if (retrievedContext && (retrievedContext.segments.length > 0 || retrievedContext.topicName)) {
    const formattedContext = formatContextForPrompt(retrievedContext, agentApproach.type === 'multi-step');
    promptForModel = `Context:\n${formattedContext}${historyContext}User Question: ${message.text}\n\nAnswer:`;
  } else {
    promptForModel = historyContext + message.text;
    systemInstruction = SYSTEM_INSTRUCTION_NO_CONTEXT;
  }

  return {
    fullPrompt: systemInstruction + "\n\n" + promptForModel,
    systemInstruction,
  };
};

/**
 * Turns stored history plus the new prompt into Responses API input. Replaying earlier turns
 * verbatim keeps the prefix byte-identical, which is what OpenAI's prompt cache matches on.
 */
const toResponseInput = (
  history: { role: 'user' | 'model'; parts: { text: string }[] }[],
  prompt: string
) => [
  ...history.map((turn) => ({
    role: turn.role === 'model' ? ('assistant' as const) : ('user' as const),
    content: turn.parts.map((part) => part.text).join(''),
  })),
  { role: 'user' as const, content: prompt },
];

const createChatRequest = (
  history: { role: 'user' | 'model'; parts: { text: string }[] }[],
  prompt: string,
  conversationId?: string
) => ({
  model: MODEL_NAME,
  input: toResponseInput(history, prompt),
  reasoning: toSdkReasoning(generationConfig.reasoningEffort),
  max_output_tokens: generationConfig.maxOutputTokens,
  // Routes same-conversation requests to the same cache shard, improving the hit rate.
  ...(conversationId ? { prompt_cache_key: conversationId } : {}),
});

/** Adapter so the multi-step agent keeps its provider-agnostic `generateContent` shape. */
const queryModel = {
  generateContent: async (prompt: string) => {
    const response = await openai.responses.create({
      model: LLM_CONFIG_QUERY.model,
      input: prompt,
      reasoning: toSdkReasoning(QUERY_REASONING_EFFORT),
      max_output_tokens: LLM_CONFIG_QUERY.maxOutputTokens,
    });

    return { response: { text: () => response.output_text ?? '' } };
  },
};

const getRetrievedContext = async (
  message: Message,
  distinctId: string | undefined,
  agentApproach: AgentApproach,
  traceCallbacks?: {
    onQueriesGenerated?: (queries: ChatTraceQuery[]) => void | Promise<void>;
    onQueryResult?: (
      query: ChatTraceQuery,
      context: RetrievedContext | null,
      error?: string
    ) => void | Promise<void>;
  }
): Promise<{
  retrievedContext: RetrievedContext | null;
  multiStepResult: MultiStepRetrievalResult | null;
}> => {
  if (agentApproach.type === 'multi-step') {
    const multiStepResult = await getMultiStepContext(
      message,
      distinctId,
      agentApproach.config,
      queryModel,
      {
        onQueriesGenerated: traceCallbacks?.onQueriesGenerated,
        onQueryResult: traceCallbacks?.onQueryResult,
      }
    );
    return {
      retrievedContext: multiStepResult.aggregatedContext,
      multiStepResult,
    };
  }

  const queryEmbedding = await getOpenAIEmbedding(message.text, message.id, distinctId);
  return {
    retrievedContext: await getContextFromKB(queryEmbedding, message.id, distinctId),
    multiStepResult: null,
  };
};

const toTraceSource = (segment: RetrievedSegment): ChatTraceSource => ({
  documentPath: segment.documentPath,
  snippet: segment.segmentText.length > 220
    ? `${segment.segmentText.slice(0, 217).trim()}...`
    : segment.segmentText,
  similarityScore: segment.similarityScore,
  publicUrl: segment.publicUrl,
  partyAbbreviation: segment.partyAbbreviation,
  page: segment.segmentPage,
  sourceType: segment.documentSourceType,
});

const createInitialTrace = (mode: AgentApproach['type']): ChatTrace => ({
  mode,
  status: 'running',
  events: [],
  queries: [],
  sources: [],
  documentCount: 0,
  segmentCount: 0,
});

const traceModeLabel = (mode: AgentApproach['type']) => mode === 'multi-step' ? 'flersteg' : 'ensteg';

const cloneTrace = (trace: ChatTrace): ChatTrace => ({
  ...trace,
  events: [...trace.events],
  queries: trace.queries.map((query) => ({
    ...query,
    sources: query.sources ? [...query.sources] : undefined,
  })),
  sources: [...trace.sources],
});

export const getChatResponse = async (
  message: Message,
  distinctId?: string,
  agentApproach: AgentApproach = { type: 'single' },
  options: ChatOptions = {}
): Promise<string> => {
  const overallStartTime = Date.now();
  let retrievedContext: RetrievedContext | null = null;
  let multiStepResult: MultiStepRetrievalResult | null = null;
  let aiResponse = "";
  let success = true;
  let errorMessage = "";
  
  try {
    const contextResult = await getRetrievedContext(message, distinctId, agentApproach);
    retrievedContext = contextResult.retrievedContext;
    multiStepResult = contextResult.multiStepResult;
    
    const { fullPrompt } = buildPrompt(message, retrievedContext, agentApproach);
    const history = getConversationTurns(options.conversationId);

    // Step 3: Generate the response (with retry logic)
    let text = "";
    let usage: ChatUsage | null = null;
    let llmDuration = 0;
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const startTime = Date.now();
        const response = await openai.responses.create(
          createChatRequest(history, fullPrompt, options.conversationId)
        );

        text = response.output_text ?? "";
        usage = buildUsage(response.usage, fullPrompt, text);
        llmDuration = Date.now() - startTime;
        break; // Success, exit retry loop

      } catch (llmError) {
        lastError = llmError instanceof Error ? llmError : new Error('Unknown LLM error');

        // Check if this is a retryable error
        const isRetryable = lastError.message.includes('overloaded') ||
                           lastError.message.includes('503') ||
                           lastError.message.includes('429') ||
                           lastError.message.includes('timeout');

        if (isRetryable && attempt < MAX_RETRIES) {
          const delayMs = RETRY_DELAY_MS * Math.pow(2, attempt);
          await delay(delayMs);
          continue;
        }

        // If not retryable or max retries reached, throw the error
        throw lastError;
      }
    }

    // Step 4: Calculate metrics and track usage
    const resolvedUsage = usage ?? buildUsage(undefined, fullPrompt, text);
    await options.onUsage?.(resolvedUsage);

    // Track the LLM call
    if (distinctId) {
      await trackLLMCall(distinctId, LLM_CONFIG.provider, MODEL_NAME, 'chat_completion', {
        ...usageTrackingProperties(resolvedUsage),
        duration: llmDuration,
        success: true,
        temperature: generationConfig.temperature,
        maxTokens: generationConfig.maxOutputTokens,
        messageId: message.id,
      });
    }

    appendConversationTurn(options.conversationId, fullPrompt, text);

    aiResponse = text;
    return text;
    
  } catch (error) {
    success = false;
    errorMessage = error instanceof Error ? error.message : 'Unknown error';
    
    // Track failed call
    if (distinctId) {
      await trackLLMCall(distinctId, LLM_CONFIG.provider, MODEL_NAME, 'chat_completion', {
        duration: Date.now() - overallStartTime,
        success: false,
        errorMessage,
        temperature: generationConfig.temperature,
        maxTokens: generationConfig.maxOutputTokens,
        messageId: message.id,
      });
    }
    
    // Handle specific error types
    if (error instanceof Error) {
      if (error.message.includes("OPENAI_API_KEY")) {
        aiResponse = "OpenAI API key is not configured correctly. Please check server logs.";
      } else if (error.message.includes("Neo4j")) {
        aiResponse = "Could not connect to the knowledge base. Please check server logs.";
      } else if (error.message.includes("overloaded") || error.message.includes("503")) {
        aiResponse = "The AI service is currently overloaded. Please try again in a moment.";
      } else {
        aiResponse = "Sorry, I encountered an error trying to answer your question. Please try again later.";
      }
    } else {
      aiResponse = "Sorry, I encountered an unexpected error. Please try again later.";
    }
    
    return aiResponse;
    
  } finally {
    // Track the complete chat interaction
    if (distinctId) {
      const totalDuration = Date.now() - overallStartTime;
      
      await trackChatInteraction(distinctId, {
        messageId: message.id,
        userMessage: message.text,
        aiResponse,
        messageLength: message.text.length,
        responseLength: aiResponse.length,
        duration: totalDuration,
        success,
        errorMessage: success ? undefined : errorMessage,
        
        // Knowledge base context
        topicName: retrievedContext?.topicName,
        topicDescription: retrievedContext?.topicDescription,
        documentsReferenced: retrievedContext?.documentsReferenced,
        segmentsUsed: retrievedContext?.segments.map(seg => ({
          documentPath: seg.documentPath,
          text: seg.segmentText,
          page: seg.segmentPage,
          similarityScore: seg.similarityScore,
          partyAbbreviation: seg.partyAbbreviation,
        })),
        
        // RAG metrics
        retrievalSuccess: retrievedContext !== null,
        retrievalDuration: retrievedContext?.retrievalDuration,
        numSegmentsRetrieved: retrievedContext?.totalSegmentsFound,
        avgSimilarityScore: retrievedContext?.avgSimilarityScore,
        
        // Multi-step metrics
        ...(multiStepResult && {
          multiStepMetrics: multiStepResult.metrics,
          agentApproach: agentApproach.type,
        }),
      });
    }
  }
};

export const getChatResponseStream = async (
  message: Message,
  distinctId?: string,
  agentApproach: AgentApproach = { type: 'single' },
  callbacks: ChatStreamCallbacks = {}
): Promise<string> => {
  const overallStartTime = Date.now();
  let retrievedContext: RetrievedContext | null = null;
  let multiStepResult: MultiStepRetrievalResult | null = null;
  let aiResponse = "";
  let success = true;
  let errorMessage = "";
  const trace = createInitialTrace(agentApproach.type);

  const emitTrace = async () => {
    await callbacks.onTraceUpdate?.(cloneTrace(trace));
  };

  const addTraceEvent = async (event: string) => {
    trace.events.push(event);
    await emitTrace();
  };

  const updateTraceFromContext = async (context: RetrievedContext | null) => {
    trace.topicName = context?.topicName || undefined;
    trace.sources = (context?.segments ?? []).map(toTraceSource);
    trace.segmentCount = trace.sources.length;
    trace.documentCount = context?.documentsReferenced?.length ?? 0;
    await emitTrace();
  };

  try {
    await addTraceEvent(`Källhämtning: ${traceModeLabel(agentApproach.type)}`);

    if (agentApproach.type === 'multi-step') {
      await addTraceEvent("Skapar sökningar");
    } else {
      trace.queries = [{ query: message.text }];
      await addTraceEvent(`Söker efter "${message.text}"`);
    }

    const contextResult = await getRetrievedContext(
      message,
      distinctId,
      agentApproach,
      {
        onQueriesGenerated: async (queries) => {
          trace.queries = queries.map((query) => ({
            query: query.query,
            partyFilter: query.partyFilter,
            reasoning: query.reasoning,
          }));
          await addTraceEvent(`Skapade ${trace.queries.length} sökningar`);
        },
        onQueryResult: async (query, context, error) => {
          const queryIndex = trace.queries.findIndex((item) =>
            item.query === query.query && item.partyFilter === query.partyFilter
          );
          const queryTrace: ChatTraceQuery = {
            query: query.query,
            partyFilter: query.partyFilter,
            reasoning: query.reasoning,
            returnedSegments: context?.segments.length ?? 0,
            error,
            sources: (context?.segments ?? []).map(toTraceSource),
          };

          if (queryIndex >= 0) {
            trace.queries[queryIndex] = {
              ...trace.queries[queryIndex],
              ...queryTrace,
            };
          } else {
            trace.queries.push(queryTrace);
          }

          await addTraceEvent(error
            ? `Sökningen "${query.query}" misslyckades`
            : `Sökningen "${query.query}" gav ${queryTrace.returnedSegments ?? 0} segment`
          );
        },
      }
    );
    retrievedContext = contextResult.retrievedContext;
    multiStepResult = contextResult.multiStepResult;

    if (agentApproach.type === 'single') {
      trace.queries[0] = {
        ...trace.queries[0],
        returnedSegments: retrievedContext?.segments.length ?? 0,
        sources: (retrievedContext?.segments ?? []).map(toTraceSource),
      };
      await addTraceEvent(`Sökningen "${message.text}" gav ${trace.queries[0].returnedSegments ?? 0} segment`);
    }

    await updateTraceFromContext(retrievedContext);

    if (trace.segmentCount > 0) {
      await addTraceEvent(`Förbereder svar från ${trace.segmentCount} källsegment`);
    } else {
      await addTraceEvent("Hittade inget tydligt källunderlag");
    }

    const { fullPrompt } = buildPrompt(message, retrievedContext, agentApproach);
    const history = getConversationTurns(callbacks.conversationId);
    const startTime = Date.now();

    const stream = await openai.responses.stream(
      createChatRequest(history, fullPrompt, callbacks.conversationId)
    );

    await addTraceEvent("Skriver svaret");

    let streamUsage: OpenAIUsage | undefined;

    for await (const event of stream) {
      if (event.type === 'response.output_text.delta' && event.delta) {
        aiResponse += event.delta;
        await callbacks.onAnswerDelta?.(event.delta);
      } else if (event.type === 'response.completed') {
        streamUsage = event.response.usage;
      }
    }

    const finalResponse = await stream.finalResponse();

    if (!aiResponse) {
      aiResponse = finalResponse.output_text ?? "";
      await callbacks.onAnswerDelta?.(aiResponse);
    }

    const llmDuration = Date.now() - startTime;
    const usage = buildUsage(streamUsage ?? finalResponse.usage, fullPrompt, aiResponse);
    await callbacks.onUsage?.(usage);

    if (distinctId) {
      await trackLLMCall(distinctId, LLM_CONFIG.provider, MODEL_NAME, 'chat_completion_stream', {
        ...usageTrackingProperties(usage),
        duration: llmDuration,
        success: true,
        temperature: generationConfig.temperature,
        maxTokens: generationConfig.maxOutputTokens,
        messageId: message.id,
      });
    }

    appendConversationTurn(callbacks.conversationId, fullPrompt, aiResponse);
    trace.status = 'complete';
    await emitTrace();
    return aiResponse;
  } catch (error) {
    success = false;
    errorMessage = error instanceof Error ? error.message : 'Unknown error';
    trace.status = 'error';
    await addTraceEvent("Svaret misslyckades");

    if (distinctId) {
      await trackLLMCall(distinctId, LLM_CONFIG.provider, MODEL_NAME, 'chat_completion_stream', {
        duration: Date.now() - overallStartTime,
        success: false,
        errorMessage,
        temperature: generationConfig.temperature,
        maxTokens: generationConfig.maxOutputTokens,
        messageId: message.id,
      });
    }

    if (error instanceof Error) {
      if (error.message.includes("OPENAI_API_KEY")) {
        aiResponse = "OpenAI API key is not configured correctly. Please check server logs.";
      } else if (error.message.includes("Neo4j")) {
        aiResponse = "Could not connect to the knowledge base. Please check server logs.";
      } else if (error.message.includes("overloaded") || error.message.includes("503")) {
        aiResponse = "The AI service is currently overloaded. Please try again in a moment.";
      } else {
        aiResponse = "Sorry, I encountered an error trying to answer your question. Please try again later.";
      }
    } else {
      aiResponse = "Sorry, I encountered an unexpected error. Please try again later.";
    }

    await callbacks.onAnswerDelta?.(aiResponse);
    await emitTrace();
    return aiResponse;
  } finally {
    if (distinctId) {
      const totalDuration = Date.now() - overallStartTime;

      await trackChatInteraction(distinctId, {
        messageId: message.id,
        userMessage: message.text,
        aiResponse,
        messageLength: message.text.length,
        responseLength: aiResponse.length,
        duration: totalDuration,
        success,
        errorMessage: success ? undefined : errorMessage,
        topicName: retrievedContext?.topicName,
        topicDescription: retrievedContext?.topicDescription,
        documentsReferenced: retrievedContext?.documentsReferenced,
        segmentsUsed: retrievedContext?.segments.map(seg => ({
          documentPath: seg.documentPath,
          text: seg.segmentText,
          page: seg.segmentPage,
          similarityScore: seg.similarityScore,
          partyAbbreviation: seg.partyAbbreviation,
        })),
        retrievalSuccess: retrievedContext !== null,
        retrievalDuration: retrievedContext?.retrievalDuration,
        numSegmentsRetrieved: retrievedContext?.totalSegmentsFound,
        avgSimilarityScore: retrievedContext?.avgSimilarityScore,
        ...(multiStepResult && {
          multiStepMetrics: multiStepResult.metrics,
          agentApproach: agentApproach.type,
        }),
      });
    }
  }
};
