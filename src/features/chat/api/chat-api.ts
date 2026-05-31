import { Message } from "@/types";

export interface ChatStreamHandlers {
  onReasoningDelta?: (text: string) => void;
  onReasoningComplete?: () => void;
  onAnswerDelta?: (text: string) => void;
}

type ChatStreamEvent =
  | { type: 'reasoning_start' }
  | { type: 'reasoning_delta'; text: string }
  | { type: 'reasoning_complete' }
  | { type: 'answer_delta'; text: string }
  | { type: 'complete'; message: Message }
  | { type: 'error'; error: string };

export const sendMessageToApi = async (userMessage: Message): Promise<Message> => {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ message: userMessage }),
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
  handlers: ChatStreamHandlers = {}
): Promise<Message> => {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ message: userMessage, stream: true }),
  });

  if (!response.ok) {
    throw new Error(`API request failed with status ${response.status}`);
  }

  if (!response.body) {
    return sendMessageToApi(userMessage);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completedMessage: Message | null = null;

  const handleEvent = (event: ChatStreamEvent) => {
    switch (event.type) {
      case 'reasoning_delta':
        handlers.onReasoningDelta?.(event.text);
        break;
      case 'reasoning_complete':
        handlers.onReasoningComplete?.();
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
      case 'reasoning_start':
        break;
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
