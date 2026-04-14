"use client";

import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { actionBadgeClass, formatPnl, formatPct, formatScore, cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Recommendation, Activity, Portfolio } from "@/lib/types";

interface DashboardData {
  top_signals: Recommendation[];
  portfolio: Portfolio;
  signal_count: Record<string, number>;
  scan_status: { running: boolean; progress: string; last_completed: string; next_scheduled: string };
  activity: Activity[];
  total_scanned: number;
}

export default function DashboardPage() {
  const { data, loading, error } = usePolling<DashboardData>(api.dashboard, 30000);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="glass-card p-6 animate-pulse">
              <div className="h-4 bg-slate-700/50 rounded w-24 mb-3" />
              <div className="h-8 bg-slate-700/50 rounded w-16" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="glass-card p-6 text-red-400">Failed to load dashboard: {error}</div>
      </div>
    );
  }

  const portfolio = data?.portfolio;
  const topSignals = data?.top_signals ?? [];
  const events = data?.activity ?? [];
  const signalCount = data?.signal_count ?? {};
  const scanStatus = data?.scan_status;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Dashboard</h1>

      {/* Stats Cards Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Portfolio P&L</p>
          <p
            className={cn(
              "text-2xl font-bold font-mono-data",
              portfolio && portfolio.total_pnl >= 0 ? "text-green-400" : "text-red-400"
            )}
          >
            {portfolio ? formatPnl(portfolio.total_pnl) : "--"}
          </p>
          {portfolio && (
            <p className={cn("text-xs font-mono-data", portfolio.total_pnl_pct >= 0 ? "text-green-400/70" : "text-red-400/70")}>
              {formatPct(portfolio.total_pnl_pct)}
            </p>
          )}
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Active Signals</p>
          <p className="text-2xl font-bold font-mono-data text-blue-400">
            {signalCount.WATCHLIST ?? 0} <span className="text-sm text-slate-500">WATCHLIST</span>
          </p>
          <p className="text-xs text-slate-500 font-mono-data">
            {signalCount.BUY ?? 0} BUY · {signalCount.CAUTION ?? 0} CAUTION
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total Scanned</p>
          <p className="text-2xl font-bold text-violet-400 font-mono-data">
            {data?.total_scanned ?? 0}
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Last Scan</p>
          <p className="text-lg font-bold text-slate-300 font-mono-data">
            {scanStatus?.last_completed ?? "Never"}
          </p>
          <p className="text-xs text-slate-500">Next: {scanStatus?.next_scheduled ?? "--"}</p>
        </div>
      </div>

      {/* Main content: signals + activity */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Top Signals Table */}
        <div className="lg:col-span-3 glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Top Signals</h2>
          </div>
          {topSignals.length === 0 ? (
            <div className="p-8 text-center text-slate-500">
              No data yet -- run your first scan
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700/50 hover:bg-transparent">
                  <TableHead className="text-slate-400 text-xs w-10">#</TableHead>
                  <TableHead className="text-slate-400 text-xs">Ticker</TableHead>
                  <TableHead className="text-slate-400 text-xs">Action</TableHead>
                  <TableHead className="text-slate-400 text-xs">Score</TableHead>
                  <TableHead className="text-slate-400 text-xs">Conf.</TableHead>
                  <TableHead className="text-slate-400 text-xs">Thesis</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topSignals.slice(0, 10).map((sig, i) => (
                  <TableRow key={sig.ticker} className="border-slate-700/30 hover:bg-slate-800/30">
                    <TableCell className="font-mono-data text-slate-500 text-xs">{i + 1}</TableCell>
                    <TableCell className="font-semibold">{sig.ticker}</TableCell>
                    <TableCell>
                      <span className={cn("px-2 py-0.5 rounded text-xs font-medium", actionBadgeClass(sig.action))}>
                        {sig.action}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-mono-data text-xs w-10 text-right">
                          {formatScore(sig.composite_score)}
                        </span>
                        <div className="w-16 h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full",
                              sig.composite_score >= 0 ? "score-bar-positive" : "score-bar-negative"
                            )}
                            style={{
                              width: `${Math.min(Math.abs(sig.composite_score) * 10, 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="font-mono-data text-xs">{sig.confidence}%</TableCell>
                    <TableCell className="text-xs text-slate-400 max-w-[200px] truncate">
                      {sig.thesis}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Activity Feed */}
        <div className="lg:col-span-2 glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Activity Feed</h2>
          </div>
          <ScrollArea className="h-[380px]">
            {events.length === 0 ? (
              <div className="p-8 text-center text-slate-500">No recent activity</div>
            ) : (
              <div className="divide-y divide-slate-700/30">
                {events.map((evt, i) => (
                  <div key={i} className="px-5 py-3 hover:bg-slate-800/20">
                    <div className="flex items-start gap-3">
                      <ActivityIcon type={evt.type} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-slate-200 leading-snug">{evt.message}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5 font-mono-data">
                          {evt.timestamp ? (() => { try { return new Date(evt.timestamp).toLocaleString(); } catch { return evt.timestamp; } })() : "--"}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </ScrollArea>
        </div>
      </div>

      {/* Portfolio mini view */}
      {portfolio && portfolio.positions && portfolio.positions.length > 0 && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Portfolio</h2>
          </div>
          <div className="flex flex-wrap gap-3 p-4">
            {portfolio.positions.map((pos) => (
              <div
                key={pos.ticker}
                className="flex items-center gap-3 px-4 py-2 rounded-lg bg-slate-800/30 border border-slate-700/30"
              >
                <span className="font-semibold text-sm">{pos.ticker}</span>
                <span className={cn("font-mono-data text-sm", pos.pnl >= 0 ? "text-green-400" : "text-red-400")}>
                  {formatPnl(pos.pnl)}
                </span>
                <span className={cn("font-mono-data text-xs", pos.pnl_pct >= 0 ? "text-green-400/70" : "text-red-400/70")}>
                  {formatPct(pos.pnl_pct)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ActivityIcon({ type }: { type: string }) {
  const iconClass = "w-4 h-4 mt-0.5 shrink-0";
  switch (type) {
    case "scan":
      return (
        <svg className={cn(iconClass, "text-blue-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      );
    case "signal":
      return (
        <svg className={cn(iconClass, "text-green-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
        </svg>
      );
    case "alert":
      return (
        <svg className={cn(iconClass, "text-orange-400")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
        </svg>
      );
    default:
      return (
        <svg className={cn(iconClass, "text-slate-500")} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
        </svg>
      );
  }
}
