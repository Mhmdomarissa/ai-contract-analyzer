"use client";

import { ContractsSection } from "./contracts-section";
import { DashboardShell } from "@/components/templates/dashboard/dashboard-shell";

export function ContractsDashboard() {
  return (
    <DashboardShell
      title="Contract Review Overview"
      description="Pre-flight dashboard for upcoming ingestion, clause extraction, and conflict analysis flows."
    >
      <ContractsSection />
    </DashboardShell>
  );
}


