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

// ── Input type helpers ────────────────────────────────────────────────────────

const BOOLEAN_KEYS = new Set([
  "watchlist_starter_enabled",
  "max_one_name_per_cluster",
  "add_to_full_only_on_buy_upgrade",
  "never_average_down_watchlist",
]);

const INTEGER_KEYS = new Set([
  "max_positions",
  "max_watchlist_names",
  "drawdown_half",
  "drawdown_pause",
  "earnings_blackout_days",
  "watchlist_exit_score",
  "watchlist_timeout_days",
  "buy",
  "sell",
  "watchlist",
  "watchlist_relaxed",
  "caution",
  "exit",
  "confidence_min",
  "watchlist_starter_min_score",
]);

const FLOAT_KEYS = new Set([
  "max_position_pct",
  "max_sector_pct",
  "risk_per_trade_pct",
  "watchlist_starter_size",
  "watchlist_starter_risk",
  "max_watchlist_sleeve",
]);

type InputKind = "boolean" | "integer" | "float" | "text";

const FIELD_RANGES: Record<string, { min?: number; max?: number }> = {
  watchlist_starter_size: { min: 0.01, max: 1.0 },
  watchlist_starter_risk: { min: 0.05, max: 1.0 },
  max_watchlist_sleeve: { min: 0.01, max: 1.0 },
  max_position_pct: { min: 1, max: 25 },
  max_sector_pct: { min: 5, max: 50 },
  risk_per_trade_pct: { min: 0.1, max: 2.0 },
  max_positions: { min: 1, max: 20 },
  max_watchlist_names: { min: 1, max: 10 },
  drawdown_half: { min: 1, max: 30 },
  drawdown_pause: { min: 5, max: 50 },
  earnings_blackout_days: { min: 0, max: 10 },
  watchlist_exit_score: { min: -100, max: 100 },
  watchlist_timeout_days: { min: 1, max: 30 },
  buy: { min: 10, max: 100 },
  sell: { min: -100, max: -10 },
  watchlist: { min: 10, max: 100 },
  watchlist_relaxed: { min: 5, max: 100 },
  caution: { min: -100, max: 0 },
  exit: { min: -50, max: 50 },
  confidence_min: { min: 0, max: 100 },
  watchlist_starter_min_score: { min: 10, max: 55 },
};

function getInputType(key: string, value: unknown): { kind: InputKind; step?: number; min?: number; max?: number } {
  const range = FIELD_RANGES[key];
  if (
    typeof value === "boolean" ||
    BOOLEAN_KEYS.has(key) ||
    key.includes("enabled") ||
    key.startsWith("never_") ||
    key.startsWith("add_to_") ||
    key.startsWith("max_one_")
  ) {
    return { kind: "boolean" };
  }
  if (INTEGER_KEYS.has(key)) {
    return { kind: "integer", step: 1, min: range?.min, max: range?.max };
  }
  if (FLOAT_KEYS.has(key)) {
    return { kind: "float", step: 0.01, min: range?.min, max: range?.max };
  }
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? { kind: "integer", step: 1, min: range?.min, max: range?.max }
      : { kind: "float", step: 0.01, min: range?.min, max: range?.max };
  }
  return { kind: "text" };
}

