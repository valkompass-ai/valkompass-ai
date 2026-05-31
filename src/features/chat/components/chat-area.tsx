"use client";

import ChatInput from "./chat-input";
import MessageBubble from "./message-bubble";
import MessageBubbleLoading from "./message-bubble-loading";
import { useChat } from "../hooks/use-chat"; // Updated import path
import { ChatHistoryDebug } from "@/components/chat-history-debug";
import Image from "next/image";
import { useEffect, useRef } from "react";

export default function ChatArea() {
  const { messages, sendMessage, clearMessages, isLoading, error, streamingState } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden">
      {/* Chat Messages Area */}
      <div 
        ref={chatContainerRef}
        className="bg-white/40 rounded-t-lg flex-1 flex flex-col min-h-0 overflow-hidden"
      >
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 overscroll-contain">
          {messages.length === 0 && !isLoading && !error ? (
            <div className="h-full flex flex-col items-center justify-center space-y-4 text-gray-600">
              <Image 
                src={"/valkompass_transparent_no_text.avif"} 
                alt="Valkompass" 
                width={150} 
                height={150}
                className="object-contain max-w-[150px] max-h-[150px] sm:max-w-[200px] sm:max-h-[200px]" 
              />
              <p className="text-base sm:text-lg font-medium text-gray-500 text-center px-4">
                Skriv din fråga till valkompassen
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg.text} role={msg.role} trace={msg.trace} />
              ))}
              {isLoading && <MessageBubbleLoading stream={streamingState} />}
              {error && (
                <MessageBubble key="error" message={`Error: ${error}`} role="ai" />
              )}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
        
        {/* Clear Chat Button */}
        {messages.length > 0 && (
          <div className="px-4 sm:px-6 pb-2">
            <div className="flex justify-end">
              <button
                onClick={clearMessages}
                className="bg-transparent hover:underline text-sm text-gray-500 cursor-pointer touch-manipulation"
              >
                Rensa chatten
              </button>
            </div>
            <ChatHistoryDebug messages={messages} />
          </div>
        )}
      </div>
      
      {/* Chat Input - Fixed at bottom */}
      <ChatInput onSendMessage={sendMessage} />
    </div>
  );
}
