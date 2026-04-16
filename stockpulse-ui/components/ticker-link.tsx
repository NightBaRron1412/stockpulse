"use client";

import { useState, createContext, useContext, type ReactNode } from "react";
import { TickerDetailModal } from "./ticker-detail-modal";

const TickerContext = createContext<{ open: (ticker: string) => void }>({ open: () => {} });

export function TickerProvider({ children }: { children: ReactNode }) {
  const [activeTicker, setActiveTicker] = useState<string | null>(null);

  return (
    <TickerContext.Provider value={{ open: setActiveTicker }}>
      {children}
      <TickerDetailModal ticker={activeTicker} onClose={() => setActiveTicker(null)} />
    </TickerContext.Provider>
  );
}

export function useTickerModal() {
  return useContext(TickerContext);
}

export function TickerLink({
  ticker,
  children,
  className,
}: {
  ticker: string;
  children?: ReactNode;
  className?: string;
}) {
  const { open } = useTickerModal();
  return (
    <button
      onClick={(e) => { e.stopPropagation(); open(ticker); }}
      className={`font-semibold hover:text-blue-400 transition-colors hover:underline underline-offset-2 ${className ?? ""}`}
    >
      {children ?? ticker}
    </button>
  );
}
