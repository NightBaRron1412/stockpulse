"use client";

import { Suspense, useState, useCallback, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { actionBadgeClass, formatScore, cn } from "@/lib/utils";
import { getSignalLabel, getSignalDescription } from "@/lib/signal-labels";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import type { Recommendation } from "@/lib/types";

function SignalsContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const paramTicker = searchParams.get("ticker") ?? "";
  const savedTicker = typeof window !== "undefined" ? sessionStorage.getItem("stockpulse_last_signal") ?? "" : "";
  const initialTicker = paramTicker || savedTicker;

  const [ticker, setTicker] = useState(initialTicker);
  const [data, setData] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAnalysis = useCallback(async (t: string) => {
    if (!t) return;
    setTicker(t);
    setLoading(true);
    setError(null);
    try {
      const result = await api.analyze(t);
      setData(result);
      sessionStorage.setItem("stockpulse_last_signal", t);
      router.replace(`/signals?ticker=${t}`, { scroll: false });
    } catch (e: any) {
      setError(e.message || "Analysis failed");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [router]);

  const handleAnalyze = useCallback(async () => {
    const t = ticker.trim().toUpperCase();
    if (t) runAnalysis(t);
  }, [ticker, runAnalysis]);

  useEffect(() => {
    if (initialTicker && !data) {
      runAnalysis(initialTicker.trim().toUpperCase());
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Signal Analysis</h1>

      {/* Search bar */}
      <div className="glass-card p-6">
        <div className="flex items-center gap-3 max-w-xl mx-auto">
          <Input
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
            placeholder="Analyze any ticker..."
            className="bg-slate-800/50 border-slate-700/50 h-12 text-lg"
          />
          <Button onClick={handleAnalyze} disabled={loading} className="h-12 px-6">
            {loading ? "Analyzing..." : "Analyze"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="glass-card p-6 text-red-400">
          {error}
        </div>
      )}

      {loading && (
        <div className="glass-card p-6 animate-pulse">
          <div className="h-6 bg-slate-700/50 rounded w-32 mb-4" />
          <div className="h-4 bg-slate-700/50 rounded w-full mb-2" />
          <div className="h-4 bg-slate-700/50 rounded w-3/4" />
        </div>
      )}

      {data && !loading && (
        <>
          {/* Ticker header */}
          <div className="glass-card p-6">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <h2 className="text-3xl font-bold">{data.ticker}</h2>
                  <span className={cn("px-3 py-1 rounded text-sm font-semibold", actionBadgeClass(data.action))}>
                    {data.action}
                  </span>
                  {data.high_conviction && (
                    <span className="badge-high-conviction px-2 py-0.5 rounded text-xs font-medium">
                      HIGH CONVICTION
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-300 max-w-2xl leading-relaxed">{data.thesis ?? ""}</p>
              </div>
              <div className="text-right">
                <p className="text-4xl font-bold font-mono-data text-slate-100">
                  {formatScore(data.composite_score ?? 0)}
                </p>
                <p className="text-xs text-slate-400 mt-1">Composite Score</p>
                <p className="text-sm font-mono-data text-slate-300 mt-1">{data.confidence ?? "--"}% confidence</p>
              </div>
            </div>
          </div>

          {/* Signal breakdown */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">Signal Breakdown</h3>
            <div className="space-y-2">
              {Object.entries(data.signals ?? {})
                .sort(([, a], [, b]) => Math.abs((b.score ?? 0) * (b.weight ?? 0)) - Math.abs((a.score ?? 0) * (a.weight ?? 0)))
                .map(([name, sig]) => {
                  const weighted = (sig.score ?? 0) * (sig.weight ?? 0);
                  const maxBar = 5; // scale reference
                  const pct = Math.min(Math.abs(weighted) / maxBar, 1) * 100;
                  const isPositive = weighted >= 0;
                  return (
                    <div key={name} className="flex items-center gap-3">
                      <span className="cursor-help text-xs text-slate-400 w-36 truncate text-right" title={getSignalDescription(name)}>
                        {getSignalLabel(name)}
                      </span>
                      <div className="flex-1 flex items-center h-5">
                        {/* center-aligned bar */}
                        <div className="w-full relative h-2 bg-slate-700/30 rounded-full">
                          {isPositive ? (
                            <div
                              className="absolute left-1/2 h-full rounded-r-full score-bar-positive"
                              style={{ width: `${pct / 2}%` }}
                            />
                          ) : (
                            <div
                              className="absolute right-1/2 h-full rounded-l-full score-bar-negative"
                              style={{ width: `${pct / 2}%` }}
                            />
                          )}
                          <div className="absolute left-1/2 top-0 bottom-0 w-px bg-slate-600" />
                        </div>
                      </div>
                      <span className={cn(
                        "font-mono-data text-xs w-14 text-right",
                        isPositive ? "text-green-400" : "text-red-400"
                      )}>
                        {weighted >= 0 ? "+" : ""}{weighted.toFixed(2)}
                      </span>
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Confirmation buckets */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {Object.entries(data.confirmation?.buckets ?? {}).map(([name, bucket]) => (
              <div key={name} className="glass-card p-5">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold capitalize text-slate-300">{name}</h4>
                  {bucket.confirms ? (
                    <svg className="w-5 h-5 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  )}
                </div>
                <p className="text-2xl font-bold font-mono-data text-slate-100">
                  {formatScore(bucket.avg_score)}
                </p>
                <p className="text-xs text-slate-500 mt-1">Avg bucket score</p>
              </div>
            ))}
          </div>

          {/* Summaries */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="glass-card p-5">
              <h4 className="text-xs text-slate-400 uppercase tracking-wider mb-2">Technical Summary</h4>
              <p className="text-sm text-slate-300 leading-relaxed">{data.technical_summary}</p>
            </div>
            <div className="glass-card p-5">
              <h4 className="text-xs text-slate-400 uppercase tracking-wider mb-2">Catalyst Summary</h4>
              <p className="text-sm text-slate-300 leading-relaxed">{data.catalyst_summary}</p>
            </div>
          </div>

          {/* Invalidation */}
          {data.invalidation && (
            <div className="glass-card p-5 border border-red-500/20 bg-red-500/5">
              <h4 className="text-xs text-red-400 uppercase tracking-wider mb-2">Invalidation</h4>
              <p className="text-sm text-red-300 leading-relaxed">{data.invalidation}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function SignalsPage() {
  return (
    <Suspense fallback={
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Signal Analysis</h1>
        <div className="glass-card p-6 animate-pulse">
          <div className="h-12 bg-slate-700/20 rounded" />
        </div>
      </div>
    }>
      <SignalsContent />
    </Suspense>
  );
}
