"use client";

import { useChat } from '@ai-sdk/react';
import { useEffect, useRef, useState } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { ScrollArea } from "./ui/scroll-area";
import { Avatar, AvatarFallback } from "./ui/avatar";
import { Send, User, Bot } from "lucide-react";
import { CentrifugoChatTransport } from "@/lib/centrifugo-transport";

export function Chat() {
  const [input, setInput] = useState('');

  const transport = new CentrifugoChatTransport({
    centrifugoUrl: process.env.NEXT_PUBLIC_CENTRIFUGO_WS_URL || "ws://localhost:8000/connection/websocket",
    backendUrl: process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8787',
    getToken: async () => {
      const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8787'}/api/centrifugo-token`);
      if (!response.ok) {
        throw new Error('Failed to get token');
      }
      const result = await response.json();
      return result.token;
    },
  });

  const {
    messages,
    sendMessage,
    status,
    error,
  } = useChat({
    transport,
  });

  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    document.documentElement.classList.add('dark');
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || status !== 'ready') return;

    sendMessage({ text: input });
    setInput('');
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto bg-background">
      <div className="border-b bg-card px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">AI Chat Assistant</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Powered by Claude with real-time streaming
            </p>
          </div>
          <div className="flex items-center gap-2">
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 px-4 sm:px-6 py-4" ref={scrollAreaRef}>
        <div className="space-y-4 sm:space-y-6 max-w-4xl mx-auto">
          {messages.length === 0 && (
            <div className="text-center py-12">
              <Bot className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
              <h2 className="text-xl font-medium text-foreground mb-2">
                Welcome to AI Chat
              </h2>
              <p className="text-muted-foreground px-4">
                Start a conversation by typing a message below.
              </p>
            </div>
          )}

              {messages.map((message) => {
                const messageText = message.parts.map((part: any) =>
                  part.type === 'text' ? part.text : ''
                ).join('');
                
                return (
                  <div
                    key={message.id}
                    className={`flex gap-3 sm:gap-4 ${
                      message.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {message.role === "assistant" && (
                      <Avatar className="h-8 w-8 mt-1 flex-shrink-0">
                        <AvatarFallback className="bg-primary text-primary-foreground">
                          <Bot className="h-4 w-4" />
                        </AvatarFallback>
                      </Avatar>
                    )}

                    <div
                      className={`max-w-[85%] sm:max-w-[70%] rounded-lg px-3 sm:px-4 py-3 break-words ${
                        message.role === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-foreground"
                      }`}
                    >
                      <div className="text-sm leading-relaxed whitespace-pre-wrap">
                        {messageText || (message.role === "assistant" && status === 'streaming' ? (
                          <div className="flex items-center gap-2">
                            <div className="flex gap-1">
                              <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                              <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                              <div className="w-2 h-2 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                            </div>
                            <span className="text-sm">Thinking...</span>
                          </div>
                        ) : messageText)}
                      </div>
                    </div>

                    {message.role === "user" && (
                      <Avatar className="h-8 w-8 mt-1 flex-shrink-0">
                        <AvatarFallback className="bg-secondary text-secondary-foreground">
                          <User className="h-4 w-4" />
                        </AvatarFallback>
                      </Avatar>
                    )}
                  </div>
                );
              })}


          {error && (
            <div className="flex gap-4 justify-start">
              <Avatar className="h-8 w-8 mt-1">
                <AvatarFallback className="bg-destructive text-destructive-foreground">
                  <Bot className="h-4 w-4" />
                </AvatarFallback>
              </Avatar>
              <div className="bg-destructive/10 text-destructive rounded-lg px-4 py-3 border border-destructive/20">
                <p className="text-sm">
                  Sorry, I encountered an error. Please try again.
                </p>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      <div className="border-t bg-card px-4 sm:px-6 py-4">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 min-h-[44px]"
              disabled={status !== 'ready'}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
            <Button
              type="submit"
              disabled={status !== 'ready' || !input.trim()}
              size="icon"
              className="h-[44px] w-[44px] flex-shrink-0"
            >
              <Send className="h-4 w-4" />
            </Button>
          </form>
          <p className="text-xs text-muted-foreground mt-2 text-center">
            Press Enter to send • Shift+Enter for new line • AI responses are streamed in real-time
          </p>
        </div>
      </div>
    </div>
  );
}
