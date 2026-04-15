"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { actionBadgeClass, formatPnl, cn } from "@/lib/utils";
import { TickerLink } from "@/components/ticker-link";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

function suggestionClass(suggestion: string): string {
  if (suggestion === "HOLD") return "bg-slate-500/10 text-slate-400";
  if (suggestion === "REVIEW") return "bg-orange-500/10 text-orange-400";
  if (suggestion === "CONSIDER TRIMMING") return "bg-red-500/10 text-red-400";
  return "bg-blue-500/10 text-blue-400"; // MONITOR
}

export default function AllocatePage() {
  const [amountInput, setAmountInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [tickerInput, setTickerInput] = useState("");
  const [selectedTickers, setSelectedTickers] = useState<string[]>([]);

  function addTicker() {
    const t = tickerInput.trim().toUpperCase();
    if (t && !selectedTickers.includes(t)) {
      setSelectedTickers([...selectedTickers, t]);
    }
    setTickerInput("");
  }

  async function handleGenerate() {
    const amount = parseFloat(amountInput.replace(/,/g, ""));
    if (!amount || amount <= 0) {
      setError("Please enter a positive investment amount.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.allocate(amount, selectedTickers.length > 0 ? selectedTickers : undefined);
      setResult(data);
    } catch (e: any) {
      setError(e?.message || "Failed to generate allocation plan.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Portfolio Allocation Advisor</h1>
      </div>

      {/* Input card */}
      <div className="glass-card p-6 space-y-4">
        <p className="text-sm text-slate-400">
          Enter an investment amount and optionally select specific tickers. Leave tickers empty to auto-select from top signals.
        </p>
        <div className="flex items-center gap-3 max-w-sm">
          <div className="relative flex-1">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">$</span>
            <Input
              className="pl-7 bg-slate-800/60 border-slate-700/50 text-slate-100 placeholder:text-slate-600 focus-visible:ring-blue-500/30"
              placeholder="10,000"
              value={amountInput}
              onChange={(e) => setAmountInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleGenerate()}
              disabled={loading}
            />
          </div>
          <Button
            onClick={handleGenerate}
            disabled={loading || !amountInput}
            className="bg-blue-600 hover:bg-blue-500 text-white font-medium px-5"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Generating...
              </span>
            ) : (
              "Generate Plan"
            )}
          </Button>
        </div>

        {/* Optional: select specific tickers */}
        <div>
          <p className="text-xs text-slate-500 mb-2">Specific tickers (optional — leave empty for auto-selection)</p>
          <div className="flex items-center gap-2">
            <Input
              className="w-28 bg-slate-800/60 border-slate-700/50 text-sm"
              placeholder="AAPL"
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addTicker(); } }}
            />
            <Button variant="outline" size="sm" onClick={addTicker} className="border-slate-700 text-xs">Add</Button>
            {selectedTickers.length > 0 && (
              <Button variant="outline" size="sm" onClick={() => setSelectedTickers([])} className="border-slate-700 text-xs text-slate-500">Clear all</Button>
            )}
          </div>
          {selectedTickers.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {selectedTickers.map((t) => (
                <span key={t} className="flex items-center gap-1 px-2 py-1 rounded-md bg-blue-500/10 text-blue-400 text-xs border border-blue-500/20">
                  {t}
                  <button onClick={() => setSelectedTickers(selectedTickers.filter(x => x !== t))} className="hover:text-red-400 ml-0.5">
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
        {error && <p className="text-sm text-red-400">{error}</p>}
      </div>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="glass-card p-6 animate-pulse space-y-3">
              <div className="h-4 bg-slate-700/50 rounded w-40" />
              <div className="h-8 bg-slate-700/50 rounded w-full" />
              <div className="h-4 bg-slate-700/50 rounded w-2/3" />
            </div>
          ))}
        </div>
      )}

      {result && !loading && (
        <div className="space-y-6">
          {/* LLM Rationale */}
          {result.rationale && (
            <div className="glass-card p-5 border-l-4 border-blue-500/60">
              <p className="text-xs text-blue-400 uppercase tracking-wider font-medium mb-2">Advisor Rationale</p>
              <p className="text-sm text-slate-300 leading-relaxed">{result.rationale}</p>
            </div>
          )}

          {/* Summary cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <div className="glass-card p-5">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Investing</p>
              <p className="text-2xl font-bold font-mono-data text-slate-200">
                ${result.amount?.toLocaleString("en-US", { minimumFractionDigits: 0 })}
              </p>
            </div>
            <div className="glass-card p-5">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Cash Reserve</p>
              <p className="text-2xl font-bold font-mono-data text-blue-400">
                ${result.cash_reserve?.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">{result.cash_reserve_pct?.toFixed(1)}% of amount</p>
            </div>
            <div className="glass-card p-5">
              <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Portfolio After</p>
              <p className="text-2xl font-bold font-mono-data text-green-400">
                ${result.total_portfolio_after?.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>

          {/* Suggested allocations */}
          {result.allocations && result.allocations.length > 0 && (
            <div className="rounded-xl border border-slate-700/50 bg-slate-900/60">
              <div className="px-5 py-4 border-b border-slate-700/50">
                <h2 className="text-sm font-semibold text-slate-300">
                  Suggested Allocations
                  <span className="ml-2 text-xs text-slate-500 font-normal">
                    {result.allocations.length} position{result.allocations.length !== 1 ? "s" : ""}
                  </span>
                </h2>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-700/50 hover:bg-transparent">
                    <TableHead className="text-slate-400 text-xs">Ticker</TableHead>
                    <TableHead className="text-slate-400 text-xs">Action</TableHead>
                    <TableHead className="text-slate-400 text-xs">Type</TableHead>
                    <TableHead className="text-slate-400 text-xs text-right">Score</TableHead>
                    <TableHead className="text-slate-400 text-xs text-right">Amount</TableHead>
                    <TableHead className="text-slate-400 text-xs text-right">% of Total</TableHead>
                    <TableHead className="text-slate-400 text-xs">Sector</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.allocations.map((alloc: any) => (
                    <TableRow key={alloc.ticker} className="border-slate-700/30 hover:bg-slate-800/30">
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <TickerLink ticker={alloc.ticker} />
                          {alloc.already_held && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700/60 text-slate-400">held</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium", actionBadgeClass(alloc.action))}>
                          {alloc.action}
                        </span>
                      </TableCell>
                      <TableCell>
                        {alloc.position_type === "starter" ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-blue-500/15 text-blue-400 border border-blue-500/25">
                            Starter 33%
                          </span>
                        ) : alloc.position_type === "full" ? (
                          <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-green-500/15 text-green-400 border border-green-500/25">
                            Full
                          </span>
                        ) : (
                          <span className="text-xs text-slate-600">—</span>
                        )}
                      </TableCell>
                      <TableCell className={cn(
                        "font-mono-data text-right text-xs",
                        alloc.score >= 0 ? "text-green-400" : "text-red-400"
                      )}>
                        {alloc.score >= 0 ? "+" : ""}{alloc.score}
                      </TableCell>
                      <TableCell className="font-mono-data text-right text-xs text-slate-200 font-semibold">
                        ${alloc.suggested_amount?.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className="font-mono-data text-right text-xs text-slate-400">
                        {alloc.suggested_pct?.toFixed(1)}%
                      </TableCell>
                      <TableCell className="text-xs text-slate-500">
                        {alloc.sector || "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {result.allocations?.length === 0 && (
            <div className="glass-card p-8 text-center text-slate-500 text-sm">
              No allocation candidates found. Run a scan to populate signal data.
            </div>
          )}

          {/* Current holdings analysis */}
          {result.current_holdings && result.current_holdings.length > 0 && (
            <div className="rounded-xl border border-slate-700/50 bg-slate-900/60">
              <div className="px-5 py-4 border-b border-slate-700/50">
                <h2 className="text-sm font-semibold text-slate-300">Current Holdings Analysis</h2>
              </div>
              <Table>
                <TableHeader>
                  <TableRow className="border-slate-700/50 hover:bg-transparent">
                    <TableHead className="text-slate-400 text-xs">Ticker</TableHead>
                    <TableHead className="text-slate-400 text-xs text-right">Current Value</TableHead>
                    <TableHead className="text-slate-400 text-xs text-right">P&L %</TableHead>
                    <TableHead className="text-slate-400 text-xs">Signal</TableHead>
                    <TableHead className="text-slate-400 text-xs">Suggestion</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.current_holdings.map((h: any) => (
                    <TableRow key={h.ticker} className="border-slate-700/30 hover:bg-slate-800/30">
                      <TableCell>
                        <TickerLink ticker={h.ticker} />
                      </TableCell>
                      <TableCell className="font-mono-data text-right text-xs text-slate-300">
                        ${h.current_value?.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                      </TableCell>
                      <TableCell className={cn(
                        "font-mono-data text-right text-xs",
                        h.pnl_pct >= 0 ? "text-green-400" : "text-red-400"
                      )}>
                        {h.pnl_pct >= 0 ? "+" : ""}{h.pnl_pct?.toFixed(2)}%
                      </TableCell>
                      <TableCell>
                        <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium", actionBadgeClass(h.signal))}>
                          {h.signal}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className={cn("px-2 py-0.5 rounded text-[11px] font-medium", suggestionClass(h.suggestion))}>
                          {h.suggestion}
                        </span>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
