import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

import type { ContractSummary } from "@/types/contracts";

type RequestState = "idle" | "loading" | "succeeded" | "failed";

interface ContractsState {
  items: ContractSummary[];
  status: RequestState;
}

const initialState: ContractsState = {
  items: [],
  status: "idle",
};

const contractsSlice = createSlice({
  name: "contracts",
  initialState,
  reducers: {
    setContracts(state, action: PayloadAction<ContractSummary[]>) {
      state.items = action.payload;
    },
    setStatus(state, action: PayloadAction<RequestState>) {
      state.status = action.payload;
    },
  },
});

export const { setContracts, setStatus } = contractsSlice.actions;
export default contractsSlice.reducer;


