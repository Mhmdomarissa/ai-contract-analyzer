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
  arabic_text?: string | null;
  is_bilingual?: boolean;
  number_normalized: string | null;
  analysis_results?: {
    spelling_errors?: Array<{
      word: string;
      position: number;
      suggestion: string;
      severity: 'HIGH' | 'MEDIUM' | 'LOW';
    }>;
    conflicts?: Array<{
      clause_id?: string;
      clause_number: string;
      type: 'LOGICAL' | 'LEGAL' | 'TERMINOLOGICAL';
      description: string;
      severity: 'HIGH' | 'MEDIUM' | 'LOW';
    }>;
    grammar_issues?: Array<{
      issue: string;
      position: number;
      suggestion: string;
      severity: 'HIGH' | 'MEDIUM' | 'LOW';
    }>;
    confidence_score?: number;
    summary?: string;
  } | null;
  analysis_status?: string | null;
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
  conflictJob: AnalysisRun | null;
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
  conflictJob: null,
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
const updateConflictJob = createAction<AnalysisRun | null>('contract/updateConflictJob');

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

const pollConflictDetection = async (
  contractId: string,
  runId: string,
  dispatch: (action: unknown) => unknown,
  signal: AbortSignal
): Promise<Conflict[]> => {
  // Conflict detection can take 30-45 minutes for large contracts
  // Poll for up to 60 minutes with 5 second intervals
  const maxAttempts = 720; // 720 * 5s = 60 minutes
  
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (signal.aborted) {
      throw new Error('Conflict detection aborted');
    }

    const statusResponse = await fetch(
      `${API_BASE_URL}/contracts/${contractId}/detect-conflicts/${runId}`,
      { signal }
    );
    if (!statusResponse.ok) {
      throw new Error('Failed to fetch conflict detection status');
    }

    const job = (await statusResponse.json()) as {
      run_id: string;
      status: string;
      error_message?: string;
      conflicts?: Conflict[];
      conflicts_count?: number;
      started_at?: string;
      finished_at?: string;
    };
    
    // Create AnalysisRun object for UI updates
    const runUpdate: AnalysisRun = {
      id: job.run_id,
      status: job.status,
      started_at: job.started_at || new Date().toISOString(),
      finished_at: job.finished_at,
      error_message: job.error_message,
    } as AnalysisRun;
    
    dispatch(updateConflictJob(runUpdate));

    if (job.status === 'COMPLETED') {
      return job.conflicts ?? [];
    }

    if (job.status === 'FAILED') {
      throw new Error(job.error_message || 'Conflict detection failed');
    }

    await delay(CLAUSE_POLL_INTERVAL_MS);

    if (signal.aborted) {
      throw new Error('Conflict detection aborted');
    }
  }

  throw new Error('Conflict detection timed out after 60 minutes');
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
  { conflicts: Conflict[]; clauses: Clause[] },
  string,
  RejectValue
>(
  'contract/detectConflicts',
  async (contractId, { rejectWithValue, signal, dispatch }) => {
    try {
      // Start async conflict detection
      const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/detect-conflicts`, {
        method: 'POST',
        signal,
      });
      if (!response.ok) {
        throw new Error('Failed to start conflict detection');
      }
      
      const run = (await response.json()) as AnalysisRun;
      dispatch(updateConflictJob(run));
      
      // Poll for completion (5-10 minutes expected)
      const conflicts = await pollConflictDetection(contractId, run.id, dispatch, signal);
      
      // Fetch updated clauses
      const clausesResponse = await fetch(`${API_BASE_URL}/contracts/${contractId}/clauses`, {
        method: 'GET',
        signal,
      });
      if (!clausesResponse.ok) {
        throw new Error('Failed to fetch clauses');
      }
      const clauses = (await clausesResponse.json()) as Clause[];
      
      return { conflicts, clauses };
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
    },
    updateClauses: (state, action) => {
      // Progressive update: merge new clause data with existing clauses
      // This preserves the UI state while updating analysis results
      const updatedClauses = action.payload as Clause[];
      const clauseMap = new Map(state.clauses.map(c => [c.id, c]));
      
      // Update existing clauses or add new ones
      updatedClauses.forEach(newClause => {
        const existing = clauseMap.get(newClause.id);
        if (existing) {
          // Update existing clause with new analysis results
          Object.assign(existing, newClause);
        } else {
          // Add new clause
          clauseMap.set(newClause.id, newClause);
        }
      });
      
      // Convert back to array, maintaining order
      state.clauses = Array.from(clauseMap.values()).sort((a, b) => a.order_index - b.order_index);
    }
  },
  extraReducers: (builder) => {
    builder.addCase(updateClauseJob, (state, action) => {
      state.clauseJob = action.payload;
    });
    builder.addCase(updateConflictJob, (state, action) => {
      state.conflictJob = action.payload;
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
      state.conflicts = action.payload.conflicts;
      state.clauses = action.payload.clauses; // Update clauses with analysis results
      state.currentStep = 'complete';
      state.status = 'succeeded';
    });
    builder.addCase(detectConflicts.rejected, (state, action) => {
      state.loadingStep = null;
      state.error = action.payload ?? action.error.message ?? 'Conflict detection failed';
      state.status = 'failed';
    });

  },
});

export const { resetState, updateClauses } = contractSlice.actions;
export default contractSlice.reducer;
