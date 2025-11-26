"use client";

import { ReactNode, useMemo } from "react";
import { Provider } from "react-redux";
import { setupListeners } from "@reduxjs/toolkit/query";

import { ThemeProvider } from "@/components/providers/theme-provider";
import { makeStore } from "@/lib/store";

type ProvidersProps = {
  children: ReactNode;
};

export function AppProviders({ children }: ProvidersProps) {
  const store = useMemo(() => {
    const instance = makeStore();
    setupListeners(instance.dispatch);
    return instance;
  }, []);

  return (
    <Provider store={store}>
      <ThemeProvider
        attribute="class"
        defaultTheme="system"
        enableSystem
        disableTransitionOnChange
      >
        {children}
      </ThemeProvider>
    </Provider>
  );
}


