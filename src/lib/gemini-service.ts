import { GoogleGenerativeAI } from "@google/generative-ai";
import { getOpenAIEmbedding } from "./openai-service";
import { getContextFromKB, RetrievedContext } from "./knowledge-base-service";
import { getMultiStepContext, MultiStepAgentConfig, MultiStepRetrievalResult } from "./multi-step-agent-service";
import { SYSTEM_INSTRUCTION, SYSTEM_INSTRUCTION_NO_CONTEXT } from "./prompt";
import { trackLLMCall, trackChatInteraction } from "./posthog";
import { Message } from "@/types";
import { DEFAULT_QUERY_MODEL_KEY, calculateLLMCost, getLLMModelConfig } from "@/types/model-types";

const API_KEY = process.env.GEMINI_API_KEY;

if (!API_KEY) {
  throw new Error("GEMINI_API_KEY is not set in environment variables.");
}

const genAI = new GoogleGenerativeAI(API_KEY);

const { key: LLM_MODEL_KEY, config: LLM_CONFIG } = getLLMModelConfig(process.env.CHAT_MODEL_KEY);
const { config: LLM_CONFIG_QUERY } = getLLMModelConfig(
  process.env.QUERY_MODEL_KEY,
  DEFAULT_QUERY_MODEL_KEY
);
const MODEL_NAME = LLM_CONFIG.model;

const model = genAI.getGenerativeModel({
  model: MODEL_NAME,
});

const queryModel = genAI.getGenerativeModel({
  model: LLM_CONFIG_QUERY.model,
});

const generationConfig = {
  temperature: 0.7, // Slightly lower temperature for more factual RAG responses
  topK: 1,
  topP: 1,
  maxOutputTokens: LLM_CONFIG.maxOutputTokens,
};

// Chat history stores user queries and final RAG answers
const chatHistory: { role: "user" | "model"; parts: { text: string }[] }[] = [];

// Token estimation for cost tracking
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

export interface ChatStreamCallbacks {
  onReasoningDelta?: (text: string) => void | Promise<void>;
  onReasoningComplete?: () => void | Promise<void>;
  onAnswerDelta?: (text: string) => void | Promise<void>;
}

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
  let promptForGemini = "";
  let systemInstruction = SYSTEM_INSTRUCTION;

  const historyContext = message.history && message.history.trim()
    ? `\nRecent Chat History:\n${message.history}\n\n`
    : '';

  if (retrievedContext && (retrievedContext.segments.length > 0 || retrievedContext.topicName)) {
    const formattedContext = formatContextForPrompt(retrievedContext, agentApproach.type === 'multi-step');
    promptForGemini = `Context:\n${formattedContext}${historyContext}User Question: ${message.text}\n\nAnswer:`;
  } else {
    promptForGemini = historyContext + message.text;
    systemInstruction = SYSTEM_INSTRUCTION_NO_CONTEXT;
  }

  return {
    fullPrompt: systemInstruction + "\n\n" + promptForGemini,
    systemInstruction,
  };
};

