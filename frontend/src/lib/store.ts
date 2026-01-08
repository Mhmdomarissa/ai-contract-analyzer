/**
 * Redux Store Configuration - Testing Lab + Upload & Extract
 * 
 * Contains state management for:
 * - Contract upload and clause extraction
 * - 1-to-1 clause comparison
 * - 1-to-N batch comparison  
 * - N-to-N all-vs-all comparison
 * - AI chatbot
 */
import { configureStore } from "@reduxjs/toolkit";

import uploadReducer from "@/features/upload/uploadSlice";
import comparisonReducer from "@/features/comparison/comparisonSlice";
import batchComparisonReducer from "@/features/batchComparison/batchComparisonSlice";
import allVsAllComparisonReducer from "@/features/allVsAllComparison/allVsAllComparisonSlice";
import chatReducer from "@/features/chat/chatSlice";
import { api } from "@/services/api";

export const makeStore = () =>
  configureStore({
    reducer: {
      upload: uploadReducer,
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


