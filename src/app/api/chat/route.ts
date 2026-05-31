import { NextRequest, NextResponse } from "next/server";
import { ChatTrace, Message } from "@/types";
import { getGeminiChatResponse, getGeminiChatResponseStream, AgentApproach } from "@/lib/gemini-service";
import { withAnalytics, getUserId } from "@/lib/middleware/analytics";
import { v7 as uuidv7 } from 'uuid';

const AGENT_APPROACH = process.env.AGENT_APPROACH || 'multi-step';

async function chatHandler(req: NextRequest) {
  const userId = getUserId(req);
  
  try {
    const body = await req.json();
    const userMessage: Message = body.message;
    const agentConfig = body.agentConfig || undefined;
    const shouldStream = body.stream === true;

    if (!userMessage || typeof userMessage.text !== 'string') {
      return NextResponse.json({ error: "Invalid message format" }, { status: 400 });
    }

    // Determine agent approach based on configuration
    const agentApproach: AgentApproach = determineAgentApproach(userMessage, agentConfig);

    if (shouldStream) {
      return createChatStreamResponse(userMessage, userId, agentApproach);
    }
    
    // Use consolidated gemini service with agent approach
    const aiTextResponse = await getGeminiChatResponse(userMessage, userId, agentApproach);

    const aiResponse: Message = {
      id: uuidv7(),
      text: aiTextResponse,
      role: "ai",
      timestamp: new Date(),
    };

    return NextResponse.json({ message: aiResponse }, { status: 200 });
  } catch (error) {
    console.error("Error processing chat request in API route:", error);
    
    // Check if the error is an instance of Error to safely access message property
    const errorMessage = error instanceof Error ? error.message : "Failed to process chat request due to an internal error.";
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}

function createChatStreamResponse(
  userMessage: Message,
  userId: string,
  agentApproach: AgentApproach
): NextResponse {
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const send = (event: object) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`));
      };
      let latestTrace: ChatTrace | undefined;

      void (async () => {
        try {
          const aiTextResponse = await getGeminiChatResponseStream(
            userMessage,
            userId,
            agentApproach,
            {
              onTraceUpdate: (trace) => {
                latestTrace = trace;
                send({ type: 'trace', trace });
              },
              onAnswerDelta: (text) => send({ type: 'answer_delta', text }),
            }
          );

          const aiResponse: Message = {
            id: uuidv7(),
            text: aiTextResponse,
            role: "ai",
            timestamp: new Date(),
            trace: latestTrace,
          };

          send({ type: 'complete', message: aiResponse });
        } catch (error) {
          const errorMessage = error instanceof Error ? error.message : "Failed to stream chat response.";
          send({ type: 'error', error: errorMessage });
        } finally {
          controller.close();
        }
      })();
    },
  });

  return new NextResponse(stream, {
    status: 200,
    headers: {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}

// Configuration options for different agent approaches
const AGENT_CONFIG_OPTIONS = {
  // Enable multi-step agent by default for all requests
  DEFAULT_MULTI_STEP: {
    type: 'multi-step' as const,
    config: {
      enableQueryGeneration: true,
      maxQueries: 5,
      enablePartyFiltering: true,
      deduplicateResults: true,
      maxSegmentsPerQuery: 25,
    },
  },
  
  // Conservative multi-step with fewer queries
  CONSERVATIVE_MULTI_STEP: {
    type: 'multi-step' as const,
    config: {
      enableQueryGeneration: true,
      maxQueries: 3,
      enablePartyFiltering: true,
      deduplicateResults: true,
      maxSegmentsPerQuery: 20,
    },
  },
  
  // Aggressive multi-step with more queries
  AGGRESSIVE_MULTI_STEP: {
    type: 'multi-step' as const,
    config: {
      enableQueryGeneration: true,
      maxQueries: 8,
      enablePartyFiltering: true,
      deduplicateResults: true,
      maxSegmentsPerQuery: 30,
    },
  },
  
  // Original single-step approach
  SINGLE_STEP: {
    type: 'single' as const,
  },
} as const;

function determineAgentApproach(userMessage: Message, explicitConfig?: { approach?: string }): AgentApproach {
  // Check for explicit configuration
  if (explicitConfig?.approach) {
    switch (explicitConfig.approach) {
      case 'single':
        return AGENT_CONFIG_OPTIONS.SINGLE_STEP;
      case 'conservative':
        return AGENT_CONFIG_OPTIONS.CONSERVATIVE_MULTI_STEP;
      case 'aggressive':
        return AGENT_CONFIG_OPTIONS.AGGRESSIVE_MULTI_STEP;
      default:
        return AGENT_CONFIG_OPTIONS.DEFAULT_MULTI_STEP;
    }
  }

  // Environment variable override
  const envApproach = process.env.CHAT_AGENT_APPROACH || AGENT_APPROACH;
  if (envApproach) {
    switch (envApproach.toLowerCase()) {
      case 'single':
        return AGENT_CONFIG_OPTIONS.SINGLE_STEP;
      case 'conservative':
        return AGENT_CONFIG_OPTIONS.CONSERVATIVE_MULTI_STEP;
      case 'aggressive':
        return AGENT_CONFIG_OPTIONS.AGGRESSIVE_MULTI_STEP;
      default:
        return AGENT_CONFIG_OPTIONS.DEFAULT_MULTI_STEP;
    }
  }

  // Heuristic-based approach selection
  const messageText = userMessage.text.toLowerCase();
  
  // Use single-step for simple queries
  if (messageText.length < 20 || 
      /^(vad|hur|när|var|varför|vilka?)\s/.test(messageText)) {
    return AGENT_CONFIG_OPTIONS.SINGLE_STEP;
  }
  
  // Use aggressive multi-step for comparative queries
  if (messageText.includes('jämför') || 
      messageText.includes('skillnad') || 
      messageText.includes('vs') ||
      messageText.includes('och') && (messageText.includes('parti') || messageText.includes('politik'))) {
    return AGENT_CONFIG_OPTIONS.AGGRESSIVE_MULTI_STEP;
  }
  
  // Default to standard multi-step
  return AGENT_CONFIG_OPTIONS.DEFAULT_MULTI_STEP;
}

export const POST = withAnalytics(chatHandler);
