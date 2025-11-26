import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

import type { ContractHealthResponse } from "@/types/contracts";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export const api = createApi({
  reducerPath: "contractApi",
  baseQuery: fetchBaseQuery({
    baseUrl: API_BASE_URL,
  }),
  tagTypes: ["Contracts"],
  endpoints: (builder) => ({
    getContractsHealth: builder.query<ContractHealthResponse, void>({
      query: () => "/contracts/health",
      providesTags: ["Contracts"],
    }),
  }),
});

export const { useGetContractsHealthQuery } = api;


