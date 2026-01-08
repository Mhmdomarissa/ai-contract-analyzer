/**
 * Redux slice for all-vs-all clause comparison (N → N)
 * 
 * This slice manages the state for comparing all clauses against each other.
 * Generates N*(N-1)/2 unique pair comparisons.
 */

import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface PairComparisonResult {
  clause_i_index: number;
  clause_j_index: number;
  is_self_check: boolean;
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

export interface AllVsAllComparisonState {
  clauses: string[];
  pairPrompt: string;  // For clause vs clause comparisons
  selfPrompt: string;  // For clause vs itself (self-consistency check)
  results: PairComparisonResult[];
  isComparing: boolean;
  totalComparisons: number;
  completedCount: number;
  error: string | null;
  clauseCount: number;
}

const DEFAULT_PAIR_PROMPT = `You are a legal expert and contract review machine. Here are two clauses from the same contract. Your job is to check the language and terms of both clauses and check for the following;
	•	There is a conflict between the language and statements of that would make the other invalid or ambiguous.
	•	They specify different or incompatible terms for the same aspect.
	•	One clause undermines or contradicts the intent of the other
	•	They create legal ambiguity or uncertainty when read together

If you find there is a conflict or ambiguity highlight it in the following manner.

state clearly "there is a conflict"

In less than 150 words state the conflict and why you believe it meets the conditions above.

If you do not find a conflict then simply state "no conflict"`;

const DEFAULT_SELF_PROMPT = `You are a legal expert and contract review machine. Here is a clause from a contract. Your job is to check the language and terms of the clause and see if any of the statements therein meet the following conditions;
	•	There is a conflict between the language and statements of that would make the other invalid or ambiguous.
	•	They specify different or incompatible terms for the same aspect.
	•	One clause undermines or contradicts the intent of the other
	•	They create legal ambiguity or uncertainty when read together

If you find there is a conflict or ambiguity highlight it in the following manner.

state clearly "there is a conflict"

In less than 150 words state the conflict and why you believe it meets the conditions above.

If you do not find a conflict then simply state "no conflict"`;

const initialState: AllVsAllComparisonState = {
  clauses: [],
  pairPrompt: DEFAULT_PAIR_PROMPT,
  selfPrompt: DEFAULT_SELF_PROMPT,
  results: [],
  isComparing: false,
  totalComparisons: 0,
  completedCount: 0,
  error: null,
  clauseCount: 0,
};

const allVsAllComparisonSlice = createSlice({
  name: 'allVsAllComparison',
  initialState,
  reducers: {
    addClause: (state, action: PayloadAction<string>) => {
      if (state.clauses.length < 50) {
        state.clauses.push(action.payload);
      }
    },
    removeClause: (state, action: PayloadAction<number>) => {
      state.clauses.splice(action.payload, 1);
    },
    updateClause: (state, action: PayloadAction<{ index: number; value: string }>) => {
      const { index, value } = action.payload;
      if (index >= 0 && index < state.clauses.length) {
        state.clauses[index] = value;
      }
    },
    setClauses: (state, action: PayloadAction<string[]>) => {
      state.clauses = action.payload;
    },
    setPairPrompt: (state, action: PayloadAction<string>) => {
      state.pairPrompt = action.payload;
    },
    setSelfPrompt: (state, action: PayloadAction<string>) => {
      state.selfPrompt = action.payload;
    },
    resetPairPrompt: (state) => {
      state.pairPrompt = DEFAULT_PAIR_PROMPT;
    },
    resetSelfPrompt: (state) => {
      state.selfPrompt = DEFAULT_SELF_PROMPT;
    },
    startComparison: (state, action: PayloadAction<{ totalComparisons: number; clauseCount: number }>) => {
      state.isComparing = true;
      state.results = [];
      state.totalComparisons = action.payload.totalComparisons;
      state.clauseCount = action.payload.clauseCount;
      state.completedCount = 0;
      state.error = null;
    },
    addResult: (state, action: PayloadAction<PairComparisonResult>) => {
      state.results.push(action.payload);
      state.completedCount += 1;
    },
    completeComparison: (state) => {
      state.isComparing = false;
    },
    cancelComparison: (state) => {
      state.isComparing = false;
      state.error = 'Comparison cancelled by user';
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
      state.isComparing = false;
    },
    clearAll: (state) => {
      state.clauses = [];
      state.results = [];
      state.completedCount = 0;
      state.totalComparisons = 0;
      state.clauseCount = 0;
      state.error = null;
    },
  },
});

export const {
  addClause,
  removeClause,
  updateClause,
  setClauses,
  setPairPrompt,
  setSelfPrompt,
  resetPairPrompt,
  resetSelfPrompt,
  startComparison,
  addResult,
  completeComparison,
  cancelComparison,
  setError,
  clearAll,
} = allVsAllComparisonSlice.actions;

export default allVsAllComparisonSlice.reducer;
export { DEFAULT_PAIR_PROMPT, DEFAULT_SELF_PROMPT };