const getRetrievedContext = async (
  message: Message,
  distinctId: string | undefined,
  agentApproach: AgentApproach
): Promise<{
  retrievedContext: RetrievedContext | null;
  multiStepResult: MultiStepRetrievalResult | null;
}> => {
  if (agentApproach.type === 'multi-step') {
    const multiStepResult = await getMultiStepContext(message, distinctId, agentApproach.config, queryModel);
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

const updateChatHistory = (userText: string, aiText: string) => {
  chatHistory.push({ role: "user", parts: [{ text: userText }] });
  chatHistory.push({ role: "model", parts: [{ text: aiText }] });

  if (chatHistory.length > 10) {
    chatHistory.splice(0, chatHistory.length - 10);
  }
};

export const getGeminiChatResponse = async (
  message: Message, 
  distinctId?: string,
  agentApproach: AgentApproach = { type: 'single' }
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
    const estimatedInputTokens = estimateTokens(fullPrompt);
    
    // Step 3: Generate response with Gemini (with retry logic)
    let text = "";
    let geminiDuration = 0;
    let lastGeminiError: Error | null = null;
    
    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const geminiStartTime = Date.now();
        const chat = model.startChat({
          generationConfig,
          history: [...chatHistory],
        });

        const result = await chat.sendMessage(fullPrompt);
        const response = result.response;
        text = response.text();
        geminiDuration = Date.now() - geminiStartTime;
        break; // Success, exit retry loop
        
      } catch (geminiError) {
        lastGeminiError = geminiError instanceof Error ? geminiError : new Error('Unknown Gemini error');
        
        // Check if this is a retryable error
        const isRetryable = lastGeminiError.message.includes('overloaded') || 
                           lastGeminiError.message.includes('503') ||
                           lastGeminiError.message.includes('429') ||
                           lastGeminiError.message.includes('timeout');
        
        if (isRetryable && attempt < MAX_RETRIES) {
          const delayMs = RETRY_DELAY_MS * Math.pow(2, attempt);
          await delay(delayMs);
          continue;
        }
        
        // If not retryable or max retries reached, throw the error
        throw lastGeminiError;
      }
    }
    
    // Step 4: Calculate metrics and track usage
    const estimatedOutputTokens = estimateTokens(text);
    const estimatedTotalTokens = estimatedInputTokens + estimatedOutputTokens;
    const estimatedCost = calculateLLMCost(LLM_MODEL_KEY, estimatedInputTokens, estimatedOutputTokens);

    // Track Gemini API call
    if (distinctId) {
      await trackLLMCall(distinctId, LLM_CONFIG.provider, MODEL_NAME, 'chat_completion', {
        inputTokens: estimatedInputTokens,
        outputTokens: estimatedOutputTokens,
        totalTokens: estimatedTotalTokens,
        duration: geminiDuration,
        cost: estimatedCost,
        success: true,
        temperature: generationConfig.temperature,
        maxTokens: generationConfig.maxOutputTokens,
        messageId: message.id,
      });
    }

    updateChatHistory(message.text, text);

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

export const getGeminiChatResponseStream = async (
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

  const emitReasoning = async (text: string) => {
    await callbacks.onReasoningDelta?.(text);
  };

  try {
    await emitReasoning("Jag läser frågan och väljer hur jag ska söka i källorna.\n");

    if (agentApproach.type === 'multi-step') {
      await emitReasoning("Jag använder flera riktade sökningar för att fånga relevanta partiståndpunkter.\n");
    } else {
      await emitReasoning("Jag gör en fokuserad sökning mot kunskapsbasen.\n");
    }

    const contextResult = await getRetrievedContext(message, distinctId, agentApproach);
    retrievedContext = contextResult.retrievedContext;
    multiStepResult = contextResult.multiStepResult;

    const segmentCount = retrievedContext?.segments.length ?? 0;
    const documentCount = retrievedContext?.documentsReferenced?.length ?? 0;

    if (segmentCount > 0) {
      await emitReasoning(`Jag hittade ${segmentCount} relevanta källavsnitt från ${documentCount} dokument.\n`);
    } else {
      await emitReasoning("Jag hittade inget tydligt källunderlag och kommer att vara försiktig i svaret.\n");
    }

    await emitReasoning("Jag formulerar svaret med källmaterialet som grund.\n");
    await callbacks.onReasoningComplete?.();

    const { fullPrompt } = buildPrompt(message, retrievedContext, agentApproach);
    const estimatedInputTokens = estimateTokens(fullPrompt);
    const geminiStartTime = Date.now();

    const chat = model.startChat({
      generationConfig,
      history: [...chatHistory],
    });

    const result = await chat.sendMessageStream(fullPrompt);

    for await (const chunk of result.stream) {
      const delta = chunk.text();
      if (!delta) {
        continue;
      }

      aiResponse += delta;
      await callbacks.onAnswerDelta?.(delta);
    }

    if (!aiResponse) {
      const response = await result.response;
      aiResponse = response.text();
      await callbacks.onAnswerDelta?.(aiResponse);
    }

    const geminiDuration = Date.now() - geminiStartTime;
    const estimatedOutputTokens = estimateTokens(aiResponse);
    const estimatedTotalTokens = estimatedInputTokens + estimatedOutputTokens;
    const estimatedCost = calculateLLMCost(LLM_MODEL_KEY, estimatedInputTokens, estimatedOutputTokens);

    if (distinctId) {
      await trackLLMCall(distinctId, LLM_CONFIG.provider, MODEL_NAME, 'chat_completion_stream', {
        inputTokens: estimatedInputTokens,
        outputTokens: estimatedOutputTokens,
        totalTokens: estimatedTotalTokens,
        duration: geminiDuration,
        cost: estimatedCost,
        success: true,
        temperature: generationConfig.temperature,
        maxTokens: generationConfig.maxOutputTokens,
        messageId: message.id,
      });
    }

    updateChatHistory(message.text, aiResponse);
    return aiResponse;
  } catch (error) {
    success = false;
    errorMessage = error instanceof Error ? error.message : 'Unknown error';

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

    await callbacks.onReasoningComplete?.();
    await callbacks.onAnswerDelta?.(aiResponse);
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
