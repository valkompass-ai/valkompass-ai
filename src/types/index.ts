export interface ChatTraceSource {
  documentPath: string;
  snippet: string;
  similarityScore: number;
  publicUrl?: string;
  partyAbbreviation?: string;
  page?: number;
  sourceType?: string;
}

export interface ChatTraceQuery {
  query: string;
  partyFilter?: string;
  reasoning?: string;
  returnedSegments?: number;
  error?: string;
  sources?: ChatTraceSource[];
}

export interface ChatTrace {
  mode: "single" | "multi-step";
  status: "running" | "complete" | "error";
  events: string[];
  queries: ChatTraceQuery[];
  sources: ChatTraceSource[];
  topicName?: string;
  documentCount: number;
  segmentCount: number;
}

export interface Message {
  id: string;
  text: string;
  role: "user" | "ai";
  timestamp: Date;
  history?: string;
  trace?: ChatTrace;
} 
