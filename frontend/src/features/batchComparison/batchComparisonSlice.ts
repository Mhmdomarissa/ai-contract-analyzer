/**
 * Redux slice for batch clause comparison (1 → N)
 * 
 * This slice manages the state for comparing one source clause against multiple target clauses.
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface ComparisonResult {
  index: number;
  conflict: boolean;
  explanation: string;
  severity: string;
  performance: {
    time_to_first_token: number;
    tokens_per_second: number;
    total_time: number;
    total_tokens: number;
  };
}

export interface BatchComparisonState {
  sourceClause: string;
  targetClauses: string[];
  prompt: string;
  results: ComparisonResult[];
  isComparing: boolean;
  totalClauses: number;
  completedCount: number;
  error: string | null;
}

const DEFAULT_BATCH_PROMPT = `Analyze the following two contract clauses and determine if they conflict with each other.

A conflict exists when:
- The clauses contain contradictory requirements or obligations
- They specify different or incompatible terms for the same aspect
- One clause undermines or contradicts the intent of the other
- They create legal ambiguity or uncertainty when read together

Please provide:
1. Whether a conflict exists (Yes/No)
2. If yes, explain the nature of the conflict
3. The severity of the conflict (High/Medium/Low)
4. Suggested resolution or clarification needed`;

const initialState: BatchComparisonState = {
  sourceClause: '',
  targetClauses: [],
  prompt: DEFAULT_BATCH_PROMPT,
  results: [],
  isComparing: false,
  totalClauses: 0,
  completedCount: 0,
  error: null,
};

const batchComparisonSlice = createSlice({
  name: 'batchComparison',
  initialState,
  reducers: {
    setSourceClause: (state, action: PayloadAction<string>) => {
      state.sourceClause = action.payload;
    },
    setTargetClauses: (state, action: PayloadAction<string[]>) => {
      state.targetClauses = action.payload;
    },
    addTargetClause: (state, action: PayloadAction<string>) => {
      if (state.targetClauses.length < 100) {
        state.targetClauses.push(action.payload);
      }
    },
    removeTargetClause: (state, action: PayloadAction<number>) => {
      state.targetClauses.splice(action.payload, 1);
    },
    updateTargetClause: (state, action: PayloadAction<{ index: number; value: string }>) => {
      const { index, value } = action.payload;
      if (index >= 0 && index < state.targetClauses.length) {
        state.targetClauses[index] = value;
      }
    },
    setPrompt: (state, action: PayloadAction<string>) => {
      state.prompt = action.payload;
    },
    resetPrompt: (state) => {
      state.prompt = DEFAULT_BATCH_PROMPT;
    },
    startComparison: (state, action: PayloadAction<number>) => {
      state.isComparing = true;
      state.results = [];
      state.totalClauses = action.payload;
      state.completedCount = 0;
      state.error = null;
    },
    addResult: (state, action: PayloadAction<ComparisonResult>) => {
      state.results.push(action.payload);
      state.completedCount += 1;
    },
    completeComparison: (state) => {
      state.isComparing = false;
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isComparing = false;
    },
    clearAll: (state) => {
      state.sourceClause = '';
      state.targetClauses = [];
      state.results = [];
      state.completedCount = 0;
      state.totalClauses = 0;
      state.error = null;
    },
  },
});

export const {
  setSourceClause,
  setTargetClauses,
  addTargetClause,
  removeTargetClause,
  updateTargetClause,
  setPrompt,
  resetPrompt,
  startComparison,
  addResult,
  completeComparison,
  setError,
  clearAll,
} = batchComparisonSlice.actions;

export default batchComparisonSlice.reducer;

