// Upload and extraction feature Redux slice
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface ProgressEvent {
  stage: string;
  message: string;
  progress: number;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface Clause {
  id: string;
  clause_number: string;
  content: string;
  order_index: number;
  sub_clauses?: Array<{
    id: string;
    clause_number: string;
    content: string;
    order_index: number;
  }>;
}

export interface ContractDetails {
  id: string;
  filename: string;
  status: string;
  file_type: string;
  file_size: number;
  created_at: string;
  clause_count: number;
  parties: Array<{ id: string; name: string }>;
  error_message?: string;
}

interface UploadState {
  // Upload state
  isUploading: boolean;
  uploadProgress: number;
  currentStage: string;
  statusMessage: string;
  progressEvents: ProgressEvent[];
  error: string | null;
  
  // Contract state
  contractId: string | null;
  contractDetails: ContractDetails | null;
  clauses: Clause[];
  selectedClauseIds: string[];
  
  // UI state
  showClauseList: boolean;
  searchQuery: string;
  clauseFilter: 'all' | 'main' | 'sub';
}

const initialState: UploadState = {
  isUploading: false,
  uploadProgress: 0,
  currentStage: '',
  statusMessage: '',
  progressEvents: [],
  error: null,
  
  contractId: null,
  contractDetails: null,
  clauses: [],
  selectedClauseIds: [],
  
  showClauseList: false,
  searchQuery: '',
  clauseFilter: 'all',
};

const uploadSlice = createSlice({
  name: 'upload',
  initialState,
  reducers: {
    // Upload actions
    uploadStarted: (state) => {
      state.isUploading = true;
      state.uploadProgress = 0;
      state.currentStage = '';
      state.statusMessage = '';
      state.progressEvents = [];
      state.error = null;
      state.contractId = null;
    },
    
    progressUpdate: (state, action: PayloadAction<ProgressEvent>) => {
      const event = action.payload;
      state.uploadProgress = event.progress;
      state.currentStage = event.stage;
      state.statusMessage = event.message;
      state.progressEvents.push(event);
      
      // Extract contract ID if present
      if (event.data.contract_id) {
        state.contractId = event.data.contract_id;
      }
    },
    
    uploadCompleted: (state, action: PayloadAction<{ contractId: string }>) => {
      state.isUploading = false;
      state.uploadProgress = 100;
      state.currentStage = 'COMPLETED';
      state.contractId = action.payload.contractId;
      state.showClauseList = true;
    },
    
    uploadFailed: (state, action: PayloadAction<string>) => {
      state.isUploading = false;
      state.error = action.payload;
      state.currentStage = 'ERROR';
    },
    
    uploadReset: () => {
      return initialState;
    },
    
    // Contract details actions
    setContractDetails: (state, action: PayloadAction<ContractDetails>) => {
      state.contractDetails = action.payload;
    },
    
    // Clause actions
    setClausesList: (state, action: PayloadAction<Clause[]>) => {
      state.clauses = action.payload;
    },
    
    toggleClauseSelection: (state, action: PayloadAction<string>) => {
      const clauseId = action.payload;
      const index = state.selectedClauseIds.indexOf(clauseId);
      
      if (index > -1) {
        state.selectedClauseIds.splice(index, 1);
      } else {
        state.selectedClauseIds.push(clauseId);
      }
    },
    
    selectAllClauses: (state) => {
      state.selectedClauseIds = state.clauses.map(c => c.id);
    },
    
    clearClauseSelection: (state) => {
      state.selectedClauseIds = [];
    },
    
    // UI actions
    setShowClauseList: (state, action: PayloadAction<boolean>) => {
      state.showClauseList = action.payload;
    },
    
    setSearchQuery: (state, action: PayloadAction<string>) => {
      state.searchQuery = action.payload;
    },
    
    setClauseFilter: (state, action: PayloadAction<'all' | 'main' | 'sub'>) => {
      state.clauseFilter = action.payload;
    },
  },
});

export const {
  uploadStarted,
  progressUpdate,
  uploadCompleted,
  uploadFailed,
  uploadReset,
  setContractDetails,
  setClausesList,
  toggleClauseSelection,
  selectAllClauses,
  clearClauseSelection,
  setShowClauseList,
  setSearchQuery,
  setClauseFilter,
} = uploadSlice.actions;

export default uploadSlice.reducer;
