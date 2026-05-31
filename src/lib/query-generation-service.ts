import { GoogleGenerativeAI } from "@google/generative-ai";
import { DEFAULT_QUERY_MODEL_KEY, calculateLLMCost, getLLMModelConfig } from "@/types/model-types";
import { trackLLMCall } from "./posthog";

const API_KEY = process.env.GEMINI_API_KEY;

if (!API_KEY) {
  throw new Error("GEMINI_API_KEY is not set in environment variables.");
}

const genAI = new GoogleGenerativeAI(API_KEY);

const { key: QUERY_LLM_MODEL_KEY, config: QUERY_LLM_CONFIG } = getLLMModelConfig(
  process.env.QUERY_MODEL_KEY,
  DEFAULT_QUERY_MODEL_KEY
);
const QUERY_MODEL_NAME = QUERY_LLM_CONFIG.model;

const queryModel = genAI.getGenerativeModel({
  model: QUERY_MODEL_NAME,
});

const queryGenerationConfig = {
  temperature: 0.3, // Lower temperature for more focused query generation
  topK: 1,
  topP: 1,
  maxOutputTokens: 1000,
};

export interface GeneratedQuery {
  query: string;
  partyFilter?: string;
  reasoning?: string;
}

export interface QueryGenerationResult {
  queries: GeneratedQuery[];
  originalQuery: string;
  totalTokensUsed: number;
  cost: number;
}

const PARTY_ABBREVIATIONS: Record<string, string> = {
  'socialdemokraterna': 'S',
  'moderaterna': 'M', 
  'centerpartiet': 'C',
  'liberalerna': 'L',
  'vansterpartiet': 'V',
  'miljopartiet': 'MP',
  'kristdemokraterna': 'KD',
  'sverigedemokraterna': 'SD',
  // Common abbreviations
  's': 'S',
  'm': 'M',
  'c': 'C',
  'l': 'L',
  'v': 'V',
  'mp': 'MP',
  'kd': 'KD',
  'sd': 'SD',
  // Alternative names
  'vänsterpartiet': 'V',
  'miljöpartiet': 'MP',
  'miljöpartiet de gröna': 'MP',
  'de gröna': 'MP',
  'sverige demokraterna': 'SD',
};

const QUERY_GENERATION_PROMPT = `Du är en expert på att skapa söktermer för att hitta information om svenska politiska partier och deras ståndpunkter.

Analysera användarens fråga och generera 1-10 söktermer som kan hjälpa till att svara på frågan. Varje sökning ska vara specifik och målgrupperad.

För varje sökning, överväg:
1. Vilka nyckelord som är mest relevanta
2. Om frågan handlar om specifika partier (använd partifilter)
3. Om frågan är jämförande (skapa separata sökningar för varje parti)
4. Olika sätt att formulera samma koncept

Tillgängliga partier och deras förkortningar:
- S (Socialdemokraterna)
- M (Moderaterna)
- C (Centerpartiet)
- L (Liberalerna)
- V (Vänsterpartiet)
- MP (Miljöpartiet)
- KD (Kristdemokraterna)
- SD (Sverigedemokraterna)

Svara ENDAST med giltig JSON i följande format:
{
  "queries": [
    {
      "query": "söksträng här",
      "partyFilter": "partiförkortning eller null",
      "reasoning": "varför denna sökning behövs"
    }
  ]
}

Exempel:
Fråga: "Vad tycker V och M om kärnkraft?"
Svar:
{
  "queries": [
    {
      "query": "kärnkraft energipolitik",
      "partyFilter": "V",
      "reasoning": "Vänsterpartiets ståndpunkt om kärnkraft"
    },
    {
      "query": "kärnkraft energipolitik",
      "partyFilter": "M", 
      "reasoning": "Moderaternas ståndpunkt om kärnkraft"
    },
    {
      "query": "kärnkraft reaktorer",
      "partyFilter": null,
      "reasoning": "Allmän information om kärnkraft för kontext"
    }
  ]
}

Användarens fråga: `;

// Rough token estimation (same as in gemini-service)
const estimateTokens = (text: string): number => {
  return Math.ceil(text.length / 4);
};

const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1000;

