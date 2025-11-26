"use client";

import { ContractCard } from "@/components/molecules/contracts/contract-card";
import type { ContractSummary } from "@/types/contracts";

type ContractListProps = {
  contracts: ContractSummary[];
};

export function ContractList({ contracts }: ContractListProps) {
  if (contracts.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-border/60 p-6 text-sm text-muted-foreground">
        No contracts yet. Upload a document to begin the review workflow.
      </p>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {contracts.map((contract) => (
        <ContractCard key={contract.id} contract={contract} />
      ))}
    </div>
  );
}


