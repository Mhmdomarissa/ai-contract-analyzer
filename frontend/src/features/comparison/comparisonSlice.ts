/**
 * Redux slice for clause comparison feature
 * 
 * This slice manages the state for comparing two contract clauses using custom prompts.
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';

// Default prompt for conflict detection
export const DEFAULT_PROMPT = `Analyze the following two contract clauses and determine if they conflict with each other.

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

interface ClauseComparisonState {
  clauseA: string;
  clauseB: string;
  prompt: string;
  response: string | null;
  loading: boolean;
  error: string | null;
  model: string | null;
}

const initialState: ClauseComparisonState = {
  clauseA: '',
  clauseB: '',
  prompt: DEFAULT_PROMPT,
  response: null,
  loading: false,
  error: null,
  model: null,
};

// Async thunk for comparing clauses
export const compareClauses = createAsyncThunk(
  'comparison/compareClauses',
  async (
    payload: { clauseA: string; clauseB: string; prompt: string },
    { rejectWithValue }
  ) => {
    try {
      const response = await fetch('/api/v1/compare/clauses', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          clause_a: payload.clauseA,
          clause_b: payload.clauseB,
          prompt: payload.prompt,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        return rejectWithValue(errorData.detail || 'Failed to compare clauses');
      }

      const data = await response.json();
      return data;
    } catch (error) {
      return rejectWithValue(
        error instanceof Error ? error.message : 'Network error occurred'
      );
    }
  }
);

const comparisonSlice = createSlice({
  name: 'comparison',
  initialState,
  reducers: {
    setClauseA: (state, action: PayloadAction<string>) => {
      state.clauseA = action.payload;
    },
    setClauseB: (state, action: PayloadAction<string>) => {
      state.clauseB = action.payload;
    },
    setPrompt: (state, action: PayloadAction<string>) => {
      state.prompt = action.payload;
    },
    resetComparison: (state) => {
      state.response = null;
      state.error = null;
      state.model = null;
    },
    clearAll: () => initialState,
  },
  extraReducers: (builder) => {
    builder
      .addCase(compareClauses.pending, (state) => {
        state.loading = true;
        state.error = null;
        state.response = null;
      })
      .addCase(compareClauses.fulfilled, (state, action) => {
        state.loading = false;
        state.response = action.payload.response;
        state.model = action.payload.model;
        state.error = null;
      })
      .addCase(compareClauses.rejected, (state, action) => {
        state.loading = false;
        state.error = action.payload as string;
        state.response = null;
      });
  },
});

export const { setClauseA, setClauseB, setPrompt, resetComparison, clearAll } =
  comparisonSlice.actions;

export default comparisonSlice.reducer;