const delay = (ms: number): Promise<void> => new Promise(resolve => setTimeout(resolve, ms));

export const generateSearchQueries = async (
  userQuery: string, 
  messageId: string, 
  distinctId?: string
): Promise<QueryGenerationResult> => {
  const overallStartTime = Date.now();
  let lastError: Error | null = null;
  
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const fullPrompt = QUERY_GENERATION_PROMPT + userQuery;
      const estimatedInputTokens = estimateTokens(fullPrompt);
      
      const geminiStartTime = Date.now();
      const result = await queryModel.generateContent(fullPrompt);
      const response = result.response;
      const text = response.text();
      const geminiDuration = Date.now() - geminiStartTime;
    
    // Estimate output tokens
    const estimatedOutputTokens = estimateTokens(text);
    const estimatedTotalTokens = estimatedInputTokens + estimatedOutputTokens;
    const estimatedCost = calculateLLMCost(QUERY_LLM_MODEL_KEY, estimatedInputTokens, estimatedOutputTokens);

    // Track LLM call
    if (distinctId) {
      await trackLLMCall(distinctId, QUERY_LLM_CONFIG.provider, QUERY_MODEL_NAME, 'query_generation', {
        inputTokens: estimatedInputTokens,
        outputTokens: estimatedOutputTokens,
        totalTokens: estimatedTotalTokens,
        duration: geminiDuration,
        cost: estimatedCost,
        success: true,
        temperature: queryGenerationConfig.temperature,
        maxTokens: queryGenerationConfig.maxOutputTokens,
        messageId,
      });
    }

    // Parse JSON response
    let parsedResponse;
    try {
      // Clean up response text - remove markdown code blocks if present
      const cleanText = text.replace(/```json\n?|\n?```/g, '').trim();
      parsedResponse = JSON.parse(cleanText);
    } catch {
      console.error('Failed to parse query generation response:', text);
      throw new Error('Failed to parse query generation response');
    }

    // Normalize party filters
    const normalizedQueries: GeneratedQuery[] = parsedResponse.queries.map((q: { query: string; partyFilter?: string; reasoning?: string }) => ({
      query: q.query,
      partyFilter: q.partyFilter ? normalizePartyFilter(q.partyFilter) : undefined,
      reasoning: q.reasoning,
    }));

    // Ensure we have the original query as a fallback
    if (!normalizedQueries.some(q => q.query === userQuery)) {
      normalizedQueries.push({
        query: userQuery,
        partyFilter: undefined,
        reasoning: 'Original user query as fallback',
      });
    }

      return {
        queries: normalizedQueries,
        originalQuery: userQuery,
        totalTokensUsed: estimatedTotalTokens,
        cost: estimatedCost,
      };

    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Unknown error');
      
      // Check if this is a retryable error
      const isRetryable = lastError.message.includes('overloaded') || 
                         lastError.message.includes('503') ||
                         lastError.message.includes('429') ||
                         lastError.message.includes('timeout');
      
      if (isRetryable && attempt < MAX_RETRIES) {
        const delayMs = RETRY_DELAY_MS * Math.pow(2, attempt); // Exponential backoff
        await delay(delayMs);
        continue;
      }
      
      // Track failed call
      if (distinctId) {
        await trackLLMCall(distinctId, QUERY_LLM_CONFIG.provider, QUERY_MODEL_NAME, 'query_generation', {
          duration: Date.now() - overallStartTime,
          success: false,
          errorMessage: lastError.message,
          messageId,
        });
      }

      console.error('Error generating search queries:', lastError);
      
      // Return fallback with original query
      return {
        queries: [{ query: userQuery, reasoning: 'Fallback to original query due to generation error' }],
        originalQuery: userQuery,
        totalTokensUsed: 0,
        cost: 0,
      };
    }
  }
  
  // This should never be reached, but provide fallback
  return {
    queries: [{ query: userQuery, reasoning: 'Fallback to original query' }],
    originalQuery: userQuery,
    totalTokensUsed: 0,
    cost: 0,
  }
};

const normalizePartyFilter = (partyInput: string): string | undefined => {
  const normalized = partyInput.toLowerCase().trim();
  return PARTY_ABBREVIATIONS[normalized] || partyInput.toUpperCase();
};
