"use client";

import { ReactNode } from "react";

type DashboardShellProps = {
  title: string;
  description?: string;
  children: ReactNode;
};

export function DashboardShell({
  title,
  description,
  children,
}: DashboardShellProps) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="space-y-2">
        <p className="text-sm font-medium text-muted-foreground uppercase tracking-wide">
          Contract Review System
        </p>
        <h1 className="text-3xl font-semibold">{title}</h1>
        {description ? (
          <p className="text-base text-muted-foreground">{description}</p>
        ) : null}
      </header>
      <main className="flex-1 space-y-8">{children}</main>
    </div>
  );
}


