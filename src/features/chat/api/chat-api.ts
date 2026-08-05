import { ChatTrace, Message } from "@/types";

export interface ChatStreamHandlers {
  onTrace?: (trace: ChatTrace) => void;
  onAnswerDelta?: (text: string) => void;
}

type ChatStreamEvent =
  | { type: 'trace'; trace: ChatTrace }
  | { type: 'answer_delta'; text: string }
  | { type: 'complete'; message: Message }
  | { type: 'error'; error: string };

export const sendMessageToApi = async (
  userMessage: Message,
  conversationId?: string
): Promise<Message> => {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message: userMessage, conversationId }),
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  const data = await response.json();
  const message = data.message as Message;
  
  // Ensure timestamp is converted back to Date object from JSON string
  message.timestamp = new Date(message.timestamp);
  
  return message;
};

export const streamMessageFromApi = async (
  userMessage: Message,
  handlers: ChatStreamHandlers = {},
  conversationId?: string
): Promise<Message> => {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message: userMessage, conversationId, stream: true }),
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  if (!response.body) {
    return sendMessageToApi(userMessage, conversationId);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completedMessage: Message | null = null;

  const handleEvent = (event: ChatStreamEvent) => {
    switch (event.type) {
      case 'trace':
        handlers.onTrace?.(event.trace);
        break;
      case 'answer_delta':
        handlers.onAnswerDelta?.(event.text);
        break;
      case 'complete':
        completedMessage = event.message;
        completedMessage.timestamp = new Date(completedMessage.timestamp);
        break;
      case 'error':
        throw new Error(event.error);
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const dataLine = frame
        .split("\n")
        .find((line) => line.startsWith("data: "));

      if (!dataLine) {
        continue;
      }

      handleEvent(JSON.parse(dataLine.slice(6)) as ChatStreamEvent);
    }

    if (done) {
      break;
    }
  }

  if (!completedMessage) {
    throw new Error("Stream ended before the response completed.");
  }

  return completedMessage;
};
