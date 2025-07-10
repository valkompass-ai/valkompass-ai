import { GoogleGenerativeAI } from "@google/generative-ai";
import { getOpenAIEmbedding } from "./openai-service";
import { getContextFromKB, RetrievedContext } from "./knowledge-base-service";
import { SYSTEM_INSTRUCTION, SYSTEM_INSTRUCTION_NO_CONTEXT } from "./prompt";
import { trackLLMCall, trackChatInteraction } from "./posthog";
import { Message } from "@/types";
import { LLM_MODELS, calculateLLMCost, type LLMModelKey } from "@/types/model-types";

const API_KEY = process.env.GEMINI_API_KEY;

if (!API_KEY) {
  throw new Error("GEMINI_API_KEY is not set in environment variables.");
}

const genAI = new GoogleGenerativeAI(API_KEY);

// Using the model configuration from centralized types
const LLM_MODEL_KEY: LLMModelKey = 'gemini-1.5-flash-latest';
const LLM_CONFIG = LLM_MODELS[LLM_MODEL_KEY];
const MODEL_NAME = LLM_CONFIG.model;

const model = genAI.getGenerativeModel({
  model: MODEL_NAME,
});

const generationConfig = {
  temperature: 0.7, // Slightly lower temperature for more factual RAG responses
  topK: 1,
  topP: 1,
  maxOutputTokens: LLM_CONFIG.maxOutputTokens,
};

// Rough token estimation (Gemini uses different tokenization but this is approximate)
const estimateTokens = (text: string): number => {
  // Very rough approximation: 1 token ≈ 4 characters for English text
  return Math.ceil(text.length / 4);
};

// Chat history will now store user queries and final RAG answers
const chatHistory: { role: "user" | "model"; parts: { text: string }[] }[] = [];

const formatContextForPrompt = (context: RetrievedContext): string => {
  let formattedContext = `Relevant Topic: ${context.topicName}\nDescription: ${context.topicDescription}\n\n`;
  if (context.segments.length > 0) {
    formattedContext += "Relevant Segments from Documents:\n";
    context.segments.forEach((seg, index) => {
      // Include publicUrl in the source information if available
      const sourceInfo = seg.publicUrl 
        ? `(Source URL: ${seg.publicUrl}, Document: ${seg.documentPath}, Page: ${seg.segmentPage || 'N/A'})` 
        : `(Source Document: ${seg.documentPath}, Page: ${seg.segmentPage || 'N/A'})`;
      formattedContext += `  ${index + 1}. Text: "${seg.segmentText}" ${sourceInfo}\n`;
    });
  }
  return formattedContext;
};

export const getGeminiChatResponse = async (message: Message, distinctId?: string): Promise<string> => {
  const overallStartTime = Date.now();
  let retrievedContext: RetrievedContext | null = null;
  let aiResponse = "";
  let success = true;
  let errorMessage = "";
  
  try {
    // 1. Get embedding for user message
    const queryEmbedding = await getOpenAIEmbedding(message.text, message.id, distinctId);

    // 2. Fetch context from Neo4j
    retrievedContext = await getContextFromKB(queryEmbedding, message.id, distinctId);
    
    let promptForGemini = "";
    let systemInstruction = SYSTEM_INSTRUCTION;
    
    // Include client-side chat history if available
    const historyContext = message.history && message.history.trim() 
      ? `\nRecent Chat History:\n${message.history}\n\n` 
      : '';
    
    if (retrievedContext && (retrievedContext.segments.length > 0 || retrievedContext.topicName)) {
      const formattedContext = formatContextForPrompt(retrievedContext);
      promptForGemini = `Context:\n${formattedContext}${historyContext}User Question: ${message.text}\n\nAnswer:`;
    } else {
      // Fallback if no context is found, or handle as a direct question to Gemini without RAG
      promptForGemini = historyContext + message.text; // Send user message directly if no context
      systemInstruction = SYSTEM_INSTRUCTION_NO_CONTEXT;
      console.warn("No specific context found from KB for the query. Proceeding with a general response.");
    }

    const fullPrompt = systemInstruction + "\n\n" + promptForGemini;
    
    // Estimate input tokens for tracking
    const estimatedInputTokens = estimateTokens(fullPrompt);
    
    const geminiStartTime = Date.now();
    const chat = model.startChat({
      generationConfig,
      history: [
        ...chatHistory,
      ],
    });

    const result = await chat.sendMessage(fullPrompt);
    const response = result.response;
    const text = response.text();
    const geminiDuration = Date.now() - geminiStartTime;
    
    // Estimate output tokens
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

    // Update main chat history with the user's original question and AI's RAG-informed answer
    chatHistory.push({ role: "user", parts: [{ text: message.text }] });
    chatHistory.push({ role: "model", parts: [{ text }] });

    if (chatHistory.length > 10) { // Keep history to last 5 exchanges (10 messages)
      chatHistory.splice(0, chatHistory.length - 10);
    }

    aiResponse = text;
    return text;
  } catch (error) {
    success = false;
    errorMessage = error instanceof Error ? error.message : 'Unknown error';
    
    // Track failed Gemini call
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
    
    console.error("Error in RAG pipeline or getting response from Gemini:", error);
    
    // Provide user-friendly error messages
    if (error instanceof Error && error.message.includes("OPENAI_API_KEY")){
        aiResponse = "OpenAI API key is not configured correctly. Please check server logs.";
    } else if (error instanceof Error && error.message.includes("Neo4j")){
        aiResponse = "Could not connect to the knowledge base. Please check server logs.";
    } else {
        aiResponse = "Sorry, I encountered an error trying to answer your question. Please try again later.";
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
        })),
        
        // RAG metrics
        retrievalSuccess: retrievedContext !== null,
        retrievalDuration: retrievedContext?.retrievalDuration,
        numSegmentsRetrieved: retrievedContext?.totalSegmentsFound,
        avgSimilarityScore: retrievedContext?.avgSimilarityScore,
      });
    }
  }
}; 