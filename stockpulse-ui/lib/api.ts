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
};
