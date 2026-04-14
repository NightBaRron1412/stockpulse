"use client";

import { useState, useCallback } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { actionBadgeClass, formatScore, cn } from "@/lib/utils";
import { getSignalLabel, getSignalDescription } from "@/lib/signal-labels";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Recommendation, Action } from "@/lib/types";

const ACTIONS: Action[] = ["BUY", "WATCHLIST", "HOLD", "CAUTION", "SELL"];

export default function WatchlistPage() {
  const { data, loading, error, refresh } = usePolling<Recommendation[]>(api.watchlist, 30000);
  const [filter, setFilter] = useState<Action | "ALL">("ALL");
  const [search, setSearch] = useState("");
  const [addTicker, setAddTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null);

  const handleAdd = useCallback(async () => {
    const ticker = addTicker.trim().toUpperCase();
    if (!ticker) return;
    setAdding(true);
    try {
      await api.addToWatchlist(ticker);
      setAddTicker("");
      refresh();
    } finally {
      setAdding(false);
    }
  }, [addTicker, refresh]);

  const handleRemove = useCallback(async (ticker: string) => {
    setRemoving(ticker);
    try {
      await api.removeFromWatchlist(ticker);
      refresh();
    } finally {
      setRemoving(null);
    }
  }, [refresh]);

  const items = (data ?? [])
    .filter((r) => filter === "ALL" || r.action === filter)
    .filter((r) => !search || r.ticker.toUpperCase().includes(search.toUpperCase()));

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Watchlist</h1>
        <div className="glass-card p-6 animate-pulse">
          <div className="h-64 bg-slate-700/20 rounded" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Watchlist</h1>
        <div className="glass-card p-6 text-red-400">Failed to load watchlist: {error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Watchlist</h1>
        <div className="flex items-center gap-2">
          <Input
            value={addTicker}
            onChange={(e) => setAddTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder="Add ticker..."
            className="w-32 bg-slate-800/50 border-slate-700/50 h-9 text-sm"
          />
          <Button onClick={handleAdd} disabled={adding} size="sm" className="h-9">
            {adding ? "Adding..." : "Add"}
          </Button>
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setFilter("ALL")}
          className={cn(
            "px-3 py-1 rounded text-xs font-medium transition-colors",
            filter === "ALL"
              ? "bg-slate-700/60 text-slate-100"
              : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
          )}
        >
          All
        </button>
        {ACTIONS.map((action) => (
          <button
            key={action}
            onClick={() => setFilter(action)}
            className={cn(
              "px-3 py-1 rounded text-xs font-medium transition-colors",
              filter === action ? actionBadgeClass(action) : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
            )}
          >
            {action}
          </button>
        ))}
        <div className="ml-auto">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ticker..."
            className="w-48 bg-slate-800/50 border-slate-700/50 h-8 text-sm"
          />
        </div>
      </div>

      {/* Table */}
      <div className="glass-card p-0 overflow-hidden">
        {items.length === 0 ? (
          <div className="p-8 text-center text-slate-500">
            {data?.length === 0
              ? "No tickers on your watchlist yet -- add one above"
              : "No tickers match your filter"}
          </div>
        ) : (
          <ScrollArea className="max-h-[600px]">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700/50 hover:bg-transparent">
                  <TableHead className="text-slate-400 text-xs">Ticker</TableHead>
                  <TableHead className="text-slate-400 text-xs">Action</TableHead>
                  <TableHead className="text-slate-400 text-xs">Score</TableHead>
                  <TableHead className="text-slate-400 text-xs">Confidence</TableHead>
                  <TableHead className="text-slate-400 text-xs">Thesis</TableHead>
                  <TableHead className="text-slate-400 text-xs">Source</TableHead>
                  <TableHead className="text-slate-400 text-xs w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((rec) => (
                  <>
                    <TableRow
                      key={rec.ticker}
                      className="border-slate-700/30 hover:bg-slate-800/30 cursor-pointer"
                      onClick={() =>
                        setExpandedTicker(expandedTicker === rec.ticker ? null : rec.ticker)
                      }
                    >
                      <TableCell className="font-semibold">{rec.ticker}</TableCell>
                      <TableCell>
                        <span className={cn("px-2 py-0.5 rounded text-xs font-medium", actionBadgeClass(rec.action))}>
                          {rec.action}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-mono-data text-xs w-10 text-right">
                            {formatScore(rec.composite_score)}
                          </span>
                          <div className="w-16 h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                            <div
                              className={cn(
                                "h-full rounded-full",
                                rec.composite_score >= 0 ? "score-bar-positive" : "score-bar-negative"
                              )}
                              style={{
                                width: `${Math.min(Math.abs(rec.composite_score) * 10, 100)}%`,
                              }}
                            />
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="font-mono-data text-xs">{rec.confidence}%</TableCell>
                      <TableCell className="text-xs text-slate-400 max-w-[250px] truncate">
                        {rec.thesis}
                      </TableCell>
                      <TableCell className="text-xs text-slate-500 capitalize">
                        {rec.source ?? "user"}
                      </TableCell>
                      <TableCell>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleRemove(rec.ticker); }}
                          disabled={removing === rec.ticker}
                          className="p-1 rounded hover:bg-red-500/10 text-slate-600 hover:text-red-400 transition-colors cursor-pointer"
                          title={`Remove ${rec.ticker}`}
                        >
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </TableCell>
                    </TableRow>
                    {expandedTicker === rec.ticker && (
                      <TableRow key={`${rec.ticker}-detail`} className="border-slate-700/30 bg-slate-800/20">
                        <TableCell colSpan={7} className="p-4">
                          <SignalDetail rec={rec} />
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))}
              </TableBody>
            </Table>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}

function SignalDetail({ rec }: { rec: Recommendation }) {
  const signals = Object.entries(rec.signals ?? {});
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-300">{rec.thesis}</p>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
        {signals.map(([name, sig]) => (
          <div key={name} className="flex items-center gap-2 text-xs">
            <Tooltip>
              <TooltipTrigger className="cursor-help text-slate-400 w-28 truncate">
                {getSignalLabel(name)}
              </TooltipTrigger>
              <TooltipContent side="left" className="max-w-[300px] bg-slate-800 border-slate-700 text-slate-200">
                <p className="text-xs">{getSignalDescription(name)}</p>
              </TooltipContent>
            </Tooltip>
            <div className="flex-1 h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full",
                  (sig.score ?? 0) >= 0 ? "score-bar-positive" : "score-bar-negative"
                )}
                style={{ width: `${Math.min(Math.abs(sig.score ?? 0) * 10, 100)}%` }}
              />
            </div>
            <span className="font-mono-data text-slate-300 w-8 text-right">{formatScore(sig.score ?? 0)}</span>
          </div>
        ))}
      </div>
      {rec.invalidation && (
        <p className="text-xs text-red-400/80 mt-2">Invalidation: {rec.invalidation}</p>
      )}
    </div>
  );
}
