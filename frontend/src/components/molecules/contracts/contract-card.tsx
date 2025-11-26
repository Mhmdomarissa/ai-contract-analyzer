"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/atoms/status-badge";
import type { ContractSummary } from "@/types/contracts";

type ContractCardProps = {
  contract: ContractSummary;
};

export function ContractCard({ contract }: ContractCardProps) {
  return (
    <Card className="h-full border-border/60">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <div>
          <CardTitle className="text-base font-semibold">{contract.title}</CardTitle>
          <CardDescription>
            Uploaded {new Date(contract.upload_date).toLocaleDateString()}
          </CardDescription>
        </div>
        <StatusBadge status={contract.status} />
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        <p>Contract ID: {contract.id}</p>
      </CardContent>
    </Card>
  );
}


