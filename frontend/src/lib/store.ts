import { configureStore } from "@reduxjs/toolkit";

import comparisonReducer from "@/features/comparison/comparisonSlice";
import batchComparisonReducer from "@/features/batchComparison/batchComparisonSlice";
import allVsAllComparisonReducer from "@/features/allVsAllComparison/allVsAllComparisonSlice";
import chatReducer from "@/features/chat/chatSlice";
import { api } from "@/services/api";

export const makeStore = () =>
  configureStore({
    reducer: {
      // ============================================================================
      // TEMPORARILY COMMENTED OUT - Original features preserved for later reuse
      // ============================================================================
      // contracts: contractsReducer,
      // contract: contractReducer,
      // ============================================================================
      
      // New temporary features
      comparison: comparisonReducer,
      batchComparison: batchComparisonReducer,
      allVsAllComparison: allVsAllComparisonReducer,
      chat: chatReducer,
      [api.reducerPath]: api.reducer,
    },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware({
        serializableCheck: false,
      }).concat(api.middleware),
  });

export type AppStore = ReturnType<typeof makeStore>;
export type AppDispatch = AppStore["dispatch"];
export type RootState = ReturnType<AppStore["getState"]>;


