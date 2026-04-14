"use client";

import { usePolling } from "@/hooks/use-polling";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface ValidationStats {
  period: string;
  signals_count: number;
  avg_return: number;
  excess_vs_spy: number;
  hit_rate: number;
}

interface TestResult {
  test: string;
  statistic: number;
  p_value: number;
  significant: boolean;
}

interface ValidationData {
  phase: string;
  phase_progress: number;
  stats: ValidationStats | null;
  test_results: TestResult[];
  verdict: string;
  verdict_status: "positive" | "negative" | "neutral";
  recent_signals: Array<{
    ticker: string;
    action: string;
    score: number;
    return_pct: number | null;
    date: string;
  }>;
}

const PHASE_ORDER = ["PILOT", "MEANINGFUL", "SERIOUS", "VALIDATED"];

function phaseColor(phase: string): string {
  switch (phase) {
    case "PILOT": return "text-blue-400 bg-blue-500/10 border-blue-500/20";
    case "MEANINGFUL": return "text-violet-400 bg-violet-500/10 border-violet-500/20";
    case "SERIOUS": return "text-orange-400 bg-orange-500/10 border-orange-500/20";
    case "VALIDATED": return "text-green-400 bg-green-500/10 border-green-500/20";
    default: return "text-slate-400 bg-slate-500/10 border-slate-500/20";
  }
}

function verdictColor(status: string): string {
  switch (status) {
    case "positive": return "border-green-500/30 bg-green-500/5 text-green-400";
    case "negative": return "border-red-500/30 bg-red-500/5 text-red-400";
    default: return "border-slate-500/30 bg-slate-500/5 text-slate-400";
  }
}

export default function ValidationPage() {
  const { data, loading, error } = usePolling<ValidationData>(api.validation, 60000);

  if (loading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Model Validation</h1>
        <div className="glass-card p-6 animate-pulse">
          <div className="h-8 bg-slate-700/50 rounded w-32 mb-4" />
          <div className="h-4 bg-slate-700/50 rounded w-full mb-2" />
          <div className="h-4 bg-slate-700/50 rounded w-3/4" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Model Validation</h1>
        <div className="glass-card p-6 text-red-400">Failed to load validation data: {error}</div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Model Validation</h1>
        <div className="glass-card p-8 text-center text-slate-500">
          No validation data yet -- run more scans to start tracking model performance
        </div>
      </div>
    );
  }

  const phaseIndex = PHASE_ORDER.indexOf(data.phase);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Model Validation</h1>

      {/* Phase badge + progress */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-6 mb-4">
          <span className={cn("px-4 py-2 rounded-lg text-lg font-bold border", phaseColor(data.phase))}>
            {data.phase}
          </span>
          <div className="flex gap-1">
            {PHASE_ORDER.map((p, i) => (
              <div
                key={p}
                className={cn(
                  "h-2 w-16 rounded-full",
                  i <= phaseIndex ? "bg-blue-500" : "bg-slate-700/50"
                )}
              />
            ))}
          </div>
        </div>
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Progress to next phase</span>
            <span className="font-mono-data">{data.phase_progress}%</span>
          </div>
          <Progress value={data.phase_progress} className="h-2 bg-slate-700/50" />
        </div>
      </div>

      {/* Stats table */}
      {data.stats && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Performance Statistics</h2>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-slate-700/30">
            <div className="p-5">
              <p className="text-xs text-slate-400 mb-1">Period</p>
              <p className="text-lg font-semibold text-slate-200">{data.stats.period}</p>
            </div>
            <div className="p-5">
              <p className="text-xs text-slate-400 mb-1">Total Signals</p>
              <p className="text-lg font-bold font-mono-data text-slate-200">{data.stats.signals_count}</p>
            </div>
            <div className="p-5">
              <p className="text-xs text-slate-400 mb-1">Avg Return</p>
              <p className={cn("text-lg font-bold font-mono-data", data.stats.avg_return >= 0 ? "text-green-400" : "text-red-400")}>
                {data.stats.avg_return >= 0 ? "+" : ""}{data.stats.avg_return.toFixed(2)}%
              </p>
            </div>
            <div className="p-5">
              <p className="text-xs text-slate-400 mb-1">Hit Rate</p>
              <p className="text-lg font-bold font-mono-data text-slate-200">{data.stats.hit_rate.toFixed(0)}%</p>
            </div>
          </div>
        </div>
      )}

      {/* Test results */}
      {data.test_results && data.test_results.length > 0 && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Statistical Tests</h2>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-slate-700/50 hover:bg-transparent">
                <TableHead className="text-slate-400 text-xs">Test</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Statistic</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">p-value</TableHead>
                <TableHead className="text-slate-400 text-xs">Significant</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.test_results.map((test) => (
                <TableRow key={test.test} className="border-slate-700/30 hover:bg-slate-800/30">
                  <TableCell className="text-sm">{test.test}</TableCell>
                  <TableCell className="font-mono-data text-right text-xs">{test.statistic.toFixed(4)}</TableCell>
                  <TableCell className={cn(
                    "font-mono-data text-right text-xs",
                    test.p_value < 0.05 ? "text-green-400" : "text-slate-400"
                  )}>
                    {test.p_value.toFixed(4)}
                  </TableCell>
                  <TableCell>
                    {test.significant ? (
                      <span className="text-green-400 text-xs font-medium">Yes</span>
                    ) : (
                      <span className="text-slate-500 text-xs">No</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Verdict */}
      <div className={cn("glass-card p-6 border", verdictColor(data.verdict_status))}>
        <h3 className="text-sm font-semibold mb-2">Verdict</h3>
        <p className="text-lg">{data.verdict}</p>
      </div>

      {/* Recent signals */}
      {data.recent_signals && data.recent_signals.length > 0 && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-700/50">
            <h2 className="text-sm font-semibold text-slate-300">Recent Signals</h2>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="border-slate-700/50 hover:bg-transparent">
                <TableHead className="text-slate-400 text-xs">Ticker</TableHead>
                <TableHead className="text-slate-400 text-xs">Action</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Score</TableHead>
                <TableHead className="text-slate-400 text-xs text-right">Return</TableHead>
                <TableHead className="text-slate-400 text-xs">Date</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.recent_signals.map((sig, i) => (
                <TableRow key={`${sig.ticker}-${i}`} className="border-slate-700/30 hover:bg-slate-800/30">
                  <TableCell className="font-semibold">{sig.ticker}</TableCell>
                  <TableCell className="text-xs">{sig.action}</TableCell>
                  <TableCell className="font-mono-data text-right text-xs">{sig.score.toFixed(1)}</TableCell>
                  <TableCell className={cn(
                    "font-mono-data text-right text-xs",
                    sig.return_pct !== null
                      ? sig.return_pct >= 0 ? "text-green-400" : "text-red-400"
                      : "text-slate-500"
                  )}>
                    {sig.return_pct !== null ? `${sig.return_pct >= 0 ? "+" : ""}${sig.return_pct.toFixed(2)}%` : "--"}
                  </TableCell>
                  <TableCell className="text-xs text-slate-400 font-mono-data">{sig.date}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
