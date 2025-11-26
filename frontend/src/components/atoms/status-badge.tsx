"use client";

import { cn } from "@/lib/utils";
import type { ContractStatus } from "@/types/contracts";

const STATUS_COPY: Record<ContractStatus, string> = {
  PENDING: "Pending",
  PROCESSED: "Processed",
  FAILED: "Failed",
};

const STATUS_STYLES: Record<ContractStatus, string> = {
  PENDING:
    "bg-amber-100 text-amber-900 border border-amber-200 dark:bg-amber-500/10 dark:text-amber-100",
  PROCESSED:
    "bg-emerald-100 text-emerald-900 border border-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-100",
  FAILED:
    "bg-rose-100 text-rose-900 border border-rose-200 dark:bg-rose-500/10 dark:text-rose-100",
};

type StatusBadgeProps = {
  status: ContractStatus;
  className?: string;
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide",
        STATUS_STYLES[status],
        className,
      )}
    >
      {STATUS_COPY[status]}
    </span>
  );
}


