"use client";

import { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { cn, actionBadgeClass, formatScore } from "@/lib/utils";
import { getSignalLabel, getSignalDescription } from "@/lib/signal-labels";
import type { Recommendation } from "@/lib/types";

interface TickerDetailModalProps {
  ticker: string | null;
  onClose: () => void;
}

// Cache analysis results for 10 minutes to avoid API exhaustion
const analysisCache: Record<string, { data: Recommendation; timestamp: number }> = {};
const CACHE_TTL = 10 * 60 * 1000; // 10 minutes

export function TickerDetailModal({ ticker, onClose }: TickerDetailModalProps) {
  const [data, setData] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) { setData(null); return; }

    // Check cache first
    const cached = analysisCache[ticker];
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      setData(cached.data);
      setLoading(false);
      return;
    }

    setLoading(true);
    api.analyze(ticker)
      .then((result) => {
        setData(result);
        analysisCache[ticker] = { data: result, timestamp: Date.now() };
      })
      .catch(() => setData(null))
      .finally(() => setLoading(false));
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
            <TradingViewChart ticker={ticker} />
          </div>

          {/* Signal Analysis (right 40%) */}
          <div className="flex-[2] overflow-y-auto p-5 space-y-4">
            {loading ? (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <div className="w-8 h-8 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
                <p className="text-sm text-slate-400">Analyzing {ticker}...</p>
              </div>
            ) : data ? (
              <>
                {/* Thesis */}
                <div>
                  <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-1">Thesis</h3>
                  <p className="text-sm text-slate-200 leading-relaxed">{data.thesis}</p>
                </div>

                {/* Price Levels */}
                <div>
                  <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-2">Price Levels</h3>
                  {(() => {
                    const inv = typeof data.invalidation === "string" ? data.invalidation : "";
                    const current = (data as any).current_price;
                    // Parse all price levels from invalidation text
                    const stopMatch = inv.match(/Stop:\s*\$?([\d.]+)/);
                    const emaMatch = inv.match(/20 EMA[:\s(]*\$?([\d.]+)/);
                    const smaMatch = inv.match(/50 SMA[:\s(]*\$?([\d.]+)/);
                    const stop = stopMatch ? parseFloat(stopMatch[1]) : null;
                    const ema20 = emaMatch ? parseFloat(emaMatch[1]) : null;
                    const sma50 = smaMatch ? parseFloat(smaMatch[1]) : null;

                    return (
                      <div className="flex flex-wrap gap-4 text-xs py-2 px-3 rounded-lg bg-slate-800/40 border border-slate-700/30">
                        {current != null && current > 0 && (
                          <span className="font-mono-data">
                            Current: <span className="text-slate-200 font-medium">${current.toFixed(2)}</span>
                          </span>
                        )}
                        {(data as any).entry_price != null && (data as any).entry_price > 0 && (
                          <span className="font-mono-data">
                            Entry: <span className="text-green-400 font-medium">${(data as any).entry_price.toFixed(2)}</span>
                          </span>
                        )}
                        {ema20 != null && (
                          <span className="font-mono-data">
                            20 EMA: <span className="text-blue-400 font-medium">${ema20.toFixed(2)}</span>
                          </span>
                        )}
                        {sma50 != null && (
                          <span className="font-mono-data">
                            50 SMA: <span className="text-amber-400 font-medium">${sma50.toFixed(2)}</span>
                          </span>
                        )}
                        {stop != null && (
                          <span className="font-mono-data">
                            Stop: <span className="text-red-400 font-medium">${stop.toFixed(2)}</span>
                          </span>
                        )}
                        {current && stop && (
                          <span className="font-mono-data text-slate-500">
                            Risk: {(((current - stop) / current) * 100).toFixed(1)}%
                          </span>
                        )}
                        {current && ema20 && !stop && (
                          <span className="font-mono-data text-slate-500">
                            vs EMA: {(((current - ema20) / ema20) * 100).toFixed(1)}%
                          </span>
                        )}
                      </div>
                    );
                  })()}
                  {(data as any).entry_timing && (
                    <p className={cn("text-[11px] mt-1.5 font-medium",
                      (data as any).entry_timing.timing === "now" ? "text-green-400/80" :
                      (data as any).entry_timing.timing === "wait" ? "text-amber-400/80" :
                      "text-blue-400/80"
                    )}>
                      {(data as any).entry_timing.timing === "now" ? "Good entry zone" :
                       (data as any).entry_timing.timing === "wait" ? "Wait for better entry" :
                       "Consider limit order"}: {(data as any).entry_timing.reason}
                    </p>
                  )}
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

function TradingViewChart({ ticker }: { ticker: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [interval, setInterval_] = useState("D");

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current;
    while (container.firstChild) container.removeChild(container.firstChild);

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.width = "100%";
    widgetDiv.style.height = "100%";
    container.appendChild(widgetDiv);

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.textContent = JSON.stringify({
      autosize: true,
      symbol: ticker,
      interval: interval,
      timezone: "America/New_York",
      theme: "dark",
      style: "3",
      locale: "en",
      backgroundColor: "rgba(15, 23, 42, 1)",
      gridColor: "rgba(30, 41, 59, 0.5)",
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      calendar: false,
      studies: interval === "D"
        ? ["MAExp@tv-basicstudies|20", "MASimple@tv-basicstudies|50", "MASimple@tv-basicstudies|200"]
        : ["MAExp@tv-basicstudies|9", "VWAP@tv-basicstudies"],
      support_host: "https://www.tradingview.com",
    });
    container.appendChild(script);
  }, [ticker, interval]);

  return (
    <div className="w-full h-full flex flex-col">
      <div className="flex gap-1 px-2 pt-1 pb-1">
        {[
          { label: "5m", value: "5" },
          { label: "15m", value: "15" },
          { label: "1H", value: "60" },
          { label: "D", value: "D" },
          { label: "W", value: "W" },
        ].map(({ label, value }) => (
          <button key={value} onClick={() => setInterval_(value)}
            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors ${
              interval === value
                ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                : "text-slate-500 hover:text-slate-300 border border-transparent"
            }`}>
            {label}
          </button>
        ))}
      </div>
      <div className="flex-1 min-h-[300px]" ref={containerRef} />
    </div>
  );
}
