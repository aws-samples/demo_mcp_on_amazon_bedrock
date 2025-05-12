'use client';

import { useEffect, useRef } from 'react';
import { useStore } from '@/lib/store';
import { ChatMessage } from './ChatMessage';

interface MessageListProps {
  isLoading?: boolean;
}

export function MessageList({ isLoading = false }: MessageListProps) {
  const { messages } = useStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  
  // Filter out system messages for display
  const displayMessages = messages.filter(msg => msg.role !== 'system');
  
  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-gray-300 border-t-blue-600 mb-4"></div>
            <h3 className="text-lg font-medium">Preparing...</h3>
            <p className="text-sm text-gray-500 mt-2">
              Please wait while we connect to available MCP servers.
            </p>
          </div>
        </div>
      ) : displayMessages.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center">
            <h3 className="text-lg font-medium">Welcome to Autonomous Agent with MCP</h3>
            <p className="text-sm text-gray-500 mt-2">
              Start a conversation by typing a message below.
            </p>
          </div>
        </div>
      ) : (
        displayMessages.map((message, index) => (
          <ChatMessage
            key={index}
            message={message}
          />
        ))
      )}
      <div ref={messagesEndRef} />
    </div>
  );
}
