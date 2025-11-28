"use client";

import { ReactNode, useEffect } from "react";

type GlobalErrorProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function GlobalError({ error, reset }: GlobalErrorProps): ReactNode {
  useEffect(() => {
    console.error("Global error boundary caught:", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-background text-foreground flex flex-col items-center justify-center gap-4 p-6">
        <h2>Something went wrong.</h2>
        <button
          type="button"
          className="rounded-md border border-foreground/20 px-4 py-2"
          onClick={reset}
        >
          Try again
        </button>
      </body>
    </html>
  );
}
