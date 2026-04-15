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
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { Portfolio } from "@/lib/types";
import { useState } from "react";
import { TickerLink } from "@/components/ticker-link";

export default function PortfolioPage() {
  const { data, loading, error, refresh } = usePolling<any>(api.portfolio, 30000);
  const [sortKey, setSortKey] = useState<string>("pnl_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [cashInput, setCashInput] = useState("");
  const [savingCash, setSavingCash] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addTicker, setAddTicker] = useState("");
  const [addShares, setAddShares] = useState("");
  const [addPrice, setAddPrice] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingRow, setEditingRow] = useState<string | null>(null);
  const [editShares, setEditShares] = useState("");
  const [editPrice, setEditPrice] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === "desc" ? "asc" : "desc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const pageHeader = (
    <div className="flex items-center justify-between">
      <h1 className="text-2xl font-semibold">Portfolio</h1>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => setShowImport(true)}
          className="border-slate-700 text-xs">Import from Wealthsimple</Button>
        <Button variant="outline" size="sm" onClick={() => setShowAdd(true)}
          className="border-slate-700 text-xs">Add Position</Button>
        <a href="/allocate" className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors">
          Allocate →
        </a>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="space-y-6">
        {pageHeader}
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
        {pageHeader}
        <div className="glass-card p-6 text-red-400">Failed to load portfolio: {error}</div>
      </div>
    );
  }

  if (!data || !data.positions || data.positions.length === 0) {
    return (
      <div className="space-y-6">
        {pageHeader}
        <div className="glass-card p-8 text-center text-slate-500">
          No positions yet -- portfolio tracking will appear after you add trades
        </div>
      </div>
    );
  }

  const drawdownPct = data.drawdown?.drawdown_pct ?? 0;
  const cash = data.cash ?? 0;
  const totalPortfolio = (data.total_current ?? 0) + cash;

  return (
    <div className="space-y-6">
      {pageHeader}

      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Total Portfolio</p>
          <p className="text-2xl font-bold font-mono-data text-blue-400">
            ${totalPortfolio.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">positions + cash</p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Positions Value</p>
          <p className="text-2xl font-bold font-mono-data text-slate-200">
            ${(data.total_current ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </p>
        </div>
        <div className="glass-card p-5">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Cash Reserve</p>
          <div className="flex items-center gap-2">
            <p className="text-2xl font-bold font-mono-data text-green-400">
              ${cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </p>
          </div>
          {totalPortfolio > 0 && (
            <p className="text-xs text-slate-500 mt-0.5">{((cash / totalPortfolio) * 100).toFixed(1)}% of portfolio</p>
          )}
          <div className="flex items-center gap-1.5 mt-2">
            <div className="relative flex-1">
              <span className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500 text-[10px]">$</span>
              <Input
                className="pl-4 h-7 text-xs bg-slate-800/50 border-slate-700/50 font-mono-data"
                placeholder={cash.toFixed(0)}
                value={cashInput}
                onChange={(e) => setCashInput(e.target.value)}
                type="number"
                min={0}
                step={100}
              />
            </div>
            <Button size="sm" className="h-7 text-[10px] px-2" disabled={savingCash} onClick={async () => {
              const val = parseFloat(cashInput.replace(/,/g, ""));
              if (!isNaN(val) && val >= 0) {
                setSavingCash(true);
                try {
                  await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000"}/api/portfolio/cash`, {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ cash: val }),
                  });
                  setCashInput("");
                  refresh();
                } finally { setSavingCash(false); }
              }
            }}>Set</Button>
          </div>
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
              <TableHead className="text-slate-400 text-xs w-20"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {[...data.positions].sort((a: any, b: any) => {
              const av = a[sortKey] ?? 0;
              const bv = b[sortKey] ?? 0;
              if (typeof av === "string") return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
              return sortDir === "asc" ? av - bv : bv - av;
            }).map((pos) => (
              <TableRow key={pos.ticker} className="border-slate-700/30 hover:bg-slate-800/30 group">
                <TableCell><TickerLink ticker={pos.ticker} /></TableCell>
                <TableCell className="font-mono-data text-right text-xs">
                  {editingRow === pos.ticker ? (
                    <Input type="number" step="0.001" value={editShares} onChange={(e) => setEditShares(e.target.value)}
                      className="w-20 h-6 text-xs bg-slate-800/50 border-slate-700/50" />
                  ) : pos.shares}
                </TableCell>
                <TableCell className="font-mono-data text-right text-xs">
                  {editingRow === pos.ticker ? (
                    <Input type="number" step="0.01" value={editPrice} onChange={(e) => setEditPrice(e.target.value)}
                      className="w-20 h-6 text-xs bg-slate-800/50 border-slate-700/50" />
                  ) : pos.entry_price != null ? `$${pos.entry_price.toFixed(2)}` : "--"}
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
                <TableCell className="text-right">
                  {editingRow === pos.ticker ? (
                    <div className="flex gap-1 justify-end">
                      <Button size="sm" className="h-6 text-[10px] px-2 bg-blue-600" disabled={saving} onClick={async () => {
                        setSaving(true);
                        try {
                          await api.upsertPosition(pos.ticker, parseFloat(editShares), parseFloat(editPrice));
                          setEditingRow(null);
                          refresh();
                        } finally { setSaving(false); }
                      }}>Save</Button>
                      <Button variant="ghost" size="sm" className="h-6 text-[10px] px-1" onClick={() => setEditingRow(null)}>X</Button>
                    </div>
                  ) : (
                    <div className="flex gap-2 justify-end">
                      <button onClick={() => { setEditingRow(pos.ticker); setEditShares(String(pos.shares)); setEditPrice(String(pos.entry_price)); }}
                        className="px-2 py-0.5 rounded text-[11px] text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors">Edit</button>
                      <button onClick={async () => {
                        if (!confirm(`Delete ${pos.ticker}?`)) return;
                        setDeleting(pos.ticker);
                        try { await api.deletePosition(pos.ticker); refresh(); } finally { setDeleting(null); }
                      }} className="px-2 py-0.5 rounded text-[11px] text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors">{deleting === pos.ticker ? "..." : "Del"}</button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Import Modal */}
      {showImport && (
        <>
          <div className="fixed inset-0 z-40 bg-black/60" onClick={() => setShowImport(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="glass-card p-6 w-full max-w-lg space-y-4">
              <h2 className="text-lg font-semibold text-slate-200">Import from Wealthsimple</h2>
              <p className="text-xs text-slate-400">Paste your portfolio text from Wealthsimple. This will replace all current positions.</p>
              <textarea
                value={importText}
                onChange={(e) => setImportText(e.target.value)}
                placeholder="Paste portfolio text here..."
                className="w-full h-48 bg-slate-800/50 border border-slate-700/50 rounded-lg p-3 text-xs text-slate-200 font-mono-data resize-none"
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowImport(false)} className="border-slate-700 text-xs">Cancel</Button>
                <Button size="sm" disabled={importing || !importText.trim()} className="bg-blue-600 text-white text-xs" onClick={async () => {
                  setImporting(true);
                  try {
                    const result = await api.importPortfolio(importText);
                    setShowImport(false);
                    setImportText("");
                    refresh();
                    alert(`Imported ${result.positions} positions: ${result.tickers.join(", ")}`);
                  } catch (e: any) {
                    alert(`Import failed: ${e.message}`);
                  } finally { setImporting(false); }
                }}>{importing ? "Importing..." : "Import & Replace"}</Button>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Add Position Modal */}
      {showAdd && (
        <>
          <div className="fixed inset-0 z-40 bg-black/60" onClick={() => setShowAdd(false)} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <div className="glass-card p-6 w-full max-w-sm space-y-4">
              <h2 className="text-lg font-semibold text-slate-200">Add Position</h2>
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">Ticker</label>
                  <Input value={addTicker} onChange={(e) => setAddTicker(e.target.value.toUpperCase())}
                    placeholder="AAPL" className="bg-slate-800/50 border-slate-700/50 h-9 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">Shares</label>
                  <Input type="number" step="0.001" value={addShares} onChange={(e) => setAddShares(e.target.value)}
                    placeholder="10" className="bg-slate-800/50 border-slate-700/50 h-9 text-sm" />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">Entry Price</label>
                  <Input type="number" step="0.01" value={addPrice} onChange={(e) => setAddPrice(e.target.value)}
                    placeholder="150.00" className="bg-slate-800/50 border-slate-700/50 h-9 text-sm" />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={() => setShowAdd(false)} className="border-slate-700 text-xs">Cancel</Button>
                <Button size="sm" disabled={saving || !addTicker || !addShares || !addPrice} className="bg-blue-600 text-white text-xs" onClick={async () => {
                  setSaving(true);
                  try {
                    await api.upsertPosition(addTicker, parseFloat(addShares), parseFloat(addPrice));
                    setShowAdd(false);
                    setAddTicker(""); setAddShares(""); setAddPrice("");
                    refresh();
                  } catch (e: any) {
                    alert(`Failed: ${e.message}`);
                  } finally { setSaving(false); }
                }}>{saving ? "Saving..." : "Add"}</Button>
              </div>
            </div>
          </div>
        </>
      )}

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
