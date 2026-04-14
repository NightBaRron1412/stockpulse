"use client";

import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { cn, actionBadgeClass, formatScore } from "@/lib/utils";
import { getSignalLabel, getSignalDescription } from "@/lib/signal-labels";
import type { Recommendation } from "@/lib/types";

interface TickerDetailModalProps {
  ticker: string | null;
  onClose: () => void;
}

export function TickerDetailModal({ ticker, onClose }: TickerDetailModalProps) {
  const [data, setData] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) { setData(null); return; }
    setLoading(true);
    api.analyze(ticker).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [ticker]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!ticker) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-4 z-50 flex flex-col rounded-2xl border border-slate-700/50 bg-slate-900 shadow-2xl shadow-black/50 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-slate-700/50 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold">{ticker}</h2>
            {data && (
              <>
                <span className={cn("px-2 py-0.5 rounded text-xs font-medium", actionBadgeClass(data.action))}>
                  {data.action}
                </span>
                <span className="font-mono-data text-sm text-slate-300">{formatScore(data.composite_score)}</span>
              </>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-slate-100 transition-colors"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* TradingView Chart (left 60%) */}
          <div className="flex-[3] border-r border-slate-700/50">
            <iframe
              key={ticker}
              src={`https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=${ticker}&interval=D&hidesidetoolbar=0&symboledit=1&saveimage=0&toolbarbg=0f172a&studies=MAExp%4025&studies=MASimple%4050&studies=MASimple%40200&theme=dark&style=1&timezone=America%2FNew_York&studies_overrides=%7B%7D&overrides=%7B%22paneProperties.background%22%3A%22%230f172a%22%2C%22paneProperties.backgroundType%22%3A%22solid%22%7D&enabled_features=[]&disabled_features=[]&locale=en&utm_source=stockpulse&utm_medium=widget&utm_campaign=chart`}
              className="w-full h-full border-0"
              allowFullScreen
            />
          </div>

          {/* Signal Analysis (right 40%) */}
          <div className="flex-[2] overflow-y-auto p-5 space-y-4">
            {loading ? (
              <div className="space-y-3 animate-pulse">
                <div className="h-6 bg-slate-700/50 rounded w-32" />
                <div className="h-4 bg-slate-700/50 rounded w-full" />
                <div className="h-4 bg-slate-700/50 rounded w-3/4" />
              </div>
            ) : data ? (
              <>
                {/* Thesis */}
                <div>
                  <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Thesis</h3>
                  <p className="text-sm text-slate-200 leading-relaxed">{data.thesis}</p>
                </div>

                {/* Invalidation */}
                {data.invalidation && (
                  <div>
                    <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Invalidation</h3>
                    <p className="text-xs text-red-400/80">{data.invalidation}</p>
                  </div>
                )}

                {/* Confirmation Buckets */}
                {data.confirmation && (
                  <div>
                    <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-2">
                      Confirmation ({(data.confirmation as any).confirming_count ?? 0}/{(data.confirmation as any).total_buckets ?? 3})
                    </h3>
                    <div className="flex gap-2">
                      {Object.entries((data.confirmation as any).buckets ?? {}).map(([name, bucket]: [string, any]) => (
                        <div key={name} className={cn(
                          "flex-1 px-3 py-2 rounded-lg border text-center text-xs",
                          bucket?.confirms
                            ? "border-green-500/30 bg-green-500/5 text-green-400"
                            : "border-slate-700/30 bg-slate-800/30 text-slate-500"
                        )}>
                          <div className="font-medium capitalize">{name}</div>
                          <div className="font-mono-data mt-0.5">{bucket?.confirms ? "✓" : "✗"}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Signal Breakdown */}
                <div>
                  <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-2">Signals</h3>
                  <div className="space-y-1.5">
                    {Object.entries(data.signals ?? {})
                      .filter(([, sig]: [string, any]) => (sig?.weight ?? 0) > 0)
                      .sort(([, a]: any, [, b]: any) => Math.abs((b?.score ?? 0) * (b?.weight ?? 0)) - Math.abs((a?.score ?? 0) * (a?.weight ?? 0)))
                      .map(([name, sig]: [string, any]) => {
                        const weighted = (sig?.score ?? 0) * (sig?.weight ?? 0);
                        return (
                          <div key={name} className="flex items-center gap-2" title={getSignalDescription(name)}>
                            <span className="text-[11px] text-slate-400 w-24 truncate text-right cursor-help">{getSignalLabel(name)}</span>
                            <div className="flex-1 flex items-center">
                              <div className="w-full h-1.5 bg-slate-700/30 rounded-full overflow-hidden relative">
                                <div
                                  className={cn("absolute top-0 h-full rounded-full",
                                    weighted >= 0 ? "left-1/2 score-bar-positive" : "right-1/2 score-bar-negative"
                                  )}
                                  style={{ width: `${Math.min(Math.abs(weighted) * 500, 50)}%` }}
                                />
                              </div>
                            </div>
                            <span className={cn("font-mono-data text-[11px] w-12 text-right",
                              weighted >= 0 ? "text-green-400" : "text-red-400"
                            )}>
                              {weighted >= 0 ? "+" : ""}{weighted.toFixed(1)}
                            </span>
                          </div>
                        );
                      })}
                  </div>
                </div>

                {/* Technical & Catalyst Summary */}
                <div className="space-y-2 text-xs text-slate-400">
                  {data.technical_summary && (
                    <p><span className="text-slate-500">Technical:</span> {data.technical_summary}</p>
                  )}
                  {data.catalyst_summary && (
                    <p><span className="text-slate-500">Catalysts:</span> {data.catalyst_summary}</p>
                  )}
                </div>

                {/* Risk */}
                {data.risk && (
                  <div>
                    <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Risk</h3>
                    <div className="text-xs text-slate-400 space-y-0.5">
                      <p>Sector: {(data.risk as any).sector || "--"} / {(data.risk as any).industry || "--"}</p>
                      {(data.risk as any).cluster_tickers?.length > 0 && (
                        <p>Cluster: {(data.risk as any).cluster_tickers.join(", ")}</p>
                      )}
                      {!(data.risk as any).allowed && (data.risk as any).reasons?.length > 0 && (
                        <div className="mt-1 text-orange-400">
                          {(data.risk as any).reasons.map((r: string, i: number) => <p key={i}>⚠ {r}</p>)}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Quick Actions */}
                <div className="flex gap-2 pt-2">
                  <a
                    href={`/signals?ticker=${ticker}`}
                    className="px-3 py-1.5 rounded-lg text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors"
                  >
                    Full Analysis →
                  </a>
                </div>
              </>
            ) : (
              <p className="text-sm text-slate-500">No analysis data available</p>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
