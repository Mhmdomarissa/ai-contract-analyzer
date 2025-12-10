import { createSlice, createAsyncThunk, createAction } from '@reduxjs/toolkit';

// Types
export interface ContractFile {
  id: string;
  storage_path: string;
  file_name: string;
  mime_type: string;
  file_size_bytes: number;
  uploaded_at: string;
}

export interface ContractVersion {
  id: string;
  contract_id: string;
  file_id: string;
  version_number: number;
  is_current: boolean;
  parsed_text: string | null;
  created_at: string;
  file: ContractFile;
}

export interface Contract {
  id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  latest_version: ContractVersion | null;
}

export interface Clause {
  id: string;
  contract_version_id: string;
  clause_number: string | null;
  heading: string | null;
  order_index: number;
  language: string | null;
  clause_group_id: string | null;
  text: string;
  number_normalized: string | null;
  created_at: string;
}

export interface Conflict {
  id: string;
  severity: string;
  summary: string;
  explanation: string | null;
  type: string;
  created_at: string;
  left_clause?: {
    id: string;
    clause_number: string | null;
    heading: string | null;
    text: string | null;
  };
  right_clause?: {
    id: string;
    clause_number: string | null;
    heading: string | null;
    text: string | null;
  };
}

export interface AnalysisRun {
  id: string;
  type: string;
  model_name: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error_message: string | null;
  contract_version_id: string;
}

interface ClauseExtractionJobResponse {
  run: AnalysisRun;
  clauses: Clause[] | null;
}

type LoadingStep = 'upload' | 'extract' | 'detect' | 'explain' | null;

interface ContractState {
  contract: Contract | null;
  clauses: Clause[];
  conflicts: Conflict[];
  clauseJob: AnalysisRun | null;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
  currentStep: 'upload' | 'extract' | 'detect' | 'explain' | 'complete';
  loadingStep: LoadingStep;
}

const initialState: ContractState = {
  contract: null,
  clauses: [],
  conflicts: [],
  clauseJob: null,
  status: 'idle',
  error: null,
  currentStep: 'upload',
  loadingStep: null,
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";
const CLAUSE_POLL_INTERVAL_MS = 3000;
const CLAUSE_POLL_ATTEMPTS = 600; // 30 minutes timeout

const delay = (ms: number): Promise<void> =>
  new Promise((resolve) => {
    setTimeout(resolve, ms);
  });

const formatError = (err: unknown): string => {
  if (err instanceof Error) {
    return err.message;
  }
  return 'Unexpected error occurred';
};

type RejectValue = { rejectValue: string };

const updateClauseJob = createAction<AnalysisRun | null>('contract/updateClauseJob');

const pollClauseExtraction = async (
  contractId: string,
  runId: string,
  dispatch: (action: unknown) => unknown,
  signal: AbortSignal
): Promise<Clause[]> => {
  for (let attempt = 0; attempt < CLAUSE_POLL_ATTEMPTS; attempt += 1) {
    if (signal.aborted) {
      throw new Error('Clause extraction aborted');
    }

    const statusResponse = await fetch(
      `${API_BASE_URL}/contracts/${contractId}/extract-clauses/${runId}`,
      { signal }
    );
    if (!statusResponse.ok) {
      throw new Error('Failed to fetch clause extraction status');
    }

    const job = (await statusResponse.json()) as ClauseExtractionJobResponse;
    dispatch(updateClauseJob(job.run));

    if (job.run.status === 'COMPLETED') {
      return job.clauses ?? [];
    }

    if (job.run.status === 'FAILED') {
      throw new Error(job.run.error_message || 'Clause extraction failed');
    }

    await delay(CLAUSE_POLL_INTERVAL_MS);

    if (signal.aborted) {
      throw new Error('Clause extraction aborted');
    }
  }

  throw new Error('Clause extraction timed out');
};

// Async Thunks
export const uploadContract = createAsyncThunk<
  Contract,
  FormData,
  RejectValue
>(
  'contract/upload',
  async (formData, { rejectWithValue, signal }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/contracts/upload`, {
        method: 'POST',
        body: formData,
        signal,
      });
      if (!response.ok) {
        throw new Error('Upload failed');
      }
      return (await response.json()) as Contract;
    } catch (err) {
      return rejectWithValue(formatError(err));
    }
  }
);

export const extractClauses = createAsyncThunk<
  Clause[],
  string,
  RejectValue
>(
  'contract/extractClauses',
  async (contractId, { rejectWithValue, dispatch, signal }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/extract-clauses`, {
        method: 'POST',
        signal,
      });
      if (!response.ok) {
        throw new Error('Failed to start clause extraction');
      }

      const run = (await response.json()) as AnalysisRun;
      dispatch(updateClauseJob(run));

      const clauses = await pollClauseExtraction(contractId, run.id, dispatch, signal);
      return clauses;
    } catch (err) {
      return rejectWithValue(formatError(err));
    }
  }
);

