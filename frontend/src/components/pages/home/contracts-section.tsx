"use client";

import { useMemo } from "react";

import { ContractList } from "@/components/organisms/contracts/contract-list";
import { StatusBadge } from "@/components/atoms/status-badge";
import { useGetContractsHealthQuery } from "@/services/api";
import type { ContractSummary } from "@/types/contracts";

const FALLBACK_CONTRACTS: ContractSummary[] = [
  {
    id: 1,
    title: "Vendor Agreement",
    upload_date: new Date().toISOString(),
    status: "PENDING",
  },
  {
    id: 2,
    title: "NDA v3",
    upload_date: new Date().toISOString(),
    status: "PROCESSED",
  },
];

export function ContractsSection() {
  const { data, isLoading, isError } = useGetContractsHealthQuery();

  const contracts = useMemo(() => FALLBACK_CONTRACTS, []);

  return (
    <section className="space-y-4 rounded-2xl border border-border/60 bg-card/60 p-6">
      <header className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold">Contract Intake</h2>
          <p className="text-sm text-muted-foreground">
            Monitor ingestion flow before wiring live data sources.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs uppercase text-muted-foreground">API Status</span>
          <StatusBadge status={isError ? "FAILED" : "PROCESSED"} />
        </div>
      </header>

      <p className="text-xs text-muted-foreground">
        Backend heartbeat:{" "}
        <span className="font-medium text-foreground">
          {isLoading ? "Checking..." : data?.status ?? "idle"}
        </span>
      </p>

      <ContractList contracts={contracts} />
    </section>
  );
}


