"use client";

import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { formatPnl, formatPct, cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Portfolio } from "@/lib/types";
import { useState } from "react";

export default function PortfolioPage() {
  const { data, loading, error } = usePolling<Portfolio>(api.portfolio, 30000);
  const [sortKey, setSortKey] = useState<string>("pnl_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Portfolio</h1>
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
        <h1 className="text-2xl font-semibold">Portfolio</h1>
        <div className="glass-card p-6 text-red-400">Failed to load portfolio: {error}</div>
      </div>
    );
  }

  if (!data || !data.positions || data.positions.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Portfolio</h1>
        <div className="glass-card p-8 text-center text-slate-500">
          No positions yet -- portfolio tracking will appear after you add trades
        </div>
      </div>
    );
  }

  const drawdownPct = data.drawdown?.drawdown_pct ?? 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Portfolio</h1>

      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total Invested</p>
          <p className="text-2xl font-bold font-mono-data text-slate-200">
            ${(data.total_invested ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Current Value</p>
          <p className="text-2xl font-bold font-mono-data text-slate-200">
            ${(data.total_current ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total P&L</p>
          <p className={cn("text-2xl font-bold font-mono-data", data.total_pnl >= 0 ? "text-green-400" : "text-red-400")}>
            {formatPnl(data.total_pnl)}
          </p>
          <p className={cn("text-xs font-mono-data", data.total_pnl_pct >= 0 ? "text-green-400/70" : "text-red-400/70")}>
            {formatPct(data.total_pnl_pct)}
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Drawdown</p>
          <p className={cn("text-2xl font-bold font-mono-data", drawdownPct > 5 ? "text-red-400" : "text-slate-300")}>
            {(drawdownPct ?? 0).toFixed(1)}%
          </p>
        </div>
      </div>

      {/* Positions table */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/60 px-4">
        <div className="px-1 py-4 border-b border-slate-700/50">
          <h2 className="text-sm font-semibold text-slate-300">Positions</h2>
        </div>
        <Table>
          <TableHeader>
            <TableRow className="border-slate-700/50 hover:bg-transparent">
              <SortHead label="Ticker" sortKey="ticker" current={sortKey} dir={sortDir} onSort={handleSort} />
              <SortHead label="Shares" sortKey="shares" current={sortKey} dir={sortDir} onSort={handleSort} align="right" />
              <SortHead label="Entry" sortKey="entry_price" current={sortKey} dir={sortDir} onSort={handleSort} align="right" />
              <SortHead label="Current" sortKey="current_price" current={sortKey} dir={sortDir} onSort={handleSort} align="right" />
              <SortHead label="P&L %" sortKey="pnl_pct" current={sortKey} dir={sortDir} onSort={handleSort} align="right" />
              <SortHead label="P&L $" sortKey="pnl" current={sortKey} dir={sortDir} onSort={handleSort} align="right" />
              <TableHead className="text-slate-400 text-xs">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...data.positions].sort((a: any, b: any) => {
              const av = a[sortKey] ?? 0;
              const bv = b[sortKey] ?? 0;
              if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
              return sortDir === "asc" ? av - bv : bv - av;
            }).map((pos) => (
              <TableRow key={pos.ticker} className="border-slate-700/30 hover:bg-slate-800/30">
                <TableCell className="font-semibold">{pos.ticker}</TableCell>
                <TableCell className="font-mono-data text-right text-xs">{pos.shares}</TableCell>
                <TableCell className="font-mono-data text-right text-xs">
                  {pos.entry_price != null ? `$${pos.entry_price.toFixed(2)}` : "--"}
                </TableCell>
                <TableCell className="font-mono-data text-right text-xs">
                  {pos.current_price != null ? `$${pos.current_price.toFixed(2)}` : "--"}
                </TableCell>
                <TableCell className={cn("font-mono-data text-right text-xs", pos.pnl_pct >= 0 ? "text-green-400" : "text-red-400")}>
                  {formatPct(pos.pnl_pct)}
                </TableCell>
                <TableCell className={cn("font-mono-data text-right text-xs", pos.pnl >= 0 ? "text-green-400" : "text-red-400")}>
                  {formatPnl(pos.pnl)}
                </TableCell>
                <TableCell className="pl-6">
                  <span className={cn(
                    "px-2 py-0.5 rounded text-[11px] font-medium",
                    pos.pnl >= 0 ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"
                  )}>
                    {pos.pnl >= 0 ? "Profit" : "Loss"}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Risk panel */}
      {data.drawdown && (
        <div className="glass-card p-5 space-y-3">
          <h2 className="text-sm font-semibold text-slate-300">Risk: Drawdown Gauge</h2>
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-slate-400">
              <span>0%</span>
              <span className="font-mono-data">{(drawdownPct ?? 0).toFixed(1)}%</span>
              <span>20%</span>
            </div>
            <Progress
              value={Math.min((drawdownPct / 20) * 100, 100)}
              className="h-3 bg-slate-700/50"
            />
          </div>
          {data.drawdown.new_buys_paused && (
            <p className="text-xs text-orange-400 font-medium">New buys paused due to high drawdown</p>
          )}
          <p className="text-xs text-slate-500">
            Size multiplier: <span className="font-mono-data">{data.drawdown?.size_multiplier != null ? `${data.drawdown.size_multiplier.toFixed(2)}x` : "--"}</span>
          </p>
        </div>
      )}
    </div>
  );
}

function SortHead({ label, sortKey, current, dir, onSort, align = "left" }: {
  label: string; sortKey: string; current: string; dir: "asc" | "desc"; onSort: (key: string) => void; align?: "left" | "right";
}) {
  const active = current === sortKey;
  return (
    <TableHead className={cn("text-slate-400 text-xs", align === "right" && "text-right")}>
      <button onClick={() => onSort(sortKey)} className={cn("flex items-center gap-1 hover:text-slate-200 transition-colors cursor-pointer", align === "right" && "ml-auto")}>
        {label}
        <span className={cn("text-[10px]", active ? "text-blue-400" : "text-slate-600")}>
          {active ? (dir === "desc" ? "▼" : "▲") : "⇅"}
        </span>
      </button>
    </TableHead>
  );
}