export const detectConflicts = createAsyncThunk<
  Conflict[],
  string,
  RejectValue
>(
  'contract/detectConflicts',
  async (contractId, { rejectWithValue, signal }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/detect-conflicts`, {
        method: 'POST',
        signal,
      });
      if (!response.ok) {
        throw new Error('Conflict detection failed');
      }
      return (await response.json()) as Conflict[];
    } catch (err) {
      return rejectWithValue(formatError(err));
    }
  }
);

export const generateExplanations = createAsyncThunk<
  Conflict[],
  string,
  RejectValue
>(
  'contract/generateExplanations',
  async (contractId, { rejectWithValue, signal }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/generate-explanations`, {
        method: 'POST',
        signal,
      });
      if (!response.ok) {
        throw new Error('Explanation generation failed');
      }
      return (await response.json()) as Conflict[];
    } catch (err) {
      return rejectWithValue(formatError(err));
    }
  }
);

const contractSlice = createSlice({
  name: 'contract',
  initialState,
  reducers: {
    resetState: (state) => {
      state.contract = null;
      state.clauses = [];
      state.conflicts = [];
      state.clauseJob = null;
      state.status = 'idle';
      state.error = null;
      state.currentStep = 'upload';
      state.loadingStep = null;
    }
  },
  extraReducers: (builder) => {
    builder.addCase(updateClauseJob, (state, action) => {
      state.clauseJob = action.payload;
    });

    // Upload
    builder.addCase(uploadContract.pending, (state) => {
      state.loadingStep = 'upload';
      state.error = null;
      state.status = 'loading';
    });
    builder.addCase(uploadContract.fulfilled, (state, action) => {
      state.loadingStep = null;
      state.contract = action.payload;
      state.currentStep = 'extract';
      state.status = 'succeeded';
    });
    builder.addCase(uploadContract.rejected, (state, action) => {
      state.loadingStep = null;
      state.error = action.payload ?? action.error.message ?? 'Upload failed';
      state.status = 'failed';
    });

    // Extract
    builder.addCase(extractClauses.pending, (state) => {
      state.loadingStep = 'extract';
      state.error = null;
      state.status = 'loading';
      state.clauseJob = null;
    });
    builder.addCase(extractClauses.fulfilled, (state, action) => {
      state.loadingStep = null;
      state.clauses = action.payload;
      state.currentStep = 'detect';
      state.status = 'succeeded';
    });
    builder.addCase(extractClauses.rejected, (state, action) => {
      state.loadingStep = null;
      state.error = action.payload ?? action.error.message ?? 'Clause extraction failed';
      state.status = 'failed';
      state.clauseJob = null;
    });

    // Detect
    builder.addCase(detectConflicts.pending, (state) => {
      state.loadingStep = 'detect';
      state.error = null;
      state.status = 'loading';
    });
    builder.addCase(detectConflicts.fulfilled, (state, action) => {
      state.loadingStep = null;
      state.conflicts = action.payload;
      state.currentStep = 'explain';
      state.status = 'succeeded';
    });
    builder.addCase(detectConflicts.rejected, (state, action) => {
      state.loadingStep = null;
      state.error = action.payload ?? action.error.message ?? 'Conflict detection failed';
      state.status = 'failed';
    });

    // Explain
    builder.addCase(generateExplanations.pending, (state) => {
      state.loadingStep = 'explain';
      state.error = null;
      state.status = 'loading';
    });
    builder.addCase(generateExplanations.fulfilled, (state, action) => {
      state.loadingStep = null;
      state.conflicts = action.payload; // Updates conflicts with explanations
      state.currentStep = 'complete';
      state.status = 'succeeded';
    });
    builder.addCase(generateExplanations.rejected, (state, action) => {
      state.loadingStep = null;
      state.error = action.payload ?? action.error.message ?? 'Explanation generation failed';
      state.status = 'failed';
    });
  },
});

export const { resetState } = contractSlice.actions;
export default contractSlice.reducer;
