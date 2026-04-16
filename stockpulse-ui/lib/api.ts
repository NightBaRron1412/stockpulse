const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000";

async function fetcher<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export const api = {
  dashboard: () => fetcher<any>("/api/dashboard"),
  watchlist: () => fetcher<any[]>("/api/watchlist"),
  watchlistTicker: (ticker: string) => fetcher<any>(`/api/watchlist/${ticker}`),
  portfolio: () => fetcher<any>("/api/portfolio"),
  analyze: (ticker: string) => fetcher<any>(`/api/analyze/${ticker}`, { method: "POST" }),
  validation: () => fetcher<any>("/api/validation"),
  reports: () => fetcher<any[]>("/api/reports"),
  report: (filename: string) => fetcher<any>(`/api/reports/${filename}`),
  alerts: () => fetcher<any[]>("/api/alerts/recent"),
  scanStatus: () => fetcher<any>("/api/scan/status"),
  activity: () => fetcher<any[]>("/api/activity"),
  quote: (ticker: string) => fetcher<any>(`/api/quote/${ticker}`),
  history: (ticker: string, period?: string) => fetcher<any>(`/api/history/${ticker}${period ? `?period=${period}` : ""}`),
  config: () => fetcher<any>("/api/config"),
  triggerScan: () => fetcher<any>("/api/scan", { method: "POST" }),
  addToWatchlist: (ticker: string) => fetcher<any>("/api/watchlist/add", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker }),
  }),
  removeFromWatchlist: (ticker: string) => fetcher<any>("/api/watchlist/remove", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker }),
  }),
  updateConfig: (data: Record<string, any>) =>
    fetcher<any>("/api/config/update", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    }),
  backtestStatus: () => fetcher<any>("/api/backtest/status"),
  triggerBacktest: (startDate: string, endDate: string) =>
    fetcher<any>("/api/backtest", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_date: startDate, end_date: endDate }),
    }),
  allocate: (amount: number, tickers?: string[]) =>
    fetcher<any>("/api/allocate", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount, ...(tickers?.length ? { tickers } : {}) }),
    }),
  importPortfolio: (text: string, cash?: number) => fetcher<any>("/api/portfolio/import", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, cash: cash ?? 0 }),
  }),
  upsertPosition: (ticker: string, shares: number, entry_price: number) => fetcher<any>("/api/portfolio/position", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ticker, shares, entry_price }),
  }),
  deletePosition: (ticker: string) => fetcher<any>(`/api/portfolio/position/${ticker}`, { method: "DELETE" }),
  advisorSuggestions: () => fetcher<any>("/api/advisor/suggestions"),
  advisorAcknowledge: (hash: string) => fetcher<any>("/api/advisor/acknowledge", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hash }),
  }),
  advisorEvaluate: () => fetcher<any>("/api/advisor/evaluate", { method: "POST" }),
  advisorExecute: (data: { hash: string; ticker: string; action: string; shares?: number; price?: number; swap_out_ticker?: string; swap_out_price?: number }) =>
    fetcher<any>("/api/advisor/execute", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  advisorConfig: () => fetcher<any>("/api/advisor/config"),
  reboundScan: () => fetcher<any>("/api/rebound/scan"),
  reboundLatest: () => fetcher<any>("/api/rebound/latest"),
  reboundStatus: () => fetcher<any>("/api/rebound/status"),
  reboundOpen: (data: { ticker: string; shares: number; entry_price: number; stop_price: number; target_price: number; setup?: string }) =>
    fetcher<any>("/api/rebound/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
  reboundClose: (ticker: string, exit_price: number, reason?: string) =>
    fetcher<any>("/api/rebound/close", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ticker, exit_price, reason: reason || "manual" }) }),
  reboundExits: () => fetcher<any>("/api/rebound/exits"),
  reboundConfig: () => fetcher<any>("/api/rebound/config"),
};
