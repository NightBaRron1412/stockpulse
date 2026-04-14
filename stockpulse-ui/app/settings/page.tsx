"use client";

import { useState, useCallback } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { getSignalLabel, getSignalDescription, getThresholdLabel, getThresholdDescription, getRiskLabel, getRiskDescription, getScheduleLabel, getScheduleDescription } from "@/lib/signal-labels";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import type { ScanStatus } from "@/lib/types";

export default function SettingsPage() {
  const { data: config, loading, error, refresh } = usePolling<any>(api.config, 60000);
  const { data: scanStatus, refresh: refreshScan } = usePolling<ScanStatus>(api.scanStatus, 5000);
  const [addTicker, setAddTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [btStartDate, setBtStartDate] = useState("2025-07-01");
  const [btEndDate, setBtEndDate] = useState("2026-01-01");
  const [backtesting, setBacktesting] = useState(false);
  const [btStatus, setBtStatus] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [editedThresholds, setEditedThresholds] = useState<Record<string, string> | null>(null);
  const [editedRisk, setEditedRisk] = useState<Record<string, string> | null>(null);
  const [editingThresholds, setEditingThresholds] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState(false);
  const [editedSchedule, setEditedSchedule] = useState<Record<string, string> | null>(null);
  const [editingRisk, setEditingRisk] = useState(false);

  const handleAdd = useCallback(async () => {
    const t = addTicker.trim().toUpperCase();
    if (!t) return;
    setAdding(true);
    try { await api.addToWatchlist(t); setAddTicker(""); refresh(); } finally { setAdding(false); }
  }, [addTicker, refresh]);

  const handleRemove = useCallback(async (ticker: string) => {
    setRemoving(ticker);
    try { await api.removeFromWatchlist(ticker); refresh(); } finally { setRemoving(null); }
  }, [refresh]);

  const handleScan = useCallback(async () => {
    setScanning(true);
    try { await api.triggerScan(); refreshScan(); } finally { setScanning(false); }
  }, [refreshScan]);

  const handleSaveConfig = useCallback(async () => {
    setSaving(true);
    try {
      const update: any = {};
      if (editedThresholds) {
        update.thresholds = {};
        for (const [k, v] of Object.entries(editedThresholds)) {
          update.thresholds[k] = Number(v);
        }
      }
      if (editedRisk) {
        update.risk = {};
        for (const [k, v] of Object.entries(editedRisk)) {
          update.risk[k] = Number(v);
        }
      }
      if (editedSchedule) {
        update.scheduling = {};
        for (const [k, v] of Object.entries(editedSchedule)) {
          const num = Number(v);
          update.scheduling[k] = isNaN(num) ? v : num;
        }
      }
      await api.updateConfig(update);
      setEditedThresholds(null);
      setEditedRisk(null);
      setEditedSchedule(null);
      refresh();
    } finally { setSaving(false); }
  }, [editedThresholds, editedRisk, refresh]);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <div className="glass-card p-6 animate-pulse"><div className="h-32 bg-slate-700/20 rounded" /></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <div className="glass-card p-6 text-red-400">Failed to load: {error}</div>
      </div>
    );
  }

  const watchlist = config?.watchlist ?? [];
  const discovered = config?.discovered ?? [];
  const weights = config?.weights ?? {};
  const thresholds = config?.thresholds ?? {};
  const risk = config?.risk ?? {};
  const scheduling = config?.scheduling ?? {};
  const maxWeight = Math.max(...Object.values(weights).map((w: any) => Number(w) || 0), 0.01);

  const currentThresholds = editedThresholds ?? Object.fromEntries(
    Object.entries(thresholds).map(([k, v]) => [k, String(v)])
  );
  const currentRisk = editedRisk ?? Object.fromEntries(
    Object.entries(risk).map(([k, v]) => [k, String(v)])
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Settings</h1>
      </div>

      {/* Watchlist management */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">User Watchlist</h2>
        <div className="flex items-center gap-2 mb-4">
          <Input
            value={addTicker}
            onChange={(e) => setAddTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            placeholder="Add ticker..."
            className="w-40 bg-slate-800/50 border-slate-700/50 h-9 text-sm"
          />
          <Button onClick={handleAdd} disabled={adding} size="sm" className="h-9">
            {adding ? "Adding..." : "Add"}
          </Button>
        </div>
        {watchlist.length === 0 ? (
          <p className="text-sm text-slate-500">No tickers in watchlist</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {watchlist.map((ticker: string) => (
              <div key={ticker} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/40 border border-slate-700/30 text-sm">
                <span className="font-semibold">{ticker}</span>
                <button
                  onClick={() => handleRemove(ticker)}
                  disabled={removing === ticker}
                  className="p-0.5 rounded hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-colors cursor-pointer ml-1"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}

        {discovered.length > 0 && (
          <>
            <Separator className="my-4 bg-slate-700/50" />
            <h3 className="text-xs text-slate-400 uppercase tracking-wider mb-3">
              Auto-Discovered ({discovered.length})
            </h3>
            <div className="flex flex-wrap gap-2">
              {discovered.map((ticker: string) => (
                <div key={ticker} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-950/30 border border-blue-800/20 text-sm">
                  <span className="text-blue-300">{ticker}</span>
                  <button
                    onClick={() => handleRemove(ticker)}
                    disabled={removing === ticker}
                    className="p-0.5 rounded hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-colors cursor-pointer ml-1"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Signal Weights (read-only) */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-300">Signal Weights</h2>
          <span className="text-[10px] text-slate-600 uppercase">Read-only</span>
        </div>
        {Object.keys(weights).length === 0 ? (
          <p className="text-sm text-slate-500">No strategy data available</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(weights)
              .sort(([, a]: any, [, b]: any) => (b ?? 0) - (a ?? 0))
              .map(([name, weight]: [string, any]) => (
                <div key={name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-36 truncate text-right cursor-help" title={getSignalDescription(name)}>{getSignalLabel(name)}</span>
                  <div className="flex-1 h-2 bg-slate-700/30 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500"
                      style={{ width: `${((Number(weight) || 0) / maxWeight) * 100}%` }}
                    />
                  </div>
                  <span className="font-mono-data text-xs text-slate-300 w-10 text-right">
                    {weight != null ? Number(weight).toFixed(2) : "--"}
                  </span>
                </div>
              ))}
          </div>
        )}
      </div>

      {/* Thresholds (editable) */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-300">Thresholds</h2>
          {!editingThresholds ? (
            <Button variant="outline" size="sm" onClick={() => { setEditingThresholds(true); setEditedThresholds({...currentThresholds}); }} className="h-7 text-xs border-slate-700">Edit</Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => { setEditingThresholds(false); setEditedThresholds(null); }} className="h-7 text-xs border-slate-700">Cancel</Button>
              <Button size="sm" onClick={() => { handleSaveConfig(); setEditingThresholds(false); }} disabled={saving} className="h-7 text-xs">Save</Button>
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Object.entries(currentThresholds).map(([name, val]) => (
            <div key={name} className="space-y-1">
              <p className="cursor-help text-xs text-slate-400" title={getThresholdDescription(name)}>{getThresholdLabel(name)}</p>
              {editingThresholds ? (
                <Input value={val} onChange={(e) => setEditedThresholds({...currentThresholds, [name]: e.target.value})} className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-20" />
              ) : (
                <p className="font-mono-data text-slate-200 text-sm">{val}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Risk Limits (editable) */}
      <div className="glass-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-300">Risk Limits</h2>
          {!editingRisk ? (
            <Button variant="outline" size="sm" onClick={() => { setEditingRisk(true); setEditedRisk({...currentRisk}); }} className="h-7 text-xs border-slate-700">Edit</Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => { setEditingRisk(false); setEditedRisk(null); }} className="h-7 text-xs border-slate-700">Cancel</Button>
              <Button size="sm" onClick={() => { handleSaveConfig(); setEditingRisk(false); }} disabled={saving} className="h-7 text-xs">Save</Button>
            </div>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {Object.entries(currentRisk).map(([name, val]) => (
            <div key={name} className="space-y-1">
              <p className="cursor-help text-xs text-slate-400" title={getRiskDescription(name)}>{getRiskLabel(name)}</p>
              {editingRisk ? (
                <Input value={val} onChange={(e) => setEditedRisk({...currentRisk, [name]: e.target.value})} className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-20" />
              ) : (
                <p className="font-mono-data text-slate-200 text-sm">{val}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Scan controls */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Scan Controls</h2>
        <div className="flex items-center gap-4">
          <Button onClick={handleScan} disabled={scanning || scanStatus?.running} className="h-10">
            {scanning || scanStatus?.running ? "Scanning..." : "Run Full Scan"}
          </Button>
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <div className={cn("w-2 h-2 rounded-full", scanStatus?.running ? "bg-blue-500 pulse-scan" : "bg-green-500")} />
            <span>{scanStatus?.running ? scanStatus.progress || "In progress" : "Idle"}</span>
          </div>
        </div>
        {scanStatus && (
          <div className="mt-3 text-xs text-slate-500 space-y-0.5">
            <p>Last completed: <span className="font-mono-data">{scanStatus.last_completed ?? "Never"}</span></p>
            <p>Next scheduled: <span className="font-mono-data">{scanStatus.next_scheduled ?? "--"}</span></p>
          </div>
        )}
      </div>

      {/* Backtesting */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Backtesting</h2>
        <div className="flex items-center gap-3 mb-3">
          <div className="space-y-1">
            <p className="text-xs text-slate-400">Start Date</p>
            <Input
              type="date"
              value={btStartDate}
              onChange={(e) => setBtStartDate(e.target.value)}
              className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-36"
            />
          </div>
          <div className="space-y-1">
            <p className="text-xs text-slate-400">End Date</p>
            <Input
              type="date"
              value={btEndDate}
              onChange={(e) => setBtEndDate(e.target.value)}
              className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-36"
            />
          </div>
          <div className="space-y-1">
            <p className="text-xs text-slate-400">&nbsp;</p>
            <Button
              onClick={async () => {
                setBacktesting(true);
                setBtStatus({ running: true, progress: "Starting..." });
                try {
                  await api.triggerBacktest(btStartDate, btEndDate);
                  // Poll for completion
                  const poll = setInterval(async () => {
                    const s = await api.backtestStatus();
                    setBtStatus(s);
                    if (!s.running) {
                      clearInterval(poll);
                      setBacktesting(false);
                    }
                  }, 3000);
                } catch {
                  setBacktesting(false);
                  setBtStatus({ running: false, error: "Failed to start backtest" });
                }
              }}
              disabled={backtesting}
              className="h-8"
            >
              {backtesting ? "Running..." : "Run Backtest"}
            </Button>
          </div>
        </div>

        {btStatus && (
          <div className="mt-3 text-xs space-y-1">
            {btStatus.running && (
              <div className="flex items-center gap-2 text-blue-400">
                <div className="w-2 h-2 rounded-full bg-blue-500 pulse-scan" />
                <span className="font-mono-data">{btStatus.progress}</span>
              </div>
            )}
            {btStatus.error && (
              <p className="text-red-400">Error: {btStatus.error}</p>
            )}
            {btStatus.result?.completed && (
              <div className="space-y-2">
                <p className="text-green-400">Backtest completed ({btStatus.result.start_date} to {btStatus.result.end_date})</p>
                {btStatus.result.tearsheet && (
                  <a
                    href={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:18000"}/api/backtest/tearsheet`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                  >
                    View Tearsheet →
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        <p className="mt-3 text-[11px] text-slate-600">
          Runs MomentumCatalyst strategy on your watchlist tickers. Uses historical data only (no live API calls). Results include Sharpe ratio, max drawdown, and trade log.
        </p>
      </div>

      {/* Schedule */}
      {Object.keys(scheduling).length > 0 && (() => {
        const currentSchedule = editedSchedule ?? Object.fromEntries(
          Object.entries(scheduling).map(([k, v]) => [k, String(v)])
        );
        return (
          <div className="glass-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold text-slate-300">Schedule</h2>
              {!editingSchedule ? (
                <Button variant="outline" size="sm" onClick={() => { setEditingSchedule(true); setEditedSchedule({...currentSchedule}); }} className="h-7 text-xs border-slate-700">Edit</Button>
              ) : (
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => { setEditingSchedule(false); setEditedSchedule(null); }} className="h-7 text-xs border-slate-700">Cancel</Button>
                  <Button size="sm" onClick={() => { handleSaveConfig(); setEditingSchedule(false); }} disabled={saving} className="h-7 text-xs">Save</Button>
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
              {Object.entries(currentSchedule).map(([name, val]) => (
                <div key={name} className="space-y-1">
                  <p className="cursor-help text-xs text-slate-400" title={getScheduleDescription(name)}>{getScheduleLabel(name)}</p>
                  {editingSchedule ? (
                    <Input value={val} onChange={(e) => setEditedSchedule({...currentSchedule, [name]: e.target.value})} className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-24" />
                  ) : (
                    <p className="font-mono-data text-slate-200 text-sm">{val}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
