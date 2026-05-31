import { useState } from 'react';
import { ChatTrace, Message } from '@/types';
import { streamMessageFromApi } from '../api/chat-api';
import { v7 as uuidv7 } from 'uuid';

/**
 * Formats chat history into a string representation
 * @param messages Array of messages to format
 * @param maxLength Maximum length of the formatted history (default: 5000)
 * @returns Formatted history string truncated to maxLength
 */
const formatChatHistory = (messages: Message[], maxLength: number = 5000): string => {
  if (messages.length === 0) {
    return '';
  }

  // Format each message as "Role: Message text"
  const formattedMessages = messages.map(msg => {
    const roleLabel = msg.role === 'user' ? 'User' : 'AI';
    // Ensure timestamp is a Date object (it might be a string from JSON)
    const timestamp = msg.timestamp instanceof Date 
      ? msg.timestamp.toLocaleTimeString() 
      : new Date(msg.timestamp).toLocaleTimeString();
    return `[${timestamp}] ${roleLabel}: ${msg.text}`;
  });

  // Join all messages with newlines
  const fullHistory = formattedMessages.join('\n\n');

  // Truncate to maxLength if necessary
  if (fullHistory.length <= maxLength) {
    return fullHistory;
  }

  // Truncate and add indicator
  const truncated = fullHistory.substring(fullHistory.length - maxLength + 20); // Leave room for truncation indicator
  const truncationIndicator = '...[truncated]...\n\n';
  
  // Find the first complete message boundary after truncation
  const firstNewlineIndex = truncated.indexOf('\n\n');
  if (firstNewlineIndex !== -1) {
    return truncationIndicator + truncated.substring(firstNewlineIndex + 2);
  }
  
  return truncationIndicator + truncated;
};

export interface StreamingChatState {
  trace: ChatTrace | null;
  answer: string;
}

export const useChat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamingState, setStreamingState] = useState<StreamingChatState | null>(null);

  const sendMessage = async (messageText: string) => {
    // Format current chat history for this message
    const chatHistory = formatChatHistory(messages);

    const newUserMessage: Message = {
      id: uuidv7(),
      text: messageText,
      role: 'user' as const,
      timestamp: new Date(),
      history: chatHistory, // Include the formatted chat history
    };
    
    setMessages((prevMessages) => [...prevMessages, newUserMessage]);
    setIsLoading(true);
    setError(null);
    setStreamingState({
      trace: null,
      answer: '',
    });

    try {
      const aiMessage = await streamMessageFromApi(newUserMessage, {
        onTrace: (trace) => {
          setStreamingState((current) => ({
            trace,
            answer: current?.answer ?? '',
          }));
        },
        onAnswerDelta: (text) => {
          setStreamingState((current) => ({
            trace: current?.trace ?? null,
            answer: (current?.answer ?? '') + text,
          }));
        },
      });
      setMessages((prevMessages) => [...prevMessages, aiMessage]);
    } catch (e) {
      const err = e as Error;
      setError(err.message || 'Failed to get response from AI.');
      // Optionally add an error message to the chat
      const errorMessage: Message = {
        id: uuidv7(),
        text: "Sorry, I couldn't get a response. Please try again.",
        role: 'ai' as const,
        timestamp: new Date(),
      };
      setMessages((prevMessages) => [...prevMessages, errorMessage]);
    } finally {
      setIsLoading(false);
      setStreamingState(null);
    }
  };

  const clearMessages = () => {
    setMessages([]);
    setError(null);
    setStreamingState(null);
  };

  return {
    messages,
    isLoading,
    error,
    streamingState,
    sendMessage,
    clearMessages,
  };
};
