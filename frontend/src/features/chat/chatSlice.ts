/**
 * Redux slice for chat feature
 * 
 * This slice manages the state for the Qwen2 chatbot.
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  performance?: {
    time_to_first_token?: number;
    tokens_per_second?: number;
    total_time?: number;
    total_tokens?: number;
  };
}

export interface ChatState {
  messages: ChatMessage[];
  isOpen: boolean;
  isTyping: boolean;
  currentResponse: string;
  error: string | null;
  currentPerformance: {
    time_to_first_token?: number;
    tokens_per_second?: number;
    total_time?: number;
    total_tokens?: number;
  } | null;
}

const initialState: ChatState = {
  messages: [
    {
      role: 'assistant',
      content: 'Hello! I\'m Qwen2.5, your AI assistant. How can I help you today?',
      timestamp: Date.now(),
    }
  ],
  isOpen: false,
  isTyping: false,
  currentResponse: '',
  error: null,
  currentPerformance: null,
};

const chatSlice = createSlice({
  name: 'chat',
  initialState,
  reducers: {
    toggleChat: (state) => {
      state.isOpen = !state.isOpen;
    },
    openChat: (state) => {
      state.isOpen = true;
    },
    closeChat: (state) => {
      state.isOpen = false;
    },
    addMessage: (state, action: PayloadAction<ChatMessage>) => {
      state.messages.push(action.payload);
    },
    startTyping: (state) => {
      state.isTyping = true;
      state.currentResponse = '';
      state.error = null;
      state.currentPerformance = {};
    },
    appendToken: (state, action: PayloadAction<string>) => {
      state.currentResponse += action.payload;
    },
    updatePerformanceMetric: (state, action: PayloadAction<{ metric: string; value: number }>) => {
      if (!state.currentPerformance) {
        state.currentPerformance = {};
      }
      (state.currentPerformance as Record<string, number>)[action.payload.metric] = action.payload.value;
    },
    completeResponse: (state, action: PayloadAction<{ performance?: Record<string, number> }>) => {
      if (state.currentResponse) {
        state.messages.push({
          role: 'assistant',
          content: state.currentResponse,
          timestamp: Date.now(),
          performance: action.payload.performance || state.currentPerformance || undefined,
        });
      }
      state.isTyping = false;
      state.currentResponse = '';
      state.currentPerformance = null;
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isTyping = false;
      state.currentResponse = '';
    },
    clearError: (state) => {
      state.error = null;
    },
    clearChat: (state) => {
      state.messages = [
        {
          role: 'assistant',
          content: 'Hello! I\'m Qwen2.5, your AI assistant. How can I help you today?',
          timestamp: Date.now(),
        }
      ];
      state.currentResponse = '';
      state.error = null;
      state.currentPerformance = null;
    },
  },
});

export const {
  toggleChat,
  openChat,
  closeChat,
  addMessage,
  startTyping,
  appendToken,
  updatePerformanceMetric,
  completeResponse,
  setError,
  clearError,
  clearChat,
} = chatSlice.actions;

export default chatSlice.reducer;
