import { getOpenAIEmbedding } from "./openai-service";
import { getContextFromKB, RetrievedContext, RetrievedSegment } from "./knowledge-base-service";
import { generateSearchQueries, GeneratedQuery, QueryGenerationResult } from "./query-generation-service";
import { Message } from "@/types";

export interface MultiStepAgentConfig {
  enableQueryGeneration: boolean;
  maxQueries: number;
  enablePartyFiltering: boolean;
  deduplicateResults: boolean;
  maxSegmentsPerQuery: number;
}

export interface MultiStepRetrievalResult {
  aggregatedContext: RetrievedContext;
  queryGenerationResult?: QueryGenerationResult;
  individualResults: Array<{
    query: GeneratedQuery;
    context: RetrievedContext | null;
    error?: string;
  }>;
  metrics: {
    totalQueries: number;
    successfulQueries: number;
    totalSegments: number;
    uniqueSegments: number;
    totalDuration: number;
    queryGenerationDuration?: number;
    retrievalDuration: number;
  };
}

const DEFAULT_CONFIG: MultiStepAgentConfig = {
  enableQueryGeneration: true,
  maxQueries: 5,
  enablePartyFiltering: true,
  deduplicateResults: true,
  maxSegmentsPerQuery: 25,
};

export const getMultiStepContext = async (
  message: Message,
  distinctId?: string,
  config: Partial<MultiStepAgentConfig> = {}
): Promise<MultiStepRetrievalResult> => {
  const overallStartTime = Date.now();
  const finalConfig = { ...DEFAULT_CONFIG, ...config };
  
  let queryGenerationResult: QueryGenerationResult | undefined;
  let queries: GeneratedQuery[] = [];
  let queryGenerationDuration = 0;
  
  try {
    if (finalConfig.enableQueryGeneration) {
      
      // Step 1: Generate multiple search queries
      const queryGenStartTime = Date.now();
      queryGenerationResult = await generateSearchQueries(message.text, message.id, distinctId);
      queryGenerationDuration = Date.now() - queryGenStartTime;
      
      // Limit the number of queries
      queries = queryGenerationResult.queries.slice(0, finalConfig.maxQueries);
    } else {
      // Fallback to original query
      queries = [{
        query: message.text,
        reasoning: 'Original query - query generation disabled',
      }];
    }

    // Step 2: Execute all queries in parallel
    const retrievalStartTime = Date.now();
    const retrievalPromises = queries.map(async (generatedQuery) => {
      try {
        // Get embedding for the query
        const queryEmbedding = await getOpenAIEmbedding(generatedQuery.query, message.id, distinctId);
        
        // Get context with optional party filtering
        const partyFilter = finalConfig.enablePartyFiltering ? generatedQuery.partyFilter : undefined;
        const context = await getContextFromKB(queryEmbedding, message.id, distinctId, partyFilter);
        
        return {
          query: generatedQuery,
          context,
          error: undefined,
        };
      } catch (error) {
        return {
          query: generatedQuery,
          context: null,
          error: error instanceof Error ? error.message : 'Unknown error',
        };
      }
    });


    const individualResults = await Promise.all(retrievalPromises);
    const retrievalDuration = Date.now() - retrievalStartTime;

    // Step 3: Aggregate and deduplicate results
    const aggregatedContext = aggregateContexts(individualResults, finalConfig);
    
    // Step 4: Calculate metrics
    const successfulQueries = individualResults.filter(r => r.context !== null).length;
    const totalSegments = individualResults.reduce((sum, r) => sum + (r.context?.segments.length || 0), 0);
    const uniqueSegments = aggregatedContext.segments.length;
    const totalDuration = Date.now() - overallStartTime;


    return {
      aggregatedContext,
      queryGenerationResult,
      individualResults,
      metrics: {
        totalQueries: queries.length,
        successfulQueries,
        totalSegments,
        uniqueSegments,
        totalDuration,
        queryGenerationDuration: queryGenerationDuration > 0 ? queryGenerationDuration : undefined,
        retrievalDuration,
      },
    };

  } catch (error) {
    console.error('Error in multi-step agent:', error);
    
    // Fallback to basic single query
    const fallbackEmbedding = await getOpenAIEmbedding(message.text, message.id, distinctId);
    const fallbackContext = await getContextFromKB(fallbackEmbedding, message.id, distinctId);
    
    return {
      aggregatedContext: fallbackContext || {
        topicName: '',
        topicDescription: '',
        segments: [],
        retrievalDuration: 0,
        totalSegmentsFound: 0,
        avgSimilarityScore: 0,
        documentsReferenced: [],
      },
      queryGenerationResult,
      individualResults: [],
      metrics: {
        totalQueries: 1,
        successfulQueries: fallbackContext ? 1 : 0,
        totalSegments: fallbackContext?.segments.length || 0,
        uniqueSegments: fallbackContext?.segments.length || 0,
        totalDuration: Date.now() - overallStartTime,
        queryGenerationDuration: queryGenerationDuration > 0 ? queryGenerationDuration : undefined,
        retrievalDuration: Date.now() - overallStartTime,
      },
    };
  }
};

const aggregateContexts = (
  individualResults: Array<{
    query: GeneratedQuery;
    context: RetrievedContext | null;
    error?: string;
  }>,
  config: MultiStepAgentConfig
): RetrievedContext => {
  const validContexts = individualResults
    .filter(r => r.context !== null)
    .map(r => r.context!);

  if (validContexts.length === 0) {
    return {
      topicName: '',
      topicDescription: '',
      segments: [],
      retrievalDuration: 0,
      totalSegmentsFound: 0,
      avgSimilarityScore: 0,
      documentsReferenced: [],
    };
  }

  // Use the topic from the first successful result
  const primaryContext = validContexts[0];
  
  // Aggregate all segments
  let allSegments: RetrievedSegment[] = [];
  validContexts.forEach(context => {
    allSegments.push(...context.segments);
  });

  // Sort by similarity score
  allSegments.sort((a, b) => b.similarityScore - a.similarityScore);

  // Deduplicate if enabled
  if (config.deduplicateResults) {
    allSegments = deduplicateSegments(allSegments);
  }

  // Calculate aggregate metrics
  const totalSegmentsFound = allSegments.length;
  const avgSimilarityScore = allSegments.length > 0 
    ? allSegments.reduce((sum, seg) => sum + seg.similarityScore, 0) / allSegments.length 
    : 0;

  // Extract unique documents
  const documentsMap = new Map<string, { path: string; type?: string; publicUrl?: string }>();
  allSegments.forEach(segment => {
    if (!documentsMap.has(segment.documentPath)) {
      documentsMap.set(segment.documentPath, {
        path: segment.documentPath,
        type: segment.documentSourceType,
        publicUrl: segment.publicUrl,
      });
    }
  });
  const documentsReferenced = Array.from(documentsMap.values());

  return {
    topicName: primaryContext.topicName,
    topicDescription: primaryContext.topicDescription,
    segments: allSegments,
    retrievalDuration: Math.max(...validContexts.map(c => c.retrievalDuration || 0)),
    totalSegmentsFound,
    avgSimilarityScore,
    documentsReferenced,
  };
};

const deduplicateSegments = (segments: RetrievedSegment[]): RetrievedSegment[] => {
  const seen = new Set<string>();
  return segments.filter(segment => {
    // Create a unique key based on document path and segment text
    const key = `${segment.documentPath}:${segment.segmentText.substring(0, 100)}`;
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
};