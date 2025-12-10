import { configureStore } from "@reduxjs/toolkit";

import contractsReducer from "@/features/contracts/contractsSlice";
import contractReducer from "@/features/contract/contractSlice";
import { api } from "@/services/api";

export const makeStore = () =>
  configureStore({
    reducer: {
      contracts: contractsReducer,
      contract: contractReducer,
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


