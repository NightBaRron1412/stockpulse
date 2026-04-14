"use client";

import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn, actionBadgeClass, formatScore } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";

const PHASES = [
  { name: "PILOT", min: 0, label: "0-50 signals" },
  { name: "MEANINGFUL", min: 75, label: "75-100 signals" },
  { name: "SERIOUS", min: 150, label: "150-250 signals" },
  { name: "VALIDATED", min: 250, label: "250+ signals" },
];

export default function ValidationPage() {
  const { data, loading, error } = usePolling<any>(api.validation, 60000);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Model Validation</h1>
        <div className="glass-card p-6 animate-pulse"><div className="h-32 bg-slate-700/20 rounded" /></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Model Validation</h1>
        <div className="glass-card p-6 text-red-400">Failed to load: {error}</div>
      </div>
    );
  }

  const signals = data?.signals ?? [];
  const stats = data?.stats ?? {};
  const validation = data?.validation ?? {};
  const sampleSize = validation?.sample_size ?? {};
  const tests = validation?.tests ?? {};
  const verdict = validation?.verdict ?? {};
  const status = validation?.status ?? "collecting";
  const phase = sampleSize?.phase ?? "pilot";
  const buyCount = sampleSize?.buy_signals ?? 0;
  const watchlistCount = sampleSize?.watchlist_signals ?? 0;
  const distinctDates = sampleSize?.distinct_buy_dates ?? 0;
  const totalSignals = signals.length;

  // Phase progress
  const phaseIndex = PHASES.findIndex(p => p.name.toLowerCase() === phase.toLowerCase());
  const nextPhase = PHASES[Math.min(phaseIndex + 1, PHASES.length - 1)];
  const progressPct = nextPhase ? Math.min((totalSignals / nextPhase.min) * 100, 100) : 100;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Model Validation</h1>

      {/* Phase + Progress */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-4 mb-4">
          <span className={cn(
            "px-4 py-2 rounded-lg text-lg font-bold border",
            phase === "validated" ? "border-green-500/30 bg-green-500/10 text-green-400" :
            phase === "serious" ? "border-blue-500/30 bg-blue-500/10 text-blue-400" :
            "border-slate-500/30 bg-slate-500/10 text-slate-300"
          )}>
            {phase.toUpperCase()}
          </span>
          <div className="flex gap-1">
            {PHASES.map((p, i) => (
              <div key={p.name} className={cn("h-2 w-16 rounded-full", i <= phaseIndex ? "bg-blue-500" : "bg-slate-700/50")} />
            ))}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">Total Tracked</p>
            <p className="text-2xl font-bold font-mono-data text-slate-200">{totalSignals}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">BUY Signals</p>
            <p className="text-2xl font-bold font-mono-data text-green-400">{buyCount}</p>
          </div>
          <div>
            <p className="text-xs text-slate-500 uppercase mb-1">WATCHLIST Signals</p>
            <p className="text-2xl font-bold font-mono-data text-blue-400">{watchlistCount}</p>
          </div>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Progress to {nextPhase?.name ?? "VALIDATED"}</span>
            <span className="font-mono-data">{totalSignals}/{nextPhase?.min ?? 250}</span>
          </div>
          <Progress value={progressPct} className="h-2 bg-slate-700/50" />
        </div>
      </div>

      {/* Stats (if available) */}
      {Object.keys(stats).length > 0 && (
        <div className="glass-card p-6">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Performance by Horizon</h2>
          <Table>
            <TableHeader>
              <TableRow className="border-slate-700/50 hover:bg-transparent">
                <TableHead className="text-slate-400 text-xs">Period</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Signals</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Avg Return</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Excess vs SPY</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Hit Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {["5d", "10d", "20d"].map((period) => {
                const s = stats[period];
                if (!s || !s.count) return null;
                return (
                  <TableRow key={period} className="border-slate-700/30">
                    <TableCell className="font-semibold">{period}</TableCell>
                    <TableCell className="text-right font-mono-data text-xs">{s.count}</TableCell>
                    <TableCell className={cn("text-right font-mono-data text-xs", (s.avg_return ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>
                      {s.avg_return != null ? `${s.avg_return >= 0 ? "+" : ""}${s.avg_return.toFixed(2)}%` : "--"}
                    </TableCell>
                    <TableCell className={cn("text-right font-mono-data text-xs", (s.avg_excess_vs_spy ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>
                      {s.avg_excess_vs_spy != null ? `${s.avg_excess_vs_spy >= 0 ? "+" : ""}${s.avg_excess_vs_spy.toFixed(2)}%` : "--"}
                    </TableCell>
                    <TableCell className="text-right font-mono-data text-xs">
                      {s.hit_rate != null ? `${s.hit_rate.toFixed(0)}%` : "--"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Statistical Tests (if available) */}
      {Object.keys(tests).length > 0 && (
        <div className="glass-card p-6">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Statistical Tests (10d BUY vs SPY)</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {tests.paired_t && (
              <div className="p-4 rounded-lg bg-slate-800/30 border border-slate-700/30">
                <p className="text-xs text-slate-400 mb-1">Paired t-test</p>
                <p className="font-mono-data text-sm">
                  Mean excess: <span className={cn((tests.paired_t.mean_excess ?? 0) >= 0 ? "text-green-400" : "text-red-400")}>{tests.paired_t.mean_excess?.toFixed(3) ?? "--"}%</span>
                </p>
                <p className="font-mono-data text-xs text-slate-500">
                  p = {tests.paired_t.p_value_one_sided?.toFixed(4) ?? "--"} {tests.paired_t.significant_at_05 ? "✓ sig" : ""}
                </p>
              </div>
            )}
            {tests.binomial_hit_rate && (
              <div className="p-4 rounded-lg bg-slate-800/30 border border-slate-700/30">
                <p className="text-xs text-slate-400 mb-1">Hit Rate</p>
                <p className="font-mono-data text-sm">
                  {tests.binomial_hit_rate.hits ?? 0}/{tests.binomial_hit_rate.total ?? 0} = <span className="text-blue-400">{tests.binomial_hit_rate.hit_rate?.toFixed(0) ?? "--"}%</span>
                </p>
                <p className="font-mono-data text-xs text-slate-500">
                  Wilson 95% CI: [{tests.binomial_hit_rate.wilson_95_ci?.[0]?.toFixed(0) ?? "--"}%, {tests.binomial_hit_rate.wilson_95_ci?.[1]?.toFixed(0) ?? "--"}%]
                </p>
              </div>
            )}
            {tests.bootstrap && (
              <div className="p-4 rounded-lg bg-slate-800/30 border border-slate-700/30">
                <p className="text-xs text-slate-400 mb-1">Bootstrap 95% CI</p>
                <p className="font-mono-data text-sm">
                  [{tests.bootstrap.ci_95_lower?.toFixed(3) ?? "--"}%, {tests.bootstrap.ci_95_upper?.toFixed(3) ?? "--"}%]
                </p>
                <p className="font-mono-data text-xs text-slate-500">
                  {tests.bootstrap.ci_above_zero ? "✓ Above zero" : "Straddles zero"}
                </p>
              </div>
            )}
            {tests.buy_vs_watchlist && (
              <div className="p-4 rounded-lg bg-slate-800/30 border border-slate-700/30">
                <p className="text-xs text-slate-400 mb-1">BUY vs WATCHLIST</p>
                <p className="font-mono-data text-sm">
                  BUY: <span className="text-green-400">{tests.buy_vs_watchlist.buy_mean?.toFixed(3) ?? "--"}%</span> vs WL: <span className="text-blue-400">{tests.buy_vs_watchlist.watchlist_mean?.toFixed(3) ?? "--"}%</span>
                </p>
                <p className="font-mono-data text-xs text-slate-500">
                  {tests.buy_vs_watchlist.monotonic ? "✓ Monotonic" : "Not monotonic"}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Verdict */}
      <div className={cn("glass-card p-6 border-l-4",
        status === "working" ? "border-l-green-500" :
        status === "needs_calibration" ? "border-l-orange-500" :
        "border-l-blue-500"
      )}>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">Verdict</h2>
        {status === "working" ? (
          <p className="text-green-400 font-semibold">MODEL IS WORKING</p>
        ) : status === "needs_calibration" ? (
          <>
            <p className="text-orange-400 font-semibold">NEEDS CALIBRATION</p>
            <div className="mt-2 text-xs text-slate-400 space-y-1">
              {Object.entries(verdict).map(([k, v]: [string, any]) => (
                <p key={k}>{v ? "✓" : "✗"} {k.replace(/_/g, " ")}</p>
              ))}
            </div>
          </>
        ) : status === "insufficient_data" ? (
          <p className="text-slate-400">Need 10+ resolved BUY signals to begin testing. Currently tracking {totalSignals} signals — results will appear after 5+ trading days.</p>
        ) : (
          <p className="text-blue-400">Collecting data. {totalSignals} signals tracked so far. Statistical tests will run automatically once signals reach their 5/10/20 day checkpoints.</p>
        )}
      </div>

      {/* Tracked Signals Table */}
      {signals.length > 0 && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Tracked Signals ({signals.length})</h2>
          </div>
          <ScrollArea style={{ maxHeight: "400px" }}>
            <Table>
              <TableHeader>
                <TableRow className="border-slate-700/50 hover:bg-transparent">
                  <TableHead className="text-slate-400 text-xs">Date</TableHead>
                  <TableHead className="text-slate-400 text-xs">Ticker</TableHead>
                  <TableHead className="text-slate-400 text-xs">Action</TableHead>
                  <TableHead className="text-slate-400 text-xs text-right">Entry</TableHead>
                  <TableHead className="text-slate-400 text-xs text-right">Score</TableHead>
                  <TableHead className="text-slate-400 text-xs text-right">5d</TableHead>
                  <TableHead className="text-slate-400 text-xs text-right">10d</TableHead>
                  <TableHead className="text-slate-400 text-xs text-right">20d</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...signals].reverse().map((sig: any, i: number) => {
                  const cp5 = sig.checkpoints?.["5d"];
                  const cp10 = sig.checkpoints?.["10d"];
                  const cp20 = sig.checkpoints?.["20d"];
                  return (
                    <TableRow key={i} className="border-slate-700/30">
                      <TableCell className="font-mono-data text-xs text-slate-400">{sig.signal_date}</TableCell>
                      <TableCell className="font-semibold text-sm">{sig.ticker}</TableCell>
                      <TableCell>
                        <span className={cn("px-2 py-0.5 rounded text-xs font-medium", actionBadgeClass(sig.action))}>
                          {sig.action}
                        </span>
                      </TableCell>
                      <TableCell className="text-right font-mono-data text-xs">${(sig.entry_price ?? 0).toFixed(2)}</TableCell>
                      <TableCell className="text-right font-mono-data text-xs">{formatScore(sig.composite_score ?? 0)}</TableCell>
                      <TableCell className={cn("text-right font-mono-data text-xs", cp5?.checked ? ((cp5.excess_vs_spy ?? 0) >= 0 ? "text-green-400" : "text-red-400") : "text-slate-600")}>
                        {cp5?.checked ? `${(cp5.excess_vs_spy ?? 0) >= 0 ? "+" : ""}${(cp5.excess_vs_spy ?? 0).toFixed(1)}%` : "..."}
                      </TableCell>
                      <TableCell className={cn("text-right font-mono-data text-xs", cp10?.checked ? ((cp10.excess_vs_spy ?? 0) >= 0 ? "text-green-400" : "text-red-400") : "text-slate-600")}>
                        {cp10?.checked ? `${(cp10.excess_vs_spy ?? 0) >= 0 ? "+" : ""}${(cp10.excess_vs_spy ?? 0).toFixed(1)}%` : "..."}
                      </TableCell>
                      <TableCell className={cn("text-right font-mono-data text-xs", cp20?.checked ? ((cp20.excess_vs_spy ?? 0) >= 0 ? "text-green-400" : "text-red-400") : "text-slate-600")}>
                        {cp20?.checked ? `${(cp20.excess_vs_spy ?? 0) >= 0 ? "+" : ""}${(cp20.excess_vs_spy ?? 0).toFixed(1)}%` : "..."}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ScrollArea>
        </div>
      )}
    </div>
  );
}
