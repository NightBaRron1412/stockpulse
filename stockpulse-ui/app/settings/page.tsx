"use client";

import { useState, useCallback } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { getSignalLabel, getThresholdLabel, getThresholdDescription, getRiskLabel, getRiskDescription } from "@/lib/signal-labels";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { ScanStatus } from "@/lib/types";

export default function SettingsPage() {
  const { data: config, loading, error, refresh } = usePolling<any>(api.config, 60000);
  const { data: scanStatus, refresh: refreshScan } = usePolling<ScanStatus>(api.scanStatus, 5000);
  const [addTicker, setAddTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editedThresholds, setEditedThresholds] = useState<Record<string, string> | null>(null);
  const [editedRisk, setEditedRisk] = useState<Record<string, string> | null>(null);
  const [editingThresholds, setEditingThresholds] = useState(false);
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
      await api.updateConfig(update);
      setEditedThresholds(null);
      setEditedRisk(null);
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
                  <span className="text-xs text-slate-400 w-36 truncate text-right">{getSignalLabel(name)}</span>
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
              <Tooltip>
                <TooltipTrigger className="cursor-help text-xs text-slate-400">{getThresholdLabel(name)}</TooltipTrigger>
                <TooltipContent className="max-w-[250px] bg-slate-800 border-slate-700"><p className="text-xs">{getThresholdDescription(name)}</p></TooltipContent>
              </Tooltip>
              {editingThresholds ? (
                <Input value={val} onChange={(e) => setEditedThresholds({...currentThresholds, [name]: e.target.value})} className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-20" />
              ) : (
                <span className="font-mono-data text-slate-300">{val}</span>
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
              <Tooltip>
                <TooltipTrigger className="cursor-help text-xs text-slate-400">{getRiskLabel(name)}</TooltipTrigger>
                <TooltipContent className="max-w-[250px] bg-slate-800 border-slate-700"><p className="text-xs">{getRiskDescription(name)}</p></TooltipContent>
              </Tooltip>
              {editingRisk ? (
                <Input value={val} onChange={(e) => setEditedRisk({...currentRisk, [name]: e.target.value})} className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-20" />
              ) : (
                <span className="font-mono-data text-slate-300">{val}</span>
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

      {/* Schedule (read-only) */}
      {Object.keys(scheduling).length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-300">Schedule</h2>
            <span className="text-[10px] text-slate-600 uppercase">Read-only</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {Object.entries(scheduling).map(([name, val]: [string, any]) => (
              <div key={name} className="flex justify-between text-xs">
                <span className="text-slate-400">{name.replace(/_/g, " ")}</span>
                <span className="font-mono-data text-slate-300">{String(val)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
