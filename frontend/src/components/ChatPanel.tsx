/**
 * Chat Panel Component
 * 
 * Main chat interface for interacting with Qwen2 model.
 * Displays conversation history and performance metrics.
 */

'use client'

import { useState, useRef, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { RootState, AppDispatch } from '@/lib/store';
import {
  addMessage,
  startTyping,
  appendToken,
  updatePerformanceMetric,
  completeResponse,
  setError,
  clearChat,
  closeChat,
} from '@/features/chat/chatSlice';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/components/ui/use-toast';
import {
  Send,
  Loader2,
  Trash2,
  X,
  Clock,
  Zap,
  Activity,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

export default function ChatPanel() {
  const dispatch = useDispatch<AppDispatch>();
  const { messages, isTyping, currentResponse, currentPerformance } = useSelector(
    (state: RootState) => state.chat
  );
  const { toast } = useToast();
  
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentResponse]);

  const handleSend = async () => {
    if (!input.trim() || isTyping) return;

    const userMessage = input.trim();
    setInput('');

    // Add user message
    dispatch(addMessage({
      role: 'user',
      content: userMessage,
      timestamp: Date.now(),
    }));

    dispatch(startTyping());

    // Get conversation history
    const conversationHistory = messages.map(msg => ({
      role: msg.role,
      content: msg.content,
    }));

    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: userMessage,
          conversation_history: conversationHistory,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) {
        throw new Error('No response body');
      }

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'token') {
                dispatch(appendToken(data.content));
              } else if (data.type === 'metric') {
                dispatch(updatePerformanceMetric({
                  metric: data.metric,
                  value: data.value,
                }));
              } else if (data.type === 'complete') {
                dispatch(completeResponse({ performance: data.performance }));
              } else if (data.type === 'error') {
                dispatch(setError(data.message));
                toast({
                  title: "Error",
                  description: data.message,
                  variant: "destructive",
                });
              }
            } catch (e) {
              console.error('Failed to parse SSE data:', e);
            }
          }
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send message';
      dispatch(setError(message));
      toast({
        title: "Chat Error",
        description: message,
        variant: "destructive",
      });
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClearChat = () => {
    dispatch(clearChat());
    toast({
      title: "Chat Cleared",
      description: "Conversation history has been cleared.",
    });
  };

  return (
    <Card className="fixed bottom-24 right-6 w-96 h-[600px] shadow-2xl z-40 flex flex-col">
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-lg">Qwen2.5 Chat</CardTitle>
            <Badge variant="outline" className="text-xs">32B</Badge>
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              onClick={handleClearChat}
              disabled={isTyping}
              className="h-8 w-8"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => dispatch(closeChat())}
              className="h-8 w-8"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col min-h-0 p-0">
        {/* Messages Area */}
        <ScrollArea className="flex-1 px-4" ref={scrollAreaRef}>
          <div className="space-y-4 py-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg px-4 py-2 ${
                    message.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted'
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  
                  {/* Performance Metrics for Assistant Messages */}
                  {message.role === 'assistant' && message.performance && (
                    <div className="mt-2 pt-2 border-t border-border/50 flex flex-wrap gap-2 text-xs opacity-70">
                      {message.performance.time_to_first_token && (
                        <div className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {message.performance.time_to_first_token.toFixed(2)}s
                        </div>
                      )}
                      {message.performance.tokens_per_second && (
                        <div className="flex items-center gap-1">
                          <Zap className="w-3 h-3" />
                          {message.performance.tokens_per_second.toFixed(1)} tok/s
                        </div>
                      )}
                      {message.performance.total_tokens && (
                        <div className="flex items-center gap-1">
                          <Activity className="w-3 h-3" />
                          {message.performance.total_tokens} tokens
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Current Response (Streaming) */}
            {isTyping && currentResponse && (
              <div className="flex justify-start">
                <div className="max-w-[85%] rounded-lg px-4 py-2 bg-muted">
                  <p className="text-sm whitespace-pre-wrap">{currentResponse}</p>
                  <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Typing...
                    {currentPerformance?.time_to_first_token && (
                      <span>• First token: {currentPerformance.time_to_first_token.toFixed(2)}s</span>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Typing Indicator (No Content Yet) */}
            {isTyping && !currentResponse && (
              <div className="flex justify-start">
                <div className="rounded-lg px-4 py-3 bg-muted">
                  <div className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span className="text-sm text-muted-foreground">Thinking...</span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Area */}
        <div className="p-4 border-t flex-shrink-0">
          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type your message... (Shift+Enter for new line)"
              className="min-h-[60px] max-h-[120px] resize-none"
              disabled={isTyping}
            />
            <Button
              onClick={handleSend}
              disabled={!input.trim() || isTyping}
              size="icon"
              className="h-[60px] w-[60px]"
            >
              {isTyping ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