function renderEditableField(
  key: string,
  val: string,
  originalValue: unknown,
  onChange: (key: string, val: string) => void
) {
  const { kind, step, min, max } = getInputType(key, originalValue);

  if (kind === "boolean") {
    return (
      <select
        value={val}
        onChange={(e) => onChange(key, e.target.value)}
        className="bg-slate-800/50 border border-slate-700/50 h-8 text-sm font-mono-data rounded-md px-2 text-slate-200 w-20"
      >
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  }

  return (
    <Input
      type="number"
      step={step}
      min={min}
      max={max}
      value={val}
      onChange={(e) => onChange(key, e.target.value)}
      className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-24"
    />
  );
}

function DisplayValue({ name, val, originalValue }: { name: string; val: string; originalValue: unknown }) {
  if (typeof originalValue === "boolean") {
    return (
      <span className={cn("font-mono-data text-sm", originalValue ? "text-green-400" : "text-slate-500")}>
        {originalValue ? "Yes" : "No"}
      </span>
    );
  }
  // Detect boolean-like string values stored as strings
  const { kind } = getInputType(name, originalValue);
  if (kind === "boolean" && (val === "true" || val === "false")) {
    const isTrue = val === "true";
    return (
      <span className={cn("font-mono-data text-sm", isTrue ? "text-green-400" : "text-slate-500")}>
        {isTrue ? "Yes" : "No"}
      </span>
    );
  }
  return <p className="font-mono-data text-slate-200 text-sm">{val}</p>;
}

// ── Component ─────────────────────────────────────────────────────────────────

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
  const { data: btStatusFromApi } = usePolling<any>(api.backtestStatus, 10000);
  const [btStatusLocal, setBtStatusLocal] = useState<any>(null);
  const btStatus = btStatusLocal ?? btStatusFromApi;
  const [saving, setSaving] = useState(false);
  const [editedThresholds, setEditedThresholds] = useState<Record<string, string> | null>(null);
  const [editedRisk, setEditedRisk] = useState<Record<string, string> | null>(null);
  const [editingThresholds, setEditingThresholds] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState(false);
  const [editedSchedule, setEditedSchedule] = useState<Record<string, string> | null>(null);
  const [editingAllocation, setEditingAllocation] = useState(false);
  const [editedAllocation, setEditedAllocation] = useState<Record<string, string> | null>(null);
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
      if (editedAllocation) {
        update.allocation = {};
        for (const [k, v] of Object.entries(editedAllocation)) {
          if (v === "true" || v === "false") update.allocation[k] = v === "true";
          else { const num = Number(v); update.allocation[k] = isNaN(num) ? v : num; }
        }
      }
      await api.updateConfig(update);
      setEditedThresholds(null);
      setEditedRisk(null);
      setEditedSchedule(null);
      setEditedAllocation(null);
      refresh();
    } finally { setSaving(false); }
  }, [editedThresholds, editedRisk, editedSchedule, editedAllocation, refresh]);

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
  const allocation = config?.allocation ?? {};
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
                renderEditableField(name, val, thresholds[name], (key, newVal) =>
                  setEditedThresholds({ ...currentThresholds, [key]: newVal })
                )
              ) : (
                <DisplayValue name={name} val={val} originalValue={thresholds[name]} />
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
                renderEditableField(name, val, risk[name], (key, newVal) =>
                  setEditedRisk({ ...currentRisk, [key]: newVal })
                )
              ) : (
                <DisplayValue name={name} val={val} originalValue={risk[name]} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Allocation Rules */}
      {Object.keys(allocation).length > 0 && (
        <div className="glass-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-300">Allocation Rules</h2>
            {!editingAllocation ? (
              <Button variant="outline" size="sm" onClick={() => {
                const vals: Record<string, string> = {};
                for (const k of ["watchlist_starter_enabled","watchlist_starter_min_score","watchlist_starter_size","watchlist_starter_risk","max_watchlist_sleeve","max_watchlist_names","watchlist_exit_score","watchlist_timeout_days"]) {
                  vals[k] = String(allocation[k] ?? "");
                }
                setEditedAllocation(vals);
                setEditingAllocation(true);
              }} className="h-7 text-xs border-slate-700">Edit</Button>
            ) : (
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={() => { setEditingAllocation(false); setEditedAllocation(null); }} className="h-7 text-xs border-slate-700">Cancel</Button>
                <Button size="sm" onClick={() => { handleSaveConfig(); setEditingAllocation(false); }} disabled={saving} className="h-7 text-xs">Save</Button>
              </div>
            )}
          </div>

          <h3 className="text-xs text-slate-400 uppercase tracking-wider mb-3">Sizing &amp; Limits</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 mb-5">
            {[
              { key: "watchlist_starter_enabled", label: "Starter Enabled", desc: "Allow WATCHLIST starter positions" },
              { key: "watchlist_starter_min_score", label: "Min Score", desc: "Minimum composite score for starter eligibility" },
              { key: "watchlist_starter_size", label: "Starter Size", desc: "Fraction of full BUY size (0.33 = 33%)" },
              { key: "watchlist_starter_risk", label: "Starter Risk %", desc: "Risk % of portfolio per starter trade (0.25 = 0.25%). BUY uses 0.75%. Max 1.0%." },
              { key: "max_watchlist_sleeve", label: "Max Sleeve", desc: "Max fraction of capital for WATCHLIST starters" },
              { key: "max_watchlist_names", label: "Max Names", desc: "Maximum WATCHLIST starter positions" },
              { key: "watchlist_exit_score", label: "Exit Score", desc: "Exit starter if score drops below this" },
              { key: "watchlist_timeout_days", label: "Timeout Days", desc: "Auto-exit starter after this many days" },
            ].map(({ key, label, desc }) => {
              const originalValue = allocation[key];
              const currentVal = editedAllocation ? (editedAllocation[key] ?? String(originalValue ?? "")) : String(originalValue ?? "");
              return (
                <div key={key} className="space-y-1">
                  <p className="cursor-help text-xs text-slate-400" title={desc}>{label}</p>
                  {editingAllocation && editedAllocation ? (
                    renderEditableField(key, currentVal, originalValue, (k, newVal) =>
                      setEditedAllocation({ ...editedAllocation, [k]: newVal })
                    )
                  ) : (
                    <DisplayValue name={key} val={currentVal} originalValue={originalValue} />
                  )}
                </div>
              );
            })}
          </div>

          <Separator className="my-4 bg-slate-700/50" />

          {/* Read-only requirement rules */}
          <h3 className="text-xs text-slate-400 uppercase tracking-wider mb-3">Starter Requirements <span className="text-slate-600 text-[10px] ml-1">Read-only</span></h3>
          <div className="flex flex-wrap gap-2">
            {(allocation.watchlist_starter_requires ?? []).map((req: string) => (
              <span key={req} className="px-2 py-1 rounded-md bg-slate-800/40 border border-slate-700/30 text-xs text-slate-300">
                {req.replace(/_/g, " ")}
              </span>
            ))}
          </div>

          <Separator className="my-4 bg-slate-700/50" />

          {/* Read-only policy flags */}
          <h3 className="text-xs text-slate-400 uppercase tracking-wider mb-3">Policy <span className="text-slate-600 text-[10px] ml-1">Read-only</span></h3>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-400">Full position only on</span>
              <span className="font-mono-data text-green-400">{allocation.full_position_only_on ?? "BUY"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Max 1 per cluster</span>
              <span className={cn("font-mono-data", allocation.max_one_name_per_cluster ? "text-green-400" : "text-slate-500")}>
                {allocation.max_one_name_per_cluster ? "Yes" : "No"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Upgrade to full on BUY</span>
              <span className={cn("font-mono-data", allocation.add_to_full_only_on_buy_upgrade ? "text-green-400" : "text-slate-500")}>
                {allocation.add_to_full_only_on_buy_upgrade ? "Yes" : "No"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Never average down</span>
              <span className={cn("font-mono-data", allocation.never_average_down_watchlist ? "text-green-400" : "text-slate-500")}>
                {allocation.never_average_down_watchlist ? "Yes" : "No"}
              </span>
            </div>
          </div>
        </div>
      )}

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
                setBtStatusLocal({ running: true, progress: "Starting..." });
                try {
                  await api.triggerBacktest(btStartDate, btEndDate);
                  const poll = setInterval(async () => {
                    const s = await api.backtestStatus();
                    setBtStatusLocal(s);
                    if (!s.running) {
                      clearInterval(poll);
                      setBacktesting(false);
                    }
                  }, 3000);
                } catch {
                  setBacktesting(false);
                  setBtStatusLocal({ running: false, error: "Failed to start backtest" });
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
                    View Tearsheet &rarr;
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        <p className="mt-3 text-[11px] text-slate-400">
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
              {Object.entries(currentSchedule).map(([name, val]) => {
                const isTime = name === "morning_scan" || name === "eod_recap";
                const isTimezone = name === "timezone";
                return (
                  <div key={name} className="space-y-1">
                    <p className="cursor-help text-xs text-slate-400" title={getScheduleDescription(name)}>{getScheduleLabel(name)}</p>
                    {editingSchedule ? (
                      isTime ? (
                        <Input
                          type="time"
                          value={val}
                          onChange={(e) => setEditedSchedule({...currentSchedule, [name]: e.target.value})}
                          className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-32"
                        />
                      ) : isTimezone ? (
                        <select
                          value={val}
                          onChange={(e) => setEditedSchedule({...currentSchedule, [name]: e.target.value})}
                          className="bg-slate-800/50 border border-slate-700/50 h-8 text-sm font-mono-data rounded-md px-2 text-slate-200 w-40"
                        >
                          <option value="US/Eastern">US/Eastern</option>
                          <option value="US/Central">US/Central</option>
                          <option value="US/Mountain">US/Mountain</option>
                          <option value="US/Pacific">US/Pacific</option>
                          <option value="America/New_York">America/New_York</option>
                          <option value="America/Chicago">America/Chicago</option>
                          <option value="America/Los_Angeles">America/Los_Angeles</option>
                          <option value="UTC">UTC</option>
                        </select>
                      ) : (
                        <Input
                          type="number"
                          value={val}
                          onChange={(e) => setEditedSchedule({...currentSchedule, [name]: e.target.value})}
                          className="bg-slate-800/50 border-slate-700/50 h-8 text-sm font-mono-data w-24"
                        />
                      )
                    ) : (
                      <p className="font-mono-data text-slate-200 text-sm">{val}</p>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}
    </div>
  );
}
