import neo4j, { Driver, Session } from 'neo4j-driver';
import { trackKnowledgeBaseQuery } from './posthog';

const NEO4J_URI = process.env.NEO4J_URI;
const NEO4J_USERNAME = process.env.NEO4J_USERNAME;
const NEO4J_PASSWORD = process.env.NEO4J_PASSWORD;

if (!NEO4J_URI || !NEO4J_USERNAME || !NEO4J_PASSWORD) {
  throw new Error('Neo4j connection details are not fully set in environment variables.');
}

let driver: Driver;

const getDriver = (): Driver => {
  if (!driver) {
    try {
      driver = neo4j.driver(NEO4J_URI, neo4j.auth.basic(NEO4J_USERNAME, NEO4J_PASSWORD));
      // You might want to verify connectivity here, e.g., by driver.verifyConnectivity()
      // However, verifyConnectivity also checks license for Aura, which might not be desired for local dev.
      // A simple session run can also work if needed.
      console.log("Neo4j Driver initialized.");
    } catch (error) {
      console.error("Failed to create Neo4j driver:", error);
      throw new Error("Could not establish connection with Neo4j database.");
    }
  }
  return driver;
};

export interface RetrievedSegment {
  documentPath: string;
  segmentText: string;
  segmentPage: number;
  similarityScore: number;
  publicUrl?: string;
  documentSourceType?: string;
}

export interface RetrievedContext {
  topicName: string;
  topicDescription: string;
  segments: RetrievedSegment[];
  // Analytics data
  retrievalDuration?: number;
  totalSegmentsFound?: number;
  avgSimilarityScore?: number;
  documentsReferenced?: Array<{
    path: string;
    type?: string;
    publicUrl?: string;
  }>;
}

export const  getContextFromKB = async (queryEmbedding: number[], messageId: string, distinctId?: string): Promise<RetrievedContext | null> => {
  const session: Session = getDriver().session();
  const overallStartTime = Date.now();
  
  try {
    // 1. Find the most similar topic
    const topicResult = await session.run(
      `CALL db.index.vector.queryNodes('topic_embedding_idx', 1, $queryEmbedding) 
       YIELD node AS topic, score
       RETURN topic.name AS name, topic.description AS description, score
       ORDER BY score DESC LIMIT 1`,
      { queryEmbedding }
    );

    if (topicResult.records.length === 0) {
      const duration = Date.now() - overallStartTime;
      
      // Track failed topic search
      if (distinctId) {
        await trackKnowledgeBaseQuery(distinctId, {
          queryType: 'topic_search',
          success: false,
          duration,
          resultsFound: 0,
          messageId,
        });
      }
      
      console.warn("No matching topic found in knowledge base.");
      return null;
    }

    const topTopic = topicResult.records[0];
    const topicName = topTopic.get('name');
    const topicDescription = topTopic.get('description');

    // 2. Find the top 25 similar segments related to this topic and their documents
    const segmentsResult = await session.run(
      `CALL db.index.vector.queryNodes('segment_embedding_idx', 25, $queryEmbedding) 
       YIELD node AS segment, score
       MATCH (doc:Document)-[:CONTAINS]->(segment)
       // Optional: If you want to ensure segments are related to the found topic, uncomment and adjust:
       // MATCH (segment)-[:MENTIONS]->(t:Topic {name: $topicName})
       RETURN doc.path AS documentPath, segment.type AS segmentType, segment.text AS segmentText, segment.page AS segmentPage, segment.public_url AS publicUrl, score AS similarityScore
       ORDER BY similarityScore DESC`, 
      { queryEmbedding, topicName } // topicName is used if the optional MATCH above is enabled
    );

    const segments: RetrievedSegment[] = segmentsResult.records.map(record => {
      const rawPublicUrl = record.get('publicUrl');
      const documentSourceType = record.get('segmentType');
      let finalPublicUrl = rawPublicUrl || undefined;
      const pageNumber = documentSourceType === 'pdf' ? record.get('segmentPage')?.toNumber() : undefined;

      if (documentSourceType === 'pdf' && rawPublicUrl && process.env.APP_DOMAIN) {
        finalPublicUrl = `${process.env.APP_DOMAIN}${rawPublicUrl}`;
      } else if (documentSourceType === 'pdf' && rawPublicUrl) {
        console.warn("APP_DOMAIN environment variable is not set. PDF publicUrl will be relative.");
      }

      return {
        documentPath: record.get('documentPath'),
        documentSourceType: documentSourceType || undefined,
        segmentText: record.get('segmentText'),
        segmentPage: pageNumber, // Ensure page is a number
        similarityScore: record.get('similarityScore'),
        publicUrl: finalPublicUrl,
      };
    }); 

    // Calculate analytics data
    const retrievalDuration = Date.now() - overallStartTime;
    const totalSegmentsFound = segments.length;
    const avgSimilarityScore = segments.length > 0 
      ? segments.reduce((sum, seg) => sum + seg.similarityScore, 0) / segments.length 
      : 0;
    
    // Extract unique documents referenced
    const documentsMap = new Map<string, { path: string; type?: string; publicUrl?: string }>();
    segments.forEach(segment => {
      if (!documentsMap.has(segment.documentPath)) {
        documentsMap.set(segment.documentPath, {
          path: segment.documentPath,
          type: segment.documentSourceType,
          publicUrl: segment.publicUrl,
        });
      }
    });
    const documentsReferenced = Array.from(documentsMap.values());

    // Track successful retrieval
    if (distinctId) {
      await trackKnowledgeBaseQuery(distinctId, {
        queryType: 'semantic_search',
        success: true,
        duration: retrievalDuration,
        resultsFound: totalSegmentsFound,
        topSimilarityScore: segments.length > 0 ? segments[0].similarityScore : undefined,
        messageId,
      });
    }

    return {
      topicName,
      topicDescription,
      segments,
      retrievalDuration,
      totalSegmentsFound,
      avgSimilarityScore,
      documentsReferenced,
    };

  } catch (error) {
    const duration = Date.now() - overallStartTime;
    
    // Track failed retrieval
    if (distinctId) {
      await trackKnowledgeBaseQuery(distinctId, {
        queryType: 'semantic_search',
        success: false,
        duration,
        resultsFound: 0,
        errorMessage: error instanceof Error ? error.message : 'Unknown error',
        messageId,
      });
    }

    console.error("Error querying Neo4j knowledge base:", error);
    throw new Error("Failed to retrieve context from knowledge base.");
  } finally {
    await session.close();
  }
};

// Optional: Function to close the driver when the application shuts down
export const closeNeo4jDriver = async () => {
  if (driver) {
    await driver.close();
    console.log("Neo4j Driver closed.");
  }
}; 