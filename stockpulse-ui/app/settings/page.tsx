"use client";

import { useState, useCallback } from "react";
import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import type { ScanStatus } from "@/lib/types";

interface ConfigData {
  watchlist: string[];
  strategy: {
    weights: Record<string, number>;
    thresholds: Record<string, number>;
  };
  scheduler: {
    status: string;
    scan_times: string[];
  };
}

export default function SettingsPage() {
  const { data: config, loading, error, refresh } = usePolling<ConfigData>(api.config, 60000);
  const { data: scanStatus, refresh: refreshScan } = usePolling<ScanStatus>(api.scanStatus, 5000);
  const [addTicker, setAddTicker] = useState("");
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  const handleAdd = useCallback(async () => {
    const t = addTicker.trim().toUpperCase();
    if (!t) return;
    setAdding(true);
    try {
      await api.addToWatchlist(t);
      setAddTicker("");
      refresh();
    } catch {
      // silently fail
    } finally {
      setAdding(false);
    }
  }, [addTicker, refresh]);

  const handleRemove = useCallback(async (ticker: string) => {
    setRemoving(ticker);
    try {
      await api.removeFromWatchlist(ticker);
      refresh();
    } catch {
      // silently fail
    } finally {
      setRemoving(null);
    }
  }, [refresh]);

  const handleScan = useCallback(async () => {
    setScanning(true);
    try {
      await api.triggerScan();
      refreshScan();
    } catch {
      // silently fail
    } finally {
      setScanning(false);
    }
  }, [refreshScan]);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <div className="glass-card p-6 animate-pulse">
          <div className="h-32 bg-slate-700/20 rounded" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <div className="glass-card p-6 text-red-400">Failed to load settings: {error}</div>
      </div>
    );
  }

  const watchlist = config?.watchlist ?? [];
  const weights = config?.strategy?.weights ?? {};
  const thresholds = config?.strategy?.thresholds ?? {};
  const maxWeight = Math.max(...Object.values(weights).map((w) => w ?? 0), 1);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Settings</h1>

      {/* Watchlist management */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Watchlist Tickers</h2>
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
            {watchlist.map((ticker) => (
              <div
                key={ticker}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800/40 border border-slate-700/30 text-sm"
              >
                <span className="font-semibold">{ticker}</span>
                <button
                  onClick={() => handleRemove(ticker)}
                  disabled={removing === ticker}
                  className="text-slate-500 hover:text-red-400 transition-colors ml-1"
                  aria-label={`Remove ${ticker}`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Strategy viewer */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Signal Weights</h2>
        {Object.keys(weights).length === 0 ? (
          <p className="text-sm text-slate-500">No strategy data available</p>
        ) : (
          <div className="space-y-2">
            {Object.entries(weights)
              .sort(([, a], [, b]) => b - a)
              .map(([name, weight]) => (
                <div key={name} className="flex items-center gap-3">
                  <span className="text-xs text-slate-400 w-36 truncate text-right">{name}</span>
                  <div className="flex-1 h-2 bg-slate-700/30 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500"
                      style={{ width: `${((weight ?? 0) / maxWeight) * 100}%` }}
                    />
                  </div>
                  <span className="font-mono-data text-xs text-slate-300 w-10 text-right">{weight != null ? weight.toFixed(2) : "--"}</span>
                </div>
              ))}
          </div>
        )}

        {Object.keys(thresholds).length > 0 && (
          <>
            <Separator className="my-4 bg-slate-700/50" />
            <h3 className="text-xs text-slate-400 uppercase tracking-wider mb-3">Thresholds</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {Object.entries(thresholds).map(([name, val]) => (
                <div key={name} className="flex justify-between text-xs">
                  <span className="text-slate-400">{name}</span>
                  <span className="font-mono-data text-slate-300">{typeof val === "number" ? val.toFixed(2) : String(val)}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Scan controls */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">Scan Controls</h2>
        <div className="flex items-center gap-4">
          <Button
            onClick={handleScan}
            disabled={scanning || scanStatus?.running}
            className="h-10"
          >
            {scanning || scanStatus?.running ? "Scanning..." : "Run Full Scan"}
          </Button>
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <div
              className={cn(
                "w-2 h-2 rounded-full",
                scanStatus?.running ? "bg-blue-500 pulse-scan" : "bg-green-500"
              )}
            />
            <span>{scanStatus?.running ? scanStatus.progress || "In progress" : "Idle"}</span>
          </div>
        </div>
        {scanStatus && (
          <div className="mt-3 text-xs text-slate-500 space-y-0.5">
            {scanStatus.last_completed && (
              <p>Last completed: <span className="font-mono-data">{scanStatus.last_completed}</span></p>
            )}
            {scanStatus.next_scheduled && (
              <p>Next scheduled: <span className="font-mono-data">{scanStatus.next_scheduled}</span></p>
            )}
          </div>
        )}
      </div>

      {/* System info */}
      <div className="glass-card p-6">
        <h2 className="text-sm font-semibold text-slate-300 mb-4">System Info</h2>
        <div className="text-sm text-slate-400 space-y-1">
          <p>
            Scheduler: <span className="text-slate-300">{config?.scheduler?.status ?? "Unknown"}</span>
          </p>
          {config?.scheduler?.scan_times && config.scheduler.scan_times.length > 0 && (
            <p>
              Scan times: <span className="font-mono-data text-slate-300">{config.scheduler.scan_times.join(", ")}</span>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
